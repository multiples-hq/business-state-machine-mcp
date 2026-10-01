"""One read that assembles a whole chain: the quote, its bookings and their jobs,
with the SOP each adopts, its phases and milestone status, the parties in
their roles, the evidence placed on it, the latest memo and the documents.

The harness reads it at the start of a turn instead of stitching six reads.
A screen renders the same dictionary. Nothing is derived beyond joining what
the ledger already holds: no status is invented, no "open" flag, no ranking.
Where a fact is missing or uncited on this chain the brief says so in its last
section rather than leaving a blank that could be read as "nothing to say".

There is one answer, this dictionary, for the harness and the screen. A
file written from it is a cache, never a second ledger.
"""

from datetime import date, datetime

from sop import reason_as_read

EVIDENCE_LIMIT = 40

_OWNED = 'coalesce({a}.quote_id, {a}.booking_id, {a}.job_id) = %(id)s'


def _iso(value):
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return None if value is None else str(value)


class CaseBriefMixin:
    def _rows(self, query, params=None):
        return self.connection.execute(query, params or {}).fetchall()

    def work_chain(self, identifier):
        """The quote, bookings and jobs that one work id belongs to, oldest first.

        A quote id gives the quote, every booking under it and every job linked
        to those bookings. A booking or job id resolves to the same chain. A job
        with no booking link stands alone. None when the id names no work.
        """
        found = self._rows('''
            SELECT 'quote', q.id, q.id FROM spine.quotes q WHERE q.id = %(id)s
            UNION ALL SELECT 'booking', b.id, b.quote_id FROM spine.bookings b WHERE b.id = %(id)s
            UNION ALL SELECT 'job', j.id, b.quote_id FROM spine.jobs j
                LEFT JOIN spine.job_booking_links l ON l.job_id = j.id
                LEFT JOIN spine.bookings b ON b.id = l.booking_id WHERE j.id = %(id)s
        ''', {'id': identifier})
        if not found:
            return None
        kind, work_id, quote_id = found[0]
        if quote_id is None:
            return [('job', work_id)]
        chain = [('quote', quote_id)]
        for booking_id, in self._rows(
                'SELECT id FROM spine.bookings WHERE quote_id = %(q)s ORDER BY recorded_at, id',
                {'q': quote_id}):
            chain.append(('booking', booking_id))
            for job_id, in self._rows('''
                    SELECT job_id FROM spine.job_booking_links WHERE booking_id = %(b)s
                    ORDER BY recorded_at, job_id''', {'b': booking_id}):
                chain.append(('job', job_id))
        return chain

    def case_brief(self, identifier):
        """The whole chain one work id belongs to, as one dictionary. None for an
        unknown id."""
        chain = self.work_chain(identifier)
        if chain is None:
            return None
        items = [self._brief_item(kind, work_id) for kind, work_id in chain]
        operator = self._rows('SELECT name FROM spine.parties WHERE is_operator'
                              if self._parties_installed() else
                              'SELECT name FROM spine.organizations WHERE is_operator')
        gaps = []
        if not operator:
            gaps.append('No organization is marked as the operator, so "internal" '
                        'cannot be told from "customer" by the ledger.')
        for item in items:
            named = f"The {item['kind']} \"{item['title']}\""
            if item['sop'] is None:
                gaps.append(f'{named} adopts no SOP version.')
            if not item['parties']:
                gaps.append(f'{named} has no recorded parties.')
        uncited = sum(1 for item in items for p in item['parties'] if not p['evidence'])
        if uncited:
            gaps.append(f'{uncited} party role(s) on this chain cite no evidence.')
        if self._parties_installed() and not any(
                i['kind'] == 'address' for item in items for p in item['parties']
                for i in p.get('identifiers', [])):
            gaps.append('No address is recorded for any party on this chain.')
        placed = [row for item in items for row in item['evidence']['rows'] if row['source_at']]
        newest = max(placed, key=lambda r: r['source_at'], default=None)
        return {'requested_id': str(identifier),
                'chain': {'root_kind': items[0]['kind'], 'root_id': items[0]['id'],
                          'title': items[0]['title']},
                # What the ledger has seen of this chain's mail: the newest dated
                # source placed on any item. A reader compares it with the mailbox.
                'newest_evidence': newest,
                'operator': operator[0][0] if operator else None,
                'read_at': datetime.now().astimezone().isoformat(timespec='seconds'),
                'items': items, 'not_recorded': gaps}

    def _brief_item(self, kind, work_id):
        params = {'id': work_id}
        table = {'quote': 'quotes', 'booking': 'bookings', 'job': 'jobs'}[kind]
        row = self._rows(f'SELECT title, actor, recorded_at FROM spine.{table} WHERE id = %(id)s',
                         params)[0]
        item = {'kind': kind, 'id': str(work_id), 'title': row[0], 'actor': row[1],
                'recorded_at': _iso(row[2])}
        item['references'] = [
            {'type': t, 'source': s, 'value': v} for t, s, v in self._rows(
                f'''SELECT reference_type, source, value FROM spine.external_references r
                    WHERE {_OWNED.format(a='r')} ORDER BY recorded_at, id''', params)]
        item['sop'] = self._brief_sop(params)
        (item['phases'], item['unassigned_milestones'], item['history_milestones'],
         item['charges']) = self._brief_phases(
            params, item['sop']['adoption_id'] if item['sop'] else None)
        # Bills linked to this item; one with no lines reads "billed, stated
        # total, lines not recorded".
        item['invoices'] = self.linked_invoices(work_id)
        item['parties'] = self._brief_parties(params)
        item['evidence'] = self._brief_evidence(params)
        item['memos'] = self._brief_memos(params)
        item['documents'] = self._brief_documents(work_id) if kind == 'job' else []
        return item

    def _brief_sop(self, params):
        rows = self._rows(f'''
            SELECT a.id, v.id, v.name, v.version, v.tag, a.reason, a.actor, a.recorded_at,
                   (SELECT count(*) FROM spine.sop_adoptions r
                    WHERE {_OWNED.format(a='r')} AND r.id <> a.id) AS replaced, a.previous_adoption_id,
                   {'a.follows_adoption_id' if self._chain_sop_installed() else 'NULL::uuid'}
            FROM spine.sop_adoptions a JOIN spine.sop_versions v ON v.id = a.sop_version_id
            WHERE {_OWNED.format(a='a')} AND NOT EXISTS (
                SELECT 1 FROM spine.sop_adoptions n WHERE n.previous_adoption_id = a.id)
            ORDER BY a.recorded_at DESC LIMIT 1''', params)
        if not rows:
            return None
        adoption_id, version_id, name, version, tag, reason, actor, at, replaced, previous, follows = rows[0]
        cites = [{'evidence_id': str(e), 'source_locator': loc, 'source_at': _iso(sat)}
                 for e, loc, sat in self._rows('''
                    SELECT e.id, e.source_locator, e.source_at
                    FROM spine.sop_adoption_citations c JOIN spine.evidence e ON e.id = c.evidence_id
                    WHERE c.adoption_id = %(a)s ORDER BY e.source_at, e.id''', {'a': adoption_id})]
        return {'adoption_id': str(adoption_id), 'version_id': str(version_id), 'name': name,
                'version': version, 'tag': tag, 'reason': reason_as_read(reason), 'actor': actor,
                'recorded_at': _iso(at), 'replaced_adoptions': replaced, 'cites': cites,
                'previous_adoption_id': str(previous) if previous else None,
                # The quote's adoption this stage follows; null when this item chose itself.
                'follows_adoption_id': str(follows) if follows else None}

    def _brief_phases(self, params, current):
        """Phases in the current SOP's order, each with the milestones followed now.

        After a job changes SOP, a milestone some earlier adoption bound and the
        current one does not is history: it keeps its status but leaves the
        phases, and is listed in history_milestones under its phase name. A
        milestone no SOP ever bound (one added by hand) is always current.
        """
        in_current, sop_order = set(), {}
        if current:
            in_current = {str(m) for (m,) in self._rows(
                'SELECT milestone_id FROM spine.sop_adoption_milestones WHERE adoption_id = %(a)s',
                {'a': current})}
            sop_order = {str(p): o for p, o in self._rows(
                'SELECT phase_id, definition_order FROM spine.sop_adoption_phases '
                'WHERE adoption_id = %(a)s', {'a': current})}
        criteria, bound_by = {}, {}
        for m, c, adoption in self._rows(f'''
            SELECT b.milestone_id, b.completion_criterion, b.adoption_id
            FROM spine.sop_adoption_milestones b JOIN spine.sop_adoptions a ON a.id = b.adoption_id
            WHERE {_OWNED.format(a='a')} ORDER BY a.recorded_at''', params):
            criteria[str(m)] = c
            bound_by[str(m)] = str(adoption)  # the latest adoption that binds it wins
        latest = {}
        for row in self._rows('''
                SELECT DISTINCT ON (j.milestone_id) j.milestone_id, j.id, j.status, j.explanation,
                       j.actor, j.recorded_at, j.occurred_on, j.occurrence_precision
                FROM spine.judgments j JOIN spine.milestones m ON m.id = j.milestone_id
                WHERE ''' + _OWNED.format(a='m') + '''
                ORDER BY j.milestone_id, j.position DESC''', params):
            milestone_id, judgment_id, status, explanation, actor, at, on, precision = row
            cites = [{'evidence_id': str(e), 'source_locator': loc, 'source_at': _iso(sat)}
                     for e, loc, sat in self._rows('''
                        SELECT e.id, e.source_locator, e.source_at FROM spine.citations c
                        JOIN spine.evidence e ON e.id = c.evidence_id
                        WHERE c.judgment_id = %(j)s ORDER BY e.source_at, e.id''',
                                                    {'j': judgment_id})]
            memo = self._rows('''
                SELECT m.id, m.summary, m.decision, m.waiting_for, m.recorded_at, m.actor,
                       (SELECT count(*) FROM spine.visit_memo_judgments x WHERE x.memo_id = m.id)
                FROM spine.visit_memo_judgments l JOIN spine.visit_memos m ON m.id = l.memo_id
                WHERE l.judgment_id = %(j)s ORDER BY m.recorded_at DESC LIMIT 1''',
                              {'j': judgment_id})
            latest[str(milestone_id)] = {
                'judgment_id': str(judgment_id), 'status': status, 'explanation': explanation,
                'actor': actor, 'recorded_at': _iso(at), 'occurred_on': _iso(on),
                'occurrence_precision': precision, 'cites': cites,
                # The memo of the review that made this judgment: one memo per
                # visit, so the same memo sits under every milestone it judged.
                'memo': {'id': str(memo[0][0]), 'summary': memo[0][1], 'decision': memo[0][2],
                         'waiting_for': memo[0][3], 'recorded_at': _iso(memo[0][4]),
                         'actor': memo[0][5], 'judgments': memo[0][6]} if memo else None}
        phase_rows = self._rows(
            'SELECT p.id, p.name, p.display_order FROM spine.phases p WHERE '
            + _OWNED.format(a='p') + ' ORDER BY p.display_order, p.id', params)
        phase_names = {str(pid): name for pid, name, _ in phase_rows}
        # A milestone with a charge line is a charge, listed under charges.
        # One an SOP named also stays where it is; one no SOP named is listed
        # only there. read_work_money gives the amounts.
        charge_ids, charges = self.charge_milestone_ids(params['id']), []
        milestones, history, holds_history = {}, [], set()
        for milestone_id, title, phase_id, at in self._rows('''
                SELECT m.id, m.title, a.phase_id, m.recorded_at FROM spine.milestones m
                LEFT JOIN spine.milestone_phase_assignments a ON a.milestone_id = m.id
                WHERE ''' + _OWNED.format(a='m') + ' ORDER BY m.recorded_at, m.id', params):
            key = str(milestone_id)
            phase = str(phase_id) if phase_id else None
            entry = {
                'id': key, 'title': title, 'from_sop': key in criteria,
                'criterion': criteria.get(key),
                # The adoption that bound it: after a break glass, milestones of the
                # replaced adoption are the ones a screen folds as not followed.
                'adoption_id': bound_by.get(key),
                'status': latest[key]['status'] if key in latest else 'unassessed',
                'latest': latest.get(key)}
            if key in charge_ids:
                charges.append({'phase': phase_names.get(phase), **entry})
                if key not in criteria:
                    continue
            if current and key in criteria and key not in in_current:
                history.append({'phase': phase_names.get(phase), **entry})
                holds_history.add(phase)
            else:
                milestones.setdefault(phase, []).append(entry)
        # A phase that now holds only history, and that the current SOP does not
        # name, leaves the list. The current SOP's own order comes first.
        phases = sorted(
            ({'id': str(pid), 'name': name, 'display_order': order,
              'sop_order': sop_order.get(str(pid)), 'milestones': milestones.get(str(pid), [])}
             for pid, name, order in phase_rows
             if str(pid) in sop_order or str(pid) in milestones or str(pid) not in holds_history),
            key=lambda p: (p['sop_order'] is None, p['sop_order'] or 0, p['display_order']))
        return phases, milestones.get(None, []), history, charges

    def _brief_parties(self, params):
        if self._parties_installed():
            return self._brief_roles(params['id'])
        out = []
        for row in self._rows('''
                SELECT p.role, p.actor, p.recorded_at, o.id, o.name, o.is_operator,
                       x.id, x.display_name, x.kind
                FROM spine.participations p
                LEFT JOIN spine.organizations o ON o.id = p.organization_id
                LEFT JOIN spine.people x ON x.id = p.person_id
                WHERE ''' + _OWNED.format(a='p') + ' ORDER BY p.recorded_at, p.id', params):
            role, actor, at, org_id, org_name, is_operator, person_id, person_name, kind = row
            party = {'role': role, 'actor': actor, 'recorded_at': _iso(at)}
            if org_id:
                party.update({'party_id': str(org_id), 'name': org_name, 'kind': 'organization',
                              'is_operator': bool(is_operator), 'affiliated_with': []})
            else:
                party.update({'party_id': str(person_id), 'name': person_name, 'kind': kind,
                              'is_operator': False,
                              'affiliated_with': [n for n, in self._rows('''
                                  SELECT o.name FROM spine.affiliations a
                                  JOIN spine.organizations o ON o.id = a.organization_id
                                  WHERE a.person_id = %(p)s AND a.ended_on IS NULL AND NOT EXISTS (
                                      SELECT 1 FROM spine.affiliations r
                                      WHERE r.replaces_affiliation_id = a.id)
                                  ORDER BY a.started_on, a.id''', {'p': person_id})]})
            party['evidence'] = []   # the ledger has no place for a role citation yet
            out.append(party)
        return out

    def _brief_roles(self, work_id):
        """One entry per role held on this work, with the
        party's identifiers, its standing roles, its evidence and its review."""
        out = []
        for row in self.work_roles(work_id):
            party = row['party']
            identifiers = [{'kind': k, 'value': v} for k, v in self._rows('''
                SELECT kind, value FROM spine.party_identifiers WHERE party_id = %(p)s
                ORDER BY recorded_at, id''', {'p': party['id']})]
            standing = [f"{role} at {name}" for role, name in self._rows(f'''
                SELECT r.role, p.name FROM spine.roles r JOIN spine.parties p ON p.id = r.on_party_id
                WHERE r.party_id = %(p)s AND r.confidence <> 'former' AND r.ended_on IS NULL
                  AND {self._LATEST_ROLES}
                ORDER BY r.recorded_at, r.id''', {'p': party['id']})]
            evidence = row.get('evidence')
            out.append({'role_id': row['id'], 'role': row['role'], 'confidence': row['confidence'],
                        'actor': row['actor'], 'recorded_at': row['recorded_at'],
                        'party_id': party['id'], 'name': party['name'], 'kind': party['kind'],
                        'is_operator': bool(party['is_operator']),
                        'identifiers': identifiers, 'standing': standing,
                        'affiliated_with': [s.split(' at ', 1)[1] for s in standing],
                        'evidence': [{'evidence_id': evidence['id'],
                                      'source_locator': evidence['source_locator'],
                                      'source_at': evidence['source_at']}] if evidence else [],
                        'memo_ids': row.get('memo_ids') or []})
        return out

    def _brief_evidence(self, params):
        rows = self._rows('''
            SELECT e.id, e.source_locator, e.source_at, e.recorded_at,
                   jsonb_array_length(e.attachments), count(*) OVER ()
            FROM spine.evidence_work_links l JOIN spine.evidence e ON e.id = l.evidence_id
            WHERE ''' + _OWNED.format(a='l') + '''
            ORDER BY e.source_at DESC NULLS LAST, e.recorded_at DESC LIMIT %(limit)s''',
                          {**params, 'limit': EVIDENCE_LIMIT})
        return {'count': rows[0][5] if rows else 0,
                'rows': [{'id': str(i), 'source_locator': loc, 'source_at': _iso(sat),
                          'recorded_at': _iso(rat), 'attachments': n}
                         for i, loc, sat, rat, n, _ in rows]}

    def _brief_memos(self, params):
        rows = self._rows('''
            SELECT m.id, m.summary, m.decision, m.waiting_for, m.next_review_at, m.changed,
                   m.actor, m.recorded_at, count(*) OVER ()
            FROM spine.visit_memos m WHERE ''' + _OWNED.format(a='m') + '''
            ORDER BY m.recorded_at DESC, m.id DESC LIMIT 1''', params)
        if not rows:
            return {'count': 0, 'latest': None}
        i, summary, decision, waiting, next_at, changed, actor, at, count = rows[0]
        return {'count': count, 'latest': {
            'id': str(i), 'summary': summary, 'decision': decision, 'waiting_for': waiting,
            'next_review_at': _iso(next_at), 'changed': changed, 'actor': actor,
            'recorded_at': _iso(at)}}

    def _brief_documents(self, job_id):
        return [{'title': d['title'], 'description': d.get('description'),
                 'version': (d.get('current_submission') or {}).get('version'),
                 'status': (d.get('current_submission') or {}).get('status', 'nothing submitted')}
                for d in self.documents(job_id)]

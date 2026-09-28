"""Immutable SOP versions and explicit adoption membership for one work owner."""

import psycopg
from psycopg import sql
from psycopg.types.json import Jsonb

from review import owner_columns


JUDGMENT_STATE_NOTE = (
    'Judgments are current at read time; this preserves adoption membership, '
    'not a historical judgment snapshot.'
)

# The reason the database writes on the adoption of a booking or job that
# follows its quote. Rows stored before migration 015 carry an older word for
# a chain, and stored rows never change, so reads show that one sentence in
# today's wording. Any other reason is returned as recorded.
FOLLOW_REASON_BEFORE_015 = 'Follows the SOP the load adopted at its quote.'
FOLLOW_REASON = 'Follows the SOP the chain adopted at its quote.'


def reason_as_read(reason):
    return FOLLOW_REASON if reason == FOLLOW_REASON_BEFORE_015 else reason


class SopVersionConflict(ValueError):
    """A stable SOP version ID was reused with different contents."""


class SopAdoptionConflict(ValueError):
    """An adoption ID changed contents or its expected previous adoption is stale."""


def _milestone_documents(include_evidence):
    if include_evidence:
        judgment = sql.SQL(
            'SELECT milestone_id, position, document FROM spine.judgment_details d'
        )
    else:
        judgment = sql.SQL('''
            SELECT j.milestone_id, j.position, to_jsonb(j) || jsonb_build_object(
                'evidence_ids', (SELECT jsonb_agg(c.evidence_id ORDER BY c.evidence_id)
                    FROM spine.citations c WHERE c.judgment_id = j.id),
                'revises_ids', coalesce((SELECT jsonb_agg(l.related_judgment_id ORDER BY l.related_judgment_id)
                    FROM spine.judgment_links l WHERE l.judgment_id = j.id
                    AND l.relationship = 'revises'), '[]'::jsonb),
                'based_on_ids', coalesce((SELECT jsonb_agg(l.related_judgment_id ORDER BY l.related_judgment_id)
                    FROM spine.judgment_links l WHERE l.judgment_id = j.id
                    AND l.relationship = 'based_on'), '[]'::jsonb)) AS document
            FROM spine.judgments j
        ''')
    return sql.SQL('''
        milestone_docs AS (
            SELECT m.id, to_jsonb(m) || jsonb_build_object(
                'phase_id', a.phase_id,
                'status', coalesce(latest.document->>'status', 'unassessed'),
                'latest_judgment', latest.document) AS document
            FROM spine.milestones m
            LEFT JOIN spine.milestone_phase_assignments a ON a.milestone_id = m.id
            LEFT JOIN LATERAL (
                SELECT document FROM ({judgment}) d
                WHERE d.milestone_id = m.id ORDER BY d.position DESC LIMIT 1
            ) latest ON true
        )
    ''').format(judgment=judgment)


def _citations(include_evidence):
    if include_evidence:
        return sql.SQL("'evidence', coalesce((SELECT jsonb_agg(to_jsonb(e) ORDER BY e.id) "
                       "FROM spine.sop_adoption_citations c JOIN spine.evidence e "
                       "ON e.id=c.evidence_id WHERE c.adoption_id=a.id), '[]'::jsonb)")
    return sql.SQL("'evidence_ids', coalesce((SELECT jsonb_agg(c.evidence_id ORDER BY c.evidence_id) "
                   "FROM spine.sop_adoption_citations c WHERE c.adoption_id=a.id), '[]'::jsonb)")


class SopLedgerMixin:
    def publish_sop_version(self, identifier, name, version, tag, definition, actor,
                            *, based_on_version_id=None):
        if not isinstance(definition, dict):
            raise ValueError('SOP definition must be an object')
        try:
            return self._append('publish_sop_version', (
                identifier, name, version, tag, Jsonb(definition), based_on_version_id, actor,
            ))
        except psycopg.Error as error:
            if error.sqlstate == 'SP006':
                raise SopVersionConflict(error.diag.message_primary) from error
            raise

    def adopt_sop_version(self, identifier, work_kind, work_id, sop_version_id,
                          reason, actor, evidence_ids, phase_bindings,
                          milestone_bindings, *, expected_previous_adoption_id=None):
        if not isinstance(phase_bindings, list) or not isinstance(milestone_bindings, list):
            raise ValueError('SOP phase and milestone bindings must be lists')
        try:
            return self._append('adopt_sop_version', (
                identifier, *owner_columns(work_kind, work_id), sop_version_id,
                expected_previous_adoption_id, reason, actor, evidence_ids,
                Jsonb(phase_bindings), Jsonb(milestone_bindings),
            ))
        except psycopg.Error as error:
            if error.sqlstate == 'SP007':
                raise SopAdoptionConflict(error.diag.message_primary) from error
            raise

    def set_sop_version_status(self, identifier, sop_version_id, status, reason, actor,
                               evidence_ids):
        """Append a cited status row: a version is active or retired. Never an edit."""
        if status not in {'active', 'retired'}:
            raise ValueError('SOP version status must be active or retired')
        try:
            return self._append('set_sop_version_status', (
                identifier, sop_version_id, status, reason, actor, list(evidence_ids),
            ))
        except psycopg.Error as error:
            if error.sqlstate == 'SP006':
                raise SopVersionConflict(error.diag.message_primary) from error
            raise

    def _chain_sop_installed(self):
        return self.connection.execute(
            "SELECT to_regclass('spine.sop_version_status') IS NOT NULL").fetchone()[0]

    def sop_version(self, identifier):
        row = self.connection.execute(
            'SELECT to_jsonb(v) FROM spine.sop_versions v WHERE id=%s', (identifier,)
        ).fetchone()
        return row[0] if row else None

    def sop_versions(self, tag=None, status=None):
        """List every published SOP version, newest first, without its definition.

        The optional tag keeps only standard or only break_glass versions; the
        optional status keeps only active or only retired ones. Nothing is derived: there is no default version.
        """
        if tag is not None and tag not in {'standard', 'break_glass'}:
            raise ValueError('SOP version tag must be standard or break_glass')
        if status is not None and status not in {'active', 'retired'}:
            raise ValueError('SOP version status must be active or retired')
        state = ("spine.sop_version_state(v.id)" if self._chain_sop_installed() else "'active'")
        rows = self.connection.execute(f"""
            SELECT jsonb_build_object(
                'id', v.id, 'name', v.name, 'version', v.version, 'tag', v.tag,
                'status', {state},
                'based_on_version_id', v.based_on_version_id,
                'actor', v.actor, 'recorded_at', v.recorded_at)
            FROM spine.sop_versions v
            WHERE (%(tag)s::text IS NULL OR v.tag = %(tag)s)
              AND (%(status)s::text IS NULL OR {state} = %(status)s)
            ORDER BY v.recorded_at DESC, v.id DESC
        """, {'tag': tag, 'status': status}).fetchall()
        return [row[0] for row in rows]

    def sop_adoption(self, identifier, *, include_evidence=False):
        query = sql.SQL('''
            WITH {milestone_documents}
            SELECT to_jsonb(a) || jsonb_build_object(
                'work_kind', CASE WHEN a.quote_id IS NOT NULL THEN 'quote'
                                  WHEN a.booking_id IS NOT NULL THEN 'booking' ELSE 'job' END,
                'status', CASE WHEN replacement.id IS NULL THEN 'current' ELSE 'diverted' END,
                'replacement_adoption_id', replacement.id,
                {citations},
                'sop_version', to_jsonb(v),
                'phases', coalesce((SELECT jsonb_agg(jsonb_build_object(
                    'phase_key', ap.phase_key,
                    'phase_id', ap.phase_id,
                    'name', ap.phase_name,
                    'definition_order', ap.definition_order,
                    'physical_display_order', p.display_order,
                    'milestones', coalesce((SELECT jsonb_agg(jsonb_build_object(
                        'milestone_key', am.milestone_key,
                        'milestone_id', am.milestone_id,
                        'title', am.milestone_title,
                        'criterion', am.completion_criterion,
                        'definition_order', am.definition_order,
                        'milestone', md.document
                    ) ORDER BY am.definition_order, am.milestone_key)
                    FROM spine.sop_adoption_milestones am
                    JOIN milestone_docs md ON md.id=am.milestone_id
                    WHERE am.adoption_id=a.id AND am.phase_key=ap.phase_key), '[]'::jsonb)
                ) ORDER BY ap.definition_order, ap.phase_key)
                FROM spine.sop_adoption_phases ap JOIN spine.phases p ON p.id=ap.phase_id
                WHERE ap.adoption_id=a.id), '[]'::jsonb),
                'judgment_state_note', %(state_note)s::text
            )
            FROM spine.sop_adoptions a
            JOIN spine.sop_versions v ON v.id=a.sop_version_id
            LEFT JOIN spine.sop_adoptions replacement ON replacement.previous_adoption_id=a.id
            WHERE a.id=%(id)s
        ''').format(milestone_documents=_milestone_documents(include_evidence),
                    citations=_citations(include_evidence))
        row = self.connection.execute(query, {
            'id': identifier, 'state_note': JUDGMENT_STATE_NOTE,
        }).fetchone()
        if not row:
            return None
        return {**row[0], 'reason': reason_as_read(row[0]['reason'])}

    def work_sop(self, identifier, *, include_evidence=False):
        with self.connection.transaction():
            self.connection.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY')
            row = self.connection.execute('''
                WITH target AS (
                    SELECT 'quote' kind, q.id FROM spine.quotes q WHERE q.id=%s
                    UNION ALL SELECT 'booking', b.id FROM spine.bookings b WHERE b.id=%s
                    UNION ALL SELECT 'job', j.id FROM spine.jobs j WHERE j.id=%s
                )
                SELECT t.kind, a.id FROM target t
                LEFT JOIN LATERAL (
                    SELECT candidate.id FROM spine.sop_adoptions candidate
                    WHERE coalesce(candidate.quote_id, candidate.booking_id, candidate.job_id)=t.id
                      AND NOT EXISTS (SELECT 1 FROM spine.sop_adoptions replacement
                                      WHERE replacement.previous_adoption_id=candidate.id)
                    LIMIT 1
                ) a ON true
            ''', (identifier, identifier, identifier)).fetchone()
            if not row:
                return None
            work_kind, current_id = row
            current = self.sop_adoption(current_id, include_evidence=include_evidence) if current_id else None
            milestone_query = sql.SQL('''
                WITH {milestone_documents}
                SELECT md.document,
                       EXISTS (SELECT 1 FROM spine.sop_adoption_milestones am
                               WHERE am.milestone_id=m.id) AS was_adopted
                FROM spine.milestones m JOIN milestone_docs md ON md.id=m.id
                WHERE coalesce(m.quote_id, m.booking_id, m.job_id)=%(id)s
                  AND (%(current)s::uuid IS NULL OR NOT EXISTS (
                      SELECT 1 FROM spine.sop_adoption_milestones current_member
                      WHERE current_member.adoption_id=%(current)s
                        AND current_member.milestone_id=m.id))
                ORDER BY m.recorded_at, m.id
            ''').format(milestone_documents=_milestone_documents(include_evidence))
            rows = self.connection.execute(milestone_query, {
                'id': identifier, 'current': current_id,
            }).fetchall()
        return {
            'work_kind': work_kind,
            'work_id': str(identifier),
            'current_adoption': current,
            'historical_removed_milestones': [item for item, was_adopted in rows if was_adopted],
            'unadopted_milestones': [item for item, was_adopted in rows if not was_adopted],
            'reader_contract': (
                'current_adoption.phases is the current SOP checkpoint set; historical_removed_milestones '
                'and unadopted_milestones are not members of that adoption.'
            ),
        }

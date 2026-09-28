"""Bounded file, document, work-relationship and party operations."""

import hashlib
import json
import os
import re
import tempfile
from pathlib import Path

import psycopg


MAX_MCP_FILE_BYTES = 8 * 1024 * 1024
FILE_NAME = re.compile(r'[0-9a-f]{64}')


class RoleConflict(ValueError):
    """A stable role ID was reused with different contents, or in a different review."""


class OperatorConflict(ValueError):
    """A second organization was named as the operator."""


class RoleChainConflict(ValueError):
    """The role being ended is missing, already ended or already replaced."""


# SP008 belongs to evidence work links. The party codes
# follow it: SP009 role ID reuse, SP010 second operator, SP011 chain.
PARTY_ERRORS = {
    'SP009': RoleConflict,
    'SP010': OperatorConflict,
    'SP011': RoleChainConflict,
}


class CommercialLedgerMixin:
    def _file_info(self, digest, *, return_bytes=False):
        if not isinstance(digest, str) or not FILE_NAME.fullmatch(digest):
            raise ValueError('file sha256 must be 64 lowercase hexadecimal characters')
        calculated = hashlib.sha256()
        chunks, size = [], 0
        try:
            with (self.files / digest).open('rb') as source:
                while chunk := source.read(1024 * 1024):
                    calculated.update(chunk)
                    size += len(chunk)
                    if return_bytes:
                        if size > MAX_MCP_FILE_BYTES:
                            raise ValueError('file is too large for the bounded MCP operation')
                        chunks.append(chunk)
        except OSError as error:
            raise ValueError(f'file unavailable: {digest}') from error
        if calculated.hexdigest() != digest:
            raise ValueError(f'file hash mismatch: {digest}')
        result = {'sha256': digest, 'byte_size': size}
        if return_bytes:
            result['bytes'] = b''.join(chunks)
        return result

    def plan_file(self, contents):
        """Hash and measure bounded bytes in memory, before anything is written."""
        if not isinstance(contents, bytes):
            raise ValueError('file contents must be bytes')
        if len(contents) > MAX_MCP_FILE_BYTES:
            raise ValueError('file is too large for the bounded MCP operation')
        return {'sha256': hashlib.sha256(contents).hexdigest(), 'byte_size': len(contents)}

    def plan_dropped_file(self, digest):
        """Read and verify bounded bytes left in the drop directory under this name.

        Nothing is written and no row is recorded. A name that is not in the
        drop directory, or whose bytes hash to something else, is refused here,
        before the evidence row exists.
        """
        if self.drop is None:
            raise ValueError('the server has no drop directory; set LEDGER_DROP')
        if not isinstance(digest, str) or not FILE_NAME.fullmatch(digest):
            raise ValueError('file sha256 must be 64 lowercase hexadecimal characters')
        source = self.drop / digest
        if not source.is_file():
            raise ValueError(f'file not in the drop directory: {digest}')
        if source.stat().st_size > MAX_MCP_FILE_BYTES:
            raise ValueError('file is too large for the bounded MCP operation')
        contents = source.read_bytes()
        planned = self.plan_file(contents)
        if planned['sha256'] != digest:
            raise ValueError(f'dropped file hash mismatch: {digest}')
        return {**planned, 'bytes': contents}

    def put_file(self, contents):
        digest = self.plan_file(contents)['sha256']
        self.files.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(prefix='.spine-put-', dir=self.files)
        temporary = Path(temporary_name)
        try:
            with os.fdopen(descriptor, 'wb') as output:
                output.write(contents)
                output.flush()
                os.fsync(output.fileno())
            try:
                os.link(temporary, self.files / digest)
            except FileExistsError:
                existing = self._file_info(digest)
                if existing['byte_size'] != len(contents):
                    raise ValueError(f'existing file conflicts with digest: {digest}')
            return {'sha256': digest, 'byte_size': len(contents)}
        finally:
            temporary.unlink(missing_ok=True)

    def evidence_names_file(self, digest):
        """True when some evidence row's attachments already name this hash."""
        if not isinstance(digest, str) or not FILE_NAME.fullmatch(digest):
            raise ValueError('file sha256 must be 64 lowercase hexadecimal characters')
        row = self.connection.execute(
            'SELECT EXISTS (SELECT 1 FROM spine.evidence e WHERE e.attachments @> %s::jsonb)',
            (json.dumps([{'sha256': digest}]),),
        ).fetchone()
        return bool(row[0])

    def read_file_if_stored(self, digest):
        """Return bytes, or None when a recorded hash has no bytes on disk yet."""
        if not isinstance(digest, str) or not FILE_NAME.fullmatch(digest):
            raise ValueError('file sha256 must be 64 lowercase hexadecimal characters')
        if not (self.files / digest).is_file() and self.evidence_names_file(digest):
            return None
        return self._file_info(digest, return_bytes=True)

    def create_quote(self, identifier, title, actor):
        return self._create('create_quote', (identifier, title, actor))

    def create_booking(self, identifier, quote_id, title, actor):
        return self._create('create_booking', (identifier, quote_id, title, actor))

    def link_job_booking(self, job_id, booking_id, actor):
        return self._create('link_job_booking', (job_id, booking_id, actor))

    def _create_party(self, function, arguments):
        try:
            return self._create(function, arguments)
        except psycopg.Error as error:
            failure = PARTY_ERRORS.get(error.sqlstate)
            if failure is not None:
                raise failure(error.diag.message_primary) from error
            raise

    # ----- the party cluster: parties, identifiers, roles -----

    def _parties_installed(self):
        """True when the spine.parties table exists. A database without it is
        read through the person and organization tables instead."""
        if not getattr(self, '_parties_ready', False):
            self._parties_ready = self.connection.execute(
                "SELECT to_regclass('spine.parties') IS NOT NULL").fetchone()[0]
        return self._parties_ready

    def create_party(self, identifier, kind, name, actor, is_operator=False):
        if kind not in {'person', 'agent', 'organization'}:
            raise ValueError('party kind must be person, agent or organization')
        return self._create_party('create_party', (identifier, kind, name, actor, is_operator))

    def record_party_identifier(self, identifier, party_id, kind, value, evidence_id, actor):
        if kind not in {'email', 'phone', 'address', 'alias'}:
            raise ValueError('identifier kind must be email, phone, address or alias')
        return self._create_party('record_party_identifier', (
            identifier, party_id, kind, value, evidence_id, actor))

    def record_role(self, identifier, party_id, role, actor, *, on_party_id=None,
                    work_kind=None, work_id=None, confidence='confirmed', evidence_id=None,
                    started_on=None, ended_on=None, memo_id=None):
        """One claim: party_id holds role on another party or on one work item."""
        if (on_party_id is None) == (work_id is None):
            raise ValueError('a role is on exactly one of a party or a work item')
        if work_id is not None and work_kind not in {'quote', 'booking', 'job'}:
            raise ValueError('work kind must be quote, booking or job')
        if confidence not in {'confirmed', 'mentioned', 'former'}:
            raise ValueError('confidence must be confirmed, mentioned or former')
        # One rule for every path that records a role: record_role and the
        # roles of record_review both come through here.
        if confidence == 'former' and ended_on is None:
            raise ValueError('a former role needs ended_on: the day the role ended')
        work = {kind: work_id if kind == work_kind else None for kind in ('quote', 'booking', 'job')}
        return self._create_party('record_role', (
            identifier, party_id, on_party_id, work['quote'], work['booking'], work['job'],
            role, confidence, evidence_id, started_on, ended_on, actor, memo_id))

    def end_role(self, identifier, role_id, ended_on, actor, *, evidence_id=None, memo_id=None):
        return self._create_party('end_role', (
            identifier, role_id, ended_on, actor, evidence_id, memo_id))

    _ROLE_DOCUMENT = '''to_jsonb(r) || jsonb_build_object(
        'party', (SELECT jsonb_build_object('id', p.id, 'kind', p.kind, 'name', p.name,
                                            'is_operator', p.is_operator)
                  FROM spine.parties p WHERE p.id = r.party_id),
        'on', CASE
            WHEN r.on_party_id IS NOT NULL THEN (SELECT jsonb_build_object(
                'kind', 'party', 'id', p.id, 'name', p.name, 'party_kind', p.kind)
                FROM spine.parties p WHERE p.id = r.on_party_id)
            WHEN r.quote_id IS NOT NULL THEN (SELECT jsonb_build_object('kind', 'quote', 'id', q.id, 'title', q.title)
                FROM spine.quotes q WHERE q.id = r.quote_id)
            WHEN r.booking_id IS NOT NULL THEN (SELECT jsonb_build_object('kind', 'booking', 'id', b.id, 'title', b.title)
                FROM spine.bookings b WHERE b.id = r.booking_id)
            ELSE (SELECT jsonb_build_object('kind', 'job', 'id', j.id, 'title', j.title)
                FROM spine.jobs j WHERE j.id = r.job_id) END,
        'evidence', (SELECT jsonb_build_object('id', e.id, 'source_locator', e.source_locator,
                                               'source_at', e.source_at)
                     FROM spine.evidence e WHERE e.id = r.evidence_id),
        'memo_ids', coalesce((SELECT jsonb_agg(l.memo_id ORDER BY l.memo_id)
                              FROM spine.visit_memo_roles l WHERE l.role_id = r.id), '[]'::jsonb))'''

    # A chain's latest row is the one no later row replaces.
    _LATEST_ROLES = 'NOT EXISTS (SELECT 1 FROM spine.roles n WHERE n.replaces_role_id = r.id)'

    def _party_after_013(self, identifier):
        row = self.connection.execute(f'''
            SELECT to_jsonb(p) || jsonb_build_object(
                'identifiers', coalesce((SELECT jsonb_agg(to_jsonb(i) ORDER BY i.recorded_at, i.id)
                    FROM spine.party_identifiers i WHERE i.party_id = p.id), '[]'::jsonb),
                'roles', coalesce((SELECT jsonb_agg({self._ROLE_DOCUMENT} ORDER BY r.recorded_at, r.id)
                    FROM spine.roles r WHERE r.party_id = p.id AND {self._LATEST_ROLES}), '[]'::jsonb),
                'held_by', coalesce((SELECT jsonb_agg({self._ROLE_DOCUMENT} ORDER BY r.recorded_at, r.id)
                    FROM spine.roles r WHERE r.on_party_id = p.id AND {self._LATEST_ROLES}), '[]'::jsonb))
            FROM spine.parties p WHERE p.id = %s''', (identifier,)).fetchone()
        return row[0] if row else None

    def memo_roles(self, memo_id):
        """The role ids a review claimed, or None when the memo is not recorded."""
        if not self._parties_installed():
            return None
        if self.connection.execute('SELECT 1 FROM spine.visit_memos WHERE id = %s',
                                   (memo_id,)).fetchone() is None:
            return None
        return sorted(row[0] for row in self.connection.execute(
            'SELECT role_id FROM spine.visit_memo_roles WHERE memo_id = %s', (memo_id,)).fetchall())

    def work_roles(self, work_id):
        """Latest row of every role chain on one quote, booking or job."""
        return [row[0] for row in self.connection.execute(f'''
            SELECT {self._ROLE_DOCUMENT} FROM spine.roles r
            WHERE coalesce(r.quote_id, r.booking_id, r.job_id) = %s AND {self._LATEST_ROLES}
            ORDER BY r.recorded_at, r.id''', (work_id,)).fetchall()]

    def work(self, identifier):
        if self._parties_installed():
            return self._work_after_013(identifier)
        row = self.connection.execute('''
            WITH target AS (
                SELECT 'quote' kind, q.id, q.id quote_id, NULL::uuid booking_id FROM spine.quotes q WHERE q.id=%s
                UNION ALL SELECT 'booking', b.id, b.quote_id, b.id FROM spine.bookings b WHERE b.id=%s
                UNION ALL SELECT 'job', j.id, b.quote_id, l.booking_id FROM spine.jobs j
                    LEFT JOIN spine.job_booking_links l ON l.job_id=j.id
                    LEFT JOIN spine.bookings b ON b.id=l.booking_id WHERE j.id=%s
            )
            SELECT jsonb_build_object(
                'kind', t.kind,
                'quote', (SELECT to_jsonb(q) FROM spine.quotes q WHERE q.id=t.quote_id),
                'bookings', coalesce((SELECT jsonb_agg(to_jsonb(b) || jsonb_build_object(
                    'job_ids', coalesce((SELECT jsonb_agg(l.job_id ORDER BY l.recorded_at, l.job_id)
                        FROM spine.job_booking_links l WHERE l.booking_id=b.id), '[]'::jsonb))
                    ORDER BY b.recorded_at, b.id) FROM spine.bookings b WHERE b.quote_id=t.quote_id), '[]'::jsonb),
                'selected_booking_id', t.booking_id,
                'job', CASE WHEN t.kind='job' THEN (SELECT to_jsonb(j) FROM spine.jobs j WHERE j.id=t.id) END,
                'participations', coalesce((SELECT jsonb_agg(to_jsonb(p) || jsonb_build_object(
                    'organization', (SELECT to_jsonb(o) FROM spine.organizations o WHERE o.id=p.organization_id),
                    'person', (SELECT to_jsonb(x) FROM spine.people x WHERE x.id=p.person_id))
                    ORDER BY p.recorded_at, p.id)
                    FROM spine.participations p WHERE
                    (t.kind='quote' AND p.quote_id=t.id) OR
                    (t.kind='booking' AND p.booking_id=t.id) OR
                    (t.kind='job' AND p.job_id=t.id)), '[]'::jsonb)
            ) FROM target t
        ''', (identifier, identifier, identifier)).fetchone()
        return row[0] if row else None

    def _work_after_013(self, identifier):
        row = self.connection.execute('''
            WITH target AS (
                SELECT 'quote' kind, q.id, q.id quote_id, NULL::uuid booking_id FROM spine.quotes q WHERE q.id=%s
                UNION ALL SELECT 'booking', b.id, b.quote_id, b.id FROM spine.bookings b WHERE b.id=%s
                UNION ALL SELECT 'job', j.id, b.quote_id, l.booking_id FROM spine.jobs j
                    LEFT JOIN spine.job_booking_links l ON l.job_id=j.id
                    LEFT JOIN spine.bookings b ON b.id=l.booking_id WHERE j.id=%s
            )
            SELECT jsonb_build_object(
                'kind', t.kind,
                'quote', (SELECT to_jsonb(q) FROM spine.quotes q WHERE q.id=t.quote_id),
                'bookings', coalesce((SELECT jsonb_agg(to_jsonb(b) || jsonb_build_object(
                    'job_ids', coalesce((SELECT jsonb_agg(l.job_id ORDER BY l.recorded_at, l.job_id)
                        FROM spine.job_booking_links l WHERE l.booking_id=b.id), '[]'::jsonb))
                    ORDER BY b.recorded_at, b.id) FROM spine.bookings b WHERE b.quote_id=t.quote_id), '[]'::jsonb),
                'selected_booking_id', t.booking_id,
                'job', CASE WHEN t.kind='job' THEN (SELECT to_jsonb(j) FROM spine.jobs j WHERE j.id=t.id) END
            ) FROM target t
        ''', (identifier, identifier, identifier)).fetchone()
        if row is None:
            return None
        document = row[0]
        document['roles'] = self.work_roles(identifier)
        return document

    def party(self, identifier):
        """Read one party with its identifiers, the latest row of each role
        chain it holds and each held on it. A database without spine.parties
        gives one person or organization with its affiliation chains."""
        if self._parties_installed():
            return self._party_after_013(identifier)
        row = self.connection.execute("""
            WITH latest AS (
                SELECT a.* FROM spine.affiliations a
                WHERE NOT EXISTS (SELECT 1 FROM spine.affiliations r
                                  WHERE r.replaces_affiliation_id = a.id)
            )
            SELECT jsonb_build_object('kind', 'person', 'person', to_jsonb(p),
                'affiliations', coalesce((SELECT jsonb_agg(to_jsonb(l) || jsonb_build_object(
                    'organization', (SELECT to_jsonb(o) FROM spine.organizations o
                                     WHERE o.id = l.organization_id))
                    ORDER BY l.started_on, l.id)
                    FROM latest l WHERE l.person_id = p.id), '[]'::jsonb))
            FROM spine.people p WHERE p.id = %s
            UNION ALL
            SELECT jsonb_build_object('kind', 'organization', 'organization', to_jsonb(g),
                'affiliations', coalesce((SELECT jsonb_agg(to_jsonb(l) || jsonb_build_object(
                    'person', (SELECT to_jsonb(x) FROM spine.people x WHERE x.id = l.person_id))
                    ORDER BY l.started_on, l.id)
                    FROM latest l WHERE l.organization_id = g.id), '[]'::jsonb))
            FROM spine.organizations g WHERE g.id = %s
        """, (identifier, identifier)).fetchone()
        return row[0] if row else None

    def create_document_requirement(self, identifier, job_id, title, actor,
                                    *, milestone_id=None, description=None):
        return self._create('create_document_requirement', (
            identifier, job_id, milestone_id, title, description, actor,
        ))

    def submit_document(self, identifier, requirement_id, digest, media_type, actor,
                        *, replaces_submission_id=None):
        info = self._file_info(digest)
        return self._create('submit_document', (
            identifier, requirement_id, replaces_submission_id, digest,
            media_type, info['byte_size'], actor,
        ))

    def append_document_assessment(self, identifier, submission_id, outcome, reason,
                                   actor, evidence_ids):
        return self._create('append_document_assessment', (
            identifier, submission_id, outcome, reason, actor, evidence_ids,
        ))

    def documents(self, job_id):
        rows = self.connection.execute('''
            WITH submission_docs AS (
                SELECT s.id, s.requirement_id, s.version,
                    to_jsonb(s) || jsonb_build_object(
                        'status', coalesce(a.document->>'outcome', 'unassessed'),
                        'latest_assessment', a.document) document
                FROM spine.document_submissions s
                LEFT JOIN LATERAL (
                    SELECT to_jsonb(x) || jsonb_build_object('evidence_ids',
                        (SELECT jsonb_agg(c.evidence_id ORDER BY c.evidence_id)
                         FROM spine.document_assessment_citations c WHERE c.assessment_id=x.id)) document
                    FROM spine.document_assessments x WHERE x.submission_id=s.id
                    ORDER BY x.position DESC LIMIT 1
                ) a ON true
            )
            SELECT to_jsonb(r) || jsonb_build_object(
                'submissions', coalesce((SELECT jsonb_agg(s.document ORDER BY s.version)
                    FROM submission_docs s WHERE s.requirement_id=r.id), '[]'::jsonb),
                'current_submission', (SELECT s.document FROM submission_docs s
                    WHERE s.requirement_id=r.id ORDER BY s.version DESC LIMIT 1))
            FROM spine.document_requirements r WHERE r.job_id=%s
            ORDER BY r.recorded_at, r.id
        ''', (job_id,)).fetchall()
        return [row[0] for row in rows]

    def document_assessment_history(self, submission_id, limit=50, before_position=None):
        if type(limit) is not int or not 1 <= limit <= 200:
            raise ValueError('assessment history limit must be between 1 and 200')
        rows = self.connection.execute('''
            SELECT to_jsonb(a) || jsonb_build_object('evidence_ids',
                (SELECT jsonb_agg(c.evidence_id ORDER BY c.evidence_id)
                 FROM spine.document_assessment_citations c WHERE c.assessment_id=a.id))
            FROM spine.document_assessments a
            WHERE a.submission_id=%s AND (%s::bigint IS NULL OR a.position < %s)
            ORDER BY a.position DESC LIMIT %s
        ''', (submission_id, before_position, before_position, limit)).fetchall()
        return [row[0] for row in rows]

"""Internal database access for the future MCP write path; no server or CLI."""

import hashlib
import re
from pathlib import Path

import psycopg
from references import ReferenceLedgerMixin
from psycopg import sql
from psycopg.types.json import Jsonb

from case_brief import CaseBriefMixin
from commercial import CommercialLedgerMixin
from evidence_lookup import EvidenceLookupMixin
from money import MoneyLedgerMixin
from party_lookup import PartyLookupMixin
from review import ReviewLedgerMixin, owner_columns
from work_list import WorkListMixin
from sop import SopLedgerMixin


def _judgment_rows(include_evidence):
    if include_evidence:
        return sql.SQL('SELECT id, milestone_id, position, document FROM spine.judgment_details')
    # Compact reads never select from evidence, so source bodies stay in Postgres.
    return sql.SQL('''
        SELECT j.id, j.milestone_id, j.position,
               to_jsonb(j) || jsonb_build_object('evidence_ids', (
                   SELECT jsonb_agg(c.evidence_id ORDER BY c.evidence_id)
                   FROM spine.citations c WHERE c.judgment_id = j.id
               ), 'revises_ids', coalesce((
                   SELECT jsonb_agg(l.related_judgment_id ORDER BY l.related_judgment_id)
                   FROM spine.judgment_links l
                   WHERE l.judgment_id = j.id AND l.relationship = 'revises'
               ), '[]'::jsonb), 'based_on_ids', coalesce((
                   SELECT jsonb_agg(l.related_judgment_id ORDER BY l.related_judgment_id)
                   FROM spine.judgment_links l
                   WHERE l.judgment_id = j.id AND l.relationship = 'based_on'
               ), '[]'::jsonb)) AS document
        FROM spine.judgments j
    ''')


class JudgmentConflict(ValueError):
    """A stable judgment ID was reused with different contents."""


class AssignmentConflict(ValueError):
    """A milestone was assigned to a different phase or actor."""


class CreationConflict(ValueError):
    """A stable creation ID was reused with different contents."""


class EvidenceConflict(ValueError):
    """A stable evidence ID was reused with different contents."""


class EvidenceLinkConflict(ValueError):
    """A stable evidence work link ID was reused with different contents."""


class Ledger(ReferenceLedgerMixin, EvidenceLookupMixin, SopLedgerMixin, ReviewLedgerMixin,
             CommercialLedgerMixin, WorkListMixin, CaseBriefMixin, MoneyLedgerMixin,
             PartyLookupMixin):
    def __init__(self, dsn, files, drop=None, **connection_options):
        self.connection = psycopg.connect(dsn, autocommit=True, **connection_options)
        self.files = Path(files)
        # The drop directory is where another program leaves bytes named by hash.
        # It stays None for callers that never record a file by hash.
        self.drop = Path(drop) if drop else None
        self._evidence_links = False

    def close(self):
        self.connection.close()

    def _append(self, function, arguments):
        query = sql.SQL('SELECT spine.{}({})').format(
            sql.Identifier(function),
            sql.SQL(',').join(sql.Placeholder() for _ in arguments),
        )
        # Retry only transaction conflicts. Stable judgment IDs preserve intent.
        for attempt in range(3):
            try:
                with self.connection.transaction():
                    return self.connection.execute(query, arguments).fetchone()[0]
            except (psycopg.errors.SerializationFailure, psycopg.errors.DeadlockDetected):
                if attempt == 2:
                    raise

    def create_job(self, identifier, title, actor):
        return self._create('create_job', (identifier, title, actor))

    def _create(self, function, arguments):
        try:
            return self._append(function, arguments)
        except psycopg.Error as error:
            if error.sqlstate == 'SP004':
                raise CreationConflict(error.diag.message_primary) from error
            raise

    def assign_milestone_phase(self, milestone_id, phase_id, actor):
        try:
            return self._append('assign_milestone_phase', (milestone_id, phase_id, actor))
        except psycopg.Error as error:
            if error.sqlstate == 'SP003':
                raise AssignmentConflict(error.diag.message_primary) from error
            raise

    def _check_attachment(self, attachment, *, verify_stored_bytes):
        """Check one attachment's shape, and its bytes when they should exist."""
        if not isinstance(attachment, dict) or set(attachment) != {
            'sha256', 'media_type', 'byte_size'
        }:
            raise ValueError('each attachment needs sha256, media_type and byte_size')
        digest = attachment['sha256']
        size = attachment['byte_size']
        media_type = attachment['media_type']
        if not isinstance(digest, str) or not re.fullmatch(r'[0-9a-f]{64}', digest):
            raise ValueError('attachment sha256 must be 64 lowercase hexadecimal characters')
        if type(size) is not int or size < 0:
            raise ValueError('attachment byte_size must be a nonnegative integer')
        if not isinstance(media_type, str) or not media_type.strip():
            raise ValueError('attachment media_type must be nonempty')
        if not verify_stored_bytes:
            return
        actual_hash = hashlib.sha256()
        actual_size = 0
        try:
            with (self.files / digest).open('rb') as source:
                while chunk := source.read(1024 * 1024):
                    actual_hash.update(chunk)
                    actual_size += len(chunk)
        except OSError as error:
            raise ValueError(f'attachment file unavailable: {digest}') from error
        if actual_size != size or actual_hash.hexdigest() != digest:
            raise ValueError(f'attachment size or hash mismatch: {digest}')

    def record_evidence_before_file(self, identifier, digest, media_type, byte_size, actor):
        """Record an attachment row whose bytes are not published yet.

        Only the file put path uses this. It supplies a hash and size already
        computed from the bytes in memory, so there is nothing to re-read from
        disk. Every other caller keeps the disk check in `record_evidence`.
        """
        return self._record_evidence(
            identifier, None,
            [{'sha256': digest, 'media_type': media_type, 'byte_size': byte_size}],
            actor, None, None, verify_stored_bytes=False,
        )

    def record_evidence(self, identifier, original_payload, attachments, actor,
                        source_locator=None, source_at=None):
        """Record a source and attachments whose bytes are already on disk."""
        return self._record_evidence(identifier, original_payload, attachments, actor,
                                     source_locator, source_at, verify_stored_bytes=True)

    def _record_evidence(self, identifier, original_payload, attachments, actor,
                         source_locator, source_at, *, verify_stored_bytes):
        if original_payload is not None and not isinstance(original_payload, str):
            raise ValueError('original payload must be text; preserve binary sources as files')
        if not isinstance(attachments, list):
            raise ValueError('attachments must be a list')
        if not original_payload and not attachments:
            raise ValueError('evidence needs an original payload or a file reference')
        for attachment in attachments:
            self._check_attachment(attachment, verify_stored_bytes=verify_stored_bytes)
        try:
            return self._append('record_evidence', (
                identifier, original_payload, Jsonb(attachments), source_locator, source_at, actor,
            ))
        except psycopg.Error as error:
            if error.sqlstate == 'SP005':
                raise EvidenceConflict(error.diag.message_primary) from error
            raise

    def append_judgment(self, identifier, milestone_id, status, explanation, actor, citations,
                        *, occurred_on=None, occurrence_precision=None, revises=None,
                        based_on=None):
        try:
            return self._append('append_judgment_v2', (
                identifier, milestone_id, status, explanation, actor, citations,
                occurred_on, occurrence_precision, revises or [], based_on or [],
            ))
        except psycopg.Error as error:
            if error.sqlstate == 'SP001':
                raise JudgmentConflict(error.diag.message_primary) from error
            raise

    def link_evidence_work(self, identifier, evidence_id, work_kind, work_id, actor):
        """Record that one evidence row is about one quote, booking or job."""
        try:
            return self._append('link_evidence_work', (
                identifier, evidence_id, *owner_columns(work_kind, work_id), actor,
            ))
        except psycopg.Error as error:
            if error.sqlstate == 'SP008':
                raise EvidenceLinkConflict(error.diag.message_primary) from error
            raise

    def _links_installed(self):
        """True when the spine.evidence_work_links table exists. A database
        without it returns evidence with no about_work list."""
        if not self._evidence_links:
            self._evidence_links = self.connection.execute(
                "SELECT to_regclass('spine.evidence_work_links') IS NOT NULL"
            ).fetchone()[0]
        return self._evidence_links

    def evidence(self, identifier):
        row = self.connection.execute(
            'SELECT to_jsonb(e) FROM spine.evidence e WHERE id = %s', (identifier,)
        ).fetchone()
        if row is None:
            return None
        document = row[0]
        if self._links_installed():
            document['about_work'] = [link[0] for link in self.connection.execute('''
                SELECT jsonb_build_object(
                    'kind', CASE WHEN l.quote_id IS NOT NULL THEN 'quote'
                                 WHEN l.booking_id IS NOT NULL THEN 'booking' ELSE 'job' END,
                    'work_id', coalesce(l.quote_id, l.booking_id, l.job_id),
                    'id', l.id, 'actor', l.actor, 'recorded_at', l.recorded_at)
                FROM spine.evidence_work_links l WHERE l.evidence_id = %s
                ORDER BY l.recorded_at, l.id
            ''', (identifier,)).fetchall()]
        return document

    _PARENT_TABLES = {
        'work': ('quotes', 'bookings', 'jobs'), 'job': ('jobs',),
        'milestone': ('milestones',), 'document version': ('document_submissions',),
    }

    def require_row(self, what, identifier):
        """Refuse a list read whose parent row does not exist, so an empty
        list always means "nothing recorded yet" and never "wrong ID"."""
        for table in self._PARENT_TABLES[what]:
            if self.connection.execute(
                    sql.SQL('SELECT 1 FROM spine.{} WHERE id = %s').format(sql.Identifier(table)),
                    (identifier,)).fetchone():
                return
        raise ValueError(f'{what} not found: {identifier}')

    def history(self, milestone_id, limit=50, before_position=None, *, include_evidence=False):
        if type(limit) is not int or not 1 <= limit <= 200:
            raise ValueError('history limit must be between 1 and 200')
        rows = self.connection.execute(sql.SQL('''
            SELECT document FROM ({judgments}) d
            WHERE milestone_id = %s AND (%s::bigint IS NULL OR position < %s)
            ORDER BY position DESC LIMIT %s
        ''').format(judgments=_judgment_rows(include_evidence)),
            (milestone_id, before_position, before_position, limit)).fetchall()
        return [row[0] for row in rows]

    def review(self, identifier, *, include_evidence=False):
        """The same compact snapshot for a quote, booking or job, with its kind."""
        return self._review_snapshot(identifier, ('quote', 'booking', 'job'),
                                     _judgment_rows(include_evidence))

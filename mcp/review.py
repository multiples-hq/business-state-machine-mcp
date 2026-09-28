"""Review context owned by exactly one quote, booking or job: phases, milestones, memos."""

import psycopg
from psycopg import sql
from psycopg.types.json import Jsonb

WORK_KINDS = ('quote', 'booking', 'job')

# Every owner-scoped row has the same three columns; exactly one is set.
OWNED_BY = sql.SQL('({alias}.quote_id = {id} OR {alias}.booking_id = {id} OR {alias}.job_id = {id})')


def owner_columns(work_kind, work_id):
    """Return the (quote_id, booking_id, job_id) triple for one owner."""
    if work_kind not in WORK_KINDS:
        raise ValueError('work kind must be quote, booking or job')
    return tuple(work_id if kind == work_kind else None for kind in WORK_KINDS)


def _memo_document(alias):
    return sql.SQL('''to_jsonb({alias}) || jsonb_build_object(
        'reviewed_milestone_ids', coalesce((SELECT jsonb_agg(x.milestone_id ORDER BY x.milestone_id)
            FROM spine.visit_memo_milestones x WHERE x.memo_id = {alias}.id), '[]'::jsonb),
        'reviewed_judgment_ids', coalesce((SELECT jsonb_agg(x.judgment_id ORDER BY x.judgment_id)
            FROM spine.visit_memo_judgments x WHERE x.memo_id = {alias}.id), '[]'::jsonb))
    ''').format(alias=sql.Identifier(alias))


class MemoConflict(ValueError):
    """A stable visit memo ID was reused with different contents."""


class ReviewLedgerMixin:
    def create_work_phase(self, identifier, work_kind, work_id, name, display_order, actor):
        return self._create('create_phase_v2', (
            identifier, *owner_columns(work_kind, work_id), name, display_order, actor,
        ))

    def create_work_milestone(self, identifier, work_kind, work_id, title, actor):
        return self._create('create_milestone_v2', (
            identifier, *owner_columns(work_kind, work_id), title, actor,
        ))

    def append_work_memo(self, identifier, work_kind, work_id, review_started_at,
                         review_ended_at, summary, decision, changed, actor, *,
                         waiting_for=None, next_review_at=None, details=None,
                         reviewed_milestones=None, reviewed_judgments=None):
        try:
            return self._append('append_visit_memo_v2', (
                identifier, *owner_columns(work_kind, work_id), review_started_at,
                review_ended_at, summary, decision, waiting_for, next_review_at, changed,
                Jsonb(details or {}), actor, reviewed_milestones or [], reviewed_judgments or [],
            ))
        except psycopg.Error as error:
            if error.sqlstate == 'SP002':
                raise MemoConflict(error.diag.message_primary) from error
            raise

    def _memo_page(self, owned, work_id, limit, before_recorded_at, before_id):
        if type(limit) is not int or not 1 <= limit <= 200:
            raise ValueError('memo limit must be between 1 and 200')
        if (before_recorded_at is None) != (before_id is None):
            raise ValueError('memo cursor needs both recorded_at and id')
        rows = self.connection.execute(sql.SQL('''
            SELECT {document} FROM spine.visit_memos m
            WHERE {owned} AND (%(before_at)s::timestamptz IS NULL OR
                (m.recorded_at, m.id) < (%(before_at)s, %(before_id)s))
            ORDER BY m.recorded_at DESC, m.id DESC LIMIT %(limit)s
        ''').format(document=_memo_document('m'), owned=owned), {
            'id': work_id, 'before_at': before_recorded_at, 'before_id': before_id,
            'limit': limit,
        }).fetchall()
        return [row[0] for row in rows]

    def work_memos(self, work_id, limit=50, before_recorded_at=None, before_id=None):
        """Newest-first memos of one quote, booking or job."""
        owned = OWNED_BY.format(alias=sql.Identifier('m'), id=sql.Placeholder('id'))
        return self._memo_page(owned, work_id, limit, before_recorded_at, before_id)

    def _review_snapshot(self, identifier, kinds, judgments):
        # One statement gives the work, its phases, milestones, judgments and memo the same snapshot.
        def owned(alias):
            return OWNED_BY.format(alias=sql.Identifier(alias), id=sql.Placeholder('id'))

        row = self.connection.execute(sql.SQL('''
            WITH target AS (
                SELECT 'quote' AS kind, q.id, to_jsonb(q) AS document FROM spine.quotes q WHERE q.id = %(id)s
                UNION ALL SELECT 'booking', b.id, to_jsonb(b) FROM spine.bookings b WHERE b.id = %(id)s
                UNION ALL SELECT 'job', j.id, to_jsonb(j) FROM spine.jobs j WHERE j.id = %(id)s
            ), milestone_docs AS (
                SELECT m.id, m.recorded_at, a.phase_id,
                       to_jsonb(m) || jsonb_build_object(
                    'status', coalesce(latest.document ->> 'status', 'unassessed'),
                    'latest_judgment', latest.document
                       ) AS document
                FROM spine.milestones m
                LEFT JOIN spine.milestone_phase_assignments a ON a.milestone_id = m.id
                LEFT JOIN LATERAL (
                    SELECT document FROM ({judgments}) d
                    WHERE d.milestone_id = m.id ORDER BY d.position DESC LIMIT 1
                ) latest ON true
                WHERE {milestone_owned}
            )
            SELECT t.document || jsonb_build_object(
                'kind', t.kind,
                'milestones', coalesce((SELECT jsonb_agg(document ORDER BY recorded_at, id)
                    FROM milestone_docs), '[]'::jsonb),
                'phases', coalesce((SELECT jsonb_agg(to_jsonb(p) || jsonb_build_object(
                    'milestones', coalesce((SELECT jsonb_agg(md.document ORDER BY md.recorded_at, md.id)
                        FROM milestone_docs md WHERE md.phase_id = p.id), '[]'::jsonb))
                    ORDER BY p.display_order, p.id) FROM spine.phases p WHERE {phase_owned}), '[]'::jsonb),
                'unassigned_milestones', coalesce((SELECT jsonb_agg(document ORDER BY recorded_at, id)
                    FROM milestone_docs WHERE phase_id IS NULL), '[]'::jsonb),
                'latest_memo', (SELECT {memo} FROM spine.visit_memos m WHERE {memo_owned}
                    ORDER BY m.recorded_at DESC, m.id DESC LIMIT 1),
                'current_sop_adoption', (SELECT jsonb_build_object(
                    'id', a.id, 'sop_version_id', a.sop_version_id,
                    'name', v.name, 'version', v.version, 'tag', v.tag,
                    'recorded_at', a.recorded_at,
                    'follows_adoption_id', {follows})
                    FROM spine.sop_adoptions a JOIN spine.sop_versions v ON v.id=a.sop_version_id
                    WHERE {adoption_owned} AND NOT EXISTS (
                        SELECT 1 FROM spine.sop_adoptions replacement
                        WHERE replacement.previous_adoption_id=a.id)
                    LIMIT 1))
            FROM target t WHERE t.kind = ANY(%(kinds)s)
        ''').format(judgments=judgments, milestone_owned=owned('m'), phase_owned=owned('p'),
                    memo=_memo_document('m'), memo_owned=owned('m'),
                    adoption_owned=owned('a'),
                    follows=sql.SQL('a.follows_adoption_id' if self._chain_sop_installed()
                                    else 'NULL::uuid')),
            {'id': identifier, 'kinds': list(kinds)}).fetchone()
        return row[0] if row else None

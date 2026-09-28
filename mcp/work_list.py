"""One flat list of the work items the ledger holds. Nothing is derived.

A fresh agent process with no memory needs a way to see what work already
exists. Every other read needs an ID or a recorded outside number, so a quote
created by an earlier process was invisible and a second one got created. This
read lists what is there, newest first, with only the joined facts that let a
reader recognize a work item: its recorded outside references, when it was last
visited, and the SOP version it currently adopts.

There is no status here and no "open" flag. Deciding which of these matters is
the agent's job.
"""

WORK_KINDS = ('quote', 'booking', 'job')
MAX_WORK_ITEMS = 1000

# Every listed item is one row of one of the three work tables. Exactly one of
# the owner columns on a related row is set, so coalesce names its owner.
_ITEMS = """
    WITH items AS (
        SELECT 'quote' AS kind, q.id, q.title, q.actor, q.recorded_at
        FROM spine.quotes q WHERE %(kind)s::text IS NULL OR %(kind)s = 'quote'
        UNION ALL
        SELECT 'booking', b.id, b.title, b.actor, b.recorded_at
        FROM spine.bookings b WHERE %(kind)s::text IS NULL OR %(kind)s = 'booking'
        UNION ALL
        SELECT 'job', j.id, j.title, j.actor, j.recorded_at
        FROM spine.jobs j WHERE %(kind)s::text IS NULL OR %(kind)s = 'job'
    )
    SELECT jsonb_build_object(
        'kind', i.kind, 'id', i.id, 'title', i.title, 'actor', i.actor,
        'recorded_at', i.recorded_at,
        'references', coalesce((SELECT jsonb_agg(jsonb_build_object(
                'type', r.reference_type, 'source', r.source, 'value', r.value)
            ORDER BY r.recorded_at, r.id)
            FROM spine.external_references r
            WHERE coalesce(r.quote_id, r.booking_id, r.job_id) = i.id), '[]'::jsonb),
        'latest_memo_at', (SELECT max(m.recorded_at) FROM spine.visit_memos m
            WHERE coalesce(m.quote_id, m.booking_id, m.job_id) = i.id),
        'sop_version_id', (SELECT a.sop_version_id FROM spine.sop_adoptions a
            WHERE coalesce(a.quote_id, a.booking_id, a.job_id) = i.id
              AND NOT EXISTS (SELECT 1 FROM spine.sop_adoptions replacement
                              WHERE replacement.previous_adoption_id = a.id)
            LIMIT 1))
    FROM items i
    ORDER BY i.recorded_at DESC, i.id DESC
    LIMIT %(limit)s
"""


class WorkListMixin:
    def work_items(self, kind=None, limit=200):
        """List every quote, booking and job, newest first, with joined facts.

        The optional kind keeps only quotes, only bookings or only jobs. Each
        entry carries its recorded external references, the recorded time of
        its most recent visit memo or None, and the SOP version it currently
        adopts or None. Nothing else is derived.
        """
        if kind is not None and kind not in WORK_KINDS:
            raise ValueError('work kind filter must be quote, booking or job')
        if type(limit) is not int or not 1 <= limit <= MAX_WORK_ITEMS:
            raise ValueError(f'work item limit must be between 1 and {MAX_WORK_ITEMS}')
        rows = self.connection.execute(_ITEMS, {'kind': kind, 'limit': limit}).fetchall()
        return [row[0] for row in rows]

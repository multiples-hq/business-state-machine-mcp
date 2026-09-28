"""Exact, attributed external references with ambiguity made explicit."""

from review import owner_columns


class ReferenceLedgerMixin:
    def record_external_reference(self, identifier, work_kind, work_id,
                                  reference_type, source, value, actor):
        return self._create('record_external_reference', (
            identifier, *owner_columns(work_kind, work_id), reference_type, source, value, actor,
        ))

    def resolve_external_reference(self, value, reference_type=None, source=None, limit=50):
        for label, text in [('value', value), ('reference_type', reference_type), ('source', source)]:
            if (label == 'value' or text is not None) and (
                not isinstance(text, str) or not text.strip()
            ):
                raise ValueError(f'{label} must be nonempty text')
        if type(limit) is not int or not 1 <= limit <= 200:
            raise ValueError('reference limit must be between 1 and 200')
        # Full count and the bounded candidate list share one statement snapshot.
        row = self.connection.execute('''
            WITH matched AS (
                SELECT r.*, coalesce(r.quote_id, r.booking_id, r.job_id) AS work_id,
                    CASE WHEN r.quote_id IS NOT NULL THEN 'quote'
                         WHEN r.booking_id IS NOT NULL THEN 'booking' ELSE 'job' END AS kind
                FROM spine.external_references r
                WHERE r.normalized_value = spine.normalize_reference(%(value)s)
                  AND (%(type)s::text IS NULL OR r.reference_type = %(type)s)
                  AND (%(source)s::text IS NULL OR r.source = %(source)s)
            ), candidates AS (
                SELECT kind, work_id, jsonb_agg(to_jsonb(m) - 'work_id' - 'kind' - 'normalized_value'
                    ORDER BY recorded_at, id) AS references
                FROM matched m GROUP BY kind, work_id
            ), page AS (
                SELECT c.kind, c.work_id, coalesce(q.title, b.title, j.title) AS title, c.references
                FROM candidates c
                LEFT JOIN spine.quotes q ON c.kind = 'quote' AND q.id = c.work_id
                LEFT JOIN spine.bookings b ON c.kind = 'booking' AND b.id = c.work_id
                LEFT JOIN spine.jobs j ON c.kind = 'job' AND j.id = c.work_id
                ORDER BY c.kind, c.work_id LIMIT %(limit)s
            )
            SELECT (SELECT count(*) FROM candidates),
                coalesce((SELECT jsonb_agg(to_jsonb(p) ORDER BY kind, work_id) FROM page p), '[]'::jsonb)
        ''', {'value': value, 'type': reference_type, 'source': source, 'limit': limit}).fetchone()
        count, candidates = row
        return {'status': 'not_found' if count == 0 else 'resolved' if count == 1 else 'ambiguous',
                'match_count': count, 'has_more': count > len(candidates), 'candidates': candidates}

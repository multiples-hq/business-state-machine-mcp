"""Find evidence already recorded, by payload hash, attachment hash or locator."""

import re

from psycopg.types.json import Jsonb

HEX64 = re.compile(r'[0-9a-f]{64}')

# One statement, so the full count and the bounded page share a snapshot.
FIND = '''
    WITH matched AS (
        SELECT e.id, e.recorded_at, e.actor, e.source_locator, e.source_at,
               jsonb_array_length(e.attachments) AS attachment_count,
               e.payload_sha256
        FROM spine.evidence e
        WHERE (%(payload)s::text IS NULL OR e.payload_sha256 = %(payload)s)
          AND (%(attachment)s::jsonb IS NULL OR e.attachments @> %(attachment)s)
          AND (%(locator)s::text IS NULL OR e.source_locator = %(locator)s)
    ), page AS (
        SELECT * FROM matched ORDER BY recorded_at, id LIMIT %(limit)s
    )
    SELECT (SELECT count(*) FROM matched),
           coalesce((SELECT jsonb_agg(to_jsonb(p) ORDER BY p.recorded_at, p.id)
                     FROM page p), '[]'::jsonb)
'''


class EvidenceLookupMixin:
    def find_evidence(self, payload_sha256=None, attachment_sha256=None,
                      source_locator=None, limit=50):
        """Evidence rows matching exactly one lookup key. It finds; it never merges.

        Uses the payload digest column and its indexes. Matching is exact: a locator differing by one character or by
        case is a different locator.
        """
        keys = {'payload_sha256': payload_sha256,
                'attachment_sha256': attachment_sha256,
                'source_locator': source_locator}
        given = [name for name, value in keys.items() if value is not None]
        if len(given) != 1:
            raise ValueError('give exactly one of payload_sha256, attachment_sha256 '
                             'or source_locator')
        key, value = given[0], keys[given[0]]
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f'{key} must be nonempty text')
        if key != 'source_locator' and not HEX64.fullmatch(value):
            raise ValueError(f'{key} must be 64 lowercase hexadecimal characters')
        if type(limit) is not int or not 1 <= limit <= 200:
            raise ValueError('evidence limit must be between 1 and 200')
        count, found = self.connection.execute(FIND, {
            'payload': payload_sha256,
            'attachment': Jsonb([{'sha256': attachment_sha256}]) if attachment_sha256 else None,
            'locator': source_locator,
            'limit': limit,
        }).fetchone()
        return {'match_count': count, 'has_more': count > len(found), 'evidence': found}

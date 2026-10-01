"""Find a party by what the agent sees: an email address, a phone number or a name.

It lists candidates and never picks. An exact match is an email, phone or
alias equal to the text, ignoring case. Only when there is none, a name
match is a name or alias that contains every word of the text, or that
appears inside the text, ignoring case: "Coastal Refrig" finds
"Coastal Refrigeration Inc", and "Harbor Co" finds the alias "Harbor". Both
are plain text containment; nothing fuzzier, so a misspelling finds nothing.
Only a name or alias of three characters or more is looked for inside the
text, so a one-letter alias does not match most texts.
"""

_EXACT = '''
    SELECT DISTINCT ON (p.id) p.id, p.kind, p.name, p.is_operator, i.kind, i.value
    FROM spine.party_identifiers i JOIN spine.parties p ON p.id = i.party_id
    WHERE i.kind IN ('email', 'phone', 'alias') AND lower(i.value) = lower(%(text)s)
    ORDER BY p.id, i.recorded_at, i.id'''

_WORDS = '''
    SELECT DISTINCT ON (p.id) p.id, p.kind, p.name, p.is_operator, x.kind || '_words', x.value
    FROM (SELECT id AS party_id, 'name' AS kind, name AS value FROM spine.parties
          UNION ALL
          SELECT party_id, kind, value FROM spine.party_identifiers WHERE kind = 'alias') x
    JOIN spine.parties p ON p.id = x.party_id
    WHERE (SELECT bool_and(strpos(lower(x.value), word) > 0) FROM unnest(%(words)s::text[]) word)
       OR (length(btrim(x.value)) >= 3 AND strpos(lower(%(text)s), lower(x.value)) > 0)
    ORDER BY p.id, x.kind = 'name' DESC, x.value'''

_KEYS = ('id', 'kind', 'name', 'is_operator', 'match', 'matched_value')


class PartyLookupMixin:
    def find_parties(self, text):
        words = text.lower().split()
        if not words:
            raise ValueError('text must not be empty: send an email, a phone number or a name')
        rows = self.connection.execute(_EXACT, {'text': text.strip()}).fetchall()
        if not rows:
            rows = self.connection.execute(_WORDS, {'words': words,
                                                    'text': text.strip()}).fetchall()
        candidates = [dict(zip(_KEYS, row)) for row in rows]
        for candidate in candidates:
            candidate['id'] = str(candidate['id'])
        return sorted(candidates, key=lambda c: (c['name'].lower(), c['id']))

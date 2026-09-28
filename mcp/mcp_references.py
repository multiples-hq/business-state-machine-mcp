"""Small external-reference MCP surface; no matching guesses or external calls."""

from mcp_params import Actor, NewId, PageLimit, WorkId, WorkKind, said
from mcp_support import parse_uuid


def register_reference_tools(tool, serialized, ledger):
    @tool()
    @serialized
    def record_external_reference(
        id: NewId, work_kind: WorkKind, work_id: WorkId,
        reference_type: said(str, 'What kind of number this is, in your own words, such as '
                             'purchase_order or ticket. Must not be empty.'),
        source: said(str, 'The outside system or party that uses this number. '
                     'Must not be empty.'),
        value: said(str, 'The number or code exactly as the outside system writes it.'),
        actor: Actor,
    ) -> dict:
        """Record a number or code an outside system uses for one quote, booking or job.

        Later, resolve_external_reference finds the work by that number. A
        recorded reference cannot be withdrawn or corrected.
        """
        return {'id': str(ledger.record_external_reference(
            parse_uuid(id), work_kind, parse_uuid(work_id), reference_type, source, value, actor,
        ))}

    @tool()
    @serialized
    def resolve_external_reference(
        value: said(str, 'The number or code to look up. Case and punctuation are ignored.'),
        reference_type: said(str | None, 'Keep only references recorded with this '
                             'reference_type.') = None,
        source: said(str | None, 'Keep only references recorded with this source.') = None,
        limit: PageLimit = 50,
    ) -> dict:
        """Find the work recorded under an outside number; several matches are all returned.

        More than one candidate is reported, never resolved for you: do not
        guess among them.

        Matching ignores case and every character that is not a letter or
        digit, so REF-10422, ref 10422 and ref10422 are the same number.
        Nothing else is guessed. The value is returned as it was recorded.
        match_count counts distinct work items; has_more means some were
        left out, so narrow the search with reference_type or source.
        """
        return ledger.resolve_external_reference(value, reference_type, source, limit)

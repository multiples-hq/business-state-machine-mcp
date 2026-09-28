"""Evidence placement: which work an evidence row is about."""

from pydantic import BaseModel, ConfigDict

from mcp_params import Actor, NewId, PageLimit, WorkId, WorkKindWord, said
from mcp_support import parse_uuid


class EvidenceWorkInput(BaseModel):
    """One placement: the work an evidence row is about, plus a stable link ID."""

    model_config = ConfigDict(extra='forbid', strict=True)

    work_kind: WorkKindWord
    work_id: WorkId
    id: said(str, 'UUID you generate for this link row. Keep it when you retry.')


def link_evidence(ledger, evidence_id, about_work, actor):
    """Append the placement rows for one evidence ID. The caller owns the transaction."""
    for placement in about_work or []:
        ledger.link_evidence_work(
            parse_uuid(placement.id), evidence_id, placement.work_kind,
            parse_uuid(placement.work_id), actor,
        )


def register_evidence_tools(tool, serialized, ledger):
    @tool()
    @serialized
    def link_evidence_work(id: NewId,
                           evidence_id: said(str, 'UUID of evidence already recorded.'),
                           work_kind: WorkKindWord, work_id: WorkId, actor: Actor) -> dict:
        """Record that one existing evidence row is about one quote, booking or job.

        Use this to link evidence after it was recorded. Links are appended and
        never removed; the same pair under a new ID is simply a second row.
        """
        return {'id': str(ledger.link_evidence_work(
            parse_uuid(id), parse_uuid(evidence_id), work_kind, parse_uuid(work_id), actor,
        ))}

    @tool()
    @serialized
    def find_evidence(
        payload_sha256: said(str | None, 'SHA-256 of the exact original_payload text as UTF-8: '
                             '64 lowercase hexadecimal characters.') = None,
        attachment_sha256: said(str | None, 'SHA-256 of a stored file: 64 lowercase '
                                'hexadecimal characters.') = None,
        source_locator: said(str | None, 'The source_locator exactly as it was recorded, '
                             'case included.') = None,
        limit: PageLimit = 50,
    ) -> dict:
        """Find evidence you have already recorded. Give exactly one key.

        Every match is exact. Two keys, or none, is refused.

        This finds; it never merges rows and never refuses a recording. Use it
        before recording a source, and cite the evidence ID it returns instead
        of recording the same source again. Recording it twice is still allowed,
        because two mailboxes can hold the same message.

        match_count is the full number of matching rows; has_more means the
        limit truncated the list.
        """
        return ledger.find_evidence(payload_sha256, attachment_sha256, source_locator, limit)

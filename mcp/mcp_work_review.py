"""MCP tools that review a quote, booking or job with one shared review system."""

import mcp_params as P
from mcp_params import Actor, AnyWorkId, IncludeEvidence, NewId, WorkId, WorkKind, said
from mcp_support import found, parse_datetime, parse_uuid, parse_uuids


def build_work_review_calls(ledger):
    """Build the one implementation of each review call.

    register_work_review_tools below publishes each one as a tool. Any other
    caller uses these same functions, so a change to a review call is made once.
    """

    def create_work_phase(
        id: NewId, work_kind: WorkKind, work_id: WorkId,
        name: said(str, 'Name of the phase, as a person would read it.'),
        display_order: said(int, 'Where the phase sorts among the phases of this work item: '
                            '0 or more, lowest first.'),
        actor: Actor,
    ) -> dict:
        """Create a phase, a named group of milestones, on one quote, booking or job.

        Adopting an SOP creates its phases for you; use this for a phase no
        SOP names. A phase has no status of its own. Returns {"id": ...}.
        """
        return {'id': str(ledger.create_work_phase(
            parse_uuid(id), work_kind, parse_uuid(work_id), name, display_order, actor,
        ))}

    def create_work_milestone(
        id: NewId, work_kind: WorkKind, work_id: WorkId,
        title: said(str, 'What this checkpoint is, in a few words.'),
        actor: Actor,
        phase_id: said(str | None, 'UUID of a phase on the same work item. The phase of a '
                       'milestone cannot be changed later.') = None,
    ) -> dict:
        """Create a milestone, a checkpoint to be judged, on one quote, booking or job.

        Adopting an SOP creates its milestones for you; use this for a
        checkpoint no SOP names. It reads as unassessed until record_review
        judges it. Returns {"id": ...}.
        """
        identifier = parse_uuid(id)
        with ledger.connection.transaction():
            stored = ledger.create_work_milestone(
                identifier, work_kind, parse_uuid(work_id), title, actor,
            )
            if phase_id:
                ledger.assign_milestone_phase(identifier, parse_uuid(phase_id), actor)
        return {'id': str(stored)}

    def leave_work_memo(
        id: NewId, work_kind: WorkKind, work_id: WorkId,
        review_started_at: said(str, P.MEMO_STARTED),
        review_ended_at: said(str, P.MEMO_ENDED),
        summary: said(str, P.MEMO_SUMMARY), decision: said(str, P.MEMO_DECISION),
        changed: said(bool, P.MEMO_CHANGED), actor: Actor,
        waiting_for: said(str | None, P.MEMO_WAITING_FOR) = None,
        next_review_at: said(str | None, P.MEMO_NEXT_REVIEW) = None,
        details: said(dict | None, P.MEMO_DETAILS) = None,
        reviewed_milestone_ids: said(list[str] | None, P.MEMO_MILESTONES) = None,
        reviewed_judgment_ids: said(list[str] | None, P.MEMO_JUDGMENTS) = None,
    ) -> dict:
        """Leave a memo, the note of one look at a quote, booking or job, with no judgment.

        Use it when you looked at the work and judged no milestone, so the
        next reader sees what you found and decided. To judge a milestone,
        use record_review, which writes its own memo.
        """
        return ledger.append_work_memo(
            parse_uuid(id), work_kind, parse_uuid(work_id), parse_datetime(review_started_at),
            parse_datetime(review_ended_at), summary, decision, changed, actor,
            waiting_for=waiting_for, next_review_at=parse_datetime(next_review_at),
            details=details, reviewed_milestones=parse_uuids(reviewed_milestone_ids or []),
            reviewed_judgments=parse_uuids(reviewed_judgment_ids or []),
        )

    def read_work_review(id: AnyWorkId, include_evidence: IncludeEvidence = False) -> dict:
        """Read where one quote, booking or job stands: phases, milestones, latest judgments.

        It shows every milestone, including ones no SOP names, plus the
        latest memo and a pointer to the current SOP adoption. For the whole
        chain at once, use read_case_brief.
        An unknown ID is refused as not found.
        """
        return found(ledger.review(parse_uuid(id), include_evidence=include_evidence), 'work', id)

    def read_work_memos(
        work_id: WorkId, limit: P.PageLimit = 50,
        before_recorded_at: said(str | None, 'Paging cursor: recorded_at of the oldest memo '
                                 'you already have. Send it together with before_id.') = None,
        before_id: said(str | None, 'Paging cursor: id of that same oldest memo.') = None,
    ) -> dict:
        """Read the memos of one quote, booking or job, newest first.

        To page, send before_recorded_at and before_id of the oldest memo you have.
        The answer is {"memos": [...]}; no memo yet gives an empty list.
        An unknown work ID is refused as not found.
        """
        ledger.require_row('work', parse_uuid(work_id))
        return {'memos': ledger.work_memos(
            parse_uuid(work_id), limit, parse_datetime(before_recorded_at),
            parse_uuid(before_id) if before_id else None,
        )}

    return {function.__name__: function for function in (
        create_work_phase, create_work_milestone, leave_work_memo,
        read_work_review, read_work_memos,
    )}


def register_work_review_tools(tool, serialized, ledger):
    """Add the owner-aware review tools. `work_kind` is quote, booking or job."""
    for function in build_work_review_calls(ledger).values():
        tool()(serialized(function))

"""Record a review's judgments and memo in one transaction."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

import mcp_params as P
from mcp_params import Actor, WorkId, WorkKindWord, said
from mcp_support import parse_date, parse_datetime, parse_uuid, parse_uuids

KEEP = ' Keep it when you retry.'


class JudgmentInput(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)

    id: said(str, 'UUID you generate for this judgment.' + KEEP)
    milestone_id: said(str, 'UUID of a milestone on the reviewed work item.')
    status: said(P.StatusWords, 'Your judgment of the milestone.')
    explanation: str = Field(min_length=1, description='Why you judge it so, in words.')
    evidence_ids: list[str] = Field(min_length=1, description=(
        'UUIDs of recorded evidence that this judgment rests on; at least one. '
        'Evidence linked only to other work is refused.'))
    occurred_on: said(str | None, 'The day the thing happened, when known: ' + P.DATE
                      + ' Goes together with occurrence_precision.') = None
    occurrence_precision: said(Literal['exact', 'by'] | None, 'exact when it happened on '
                               'occurred_on; by when it happened no later than that day.') = None
    revises_ids: list[str] = Field(default_factory=list, description=(
        'At most one UUID: the earlier judgment of the same work item that this one corrects.'))
    based_on_ids: list[str] = Field(default_factory=list, description=(
        'UUIDs of earlier judgments on the same work item that this one relies on.'))


class RoleInput(BaseModel):
    """One party role claimed in this review, on the reviewed work or standing."""
    model_config = ConfigDict(extra='forbid', strict=True)

    id: said(str, 'UUID you generate for this role row.' + KEEP)
    party_id: said(str, 'UUID of the existing party that holds the role.')
    role: str = Field(min_length=1, description=P.ROLE)
    confidence: P.Confidence = 'confirmed'
    evidence_id: P.OptionalEvidenceId = None
    on_party_id: said(str | None, P.ON_PARTY + ' Omit for a role on the reviewed work.') = None
    started_on: said(str | None, P.STARTED_ON) = None
    ended_on: said(str | None, P.ENDED_ON) = None


class ReviewMemoInput(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)

    id: said(str, 'UUID you generate for this memo.' + KEEP)
    review_started_at: said(str, P.MEMO_STARTED)
    review_ended_at: said(str, P.MEMO_ENDED)
    summary: str = Field(min_length=1, description=P.MEMO_SUMMARY)
    decision: str = Field(min_length=1, description=P.MEMO_DECISION)
    changed: said(bool, P.MEMO_CHANGED)
    waiting_for: said(str | None, P.MEMO_WAITING_FOR) = None
    next_review_at: said(str | None, P.MEMO_NEXT_REVIEW) = None
    details: dict = Field(default_factory=dict, description=P.MEMO_DETAILS)
    reviewed_milestone_ids: list[str] = Field(default_factory=list,
                                              description=P.MEMO_MILESTONES)
    reviewed_judgment_ids: list[str] = Field(default_factory=list,
                                             description=P.MEMO_JUDGMENTS)


def register_review_tools(tool, serialized, ledger):
    @tool()
    @serialized
    def record_review(
        work_kind: WorkKindWord, work_id: WorkId, actor: Actor,
        judgments: said(list[JudgmentInput], 'One entry per milestone you judge, each milestone '
                        'at most once. [] for a review that changes no status.'),
        memo: said(ReviewMemoInput, 'The required note of this review: what you found and '
                   'what you decided.'),
        roles: said(list[RoleInput] | None, 'Party roles you claim in this review, on the '
                    'reviewed work or standing on another party. Omit when none.') = None,
    ) -> dict:
        """Save one review of a quote, booking or job: judgments, party roles and the memo, together.

        This is the way to record a judgment. One transaction saves all of
        it; one bad entry saves none of it. Adopt an SOP on the quote first
        when you can (see the server instructions); judging with none
        adopted is allowed. Send real review times. Every new judgment, its
        milestone and every role claimed here are linked into the memo for
        you. Every milestone and judgment named must belong to this work
        item. A retry sends the entire payload again unchanged, including
        memo, judgment and role IDs. Returns memo_id, judgment_ids and, when
        roles were sent, role_ids.
        """
        owner_id = parse_uuid(work_id)
        memo_id = parse_uuid(memo.id)
        identifiers = [parse_uuid(j.id) for j in judgments]
        if len(set(identifiers)) != len(identifiers):
            raise ValueError('a review must not repeat a judgment ID')
        milestones = [parse_uuid(j.milestone_id) for j in judgments]
        if len(set(milestones)) != len(milestones):
            raise ValueError('a review may assess each milestone once')
        if judgments and not memo.changed:
            raise ValueError('a review with judgments must declare changed=true')
        started = parse_datetime(memo.review_started_at)
        ended = parse_datetime(memo.review_ended_at)
        if started is None or ended is None:
            raise ValueError('review start and end times are required')

        with ledger.connection.transaction():
            # Take the memo lock first: it identifies this immutable review.
            # A retry with changed batch contents reaches the memo's exact-content
            # check and rolls back any new judgments before returning an error.
            ledger.connection.execute(
                'SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))', (str(memo_id),)
            )
            owner = ledger.work(owner_id)
            if owner is None or owner['kind'] != work_kind:
                raise ValueError('review work does not exist with the supplied kind')
            roles_before = ledger.memo_roles(memo_id)
            for judgment, identifier, milestone_id in zip(judgments, identifiers, milestones):
                ledger.append_judgment(
                    identifier, milestone_id, judgment.status, judgment.explanation, actor,
                    parse_uuids(judgment.evidence_ids),
                    occurred_on=parse_date(judgment.occurred_on),
                    occurrence_precision=judgment.occurrence_precision,
                    revises=parse_uuids(judgment.revises_ids),
                    based_on=parse_uuids(judgment.based_on_ids),
                )
            ledger.append_work_memo(
                memo_id, work_kind, owner_id, started, ended, memo.summary, memo.decision,
                memo.changed, actor, waiting_for=memo.waiting_for,
                next_review_at=parse_datetime(memo.next_review_at), details=memo.details,
                reviewed_milestones=sorted(set(milestones + parse_uuids(memo.reviewed_milestone_ids))),
                reviewed_judgments=sorted(set(identifiers + parse_uuids(memo.reviewed_judgment_ids))),
            )
            claimed = sorted(parse_uuid(claim.id) for claim in roles or [])
            if roles_before is not None and roles_before != claimed:
                raise ValueError('a retry must keep the same role IDs as the recorded review')
            for claim in roles or []:
                ledger.record_role(
                    parse_uuid(claim.id), parse_uuid(claim.party_id), claim.role, actor,
                    on_party_id=parse_uuid(claim.on_party_id) if claim.on_party_id else None,
                    work_kind=None if claim.on_party_id else work_kind,
                    work_id=None if claim.on_party_id else owner_id,
                    confidence=claim.confidence,
                    evidence_id=parse_uuid(claim.evidence_id) if claim.evidence_id else None,
                    started_on=parse_date(claim.started_on), ended_on=parse_date(claim.ended_on),
                    memo_id=memo_id,
                )
        receipt = {'memo_id': str(memo_id), 'judgment_ids': [str(i) for i in identifiers]}
        if roles:
            receipt['role_ids'] = [claim.id for claim in roles]
        return receipt

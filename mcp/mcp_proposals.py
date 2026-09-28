"""MCP tools for drafts: propose, list, read, mark recorded, withdraw.

Registered only when LEDGER_PROPOSALS names the run's proposals directory.
These write files, never ledger rows. A person answers each draft in the
harness conversation; the accepted outcome is then recorded with the
ordinary tools (record_review, create_party, record_role, adopt_sop_version)
and the proposal is marked recorded with the memo that carries it.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

import proposals
import mcp_params as P
from mcp_params import Actor, said
from mcp_support import InvalidUuid, found, parse_uuid, setting

ProposalId = said(str, 'Id of the draft, as propose_review returned it.')


class WouldRecord(BaseModel):
    """One row the agent would write: a role, an identifier, a judgment, a memo or an adoption."""
    model_config = ConfigDict(extra='forbid', strict=True)
    type: said(Literal['role', 'identifier', 'judgment', 'memo', 'adoption', 'ignore'],
               'Which kind of row this is; ignore means nothing would be recorded.')
    party: said(str | None, 'For a role or an identifier, the name of the party.') = None
    role: said(str | None, 'For a role, the role word, such as customer or supplier.') = None
    confidence: said(P.ConfidenceWords | None, 'For a role, how sure the evidence is.') = None
    on_party: said(str | None, 'For a standing role, the name of the party it is held '
                   'on. Omit for a role on the work.') = None
    replaces_role_id: said(str | None, 'For a role, UUID of the recorded role row that this '
                           'one would replace.') = None
    identifier_kind: said(P.IdentifierKindWords | None, 'For an identifier, what the value '
                          'is.') = None
    value: said(str | None, 'For an identifier, the value as it was seen.') = None
    milestone_id: said(str | None, 'For a judgment, UUID of the milestone.') = None
    milestone_title: said(str | None, 'For a judgment, the milestone title, so the person '
                          'can read the draft.') = None
    from_status: said(str | None, 'For a judgment, the status the case brief shows '
                      'now.') = None
    to_status: said(P.StatusWords | None, 'For a judgment, the status you would record.') = None
    reason: said(str | None, 'Why you would record this row.') = None
    sop_version_id: said(str | None, 'For an adoption, UUID of the SOP version.') = None
    sop_version_name: said(str | None, 'For an adoption, its name and version, so the '
                           'person can read the draft.') = None


class MemoDraft(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    summary: said(str, P.MEMO_SUMMARY)
    decision: said(str, P.MEMO_DECISION)
    waiting_for: said(str | None, P.MEMO_WAITING_FOR) = None


class ProposalInput(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    kind: said(Literal['party', 'milestone', 'memo', 'ignore', 'sop'],
               'What the decision is mainly about; ignore means a message needs no record.')
    needs_human: said(bool, 'true when you want the person\'s judgment; false when you are '
                      'confident. Either way the person answers before anything is recorded.')
    question: said(str, 'One line: the question for the person, or the decision stated.')
    summary: said(str, 'What arrived and the context you read it against, in a few sentences.')
    message_ids: said(list[str], 'The messages this decision rests on, each named as its '
                      'source names it, such as the source_locator you record it under. '
                      'These are not evidence UUIDs and are not checked.') = Field(
                          default_factory=list)
    sources: said(list[str], 'Every source locator the draft cites, those messages '
                  'included. Not checked.') = Field(default_factory=list)
    work_kind: said(P.WorkKindWords | None, 'Kind of the work item that work_id names; goes '
                    'together with work_id.') = None
    work_id: said(str | None, 'UUID of the existing quote, booking or job the decision is '
                  'about; needed for a judgment, an adoption or a role on work. A UUID that '
                  'names no such work is refused.') = None
    would_record: said(list[WouldRecord], 'The rows you would write if the person '
                       'agrees.') = Field(default_factory=list)
    memo: said(MemoDraft | None, 'The memo you would leave with it.') = None

    @model_validator(mode='after')
    def _bound(self):
        if (self.work_id is None) != (self.work_kind is None):
            raise ValueError('work_kind and work_id go together')
        if self.work_id is None and any(w.type in ('judgment', 'adoption') or (w.type == 'role' and not w.on_party)
                                        for w in self.would_record):
            raise ValueError('a judgment, an adoption or a role on the work needs work_kind and work_id')
        if self.kind == 'ignore' and self.would_record and any(w.type != 'ignore' for w in self.would_record):
            raise ValueError('an ignore proposal records nothing else')
        return self


def _directory():
    directory = setting('PROPOSALS')
    if not directory:
        raise ValueError('this ledger has no proposals directory (LEDGER_PROPOSALS)')
    return directory


def register_proposal_tools(tool, serialized, ledger):
    @tool()
    @serialized
    def propose_review(
        proposal: said(ProposalInput, 'The draft: the question, what it rests on and what '
                       'you would record.'),
        actor: Actor,
        id: said(str | None, 'UUID for the draft; omit it and the server makes one. Retry '
                 'with the same id and draft; a different draft is refused.') = None,
    ) -> dict:
        """Put a draft decision in front of a person before recording anything.

        One proposal per decision, not per message: a decision may rest on
        several messages and touch one party, one or several milestones, a
        memo only or an SOP adoption (such as a job moving to a break_glass
        recovery version), or say a message is ignored. The draft is a file,
        not a ledger row, and it waits for the person's word in the
        conversation. After the person answers, record the outcome with the
        ordinary tools and call mark_proposal_recorded with the memo; or
        withdraw it.
        """
        if id is not None:
            parse_uuid(id)
        if proposal.work_id is not None:
            work = found(ledger.work(parse_uuid(proposal.work_id)), 'work', proposal.work_id)
            if work['kind'] != proposal.work_kind:
                raise ValueError(f'proposal.work_id names a {work["kind"]}, '
                                 f'not a {proposal.work_kind}')
        for index, row in enumerate(proposal.would_record):
            for key in ('milestone_id', 'sop_version_id', 'replaces_role_id'):
                if getattr(row, key) is not None:
                    try:
                        parse_uuid(getattr(row, key))
                    except InvalidUuid as error:
                        error.name = f'proposal.would_record[{index}].{key}'
                        raise
        record = proposals.propose(_directory(), proposal.model_dump(), actor, id)
        return {'id': record['id'], 'status': record['status'], 'asked_at': record['asked_at']}

    @tool()
    @serialized
    def list_proposals(
        status: said(Literal['proposed', 'recorded', 'withdrawn'] | None, 'Keep only proposed '
                     '(still open), recorded or withdrawn drafts. Omit for all.') = None,
        work_id: said(str | None, 'Keep only drafts about this quote, booking or job.') = None,
    ) -> dict:
        """Every proposal, oldest first; optionally one status or one work item.

        The answer is {"proposals": [...]}; none gives an empty list.

        Read this before proposing: a decision a person already answered
        is recorded or withdrawn, and an open one is not proposed twice.
        """
        return {'proposals': proposals.list_proposals(_directory(), status, work_id)}

    @tool()
    @serialized
    def read_proposal(id: ProposalId) -> dict:
        """One proposal with its status and what became of it. An unknown ID is refused as not found."""
        return found(proposals.read_proposal(_directory(), id), 'proposal', id)

    @tool()
    @serialized
    def mark_proposal_recorded(
        id: ProposalId,
        memo_id: said(str, 'UUID of the memo already in the ledger that carries the outcome.'),
    ) -> dict:
        """After the outcome is recorded, name the memo that carries it.

        The memo is read back from the ledger first; only then does the
        proposal say recorded. Repeating with the same memo is a no-op.
        """
        memo = ledger.connection.execute(
            'SELECT id, summary, decision, recorded_at FROM spine.visit_memos WHERE id = %s',
            (parse_uuid(memo_id),)).fetchone()
        read_back = None if memo is None else {
            'memo_id': str(memo[0]), 'summary': memo[1], 'decision': memo[2],
            'recorded_at': memo[3].isoformat(timespec='seconds')}
        record = proposals.mark_recorded(_directory(), id, memo_id, read_back)
        return {'id': id, 'status': record['status'], 'recorded': record['recorded']}

    @tool()
    @serialized
    def withdraw_proposal(id: ProposalId,
                          reason: said(str, 'Why the draft is withdrawn, in words.'),
                          actor: Actor) -> dict:
        """Withdraw a draft the person declined or that no longer applies."""
        record = proposals.withdraw(_directory(), id, reason, actor)
        return {'id': id, 'status': record['status'], 'withdrawn': record['withdrawn']}

"""MCP tools for the party cluster: parties, their identifiers, their roles.

A party is a person, an agent or an organization in one
table. What is said about a party is appended as rows: an identifier (an
email, a phone, an address, an alias it was seen under) or a role (held on another party,
standing, or on one quote, booking or job, for that chain). Each row names the
evidence that supports it. A change is a new row; nothing is edited.
"""

from mcp_params import (DATE, ENDED_ON, ON_PARTY, ROLE, STARTED_ON, Actor, Confidence,
                        IdentifierKindWords, NewId, OptionalEvidenceId, OptionalMemoId,
                        PartyKindWords, ReadId, WorkKindWords, said)
from mcp_support import found, parse_date, parse_uuid

PartyId = said(str, 'UUID of an existing party.')


def register_party_tools(tool, serialized, ledger):
    """The party creation, the identifier and role writes, and the party read."""

    @tool()
    @serialized
    def create_party(
        id: NewId, kind: said(PartyKindWords, 'What the party is.'),
        name: said(str, 'The name to show for this party. Must not be empty.'),
        actor: Actor,
        is_operator: said(bool, 'true only for the one organization that runs this ledger. '
                          'A second operator is refused.') = False,
    ) -> dict:
        """Create a party: a person, an agent, or an organization.

        Parties are never merged: the same company under two names is two
        rows until an alias identifier says otherwise. The name is a label
        only: record an email, phone number or address with
        record_party_identifier, not in the name.
        """
        return {'id': str(ledger.create_party(parse_uuid(id), kind, name, actor, is_operator))}

    @tool()
    @serialized
    def record_party_identifier(
        id: NewId, party_id: PartyId,
        kind: said(IdentifierKindWords, 'What the value is; alias is another name.'),
        value: said(str, 'The email, phone number, address or other name, as it was seen.'),
        actor: Actor, evidence_id: OptionalEvidenceId = None,
    ) -> dict:
        """Record an email, phone, address or alias a party was seen under, and where.

        One row per value: a person with two emails has two rows, and an
        organization with two sites has two address rows. A new one is a new
        row, never a change to the party. evidence_id names the message
        that showed it.
        """
        return {'id': str(ledger.record_party_identifier(
            parse_uuid(id), parse_uuid(party_id), kind, value,
            parse_uuid(evidence_id) if evidence_id else None, actor))}

    @tool()
    @serialized
    def record_role(
        id: NewId, party_id: said(str, 'UUID of the existing party that holds the role.'),
        role: said(str, ROLE), actor: Actor,
        on_party_id: said(str | None, ON_PARTY + ' Omit for a role on work.') = None,
        work_kind: said(WorkKindWords | None, 'For a role on one work item, its kind. '
                        'Goes together with work_id; omit both when on_party_id is given.') = None,
        work_id: said(str | None, 'UUID of the quote, booking or job the role is on. '
                      'Goes together with work_kind.') = None,
        confidence: Confidence = 'confirmed',
        evidence_id: OptionalEvidenceId = None,
        started_on: said(str | None, STARTED_ON) = None,
        ended_on: said(str | None, ENDED_ON) = None, memo_id: OptionalMemoId = None,
    ) -> dict:
        """Record that a party holds a role, with the evidence for it.

        Exactly one target: on_party_id for a standing role (a person works
        at an organization; one organization is a supplier to another) or
        work_kind plus work_id for a role on one quote, booking or job (this
        organization is the supplier on this booking). A former role is
        refused without ended_on, here and in record_review. To end a role
        already recorded, use end_role.
        """
        return {'id': str(ledger.record_role(
            parse_uuid(id), parse_uuid(party_id), role, actor,
            on_party_id=parse_uuid(on_party_id) if on_party_id else None,
            work_kind=work_kind, work_id=parse_uuid(work_id) if work_id else None,
            confidence=confidence, evidence_id=parse_uuid(evidence_id) if evidence_id else None,
            started_on=parse_date(started_on), ended_on=parse_date(ended_on),
            memo_id=parse_uuid(memo_id) if memo_id else None))}

    @tool()
    @serialized
    def end_role(id: NewId,
                 role_id: said(str, 'UUID of the role row to end. It must be the current row '
                               'of that role: not already ended or replaced.'),
                 ended_on: said(str, 'The day the role ended: ' + DATE), actor: Actor,
                 evidence_id: OptionalEvidenceId = None, memo_id: OptionalMemoId = None) -> dict:
        """End a role by appending a replacement row marked former.

        The earlier row stays exactly as recorded; reads return the new row.
        """
        return {'id': str(ledger.end_role(
            parse_uuid(id), parse_uuid(role_id), parse_date(ended_on), actor,
            evidence_id=parse_uuid(evidence_id) if evidence_id else None,
            memo_id=parse_uuid(memo_id) if memo_id else None))}

    @tool()
    @serialized
    def read_party(id: ReadId) -> dict:
        """Read one party with its identifiers and its roles as they stand now.

        roles are the roles this party holds, standing and on work; held_by
        are the roles other parties hold on it. Each role carries its
        confidence, its evidence and the reviews that made it. Replaced rows
        stay in the ledger but are not returned here. An unknown ID is
        refused as not found.
        """
        return found(ledger.party(parse_uuid(id)), 'party', id)

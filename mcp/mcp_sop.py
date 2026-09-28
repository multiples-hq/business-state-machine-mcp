"""MCP tools for immutable SOP versions and explicit work adoption."""

from mcp_params import (Actor, EvidenceIds, IncludeEvidence, NewId, ReadId, SopStatusWords,
                        SopTagWords, WorkId, WorkKind, said)
from mcp_support import found, parse_bindings, parse_uuid, parse_uuids

SopVersionId = said(str, 'UUID of a published SOP version, from list_sop_versions.')
Reason = said(str, 'Why, in words. Must not be empty.')


def register_sop_tools(tool, serialized, ledger):
    """Add the bounded SOP publish, adoption and read surface."""

    @tool()
    @serialized
    def publish_sop_version(
        id: NewId,
        name: said(str, 'Name of the procedure. A name and version pair can be published once.'),
        version: said(str, 'Version label of this text, such as 1 or 2026-03.'),
        tag: said(SopTagWords, 'standard, or break_glass for a recovery procedure that only '
                  'a job may adopt.'),
        definition: said(dict, 'Exactly {"stages": {"quote": {"phases": [...]}, "booking": '
                         '{"phases": [...]}, "job": {"phases": [...]}}}. A phase is {"key", '
                         '"name", "display_order": integer 0 or more, "milestones": [{"key", '
                         '"title", "criterion"}]}. All three stages are required; phases may '
                         'be []. Every string is non-empty.'),
        actor: Actor,
        based_on_version_id: said(str | None, 'UUID of the SOP version this one was written '
                                  'from. A note of origin only; nothing is inherited.') = None,
    ) -> dict:
        """Publish an SOP version: the phases and milestones to follow at each stage of a chain.

        A published version never changes; a correction is a new version. No
        work is changed and no default is installed: work follows a version
        only after adopt_sop_version. In the definition, phase keys and
        display orders are unique within a stage, milestone keys are unique
        within a stage, and the order of the milestones array is kept. A
        criterion is an instruction for the agent that judges the milestone;
        the ledger never evaluates it.
        """
        return {'id': str(ledger.publish_sop_version(
            parse_uuid(id), name, version, tag, definition, actor,
            based_on_version_id=(parse_uuid(based_on_version_id)
                                 if based_on_version_id else None),
        ))}

    @tool()
    @serialized
    def adopt_sop_version(
        id: NewId, work_kind: WorkKind, work_id: WorkId, sop_version_id: SopVersionId,
        reason: Reason, actor: Actor, evidence_ids: EvidenceIds,
        phase_bindings: said(list[dict], 'One {"phase_key": text, "phase_id": UUID you '
                             'generate} for every phase of this work\'s stage in the '
                             'definition, each exactly once.'),
        milestone_bindings: said(list[dict], 'One {"phase_key": text, "milestone_key": text, '
                                 '"milestone_id": UUID you generate} for every milestone of '
                                 'that stage, each exactly once.'),
        expected_previous_adoption_id: said(str | None, 'Omit for a first adoption. To replace '
                                            'a job\'s SOP, the UUID of its current adoption; '
                                            'a stale value is refused.') = None,
    ) -> dict:
        """Record that a quote or a lone job follows one SOP version, or replace any job's.

        Adopt on the quote: its bookings and jobs follow on their own, and
        adopting on them is refused. The call creates the phases and
        milestones of that stage under the IDs you bind. Which version to adopt is not yours to
        pick: if your instructions do not name one, ask a person.
        Read the version with read_sop_version first. A phase or milestone
        that does not exist yet is created in the same transaction; an
        existing ID must keep its owner and meaning. Only a job may replace
        its adoption, standing alone or under a booking, and it must name the
        current one. To keep a milestone and its judgments across a
        replacement, bind its existing ID and its phase's existing ID again;
        its title, criterion and phase name must be unchanged. Milestones the new
        adoption leaves out stay as history and are not marked done. Send
        the same id and binding IDs when you retry. Returns {"id": ...};
        read the result with read_work_sop.
        """
        identifier = parse_uuid(id)
        ledger.adopt_sop_version(
            identifier, work_kind, parse_uuid(work_id), parse_uuid(sop_version_id),
            reason, actor, parse_uuids(evidence_ids),
            parse_bindings(phase_bindings, 'phase_bindings', 'phase_id'),
            parse_bindings(milestone_bindings, 'milestone_bindings', 'milestone_id'),
            expected_previous_adoption_id=(parse_uuid(expected_previous_adoption_id)
                                           if expected_previous_adoption_id else None),
        )
        return {'id': str(identifier)}

    @tool()
    @serialized
    def read_sop_version(id: ReadId) -> dict:
        """Read one complete immutable SOP version by ID. An unknown ID is refused as not found."""
        return found(ledger.sop_version(parse_uuid(id)), 'SOP version', id)

    @tool()
    @serialized
    def list_sop_versions(
        tag: said(SopTagWords | None, 'Keep only versions with this tag. Omit for '
                  'both.') = None,
        status: said(SopStatusWords | None, 'Keep only versions in this state. Omit for '
                     'both.') = None,
    ) -> dict:
        """List every published SOP version, newest first, without the definition.

        The answer is {"versions": [...]}; none published gives an empty list.
        Each entry has id, name, version, tag, status (active or retired),
        based_on_version_id, actor and recorded_at. Nothing is derived:
        there is no default version. Read one version in full with
        read_sop_version.
        """
        return {'versions': ledger.sop_versions(tag, status)}

    @tool()
    @serialized
    def set_sop_version_status(id: NewId, sop_version_id: SopVersionId,
                               status: said(SopStatusWords, 'The new state.'),
                               reason: Reason,
                               actor: Actor, evidence_ids: EvidenceIds) -> dict:
        """Retire an SOP version, or make it active again, by appending a cited status row.

        evidence_ids name the message or instruction that called for the
        change. A retired version cannot be adopted by a new chain; chains
        already following it keep doing so. Nothing is edited: the latest
        row is the state.
        """
        return {'id': str(ledger.set_sop_version_status(
            parse_uuid(id), parse_uuid(sop_version_id), status, reason, actor,
            parse_uuids(evidence_ids)))}

    @tool()
    @serialized
    def read_work_sop(work_id: WorkId, include_evidence: IncludeEvidence = False) -> dict:
        """Read which milestones of one quote, booking or job its current SOP adoption covers.

        current_adoption holds the adopted version with its phases and
        milestones, or null when the work follows no SOP.
        historical_removed_milestones are those an earlier adoption had and
        the current one dropped. unadopted_milestones are those no adoption
        ever named. Each milestone carries its latest judgment.
        An unknown work ID is refused as not found.
        """
        return found(ledger.work_sop(parse_uuid(work_id), include_evidence=include_evidence),
                     'work', work_id)

    @tool()
    @serialized
    def read_sop_adoption(id: ReadId, include_evidence: IncludeEvidence = False) -> dict:
        """Read one SOP adoption, old or current: its fixed phases and milestones.

        Judgments are shown as they stand now, so this is not a view of the past.
        An unknown ID is refused as not found.
        """
        return found(ledger.sop_adoption(parse_uuid(id), include_evidence=include_evidence),
                     'SOP adoption', id)

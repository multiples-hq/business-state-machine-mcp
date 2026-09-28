"""MCP tools for the documents a job needs: requirements, versions, assessments."""

from mcp_params import (Actor, BeforePosition, EvidenceIds, JobId, MediaType, NewId,
                        OutcomeWords, PageLimit, Sha256, said)
from mcp_support import parse_uuid, parse_uuids

SubmissionId = said(str, 'UUID of one document version, the id given to submit_document.')


def register_document_tools(tool, serialized, ledger):
    @tool()
    @serialized
    def create_document_requirement(
        id: NewId, job_id: JobId,
        title: said(str, 'Short name of the document the job needs. Must not be empty.'),
        actor: Actor,
        milestone_id: said(str | None, 'UUID of a milestone on the same job that this '
                           'document is needed for. Omit when none.') = None,
        description: said(str | None, 'What the document must contain or show, in words.') = None,
    ) -> dict:
        """Say that a job needs a document, optionally for one milestone of the same job.

        Only jobs carry document requirements. Files are added to it with
        submit_document. Returns {"id": ...}.
        """
        return {'id': str(ledger.create_document_requirement(
            parse_uuid(id), parse_uuid(job_id), title, actor,
            milestone_id=parse_uuid(milestone_id) if milestone_id else None,
            description=description,
        ))}

    @tool()
    @serialized
    def submit_document(
        id: NewId,
        requirement_id: said(str, 'UUID of the document requirement this file answers.'),
        sha256: Sha256, media_type: MediaType, actor: Actor,
        replaces_submission_id: said(str | None, 'UUID of the current latest version of this '
                                     'requirement. Omit for the first version; required for '
                                     'every later one.') = None,
    ) -> dict:
        """Add a stored file as the next version of a required document.

        Store the bytes first with put_file or record_file_by_hash. A new
        version starts with no assessment.
        """
        return ledger.submit_document(
            parse_uuid(id), parse_uuid(requirement_id), sha256, media_type, actor,
            replaces_submission_id=(
                parse_uuid(replaces_submission_id) if replaces_submission_id else None
            ),
        )

    @tool()
    @serialized
    def assess_document(id: NewId, submission_id: SubmissionId,
                        outcome: said(OutcomeWords, 'Your assessment of this version.'),
                        reason: said(str, 'Why, in words. Must not be empty.'),
                        actor: Actor, evidence_ids: EvidenceIds) -> dict:
        """Record that one document version is accepted or rejected, with a reason and evidence.

        Assessments are appended; the latest one is the version's status.
        """
        return ledger.append_document_assessment(
            parse_uuid(id), parse_uuid(submission_id), outcome, reason, actor,
            parse_uuids(evidence_ids),
        )

    @tool()
    @serialized
    def read_documents(job_id: JobId) -> dict:
        """Read a job's document requirements, every version and each version's latest assessment.

        The answer is {"requirements": [...]}; a job with none gives an empty list.
        An unknown job ID is refused as not found.
        """
        ledger.require_row('job', parse_uuid(job_id))
        return {'requirements': ledger.documents(parse_uuid(job_id))}

    @tool()
    @serialized
    def read_document_assessments(submission_id: SubmissionId, limit: PageLimit = 50,
                                  before_position: BeforePosition = None) -> dict:
        """Read every assessment of one document version, newest first.

        The answer is {"assessments": [...]}; none yet gives an empty list.
        An unknown submission ID is refused as not found.
        """
        ledger.require_row('document version', parse_uuid(submission_id))
        return {'assessments': ledger.document_assessment_history(
            parse_uuid(submission_id), limit, before_position,
        )}

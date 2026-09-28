"""MCP tools that store file bytes and read them back by SHA-256."""

import base64

from mcp_params import Actor, MediaType, Sha256, said
from mcp_support import parse_uuid

FileEvidenceId = said(str, 'UUID you generate for the evidence row that names this file. Retry '
                           'with the same id and bytes; different bytes are refused.')


def register_file_tools(tool, serialized, ledger):
    @tool()
    @serialized
    def put_file(evidence_id: FileEvidenceId,
                 contents_base64: said(str, 'The file bytes, base64-encoded. At most 8 MiB '
                                       'after decoding.'),
                 media_type: MediaType, actor: Actor) -> dict:
        """Store a file's bytes, at most 8 MiB, and record an evidence row that names them.

        Use it for a file that reached you as bytes, such as an attachment.
        Returns sha256, byte_size and evidence_id. Cite the evidence_id, or
        list the sha256 in record_evidence attachments. The new row is not
        linked to any work until you link it with link_evidence_work. If the
        call fails part way, call it again unchanged: that completes the store.
        """
        try:
            contents = base64.b64decode(contents_base64, validate=True)
        except ValueError as error:
            raise ValueError('contents_base64 must be valid base64') from error
        planned = ledger.plan_file(contents)
        ledger.record_evidence_before_file(
            parse_uuid(evidence_id), planned['sha256'], media_type, planned['byte_size'], actor,
        )
        stored = ledger.put_file(contents)
        return {**stored, 'evidence_id': evidence_id}

    @tool()
    @serialized
    def record_file_by_hash(evidence_id: FileEvidenceId, sha256: Sha256,
                            media_type: MediaType, actor: Actor) -> dict:
        """Record a file whose bytes another program left in the drop directory.

        The twin of put_file, with the same answer: the bytes never pass
        through this call. The drop file named by this SHA-256 is read and
        re-hashed first, so a name that is not there, or bytes that do not
        match their name, is refused and no row is written. If the call
        fails part way, call it again unchanged: that completes the store.
        """
        planned = ledger.plan_dropped_file(sha256)
        ledger.record_evidence_before_file(
            parse_uuid(evidence_id), planned['sha256'], media_type, planned['byte_size'], actor,
        )
        stored = ledger.put_file(planned['bytes'])
        return {**stored, 'evidence_id': evidence_id}

    @tool()
    @serialized
    def read_file(sha256: Sha256) -> dict:
        """Verify and return at most 8 MiB of file bytes by SHA-256, base64-encoded in "bytes".

        A hash that an evidence row names but whose bytes are not on disk yet
        returns {"sha256": ..., "stored": false} instead of failing. A hash with
        neither a row nor bytes still fails as an unavailable file.
        """
        result = ledger.read_file_if_stored(sha256)
        if result is None:
            return {'sha256': sha256, 'stored': False}
        return {**result, 'bytes': base64.b64encode(result['bytes']).decode('ascii')}

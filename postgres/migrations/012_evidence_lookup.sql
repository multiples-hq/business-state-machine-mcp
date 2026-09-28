-- File bytes are already deduplicated by content hash. Evidence rows are not.
-- An email body is plain text on the row with no hash, and an attachment hash
-- sits inside a JSON column with no index, so an agent polling a mailbox cannot
-- cheaply ask "have I recorded this already?" and records it again.
--
-- This migration adds the three ways to ask. Nothing here refuses a duplicate:
-- two mailboxes can legitimately hold the same message. It only makes the
-- question cheap, so a skill can look first and cite the row that already exists.

-- The database computes the digest, so MCP calls, scripts and backfills cannot
-- disagree about it. STRICT means a row with no payload keeps a null digest.
CREATE FUNCTION spine.payload_digest(p_payload text) RETURNS text
LANGUAGE sql IMMUTABLE STRICT PARALLEL SAFE SET search_path = pg_catalog AS $$
    SELECT encode(sha256(convert_to(p_payload, 'UTF8')), 'hex')
$$;

-- A generated column fills itself and changes no existing column. The
-- append-only trigger is untouched: an ALTER TABLE rewrite is not an UPDATE.
ALTER TABLE spine.evidence
    ADD COLUMN payload_sha256 text
    GENERATED ALWAYS AS (spine.payload_digest(original_payload)) STORED;

CREATE INDEX ON spine.evidence (payload_sha256);

-- jsonb_path_ops indexes containment only, which is the single question asked
-- of attachments: attachments @> '[{"sha256": "..."}]'.
CREATE INDEX ON spine.evidence USING gin (attachments jsonb_path_ops);

-- A locator is matched exactly, byte for byte. Nothing is normalized here.
CREATE INDEX ON spine.evidence (source_locator);

GRANT EXECUTE ON FUNCTION spine.payload_digest(text) TO PUBLIC;

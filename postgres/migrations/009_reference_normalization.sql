-- Outside numbers arrive with dashes, spaces and mixed case. Matching stays
-- exact, but exact on one normalized form: letters and digits, lowercased.
-- The database computes the key, so callers, scripts and backfills agree.
CREATE FUNCTION spine.normalize_reference(p_value text) RETURNS text
LANGUAGE sql IMMUTABLE STRICT PARALLEL SAFE SET search_path = pg_catalog AS $$
    SELECT regexp_replace(lower(p_value), '[^a-z0-9]', '', 'g')
$$;

-- The key is stored beside the original text, which is never altered. Adding a
-- generated column changes no existing column and fires no append-only trigger.
ALTER TABLE spine.external_references
    ADD COLUMN normalized_value text
    GENERATED ALWAYS AS (spine.normalize_reference(value)) STORED;

CREATE INDEX ON spine.external_references (normalized_value, reference_type, source);
GRANT EXECUTE ON FUNCTION spine.normalize_reference(text) TO PUBLIC;

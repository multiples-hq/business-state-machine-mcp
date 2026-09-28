-- Run once as the database owner on an empty database.
CREATE SCHEMA spine;
REVOKE ALL ON SCHEMA spine FROM PUBLIC;
GRANT USAGE ON SCHEMA spine TO PUBLIC;

CREATE TABLE spine.jobs (
    id uuid PRIMARY KEY,
    title text NOT NULL CHECK (length(btrim(title)) > 0),
    actor text NOT NULL CHECK (length(btrim(actor)) > 0),
    recorded_at timestamptz NOT NULL DEFAULT clock_timestamp()
);

CREATE TABLE spine.milestones (
    id uuid PRIMARY KEY,
    job_id uuid NOT NULL REFERENCES spine.jobs,
    title text NOT NULL CHECK (length(btrim(title)) > 0),
    actor text NOT NULL CHECK (length(btrim(actor)) > 0),
    recorded_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
CREATE INDEX ON spine.milestones (job_id);

CREATE TABLE spine.evidence (
    id uuid PRIMARY KEY,
    original_payload text,
    attachments jsonb NOT NULL CHECK (jsonb_typeof(attachments) = 'array'),
    source_locator text,
    source_at timestamptz,
    actor text NOT NULL CHECK (length(btrim(actor)) > 0),
    recorded_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CHECK (coalesce(length(original_payload), 0) > 0 OR jsonb_array_length(attachments) > 0)
);

CREATE TABLE spine.judgments (
    id uuid PRIMARY KEY,
    milestone_id uuid NOT NULL REFERENCES spine.milestones,
    position bigint NOT NULL CHECK (position > 0),
    status text NOT NULL CHECK (status IN ('done', 'pending', 'blocked', 'failed')),
    explanation text NOT NULL CHECK (length(btrim(explanation)) > 0),
    actor text NOT NULL CHECK (length(btrim(actor)) > 0),
    recorded_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    UNIQUE (milestone_id, position)
);

CREATE TABLE spine.citations (
    judgment_id uuid NOT NULL REFERENCES spine.judgments,
    evidence_id uuid NOT NULL REFERENCES spine.evidence,
    PRIMARY KEY (judgment_id, evidence_id)
);

CREATE FUNCTION spine.refuse_mutation() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'ledger records are append-only' USING ERRCODE = '55000';
END;
$$;
DO $$
DECLARE table_name text;
BEGIN
    FOREACH table_name IN ARRAY ARRAY['jobs','milestones','evidence','judgments','citations'] LOOP
        EXECUTE format(
            'CREATE TRIGGER append_only BEFORE UPDATE OR DELETE OR TRUNCATE ON spine.%I '
            'FOR EACH STATEMENT EXECUTE FUNCTION spine.refuse_mutation()', table_name);
    END LOOP;
END;
$$;

CREATE VIEW spine.judgment_details AS
SELECT j.id, j.milestone_id, j.position,
       to_jsonb(j) || jsonb_build_object('evidence', (
           SELECT jsonb_agg(to_jsonb(e) ORDER BY e.id)
           FROM spine.citations c JOIN spine.evidence e ON e.id = c.evidence_id
           WHERE c.judgment_id = j.id
       )) AS document
FROM spine.judgments j;

-- Ordinary connections can read tables, but append only through these functions.
-- The owner is reserved for schema installation and administration.
REVOKE ALL ON ALL TABLES IN SCHEMA spine FROM PUBLIC;
GRANT SELECT ON ALL TABLES IN SCHEMA spine TO PUBLIC;

CREATE FUNCTION spine.create_job(p_id uuid, p_title text, p_actor text)
RETURNS uuid LANGUAGE sql SECURITY DEFINER SET search_path = pg_catalog AS $$
    INSERT INTO spine.jobs (id, title, actor) VALUES (p_id, p_title, p_actor) RETURNING id;
$$;

CREATE FUNCTION spine.create_milestone(p_id uuid, p_job uuid, p_title text, p_actor text)
RETURNS uuid LANGUAGE sql SECURITY DEFINER SET search_path = pg_catalog AS $$
    INSERT INTO spine.milestones (id, job_id, title, actor)
    VALUES (p_id, p_job, p_title, p_actor) RETURNING id;
$$;

-- File bytes are checked by the access module before this function is called.
CREATE FUNCTION spine.record_evidence(
    p_id uuid, p_payload text, p_attachments jsonb, p_locator text,
    p_source_at timestamptz, p_actor text
) RETURNS uuid LANGUAGE sql SECURITY DEFINER SET search_path = pg_catalog AS $$
    INSERT INTO spine.evidence (id, original_payload, attachments, source_locator, source_at, actor)
    VALUES (p_id, p_payload, p_attachments, p_locator, p_source_at, p_actor) RETURNING id;
$$;

CREATE FUNCTION spine.append_judgment(
    p_id uuid, p_milestone uuid, p_status text, p_explanation text,
    p_actor text, p_citations uuid[]
) RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog AS $$
DECLARE
    existing spine.judgments;
    cited uuid[];
    existing_cited uuid[];
    next_position bigint;
BEGIN
    IF p_citations IS NULL OR cardinality(p_citations) = 0
       OR array_position(p_citations, NULL) IS NOT NULL THEN
        RAISE EXCEPTION 'a judgment requires at least one evidence citation'
            USING ERRCODE = '23514';
    END IF;
    SELECT array_agg(DISTINCT item ORDER BY item) INTO cited FROM unnest(p_citations) item;

    -- Serialize retries by stable ID even when they name different milestones.
    PERFORM pg_advisory_xact_lock(hashtextextended(p_id::text, 0));
    SELECT * INTO existing FROM spine.judgments WHERE id = p_id;
    IF FOUND THEN
        SELECT array_agg(evidence_id ORDER BY evidence_id) INTO existing_cited
        FROM spine.citations WHERE judgment_id = p_id;
        IF existing.milestone_id IS DISTINCT FROM p_milestone
           OR existing.status IS DISTINCT FROM p_status
           OR existing.explanation IS DISTINCT FROM p_explanation
           OR existing.actor IS DISTINCT FROM p_actor
           OR existing_cited IS DISTINCT FROM cited THEN
            RAISE EXCEPTION 'judgment ID already has different contents'
                USING ERRCODE = 'SP001';
        END IF;
        RETURN (SELECT document FROM spine.judgment_details WHERE id = p_id);
    END IF;

    PERFORM 1 FROM spine.milestones WHERE id = p_milestone FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'milestone does not exist' USING ERRCODE = '23503';
    END IF;
    SELECT coalesce(max(position), 0) + 1 INTO next_position
    FROM spine.judgments WHERE milestone_id = p_milestone;
    INSERT INTO spine.judgments (id, milestone_id, position, status, explanation, actor)
    VALUES (p_id, p_milestone, next_position, p_status, p_explanation, p_actor);
    INSERT INTO spine.citations (judgment_id, evidence_id)
    SELECT p_id, item FROM unnest(cited) item;
    RETURN (SELECT document FROM spine.judgment_details WHERE id = p_id);
END;
$$;

-- Add immutable document requirements, submissions and agent assessments.

CREATE TABLE spine.document_requirements (
    id uuid PRIMARY KEY,
    job_id uuid NOT NULL REFERENCES spine.jobs,
    milestone_id uuid REFERENCES spine.milestones,
    title text NOT NULL CHECK (length(btrim(title)) > 0),
    description text,
    actor text NOT NULL CHECK (length(btrim(actor)) > 0),
    recorded_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CHECK (description IS NULL OR length(btrim(description)) > 0)
);
CREATE INDEX ON spine.document_requirements (job_id, recorded_at, id);

CREATE TABLE spine.document_submissions (
    id uuid PRIMARY KEY,
    requirement_id uuid NOT NULL REFERENCES spine.document_requirements,
    version integer NOT NULL CHECK (version > 0),
    replaces_submission_id uuid REFERENCES spine.document_submissions,
    file_sha256 text NOT NULL CHECK (file_sha256 ~ '^[0-9a-f]{64}$'),
    media_type text NOT NULL CHECK (length(btrim(media_type)) > 0),
    byte_size bigint NOT NULL CHECK (byte_size >= 0),
    actor text NOT NULL CHECK (length(btrim(actor)) > 0),
    recorded_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    UNIQUE (requirement_id, version)
);
CREATE INDEX ON spine.document_submissions (requirement_id, version DESC);

CREATE TABLE spine.document_assessments (
    id uuid PRIMARY KEY,
    submission_id uuid NOT NULL REFERENCES spine.document_submissions,
    position bigint NOT NULL CHECK (position > 0),
    outcome text NOT NULL CHECK (outcome IN ('accepted', 'rejected')),
    reason text NOT NULL CHECK (length(btrim(reason)) > 0),
    actor text NOT NULL CHECK (length(btrim(actor)) > 0),
    recorded_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    UNIQUE (submission_id, position)
);

CREATE TABLE spine.document_assessment_citations (
    assessment_id uuid NOT NULL REFERENCES spine.document_assessments,
    evidence_id uuid NOT NULL REFERENCES spine.evidence,
    PRIMARY KEY (assessment_id, evidence_id)
);

DO $$
DECLARE table_name text;
BEGIN
    FOREACH table_name IN ARRAY ARRAY[
        'document_requirements', 'document_submissions',
        'document_assessments', 'document_assessment_citations'
    ] LOOP
        EXECUTE format(
            'CREATE TRIGGER append_only BEFORE UPDATE OR DELETE OR TRUNCATE ON spine.%I '
            'FOR EACH STATEMENT EXECUTE FUNCTION spine.refuse_mutation()', table_name);
    END LOOP;
END;
$$;

CREATE FUNCTION spine.create_document_requirement(
    p_id uuid, p_job uuid, p_milestone uuid, p_title text,
    p_description text, p_actor text
) RETURNS uuid LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog AS $$
DECLARE existing spine.document_requirements;
BEGIN
    PERFORM pg_advisory_xact_lock(hashtextextended(p_id::text, 0));
    SELECT * INTO existing FROM spine.document_requirements WHERE id = p_id;
    IF FOUND THEN
        IF existing.job_id IS DISTINCT FROM p_job OR existing.milestone_id IS DISTINCT FROM p_milestone
           OR existing.title IS DISTINCT FROM p_title OR existing.description IS DISTINCT FROM p_description
           OR existing.actor IS DISTINCT FROM p_actor THEN
            RAISE EXCEPTION 'requirement ID already has different contents' USING ERRCODE = 'SP004';
        END IF;
        RETURN p_id;
    END IF;
    IF p_milestone IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM spine.milestones WHERE id = p_milestone AND job_id = p_job
    ) THEN RAISE EXCEPTION 'requirement milestone must belong to the job' USING ERRCODE = '23503'; END IF;
    INSERT INTO spine.document_requirements (id, job_id, milestone_id, title, description, actor)
    VALUES (p_id, p_job, p_milestone, p_title, p_description, p_actor);
    RETURN p_id;
END;
$$;

CREATE FUNCTION spine.submit_document(
    p_id uuid, p_requirement uuid, p_replaces uuid, p_sha256 text,
    p_media_type text, p_byte_size bigint, p_actor text
) RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog AS $$
DECLARE existing spine.document_submissions; latest spine.document_submissions; next_version integer;
BEGIN
    PERFORM pg_advisory_xact_lock(hashtextextended(p_id::text, 0));
    SELECT * INTO existing FROM spine.document_submissions WHERE id = p_id;
    IF FOUND THEN
        IF existing.requirement_id IS DISTINCT FROM p_requirement
           OR existing.replaces_submission_id IS DISTINCT FROM p_replaces
           OR existing.file_sha256 IS DISTINCT FROM p_sha256 OR existing.media_type IS DISTINCT FROM p_media_type
           OR existing.byte_size IS DISTINCT FROM p_byte_size OR existing.actor IS DISTINCT FROM p_actor THEN
            RAISE EXCEPTION 'submission ID already has different contents' USING ERRCODE = 'SP004';
        END IF;
        RETURN to_jsonb(existing);
    END IF;
    PERFORM 1 FROM spine.document_requirements WHERE id = p_requirement FOR UPDATE;
    IF NOT FOUND THEN RAISE EXCEPTION 'document requirement does not exist' USING ERRCODE = '23503'; END IF;
    SELECT * INTO latest FROM spine.document_submissions
      WHERE requirement_id = p_requirement ORDER BY version DESC LIMIT 1;
    IF FOUND THEN
        IF p_replaces IS DISTINCT FROM latest.id THEN
            RAISE EXCEPTION 'a new version must replace the current submission' USING ERRCODE = '23514';
        END IF;
        next_version := latest.version + 1;
    ELSE
        IF p_replaces IS NOT NULL THEN
            RAISE EXCEPTION 'the first submission cannot replace another submission' USING ERRCODE = '23514';
        END IF;
        next_version := 1;
    END IF;
    INSERT INTO spine.document_submissions (
        id, requirement_id, version, replaces_submission_id,
        file_sha256, media_type, byte_size, actor
    ) VALUES (p_id, p_requirement, next_version, p_replaces,
        p_sha256, p_media_type, p_byte_size, p_actor) RETURNING * INTO existing;
    RETURN to_jsonb(existing);
END;
$$;

CREATE FUNCTION spine.append_document_assessment(
    p_id uuid, p_submission uuid, p_outcome text, p_reason text,
    p_actor text, p_evidence uuid[]
) RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog AS $$
DECLARE
    existing spine.document_assessments; cited uuid[]; old_cited uuid[]; next_position bigint;
BEGIN
    IF p_evidence IS NULL OR cardinality(p_evidence) = 0 OR array_position(p_evidence, NULL) IS NOT NULL THEN
        RAISE EXCEPTION 'a document assessment requires evidence' USING ERRCODE = '23514';
    END IF;
    SELECT array_agg(DISTINCT x ORDER BY x) INTO cited FROM unnest(p_evidence) x;
    PERFORM pg_advisory_xact_lock(hashtextextended(p_id::text, 0));
    SELECT * INTO existing FROM spine.document_assessments WHERE id = p_id;
    IF FOUND THEN
        SELECT array_agg(evidence_id ORDER BY evidence_id) INTO old_cited
          FROM spine.document_assessment_citations WHERE assessment_id = p_id;
        IF existing.submission_id IS DISTINCT FROM p_submission OR existing.outcome IS DISTINCT FROM p_outcome
           OR existing.reason IS DISTINCT FROM p_reason OR existing.actor IS DISTINCT FROM p_actor
           OR old_cited IS DISTINCT FROM cited THEN
            RAISE EXCEPTION 'assessment ID already has different contents' USING ERRCODE = 'SP004';
        END IF;
    ELSE
        PERFORM 1 FROM spine.document_submissions WHERE id = p_submission FOR UPDATE;
        IF NOT FOUND THEN RAISE EXCEPTION 'document submission does not exist' USING ERRCODE = '23503'; END IF;
        SELECT coalesce(max(position), 0) + 1 INTO next_position
          FROM spine.document_assessments WHERE submission_id = p_submission;
        INSERT INTO spine.document_assessments (id, submission_id, position, outcome, reason, actor)
        VALUES (p_id, p_submission, next_position, p_outcome, p_reason, p_actor) RETURNING * INTO existing;
        INSERT INTO spine.document_assessment_citations SELECT p_id, x FROM unnest(cited) x;
    END IF;
    RETURN to_jsonb(existing) || jsonb_build_object('evidence_ids', to_jsonb(cited));
END;
$$;

REVOKE ALL ON spine.document_requirements, spine.document_submissions,
    spine.document_assessments, spine.document_assessment_citations FROM PUBLIC;
GRANT SELECT ON spine.document_requirements, spine.document_submissions,
    spine.document_assessments, spine.document_assessment_citations TO PUBLIC;
GRANT EXECUTE ON FUNCTION spine.create_document_requirement(uuid, uuid, uuid, text, text, text),
    spine.submit_document(uuid, uuid, uuid, text, text, bigint, text),
    spine.append_document_assessment(uuid, uuid, text, text, text, uuid[]) TO PUBLIC;

-- Immutable SOP versions and explicit, cited adoption membership for one work owner.
-- The ledger records adoption. It does not authenticate approval or evaluate criteria.

CREATE TABLE spine.sop_versions (
    id uuid PRIMARY KEY,
    name text NOT NULL CHECK (length(btrim(name)) > 0),
    version text NOT NULL CHECK (length(btrim(version)) > 0),
    tag text NOT NULL CHECK (tag IN ('standard', 'break_glass')),
    based_on_version_id uuid REFERENCES spine.sop_versions,
    definition jsonb NOT NULL CHECK (jsonb_typeof(definition) = 'object'),
    actor text NOT NULL CHECK (length(btrim(actor)) > 0),
    recorded_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    UNIQUE (name, version),
    CHECK (based_on_version_id IS NULL OR based_on_version_id <> id)
);

CREATE TABLE spine.sop_adoptions (
    id uuid PRIMARY KEY,
    quote_id uuid REFERENCES spine.quotes,
    booking_id uuid REFERENCES spine.bookings,
    job_id uuid REFERENCES spine.jobs,
    sop_version_id uuid NOT NULL REFERENCES spine.sop_versions,
    previous_adoption_id uuid UNIQUE REFERENCES spine.sop_adoptions,
    reason text NOT NULL CHECK (length(btrim(reason)) > 0),
    actor text NOT NULL CHECK (length(btrim(actor)) > 0),
    recorded_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CHECK (num_nonnulls(quote_id, booking_id, job_id) = 1),
    CHECK (previous_adoption_id IS NULL OR previous_adoption_id <> id)
);
CREATE INDEX ON spine.sop_adoptions (quote_id, recorded_at, id);
CREATE INDEX ON spine.sop_adoptions (booking_id, recorded_at, id);
CREATE INDEX ON spine.sop_adoptions (job_id, recorded_at, id);
CREATE UNIQUE INDEX one_initial_sop_adoption_per_quote
    ON spine.sop_adoptions (quote_id) WHERE quote_id IS NOT NULL AND previous_adoption_id IS NULL;
CREATE UNIQUE INDEX one_initial_sop_adoption_per_booking
    ON spine.sop_adoptions (booking_id) WHERE booking_id IS NOT NULL AND previous_adoption_id IS NULL;
CREATE UNIQUE INDEX one_initial_sop_adoption_per_job
    ON spine.sop_adoptions (job_id) WHERE job_id IS NOT NULL AND previous_adoption_id IS NULL;

CREATE TABLE spine.sop_adoption_citations (
    adoption_id uuid NOT NULL REFERENCES spine.sop_adoptions,
    evidence_id uuid NOT NULL REFERENCES spine.evidence,
    PRIMARY KEY (adoption_id, evidence_id)
);

CREATE TABLE spine.sop_adoption_phases (
    adoption_id uuid NOT NULL REFERENCES spine.sop_adoptions,
    phase_key text NOT NULL CHECK (length(btrim(phase_key)) > 0),
    phase_id uuid NOT NULL REFERENCES spine.phases,
    phase_name text NOT NULL CHECK (length(btrim(phase_name)) > 0),
    definition_order integer NOT NULL CHECK (definition_order >= 0),
    PRIMARY KEY (adoption_id, phase_key),
    UNIQUE (adoption_id, phase_id),
    UNIQUE (adoption_id, definition_order)
);

CREATE TABLE spine.sop_adoption_milestones (
    adoption_id uuid NOT NULL REFERENCES spine.sop_adoptions,
    phase_key text NOT NULL,
    milestone_key text NOT NULL CHECK (length(btrim(milestone_key)) > 0),
    milestone_id uuid NOT NULL REFERENCES spine.milestones,
    milestone_title text NOT NULL CHECK (length(btrim(milestone_title)) > 0),
    completion_criterion text NOT NULL CHECK (length(btrim(completion_criterion)) > 0),
    definition_order integer NOT NULL CHECK (definition_order >= 0),
    PRIMARY KEY (adoption_id, milestone_key),
    UNIQUE (adoption_id, milestone_id),
    UNIQUE (adoption_id, phase_key, definition_order),
    FOREIGN KEY (adoption_id, phase_key)
        REFERENCES spine.sop_adoption_phases (adoption_id, phase_key)
);
CREATE INDEX ON spine.sop_adoption_milestones (milestone_id);

DO $$
DECLARE table_name text;
BEGIN
    FOREACH table_name IN ARRAY ARRAY[
        'sop_versions', 'sop_adoptions', 'sop_adoption_citations',
        'sop_adoption_phases', 'sop_adoption_milestones'
    ] LOOP
        EXECUTE format(
            'CREATE TRIGGER append_only BEFORE UPDATE OR DELETE OR TRUNCATE ON spine.%I '
            'FOR EACH STATEMENT EXECUTE FUNCTION spine.refuse_mutation()', table_name);
    END LOOP;
END;
$$;

CREATE FUNCTION spine.validate_sop_definition(p_definition jsonb)
RETURNS void LANGUAGE plpgsql IMMUTABLE SET search_path = pg_catalog AS $$
DECLARE
    object_keys text[]; stage_keys text[]; seen_phase_keys text[]; seen_milestone_keys text[];
    seen_orders integer[]; stage_name text; stage jsonb; phase jsonb; milestone jsonb;
    phase_key text; milestone_key text; display_order integer;
BEGIN
    IF p_definition IS NULL OR jsonb_typeof(p_definition) <> 'object' THEN
        RAISE EXCEPTION 'SOP definition must be an object' USING ERRCODE = '23514';
    END IF;
    SELECT array_agg(k ORDER BY k) INTO object_keys FROM jsonb_object_keys(p_definition) k;
    IF object_keys IS DISTINCT FROM ARRAY['stages']::text[]
       OR jsonb_typeof(p_definition->'stages') <> 'object' THEN
        RAISE EXCEPTION 'SOP definition must contain only a stages object' USING ERRCODE = '23514';
    END IF;
    SELECT array_agg(k ORDER BY k) INTO stage_keys FROM jsonb_object_keys(p_definition->'stages') k;
    IF stage_keys IS DISTINCT FROM ARRAY['booking', 'job', 'quote']::text[] THEN
        RAISE EXCEPTION 'SOP definition requires exactly quote, booking and job stages'
            USING ERRCODE = '23514';
    END IF;

    FOREACH stage_name IN ARRAY ARRAY['quote', 'booking', 'job'] LOOP
        stage := p_definition->'stages'->stage_name;
        IF jsonb_typeof(stage) <> 'object' THEN
            RAISE EXCEPTION 'each SOP stage must be an object' USING ERRCODE = '23514';
        END IF;
        SELECT array_agg(k ORDER BY k) INTO object_keys FROM jsonb_object_keys(stage) k;
        IF object_keys IS DISTINCT FROM ARRAY['phases']::text[]
           OR jsonb_typeof(stage->'phases') <> 'array' THEN
            RAISE EXCEPTION 'each SOP stage must contain only a phases array'
                USING ERRCODE = '23514';
        END IF;
        seen_phase_keys := ARRAY[]::text[];
        seen_milestone_keys := ARRAY[]::text[];
        seen_orders := ARRAY[]::integer[];
        FOR phase IN SELECT value FROM jsonb_array_elements(stage->'phases') LOOP
            IF jsonb_typeof(phase) <> 'object' THEN
                RAISE EXCEPTION 'each SOP phase must be an object' USING ERRCODE = '23514';
            END IF;
            SELECT array_agg(k ORDER BY k) INTO object_keys FROM jsonb_object_keys(phase) k;
            IF object_keys IS DISTINCT FROM ARRAY['display_order', 'key', 'milestones', 'name']::text[]
               OR jsonb_typeof(phase->'key') <> 'string'
               OR jsonb_typeof(phase->'name') <> 'string'
               OR jsonb_typeof(phase->'display_order') <> 'number'
               OR jsonb_typeof(phase->'milestones') <> 'array'
               OR length(btrim(phase->>'key')) = 0 OR length(btrim(phase->>'name')) = 0
               OR (phase->>'display_order') !~ '^[0-9]+$' THEN
                RAISE EXCEPTION 'each SOP phase needs key, name, nonnegative integer display_order and milestones'
                    USING ERRCODE = '23514';
            END IF;
            phase_key := phase->>'key';
            display_order := (phase->>'display_order')::integer;
            IF phase_key = ANY(seen_phase_keys) OR display_order = ANY(seen_orders) THEN
                RAISE EXCEPTION 'SOP phase keys and display orders must be unique within a stage'
                    USING ERRCODE = '23514';
            END IF;
            seen_phase_keys := array_append(seen_phase_keys, phase_key);
            seen_orders := array_append(seen_orders, display_order);
            FOR milestone IN SELECT value FROM jsonb_array_elements(phase->'milestones') LOOP
                IF jsonb_typeof(milestone) <> 'object' THEN
                    RAISE EXCEPTION 'each SOP milestone must be an object' USING ERRCODE = '23514';
                END IF;
                SELECT array_agg(k ORDER BY k) INTO object_keys FROM jsonb_object_keys(milestone) k;
                IF object_keys IS DISTINCT FROM ARRAY['criterion', 'key', 'title']::text[]
                   OR jsonb_typeof(milestone->'key') <> 'string'
                   OR jsonb_typeof(milestone->'title') <> 'string'
                   OR jsonb_typeof(milestone->'criterion') <> 'string'
                   OR length(btrim(milestone->>'key')) = 0
                   OR length(btrim(milestone->>'title')) = 0
                   OR length(btrim(milestone->>'criterion')) = 0 THEN
                    RAISE EXCEPTION 'each SOP milestone needs nonempty key, title and criterion'
                        USING ERRCODE = '23514';
                END IF;
                milestone_key := milestone->>'key';
                IF milestone_key = ANY(seen_milestone_keys) THEN
                    RAISE EXCEPTION 'SOP milestone keys must be unique within a stage'
                        USING ERRCODE = '23514';
                END IF;
                seen_milestone_keys := array_append(seen_milestone_keys, milestone_key);
            END LOOP;
        END LOOP;
    END LOOP;
END;
$$;

CREATE FUNCTION spine.publish_sop_version(
    p_id uuid, p_name text, p_version text, p_tag text, p_definition jsonb,
    p_based_on uuid, p_actor text
) RETURNS uuid LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog AS $$
DECLARE existing spine.sop_versions;
BEGIN
    PERFORM pg_advisory_xact_lock(hashtextextended(p_id::text, 0));
    SELECT * INTO existing FROM spine.sop_versions WHERE id = p_id;
    IF FOUND THEN
        IF existing.name IS DISTINCT FROM p_name OR existing.version IS DISTINCT FROM p_version
           OR existing.tag IS DISTINCT FROM p_tag OR existing.definition IS DISTINCT FROM p_definition
           OR existing.based_on_version_id IS DISTINCT FROM p_based_on
           OR existing.actor IS DISTINCT FROM p_actor THEN
            RAISE EXCEPTION 'SOP version ID already has different contents' USING ERRCODE = 'SP006';
        END IF;
        RETURN p_id;
    END IF;
    PERFORM spine.validate_sop_definition(p_definition);
    INSERT INTO spine.sop_versions (id, name, version, tag, definition, based_on_version_id, actor)
    VALUES (p_id, p_name, p_version, p_tag, p_definition, p_based_on, p_actor);
    RETURN p_id;
END;
$$;

REVOKE ALL ON spine.sop_versions, spine.sop_adoptions, spine.sop_adoption_citations,
    spine.sop_adoption_phases, spine.sop_adoption_milestones FROM PUBLIC;
GRANT SELECT ON spine.sop_versions, spine.sop_adoptions, spine.sop_adoption_citations,
    spine.sop_adoption_phases, spine.sop_adoption_milestones TO PUBLIC;
GRANT EXECUTE ON FUNCTION
    spine.publish_sop_version(uuid, text, text, text, jsonb, uuid, text)
TO PUBLIC;

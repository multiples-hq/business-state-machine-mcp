-- Atomically adopt an immutable SOP version for one quote, booking or job.
-- Migration 006 creates and protects the referenced SOP tables.

CREATE FUNCTION spine.adopt_sop_version(
    p_id uuid, p_quote uuid, p_booking uuid, p_job uuid, p_sop_version uuid,
    p_expected_previous uuid, p_reason text, p_actor text, p_evidence uuid[],
    p_phase_bindings jsonb, p_milestone_bindings jsonb
) RETURNS uuid LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog AS $$
DECLARE
    existing spine.sop_adoptions; version_row spine.sop_versions; phase_row spine.phases;
    milestone_row spine.milestones; phase_assignment uuid; current_adoption uuid;
    work_owner uuid; work_kind text; stage jsonb; phase_def jsonb; milestone_def jsonb;
    binding jsonb; object_keys text[]; cited uuid[]; old_cited uuid[];
    normalized_phases jsonb; normalized_milestones jsonb; old_phases jsonb; old_milestones jsonb;
    selected_phase_id uuid; selected_milestone_id uuid; bound_phase_id uuid;
    physical_order integer; first_unique_count integer; second_unique_count integer;
    selected_phase_key text; selected_milestone_key text; selected_phase_name text;
    selected_milestone_title text; selected_criterion text;
    selected_definition_order integer; ordinal bigint; definition_count integer; binding_count integer;
BEGIN
    IF p_evidence IS NULL OR cardinality(p_evidence) = 0 OR array_position(p_evidence, NULL) IS NOT NULL THEN
        RAISE EXCEPTION 'an SOP adoption requires at least one evidence citation' USING ERRCODE = '23514';
    END IF;
    IF p_phase_bindings IS NULL OR jsonb_typeof(p_phase_bindings) <> 'array'
       OR p_milestone_bindings IS NULL OR jsonb_typeof(p_milestone_bindings) <> 'array' THEN
        RAISE EXCEPTION 'SOP phase and milestone bindings must be arrays' USING ERRCODE = '23514';
    END IF;
    SELECT array_agg(DISTINCT x ORDER BY x) INTO cited FROM unnest(p_evidence) x;
    work_owner := spine.require_work_owner(p_quote, p_booking, p_job);
    work_kind := CASE WHEN p_quote IS NOT NULL THEN 'quote'
                      WHEN p_booking IS NOT NULL THEN 'booking' ELSE 'job' END;

    FOR binding IN SELECT value FROM jsonb_array_elements(p_phase_bindings) LOOP
        IF jsonb_typeof(binding) <> 'object' THEN
            RAISE EXCEPTION 'each phase binding must be an object' USING ERRCODE = '23514';
        END IF;
        SELECT array_agg(k ORDER BY k) INTO object_keys FROM jsonb_object_keys(binding) k;
        IF object_keys IS DISTINCT FROM ARRAY['phase_id', 'phase_key']::text[]
           OR jsonb_typeof(binding->'phase_id') <> 'string'
           OR jsonb_typeof(binding->'phase_key') <> 'string'
           OR length(btrim(binding->>'phase_key')) = 0 THEN
            RAISE EXCEPTION 'each phase binding needs phase_key and phase_id'
                USING ERRCODE = '23514';
        END IF;
        PERFORM (binding->>'phase_id')::uuid;
    END LOOP;
    FOR binding IN SELECT value FROM jsonb_array_elements(p_milestone_bindings) LOOP
        IF jsonb_typeof(binding) <> 'object' THEN
            RAISE EXCEPTION 'each milestone binding must be an object' USING ERRCODE = '23514';
        END IF;
        SELECT array_agg(k ORDER BY k) INTO object_keys FROM jsonb_object_keys(binding) k;
        IF object_keys IS DISTINCT FROM ARRAY['milestone_id', 'milestone_key', 'phase_key']::text[]
           OR jsonb_typeof(binding->'milestone_id') <> 'string'
           OR jsonb_typeof(binding->'milestone_key') <> 'string'
           OR jsonb_typeof(binding->'phase_key') <> 'string'
           OR length(btrim(binding->>'phase_key')) = 0
           OR length(btrim(binding->>'milestone_key')) = 0 THEN
            RAISE EXCEPTION 'each milestone binding needs phase_key, milestone_key and milestone_id'
                USING ERRCODE = '23514';
        END IF;
        PERFORM (binding->>'milestone_id')::uuid;
    END LOOP;
    SELECT coalesce(jsonb_agg(jsonb_build_object(
        'phase_key', value->>'phase_key',
        'phase_id', ((value->>'phase_id')::uuid)::text
    ) ORDER BY value->>'phase_key'), '[]'::jsonb)
      INTO normalized_phases FROM jsonb_array_elements(p_phase_bindings);
    SELECT coalesce(jsonb_agg(jsonb_build_object(
        'phase_key', value->>'phase_key',
        'milestone_key', value->>'milestone_key',
        'milestone_id', ((value->>'milestone_id')::uuid)::text
    ) ORDER BY value->>'phase_key', value->>'milestone_key'), '[]'::jsonb)
      INTO normalized_milestones FROM jsonb_array_elements(p_milestone_bindings);

    -- One owner lock serializes current-adoption checks and physical phase allocation.
    PERFORM pg_advisory_xact_lock(hashtextextended('sop-owner:' || work_owner::text, 0));
    PERFORM pg_advisory_xact_lock(hashtextextended(p_id::text, 0));
    SELECT * INTO existing FROM spine.sop_adoptions WHERE id = p_id;
    IF FOUND THEN
        SELECT array_agg(evidence_id ORDER BY evidence_id) INTO old_cited
          FROM spine.sop_adoption_citations WHERE adoption_id = p_id;
        SELECT coalesce(jsonb_agg(jsonb_build_object(
            'phase_key', ap.phase_key, 'phase_id', ap.phase_id::text)
            ORDER BY ap.phase_key), '[]'::jsonb)
          INTO old_phases FROM spine.sop_adoption_phases ap WHERE ap.adoption_id = p_id;
        SELECT coalesce(jsonb_agg(jsonb_build_object(
            'phase_key', am.phase_key, 'milestone_key', am.milestone_key,
            'milestone_id', am.milestone_id::text) ORDER BY am.phase_key, am.milestone_key), '[]'::jsonb)
          INTO old_milestones FROM spine.sop_adoption_milestones am WHERE am.adoption_id = p_id;
        IF existing.quote_id IS DISTINCT FROM p_quote OR existing.booking_id IS DISTINCT FROM p_booking
           OR existing.job_id IS DISTINCT FROM p_job OR existing.sop_version_id IS DISTINCT FROM p_sop_version
           OR existing.previous_adoption_id IS DISTINCT FROM p_expected_previous
           OR existing.reason IS DISTINCT FROM p_reason OR existing.actor IS DISTINCT FROM p_actor
           OR old_cited IS DISTINCT FROM cited OR old_phases IS DISTINCT FROM normalized_phases
           OR old_milestones IS DISTINCT FROM normalized_milestones THEN
            RAISE EXCEPTION 'SOP adoption ID already has different contents' USING ERRCODE = 'SP007';
        END IF;
        RETURN p_id;
    END IF;

    SELECT a.id INTO current_adoption FROM spine.sop_adoptions a
    WHERE coalesce(a.quote_id, a.booking_id, a.job_id) = work_owner
      AND NOT EXISTS (SELECT 1 FROM spine.sop_adoptions newer WHERE newer.previous_adoption_id = a.id);
    IF current_adoption IS DISTINCT FROM p_expected_previous THEN
        RAISE EXCEPTION 'expected previous SOP adoption is stale' USING ERRCODE = 'SP007';
    END IF;
    SELECT * INTO version_row FROM spine.sop_versions WHERE id = p_sop_version;
    IF NOT FOUND THEN RAISE EXCEPTION 'SOP version does not exist' USING ERRCODE = '23503'; END IF;
    stage := version_row.definition->'stages'->work_kind;

    SELECT count(*) INTO definition_count FROM jsonb_array_elements(stage->'phases');
    SELECT count(*), count(DISTINCT value->>'phase_key'),
           count(DISTINCT (value->>'phase_id')::uuid)
      INTO binding_count, first_unique_count, second_unique_count FROM jsonb_array_elements(p_phase_bindings);
    IF binding_count <> definition_count OR first_unique_count <> binding_count
       OR second_unique_count <> binding_count
       OR EXISTS (
           SELECT 1 FROM jsonb_array_elements(p_phase_bindings) b
           WHERE NOT EXISTS (SELECT 1 FROM jsonb_array_elements(stage->'phases') p
                             WHERE p->>'key' = b->>'phase_key')
       ) THEN
        RAISE EXCEPTION 'phase bindings must cover the SOP stage exactly once'
            USING ERRCODE = '23514';
    END IF;

    SELECT count(*) INTO definition_count FROM jsonb_array_elements(stage->'phases') p,
        LATERAL jsonb_array_elements(p->'milestones') m;
    SELECT count(*), count(DISTINCT value->>'milestone_key'),
           count(DISTINCT (value->>'milestone_id')::uuid)
      INTO binding_count, first_unique_count, second_unique_count FROM jsonb_array_elements(p_milestone_bindings);
    IF binding_count <> definition_count OR first_unique_count <> binding_count
       OR second_unique_count <> binding_count
       OR EXISTS (
           SELECT 1 FROM jsonb_array_elements(p_milestone_bindings) b
           WHERE NOT EXISTS (
               SELECT 1 FROM jsonb_array_elements(stage->'phases') p,
                   LATERAL jsonb_array_elements(p->'milestones') m
               WHERE p->>'key' = b->>'phase_key' AND m->>'key' = b->>'milestone_key'
           )
       ) THEN
        RAISE EXCEPTION 'milestone bindings must cover the SOP stage exactly once'
            USING ERRCODE = '23514';
    END IF;

    INSERT INTO spine.sop_adoptions (
        id, quote_id, booking_id, job_id, sop_version_id, previous_adoption_id, reason, actor
    ) VALUES (p_id, p_quote, p_booking, p_job, p_sop_version, p_expected_previous, p_reason, p_actor);
    INSERT INTO spine.sop_adoption_citations SELECT p_id, x FROM unnest(cited) x;

    FOR phase_def IN SELECT value FROM jsonb_array_elements(stage->'phases') LOOP
        selected_phase_key := phase_def->>'key';
        selected_phase_name := phase_def->>'name';
        selected_definition_order := (phase_def->>'display_order')::integer;
        SELECT (value->>'phase_id')::uuid INTO selected_phase_id
          FROM jsonb_array_elements(p_phase_bindings)
         WHERE value->>'phase_key' = selected_phase_key;
        SELECT * INTO phase_row FROM spine.phases WHERE id = selected_phase_id;
        IF FOUND THEN
            IF coalesce(phase_row.quote_id, phase_row.booking_id, phase_row.job_id) <> work_owner
               OR phase_row.name <> selected_phase_name THEN
                RAISE EXCEPTION 'bound phase owner or name does not match the SOP definition'
                    USING ERRCODE = '23514';
            END IF;
        ELSE
            SELECT coalesce(max(display_order), -1) + 1 INTO physical_order FROM spine.phases
             WHERE coalesce(quote_id, booking_id, job_id) = work_owner;
            INSERT INTO spine.phases (id, quote_id, booking_id, job_id, name, display_order, actor)
            VALUES (selected_phase_id, p_quote, p_booking, p_job,
                    selected_phase_name, physical_order, p_actor);
        END IF;
        INSERT INTO spine.sop_adoption_phases (
            adoption_id, phase_key, phase_id, phase_name, definition_order
        ) VALUES (p_id, selected_phase_key, selected_phase_id,
                  selected_phase_name, selected_definition_order);
    END LOOP;

    FOR phase_def IN SELECT value FROM jsonb_array_elements(stage->'phases') LOOP
        selected_phase_key := phase_def->>'key';
        SELECT ap.phase_id INTO bound_phase_id FROM spine.sop_adoption_phases ap
          WHERE ap.adoption_id = p_id AND ap.phase_key = selected_phase_key;
        ordinal := 0;
        FOR milestone_def IN SELECT value FROM jsonb_array_elements(phase_def->'milestones') LOOP
            selected_milestone_key := milestone_def->>'key';
            selected_milestone_title := milestone_def->>'title';
            selected_criterion := milestone_def->>'criterion';
            SELECT (value->>'milestone_id')::uuid INTO selected_milestone_id
              FROM jsonb_array_elements(p_milestone_bindings)
             WHERE value->>'phase_key' = selected_phase_key
               AND value->>'milestone_key' = selected_milestone_key;
            SELECT * INTO milestone_row FROM spine.milestones WHERE id = selected_milestone_id;
            IF FOUND THEN
                IF coalesce(milestone_row.quote_id, milestone_row.booking_id, milestone_row.job_id) <> work_owner
                   OR milestone_row.title <> selected_milestone_title THEN
                    RAISE EXCEPTION 'bound milestone owner or title does not match the SOP definition'
                        USING ERRCODE = '23514';
                END IF;
                IF EXISTS (
                    SELECT 1 FROM spine.sop_adoption_milestones old
                    WHERE old.milestone_id = selected_milestone_id
                      AND (old.milestone_title <> selected_milestone_title
                           OR old.completion_criterion <> selected_criterion)
                ) THEN
                    RAISE EXCEPTION 'an SOP-bound milestone with changed meaning needs a new ID'
                        USING ERRCODE = '23514';
                END IF;
            ELSE
                INSERT INTO spine.milestones (id, quote_id, booking_id, job_id, title, actor)
                VALUES (selected_milestone_id, p_quote, p_booking, p_job,
                        selected_milestone_title, p_actor);
            END IF;
            SELECT assignment.phase_id INTO phase_assignment
              FROM spine.milestone_phase_assignments assignment
             WHERE assignment.milestone_id = selected_milestone_id;
            IF FOUND AND phase_assignment <> bound_phase_id THEN
                RAISE EXCEPTION 'a bound milestone cannot change its fixed phase assignment'
                    USING ERRCODE = '23514';
            ELSIF NOT FOUND THEN
                INSERT INTO spine.milestone_phase_assignments (milestone_id, phase_id, actor)
                VALUES (selected_milestone_id, bound_phase_id, p_actor);
            END IF;
            INSERT INTO spine.sop_adoption_milestones (
                adoption_id, phase_key, milestone_key, milestone_id, milestone_title,
                completion_criterion, definition_order
            ) VALUES (p_id, selected_phase_key, selected_milestone_key,
                      selected_milestone_id, selected_milestone_title, selected_criterion, ordinal);
            ordinal := ordinal + 1;
        END LOOP;
    END LOOP;
    RETURN p_id;
END;
$$;

GRANT EXECUTE ON FUNCTION
    spine.adopt_sop_version(uuid, uuid, uuid, uuid, uuid, uuid, text, text, uuid[], jsonb, jsonb)
TO PUBLIC;

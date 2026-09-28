-- Make restored core creation operations retry-safe and add phase assignment writes.

CREATE OR REPLACE FUNCTION spine.create_job(p_id uuid, p_title text, p_actor text)
RETURNS uuid LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog AS $$
DECLARE existing spine.jobs;
BEGIN
    PERFORM pg_advisory_xact_lock(hashtextextended(p_id::text, 0));
    SELECT * INTO existing FROM spine.jobs WHERE id = p_id;
    IF FOUND THEN
        IF existing.title IS DISTINCT FROM p_title OR existing.actor IS DISTINCT FROM p_actor THEN
            RAISE EXCEPTION 'job ID already has different contents' USING ERRCODE = 'SP004';
        END IF;
        RETURN p_id;
    END IF;
    INSERT INTO spine.jobs (id, title, actor) VALUES (p_id, p_title, p_actor);
    RETURN p_id;
END;
$$;

CREATE OR REPLACE FUNCTION spine.create_milestone(p_id uuid, p_job uuid, p_title text, p_actor text)
RETURNS uuid LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog AS $$
DECLARE existing spine.milestones;
BEGIN
    PERFORM pg_advisory_xact_lock(hashtextextended(p_id::text, 0));
    SELECT * INTO existing FROM spine.milestones WHERE id = p_id;
    IF FOUND THEN
        IF existing.job_id IS DISTINCT FROM p_job OR existing.title IS DISTINCT FROM p_title
           OR existing.actor IS DISTINCT FROM p_actor THEN
            RAISE EXCEPTION 'milestone ID already has different contents' USING ERRCODE = 'SP004';
        END IF;
        RETURN p_id;
    END IF;
    INSERT INTO spine.milestones (id, job_id, title, actor) VALUES (p_id, p_job, p_title, p_actor);
    RETURN p_id;
END;
$$;

CREATE OR REPLACE FUNCTION spine.record_evidence(
    p_id uuid, p_payload text, p_attachments jsonb, p_locator text,
    p_source_at timestamptz, p_actor text
) RETURNS uuid LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog AS $$
DECLARE existing spine.evidence;
BEGIN
    PERFORM pg_advisory_xact_lock(hashtextextended(p_id::text, 0));
    SELECT * INTO existing FROM spine.evidence WHERE id = p_id;
    IF FOUND THEN
        IF existing.original_payload IS DISTINCT FROM p_payload
           OR existing.attachments IS DISTINCT FROM p_attachments
           OR existing.source_locator IS DISTINCT FROM p_locator
           OR existing.source_at IS DISTINCT FROM p_source_at
           OR existing.actor IS DISTINCT FROM p_actor THEN
            RAISE EXCEPTION 'evidence ID already has different contents' USING ERRCODE = 'SP005';
        END IF;
        RETURN p_id;
    END IF;
    INSERT INTO spine.evidence (id, original_payload, attachments, source_locator, source_at, actor)
    VALUES (p_id, p_payload, p_attachments, p_locator, p_source_at, p_actor);
    RETURN p_id;
END;
$$;

CREATE FUNCTION spine.create_phase(
    p_id uuid, p_job uuid, p_name text, p_display_order integer, p_actor text
) RETURNS uuid LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog AS $$
DECLARE existing spine.phases;
BEGIN
    PERFORM pg_advisory_xact_lock(hashtextextended(p_id::text, 0));
    SELECT * INTO existing FROM spine.phases WHERE id = p_id;
    IF FOUND THEN
        IF existing.job_id IS DISTINCT FROM p_job OR existing.name IS DISTINCT FROM p_name
           OR existing.display_order IS DISTINCT FROM p_display_order OR existing.actor IS DISTINCT FROM p_actor THEN
            RAISE EXCEPTION 'phase ID already has different contents' USING ERRCODE = 'SP004';
        END IF;
        RETURN p_id;
    END IF;
    INSERT INTO spine.phases (id, job_id, name, display_order, actor)
    VALUES (p_id, p_job, p_name, p_display_order, p_actor);
    RETURN p_id;
END;
$$;

CREATE FUNCTION spine.assign_milestone_phase(
    p_milestone uuid, p_phase uuid, p_actor text
) RETURNS uuid LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog AS $$
DECLARE milestone_job uuid; phase_job uuid; existing_phase uuid; existing_actor text;
BEGIN
    PERFORM pg_advisory_xact_lock(hashtextextended(p_milestone::text, 0));
    SELECT job_id INTO milestone_job FROM spine.milestones WHERE id = p_milestone;
    IF NOT FOUND THEN RAISE EXCEPTION 'milestone does not exist' USING ERRCODE = '23503'; END IF;
    SELECT job_id INTO phase_job FROM spine.phases WHERE id = p_phase;
    IF NOT FOUND THEN RAISE EXCEPTION 'phase does not exist' USING ERRCODE = '23503'; END IF;
    IF milestone_job <> phase_job THEN
        RAISE EXCEPTION 'phase and milestone must belong to the same job' USING ERRCODE = '23514';
    END IF;
    SELECT phase_id, actor INTO existing_phase, existing_actor
    FROM spine.milestone_phase_assignments WHERE milestone_id = p_milestone;
    IF FOUND THEN
        IF existing_phase <> p_phase OR existing_actor <> p_actor THEN
            RAISE EXCEPTION 'milestone already has a different phase assignment' USING ERRCODE = 'SP003';
        END IF;
        RETURN p_milestone;
    END IF;
    INSERT INTO spine.milestone_phase_assignments (milestone_id, phase_id, actor)
    VALUES (p_milestone, p_phase, p_actor);
    RETURN p_milestone;
END;
$$;

GRANT EXECUTE ON FUNCTION spine.create_phase(uuid, uuid, text, integer, text),
    spine.assign_milestone_phase(uuid, uuid, text) TO PUBLIC;

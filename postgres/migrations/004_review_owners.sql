-- Let phases, milestones and visit memos belong to exactly one quote, booking or job.
-- Existing job-owned rows keep their job_id; the two new owner columns stay null.
-- Judgments, citations, links and phase assignments keep their shape and follow
-- the owner of the milestone they name. Documents belong to jobs only.

ALTER TABLE spine.phases
    ADD COLUMN quote_id uuid REFERENCES spine.quotes,
    ADD COLUMN booking_id uuid REFERENCES spine.bookings,
    ALTER COLUMN job_id DROP NOT NULL,
    ADD CONSTRAINT phases_one_owner CHECK (num_nonnulls(quote_id, booking_id, job_id) = 1),
    ADD CONSTRAINT phases_quote_display_order UNIQUE (quote_id, display_order),
    ADD CONSTRAINT phases_booking_display_order UNIQUE (booking_id, display_order);
CREATE INDEX ON spine.phases (quote_id);
CREATE INDEX ON spine.phases (booking_id);

ALTER TABLE spine.milestones
    ADD COLUMN quote_id uuid REFERENCES spine.quotes,
    ADD COLUMN booking_id uuid REFERENCES spine.bookings,
    ALTER COLUMN job_id DROP NOT NULL,
    ADD CONSTRAINT milestones_one_owner CHECK (num_nonnulls(quote_id, booking_id, job_id) = 1);
CREATE INDEX ON spine.milestones (quote_id);
CREATE INDEX ON spine.milestones (booking_id);

ALTER TABLE spine.visit_memos
    ADD COLUMN quote_id uuid REFERENCES spine.quotes,
    ADD COLUMN booking_id uuid REFERENCES spine.bookings,
    ALTER COLUMN job_id DROP NOT NULL,
    ADD CONSTRAINT visit_memos_one_owner CHECK (num_nonnulls(quote_id, booking_id, job_id) = 1);
CREATE INDEX ON spine.visit_memos (quote_id, recorded_at DESC);
CREATE INDEX ON spine.visit_memos (booking_id, recorded_at DESC);

-- Exactly one owner must be named and must exist. Returns that owner's ID.
CREATE FUNCTION spine.require_work_owner(p_quote uuid, p_booking uuid, p_job uuid)
RETURNS uuid LANGUAGE plpgsql STABLE SET search_path = pg_catalog AS $$
BEGIN
    IF num_nonnulls(p_quote, p_booking, p_job) <> 1 THEN
        RAISE EXCEPTION 'exactly one owning quote, booking or job is required' USING ERRCODE = '23514';
    END IF;
    IF (p_quote IS NOT NULL AND NOT EXISTS (SELECT 1 FROM spine.quotes WHERE id = p_quote))
       OR (p_booking IS NOT NULL AND NOT EXISTS (SELECT 1 FROM spine.bookings WHERE id = p_booking))
       OR (p_job IS NOT NULL AND NOT EXISTS (SELECT 1 FROM spine.jobs WHERE id = p_job)) THEN
        RAISE EXCEPTION 'owning work does not exist' USING ERRCODE = '23503';
    END IF;
    RETURN coalesce(p_quote, p_booking, p_job);
END;
$$;

CREATE FUNCTION spine.create_phase_v2(
    p_id uuid, p_quote uuid, p_booking uuid, p_job uuid,
    p_name text, p_display_order integer, p_actor text
) RETURNS uuid LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog AS $$
DECLARE existing spine.phases;
BEGIN
    PERFORM pg_advisory_xact_lock(hashtextextended(p_id::text, 0));
    SELECT * INTO existing FROM spine.phases WHERE id = p_id;
    IF FOUND THEN
        IF existing.quote_id IS DISTINCT FROM p_quote OR existing.booking_id IS DISTINCT FROM p_booking
           OR existing.job_id IS DISTINCT FROM p_job OR existing.name IS DISTINCT FROM p_name
           OR existing.display_order IS DISTINCT FROM p_display_order OR existing.actor IS DISTINCT FROM p_actor THEN
            RAISE EXCEPTION 'phase ID already has different contents' USING ERRCODE = 'SP004';
        END IF;
        RETURN p_id;
    END IF;
    PERFORM spine.require_work_owner(p_quote, p_booking, p_job);
    INSERT INTO spine.phases (id, quote_id, booking_id, job_id, name, display_order, actor)
    VALUES (p_id, p_quote, p_booking, p_job, p_name, p_display_order, p_actor);
    RETURN p_id;
END;
$$;

CREATE FUNCTION spine.create_milestone_v2(
    p_id uuid, p_quote uuid, p_booking uuid, p_job uuid, p_title text, p_actor text
) RETURNS uuid LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog AS $$
DECLARE existing spine.milestones;
BEGIN
    PERFORM pg_advisory_xact_lock(hashtextextended(p_id::text, 0));
    SELECT * INTO existing FROM spine.milestones WHERE id = p_id;
    IF FOUND THEN
        IF existing.quote_id IS DISTINCT FROM p_quote OR existing.booking_id IS DISTINCT FROM p_booking
           OR existing.job_id IS DISTINCT FROM p_job OR existing.title IS DISTINCT FROM p_title
           OR existing.actor IS DISTINCT FROM p_actor THEN
            RAISE EXCEPTION 'milestone ID already has different contents' USING ERRCODE = 'SP004';
        END IF;
        RETURN p_id;
    END IF;
    PERFORM spine.require_work_owner(p_quote, p_booking, p_job);
    INSERT INTO spine.milestones (id, quote_id, booking_id, job_id, title, actor)
    VALUES (p_id, p_quote, p_booking, p_job, p_title, p_actor);
    RETURN p_id;
END;
$$;

-- The job-only signatures stay for restored clients and route through the owner-aware writes.
CREATE OR REPLACE FUNCTION spine.create_phase(
    p_id uuid, p_job uuid, p_name text, p_display_order integer, p_actor text
) RETURNS uuid LANGUAGE sql SECURITY DEFINER SET search_path = pg_catalog AS $$
    SELECT spine.create_phase_v2(p_id, NULL, NULL, p_job, p_name, p_display_order, p_actor);
$$;

CREATE OR REPLACE FUNCTION spine.create_milestone(p_id uuid, p_job uuid, p_title text, p_actor text)
RETURNS uuid LANGUAGE sql SECURITY DEFINER SET search_path = pg_catalog AS $$
    SELECT spine.create_milestone_v2(p_id, NULL, NULL, p_job, p_title, p_actor);
$$;

CREATE OR REPLACE FUNCTION spine.assign_milestone_phase(
    p_milestone uuid, p_phase uuid, p_actor text
) RETURNS uuid LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog AS $$
DECLARE milestone_owner uuid; phase_owner uuid; existing_phase uuid; existing_actor text;
BEGIN
    PERFORM pg_advisory_xact_lock(hashtextextended(p_milestone::text, 0));
    SELECT coalesce(quote_id, booking_id, job_id) INTO milestone_owner
    FROM spine.milestones WHERE id = p_milestone;
    IF NOT FOUND THEN RAISE EXCEPTION 'milestone does not exist' USING ERRCODE = '23503'; END IF;
    SELECT coalesce(quote_id, booking_id, job_id) INTO phase_owner
    FROM spine.phases WHERE id = p_phase;
    IF NOT FOUND THEN RAISE EXCEPTION 'phase does not exist' USING ERRCODE = '23503'; END IF;
    IF milestone_owner <> phase_owner THEN
        RAISE EXCEPTION 'phase and milestone must belong to the same work' USING ERRCODE = '23514';
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

-- Same body as 001 except that linked judgments must share the milestone's owner, not its job.
CREATE OR REPLACE FUNCTION spine.append_judgment_v2(
    p_id uuid, p_milestone uuid, p_status text, p_explanation text, p_actor text,
    p_citations uuid[], p_occurred_on date, p_precision text,
    p_revises uuid[], p_based_on uuid[]
) RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog AS $$
DECLARE
    existing spine.judgments; cited uuid[]; revisions uuid[]; bases uuid[];
    old_cited uuid[]; old_revisions uuid[]; old_bases uuid[]; next_position bigint;
    milestone_owner uuid; linked_count integer;
BEGIN
    IF p_citations IS NULL OR cardinality(p_citations) = 0 OR array_position(p_citations, NULL) IS NOT NULL THEN
        RAISE EXCEPTION 'a judgment requires at least one evidence citation' USING ERRCODE = '23514';
    END IF;
    IF (p_occurred_on IS NULL) <> (p_precision IS NULL) OR
       (p_precision IS NOT NULL AND p_precision NOT IN ('exact', 'by')) THEN
        RAISE EXCEPTION 'occurrence date and precision must be supplied together' USING ERRCODE = '23514';
    END IF;
    SELECT array_agg(DISTINCT x ORDER BY x) INTO cited FROM unnest(p_citations) x;
    SELECT coalesce(array_agg(DISTINCT x ORDER BY x), ARRAY[]::uuid[]) INTO revisions FROM unnest(coalesce(p_revises, ARRAY[]::uuid[])) x;
    SELECT coalesce(array_agg(DISTINCT x ORDER BY x), ARRAY[]::uuid[]) INTO bases FROM unnest(coalesce(p_based_on, ARRAY[]::uuid[])) x;
    IF cardinality(revisions) > 1 OR array_position(revisions, p_id) IS NOT NULL OR
       array_position(bases, p_id) IS NOT NULL OR revisions && bases THEN
        RAISE EXCEPTION 'invalid judgment links' USING ERRCODE = '23514';
    END IF;

    PERFORM pg_advisory_xact_lock(hashtextextended(p_id::text, 0));
    SELECT * INTO existing FROM spine.judgments WHERE id = p_id;
    IF FOUND THEN
        SELECT array_agg(evidence_id ORDER BY evidence_id) INTO old_cited FROM spine.citations WHERE judgment_id = p_id;
        SELECT coalesce(array_agg(related_judgment_id ORDER BY related_judgment_id), ARRAY[]::uuid[]) INTO old_revisions
          FROM spine.judgment_links WHERE judgment_id = p_id AND relationship = 'revises';
        SELECT coalesce(array_agg(related_judgment_id ORDER BY related_judgment_id), ARRAY[]::uuid[]) INTO old_bases
          FROM spine.judgment_links WHERE judgment_id = p_id AND relationship = 'based_on';
        IF existing.milestone_id IS DISTINCT FROM p_milestone OR existing.status IS DISTINCT FROM p_status
           OR existing.explanation IS DISTINCT FROM p_explanation OR existing.actor IS DISTINCT FROM p_actor
           OR existing.occurred_on IS DISTINCT FROM p_occurred_on
           OR existing.occurrence_precision IS DISTINCT FROM p_precision
           OR old_cited IS DISTINCT FROM cited OR old_revisions IS DISTINCT FROM revisions
           OR old_bases IS DISTINCT FROM bases THEN
            RAISE EXCEPTION 'judgment ID already has different contents' USING ERRCODE = 'SP001';
        END IF;
        RETURN (SELECT document FROM spine.judgment_details WHERE id = p_id);
    END IF;

    SELECT coalesce(quote_id, booking_id, job_id) INTO milestone_owner
    FROM spine.milestones WHERE id = p_milestone FOR UPDATE;
    IF NOT FOUND THEN RAISE EXCEPTION 'milestone does not exist' USING ERRCODE = '23503'; END IF;
    SELECT count(*) INTO linked_count FROM (
        SELECT x FROM unnest(revisions || bases) x
        JOIN spine.judgments j ON j.id = x
        JOIN spine.milestones m ON m.id = j.milestone_id
        WHERE coalesce(m.quote_id, m.booking_id, m.job_id) = milestone_owner
    ) valid;
    IF linked_count <> cardinality(revisions) + cardinality(bases) THEN
        RAISE EXCEPTION 'linked judgments must exist on the same work' USING ERRCODE = '23503';
    END IF;
    IF cardinality(revisions) = 1 AND NOT EXISTS (
        SELECT 1 FROM spine.judgments j WHERE j.id = revisions[1] AND j.milestone_id = p_milestone
    ) THEN RAISE EXCEPTION 'a revision must name the same milestone' USING ERRCODE = '23514'; END IF;

    SELECT coalesce(max(position), 0) + 1 INTO next_position FROM spine.judgments WHERE milestone_id = p_milestone;
    INSERT INTO spine.judgments (id, milestone_id, position, status, explanation, actor, occurred_on, occurrence_precision)
    VALUES (p_id, p_milestone, next_position, p_status, p_explanation, p_actor, p_occurred_on, p_precision);
    INSERT INTO spine.citations SELECT p_id, x FROM unnest(cited) x;
    INSERT INTO spine.judgment_links SELECT p_id, x, 'revises' FROM unnest(revisions) x;
    INSERT INTO spine.judgment_links SELECT p_id, x, 'based_on' FROM unnest(bases) x;
    RETURN (SELECT document FROM spine.judgment_details WHERE id = p_id);
END;
$$;

CREATE FUNCTION spine.append_visit_memo_v2(
    p_id uuid, p_quote uuid, p_booking uuid, p_job uuid,
    p_started timestamptz, p_ended timestamptz,
    p_summary text, p_decision text, p_waiting text, p_next timestamptz,
    p_changed boolean, p_details jsonb, p_actor text,
    p_milestones uuid[], p_judgments uuid[]
) RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog AS $$
DECLARE
    existing spine.visit_memos; reviewed_m_ids uuid[]; reviewed_j_ids uuid[];
    old_milestones uuid[]; old_judgments uuid[]; valid_count integer;
    normalized_details jsonb; work_owner uuid;
BEGIN
    normalized_details := coalesce(p_details, '{}'::jsonb);
    SELECT coalesce(array_agg(DISTINCT x ORDER BY x), ARRAY[]::uuid[]) INTO reviewed_m_ids FROM unnest(coalesce(p_milestones, ARRAY[]::uuid[])) x;
    SELECT coalesce(array_agg(DISTINCT x ORDER BY x), ARRAY[]::uuid[]) INTO reviewed_j_ids FROM unnest(coalesce(p_judgments, ARRAY[]::uuid[])) x;
    PERFORM pg_advisory_xact_lock(hashtextextended(p_id::text, 0));
    SELECT * INTO existing FROM spine.visit_memos WHERE id = p_id;
    IF FOUND THEN
        SELECT coalesce(array_agg(milestone_id ORDER BY milestone_id), ARRAY[]::uuid[]) INTO old_milestones FROM spine.visit_memo_milestones WHERE memo_id = p_id;
        SELECT coalesce(array_agg(judgment_id ORDER BY judgment_id), ARRAY[]::uuid[]) INTO old_judgments FROM spine.visit_memo_judgments WHERE memo_id = p_id;
        IF existing.quote_id IS DISTINCT FROM p_quote OR existing.booking_id IS DISTINCT FROM p_booking
           OR existing.job_id IS DISTINCT FROM p_job OR existing.review_started_at IS DISTINCT FROM p_started
           OR existing.review_ended_at IS DISTINCT FROM p_ended OR existing.summary IS DISTINCT FROM p_summary
           OR existing.decision IS DISTINCT FROM p_decision OR existing.waiting_for IS DISTINCT FROM p_waiting
           OR existing.next_review_at IS DISTINCT FROM p_next OR existing.changed IS DISTINCT FROM p_changed
           OR existing.details IS DISTINCT FROM normalized_details OR existing.actor IS DISTINCT FROM p_actor
           OR old_milestones IS DISTINCT FROM reviewed_m_ids OR old_judgments IS DISTINCT FROM reviewed_j_ids THEN
            RAISE EXCEPTION 'memo ID already has different contents' USING ERRCODE = 'SP002';
        END IF;
    ELSE
        work_owner := spine.require_work_owner(p_quote, p_booking, p_job);
        SELECT count(*) INTO valid_count FROM spine.milestones
            WHERE id = ANY(reviewed_m_ids) AND coalesce(quote_id, booking_id, job_id) = work_owner;
        IF valid_count <> cardinality(reviewed_m_ids) THEN
            RAISE EXCEPTION 'reviewed milestones must belong to the owning work' USING ERRCODE = '23503';
        END IF;
        SELECT count(*) INTO valid_count FROM spine.judgments j JOIN spine.milestones m ON m.id = j.milestone_id
            WHERE j.id = ANY(reviewed_j_ids) AND coalesce(m.quote_id, m.booking_id, m.job_id) = work_owner;
        IF valid_count <> cardinality(reviewed_j_ids) THEN
            RAISE EXCEPTION 'reviewed judgments must belong to the owning work' USING ERRCODE = '23503';
        END IF;
        INSERT INTO spine.visit_memos (id, quote_id, booking_id, job_id, review_started_at, review_ended_at,
            summary, decision, waiting_for, next_review_at, changed, details, actor)
        VALUES (p_id, p_quote, p_booking, p_job, p_started, p_ended, p_summary, p_decision, p_waiting,
            p_next, p_changed, normalized_details, p_actor);
        INSERT INTO spine.visit_memo_milestones SELECT p_id, x FROM unnest(reviewed_m_ids) x;
        INSERT INTO spine.visit_memo_judgments SELECT p_id, x FROM unnest(reviewed_j_ids) x;
    END IF;
    RETURN to_jsonb((SELECT m FROM spine.visit_memos m WHERE id = p_id)) || jsonb_build_object(
        'reviewed_milestone_ids', to_jsonb(reviewed_m_ids), 'reviewed_judgment_ids', to_jsonb(reviewed_j_ids));
END;
$$;

CREATE OR REPLACE FUNCTION spine.append_visit_memo(
    p_id uuid, p_job uuid, p_started timestamptz, p_ended timestamptz,
    p_summary text, p_decision text, p_waiting text, p_next timestamptz,
    p_changed boolean, p_details jsonb, p_actor text,
    p_milestones uuid[], p_judgments uuid[]
) RETURNS jsonb LANGUAGE sql SECURITY DEFINER SET search_path = pg_catalog AS $$
    SELECT spine.append_visit_memo_v2(
        p_id, NULL, NULL, p_job, p_started, p_ended, p_summary, p_decision, p_waiting,
        p_next, p_changed, p_details, p_actor, p_milestones, p_judgments
    );
$$;

GRANT EXECUTE ON FUNCTION
    spine.require_work_owner(uuid, uuid, uuid),
    spine.create_phase_v2(uuid, uuid, uuid, uuid, text, integer, text),
    spine.create_milestone_v2(uuid, uuid, uuid, uuid, text, text),
    spine.append_visit_memo_v2(uuid, uuid, uuid, uuid, timestamptz, timestamptz, text, text, text,
        timestamptz, boolean, jsonb, text, uuid[], uuid[]) TO PUBLIC;

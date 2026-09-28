-- The word for one quote with its bookings and jobs is "chain".
--
-- Migration 014 used an older word in three sentences that reach a reader:
-- the reason it writes on the adoption of a booking or job that follows its
-- quote, and two refusals. An applied migration never changes, so this file
-- replaces the two functions that hold those sentences. Each body is copied
-- from 014 unchanged except for that one word. Function and trigger names
-- stay as they are, because applied names never change either.
--
-- CREATE OR REPLACE keeps each function's owner, its privileges and the
-- triggers that call it. No row changes: adoptions recorded before this file
-- keep the reason they were written with, and the server shows that stored
-- sentence in the new wording when it is read.

-- A booking or job takes its stage from the chain's adoption at the quote.
CREATE OR REPLACE FUNCTION spine.follow_load_sop(p_booking uuid, p_job uuid, p_actor text)
RETURNS uuid LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog AS $$
DECLARE
    work_id uuid; work_kind text; root_quote uuid; lead spine.sop_adoptions;
    version_row spine.sop_versions; stage jsonb; phases jsonb; milestones jsonb;
    cited uuid[]; adoption_id uuid; existing spine.sop_adoptions;
BEGIN
    IF num_nonnulls(p_booking, p_job) <> 1 THEN
        RAISE EXCEPTION 'follow_load_sop takes a booking or a job' USING ERRCODE = '23514';
    END IF;
    work_id := coalesce(p_booking, p_job);
    work_kind := CASE WHEN p_booking IS NOT NULL THEN 'booking' ELSE 'job' END;
    root_quote := spine.load_root_quote(p_booking, p_job);
    IF root_quote IS NULL THEN
        RETURN NULL;
    END IF;
    -- The same lock adopt_sop_version takes for the quote: a follow and the
    -- quote's adoption never read past each other, in either order.
    PERFORM pg_advisory_xact_lock(hashtextextended('sop-owner:' || root_quote::text, 0));
    SELECT a.* INTO lead FROM spine.sop_adoptions a
     WHERE a.quote_id = root_quote
       AND NOT EXISTS (SELECT 1 FROM spine.sop_adoptions n WHERE n.previous_adoption_id = a.id)
     ORDER BY a.recorded_at DESC, a.id DESC LIMIT 1;
    IF NOT FOUND THEN
        RETURN NULL;
    END IF;
    SELECT a.* INTO existing FROM spine.sop_adoptions a
     WHERE coalesce(a.quote_id, a.booking_id, a.job_id) = work_id
       AND NOT EXISTS (SELECT 1 FROM spine.sop_adoptions n WHERE n.previous_adoption_id = a.id)
     LIMIT 1;
    IF FOUND THEN
        -- Already following this lead, or chosen the same version on its own
        -- before the rule existed: nothing to add. A different version is a
        -- chain that would follow two SOPs, so the event that brought them
        -- together is refused.
        IF existing.follows_adoption_id = lead.id OR existing.sop_version_id = lead.sop_version_id THEN
            RETURN existing.id;
        END IF;
        RAISE EXCEPTION '% % already follows a different SOP version than its quote', work_kind, work_id
            USING ERRCODE = '23514';
    END IF;
    SELECT * INTO version_row FROM spine.sop_versions WHERE id = lead.sop_version_id;
    stage := version_row.definition->'stages'->work_kind;
    adoption_id := spine.follow_adoption_id(work_id, lead.id);
    SELECT coalesce(jsonb_agg(jsonb_build_object(
        'phase_key', p->>'key',
        'phase_id', md5('sop-follow-phase:' || work_id::text || ':' || lead.id::text
                        || ':' || (p->>'key'))::uuid)), '[]'::jsonb)
      INTO phases FROM jsonb_array_elements(stage->'phases') p;
    SELECT coalesce(jsonb_agg(jsonb_build_object(
        'phase_key', p->>'key', 'milestone_key', m->>'key',
        'milestone_id', md5('sop-follow-milestone:' || work_id::text || ':' || lead.id::text
                            || ':' || (p->>'key') || ':' || (m->>'key'))::uuid)), '[]'::jsonb)
      INTO milestones
      FROM jsonb_array_elements(stage->'phases') p, jsonb_array_elements(p->'milestones') m;
    SELECT array_agg(c.evidence_id ORDER BY c.evidence_id) INTO cited
      FROM spine.sop_adoption_citations c WHERE c.adoption_id = lead.id;
    PERFORM set_config('spine.follows_adoption', lead.id::text, true);
    PERFORM spine.adopt_sop_version(
        adoption_id, NULL, p_booking, p_job, lead.sop_version_id, NULL,
        'Follows the SOP the chain adopted at its quote.', p_actor, cited, phases, milestones);
    PERFORM set_config('spine.follows_adoption', '', true);
    RETURN adoption_id;
END;
$$;

-- The rule on every adoption row, as in 014; only the two refusals are reworded.
CREATE OR REPLACE FUNCTION spine.require_load_sop()
RETURNS trigger LANGUAGE plpgsql SET search_path = pg_catalog AS $$
DECLARE follows text; lead spine.sop_adoptions; work_id uuid;
BEGIN
    follows := current_setting('spine.follows_adoption', true);
    IF follows IS NOT NULL AND follows <> '' THEN
        SELECT a.* INTO lead FROM spine.sop_adoptions a WHERE a.id = follows::uuid;
        IF NOT FOUND OR lead.quote_id IS NULL OR EXISTS (
            SELECT 1 FROM spine.sop_adoptions n WHERE n.previous_adoption_id = lead.id) THEN
            RAISE EXCEPTION 'a follow must name the current adoption of a quote' USING ERRCODE = '23514';
        END IF;
        work_id := coalesce(NEW.booking_id, NEW.job_id);
        IF NEW.quote_id IS NOT NULL OR NEW.previous_adoption_id IS NOT NULL
           OR NEW.sop_version_id <> lead.sop_version_id
           OR spine.load_root_quote(NEW.booking_id, NEW.job_id) IS DISTINCT FROM lead.quote_id
           OR NEW.id <> spine.follow_adoption_id(work_id, lead.id) THEN
            RAISE EXCEPTION 'a follow must be the booking or job under that quote, on its version, with the derived id'
                USING ERRCODE = '23514';
        END IF;
        NEW.follows_adoption_id := lead.id;
        RETURN NEW;
    END IF;
    IF spine.sop_version_state(NEW.sop_version_id) = 'retired' THEN
        RAISE EXCEPTION 'SOP version is retired; a chain cannot adopt it' USING ERRCODE = '23514';
    END IF;
    IF NEW.previous_adoption_id IS NOT NULL THEN
        RETURN NEW;
    END IF;
    IF NEW.booking_id IS NOT NULL OR (NEW.job_id IS NOT NULL AND EXISTS (
        SELECT 1 FROM spine.job_booking_links l WHERE l.job_id = NEW.job_id)) THEN
        RAISE EXCEPTION 'a chain adopts its SOP once, at the quote; its bookings and jobs follow it'
            USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END;
$$;

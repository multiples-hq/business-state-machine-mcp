-- One SOP per chain, and versions that are active or retired.
--
-- Without this rule a quote, its booking and its job would each adopt an SOP
-- version on their own, and could adopt three different ones. The rule: a
-- chain chooses once, at the quote. The booking and the job
-- under it follow that choice. A booking created under an adopted quote, or a
-- job linked to a booking under one, gets its stage's phases and milestones
-- from the same version in the same transaction, recorded as an adoption row
-- whose follows_adoption_id names the quote's. When a quote adopts after its
-- bookings and jobs exist, they follow at commit. An adoption on a booking,
-- or on a job linked to a booking, is refused: the chain adopts at the quote.
-- A job with no booking still adopts on its own, and a job's break-glass
-- replacement is unchanged: only a job can replace its SOP version.
--
-- A version is active unless its latest status row says retired. Retiring is
-- an appended row, never an edit; a retired version cannot be adopted by a
-- new chain, and chains already on it keep following it.
--
-- No existing row changes. sop_adoptions gains one nullable column, null on
-- every row that exists today.

CREATE TABLE spine.sop_version_status (
    id uuid PRIMARY KEY,
    sop_version_id uuid NOT NULL REFERENCES spine.sop_versions,
    status text NOT NULL CONSTRAINT sop_version_status_check CHECK (status IN ('active', 'retired')),
    reason text NOT NULL CHECK (length(btrim(reason)) > 0),
    actor text NOT NULL CHECK (length(btrim(actor)) > 0),
    recorded_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
CREATE INDEX ON spine.sop_version_status (sop_version_id, recorded_at, id);
-- A status change cites the message or instruction that called for it.
CREATE TABLE spine.sop_version_status_citations (
    status_id uuid NOT NULL REFERENCES spine.sop_version_status,
    evidence_id uuid NOT NULL REFERENCES spine.evidence,
    PRIMARY KEY (status_id, evidence_id)
);
DO $$
DECLARE table_name text;
BEGIN
    FOREACH table_name IN ARRAY ARRAY['sop_version_status', 'sop_version_status_citations'] LOOP
        EXECUTE format(
            'CREATE TRIGGER append_only BEFORE UPDATE OR DELETE OR TRUNCATE ON spine.%I '
            'FOR EACH STATEMENT EXECUTE FUNCTION spine.refuse_mutation()', table_name);
    END LOOP;
END;
$$;
REVOKE ALL ON spine.sop_version_status, spine.sop_version_status_citations FROM PUBLIC;
GRANT SELECT ON spine.sop_version_status, spine.sop_version_status_citations TO PUBLIC;

ALTER TABLE spine.sop_adoptions
    ADD COLUMN follows_adoption_id uuid REFERENCES spine.sop_adoptions;
CREATE INDEX ON spine.sop_adoptions (follows_adoption_id);

-- The state of a version at read time: its latest status row, else active.
CREATE FUNCTION spine.sop_version_state(p_version uuid)
RETURNS text LANGUAGE sql STABLE SET search_path = pg_catalog AS $$
    SELECT coalesce((SELECT s.status FROM spine.sop_version_status s
                     WHERE s.sop_version_id = p_version
                     ORDER BY s.recorded_at DESC, s.id DESC LIMIT 1), 'active');
$$;

CREATE FUNCTION spine.set_sop_version_status(
    p_id uuid, p_version uuid, p_status text, p_reason text, p_actor text, p_evidence uuid[]
) RETURNS uuid LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog AS $$
DECLARE existing spine.sop_version_status; cited uuid[]; old_cited uuid[];
BEGIN
    IF p_evidence IS NULL OR cardinality(p_evidence) = 0 OR array_position(p_evidence, NULL) IS NOT NULL THEN
        RAISE EXCEPTION 'an SOP status change requires at least one evidence citation' USING ERRCODE = '23514';
    END IF;
    SELECT array_agg(DISTINCT x ORDER BY x) INTO cited FROM unnest(p_evidence) x;
    PERFORM pg_advisory_xact_lock(hashtextextended(p_id::text, 0));
    SELECT * INTO existing FROM spine.sop_version_status WHERE id = p_id;
    IF FOUND THEN
        SELECT array_agg(evidence_id ORDER BY evidence_id) INTO old_cited
          FROM spine.sop_version_status_citations WHERE status_id = p_id;
        IF existing.sop_version_id IS DISTINCT FROM p_version OR existing.status IS DISTINCT FROM p_status
           OR existing.reason IS DISTINCT FROM p_reason OR existing.actor IS DISTINCT FROM p_actor
           OR old_cited IS DISTINCT FROM cited THEN
            RAISE EXCEPTION 'SOP status ID already has different contents' USING ERRCODE = 'SP006';
        END IF;
        RETURN p_id;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM spine.sop_versions WHERE id = p_version) THEN
        RAISE EXCEPTION 'SOP version does not exist' USING ERRCODE = '23503';
    END IF;
    INSERT INTO spine.sop_version_status (id, sop_version_id, status, reason, actor)
    VALUES (p_id, p_version, p_status, p_reason, p_actor);
    INSERT INTO spine.sop_version_status_citations SELECT p_id, x FROM unnest(cited) x;
    RETURN p_id;
END;
$$;

-- The quote a booking or job belongs to; null for a job with no booking.
CREATE FUNCTION spine.load_root_quote(p_booking uuid, p_job uuid)
RETURNS uuid LANGUAGE sql STABLE SET search_path = pg_catalog AS $$
    SELECT CASE
        WHEN p_booking IS NOT NULL THEN (SELECT b.quote_id FROM spine.bookings b WHERE b.id = p_booking)
        WHEN p_job IS NOT NULL THEN (SELECT b.quote_id FROM spine.job_booking_links l
                                     JOIN spine.bookings b ON b.id = l.booking_id WHERE l.job_id = p_job)
    END;
$$;

-- The one id a follow row may carry: derived from the work and the lead.
CREATE FUNCTION spine.follow_adoption_id(p_work uuid, p_lead uuid)
RETURNS uuid LANGUAGE sql IMMUTABLE SET search_path = pg_catalog AS $$
    SELECT md5('sop-follow:' || p_work::text || ':' || p_lead::text)::uuid;
$$;

-- A booking or job takes its stage from the chain's adoption at the quote.
-- Ids are derived from the work and the quote's adoption, so the same call
-- twice is the exact retry adopt_sop_version already accepts. The reason and
-- the citations are the quote's. Returns the adoption followed or made, or
-- null when the chain has not chosen an SOP yet.
CREATE FUNCTION spine.follow_load_sop(p_booking uuid, p_job uuid, p_actor text)
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
        'Follows the SOP the load adopted at its quote.', p_actor, cited, phases, milestones);
    PERFORM set_config('spine.follows_adoption', '', true);
    RETURN adoption_id;
END;
$$;

-- The rule on every adoption row. A following row names the quote's
-- adoption through the transaction setting, and the setting is not trusted:
-- the row must be exactly the follow that function would write, a booking or
-- job under that quote, on the quote's current version, with the derived id.
-- Any other new adoption: not of a retired version; not on a booking, nor on
-- a job that has a booking, unless it is a job's replacement.
CREATE FUNCTION spine.require_load_sop()
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
        RAISE EXCEPTION 'SOP version is retired; a load cannot adopt it' USING ERRCODE = '23514';
    END IF;
    IF NEW.previous_adoption_id IS NOT NULL THEN
        RETURN NEW;
    END IF;
    IF NEW.booking_id IS NOT NULL OR (NEW.job_id IS NOT NULL AND EXISTS (
        SELECT 1 FROM spine.job_booking_links l WHERE l.job_id = NEW.job_id)) THEN
        RAISE EXCEPTION 'a load adopts its SOP once, at the quote; its bookings and jobs follow it'
            USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER load_sop_rule BEFORE INSERT ON spine.sop_adoptions
FOR EACH ROW EXECUTE FUNCTION spine.require_load_sop();

-- A booking created under an adopted quote follows at once.
CREATE FUNCTION spine.follow_on_booking()
RETURNS trigger LANGUAGE plpgsql SET search_path = pg_catalog AS $$
BEGIN
    PERFORM spine.follow_load_sop(NEW.id, NULL, NEW.actor);
    RETURN NULL;
END;
$$;
CREATE TRIGGER follow_load_sop AFTER INSERT ON spine.bookings
FOR EACH ROW EXECUTE FUNCTION spine.follow_on_booking();

-- A job linked to a booking under an adopted quote follows at once.
CREATE FUNCTION spine.follow_on_job_link()
RETURNS trigger LANGUAGE plpgsql SET search_path = pg_catalog AS $$
BEGIN
    PERFORM spine.follow_load_sop(NULL, NEW.job_id, NEW.actor);
    RETURN NULL;
END;
$$;
CREATE TRIGGER follow_load_sop AFTER INSERT ON spine.job_booking_links
FOR EACH ROW EXECUTE FUNCTION spine.follow_on_job_link();

-- A quote adopting after its bookings and jobs exist: they follow at commit,
-- once the adoption's citations are in place.
CREATE FUNCTION spine.follow_on_quote_adoption()
RETURNS trigger LANGUAGE plpgsql SET search_path = pg_catalog AS $$
DECLARE booking record; job record;
BEGIN
    IF NEW.quote_id IS NULL THEN
        RETURN NULL;
    END IF;
    FOR booking IN SELECT b.id FROM spine.bookings b WHERE b.quote_id = NEW.quote_id
                   ORDER BY b.recorded_at, b.id LOOP
        PERFORM spine.follow_load_sop(booking.id, NULL, NEW.actor);
        FOR job IN SELECT l.job_id FROM spine.job_booking_links l WHERE l.booking_id = booking.id
                   ORDER BY l.recorded_at, l.job_id LOOP
            PERFORM spine.follow_load_sop(NULL, job.job_id, NEW.actor);
        END LOOP;
    END LOOP;
    RETURN NULL;
END;
$$;
CREATE CONSTRAINT TRIGGER follow_load_sop AFTER INSERT ON spine.sop_adoptions
DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION spine.follow_on_quote_adoption();

-- follow_load_sop is callable by anyone: the deferred trigger runs at commit
-- as the session's own role, outside any definer context, and calling it by
-- hand only does what creating the booking or the link would have done.
GRANT EXECUTE ON FUNCTION
    spine.sop_version_state(uuid),
    spine.set_sop_version_status(uuid, uuid, text, text, text, uuid[]),
    spine.load_root_quote(uuid, uuid),
    spine.follow_adoption_id(uuid, uuid),
    spine.follow_load_sop(uuid, uuid, text)
TO PUBLIC;

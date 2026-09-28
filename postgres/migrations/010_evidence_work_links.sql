-- Evidence stays ownerless. A link says which work an evidence row is about.
-- One row per evidence-and-work pair, appended and never removed. Zero links
-- means "not yet placed" and stays citable from any work, exactly as before.
CREATE TABLE spine.evidence_work_links (
    id uuid PRIMARY KEY,
    evidence_id uuid NOT NULL REFERENCES spine.evidence,
    quote_id uuid REFERENCES spine.quotes,
    booking_id uuid REFERENCES spine.bookings,
    job_id uuid REFERENCES spine.jobs,
    actor text NOT NULL CHECK (length(btrim(actor)) > 0),
    recorded_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CHECK (num_nonnulls(quote_id, booking_id, job_id) = 1)
);
CREATE INDEX ON spine.evidence_work_links (evidence_id);
CREATE INDEX ON spine.evidence_work_links (quote_id);
CREATE INDEX ON spine.evidence_work_links (booking_id);
CREATE INDEX ON spine.evidence_work_links (job_id);
CREATE TRIGGER append_only BEFORE UPDATE OR DELETE OR TRUNCATE
ON spine.evidence_work_links FOR EACH STATEMENT EXECUTE FUNCTION spine.refuse_mutation();

-- Same stable-ID retry rule as record_external_reference: an identical retry
-- returns the ID, a different payload under that ID is an error.
CREATE FUNCTION spine.link_evidence_work(
    p_id uuid, p_evidence uuid, p_quote uuid, p_booking uuid, p_job uuid, p_actor text
) RETURNS uuid LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog AS $$
DECLARE existing spine.evidence_work_links;
BEGIN
    PERFORM pg_advisory_xact_lock(hashtextextended(p_id::text, 0));
    SELECT * INTO existing FROM spine.evidence_work_links WHERE id = p_id;
    IF FOUND THEN
        IF existing.evidence_id IS DISTINCT FROM p_evidence
           OR existing.quote_id IS DISTINCT FROM p_quote
           OR existing.booking_id IS DISTINCT FROM p_booking
           OR existing.job_id IS DISTINCT FROM p_job
           OR existing.actor IS DISTINCT FROM p_actor THEN
            RAISE EXCEPTION 'evidence work link ID already has different contents'
                USING ERRCODE = 'SP008';
        END IF;
        RETURN p_id;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM spine.evidence WHERE id = p_evidence) THEN
        RAISE EXCEPTION 'evidence does not exist' USING ERRCODE = '23503';
    END IF;
    PERFORM spine.require_work_owner(p_quote, p_booking, p_job);
    INSERT INTO spine.evidence_work_links (id, evidence_id, quote_id, booking_id, job_id, actor)
    VALUES (p_id, p_evidence, p_quote, p_booking, p_job, p_actor);
    RETURN p_id;
END;
$$;

-- A citation may not reach across placed evidence. No links: allowed anywhere.
-- Links that include this judgment's own work owner: allowed. Otherwise refused.
CREATE FUNCTION spine.require_evidence_placement()
RETURNS trigger LANGUAGE plpgsql SET search_path = pg_catalog AS $$
DECLARE citing_owner uuid;
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM spine.evidence_work_links WHERE evidence_id = NEW.evidence_id
    ) THEN
        RETURN NULL;
    END IF;
    SELECT coalesce(m.quote_id, m.booking_id, m.job_id) INTO citing_owner
    FROM spine.judgments j JOIN spine.milestones m ON m.id = j.milestone_id
    WHERE j.id = NEW.judgment_id;
    IF NOT EXISTS (
        SELECT 1 FROM spine.evidence_work_links l
        WHERE l.evidence_id = NEW.evidence_id
          AND coalesce(l.quote_id, l.booking_id, l.job_id) = citing_owner
    ) THEN
        RAISE EXCEPTION
            'evidence is linked to other work; link it to this work first or cite different evidence'
            USING ERRCODE = '23514';
    END IF;
    RETURN NULL;
END;
$$;

-- Deferred until commit for two reasons. First, a review may insert the
-- citation before the link that places the evidence, and both belong to one
-- transaction. Second, it must compose with judgment_requires_memo from
-- migration 008, which is also deferred. Postgres queues both sets of deferred
-- events inside the transaction opened by record_review and fires them at
-- COMMIT, before anything becomes visible to other sessions. Whichever check
-- raises first aborts that COMMIT, so the whole review rolls back: every
-- judgment, citation, link and the memo. Their firing order therefore decides
-- only which message the caller sees, never whether partial rows survive.
-- AFTER INSERT only, so historical citations are never re-checked.
CREATE CONSTRAINT TRIGGER citation_matches_placement
AFTER INSERT ON spine.citations DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW EXECUTE FUNCTION spine.require_evidence_placement();

REVOKE ALL ON spine.evidence_work_links FROM PUBLIC;
GRANT SELECT ON spine.evidence_work_links TO PUBLIC;
GRANT EXECUTE ON FUNCTION spine.link_evidence_work(uuid, uuid, uuid, uuid, uuid, text) TO PUBLIC;

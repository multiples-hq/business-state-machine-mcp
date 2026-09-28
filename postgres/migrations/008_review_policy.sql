-- Apply recording policy to new writes; preserve all existing historical rows.
CREATE FUNCTION spine.require_judgment_memo()
RETURNS trigger LANGUAGE plpgsql SET search_path = pg_catalog AS $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM spine.visit_memo_judgments link
        JOIN spine.visit_memos memo ON memo.id = link.memo_id
        JOIN spine.milestones milestone ON milestone.id = NEW.milestone_id
        WHERE link.judgment_id = NEW.id
          AND coalesce(memo.quote_id, memo.booking_id, memo.job_id)
              = coalesce(milestone.quote_id, milestone.booking_id, milestone.job_id)
    ) THEN
        RAISE EXCEPTION 'new judgments require a linked memo; use record_review'
            USING ERRCODE = '23514';
    END IF;
    RETURN NULL;
END;
$$;

-- Deferred until commit so a review can insert judgments before its sealed memo.
CREATE CONSTRAINT TRIGGER judgment_requires_memo
AFTER INSERT ON spine.judgments DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW EXECUTE FUNCTION spine.require_judgment_memo();
CREATE INDEX ON spine.visit_memo_judgments (judgment_id);

CREATE FUNCTION spine.require_job_recovery()
RETURNS trigger LANGUAGE plpgsql SET search_path = pg_catalog AS $$
BEGIN
    IF NEW.job_id IS NULL AND (
        NEW.previous_adoption_id IS NOT NULL OR EXISTS (
            SELECT 1 FROM spine.sop_versions v
            WHERE v.id = NEW.sop_version_id AND v.tag = 'break_glass'
        )
    ) THEN
        RAISE EXCEPTION 'SOP replacement and break-glass adoption are job-only'
            USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END;
$$;

-- Insertion guard also covers direct access-function callers. An identical
-- historical retry returns before INSERT, leaving the old record unchanged.
CREATE TRIGGER job_only_recovery BEFORE INSERT ON spine.sop_adoptions
FOR EACH ROW EXECUTE FUNCTION spine.require_job_recovery();

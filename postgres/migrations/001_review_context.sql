-- Add review context to an existing five-table spine database.
-- Safe to run once after db/schema.sql or after restoring an old dump.

ALTER TABLE spine.judgments
    ADD COLUMN occurred_on date,
    ADD COLUMN occurrence_precision text,
    ADD CONSTRAINT judgment_occurrence_pair CHECK (
        (occurred_on IS NULL AND occurrence_precision IS NULL) OR
        (occurred_on IS NOT NULL AND occurrence_precision IS NOT NULL
            AND occurrence_precision IN ('exact', 'by'))
    );

CREATE TABLE spine.phases (
    id uuid PRIMARY KEY,
    job_id uuid NOT NULL REFERENCES spine.jobs,
    name text NOT NULL CHECK (length(btrim(name)) > 0),
    display_order integer NOT NULL CHECK (display_order >= 0),
    actor text NOT NULL CHECK (length(btrim(actor)) > 0),
    recorded_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    UNIQUE (job_id, display_order)
);
CREATE INDEX ON spine.phases (job_id);

CREATE TABLE spine.milestone_phase_assignments (
    milestone_id uuid PRIMARY KEY REFERENCES spine.milestones,
    phase_id uuid NOT NULL REFERENCES spine.phases,
    actor text NOT NULL CHECK (length(btrim(actor)) > 0),
    recorded_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
CREATE INDEX ON spine.milestone_phase_assignments (phase_id);

CREATE TABLE spine.judgment_links (
    judgment_id uuid NOT NULL REFERENCES spine.judgments,
    related_judgment_id uuid NOT NULL REFERENCES spine.judgments,
    relationship text NOT NULL CHECK (relationship IN ('revises', 'based_on')),
    PRIMARY KEY (judgment_id, related_judgment_id, relationship),
    CHECK (judgment_id <> related_judgment_id)
);
CREATE UNIQUE INDEX one_revision_per_judgment
    ON spine.judgment_links (judgment_id) WHERE relationship = 'revises';

CREATE TABLE spine.visit_memos (
    id uuid PRIMARY KEY,
    job_id uuid NOT NULL REFERENCES spine.jobs,
    review_started_at timestamptz NOT NULL,
    review_ended_at timestamptz NOT NULL,
    summary text NOT NULL CHECK (length(btrim(summary)) > 0),
    decision text NOT NULL CHECK (length(btrim(decision)) > 0),
    waiting_for text,
    next_review_at timestamptz,
    changed boolean NOT NULL,
    details jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(details) = 'object'),
    actor text NOT NULL CHECK (length(btrim(actor)) > 0),
    recorded_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CHECK (review_started_at <= review_ended_at),
    CHECK (waiting_for IS NULL OR length(btrim(waiting_for)) > 0)
);
CREATE INDEX ON spine.visit_memos (job_id, recorded_at DESC);

CREATE TABLE spine.visit_memo_milestones (
    memo_id uuid NOT NULL REFERENCES spine.visit_memos,
    milestone_id uuid NOT NULL REFERENCES spine.milestones,
    PRIMARY KEY (memo_id, milestone_id)
);

CREATE TABLE spine.visit_memo_judgments (
    memo_id uuid NOT NULL REFERENCES spine.visit_memos,
    judgment_id uuid NOT NULL REFERENCES spine.judgments,
    PRIMARY KEY (memo_id, judgment_id)
);

DO $$
DECLARE table_name text;
BEGIN
    FOREACH table_name IN ARRAY ARRAY[
        'phases', 'milestone_phase_assignments', 'judgment_links',
        'visit_memos', 'visit_memo_milestones', 'visit_memo_judgments'
    ] LOOP
        EXECUTE format(
            'CREATE TRIGGER append_only BEFORE UPDATE OR DELETE OR TRUNCATE ON spine.%I '
            'FOR EACH STATEMENT EXECUTE FUNCTION spine.refuse_mutation()', table_name);
    END LOOP;
END;
$$;

CREATE OR REPLACE VIEW spine.judgment_details AS
SELECT j.id, j.milestone_id, j.position,
       to_jsonb(j) || jsonb_build_object(
           'evidence', (SELECT jsonb_agg(to_jsonb(e) ORDER BY e.id)
               FROM spine.citations c JOIN spine.evidence e ON e.id = c.evidence_id
               WHERE c.judgment_id = j.id),
           'revises_ids', coalesce((SELECT jsonb_agg(l.related_judgment_id ORDER BY l.related_judgment_id)
               FROM spine.judgment_links l WHERE l.judgment_id = j.id AND l.relationship = 'revises'), '[]'::jsonb),
           'based_on_ids', coalesce((SELECT jsonb_agg(l.related_judgment_id ORDER BY l.related_judgment_id)
               FROM spine.judgment_links l WHERE l.judgment_id = j.id AND l.relationship = 'based_on'), '[]'::jsonb)
       ) AS document
FROM spine.judgments j;

CREATE FUNCTION spine.append_judgment_v2(
    p_id uuid, p_milestone uuid, p_status text, p_explanation text, p_actor text,
    p_citations uuid[], p_occurred_on date, p_precision text,
    p_revises uuid[], p_based_on uuid[]
) RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog AS $$
DECLARE
    existing spine.judgments; cited uuid[]; revisions uuid[]; bases uuid[];
    old_cited uuid[]; old_revisions uuid[]; old_bases uuid[]; next_position bigint;
    milestone_job uuid; linked_count integer;
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

    SELECT job_id INTO milestone_job FROM spine.milestones WHERE id = p_milestone FOR UPDATE;
    IF NOT FOUND THEN RAISE EXCEPTION 'milestone does not exist' USING ERRCODE = '23503'; END IF;
    SELECT count(*) INTO linked_count FROM (
        SELECT x FROM unnest(revisions || bases) x
        JOIN spine.judgments j ON j.id = x
        JOIN spine.milestones m ON m.id = j.milestone_id
        WHERE m.job_id = milestone_job
    ) valid;
    IF linked_count <> cardinality(revisions) + cardinality(bases) THEN
        RAISE EXCEPTION 'linked judgments must exist on the same job' USING ERRCODE = '23503';
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

-- Preserve the original signature for restored clients while routing every
-- write through the v2 retry comparison. A retry cannot hide newer fields.
CREATE OR REPLACE FUNCTION spine.append_judgment(
    p_id uuid, p_milestone uuid, p_status text, p_explanation text,
    p_actor text, p_citations uuid[]
) RETURNS jsonb LANGUAGE sql SECURITY DEFINER SET search_path = pg_catalog AS $$
    SELECT spine.append_judgment_v2(
        p_id, p_milestone, p_status, p_explanation, p_actor, p_citations,
        NULL, NULL, ARRAY[]::uuid[], ARRAY[]::uuid[]
    );
$$;

CREATE FUNCTION spine.append_visit_memo(
    p_id uuid, p_job uuid, p_started timestamptz, p_ended timestamptz,
    p_summary text, p_decision text, p_waiting text, p_next timestamptz,
    p_changed boolean, p_details jsonb, p_actor text,
    p_milestones uuid[], p_judgments uuid[]
) RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog AS $$
DECLARE
    existing spine.visit_memos; reviewed_m_ids uuid[]; reviewed_j_ids uuid[];
    old_milestones uuid[]; old_judgments uuid[]; valid_count integer;
    normalized_details jsonb;
BEGIN
    normalized_details := coalesce(p_details, '{}'::jsonb);
    SELECT coalesce(array_agg(DISTINCT x ORDER BY x), ARRAY[]::uuid[]) INTO reviewed_m_ids FROM unnest(coalesce(p_milestones, ARRAY[]::uuid[])) x;
    SELECT coalesce(array_agg(DISTINCT x ORDER BY x), ARRAY[]::uuid[]) INTO reviewed_j_ids FROM unnest(coalesce(p_judgments, ARRAY[]::uuid[])) x;
    PERFORM pg_advisory_xact_lock(hashtextextended(p_id::text, 0));
    SELECT * INTO existing FROM spine.visit_memos WHERE id = p_id;
    IF FOUND THEN
        SELECT coalesce(array_agg(milestone_id ORDER BY milestone_id), ARRAY[]::uuid[]) INTO old_milestones FROM spine.visit_memo_milestones WHERE memo_id = p_id;
        SELECT coalesce(array_agg(judgment_id ORDER BY judgment_id), ARRAY[]::uuid[]) INTO old_judgments FROM spine.visit_memo_judgments WHERE memo_id = p_id;
        IF existing.job_id IS DISTINCT FROM p_job OR existing.review_started_at IS DISTINCT FROM p_started
           OR existing.review_ended_at IS DISTINCT FROM p_ended OR existing.summary IS DISTINCT FROM p_summary
           OR existing.decision IS DISTINCT FROM p_decision OR existing.waiting_for IS DISTINCT FROM p_waiting
           OR existing.next_review_at IS DISTINCT FROM p_next OR existing.changed IS DISTINCT FROM p_changed
           OR existing.details IS DISTINCT FROM normalized_details OR existing.actor IS DISTINCT FROM p_actor
           OR old_milestones IS DISTINCT FROM reviewed_m_ids OR old_judgments IS DISTINCT FROM reviewed_j_ids THEN
            RAISE EXCEPTION 'memo ID already has different contents' USING ERRCODE = 'SP002';
        END IF;
    ELSE
        PERFORM 1 FROM spine.jobs WHERE id = p_job;
        IF NOT FOUND THEN RAISE EXCEPTION 'job does not exist' USING ERRCODE = '23503'; END IF;
        SELECT count(*) INTO valid_count FROM spine.milestones WHERE id = ANY(reviewed_m_ids) AND job_id = p_job;
        IF valid_count <> cardinality(reviewed_m_ids) THEN RAISE EXCEPTION 'reviewed milestones must belong to the job' USING ERRCODE = '23503'; END IF;
        SELECT count(*) INTO valid_count FROM spine.judgments j JOIN spine.milestones m ON m.id = j.milestone_id
            WHERE j.id = ANY(reviewed_j_ids) AND m.job_id = p_job;
        IF valid_count <> cardinality(reviewed_j_ids) THEN RAISE EXCEPTION 'reviewed judgments must belong to the job' USING ERRCODE = '23503'; END IF;
        INSERT INTO spine.visit_memos (id, job_id, review_started_at, review_ended_at, summary,
            decision, waiting_for, next_review_at, changed, details, actor)
        VALUES (p_id, p_job, p_started, p_ended, p_summary, p_decision, p_waiting, p_next,
            p_changed, normalized_details, p_actor);
        INSERT INTO spine.visit_memo_milestones SELECT p_id, x FROM unnest(reviewed_m_ids) x;
        INSERT INTO spine.visit_memo_judgments SELECT p_id, x FROM unnest(reviewed_j_ids) x;
    END IF;
    RETURN to_jsonb((SELECT m FROM spine.visit_memos m WHERE id = p_id)) || jsonb_build_object(
        'reviewed_milestone_ids', to_jsonb(reviewed_m_ids), 'reviewed_judgment_ids', to_jsonb(reviewed_j_ids));
END;
$$;

REVOKE ALL ON spine.phases, spine.milestone_phase_assignments, spine.judgment_links,
    spine.visit_memos, spine.visit_memo_milestones, spine.visit_memo_judgments FROM PUBLIC;
GRANT SELECT ON spine.phases, spine.milestone_phase_assignments, spine.judgment_links,
    spine.visit_memos, spine.visit_memo_milestones, spine.visit_memo_judgments TO PUBLIC;
GRANT EXECUTE ON FUNCTION
    spine.append_judgment_v2(uuid, uuid, text, text, text, uuid[], date, text, uuid[], uuid[]),
    spine.append_visit_memo(uuid, uuid, timestamptz, timestamptz, text, text, text,
        timestamptz, boolean, jsonb, text, uuid[], uuid[]) TO PUBLIC;

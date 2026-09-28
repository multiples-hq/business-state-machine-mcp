-- Explicit external identifiers map to work, not necessarily uniquely.
CREATE TABLE spine.external_references (
    id uuid PRIMARY KEY,
    quote_id uuid REFERENCES spine.quotes,
    booking_id uuid REFERENCES spine.bookings,
    job_id uuid REFERENCES spine.jobs,
    reference_type text NOT NULL CHECK (length(btrim(reference_type)) > 0),
    source text NOT NULL CHECK (length(btrim(source)) > 0),
    value text NOT NULL CHECK (length(btrim(value)) > 0),
    actor text NOT NULL CHECK (length(btrim(actor)) > 0),
    recorded_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CHECK (num_nonnulls(quote_id, booking_id, job_id) = 1)
);
CREATE INDEX ON spine.external_references (value, reference_type, source);
CREATE INDEX ON spine.external_references (quote_id);
CREATE INDEX ON spine.external_references (booking_id);
CREATE INDEX ON spine.external_references (job_id);
CREATE TRIGGER append_only BEFORE UPDATE OR DELETE OR TRUNCATE
ON spine.external_references FOR EACH STATEMENT EXECUTE FUNCTION spine.refuse_mutation();

CREATE FUNCTION spine.record_external_reference(
    p_id uuid, p_quote uuid, p_booking uuid, p_job uuid,
    p_type text, p_source text, p_value text, p_actor text
) RETURNS uuid LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog AS $$
DECLARE existing spine.external_references;
BEGIN
    PERFORM pg_advisory_xact_lock(hashtextextended(p_id::text, 0));
    SELECT * INTO existing FROM spine.external_references WHERE id = p_id;
    IF FOUND THEN
        IF existing.quote_id IS DISTINCT FROM p_quote OR existing.booking_id IS DISTINCT FROM p_booking
           OR existing.job_id IS DISTINCT FROM p_job OR existing.reference_type IS DISTINCT FROM p_type
           OR existing.source IS DISTINCT FROM p_source OR existing.value IS DISTINCT FROM p_value
           OR existing.actor IS DISTINCT FROM p_actor THEN
            RAISE EXCEPTION 'external reference ID already has different contents' USING ERRCODE = 'SP004';
        END IF;
        RETURN p_id;
    END IF;
    PERFORM spine.require_work_owner(p_quote, p_booking, p_job);
    INSERT INTO spine.external_references (id, quote_id, booking_id, job_id, reference_type, source, value, actor)
    VALUES (p_id, p_quote, p_booking, p_job, p_type, p_source, p_value, p_actor);
    RETURN p_id;
END;
$$;
REVOKE ALL ON spine.external_references FROM PUBLIC;
GRANT SELECT ON spine.external_references TO PUBLIC;
GRANT EXECUTE ON FUNCTION spine.record_external_reference(uuid, uuid, uuid, uuid, text, text, text, text) TO PUBLIC;

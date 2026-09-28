-- Add explicit quote, booking, job and party relationships.

CREATE TABLE spine.quotes (
    id uuid PRIMARY KEY,
    title text NOT NULL CHECK (length(btrim(title)) > 0),
    actor text NOT NULL CHECK (length(btrim(actor)) > 0),
    recorded_at timestamptz NOT NULL DEFAULT clock_timestamp()
);

CREATE TABLE spine.bookings (
    id uuid PRIMARY KEY,
    quote_id uuid NOT NULL REFERENCES spine.quotes,
    title text NOT NULL CHECK (length(btrim(title)) > 0),
    actor text NOT NULL CHECK (length(btrim(actor)) > 0),
    recorded_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
CREATE INDEX ON spine.bookings (quote_id, recorded_at, id);

CREATE TABLE spine.job_booking_links (
    job_id uuid PRIMARY KEY REFERENCES spine.jobs,
    booking_id uuid NOT NULL REFERENCES spine.bookings,
    actor text NOT NULL CHECK (length(btrim(actor)) > 0),
    recorded_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
CREATE INDEX ON spine.job_booking_links (booking_id, recorded_at, job_id);

CREATE TABLE spine.organizations (
    id uuid PRIMARY KEY,
    name text NOT NULL CHECK (length(btrim(name)) > 0),
    actor text NOT NULL CHECK (length(btrim(actor)) > 0),
    recorded_at timestamptz NOT NULL DEFAULT clock_timestamp()
);

CREATE TABLE spine.people (
    id uuid PRIMARY KEY,
    display_name text NOT NULL CHECK (length(btrim(display_name)) > 0),
    actor text NOT NULL CHECK (length(btrim(actor)) > 0),
    recorded_at timestamptz NOT NULL DEFAULT clock_timestamp()
);

CREATE TABLE spine.participations (
    id uuid PRIMARY KEY,
    quote_id uuid REFERENCES spine.quotes,
    booking_id uuid REFERENCES spine.bookings,
    job_id uuid REFERENCES spine.jobs,
    organization_id uuid REFERENCES spine.organizations,
    person_id uuid REFERENCES spine.people,
    role text NOT NULL CHECK (length(btrim(role)) > 0),
    actor text NOT NULL CHECK (length(btrim(actor)) > 0),
    recorded_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CHECK (num_nonnulls(quote_id, booking_id, job_id) = 1),
    CHECK (num_nonnulls(organization_id, person_id) = 1)
);
CREATE INDEX ON spine.participations (quote_id);
CREATE INDEX ON spine.participations (booking_id);
CREATE INDEX ON spine.participations (job_id);

DO $$
DECLARE table_name text;
BEGIN
    FOREACH table_name IN ARRAY ARRAY[
        'quotes', 'bookings', 'job_booking_links',
        'organizations', 'people', 'participations'
    ] LOOP
        EXECUTE format(
            'CREATE TRIGGER append_only BEFORE UPDATE OR DELETE OR TRUNCATE ON spine.%I '
            'FOR EACH STATEMENT EXECUTE FUNCTION spine.refuse_mutation()', table_name);
    END LOOP;
END;
$$;

CREATE FUNCTION spine.create_quote(p_id uuid, p_title text, p_actor text)
RETURNS uuid LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog AS $$
DECLARE existing spine.quotes;
BEGIN
    PERFORM pg_advisory_xact_lock(hashtextextended(p_id::text, 0));
    SELECT * INTO existing FROM spine.quotes WHERE id = p_id;
    IF FOUND THEN
        IF existing.title IS DISTINCT FROM p_title OR existing.actor IS DISTINCT FROM p_actor THEN
            RAISE EXCEPTION 'quote ID already has different contents' USING ERRCODE = 'SP004';
        END IF;
        RETURN p_id;
    END IF;
    IF EXISTS (SELECT 1 FROM spine.bookings WHERE id = p_id) OR
       EXISTS (SELECT 1 FROM spine.jobs WHERE id = p_id) THEN
        RAISE EXCEPTION 'work ID already has another kind' USING ERRCODE = 'SP004';
    END IF;
    INSERT INTO spine.quotes (id, title, actor) VALUES (p_id, p_title, p_actor);
    RETURN p_id;
END;
$$;

CREATE FUNCTION spine.create_booking(
    p_id uuid, p_quote uuid, p_title text, p_actor text
) RETURNS uuid LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog AS $$
DECLARE existing spine.bookings;
BEGIN
    PERFORM pg_advisory_xact_lock(hashtextextended(p_id::text, 0));
    SELECT * INTO existing FROM spine.bookings WHERE id = p_id;
    IF FOUND THEN
        IF existing.quote_id IS DISTINCT FROM p_quote OR existing.title IS DISTINCT FROM p_title
           OR existing.actor IS DISTINCT FROM p_actor THEN
            RAISE EXCEPTION 'booking ID already has different contents' USING ERRCODE = 'SP004';
        END IF;
        RETURN p_id;
    END IF;
    IF EXISTS (SELECT 1 FROM spine.quotes WHERE id = p_id) OR
       EXISTS (SELECT 1 FROM spine.jobs WHERE id = p_id) THEN
        RAISE EXCEPTION 'work ID already has another kind' USING ERRCODE = 'SP004';
    END IF;
    INSERT INTO spine.bookings (id, quote_id, title, actor)
    VALUES (p_id, p_quote, p_title, p_actor);
    RETURN p_id;
END;
$$;

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
    IF EXISTS (SELECT 1 FROM spine.quotes WHERE id = p_id) OR
       EXISTS (SELECT 1 FROM spine.bookings WHERE id = p_id) THEN
        RAISE EXCEPTION 'work ID already has another kind' USING ERRCODE = 'SP004';
    END IF;
    INSERT INTO spine.jobs (id, title, actor) VALUES (p_id, p_title, p_actor);
    RETURN p_id;
END;
$$;

CREATE FUNCTION spine.link_job_booking(p_job uuid, p_booking uuid, p_actor text)
RETURNS uuid LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog AS $$
DECLARE existing spine.job_booking_links;
BEGIN
    PERFORM pg_advisory_xact_lock(hashtextextended(p_job::text, 0));
    SELECT * INTO existing FROM spine.job_booking_links WHERE job_id = p_job;
    IF FOUND THEN
        IF existing.booking_id IS DISTINCT FROM p_booking OR existing.actor IS DISTINCT FROM p_actor THEN
            RAISE EXCEPTION 'job already has a different booking relationship' USING ERRCODE = 'SP004';
        END IF;
        RETURN p_job;
    END IF;
    INSERT INTO spine.job_booking_links (job_id, booking_id, actor)
    VALUES (p_job, p_booking, p_actor);
    RETURN p_job;
END;
$$;

CREATE FUNCTION spine.create_organization(p_id uuid, p_name text, p_actor text)
RETURNS uuid LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog AS $$
DECLARE existing spine.organizations;
BEGIN
    PERFORM pg_advisory_xact_lock(hashtextextended(p_id::text, 0));
    SELECT * INTO existing FROM spine.organizations WHERE id = p_id;
    IF FOUND THEN
        IF existing.name IS DISTINCT FROM p_name OR existing.actor IS DISTINCT FROM p_actor THEN
            RAISE EXCEPTION 'organization ID already has different contents' USING ERRCODE = 'SP004'; END IF;
        RETURN p_id;
    END IF;
    INSERT INTO spine.organizations (id, name, actor) VALUES (p_id, p_name, p_actor);
    RETURN p_id;
END;
$$;

CREATE FUNCTION spine.create_person(p_id uuid, p_name text, p_actor text)
RETURNS uuid LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog AS $$
DECLARE existing spine.people;
BEGIN
    PERFORM pg_advisory_xact_lock(hashtextextended(p_id::text, 0));
    SELECT * INTO existing FROM spine.people WHERE id = p_id;
    IF FOUND THEN
        IF existing.display_name IS DISTINCT FROM p_name OR existing.actor IS DISTINCT FROM p_actor THEN
            RAISE EXCEPTION 'person ID already has different contents' USING ERRCODE = 'SP004'; END IF;
        RETURN p_id;
    END IF;
    INSERT INTO spine.people (id, display_name, actor) VALUES (p_id, p_name, p_actor);
    RETURN p_id;
END;
$$;

CREATE FUNCTION spine.record_participation(
    p_id uuid, p_quote uuid, p_booking uuid, p_job uuid,
    p_organization uuid, p_person uuid, p_role text, p_actor text
) RETURNS uuid LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog AS $$
DECLARE existing spine.participations;
BEGIN
    PERFORM pg_advisory_xact_lock(hashtextextended(p_id::text, 0));
    SELECT * INTO existing FROM spine.participations WHERE id = p_id;
    IF FOUND THEN
        IF existing.quote_id IS DISTINCT FROM p_quote OR existing.booking_id IS DISTINCT FROM p_booking
           OR existing.job_id IS DISTINCT FROM p_job OR existing.organization_id IS DISTINCT FROM p_organization
           OR existing.person_id IS DISTINCT FROM p_person OR existing.role IS DISTINCT FROM p_role
           OR existing.actor IS DISTINCT FROM p_actor THEN
            RAISE EXCEPTION 'participation ID already has different contents' USING ERRCODE = 'SP004';
        END IF;
        RETURN p_id;
    END IF;
    INSERT INTO spine.participations (id, quote_id, booking_id, job_id, organization_id, person_id, role, actor)
    VALUES (p_id, p_quote, p_booking, p_job, p_organization, p_person, p_role, p_actor);
    RETURN p_id;
END;
$$;

REVOKE ALL ON spine.quotes, spine.bookings, spine.job_booking_links,
    spine.organizations, spine.people, spine.participations FROM PUBLIC;
GRANT SELECT ON spine.quotes, spine.bookings, spine.job_booking_links,
    spine.organizations, spine.people, spine.participations TO PUBLIC;
GRANT EXECUTE ON FUNCTION spine.create_quote(uuid, text, text),
    spine.create_booking(uuid, uuid, text, text), spine.link_job_booking(uuid, uuid, text),
    spine.create_organization(uuid, text, text), spine.create_person(uuid, text, text),
    spine.record_participation(uuid, uuid, uuid, uuid, uuid, uuid, text, text) TO PUBLIC;

-- Party kinds, one operator organization, and append-only affiliations.
-- Nothing here rewrites an existing business row. The two added columns use
-- defaults, which is allowed only because each default states the meaning old
-- rows already had: every person recorded before this migration was a person,
-- and no organization had been named the operator.

ALTER TABLE spine.people
    ADD COLUMN kind text NOT NULL DEFAULT 'person'
    CONSTRAINT people_kind_check CHECK (kind IN ('person', 'agent'));

ALTER TABLE spine.organizations
    ADD COLUMN is_operator boolean NOT NULL DEFAULT false;

-- At most one organization runs this ledger.
CREATE UNIQUE INDEX organizations_single_operator
    ON spine.organizations (is_operator) WHERE is_operator;

-- A person or agent belongs to an organization for a period. An end is
-- recorded as a replacement row, so a chain of rows never loses its history.
CREATE TABLE spine.affiliations (
    id uuid PRIMARY KEY,
    person_id uuid NOT NULL REFERENCES spine.people,
    organization_id uuid NOT NULL REFERENCES spine.organizations,
    role text NOT NULL CHECK (length(btrim(role)) > 0),
    started_on date NOT NULL,
    ended_on date,
    replaces_affiliation_id uuid UNIQUE REFERENCES spine.affiliations,
    actor text NOT NULL CHECK (length(btrim(actor)) > 0),
    recorded_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT affiliations_period_check CHECK (ended_on IS NULL OR ended_on >= started_on)
);
CREATE INDEX ON spine.affiliations (person_id, started_on, id);
CREATE INDEX ON spine.affiliations (organization_id, started_on, id);
CREATE TRIGGER append_only BEFORE UPDATE OR DELETE OR TRUNCATE
ON spine.affiliations FOR EACH STATEMENT EXECUTE FUNCTION spine.refuse_mutation();

-- The three-argument creation functions are replaced by four-argument ones
-- whose last argument has a default. An extra overload would make an old
-- three-argument call ambiguous, so the old signature is dropped instead.
-- Existing callers keep working and record exactly what they recorded before.
DROP FUNCTION spine.create_person(uuid, text, text);
CREATE FUNCTION spine.create_person(
    p_id uuid, p_name text, p_actor text, p_kind text DEFAULT 'person'
) RETURNS uuid LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog AS $$
DECLARE existing spine.people;
BEGIN
    PERFORM pg_advisory_xact_lock(hashtextextended(p_id::text, 0));
    SELECT * INTO existing FROM spine.people WHERE id = p_id;
    IF FOUND THEN
        IF existing.display_name IS DISTINCT FROM p_name
           OR existing.actor IS DISTINCT FROM p_actor
           OR existing.kind IS DISTINCT FROM p_kind THEN
            RAISE EXCEPTION 'person ID already has different contents' USING ERRCODE = 'SP004';
        END IF;
        RETURN p_id;
    END IF;
    INSERT INTO spine.people (id, display_name, actor, kind)
    VALUES (p_id, p_name, p_actor, p_kind);
    RETURN p_id;
END;
$$;

DROP FUNCTION spine.create_organization(uuid, text, text);
CREATE FUNCTION spine.create_organization(
    p_id uuid, p_name text, p_actor text, p_is_operator boolean DEFAULT false
) RETURNS uuid LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog AS $$
DECLARE existing spine.organizations;
BEGIN
    PERFORM pg_advisory_xact_lock(hashtextextended(p_id::text, 0));
    SELECT * INTO existing FROM spine.organizations WHERE id = p_id;
    IF FOUND THEN
        IF existing.name IS DISTINCT FROM p_name
           OR existing.actor IS DISTINCT FROM p_actor
           OR existing.is_operator IS DISTINCT FROM p_is_operator THEN
            RAISE EXCEPTION 'organization ID already has different contents' USING ERRCODE = 'SP004';
        END IF;
        RETURN p_id;
    END IF;
    IF p_is_operator AND EXISTS (
        SELECT 1 FROM spine.organizations WHERE is_operator AND id <> p_id
    ) THEN
        RAISE EXCEPTION 'another organization is already the operator' USING ERRCODE = 'SP010';
    END IF;
    INSERT INTO spine.organizations (id, name, actor, is_operator)
    VALUES (p_id, p_name, p_actor, p_is_operator);
    RETURN p_id;
END;
$$;

CREATE FUNCTION spine.record_affiliation(
    p_id uuid, p_person uuid, p_organization uuid, p_role text,
    p_started_on date, p_ended_on date, p_actor text
) RETURNS uuid LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog AS $$
DECLARE existing spine.affiliations;
BEGIN
    PERFORM pg_advisory_xact_lock(hashtextextended(p_id::text, 0));
    SELECT * INTO existing FROM spine.affiliations WHERE id = p_id;
    IF FOUND THEN
        IF existing.person_id IS DISTINCT FROM p_person
           OR existing.organization_id IS DISTINCT FROM p_organization
           OR existing.role IS DISTINCT FROM p_role
           OR existing.started_on IS DISTINCT FROM p_started_on
           OR existing.ended_on IS DISTINCT FROM p_ended_on
           OR existing.replaces_affiliation_id IS NOT NULL
           OR existing.actor IS DISTINCT FROM p_actor THEN
            RAISE EXCEPTION 'affiliation ID already has different contents' USING ERRCODE = 'SP009';
        END IF;
        RETURN p_id;
    END IF;
    INSERT INTO spine.affiliations (
        id, person_id, organization_id, role, started_on, ended_on, actor
    ) VALUES (p_id, p_person, p_organization, p_role, p_started_on, p_ended_on, p_actor);
    RETURN p_id;
END;
$$;

-- Ending an affiliation writes a new row that replaces the earlier one. The
-- earlier row stays exactly as it was; reads take the latest row of the chain.
CREATE FUNCTION spine.end_affiliation(
    p_id uuid, p_affiliation uuid, p_ended_on date, p_actor text
) RETURNS uuid LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog AS $$
DECLARE existing spine.affiliations;
DECLARE earlier spine.affiliations;
BEGIN
    PERFORM pg_advisory_xact_lock(hashtextextended(p_id::text, 0));
    SELECT * INTO existing FROM spine.affiliations WHERE id = p_id;
    IF FOUND THEN
        IF existing.replaces_affiliation_id IS DISTINCT FROM p_affiliation
           OR existing.ended_on IS DISTINCT FROM p_ended_on
           OR existing.actor IS DISTINCT FROM p_actor THEN
            RAISE EXCEPTION 'affiliation ID already has different contents' USING ERRCODE = 'SP009';
        END IF;
        RETURN p_id;
    END IF;
    SELECT * INTO earlier FROM spine.affiliations WHERE id = p_affiliation;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'affiliation to end does not exist' USING ERRCODE = 'SP011';
    END IF;
    IF earlier.ended_on IS NOT NULL OR EXISTS (
        SELECT 1 FROM spine.affiliations WHERE replaces_affiliation_id = p_affiliation
    ) THEN
        RAISE EXCEPTION 'affiliation is already ended or replaced' USING ERRCODE = 'SP011';
    END IF;
    INSERT INTO spine.affiliations (
        id, person_id, organization_id, role, started_on, ended_on,
        replaces_affiliation_id, actor
    ) VALUES (p_id, earlier.person_id, earlier.organization_id, earlier.role,
              earlier.started_on, p_ended_on, p_affiliation, p_actor);
    RETURN p_id;
END;
$$;

REVOKE ALL ON spine.affiliations FROM PUBLIC;
GRANT SELECT ON spine.affiliations TO PUBLIC;
GRANT EXECUTE ON FUNCTION spine.create_person(uuid, text, text, text),
    spine.create_organization(uuid, text, text, boolean),
    spine.record_affiliation(uuid, uuid, uuid, text, date, date, text),
    spine.end_affiliation(uuid, uuid, date, text) TO PUBLIC;

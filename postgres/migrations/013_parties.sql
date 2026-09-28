-- The party cluster folds from four tables to three.
--
--   parties            one row per person, agent or organization
--   party_identifiers  one row per email, phone, address or alias a party was seen under
--   roles              one row per claim that a party holds a role on another
--                      party (a standing role) or on a quote, booking or job
--                      (a chain role), with the evidence that supports it
--
-- Every row of people, organizations, affiliations and participations is
-- copied into the new tables unchanged: same id, same actor, same recorded
-- time. An affiliation that had ended (an ending row, or one recorded with
-- its end date) is copied as confidence former; every other copied row is
-- confirmed. The copy is compared field by field with the source before the
-- old tables go. Nothing about the append-only rule changes: a role ends or
-- changes by a new row that replaces the earlier one, and the earlier row
-- stays exactly as it was.
--
-- One narrowing: people and organizations shared no id space before, so one
-- uuid could name a person and an organization. Parties is one table, so
-- the second create of a reused id is refused with SP004.
--
-- The old write functions keep their names and signatures and write into the
-- new tables, so an earlier caller records the same thing it always did.
-- New callers use create_party, record_party_identifier, record_role and
-- end_role, which carry what the old ones could not: the citing evidence, a
-- confidence, and the review the claim was made in.

CREATE TABLE spine.parties (
    id uuid PRIMARY KEY,
    kind text NOT NULL CONSTRAINT parties_kind_check CHECK (kind IN ('person', 'agent', 'organization')),
    name text NOT NULL CHECK (length(btrim(name)) > 0),
    is_operator boolean NOT NULL DEFAULT false,
    actor text NOT NULL CHECK (length(btrim(actor)) > 0),
    recorded_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT parties_operator_is_organization CHECK (NOT is_operator OR kind = 'organization')
);
-- At most one party runs this ledger.
CREATE UNIQUE INDEX parties_single_operator ON spine.parties (is_operator) WHERE is_operator;

CREATE TABLE spine.party_identifiers (
    id uuid PRIMARY KEY,
    party_id uuid NOT NULL REFERENCES spine.parties,
    kind text NOT NULL CONSTRAINT party_identifiers_kind_check CHECK (kind IN ('email', 'phone', 'address', 'alias')),
    value text NOT NULL CHECK (length(btrim(value)) > 0),
    evidence_id uuid REFERENCES spine.evidence,
    actor text NOT NULL CHECK (length(btrim(actor)) > 0),
    recorded_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
CREATE INDEX ON spine.party_identifiers (party_id, recorded_at, id);
CREATE INDEX ON spine.party_identifiers (kind, lower(value));

CREATE TABLE spine.roles (
    id uuid PRIMARY KEY,
    party_id uuid NOT NULL REFERENCES spine.parties,
    on_party_id uuid REFERENCES spine.parties,
    quote_id uuid REFERENCES spine.quotes,
    booking_id uuid REFERENCES spine.bookings,
    job_id uuid REFERENCES spine.jobs,
    role text NOT NULL CHECK (length(btrim(role)) > 0),
    -- confirmed: the evidence says so. mentioned: named, part unclear.
    -- former: held once, not now (an ending row).
    confidence text NOT NULL DEFAULT 'confirmed'
        CONSTRAINT roles_confidence_check CHECK (confidence IN ('confirmed', 'mentioned', 'former')),
    evidence_id uuid REFERENCES spine.evidence,
    started_on date,
    ended_on date,
    replaces_role_id uuid UNIQUE REFERENCES spine.roles,
    actor text NOT NULL CHECK (length(btrim(actor)) > 0),
    recorded_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT roles_one_target CHECK (num_nonnulls(on_party_id, quote_id, booking_id, job_id) = 1),
    CONSTRAINT roles_not_on_self CHECK (on_party_id IS NULL OR on_party_id <> party_id),
    CONSTRAINT roles_period_check CHECK (ended_on IS NULL OR started_on IS NULL OR ended_on >= started_on)
);
CREATE INDEX ON spine.roles (party_id, recorded_at, id);
CREATE INDEX ON spine.roles (on_party_id, recorded_at, id);
CREATE INDEX ON spine.roles (quote_id, recorded_at, id);
CREATE INDEX ON spine.roles (booking_id, recorded_at, id);
CREATE INDEX ON spine.roles (job_id, recorded_at, id);

-- Which review made a role claim, the way visit_memo_judgments ties a
-- judgment to its review.
CREATE TABLE spine.visit_memo_roles (
    memo_id uuid NOT NULL REFERENCES spine.visit_memos,
    role_id uuid NOT NULL REFERENCES spine.roles,
    PRIMARY KEY (memo_id, role_id)
);
CREATE INDEX ON spine.visit_memo_roles (role_id);

DO $$
DECLARE table_name text;
BEGIN
    FOREACH table_name IN ARRAY ARRAY['parties', 'party_identifiers', 'roles', 'visit_memo_roles'] LOOP
        EXECUTE format(
            'CREATE TRIGGER append_only BEFORE UPDATE OR DELETE OR TRUNCATE ON spine.%I '
            'FOR EACH STATEMENT EXECUTE FUNCTION spine.refuse_mutation()', table_name);
    END LOOP;
END;
$$;

-- The copy. Ids, actors and recorded times are kept, so every earlier
-- reference to a person, organization, affiliation or participation id still
-- names the same row.
INSERT INTO spine.parties (id, kind, name, is_operator, actor, recorded_at)
SELECT id, kind, display_name, false, actor, recorded_at FROM spine.people
UNION ALL
SELECT id, 'organization', name, is_operator, actor, recorded_at FROM spine.organizations;

INSERT INTO spine.roles (id, party_id, on_party_id, role, confidence, started_on, ended_on,
                         replaces_role_id, actor, recorded_at)
SELECT id, person_id, organization_id, role,
       CASE WHEN ended_on IS NOT NULL OR replaces_affiliation_id IS NOT NULL
            THEN 'former' ELSE 'confirmed' END,
       started_on, ended_on, replaces_affiliation_id, actor, recorded_at
FROM spine.affiliations;

INSERT INTO spine.roles (id, party_id, quote_id, booking_id, job_id, role, actor, recorded_at)
SELECT id, coalesce(person_id, organization_id), quote_id, booking_id, job_id, role, actor, recorded_at
FROM spine.participations;

-- The copy is checked by content, not by count: the same tuples, in id
-- order, on both sides.
DO $$
DECLARE old_parties text; new_parties text; old_roles text; new_roles text;
BEGIN
    SELECT string_agg(concat_ws('|', id, kind, name, is_operator, actor, recorded_at), E'\n' ORDER BY id)
    INTO old_parties FROM (
        SELECT id, kind, display_name AS name, false AS is_operator, actor, recorded_at FROM spine.people
        UNION ALL
        SELECT id, 'organization', name, is_operator, actor, recorded_at FROM spine.organizations) src;
    SELECT string_agg(concat_ws('|', id, kind, name, is_operator, actor, recorded_at), E'\n' ORDER BY id)
    INTO new_parties FROM spine.parties;
    SELECT string_agg(concat_ws('|', id, party_id, on_party_id, quote_id, booking_id, job_id, role,
                                confidence, evidence_id, started_on, ended_on, replaces_role_id,
                                actor, recorded_at), E'\n' ORDER BY id)
    INTO old_roles FROM (
        SELECT id, person_id AS party_id, organization_id AS on_party_id,
               NULL::uuid AS quote_id, NULL::uuid AS booking_id, NULL::uuid AS job_id, role,
               CASE WHEN ended_on IS NOT NULL OR replaces_affiliation_id IS NOT NULL
                    THEN 'former' ELSE 'confirmed' END AS confidence,
               NULL::uuid AS evidence_id, started_on, ended_on,
               replaces_affiliation_id AS replaces_role_id, actor, recorded_at
        FROM spine.affiliations
        UNION ALL
        SELECT id, coalesce(person_id, organization_id), NULL, quote_id, booking_id, job_id, role,
               'confirmed', NULL, NULL, NULL, NULL, actor, recorded_at
        FROM spine.participations) src;
    SELECT string_agg(concat_ws('|', id, party_id, on_party_id, quote_id, booking_id, job_id, role,
                                confidence, evidence_id, started_on, ended_on, replaces_role_id,
                                actor, recorded_at), E'\n' ORDER BY id)
    INTO new_roles FROM spine.roles;
    IF old_parties IS DISTINCT FROM new_parties OR old_roles IS DISTINCT FROM new_roles THEN
        RAISE EXCEPTION 'party copy differs from its source';
    END IF;
END;
$$;

DROP FUNCTION spine.create_person(uuid, text, text, text);
DROP FUNCTION spine.create_organization(uuid, text, text, boolean);
DROP FUNCTION spine.record_participation(uuid, uuid, uuid, uuid, uuid, uuid, text, text);
DROP FUNCTION spine.record_affiliation(uuid, uuid, uuid, text, date, date, text);
DROP FUNCTION spine.end_affiliation(uuid, uuid, date, text);
DROP TABLE spine.participations;
DROP TABLE spine.affiliations;
DROP TABLE spine.people;
DROP TABLE spine.organizations;

CREATE FUNCTION spine.create_party(
    p_id uuid, p_kind text, p_name text, p_actor text, p_is_operator boolean DEFAULT false
) RETURNS uuid LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog AS $$
DECLARE existing spine.parties;
BEGIN
    PERFORM pg_advisory_xact_lock(hashtextextended(p_id::text, 0));
    SELECT * INTO existing FROM spine.parties WHERE id = p_id;
    IF FOUND THEN
        IF existing.kind IS DISTINCT FROM p_kind OR existing.name IS DISTINCT FROM p_name
           OR existing.actor IS DISTINCT FROM p_actor
           OR existing.is_operator IS DISTINCT FROM p_is_operator THEN
            RAISE EXCEPTION 'party ID already has different contents' USING ERRCODE = 'SP004';
        END IF;
        RETURN p_id;
    END IF;
    IF p_is_operator AND EXISTS (SELECT 1 FROM spine.parties WHERE is_operator AND id <> p_id) THEN
        RAISE EXCEPTION 'another party is already the operator' USING ERRCODE = 'SP010';
    END IF;
    INSERT INTO spine.parties (id, kind, name, is_operator, actor)
    VALUES (p_id, p_kind, p_name, p_is_operator, p_actor);
    RETURN p_id;
END;
$$;

CREATE FUNCTION spine.record_party_identifier(
    p_id uuid, p_party uuid, p_kind text, p_value text, p_evidence uuid, p_actor text
) RETURNS uuid LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog AS $$
DECLARE existing spine.party_identifiers;
BEGIN
    PERFORM pg_advisory_xact_lock(hashtextextended(p_id::text, 0));
    SELECT * INTO existing FROM spine.party_identifiers WHERE id = p_id;
    IF FOUND THEN
        IF existing.party_id IS DISTINCT FROM p_party OR existing.kind IS DISTINCT FROM p_kind
           OR existing.value IS DISTINCT FROM p_value OR existing.evidence_id IS DISTINCT FROM p_evidence
           OR existing.actor IS DISTINCT FROM p_actor THEN
            RAISE EXCEPTION 'identifier ID already has different contents' USING ERRCODE = 'SP004';
        END IF;
        RETURN p_id;
    END IF;
    INSERT INTO spine.party_identifiers (id, party_id, kind, value, evidence_id, actor)
    VALUES (p_id, p_party, p_kind, p_value, p_evidence, p_actor);
    RETURN p_id;
END;
$$;

-- The review a role claim was made in. A retry with the same memo is a
-- no-op; a retry naming a different review is a different claim.
CREATE FUNCTION spine.link_role_memo(p_role uuid, p_memo uuid)
RETURNS void LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog AS $$
BEGIN
    IF p_memo IS NULL THEN
        RETURN;
    END IF;
    IF EXISTS (SELECT 1 FROM spine.visit_memo_roles WHERE role_id = p_role AND memo_id <> p_memo) THEN
        RAISE EXCEPTION 'role ID already belongs to a different review' USING ERRCODE = 'SP009';
    END IF;
    INSERT INTO spine.visit_memo_roles (memo_id, role_id) VALUES (p_memo, p_role)
    ON CONFLICT DO NOTHING;
END;
$$;

-- One claim: p_party holds p_role on exactly one of p_on_party, p_quote,
-- p_booking, p_job. p_memo, when given, ties the claim to the review that
-- made it.
CREATE FUNCTION spine.record_role(
    p_id uuid, p_party uuid, p_on_party uuid, p_quote uuid, p_booking uuid, p_job uuid,
    p_role text, p_confidence text, p_evidence uuid, p_started_on date, p_ended_on date,
    p_actor text, p_memo uuid DEFAULT NULL
) RETURNS uuid LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog AS $$
DECLARE existing spine.roles;
BEGIN
    PERFORM pg_advisory_xact_lock(hashtextextended(p_id::text, 0));
    SELECT * INTO existing FROM spine.roles WHERE id = p_id;
    IF FOUND THEN
        IF existing.party_id IS DISTINCT FROM p_party OR existing.on_party_id IS DISTINCT FROM p_on_party
           OR existing.quote_id IS DISTINCT FROM p_quote OR existing.booking_id IS DISTINCT FROM p_booking
           OR existing.job_id IS DISTINCT FROM p_job OR existing.role IS DISTINCT FROM p_role
           OR existing.confidence IS DISTINCT FROM p_confidence
           OR existing.evidence_id IS DISTINCT FROM p_evidence
           OR existing.started_on IS DISTINCT FROM p_started_on
           OR existing.ended_on IS DISTINCT FROM p_ended_on
           OR existing.replaces_role_id IS NOT NULL
           OR existing.actor IS DISTINCT FROM p_actor THEN
            RAISE EXCEPTION 'role ID already has different contents' USING ERRCODE = 'SP009';
        END IF;
        PERFORM spine.link_role_memo(p_id, p_memo);
        RETURN p_id;
    END IF;
    INSERT INTO spine.roles (id, party_id, on_party_id, quote_id, booking_id, job_id, role,
                             confidence, evidence_id, started_on, ended_on, actor)
    VALUES (p_id, p_party, p_on_party, p_quote, p_booking, p_job, p_role,
            p_confidence, p_evidence, p_started_on, p_ended_on, p_actor);
    PERFORM spine.link_role_memo(p_id, p_memo);
    RETURN p_id;
END;
$$;

-- Ending a role appends a replacement row marked former. The earlier row
-- stays exactly as it was; reads take the latest row of the chain.
CREATE FUNCTION spine.end_role(
    p_id uuid, p_role uuid, p_ended_on date, p_actor text,
    p_evidence uuid DEFAULT NULL, p_memo uuid DEFAULT NULL
) RETURNS uuid LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog AS $$
DECLARE existing spine.roles;
DECLARE earlier spine.roles;
BEGIN
    PERFORM pg_advisory_xact_lock(hashtextextended(p_id::text, 0));
    SELECT * INTO existing FROM spine.roles WHERE id = p_id;
    IF FOUND THEN
        IF existing.replaces_role_id IS DISTINCT FROM p_role
           OR existing.ended_on IS DISTINCT FROM p_ended_on
           OR existing.evidence_id IS DISTINCT FROM p_evidence
           OR existing.actor IS DISTINCT FROM p_actor THEN
            RAISE EXCEPTION 'role ID already has different contents' USING ERRCODE = 'SP009';
        END IF;
        PERFORM spine.link_role_memo(p_id, p_memo);
        RETURN p_id;
    END IF;
    SELECT * INTO earlier FROM spine.roles WHERE id = p_role;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'role to end does not exist' USING ERRCODE = 'SP011';
    END IF;
    IF earlier.confidence = 'former' OR earlier.ended_on IS NOT NULL OR EXISTS (
        SELECT 1 FROM spine.roles WHERE replaces_role_id = p_role
    ) THEN
        RAISE EXCEPTION 'role is already ended or replaced' USING ERRCODE = 'SP011';
    END IF;
    INSERT INTO spine.roles (id, party_id, on_party_id, quote_id, booking_id, job_id, role,
                             confidence, evidence_id, started_on, ended_on, replaces_role_id, actor)
    VALUES (p_id, earlier.party_id, earlier.on_party_id, earlier.quote_id, earlier.booking_id,
            earlier.job_id, earlier.role, 'former', p_evidence, earlier.started_on, p_ended_on,
            p_role, p_actor);
    PERFORM spine.link_role_memo(p_id, p_memo);
    RETURN p_id;
END;
$$;

-- The earlier write functions, same names and signatures, now writing into
-- the new tables. An earlier caller records what it always recorded.
CREATE FUNCTION spine.create_person(p_id uuid, p_name text, p_actor text, p_kind text DEFAULT 'person')
RETURNS uuid LANGUAGE sql SECURITY DEFINER SET search_path = pg_catalog AS $$
    SELECT spine.create_party(p_id, p_kind, p_name, p_actor, false);
$$;
CREATE FUNCTION spine.create_organization(p_id uuid, p_name text, p_actor text, p_is_operator boolean DEFAULT false)
RETURNS uuid LANGUAGE sql SECURITY DEFINER SET search_path = pg_catalog AS $$
    SELECT spine.create_party(p_id, 'organization', p_name, p_actor, p_is_operator);
$$;
CREATE FUNCTION spine.record_participation(
    p_id uuid, p_quote uuid, p_booking uuid, p_job uuid,
    p_organization uuid, p_person uuid, p_role text, p_actor text
) RETURNS uuid LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog AS $$
BEGIN
    IF num_nonnulls(p_organization, p_person) <> 1 THEN
        RAISE EXCEPTION 'a participation names exactly one of an organization or a person'
            USING ERRCODE = '23514';
    END IF;
    RETURN spine.record_role(p_id, coalesce(p_person, p_organization), NULL, p_quote, p_booking, p_job,
                             p_role, 'confirmed', NULL, NULL, NULL, p_actor, NULL);
END;
$$;
CREATE FUNCTION spine.record_affiliation(
    p_id uuid, p_person uuid, p_organization uuid, p_role text,
    p_started_on date, p_ended_on date, p_actor text
) RETURNS uuid LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog AS $$
BEGIN
    IF p_started_on IS NULL THEN
        RAISE EXCEPTION 'an affiliation needs started_on' USING ERRCODE = '23502';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM spine.parties WHERE id = p_person AND kind IN ('person', 'agent'))
       OR NOT EXISTS (SELECT 1 FROM spine.parties WHERE id = p_organization AND kind = 'organization') THEN
        RAISE EXCEPTION 'an affiliation links a person or agent to an organization'
            USING ERRCODE = '23503';
    END IF;
    RETURN spine.record_role(p_id, p_person, p_organization, NULL, NULL, NULL,
                             p_role, CASE WHEN p_ended_on IS NULL THEN 'confirmed' ELSE 'former' END,
                             NULL, p_started_on, p_ended_on, p_actor, NULL);
END;
$$;
CREATE FUNCTION spine.end_affiliation(p_id uuid, p_affiliation uuid, p_ended_on date, p_actor text)
RETURNS uuid LANGUAGE sql SECURITY DEFINER SET search_path = pg_catalog AS $$
    SELECT spine.end_role(p_id, p_affiliation, p_ended_on, p_actor, NULL, NULL);
$$;

REVOKE ALL ON spine.parties, spine.party_identifiers, spine.roles, spine.visit_memo_roles FROM PUBLIC;
GRANT SELECT ON spine.parties, spine.party_identifiers, spine.roles, spine.visit_memo_roles TO PUBLIC;
GRANT EXECUTE ON FUNCTION
    spine.create_party(uuid, text, text, text, boolean),
    spine.record_party_identifier(uuid, uuid, text, text, uuid, text),
    spine.record_role(uuid, uuid, uuid, uuid, uuid, uuid, text, text, uuid, date, date, text, uuid),
    spine.end_role(uuid, uuid, date, text, uuid, uuid),
    spine.create_person(uuid, text, text, text),
    spine.create_organization(uuid, text, text, boolean),
    spine.record_participation(uuid, uuid, uuid, uuid, uuid, uuid, text, text),
    spine.record_affiliation(uuid, uuid, uuid, text, date, date, text),
    spine.end_affiliation(uuid, uuid, date, text)
TO PUBLIC;
REVOKE ALL ON FUNCTION spine.link_role_memo(uuid, uuid) FROM PUBLIC;

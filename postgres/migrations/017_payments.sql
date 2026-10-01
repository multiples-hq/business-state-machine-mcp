-- Money, part two: what was paid. Two new tables; no existing table changes.
--
--   payments             money that moved from one party to another.
--   payment_allocations  a payment, or part of it, put on a charge or on a
--                        bill, with or without lines.
--
-- Same patterns as 016: rows are only added, a correction names the row it
-- replaces, payment and allocation amounts are zero or more. "A payment"
-- means its chain of corrections; allocations follow it. Any payment may go
-- on any charge or bill: the payment itself says who paid and who received.
--
-- Hard rules, refused below:
--   SP015  the allocations of a payment add up to more than the payment
--   SP016  a payment and what it goes on differ in currency, or a charge's,
--          payment's or reissued bill's currency changes while money is on
--          it (the bill's check is in 016's record_invoice)

CREATE TABLE spine.payments (
    id uuid PRIMARY KEY,
    from_party_id uuid NOT NULL REFERENCES spine.parties,
    to_party_id uuid NOT NULL REFERENCES spine.parties,
    amount numeric NOT NULL,
    currency text NOT NULL CONSTRAINT payments_currency_check CHECK (currency ~ '^[A-Z]{3}$'),
    home_amount numeric,
    home_currency text CONSTRAINT payments_home_currency_check CHECK (home_currency ~ '^[A-Z]{3}$'),
    paid_on date,
    reference text CONSTRAINT payments_reference_check CHECK (reference IS NULL OR length(btrim(reference)) > 0),
    method text CONSTRAINT payments_method_check CHECK (method IS NULL OR length(btrim(method)) > 0),
    replaces_payment_id uuid CONSTRAINT payments_one_successor UNIQUE REFERENCES spine.payments,
    reason text NOT NULL CHECK (length(btrim(reason)) > 0),
    evidence_id uuid NOT NULL REFERENCES spine.evidence,
    actor text NOT NULL CHECK (length(btrim(actor)) > 0),
    recorded_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT payments_parties_differ CHECK (from_party_id <> to_party_id),
    CONSTRAINT payments_home_needs_currency CHECK ((home_amount IS NULL) = (home_currency IS NULL)),
    CONSTRAINT payments_amounts_check CHECK (amount NOT IN ('NaN', 'Infinity') AND amount >= 0
        AND (home_amount IS NULL OR (home_amount NOT IN ('NaN', 'Infinity') AND home_amount >= 0))),
    CONSTRAINT payments_not_self CHECK (replaces_payment_id <> id)
);
CREATE INDEX ON spine.payments (from_party_id);
CREATE INDEX ON spine.payments (to_party_id);

CREATE TABLE spine.payment_allocations (
    id uuid PRIMARY KEY,
    payment_id uuid NOT NULL REFERENCES spine.payments,
    milestone_id uuid REFERENCES spine.milestones,
    invoice_id uuid REFERENCES spine.invoices,
    amount numeric NOT NULL,
    replaces_allocation_id uuid CONSTRAINT payment_allocations_one_successor UNIQUE
        REFERENCES spine.payment_allocations,
    reason text NOT NULL CHECK (length(btrim(reason)) > 0),
    evidence_id uuid NOT NULL REFERENCES spine.evidence,
    actor text NOT NULL CHECK (length(btrim(actor)) > 0),
    recorded_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT payment_allocations_one_target CHECK (num_nonnulls(milestone_id, invoice_id) = 1),
    CONSTRAINT payment_allocations_amount_check CHECK (amount NOT IN ('NaN', 'Infinity') AND amount >= 0),
    CONSTRAINT payment_allocations_not_self CHECK (replaces_allocation_id <> id)
);
CREATE INDEX ON spine.payment_allocations (payment_id);
CREATE INDEX ON spine.payment_allocations (milestone_id);
CREATE INDEX ON spine.payment_allocations (invoice_id);

DO $$
DECLARE table_name text;
BEGIN
    FOREACH table_name IN ARRAY ARRAY['payments', 'payment_allocations'] LOOP
        EXECUTE format(
            'CREATE TRIGGER append_only BEFORE UPDATE OR DELETE OR TRUNCATE ON spine.%I '
            'FOR EACH STATEMENT EXECUTE FUNCTION spine.refuse_mutation()', table_name);
    END LOOP;
END;
$$;

-- The first version of the payment chain one version belongs to.
CREATE FUNCTION spine.payment_root(p_id uuid) RETURNS uuid
LANGUAGE sql STABLE SET search_path = pg_catalog AS $$
    WITH RECURSIVE up(id, replaces) AS (
        SELECT id, replaces_payment_id FROM spine.payments WHERE id = p_id
        UNION ALL
        SELECT p.id, p.replaces_payment_id FROM spine.payments p JOIN up ON p.id = up.replaces)
    SELECT id FROM up WHERE replaces IS NULL
$$;

-- One payment version. Same retry rule. A correction may name another payer,
-- receiver or currency; the currency only while no money of the payment is
-- put anywhere, so allocations never mix currencies.
CREATE FUNCTION spine.record_payment(
    p_id uuid, p_from uuid, p_to uuid, p_amount numeric, p_currency text,
    p_home_amount numeric, p_home_currency text, p_paid_on date, p_reference text, p_method text,
    p_replaces uuid, p_reason text, p_evidence uuid, p_actor text
) RETURNS uuid LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog AS $$
DECLARE existing spine.payments; other spine.payments;
BEGIN
    PERFORM pg_advisory_xact_lock(hashtextextended(p_id::text, 0));
    SELECT * INTO existing FROM spine.payments WHERE id = p_id;
    IF FOUND THEN
        IF existing.from_party_id IS DISTINCT FROM p_from OR existing.to_party_id IS DISTINCT FROM p_to
           OR existing.amount IS DISTINCT FROM p_amount OR existing.currency IS DISTINCT FROM p_currency
           OR existing.home_amount IS DISTINCT FROM p_home_amount
           OR existing.home_currency IS DISTINCT FROM p_home_currency
           OR existing.paid_on IS DISTINCT FROM p_paid_on OR existing.reference IS DISTINCT FROM p_reference
           OR existing.method IS DISTINCT FROM p_method
           OR existing.replaces_payment_id IS DISTINCT FROM p_replaces
           OR existing.reason IS DISTINCT FROM p_reason OR existing.evidence_id IS DISTINCT FROM p_evidence
           OR existing.actor IS DISTINCT FROM p_actor THEN
            RAISE EXCEPTION 'payment ID already has different contents' USING ERRCODE = 'SP004';
        END IF;
        RETURN p_id;
    END IF;
    IF p_replaces IS NOT NULL THEN
        SELECT * INTO other FROM spine.payments WHERE id = p_replaces;
        IF NOT FOUND THEN
            RAISE EXCEPTION 'the payment to replace does not exist' USING ERRCODE = '23503';
        END IF;
        PERFORM 1 FROM spine.payments WHERE id = spine.payment_root(p_replaces) FOR UPDATE;
        IF EXISTS (SELECT 1 FROM spine.payments WHERE replaces_payment_id = p_replaces) THEN
            RAISE EXCEPTION 'that payment is already replaced; replace its latest version'
                USING ERRCODE = 'SP011';
        END IF;
        IF other.currency <> p_currency AND EXISTS (
                WITH RECURSIVE chain(id) AS (
                    SELECT spine.payment_root(p_replaces) UNION ALL
                    SELECT p.id FROM spine.payments p JOIN chain c ON p.replaces_payment_id = c.id)
                SELECT 1 FROM spine.payment_allocations a
                WHERE a.payment_id IN (SELECT id FROM chain) AND a.amount > 0
                  AND NOT EXISTS (SELECT 1 FROM spine.payment_allocations n
                                  WHERE n.replaces_allocation_id = a.id)) THEN
            RAISE EXCEPTION 'the payment is in % and what it goes on is in %: currencies are never mixed; lower its allocations to 0 first, then correct the currency',
                p_currency, other.currency USING ERRCODE = 'SP016';
        END IF;
    END IF;
    INSERT INTO spine.payments (id, from_party_id, to_party_id, amount, currency, home_amount,
                                home_currency, paid_on, reference, method, replaces_payment_id,
                                reason, evidence_id, actor)
    VALUES (p_id, p_from, p_to, p_amount, p_currency, p_home_amount, p_home_currency, p_paid_on,
            p_reference, p_method, p_replaces, p_reason, p_evidence, p_actor);
    RETURN p_id;
END;
$$;

-- One allocation: a payment, or part of it, put on a charge or on a bill.
-- "A payment" means its chain: an allocation may name any version, and
-- allocations follow a replaced payment; the latest version's currency counts.
-- A replacing allocation may name another target of the same payment. The
-- payment chain's first row is locked FOR UPDATE until commit, so two calls
-- allocating the same payment take turns; the total is checked at commit
-- (payment_cap).
CREATE FUNCTION spine.record_payment_allocation(
    p_id uuid, p_payment uuid, p_milestone uuid, p_invoice uuid, p_amount numeric,
    p_replaces uuid, p_reason text, p_evidence uuid, p_actor text
) RETURNS uuid LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog AS $$
DECLARE existing spine.payment_allocations; other spine.payment_allocations;
        paid spine.payments; target_currency text;
BEGIN
    PERFORM pg_advisory_xact_lock(hashtextextended(p_id::text, 0));
    SELECT * INTO existing FROM spine.payment_allocations WHERE id = p_id;
    IF FOUND THEN
        IF existing.payment_id IS DISTINCT FROM p_payment
           OR existing.milestone_id IS DISTINCT FROM p_milestone
           OR existing.invoice_id IS DISTINCT FROM p_invoice OR existing.amount IS DISTINCT FROM p_amount
           OR existing.replaces_allocation_id IS DISTINCT FROM p_replaces
           OR existing.reason IS DISTINCT FROM p_reason OR existing.evidence_id IS DISTINCT FROM p_evidence
           OR existing.actor IS DISTINCT FROM p_actor THEN
            RAISE EXCEPTION 'allocation ID already has different contents' USING ERRCODE = 'SP004';
        END IF;
        RETURN p_id;
    END IF;
    SELECT * INTO paid FROM spine.payments WHERE id = p_payment;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'the payment named does not exist: record it in this call, or check its ID with read_money_open'
            USING ERRCODE = '23503';
    END IF;
    PERFORM 1 FROM spine.payments WHERE id = spine.payment_root(p_payment) FOR UPDATE;
    -- The latest version of the payment chain gives the currency.
    WITH RECURSIVE chain(id) AS (
        SELECT spine.payment_root(p_payment) UNION ALL
        SELECT p.id FROM spine.payments p JOIN chain c ON p.replaces_payment_id = c.id)
    SELECT * INTO paid FROM spine.payments p
    WHERE p.id IN (SELECT id FROM chain)
      AND NOT EXISTS (SELECT 1 FROM spine.payments n WHERE n.replaces_payment_id = p.id);
    IF num_nonnulls(p_milestone, p_invoice) <> 1 THEN
        RAISE EXCEPTION 'an allocation names exactly one target: charge_id or invoice_id' USING ERRCODE = '23514';
    END IF;
    IF p_milestone IS NOT NULL THEN
        PERFORM 1 FROM spine.charge_lines WHERE milestone_id = p_milestone;
        IF NOT FOUND THEN
            RAISE EXCEPTION 'that milestone has no charge line: a payment goes on a charge' USING ERRCODE = '23514';
        END IF;
        -- The charge's currency: its current invoiced line, else its current expected line.
        SELECT c.currency INTO target_currency FROM spine.charge_lines c
        WHERE c.milestone_id = p_milestone
          AND NOT EXISTS (SELECT 1 FROM spine.charge_lines n WHERE n.replaces_line_id = c.id)
        ORDER BY c.kind = 'invoiced' DESC LIMIT 1;
    ELSE
        -- The latest version of the invoice gives the currency.
        SELECT i.currency INTO target_currency
        FROM spine.invoices i
        WHERE i.id IN (SELECT spine.invoice_chain(p_invoice))
          AND NOT EXISTS (SELECT 1 FROM spine.invoices n WHERE n.replaces_invoice_id = i.id);
        IF NOT FOUND THEN
            RAISE EXCEPTION 'the invoice named does not exist' USING ERRCODE = '23503';
        END IF;
    END IF;
    IF target_currency IS DISTINCT FROM paid.currency THEN
        RAISE EXCEPTION 'the payment is in % and what it goes on is in %: currencies are never mixed',
            paid.currency, coalesce(target_currency, 'no known currency') USING ERRCODE = 'SP016';
    END IF;
    IF p_replaces IS NOT NULL THEN
        SELECT * INTO other FROM spine.payment_allocations WHERE id = p_replaces;
        IF NOT FOUND THEN
            RAISE EXCEPTION 'the allocation to replace does not exist' USING ERRCODE = '23503';
        END IF;
        IF spine.payment_root(other.payment_id) <> spine.payment_root(p_payment) THEN
            RAISE EXCEPTION 'an allocation can replace only an allocation of the same payment'
                USING ERRCODE = '23514';
        END IF;
        IF EXISTS (SELECT 1 FROM spine.payment_allocations WHERE replaces_allocation_id = p_replaces) THEN
            RAISE EXCEPTION 'that allocation is already replaced; replace its latest version'
                USING ERRCODE = 'SP011';
        END IF;
    END IF;
    INSERT INTO spine.payment_allocations (id, payment_id, milestone_id, invoice_id, amount,
                                           replaces_allocation_id, reason, evidence_id, actor)
    VALUES (p_id, p_payment, p_milestone, p_invoice, p_amount, p_replaces, p_reason, p_evidence, p_actor);
    RETURN p_id;
END;
$$;

-- At commit, once per payment chain a call touched: the latest allocations
-- of the chain must not exceed its latest amount. The chain's first row is
-- locked first, so another call on the same payment waits for this one.
CREATE FUNCTION spine.check_payment_cap() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog AS $$
DECLARE root uuid; latest spine.payments; allocated numeric;
BEGIN
    IF TG_TABLE_NAME = 'payments' THEN
        root := spine.payment_root(NEW.id);
    ELSE
        root := spine.payment_root(NEW.payment_id);
    END IF;
    PERFORM 1 FROM spine.payments WHERE id = root FOR UPDATE;
    WITH RECURSIVE chain(id) AS (
        SELECT root UNION ALL
        SELECT p.id FROM spine.payments p JOIN chain c ON p.replaces_payment_id = c.id)
    SELECT p.* INTO latest FROM spine.payments p
    WHERE p.id IN (SELECT id FROM chain)
      AND NOT EXISTS (SELECT 1 FROM spine.payments n WHERE n.replaces_payment_id = p.id);
    WITH RECURSIVE chain(id) AS (
        SELECT root UNION ALL
        SELECT p.id FROM spine.payments p JOIN chain c ON p.replaces_payment_id = c.id)
    SELECT coalesce(sum(a.amount), 0) INTO allocated FROM spine.payment_allocations a
    WHERE a.payment_id IN (SELECT id FROM chain)
      AND NOT EXISTS (SELECT 1 FROM spine.payment_allocations n WHERE n.replaces_allocation_id = a.id);
    IF allocated > latest.amount THEN
        RAISE EXCEPTION 'the allocations of this payment add up to % %, more than the payment''s % %',
            allocated, latest.currency, latest.amount, latest.currency USING ERRCODE = 'SP015';
    END IF;
    RETURN NULL;
END;
$$;
CREATE CONSTRAINT TRIGGER payment_cap AFTER INSERT ON spine.payment_allocations
DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION spine.check_payment_cap();
CREATE CONSTRAINT TRIGGER payment_cap AFTER INSERT ON spine.payments
DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION spine.check_payment_cap();

-- A charge's currency cannot change while money is on it, so what was paid
-- on a charge is always in one currency.
CREATE FUNCTION spine.check_charge_currency() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog AS $$
DECLARE held text;
BEGIN
    IF NEW.currency IS NULL THEN
        RETURN NULL;
    END IF;
    SELECT p.currency INTO held FROM spine.payment_allocations a
    JOIN spine.payments p ON p.id = a.payment_id
    WHERE a.milestone_id = NEW.milestone_id AND a.amount > 0
      AND NOT EXISTS (SELECT 1 FROM spine.payment_allocations n WHERE n.replaces_allocation_id = a.id)
    LIMIT 1;
    IF held IS NOT NULL AND held <> NEW.currency THEN
        RAISE EXCEPTION 'this charge already has money paid in %, so its lines stay in %: lower those allocations to 0 first',
            held, held USING ERRCODE = 'SP016';
    END IF;
    RETURN NULL;
END;
$$;
CREATE TRIGGER charge_currency_holds AFTER INSERT ON spine.charge_lines
FOR EACH ROW EXECUTE FUNCTION spine.check_charge_currency();

REVOKE ALL ON spine.payments, spine.payment_allocations FROM PUBLIC;
GRANT SELECT ON spine.payments, spine.payment_allocations TO PUBLIC;
GRANT EXECUTE ON FUNCTION
    spine.payment_root(uuid),
    spine.record_payment(uuid, uuid, uuid, numeric, text, numeric, text, date, text, text,
                         uuid, text, uuid, text),
    spine.record_payment_allocation(uuid, uuid, uuid, uuid, numeric, uuid, text, uuid, text)
TO PUBLIC;

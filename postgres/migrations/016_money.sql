-- Money, part one: what is owed. Three new tables; no existing table changes.
--
--   invoices             one row per version of a bill one party sends another:
--                        number, dates, terms as written, stated total. A
--                        reissued bill is a new row that replaces the old one.
--   invoice_work_links   which quotes, bookings and jobs an invoice covers.
--                        An invoice may cover none, such as rent.
--   charge_lines         one amount of a charge, a milestone with lines. Kind
--                        expected is what was agreed, invoiced what a bill says.
--
-- Rows are only added. A correction is a new row naming the old one in its
-- unique replaces_* column. Open amounts and direction are worked out when
-- read, never stored. An unknown number stays NULL. Money is numeric and may be
-- below zero on a line, a rate or a stated total, so a credit is a line like
-- any other; a currency is three capital letters. home_amount says what an amount
-- was in the shop's own currency; the ledger converts nothing.
--
-- Hard rules, refused below (codes after SP011; payments are 017):
--   SP012  a charge has one current line per kind; a new one replaces it
--   SP013  a charge has one pair of parties (who owes, who is owed)
--   SP016  a reissued bill changes currency while money in another currency is
--          on the bill or on its lines (currencies are never mixed; 017)
-- A charge may be billed again by a later bill, and a reissued bill may name
-- other parties: the ledger records what the bills say.
-- SP004 is a reused ID with different contents, SP011 a row already replaced.

CREATE TABLE spine.invoices (
    id uuid PRIMARY KEY,
    number text CONSTRAINT invoices_number_check CHECK (number IS NULL OR length(btrim(number)) > 0),
    from_party_id uuid NOT NULL REFERENCES spine.parties,
    to_party_id uuid NOT NULL REFERENCES spine.parties,
    issued_on date,
    terms text CONSTRAINT invoices_terms_check CHECK (terms IS NULL OR length(btrim(terms)) > 0),
    due_on date,
    stated_total numeric,
    currency text CONSTRAINT invoices_currency_check CHECK (currency ~ '^[A-Z]{3}$'),
    replaces_invoice_id uuid CONSTRAINT invoices_one_successor UNIQUE REFERENCES spine.invoices,
    reason text NOT NULL CHECK (length(btrim(reason)) > 0),
    evidence_id uuid NOT NULL REFERENCES spine.evidence,
    actor text NOT NULL CHECK (length(btrim(actor)) > 0),
    recorded_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT invoices_parties_differ CHECK (from_party_id <> to_party_id),
    CONSTRAINT invoices_total_needs_currency CHECK (stated_total IS NULL OR currency IS NOT NULL),
    CONSTRAINT invoices_total_check CHECK (stated_total IS NULL OR (
        stated_total NOT IN ('NaN', 'Infinity', '-Infinity'))),
    CONSTRAINT invoices_not_self CHECK (replaces_invoice_id <> id)
);
CREATE INDEX ON spine.invoices (from_party_id, to_party_id, number);
CREATE INDEX ON spine.invoices (to_party_id);

CREATE TABLE spine.invoice_work_links (
    id uuid PRIMARY KEY,
    invoice_id uuid NOT NULL REFERENCES spine.invoices,
    quote_id uuid REFERENCES spine.quotes,
    booking_id uuid REFERENCES spine.bookings,
    job_id uuid REFERENCES spine.jobs,
    actor text NOT NULL CHECK (length(btrim(actor)) > 0),
    recorded_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CHECK (num_nonnulls(quote_id, booking_id, job_id) = 1)
);
CREATE UNIQUE INDEX invoice_work_links_once
    ON spine.invoice_work_links (invoice_id, coalesce(quote_id, booking_id, job_id));
CREATE INDEX ON spine.invoice_work_links (quote_id);
CREATE INDEX ON spine.invoice_work_links (booking_id);
CREATE INDEX ON spine.invoice_work_links (job_id);

CREATE TABLE spine.charge_lines (
    id uuid PRIMARY KEY,
    milestone_id uuid NOT NULL REFERENCES spine.milestones,
    owes_party_id uuid NOT NULL REFERENCES spine.parties,
    owed_party_id uuid NOT NULL REFERENCES spine.parties,
    charge_type text NOT NULL CHECK (length(btrim(charge_type)) > 0),
    quantity numeric,
    rate numeric,
    amount numeric,
    currency text CONSTRAINT charge_lines_currency_check CHECK (currency ~ '^[A-Z]{3}$'),
    home_amount numeric,
    home_currency text CONSTRAINT charge_lines_home_currency_check CHECK (home_currency ~ '^[A-Z]{3}$'),
    kind text NOT NULL CONSTRAINT charge_lines_kind_check CHECK (kind IN ('expected', 'invoiced')),
    invoice_id uuid REFERENCES spine.invoices,
    replaces_line_id uuid CONSTRAINT charge_lines_one_successor UNIQUE REFERENCES spine.charge_lines,
    reason text NOT NULL CHECK (length(btrim(reason)) > 0),
    evidence_id uuid NOT NULL REFERENCES spine.evidence,
    actor text NOT NULL CHECK (length(btrim(actor)) > 0),
    recorded_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT charge_lines_parties_differ CHECK (owes_party_id <> owed_party_id),
    -- A known amount or rate is money: it needs its currency.
    CONSTRAINT charge_lines_money_needs_currency
        CHECK ((amount IS NULL AND rate IS NULL) OR currency IS NOT NULL),
    CONSTRAINT charge_lines_home_needs_currency
        CHECK ((home_amount IS NULL) = (home_currency IS NULL)),
    CONSTRAINT charge_lines_numbers_check CHECK (
        (quantity IS NULL OR quantity NOT IN ('NaN', 'Infinity', '-Infinity'))
        AND (rate IS NULL OR rate NOT IN ('NaN', 'Infinity', '-Infinity'))
        AND (amount IS NULL OR amount NOT IN ('NaN', 'Infinity', '-Infinity'))
        AND (home_amount IS NULL OR home_amount NOT IN ('NaN', 'Infinity', '-Infinity'))),
    CONSTRAINT charge_lines_invoice_matches_kind
        CHECK ((kind = 'invoiced') = (invoice_id IS NOT NULL)),
    CONSTRAINT charge_lines_not_self CHECK (replaces_line_id <> id)
);
CREATE INDEX ON spine.charge_lines (milestone_id, recorded_at, id);
CREATE INDEX ON spine.charge_lines (owes_party_id);
CREATE INDEX ON spine.charge_lines (owed_party_id);
CREATE INDEX ON spine.charge_lines (invoice_id);

DO $$
DECLARE table_name text;
BEGIN
    FOREACH table_name IN ARRAY ARRAY['invoices', 'invoice_work_links', 'charge_lines'] LOOP
        EXECUTE format(
            'CREATE TRIGGER append_only BEFORE UPDATE OR DELETE OR TRUNCATE ON spine.%I '
            'FOR EACH STATEMENT EXECUTE FUNCTION spine.refuse_mutation()', table_name);
    END LOOP;
END;
$$;

-- Every version of the invoice chain one version belongs to.
CREATE FUNCTION spine.invoice_chain(p_id uuid) RETURNS SETOF uuid
LANGUAGE sql STABLE SET search_path = pg_catalog AS $$
    WITH RECURSIVE up(id, replaces) AS (
        SELECT id, replaces_invoice_id FROM spine.invoices WHERE id = p_id
        UNION ALL
        SELECT i.id, i.replaces_invoice_id FROM spine.invoices i JOIN up ON i.id = up.replaces
    ), down(id) AS (
        SELECT id FROM up WHERE replaces IS NULL
        UNION ALL
        SELECT i.id FROM spine.invoices i JOIN down ON i.replaces_invoice_id = down.id)
    SELECT id FROM down
$$;

-- One invoice version. The same id with the same contents is a retry and
-- returns the id; with different contents it is refused with SP004. A
-- reissue in another currency is refused while money paid in another
-- currency is on the bill or on its current lines (once 017 is installed).
CREATE FUNCTION spine.record_invoice(
    p_id uuid, p_number text, p_from uuid, p_to uuid, p_issued_on date, p_terms text,
    p_due_on date, p_stated_total numeric, p_currency text, p_replaces uuid,
    p_reason text, p_evidence uuid, p_actor text
) RETURNS uuid LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog AS $$
DECLARE existing spine.invoices; other spine.invoices; held text;
BEGIN
    PERFORM pg_advisory_xact_lock(hashtextextended(p_id::text, 0));
    SELECT * INTO existing FROM spine.invoices WHERE id = p_id;
    IF FOUND THEN
        IF existing.number IS DISTINCT FROM p_number OR existing.from_party_id IS DISTINCT FROM p_from
           OR existing.to_party_id IS DISTINCT FROM p_to OR existing.issued_on IS DISTINCT FROM p_issued_on
           OR existing.terms IS DISTINCT FROM p_terms OR existing.due_on IS DISTINCT FROM p_due_on
           OR existing.stated_total IS DISTINCT FROM p_stated_total
           OR existing.currency IS DISTINCT FROM p_currency
           OR existing.replaces_invoice_id IS DISTINCT FROM p_replaces
           OR existing.reason IS DISTINCT FROM p_reason OR existing.evidence_id IS DISTINCT FROM p_evidence
           OR existing.actor IS DISTINCT FROM p_actor THEN
            RAISE EXCEPTION 'invoice ID already has different contents' USING ERRCODE = 'SP004';
        END IF;
        RETURN p_id;
    END IF;
    IF p_replaces IS NOT NULL THEN
        SELECT * INTO other FROM spine.invoices WHERE id = p_replaces;
        IF NOT FOUND THEN
            RAISE EXCEPTION 'the invoice to replace does not exist' USING ERRCODE = '23503';
        END IF;
        IF EXISTS (SELECT 1 FROM spine.invoices WHERE replaces_invoice_id = p_replaces) THEN
            RAISE EXCEPTION 'that invoice version is already replaced; replace its latest version'
                USING ERRCODE = 'SP011';
        END IF;
        IF other.currency IS DISTINCT FROM p_currency
           AND to_regclass('spine.payment_allocations') IS NOT NULL THEN
            SELECT p.currency INTO held FROM spine.payment_allocations a
            JOIN spine.payments p ON p.id = a.payment_id
            WHERE a.amount > 0
              AND NOT EXISTS (SELECT 1 FROM spine.payment_allocations n
                              WHERE n.replaces_allocation_id = a.id)
              AND (a.invoice_id IN (SELECT spine.invoice_chain(p_replaces))
                   OR a.milestone_id IN (
                       SELECT l.milestone_id FROM spine.charge_lines l
                       WHERE l.invoice_id IN (SELECT spine.invoice_chain(p_replaces))
                         AND NOT EXISTS (SELECT 1 FROM spine.charge_lines n
                                         WHERE n.replaces_line_id = l.id)))
              AND p.currency IS DISTINCT FROM p_currency
            LIMIT 1;
            IF held IS NOT NULL THEN
                RAISE EXCEPTION 'this bill or its lines already have money paid in %, so a reissue stays in %: currencies are never mixed; lower those allocations to 0 first',
                    held, held USING ERRCODE = 'SP016';
            END IF;
        END IF;
    END IF;
    INSERT INTO spine.invoices (id, number, from_party_id, to_party_id, issued_on, terms, due_on,
                                stated_total, currency, replaces_invoice_id, reason, evidence_id, actor)
    VALUES (p_id, p_number, p_from, p_to, p_issued_on, p_terms, p_due_on,
            p_stated_total, p_currency, p_replaces, p_reason, p_evidence, p_actor);
    RETURN p_id;
END;
$$;

-- One quote, booking or job an invoice covers. Same retry rule.
CREATE FUNCTION spine.link_invoice_work(
    p_id uuid, p_invoice uuid, p_quote uuid, p_booking uuid, p_job uuid, p_actor text
) RETURNS uuid LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog AS $$
DECLARE existing spine.invoice_work_links;
BEGIN
    PERFORM pg_advisory_xact_lock(hashtextextended(p_id::text, 0));
    SELECT * INTO existing FROM spine.invoice_work_links WHERE id = p_id;
    IF FOUND THEN
        IF existing.invoice_id IS DISTINCT FROM p_invoice OR existing.quote_id IS DISTINCT FROM p_quote
           OR existing.booking_id IS DISTINCT FROM p_booking OR existing.job_id IS DISTINCT FROM p_job
           OR existing.actor IS DISTINCT FROM p_actor THEN
            RAISE EXCEPTION 'invoice work link ID already has different contents' USING ERRCODE = 'SP004';
        END IF;
        RETURN p_id;
    END IF;
    PERFORM spine.require_work_owner(p_quote, p_booking, p_job);
    INSERT INTO spine.invoice_work_links (id, invoice_id, quote_id, booking_id, job_id, actor)
    VALUES (p_id, p_invoice, p_quote, p_booking, p_job, p_actor);
    RETURN p_id;
END;
$$;

-- One charge line. Same retry rule. A line with no parties takes those of
-- the charge's first line; the first invoiced line of a charge with no
-- parties takes those of its invoice: owes is the recipient, owed is the
-- issuer. A line that names other parties than its bill is saved;
-- record_charges warns. The rules that span
-- rows are checked under a lock on the charge, so two calls cannot both add a
-- current line of the same kind.
CREATE FUNCTION spine.record_charge_line(
    p_id uuid, p_milestone uuid, p_owes uuid, p_owed uuid, p_charge_type text,
    p_quantity numeric, p_rate numeric, p_amount numeric, p_currency text,
    p_home_amount numeric, p_home_currency text, p_kind text, p_invoice uuid, p_replaces uuid,
    p_reason text, p_evidence uuid, p_actor text
) RETURNS uuid LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog AS $$
DECLARE existing spine.charge_lines; other spine.charge_lines; bill spine.invoices; current_id uuid;
BEGIN
    PERFORM pg_advisory_xact_lock(hashtextextended(p_id::text, 0));
    PERFORM pg_advisory_xact_lock(hashtextextended(p_milestone::text, 0));
    IF p_owes IS NULL OR p_owed IS NULL THEN
        SELECT * INTO other FROM spine.charge_lines WHERE milestone_id = p_milestone
        ORDER BY recorded_at, id LIMIT 1;
        IF FOUND THEN
            p_owes := coalesce(p_owes, other.owes_party_id);
            p_owed := coalesce(p_owed, other.owed_party_id);
        END IF;
    END IF;
    IF p_invoice IS NOT NULL THEN
        SELECT * INTO bill FROM spine.invoices WHERE id = p_invoice;
        IF FOUND THEN
            p_owes := coalesce(p_owes, bill.to_party_id);
            p_owed := coalesce(p_owed, bill.from_party_id);
        END IF;
    END IF;
    SELECT * INTO existing FROM spine.charge_lines WHERE id = p_id;
    IF FOUND THEN
        IF existing.milestone_id IS DISTINCT FROM p_milestone
           OR existing.owes_party_id IS DISTINCT FROM p_owes
           OR existing.owed_party_id IS DISTINCT FROM p_owed
           OR existing.charge_type IS DISTINCT FROM p_charge_type
           OR existing.quantity IS DISTINCT FROM p_quantity OR existing.rate IS DISTINCT FROM p_rate
           OR existing.amount IS DISTINCT FROM p_amount OR existing.currency IS DISTINCT FROM p_currency
           OR existing.home_amount IS DISTINCT FROM p_home_amount
           OR existing.home_currency IS DISTINCT FROM p_home_currency
           OR existing.kind IS DISTINCT FROM p_kind OR existing.invoice_id IS DISTINCT FROM p_invoice
           OR existing.replaces_line_id IS DISTINCT FROM p_replaces
           OR existing.reason IS DISTINCT FROM p_reason OR existing.evidence_id IS DISTINCT FROM p_evidence
           OR existing.actor IS DISTINCT FROM p_actor THEN
            RAISE EXCEPTION 'charge line ID already has different contents' USING ERRCODE = 'SP004';
        END IF;
        RETURN p_id;
    END IF;
    IF p_owes IS NULL OR p_owed IS NULL THEN
        RAISE EXCEPTION 'the first line of a charge needs owes_party_id and owed_party_id' USING ERRCODE = '23502';
    END IF;
    IF p_invoice IS NOT NULL AND bill.id IS NOT NULL THEN
        IF EXISTS (SELECT 1 FROM spine.invoices WHERE replaces_invoice_id = p_invoice) THEN
            RAISE EXCEPTION 'that invoice version is already replaced; record the line on its latest version'
                USING ERRCODE = 'SP011';
        END IF;
    END IF;
    SELECT * INTO other FROM spine.charge_lines WHERE milestone_id = p_milestone
    ORDER BY recorded_at, id LIMIT 1;
    IF FOUND AND (other.owes_party_id <> p_owes OR other.owed_party_id <> p_owed) THEN
        RAISE EXCEPTION 'a charge has one pair of parties, and this charge''s lines name a different pair: record a line between other parties on a new charge'
            USING ERRCODE = 'SP013';
    END IF;
    IF p_replaces IS NOT NULL THEN
        SELECT * INTO other FROM spine.charge_lines WHERE id = p_replaces;
        IF NOT FOUND THEN
            RAISE EXCEPTION 'the charge line to replace does not exist' USING ERRCODE = '23503';
        END IF;
        IF other.milestone_id IS DISTINCT FROM p_milestone OR other.kind IS DISTINCT FROM p_kind THEN
            RAISE EXCEPTION 'a line can replace only an earlier line of the same charge and kind'
                USING ERRCODE = '23514';
        END IF;
        IF EXISTS (SELECT 1 FROM spine.charge_lines WHERE replaces_line_id = p_replaces) THEN
            RAISE EXCEPTION 'that charge line is already replaced; replace the latest line of its chain'
                USING ERRCODE = 'SP011';
        END IF;
    END IF;
    SELECT c.id INTO current_id FROM spine.charge_lines c
    WHERE c.milestone_id = p_milestone AND c.kind = p_kind
      AND NOT EXISTS (SELECT 1 FROM spine.charge_lines n WHERE n.replaces_line_id = c.id);
    IF current_id IS NOT NULL AND p_replaces IS NULL THEN
        RAISE EXCEPTION 'this charge already has a current % line (%): a new amount replaces it, never adds; name it in replaces_line_id',
            p_kind, current_id USING ERRCODE = 'SP012';
    END IF;
    INSERT INTO spine.charge_lines (id, milestone_id, owes_party_id, owed_party_id, charge_type,
                                    quantity, rate, amount, currency, home_amount, home_currency,
                                    kind, invoice_id, replaces_line_id, reason, evidence_id, actor)
    VALUES (p_id, p_milestone, p_owes, p_owed, p_charge_type, p_quantity, p_rate, p_amount,
            p_currency, p_home_amount, p_home_currency, p_kind, p_invoice, p_replaces,
            p_reason, p_evidence, p_actor);
    RETURN p_id;
END;
$$;

REVOKE ALL ON spine.invoices, spine.invoice_work_links, spine.charge_lines FROM PUBLIC;
GRANT SELECT ON spine.invoices, spine.invoice_work_links, spine.charge_lines TO PUBLIC;
GRANT EXECUTE ON FUNCTION
    spine.invoice_chain(uuid),
    spine.record_invoice(uuid, text, uuid, uuid, date, text, date, numeric, text, uuid, text, uuid, text),
    spine.link_invoice_work(uuid, uuid, uuid, uuid, uuid, text),
    spine.record_charge_line(uuid, uuid, uuid, uuid, text, numeric, numeric, numeric, text,
                             numeric, text, text, uuid, uuid, text, uuid, text)
TO PUBLIC;

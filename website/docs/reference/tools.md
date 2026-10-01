---
title: Tools
description: All 45 ledger tools and the 5 optional draft tools.
---

# Tools

There are 45 tools, plus 5 optional draft tools. Every ID is a UUID that the
caller chooses. The one exception is a draft: `propose_review` makes the ID
when the caller sends none. Every write takes an `actor`. Times are ISO 8601
and must carry a UTC offset (`Z`, `+00:00`, `+07:00`); one without an offset
is refused. Dates are `YYYY-MM-DD`. Arrays and objects must be sent as
arrays and objects, not as strings. A text argument is kept exactly as sent,
even when the text is itself valid JSON.

An argument that takes one of a fixed list of words, such as `work_kind`,
`tag`, `status`, `outcome`, `confidence` or a party's `kind`, lists its words
in the tool schema. A word outside the list is refused before the database is
asked.

Every tool and every parameter carries a description in the tool schema your
harness shows the agent: what the value is, its format and the rule that
applies. This page gives the same facts by topic.

Every answer is one JSON object. A tool that lists things puts the list under
a named key, such as `{"work": [...]}`, and an empty list means there is
nothing to list. A read by an ID that does not exist is refused with
`... not found: <id>`. That holds for a list read too: the memos of a work
item, the judgments of a milestone, the documents of a job and the
assessments of a document version each refuse a parent that does not exist.
So an empty answer is never a broken one. See [Refusals](errors.md) for how
errors read.

## Start here

- `read_case_brief(id)`: the whole chain that a quote, booking or job belongs
  to, as one JSON document `{"brief": {...}}`. Any ID in the chain gives the
  same chain; `requested_id` echoes the ID that was sent and `read_at` is the
  time of the read. Each item carries the SOP version it adopts, its phases,
  every milestone's latest judgment with its citations (or the SOP criterion
  when it was never judged), the parties in their roles, the evidence linked
  to it, the latest memo and, for a job, its documents. A milestone that no
  SOP adoption named shows `from_sop` false. `charges` lists every
  milestone with a charge line, with its phase name; `read_work_money`
  gives the amounts. `invoices` lists the bills linked to each item; one
  with no lines reads "billed, stated total, lines not recorded", or "billed,
  total not stated, lines not recorded" when its total is unknown. A charge an SOP named also stays in its phase (or in
  `history_milestones`); a charge no SOP named is listed only under
  `charges`. Phases come in the order of
  the SOP the item follows now (`sop_order`), then any the agent added.
  After a job changes SOP, milestones only the earlier SOP had leave the
  phases and are listed under `history_milestones` with their phase name
  and last status; a milestone the new SOP copied word for word stays in
  its phase. The last section,
  `not_recorded`, lists what is missing, such as a work item that adopts no
  SOP version or roles that cite no evidence, so a blank is not read as
  "nothing to say". `chain` names the root of the chain. An unknown ID is
  refused as not found.
- `list_work(kind, limit)`: every quote, booking and job, newest first, as
  `{"work": [...]}`. It is the only read that needs no ID. Use it before
  creating work, so the same enquiry does not become two quotes. Each entry
  has `kind`, `id`, `title`, `actor`, `recorded_at`, its outside reference
  numbers, `latest_memo_at` and `sop_version_id`. `limit` defaults to 200 and
  may be at most 1000. There is no status and no open flag.

## Work: quotes, bookings and jobs

- `create_quote(id, title, actor)`: create a quote, the first record of work
  someone asked for and the root of a chain.
- `create_booking(id, quote_id, title, actor)`: create a booking under an
  existing quote: quoted work that is going ahead. A quote may have several.
- `create_job(id, title, actor)`: create a job, one piece of work that is
  carried out. A job may stand alone.
- `link_job_booking(job_id, booking_id, actor)`: put an existing job under
  an existing booking, which joins it to that quote's chain. A job can have
  one booking; a different second link is refused. A link is never removed.
- `read_work(id)`: one quote, booking or job with its chain of relationships
  and its party roles.

An ID names one kind of work only. Reusing an ID with the same contents is a
safe retry.

## Evidence and files

- `record_evidence(id, original_payload, attachments, actor, source_locator, source_at, about_work)`: record a source unchanged. It needs a text payload
  or at least one attachment. Each attachment is `{sha256, media_type, byte_size}` and its bytes must already be in the file store. `about_work`
  lists the work this evidence is about, one `{id, work_kind, work_id}` per
  work item, where `id` is a new UUID for the link; evidence and links are
  saved together.
- `link_evidence_work(id, evidence_id, work_kind, work_id, actor)`: say later
  that an evidence row is about a work item. Links are never removed.
- `read_evidence(id)`: the full original record, its `payload_sha256` and its
  `about_work` links.
- `find_evidence(payload_sha256, attachment_sha256, source_locator, limit)`:
  answers "have I recorded this already?". Give exactly one key. Matching is
  exact, including case. It returns `match_count`, `has_more` and a short
  list. It never merges rows, and recording the same source twice is allowed.
  Look up first, and cite the existing ID when there is one.
- `put_file(evidence_id, contents_base64, media_type, actor)`: store file
  bytes, up to 8 MiB, and record an evidence row that names them. It returns
  `sha256`, `byte_size` and `evidence_id`. The new row is not linked to any
  work until you link it with `link_evidence_work`. The row is saved first,
  the bytes second. If the byte write fails, the row exists and `read_file`
  reports that hash as not stored; call again with the same ID and the same
  bytes to complete the store. The same ID with different bytes is refused.
- `record_file_by_hash(evidence_id, sha256, media_type, actor)`: the same, for
  bytes that should not pass through the model. Another program leaves the
  file in the drop directory, named by its hash. The server checks that the
  bytes match the name before it writes anything. Then the order is the same
  as `put_file`: row first, bytes second, and the same call again completes
  a store that failed part way.
- `read_file(sha256)`: the bytes, base64-encoded in `bytes`, checked against
  the hash. If an evidence row names the hash but the bytes are not on disk,
  it returns `{"sha256": ..., "stored": false}`.

Files are limited to 8 MiB. Hashes are 64 lowercase hex characters. No tool
takes or returns a path on the server, and no tool deletes a file. Two
evidence rows may name the same hash: that is two rows and one stored file.
A file stored this way is not linked to any work until you link it.

Links matter for citations. Evidence with no links can be cited from any
work. Evidence with links can be cited only by a judgment on one of the linked
work items. So link the evidence to this work first, then cite it.

## Phases, milestones, reviews and memos

- `create_work_phase(id, work_kind, work_id, name, display_order, actor)`:
  create a phase on one work item.
- `create_work_milestone(id, work_kind, work_id, title, actor, phase_id)`:
  create a milestone, optionally inside a phase on the same work item. The
  phase of a milestone cannot be changed later.
- `record_review(work_kind, work_id, actor, judgments, memo, roles)`: the way
  to record judgments. One transaction saves every judgment, the required
  memo and any party roles claimed in the review, and links them together.
  Each judgment has `id`, `milestone_id`, `status`, `explanation` and at least
  one `evidence_ids` entry. It may carry `occurred_on` with
  `occurrence_precision` (`exact` or `by`), one earlier judgment in
  `revises_ids` and others in `based_on_ids`. The memo has `id`,
  `review_started_at`, `review_ended_at`, `summary`, `decision` and `changed`,
  plus optional `waiting_for`, `next_review_at`, `details`,
  `reviewed_milestone_ids` and `reviewed_judgment_ids`. A milestone may be
  judged once per review. Judgments need `changed` to be true. Everything
  must belong to the named work item. One bad entry rolls back the whole
  review.
- `leave_work_memo(id, work_kind, work_id, ...)`: a memo with no judgment, for
  a look at the work that judged no milestone. It takes the same memo fields.
  `review_started_at` and `review_ended_at` say when the look began and
  finished; the end must not be before the start. `changed` says whether it
  learned anything new. `decision` says what the reviewer chose to do about
  it; "no action" is a decision.
- `read_work_review(id, include_evidence)`: a compact snapshot of one work
  item: its phases, its milestones with their latest judgments, and a pointer
  to its current SOP adoption. It shows every milestone, including ones no SOP
  governs.
- `read_work_memos(work_id, limit, before_recorded_at, before_id)`: memos,
  newest first, as `{"memos": [...]}`. Pass both cursor values to page.
- `read_history(milestone_id, limit, before_position, include_evidence)`:
  every judgment of one milestone, newest first, as `{"judgments": [...]}`.
  `limit` is at most 200.

The latest judgment of a milestone is the last one appended. `occurred_on` is
a calendar date that says when the thing happened. `recorded_at` is always the
time of the write.

## Documents on a job

- `create_document_requirement(id, job_id, title, actor, milestone_id, description)`: say that a job needs a document, optionally for one of that
  job's milestones.
- `submit_document(id, requirement_id, sha256, media_type, actor, replaces_submission_id)`: add a stored file as the next version. The first
  version replaces nothing. Each later version must name the current one.
- `assess_document(id, submission_id, outcome, reason, actor, evidence_ids)`:
  record `accepted` or `rejected`, with a reason and evidence. A new version
  starts with no assessment.
- `read_documents(job_id)`: requirements, every version and each version's
  latest assessment, as `{"requirements": [...]}`.
- `read_document_assessments(submission_id, limit, before_position)`: every
  assessment of one version, newest first, as `{"assessments": [...]}`.

## SOP versions and adoption

- `publish_sop_version(id, name, version, tag, definition, actor, based_on_version_id)`: publish an SOP. A published version never changes,
  and a `name` and `version` pair can be published only once.
  `tag` is `standard` or `break_glass` (a recovery procedure). `definition`
  is `{"stages": {"quote": {"phases": []}, "booking": {"phases": []}, "job": {"phases": []}}}`. All three stages must be present and may be empty. A
  phase is `{key, name, display_order, milestones}`. A milestone is `{key, title, criterion}`. The criterion is text for the agent to read; the ledger
  never evaluates it. `based_on_version_id` records where a version came
  from; nothing is inherited. `examples/` holds three example definitions
  from different trades; none is a default.
- `list_sop_versions(tag, status)`: every version, newest first, without the
  definition, as `{"versions": [...]}`. `status` is `active` or `retired`.
- `read_sop_version(id)`: one version in full.
- `set_sop_version_status(id, sop_version_id, status, reason, actor, evidence_ids)`: retire a version or make it active again. It needs a reason
  and at least one evidence ID. A retired version cannot be adopted; work
  already on it stays on it.
- `adopt_sop_version(id, work_kind, work_id, sop_version_id, reason, actor, evidence_ids, phase_bindings, milestone_bindings, expected_previous_adoption_id)`: record that a work item follows a version.
  It needs a reason and at least one evidence ID. The bindings give an ID to
  every phase and milestone of that stage, each exactly once:
  `{phase_key, phase_id}` and `{phase_key, milestone_key, milestone_id}`.
  Missing phases and milestones are created in the same transaction. An
  existing ID must keep its owner and meaning.
- `read_work_sop(work_id, include_evidence)`: the milestones of the current
  adoption (`current_adoption`, null when the work follows no SOP), those an
  earlier adoption had and this one dropped
  (`historical_removed_milestones`), and those no adoption ever named
  (`unadopted_milestones`).
- `read_sop_adoption(id, include_evidence)`: the fixed membership of any
  adoption, old or current, with judgments as they stand now. It is not a
  view of the past.

How adoption works:

- A chain chooses its SOP once, at the quote. Adopt on the quote.
- Bookings under that quote, and jobs linked to those bookings, follow it on
  their own. Each gets the phases and milestones of its own stage when it is
  created or linked, or when the quote adopts if it already exists. Do not
  adopt on them; it is refused.
- A job with no booking adopts on its own.
- A job that already adopted a different version cannot be linked under an
  adopted quote.
- Replacing an adoption, and adopting a `break_glass` version, are allowed on
  jobs only. A replacement must name the current adoption in
  `expected_previous_adoption_id`; a stale value is refused. Adopting again
  on a quote or booking that already follows an SOP is refused: only a job
  can replace its SOP version. The older adoption stays readable. Milestones
  the new one leaves out remain as history and are not marked done. To keep
  a milestone and its judgments, bind its existing ID and its phase's
  existing ID; its title, criterion and phase name must be unchanged, and a
  changed one needs a new ID. A job under a booking replaces the adoption
  it inherited the same way.
- Nothing picks a version. List the active ones and ask a person, unless your
  instructions name one.

## Parties, identifiers and roles

- `create_party(id, kind, name, actor, is_operator)`: `kind` is `person`,
  `agent` or `organization`. `is_operator` marks the one organization that
  runs this ledger; a second one is refused. The name is a label only.
- `record_party_identifier(id, party_id, kind, value, actor, evidence_id)`: an
  `email`, `phone`, `address` or `alias` the party was seen under. One row per
  value.
- `record_role(id, party_id, role, actor, on_party_id, work_kind, work_id, confidence, evidence_id, started_on, ended_on, memo_id)`: a party holds a
  role. Give exactly one target: another party (a standing role, such as a
  person who works at an organization) or one work item. `role` is any word
  your business uses. `confidence` is `confirmed`, `mentioned` or `former`.
  A `former` role needs `ended_on`, here and in `record_review`.
  A role with no `evidence_id` is reported as uncited in the case brief.
  Roles passed to `record_review` are tied to that review for you.
- `end_role(id, role_id, ended_on, actor, evidence_id, memo_id)`: append a
  replacement row marked `former`. The earlier row stays as written. A role
  that is already ended or replaced is refused.
- `read_party(id)`: the party, its identifiers, the latest row of each role it
  holds (`roles`) and of each role held on it (`held_by`).
- `find_parties(text)`: the parties that match what the agent sees. An
  email, phone or alias equal to the text, ignoring case, is an exact match.
  Only when there is none, every party whose name or one alias contains
  every word of the text, or (three characters or more) appears inside the
  text, ignoring case, so
  "Coastal Refrig" finds "Coastal Refrigeration Inc" and "Harbor Co" finds the
  alias "Harbor". Nothing fuzzier: a misspelling finds nothing. It returns `{"candidates": [...]}`, each with `id`,
  `kind`, `name`, `is_operator`, `match` (`email`, `phone`, `alias`,
  `name_words` or `alias_words`) and `matched_value`. It never picks.

Parties are never merged. The same company under two names is two rows.
Call `find_parties` before `create_party`, so it does not happen.

## Money: what is owed and what was paid

This is a record for operations, not accounting. It answers "what do I owe,
and to whom?", "what am I owed, and who is late?", "is this bill what we
agreed?" and "did I make money on this job?", both ways. The ledger records
and the reads do the sums; it files no tax and converts no currency. It
takes in what happened, even when it looks wrong, and refuses only the few
things that would make the reads lie (see "Rules the ledger enforces").

- A **charge** is one priced thing on one quote, booking or job: a milestone
  with charge lines. One party owes it and one party is owed it. It is judged with `record_review` like any
  milestone: `done` is accepted, `pending` is waiting for detail, `blocked`
  is disputed, `failed` is waived.
- A **charge line** states one amount. Kind `expected` is what was agreed;
  kind `invoiced` is what a bill says. A charge has at most one current line
  of each kind. The two are shown side by side and never added.
- An **invoice** is one version of a bill: number, dates, terms as written,
  stated total. A reissued bill is a new version that replaces the old one.
- A **payment** is money that moved from one party to another. An
  **allocation** puts a payment, or part of it, on a charge or on an
  invoice, whoever the charge or invoice names.

Writes:

- `record_charges(actor, reason, evidence_id, lines, invoice, invoice_id)`:
  one transaction. One bad line saves nothing: no line, no invoice, no link
  and no new charge. `reason` and `evidence_id` apply to every row. Lines
  are `expected` unless the call names a bill: `invoice` for a new one,
  `invoice_id` for the latest version of one already recorded. Then they are
  `invoiced`, and each that leaves out its parties takes them from the
  bill: the recipient owes, the issuer is owed. A line naming other parties
  than its bill is saved with a warning. The first line of a charge names `owes_party_id` and
  `owed_party_id`; a later line that leaves them out keeps the charge's.
  Each line has `id`, `charge_id`, `charge_type` (any
  words your business uses) and may have `quantity`, `rate`, `amount`,
  `currency`, `home_amount`, `home_currency` and `replaces_line_id`. A line
  for a charge that does not exist yet carries `new_charge` (`work_kind`,
  `work_id`, `title`, optional `phase_id`); new charges are created first.
  `lines` may be empty only with a new `invoice`, for a bill whose lines
  are not known yet. The invoice has `id`, `from_party_id`, `to_party_id`
  and may have `number`, `issued_on`, `terms`, `due_on`, `stated_total`,
  `currency`, `replaces_invoice_id` and `work`: one `{id, work_kind, work_id}` per quote, booking or job it covers, none for a bill of no job
  such as rent. Give the bill's currency even when its total is unknown, so
  a payment can be put on it. A reissued bill may name other parties than
  the bill it replaces. It returns `invoice_id`, `line_ids`, `charge_ids`
  and `warnings`.
- `record_payment(actor, reason, evidence_id, allocations, payment, payment_id)`: one transaction. `payment` is a new payment: `id`,
  `from_party_id`, `to_party_id`, `amount`, `currency`, and optional
  `home_amount`, `home_currency`, `paid_on`, `reference`, `method` (as
  written) and `replaces_payment_id`. `payment_id` names one already
  recorded, to allocate it later. Send exactly one of the two. Each
  allocation has `id`, `amount`, exactly one of `charge_id` and
  `invoice_id`, and may have `replaces_allocation_id`. `allocations` may be
  empty: the payment then waits as unallocated. It returns `payment_id`,
  `allocation_ids`, the payment's `unallocated` remainder and its
  `currency`, and `targets`: `paid`, `open` and `note` for each charge or
  invoice the call touched.

How money is written:

- Numbers are text, such as `"1250.00"`, or whole numbers, and are kept
  exactly as written. A number with a decimal point sent as a JSON number
  is refused, because it may already have lost digits. A line's amount,
  rate and home amount and a bill's stated total may be below zero: a
  credit is a line like any other, and the reads add signed numbers. A
  payment and an allocation are zero or more. Leave a number out when it is
  unknown; it stays unknown and is never read as 0.
- A known amount or rate needs a currency, three capital letters such as
  `USD`. A rate is a price per unit; a percentage goes in the reason.
  Currencies are never added together.
- `home_amount` and `home_currency` go together. They say what an amount
  was in the shop's own currency, from the bank or a stated rate. The
  ledger converts nothing. There is no setting for the shop's currency.
- A new amount is a new line with `replaces_line_id`, naming the current
  line of the same charge and kind. A discount or an absorbed bank fee
  lowers the line it concerns this way, with the reason. A lump
  whose detail arrives later is replaced by 0, and each part becomes a new
  charge.
- A bill for a charge already billed replaces, never adds: a reissued bill
  is a new invoice with `replaces_invoice_id`, and each changed line
  replaces the line it changes. A later bill may bill a charge again: its
  line replaces the charge's current invoiced line and names the new bill.
- An agreed amount is recorded once, on the stage where it was agreed, and
  never restated later; the reads total the whole chain.
- A payment goes on whichever charge or bill it settled, in its currency,
  whoever paid: the payment records who paid and who received, and the
  reads show both. The shop paying a vendor's bill addressed to its
  customer is the shop's payment on that bill's charges. A bounce or a
  refund is a new payment back, allocated to the same charge; a payment from
  the party owed lowers `paid`.
- A charge with money on it keeps its currency: a line in another currency
  is refused until those allocations are lowered to 0.
- `replaces_payment_id` corrects a recording mistake, including the payer
  or the receiver. The currency changes only once the payment's allocations
  are lowered to 0.
- To move money, take the allocation's `id` and `payment_id` from
  `allocations` in a read, then with that `payment_id` replace it with
  `replaces_allocation_id`, naming the new target. Money on a bill may stay
  there after its lines are recorded.
- An invoice with the same issuer, recipient and number as another invoice
  outside its own chain is saved, and the answer carries a warning. An
  unknown number never warns.

Reads:

- `read_work_money(id)`: the whole chain the quote, booking or job is in.
  `items` lists each quote, booking and job with its `charges` and the
  `invoices` linked to it. Each charge has `work`, `owes`, `owed`,
  `direction`, `judgment` (or `unassessed`) with `latest_judgment`, the
  current `expected` and `invoiced` lines with their `earlier` amounts,
  `paid`, `open`, `allocations` (`id`, `payment_id`, `amount`, `paid_on`,
  `paid_by`, `paid_to` each), `invoice_number`, `issued_on`, `due_on`, `paid_on`,
  `days_past_due`, `note` and two marks: `changed_since_judged` (the amount
  or currency of a line changed after the latest judgment; home figures do
  not count) and `before_procedure_change` (the charge was recorded before
  its job's latest SOP adoption replaced an earlier one). Each invoice has
  its latest version's fields, `versions`, `work`, `lines_recorded`,
  `same_number_as` and, when it has lines, `lines_total` and `difference`
  (stated total minus its current lines, across all work; when not 0, a
  `note` gives both figures), `allocations`, `paid` (money on its lines and
  on the bill) and `open` (its lines minus that). An invoice with no
  lines has `note` "billed, stated total, lines not recorded" (or "billed,
  total not stated, lines not recorded"), with its own `paid`, `open`,
  `days_past_due` and `allocations`. Each item has `cash`: per currency,
  `paid_out` and `taken_in`, the money the operator paid and received on
  that item's charges and bills, read from the payments whoever the charges
  name. It is cash, not margin. `totals` gives, for expected and for
  invoiced, `sales`, `costs` and `sales_minus_costs` per currency;
  `unknown_amount_lines`; `bills_without_lines`, one `{direction, currency, stated_total}` per bill with no lines linked to the chain, never added to
  sales or costs; and `home`: the same sums in each home currency recorded,
  a `warning` when more than one appears, and `unconverted_lines`. `home`
  is null when no line carries a home figure. Waived charges are left out
  of `totals`. An unknown ID is refused as not found.
- `read_money_open(party_id)`: what is open across the business, or for
  one party. `receivable`, `payable`, `between_others` and `unknown` list
  the charges that have an invoiced line and the invoices with no lines
  whose `open` is not 0, oldest due first, with their `allocations`.
  A charge judged `failed` is listed only while money paid on it makes
  its `open` not 0. `totals` sums `open` per direction
  and currency, with a count of unknown ones in `unknown_open`; `open` is
  null when none is known. Also `unallocated_payments`, `paid_not_billed`
  (charges with money on them and nothing invoiced),
  `bills_without_lines` (invoices linked to work that
  have no lines yet) and `awaiting_judgment` (billed charges that are
  unassessed, or changed since judged). An unknown party is refused as not
  found.

How the reads count:

- Only the latest row of each chain counts: the line, the invoice version,
  the payment and the allocation that nothing replaces. "A payment" is its
  whole chain; allocations follow a corrected payment.
  The work an invoice covers is the work linked to any version of it, so a
  reissued bill needs no new links.
- `paid` on a charge is the sum of its allocations, whoever paid: a
  payment from the party owed takes away, any other adds. `open` is the
  current invoiced amount minus `paid`; a minus is an overpayment. With
  nothing invoiced, `open` is null, and a charge with money on it reads
  "paid, not yet billed". On an invoice with no lines, `open` is the stated
  total minus `paid`.
- Money put on a bill that has lines stays on the bill; the ledger never
  guesses which line it settled. The bill's `open` is its lines not
  waived, minus the money on all its lines (waived ones too), minus the
  money on the bill (`money_on_bill`). A charge's `paid` and `open` count only money put on
  that charge; `bill_holds` on the charge shows what its bill holds as a
  whole. `read_money_open` lists that money as one row (`kind`
  `money_on_bill`, "N paid on bill X, not assigned to lines", or "N
  refunded on bill X" for money sent back) beside the
  bill's open lines, and its totals subtract it once. A bill whose open is
  0 is settled: neither its lines nor that row are listed.
- A bill whose lines all moved to a later bill (a charge billed again)
  reads "lines now on" and the later bill's number, open null, and leaves the open lists.
- A bill whose current lines name other parties than the bill, as after a
  reissue to another party, is marked `parties_differ_from_bill`, and so
  are those charges. `read_money_open` for a party lists a charge that
  names the party or whose bill is from or to it, in the charge's own
  direction.
- A waived charge (judged `failed`) owes 0: its `open` is minus what was
  paid on it, noted "waived, N paid", and listed while not 0.
- A charge whose bill holds money as a whole and whose bill reads open
  0 or less keeps its `open` but has no `days_past_due`: "covered by money on bill X".
- A bill some of whose lines moved to a later bill notes "line moved to"
  that bill before its stated total and lines.
- Each allocation row carries the payment's `reference` and `method`.
- `cash` counts money on a bill as a whole once: on the item of the
  bill's first line, or for a bill without lines on the first item it is
  linked to. The bill, listed on any other item, names that item in
  `cash_counted_on`. Unallocated payments are in no item's `cash`.
- `totals.others_bills` gives, per currency, what the operator paid
  (`paid_on_others_bills`) and received (`received_on_others_bills`) on
  charges and bills between other parties, with a `note`: sales minus
  costs leaves that money out; `cash` has it.
- Direction is worked out when read, never stored: `payable` when the
  operator owes, `receivable` when the operator is owed, `between_others`
  otherwise, `unknown` with no operator party.
- `days_past_due` counts from `due_on` to the day of the read, when
  something is open; it is 0 before the due date. Every read carries
  `read_at`, the time it was read.
- Home totals use only what was recorded: a line's `home_amount`, or its
  `amount` when its own currency is a home currency seen in the same read.
- Amounts come back as exact decimal text, such as `"1250.00"`.
- The paid milestone of an SOP is judged like any milestone, citing the
  payment's evidence. Nothing compares the two.

## Outside reference numbers

- `record_external_reference(id, work_kind, work_id, reference_type, source, value, actor)`: record a number another system uses for this work.
- `resolve_external_reference(value, reference_type, source, limit)`: find the
  work recorded under a number. Matching ignores case and everything that is
  not a letter or digit, so `REF-10422` and `ref 10422` match. Nothing else is
  guessed. It returns every candidate, the value as recorded and
  `match_count`. `has_more` means the list was cut; narrow by type or source.
  More than one candidate is reported, never resolved for you.

## Optional draft tools

These five exist only when `LEDGER_PROPOSALS` is set. A draft is a JSON file in
that directory, never a ledger row. Use drafts when a person should confirm a
decision before it is recorded. The person answers in the harness
conversation; the agent then records the outcome with the ordinary tools.

- `propose_review(proposal, actor, id)`: write one draft per decision: what
  would be recorded, the question for the person, the sources, and whether the
  agent needs the person's judgment (`needs_human`) or is confident. `id` is
  optional; when sent it must be a UUID. The `actor` must not be empty. A
  `work_id` must name an existing quote, booking or job of the `work_kind`
  given, and every ID inside `would_record` must be a UUID. `message_ids`
  and `sources` are the names the messages have at their source, such as the
  `source_locator` evidence is recorded under. They are not evidence UUIDs
  and are not checked.
- `list_proposals(status, work_id)`: all drafts, oldest first, as
  `{"proposals": [...]}`. Read it before proposing, so a decision is not
  asked twice.
- `read_proposal(id)`: one draft and what became of it. An unknown ID is
  refused as not found.
- `mark_proposal_recorded(id, memo_id)`: after recording, name the memo that
  carries the outcome. The memo is read back from the ledger first.
- `withdraw_proposal(id, reason, actor)`: withdraw a draft that was declined
  or no longer applies. It needs a reason and a non-empty `actor`.

# Changelog

## 0.2.0 (2026-10-01)

Money: find the right customer or vendor, record what is owed and what was
paid, both ways, and read what is open and how late.

New:

- Five tools: `find_parties`, `record_charges`, `record_payment`,
  `read_work_money` and `read_money_open`. The server now has 45 tools,
  plus 5 optional draft tools.
- `find_parties` finds a party by an exact email, phone or alias, by the
  words of its name, or by a name or alias of three characters or more
  inside the text. It lists candidates and never picks.
- A charge is a milestone with an expected (agreed) and an invoiced
  (billed) amount, side by side and never added. It is judged like any
  milestone: done is accepted, pending is waiting for detail, blocked is
  disputed, failed is waived.
- `record_charges` saves agreed prices, or a bill with the work it covers
  and its lines, in one transaction. A reissued bill replaces the old one.
- `record_payment` saves a payment and puts it on charges, or on a bill as
  a whole such as rent. A payment can wait until someone says what it
  was for.
- `read_work_money` reads a whole chain: each charge's expected, invoiced,
  paid and open amounts, due date and days past due, and sales minus costs
  per currency, and in the shop's own currency where that was recorded.
- `read_money_open` reads what is open for the business or one party,
  oldest due first, with payments not yet allocated, money paid before a
  bill, bills without lines and charges waiting for a judgment.
- Five new tables, all append-only: `invoices`, `invoice_work_links` and
  `charge_lines` in migration 016, `payments` and `payment_allocations` in
  migration 017. The ledger takes in what happened. It refuses only: the
  same ID sent again with different contents; replacing anything but the
  latest version; a charge's first line without both parties, or a later
  line between another pair; a second current amount of one kind on a
  charge; a payment with no amount; a payment put on something in another
  currency, or a currency change on a charge, payment or reissued bill
  that money in another currency is on; and allocations beyond a
  payment's amount. It does not refuse
  a payment by someone the charge does not name (the shop paying a bill
  addressed to its customer is recorded as the shop's), money left on a
  bill after its lines arrive, a charge billed again by a later bill, a
  reissued bill sent to other parties, or a credit as a line below zero. A
  line whose parties differ from its bill, or a reissue whose parties
  differ from its lines, is saved with a warning and marked in the reads.
- Money put on a bill as a whole stays on the bill: the reads never guess
  which line it settled. The bill shows it as `money_on_bill`, each of its
  charges as `bill_holds`, and `read_money_open` lists it as its own row.
  A bill whose lines moved to a later bill reads "lines now on" that bill.
- `read_work_money` gives each job its cash: what the shop paid out and
  took in on the job's charges and bills, read from the payments. It is
  cash, not margin, and money on a bill as a whole counts on one job
  only. Each allocation says who paid and who received, with the
  payment's reference and method. Totals say what the shop paid on bills
  between other parties, which sales minus costs leaves out.
- Skills: a money page in `update-the-state-machine`. `call-to-action`
  reads what is open, `break-glass` reviews what is owed after a job
  changes procedure, and `get-started` asks which currency the books are
  kept in and how to record departments.

Changed from 0.1.0:

- No 0.1.0 table changes. Migrations 016 and 017 only add tables and
  functions.
- Each item in `read_case_brief` gains `charges` (its milestones that have
  a charge line) and `invoices` (the bills linked to it).
- The skills look a party up with `find_parties` before creating one.
- `read_case_brief` names the quote, booking or job in "adopts no SOP
  version" and "has no recorded parties".

To upgrade, pull and run `.venv/bin/python postgres/migrate.py
"$DATABASE_URL"` as the owner. It applies only migrations 016 and 017.

## 0.1.0 (2026-09-29)

First public release.

- Postgres ledger: quotes, bookings and jobs, milestones, evidence,
  judgments with memos, SOP versions, parties and documents. Append-only,
  enforced by the database.
- MCP server with 40 tools, plus 5 optional draft tools.
- Five skills: `get-started`, `manage-sop`, `update-the-state-machine`,
  `call-to-action`, `break-glass`.
- Three example SOPs.

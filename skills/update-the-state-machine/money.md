# Money

The ledger records what is owed and what was paid, both ways. It works out
what is open when read, and never decides anything. It takes in what
happened, even when it looks wrong; it refuses only what would make the
reads lie. You record; the reads do the sums. Never add up money in your
head: read it.

Words:

- A **charge** is one priced thing on one quote, booking or job: the
  equipment, an extra, the sales tax. It is a milestone, so it is judged.
  One party owes it and one party is owed it.
- A charge has two amounts side by side, never added: **expected**, what
  was agreed, and **invoiced**, what the bill says.
- An **invoice** is the bill itself: number, dates, terms as written, total.
- A **payment** is money that moved. An **allocation** puts a payment, or
  part of it, on a charge or on a bill.

## What kind of message is it?

A quote or a price agreed; a bill; a reissued bill; a payment notice or
bank line; a statement; a reminder that something is late. Each is
evidence first: record it as in `SKILL.md` steps 1 to 3. The owner's word
in the conversation is evidence too, when that is all there is.

## Read before you write

1. Find each party with `find_parties`: the sender's email, then the name.
   One exact match: use it. A name match: ask the person whether it is the
   same one, then save the new email or spelling with
   `record_party_identifier`. None: ask, then `create_party`. Parties are
   never merged, so a duplicate splits every total for good.
2. `read_work_money` on the chain, and `read_money_open` for the party, so
   you see what is already recorded and paid.

## A price agreed

`record_charges` with no invoice: expected lines. Record it once, on the
stage where it was agreed, usually the quote. Never restate it on a later
stage; the reads total the whole chain. A deposit charge on a booking
carries no expected amount of its own.

## A bill

`record_charges` with `invoice`: number, dates, terms as written, stated
total, and `work` for the jobs it covers. Its lines are invoiced lines,
each on its own charge, usually on the job. Comparing a bill with the
quote is your job: tell the person what matches and what is new.

- A bill for a charge already billed **replaces, never adds**. A reissued
  bill is a new invoice with `replaces_invoice_id`; each changed line
  replaces the line it changes with `replaces_line_id`. A reissue may name
  other parties, such as a bill first sent to the wrong company; its
  lines keep their parties, the call warns, and the reads mark the bill
  and its charges parties_differ_from_bill. Ask who owes whom.
- A reissue in another currency is refused only when money in another
  currency is already on the bill or its lines: currencies are never
  mixed. With no money on it, or money in the new currency, it saves.
- A later bill may bill a charge again: its line replaces the charge's
  current invoiced line, naming the new bill. The old bill then reads
  "lines now on" the new one.
- Sales tax, fees and extras are charges like any other, so the lines
  match the bill's total. The read shows any difference.
- A credit is a line below zero, on its own charge, like any other line.
- Lines you cannot read: record the invoice with its total and no lines.
  The job reads "billed, stated total, lines not recorded". A total you
  cannot read either is left out ("total not stated"), but give the bill's
  currency anyway, so a payment can be put on it. Add the lines later with
  `invoice_id`. Money already on the bill stays on the bill.
- A bill that belongs to no job, such as rent: no `work`, no lines.
- A bill number the same issuer already used on a bill to the same
  recipient comes back as a warning. The bill is saved. Ask whether it is a duplicate.
- One line covering several jobs: split it into one line per job yourself,
  and say how in the reason.

## A changed amount

A new line with `replaces_line_id` and the reason; it keeps the charge's
parties, so leave them out. The old one stays. A charge with money on it
keeps its currency. A
lump that later arrives in detail is replaced by 0, and each part becomes
its own charge. A line put on the wrong charge is replaced by 0 and
recorded again on the right one; the empty charge stays.

## Judging a charge

With `record_review`, like any milestone: done is accepted, pending is
waiting for detail, blocked is disputed, failed is waived. Only the person
accepts, disputes or waives; ask them. A charge whose amount changed after
it was judged is marked in the reads: ask again.

## A payment

`record_payment`. The payer, the receiver, the amount and currency as the
bank shows them, and where it goes in `allocations`.

- No reference: record it with no allocations. It waits as unallocated
  until the person says what it was for; then allocate it with
  `payment_id`.
- Put a payment on whichever charge or bill it settled, whoever paid: the
  payment says who paid and who received, and the reads show both. The
  shop paying a vendor's bill addressed to its customer is recorded as the
  shop's payment, on that bill's charges.
- One transfer for several jobs: one payment, one allocation per charge.
- Allocate to lines whenever the mail says which lines were paid. When it
  does not, put the money on the bill itself and leave it there: the
  ledger never guesses which line it settled. The bill's open counts it;
  each charge shows it as bill_holds, and `read_money_open` lists it
  as its own row beside the lines.
- Paid on the wrong job: find the allocation's `id` and `payment_id` under
  `allocations` on the charge in `read_work_money`, then with that
  `payment_id` replace it with `replaces_allocation_id`, naming the right
  charge.
- A bounce or a refund is a new payment the other way, put on the same
  charge. `replaces_payment_id` is only for your own recording mistakes,
  such as the wrong payer; a currency changes only once the payment's
  allocations are lowered to 0.
- In another currency: give `home_amount` and `home_currency` when the
  bank or a stated rate says what it was in the shop's currency. The
  ledger converts nothing. Do the same on a charge line with a new line
  that replaces it.

## The paid milestone

If the SOP has a milestone such as "Balance paid", judge it like any
other, citing the payment's evidence. Nothing compares them for you.

## A statement

A vendor's or customer's statement lists open bills. Compare it with
`read_money_open` for that party. Record only what is new or different,
each from the statement as evidence, and ask about what does not match.

## A short payment or a write-off

A bank fee or a small discount: the difference stays open. When the person
says absorb it, replace the invoiced line with the amount received, and say
why in the reason. A customer who will never pay: the person waives the
charge (judged failed). A waived charge owes 0 and leaves the open list,
unless money was paid on it: then it stays listed at minus that money,
noted "waived, N paid", until the money is sent back or moved.

## After a recovery procedure

What is owed to the business stays. The reads mark charges recorded before
the job changed procedure: put each open one the business owes to the
person, and ask whether it still stands.

## Questions for the person

Is this the same customer or vendor? Accept or dispute this extra? What
was this payment for? Absorb the difference? Waive this charge? Chase now
or wait? Ask one at a time, with the amounts from the read.

## What to say back

From the reads, never from memory: what matches, what is new, what is
open and how late, and what waits on them. Quote the amounts and
currencies as the read gives them.

## Known limits

- A bill with no lines cannot be waived: it has no charge to judge. If the
  person writes it off, reissue it with a stated total of 0 and the reason.
- A bill recorded without its jobs gains them only by a reissue that names
  them in `work`.
- One line covering several jobs must be split by you, and a line on the
  wrong charge stays as a 0 there.
- Parties recorded twice before `find_parties` existed stay separate.

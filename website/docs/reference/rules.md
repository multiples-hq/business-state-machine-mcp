---
title: Rules
description: What the database enforces, and what it leaves to good practice.
---

# Rules

## Rules the ledger enforces

- **Append-only.** Rows are never updated or deleted; the database refuses
  both. A correction is a new row: a new judgment, a role ended by a
  replacement row, a new document version, a new status row, or a charge
  line, invoice version, payment or allocation that replaces an earlier one.
- **Every write has an actor.** An empty actor is refused. The label is a
  claim. It is not authenticated, and recording an adoption or a review does
  not prove that anyone approved it.
- **Judgments cite evidence.** A judgment with no evidence ID is refused. So
  are a document assessment, an SOP adoption and an SOP status change.
- **A judgment needs a memo.** At commit, the database refuses a new judgment
  that is not linked to a memo on the same work item. `record_review` saves
  both together.
- **Linked evidence stays with its work.** See [Evidence and files](tools.md#evidence-and-files).
- **One owner.** A phase, a milestone and a memo each belong to exactly one
  quote, booking or job. Judgments linked by `revises_ids` or `based_on_ids`,
  and the items a memo lists, must share that owner. A booking and its job are
  different owners; nothing is copied between them.
- **One SOP per chain**, chosen at the quote. See [How adoption works](tools.md#sop-versions-and-adoption).
- **Retries are safe.** A write that reuses an ID with exactly the same
  contents returns the same ID and writes nothing. The same ID with different
  contents is refused. Keep IDs stable when you retry, including every
  judgment, memo, role and binding ID inside a review or an adoption.
- **Status is never derived.** A milestone's status is its latest judgment.
  A phase has no status.
- **Money.** The ledger takes in what happened and refuses only these: a
  charge has one current line of each kind, and a new one must replace it;
  a charge's first line names both parties, and the charge keeps that one
  pair; only the latest version of a line, bill, payment or allocation is
  replaced; a payment has an amount; a payment and what it goes on share
  one currency, a charge with money on it keeps its currency, a bill
  reissued while money in another currency is on it or its lines keeps
  that currency, and a payment's currency changes only with nothing
  allocated; the allocations
  of a payment never add up to more than its latest amount, checked when
  the call commits, with the payment locked so that two calls on it take
  turns. It does not refuse a payment from a party the charge does not
  name, a charge billed by a second bill, a reissue to other parties, money
  on a bill that has lines, a negative line, or a line whose parties differ
  from its bill (a warning, as is a reissue whose parties differ from its
  lines). Money left on a bill as a whole stays there: the ledger never
  guesses which line it settled.

## Advice the ledger does not enforce

These are good practice. The database refuses none of them, on purpose: the
ledger allows work with no SOP and milestones that no SOP named.

- **Adopt an SOP before the first review.** Adopt a version on the quote
  before the first `record_review` on its chain. If none fits, or it is
  unclear which one does, ask a person rather than pick. Judging milestones
  with no SOP adopted is allowed. The case brief then lists the work under
  `not_recorded` as adopting no SOP version and shows those milestones with
  `from_sop` false; `read_work_sop` lists them as `unadopted_milestones`.
- **Look before you create.** Call `list_work` before creating work,
  `find_evidence` before recording a source and `find_parties` before
  creating a party. Creating or recording twice is not refused.
- **Money advice.** An agreed amount is recorded once, on the stage where it
  was agreed; a deposit charge on a booking carries no expected amount of
  its own. A duplicate bill number is a warning, not a refusal. A waived
  charge is a `failed` judgment, not a line set to 0. None of these is
  refused.
- **Link evidence to its work.** Evidence with no links can be cited from
  anywhere, so nothing forces you to link it. Link it anyway, so the case
  brief shows it on the right chain.
- **Cite evidence for roles and identifiers.** A role with no `evidence_id`
  is accepted and reported as uncited.

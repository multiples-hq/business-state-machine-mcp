---
title: Rules
description: What the database enforces, and what it leaves to good practice.
---

# Rules

## Rules the ledger enforces

- **Append-only.** Rows are never updated or deleted; the database refuses
  both. A correction is a new row: a new judgment, a role ended by a
  replacement row, a new document version, a new status row.
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

## Advice the ledger does not enforce

These are good practice. The database refuses none of them, on purpose: the
ledger allows work with no SOP and milestones that no SOP named.

- **Adopt an SOP before the first review.** Adopt a version on the quote
  before the first `record_review` on its chain. If none fits, or it is
  unclear which one does, ask a person rather than pick. Judging milestones
  with no SOP adopted is allowed. The case brief then lists the work under
  `not_recorded` as adopting no SOP version and shows those milestones with
  `from_sop` false; `read_work_sop` lists them as `unadopted_milestones`.
- **Look before you create.** Call `list_work` before creating work and
  `find_evidence` before recording a source. Creating or recording twice is
  not refused.
- **Link evidence to its work.** Evidence with no links can be cited from
  anywhere, so nothing forces you to link it. Link it anyway, so the case
  brief shows it on the right chain.
- **Cite evidence for roles and identifiers.** A role with no `evidence_id`
  is accepted and reported as uncited.

---
name: update-the-state-machine
description: Bring the ledger up to date from an update - an email, a call note, a document, or an answer the person gave - by recording it as evidence, tying it to the right quote, booking or job, and judging milestones with cited evidence and a memo. Use whenever new information arrives about tracked work, one update or a batch, including catching up on a backlog.
---

Goal: every update about tracked work is recorded unchanged, tied to the
chain it concerns, and reflected in judgments that cite it. Anything else
stays out of the ledger.

The ledger records; you decide. It derives no status and guesses nothing. You
may be a fresh process with no memory of earlier runs; the ledger has that
memory, so read it before you write. Words: [vocabulary.md](vocabulary.md).

## For each update, in this order

1. **Is it about work?** Read it. If it concerns no quote, booking or job
   the business tracks or would start (a newsletter, personal mail, an
   advert), record nothing, say so in one line and stop. Recorded evidence
   can never be removed. If you cannot tell, ask the person first.
2. **Record it once.** `find_evidence` with the update's locator as
   `source_locator`. If a row comes back, cite that row and record nothing
   new. Otherwise `record_evidence` with the content unchanged, the locator
   and the time it happened as `source_at`, and no `attachments`. Then
   store each attachment with `put_file` or `record_file_by_hash`, as the
   source provides it; each becomes its own evidence row, which you link
   to the work in step 3. What the
   source should hand you is in the `get-started` skill's source contract.
3. **Find the work.** Put every outside reference number through
   `resolve_external_reference`. Call `list_work`, and `read_case_brief` on
   likely candidates, before creating anything; an earlier run may have
   created it. One update may concern several chains; handle each. When
   the update clearly names two quotes, it is about both. When it could
   belong to more than one and does not say which, ask the person; never
   pick. Create only what the evidence establishes: a new request is
   `create_quote`; the customer's acceptance is `create_booking` under its
   quote; a piece of work being scheduled or carried out is `create_job`,
   then `link_job_booking`. When the SOP's criteria or the harness
   instructions say when a job opens, follow them. Record each new outside
   number with `record_external_reference`: `reference_type` says what it
   is (a quote number, an order number) and `source` who issued it. Link
   the evidence and each attachment's evidence to every work item it
   concerns: `about_work` takes one `{id, work_kind, work_id}` per item,
   with a new UUID as `id`, or call `link_evidence_work` later.
4. **The SOP comes first.** `read_case_brief` shows whether the chain follows
   an SOP. If it does not, adopt one on the quote, or on a job that has no
   booking: the version the harness instructions name, or, if they name none,
   the one the person chooses from `list_sop_versions` (status `active`). Ask;
   never pick. Adopt on a job that has no booking only when it will stay on its
   own: a job that adopted cannot later be linked under a booking whose quote
   follows a different version. When a booking is expected, wait and link the
   job first. `read_sop_version` gives the stage's phases and milestones; bind
   every one with a new ID in `adopt_sop_version`, citing the evidence that
   started the work and the person's answer. Bookings and jobs under the quote
   follow it on their own. Until the chain has an SOP, judge nothing: leave a
   memo with `leave_work_memo` saying what arrived and that judging waits on
   the SOP.
5. **Read before you judge.** `read_work_review` for the milestones and
   their latest judgments, `read_work_sop` for the criteria, and the latest
   memo from `read_work_memos`. Look back through the ledger, not the
   inbox: what an earlier update established is in its evidence and the
   judgments that cite it.
6. **Record one review per work item.** One `record_review` with the
   judgments this evidence moves, the parties and roles it shows, and a
   memo saying what changed and what is waiting. A booking and its job are
   separate work items with separate reviews. How to judge:
   [judging.md](judging.md).
7. **Read back, then hand over.** `read_case_brief` for each chain you
   touched. Then run the `call-to-action` skill for those chains.

## The person's answers

When the person answers a question, record the answer as evidence before
acting on it: the question and the answer word for word as the payload, a
locator such as `chat:` followed by the time, and that time as
`source_at`. Link it to the work it concerns and cite it like any email.

## Batches and backlogs

Take updates oldest first, so later evidence revises earlier judgments in
the order things happened. Record and place every update of the batch
(steps 1 to 4), then run steps 5 to 7 once per work item over all of its
new evidence. Catching up on old mail is the same skill with a longer
batch. A question that later evidence already answers is not asked.

## Never

- Never judge a milestone on a chain that follows no SOP.
- Never guess. Every date, amount, name and reference comes from recorded
  evidence or the person's answer. Unknown stays unknown.
- Never pick between two work items when the update does not say which.
- Never choose, adopt or change an SOP version on your own.
- Never send anything to anyone. Questions go to the person.
- Never record an update that is not about work.

Done when: each update is recorded once or knowingly skipped, each touched
chain's read-back shows the new judgments with their evidence and one memo
per reviewed work item, and `call-to-action` has run.

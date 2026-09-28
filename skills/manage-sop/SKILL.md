---
name: manage-sop
description: Write, revise or retire the SOP (standard operating procedure) the ledger judges work against - the phases and milestones of the quote, booking and job stages. Use when setting up the ledger, when someone shares a training document or describes how they work, or when their process changes.
---

Goal: a published SOP version that describes how this business really
works, approved by the person, with milestones an agent can judge from an
email alone.

An SOP here has three stages: quote, booking and job. Each stage has
phases, and each phase has milestones. A milestone has a key, a short title
and a criterion: the evidence that shows it happened. The ledger never
evaluates a criterion; the agent reads it when judging. The exact shape and
a worked example are in [sop-format.md](sop-format.md).

A published version never changes. A change is a new version. Each chain
follows the version its quote adopted, to the end.

## Write the first version

1. **Start from what they have.** Ask for a training document, checklist,
   onboarding guide or a few real email threads. Read it and pull out the
   steps. If they have nothing written, interview them:
   - How does a request for work arrive, and what do you send back?
   - What makes a customer say yes, and what do you need from them then?
   - What must be true before the work starts?
   - What does finished mean, and who confirms it?
   - What goes wrong most often, and how do you notice?
2. **Place each step in a stage.** The quote runs from the request until
   the customer answers the offer. The booking starts with their yes and
   holds what is arranged after it: signing, deposit, ordering,
   scheduling. The job is one piece of work being carried out; a booking
   may lead to several. Ask the person when a job begins, and make that the
   criterion of the job stage's first milestone. All three stages must be
   present. A stage may be empty, for a business that has no bookings or
   never quotes.

   An SOP can go straight to the job, but recommend all three stages and
   say why. Many businesses track only the work itself: a freight
   forwarder tracks shipments, an installer tracks installs. The quote
   stage shows which offers wait on the customer and need a follow-up. The
   booking stage holds what must be agreed before work starts: the
   signature, the deposit, the date. Without them, the work the business
   is still winning, or has won but not arranged, is invisible. If the
   person still wants jobs only, leave the other two stages empty.
3. **Write milestones as outcomes, not tasks.** "Deposit received", not
   "Chase the deposit". A title is a short noun phrase of at most six
   words, with no names, numbers or dates. The criterion says what a
   message must show, in the business's own words, and what does not
   count: "Cited evidence shows the customer accepting the price in
   writing. A verbal yes reported by staff is not enough."
4. **Keep it small.** Only milestones that change what someone does next.
   When one job takes a turn the SOP does not name, the agent adds a
   milestone to that job alone; the SOP does not need to foresee
   everything.
5. **Show the draft before anything is recorded.** Present it as an
   outline: stage, phase, milestone title, criterion. Ask what is wrong or
   missing. Repeat until the person says it is right.
6. **Publish on their explicit yes.** Record their approval as evidence first
   with `record_evidence`: their words as the payload, a locator such as
   `chat:` followed by the time, and that time as `source_at`. Then call
   `publish_sop_version` with tag `standard`, a name they recognise and version
   `"1"`, sent as text. Read it back with `read_sop_version` and confirm the
   outline matches.
7. **Agree the default.** Ask whether new work should follow this version
   without asking each time. If yes, write the version's name, number and
   ID into the harness instructions. Otherwise the agent asks at every new
   quote.

## Revise

1. Read the current version: `list_sop_versions`, then `read_sop_version`.
2. Draft the change and show the person only what differs.
3. On their yes, record the approval as evidence and publish the new
   version with `based_on_version_id` set to the old one. Where a
   milestone's meaning is unchanged, keep its title, its criterion and its
   phase's name exactly as they were: a job moved to the new version keeps
   that milestone's history only when all three match.
4. Ask whether the old version should be retired. Retiring stops new
   chains from adopting it: `set_sop_version_status` with status
   `retired`, a reason and the evidence of their instruction.
5. Say what happens to work already running: every chain stays on the
   version it started with. Only a job can move to the new one, one at a
   time, with the `break-glass` skill. A quote or booking cannot move.

## Recovery procedures

Once the standard SOP exists, offer to write a recovery procedure for what
goes wrong often: a cancellation, damage, a redo. It is published the same
way with tag `break_glass`, and a job moves onto it with `break-glass`.

Write a recovery procedure as a fork of the SOP it recovers from:

- **Up to the break point, copy.** Every milestone that comes before the
  thing that went wrong is copied word for word: the same title, the same
  criterion, in a phase of the same name. A job that moves onto it keeps
  those milestones and their status.
- **From the break point on, new steps.** The milestone that failed is left
  out; the steps that replace it and everything after follow.
- **Unknown steps wait.** Write only the steps known today. When more
  become known, publish version 2 based on version 1, with the same copied
  part, and move the job again with the person's yes.
- **One-off steps stay on the job.** A step that belongs to one job only,
  not to the procedure, is added to that job and not published.

Set `based_on_version_id` to the SOP it forks from.

## Never

- Never publish, retire or choose a version without the person's explicit
  yes. The agent drafts; the person decides.
- Never invent steps the person did not describe or the document does not
  contain. Ask.

Done when: the version the person approved is published and read back, and
the harness instructions say which version new work follows, or that the
agent asks.

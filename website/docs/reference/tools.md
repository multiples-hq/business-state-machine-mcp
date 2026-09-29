---
title: Tools
description: All 40 ledger tools and the 5 optional draft tools.
---

# Tools

There are 40 tools, plus 5 optional draft tools. Every ID is a UUID that the
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
  SOP adoption named shows `from_sop` false. Phases come in the order of
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

Parties are never merged. The same company under two names is two rows.

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

---
title: Refusals
description: How a refused call reads.
---

# Refusals

A refused call comes back as an MCP tool error: `Error executing tool <name>: ` and then one sentence. No refusal is blank. The common ones:

- `<argument> must be a UUID, got '...'`: the named argument did not parse.
  An ID inside a list is named by its place, such as
  `judgments[0].milestone_id` or `phase_bindings[0].phase_id`.
- `<argument> must be an ISO 8601 time with a UTC offset, such as 2026-03-01T09:30:00+07:00 or ending in Z; got '...'`, and `<argument> must be a calendar date written YYYY-MM-DD, such as 2026-03-01; got '...'`.
- `<argument>: Input should be 'quote', 'booking' or 'job' (got '...')`: a
  word outside a fixed list, or any other argument that does not fit the tool
  schema. Several problems are joined with `; `.
- `actor must not be empty`, `title must not be empty`, and the same for
  every other required text.
- `evidence ID does not exist: cite evidence you recorded or found`: an
  `evidence_id` names no evidence row.
- `the quote named does not exist: create it first with create_quote, or find its ID with list_work`, and the same for a booking, a job and a party.
- `review_ended_at must not be before review_started_at`, `ended_on must not be before started_on`, `display_order must be 0 or more`.
- `a former role needs ended_on: the day the role ended`.
- Money: `this charge already has a current expected line (...): a new amount replaces it, never adds; name it in replaces_line_id`, `a charge has one pair of parties ...`, `the allocations of this payment add up to ..., more than the payment's ...`, `the payment is in ... and what it goes on is in ...: currencies are never mixed`, `this charge already has money paid in ..., so its lines stay in ...`, `this bill or its lines already have money paid in ..., so a reissue stays in ...`, `a known amount or rate needs its currency, such as USD`, `that charge line is already replaced; replace the latest line of its chain`, `that invoice version is already replaced; record the line on its latest version`, `lines[0].amount must be a number, written as text such as "1250.00" or as a whole number; got ...`, and `... is an invoice, not a milestone: judgments go on milestones ...`.
- `an SOP with this name and version is already published`.
- `this quote already follows an SOP; only a job can replace its SOP version`, and the same for a booking, with or without
  `expected_previous_adoption_id`. A job is told to name its current adoption
  in `expected_previous_adoption_id`.
- `a chain adopts its SOP once, at the quote; its bookings and jobs follow it`, and `SOP version is retired; a chain cannot adopt it`.
- `work not found: <id>`, `evidence not found: <id>`, and the same for a
  party, a milestone, a job, a document version, an SOP version, an SOP
  adoption and a draft.
- `... ID already has different contents`: a retry changed what it sent.

Any other rule the database refuses is reported in the database's own words,
which may name a table and a constraint. The sentence is never empty.

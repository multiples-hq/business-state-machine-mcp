# Business state machine MCP

**A Postgres ledger and MCP server that keeps the state of a
business: every quote, booking and job, what has happened, what is next,
and the evidence behind each step.**

[Quickstart](#quickstart) · [What you get](#what-you-get) ·
[Core concepts](#core-concepts) · [MCP server](#the-mcp-server) ·
[Skills](#the-skills) · [Recommendations](#our-recommendations) ·
[Example SOPs](examples/README.md)

## Quickstart

### With your AI agent (recommended)

Paste this into your agent:

```
Set up the business state machine ledger from
github.com/multiples-hq-jc/business-state-machine-mcp for my business.

Read skills/get-started/SKILL.md in that repository and follow it.

Ask me whatever it needs, and install nothing without asking me first.
```
A quick way to test this yourself:

1. Make sure your agent can reach your inbox, through your mail tool.
2. Learn what an SOP and a milestone are, and write your SOP with the
   agent.
3. Pick one real quote, booking or job. Have the agent find every past
   email about it and record them, then ask "what is waiting on me?"

Setting it up yourself? Follow [mcp/README.md](mcp/README.md). The server
is connected when your agent app lists 40 ledger tools (45 with the
optional draft tools) and, on a new database, `list_work` returns
`{"work": []}`.

## Are you an AI agent?

Read [skills/README.md](skills/README.md) to install the skills, then
follow `skills/get-started/SKILL.md`. The full tool reference is
[mcp/README.md](mcp/README.md). Ask your person before installing
anything.

## What is this?

At Multiples we buy durable service businesses and make them AI native. 

On day one we don't hand the business to a persistent agent. The operators
first learn to run their own manual process through an agent harness, the
tool they use to drive a fleet of agents. Whether a human stays in the loop
or an agent runs on its own, the business needs one machine that holds its
state: which jobs, visits, shipments and quotes exist, what has happened
to each, and what should happen next. It has to work the same way in every
business we run, so we built it once and opened it up.

The ledger records; your agent decides. The server derives no status and
guesses nothing. Every status an agent sets must cite the recorded evidence
it rests on, such as an email, a document or your answer, and nothing
recorded can be edited or deleted.

## What you get

Your mail tool hands each email to your agent. The agent records it in the
ledger and updates the milestones it supports: the steps your SOP (your
written procedure) lists for every job. Here is one job from a made-up
sign shop we test with; nothing here is real, and nothing like it ships
with the ledger. The ledger returns data, not a screen; this is how the
agent summarised it (shortened):

```
Corner Cafe fascia sign                   SOP: Bright Signs sign work v1
  quote    Enquiry received         done      <a1@mail.example>
           Quote sent               done      <a3@mail.example>
  booking  Proof approved           done      <a4@mail.example>
           Deposit received         done      <a4@mail.example>, your answer
  job      moved to recovery SOP "Reprint after damage" v1: face cracked on install
           Damage reported          done      <a5@mail.example>
           Replacement printed      pending   <a5@mail.example>, your answer
           Completion form signed   blocked   <a5@mail.example>: "Customer not signed off"
           Balance paid             unassessed
           history: Sign printed done · Installed on site failed
  waiting for: Bright Signs: reprint the acrylic face and book the refit at
               Corner Cafe; then customer sign-off.
```

Each `<…@mail.example>` is the ID of the email behind that status. "Your
answer" means the agent asked you a question in the chat and recorded your
reply as evidence. `pending` means not yet done with nothing in the way,
and its evidence shows where the step stands; `blocked` means someone else
must act first; `failed` means it was tried and did not happen;
`unassessed` means no one has judged it yet. `waiting for` comes from the
agent's latest memo on the job. When the sign cracked, the agent moved the
job to a recovery SOP (the `break-glass` skill covers this); `history`
shows the steps from its earlier SOP that no longer apply.

From this the agent tells you, in the chat, what only you can unblock
and which follow-ups are due. For example, it writes:

```
Unblock me
  Corner Cafe fascia sign: when is the refit booked? (a date / not yet)
    A reprint is needed and the refit has no date. <a5@mail.example>, your answer
Follow-up needed
  Corner Cafe fascia sign: the customer has not signed the completion form.
    The installer reported "Customer not signed off". <a5@mail.example>
  Shall I draft a reminder for you to send, will you handle it, or wait until a date?
```

## One email, end to end

What the agent does with one email; owners can skip to the next section.
In short: the agent files the email and its PDF, finds the quote by its
number, opens the booking, marks "Contract signed" done and tells you
what is next. Step by step, with the tools it calls:

Quote Q-1042 follows the
[HVAC installer SOP](examples/hvac-installer-sop.json). When the agent
created the quote, it also saved the quote number, with
`record_external_reference`. The customer replies: "Signed contract
attached." The agent:

1. Looks the email up by its Message-ID with `find_evidence`. It is new, so
   `record_evidence` stores it word for word, and `put_file` stores the
   signed PDF as a second piece of evidence.
2. Finds the quote with `resolve_external_reference` on "Q-1042", creates
   the booking with `create_booking`, which gives it the SOP's booking
   milestones, and links the email and the PDF to it with
   `link_evidence_work`.
3. Reads the booking's milestones with `read_work_review`, then calls
   `record_review`: "Contract signed" is `done`, citing the email and the PDF, with a memo
   saying the work now waits for the deposit.
4. Reads the quote and its booking back with `read_case_brief` and tells
   you what is waiting on you.

We ran these calls in this order on a test ledger, after publishing the
HVAC SOP, creating the quote, adopting the SOP at the quote and recording
the quote number; each one succeeded.

## Core concepts

Every ledger record lives in one Postgres schema, `spine` (the project's
working name for the ledger). File bytes live
in a folder on disk, named by the SHA-256 hash of their contents.

```
 quote ──┬── booking ──┬── job       a quote with its bookings and jobs is
         │             └── job       one chain; the chain adopts an SOP at
         └── booking ───── job       its quote, and a job can stand alone

 each quote, booking and job can have milestones, grouped in phases or not

   evidence ◀── cites ── judgment ── sets the status of ──▶ milestone
                            │
                 a review saves its judgments with one memo
```

**Append-only.** Every ledger table refuses `UPDATE`, `DELETE` and
`TRUNCATE`. Logins can read the tables but write only through database
functions, and each function checks what it writes. To
correct a judgment, a document or a role, the agent adds a record: a newer
judgment, a new version of the document, or an end to the wrong role and
the right one. Work titles and outside reference numbers cannot be
corrected. Every write carries an actor label that names who wrote it, such as
`agent:intake`; it is a label, not a login.

**Quotes, bookings and jobs.** A quote is a request for work and the offer
made for it. When the customer accepts, the agent creates a booking under
the quote; a quote can have several. A job is one piece of work carried
out, linked to one booking or standing on its own with no quote, such as
repeat maintenance. Other systems' numbers for the same work, such as an
order number, are recorded as external references, so a later email that
quotes one can be traced to its work.

**Evidence.** An email, note or file, stored word for word, with where it
came from and when, if known. Evidence can be linked to the work it is
about. Evidence linked to a piece of work can support new statuses only on
that work; evidence linked to nothing can support any status. The ledger
does not stop the same email being recorded twice, so agents check with
`find_evidence` first.

**Milestones and phases.** A milestone is an outcome that evidence can
show, such as "Deposit received". It belongs to one quote, booking or job,
the three stages of the work. A phase is an optional named group of
milestones.

**Judgments, reviews and memos.** A judgment sets a milestone to `done`,
`pending`, `blocked` or `failed`, with an explanation, and cites at least
one piece of evidence. A milestone's status is its latest judgment; one
never judged reads as `unassessed`. A review is one assessment of a
quote, booking or job. It saves its judgments with one memo: what changed,
what was decided and, if known, what the work waits for and when to look
again. The database refuses a judgment without a memo.

**SOPs.** Your standard operating procedure: the phases and milestones for
each stage, each milestone with a criterion saying what evidence shows it
is met. It is saved as named versions, such as v1 and v2, and a published
version never changes; to change it, you publish a new one. Attaching a
version to work is called adopting it. The agent adopts a version at the
quote, and the quote's bookings and jobs follow it with no further call; a
job with no quote adopts its own. While a version is retired it cannot be
adopted, but work that already follows it keeps it, including new bookings
and jobs under its quote.

Only a job, under a booking or on its own, can move to another version,
such as a recovery procedure when the work goes wrong. If the new version
repeats a milestone word for word, in a phase of the same name, the agent
keeps its judgments by reusing that milestone's ID and its phase's ID. The
other milestones stay readable as history.

**Parties and documents.** A party is a person, an organization or an
agent, with the email addresses, phone numbers, addresses and other names
it was seen under. Roles connect parties to work and to each other: the
customer on a job, or a person who works at a supplier. A job can list the
documents it needs, with every version submitted and whether each was
accepted.

## The MCP server

A Python program that your agent app starts locally and talks to over
MCP (Model Context Protocol, the standard way agent apps call tools), on
standard input and output. It holds one database
connection, answers one tool call at a time and calls no outside system.
The agent supplies a UUID for each ledger record it creates, so
retrying a call with the same ID and contents is safe. The phases and
milestones a booking or job takes from its quote's SOP get their IDs from
the database.

It has 40 tools:

| Group | Tools |
| --- | --- |
| Find and read work | `list_work`, `read_case_brief`, `read_work` |
| Create work | `create_quote`, `create_booking`, `create_job`, `link_job_booking` |
| Evidence and files | `record_evidence`, `find_evidence`, `link_evidence_work`, `read_evidence`, `put_file`, `record_file_by_hash`, `read_file` |
| Milestones, reviews and memos | `create_work_phase`, `create_work_milestone`, `record_review`, `leave_work_memo`, `read_work_review`, `read_work_memos`, `read_history` |
| SOPs | `publish_sop_version`, `list_sop_versions`, `read_sop_version`, `set_sop_version_status`, `adopt_sop_version`, `read_work_sop`, `read_sop_adoption` |
| Parties | `create_party`, `record_party_identifier`, `record_role`, `end_role`, `read_party` |
| Outside reference numbers | `record_external_reference`, `resolve_external_reference` |
| Documents on a job | `create_document_requirement`, `submit_document`, `assess_document`, `read_documents`, `read_document_assessments` |

Set up the database first, as in [mcp/README.md](mcp/README.md). Then add
the server to your agent app's MCP settings. The format differs by app;
many take a block like this:

```json
{
  "mcpServers": {
    "ledger": {
      "command": "/path/to/repo/.venv/bin/python",
      "args": ["/path/to/repo/mcp/mcp_server.py"],
      "env": {
        "LEDGER_DSN": "postgresql://your_runtime_login:password@localhost/your_database",
        "LEDGER_FILES": "/path/to/files",
        "LEDGER_DROP": "/path/to/drop"
      }
    }
  }
}
```

`LEDGER_DSN` uses the runtime login that setup creates. It owns nothing,
and it must be a member of `ledger_client` because the server switches to
that role; this protects nothing on its own, since any login can write
through the ledger's functions (see the limits below). Keep the owner
login's password out of this file. `LEDGER_FILES` is where file bytes are
kept. `LEDGER_DROP` is a folder where another program, such as your mail
tool, can save files named by their SHA-256 hash, for the agent to record
with `record_file_by_hash`. It is required; if nothing saves files there,
give any path, which need not exist; the server never creates it.
[mcp/README.md](mcp/README.md) documents every tool.

Two settings are optional. `LEDGER_LOG` names a log file that gets a line
per tool call, with the first 300 characters of each argument, so it can
hold parts of your emails. Logging is best effort: a call whose
arguments do not match the tool's schema, or a failed write to the log,
leaves no line.
`LEDGER_PROPOSALS` names a folder for draft files and adds five draft
tools that let an agent save a proposed decision for your approval before recording it (45
tools in all). The server does not force the agent to ask first.

## The skills

Five skills teach an agent to run the ledger. Each is a folder
holding a `SKILL.md` file, so any agent app that reads skills can use them;
[skills/README.md](skills/README.md) says how to install them.

| Skill | When to use it |
| --- | --- |
| `get-started` | Once. It asks you where the ledger should run, installs it, connects your agent app and agrees with you which details your mail tool passes to the agent. |
| `manage-sop` | Once, and whenever your process changes. It turns a training document or a conversation into an SOP version. |
| `update-the-state-machine` | For every update, or a backlog of them. It records the update, finds the work, judges the milestones it moves and leaves a memo. |
| `call-to-action` | After each update, or when you ask what is waiting on you. It lists the questions only you can answer and offers to draft follow-ups. |
| `break-glass` | When a job goes off its normal path, or your process changed mid-job. It moves the job onto a recovery procedure or a newer SOP version, with your approval. |

## Our recommendations

- **Let your own tool read the mail.** A mail MCP server for Gmail or
  Outlook, an email client with an agent, or a skill of your own picks the
  messages that matter and hands each one to your agent. Pasting an email
  into the chat works too.
- **Track every piece of work as quote, then booking, then job.** An SOP
  can go straight to the job, and many businesses think only in jobs: a
  freight forwarder tracks shipments, an installer tracks installs. But
  the quote stage shows which offers are waiting on the customer, and the
  booking stage holds what must be agreed before work starts, such as the
  signature, the deposit and the date. Without them, work you are still
  winning, or have won but not arranged, is invisible.
- **Write your own SOP.** No example for your trade? The `manage-sop` skill
  turns your checklist or training document into one.
- **Give each quote or job an SOP before the agent marks progress.** The
  database allows judgments on work that follows no SOP; the work summary
  from `read_case_brief` flags that work as having none, and the skills
  will not judge it until it has one.
- **Answer the agent's questions in the chat.** It records each answer as
  evidence, so the statuses that rest on it can cite it.
- **Where to host it.** We run Postgres on a private VPS and reach it over
  Tailscale. Working alone, your own computer is fine, with Postgres
  installed or in Docker. Hosted Postgres such as Supabase, Neon or Amazon
  RDS works if the provider lets you create roles, grant one role to
  another, and create `SECURITY DEFINER` functions and triggers. The
  `get-started` skill asks which you want and explains the trade-offs.
  Another database, such as Snowflake, would need the rules rebuilt,
  because they are Postgres functions and triggers.
- **Files stay in a plain folder.** Attachments are stored as evidence in
  a folder on the machine that runs the server, each named by the SHA-256
  hash of its contents. No S3 or R2 is needed.

## What it is not

No user interface, no pricing or invoicing, no email client, no scheduler,
and no automatic statuses.

Limits today: one tool call at a time; `list_work` returns 200 items by
default and at most 1,000, with no paging; file tools take up to 8 MiB;
no native Windows. There are no user accounts or per-user permissions: the
ledger's tables and write functions are granted to every login, so any
login that can reach the database can read everything and make every
write, and the actor label is not checked. Give the ledger a database of
its own.

## License

[Apache 2.0](LICENSE).

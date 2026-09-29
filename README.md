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

We've been running into the same problem at every company we try to deploy AI. We need a simple shared ledger across every operator's harness to track the state of a repetitive test that they are working on across our funnels. And that gave us the idea of the business state machine, MCP. This business state machine, MCP, is a simple ledger. It tracks the evidences, the decisions, and the reasoning reasons of every single decision the AI agent makes against a milestone.

A milestone is an item of a checklist that tracks the overall progress of a business task. If all the milestones are checked off, this task is done.

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
the quote; a quote can have several bookings. A job is one piece of work 
being executed, linked to one booking, such as a site visit, a shipment, 
an appointment maintenance. Other systems' numbers for the same work, 
such as an order number, are recorded as external references, so a later 
email that quotes one can be traced to its work.

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

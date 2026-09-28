# Business state machine MCP

**A Postgres ledger and MCP server that keeps the state of a
business: every quote, booking and job, what has happened, what is next,
and the evidence behind each step.**

[Quickstart](#quickstart) · [Core concepts](#core-concepts) ·
[How it works](#how-it-works) · [Skills](skills/README.md) ·
[Server reference](mcp/README.md) · [Example SOPs](examples/README.md)

## Quickstart

### With your AI agent (recommended)

Paste this into your agent:

```
Set up the business state machine ledger from
github.com/multiples-hq-jc/business-state-machine-mcp for my business.
Read skills/get-started/SKILL.md in that repository and follow it. Ask me
whatever it needs, and install nothing without asking me first.
```

In Claude Code, install the skills first:

```
/plugin marketplace add multiples-hq-jc/business-state-machine-mcp
/plugin install business-state-machine-mcp@business-state-machine-mcp
```

The `get-started` skill asks where the ledger should run, sets it up,
connects your email source and walks you through writing your SOP.

### By hand

You need Python 3.10 or newer and Postgres 16.

```sh
git clone https://github.com/multiples-hq-jc/business-state-machine-mcp.git
cd business-state-machine-mcp
python3 -m venv .venv
.venv/bin/pip install -r mcp/requirements.txt
```

Then follow [mcp/README.md](mcp/README.md): create three Postgres roles, run
the schema and migrations, and register the server in your harness with
`LEDGER_DSN`, `LEDGER_FILES` and `LEDGER_DROP`. List the tools to check:
you should see 40.

## Are you an AI agent?

Read [skills/README.md](skills/README.md) to install the skills, then
follow `skills/get-started/SKILL.md`. The full tool reference is
[mcp/README.md](mcp/README.md). Ask your person before installing
anything.

## What is this?

At Multiples we buy durable service businesses and make them AI native. On
day one we don't hand the business to a persistent agent. The operators
first learn to run their own manual process through an agent harness, the
tool they use to drive a fleet of agents. Whether a human stays in the loop
or an agent runs on its own, the business needs one machine that holds its
state: which jobs, visits, shipments and quotes exist, what has happened
to each, and what should happen next. It has to work the same way in every
business we run, so we built it once and opened it up.

The ledger records; your agent decides. The server derives no status and
guesses nothing. Every status an agent sets must cite the email or document
that proves it, and nothing recorded can be edited or deleted.

## Core concepts

The shape we recommend follows the quote-to-cash path most service
businesses already use:

1. A request for work becomes a **quote**.
2. When the customer accepts the quote, it becomes a **booking**.
3. When your own team, or your vendors and contractors, can honor the
   booking and the work is confirmed, it becomes a **job**.

A quote with its bookings and jobs is one **chain**, and each chain follows
one **SOP**. Under each quote, booking or job sit **phases** (optional
groups) and **milestones** (outcomes evidence can show, such as "Deposit
received"). A **judgment** sets a milestone to one of four words, citing
**evidence**. A **memo** records what each review changed and what is
waiting.

| Read | For |
| --- | --- |
| [skills/README.md](skills/README.md) | The five agent skills: get started, manage the SOP, update the state machine, call to action, break glass. |
| [mcp/README.md](mcp/README.md) | Setup, settings, every tool, the rules the ledger enforces, refusals and known limits. |
| [examples/README.md](examples/README.md) | Three example SOPs: an HVAC installer, an event caterer and a freight forwarder. |
| [postgres/](postgres/) | The schema and the numbered migrations. |

## What it does

- **Every status has proof.** A milestone is marked done, pending, blocked
  or failed only with the evidence that shows it: an email, a file, or your
  own recorded answer.
- **History can't be rewritten.** The database only gains rows. A
  correction is a new row; the old one stays readable.
- **Your process, in your words.** You write your SOP (standard operating
  procedure) once, from a training document or a conversation. The agent
  judges every job against it.
- **It asks, it never picks.** When an email could belong to two jobs, or no
  email states a fact, the agent asks you instead of guessing.
- **When a job goes wrong, it changes course cleanly.** A job can move onto
  a recovery procedure. What was done stays done, and the history stays.
- **It tells you what needs you.** After each update, the agent lists what
  only you can unblock and which follow-ups are due, and offers to draft
  them. It never sends anything itself.

## How it works

```
 your email ──▶ your agent ──▶ state machine MCP ──▶ Postgres ledger
 (or calls,      reads each      records evidence,     append-only;
  forms)         update, judges  checks every write    refuses bad writes
                 milestones
                     │
                     ▼
             "here is what needs you"
```

Your own tool reads the mail and hands each update that matters to your
agent; this project reads no email and sends nothing. The agent records the
update unchanged, finds the quote, booking or job it concerns, judges the
milestones it moves against your SOP, and leaves a memo. The server is a
stdio MCP server in Python. The rules live in Postgres itself, so any
client that connects gets the same guarantees.

## Where it runs

| Setup | Notes |
| --- | --- |
| Your own machine | Postgres, the server and the file folders together. |
| A server you control | Postgres on a VPS, reached over a private network such as a tailnet. |
| Hosted Postgres | Supabase, Neon, Amazon RDS and similar, if they allow roles, functions and triggers. |
| Another database | Not supported as is: the rules are Postgres functions and triggers. The schema and migrations are the specification for a port. |

## What it is not

No user interface, no pricing or invoicing, no email client, and no status
it works out on its own. It is a ledger your agent writes to and reads
from, and nothing more.

## License

[Apache 2.0](LICENSE).

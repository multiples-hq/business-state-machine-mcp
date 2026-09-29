<p align="center">
  <a href="https://multiples.company"><img src="assets/banner.jpg" alt="Multiples" width="100%"></a>
</p>

<h1 align="center">Business state machine MCP</h1>

<p align="center">
  <b>A Postgres ledger and MCP server that keeps the state of a business:<br>
  every quote, booking and job, what has happened, what is next,<br>
  and the evidence behind each step.</b>
</p>

<p align="center">
  <a href="#quickstart">Quickstart</a> ·
  <a href="#what-is-this">What is this?</a> ·
  <a href="#how-it-works">How it works</a> ·
  <a href="#the-skills">Skills</a> ·
  <a href="#our-recommendations">Recommendations</a> ·
  <a href="mcp/README.md">Reference</a>
</p>

<p align="center">
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-Apache--2.0-blue" alt="License: Apache 2.0"></a>
  <img src="https://img.shields.io/badge/MCP-stdio-black" alt="MCP over stdio">
  <img src="https://img.shields.io/badge/Postgres-16-336791" alt="Postgres 16">
  <img src="https://img.shields.io/badge/Python-3.10%2B-3776AB" alt="Python 3.10+">
</p>

## Quickstart

### With your AI agent (recommended)

Paste this into your agent:

```
Set up the business state machine ledger from
github.com/multiples-hq/business-state-machine-mcp for my business.

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

At Multiples, we buy durable service businesses and make them AI-native.

We kept running into the same problem at every company where we deployed
AI. We needed a simple shared ledger, across every operator's harness, to
track the state of the repetitive tasks they work on across our funnels.
That gave us the idea for the business state machine MCP. It is a simple
ledger: it tracks the evidence, the decision and the reasoning behind
every decision the AI agent makes against a milestone.

A milestone is an item on a checklist that tracks the progress of a
business task. When all the milestones are checked off, the task is done.

## How it works

Think of a bank ledger, kept for your work instead of your money. Nothing
is edited or deleted. Every change is a new line that says who made it,
why, and which email proves it.

```
 quote ──┬── booking ──┬── job        the offer, the customer's yes,
         │             └── job        and the work itself
         └── booking ───── job

 each one has milestones: the checklist from your SOP

   email ◀── cites ── judgment ── marks ──▶ milestone
```

- **Quotes, bookings and jobs.** A quote is the offer. A booking is the
  customer's yes. A job is the work: a site visit, a shipment, a
  maintenance appointment. A quote can lead to several bookings, and a
  booking to several jobs.
- **Milestones.** The steps you track, such as "Deposit received". Your
  SOP (standard operating procedure) lists them once, and each new quote,
  booking and job gets its own set.
- **Evidence.** Emails, notes and files, stored word for word. Attachments
  go in a plain folder on disk, each named by its SHA-256 hash. No S3 or R2.
- **Judgments.** When an email shows a milestone moved, the agent marks it
  done, pending, blocked or failed, and cites the email. The ledger refuses
  a judgment without evidence, and one without a memo saying why.
- **Nothing is overwritten.** Postgres itself refuses edits and deletes.
  To correct a status, the agent records a newer one; the old one stays.
- **SOP versions.** To change your process, publish a new version.
  Published versions never change, and work keeps the version it started
  on. A job that goes wrong can move to a recovery procedure.

The agent does the reading and deciding. The ledger only records, and
checks what it records.

## The MCP server

A small Python program that your agent app starts on your computer. It
gives the agent 40 tools to create work, record evidence, mark milestones
and read back where everything stands. It never reads your mail and never
sends anything.

Setup, every tool and every setting are in [mcp/README.md](mcp/README.md).

## The skills

Five skills teach your agent the work. Each is a folder with a `SKILL.md`
file, so any agent app that reads skills can use them. See
[skills/README.md](skills/README.md) to install them.

| Skill | What it does |
| --- | --- |
| `get-started` | Asks where to run the ledger, installs it and connects your agent app. |
| `manage-sop` | Turns your training document, or a conversation, into an SOP. |
| `update-the-state-machine` | For each email: records it, finds the work and updates its milestones. |
| `call-to-action` | Tells you what is waiting on you and offers to draft follow-ups. |
| `break-glass` | Moves a job that went off track onto a recovery procedure, with your approval. |

## Our recommendations

- **Track every piece of work as quote, then booking, then job.** Many
  businesses track only the job: the shipment, the install. But quotes
  show which offers are waiting on the customer, and bookings hold what
  must be agreed first: the signature, the deposit, the date. Skip them and
  the work you are still winning is invisible. An SOP can still go straight
  to the job.
- **Write your SOP before the agent marks progress.** The skills will not
  judge work that has no SOP. `manage-sop` turns your checklist into one,
  and [examples/](examples/README.md) has three for different trades.
- **Let your own tool read the mail.** A mail MCP server for Gmail or
  Outlook, or a skill of your own, picks the emails that matter. Pasting an
  email into the chat works too.
- **Answer the agent's questions in the chat.** Your answer is recorded as
  evidence, just like an email.
- **Host it where it suits you.** We run Postgres on a private VPS and
  reach it over Tailscale. Working alone, your own computer is fine, with
  Postgres installed or in Docker. Supabase, Neon and Amazon RDS work if
  they allow what the ledger needs; see the
  [hosting guide](skills/get-started/hosting.md). Snowflake and other
  databases are not supported, because the rules are Postgres functions
  and triggers.

## What it is not

No user interface, no pricing or invoicing, no email client and no
scheduler. The agent decides every status; the ledger never works one out.

Limits today:

- One tool call at a time.
- `list_work` returns at most 1,000 items, with no paging.
- Files up to 8 MiB.
- No native Windows.
- No user accounts. Any login that can reach the database can read and
  write the whole ledger, so give it a database of its own.

## License

[Apache 2.0](LICENSE).

---
name: get-started
description: Set up the state machine ledger for a business - where Postgres runs, the MCP server, the source that hands over updates such as email, and a first SOP. Use when someone wants to start tracking quotes, bookings and jobs with this ledger, or asks how to install, host or connect it.
---

Goal: a ledger the agent can call, a source that hands it updates, and an
SOP to judge work against. Walk the person through the checklist in order.
Where an answer is theirs, ask; do not decide for them.

The ledger is a Postgres database that only gains rows, with an MCP server
in front of it. It records quotes, bookings and jobs, the evidence that
arrived about them, and judgments of each milestone that cite that evidence.
It reads no email and sends nothing. A chain is one quote with its
bookings and jobs, or a job on its own; each chain follows one SOP, the
business's written process. The full reference is `mcp/README.md`
in the repository; this skill does not repeat it.

## The checklist

1. **Fit.** Ask what the business does and what it wants to track. The
   ledger fits a business that is asked for prices (quotes), has some of
   them accepted (bookings) and then carries out the work (jobs), and wants
   to know where each one stands with proof. A business that never quotes
   can use jobs on their own. The ledger also records what is owed and
   paid on each one, both ways, and reads what is still open. It is not
   an accounting system: it files no tax and converts no currency; say so
   if that is what they want.
2. **Where it runs.** Ask which of these they want, with the trade-offs.
   Details for each are in [hosting.md](hosting.md).
   - This machine, with Postgres installed or in Docker. Quickest to try
     and good for one person; the ledger lives and dies with that machine,
     so it needs backups.
   - A server they control, such as a VPS, reached over a private network
     such as a tailnet. This is how the project's authors run it: several
     machines can share one ledger, and nothing is on the public internet.
     It takes a server and some network setup.
   - Hosted Postgres, such as Supabase, Neon or Amazon RDS. No server to
     run, but the provider must allow what the ledger needs, and the data
     sits with them.
   In every case files are kept in a plain folder on the machine that runs
   the MCP server, each named by the SHA-256 hash of its contents. S3, R2
   and similar are not needed.
   - Anything that is not Postgres, such as Snowflake, MotherDuck or
     BigQuery, is not supported. The ledger's rules are Postgres functions
     and triggers that refuse bad writes, and another engine would drop
     them. Rebuilding it there is a separate project with the schema and
     migrations as its specification. Say so and stop here.
3. **Prerequisites.** Git, Python 3.10 or newer, Postgres 16 where the
   ledger lives, the `psql` client where setup runs, and a harness (the
   program that runs the agent) that can start a stdio MCP server. Check
   what is installed. Install nothing without the person's yes.
4. **Install.** Clone the repository into a folder the person keeps; not a
   plugin cache, which may be replaced. Then follow `mcp/README.md` in
   order: "Requirements", "Set up the database", "Run the server",
   "Connect a harness". Keep the owner's password out of the harness
   configuration. The server connects as the runtime login only.
5. **Check it works.** Restart the harness and list the ledger's tools:
   expect 45, or 50 with drafts turned on. Call `list_work`; a new ledger
   answers with an empty list.
6. **The operator and the actor.** Ask the business's name and record it
   once with `create_party`, `kind` organization and `is_operator` true.
   Agree on the actor label every write will carry, such as `agent:ops`.
   Write it in the harness instructions: the standing instructions the
   harness gives the agent on every run, such as a `CLAUDE.md` or
   `AGENTS.md` file or a system prompt. Later steps add to them.
   - Ask once which currency the business keeps its books in, and write
     it in the harness instructions. An amount in another currency is
     recorded as billed, with its value in the books' currency as
     `home_amount` once the bank or a stated rate says what it is.
   - Departments, if they have any: each is an organization created with
     `create_party` and given a role such as department on the operator
     with `record_role`. An employee is a person with a role in each
     department they work in. The business, never a department, is the
     party on a charge. The ledger records who belongs where; it has no
     logins and controls no access.
7. **The source.** Ask how updates reach them. This project does not read
   email. A source is the person's own tool that reads their mail (or
   calls, or forms), decides which updates matter, and hands each one to
   the agent. If they use a mail tool that already sorts mail, that tool is
   the source. If the agent reads a raw inbox, the person needs a skill or
   step that picks out the messages about their work first. If they have
   no source yet, say plainly that they should set one up. Until then
   they can paste an update into the conversation. Agree what each update
   must carry: [source-contract.md](source-contract.md).
8. **The schedule.** Updates are handled by the `update-the-state-machine`
   skill, then `call-to-action`. To run that every few minutes, use the
   harness's own scheduler. This project has none.
9. **The SOP.** Explain the two ideas first. An SOP is their written
   process, split into stages: quote, booking and job. A milestone is one
   outcome in it that an email can show, such as "Deposit received"; the
   agent marks each milestone done, pending, blocked or failed, citing the
   email. Recommend tracking every piece of work as quote, then booking,
   then job, and say why (`manage-sop` step 2). Then ask whether they have
   a written process: a training document, a checklist, an onboarding
   guide. Either way, continue with the `manage-sop` skill. Nothing is
   judged until a chain has an SOP.
10. **A first run on their own work.** No sample data: once the SOP is
   published, ask the person to pick one real quote, booking or job. Ask
   their source to find every past email about it, oldest first, and hand
   them over as a backlog to `update-the-state-machine`. Then run
   `call-to-action` and show them what is waiting on them for that one
   piece of work.

## Drafts before recording

By default the agent records what the evidence shows and asks the person
about what it does not. If the person wants to approve each decision
before anything is recorded, set `LEDGER_PROPOSALS` as `mcp/README.md`
describes. The agent then writes drafts and records only after their word.

Done when: the tools list, `list_work` answers, the operator party exists,
the actor label is written down, the source and its contract are agreed,
an SOP is published, and one real piece of work has been recorded from its
past emails.

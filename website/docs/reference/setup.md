---
title: Setup
description: Install the database and the server, and connect your agent app.
---

# Setup

The `mcp/` folder holds a small server that speaks MCP (Model Context Protocol, the
standard way an AI agent calls tools) over stdio. It sits on a Postgres
database that only ever gains rows. Your agent calls the tools to record what
happened on a quote, a booking or a job, and reads the record back later.

The ledger records; the agent decides. The server calls no outside system,
derives no status and picks nothing for you.

The database schema is named `spine`, the project's working name for the
ledger. The server announces itself to a harness as `state-machine-ledger`.

Every command below assumes the working directory is the repository root.

Words used here:

- **Work** is a quote, a booking or a job. A booking belongs to a quote. A job
  can be linked to one booking. A quote with its bookings and their jobs is one
  chain. A job with no booking is a chain of one. In the case brief the key
  `chain` names the root: the quote, or the job that stands alone.
- **Evidence** is an unchanged source: the text of a message, or a file.
- A **milestone** is a checkpoint on one work item. A **phase** is a named
  group of milestones, used for display.
- A **judgment** is one of four words about a milestone: `done`, `pending`,
  `blocked` or `failed`, with an explanation and the evidence it rests on. A
  milestone with no judgment yet reads as `unassessed`; that is a gap, not a
  fifth judgment word.
- A **memo** is the note a reviewer leaves after looking at a work item.
- A **charge** is a milestone with at least one charge line: one priced
  thing, between one party that owes and one that is owed. A **charge
  line** states its amount, expected (agreed) or invoiced (billed). An
  **invoice** is one version of a bill. A **payment** is money that moved;
  an **allocation** puts it on a charge or a bill.
- An **SOP** (standard operating procedure) is a published list of phases and
  milestones for the quote, booking and job stages.
- A **party** is a person, an agent or an organization. A **role** says what a
  party is on a work item or to another party.
- An **actor** is a text label naming who made a write.
- **The operator** is the organization that runs this ledger, the one party
  created with `is_operator`. **A person** is whoever answers the agent's
  questions and drafts. The two words are never used for each other.

## Requirements

- Python 3.10 or newer.
- Postgres 16, and its `psql` command-line client on the machine you set up
  from.
- The two pinned packages in `mcp/requirements.txt`.

```sh
python3 -m venv .venv
.venv/bin/pip install -r mcp/requirements.txt
```

## Set up the database

Setup uses three Postgres roles:

- `ledger_owner`, a login that owns the database and the schema. It is used
  only for setup and migrations.
- `your_runtime_login`, the login the server connects as. It owns nothing.
- `ledger_client`, a role that cannot log in. The server switches every
  connection to it, so the runtime login must be a member of it.

You may choose other names for the first two. The name `ledger_client` is
fixed.

**Step 1: roles and the database.** Run this once as a Postgres administrator
(a superuser such as `postgres`), connected to any existing database:

```sh
psql "postgresql://postgres@localhost/postgres" -v ON_ERROR_STOP=1
```

```sql
CREATE ROLE ledger_owner LOGIN PASSWORD 'choose-a-password';
CREATE DATABASE your_database OWNER ledger_owner;
CREATE ROLE your_runtime_login LOGIN PASSWORD 'choose-another-password';
CREATE ROLE ledger_client NOLOGIN;
GRANT ledger_client TO your_runtime_login;
```

The last two statements may also be run after step 2. The schema and the
migrations never name `ledger_client`; only the running server needs it.

**Step 2: schema and migrations.** Run these as the owner, on the new empty
database. `$DATABASE_URL` is the owner's connection string:

```sh
export DATABASE_URL=\
"postgresql://ledger_owner:choose-a-password@localhost/your_database"
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f postgres/schema.sql
.venv/bin/python postgres/migrate.py "$DATABASE_URL"
```

`postgres/migrate.py` applies the files in `postgres/migrations/`, `001` to
`017`, in filename order and records each one in `spine.schema_migrations`.
It prints the name of each file it applies. Running it again applies only
files it has not seen, so run it again after every update of this
repository. Never rename or edit an applied file. Two files share the prefix
`002`; that is intended, and filename order still decides which runs first.

If the server stops at startup with `permission denied to set role "ledger_client"`, the `GRANT` in step 1 was not run for the login named in
`LEDGER_DSN`.

The runtime login should not own the schema or be a superuser. Tables allow
reads only; every write goes through a database function. This is not
per-user permission: any role that can connect gets the same reads and the
same write functions. Keep the owner's credentials out of the agent's
configuration.

## Run the server

Start `mcp/mcp_server.py` with these environment variables:

- `LEDGER_DSN` (required): the Postgres connection string of the runtime login.
- `LEDGER_FILES` (required): the directory where file bytes are stored. Each
  file is named by the SHA-256 hash of its own bytes.
- `LEDGER_DROP` (required): a directory another program may put files into,
  each named by the SHA-256 of its bytes. Only `record_file_by_hash` reads it.
- `LEDGER_LOG` (optional): a file that gains one JSON line per tool call (time,
  tool, shortened arguments, `ok` or `error`, a short note) and one line when
  a session connects or disconnects. Nothing reads it back. A logging failure
  never fails a call.
- `LEDGER_PROPOSALS` (optional): a directory for draft files. Setting it adds
  the five draft tools described below.

Each setting is also read under its older name, with `SPINE_` in place of
`LEDGER_`; when both are set, `LEDGER_` wins.

None of the directories has to exist when the server starts. The server
creates `LEDGER_FILES` on the first `put_file` and `LEDGER_PROPOSALS` on the
first draft. It never creates `LEDGER_DROP`: the program that leaves files
there creates it.

The server stops at startup if any of the first three is missing. One server
process holds one database connection and serves one tool call at a time.

## Connect a harness

A harness is the program that runs your agent. Register the server as a stdio
MCP server. Most harnesses take a block like this; use absolute paths:

```json
{
  "mcpServers": {
    "ledger": {
      "command": "/path/to/repo/.venv/bin/python",
      "args": ["/path/to/repo/mcp/mcp_server.py"],
      "env": {
        "LEDGER_DSN": "postgresql://your_runtime_login@localhost/your_database",
        "LEDGER_FILES": "/path/to/files",
        "LEDGER_DROP": "/path/to/drop"
      }
    }
  }
}
```

To check that it worked, connect and list the tools. Expect 45, or 50 when
`LEDGER_PROPOSALS` is set.

A program that embeds the server can add its own tools by calling `main` or
`build_server` with `extra_tool_groups`. An added tool cannot replace a
built-in one.

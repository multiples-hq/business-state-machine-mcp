# Where the ledger runs

Three parts must be placed: the Postgres database, the MCP server, and the
two file folders (`LEDGER_FILES` for stored files, `LEDGER_DROP` for files
another program leaves by hash). The MCP server is a stdio process: the
harness starts it on the machine where the agent runs. The folders must be
on that same machine, or mounted there. Only the database can be elsewhere.

The ledger is tested on Postgres 16. Other versions are not tested.

## This machine

Postgres, the server and the folders all on one computer. Postgres can be
installed directly or run in Docker, for example the official `postgres:16`
image with its port published on `localhost` only. Follow `mcp/README.md`
as written, with the connection strings pointing at that Postgres. Back up the database with `pg_dump` and the
files folder with any file backup; the two belong together.

## A server the person controls, over a private network

This is how the project's authors run it: Postgres on a VPS, reached over
Tailscale. Postgres runs on a server (a VPS or a machine in the office). The agent
and the MCP server run on another machine and reach Postgres over a private
network such as a tailnet (a private network between your own machines,
made with a tool such as Tailscale).

- Make Postgres listen on the private network address only, never on a
  public one. Allow only that network in `pg_hba.conf`, with password
  authentication (`scram-sha-256`).
- Run the setup in `mcp/README.md` against the server's private address.
- `LEDGER_DSN` names that private address.
- The file folders stay on the machine that runs the MCP server, unless
  the person mounts a shared folder there. If several machines will run
  the server, they need the same folders; say so before they start.

## Hosted Postgres

Supabase, Neon, Amazon RDS, Google Cloud SQL and similar are Postgres, so
the schema runs unchanged if the provider allows four things: creating
roles, granting one role to another, creating PL/pgSQL functions marked
`SECURITY DEFINER`, and creating triggers. Setup refuses loudly when one of
them is missing; nothing half-works. Use the provider's connection string
for the owner during setup and for the runtime login in `LEDGER_DSN`.

Stored files are not built for object storage. `LEDGER_FILES` is a folder.
To keep files in S3, R2 or similar, the person can mount a bucket as a
folder on the machine that runs the server, or keep the folder on local
disk and back it up to the bucket. Say that either is their choice and
their setup; the ledger only needs a folder that holds each file under its
hash.

## Not Postgres

Snowflake, MotherDuck, BigQuery and other engines are not supported. The
ledger's rules live in the database: dozens of functions written in
Postgres's own language (PL/pgSQL), and triggers, refuse updates, deletes,
judgments without evidence and the rest. Copying the tables to another
engine would copy none of that. A person who wants it anyway is starting a
new project; `postgres/schema.sql`,
`postgres/migrations/` and the "Rules the ledger enforces" section of
`mcp/README.md` are its specification. This skill stops there.

---
title: Hosting
description: Where the ledger can run, and the trade-offs.
---

# Hosting

Three parts need a home: the Postgres database, the MCP server, and two
file folders. Your agent app starts the MCP server on the machine where
the agent runs, and the folders must be on that machine too. Only the
database can live elsewhere.

| Option | Good for | Trade-off |
| --- | --- | --- |
| Your own computer | Trying it, or one person | The ledger lives and dies with that machine, so back it up. |
| A VPS over Tailscale | A team, several machines, one ledger | Needs a server and a little network setup. |
| Hosted Postgres | No server to run | The provider must allow what the ledger needs, and holds your data. |

## Your own computer

Install Postgres, or run it in Docker, for example the official
`postgres:16` image with its port published on `localhost` only. Then
follow [Setup](reference/setup.md). Back up the database with `pg_dump`
and the files folder with any file backup; the two belong together.

## A VPS over Tailscale

This is how we run it at Multiples. Postgres runs on a server, and the
agent's machine reaches it over a private network made with Tailscale.

- Make Postgres listen on the private network address only, never a
  public one. Allow only that network in `pg_hba.conf`, with password
  authentication (`scram-sha-256`).
- Run [Setup](reference/setup.md) against the server's private address,
  and put that address in `LEDGER_DSN`.
- The file folders stay on the machine that runs the MCP server, unless
  you mount a shared folder there. Several machines running the server
  need the same folders.

## Hosted Postgres

Supabase, Neon, Amazon RDS, Google Cloud SQL and similar run the schema
unchanged if the provider lets you:

- create roles,
- grant one role to another,
- create PL/pgSQL functions marked `SECURITY DEFINER`,
- create triggers.

Setup fails loudly when one is missing; nothing half-works.

## Files

Attachments are stored in a plain folder, each named by the SHA-256 hash of
its contents. No S3 or R2 is needed. To keep files in a bucket anyway,
mount the bucket as a folder on the server's machine, or keep the folder
on local disk and back it up to the bucket.

## Not Postgres

Snowflake, MotherDuck, BigQuery and other databases are not supported. The
ledger's rules are Postgres functions and triggers that refuse bad writes;
copying the tables elsewhere copies none of them.

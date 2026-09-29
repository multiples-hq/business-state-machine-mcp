---
title: Quickstart
description: Set up the ledger with your AI agent, or by hand.
---

# Quickstart

## With your AI agent (recommended)

Paste this into your agent:

```
Set up the business state machine ledger from
github.com/multiples-hq/business-state-machine-mcp for my business.

Read skills/get-started/SKILL.md in that repository and follow it.

Ask me whatever it needs, and install nothing without asking me first.
```

The agent asks what your business does, where the ledger should run, and
what you already have installed. It installs nothing without your yes.

## What you need

- Linux, macOS or WSL. Native Windows is not supported.
- Postgres 16, with the `psql` client and an admin login.
- Python 3.10 or newer.
- An agent app that runs local MCP servers, such as Claude Code, Codex or
  Cursor.

This project has no inbox connector and no scheduler. Your email reaches
the agent through a mail tool of your own, or you paste it in. Anything
scheduled runs on your agent app's own scheduler.

## By hand

Follow [Setup](reference/setup.md): create three Postgres roles, run the
schema and migrations, then add the server to your agent app.

The server is connected when your agent app lists 40 ledger tools (45 with
the optional draft tools) and, on a new database, `list_work` returns
`{"work": []}`.

## Then

Spend your [first day](first-day.md) on one real piece of work.

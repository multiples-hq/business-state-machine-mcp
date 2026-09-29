---
slug: /
title: Overview
sidebar_label: Overview
description: A Postgres ledger and MCP server that keeps the state of a business.
---

<img className="hero-banner" src={require('@site/static/img/banner.jpg').default} alt="Multiples" />

# Business state machine MCP

A Postgres ledger and MCP server that keeps the state of a business: every
quote, booking and job, what has happened, what is next, and the evidence
behind each step.

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

## What it does

Think of a bank ledger, kept for your work instead of your money. Nothing
is edited or deleted. Every change is a new line that says who made it,
why, and which email proves it.

Your mail tool hands an email to your agent. The agent records it, finds
the quote, booking or job it is about, marks the milestones it moves, and
tells you what is waiting on you. The ledger does the recording and
refuses anything that breaks its rules. The agent does the reading and
deciding.

## Where to go next

- **[Quickstart](quickstart.md):** one prompt to paste into your agent.
- **[Hosting](hosting.md):** your own computer, a VPS over Tailscale, or
  hosted Postgres.
- **[How it works](concepts/work.md):** quotes, bookings, jobs, milestones
  and evidence, in five short pages.
- **[Reference](reference/tools.md):** every tool, setting and rule.

## What it is not

No user interface, no pricing or invoicing, no email client and no
scheduler. The agent decides every status; the ledger never works one out.
See [Limits](reference/limits.md).

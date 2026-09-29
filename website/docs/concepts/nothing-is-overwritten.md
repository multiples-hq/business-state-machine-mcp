---
title: Nothing is overwritten
description: Why the ledger only ever adds rows.
---

# Nothing is overwritten

Postgres itself refuses to edit or delete anything in the ledger. Every
ledger table has a trigger that refuses `UPDATE`, `DELETE` and `TRUNCATE`.

So a mistake is fixed by adding, never by erasing:

- A wrong status: record a newer judgment. The old one stays in the
  history.
- A wrong role: end it, then record the right one.
- A wrong document: submit a new version.

An outside reference number cannot be withdrawn or corrected.

## Who wrote it

Every write carries an **actor** label, which must not be empty,, such as `agent:intake`, that says who
wrote it. It is a label, not a login: the ledger does not check it.

## Retries are safe

The agent picks the ID of each record it creates. Sending the same call
again, with the same ID and the same contents, writes nothing new. The same
ID with different contents is refused.

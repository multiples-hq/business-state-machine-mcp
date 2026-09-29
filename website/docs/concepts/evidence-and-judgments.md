---
title: Evidence and judgments
description: How a milestone moves, and why every move cites an email.
---

# Evidence and judgments

```
   email ◀── cites ── judgment ── marks ──▶ milestone
```

**Evidence** is an email, a note or a file, stored word for word, with
where it came from and when. Your own answers to the agent's questions are
evidence too. Files up to 8 MiB are kept in a plain folder, each named by
its SHA-256 hash.

A **judgment** marks a milestone with one of four words:

| Word | Means |
| --- | --- |
| `done` | It happened, and the evidence shows it. |
| `pending` | Not yet, and nothing is in the way. |
| `blocked` | Someone else must act first. |
| `failed` | It was tried and did not happen. |

A milestone never judged reads as `unassessed`. A milestone's status is its
latest judgment; nothing works a status out on its own.

## The rules

- Every judgment cites at least one piece of evidence. The ledger refuses
  one that cites none.
- Every judgment comes with a **memo**: what changed, what was decided,
  and, when known, what the work is waiting for and when to look again.
  The ledger refuses a judgment without one.
- Evidence linked to a piece of work can support statuses only on that
  work. Evidence linked to nothing can support any status.

## Looking before recording

The ledger does not stop the same email being recorded twice. So the agent
looks it up first, by its Message-ID, and cites the existing record when
there is one.

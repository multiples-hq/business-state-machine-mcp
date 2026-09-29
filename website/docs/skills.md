---
title: Skills
description: Five skills that teach your agent to run the ledger.
---

# Skills

The ledger records; the skills teach your agent how to use it for a
business. There are five:

| Skill | When |
| --- | --- |
| `get-started` | Once: where the ledger runs, install, connect your agent app and a source of updates. |
| `manage-sop` | Once, and when your process changes: write, revise or retire the SOP. |
| `update-the-state-machine` | Every update, one at a time or a backlog: record, place, judge, memo. |
| `call-to-action` | After each update, or when you ask: what needs you, and how to follow up. |
| `break-glass` | Rarely: move a running job onto a recovery procedure or a newer SOP. |

Reading email is not one of them. You bring your own source; see
[Connect your mail](guides/connect-your-mail.md).

## Install

In Claude Code:

```
/plugin marketplace add multiples-hq/business-state-machine-mcp
/plugin install business-state-machine-mcp@business-state-machine-mcp
```

The skills then load as `/business-state-machine-mcp:get-started` and so on.
Other agent apps that read `SKILL.md` folders can copy the five folders into
their own skills directory.

The skills live in
[`skills/`](https://github.com/multiples-hq/business-state-machine-mcp/tree/main/skills)
in the repository.

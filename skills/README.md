# Skills

Five skills teach an agent to run the ledger for a business. They name the
ledger's tools without the prefix a harness (the program that runs the
agent, such as Claude Code) adds, and restate no schemas:
the tool descriptions and `mcp/README.md` carry those.

| Skill | When |
| --- | --- |
| `get-started` | Once: where the ledger runs, install, connect the harness and a source of updates. |
| `manage-sop` | Once, and when the process changes: write, revise or retire the SOP. |
| `update-the-state-machine` | Every update, one at a time or a backlog: record, place, judge, memo. |
| `call-to-action` | After each update, or when asked: what needs the person, and how to follow up. |
| `break-glass` | Rarely: move a running job onto a recovery procedure or a newer SOP. |

Reading email is not one of them. The person brings their own source,
something that reads their mail and hands over the updates that matter;
`get-started` says what each update must carry.

## Install

In Claude Code:

```
/plugin marketplace add multiples-hq/business-state-machine-mcp
/plugin install business-state-machine-mcp@business-state-machine-mcp
```

The skills then load as `/business-state-machine-mcp:get-started` and so on. Other
harnesses that read `SKILL.md` folders can copy the five folders into
their own skills directory.

## A prompt to start with

Paste this into your agent:

```
Set up the business state machine ledger from
github.com/multiples-hq/business-state-machine-mcp for my business.
Read skills/get-started/SKILL.md in that repository and follow it. Ask me
whatever it needs, and install nothing without asking me first.
```

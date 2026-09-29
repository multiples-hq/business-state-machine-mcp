---
title: Answer the agent
description: What the agent asks you, and what happens to your answers.
---

# Answer the agent

After each update, or when you ask "What is waiting on me?", the agent runs
the `call-to-action` skill. It tells you two things, most urgent first:

1. **Unblock me.** Questions only you can answer, one per item, with the
   choices when there are choices. For example, which SOP a new quote
   should follow, or which of two jobs an email is about.
2. **Follow-up needed.** Who must act, and on what. For each, you choose:
   - the agent drafts a reply for you to send,
   - you handle it yourself, or
   - wait until a date you name.

If nothing needs you, it says so in one line.

## Your answers are evidence

When you answer in the chat, the agent records the question and your answer
word for word as evidence before acting on it, and cites it like any email.

## The agent never sends

The agent drafts; you or your mail tool send. A draft uses only facts the
ledger shows, and never promises a date the evidence does not support.
After it drafts, it leaves a memo saying the follow-up is in hand and when
to raise it again, so it does not ask twice.

## Approving before anything is recorded

By default the agent records what the evidence shows and asks you only
about what it does not. If you want to approve each decision first, turn on
the optional draft tools (`LEDGER_PROPOSALS`, see
[Setup](../reference/setup.md)). The agent then writes each decision as a
draft and records it only after your word.

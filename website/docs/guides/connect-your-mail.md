---
title: Connect your mail
description: How your emails reach the agent.
---

# Connect your mail

This project does not read email. You bring a **source**: your own tool
that reads your mail (or calls, or forms), decides which messages matter,
and hands them to the agent one at a time.

- If your mail tool already sorts your mail, that tool is the source.
- If the agent reads a raw inbox, add a step that picks out the messages
  about your work first.
- If you have no source yet, paste emails into the chat until you set one
  up.

## What each update must carry

1. **A locator** that never changes. For an email, its `Message-ID` header,
   exactly as the header gives it, angle brackets included. The agent uses
   it to avoid recording the same email twice.
2. **The time** it was sent or received, with a UTC offset.
3. **The original content, unchanged.** For email: the From, To, Cc, Date
   and Subject headers and the body, as sent. A summary is not the
   original.
4. **Each attachment**, with its media type. Either the bytes (at most
   8 MiB each), or the file left in the drop folder named by the SHA-256
   hash of its bytes, for large files or when the bytes should not pass
   through the model.
5. **Optionally, a hint:** which customer or job it seems to be about. The
   agent checks the hint against the ledger and does not record it.

## Running it on a schedule

The `update-the-state-machine` skill handles updates, then `call-to-action`
tells you what needs you. To run that every few minutes, use your agent
app's own scheduler. This project has none.

## Catching up on old mail

The same skill takes a backlog. Updates are handled oldest first, so later
emails revise earlier judgments in the order things happened.

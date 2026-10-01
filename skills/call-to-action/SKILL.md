---
name: call-to-action
description: Tell the person what the ledger says needs them - questions only they can answer, and follow-ups that are due - and offer to draft each follow-up. Use right after updating the state machine, or whenever the person asks what is waiting on them.
---

Goal: the person knows, in a minute, what only they can unblock and which
follow-ups are due, and each one has a next step they chose.

## Which chains

- **After an update**: the chains that update touched.
- **When the person asks**: every chain. `list_work` lists all work newest
  first; read `read_case_brief` for each chain once (any ID in a chain
  gives the whole chain). Leave out a chain when every milestone of every
  work item is done and no latest memo has a `waiting_for`.

## What to look for in each case brief

- A judgment `blocked` whose explanation says the person must act, or that
  needs a fact only the person has.
- A question the agent asked earlier that has no recorded answer: a
  `waiting_for` that starts with "Question for the person:". The brief
  shows each work item's latest memo and its `waiting_for`; read
  `read_work_memos` for a memo's `details` and for earlier memos.
- A chain that follows no SOP (listed under `not_recorded`): the person
  must choose a version before anything is judged.
- A latest memo whose `next_review_at` has passed, or a milestone
  `blocked` on someone outside the business: a follow-up is due.
- If draft tools are on: open drafts from `list_proposals`.

A job moved to another SOP keeps the milestones its old procedure had
under `history_milestones`, with their last status. They are history:
leave them out.

## Money

Read `read_money_open` once: for the whole business when the person asks,
or with `party_id` for each customer or vendor the update touched. Take
the amounts from it; never add them up yourself.

- Owed to the business and late: who, how much, how many days past due.
  Ask: chase now or wait?
- Owed by the business: who and by when.
- A bill charge that is unassessed, or whose amount changed since it was
  judged: accept or dispute?
- A payment with nothing allocated: what was it for?
- Money paid before a bill, and a bill linked to a job with no lines yet:
  say so.

For one chain, `read_work_money` shows the agreed prices beside the bills:
a vendor with an agreed price and no bill on the chain has not billed yet.

## What to tell the person

Group what you found in two parts, most urgent first, one line of context
each: the work's title, what is stuck, and the evidence behind it.

1. **Unblock me.** Each question only the person can answer, asked
   exactly, with the choices when there are choices. One question per item.
2. **Follow-up needed.** Who must act and on what. For each, ask how the
   person wants it handled:
   - "I draft a reply for you to send",
   - "you handle it yourself", or
   - "wait until a date you name".

If nothing needs them, say so in one line.

## When the person answers

- **An answer to a question**: hand it to `update-the-state-machine`, which
  records it as evidence and acts on it.
- **Draft a reply**: write it from the ledger only: facts from the case
  brief and the evidence it cites, nothing the ledger does not show. Give
  it to the person, or to their mail tool as a draft if their harness has
  one. Then leave a memo on the work with `leave_work_memo`: follow-up
  drafted, `waiting_for` the reply, and `next_review_at` if they gave a
  date.
- **They handle it, or wait**: leave the same memo, so the next run knows
  the follow-up is in hand and when to raise it again.

The reply, once someone sends it, comes back through the source as a new
update. Nothing more to record until then.

## Never

- Never send anything. You draft; the person or their mail tool sends.
- Never put a fact in a draft that the ledger does not show, and never
  promise a date the evidence does not support.
- Never ask the same question twice: check memos and drafts first.

Done when: the person has seen every open item for the chains in scope,
and each item they answered has its memo or its recorded answer.

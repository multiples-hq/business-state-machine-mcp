# How to judge

## The four words

- **done**: the evidence shows the milestone's criterion is met.
- **pending**: not met yet, and nothing is in the way; it is simply not
  time, or the business itself has the next move.
- **blocked**: someone else must act before it can move. Waiting on a
  customer's or supplier's reply is blocked, not pending. Say in the
  explanation who must act and on what. When the business itself must act
  first (redo a piece of work, send something), the milestone is pending
  and the memo says what the business owes.
- **failed**: the outcome did not happen and needs a redo or another path.

A plan that was dropped is none of these: the milestone stays pending and
the memo says the plan changed. A milestone with no judgment yet reads as
unassessed; judge only the milestones this evidence moves.

## Rules of evidence

- Every judgment cites the evidence it rests on, recorded or found in this
  run. Evidence linked to other work cannot be cited here; link it first.
- When later evidence settles an earlier milestone ("the goods arrived"
  proves they were sent), judge the earlier milestone too, cite the later
  evidence, and say in the explanation that it is inferred from what came
  after.
- When two sources disagree about a fact, judge blocked, cite both, and put
  the question to the person. Never choose one.
- `occurred_on` is the day it happened. Use precision `exact` only when the
  source states the day; use `by` when the source only proves it had
  happened by then.
- A revision of your own earlier judgment names it in `revises_ids`.

## When the work leaves the SOP

When the work takes a turn the SOP does not name (an extra visit, a
return, a second delivery), create the milestone on that work item with
`create_work_milestone`, under the right phase, and judge it. A title is a
short noun phrase of at most six words; names, numbers and dates go in the
explanation. A turn left only in memo prose is a turn the ledger does not
know about. When the whole job has left its SOP, the `break-glass` skill
moves it onto a recovery procedure, with the person's yes.

## Parties and roles

Record each organization, person or agent the update introduces with
`create_party`, and the email, phone or address it shows with
`record_party_identifier`, citing the update. Check `read_party` or the
case brief first; parties are never merged, so a duplicate stays forever.
Put each party's part in the work as a role in the same `record_review`,
citing the update that shows it, with confidence `mentioned` when the part
is unclear. A standing relationship (a person who works at a company, a
company that supplies another) is a role on the other party, recorded with
`record_role`, not a role on the work.

## Questions for the person

When only the person can settle something (which quote a message means, a
fact no email states, a choice of SOP), put the question in the memo's
`waiting_for`, starting with the words "Question for the person:", and
judge any milestone that waits on it blocked. The `call-to-action` skill
finds questions by those words. Once they answer, record the answer as
evidence and act on it.

## The memo

Every review leaves one memo on the work item: what changed, what was
decided, and in `waiting_for` who or what the work is waiting on. Set
`next_review_at` when a date is known by which something should have
happened. A look that changed nothing is still a memo, with `changed`
false and no judgments.

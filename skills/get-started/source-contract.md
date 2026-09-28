# What an update must carry

A source is whatever reads the person's mail, calls or forms and hands one
update at a time to the agent, having decided it matters. The ledger does
not care which tool it is. It needs these things from each update:

1. **A locator.** An ID that names this update in its own system and never
   changes: an email's `Message-ID` header, exactly as the header gives
   it, angle brackets included; a call's ID in the phone system; a form
   submission's ID. Lookups match exactly, so the same update must always
   arrive with the same locator. The agent records it as
   `source_locator` and looks it up with `find_evidence` so the same update
   is never recorded twice.
2. **The time it happened there**, with a UTC offset: when the email was
   sent or received, when the call ended. It becomes `source_at`.
3. **The original content, unchanged.** For email: the From, To, Cc, Date
   and Subject headers and the body text, as sent. For a call: the
   transcript. A summary is not the original; the ledger keeps what was
   said, and interpretation goes in judgments and memos.
4. **Each attachment**, with its media type, in one of two ways:
   - the bytes, which the agent sends with `put_file` (at most 8 MiB each),
     or
   - the file left in the `LEDGER_DROP` folder named by the SHA-256 hash of
     its bytes, with that hash given to the agent, which records it with
     `record_file_by_hash`. Use this for large files or when bytes should
     not pass through the model.
5. **Optionally, a hint**: why the source thinks it matters, or which
   customer or job it seems to be about. The agent checks the hint against
   the ledger. It is not evidence and is not recorded as such.

## The person's own answers

When the agent asks the person a question and they answer in the
conversation, that answer is an update too. The agent records it as
evidence: the question and the answer word for word as the payload, a
locator such as `chat:` followed by the time, and the time of the answer.
Judgments that rest on the answer cite it like any email.

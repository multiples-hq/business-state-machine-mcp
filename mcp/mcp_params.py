"""Parameter descriptions shared by the tool modules.

Each name is a type plus the one sentence the agent reads for that parameter
in the tool schema. A parameter that means the same thing in several tools is
defined once here, so it reads the same everywhere. The agent pays for every
character of the tool list in every session, so the texts that repeat most
(id, actor) are the shortest sentence that keeps the rule.

A parameter that takes one of a fixed list of words is a Literal type. The
words are the ones the database constraints allow, so the harness refuses a
wrong word before the database does, and the schema lists the choices.
"""

from typing import Annotated, Literal

from pydantic import Field


def said(kind, text):
    """The same type, carrying its description into the tool schema."""
    return Annotated[kind, Field(description=text)]


# The fixed word lists, as the database constraints have them.
WorkKindWords = Literal['quote', 'booking', 'job']
StatusWords = Literal['done', 'pending', 'blocked', 'failed']
ConfidenceWords = Literal['confirmed', 'mentioned', 'former']
SopTagWords = Literal['standard', 'break_glass']
SopStatusWords = Literal['active', 'retired']
PartyKindWords = Literal['person', 'agent', 'organization']
IdentifierKindWords = Literal['email', 'phone', 'address', 'alias']
OutcomeWords = Literal['accepted', 'rejected']

NEW_ID = 'UUID you generate for this row. A retry must send the same id and arguments.'
ACTOR = 'Stable label of who makes this write, such as "agent:intake". Not empty.'
WORK_KIND = 'Kind of the work item that work_id names.'
WORK_ID = 'UUID of the quote, booking or job.'
EVIDENCE_IDS = 'UUIDs of recorded evidence that supports this write; at least one.'
EVIDENCE_ID = 'UUID of recorded evidence that supports this row. Without it the row reads as uncited.'
ISO_TIME = 'ISO 8601 with a UTC offset, such as 2026-03-01T09:30:00+07:00 or ending in Z.'
DATE = 'a calendar date, YYYY-MM-DD.'

# Memo fields, used by record_review's memo and by leave_work_memo. The first
# time field states the format; the others share it.
MEMO_STARTED = 'When you began looking at this work item. ' + ISO_TIME
MEMO_ENDED = 'When you finished, in the same format; not before review_started_at.'
MEMO_SUMMARY = 'What you found in this review, in plain sentences. Must not be empty.'
MEMO_DECISION = ('What you decided to do, or not to do, and why. Must not be empty. '
                 '"No action" is a valid decision.')
MEMO_CHANGED = ('true when this review changed what is known about the work; false for a look '
                'that found nothing new. A review with judgments must send true.')
MEMO_WAITING_FOR = 'Who or what the work is waiting on now, in words. Omit when nothing.'
MEMO_NEXT_REVIEW = ('When to look at this work again, in the same format. The ledger stores it '
                    'and schedules nothing.')
MEMO_DETAILS = 'Free JSON object for anything else the next reader needs. The ledger does not read it.'
MEMO_MILESTONES = 'UUIDs of milestones on this work item that you looked at without judging them.'
MEMO_JUDGMENTS = 'UUIDs of earlier judgments on this work item that you read and relied on.'

# Role fields, used by record_role and by the roles of record_review.
ROLE = ("What the party is here, in any word the operator's business uses, such as customer "
        'or supplier. Must not be empty.')
ON_PARTY = ('For a standing role, UUID of the party the role is held on, such as the '
            'organization a person works at.')
CONFIDENCE = ('confirmed (the evidence says so), mentioned (named, but the part it plays is '
              'unclear) or former (held once, not now; needs ended_on). Default confirmed.')
STARTED_ON = 'The day the role began, when known: ' + DATE
ENDED_ON = 'The day the role ended: ' + DATE[:-1] + ', not before started_on.'

NewId = said(str, NEW_ID)
Actor = said(str, ACTOR)
Title = said(str, 'A short name a person would recognise this work by. Must not be empty.')
WorkKind = said(WorkKindWords, WORK_KIND)
WorkKindWord = WorkKind
WorkId = said(str, WORK_ID)
ReadId = said(str, 'UUID of the row to read.')
AnyWorkId = said(str, WORK_ID)
JobId = said(str, 'UUID of an existing job.')
EvidenceIds = said(list[str], EVIDENCE_IDS)
OptionalEvidenceId = said(str | None, EVIDENCE_ID)
OptionalMemoId = said(str | None, 'UUID of the memo of the review that made this claim. '
                                  'record_review sets it for you; omit it otherwise.')
Confidence = said(ConfidenceWords, CONFIDENCE)
Sha256 = said(str, 'SHA-256 of the file bytes: 64 lowercase hexadecimal characters.')
MediaType = said(str, 'Media type of the file, such as application/pdf. Must not be empty.')
IncludeEvidence = said(bool, 'true returns each cited evidence record in full; false, the '
                             'default, returns ids only.')
PageLimit = said(int, 'Most rows to return: 1 to 200, default 50.')
BeforePosition = said(int | None, 'Paging cursor: the position of the oldest row you already '
                                  'have. Only older rows are returned. Omit for the newest page.')

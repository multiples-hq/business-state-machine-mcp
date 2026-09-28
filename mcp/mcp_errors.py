"""Plain sentences for the refusals an agent meets most often.

Postgres names a broken table rule by its constraint name, which tells an
agent nothing. The small maps here turn the common ones into one sentence
that says what to fix. A refusal stays a refusal: only the wording changes.
Anything not listed keeps the database's own message. The messages the SQL
functions raise themselves are already plain and pass through, except a few
that use an older word for a chain or that say the same thing two ways.
"""

from mcp_support import InvalidTime, InvalidUuid

# Exact constraint names. These are looked up before the endings below.
CONSTRAINT_MESSAGES = {
    'sop_versions_name_version_key':
        'an SOP with this name and version is already published',
    'sop_versions_tag_check': 'tag must be standard or break_glass',
    'sop_versions_check': 'based_on_version_id must name a different SOP version, not this one',
    'document_assessments_outcome_check': 'outcome must be accepted or rejected',
    'phases_display_order_check': 'display_order must be 0 or more',
    'phases_quote_display_order':
        'another phase of this quote already has this display_order; choose a different number',
    'phases_booking_display_order':
        'another phase of this booking already has this display_order; choose a different number',
    'phases_job_id_display_order_key':
        'another phase of this job already has this display_order; choose a different number',
    'visit_memos_check': 'review_ended_at must not be before review_started_at',
    'visit_memos_details_check': 'details must be a JSON object',
    'roles_period_check': 'ended_on must not be before started_on',
    'roles_not_on_self': 'a party cannot hold a role on itself: on_party_id must differ from party_id',
}

# Constraint names by their ending, first match wins. Every table that takes
# a write has a check named <table>_actor_check. Every table that cites
# evidence has a foreign key named <table>_evidence_id_fkey. A foreign key to
# work or to a party is named after its column in the same way.
CONSTRAINT_ENDINGS = {
    '_actor_check': 'actor must not be empty',
    '_evidence_id_fkey': 'evidence ID does not exist: cite evidence you recorded or found',
    '_party_id_fkey': 'the party named does not exist: create it first with create_party, '
                      'or check the ID with read_party',
    '_quote_id_fkey': 'the quote named does not exist: create it first with create_quote, '
                      'or find its ID with list_work',
    '_booking_id_fkey': 'the booking named does not exist: create it first with '
                        'create_booking, or find its ID with list_work',
    '_job_id_fkey': 'the job named does not exist: create it first with create_job, '
                    'or find its ID with list_work',
}

# Text columns that must not be empty or blank: <table>_<column>_check.
NONEMPTY_COLUMNS = ('title', 'name', 'summary', 'decision', 'reason', 'explanation', 'role',
                    'value', 'source', 'reference_type', 'version', 'media_type')
OPTIONAL_NONEMPTY_COLUMNS = ('waiting_for', 'description')

# Migration text cannot change once applied, so its older word for a chain
# (one quote with the bookings and jobs under it) is replaced here. Migration
# 015 raises the new wording itself; this map covers databases not yet on it.
MESSAGE_REWRITES = {
    'SOP version is retired; a load cannot adopt it':
        'SOP version is retired; a chain cannot adopt it',
    'a load adopts its SOP once, at the quote; its bookings and jobs follow it':
        'a chain adopts its SOP once, at the quote; its bookings and jobs follow it',
}

STALE_ADOPTION = 'expected previous SOP adoption is stale'
JOB_ONLY = 'SOP replacement and break-glass adoption are job-only'


def _job_only(arguments):
    kind = arguments.get('work_kind') or 'work item'
    if arguments.get('expected_previous_adoption_id'):
        return f'this {kind} already follows an SOP; only a job can replace its SOP version'
    return (f'only a job can adopt a break_glass SOP version or replace its SOP version; '
            f'this is a {kind}')


def database_message(error, arguments=None):
    """The sentence for one psycopg error. It is never empty."""
    constraint = error.diag.constraint_name or ''
    if constraint in CONSTRAINT_MESSAGES:
        return CONSTRAINT_MESSAGES[constraint]
    for ending, sentence in CONSTRAINT_ENDINGS.items():
        if constraint.endswith(ending):
            return sentence
    for column in NONEMPTY_COLUMNS:
        if constraint.endswith(f'_{column}_check'):
            return f'{column} must not be empty'
    for column in OPTIONAL_NONEMPTY_COLUMNS:
        if constraint.endswith(f'_{column}_check'):
            return f'{column} must not be blank: omit it when there is nothing to say'
    message = error.diag.message_primary or str(error).strip()
    if message == JOB_ONLY:
        return _job_only(arguments or {})
    return MESSAGE_REWRITES.get(message, message) or 'the database refused this call'


def _argument_holding(arguments, value, path=''):
    """The name of the argument that holds this value, such as work_id or
    judgments[0].milestone_id. None when it cannot be found."""
    if hasattr(arguments, 'model_dump'):
        arguments = arguments.model_dump()
    if isinstance(arguments, dict):
        entries = [(f'{path}.{key}' if path else str(key), item) for key, item in arguments.items()]
    elif isinstance(arguments, (list, tuple)):
        entries = [(f'{path}[{index}]', item) for index, item in enumerate(arguments)]
    else:
        return None
    for name, item in entries:
        if isinstance(item, type(value)) and item == value:
            return name
        found = _argument_holding(item, value, name)
        if found:
            return found
    return None


def refusal_message(error, arguments):
    """The sentence for one ValueError, given the tool call's arguments.

    A value that is not a UUID is reported with the argument that held it.
    The database reports a stale expected adoption in two different cases.
    With no expected ID, the work already follows an SOP. With one, the ID
    named is not the current adoption.
    """
    if isinstance(error, InvalidUuid):
        name = error.name or _argument_holding(arguments, error.value) or 'an ID argument'
        return f'{name} must be a UUID, got {error.value!r}'
    if isinstance(error, InvalidTime):
        name = _argument_holding(arguments, error.value) or 'a time or date argument'
        return f'{name} must be {error.wanted}; got {error.value!r}'
    message = str(error)
    if message != STALE_ADOPTION:
        return MESSAGE_REWRITES.get(message, message)
    kind = arguments.get('work_kind') or 'work item'
    if arguments.get('expected_previous_adoption_id'):
        return ('expected_previous_adoption_id is stale: it is not the current adoption '
                'of this work; read_work_sop shows the current one')
    if kind == 'job':
        return ('this job already follows an SOP; to replace its SOP version, name the '
                'current adoption in expected_previous_adoption_id (read_work_sop shows it)')
    return f'this {kind} already follows an SOP; only a job can replace its SOP version'

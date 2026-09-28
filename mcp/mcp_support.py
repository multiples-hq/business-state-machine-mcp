"""Wire-value parsing shared by the MCP tool modules."""

import os
from datetime import date, datetime
from uuid import UUID


def setting(name):
    """The server setting LEDGER_<name>, or the older SPINE_<name> when only that is set."""
    return os.environ.get(f'LEDGER_{name}') or os.environ.get(f'SPINE_{name}')


class InvalidUuid(ValueError):
    """A value that should be a UUID did not parse. The server names the argument."""

    def __init__(self, value):
        self.value = value
        self.name = None  # set when the caller already knows the argument
        super().__init__(f'not a UUID: {value!r}')


class InvalidTime(ValueError):
    """A time or a date did not parse. The server names the argument."""

    def __init__(self, value, wanted):
        self.value, self.wanted = value, wanted
        super().__init__(f'not {wanted}: {value!r}')


TIME_WANTED = ('an ISO 8601 time with a UTC offset, such as 2026-03-01T09:30:00+07:00 '
               'or ending in Z')
DATE_WANTED = 'a calendar date written YYYY-MM-DD, such as 2026-03-01'


def parse_uuid(value):
    try:
        return UUID(value)
    except (ValueError, TypeError, AttributeError) as error:
        raise InvalidUuid(value) from error


def found(value, what, identifier):
    """A read of an unknown ID is refused, so no answer never means nothing there."""
    if value is None:
        raise ValueError(f'{what} not found: {identifier}')
    return value


def parse_uuids(values):
    return [parse_uuid(value) for value in values]


def parse_bindings(bindings, name, key):
    """Check the UUID under `key` in each SOP binding before the database sees it.

    A value that is not a UUID is refused with its place, such as
    phase_bindings[0].phase_id. A binding without the key is left for the
    database, which refuses bindings that do not cover the stage.
    """
    if not isinstance(bindings, list):
        raise ValueError(f'{name} must be a list')
    checked = []
    for index, binding in enumerate(bindings):
        if not isinstance(binding, dict):
            raise ValueError(f'{name}[{index}] must be an object')
        if key in binding:
            try:
                parse_uuid(binding[key])
            except InvalidUuid as error:
                error.name = f'{name}[{index}].{key}'
                raise
        checked.append(binding)
    return checked


def parse_datetime(value):
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    except (ValueError, TypeError, AttributeError) as error:
        raise InvalidTime(value, TIME_WANTED) from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise InvalidTime(value, TIME_WANTED)
    return parsed


def parse_date(value):
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except (ValueError, TypeError) as error:
        raise InvalidTime(value, DATE_WANTED) from error

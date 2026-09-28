"""Drafts the agent puts in front of a person before anything is recorded.

A proposal is one JSON file in the run's proposals directory (LEDGER_PROPOSALS),
never a ledger row. It says what the agent would record and why, whether it
needs the person's judgment or is confident, and what became of it: the
harness asks the person, the person answers there, and the harness then
records the outcome through the ordinary ledger writes and marks the file
recorded with the memo that carries it, or withdraws it. Nothing here decides
anything; a screen can read these files to show the person what is waiting.
"""

import fcntl
import json
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

KINDS = ('party', 'milestone', 'memo', 'ignore', 'sop')


class ProposalConflict(ValueError):
    """The proposal is not in a state that allows this step."""


def _now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def _require_actor(actor):
    """A draft names who made it, by the same rule as every ledger write."""
    if not isinstance(actor, str) or not actor.strip():
        raise ValueError('actor must not be empty')


def _path(directory, identifier):
    if not identifier or '/' in identifier or identifier.startswith('.'):
        raise ValueError('proposal id must be a plain identifier')
    return Path(directory) / f'{identifier}.json'


@contextmanager
def _locked(directory, identifier):
    path = _path(directory, identifier)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path.with_suffix('.lock'), 'a+') as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def _write(directory, record):
    path = _path(directory, record['id'])
    temp = path.with_name(f'.{path.stem}.{uuid4().hex}.tmp')
    temp.write_text(json.dumps(record, indent=1, ensure_ascii=False))
    temp.replace(path)
    return record


def read_proposal(directory, identifier):
    path = _path(directory, identifier)
    return json.loads(path.read_text()) if path.exists() else None


def list_proposals(directory, status=None, work_id=None):
    """Every proposal, oldest first, optionally one status or one work item."""
    out = []
    for path in sorted(Path(directory).glob('*.json')):
        try:
            record = json.loads(path.read_text())
        except (OSError, ValueError):
            continue
        if status and record.get('status') != status:
            continue
        if work_id and (record.get('proposal') or {}).get('work_id') != work_id:
            continue
        out.append(record)
    out.sort(key=lambda r: r.get('proposed_at', ''))
    return out


def propose(directory, proposal, actor, identifier=None):
    """Write a new proposal. The harness asks the person right after, so
    asked_at is the moment it was proposed."""
    _require_actor(actor)
    if proposal.get('kind') not in KINDS:
        raise ValueError(f'kind must be one of {KINDS}')
    identifier = identifier or str(uuid4())
    with _locked(directory, identifier):
        existing = read_proposal(directory, identifier)
        if existing:
            if existing['proposal'] == proposal:
                return existing
            raise ProposalConflict('a different proposal already has this id')
        now = _now()
        return _write(directory, {
            'id': identifier, 'status': 'proposed', 'actor': actor, 'proposed_at': now,
            'asked_at': now, 'recorded': None, 'withdrawn': None, 'proposal': proposal})


def mark_recorded(directory, identifier, memo_id, read_back):
    """The outcome is in the ledger: the memo was read back, so the file says recorded."""
    with _locked(directory, identifier):
        record = read_proposal(directory, identifier)
        if record is None:
            raise ProposalConflict('no such proposal')
        if record['status'] == 'recorded':
            if record['recorded']['memo_id'] == memo_id:
                return record
            raise ProposalConflict(f"already recorded as memo {record['recorded']['memo_id']}")
        if record['status'] == 'withdrawn':
            raise ProposalConflict('this proposal was withdrawn; propose again')
        if not read_back:
            raise ProposalConflict(f'memo {memo_id} is not in the ledger; nothing is recorded')
        record['status'] = 'recorded'
        record['recorded'] = {'memo_id': memo_id, 'at': _now(), 'read_back': read_back}
        return _write(directory, record)


def withdraw(directory, identifier, reason, actor):
    _require_actor(actor)
    reason = (reason or '').strip()
    if not reason:
        raise ValueError('say why the proposal is withdrawn')
    with _locked(directory, identifier):
        record = read_proposal(directory, identifier)
        if record is None:
            raise ProposalConflict('no such proposal')
        if record['status'] == 'recorded':
            raise ProposalConflict(f"already recorded as memo {record['recorded']['memo_id']}")
        if record['status'] == 'withdrawn':
            return record
        record['status'] = 'withdrawn'
        record['withdrawn'] = {'reason': reason, 'actor': actor, 'at': _now()}
        return _write(directory, record)

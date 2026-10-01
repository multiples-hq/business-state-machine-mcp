"""Narrow stdio MCP adapter over the Postgres Ledger."""

import os
import inspect
import threading
import json
from datetime import datetime, timezone
from functools import wraps

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.server.mcpserver.utilities.func_metadata import FuncMetadata
import psycopg

from ledger import Ledger
from mcp_errors import database_message, refusal_message
from mcp_schema import PlainTool, without_titles
from mcp_support import parse_datetime as _datetime
from mcp_support import found as _found, parse_uuid as _uuid, setting
from mcp_params import (ISO_TIME, Actor, AnyWorkId, BeforePosition, IncludeEvidence, JobId,
                        NewId, PageLimit, ReadId, Title, WorkKindWords, said)
from mcp_files import register_file_tools
from mcp_documents import register_document_tools
from mcp_sop import register_sop_tools
from mcp_references import register_reference_tools
from mcp_work_review import register_work_review_tools
from mcp_review import register_review_tools
from mcp_evidence import EvidenceWorkInput, link_evidence, register_evidence_tools
from mcp_parties import register_party_tools
from mcp_money import register_money_tools
from mcp_payments import register_payment_tools
from mcp_proposals import register_proposal_tools


class ExactArgumentMetadata(FuncMetadata):
    """Leave MCP wire values intact; source text may itself be valid JSON."""

    def pre_parse_json(self, data):
        return data


def build_server(ledger, extra_tool_groups=()):
    """Build the server over one ledger.

    extra_tool_groups lets a program that embeds this server add its own tools.
    Each group is a function register(tool, serialized, ledger), the same shape
    as the register_* functions in the mcp_* modules. Extra groups are added
    after the built-in tools, so they can never replace a built-in name.
    """
    tools = []

    def tool():
        def register(function):
            # The agent reads the docstring: send it without source indentation.
            registered = PlainTool.from_function(
                function, description=inspect.cleandoc(function.__doc__ or ''))
            registered.parameters = without_titles(registered.parameters)
            metadata = registered.fn_metadata
            registered.fn_metadata = ExactArgumentMetadata(
                arg_model=metadata.arg_model, output_model=metadata.output_model,
                output_schema=metadata.output_schema, wrap_output=metadata.wrap_output,
            )
            tools.append(registered)
            return function
        return register

    call_lock = threading.Lock()
    log_path = setting('LOG')

    def log(tool, kwargs, outcome, note):
        """One JSON line per call when LEDGER_LOG names a file: what was asked,
        whether it worked, and a short note on the answer. Never breaks a call."""
        if not log_path:
            return
        try:
            arguments = {}
            for key, value in kwargs.items():
                if value is None:
                    continue
                text = value if isinstance(value, str) else json.dumps(value, default=str)
                arguments[key] = text if len(text) <= 300 else text[:300] + f'… ({len(text)} chars)'
            with open(log_path, 'a') as handle:
                handle.write(json.dumps({'at': datetime.now(timezone.utc).isoformat(),
                                         'tool': tool, 'arguments': arguments,
                                         'outcome': outcome, 'note': note}) + '\n')
        except Exception:
            pass

    def describe(result):
        if isinstance(result, list):
            return f'{len(result)} rows'
        if isinstance(result, dict):
            if len(result) == 1 and isinstance(next(iter(result.values())), list):
                return f'{len(next(iter(result.values())))} rows'
            keys =[k for k in ('id', 'evidence_id', 'judgment_id', 'memo_id', 'status', 'count',
                                'match_count', 'version_id', 'adoption_id')
                    if k in result]
            return ', '.join(f'{k} {result[k]}' for k in keys) if keys else f'{len(result)} fields'
        return '' if result is None else str(result)[:80]

    def serialized(function):
        @wraps(function)
        def call(*args, **kwargs):
            with call_lock:
                try:
                    result = function(*args, **kwargs)
                except ValueError as error:
                    message = refusal_message(error, kwargs)
                    log(function.__name__, kwargs, 'error', message[:200])
                    raise ToolError(message) from error
                except psycopg.Error as error:
                    # Every database error, not only broken table rules: a
                    # refusal never reaches the agent without its sentence.
                    message = database_message(error, kwargs)
                    log(function.__name__, kwargs, 'error', message[:200])
                    raise ToolError(message) from error
                except OSError as error:
                    # Never repeat the file-store path: it names a private server directory.
                    reason = error.strerror or type(error).__name__
                    log(function.__name__, kwargs, 'error', reason)
                    raise ToolError(f'{function.__name__} could not use the file store: {reason}') from error
                except Exception as error:
                    log(function.__name__, kwargs, 'error', f'{type(error).__name__}: {error}'[:200])
                    raise
                log(function.__name__, kwargs, 'ok', describe(result))
                return result
        return call

    @tool()
    @serialized
    def create_job(id: NewId, title: Title, actor: Actor) -> dict:
        """Create a job: one piece of work that is actually carried out.

        A job may stand alone, or be put under a booking afterwards with
        link_job_booking. Check list_work first so the same job is not
        created twice. Returns {"id": ...}.
        """
        return {'id': str(ledger.create_job(_uuid(id), title, actor))}

    @tool()
    @serialized
    def record_evidence(
        id: NewId,
        original_payload: said(str | None, 'The source text exactly as it arrived, such as a '
                               'whole message. Null only when the source is attachments alone.'),
        attachments: said(list[dict], 'Files that came with the source; [] when none. Each item '
                          'is exactly {"sha256": 64 lowercase hex, "media_type": text, '
                          '"byte_size": integer}, and its bytes must already be stored with '
                          'put_file or record_file_by_hash.'),
        actor: Actor,
        source_locator: said(str | None, 'Where the source lives outside the ledger, such as a '
                             'message id or URL. Kept exactly as sent; find_evidence matches '
                             'it exactly.') = None,
        source_at: said(str | None, 'When the source was written or sent. ' + ISO_TIME) = None,
        about_work: said(list[EvidenceWorkInput] | None, 'One {id: new link UUID, work_kind, '
                         'work_id} per work item this is about. Omit to leave it unlinked.') = None,
    ) -> dict:
        """Record a source exactly as it arrived, so that later writes can cite it.

        A source is a message's text, its files, or both: it needs a text
        payload or at least one attachment. Look for it with find_evidence
        first. The evidence and its about_work links are saved in one
        transaction. Evidence with no links stays citable from any work.
        """
        with ledger.connection.transaction():
            stored = ledger.record_evidence(
                _uuid(id), original_payload, attachments, actor, source_locator,
                _datetime(source_at),
            )
            link_evidence(ledger, stored, about_work, actor)
        return {'id': str(stored)}

    @tool()
    @serialized
    def read_history(milestone_id: said(str, 'UUID of the milestone.'), limit: PageLimit = 50,
                     before_position: BeforePosition = None,
                     include_evidence: IncludeEvidence = False) -> dict:
        """Read every judgment of one milestone, newest first, as {"judgments": [...]}.

        A milestone that was never judged gives an empty list. An unknown
        milestone ID is refused as not found.
        """
        ledger.require_row('milestone', _uuid(milestone_id))
        return {'judgments': ledger.history(
            _uuid(milestone_id), limit, before_position,
            include_evidence=include_evidence,
        )}

    @tool()
    @serialized
    def read_evidence(id: ReadId) -> dict:
        """Read one full original evidence record by ID, with its about_work links.

        An unknown ID is refused as not found.
        """
        return _found(ledger.evidence(_uuid(id)), 'evidence', id)

    register_file_tools(tool, serialized, ledger)

    @tool()
    @serialized
    def create_quote(id: NewId, title: Title, actor: Actor) -> dict:
        """Create a quote: the first record of work someone asked for, and the root of a chain.

        Bookings are created under it and jobs are linked to those bookings.
        Check list_work first so the same enquiry does not become two
        quotes. An ID names one kind of work only: an ID already used by a
        booking or a job is refused. Returns {"id": ...}.
        """
        return {'id': str(ledger.create_quote(_uuid(id), title, actor))}

    @tool()
    @serialized
    def create_booking(id: NewId,
                       quote_id: said(str, 'UUID of the existing quote this booking belongs to.'),
                       title: Title, actor: Actor) -> dict:
        """Create a booking under an existing quote: quoted work that is going ahead.

        A quote may have several bookings. If the quote adopted an SOP, the
        booking gets its booking-stage phases and milestones at once. An ID
        already used by a quote or a job is refused. Returns {"id": ...}.
        """
        return {'id': str(ledger.create_booking(_uuid(id), _uuid(quote_id), title, actor))}

    @tool()
    @serialized
    def link_job_booking(job_id: JobId,
                         booking_id: said(str, 'UUID of the existing booking the job carries out.'),
                         actor: Actor) -> dict:
        """Put an existing job under an existing booking, which joins it to that quote's chain.

        A job can have one booking. The same link again is a safe retry, a
        different booking is refused, and a link is never removed. If the
        quote adopted an SOP, the job gets its job-stage phases and
        milestones now; a job that already adopted a different SOP version
        is refused. Returns the job's ID as {"id": ...}.
        """
        return {'id': str(ledger.link_job_booking(_uuid(job_id), _uuid(booking_id), actor))}

    @tool()
    @serialized
    def read_work(id: AnyWorkId) -> dict:
        """Read one quote, booking or job, the work it is linked to and its party roles.

        For the whole chain with milestones and evidence, use read_case_brief.
        An unknown ID is refused as not found.
        """
        return _found(ledger.work(_uuid(id)), 'work', id)

    @tool()
    @serialized
    def list_work(kind: said(WorkKindWords | None, 'Keep only one kind. Omit for all '
                             'three.') = None,
                  limit: said(int, 'Most items to return: 1 to 1000, default 200.') = 200) -> dict:
        """List every quote, booking and job, newest first, so nothing is created twice.

        Use this first when you do not know what work exists: no other read
        finds a quote without its ID or a recorded outside number. The answer
        is {"work": [...]}; an empty ledger gives an empty list. Each entry
        has kind, id, title, actor, recorded_at, its recorded external
        references, latest_memo_at (the recorded time of its most recent
        memo, or null) and sop_version_id (the version it currently adopts, or
        null). Nothing is derived: there is no status, no open flag and no
        ordering by importance.
        """
        return {'work': ledger.work_items(kind, limit)}

    register_document_tools(tool, serialized, ledger)

    @tool()
    @serialized
    def read_case_brief(id: AnyWorkId) -> dict:
        """Read the whole chain one quote, booking or job belongs to, in one call.

        Start a turn here. Any id in the chain gives the same chain;
        requested_id echoes the id you sent. The brief holds
        the quote, its bookings and their jobs, each with the SOP version it
        adopts, its phases and every milestone's latest judgment with
        citations, the parties in their recorded roles, the evidence linked
        to it, the latest memo and, for a job, its documents. A milestone
        that no SOP adoption named shows from_sop false. charges lists every
        milestone with a charge line; one no SOP named is listed only there.
        The last section,
        not_recorded, lists what is missing or uncited on this chain, such
        as a work item that adopts no SOP version or a party role that cites
        no evidence, so a blank is never read as "nothing to say". The
        answer is {"brief": {...}}. Nothing is derived. An unknown id is
        refused as not found.
        """
        return {'brief': _found(ledger.case_brief(_uuid(id)), 'work', id)}

    if setting('PROPOSALS'):
        # Drafts for a person to answer, opt-in per run; files, not ledger rows.
        register_proposal_tools(tool, serialized, ledger)
    register_work_review_tools(tool, serialized, ledger)
    register_sop_tools(tool, serialized, ledger)
    register_reference_tools(tool, serialized, ledger)
    register_review_tools(tool, serialized, ledger)
    register_evidence_tools(tool, serialized, ledger)
    register_party_tools(tool, serialized, ledger)
    register_money_tools(tool, serialized, ledger)
    register_payment_tools(tool, serialized, ledger)
    for register_group in extra_tool_groups:
        register_group(tool, serialized, ledger)

    return MCPServer(
        'state-machine-ledger',
        instructions=(
            'Records evidence and the decisions of people and agents; it never makes decisions. '
            'Every ID is a UUID you generate; the same ID with the same arguments is a safe retry, '
            'and with different arguments it is refused. '
            'Times are ISO 8601 with a UTC offset, such as 2026-03-01T09:30:00+07:00 or ending in Z; '
            'dates are YYYY-MM-DD. '
            'A chain is one quote with the bookings and jobs under it. '
            'list_work lists every quote, booking and job: call it when you start with no memory of '
            'earlier sessions, so you do not create work that already exists. '
            'read_case_brief gives one whole chain as one JSON document: start a turn there. '
            'Use record_review to save new judgments and their required memo together. '
            'A chain adopts one SOP version, at its quote; its bookings and jobs follow it and must not adopt. '
            'A job with no booking adopts on its own. '
            'Only a job may replace its SOP adoption or adopt a break_glass version, '
            'which is an SOP published for recovery when the standard one no longer fits. '
            'Advice, not enforced: adopt an SOP version on the quote before the first review; '
            'if none fits or it is unclear which, ask a person rather than pick. '
            'Judging milestones with no SOP adopted is allowed; the case brief then lists the work as adopting no SOP version. '
            'Record a file another program dropped with record_file_by_hash; bytes never pass through the model. '
            'Link evidence to the work it is about, with about_work or link_evidence_work. '
            'Evidence linked to some work can be cited only on that work; evidence with no link can be cited anywhere. '
            'Resolve recorded outside numbers with resolve_external_reference; do not guess among candidates. '
            'read_work gives one work item and its links; read_work_review gives its milestones with their latest judgments. '
            'A party is a person, agent or organization; what is said about it is appended: identifiers and roles, each with evidence. '
            'The operator is the organization that runs this ledger; a person is whoever answers your questions. '
            'read_party gives one party with its identifiers and its roles as they stand now. '
            'read_work_sop separates the milestones of the current SOP adoption from those an earlier adoption had '
            'and those no adoption ever named. '
            'read_sop_adoption keeps the membership of an old adoption but shows judgments as they stand now. '
            'When you retry a write, send the same IDs again, including the IDs inside a review or an adoption. '
            'An actor label is a claim, not authenticated; neither it nor a cited instruction is approval.'
        ),
        tools=tools,
    )


def _session_event(event):
    """A 'connected' or 'disconnected' line in LEDGER_LOG, with the process id
    and the name of the process that started this server (sshd for a remote
    harness, the harness binary for a local one). Never raises."""
    path = setting('LOG')
    if not path:
        return
    try:
        parent = ''
        try:
            parent = open(f'/proc/{os.getppid()}/comm').read().strip()
        except OSError:
            pass
        with open(path, 'a') as handle:
            handle.write(json.dumps({'at': datetime.now(timezone.utc).isoformat(),
                                     'event': event, 'pid': os.getpid(),
                                     'started_by': parent}) + '\n')
    except Exception:
        pass


def main(extra_tool_groups=()):
    dsn, files, drop = setting('DSN'), setting('FILES'), setting('DROP')
    if not dsn or not files or not drop:
        raise SystemExit('LEDGER_DSN, LEDGER_FILES and LEDGER_DROP are required')
    ledger = Ledger(dsn, files, drop=drop, options='-c role=ledger_client')
    _session_event('connected')
    try:
        build_server(ledger, extra_tool_groups).run('stdio')
    finally:
        _session_event('disconnected')
        ledger.close()


if __name__ == '__main__':
    main()

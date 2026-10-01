"""MCP tools for money: what is owed (charges and invoices) and the two reads.

A charge is a milestone with at least one charge line. It is judged with
record_review like any other milestone. Payments are in mcp_payments.py.
"""

from decimal import Decimal, InvalidOperation

from pydantic import BaseModel, ConfigDict

import mcp_params as P
from mcp_params import Actor, AnyWorkId, WorkId, said
from mcp_support import found, parse_date, parse_uuid
from mcp_work_review import build_work_review_calls

NEW = 'New UUID; the same on a retry.'
Money = str | int | None
Amount = said(Money, 'Text such as "1250.00", or a whole number. Below zero for a credit. '
              'Omit when unknown.')
Currency = said(str | None, 'Code in capitals, such as USD. Needed with an amount or rate.')
HomeAmount = said(Money, "The same money in the shop's own currency, from the bank or a "
                  'stated rate. Omit when unknown.')
HomeCurrency = said(str | None, 'Currency of home_amount; needed with it.')
Reason = said(str, 'Why, and where in the evidence. Not empty.')
Evidence = said(str, 'UUID of the evidence: the message, the file, or the owner\'s word.')


class InvoiceWorkInput(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)

    id: said(str, NEW)
    work_kind: P.WorkKind
    work_id: WorkId


class InvoiceInput(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)

    id: said(str, NEW)
    from_party_id: said(str, 'UUID of the issuer: the party owed.')
    to_party_id: said(str, 'UUID of the recipient: the party that owes.')
    number: said(str | None, "The issuer's number. Omit when it has none.") = None
    issued_on: said(str | None, P.DATE) = None
    terms: said(str | None, 'Terms as written, such as "net 45".') = None
    due_on: said(str | None, 'Only when stated or worked out from the terms; say which in reason.') = None
    stated_total: said(Money, 'The total the bill states; below zero for a credit note.') = None
    currency: said(str | None, "The bill's currency. Give it even when the total is unknown, "
                   'so a payment can be put on the bill.') = None
    replaces_invoice_id: said(str | None, 'UUID of the latest version of a bill this one reissues.') = None
    work: said(list[InvoiceWorkInput] | None, 'The work this bill covers: one {id, work_kind, '
               'work_id} per quote, booking or job. Omit for a bill of no job, such as rent.') = None


class NewChargeInput(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)

    work_kind: P.WorkKind
    work_id: WorkId
    title: said(str, 'What the charge is, in a few words.')
    phase_id: said(str | None, 'UUID of a phase of that work item.') = None


class ChargeLineInput(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)

    id: said(str, NEW)
    charge_id: said(str, 'UUID of the charge, a milestone.')
    new_charge: said(NewChargeInput | None, 'Creates the charge. Omit when it exists.') = None
    charge_type: said(str, 'What is charged, in your business words.')
    owes_party_id: said(str | None, 'UUID of the party that owes. Omit on an invoiced line, '
                        "or to keep the charge's.") = None
    owed_party_id: said(str | None, 'UUID of the party owed. Omit on an invoiced line, or to '
                        "keep the charge's.") = None
    quantity: said(Money, 'Number of units, as written.') = None
    rate: said(Money, 'Price per unit, as written. A percentage goes in reason.') = None
    amount: Amount = None
    currency: Currency = None
    home_amount: HomeAmount = None
    home_currency: HomeCurrency = None
    replaces_line_id: said(str | None, 'UUID of the current line of this kind on this charge. '
                           'Required when the charge has one.') = None


def money(value, name, signed=False):
    """A number sent as text or a whole number, kept exactly. Zero or more,
    unless signed: a line, a rate or a stated total may be below zero."""
    if value is None:
        return None
    try:
        number = Decimal(value.strip() if isinstance(value, str) else int(value))
    except (InvalidOperation, ValueError, TypeError):
        number = None
    if isinstance(value, bool) or number is None or not number.is_finite() or (
            number < 0 and not signed):
        wanted = 'a number' if signed else 'zero or more'
        raise ValueError(f'{name} must be {wanted}, written as text such as "1250.00" '
                         f'or as a whole number; got {value!r}')
    return number


def quantity(value, name):
    """A quantity may be any finite number, as written."""
    if value is None:
        return None
    try:
        number = Decimal(value.strip() if isinstance(value, str) else int(value))
    except (InvalidOperation, ValueError, TypeError):
        number = None
    if isinstance(value, bool) or number is None or not number.is_finite():
        raise ValueError(f'{name} must be a number, such as "2" or "1.5"; got {value!r}')
    return number


def optional_uuid(value):
    return parse_uuid(value) if value else None


def register_money_tools(tool, serialized, ledger):
    create_milestone = build_work_review_calls(ledger)['create_work_milestone']

    @tool()
    @serialized
    def record_charges(
        actor: Actor, reason: Reason, evidence_id: Evidence,
        lines: said(list[ChargeLineInput], 'The charge lines. May be empty only with a new '
                    'invoice whose lines are not known yet.'),
        invoice: said(InvoiceInput | None, 'A new bill: its lines are invoiced lines.') = None,
        invoice_id: said(str | None, 'UUID of the latest version of a bill already recorded, '
                         'when adding its lines later.') = None,
    ) -> dict:
        """Record what is owed: charge lines, and the bill they come from, in one transaction.

        A charge is one priced thing on one quote, booking or job, between one
        party that owes and one that is owed. Lines are expected (agreed)
        unless the call names a bill (invoice or invoice_id); then they are
        invoiced. A charge has one current line of each kind, shown side by
        side and never added. A new amount, or a later bill's, replaces the
        current line. A reissued bill names replaces_invoice_id. A credit is
        a line below zero. reason and evidence_id apply to every row. Numbers are
        text or whole numbers; an unknown one is omitted, never 0. One bad
        line saves nothing. Judge a charge with
        record_review: done is accepted, pending is waiting for detail,
        blocked is disputed, failed is waived. Returns invoice_id, line_ids,
        charge_ids and warnings, such as a bill number the same issuer
        already used, or a line whose parties differ from its bill's.
        """
        if invoice is not None and invoice_id:
            raise ValueError('send invoice for a new bill or invoice_id for one already recorded, '
                             'not both')
        if not lines and invoice is None:
            raise ValueError('record_charges needs at least one line, or a new invoice')
        identifiers = [parse_uuid(line.id) for line in lines]
        if len(set(identifiers)) != len(identifiers):
            raise ValueError('record_charges must not repeat a line ID')
        bill = parse_uuid(invoice.id) if invoice else optional_uuid(invoice_id)
        kind = 'invoiced' if bill else 'expected'
        evidence = parse_uuid(evidence_id)
        warnings = []
        with ledger.connection.transaction():
            if invoice is not None:
                ledger.record_invoice(
                    bill, invoice.number, parse_uuid(invoice.from_party_id),
                    parse_uuid(invoice.to_party_id), parse_date(invoice.issued_on),
                    invoice.terms, parse_date(invoice.due_on),
                    money(invoice.stated_total, 'invoice.stated_total', signed=True),
                    invoice.currency,
                    optional_uuid(invoice.replaces_invoice_id), reason, evidence, actor)
                for link in invoice.work or []:
                    ledger.link_invoice_work(parse_uuid(link.id), bill, link.work_kind,
                                             parse_uuid(link.work_id), actor)
                same = ledger.same_number_invoices(bill)
                if same:
                    warnings.append(f'the same issuer already sent invoice number '
                                    f'{invoice.number!r} to the same recipient: {", ".join(same)}. '
                                    'Saved; ask whether it is a duplicate or a reissue.')
            # Every new charge first, so a line may name any charge of this call.
            for line in lines:
                if line.new_charge is not None:
                    create_milestone(id=line.charge_id, work_kind=line.new_charge.work_kind,
                                     work_id=line.new_charge.work_id,
                                     title=line.new_charge.title, actor=actor,
                                     phase_id=line.new_charge.phase_id)
            for index, (line, identifier) in enumerate(zip(lines, identifiers)):
                at = f'lines[{index}]'
                ledger.record_charge_line(
                    identifier, parse_uuid(line.charge_id), optional_uuid(line.owes_party_id),
                    optional_uuid(line.owed_party_id), line.charge_type,
                    quantity(line.quantity, f'{at}.quantity'),
                    money(line.rate, f'{at}.rate', signed=True),
                    money(line.amount, f'{at}.amount', signed=True), line.currency,
                    money(line.home_amount, f'{at}.home_amount', signed=True),
                    line.home_currency, kind, bill,
                    optional_uuid(line.replaces_line_id), reason, evidence, actor)
                if bill and ledger.line_parties_differ_from_bill(identifier):
                    warnings.append(f'{at} names other parties than its bill (the bill is from '
                                    'the party owed to the party that owes). Saved; check who '
                                    'owes whom.')
            if invoice is not None and invoice.replaces_invoice_id:
                kept = [i for i in ledger.lines_differing_from_bill(bill)
                        if i not in {str(n) for n in identifiers}]
                if kept:
                    warnings.append(f'the reissued bill names other parties than {len(kept)} of '
                                    'its current lines; they keep their parties. Saved; check '
                                    'who owes whom.')
        return {'invoice_id': str(bill) if bill else None,
                'line_ids': [str(i) for i in identifiers],
                'charge_ids': [str(parse_uuid(line.charge_id)) for line in lines],
                'warnings': warnings}

    @tool()
    @serialized
    def read_work_money(id: AnyWorkId) -> dict:
        """Read the money of the whole chain a quote, booking or job is in.

        items: each quote, booking and job, its charges and linked bills.
        A charge gives its parties, direction (payable,
        receivable, between_others, unknown), judgment, current expected and
        invoiced lines with earlier amounts, paid, open (invoiced minus paid;
        a minus is an overpayment), due_on, days_past_due, allocations (IDs
        a move needs, paid_by, paid_to, reference, method) and marks:
        changed_since_judged, before_procedure_change. Money on a bill as a
        whole stays there: money_on_bill, and bill_holds on its charges. A
        bill without lines reads "billed, stated total, lines not recorded"
        (or "total not stated"); one whose lines moved, "lines now on ...".
        Each item's cash: per currency, what the operator paid_out and took
        in (taken_in); cash, not margin. totals: expected and invoiced sales,
        costs and sales minus costs per currency, and per home currency where
        recorded, waived charges left out; bills_without_lines apart;
        others_bills: what the operator paid on bills between others.
        """
        return found(ledger.work_money(parse_uuid(id)), 'work', id)

    @tool()
    @serialized
    def read_money_open(party_id: said(str | None, 'UUID of one customer or vendor. Omit for '
                                       'the whole business.') = None) -> dict:
        """Read what is open: owed to you, owed by you, and what needs a look.

        receivable, payable, between_others and unknown list billed charges
        and bills without lines whose open is not 0, oldest due first, with
        open, due_on, days_past_due and allocations, and one row (kind
        money_on_bill) per bill holding money not put on its lines. A waived
        charge shows only money paid on it. totals sum open per direction
        and currency. Also: unallocated_payments, paid_not_billed (charges
        paid before a bill), bills_without_lines (linked to work) and
        awaiting_judgment (unassessed, or changed since judged). read_at is
        when it was read.
        """
        identifier = parse_uuid(party_id) if party_id else None
        return found(ledger.money_open(identifier), 'party', party_id)

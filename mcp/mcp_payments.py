"""MCP tool for payments: money that moved, and where it goes.

A payment is from one party to another. An allocation puts it, or part of
it, on a charge or on a bill, whoever the charge or bill names. A payment
can wait with no allocation until the owner says what it was for.
"""

from pydantic import BaseModel, ConfigDict

import mcp_params as P
from mcp_money import NEW, Evidence, HomeAmount, HomeCurrency, Reason, money, optional_uuid
from mcp_params import Actor, said
from mcp_support import parse_date, parse_uuid


class PaymentInput(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)

    id: said(str, NEW)
    from_party_id: said(str, 'UUID of the party that paid.')
    to_party_id: said(str, 'UUID of the party that received it.')
    amount: said(str | int, 'Text such as "2000.00", or a whole number. Zero or more.')
    currency: said(str, 'Code in capitals, such as USD.')
    home_amount: HomeAmount = None
    home_currency: HomeCurrency = None
    paid_on: said(str | None, P.DATE) = None
    reference: said(str | None, 'The reference as written on the payment.') = None
    method: said(str | None, 'How it was paid, as written, such as "wire".') = None
    replaces_payment_id: said(str | None, 'UUID of the latest version, to correct a recording '
                              'mistake. A bounce or refund is a new payment the other way.') = None


class AllocationInput(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)

    id: said(str, NEW)
    charge_id: said(str | None, 'UUID of the charge it pays. Give this or invoice_id.') = None
    invoice_id: said(str | None, 'UUID of a bill paid as a whole, such as rent.') = None
    amount: said(str | int, 'How much of the payment goes here. Zero or more.')
    replaces_allocation_id: said(str | None, 'UUID of the latest allocation of this payment, '
                                 'to change or move it.') = None


def register_payment_tools(tool, serialized, ledger):
    @tool()
    @serialized
    def record_payment(
        actor: Actor, reason: Reason, evidence_id: Evidence,
        allocations: said(list[AllocationInput], 'Where the money goes; [] when not known yet.'),
        payment: said(PaymentInput | None, 'A new payment.') = None,
        payment_id: said(str | None, 'UUID of a payment already recorded, to allocate it '
                         'now.') = None,
    ) -> dict:
        """Record a payment and where it goes, or allocate one already recorded, in one call.

        Put a payment on whichever charge or bill it settled, in its
        currency, whoever paid. A payment from the party owed (a bounce or
        refund is a new payment the other way) lowers what was paid. The
        allocations of a payment never add up to more than it. To move
        money, replace an allocation (replaces_allocation_id; the reads list
        IDs) naming the new target. reason and evidence_id
        apply to every row. Returns the payment's unallocated remainder and
        paid and open on each target touched.
        """
        if (payment is None) == (not payment_id):
            raise ValueError('send payment for a new payment or payment_id for one already '
                             'recorded: exactly one of the two')
        paid = parse_uuid(payment.id) if payment else parse_uuid(payment_id)
        evidence = parse_uuid(evidence_id)
        identifiers = [parse_uuid(a.id) for a in allocations]
        if len(set(identifiers)) != len(identifiers):
            raise ValueError('record_payment must not repeat an allocation ID')
        charges, bills = [], []
        with ledger.connection.transaction():
            if payment is not None:
                ledger.record_payment(
                    paid, parse_uuid(payment.from_party_id), parse_uuid(payment.to_party_id),
                    money(payment.amount, 'payment.amount'), payment.currency,
                    money(payment.home_amount, 'payment.home_amount'), payment.home_currency,
                    parse_date(payment.paid_on), payment.reference, payment.method,
                    optional_uuid(payment.replaces_payment_id), reason, evidence, actor)
            for index, (allocation, identifier) in enumerate(zip(allocations, identifiers)):
                charge, bill = optional_uuid(allocation.charge_id), optional_uuid(allocation.invoice_id)
                if (charge is None) == (bill is None):
                    raise ValueError(f'allocations[{index}] needs exactly one of charge_id and '
                                     'invoice_id')
                ledger.record_payment_allocation(
                    identifier, paid, charge, bill,
                    money(allocation.amount, f'allocations[{index}].amount'),
                    optional_uuid(allocation.replaces_allocation_id), reason, evidence, actor)
                (charges if charge else bills).append(charge or bill)
        book, targets = ledger.target_figures(list(dict.fromkeys(charges)),
                                              list(dict.fromkeys(bills)))
        if paid not in book.payment_root:
            raise ValueError(f'payment not found: {payment_id}')
        summary = book.payment(book.payment_root[paid])
        return {'payment_id': str(paid), 'allocation_ids': [str(i) for i in identifiers],
                'unallocated': summary['unallocated'], 'currency': summary['currency'],
                'targets': targets}

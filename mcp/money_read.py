"""Shape a Book into the answers of read_work_money and read_money_open.

Totals never mix currencies. Home-currency totals use only figures the
ledger was given: a line's home_amount in its home_currency, or its amount
when its own currency is a home currency seen in the same read. Nothing is
converted. A waived charge (judged failed) is shown but left out of totals.
A bill with no lines has no charge, so it is listed apart in totals, by its
stated total, and never added to sales or costs. Each item's cash is what
the operator paid out and took in on that item's charges and bills, read
from the payments, whoever the charges name: cash, not margin. Money on a
bill as a whole counts once: on the item of the bill's first line, or for
a bill without lines on the first item it is linked to; the bill names
that item (cash_counted_on) where it is listed on any other. totals say
what the operator paid or received on charges and bills between other
parties, which sales minus costs leaves out.
"""

from collections import defaultdict
from decimal import Decimal

from money_book import KINDS, text

WAIVED = 'failed'
SIDES = {'receivable': 'sales', 'payable': 'costs'}


def _add(group, key, amount):
    group[key] = group.get(key, Decimal(0)) + amount


def _margin(sums):
    sales, costs = sums.get('sales', Decimal(0)), sums.get('costs', Decimal(0))
    return {'sales': text(sales), 'costs': text(costs), 'sales_minus_costs': text(sales - costs)}


def chain_totals(book, charge_ids, lineless=()):
    """Expected and invoiced totals of these charges, sales minus costs, per
    currency and, where known, per home currency; and the bills without lines."""
    by_currency = defaultdict(dict)    # (kind, currency) -> sums
    unknown = defaultdict(int)         # kind -> lines with no amount
    lines = []
    for charge_id in charge_ids:
        judgment = book.judgments.get(charge_id)
        if judgment and judgment['status'] == WAIVED:
            continue
        for kind in KINDS:
            line, _ = book.current(charge_id, kind)
            side = line and SIDES.get(book.direction(line['owes_party_id'], line['owed_party_id']))
            if side is None:
                continue
            if line['amount'] is None:
                unknown[kind] += 1
                continue
            _add(by_currency[(kind, line['currency'])], side, line['amount'])
            lines.append((kind, side, line))
    homes = sorted({line['home_currency'] for _, _, line in lines if line['home_currency']})
    by_home, unconverted = defaultdict(dict), 0
    for kind, side, line in lines:
        if line['home_currency']:
            _add(by_home[(kind, line['home_currency'])], side, line['home_amount'])
        elif line['currency'] in homes:
            _add(by_home[(kind, line['currency'])], side, line['amount'])
        else:
            unconverted += 1
    answer = {kind: [{'currency': currency, **_margin(sums)}
                     for (k, currency), sums in sorted(by_currency.items()) if k == kind]
              for kind in KINDS}
    answer['unknown_amount_lines'] = dict(unknown)
    answer['bills_without_lines'] = [
        {'direction': book.direction(bill['to_party_id'], bill['from_party_id']),
         'currency': bill['currency'], 'stated_total': text(bill['stated_total'])}
        for bill in (book.invoices[root][-1] for root in lineless)]
    answer['home'] = None if not homes else {
        'currencies': homes,
        'warning': ('more than one home currency is recorded; totals are shown for each'
                    if len(homes) > 1 else None),
        **{kind: [{'currency': currency, **_margin(sums)}
                  for (k, currency), sums in sorted(by_home.items()) if k == kind]
           for kind in KINDS},
        'unconverted_lines': unconverted}
    return answer


def _cash_allocations(book, item_id, charge_ids):
    """(allocation, direction of its target) for the money counted in one
    item's cash: on its charges, and on the bills counted on it."""
    out = []
    for charge_id in charge_ids:
        first = book.lines[charge_id][0]
        direction = book.direction(first['owes_party_id'], first['owed_party_id'])
        out += [(a, direction) for a in book.on_charge.get(charge_id, [])]
    for root, versions in book.invoices.items():
        counted = book.counted_on(root)
        if counted and counted[1] == item_id:
            latest = versions[-1]
            direction = book.direction(latest['to_party_id'], latest['from_party_id'])
            out += [(a, direction) for a in book.on_invoice.get(root, [])]
    return out


def _operator_sums(book, allocations):
    """Per currency, [paid by the operator, received by the operator]."""
    sums = defaultdict(lambda: [Decimal(0), Decimal(0)])
    for allocation in allocations:
        payment = book.latest_payment(allocation['payment_id'])
        if book.operator is None or not allocation['amount']:
            continue
        if payment['from_party_id'] == book.operator:
            sums[payment['currency']][0] += allocation['amount']
        elif payment['to_party_id'] == book.operator:
            sums[payment['currency']][1] += allocation['amount']
    return sums


def cash(book, allocations):
    """Per currency, the money the operator paid (paid_out) and received (taken_in)."""
    return [{'currency': currency, 'paid_out': text(out), 'taken_in': text(taken)}
            for currency, (out, taken) in sorted(_operator_sums(book, allocations).items())]


def others_bills(book, allocations):
    """Per currency, what the operator paid or received on charges and bills
    between other parties: in cash, never in sales minus costs."""
    sums = _operator_sums(book, [a for a, direction in allocations
                                 if direction == 'between_others'])
    out = []
    for currency, (paid, received) in sorted(sums.items()):
        if not (paid or received):
            continue
        note = (f'sales minus costs leaves out {text(paid)} paid'
                + (f' and {text(received)} received' if received else '')
                + ' on bills addressed to other parties; see cash')
        out.append({'currency': currency, 'paid_on_others_bills': text(paid),
                    'received_on_others_bills': text(received), 'note': note})
    return out


def work_answer(book, read_at, requested_id, chain, titles):
    items, charge_ids, lineless, counted = [], [], [], []
    for kind, item_id in chain:
        mine = [c for c, info in book.charges.items() if info['work_id'] == item_id]
        charge_ids += mine
        roots = sorted({book.invoice_root[link['invoice_id']]
                        for links in book.links.values() for link in links
                        if item_id in (link['quote_id'], link['booking_id'], link['job_id'])},
                       key=lambda root: (book.invoices[root][0]['recorded_at'], root))
        lineless += [root for root in roots if not book.ever_billed.get(root)
                     and root not in lineless]
        invoices = []
        for root in roots:
            entry = book.invoice(root)
            where = book.counted_on(root)
            if where and where[1] != item_id:
                entry['cash_counted_on'] = {'kind': where[0], 'id': str(where[1])}
            invoices.append(entry)
        allocations = _cash_allocations(book, item_id, mine)
        counted += allocations
        items.append({'kind': kind, 'id': str(item_id), 'title': titles.get(item_id),
                      'charges': [book.charge(c) for c in mine],
                      'invoices': invoices,
                      'cash': cash(book, [a for a, _ in allocations])})
    totals = chain_totals(book, charge_ids, lineless)
    totals['others_bills'] = others_bills(book, counted)
    return {'read_at': read_at, 'requested_id': str(requested_id),
            'operator': book.party(book.operator) if book.operator else None,
            'items': items, 'totals': totals}


def _due_order(entry):
    recorded = (entry.get('invoiced') or entry.get('expected') or entry)['recorded_at']
    return (entry['due_on'] is None, entry['due_on'] or '', entry['issued_on'] or '',
            recorded, entry['id'])


def _bill_money(entry, held):
    """One open row for money on a bill as a whole, not assigned to lines."""
    name = entry['number'] or entry['id']
    title = (f'{text(held)} paid on bill {name}, not assigned to lines' if held > 0 else
             f'{text(-held)} refunded on bill {name}, not assigned to lines')
    return {'id': entry['id'], 'kind': 'money_on_bill', 'number': entry['number'],
            'title': title,
            'direction': entry['direction'], 'from': entry['from'], 'to': entry['to'],
            'currency': entry['currency'], 'open': text(-held), 'due_on': entry['due_on'],
            'issued_on': entry['issued_on'], 'recorded_at': entry['recorded_at'],
            'allocations': entry['allocations']}


def open_answer(book, read_at, party_id=None):
    """Everything open, by direction, oldest due first, with what else needs a look."""
    def concerns(*parties):
        return party_id is None or party_id in parties

    lists = {d: [] for d in ('receivable', 'payable', 'between_others', 'unknown')}
    paid_not_billed, awaiting, totals = [], [], defaultdict(lambda: [Decimal(0), 0, 0])
    bill = book.bill_entry

    for charge_id in book.charges:
        first = book.lines[charge_id][0]
        billed = book.current(charge_id, 'invoiced')[0]
        on_bill = billed and book.latest_invoice(billed['invoice_id'])
        # A charge concerns a party it names, or the party its bill is from or to.
        if not (concerns(first['owes_party_id'], first['owed_party_id'])
                or (on_bill and concerns(on_bill['from_party_id'], on_bill['to_party_id']))):
            continue
        entry = book.charge(charge_id)
        waived = entry['judgment'] == WAIVED
        if entry['invoiced'] is None and not waived:
            if entry['note']:
                paid_not_billed.append(entry)
            continue
        if not waived and (entry['judgment'] == 'unassessed' or entry['changed_since_judged']):
            awaiting.append(entry)
        # A waived charge owes 0: it is listed while money paid on it is there.
        if entry['open'] is None and waived or (
                entry['open'] is not None and Decimal(entry['open']) == 0):
            continue
        # A bill settled as a whole: its lines are not open, whichever line
        # the money was for.
        bill_open = billed and bill(book.invoice_root[billed['invoice_id']])['open']
        if bill_open and Decimal(bill_open) == 0:
            continue
        lists[entry['direction']].append(entry)
    bills_without_lines = []
    for root, versions in book.invoices.items():
        latest = versions[-1]
        # A bill concerns a party its latest version names, or any of its
        # current lines names.
        if not (concerns(latest['from_party_id'], latest['to_party_id'])
                or any(concerns(line['owes_party_id'], line['owed_party_id'])
                       for line in book.billed.get(root, []))):
            continue
        if book.ever_billed.get(root):
            # Its charges are listed; money on the bill as a whole is one row
            # beside them, unless the bill is settled.
            entry = bill(root)
            held = Decimal(entry['money_on_bill'])
            if held and (entry['open'] is None or Decimal(entry['open']) != 0):
                lists[entry['direction']].append(_bill_money(entry, held))
            continue
        entry = bill(root)
        if entry['work']:
            bills_without_lines.append(entry)
        if entry['open'] is None or Decimal(entry['open']) != 0:
            lists[entry['direction']].append(entry)
    for direction, entries in lists.items():
        entries.sort(key=_due_order)
        for entry in entries:
            currency = entry.get('currency') or (
                entry.get('invoiced') or entry.get('expected') or {}).get('currency')
            group = totals[(direction, currency)]
            if entry['open'] is None:
                group[1] += 1
            else:
                group[0] += Decimal(entry['open'])
                group[2] += 1
    unallocated = []
    for root, versions in book.payments.items():
        latest = versions[-1]
        if not concerns(latest['from_party_id'], latest['to_party_id']):
            continue
        entry = book.payment(root)
        if Decimal(entry['unallocated']) != 0:
            unallocated.append(entry)
    return {
        'read_at': read_at,
        'operator': book.party(book.operator) if book.operator else None,
        'party': book.party(party_id) if party_id else None,
        **lists,
        'totals': [{'direction': direction, 'currency': currency,
                    'open': text(sums[0]) if sums[2] else None,
                    'unknown_open': sums[1]}
                   for (direction, currency), sums in sorted(
                       totals.items(), key=lambda item: (item[0][0], str(item[0][1])))],
        'unallocated_payments': unallocated,
        'paid_not_billed': paid_not_billed,
        'bills_without_lines': bills_without_lines,
        'awaiting_judgment': awaiting,
    }

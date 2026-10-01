"""The money of a set of charges, invoices and payments, worked out when read.

Nothing here is stored and nothing is decided. The rules:

- Every money table forms chains through its replaces column. The latest
  row of a chain is the one nothing replaces. Reads use latest rows.
- A charge has at most one current line per kind, expected and invoiced.
  They are shown side by side and never added.
- Paid on a charge is the sum of the latest allocations on it, whoever paid.
  A payment from the party owed (money sent back) takes away; any other
  adds. Open is invoiced minus paid. With nothing invoiced, open is null,
  and a charge with money on it reads "paid, not yet billed".
- An invoice with no lines is settled on itself: open is its stated total
  minus what was paid on it.
- Money put on a bill that has lines stays on the bill: nothing guesses
  which line it settled. The bill's open is its lines not waived, minus
  the money on all its lines (waived ones too), minus the money on the
  bill (money_on_bill). A charge counts only the money put on that charge;
  bill_holds shows what its bill holds as a whole. A charge whose bill's
  open is 0 or less while the bill holds money reads "covered by money on
  bill <number>", never late.
- A waived charge (judged failed) owes 0: its open is minus what was paid
  on it, with the note "waived, <paid> paid".
- A bill whose lines all moved to a later bill (a charge billed again)
  reads "lines now on <bill>", open null: its charges are read there.
- An unknown amount stays None, never 0. Currencies are never added; the
  database keeps what was paid on one charge or one bill in one currency.
- Direction comes from the operator party: payable when it owes,
  receivable when it is owed, between_others otherwise, unknown with no
  operator.
"""

from collections import defaultdict
from datetime import date, datetime
from decimal import Decimal

KINDS = ('expected', 'invoiced')
LINES_MISSING = 'billed, stated total, lines not recorded'
TOTAL_MISSING = 'billed, total not stated, lines not recorded'
PAID_NOT_BILLED = 'paid, not yet billed'


def text(value):
    if value is None:
        return None
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return str(value)


def chains(rows, replaces):
    """Each row's chain, as {row id: first id}, and {first id: rows oldest first}."""
    by_id = {row['id']: row for row in rows}
    after = {row[replaces]: row['id'] for row in rows if row[replaces]}
    root, versions = {}, {}
    for row in rows:
        if row[replaces] is None:
            step, chain = row['id'], []
            while step is not None:
                chain.append(by_id[step])
                root[step] = row['id']
                step = after.get(step)
            versions[row['id']] = chain
    return root, versions


class Book:
    """Rows loaded by money.py, and the figures a read needs from them."""

    def __init__(self, rows, today):
        self.today = today
        self.parties = {p['id']: p for p in rows['parties']}
        operator = [p for p in rows['parties'] if p['is_operator']]
        self.operator = operator[0]['id'] if operator else None
        self.invoice_root, self.invoices = chains(rows['invoices'], 'replaces_invoice_id')
        self.payment_root, self.payments = chains(rows['payments'], 'replaces_payment_id')
        self.links = defaultdict(list)
        for link in rows['links']:
            self.links[self.invoice_root[link['invoice_id']]].append(link)
        self.charges = {c['id']: c for c in rows['charges']}
        self.judgments = {j['milestone_id']: j for j in rows['judgments']}
        self._bills = {}                          # invoice chain -> invoice(), once per read
        self.adoptions = {a['job_id']: a for a in rows['adoptions']}
        replaced = {line['replaces_line_id'] for line in rows['lines']}
        self.lines = defaultdict(list)            # charge id -> lines, oldest first
        self.billed = defaultdict(list)           # invoice chain -> current lines
        self.ever_billed = defaultdict(list)      # invoice chain -> every line it carried
        for line in rows['lines']:
            self.lines[line['milestone_id']].append(line)
            if line['invoice_id']:
                self.ever_billed[self.invoice_root[line['invoice_id']]].append(line)
                if line['id'] not in replaced:
                    self.billed[self.invoice_root[line['invoice_id']]].append(line)
        # charge id -> (kind, id) of its quote, booking or job
        self.work_of = {c['id']: (c['work_kind'], c['work_id']) for c in rows['charges']}
        self.work_of.update({w['id']: (w['work_kind'], w['work_id'])
                             for w in rows.get('line_work', [])})
        gone = {a['replaces_allocation_id'] for a in rows['allocations']}
        self.on_charge, self.on_invoice = defaultdict(list), defaultdict(list)
        self.of_payment = defaultdict(list)
        for allocation in rows['allocations']:
            if allocation['id'] in gone:
                continue
            self.of_payment[self.payment_root[allocation['payment_id']]].append(allocation)
            if allocation['milestone_id']:
                self.on_charge[allocation['milestone_id']].append(allocation)
            else:
                self.on_invoice[self.invoice_root[allocation['invoice_id']]].append(allocation)

    # ----- small pieces -----

    def party(self, party_id):
        return {'id': str(party_id), 'name': self.parties[party_id]['name']}

    def direction(self, owes, owed):
        if self.operator is None:
            return 'unknown'
        if owes == self.operator:
            return 'payable'
        if owed == self.operator:
            return 'receivable'
        return 'between_others'

    def latest_payment(self, payment_id):
        return self.payments[self.payment_root[payment_id]][-1]

    def latest_invoice(self, invoice_id):
        return self.invoices[self.invoice_root[invoice_id]][-1]

    def _paid(self, allocations, owed):
        """(paid, currencies, last paid_on) of the allocations on one target."""
        total, currencies, paid_on = Decimal(0), set(), None
        for allocation in allocations:
            payment = self.latest_payment(allocation['payment_id'])
            sign = -1 if payment['from_party_id'] == owed else 1
            total += sign * allocation['amount']
            if allocation['amount']:
                currencies.add(payment['currency'])
            if payment['paid_on'] and (paid_on is None or payment['paid_on'] > paid_on):
                paid_on = payment['paid_on']
        return total, currencies, paid_on

    def allocations(self, allocations):
        """The current allocations on one charge or bill, with the IDs a move
        needs and who paid whom, from the payment."""
        out = []
        for a in allocations:
            payment = self.latest_payment(a['payment_id'])
            out.append({'id': str(a['id']), 'payment_id': str(a['payment_id']),
                        'amount': text(a['amount']), 'paid_on': text(payment['paid_on']),
                        'paid_by': self.parties[payment['from_party_id']]['name'],
                        'paid_to': self.parties[payment['to_party_id']]['name'],
                        'reference': payment['reference'], 'method': payment['method']})
        return out

    def _late(self, open_amount, due_on):
        if open_amount is None or open_amount <= 0 or due_on is None:
            return None
        return max(0, (self.today - due_on).days)

    def _open(self, billed, currency, paid, currencies):
        if billed is None or (currencies and currencies != {currency}):
            return None
        return billed - paid

    # ----- one charge -----

    def current(self, charge_id, kind):
        lines = [line for line in self.lines[charge_id] if line['kind'] == kind]
        replaced = {line['replaces_line_id'] for line in lines}
        return next((line for line in lines if line['id'] not in replaced), None), lines

    def _line(self, line, earlier):
        entry = {key: text(line[key]) for key in (
            'id', 'charge_type', 'quantity', 'rate', 'amount', 'currency', 'home_amount',
            'home_currency', 'invoice_id', 'replaces_line_id', 'reason', 'evidence_id', 'actor',
            'recorded_at')}
        entry['earlier'] = [{key: text(old[key]) for key in (
            'id', 'amount', 'currency', 'reason', 'evidence_id', 'recorded_at')}
            for old in reversed(earlier)]   # newest first
        return entry

    def _changed_since_judged(self, charge_id, judgment):
        """The amount or currency of a kind differs from what it was when judged."""
        if judgment is None:
            return False
        for kind in KINDS:
            now, lines = self.current(charge_id, kind)
            then = [line for line in lines if line['recorded_at'] <= judgment['recorded_at']]
            then = then[-1] if then else None
            if (then and (then['amount'], then['currency'])) != (now and (now['amount'], now['currency'])):
                return True
        return False

    def charge(self, charge_id):
        info, lines = self.charges[charge_id], self.lines[charge_id]
        owes, owed = lines[0]['owes_party_id'], lines[0]['owed_party_id']
        judgment = self.judgments.get(charge_id)
        entry = {'id': str(charge_id), 'title': info['title'],
                 'work': {'kind': info['work_kind'], 'id': str(info['work_id']),
                          'title': info['work_title']},
                 'direction': self.direction(owes, owed),
                 'owes': self.party(owes), 'owed': self.party(owed),
                 'judgment': judgment['status'] if judgment else 'unassessed',
                 'latest_judgment': None if judgment is None else {
                     key: text(judgment[key]) for key in (
                         'id', 'status', 'explanation', 'actor', 'recorded_at', 'occurred_on')}}
        current = {}
        for kind in KINDS:
            line, chain = self.current(charge_id, kind)
            current[kind] = line
            entry[kind] = self._line(line, [old for old in chain if old is not line]) if line else None
        allocations = self.on_charge.get(charge_id, [])
        paid, currencies, paid_on = self._paid(allocations, owed)
        billed = current['invoiced']
        bill = self.latest_invoice(billed['invoice_id']) if billed else None
        if bill:
            held = self.money_on_bill(self.invoice_root[bill['id']])
            if held:
                entry['bill_holds'] = text(held)
            if self._differs(billed, bill):
                entry['parties_differ_from_bill'] = True
        waived = self._waived(charge_id)
        if waived:
            # A waived charge owes 0; money paid on it still counts.
            open_amount = self._open(Decimal(0), (billed or current['expected'] or {}).get(
                'currency'), paid, currencies) if paid or billed else None
        else:
            open_amount = self._open(billed and billed['amount'], billed and billed['currency'],
                                     paid, currencies)
        late = self._late(open_amount, bill and bill['due_on'])
        note = PAID_NOT_BILLED if billed is None and paid > 0 else None
        if waived and paid:
            note = f'waived, {text(paid)} paid'
        elif bill and open_amount is not None and open_amount > 0 and self.money_on_bill(
                self.invoice_root[bill['id']]) > 0:
            bill_open = self.bill_entry(self.invoice_root[bill['id']])['open']
            if bill_open is not None and Decimal(bill_open) <= 0:
                late = None
                note = f"covered by money on bill {bill['number'] or bill['id']}"
        entry.update({
            'paid': text(paid), 'open': text(open_amount),
            'allocations': self.allocations(allocations),
            'invoice_number': bill and bill['number'],
            'issued_on': text(bill and bill['issued_on']), 'due_on': text(bill and bill['due_on']),
            'paid_on': text(paid_on),
            'days_past_due': late,
            'note': note,
            'changed_since_judged': self._changed_since_judged(charge_id, judgment),
            'before_procedure_change': self._before_change(info)})
        return entry

    def _before_change(self, info):
        adoption = self.adoptions.get(info['work_id']) if info['work_kind'] == 'job' else None
        return bool(adoption and adoption['replaced_one']
                    and info['recorded_at'] < adoption['recorded_at'])

    # ----- invoices and payments -----

    def _waived(self, charge_id):
        judgment = self.judgments.get(charge_id)
        return judgment is not None and judgment['status'] == 'failed'

    def money_on_bill(self, root):
        """The money put on a bill as a whole, not on any of its lines."""
        return self._paid(self.on_invoice.get(root, []), self.invoices[root][-1]['from_party_id'])[0]

    @staticmethod
    def _differs(line, bill):
        """A line's parties are not its bill's (owes is the recipient, owed the issuer)."""
        return (line['owes_party_id'], line['owed_party_id']) != (bill['to_party_id'],
                                                                  bill['from_party_id'])

    def counted_on(self, root):
        """(kind, id) of the work item whose cash counts the money on this bill
        as a whole: the item of the bill's first line (current, else the
        first it ever carried), else the first item the bill is linked to."""
        lines = self.billed.get(root) or self.ever_billed.get(root)
        if lines:
            return self.work_of.get(lines[0]['milestone_id'])
        for link in self.links.get(root, []):
            for kind in ('quote', 'booking', 'job'):
                if link[f'{kind}_id']:
                    return kind, link[f'{kind}_id']
        return None

    def _moved_to(self, root, leave_out=None):
        """Number (or id) of the bills now carrying the lines this bill carried,
        leaving out the bill leave_out."""
        out = []
        for charge_id in dict.fromkeys(line['milestone_id'] for line in self.ever_billed[root]):
            line, _ = self.current(charge_id, 'invoiced')
            if line:
                if self.invoice_root[line['invoice_id']] == leave_out:
                    continue
                bill = self.latest_invoice(line['invoice_id'])
                name = bill['number'] or str(bill['id'])
                if name not in out:
                    out.append(name)
        return out

    def bill_entry(self, root):
        """invoice(root), worked out once per read. Callers must not change it."""
        if root not in self._bills:
            self._bills[root] = self.invoice(root)
        return self._bills[root]

    def invoice(self, root):
        versions = self.invoices[root]
        latest, lines = versions[-1], self.billed.get(root, [])
        entry = {key: text(latest[key]) for key in (
            'id', 'number', 'issued_on', 'terms', 'due_on', 'stated_total', 'currency', 'reason',
            'evidence_id', 'actor', 'recorded_at')}
        entry.update({'from': self.party(latest['from_party_id']),
                      'to': self.party(latest['to_party_id']),
                      'direction': self.direction(latest['to_party_id'], latest['from_party_id']),
                      'versions': [str(v['id']) for v in versions],
                      'work': [{'kind': kind, 'id': str(link[f'{kind}_id'])}
                               for link in self.links.get(root, [])
                               for kind in ('quote', 'booking', 'job') if link[f'{kind}_id']],
                      'lines_recorded': len(lines),
                      'same_number_as': self._same_number(root)})
        on_bill = self.on_invoice.get(root, [])
        bill_paid, currencies, paid_on = self._paid(on_bill, latest['from_party_id'])
        entry['allocations'] = self.allocations(on_bill)
        if lines:
            known = [line for line in lines if line['amount'] is not None]
            same = {line['currency'] for line in known} == {latest['currency']}
            total = sum(line['amount'] for line in known) if known else None
            whole = same and len(known) == len(lines)
            entry['lines_total'] = text(total) if same or not known else None
            difference = (latest['stated_total'] - total
                          if whole and latest['stated_total'] is not None else None)
            entry['difference'] = text(difference)
            if difference:
                entry['note'] = f"stated total {text(latest['stated_total'])}, lines {text(total)}"
                moved = self._moved_to(root, root)
                if moved:
                    entry['note'] = f"line moved to {', '.join(moved)}; " + entry['note']
            if any(self._differs(line, latest) for line in lines):
                entry['parties_differ_from_bill'] = True
            # Open: the lines not waived, minus the money on all its lines
            # (a waived line owes 0, but money paid on it still counts),
            # minus the money on the bill as a whole.
            owed = [line for line in lines if not self._waived(line['milestone_id'])]
            on_lines = sum((self._paid(self.on_charge.get(line['milestone_id'], []),
                                       line['owed_party_id'])[0] for line in lines), Decimal(0))
            entry['money_on_bill'] = text(bill_paid)
            entry['paid'] = text(on_lines + bill_paid)
            entry['open'] = (text(sum((line['amount'] for line in owed), Decimal(0))
                                  - on_lines - bill_paid) if whole else None)
            entry['paid_on'] = text(paid_on)
            return entry
        if self.ever_billed.get(root):
            moved = self._moved_to(root)
            entry.update({'note': 'lines now on ' + (', '.join(moved) or 'no bill'),
                          'money_on_bill': text(bill_paid), 'paid': text(bill_paid),
                          'open': None, 'paid_on': text(paid_on), 'days_past_due': None})
            return entry
        open_amount = self._open(latest['stated_total'], latest['currency'], bill_paid, currencies)
        note = TOTAL_MISSING if latest['stated_total'] is None else LINES_MISSING
        entry.update({'note': note, 'paid': text(bill_paid), 'open': text(open_amount),
                      'paid_on': text(paid_on),
                      'days_past_due': self._late(open_amount, latest['due_on'])})
        return entry

    def _same_number(self, root):
        latest = self.invoices[root][-1]
        if latest['number'] is None:
            return []
        return [str(chain[-1]['id']) for other, chain in self.invoices.items() if other != root
                and any(v['number'] == latest['number'] and v['from_party_id'] == latest['from_party_id']
                        and v['to_party_id'] == latest['to_party_id'] for v in chain)]

    def payment(self, root):
        latest = self.payments[root][-1]
        allocations = self.of_payment.get(root, [])
        allocated = sum((a['amount'] for a in allocations), Decimal(0))
        entry = {key: text(latest[key]) for key in (
            'id', 'amount', 'currency', 'home_amount', 'home_currency', 'paid_on', 'reference',
            'method', 'reason', 'evidence_id', 'recorded_at')}
        entry.update({'from': self.party(latest['from_party_id']),
                      'to': self.party(latest['to_party_id']),
                      'versions': [str(v['id']) for v in self.payments[root]],
                      'allocated': text(allocated),
                      'unallocated': text(latest['amount'] - allocated),
                      'allocations': [{'id': str(a['id']), 'amount': text(a['amount']),
                                       'charge_id': text(a['milestone_id']),
                                       'invoice_id': text(a['invoice_id'])} for a in allocations]})
        return entry

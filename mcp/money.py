"""Money: the writes, and the rows the money reads start from.

A charge is a milestone with at least one charge line. A line states one
amount for the charge, expected (agreed) or invoiced (billed). An invoice is
one version of a bill. A payment is money that moved; an allocation puts a
payment, or part of it, on a charge or on an invoice.

Nothing here decides anything. money_book.py works out paid, open and
direction when read; money_read.py shapes the answers.
"""

from datetime import datetime

from psycopg.rows import dict_row

from money_book import Book
from money_read import open_answer, work_answer
from review import owner_columns

_CHARGES = '''
    SELECT m.id, m.title, m.recorded_at,
           CASE WHEN m.quote_id IS NOT NULL THEN 'quote'
                WHEN m.booking_id IS NOT NULL THEN 'booking' ELSE 'job' END AS work_kind,
           coalesce(m.quote_id, m.booking_id, m.job_id) AS work_id,
           coalesce(q.title, b.title, j.title) AS work_title
    FROM spine.milestones m
    LEFT JOIN spine.quotes q ON q.id = m.quote_id
    LEFT JOIN spine.bookings b ON b.id = m.booking_id
    LEFT JOIN spine.jobs j ON j.id = m.job_id
    WHERE m.id IN (SELECT milestone_id FROM spine.charge_lines)
      AND (%(work)s::uuid[] IS NULL OR coalesce(m.quote_id, m.booking_id, m.job_id) = ANY(%(work)s))
    ORDER BY m.recorded_at, m.id'''

_JUDGMENTS = '''
    SELECT DISTINCT ON (j.milestone_id) j.milestone_id, j.id, j.status, j.explanation,
           j.actor, j.recorded_at, j.occurred_on
    FROM spine.judgments j WHERE j.milestone_id = ANY(%(ids)s)
    ORDER BY j.milestone_id, j.position DESC'''

# The latest adoption of each job, and whether it replaced an earlier one.
_ADOPTIONS = '''
    SELECT a.job_id, a.recorded_at, a.previous_adoption_id IS NOT NULL AS replaced_one
    FROM spine.sop_adoptions a
    WHERE a.job_id = ANY(%(ids)s)
      AND NOT EXISTS (SELECT 1 FROM spine.sop_adoptions n WHERE n.previous_adoption_id = a.id)'''


class MoneyLedgerMixin:
    def _money_installed(self):
        """True when spine.charge_lines exists (migration 016)."""
        if not getattr(self, '_money_ready', False):
            self._money_ready = self.connection.execute(
                "SELECT to_regclass('spine.charge_lines') IS NOT NULL").fetchone()[0]
        return self._money_ready

    # ----- writes: each one database function -----

    def record_invoice(self, identifier, number, from_party, to_party, issued_on, terms,
                       due_on, stated_total, currency, replaces, reason, evidence_id, actor):
        return self._create('record_invoice', (
            identifier, number, from_party, to_party, issued_on, terms, due_on, stated_total,
            currency, replaces, reason, evidence_id, actor))

    def link_invoice_work(self, identifier, invoice_id, work_kind, work_id, actor):
        return self._create('link_invoice_work', (
            identifier, invoice_id, *owner_columns(work_kind, work_id), actor))

    def record_charge_line(self, identifier, milestone_id, owes, owed, charge_type, quantity,
                           rate, amount, currency, home_amount, home_currency, kind, invoice_id,
                           replaces, reason, evidence_id, actor):
        return self._create('record_charge_line', (
            identifier, milestone_id, owes, owed, charge_type, quantity, rate, amount, currency,
            home_amount, home_currency, kind, invoice_id, replaces, reason, evidence_id, actor))

    def record_payment(self, identifier, from_party, to_party, amount, currency, home_amount,
                       home_currency, paid_on, reference, method, replaces, reason,
                       evidence_id, actor):
        return self._create('record_payment', (
            identifier, from_party, to_party, amount, currency, home_amount, home_currency,
            paid_on, reference, method, replaces, reason, evidence_id, actor))

    def record_payment_allocation(self, identifier, payment_id, charge_id, invoice_id, amount,
                                  replaces, reason, evidence_id, actor):
        return self._create('record_payment_allocation', (
            identifier, payment_id, charge_id, invoice_id, amount, replaces, reason,
            evidence_id, actor))

    def same_number_invoices(self, invoice_id):
        """Other invoices from the same issuer to the same recipient with the same
        number, outside this invoice's chain. An unknown number matches nothing."""
        return [str(i) for (i,) in self.connection.execute('''
            SELECT o.id FROM spine.invoices i JOIN spine.invoices o
              ON o.from_party_id = i.from_party_id AND o.to_party_id = i.to_party_id
             AND o.number = i.number
            WHERE i.id = %(id)s AND o.id NOT IN (SELECT spine.invoice_chain(%(id)s))
            ORDER BY o.recorded_at, o.id''', {'id': invoice_id}).fetchall()]

    def line_parties_differ_from_bill(self, line_id):
        """True when an invoiced line's parties are not its bill's (owes is
        the recipient, owed the issuer). The ledger saves it; the tool warns."""
        row = self.connection.execute('''
            SELECT l.owes_party_id <> i.to_party_id OR l.owed_party_id <> i.from_party_id
            FROM spine.charge_lines l JOIN spine.invoices i ON i.id = l.invoice_id
            WHERE l.id = %s''', (line_id,)).fetchone()
        return bool(row and row[0])

    def lines_differing_from_bill(self, invoice_id):
        """IDs of the current lines on this bill's chain whose parties are not
        this bill's, such as after a reissue to other parties."""
        return [str(i) for (i,) in self.connection.execute('''
            SELECT l.id FROM spine.charge_lines l, spine.invoices i
            WHERE i.id = %(id)s AND l.invoice_id IN (SELECT spine.invoice_chain(%(id)s))
              AND NOT EXISTS (SELECT 1 FROM spine.charge_lines n WHERE n.replaces_line_id = l.id)
              AND (l.owes_party_id <> i.to_party_id OR l.owed_party_id <> i.from_party_id)
            ORDER BY l.recorded_at, l.id''', {'id': invoice_id}).fetchall()]

    def invoice_ids(self, identifiers):
        """Those of these IDs that name an invoice, not a milestone."""
        if not identifiers or not self._money_installed():
            return []
        return [str(i) for (i,) in self.connection.execute(
            '''SELECT id FROM spine.invoices WHERE id = ANY(%(ids)s)
                 AND id NOT IN (SELECT id FROM spine.milestones WHERE id = ANY(%(ids)s))''',
            {'ids': list(identifiers)}).fetchall()]

    # ----- reads -----

    def charge_milestone_ids(self, work_id):
        """IDs of the milestones of one work item that have a charge line."""
        if not self._money_installed():
            return set()
        return {str(m) for (m,) in self.connection.execute('''
            SELECT DISTINCT l.milestone_id FROM spine.charge_lines l
            JOIN spine.milestones m ON m.id = l.milestone_id
            WHERE coalesce(m.quote_id, m.booking_id, m.job_id) = %s''', (work_id,)).fetchall()}

    def _book(self, work_ids=None):
        """Load the rows of the charges on these work items (every charge when
        None), with every invoice, payment and allocation, into a Book."""
        rows = {}

        def run(name, query, params=None):
            with self.connection.cursor(row_factory=dict_row) as cursor:
                rows[name] = cursor.execute(query, params or {}).fetchall()

        run('charges', _CHARGES, {'work': work_ids})
        ids = [c['id'] for c in rows['charges']]
        run('adoptions', _ADOPTIONS, {'ids': [c['work_id'] for c in rows['charges']
                                              if c['work_kind'] == 'job']})
        run('parties', 'SELECT id, name, is_operator FROM spine.parties')
        run('invoices', 'SELECT * FROM spine.invoices ORDER BY recorded_at, id')
        run('links', 'SELECT * FROM spine.invoice_work_links ORDER BY recorded_at, id')
        if self.connection.execute("SELECT to_regclass('spine.payments') IS NOT NULL").fetchone()[0]:
            run('payments', 'SELECT * FROM spine.payments ORDER BY recorded_at, id')
            run('allocations', 'SELECT * FROM spine.payment_allocations ORDER BY recorded_at, id')
        else:   # before migration 017
            rows['payments'], rows['allocations'] = [], []
        # The lines of these charges, and every line on any invoice, so an
        # invoice's lines can be compared with its stated total across all work.
        run('lines', '''SELECT * FROM spine.charge_lines
                        WHERE milestone_id = ANY(%(ids)s) OR invoice_id IS NOT NULL
                        ORDER BY recorded_at, id''', {'ids': ids})
        # The work item of every charge with a line on a bill, so a bill's
        # money as a whole is counted in cash on one item, named in every read.
        run('line_work', '''
            SELECT m.id, CASE WHEN m.quote_id IS NOT NULL THEN 'quote'
                              WHEN m.booking_id IS NOT NULL THEN 'booking' ELSE 'job' END AS work_kind,
                   coalesce(m.quote_id, m.booking_id, m.job_id) AS work_id
            FROM spine.milestones m
            WHERE m.id IN (SELECT milestone_id FROM spine.charge_lines WHERE invoice_id IS NOT NULL)''')
        # Judgments of these charges and of every charge on a bill, so a bill's
        # open leaves out its waived lines whichever work item it is read from.
        run('judgments', _JUDGMENTS, {'ids': ids + [w['id'] for w in rows['line_work']]})
        moment = datetime.now().astimezone()
        return Book(rows, moment.date()), moment.isoformat(timespec='seconds')

    def work_money(self, work_id):
        """The money of the chain one quote, booking or job is in. None for an unknown ID."""
        chain = self.work_chain(work_id)
        if chain is None:
            return None
        book, read_at = self._book([item_id for _, item_id in chain])
        titles = dict(self.connection.execute('''
            SELECT id, title FROM spine.quotes WHERE id = ANY(%(ids)s)
            UNION ALL SELECT id, title FROM spine.bookings WHERE id = ANY(%(ids)s)
            UNION ALL SELECT id, title FROM spine.jobs WHERE id = ANY(%(ids)s)''',
            {'ids': [item_id for _, item_id in chain]}).fetchall())
        return work_answer(book, read_at, work_id, chain, titles)

    def money_open(self, party_id=None):
        """Everything open across the ledger, or for one party. None for an unknown party."""
        if party_id is not None and self.connection.execute(
                'SELECT 1 FROM spine.parties WHERE id = %s', (party_id,)).fetchone() is None:
            return None
        book, read_at = self._book()
        return open_answer(book, read_at, party_id)

    def target_figures(self, charge_ids, invoice_ids):
        """Paid and open on the charges and invoices one payment call touched."""
        book, _ = self._book()
        out = []
        for charge_id in charge_ids:
            charge = book.charge(charge_id)
            out.append({'charge_id': str(charge_id), **{
                key: charge[key] for key in ('paid', 'open', 'note')}})
        for invoice_id in invoice_ids:
            invoice = book.invoice(book.invoice_root[invoice_id])
            out.append({'invoice_id': str(invoice_id), **{
                key: invoice.get(key) for key in ('paid', 'open', 'note')}})
        return book, out

    def linked_invoices(self, work_id):
        """For the case brief: each invoice chain linked to one work item, latest version."""
        if not self._money_installed():
            return []
        book, _ = self._book([work_id])
        roots = {book.invoice_root[link['invoice_id']] for links in book.links.values()
                 for link in links if work_id in (link['quote_id'], link['booking_id'],
                                                   link['job_id'])}
        return [{key: entry.get(key) for key in (
            'id', 'number', 'from', 'to', 'issued_on', 'due_on', 'stated_total', 'currency',
            'lines_recorded', 'note')}
            for entry in (book.invoice(root) for root in sorted(
                roots, key=lambda r: (book.invoices[r][0]['recorded_at'], r)))]

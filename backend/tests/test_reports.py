"""Reports, home, analytics, reconciliation and journal on a small realistic month."""

import unittest

from helpers import LedgerTestCase

from services import (
    adjustments_service, analytics_service, assets_service, home_service, journal_service, ledger_service, meta_service,
    recon_service, reports, settings_service, shifts_service, transactions_service as tx,
)
from services.reports import customers
from utils.dates import add_days, today
from utils.errors import DomainError

T = today()
D1, D2 = add_days(T, -3), add_days(T, -2)


class Month(LedgerTestCase):
    def setUp(self):
        super().setUp()
        settings_service.update(self.conn, {"costingStart": add_days(T, -20)})
        o = self.owner
        tx.save(self.conn, "in", {"date": D1, "ref": "F1", "amount": 2000, "cur": "SAR", "rate": 140, "purpose": "owner"}, o)
        tx.save(self.conn, "out", {"date": D1, "ref": "O1", "purpose": "rm", "amount": 750, "cur": "SAR", "rate": 140, "qty": 100 * 25 / 1}, o)
        tx.save(self.conn, "out", {"date": D1, "ref": "O2", "purpose": "cartons", "amount": 110000, "cur": "YER", "rate": 140, "qty": 200}, o)
        tx.save(self.conn, "out", {"date": D1, "ref": "O3", "purpose": "power", "amount": 2000000, "cur": "YER", "rate": 140}, o)
        tx.save(self.conn, "exp", {"date": D2, "paidFrom": "3101", "lines": [
            {"desc": "عمال", "cat": "wages", "shift": "صباحية", "amount": 40000},
            {"desc": "شاي", "cat": "admin", "shift": "عام", "amount": 3000}]}, o)
        sh = shifts_service.submit(self.conn, {"date": D2, "shift": "صباحية", "meterStart": 0, "meterEnd": 300, "bags": 12,
                                               "cartons": 29, "downMin": 30, "downReason": "عطل ماكينة"}, self.sup)
        shifts_service.approve(self.conn, sh["id"], o)
        for i, qty in enumerate([10, 8]):
            tx.save(self.conn, "sale", {"date": D2, "ref": f"S{i}", "party": "سنوان بلاست", "qty": qty, "price": 155, "rate": 140}, o)
        tx.save(self.conn, "in", {"date": T, "ref": "T1", "amount": 1550, "cur": "SAR", "rate": 140, "purpose": "customer",
                                  "party": "سنوان بلاست"}, o)
        assets_service.add(self.conn, {"name": "كاميرات", "date": add_days(T, -10), "amount": 74500, "cur": "YER", "life": 3}, o)

    def test_every_report_runs(self):
        for kind in reports.REPORTS:
            data = reports.run(self.conn, kind, {})
            self.assertEqual(data["kind"], kind)

    def test_trial_balance_is_balanced(self):
        tb = reports.run(self.conn, "tb", {})
        self.assertTrue(tb["balanced"])

    def test_claim_fifo(self):
        c = reports.run(self.conn, "claim", {"party": "سنوان بلاست"})
        self.assertEqual(c["totalInvoiced"], 18 * 155)
        self.assertEqual(c["totalPaid"], 1550)
        self.assertEqual(c["due"], 8 * 155)
        self.assertEqual([i["ref"] for i in c["open"]], ["S1"])

    def test_cogs_follows_shift_cost(self):
        fg = ledger_service.bal(self.conn, "1305")
        self.assertEqual(fg["q"], 11)
        self.assertTrue(recon_service.checks(self.conn)[0]["level"] == "good")

    def test_income_statement_includes_all_expense_accounts(self):
        settings_service.update(self.conn, {"nisabYer": 1})
        is_ = reports.run(self.conn, "is", {"frm": add_days(T, -30)})
        self.assertIn("6101", [e["account"] for e in is_["expenses"]])
        self.assertAlmostEqual(is_["gross"], is_["sales"] - is_["cogs"], places=2)

    def test_home_analytics_journal_meta(self):
        h = home_service.overview(self.conn)
        self.assertEqual(h["balances"]["sar"], 2000 - 750 + 1550)
        a = analytics_service.overview(self.conn, "week")
        self.assertEqual(len(a["tiles"]), 6)
        j = journal_service.search(self.conn, {"party": "سنوان بلاست"})
        self.assertGreater(j["total"], 0)
        self.assertNotIn("accounts", meta_service.context(self.conn, self.sup))
        self.assertIn("move", meta_service.context(self.conn, self.entry)["tabs"])

    def test_statement_matching(self):
        st = recon_service.statement(self.conn, "1102")
        self.assertEqual(st["book"], 2800)
        ids = [x["lineId"] for x in st["lines"]]
        st = recon_service.save(self.conn, "1102", ids[:1], T, 2800, self.owner)
        self.assertEqual(len(st["history"]), 1)

    def test_adjustment_postings(self):
        settings_service.update(self.conn, {"fx": 145})
        adjustments_service.revalue(self.conn, self.owner)
        self.assertEqual(customers.currency_position(self.conn)["totalDiff"], 0)
        with self.assertRaises(DomainError):
            adjustments_service.close_fx_difference(self.conn, "سنوان بلاست", self.owner)
        settings_service.update(self.conn, {"nisabYer": 1})
        with self.assertRaises(DomainError):  # the YER overdraft outweighs the zakatable assets
            adjustments_service.post_zakat(self.conn, T, self.owner)
        tx.save(self.conn, "in", {"date": T, "ref": "F2", "amount": 5_000_000, "cur": "YER", "rate": 140, "purpose": "owner"}, self.owner)
        adjustments_service.post_zakat(self.conn, T, self.owner)
        self.assertGreater(ledger_service.bal(self.conn, "6105")["y"], 0)


if __name__ == "__main__":
    unittest.main()

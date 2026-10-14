"""Posting engine rules (spec §1) and the transaction forms (spec §5)."""

import unittest

from helpers import LedgerTestCase

from repositories import entries_repo
from services import ledger_service, settings_service, transactions_service as tx
from utils.dates import today
from utils.errors import Conflict, DomainError, Forbidden

D = "2026-10-15"


class PostingRules(LedgerTestCase):
    def test_unbalanced_entry_is_rejected(self):
        with self.assertRaisesRegex(DomainError, "غير متوازن"):
            ledger_service.post(self.conn, {"date": D, "memo": "x", "src": "manual",
                                            "lines": [{"a": "1101", "d": 100}, {"a": "3101", "c": 99}]}, self.owner)
        self.assertEqual(entries_repo.next_no(self.conn), 1)

    def test_numbers_are_sequential(self):
        nos = [ledger_service.post(self.conn, {"date": D, "memo": "x", "src": "manual",
                                               "lines": [{"a": "1101", "d": 10}, {"a": "3101", "c": 10}]}, self.owner)["no"]
               for _ in range(3)]
        self.assertEqual(nos, [1, 2, 3])

    def test_failed_batch_leaves_no_trace(self):
        good = {"date": D, "memo": "ok", "src": "manual", "lines": [{"a": "1101", "d": 10}, {"a": "3101", "c": 10}]}
        bad = {"date": D, "memo": "bad", "src": "manual", "lines": [{"a": "9999", "d": 10}, {"a": "3101", "c": 10}]}
        with self.assertRaises(DomainError):
            ledger_service.post_many(self.conn, [good, bad], self.owner)
        self.assertEqual(entries_repo.next_no(self.conn), 1)

    def test_period_lock_blocks_posting_and_reversal(self):
        r = ledger_service.post(self.conn, {"date": "2026-10-10", "memo": "x", "src": "manual",
                                            "lines": [{"a": "1101", "d": 10}, {"a": "3101", "c": 10}]}, self.owner)
        settings_service.update(self.conn, {"lockDate": "2026-10-12"})
        with self.assertRaisesRegex(DomainError, "مقفلة"):
            ledger_service.post(self.conn, {"date": "2026-10-12", "memo": "x", "src": "manual",
                                            "lines": [{"a": "1101", "d": 10}, {"a": "3101", "c": 10}]}, self.owner)
        with self.assertRaisesRegex(DomainError, "مقفلة"):
            ledger_service.reverse(self.conn, r["id"], self.owner)

    def test_reversal_mirrors_and_nets_to_zero(self):
        r = ledger_service.post(self.conn, {"date": D, "memo": "x", "src": "manual",
                                            "lines": [{"a": "1101", "d": 250}, {"a": "3101", "c": 250}]}, self.owner)
        rev = ledger_service.reverse(self.conn, r["id"], self.owner)
        e = entries_repo.get(self.conn, r["id"])
        self.assertEqual(e["status"], "reversed")
        mirror = entries_repo.get(self.conn, rev["id"])
        self.assertEqual(mirror["date"], today())
        self.assertEqual(mirror["lines"][0]["c"], 250)
        self.assertEqual(ledger_service.bal(self.conn, "1101")["y"], 0)
        with self.assertRaises(Conflict):
            ledger_service.reverse(self.conn, r["id"], self.owner)

    def test_sar_account_line_must_carry_sar(self):
        with self.assertRaisesRegex(DomainError, "بالريال السعودي"):
            ledger_service.post(self.conn, {"date": D, "memo": "x", "src": "manual",
                                            "lines": [{"a": "1102", "d": 140}, {"a": "3101", "c": 140}]}, self.owner)


class Forms(LedgerTestCase):
    def fund_sar(self, sar=1000, rate=140):
        ledger_service.post(self.conn, {"date": "2026-10-05", "memo": "تمويل", "src": "manual", "lines": [
            {"a": "1102", "d": sar * rate, "cur": "SAR", "fc": sar}, {"a": "3101", "c": sar * rate, "party": "طه عادل"}]}, self.owner)

    def test_sale_posts_receivable_in_sar(self):
        res = tx.save(self.conn, "sale", {"date": "2026-10-13", "ref": "INV1", "party": "سنوان بلاست", "qty": 10,
                                          "price": 155, "rate": 140}, self.owner)
        self.assertEqual(len(res["posted"]), 1)  # before costingStart: no COGS
        b = ledger_service.pbal(self.conn, "1201", "سنوان بلاست")
        self.assertEqual((b["y"], b["fc"]), (217000, 1550))

    def test_duplicate_invoice_rejected(self):
        form = {"date": D, "ref": "INV9", "party": "سنوان بلاست", "qty": 1, "price": 155, "rate": 140}
        tx.save(self.conn, "sale", form, self.owner)
        with self.assertRaises(DomainError):
            tx.save(self.conn, "sale", form, self.owner)

    def test_sale_after_costing_start_posts_cogs_from_stock(self):
        ledger_service.post(self.conn, {"date": D, "memo": "stock", "src": "manual", "lines": [
            {"a": "1305", "d": 15000, "qty": 10}, {"a": "3101", "c": 15000, "party": "طه عادل"}]}, self.owner)
        res = tx.save(self.conn, "sale", {"date": D, "ref": "INV2", "party": "سنوان بلاست", "qty": 4, "price": 155, "rate": 140}, self.owner)
        self.assertEqual(len(res["posted"]), 2)
        self.assertEqual(ledger_service.bal(self.conn, "5101")["y"], 6000)
        self.assertEqual(ledger_service.bal(self.conn, "1305")["q"], 6)

    def test_credit_limit(self):
        settings_service.set_credit_limits(self.conn, {"محمد يحيى": 1000})
        form = {"date": D, "ref": "L1", "party": "محمد يحيى", "qty": 7, "price": 155, "rate": 140}
        with self.assertRaisesRegex(DomainError, "سقف"):
            tx.save(self.conn, "sale", form, self.entry)
        with self.assertRaisesRegex(DomainError, "اطلب موافقة المالك"):
            tx.save(self.conn, "sale", {**form, "overLimit": True}, self.entry)
        tx.save(self.conn, "sale", {**form, "overLimit": True}, self.owner)

    def test_customer_yer_payment_books_fx_difference(self):
        """The real case: a YER transfer converted at 138.55 instead of 140 (§5.2)."""
        tx.save(self.conn, "sale", {"date": "2026-10-10", "ref": "I1", "party": "سنوان بلاست", "qty": 17.4,
                                    "price": 155, "rate": 140}, self.owner)
        sar = 2697
        res = tx.save(self.conn, "in", {"date": "2026-10-11", "ref": "T1", "sender": "سنوان", "amount": round(sar * 138.55, 2),
                                        "cur": "YER", "rate": 140, "via": "exch", "purpose": "customer",
                                        "party": "سنوان بلاست", "sar": sar}, self.owner)
        e = entries_repo.get(self.conn, res["posted"][0]["id"])
        fx_line = [l for l in e["lines"] if l["a"] == "6103"][0]
        self.assertAlmostEqual(fx_line["d"], round(sar * 1.45, 2), places=2)
        b = ledger_service.pbal(self.conn, "1201", "سنوان بلاست")
        self.assertAlmostEqual(b["fc"], 0, places=2)

    def test_outgoing_purchase_needs_quantity(self):
        with self.assertRaisesRegex(DomainError, "الكمية"):
            tx.save(self.conn, "out", {"date": D, "purpose": "rm", "amount": 100000, "cur": "YER", "rate": 140}, self.owner)
        tx.save(self.conn, "out", {"date": D, "ref": "O1", "purpose": "rm", "amount": 1000, "cur": "SAR", "rate": 140,
                                   "qty": 125, "fee": 500}, self.owner)
        self.assertEqual(ledger_service.bal(self.conn, "1301")["q"], 125)
        self.assertEqual(ledger_service.bal(self.conn, "1102")["fc"], -1000)
        self.assertEqual(ledger_service.bal(self.conn, "1103")["y"], -500)

    def test_expenses_with_advance_deduction(self):
        res = tx.save(self.conn, "exp", {"date": D, "paidFrom": "1104", "party": "أحمد", "lines": [
            {"desc": "عمال", "cat": "wages", "shift": "صباحية", "amount": 30000},
            {"desc": "علي", "cat": "advrep", "shift": "عام", "amount": 5000}]}, self.owner)
        e = entries_repo.get(self.conn, res["posted"][0]["id"])
        self.assertEqual([(l["a"], l["d"], l["c"]) for l in e["lines"]],
                         [("5201", 30000, 0), ("1106", 0, 5000), ("1104", 0, 25000)])

    def test_currency_exchange_uses_book_rate(self):
        self.fund_sar(1000, 140)
        res = tx.save(self.conn, "fx", {"date": D, "amount": 500, "rate": 142}, self.owner)
        e = entries_repo.get(self.conn, res["posted"][0]["id"])
        self.assertEqual([(l["a"], l["d"], l["c"]) for l in e["lines"]],
                         [("1103", 71000, 0), ("1102", 0, 70000), ("6103", 0, 1000)])
        with self.assertRaisesRegex(DomainError, "أقل من المبلغ"):
            tx.save(self.conn, "fx", {"date": D, "amount": 600, "rate": 142}, self.owner)

    def test_balance_adjustment_and_refusal_when_equal(self):
        self.fund_sar(100, 140)
        tx.save(self.conn, "adj", {"date": D, "account": "1102", "actual": 90, "counter": "3101"}, self.owner)
        self.assertEqual(ledger_service.bal(self.conn, "1102")["fc"], 90)
        with self.assertRaisesRegex(DomainError, "مطابق"):
            tx.save(self.conn, "adj", {"date": D, "account": "1102", "actual": 90, "counter": "3101"}, self.owner)

    def test_stock_count_values_gain_at_standard(self):
        tx.save(self.conn, "count", {"date": D, "rm": 100}, self.owner)
        b = ledger_service.bal(self.conn, "1301")
        self.assertEqual(b["q"], 100)
        self.assertEqual(b["y"], 100 * 7500 / 1000 * 140)

    def test_manual_entry_is_owner_only(self):
        form = {"date": D, "memo": "m", "lines": [{"a": "1101", "d": 5}, {"a": "3101", "c": 5}]}
        with self.assertRaises(Forbidden):
            tx.save(self.conn, "manual", form, self.entry)
        tx.save(self.conn, "manual", form, self.owner)

    def test_entry_user_cannot_use_owner_forms(self):
        with self.assertRaises(Forbidden):
            tx.preview(self.conn, "fx", {"date": D, "amount": 1, "rate": 140}, self.entry)


if __name__ == "__main__":
    unittest.main()

"""Dual control (§6), advances (§6.1), shifts (§7) and assets (§8)."""

import unittest

from helpers import LedgerTestCase

from repositories import entries_repo, shifts_repo
from services import (
    assets_service, ledger_service, requests_service, settings_service, shifts_service, transactions_service as tx,
)
from utils.errors import Conflict, DomainError, Forbidden

D = "2026-10-15"
SHIFT = {"date": D, "shift": "صباحية", "meterStart": 1000, "meterEnd": 1300, "bags": 12, "cartons": 29, "scrapKg": 7}


class DualControl(LedgerTestCase):
    def setUp(self):
        super().setUp()
        settings_service.update(self.conn, {"dualControl": True})

    def out_form(self, ref="P1"):
        return {"date": D, "ref": ref, "purpose": "tools", "amount": 20000, "cur": "YER", "rate": 140}

    def test_entry_user_payment_becomes_request_and_owner_approves(self):
        res = tx.save(self.conn, "out", self.out_form(), self.entry)
        self.assertEqual(res["posted"], [])
        req = res["request"]
        self.assertEqual(ledger_service.bal(self.conn, "5203")["y"], 0)
        with self.assertRaises(Forbidden):
            requests_service.approve(self.conn, req["id"], self.entry)
        out = requests_service.approve(self.conn, req["id"], self.owner)
        e = entries_repo.get(self.conn, out["posted"][0]["id"])
        self.assertEqual((e["created_by"], e["approved_by"]), (self.entry["id"], self.owner["id"]))
        self.assertEqual(ledger_service.bal(self.conn, "5203")["y"], 20000)
        with self.assertRaises(Conflict):
            requests_service.approve(self.conn, req["id"], self.owner)

    def test_owner_posts_directly_until_a_partner_approver_exists(self):
        self.assertEqual(tx.save(self.conn, "out", self.out_form("P2"), self.owner)["request"], None)
        partner = self.make_approver(self.reviewer)
        res = tx.save(self.conn, "out", self.out_form("P3"), self.owner)
        self.assertIsNotNone(res["request"])
        with self.assertRaises(Forbidden):
            requests_service.approve(self.conn, res["request"]["id"], self.owner)
        requests_service.approve(self.conn, res["request"]["id"], partner)

    def test_withdraw_and_reject(self):
        r1 = tx.save(self.conn, "out", self.out_form("W1"), self.entry)["request"]
        requests_service.withdraw(self.conn, r1["id"], self.entry)
        r2 = tx.save(self.conn, "out", self.out_form("W2"), self.entry)["request"]
        requests_service.reject(self.conn, r2["id"], self.owner)
        statuses = {r["id"]: r["status"] for r in requests_service.list_for(self.conn, self.entry)}
        self.assertEqual(statuses, {r1["id"]: "withdrawn", r2["id"]: "rejected"})

    def test_sales_never_need_approval(self):
        res = tx.save(self.conn, "sale", {"date": D, "ref": "S1", "party": "سنوان بلاست", "qty": 1, "price": 155, "rate": 140}, self.entry)
        self.assertTrue(res["posted"])


class Advances(LedgerTestCase):
    def test_supervisor_requests_owner_pays_from_custody(self):
        adv = requests_service.create_advance(self.conn, {"employee": "سالم", "amount": 10000, "installments": 2}, self.sup)
        self.assertNotIn("balance", requests_service.list_advances(self.conn, self.sup)[0])
        with self.assertRaises(Forbidden):
            requests_service.approve_advance(self.conn, adv["id"], "1101", "", self.sup)
        requests_service.approve_advance(self.conn, adv["id"], "1104", "أحمد", self.owner)
        self.assertEqual(ledger_service.pbal(self.conn, "1106", "سالم")["y"], 10000)
        self.assertEqual(ledger_service.pbal(self.conn, "1104", "أحمد")["y"], -10000)


class Shifts(LedgerTestCase):
    def test_cost_at_standard_prices(self):
        sh = shifts_service.submit(self.conn, SHIFT, self.sup)
        self.assertNotIn("cost", sh)
        c = shifts_service.shift_cost(self.conn, shifts_repo.get(self.conn, sh["id"]))
        self.assertEqual(c["rmCost"], 315000)            # 300 kg × 7.5 SAR × 140
        self.assertEqual(c["pigKg"], 0.36)              # 12 bags × 30 g
        self.assertEqual(c["pigCost"], 9800)            # 0.36 kg × 350 × 140 / 1.8
        self.assertEqual(c["ctCost"], 15950)            # 29 × 550
        self.assertEqual(c["kwh"], 456.84)              # 300 + 26.14 × 0.5 × 12
        self.assertEqual(c["elec"], 82231.2)
        self.assertEqual(c["total"], 422981.2)

    def test_slot_is_unique_and_meter_validated(self):
        shifts_service.submit(self.conn, SHIFT, self.sup)
        with self.assertRaises(Conflict):
            shifts_service.submit(self.conn, SHIFT, self.sup)
        with self.assertRaisesRegex(DomainError, "أكبر من قبل"):
            shifts_service.submit(self.conn, {**SHIFT, "shift": "مسائية", "meterEnd": 900}, self.sup)

    def test_approval_absorbs_labor_and_reversal_reopens(self):
        tx.save(self.conn, "exp", {"date": D, "paidFrom": "3101", "lines": [
            {"desc": "عمال", "cat": "wages", "shift": "صباحية", "amount": 40000}]}, self.owner)
        sh = shifts_service.submit(self.conn, SHIFT, self.sup)
        res = shifts_service.approve(self.conn, sh["id"], self.owner)
        self.assertEqual(ledger_service.bal(self.conn, "5201")["y"], 0)
        self.assertEqual(ledger_service.bal(self.conn, "1305")["y"], 422981.2 + 40000)
        self.assertEqual(ledger_service.bal(self.conn, "1305")["q"], 29)
        # wages recorded after approval are moved into the finished caps too
        tx.save(self.conn, "exp", {"date": D, "paidFrom": "3101", "lines": [
            {"desc": "إعاشة", "cat": "meals", "shift": "صباحية", "amount": 5000}]}, self.owner)
        self.assertEqual(ledger_service.bal(self.conn, "5201")["y"], 0)
        ledger_service.reverse(self.conn, res["id"], self.owner)
        self.assertEqual(shifts_repo.get(self.conn, sh["id"])["status"], "pending")

    def test_supervisor_sees_only_own_shifts_without_money(self):
        shifts_service.submit(self.conn, SHIFT, self.owner)
        shifts_service.submit(self.conn, {**SHIFT, "shift": "مسائية", "meterStart": 1300, "meterEnd": 1600}, self.sup)
        mine = shifts_service.list_for(self.conn, self.sup)
        self.assertEqual(len(mine), 1)
        self.assertNotIn("cost", mine[0])
        with self.assertRaises(Forbidden):
            shifts_service.list_for(self.conn, self.entry)


class Assets(LedgerTestCase):
    def test_add_priced_asset_and_depreciate(self):
        a = assets_service.add(self.conn, {"name": "قالب", "date": "2026-10-01", "amount": 100000, "cur": "USD",
                                           "life": 12, "fund": "3101"}, self.owner)
        self.assertEqual(a["cost"], 52_500_000)
        res = assets_service.post_depreciation(self.conn, "2026-10-10", self.owner)
        daily = 52_500_000 / (12 * 365)
        self.assertAlmostEqual(-ledger_service.bal(self.conn, "1502")["y"], round(daily * 10, 2), places=2)
        with self.assertRaises(DomainError):
            assets_service.post_depreciation(self.conn, "2026-10-10", self.owner)
        ledger_service.reverse(self.conn, res["id"], self.owner)
        self.assertEqual(assets_service.overview(self.conn)["assets"][0]["postedTo"], "2026-09-30")

    def test_unpriced_asset_gets_price_later(self):
        a = assets_service.add(self.conn, {"name": "ماكينة", "date": "2026-10-01", "amount": 0, "life": 10}, self.owner)
        self.assertFalse(assets_service.overview(self.conn)["assets"][0]["priced"])
        assets_service.set_price(self.conn, a["id"], {"amount": 20000, "cur": "USD", "fund": "3101"}, self.owner)
        self.assertEqual(ledger_service.bal(self.conn, "1501")["y"], 20000 * 3.75 * 140)


if __name__ == "__main__":
    unittest.main()

"""Call each route function directly with a real connection and user.

This checks the glue between request schemas, routes and services without an HTTP
server. Requires FastAPI to be importable.
"""

import inspect
import unittest

from helpers import LedgerTestCase

from api import approvals, books, production, settings as settings_api, transactions
from schemas import requests as rq
from utils.dates import add_days, today
from utils.errors import Forbidden

T = today()


class Glue(LedgerTestCase):
    def call(self, fn, *args, user=None, **kwargs):
        """Route functions take the user as `user` or `_`; pass both styles."""
        params = inspect.signature(fn).parameters
        if "user" in params:
            kwargs["user"] = user or self.owner
        if "_" in params:
            kwargs["_"] = user or self.owner
        return fn(*args, conn=self.conn, **kwargs)

    def test_forms_through_routes(self):
        res = self.call(transactions.save, "in", {"date": T, "ref": "A1", "amount": 1000, "cur": "SAR", "rate": 140,
                                                  "purpose": "owner"})
        self.assertEqual(len(res["posted"]), 1)
        prev = self.call(transactions.preview, "sale", {"date": T, "party": "سنوان بلاست", "qty": 2, "price": 155, "rate": 140})
        self.assertEqual(prev["entries"][0]["lines"][0]["a"], "1201")
        res = self.call(transactions.save, "exp", {"date": T, "paidFrom": "3101", "lines": [
            {"desc": "x", "cat": "tools", "shift": "عام", "cc": "", "amount": 500}]})
        self.assertEqual(len(res["posted"]), 1)

    def test_shift_and_asset_routes(self):
        sh = self.call(production.submit_shift, rq.ShiftForm(date=T, shift="صباحية", meterStart=1, meterEnd=200, bags=12, cartons=29),
                       user=self.sup)
        self.call(production.approve_shift, sh["id"])
        self.call(production.add_asset, rq.AssetCreate(name="لوحة", date=add_days(T, -5), amount=0, life=5))
        self.assertEqual(len(self.call(production.assets)["assets"]), 1)

    def test_read_routes(self):
        for kind in ("tb", "is", "claim", "cash", "budget", "party", "ledger"):
            self.call(books.report, kind, frm=None, to=None, party=None, account=None, cur="", month=None, horizon=None, cartons=None)
        self.call(books.home)
        self.call(books.analytics, period="month")
        self.call(books.journal, frm="", to="", src="", party="", account="", cur="", q="", limit=10, offset=0)
        self.call(books.checks)
        self.call(books.statement, key="1103")
        self.call(settings_api.meta)
        self.call(approvals.list_requests, user=self.entry)
        self.call(approvals.create_advance, rq.AdvanceForm(employee="سالم", amount=1000), user=self.sup)

    def test_reviewer_cannot_post(self):
        with self.assertRaises(Forbidden):
            self.call(transactions.save, "sale", {"date": T, "party": "سنوان بلاست", "qty": 1, "price": 155, "rate": 140},
                      user=self.reviewer)


if __name__ == "__main__":
    unittest.main()

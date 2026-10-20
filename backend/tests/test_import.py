"""One-time prototype import (spec §17, IMPORT_SPEC.md).

The committed fixture is synthetic: the real export holds the factory's customers and balances and
the repository is public. To check a real export file locally:

    JOAN_IMPORT_FILE=/path/to/goaan-export.json python -m unittest test_import
"""

import copy
import json
import os
import unittest

from helpers import LedgerTestCase

from database import fetch_one
from repositories import entries_repo, shifts_repo
from services import import_service, ledger_service, reports, transactions_service as tx
from utils.errors import Conflict, Unprocessable

OWNER = "طه عادل"
C = "عميل تجريبي"


def payload() -> dict:
    return {
        "exportedAt": "2026-10-20",
        "settings": {"fx": 140, "cartonNetKg": 10, "sarOverdraft": True, "someFutureKey": "kept",
                     "parties": [{"name": C, "type": "customer"}, {"name": OWNER, "type": "owner"}]},
        "assets": [{"id": "mould", "name": "قالب", "date": "2026-10-01", "cost": 52500000, "amount": 100000, "cur": "USD",
                    "life": 12, "salvage": 0, "postedTo": "2026-09-30", "cc": "prod"},
                   {"id": "machine", "name": "ماكينة", "date": "2026-10-01", "cost": 0, "life": 10, "salvage": 0}],
        "entries": [
            {"id": "e0001", "no": 1, "date": "2026-10-03", "src": "manual", "ref": "", "party": OWNER, "memo": "تمويل",
             "status": "posted", "by": "seed", "at": "2026-10-14T08:30:00+03:00", "meta": {},
             "lines": [{"a": "1102", "d": 140000, "c": 0, "cur": "SAR", "fc": 1000},
                       {"a": "3101", "d": 0, "c": 140000, "party": OWNER}]},
            {"id": "e0002", "no": 2, "date": "2026-10-04", "src": "buy", "ref": "B1", "party": "", "memo": "مواد",
             "status": "posted", "by": "owner", "at": "2026-10-14T09:00:00+03:00", "meta": {"purpose": "rm"},
             "lines": [{"a": "1301", "d": 70000, "c": 0, "qty": 100},
                       {"a": "1102", "d": 0, "c": 70000, "cur": "SAR", "fc": 500}]},
            {"id": "e0003", "no": 3, "date": "2026-10-05", "src": "sale", "ref": "2224", "party": C, "memo": "بيع",
             "status": "posted", "by": "seed", "at": "2026-10-14T09:00:00+03:00", "meta": {"cartons": 1, "noCogs": True},
             "lines": [{"a": "1201", "d": 21700, "c": 0, "cur": "SAR", "fc": 155, "party": C},
                       {"a": "4101", "d": 0, "c": 21700}]},
            {"id": "e0004-x", "no": 4, "date": "2026-10-06", "src": "manual", "ref": "", "party": "", "memo": "خطأ",
             "status": "reversed", "by": "claude", "at": "2026-10-14T09:00:00+03:00", "meta": {},
             "lines": [{"a": "6101", "d": 5000, "c": 0}, {"a": "3101", "d": 0, "c": 5000, "party": OWNER}]},
            {"id": "e0005-y", "no": 5, "date": "2026-10-07", "src": "rev", "ref": "4", "party": "", "memo": "عكس القيد 4",
             "status": "posted", "reversal": True, "by": "u_abc", "at": "2026-10-14T09:00:00+03:00", "meta": {"reverses": "e0004-x"},
             "lines": [{"a": "6101", "d": 0, "c": 5000}, {"a": "3101", "d": 5000, "c": 0, "party": OWNER}]},
            {"id": "e0006-shift", "no": 6, "date": "2026-10-08", "src": "shift", "ref": "2026-10-08-صباحية", "party": "",
             "memo": "إنتاج", "status": "posted", "by": "u_abc", "at": "2026-10-14T09:00:00+03:00", "meta": {"shiftId": "s1"},
             "lines": [{"a": "1305", "d": 30000, "c": 0, "qty": 10, "prod": "main", "futureField": 7},
                       {"a": "1301", "d": 0, "c": 30000, "qty": 40, "prod": "main"}]},
            {"id": "e0007", "no": 7, "date": "2026-10-08", "src": "count", "ref": "", "party": "", "memo": "مفروم",
             "status": "posted", "by": "seed", "at": "2026-10-14T09:00:00+03:00", "meta": {},
             "lines": [{"a": "1304", "d": 100, "c": 0, "qty": 1}, {"a": "5102", "d": 0, "c": 100}]},
        ],
        "shifts": [{"id": "s1", "date": "2026-10-08", "shift": "صباحية", "status": "approved", "byName": "أيمن",
                    "meterStart": 100, "meterEnd": 400, "bags": 2, "cartons": 10, "scrapKg": 1, "regrindKg": 3,
                    "downs": [{"m": 10, "r": "عطل"}], "entryId": "e0006-shift",
                    "cost": {"total": 30000, "perSar": 21.43, "rmKg": 50, "kwh": 300, "eff": 0.5, "maxCartons": 29}}],
        "requests": [], "advances": [], "recon": [],
        "budgets": [{"id": "m202610", "month": "2026-10", "cartons": 1500, "sales": 232500}],
        "expected": {
            "trialBalance": 0.0, "entries": 7, "entriesPosted": 6, "entriesReversed": 1, "maxNo": 7, "assets": 2, "shifts": 1,
            "accountBalancesYER": {"1102": 70000, "1201": 21700, "1301": 40000, "1304": 100, "1305": 30000},
            "accountBalancesSAR": {"1102": 500, "1201": 155},
            "quantities": {"1301": 60, "1304": 1, "1305": 10},
            "partyBalancesYER": {f"3101|{OWNER}": -140000, f"1201|{C}": 21700},
            "partyBalancesSAR": {f"1201|{C}": 155},
        },
    }


def raw(p: dict) -> bytes:
    return json.dumps(p, ensure_ascii=False).encode()


class Import(LedgerTestCase):
    def entry_count(self) -> int:
        return fetch_one(self.conn, "SELECT COUNT(*) AS n FROM entries")["n"]

    def test_happy_path(self):
        r = import_service.import_export(self.conn, raw(payload()))
        self.assertTrue(r["matchesExpected"])
        self.assertFalse(r["alreadyImported"])
        self.assertEqual(r["nextEntryNo"], 8)
        self.assertEqual(r["trialBalance"], 0)
        self.assertEqual(r["imported"], {"entries": 7, "assets": 2, "shifts": 1, "parties": 2, "requests": 0, "advances": 0})
        self.assertEqual(r["keyBalances"]["1102_SAR"], 500)
        self.assertTrue(reports.run(self.conn, "tb", {})["balanced"])
        # kept as is
        e = entries_repo.get(self.conn, fetch_one(self.conn, "SELECT id FROM entries WHERE no = 6")["id"])
        self.assertEqual(e["lines"][0]["prod"], "main")
        self.assertEqual(json.loads(fetch_one(self.conn, "SELECT extra FROM entry_lines WHERE entry_id = ? AND seq = 0", (e["id"],))["extra"]),
                         {"futureField": 7})
        self.assertEqual(fetch_one(self.conn, "SELECT legacy_by FROM entries WHERE no = 6")["legacy_by"], "u_abc")
        self.assertEqual(self.conn.execute("SELECT value FROM settings WHERE key = 'someFutureKey'").fetchone()["value"], '"kept"')
        sh = shifts_repo.list_all(self.conn)[0]
        self.assertEqual((sh["status"], sh["entry_id"], sh["cost"]["total"]), ("approved", e["id"], 30000))
        self.assertEqual(json.loads(fetch_one(self.conn, "SELECT doc FROM shifts")["doc"])["downs"], [{"m": 10, "r": "عطل"}])

    def test_idempotent_same_payload(self):
        body = raw(payload())
        import_service.import_export(self.conn, body)
        again = import_service.import_export(self.conn, body)
        self.assertTrue(again["alreadyImported"])
        self.assertEqual(self.entry_count(), 7)

    def test_different_payload_after_success(self):
        import_service.import_export(self.conn, raw(payload()))
        p = payload()
        p["exportedAt"] = "2026-10-21"
        with self.assertRaises(Conflict):
            import_service.import_export(self.conn, raw(p))

    def test_unbalanced_entry_rolls_back(self):
        p = payload()
        p["entries"][2]["lines"][1]["c"] = 21000
        with self.assertRaises(Unprocessable) as cm:
            import_service.import_export(self.conn, raw(p))
        self.assertEqual(cm.exception.field, "entries[2]")
        self.assertEqual(self.entry_count(), 0)

    def test_unknown_account(self):
        p = payload()
        p["entries"][1]["lines"][0]["a"] = "9999"
        with self.assertRaises(Unprocessable) as cm:
            import_service.import_export(self.conn, raw(p))
        self.assertEqual(cm.exception.field, "entries[1].lines[0].a")
        self.assertEqual(self.entry_count(), 0)

    def test_expected_mismatch_rolls_back(self):
        p = payload()
        p["expected"]["accountBalancesYER"]["1102"] = 69000
        with self.assertRaises(Unprocessable) as cm:
            import_service.import_export(self.conn, raw(p))
        self.assertEqual(cm.exception.extra["differences"][0]["item"], "accountBalancesYER[1102]")
        self.assertEqual(self.entry_count(), 0)
        self.assertEqual(fetch_one(self.conn, "SELECT COUNT(*) AS n FROM assets")["n"], 0)

    def test_reversed_entries_excluded(self):
        import_service.import_export(self.conn, raw(payload()))
        self.assertEqual(ledger_service.bal(self.conn, "6101")["y"], 0)
        orig = fetch_one(self.conn, "SELECT id, status, reversed_by_id FROM entries WHERE no = 4")
        mirror = fetch_one(self.conn, "SELECT id, reverses_id FROM entries WHERE no = 5")
        self.assertEqual((orig["status"], orig["reversed_by_id"], mirror["reverses_id"]), ("reversed", mirror["id"], orig["id"]))

    def test_posting_after_import_continues_numbering(self):
        import_service.import_export(self.conn, raw(payload()))
        res = tx.save(self.conn, "sale", {"date": "2026-10-20", "ref": "NEW1", "party": C, "qty": 1, "price": 155, "rate": 140},
                      self.owner)
        self.assertEqual(res["posted"][0]["no"], 8)

    def test_refuses_a_ledger_that_already_has_entries(self):
        tx.save(self.conn, "manual", {"date": "2026-10-20", "memo": "اختبار",
                                      "lines": [{"a": "1101", "d": 5, "c": 0}, {"a": "3101", "d": 0, "c": 5}]}, self.owner)
        with self.assertRaises(Conflict):
            import_service.import_export(self.conn, raw(payload()))

    def test_skips_posting_rules(self):
        """Lock date and duplicate references apply to new postings, not to historical data."""
        from services import settings_service
        settings_service.update(self.conn, {"lockDate": "2026-12-31"})
        p = payload()
        p["entries"][2]["ref"] = p["entries"][1]["ref"] = "SAME"
        self.assertTrue(import_service.import_export(self.conn, raw(p))["matchesExpected"])

    def test_bad_json(self):
        with self.assertRaises(Unprocessable):
            import_service.import_export(self.conn, b"{not json")


@unittest.skipUnless(os.environ.get("JOAN_IMPORT_FILE"), "set JOAN_IMPORT_FILE to check a real export")
class RealExport(LedgerTestCase):
    def test_real_export(self):
        with open(os.environ["JOAN_IMPORT_FILE"], "rb") as fh:
            body = fh.read()
        r = import_service.import_export(self.conn, body)
        self.assertTrue(r["matchesExpected"])
        expected = json.loads(body)["expected"]
        self.assertEqual(r["nextEntryNo"], expected["maxNo"] + 1)


class ImportEndpoint(LedgerTestCase):
    """The HTTP layer: token rules and status codes, calling the route with a real Starlette request."""

    def call(self, token_env: str, body: bytes, header: str | None = None):
        import asyncio

        from fastapi import HTTPException
        from starlette.requests import Request

        from api import admin
        from config import settings

        object.__setattr__(settings, "import_token", token_env)
        headers = [(b"content-type", b"application/json")]
        if header is not None:
            headers.append((b"x-import-token", header.encode()))
        sent = {"done": False}

        async def receive():
            if sent["done"]:
                return {"type": "http.disconnect"}
            sent["done"] = True
            return {"type": "http.request", "body": body, "more_body": False}

        request = Request({"type": "http", "method": "POST", "path": "/api/admin/import", "headers": headers}, receive)
        try:
            return 200, asyncio.run(admin.import_export(request, conn=self.conn))
        except HTTPException as exc:
            return exc.status_code, {"detail": exc.detail}
        except (Conflict, Unprocessable) as exc:
            return exc.status_code, {"detail": exc.message, "field": exc.field}
        finally:
            object.__setattr__(settings, "import_token", "")

    def test_token_rules_and_status_codes(self):
        body = raw(payload())
        self.assertEqual(self.call("", body, "anything")[0], 404)
        self.assertEqual(self.call("s3cret", body)[0], 403)
        self.assertEqual(self.call("s3cret", body, "wrong")[0], 403)
        bad = copy.deepcopy(payload())
        bad["entries"][0]["lines"][0]["a"] = "9999"
        self.assertEqual(self.call("s3cret", raw(bad), "s3cret"), (422, {"detail": "حساب غير معروف: 9999", "field": "entries[0].lines[0].a"}))
        code, out = self.call("s3cret", body, "s3cret")
        self.assertEqual((code, out["matchesExpected"], out["alreadyImported"]), (200, True, False))
        code, out = self.call("s3cret", body, "s3cret")
        self.assertEqual((code, out["alreadyImported"]), (200, True))
        other = payload()
        other["exportedAt"] = "x"
        self.assertEqual(self.call("s3cret", raw(other), "s3cret")[0], 409)


if __name__ == "__main__":
    unittest.main()

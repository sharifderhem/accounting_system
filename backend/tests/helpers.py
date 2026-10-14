"""Shared test setup: a fresh in-memory ledger with the agreed parties and users."""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import Database  # noqa: E402
from migrations.migrations import migrate  # noqa: E402
from repositories import users_repo  # noqa: E402
from services import auth_service, settings_service  # noqa: E402


class LedgerTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = Database.connect(":memory:")
        migrate(self.conn)
        settings_service.seed(self.conn, "طه عادل")
        settings_service.add_party(self.conn, "أحمد", "custodian")
        auth_service.ensure_owner(self.conn, "taha", "owner-pass-1", "طه عادل")
        self.owner = auth_service.public_user(users_repo.get_auth_by_username(self.conn, "taha"))
        self.entry = auth_service.create_user(self.conn, "clerk", "مدخل", "clerk-pass-1", "entry", False)
        self.reviewer = auth_service.create_user(self.conn, "partner", "الشريك", "partner-pass", "reviewer", False)
        self.sup = auth_service.create_user(self.conn, "sup1", "مشرف", "super-pass-1", "supervisor", False)
        # Most tests post directly; dual control is exercised in its own tests.
        settings_service.update(self.conn, {"dualControl": False})

    def tearDown(self) -> None:
        self.conn.close()

    def make_approver(self, user: dict) -> dict:
        return auth_service.update_user(self.conn, user["id"], {"approver": True})

"""Ordered schema migrations, tracked with SQLite's ``PRAGMA user_version``.

Never edit a migration that may already have run on the server. Add a new one.
Money is stored in minor units (fils for YER, halalas for SAR) as integers, so
sums are exact.
"""

import logging
import sqlite3

logger = logging.getLogger(__name__)


_M001_INITIAL = """
        CREATE TABLE users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE COLLATE NOCASE,
            label TEXT NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL CHECK (role IN ('owner','entry','reviewer','supervisor','none')),
            approver INTEGER NOT NULL DEFAULT 0,
            active INTEGER NOT NULL DEFAULT 1,
            failed_logins INTEGER NOT NULL DEFAULT 0,
            locked_until TEXT,
            created_at TEXT NOT NULL
        );

        CREATE TABLE sessions (
            token_hash TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            created_at TEXT NOT NULL,
            expires_at TEXT NOT NULL
        );
        CREATE INDEX idx_sessions_user ON sessions(user_id);

        CREATE TABLE settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );

        CREATE TABLE parties (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            type TEXT NOT NULL CHECK (type IN ('customer','supplier','custodian','lender','owner','other'))
        );

        CREATE TABLE cost_centers (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL
        );

        CREATE TABLE entries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            no INTEGER NOT NULL UNIQUE,
            date TEXT NOT NULL,
            memo TEXT NOT NULL,
            src TEXT NOT NULL,
            ref TEXT NOT NULL DEFAULT '',
            party TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'posted' CHECK (status IN ('posted','reversed')),
            reverses_id INTEGER REFERENCES entries(id),
            reversed_by_id INTEGER REFERENCES entries(id),
            is_cogs INTEGER NOT NULL DEFAULT 0,
            created_by INTEGER REFERENCES users(id),
            created_by_label TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            approved_by INTEGER REFERENCES users(id),
            approved_by_label TEXT NOT NULL DEFAULT '',
            meta TEXT NOT NULL DEFAULT '{}'
        );
        CREATE INDEX idx_entries_date ON entries(date);
        CREATE INDEX idx_entries_src_ref ON entries(src, ref);

        CREATE TABLE entry_lines (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            entry_id INTEGER NOT NULL REFERENCES entries(id),
            seq INTEGER NOT NULL,
            account TEXT NOT NULL,
            debit INTEGER NOT NULL DEFAULT 0,
            credit INTEGER NOT NULL DEFAULT 0,
            party TEXT,
            cur TEXT,
            fc INTEGER,
            qty REAL,
            shift TEXT,
            cc TEXT,
            asset TEXT,
            memo TEXT,
            CHECK (debit >= 0 AND credit >= 0)
        );
        CREATE INDEX idx_lines_entry ON entry_lines(entry_id);
        CREATE INDEX idx_lines_account ON entry_lines(account, party);

        CREATE TABLE shifts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            shift TEXT NOT NULL CHECK (shift IN ('صباحية','مسائية')),
            by_name TEXT NOT NULL DEFAULT '',
            meter_start REAL NOT NULL,
            meter_end REAL NOT NULL,
            bags REAL NOT NULL,
            extra_kg REAL NOT NULL DEFAULT 0,
            cartons REAL NOT NULL,
            scrap_kg REAL NOT NULL DEFAULT 0,
            shots_start REAL,
            shots_end REAL,
            down_min REAL NOT NULL DEFAULT 0,
            down_reason TEXT NOT NULL DEFAULT '',
            notes TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','approved','rejected')),
            entry_id INTEGER REFERENCES entries(id),
            cost TEXT,
            created_by INTEGER REFERENCES users(id),
            created_at TEXT NOT NULL,
            decided_by INTEGER REFERENCES users(id),
            decided_at TEXT
        );
        CREATE UNIQUE INDEX idx_shifts_slot ON shifts(date, shift) WHERE status <> 'rejected';

        CREATE TABLE requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            kind TEXT NOT NULL CHECK (kind IN ('out','exp','fx')),
            entries TEXT NOT NULL,
            summary TEXT NOT NULL,
            amount INTEGER NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','approved','rejected','withdrawn')),
            created_by INTEGER NOT NULL REFERENCES users(id),
            created_by_label TEXT NOT NULL,
            created_at TEXT NOT NULL,
            decided_by INTEGER REFERENCES users(id),
            decided_by_label TEXT NOT NULL DEFAULT '',
            decided_at TEXT,
            posted_nos TEXT NOT NULL DEFAULT '[]'
        );

        CREATE TABLE advances (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            employee TEXT NOT NULL,
            amount INTEGER NOT NULL,
            installments INTEGER NOT NULL DEFAULT 1,
            reason TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','approved','rejected')),
            created_by INTEGER NOT NULL REFERENCES users(id),
            created_by_label TEXT NOT NULL,
            created_at TEXT NOT NULL,
            decided_by INTEGER REFERENCES users(id),
            decided_by_label TEXT NOT NULL DEFAULT '',
            decided_at TEXT,
            entry_no INTEGER
        );

        CREATE TABLE assets (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            date TEXT NOT NULL,
            cost INTEGER NOT NULL DEFAULT 0,
            amount REAL NOT NULL DEFAULT 0,
            cur TEXT NOT NULL DEFAULT 'YER',
            life REAL NOT NULL,
            salvage INTEGER NOT NULL DEFAULT 0,
            cc TEXT NOT NULL DEFAULT 'prod',
            note TEXT NOT NULL DEFAULT '',
            posted_to TEXT,
            created_at TEXT NOT NULL
        );

        CREATE TABLE recon_marks (
            account_key TEXT NOT NULL,
            line_id INTEGER NOT NULL REFERENCES entry_lines(id),
            PRIMARY KEY (account_key, line_id)
        );

        CREATE TABLE recon_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            account_key TEXT NOT NULL,
            date TEXT NOT NULL,
            statement INTEGER NOT NULL,
            book INTEGER NOT NULL,
            cleared INTEGER NOT NULL,
            diff INTEGER NOT NULL,
            by_label TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE budgets (
            month TEXT PRIMARY KEY,
            data TEXT NOT NULL
        );
"""


_M002_IMPORT = """
        ALTER TABLE entries ADD COLUMN legacy_id TEXT;
        ALTER TABLE entries ADD COLUMN legacy_by TEXT;
        CREATE UNIQUE INDEX idx_entries_legacy ON entries(legacy_id) WHERE legacy_id IS NOT NULL;
        ALTER TABLE entry_lines ADD COLUMN prod TEXT;
        ALTER TABLE entry_lines ADD COLUMN extra TEXT;
        ALTER TABLE shifts ADD COLUMN legacy_id TEXT;
        ALTER TABLE shifts ADD COLUMN doc TEXT;
        CREATE TABLE import_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sha256 TEXT NOT NULL UNIQUE,
            done_at TEXT NOT NULL,
            summary TEXT NOT NULL
        );
"""


# (version, description, SQL). Each runs in one transaction with its version bump.
MIGRATIONS: list[tuple[int, str, str]] = [
    (1, "Initial ledger schema", _M001_INITIAL),
    (2, "Legacy ids, production line, shift documents and import log for the prototype import", _M002_IMPORT),
]


def migrate(conn: sqlite3.Connection) -> int:
    """Apply every pending migration in order. Returns the resulting version."""
    current = conn.execute("PRAGMA user_version").fetchone()["user_version"]
    for version, description, sql in MIGRATIONS:
        if version <= current:
            continue
        logger.info("Applying migration %s: %s", version, description)
        script = f"BEGIN IMMEDIATE;\n{sql}\nPRAGMA user_version = {int(version)};\nCOMMIT;"
        try:
            conn.executescript(script)
        except BaseException:
            if conn.in_transaction:
                conn.execute("ROLLBACK")
            raise
        current = version
    return current

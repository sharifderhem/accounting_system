# Backend guide

FastAPI + SQLite, organised in layers. Read [`../project.md`](../project.md) first for the business rules this code
enforces.

## Run and test

```bash
cd backend
pip install -r requirements.txt
OWNER_USERNAME=taha OWNER_PASSWORD='a-long-password' SECURE_COOKIES=0 uvicorn main:app --reload
# http://127.0.0.1:8000  (also serves ../frontend)

cd tests && python -m unittest discover -p "test_*.py"
```

The database file is created and migrated on startup (`data/ledger.db` locally, `DATABASE_PATH` on the server).

## Project tree

```
backend/
├── main.py            App: lifespan (migrate, seed, first owner), security middleware, error handlers,
│                      routers, static frontend mounted at "/"
├── config.py          Settings from environment variables (no secrets in code)
├── database.py        Connection factory, transaction(), fetch_one/fetch_all/execute
├── requirements.txt
├── api/               HTTP layer: one module per area, thin routes
│   ├── deps.py        get_conn, current_user, owner, finance_viewer
│   ├── auth.py        login, logout, me, own password
│   ├── settings.py    /meta (form context per role), settings, parties, cost centers, users
│   ├── transactions.py  POST /api/transactions/{kind}[/preview]
│   ├── approvals.py   payment requests and advance requests
│   ├── production.py  shifts, assets, depreciation
│   ├── books.py       home, analytics, journal, reverse, reports, reconciliation, owner postings from reports
│   └── admin.py       one-time import (IMPORT_TOKEN)
├── schemas/
│   ├── requests.py    Pydantic request bodies (shape only). FORMS maps transaction kind → model
│   └── responses.py   Small response models
├── services/          Business rules
│   ├── chart.py       Chart of accounts, sources, categories, purposes, default settings (fixed vocabulary)
│   ├── access.py      Role checks used by every service
│   ├── ledger_service.py   THE posting engine: validate, post, post_many, reverse, balances
│   ├── transactions_service.py  Form → entries builders (sale, in, out, exp, fx, xfer, adj, count, manual)
│   ├── requests_service.py  Dual control: create/approve/reject/withdraw; advances
│   ├── shifts_service.py    Submit, cost (§7.2), flags, approve, reject, late wages
│   ├── costing.py     Pure formulas (no database)
│   ├── assets_service.py    Assets, prices, life, monthly depreciation
│   ├── rates_service.py     Current production rates (forecasts, stock cover)
│   ├── adjustments_service.py  Provision, revaluation, zakat accrual, FX residue close
│   ├── home_service.py, analytics_service.py, journal_service.py, recon_service.py, meta_service.py
│   ├── settings_service.py, auth_service.py, import_service.py
│   └── reports/       The 17 reports: statements.py, customers.py, operations.py; REPORTS registry in __init__
├── repositories/      SQL only, one module per table group (entries, shifts, assets, requests, users, settings, recon, import)
├── migrations/
│   └── migrations.py  Ordered SQL migrations tracked by PRAGMA user_version
├── utils/             errors.py (DomainError & co.), money.py (r2, minor units), dates.py (factory "today")
└── tests/             unittest suites; helpers.py builds an in-memory ledger with users
```

## Layers and the rules between them

```
api  →  services  →  repositories  →  database
```

| Layer | Allowed | Not allowed |
|---|---|---|
| `api/` | Parse the request (schema), get user/conn from `deps`, call one service function, return its result | SQL, business rules, role logic beyond the dependency |
| `schemas/` | Field types, lengths, enums | Business decisions (those belong in services) |
| `services/` | Rules, role checks (`access.*`), orchestration, transactions | SQL strings, HTTP objects |
| `repositories/` | Parameterised SQL, row ↔ dict mapping, minor-unit conversion | Business rules, imports from `services` |

- **Errors:** services raise `DomainError` subclasses from `utils/errors.py` with a plain-Arabic message and, when it is
  about one input, `field=` (the frontend highlights that field). `main.py` turns them into JSON `{detail, field, ...}`
  with the right status: `DomainError` 400, `Forbidden` 403, `NotFound` 404, `Conflict` 409, `Unprocessable` 422.
- **Roles:** check them in the service (`access.require_owner(user)`, `access.require_form(user, kind)`), and also use
  `Depends(owner)` / `Depends(finance_viewer)` on routes that are owner-only or finance-only. Supervisors must never
  receive money figures: filter in the service, not in the frontend.
- **Transactions:** wrap every multi-step write in `with transaction(conn):`. It takes SQLite's write lock up front
  (`BEGIN IMMEDIATE`) and nests safely, so a service that calls another service stays atomic.
- **Routes are plain `def`**, so FastAPI runs them in its thread pool and the blocking `sqlite3` driver never stalls the
  event loop. One connection per request (`get_conn`).

## The posting engine

All writes to `entries` / `entry_lines` go through `services/ledger_service.py`:

- `validate(conn, entry)`: known accounts, one-sided positive lines, SAR lines carry `fc`, balanced (±0.01), date not
  in the locked period, no duplicate reference for `sale`/`in`/`out`.
- `post(conn, entry, user, approver=None)` → `{id, no}`: validates, numbers (`MAX(no)+1` inside the write lock), records
  creator/approver.
- `post_many(...)`: several entries, all or nothing.
- `reverse(conn, entry_id, user)`: mirror entry dated today; marks the original reversed and undoes side effects
  (shift back to pending, asset acquisition, depreciation `posted_to`).
- `bal`, `pbal`, `avg_cost`: balances; `avg_cost` is date-aware (as of the entry's date).

An entry is a dict: `{date, memo, src, ref, party, meta, lines: [{a, d, c, party?, cur?, fc?, qty?, shift?, cc?, asset?, memo?}]}`.
`d`/`c` are YER; `fc` is the SAR amount; `qty` is positive (its sign comes from the side).

Never insert into those tables any other way. The only exception is `import_service.py`, a deliberate one-time copy.

## Conventions

- Python 3.11+, type hints, `logging.getLogger(__name__)` (no `print`).
- Money: compute in rials, round with `utils.money.r2`, store with `to_minor` (repositories do this).
- Dates are ISO strings `YYYY-MM-DD`. "Today" is the factory's day: `utils.dates.today()` (Asia/Aden).
- User-facing text is Arabic and says exactly what to fix ("قراءة العداد بعد يجب أن تكون أكبر من قبل").
- Dynamic SQL only from fixed allowlists (see `entries_repo._filters`); every value is a bound parameter.
- Docstrings say *why*; reference the spec section (`§5.3`) when a rule comes from it.
- New account, source type, category or purpose: add it to `services/chart.py` (and to the frontend only if it needs a
  label that the API does not already send through `/api/meta`).

## Adding a feature

Example: a new transaction form "purchase on credit" (`credit_buy`).

1. **Vocabulary:** if it needs new accounts or sources, add them in `services/chart.py`.
2. **Schema:** add `CreditBuyForm` in `schemas/requests.py` and register it in `FORMS`.
3. **Service:** write `build_credit_buy(conn, form, user)` in `transactions_service.py` that returns the entries
   (validate inputs with `need(...)`, field names matching the form). Register it in `BUILDERS`. Preview and save then
   work automatically, including dual control if you add the kind to `DUAL_CONTROL_KINDS`.
4. **Roles:** add the kind to `ENTRY_FORMS` / `OWNER_FORMS` in `services/access.py`.
5. **Route:** none needed for a form (the generic `/api/transactions/{kind}` handles it). For other features, add a
   function to the right `api/` module (or a new module registered in `main.py`), keeping it thin.
6. **Persistence:** if new data must be stored, add a migration (below) and a repository function.
7. **Tests:** add cases to the matching `tests/test_*.py`: the success path and the important refusals. Use
   `LedgerTestCase` (fresh in-memory database with owner, entry, reviewer and supervisor users).
8. **Frontend:** add the form or screen (see `../frontend/readme.md`).
9. Run the full test suite, then push. `main` deploys to production.

## Migrations

`migrations/migrations.py` holds an ordered list (descriptions shortened here):

```python
MIGRATIONS = [
    (1, "Initial ledger schema", _M001_INITIAL),
    (2, "Legacy ids, production line, shift documents and import log", _M002_IMPORT),
]
```

On startup `migrate()` reads `PRAGMA user_version` and runs each newer migration as one transaction together with its
version bump.

To change the schema:

1. Add `_M00N_<NAME> = """ ...SQL... """` and append `(N, "description", _M00N_<NAME>)` with the next number.
2. **Never edit or renumber a migration that is already on `main`**: the live database has run it.
3. Prefer additive changes (`ALTER TABLE ... ADD COLUMN`, new tables, new indexes). SQLite cannot drop or alter columns
   in place; for those, create a new table, copy, drop, rename, all inside the migration.
4. Update the repositories that read or write the table, and the tests.
5. Check both paths: a fresh database (tests do this) and an upgrade of an existing one (create a database at version
   N−1 with some rows, then run `migrate`).
6. Deploying runs the migration on the live database at restart. A snapshot is taken first, but rollback only restores
   code, so make the migration correct.

## Tests

- `tests/helpers.py`: `LedgerTestCase` gives `self.conn` (in-memory, migrated, seeded) and users `self.owner`,
  `self.entry`, `self.reviewer`, `self.sup`. Dual control is off by default; tests that need it turn it on.
- Suites: `test_ledger.py` (rules and forms), `test_workflows.py` (approvals, shifts, assets), `test_reports.py`
  (reports, home, analytics, reconciliation), `test_import.py` (prototype import), `test_api_glue.py` (calls the route
  functions directly; needs FastAPI).
- The server runs the same suite before every deploy, so a failing test blocks the deploy.
- Fixtures are synthetic. Never commit a real export or database.

## Environment variables

See the table in [`../README.md`](../README.md). In short: `DATABASE_PATH`, `OWNER_USERNAME` / `OWNER_PASSWORD`
(first owner only), `OWNER_NAME`, `SECURE_COOKIES`, `SESSION_DAYS`, `APP_TIMEZONE`, `FRONTEND_DIR`, `LOG_LEVEL`,
`IMPORT_TOKEN` (leave unset).

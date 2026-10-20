# دفتر مصنع جوان — Joan Factory Ledger

Bookkeeping and production costing for مصنع جوان. The owner and shift supervisors enter what happens in the
factory through plain Arabic forms; the backend turns every action into balanced double-entry accounting.
The full requirements are in the spec; this file explains how the code is laid out and how to run it.

```
backend/    FastAPI + SQLite (one file), layered: api → services → repositories
frontend/   Plain HTML + JavaScript modules, no build step. Served by the backend.
```

## Run it

Requires Python 3.11+.

```bash
cd backend
pip install -r requirements.txt
export OWNER_USERNAME=taha OWNER_PASSWORD='choose-a-long-password' SECURE_COOKIES=0   # 0 only for local http
uvicorn main:app --host 127.0.0.1 --port 8000
```

Open http://127.0.0.1:8000 and sign in as the owner. The database file is created at `backend/data/ledger.db`,
migrated automatically, and seeded with the agreed parties and cost centers. The owner creates every other login
from **الإعدادات**.

### Environment

| Variable | Default | Meaning |
|---|---|---|
| `DATABASE_PATH` | `backend/data/ledger.db` | SQLite file |
| `OWNER_USERNAME`, `OWNER_PASSWORD` | – | First owner account, created once when no owner exists |
| `OWNER_NAME` | طه عادل | Owner's party name (used on 3101 lines) |
| `SECURE_COOKIES` | `1` | Send the session cookie over HTTPS only. Keep `1` in production |
| `SESSION_DAYS` | `30` | Sign-in lifetime (extends while used) |
| `APP_TIMEZONE` | `Asia/Aden` | What "today" means |
| `FRONTEND_DIR` | `../frontend` | Static files served at `/` |

In production run uvicorn behind a reverse proxy (e.g. Caddy or nginx) that terminates HTTPS.

## Tests

```bash
cd backend/tests
python -m unittest discover -p "test_*.py"
```

- `test_ledger.py` – §1 rules (balance, numbering, lock, reversal) and every §5 form.
- `test_workflows.py` – dual control, advances, shift costing (checked against hand-calculated figures), assets.
- `test_reports.py` – all 17 reports, home, analytics, reconciliation, journal on a realistic month.
- `test_api_glue.py` – calls each route function with real data (needs FastAPI installed).

## How the backend is organised

| Layer | Folder | What lives there |
|---|---|---|
| HTTP | `api/` | Thin routes. Login/role checks via `api/deps.py`; business errors become JSON `{detail, field}` |
| Shapes | `schemas/` | Pydantic request bodies; services check the business rules |
| Rules | `services/` | `ledger_service` (the only way to post or reverse), one module per area, `reports/` for §11 |
| SQL | `repositories/` | Parameterised queries only |
| Schema | `migrations/` | Numbered migrations tracked by `PRAGMA user_version`. Add new ones; never edit old ones |

Design points worth knowing:

- **Money is stored as integers** (fils/halalas). `fc` (SAR) and `qty` are stored positive; the side of the line gives the sign.
- **Every write is one transaction** with SQLite's write lock (`BEGIN IMMEDIATE`). Entry numbers are `MAX+1` inside it,
  so they are unique and gap-free; approving a request or a shift posts and updates status atomically.
- **Reversals** post a mirror entry dated today and mark the original `reversed`. Both stay in the ledger. Reversing is
  refused when either date is in the locked period.
- **Average costs are date-aware**: a back-dated sale or shift uses the stock average as of its own date.
- **Wages entered after a shift was approved** are moved into finished goods with a small follow-up entry, and the
  shift's stored cost is updated.
- **Roles are enforced on the server.** Supervisors only receive their own shifts and advance requests and never money
  figures; data-entry users never receive balances.
- Writes require the `X-Requested-With: fetch` header (blocks cross-site form posts); cookies are HttpOnly, SameSite=Lax.

## Frontend

`frontend/js/main.js` is the shell (login, role tabs, header). Each tab is a module in `frontend/js/views/` with
`render(element, app)`. `xlsx.js` builds the formatted Excel exports in the browser (spec §13) without libraries.

## Deployment (server + automatic updates)

One-time setup on a fresh Ubuntu/Debian server, as root:

```bash
curl -fsSL https://raw.githubusercontent.com/sharifderhem/accounting_system/main/deploy/setup-server.sh -o setup.sh
bash setup.sh                         # or: DOMAIN=ledger.example.com bash setup.sh   (automatic HTTPS)
```

It asks for the owner's username and password, then installs everything:

| What | Where |
|---|---|
| Code (replaced on each deploy) | `/opt/joan-ledger/app` |
| **Database — never touched by deploys** | `/var/lib/joan-ledger/ledger.db` |
| Snapshot before each deploy (last 10) | `/var/lib/joan-ledger/snapshots/` |
| Settings | `/etc/joan-ledger.env` |
| App service | `joan-ledger` (uvicorn on 127.0.0.1:8000) |
| Web server | Caddy on port 80 (443 with a domain) |

**How a change reaches the server:** push to `main` → GitHub Actions runs the tests (`.github/workflows/ci.yml`) →
within a minute the server notices the new commit (`joan-ledger-update.timer`), runs the same tests in a separate
folder, snapshots the database, switches the code and restarts. If the tests fail it stays on the current version;
if the app does not come up healthy it rolls back to the previous commit. No keys or passwords are stored in GitHub,
and GitHub never connects to the server.

Useful commands on the server:

```bash
journalctl -u joan-ledger-update -f      # deploy log
journalctl -u joan-ledger -n 100         # app log
systemctl start joan-ledger-update       # deploy now instead of waiting
rm /var/lib/joan-ledger/failed-commit    # retry a commit that failed
```

Notes:
- Without a domain the site is plain HTTP, so passwords cross the network unencrypted. Point a domain (or a free
  subdomain) at the server and run the setup again with `DOMAIN=...` before real use; it then sets `SECURE_COOKIES=1`.
- Rollback restores the code, not the data. If a new version changed the database schema before failing, restore the
  latest file from `snapshots/` (stop the app, copy it over `ledger.db`, start the app).
- If the repository is made private, the server will need a read-only deploy key to keep pulling.

## Not done yet

- **§17 data import** from the prototype (one-time protected endpoint).

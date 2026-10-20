# دفتر مصنع جوان — Project context

Start here. This file is the shared context for anyone (person or AI agent) working on this repository.
Read it fully before changing anything, then read the guide for the part you are touching:

- **Backend guide:** [`backend/readme.md`](backend/readme.md): architecture, project tree, conventions, how to add a feature, migrations, tests.
- **Frontend guide:** [`frontend/readme.md`](frontend/readme.md): structure, view modules, UI rules, how to add a screen.
- **Running and deploying:** [`README.md`](README.md): local run, environment variables, server setup, the one-time import.

---

## 1. What this is

A bookkeeping and production-costing system for **مصنع جوان لصناعة وتجارة البلاستيك**, a small plastics factory in
Yemen that makes HDPE bottle caps (غطايا) on one injection machine and sells them by the carton.

- **The owner is not an accountant.** He and his shift supervisors enter what happens in the factory through plain
  Arabic forms (a sale, a transfer, the day's expenses, a shift's meter readings). The backend turns each action into
  correct double-entry accounting and shows where money and production stand.
- **It replaces an accountant.** There is no separate accounting package; this system is the books.
- **History:** the first version was a single-file prototype that ran inside claude.ai (`goaan-ledger.html`). This
  repository is the hosted replacement. The prototype's books were copied in once through `POST /api/admin/import`.
  Formulas and screens follow the prototype, which is the behavioural reference.
- **Requirements:** the agreed spec lives outside the repo (it names customers and prices, and this repo is public).
  Section numbers like "§5.3" in code comments refer to it. The rules that matter for code are summarised below.

## 2. Users and roles (enforced on the server)

| Role | Sees | Does |
|---|---|---|
| **owner** (المالك) | everything | everything: approve shifts, reverse entries, manual entries, settings, users, period lock, assets, depreciation, revaluation, provisions, zakat |
| **entry** (مدخل بيانات) | entry forms and own requests | sales, transfers, expenses, advance requests. No balances or reports |
| **reviewer** (مراجع أو شريك) | home, analytics, reports, journal, reconciliation, read only | nothing, unless flagged **approver**: then approves other people's payment requests |
| **supervisor** (مشرف وردية) | the shift form and own submissions only | submit shifts and advance requests. **Never sees money figures** |

There is no sign-up and no default account. The owner account is created once by the server setup script; the owner
creates every other login from الإعدادات. Users are mostly on **phones**.

## 3. Non-negotiable accounting rules

These come from the owner and are enforced in `backend/services/ledger_service.py`. Do not weaken them.

1. **Double entry, always balanced.** In each entry, total debit equals total credit (tolerance 0.01).
2. **Posted entries are immutable.** No edit, no delete. A correction is a **reversal**: a mirror entry dated today that
   references the original, which is then marked `reversed`. Both stay in the ledger.
3. **Base currency is the Yemeni rial (YER, ر.ي).** Every line has a YER amount. Lines on Saudi-riyal items also carry
   the SAR amount (`fc`, with `cur: "SAR"`).
4. **Never mix SAR and YER balances** on screen. Show the SAR account and the YER account separately; never a "net".
5. **Inventory lines carry quantity** (kg or cartons) so weighted-average costs work.
6. **Period lock.** Nothing may be posted or reversed on or before the lock date.
7. **Entry numbers are sequential and unique**, with no gaps or duplicates, even under concurrent posting.
8. **Every action is attributable:** who created it, who approved it, when.
9. **Arabic, right-to-left UI.** Western digits with thousands separators; inputs also accept Arabic-Indic digits.

Also important:

- **Dual control (الرقابة المزدوجة):** outgoing transfers, expenses and currency exchange become *requests* when another
  approver exists. **The creator can never approve their own request**, including the owner.
- **Shift costing is absorption costing:** approving a shift moves materials, cartons, electricity, that shift's wages
  and its share of depreciation into finished-goods stock at full cost. COGS uses weighted average.
- **Chart of accounts is fixed** (`backend/services/chart.py`). Adding an account is a code change, not a setting.

## 4. Technology

| Part | Choice | Why |
|---|---|---|
| Backend | Python 3.11+, FastAPI, standard-library `sqlite3` | Small, layered, easy to read (see the backend guide) |
| Database | One SQLite file | A few users and a few hundred entries a month; one writer at a time keeps numbering safe |
| Frontend | Plain HTML, CSS and JavaScript modules, no framework, no build step | Served as static files by the backend |
| Web server | Caddy in front of uvicorn | HTTPS automatically once a domain exists |
| CI/CD | GitHub Actions runs tests; the server pulls and deploys itself | No secrets stored in GitHub |

Money is stored as integer minor units in the database; services work in rials rounded to 2 decimals.

## 5. Repository map

```
project.md            this file
README.md             running locally, environment variables, deployment, import
backend/              FastAPI app        → backend/readme.md
frontend/             static web app      → frontend/readme.md
deploy/
  setup-server.sh     one-time server setup (run as root on a fresh Ubuntu/Debian VPS)
  update.sh           auto-deploy, run every minute on the server by a systemd timer
.github/workflows/
  ci.yml              tests on every push and pull request
```

## 6. The server

| Item | Value |
|---|---|
| Provider | Contabo, Cloud VPS 4 (2026), "Hub Europe" location |
| Public IP | **37.60.234.159** |
| Hostname | `vmi3683137` |
| OS | Debian/Ubuntu (set up by `deploy/setup-server.sh`) |
| Site | **http://37.60.234.159/** (plain HTTP: no domain yet, so no HTTPS) |
| SSH | `ssh -o PubkeyAuthentication=no -o PreferredAuthentications=password root@37.60.234.159` |

Credentials are **never** written in this repository. The owner of the server holds the root password.

**Layout on the server**

| Path | What |
|---|---|
| `/opt/joan-ledger/app` | git checkout of `main` (replaced on every deploy) |
| `/opt/joan-ledger/venv` | Python packages |
| `/var/lib/joan-ledger/ledger.db` | **the live database. Deploys never delete or replace it** |
| `/var/lib/joan-ledger/snapshots/` | database copy taken before each deploy (last 10 kept) |
| `/etc/joan-ledger.env` | settings: `DATABASE_PATH`, `SECURE_COOKIES`, `APP_TIMEZONE`, `OWNER_*` (password removed after first start) |

**Services:** `joan-ledger` (uvicorn on `127.0.0.1:8000`, runs as user `joan`), `joan-ledger-update.timer` (deploy
check every minute), `caddy` (port 80, and 443 once a domain is set). Firewall (ufw) allows only SSH, 80 and 443.

**How a change reaches production:** push to `main` → GitHub Actions runs the tests → within a minute the server sees
the new commit, runs the same tests in a separate folder, snapshots the database, switches the code and restarts.
Failing tests keep the current version; an app that does not come up healthy is rolled back to the previous commit.
Schema migrations run automatically on startup.

**Useful commands on the server**

```bash
journalctl -u joan-ledger-update -f       # deploy log ("[deploy] live on <sha>")
journalctl -u joan-ledger -n 100          # app log
systemctl start joan-ledger-update        # deploy now
rm /var/lib/joan-ledger/failed-commit     # retry a commit that failed
```

**Things to know**

- **Agents usually cannot reach the server.** Sandboxed agent environments typically block outbound connections to
  arbitrary hosts, including this IP (SSH and HTTP). Anything that must run on the server is done by the owner in a
  terminal; give exact commands to paste. Code changes reach the server by pushing to `main`.
- **No HTTPS yet.** Logins travel unencrypted until a domain points at the server and the setup is re-run with
  `DOMAIN=example.com bash setup.sh` (which also sets `SECURE_COOKIES=1`).
- **Rollback restores code, not data.** If a migration ran before a failed start, restore the latest snapshot
  (stop the app, copy the snapshot over `ledger.db`, start the app).
- **The import endpoint** (`POST /api/admin/import`) only exists while `IMPORT_TOKEN` is set in `/etc/joan-ledger.env`.
  It was for the one-time move from the prototype; the variable should stay unset.

## 7. Working rules for agents

- **Read before writing.** Follow the backend and frontend guides; keep the layer boundaries.
- **Every change to the books goes through `ledger_service.post` / `reverse`.** Never write to `entries` or
  `entry_lines` directly (the import is the only, deliberate, exception).
- **Schema changes are new migrations**, never edits to an existing one: the live database has already run them.
- **Run the tests** (`cd backend/tests && python -m unittest discover -p "test_*.py"`) before pushing. Pushing to `main`
  deploys to production within a minute.
- **Never commit real data** (exports, database files, passwords, tokens). The repository is public; `.gitignore`
  already excludes `*.db` and `*export*.json`.
- **Commits** are made as `sharifderhem <sharifderhem@gmail.com>`, without AI attribution trailers.
- **Plain Arabic for users.** Error messages say exactly what to fix, next to the field; no accounting jargon on primary
  screens.

## 8. Known open points

- Prices of the injection machine, chiller and temperature controller are not entered yet (their depreciation is
  missing from cost per carton until they are).
- The mould's 12-year life is temporary, pending the owner's review.
- Carton content (5,500 caps by count vs. by weight) and the chiller's estimated load are still estimates.
- Invoices 2233 and 2234 came from the prototype without cost of sales; reconciliation flags them.
- Out of scope: AI reading of invoices, automatic exchanger or wallet integration, payroll, multi-warehouse,
  multi-company, e-invoicing.

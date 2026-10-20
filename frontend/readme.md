# Frontend guide

Plain HTML, CSS and JavaScript modules: no framework, no npm, no build step. The backend serves this folder at `/`
and the API at `/api`. Read [`../project.md`](../project.md) first for roles and rules.

## Run

Start the backend (`../backend/readme.md`) and open http://127.0.0.1:8000. Edit a file, reload the page. There is
nothing to compile.

## Project tree

```
frontend/
├── index.html          Shell: header, tab bar, <main id="main">, toast. Loads css/app.css and js/main.js
├── css/
│   └── app.css         All styles. Design tokens on :root, dark mode, RTL, phone-first layout
└── js/
    ├── main.js         App shell: login gate, role-based tabs, header balances, theme, routing between views
    ├── api.js          fetch wrapper: JSON, same-origin cookie, X-Requested-With header, ApiError {message, status, field}
    ├── util.js         Escaping (h), number format/parse (fmt, num), dates, toast, status chips, form helpers
    ├── ui.js           Shared pieces: journal line tables, entry preview/card, KPI tile, shift cost table
    ├── charts.js       Small SVG charts (bars, line, cost bridge, morning/evening pairs) + tooltips
    ├── xlsx.js         Formatted Excel export built in the browser (RTL sheet, title, totals, filters)
    └── views/          One module per tab
        ├── login.js       Sign-in form
        ├── home.js        الرئيسية: balances, KPIs, alerts, stock
        ├── supervisor.js  وردية جديدة: the supervisor's only screen (no money); exports the shift and advance forms
        ├── shifts.js      الورديات: pending shift cards with cost and flags, approve/reject (owner)
        ├── move.js        تسجيل حركة: all transaction forms, preview, save or send for approval
        ├── requests.js    الطلبات: payment and advance requests
        ├── analytics.js   التحليلات
        ├── recon.js       المطابقات: checks and statement matching
        ├── assets.js      الأصول: assets, prices, depreciation
        ├── reports.js     التقارير: the 17 reports and their Excel export
        ├── journal.js     القيود: filters, reversal, export
        └── settings.js    الإعدادات: factory numbers, lock date, users, parties, cost centers
```

## How it works

- **Boot:** `main.js` calls `GET /api/auth/me`. Without a session it shows `views/login.js`. With one, it loads
  `GET /api/meta`, which returns everything the forms need *for this user's role*: the allowed tabs, accounts, parties,
  cost centers, form settings, approval badges and, for owner/reviewer, the header balances.
- **Views:** each tab module exports `render(main, app)`. It fetches its own data from the API, writes HTML into
  `main`, and attaches event handlers to that HTML. There is no virtual DOM or global store.
- **The `app` object** (passed to every view):
  - `app.meta`: the `/api/meta` payload
  - `app.go(tab, opts)`: switch tab (e.g. `app.go('reports', {report: 'claim', party})`)
  - `app.refresh()`: reload meta (badges, balances) and redraw the current view; call it after any change
- **Server is the authority.** Tabs and forms are hidden by role for convenience only; the backend enforces every rule.
  Never compute balances, approvals or permissions in the browser.

## Conventions

- **Arabic, RTL, plain words.** `<html dir="rtl" lang="ar">`. Labels and messages in Arabic, no accounting jargon on
  primary screens.
- **Escape everything** that comes from data with `h()` before putting it in HTML.
- **Numbers:** show with `fmt(x, digits)` (Western digits, thousands separators); wrap amounts in `<span class="num">`.
  Read inputs with `num()` / `numOrNull()`, which accept Arabic-Indic digits and separators. Number inputs use
  `inputmode="decimal"` (or `numeric`) for the phone keypad.
- **Currency always labelled** (ر.س / ر.ي). Never add SAR and YER together.
- **Status = icon + word + colour** (`statusChip()`), never colour alone.
- **Forms:** inputs carry `data-field="<api field name>"`. `readForm(container)` collects them (`data-num` for numbers).
  On error, `showError(container, msgEl, err)` puts the server's Arabic message under the field named by
  `err.field`, or in the message box.
- **Buttons that call the API:** capture `const btn = e.currentTarget` *before* any `await`, disable it with
  `busy(btn, true)` and re-enable it on error.
- **Preview before save** for anything that posts to the books (`/api/transactions/{kind}/preview`), and after saving
  show the entry number in a message that stays visible.
- **Styling:** use the tokens in `app.css` (`--accent`, `--good`, `--warn`, `--bad`, `--line`, ...). One accent colour;
  status colours only for status. Classes to reuse: `panel`, `kpis`/`kpi`, `form`, `tbl`, `chip`, `btn`, `seg`, `msg`,
  `alert`, `card`, `empty`.
- **Phone first:** single column at phone width, touch targets ≥ 44 px, no horizontal page scroll; wide tables go
  inside `<div class="tbl">`, which scrolls by itself.
- **No external scripts.** The page's Content-Security-Policy allows scripts from this site only, styles from this site
  and Google Fonts. Do not add CDN scripts; write the small helper instead.
- **Browser storage** only for conveniences (last tab, theme), always inside `try/catch`.

## Adding a screen or form

**A new tab:**

1. Create `js/views/<name>.js` exporting `async function render(main, app)`.
2. Import it in `js/main.js` and add it to `VIEWS` with its Arabic label.
3. Add the tab key to `tabs_for()` in `backend/services/meta_service.py` for the roles that may see it (and protect the
   API routes it calls on the backend).

**A new transaction form** (after the backend part, see the backend guide):

1. In `js/views/move.js`, add `[kind, label, description]` to `KINDS`.
2. Add the form's HTML to the `F` map in `formHtml()`, using the helpers there (`dateIn`, `numIn`, `textIn`, `curSel`,
   `viaSel`) with `data-field` names matching the backend schema.
3. Preview, save, dual-control requests and error highlighting then work without further code.

**A new report:** add its body function to `BODY` and its entry to `LIST` in `js/views/reports.js`; the report data
comes from `GET /api/reports/<kind>`. Excel export of what is on screen works automatically.

## Checking your change

- `for f in $(find js -name '*.js'); do node --check "$f"; done` catches syntax errors (CI runs this).
- Open it at phone width (about 390 px) and at desktop width, in light and dark mode.
- Try it with each role that can see it, especially the supervisor (no money anywhere).

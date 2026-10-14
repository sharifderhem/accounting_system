// App shell: login gate, role-based tabs, header, theme. Each tab is a view module with render(el, app).

import { api, setUnauthorizedHandler } from './api.js';
import { $, h, fmt, toast } from './util.js';
import { initTooltips } from './charts.js';
import * as login from './views/login.js';
import * as home from './views/home.js';
import * as shifts from './views/shifts.js';
import * as supervisor from './views/supervisor.js';
import * as move from './views/move.js';
import * as requests from './views/requests.js';
import * as analytics from './views/analytics.js';
import * as recon from './views/recon.js';
import * as assets from './views/assets.js';
import * as reports from './views/reports.js';
import * as journal from './views/journal.js';
import * as settings from './views/settings.js';

const VIEWS = {
  home: ['الرئيسية', home], shifts: ['الورديات', shifts], sup: ['وردية جديدة', supervisor], move: ['تسجيل حركة', move],
  requests: ['الطلبات', requests], analytics: ['التحليلات', analytics], recon: ['المطابقات', recon], assets: ['الأصول', assets],
  reports: ['التقارير', reports], journal: ['القيود', journal], settings: ['الإعدادات', settings],
};

const app = {
  user: null,
  meta: null,
  tab: null,
  async reloadMeta() {
    app.meta = await api.get('/meta');
    renderHeader();
  },
  go(tab, opts = {}) {
    if (!app.meta.tabs.includes(tab)) return;
    app.tab = tab;
    app.opts = opts;
    try { localStorage.setItem('jl-tab', tab); } catch { /* storage may be blocked */ }
    renderHeader();
    renderView();
  },
  // After any change: refresh badges and balances, then redraw the current view.
  async refresh() {
    await app.reloadMeta();
    await renderView();
  },
};

function storedTab() {
  try { return localStorage.getItem('jl-tab'); } catch { return null; }
}

function renderHeader() {
  const m = app.meta;
  if (!m) { $('tabs').innerHTML = ''; $('hstat').innerHTML = ''; return; }
  $('tabs').innerHTML = m.tabs.map((k) => {
    const n = m.badges[k] || 0;
    return `<button role="tab" data-t="${k}" aria-selected="${k === app.tab}">${VIEWS[k][0]}${n ? `<span class="badge" aria-label="${n} بانتظارك">${n}</span>` : ''}</button>`;
  }).join('');
  const hl = m.headline;
  const chips = hl ? `<span class="chip acc">سعودي <span class="num">${fmt(hl.sar)}</span> ر.س</span>`
    + `<span class="chip ${hl.yer < 0 ? 'warn' : 'acc'}">${hl.yer < 0 ? 'مكشوف ' : ''}يمني <span class="num">${fmt(hl.yer)}</span> ر.ي</span>` : '';
  $('hstat').innerHTML = `${chips}<button class="btn sm" id="themeBtn" aria-label="تبديل الوضع الليلي والنهاري">ليلي/نهاري</button>`
    + `<button class="btn sm" id="logoutBtn" title="${h(m.user.label)}">خروج</button>`;
  $('roleLine').textContent = m.user.role === 'owner'
    ? 'مصنع جوان لصناعة وتجارة البلاستيك · الغطايا'
    : `${m.user.label} · ${m.user.roleLabel}`;
}

async function renderView() {
  const main = $('main');
  if (!app.tab) {
    main.innerHTML = '<div class="gate"><h2>لم يحدد المالك صلاحياتك بعد</h2><p class="note">اطلب من صاحب المصنع تحديد دورك.</p></div>';
    return;
  }
  const tab = app.tab;
  main.innerHTML = '<div class="loading">جارٍ التحميل…</div>';
  try {
    await VIEWS[tab][1].render(main, app);
  } catch (err) {
    if (app.tab === tab) main.innerHTML = `<div class="msg bad">${h(err.message || err)}</div>`;
  }
}

function showLogin() {
  app.user = null;
  app.meta = null;
  app.tab = null;
  renderHeader();
  $('roleLine').textContent = 'مصنع جوان لصناعة وتجارة البلاستيك · الغطايا';
  login.render($('main'), async (user) => {
    app.user = user;
    await start();
  });
}

async function start() {
  await app.reloadMeta();
  const saved = storedTab();
  app.tab = app.meta.tabs.includes(saved) ? saved : app.meta.tabs[0] || null;
  renderHeader();
  await renderView();
}

function applyTheme(t) {
  if (t) document.documentElement.dataset.theme = t;
  else delete document.documentElement.dataset.theme;
}

document.addEventListener('click', async (e) => {
  const tabBtn = e.target.closest('[data-t]');
  if (tabBtn) { app.go(tabBtn.dataset.t); return; }
  if (e.target.closest('#logoutBtn')) {
    await api.post('/auth/logout').catch(() => {});
    showLogin();
    return;
  }
  if (e.target.closest('#themeBtn')) {
    const dark = document.documentElement.dataset.theme === 'dark'
      || (!document.documentElement.dataset.theme && matchMedia('(prefers-color-scheme: dark)').matches);
    const next = dark ? 'light' : 'dark';
    applyTheme(next);
    try { localStorage.setItem('jl-theme', next); } catch { /* ignore */ }
  }
});

setUnauthorizedHandler(() => {
  if (app.user) { toast('انتهت الجلسة. سجّل الدخول من جديد.'); showLogin(); }
});

(async () => {
  try { applyTheme(localStorage.getItem('jl-theme')); } catch { /* ignore */ }
  initTooltips();
  try {
    app.user = await api.get('/auth/me');
    await start();
  } catch (err) {
    if (err.status === 403) {
      $('main').innerHTML = `<div class="gate"><h2>${h(err.message)}</h2><p class="note">اطلب من صاحب المصنع تحديد دورك.</p>`
        + '<button class="btn" id="logoutBtn">خروج</button></div>';
    } else {
      showLogin();
    }
  }
})();

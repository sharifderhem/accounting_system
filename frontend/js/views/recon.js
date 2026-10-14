// Reconciliation (§10): consistency checks, and ticking book lines against an exchanger or custodian statement.
import { api } from '../api.js';
import { alertBox, busy, fmt, h, numOrNull, select, toast, today } from '../util.js';
import { kpi } from '../ui.js';
import { layoutSheet, panelBlocks, saveXlsx } from '../xlsx.js';

const S = { key: '1103', date: today(), statement: '', ticked: null };

export async function render(main, app) {
  const owner = app.meta.user.role === 'owner';
  const [checks, st] = await Promise.all([api.get('/recon/checks'), api.get('/recon/statement', { key: S.key })]);
  if (!S.ticked || S.ticked.key !== S.key) S.ticked = { key: S.key, ids: new Set(st.lines.filter((l) => l.cleared).map((l) => l.lineId)) };
  const d = st.sar ? 2 : 0;
  const book = st.book;
  const cleared = st.lines.filter((l) => S.ticked.ids.has(l.lineId)).reduce((s, l) => s + l.amount, 0);
  const stmt = numOrNull(S.statement);
  const diff = stmt == null ? null : stmt - cleared;
  const cur = st.sar ? 'ر.س' : 'ر.ي';
  main.innerHTML = `<section class="tab"><h2>المطابقات والتسويات</h2>
    <div class="panel"><h3>فحوص التوازن</h3><div style="display:grid;gap:6px">${checks.map((c) => `<div class="split">${alertBox(c.level, c.text)}${c.fxClose && owner ? `<button class="btn sm" data-fxclose="${h(c.fxClose)}">إقفال فرق الصرف</button>` : ''}${c.claim ? `<button class="btn sm" data-claim="${h(c.claim)}">المطالبة</button>` : ''}</div>`).join('')}</div></div>
    <div class="panel" id="stPanel"><h3>مطابقة حساب مع كشف الصرّاف أو العهدة</h3>
      <div class="form"><label class="f">الحساب${select('data-s="key"', st.options.map((o) => [o.key, o.label]), S.key)}</label>
        <label class="f">تاريخ الكشف<input type="date" data-s="date" value="${h(S.date)}"></label>
        <label class="f">الرصيد في الكشف ${cur}<input data-s="statement" inputmode="decimal" class="ltr" value="${h(S.statement)}"></label></div>
      <div class="kpis">${kpi('رصيد الدفاتر', fmt(book, d), cur)}${kpi('المطابَق (المؤشَّر)', fmt(cleared, d), cur)}${kpi('غير مطابَق', fmt(book - cleared, d), cur)}
        ${kpi('الفرق عن الكشف', diff == null ? '—' : fmt(diff, d), diff == null ? 'أدخل رصيد الكشف' : Math.abs(diff) < 0.01 ? '✓ مطابق' : '⚠ حركة ناقصة أو رسوم غير مسجلة')}</div>
      <p class="note">أشّر على كل حركة تظهر في الكشف. الحركات غير المؤشرة تبقى معلّقة حتى تظهر في كشف لاحق. إذا بقي فرق، سجّل الحركة الناقصة أو استخدم «تسجيل حركة ← مطابقة رصيد».</p>
      <div class="tbl"><table><thead><tr><th>✓</th><th>القيد</th><th>التاريخ</th><th>البيان</th><th class="n">المبلغ ${cur}</th></tr></thead><tbody>
      ${st.lines.map((l) => `<tr><td><input type="checkbox" style="width:22px;min-height:22px" data-line="${l.lineId}"${S.ticked.ids.has(l.lineId) ? ' checked' : ''}${owner ? '' : ' disabled'} aria-label="مطابق"></td>
        <td class="num">${l.no}</td><td class="num">${h(l.date)}</td><td>${h(l.memo)}</td><td class="n num">${fmt(l.amount, d)}</td></tr>`).join('') || '<tr><td colspan="5" class="note">لا حركات</td></tr>'}</tbody></table></div>
      <div class="row">${owner ? '<button class="btn sm" id="allBtn">تأشير الكل</button><button class="btn pri" id="saveBtn">حفظ المطابقة</button>' : ''}<button class="btn" id="xlsBtn">⤓ تصدير Excel</button></div>
      ${st.history.length ? `<h3>سجل المطابقات</h3><div class="tbl"><table><thead><tr><th>تاريخ الكشف</th><th class="n">الكشف</th><th class="n">الدفاتر</th><th class="n">الفرق</th><th>بواسطة</th></tr></thead><tbody>
        ${st.history.map((x) => `<tr><td class="num">${h(x.date)}</td><td class="n num">${fmt(x.statement, d)}</td><td class="n num">${fmt(x.book, d)}</td><td class="n num">${fmt(x.diff, d)}</td><td>${h(x.by_label)}</td></tr>`).join('')}</tbody></table></div>` : ''}
    </div></section>`;
  main.querySelectorAll('[data-s]').forEach((el) => el.addEventListener('change', () => { S[el.dataset.s] = el.value; render(main, app); }));
  main.querySelectorAll('[data-line]').forEach((cb) => cb.addEventListener('change', () => {
    const id = +cb.dataset.line;
    if (cb.checked) S.ticked.ids.add(id); else S.ticked.ids.delete(id);
    render(main, app);
  }));
  main.querySelector('#allBtn')?.addEventListener('click', () => { st.lines.forEach((l) => S.ticked.ids.add(l.lineId)); render(main, app); });
  main.querySelector('#saveBtn')?.addEventListener('click', async (e) => {
    const btn = e.currentTarget;
    busy(btn, true);
    try {
      await api.put('/recon/statement', { key: S.key, lineIds: [...S.ticked.ids], date: S.date, statement: numOrNull(S.statement) });
      toast('حُفظت المطابقة');
      S.ticked = null;
      await render(main, app);
    } catch (err) { toast(err.message); busy(btn, false); }
  });
  main.querySelectorAll('[data-fxclose]').forEach((b) => b.addEventListener('click', async () => {
    busy(b, true);
    try { const r = await api.post('/recon/fx-close', { party: b.dataset.fxclose }); toast('أُقفل فرق الصرف – القيد ' + r.no); await app.refresh(); } catch (err) { toast(err.message); busy(b, false); }
  }));
  main.querySelectorAll('[data-claim]').forEach((b) => b.addEventListener('click', () => app.go('reports', { report: 'claim', party: b.dataset.claim })));
  main.querySelector('#xlsBtn').addEventListener('click', () => {
    const label = st.options.find((o) => o.key === S.key)?.label || S.key;
    const panel = main.querySelector('#stPanel').cloneNode(true);
    panel.querySelectorAll('.form, .row, button').forEach((x) => { if (!x.querySelector('table')) x.remove(); });
    panel.querySelector('h3')?.remove();
    saveXlsx(`مطابقة ${label} ${S.date}.xlsx`, [layoutSheet('مطابقة', 'مطابقة ' + label,
      `كشف بتاريخ ${S.date}   ·   رصيد الكشف ${S.statement || '—'}   ·   أُصدر ${today()} بواسطة ${app.meta.user.label}`, panelBlocks(panel))]);
  });
}

// Fixed assets and depreciation (§8).
import { api } from '../api.js';
import { addDays, busy, clearErrors, fmt, h, numOrNull, readForm, select, showError, today, toast } from '../util.js';
import { kpi } from '../ui.js';

const CURS = [['USD', 'دولار'], ['SAR', 'ر.س'], ['YER', 'ر.ي']];
const lastMonthEnd = () => addDays(today().slice(0, 8) + '01', -1);
let depTo = lastMonthEnd();

export async function render(main, app) {
  const d = await api.get('/assets');
  const t = d.totals;
  const fundOpts = [['3101', `المالك ${app.meta.ownerName} (رأس مال)`], ['1103', 'حساب المصنع – يمني'], ['1102', 'حساب المصنع – سعودي'], ['2102', 'قرض']];
  main.innerHTML = `<section class="tab"><h2>الأصول والإهلاك</h2>
    <p class="lead">الإهلاك تكلفة حقيقية: القالب والآلات تفقد قيمتها مع الوقت. حصة كل وردية تُحمَّل على تكلفة الكرتون عند اعتمادها، والإهلاك الشهري يُرحَّل من هنا.</p>
    <div class="kpis">${kpi('تكلفة الأصول', fmt(t.cost), `ر.ي · ${fmt(t.cost / app.meta.settings.fx)} ر.س`)}${kpi('الإهلاك الشهري', fmt(t.monthly), `ر.ي · ${fmt(t.monthly / app.meta.settings.fx)} ر.س`)}
      ${kpi('الإهلاك للكرتون', fmt(t.perCartonSar, 2), `ر.س بإنتاج ${fmt(t.cartonsPerDay)} كرتون/يوم`)}${kpi('مجمع الإهلاك', fmt(t.accumulated), 'ر.ي')}</div>
    <div class="panel"><div class="tbl"><table><thead><tr><th>الأصل</th><th>التاريخ</th><th class="n">التكلفة ر.ي</th><th class="n">العمر سنة</th><th class="n">إهلاك شهري</th><th class="n">المجمع</th><th class="n">القيمة الدفترية</th></tr></thead><tbody>
    ${d.assets.map((a) => `<tr><td>${h(a.name)}${a.cur !== 'YER' && a.amount ? `<div class="note"><span class="num">${fmt(a.amount)}</span> ${a.cur === 'USD' ? 'دولار' : 'ر.س'}</div>` : ''}${a.note ? `<div class="note">${h(a.note)}</div>` : ''}</td>
      <td class="num">${h(a.date)}</td><td class="n">${a.priced ? `<span class="num">${fmt(a.cost)}</span>` : '<span class="chip warn">⚠ بلا سعر</span>'}</td><td class="n num">${fmt(a.life, a.life % 1 ? 1 : 0)}</td>
      <td class="n num">${a.priced ? fmt(a.monthly) : '—'}</td><td class="n num">${fmt(a.accumulated)}</td><td class="n num">${a.priced ? fmt(a.bookValue) : '—'}</td></tr>
      <tr><td colspan="7"><div class="row" data-asset="${h(a.id)}">${a.priced
        ? `<span class="note">العمر</span><input data-k="life" inputmode="decimal" class="ltr" value="${a.life}" style="max-width:80px" aria-label="العمر بالسنوات"><span class="note">سنة</span><button class="btn sm" data-life>حفظ العمر</button>`
        : `<input data-k="amount" inputmode="decimal" class="ltr" placeholder="السعر" style="max-width:130px" aria-label="السعر">${select('data-k="cur" style="max-width:100px" aria-label="العملة"', CURS, 'USD')}
           <input data-k="life" inputmode="decimal" class="ltr" value="${a.life}" style="max-width:80px" aria-label="العمر بالسنوات">${select('data-k="fund" style="max-width:190px" aria-label="مُموّل من"', fundOpts, '3101')}<button class="btn sm pri" data-price>تسجيل السعر</button>`}</div></td></tr>`).join('') || '<tr><td colspan="7" class="note">لا أصول</td></tr>'}
    </tbody></table></div>
    <div class="row"><label class="f">ترحيل الإهلاك حتى<input type="date" id="depTo" value="${h(depTo)}" max="${today()}"></label><button class="btn pri" id="depPost">ترحيل الإهلاك</button></div>
    <p class="note">يُرحَّل الإهلاك من آخر تاريخ رُحّل فيه لكل أصل حتى التاريخ المختار. ما حمّلته الورديات (${fmt(t.absorbed)} ر.ي حتى الآن) يُطرح تلقائياً، والباقي يظهر في «إهلاك الآلات والقوالب» كتكلفة أيام التوقف.</p></div>
    <details class="panel" id="addBox"><summary><b>إضافة أصل</b></summary><div class="form">
      <label class="f">اسم الأصل<input data-field="name"></label><label class="f">تاريخ الشراء<input type="date" data-field="date" value="${today()}"></label>
      <label class="f">السعر (اتركه صفراً إن لم يُعرف)<input data-field="amount" data-num inputmode="decimal" value="0"></label>
      <label class="f">العملة${select('data-field="cur"', CURS, 'USD')}</label>
      <label class="f">العمر الإنتاجي (سنة)<input data-field="life" data-num inputmode="decimal" value="5"></label>
      <label class="f">القيمة المتبقية في نهايته ر.ي<input data-field="salvage" data-num inputmode="decimal" value="0"></label>
      <label class="f">مُموّل من${select('data-field="fund"', fundOpts, '3101')}</label>
      <label class="f">مركز التكلفة${select('data-field="cc"', app.meta.costCenters.map((c) => [c.id, c.name]), 'prod')}</label>
      <label class="f">ملاحظة<input data-field="note"></label></div>
      <div class="row"><button class="btn pri" id="addBtn">إضافة وترحيل</button></div><div id="addMsg" role="status"></div></details>
  </section>`;
  const val = (row, k) => row.querySelector(`[data-k="${k}"]`).value;
  main.querySelectorAll('[data-life]').forEach((b) => b.addEventListener('click', async () => {
    const row = b.closest('[data-asset]');
    busy(b, true);
    try { await api.post(`/assets/${row.dataset.asset}/life`, { life: numOrNull(val(row, 'life')) }); toast('حُفظ العمر؛ الإهلاك القادم بالرقم الجديد'); await render(main, app); } catch (err) { toast(err.message); busy(b, false); }
  }));
  main.querySelectorAll('[data-price]').forEach((b) => b.addEventListener('click', async () => {
    const row = b.closest('[data-asset]');
    busy(b, true);
    try {
      await api.post(`/assets/${row.dataset.asset}/price`, { amount: numOrNull(val(row, 'amount')), cur: val(row, 'cur'), life: numOrNull(val(row, 'life')), fund: val(row, 'fund') });
      toast('سُجل السعر وأُثبت الأصل');
      await app.refresh();
    } catch (err) { toast(err.message); busy(b, false); }
  }));
  main.querySelector('#depTo').addEventListener('change', (e) => { depTo = e.target.value; });
  main.querySelector('#depPost').addEventListener('click', async (e) => {
    const btn = e.currentTarget;
    busy(btn, true);
    try { const r = await api.post('/depreciation', { to: depTo }); toast('رُحّل الإهلاك – القيد ' + r.no); await app.refresh(); } catch (err) { toast(err.message); busy(btn, false); }
  });
  const box = main.querySelector('#addBox');
  main.querySelector('#addBtn').addEventListener('click', async (e) => {
    clearErrors(box);
    const btn = e.currentTarget;
    busy(btn, true);
    try { await api.post('/assets', readForm(box)); toast('أُضيف الأصل'); await app.refresh(); } catch (err) { showError(box, box.querySelector('#addMsg'), err); busy(btn, false); }
  });
}

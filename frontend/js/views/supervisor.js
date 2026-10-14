// Shift supervisor screen (§18): one form, an advance request, and their own recent submissions. No money anywhere.
import { api } from '../api.js';
import { busy, clearErrors, fmt, h, readForm, select, showError, statusChip, today, toast } from '../util.js';

export function shiftFormHtml(app, lastMeter) {
  const reasons = [['', 'لا يوجد'], ...app.meta.downReasons.map((r) => [r, r])];
  const bag = app.meta.settings.bagKg || 25;
  return `<div class="form">
    <label class="f">التاريخ<input type="date" data-field="date" value="${today()}"></label>
    <label class="f">الوردية${select('data-field="shift"', [['صباحية', 'صباحية'], ['مسائية', 'مسائية']], 'صباحية')}</label>
    <label class="f">المشرف<input data-field="byName" value="${h(app.meta.user.label)}"></label>
    <label class="f">عداد الكهرباء قبل<input data-field="meterStart" data-num inputmode="decimal" value="${lastMeter ?? ''}"></label>
    <label class="f">عداد الكهرباء بعد<input data-field="meterEnd" data-num inputmode="decimal"></label>
    <label class="f">أكياس مواد خام مفتوحة (${fmt(bag)} كغ)<input data-field="bags" data-num inputmode="decimal"></label>
    <label class="f">كراتين معبأة<input data-field="cartons" data-num inputmode="decimal"></label>
    <label class="f">التالف كغ<input data-field="scrapKg" data-num inputmode="decimal"></label>
    <label class="f">عداد الضربات قبل (اختياري)<input data-field="shotsStart" data-num inputmode="numeric"></label>
    <label class="f">عداد الضربات بعد (اختياري)<input data-field="shotsEnd" data-num inputmode="numeric"></label>
    <label class="f">دقائق التوقف<input data-field="downMin" data-num inputmode="numeric" placeholder="0"></label>
    <label class="f">سبب التوقف الرئيسي${select('data-field="downReason"', reasons, '')}</label>
  </div>
  <label class="f">ملاحظات<input data-field="notes"></label>`;
}

// Plain-Arabic checks before sending; the server repeats them.
function checkShift(f) {
  if (!f.date) return ['date', 'اختر التاريخ'];
  if (f.meterStart == null) return ['meterStart', 'اكتب قراءة العداد قبل'];
  if (f.meterEnd == null || !(f.meterEnd > f.meterStart)) return ['meterEnd', 'قراءة العداد بعد يجب أن تكون أكبر من قبل'];
  if (f.bags == null || f.bags < 0) return ['bags', 'اكتب عدد الأكياس المفتوحة'];
  if (!(f.cartons > 0)) return ['cartons', 'اكتب عدد الكراتين المعبأة'];
  return null;
}

export function bindShiftForm(box, msgEl, onDone) {
  box.querySelector('[data-send]').addEventListener('click', async (e) => {
    const btn = e.currentTarget;
    clearErrors(box);
    const f = readForm(box);
    const bad = checkShift(f);
    if (bad) { showError(box, msgEl, { field: bad[0], message: bad[1] }); return; }
    busy(btn, true);
    try {
      await api.post('/shifts', f);
      msgEl.innerHTML = `<div class="msg good">✓ أُرسلت وردية ${h(f.shift)} بتاريخ <span class="num">${h(f.date)}</span> للاعتماد. شكراً.</div>`;
      toast('أُرسلت الوردية');
      await onDone();
    } catch (err) {
      showError(box, msgEl, err);
    } finally {
      busy(btn, false);
    }
  });
}

export function advanceFormHtml(app) {
  return `<div class="form">
    <label class="f">اسم العامل<input data-field="employee" list="dlEmp"></label>
    <label class="f">المبلغ ر.ي<input data-field="amount" data-num inputmode="decimal"></label>
    <label class="f">عدد دفعات الخصم<input data-field="installments" data-num inputmode="numeric" value="1"></label>
    <label class="f">السبب<input data-field="reason"></label>
  </div><datalist id="dlEmp">${app.meta.employees.map((n) => `<option>${h(n)}</option>`).join('')}</datalist>
  <div class="row"><button class="btn" data-adv>إرسال طلب السلفة</button></div>`;
}

export function bindAdvanceForm(box, msgEl, app, onDone) {
  box.querySelector('[data-adv]').addEventListener('click', async (e) => {
    const btn = e.currentTarget;
    clearErrors(box);
    const f = readForm(box);
    if (!f.employee) { showError(box, msgEl, { field: 'employee', message: 'اكتب اسم العامل' }); return; }
    if (!(f.amount > 0)) { showError(box, msgEl, { field: 'amount', message: 'اكتب المبلغ' }); return; }
    busy(btn, true);
    try {
      await api.post('/advances', { ...f, installments: f.installments || 1, byName: app.meta.user.label });
      msgEl.innerHTML = '<div class="msg good">✓ أُرسل طلب السلفة للموافقة.</div>';
      await onDone();
    } catch (err) {
      showError(box, msgEl, err);
    } finally {
      busy(btn, false);
    }
  });
}

export async function render(main, app) {
  const [shifts, advances, meta] = await Promise.all([api.get('/shifts'), api.get('/advances'), api.get('/meta')]);
  app.meta = meta;
  main.innerHTML = `<section class="tab"><h2>تسجيل وردية</h2>
    <p class="lead">سجّل أرقام ورديتك عند نهايتها. يراجعها صاحب المصنع ويعتمدها.</p>
    <div class="panel" id="shiftBox">${shiftFormHtml(app, meta.lastMeter)}
      <button class="btn pri big" data-send>إرسال الوردية</button><div id="shiftMsg" role="status"></div></div>
    <div class="panel"><h3>آخر وردياتي</h3>${shifts.length ? `<div class="tbl"><table><thead><tr><th>التاريخ</th><th>الوردية</th><th class="n">كراتين</th><th class="n">أكياس</th><th>الحالة</th></tr></thead><tbody>
      ${shifts.map((s) => `<tr><td class="num">${h(s.date)}</td><td>${h(s.shift)}</td><td class="n num">${fmt(s.cartons)}</td><td class="n num">${fmt(s.bags)}</td><td>${statusChip(s.status)}</td></tr>`).join('')}
      </tbody></table></div>` : '<div class="empty">لا ورديات بعد</div>'}</div>
    <details class="panel" id="advBox"><summary><b>طلب سلفة لعامل</b></summary>${advanceFormHtml(app)}<div id="advMsg" role="status"></div>
      ${advances.length ? `<div class="tbl"><table><thead><tr><th>العامل</th><th class="n">المبلغ ر.ي</th><th>الحالة</th></tr></thead><tbody>${advances.map((a) => `<tr><td>${h(a.employee)}</td><td class="n num">${fmt(a.amount)}</td><td>${statusChip(a.status, a.status === 'approved' ? 'صُرفت' : null)}</td></tr>`).join('')}</tbody></table></div>` : ''}
    </details>
  </section>`;
  const keepMsg = (id) => main.querySelector(id).innerHTML;
  bindShiftForm(main.querySelector('#shiftBox'), main.querySelector('#shiftMsg'), async () => {
    const msg = keepMsg('#shiftMsg');
    await render(main, app);
    main.querySelector('#shiftMsg').innerHTML = msg;
  });
  bindAdvanceForm(main.querySelector('#advBox'), main.querySelector('#advMsg'), app, async () => {
    const msg = keepMsg('#advMsg');
    await render(main, app);
    main.querySelector('#advBox').open = true;
    main.querySelector('#advMsg').innerHTML = msg;
  });
}

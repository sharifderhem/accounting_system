// Owner's shifts tab (§7): pending cards with live cost, flags, approve or reject.
import { api } from '../api.js';
import { alertBox, busy, fmt, h, statusChip, toast } from '../util.js';
import { bindShiftForm, shiftFormHtml } from './supervisor.js';

function costRows(c, kwhPrice) {
  return `<div class="tbl"><table><tbody>
    <tr><td>مواد خام</td><td><span class="num">${fmt(c.rmKg)}</span> كغ × <span class="num">${fmt(c.rmAvg)}</span></td><td class="n num">${fmt(c.rmCost)}</td></tr>
    <tr><td>صبغة</td><td><span class="num">${fmt(c.pigKg * 1000)}</span> غ × <span class="num">${fmt(c.pigAvg / 1000, 2)}</span></td><td class="n num">${fmt(c.pigCost)}</td></tr>
    <tr><td>كراتين وأكياس</td><td><span class="num">${fmt(c.cartons)}</span> × <span class="num">${fmt(c.ctAvg)}</span></td><td class="n num">${fmt(c.ctCost)}</td></tr>
    <tr><td>كهرباء</td><td><span class="num">${fmt(c.kwhMeter)}</span> عداد + <span class="num">${fmt(c.kwhChiller)}</span> مبرد = <span class="num">${fmt(c.kwh)}</span> ك.و × <span class="num">${fmt(kwhPrice)}</span></td><td class="n num">${fmt(c.elec)}</td></tr>
    <tr><td>إهلاك الآلات والقالب</td><td class="note">${c.dep ? 'حصة الوردية من الإهلاك اليومي' : 'لا أصول مسعّرة بعد'}</td><td class="n num">${fmt(c.dep)}</td></tr>
    <tr><td>أجور وإعاشة الوردية</td><td class="note">${c.labor ? 'من مصروفات نفس التاريخ والوردية' : 'لم تُسجَّل مصروفات لهذه الوردية بعد'}</td><td class="n num">${fmt(c.labor)}</td></tr>
    <tr><td>الكفاءة</td><td class="note"><span class="num">${fmt(c.eff * 100)}%</span> من الطاقة القصوى (<span class="num">${fmt(c.maxCartons, 1)}</span> كرتون)${c.downMin ? ` · توقف <span class="num">${fmt(c.downMin)}</span> د (${h(c.downReason || 'بدون سبب')}) = <span class="num">${fmt(c.lostDown, 1)}</span> كرتون` : ''}</td><td></td></tr>
    <tr class="tot"><td>الإجمالي ر.ي</td><td><span class="num">${fmt(c.per)}</span> ر.ي = <span class="num">${fmt(c.perSar, 2)}</span> ر.س للكرتون · الهامش <span class="num">${fmt(c.marginSar, 2)}</span> ر.س</td><td class="n num">${fmt(c.total)}</td></tr>
  </tbody></table></div>`;
}

function card(s, app) {
  const c = s.cost;
  const head = `<div class="split"><h3>وردية ${h(s.shift)} · <span class="num">${h(s.date)}</span></h3><span class="row">${statusChip(s.status)}${s.byName ? `<span class="chip">${h(s.byName)}</span>` : ''}</span></div>
    <div class="note">${s.downMin ? `توقف <b class="num">${fmt(s.downMin)}</b> د (${h(s.downReason || '')}) · ` : ''}كراتين <b class="num">${fmt(s.cartons)}</b> · أكياس <b class="num">${fmt(s.bags)}</b> · تالف <b class="num">${fmt(s.scrapKg)}</b> كغ · عداد <span class="num">${fmt(s.meterStart)} → ${fmt(s.meterEnd)}</span>${s.notes ? ` · ${h(s.notes)}` : ''}</div>`;
  if (s.status === 'pending' && c) {
    return `<div class="card">${head}${costRows(c, c.kwhPrice)}
      ${c.flags.length ? `<div style="display:grid;gap:6px">${c.flags.map((f) => alertBox('warn', f)).join('')}</div>` : '<div class="msg good">✓ الأرقام ضمن المعدلات الطبيعية</div>'}
      <div class="row"><button class="btn ok" data-approve="${s.id}"${c.cartons ? '' : ' disabled'}>✓ اعتماد وترحيل</button><button class="btn no" data-reject="${s.id}">✕ رفض</button></div></div>`;
  }
  return `<div class="card ${s.status}">${head}${c ? `<div class="note">التكلفة <span class="num">${fmt(c.total)}</span> ر.ي · <span class="num">${fmt(c.perSar, 2)}</span> ر.س للكرتون</div>` : ''}</div>`;
}

export async function render(main, app) {
  const list = await api.get('/shifts');
  main.innerHTML = `<section class="tab"><h2>الورديات</h2>
    <p class="lead">المشرفون يرسلون أرقام الورديات، وعند اعتمادك يُرحَّل قيد الإنتاج: المواد والكراتين والكهرباء وأجور الوردية والإهلاك تتحول إلى مخزون غطايا تامة بتكلفتها الفعلية.</p>
    <details class="panel" id="ownShift"><summary><b>تسجيل وردية بنفسك</b></summary>${shiftFormHtml(app, app.meta.lastMeter)}
      <button class="btn pri" data-send>إرسال للاعتماد</button><div id="owMsg" role="status"></div></details>
    <div id="shMsg" role="status"></div>
    ${list.length ? list.map((s) => card(s, app)).join('') : '<div class="empty">لا ورديات بعد. أنشئ حسابات «مشرف وردية» من الإعدادات ليسجلوا من جوالاتهم.</div>'}
  </section>`;
  bindShiftForm(main.querySelector('#ownShift'), main.querySelector('#owMsg'), () => app.refresh());
  main.querySelectorAll('[data-approve]').forEach((b) => b.addEventListener('click', async () => {
    busy(b, true);
    try {
      const r = await api.post(`/shifts/${b.dataset.approve}/approve`);
      toast(`اعتُمدت الوردية ورُحّل قيد الإنتاج ${r.no}`);
      await app.refresh();
      main.querySelector('#shMsg').innerHTML = `<div class="msg good">✓ اعتُمدت الوردية · قيد الإنتاج رقم <span class="num">${r.no}</span></div>`;
    } catch (err) { toast(err.message); busy(b, false); }
  }));
  main.querySelectorAll('[data-reject]').forEach((b) => b.addEventListener('click', async () => {
    busy(b, true);
    try { await api.post(`/shifts/${b.dataset.reject}/reject`); toast('رُفضت الوردية'); await app.refresh(); } catch (err) { toast(err.message); busy(b, false); }
  }));
}

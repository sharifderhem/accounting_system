// Requests (§6): payment requests needing a second person, and employee advance requests.
import { api } from '../api.js';
import { busy, fmt, h, select, statusChip, toast } from '../util.js';
import { entryPreview } from '../ui.js';
import { advanceFormHtml, bindAdvanceForm } from './supervisor.js';

let confirming = null;

function requestCard(r, app) {
  const status = r.status === 'approved' ? statusChip('approved', 'معتمد ومرحّل') : statusChip(r.status);
  const decided = r.decidedByLabel ? ` · ${r.status === 'approved' ? 'اعتمده' : r.status === 'withdrawn' ? 'سحبه' : 'رفضه'} ${h(r.decidedByLabel)}` : '';
  let actions = '';
  if (r.canDecide) {
    actions = confirming === r.id
      ? `<div class="confirm"><span>سيُرحَّل القيد باسمك كمعتمد.</span><button class="btn sm ok" data-rqok="${r.id}">✓ تأكيد الاعتماد</button><button class="btn sm" data-rqcancel>إلغاء</button></div>`
      : `<div class="row"><button class="btn ok" data-rqa="${r.id}">✓ موافقة وترحيل</button><button class="btn no" data-rqr="${r.id}">✕ رفض</button></div>`;
  } else if (r.status === 'pending' && r.mine) {
    actions = '<div class="row"><span class="msg">⏳ بانتظار موافقة الطرف الآخر</span><button class="btn sm" data-rqw="' + r.id + '">سحب الطلب</button></div>';
  }
  return `<div class="card ${r.status}"><div class="split"><h3>${h(r.summary)}</h3>${status}</div>
    <div class="note">أنشأه ${h(r.createdByLabel)} · <span class="num">${h((r.createdAt || '').slice(0, 16).replace('T', ' '))}</span> · المبلغ <span class="num">${fmt(r.amount)}</span> ر.ي${decided}${r.postedNos.length ? ` · القيد <span class="num">${r.postedNos.join('، ')}</span>` : ''}</div>
    ${r.entries.map((e) => entryPreview(e, app.meta.accounts, app.meta.sources)).join('')}${actions}</div>`;
}

function advanceCard(a, app) {
  const custodians = app.meta.parties.filter((p) => p.type === 'custodian').map((p) => p.name);
  const status = statusChip(a.status, a.status === 'approved' ? 'صُرفت' : null);
  const decide = a.canDecide ? `<div class="row">${select(`id="src-${a.id}" style="max-width:200px"`, [['1104', 'من عهدة'], ['1101', 'من الصندوق'], ['1103', 'من حساب المصنع اليمني']], '1104')}
      <input id="cus-${a.id}" list="dlCus2" placeholder="صاحب العهدة" value="${h(custodians[0] || '')}" style="max-width:170px">
      <button class="btn sm ok" data-advok="${a.id}">✓ موافقة وصرف</button><button class="btn sm no" data-advno="${a.id}">✕ رفض</button></div>` : '';
  return `<div class="card ${a.status}"><div class="split"><b>${h(a.employee)} · <span class="num">${fmt(a.amount)}</span> ر.ي</b>${status}</div>
    <div class="note">${h(a.reason || '')}${a.reason ? ' · ' : ''}تُخصم على ${a.installments} دفعة · طلبها ${h(a.createdByLabel)}${a.balance ? ` · رصيد سلفه الحالي <span class="num">${fmt(a.balance)}</span> ر.ي` : ''}${a.entryNo ? ` · القيد <span class="num">${a.entryNo}</span>` : ''}</div>${decide}</div>`;
}

export async function render(main, app) {
  const [reqs, advs] = await Promise.all([api.get('/requests'), api.get('/advances')]);
  const custodians = app.meta.parties.filter((p) => p.type === 'custodian').map((p) => p.name);
  main.innerHTML = `<section class="tab">
    <h2>طلبات الصرف</h2>
    <p class="lead">الحوالات الصادرة والمصروفات وصرف العملة لا تُرحَّل إلا بموافقة شخص آخر غير الذي أنشأها. من أنشأ الطلب لا يستطيع اعتماده.</p>
    ${reqs.length ? reqs.map((r) => requestCard(r, app)).join('') : '<div class="empty">لا طلبات صرف</div>'}
    <h2>طلبات السلف</h2>
    <div class="panel">${advs.length ? advs.map((a) => advanceCard(a, app)).join('') : '<p class="note">لا طلبات سلف.</p>'}
      <details id="advBox"><summary class="note">طلب سلفة جديد</summary>${advanceFormHtml(app)}<div id="advMsg" role="status"></div></details>
      <datalist id="dlCus2">${custodians.map((c) => `<option>${h(c)}</option>`).join('')}</datalist></div>
  </section>`;
  const act = async (btn, fn, done) => {
    busy(btn, true);
    try { const r = await fn(); confirming = null; toast(done(r)); await app.refresh(); } catch (err) { toast(err.message); busy(btn, false); }
  };
  main.querySelectorAll('[data-rqa]').forEach((b) => b.addEventListener('click', () => { confirming = +b.dataset.rqa; render(main, app); }));
  main.querySelectorAll('[data-rqcancel]').forEach((b) => b.addEventListener('click', () => { confirming = null; render(main, app); }));
  main.querySelectorAll('[data-rqok]').forEach((b) => b.addEventListener('click', () => act(b, () => api.post(`/requests/${b.dataset.rqok}/approve`),
    (r) => 'اعتُمد ورُحّل القيد ' + r.posted.map((p) => p.no).join('، '))));
  main.querySelectorAll('[data-rqr]').forEach((b) => b.addEventListener('click', () => act(b, () => api.post(`/requests/${b.dataset.rqr}/reject`), () => 'رُفض الطلب')));
  main.querySelectorAll('[data-rqw]').forEach((b) => b.addEventListener('click', () => act(b, () => api.post(`/requests/${b.dataset.rqw}/withdraw`), () => 'سُحب الطلب')));
  main.querySelectorAll('[data-advok]').forEach((b) => b.addEventListener('click', () => {
    const id = b.dataset.advok;
    act(b, () => api.post(`/advances/${id}/approve`, { source: main.querySelector('#src-' + id).value, custodian: main.querySelector('#cus-' + id).value.trim() }),
      (r) => 'صُرفت السلفة – القيد ' + r.no);
  }));
  main.querySelectorAll('[data-advno]').forEach((b) => b.addEventListener('click', () => act(b, () => api.post(`/advances/${b.dataset.advno}/reject`), () => 'رُفض طلب السلفة')));
  bindAdvanceForm(main.querySelector('#advBox'), main.querySelector('#advMsg'), app, async () => {
    await app.refresh();
    toast('أُرسل طلب السلفة');
  });
}

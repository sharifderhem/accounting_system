// Journal (§16): filters, entries with maker/checker, reversal by the owner, Excel export.
import { api } from '../api.js';
import { busy, fmt, h, select, toast, today } from '../util.js';
import { entryCard } from '../ui.js';
import { layoutSheet, saveXlsx } from '../xlsx.js';

const F = { frm: '', to: '', src: '', party: '', account: '', cur: '', q: '' };
let limit = 60;
let confirming = null;

export async function render(main, app) {
  const m = app.meta;
  const data = await api.get('/journal', { ...F, limit });
  const owner = m.user.role === 'owner';
  const parties = m.parties.map((p) => p.name);
  main.innerHTML = `<section class="tab"><h2>قيود اليومية</h2>
    <div class="panel" id="jFilters"><div class="form">
      <label class="f">من تاريخ<input type="date" data-j="frm" value="${h(F.frm)}"></label><label class="f">إلى تاريخ<input type="date" data-j="to" value="${h(F.to)}"></label>
      <label class="f">النوع${select('data-j="src"', [['', 'الكل'], ...Object.entries(m.sources)], F.src)}</label>
      <label class="f">الاسم / الطرف<input data-j="party" list="dlJP" value="${h(F.party)}"></label>
      <label class="f">الحساب${select('data-j="account"', [['', 'كل الحسابات'], ...Object.entries(m.accounts).map(([k, v]) => [k, `${k} ${v.name}`])], F.account)}</label>
      <label class="f">العملة${select('data-j="cur"', [['', 'الكل'], ['SAR', 'فيها ريال سعودي'], ['YER', 'ريال يمني فقط']], F.cur)}</label>
      <label class="f">بحث (بيان، مرجع، رقم قيد)<input data-j="q" value="${h(F.q)}"></label></div>
      <datalist id="dlJP">${parties.map((p) => `<option>${h(p)}</option>`).join('')}</datalist>
      <div class="split"><span class="note"><span class="num">${data.total}</span> قيد · مجموع المدين <span class="num">${fmt(data.debitTotal)}</span> ر.ي (بدون المعكوس)</span>
        <span class="row"><button class="btn sm" id="jClear">مسح الفلاتر</button><button class="btn sm" id="jXls">⤓ تصدير Excel</button></span></div></div>
    <p class="lead">لا يُحذف قيد بعد ترحيله.${owner ? ' للتصحيح استخدم «عكس القيد» ثم سجّل الحركة الصحيحة.' : ''}</p>
    <div style="display:grid;gap:10px">${data.entries.map((e) => entryCard(e, m.accounts, m.sources, { canReverse: owner, confirming: confirming === e.id })).join('') || '<div class="empty">لا قيود تطابق الفلاتر</div>'}</div>
    ${data.total > data.entries.length ? '<div class="row"><button class="btn" id="jMore">عرض المزيد</button></div>' : ''}</section>`;
  main.querySelectorAll('[data-j]').forEach((el) => el.addEventListener('change', () => { F[el.dataset.j] = el.value.trim(); limit = 60; render(main, app); }));
  main.querySelector('#jClear').addEventListener('click', () => { Object.keys(F).forEach((k) => { F[k] = ''; }); render(main, app); });
  main.querySelector('#jMore')?.addEventListener('click', () => { limit += 60; render(main, app); });
  main.querySelectorAll('[data-rev]').forEach((b) => b.addEventListener('click', () => { confirming = +b.dataset.rev; render(main, app); }));
  main.querySelectorAll('[data-revno]').forEach((b) => b.addEventListener('click', () => { confirming = null; render(main, app); }));
  main.querySelectorAll('[data-revok]').forEach((b) => b.addEventListener('click', async () => {
    busy(b, true);
    try {
      const r = await api.post(`/entries/${b.dataset.revok}/reverse`);
      confirming = null;
      toast('رُحّل القيد العكسي ' + r.no);
      await app.refresh();
    } catch (err) { toast(err.message); busy(b, false); }
  }));
  main.querySelector('#jXls').addEventListener('click', async (e) => {
    const btn = e.currentTarget;
    busy(btn, true);
    try {
      const all = await api.get('/journal', { ...F, limit: 5000 });
      const rows = [];
      let D = 0, C = 0;
      for (const en of all.entries.slice().reverse()) {
        for (const l of en.lines) {
          rows.push([en.no, en.date, m.sources[en.src] || en.src, en.ref || '', l.memo || en.memo, `${l.a} ${m.accounts[l.a]?.name || ''}`, l.party || '',
            l.d || '', l.c || '', l.cur === 'SAR' ? l.fc : '', en.status === 'reversed' ? 'معكوس' : en.reverses_id ? 'قيد عكسي' : 'مرحّل',
            en.created_by_label || '', en.approved_by_label || '']);
          D += l.d || 0;
          C += l.c || 0;
        }
      }
      const filt = [F.frm || F.to ? `من ${F.frm || 'البداية'} إلى ${F.to || today()}` : 'كل الفترات', F.party && 'الطرف: ' + F.party, F.account && 'الحساب: ' + F.account,
        F.src && 'النوع: ' + m.sources[F.src], F.cur && 'العملة: ' + F.cur].filter(Boolean).join('   ·   ');
      saveXlsx(`قيود اليومية ${today()}.xlsx`, [layoutSheet('القيود', 'قيود اليومية', `${filt}   ·   ${all.total} قيد   ·   أُصدر ${today()} بواسطة ${m.user.label}`, [{
        type: 'table', centerFirst: true, empty: 'لا بيانات',
        head: ['رقم القيد', 'التاريخ', 'النوع', 'المرجع', 'البيان', 'الحساب', 'الطرف', 'مدين ر.ي', 'دائن ر.ي', 'ر.س', 'الحالة', 'أنشأه', 'اعتمده'],
        rows, foot: [['الإجمالي', '', '', '', '', '', '', Math.round(D * 100) / 100, Math.round(C * 100) / 100, '', '', '', '']],
      }])]);
    } catch (err) { toast(err.message); } finally { busy(btn, false); }
  });
}

// Record a transaction (§5): one form per kind, preview of the entry, then save (or a request under dual control).
import { api } from '../api.js';
import { busy, clearErrors, fmt, h, numOrNull, readForm, select, showError, today, toast } from '../util.js';
import { entryPreview } from '../ui.js';

const KINDS = [
  ['sale', 'فاتورة مبيعات', 'بعت غطايا لعميل بالآجل.'],
  ['in', 'حوالة واردة', 'وصلك مال: سداد عميل، تمويل من المالك، قرض أو إيراد آخر.'],
  ['out', 'حوالة صادرة', 'دفعت مالاً: شراء مواد، سداد مورد، عهدة، كهرباء، مصروف…'],
  ['exp', 'مصروفات يومية', 'أجور وإعاشة ونثريات اليوم، من العهدة أو الصندوق أو المالك.'],
  ['fx', 'صرف عملة', 'صرفت ريالاً سعودياً إلى يمني عند الصرّاف.'],
  ['adj', 'مطابقة رصيد', 'الرصيد الحقيقي يختلف عن الدفاتر.'],
  ['count', 'جرد مخزون', 'عددت المخزون فعلياً.'],
  ['xfer', 'تحويل بين حساباتي', 'نقلت مالاً من حساب للمصنع إلى حساب آخر له.'],
  ['manual', 'قيد يدوي', 'قيد حر للحالات الخاصة.'],
];

let kind = 'sale';
let lastMsg = '';

const opt = (obj) => Object.entries(obj);
const partyList = (app, type) => app.meta.parties.filter((p) => !type || p.type === type).map((p) => p.name);
const datalist = (id, names) => `<datalist id="${id}">${names.map((n) => `<option>${h(n)}</option>`).join('')}</datalist>`;
const numIn = (field, label, value = '', extra = '') => `<label class="f">${label}<input data-field="${field}" data-num inputmode="decimal" value="${h(value)}" ${extra}></label>`;
const textIn = (field, label, value = '', extra = '') => `<label class="f">${label}<input data-field="${field}" value="${h(value)}" ${extra}></label>`;
const dateIn = () => `<label class="f">التاريخ<input type="date" data-field="date" value="${today()}"></label>`;
const curSel = (def) => `<label class="f">العملة${select('data-field="cur"', [['SAR', 'ريال سعودي'], ['YER', 'ريال يمني']], def)}</label>`;
const viaSel = (app, field = 'via', label = 'عبر', def = 'exch') => `<label class="f">${label}${select(`data-field="${field}"`, opt(app.meta.via), def)}</label>`;
const ccSel = (app, attrs, def) => select(attrs, app.meta.costCenters.map((c) => [c.id, c.name]), def);

function formHtml(app, stock) {
  const s = app.meta.settings;
  const owner = app.meta.user.role === 'owner';
  const F = {
    sale: () => `<div class="form">${dateIn()}${textIn('ref', 'رقم الفاتورة', '', 'class="ltr"')}
        ${textIn('party', 'العميل', '', 'list="dlCust"')}${numIn('qty', 'عدد الكراتين')}${numIn('price', 'سعر الكرتون ر.س', s.priceSar)}${numIn('rate', 'سعر الصرف (ر.ي لكل ر.س)', s.fx)}</div>
        ${datalist('dlCust', partyList(app, 'customer'))}
        ${owner ? '<label class="check"><input type="checkbox" data-field="overLimit"> أوافق على البيع حتى لو تجاوز العميل سقف الائتمان</label>' : ''}
        <p class="note">يُقيَّد على حساب العميل بالريال السعودي، وتُقيَّد تكلفة المبيعات تلقائياً. سجّل السداد لاحقاً كحوالة واردة.</p>`,
    in: () => `<div class="form">${dateIn()}${textIn('ref', 'رقم الحوالة', '', 'class="ltr"')}${textIn('sender', 'المرسل')}
        ${numIn('amount', 'المبلغ')}${curSel('SAR')}${numIn('rate', 'سعر الصرف', s.fx)}${viaSel(app)}
        <label class="f">تُخصَّص لـ${select('data-field="purpose"', [['customer', 'سداد من عميل'], ['owner', 'تمويل من المالك'], ['loan', 'قرض أو سلفة'], ['other', 'إيراد آخر']], 'customer')}</label>
        ${textIn('party', 'العميل / الطرف', '', 'list="dlAll"')}${numIn('sar', 'يعادل من ذمة العميل ر.س', '', 'placeholder="للحوالة اليمنية"')}</div>
        ${datalist('dlAll', partyList(app))}
        <p class="note">لحوالة يمنية تسدد ذمة بالسعودي اكتب ما تعادله بالسعودي؛ الفرق يُقيَّد فرق صرف تلقائياً.</p>`,
    out: () => `<div class="form">${dateIn()}${textIn('ref', 'رقم الحوالة', '', 'class="ltr"')}${textIn('beneficiary', 'المستفيد')}
        <label class="f">الغرض${select('data-field="purpose"', opt(app.meta.outPurposes), 'rm')}</label>
        ${numIn('amount', 'المبلغ')}${curSel('YER')}${numIn('rate', 'سعر الصرف', s.fx)}${viaSel(app)}
        <label class="f">مركز التكلفة${ccSel(app, 'data-field="cc"', 'prod')}</label>${numIn('fee', 'رسوم التحويل ر.ي')}
        ${s.vatEnabled ? numIn('vat', 'ضريبة مدخلات ضمن المبلغ (بعملة الحوالة)') : ''}
        ${numIn('qty', 'الكمية (كغ للمواد والصبغة، عدد للكراتين)')}${textIn('party', 'الطرف (صاحب العهدة، المورد، العامل…)', '', 'list="dlAll"')}</div>
        ${datalist('dlAll', partyList(app))}`,
    exp: () => {
      const hasCustody = partyList(app, 'custodian').length > 0;
      return `<div class="form">${dateIn()}
        <label class="f">دُفعت من${select('data-field="paidFrom"', [['3101', `المالك (${app.meta.ownerName}) مباشرة`], ['1104', 'عهدة موظف'], ['1101', 'الصندوق']], hasCustody ? '1104' : '3101')}</label>
        ${textIn('party', 'صاحب العهدة (إن كانت من عهدة)', partyList(app, 'custodian')[0] || '', 'list="dlCus"')}</div>
        ${datalist('dlCus', partyList(app, 'custodian'))}
        <div class="lines-ed" id="expLines"></div>
        <div class="row"><button class="btn sm" id="addLine" type="button">+ سطر</button><span class="note" id="linesTot"></span></div>
        <p class="note">الأجور والإعاشة المسجلة على وردية صباحية أو مسائية تُحمَّل على تكلفة إنتاج تلك الوردية. لخصم سلفة اختر «خصم سلفة» واكتب اسم العامل في البيان.</p>`;
    },
    fx: () => `<div class="form">${dateIn()}${numIn('amount', 'مبلغ الريال السعودي المصروف')}${numIn('rate', 'سعر الصرف الفعلي', s.fx)}${textIn('ref', 'المرجع', '', 'class="ltr"')}</div>
        <p class="note">يحوّل من حساب السعودي إلى حساب اليمني. الفرق عن متوسط سعر الدفاتر يُقيَّد فرق صرف.</p>`,
    adj: () => `<div class="form">${dateIn()}
        <label class="f">الحساب${select('data-field="account"', [['1103', 'حساب المصنع – يمني'], ['1102', 'حساب المصنع – سعودي (بالسعودي)'], ['1101', 'الصندوق'], ['1104', 'عهدة'], ['1107', 'محفظة جيب'], ['1108', 'محفظة إيزي'], ['1109', 'محفظة فلوسك']], '1103')}</label>
        ${textIn('party', 'صاحب العهدة (للعهدة فقط)', '', 'list="dlCus"')}${numIn('actual', 'الرصيد الفعلي الآن')}
        <label class="f">الفرق يُقيَّد على${select('data-field="counter"', [['3101', 'تمويل أو سحب المالك'], ['5203', 'مصروفات غير موثقة'], ['4201', 'إيراد آخر']], '3101')}</label></div>
        ${datalist('dlCus', partyList(app, 'custodian'))}
        <p class="note">اكتب الرصيد كما تراه عند الصرّاف أو في الصندوق؛ يحسب النظام الفرق عن الدفاتر ويقيّده.</p>`,
    count: () => `<div class="form">${dateIn()}
        ${numIn('rm', 'مواد خام موجودة فعلاً (كغ)', '', `placeholder="${fmt(stock?.['1301'] ?? 0)}"`)}
        ${numIn('pig', 'صبغة موجودة (كغ)', '', `placeholder="${fmt(stock?.['1302'] ?? 0, 2)}"`)}
        ${numIn('ct', 'كراتين فارغة موجودة', '', `placeholder="${fmt(stock?.['1303'] ?? 0)}"`)}
        ${numIn('fg', 'كراتين غطايا تامة في المخزن', '', `placeholder="${fmt(stock?.['1305'] ?? 0)}"`)}</div>
        <p class="note">الرقم الباهت هو رصيد الدفاتر. اترك الحقل فارغاً إذا لم تَعُدّه. الفرق يُقيَّد على «فروق جرد ومواد التشغيل التجريبي».</p>`,
    xfer: () => `<div class="form">${dateIn()}${viaSel(app, 'fromVia', 'من', 'exch')}${viaSel(app, 'toVia', 'إلى', 'jeeb')}
        ${numIn('amount', 'المبلغ')}${curSel('YER')}${numIn('fee', 'رسوم ر.ي')}${textIn('ref', 'المرجع', '', 'class="ltr"')}</div>
        <p class="note">نقل مال بين حسابات المصنع نفسه. لا يؤثر على الأرباح؛ الرسوم فقط مصروف.</p>`,
    manual: () => `<div class="form">${dateIn()}${textIn('memo', 'البيان')}${textIn('ref', 'المرجع', '', 'class="ltr"')}</div>
        <div class="lines-ed" id="manLines"></div>${datalist('dlAll2', partyList(app))}
        <div class="row"><button class="btn sm" id="addLine" type="button">+ سطر</button><span class="note" id="linesTot"></span></div>`,
  };
  return F[kind]();
}

function expRow(app, i) {
  const cats = opt(app.meta.expCats);
  return `<div class="lr"><label class="f">البيان<input data-field="lines.${i}.desc" data-k="desc"></label>
    <label class="f">الفئة${select(`data-field="lines.${i}.cat" data-k="cat"`, cats, 'wages')}</label>
    <label class="f">الوردية${select(`data-field="lines.${i}.shift" data-k="shift"`, [['صباحية', 'صباحية'], ['مسائية', 'مسائية'], ['عام', 'عام']], 'صباحية')}</label>
    <label class="f">مركز التكلفة${ccSel(app, `data-field="lines.${i}.cc" data-k="cc"`, 'prod')}</label>
    <label class="f">المبلغ ر.ي<input data-field="lines.${i}.amount" data-k="amount" inputmode="decimal"></label>
    <button class="btn sm no" data-del type="button" aria-label="حذف السطر">×</button></div>`;
}

function manRow(app, i) {
  const accs = Object.entries(app.meta.accounts).map(([k, v]) => [k, `${k} ${v.name}`]);
  return `<div class="lr man"><label class="f">الحساب${select(`data-field="lines.${i}.a" data-k="a"`, accs, '')}</label>
    <label class="f">الطرف<input data-field="lines.${i}.party" data-k="party" list="dlAll2"></label>
    <label class="f">مدين<input data-field="lines.${i}.d" data-k="d" inputmode="decimal"></label>
    <label class="f">دائن<input data-field="lines.${i}.c" data-k="c" inputmode="decimal"></label>
    <button class="btn sm no" data-del type="button" aria-label="حذف السطر">×</button></div>`;
}

function renumber(box) {
  [...box.children].forEach((row, i) => row.querySelectorAll('[data-k]').forEach((el) => { el.dataset.field = `lines.${i}.${el.dataset.k}`; }));
}

function readLines(box, numeric) {
  return [...box.children].map((row) => {
    const o = {};
    row.querySelectorAll('[data-k]').forEach((el) => { o[el.dataset.k] = numeric.includes(el.dataset.k) ? numOrNull(el.value) : el.value.trim(); });
    return o;
  });
}

function bindLines(app, panel) {
  const box = panel.querySelector('#expLines') || panel.querySelector('#manLines');
  if (!box) return;
  const isExp = box.id === 'expLines';
  const row = (i) => (isExp ? expRow(app, i) : manRow(app, i));
  box.innerHTML = [0, 1, 2].slice(0, isExp ? 3 : 2).map(row).join('');
  const total = () => {
    const lines = readLines(box, ['amount', 'd', 'c']);
    if (isExp) {
      const t = lines.reduce((s, l) => s + (l.cat === 'advrep' ? -1 : 1) * (l.amount || 0), 0);
      panel.querySelector('#linesTot').textContent = `الصافي ${fmt(t)} ر.ي`;
    } else {
      const d = lines.reduce((s, l) => s + (l.d || 0), 0), c = lines.reduce((s, l) => s + (l.c || 0), 0);
      panel.querySelector('#linesTot').textContent = `مدين ${fmt(d, 2)} · دائن ${fmt(c, 2)}${Math.abs(d - c) > 0.01 ? ' · ⚠ غير متوازن' : ' · ✓ متوازن'}`;
    }
  };
  panel.querySelector('#addLine').addEventListener('click', () => { box.insertAdjacentHTML('beforeend', row(box.children.length)); });
  box.addEventListener('click', (e) => { if (e.target.closest('[data-del]')) { e.target.closest('.lr').remove(); renumber(box); total(); } });
  box.addEventListener('input', total);
}

function collect(panel) {
  const f = readForm(panel);
  const exp = panel.querySelector('#expLines'), man = panel.querySelector('#manLines');
  if (exp) f.lines = readLines(exp, ['amount']).filter((l) => l.amount);
  if (man) f.lines = readLines(man, ['d', 'c']).filter((l) => l.d || l.c).map((l) => ({ ...l, d: l.d || 0, c: l.c || 0 }));
  return f;
}

export async function render(main, app) {
  const forms = app.meta.forms;
  if (!forms.includes(kind)) kind = forms[0];
  let stock = null;
  if (kind === 'count') {
    const inv = await api.get('/reports/inv');
    stock = Object.fromEntries(inv.rows.map((r) => [r.account, r.qty]));
  }
  const needs = app.meta.needsApproval[kind];
  const desc = KINDS.find(([k]) => k === kind)[2];
  main.innerHTML = `<section class="tab"><h2>تسجيل حركة</h2>
    <div class="seg" id="kinds">${KINDS.filter(([k]) => forms.includes(k)).map(([k, l]) => `<button data-kind="${k}" aria-pressed="${k === kind}">${l}</button>`).join('')}</div>
    <div class="panel" id="formPanel"><p class="note">${h(desc)}</p>${formHtml(app, stock)}
      <div id="preview"></div>
      <div class="row"><button class="btn" id="prevBtn">معاينة القيد</button><button class="btn pri" id="saveBtn">${needs ? 'إرسال طلب للموافقة' : 'حفظ وترحيل'}</button></div>
      ${needs ? '<p class="note">هذه الحركة تحتاج موافقة شخص آخر قبل ترحيلها (الرقابة المزدوجة).</p>' : ''}
      <div id="moveMsg" role="status">${lastMsg}</div></div>
  </section>`;
  const panel = main.querySelector('#formPanel');
  bindLines(app, panel);
  main.querySelector('#kinds').addEventListener('click', (e) => {
    const b = e.target.closest('[data-kind]');
    if (!b) return;
    kind = b.dataset.kind;
    lastMsg = '';
    render(main, app);
  });
  const msg = panel.querySelector('#moveMsg');
  panel.querySelector('#prevBtn').addEventListener('click', async (e) => {
    clearErrors(panel);
    const btn = e.currentTarget;
    busy(btn, true);
    try {
      const res = await api.post(`/transactions/${kind}/preview`, collect(panel));
      panel.querySelector('#preview').innerHTML = `<h3>هذا ما سيُسجَّل</h3>${res.entries.map((x) => entryPreview(x, app.meta.accounts, app.meta.sources)).join('')}`;
      msg.innerHTML = '';
    } catch (err) {
      panel.querySelector('#preview').innerHTML = '';
      showError(panel, msg, err);
    } finally { busy(btn, false); }
  });
  panel.querySelector('#saveBtn').addEventListener('click', async (e) => {
    clearErrors(panel);
    const btn = e.currentTarget;
    busy(btn, true);
    try {
      const res = await api.post(`/transactions/${kind}`, collect(panel));
      if (res.request) {
        lastMsg = `<div class="msg acc">⏳ أُرسل الطلب رقم <span class="num">${res.request.id}</span> للموافقة. يُرحَّل القيد بعد موافقة الطرف الآخر من تبويب «الطلبات».</div>`;
        toast('أُرسل الطلب للموافقة');
      } else {
        lastMsg = `<div class="msg good">✓ حُفظ ورُحّل · القيد رقم <span class="num">${res.posted.map((p) => p.no).join(' و ')}</span></div>`;
        toast('حُفظ ورُحّل');
      }
      await app.refresh();
    } catch (err) {
      showError(panel, msg, err);
      busy(btn, false);
    }
  });
}

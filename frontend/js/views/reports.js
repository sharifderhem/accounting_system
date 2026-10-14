// Reports (§11): 17 reports, each with its filters and an Excel export of exactly what is on screen.
import { api } from '../api.js';
import { alertBox, busy, fmt, h, numOrNull, select, today, toast } from '../util.js';
import { costTable, kpi } from '../ui.js';
import { layoutSheet, panelBlocks, saveXlsx } from '../xlsx.js';

const LIST = [['claim', 'مطالبة مالية'], ['tb', 'ميزان المراجعة'], ['is', 'قائمة الدخل'], ['party', 'كشف حساب طرف'], ['ledger', 'دفتر الأستاذ'],
  ['cost', 'تكلفة الإنتاج'], ['cash', 'التدفق النقدي'], ['aging', 'مخاطر العملاء'], ['fxrisk', 'مخاطر العملة'], ['be', 'نقطة التعادل'],
  ['budget', 'الموازنة'], ['eff', 'الكفاءة والتوقف'], ['cc', 'مراكز التكلفة'], ['fxpos', 'مركز العملة'], ['vat', 'الضريبة'], ['zakat', 'الزكاة'], ['inv', 'المخزون']];
const RANGED = ['is', 'party', 'ledger', 'eff', 'cc', 'vat'];

const P = { kind: 'claim', frm: today().slice(0, 8) + '01', to: today(), party: '', account: '1103', cur: '', month: today().slice(0, 7), horizon: 14, cartons: '' };

const n0 = (x) => `<span class="num">${fmt(x)}</span>`;
const n2 = (x) => `<span class="num">${fmt(x, 2)}</span>`;
const td = (x, d = 0) => `<td class="n num">${x == null || x === '' ? '' : fmt(x, d)}</td>`;
const dateF = (key, label) => `<label class="f">${label}<input type="date" data-p="${key}" value="${h(P[key])}"></label>`;
const range = () => `<div class="form">${dateF('frm', 'من')}${dateF('to', 'إلى')}</div>`;
const curF = () => `<label class="f">العملة${select('data-p="cur"', [['', 'الكل'], ['SAR', 'الحركات بالسعودي'], ['YER', 'الحركات باليمني']], P.cur)}</label>`;

function statementTable(d) {
  const sar = d.showSar;
  return `<div class="tbl"><table><thead><tr><th>القيد</th><th>التاريخ</th><th>البيان</th><th class="n">مدين</th><th class="n">دائن</th><th class="n">الرصيد ر.ي</th>${sar ? '<th class="n">الرصيد ر.س</th>' : ''}</tr></thead><tbody>
    <tr class="tot"><td></td><td class="num">${h(d.from)}</td><td>رصيد ما قبل الفترة</td><td></td><td></td>${td(d.opening.yer)}${sar ? td(d.opening.sar, 2) : ''}</tr>
    ${d.rows.map((r) => `<tr class="${r.status === 'reversed' ? 'struck' : ''}"><td class="num">${r.no}</td><td class="num">${h(r.date)}</td><td>${h(r.memo)} <span class="note">· ${h(d.party ? r.accountName : r.party)}</span></td>${td(r.debit || '')}${td(r.credit || '')}${td(r.balance)}${sar ? td(r.sar, 2) : ''}</tr>`).join('')}
    ${d.rows.length ? '' : `<tr><td colspan="${sar ? 7 : 6}" class="note">لا حركات في الفترة</td></tr>`}</tbody>
    <tfoot><tr><td></td><td></td><td>مجموع الفترة · الرصيد الختامي</td>${td(d.totals.debit)}${td(d.totals.credit)}${td(d.closing.yer)}${sar ? td(d.closing.sar, 2) : ''}</tr></tfoot></table></div>`;
}

const BODY = {
  claim: (d) => `<div class="form"><label class="f">العميل${select('data-p="party"', d.options.map((c) => [c, c]), d.party)}</label>${dateF('to', 'بتاريخ')}</div>
    <div class="kpis">${kpi('إجمالي الفواتير', fmt(d.totalInvoiced, 2), 'ر.س')}${kpi('المسدد', fmt(d.totalPaid, 2), 'ر.س')}
      ${kpi(d.credit > 0 ? 'رصيد دائن للعميل' : 'المستحق للمطالبة', fmt(d.credit > 0 ? d.credit : d.due, 2), `ر.س · ${fmt((d.credit > 0 ? d.credit : d.due) * d.fx)} ر.ي`)}</div>
    <h3>الفواتير غير المسددة</h3><div class="tbl"><table><thead><tr><th>الفاتورة</th><th>التاريخ</th><th class="n">كراتين</th><th class="n">القيمة ر.س</th><th class="n">المسدد ر.س</th><th class="n">المتبقي ر.س</th><th class="n">العمر يوم</th></tr></thead><tbody>
    ${d.open.map((i) => `<tr><td class="num">${h(i.ref)}</td><td class="num">${h(i.date)}</td>${td(i.cartons)}${td(i.sar, 2)}${td(i.paid, 2)}${td(i.remaining, 2)}${td(i.age)}</tr>`).join('') || '<tr><td colspan="7" class="note">لا فواتير مفتوحة — الحساب مسدد</td></tr>'}</tbody>
    ${d.open.length ? `<tfoot><tr><td>الإجمالي المستحق</td><td></td><td></td><td></td><td></td>${td(d.due, 2)}<td></td></tr></tfoot>` : ''}</table></div>
    <h3>السدادات المستلمة</h3><div class="tbl"><table><thead><tr><th>المرجع</th><th>التاريخ</th><th class="n">المبلغ ر.س</th></tr></thead><tbody>
    ${d.payments.map((p) => `<tr><td class="num">${h(p.ref)}</td><td class="num">${h(p.date)}</td>${td(p.sar, 2)}</tr>`).join('') || '<tr><td colspan="3" class="note">لا سدادات</td></tr>'}</tbody></table></div>
    <p class="note">تُوزَّع السدادات على الفواتير الأقدم فالأحدث.</p>`,

  tb: (d) => `<div class="form">${dateF('to', 'حتى تاريخ')}</div><div class="tbl"><table><thead><tr><th>الرمز</th><th>الحساب</th><th class="n">مدين ر.ي</th><th class="n">دائن ر.ي</th></tr></thead><tbody>
    ${d.rows.map((r) => `<tr><td class="num">${r.account}</td><td>${h(r.name)}${r.sar != null ? ` <span class="note">(${n2(r.sar)} ر.س)</span>` : ''}${r.unit ? ` <span class="note">(${n0(r.qty)} ${h(r.unit)})</span>` : ''}</td>${td(r.debit || '', 2)}${td(r.credit || '', 2)}</tr>`).join('') || '<tr><td colspan="4" class="note">لا قيود</td></tr>'}</tbody>
    <tfoot><tr><td></td><td>الإجمالي ${d.balanced ? '<span class="chip good">✓ متوازن</span>' : '<span class="chip bad">⛔ غير متوازن</span>'}</td>${td(d.totals.debit, 2)}${td(d.totals.credit, 2)}</tr></tfoot></table></div>`,

  is: (d) => {
    const row = (l, v, bold) => `<tr${bold ? ' class="tot"' : ''}><td>${l}</td>${td(v)}${td(v / d.fx, 2)}</tr>`;
    return `${range()}<div class="tbl"><table><thead><tr><th>البند</th><th class="n">ر.ي</th><th class="n">ر.س</th></tr></thead><tbody>
      ${row('المبيعات', d.sales)}${row('تكلفة المبيعات', -d.cogs)}${row('مجمل الربح', d.gross, 1)}${d.other ? row('إيرادات أخرى', d.other) : ''}
      ${d.expenses.map((e) => row(h(e.name), -e.amount)).join('')}${row('صافي الربح', d.net, 1)}</tbody></table></div>
      <p class="note">مبيعات فترة التشغيل التجريبي (قبل ${h(d.costingStart)}) بلا تكلفة مبيعات، لأن تكاليفها قُيّدت مصروفات مباشرة.</p>`;
  },

  party: (d) => `<div class="form"><label class="f">الطرف${select('data-p="party"', d.options.map((p) => [p, p]), d.party)}</label>${dateF('frm', 'من')}${dateF('to', 'إلى')}${curF()}</div>
    ${statementTable(d)}<p class="note">الرصيد الموجب: الطرف مدين لك (أو عهدة لديه / دفعة مقدمة). السالب: أنت مدين له.</p>`,

  ledger: (d, app) => `<div class="form"><label class="f">الحساب${select('data-p="account"', Object.entries(app.meta.accounts).map(([k, v]) => [k, `${k} ${v.name}`]), d.account)}</label>${dateF('frm', 'من')}${dateF('to', 'إلى')}${curF()}</div>${statementTable(d)}`,

  cost: (d) => `${d.rows.length ? `<div class="kpis">${kpi('كراتين معتمدة', fmt(d.totals.cartons))}${kpi('متوسط تكلفة الكرتون', fmt(d.totals.perSar, 2), `ر.س · ${fmt(d.totals.perYer)} ر.ي`)}
      ${kpi('مواد للكرتون', fmt(d.totals.rmPerCarton, 2), `كغ · الصافي ${fmt(d.cartonNetKg, 3)}`)}${kpi('كهرباء للكرتون', fmt(d.totals.kwhPerCarton, 1), 'ك.و')}</div>${costTable(d.rows)}` : '<div class="empty">لا ورديات معتمدة بعد</div>'}
    <p class="note">الطاقة القصوى: ${fmt(d.capacityDay, 1)} كرتون في 24 ساعة (${d.cavities} غطاء كل ${d.cycleSec} ثانية). المبرد مقدّر بـ ${fmt(d.chillerKw, 2)} ك.و × ${fmt(d.chillerLoad * 100)}% حتى يُركّب له عداد.</p>`,

  cash: (d) => `<div class="form"><label class="f">الأفق${select('data-p="horizon"', [[7, '7 أيام'], [14, '14 يوماً'], [30, '30 يوماً']], d.horizon)}</label>
      <label class="f">إنتاج متوقع (كرتون/يوم)<input data-p="cartons" inputmode="decimal" value="${h(P.cartons || Math.round(d.cartons))}"></label></div>
    <div class="kpis">${kpi('النقد المتاح الآن', fmt(d.start), 'ر.ي · الحسابات والمحافظ والعُهد')}${kpi('أدنى رصيد متوقع', fmt(d.lowest), h(d.lowestDate))}${kpi(`الرصيد بعد ${d.horizon} يوماً`, fmt(d.end), `ر.ي · ${fmt(d.end / d.fx)} ر.س`)}</div>
    ${d.lowest < 0 ? alertBox('warn', `الرصيد ينخفض إلى ${fmt(d.lowest)} ر.ي في ${d.lowestDate}. جهّز التمويل أو سرّع التحصيل قبل هذا التاريخ.`) : ''}
    <div class="tbl"><table><thead><tr><th>اليوم</th><th class="n">داخل</th><th class="n">مواد وكراتين</th><th class="n">كهرباء</th><th class="n">أجور ومصاريف</th><th class="n">الرصيد</th></tr></thead><tbody>
    ${d.rows.map((r) => `<tr><td class="num">${r.date}</td>${td(r.in)}${td(r.materials)}${td(r.electricity)}${td(r.wages)}${td(r.balance)}</tr>`).join('')}</tbody></table></div>
    <p class="note">افتراضات: الإنتاج من ${h(d.source)}. المخزون الحالي يغطي المواد ${fmt(d.cover.rm, 1)} يوم، والصبغة ${fmt(d.cover.pig, 1)}، والكراتين ${fmt(d.cover.ct, 1)}، ثم تُشترى يومياً بالأسعار في الإعدادات. الكهرباء من الرصيد المقدم حتى نفاده. الأجور والمصاريف بمتوسط آخر 14 يوماً (${fmt(d.dailyWages)} يومياً). الذمم الحالية تُحصَّل خلال ${d.collectionDays} أيام، والمبيعات الجديدة بعد ${d.collectionDays} أيام. الرصيد هنا تقدير تخطيطي بالريال اليمني (السعودي محوّل بسعر ${fmt(d.fx)})؛ الحسابان يبقيان منفصلين في الدفاتر.</p>`,

  aging: (d, app) => {
    const owner = app.meta.user.role === 'owner';
    return `<div class="form">${dateF('to', 'بتاريخ')}</div>
    <h3>أعمار الديون وسقوف الائتمان (ر.س)</h3><div class="tbl"><table><thead><tr><th>العميل</th>${d.buckets.map((b) => `<th class="n">${b}</th>`).join('')}<th class="n">المستحق</th><th class="n">سقف الائتمان</th><th class="n">من السقف</th></tr></thead><tbody>
    ${d.rows.map((r) => `<tr><td>${h(r.party)}</td>${r.buckets.map((v) => td(v || '', 2)).join('')}${td(r.due, 2)}
      <td class="n">${owner ? `<input data-lim="${h(r.party)}" inputmode="decimal" class="ltr" value="${r.limit || ''}" placeholder="بلا سقف" style="max-width:110px">` : (r.limit ? n0(r.limit) : '—')}</td><td class="n num">${r.usedPct != null ? fmt(r.usedPct) + '%' : ''}</td></tr>`).join('')}</tbody>
    <tfoot><tr><td>الإجمالي</td>${d.totals.map((v) => td(v, 2)).join('')}${td(d.totalDue, 2)}<td></td><td></td></tr></tfoot></table></div>
    ${owner ? '<div class="row"><button class="btn sm" id="limSave">حفظ السقوف</button><span class="note">عند تجاوز السقف يرفض النظام فاتورة البيع الآجل إلا بموافقتك.</span></div>' : ''}
    <h3>تركّز المبيعات (آخر 30 يوماً)</h3>${d.concentration.length ? `<div class="tbl"><table><thead><tr><th>العميل</th><th class="n">المبيعات ر.س</th><th class="n">الحصة</th></tr></thead><tbody>
      ${d.concentration.map((c) => `<tr><td>${h(c.party)}</td>${td(c.sar)}<td class="n num">${fmt(c.share)}%</td></tr>`).join('')}</tbody></table></div>
      ${d.concentration[0].share > 50 ? alertBox('warn', `${d.concentration[0].party} يمثل ${fmt(d.concentration[0].share)}% من المبيعات. تأخره في السداد يضغط السيولة كلها؛ ابحث عن عملاء إضافيين وضع له سقفاً.`) : ''}` : '<p class="note">لا مبيعات في آخر 30 يوماً.</p>'}
    <h3>مخصص الديون المشكوك فيها</h3><div class="tbl"><table><tbody><tr><td>النسب حسب العمر</td><td class="num">${d.provPct.map((p, k) => d.buckets[k] + ': ' + p + '%').join(' · ')}</td></tr>
      <tr><td>المخصص المطلوب</td><td class="n">${n0(d.provisionNeeded)} ر.ي</td></tr><tr><td>المخصص المسجل</td><td class="n">${n0(d.provisionRecorded)} ر.ي</td></tr><tr class="tot"><td>التسوية</td><td class="n">${n0(d.provisionAdjust)} ر.ي</td></tr></tbody></table></div>
    ${owner && Math.abs(d.provisionAdjust) > 0.5 ? `<div class="row"><button class="btn pri" id="provPost">تسجيل تسوية المخصص ${fmt(d.provisionAdjust)} ر.ي</button></div>` : ''}
    <p class="note">المخصص تقدير لخسارة محتملة من الديون المتأخرة، يُحمَّل على الربح دون أن يلغي حق المطالبة. يُراجع شهرياً.</p>`;
  },

  fxrisk: (d) => `<p class="note">إيراداتك ومشترياتك من المواد والصبغة بالريال السعودي، بينما الأجور والكهرباء والكراتين والإهلاك بالريال اليمني. تغيّر سعر الصرف يغيّر ربحك. التقدير لشهر بإنتاج ${fmt(d.cartonsDay)} كرتون يومياً (${h(d.source)}).</p>
    <div class="kpis">${kpi('إيراد شهري بالسعودي', fmt(d.revenueSar), 'ر.س')}${kpi('مواد وصبغة بالسعودي', fmt(d.materialsSar), 'ر.س')}${kpi('تكاليف باليمني', fmt(d.yerCosts), `ر.ي · ${fmt(d.yerCosts / d.fx)} ر.س`)}${kpi('ما تملكه بالسعودي', fmt(d.sarHoldings), 'ر.س نقداً وذمماً')}</div>
    <div class="tbl"><table><thead><tr><th>سعر الصرف</th><th class="n">الربح الشهري ر.س</th><th class="n">الربح الشهري ر.ي</th><th class="n">الفرق عن اليوم ر.س</th></tr></thead><tbody>
    ${d.scenarios.map((s) => `<tr${s.today ? ' class="tot"' : ''}><td class="num">${fmt(s.fx)}${s.today ? ' (اليوم)' : ''}</td>${td(s.profitSar)}${td(s.profitYer)}${td(s.diffSar)}</tr>`).join('')}</tbody></table></div>
    <p class="note">ارتفاع السعر (ريال يمني أضعف) يخفّض تكاليفك اليمنية بالسعودي فيرفع ربحك، والعكس. لتقليل المخاطرة: اصرف من السعودي إلى اليمني بقدر حاجة الأسبوع فقط.</p>`,

  be: (d) => `<div class="kpis">${kpi('نقطة التعادل', d.breakEvenDay != null ? fmt(d.breakEvenDay, 1) : '—', `كرتون يومياً · ${d.breakEvenMonth != null ? fmt(d.breakEvenMonth) : '—'} شهرياً`)}
      ${kpi('الطاقة القصوى', fmt(d.capacityDay, 1), `كرتون يومياً · التعادل ${d.capacityPct != null ? fmt(d.capacityPct) : '—'}% منها`)}${kpi('هامش المساهمة', fmt(d.contribution / d.fx, 2), 'ر.س لكل كرتون فوق التكلفة المتغيرة')}${kpi('التكاليف الثابتة', fmt(d.fixed / d.fx), 'ر.س شهرياً')}</div>
    <div class="tbl"><table><thead><tr><th>البند</th><th class="n">ر.ي</th><th class="n">ر.س</th></tr></thead><tbody>
      <tr><td>سعر بيع الكرتون</td>${td(d.priceYer)}${td(d.priceSar, 2)}</tr>
      <tr><td>التكلفة المتغيرة للكرتون (مواد ${fmt(d.matPerCarton, 2)} كغ، صبغة، كرتون، كهرباء الماكينة)</td>${td(d.variablePerCarton)}${td(d.variablePerCarton / d.fx, 2)}</tr>
      <tr class="tot"><td>هامش المساهمة للكرتون</td>${td(d.contribution)}${td(d.contribution / d.fx, 2)}</tr>
      <tr><td>أجور وإعاشة شهرياً</td>${td(d.wages)}${td(d.wages / d.fx)}</tr><tr><td>مستلزمات ومصاريف إدارية شهرياً</td>${td(d.other)}${td(d.other / d.fx)}</tr>
      <tr><td>كهرباء المبرد (ثابتة تقريباً)</td>${td(d.chiller)}${td(d.chiller / d.fx)}</tr><tr><td>إهلاك الأصول المسعّرة</td>${td(d.depreciation)}${td(d.depreciation / d.fx)}</tr>
      <tr class="tot"><td>التكاليف الثابتة الشهرية</td>${td(d.fixed)}${td(d.fixed / d.fx)}</tr></tbody></table></div>
    <h3>الربح الشهري عند مستويات الإنتاج</h3><div class="tbl"><table><thead><tr><th class="n">كرتون يومياً</th><th class="n">الربح الشهري ر.س</th></tr></thead><tbody>
    ${d.levels.map((l) => `<tr><td class="n"><span class="num">${l.cartonsDay}</span>${l.tag ? ` (${l.tag})` : ''}</td>${td(l.profitSar)}</tr>`).join('')}</tbody></table></div>
    <p class="note">التكاليف المتغيرة من ${h(d.source)}، والثابتة من متوسط مصروفات آخر 30 يوماً. الأصول غير المسعّرة لا يدخل إهلاكها حتى تُسعَّر.</p>`,

  budget: (d, app) => {
    const owner = app.meta.user.role === 'owner';
    return `<div class="form"><label class="f">الشهر<input type="month" data-p="month" value="${h(d.month)}"></label></div>
    <div class="tbl"><table><thead><tr><th>البند</th><th class="n">المخطط</th><th class="n">الفعلي</th><th class="n">الفرق</th></tr></thead><tbody>
    ${d.rows.map((r) => `<tr${r.key === 'profit' ? ' class="tot"' : ''}><td>${h(r.label)}</td><td class="n">${owner && r.editable ? `<input data-bg="${r.key}" inputmode="decimal" class="ltr" value="${r.plan ?? ''}" placeholder="${r.suggested ?? ''}" style="max-width:120px">` : (r.plan != null ? n0(r.plan) : '—')}</td>
      ${td(r.actual)}<td class="n">${r.diff == null ? '' : `<span class="chip ${r.good ? 'good' : 'bad'}">${r.good ? '▲' : '▼'} ${fmt(r.diff)}${r.diffPct != null ? ' (' + fmt(r.diffPct) + '%)' : ''}</span>`}</td></tr>`).join('')}</tbody></table></div>
    ${owner ? '<div class="row"><button class="btn pri" id="bgSave">حفظ الموازنة</button><button class="btn sm" id="bgSug">تعبئة مقترحة</button><span class="note">المقترح من معدلاتك الحالية والإعدادات.</span></div>' : ''}
    <p class="note">▲ أفضل من الخطة و ▼ أسوأ. الفعلي يُحدَّث تلقائياً مع كل قيد ووردية معتمدة.</p>`;
  },

  eff: (d) => `${range()}${d.rows.length ? `<div class="kpis">${kpi('الكفاءة', fmt(d.totals.eff) + '%', `${fmt(d.totals.cartons)} من ${fmt(d.totals.max)} كرتون ممكن`)}
      ${kpi('التوقف', fmt(d.totals.downHours, 1), `ساعة · ${fmt(d.totals.lostDown, 1)} كرتون ضائع`)}${kpi('فاقد السرعة', fmt(d.totals.lostOther, 1), 'كرتون دون توقف مسجل')}${kpi('الهامش الضائع', fmt(d.totals.lostMargin), 'ر.س')}</div>
    ${d.reasons.length ? `<h3>التوقف حسب السبب</h3><div class="tbl"><table><thead><tr><th>السبب</th><th class="n">دقائق</th><th class="n">كراتين ضائعة</th></tr></thead><tbody>${d.reasons.map((r) => `<tr><td>${h(r.reason)}</td>${td(r.minutes)}${td(r.lostCartons, 1)}</tr>`).join('')}</tbody></table></div>` : ''}
    <h3>الورديات</h3><div class="tbl"><table><thead><tr><th>التاريخ</th><th>الوردية</th><th class="n">كراتين</th><th class="n">الكفاءة</th><th class="n">توقف د</th><th>السبب</th><th class="n">ضائع</th></tr></thead><tbody>
    ${d.rows.map((s) => `<tr><td class="num">${h(s.date)}</td><td>${h(s.shift)}</td>${td(s.cartons)}<td class="n num">${fmt((s.eff || 0) * 100)}%</td>${td(s.downMin)}<td>${h(s.downReason)}</td>${td(s.lost, 1)}</tr>`).join('')}</tbody></table></div>`
    : '<div class="empty">لا ورديات معتمدة في الفترة</div>'}
    <p class="note">الطاقة القصوى ${fmt(d.cartonsPerHour, 2)} كرتون في الساعة. «فاقد السرعة» إنتاج أقل من الطاقة دون توقف مسجل، وسببه غالباً دورة أبطأ من ${d.cycleSec} ثانية أو فتحات مغلقة في القالب.</p>`,

  cc: (d) => `${range()}<div class="tbl"><table><thead><tr><th>الحساب</th>${d.centers.map((c) => `<th class="n">${h(c.name)}</th>`).join('')}<th class="n">الإجمالي</th></tr></thead><tbody>
    ${d.rows.map((r) => `<tr><td>${h(r.name)}</td>${d.centers.map((c) => td(r.values[c.id] || '')).join('')}${td(r.total)}</tr>`).join('') || `<tr><td colspan="${d.centers.length + 2}" class="note">لا مصروفات في الفترة</td></tr>`}</tbody>
    <tfoot><tr><td>الإجمالي ر.ي</td>${d.centers.map((c) => td(d.totals[c.id] || 0)).join('')}${td(d.grandTotal)}</tr></tfoot></table></div>
    <p class="note">أجور الورديات المعتمدة (${fmt(d.absorbedLabor)} ر.ي) تنتقل إلى مخزون الغطايا فتظهر سالبة في مركز الإنتاج. أضف مراكز جديدة من الإعدادات.</p>`,

  fxpos: (d, app) => `<p class="note">ما تملكه بالريال السعودي، والسعر المتوسط الذي قُيّد به في الدفاتر، وقيمته بسعر اليوم (${fmt(d.fx)} من الإعدادات).</p>
    <div class="tbl"><table><thead><tr><th>البند</th><th class="n">ر.س</th><th class="n">القيمة الدفترية ر.ي</th><th class="n">متوسط السعر</th><th class="n">بسعر اليوم ر.ي</th><th class="n">فرق غير محقق</th></tr></thead><tbody>
    ${d.rows.map((r) => `<tr><td>${h(r.label)}</td>${td(r.sar, 2)}${td(r.bookYer)}${td(r.avgRate, 2)}${td(r.nowYer)}${td(r.diff)}</tr>`).join('')}</tbody>
    <tfoot><tr><td>الإجمالي</td><td></td><td></td><td></td><td></td>${td(d.totalDiff)}</tr></tfoot></table></div>
    ${app.meta.user.role === 'owner' && Math.abs(d.totalDiff) > 0.5 ? `<div class="row"><button class="btn pri" id="fxReval">إعادة التقييم بسعر ${fmt(d.fx)} وتسجيل الفرق</button></div><p class="note">يُستخدم في نهاية الشهر عند تغيّر سعر الصرف.</p>` : ''}`,

  vat: (d) => `${d.enabled ? '' : '<div class="msg">الضريبة غير مفعّلة الآن. فعّلها من الإعدادات مع النسبة والرقم الضريبي عند تسجيلك.</div>'}${range()}
    <div class="tbl"><table><thead><tr><th>البند</th><th class="n">ر.ي</th><th class="n">ر.س</th></tr></thead><tbody>
      <tr><td>ضريبة المخرجات (على المبيعات)</td>${td(d.output)}${td(d.output / d.fx, 2)}</tr><tr><td>ضريبة المدخلات (على المشتريات)</td>${td(d.input)}${td(d.input / d.fx, 2)}</tr>
      <tr class="tot"><td>${d.net >= 0 ? 'صافي المستحق للدفع' : 'صافي القابل للاسترداد'}</td>${td(Math.abs(d.net))}${td(Math.abs(d.net) / d.fx, 2)}</tr></tbody></table></div>
    ${d.enabled ? `<p class="note">النسبة ${fmt(d.rate, 1)}%${d.vatNo ? ' · الرقم الضريبي ' + h(d.vatNo) : ''}. السداد من «حوالة صادرة ← سداد ضريبة».</p>` : ''}`,

  zakat: (d, app) => {
    const row = (l, v, b) => `<tr${b ? ' class="tot"' : ''}><td>${l}</td>${td(v)}${td(v / d.fx, 2)}</tr>`;
    return `<div class="form">${dateF('to', 'بتاريخ تمام الحول')}</div>
    <div class="tbl"><table><thead><tr><th>الوعاء الزكوي</th><th class="n">ر.ي</th><th class="n">ر.س</th></tr></thead><tbody>
      ${d.assets.map((a) => row(h(a.label), a.amount)).join('')}${row('مجموع الأصول الزكوية', d.totalAssets, 1)}
      ${d.liabilities.map((a) => row('يُطرح: ' + h(a.label), a.amount)).join('')}${row('الوعاء الزكوي', d.base, 1)}
      ${row(`الزكاة ${fmt(d.rate, 3)}%${d.nisab ? ` (النصاب ${fmt(d.nisab)})` : ''}`, d.zakat, 1)}</tbody></table></div>
    ${!d.nisab ? alertBox('warn', 'أدخل قيمة النصاب في الإعدادات (قيمة 85 غرام ذهب بالريال اليمني يوم تمام الحول) ليتحقق النظام من بلوغ النصاب.') : ''}
    <p class="note">تقدير محاسبي: الآلات والمعدات لا تدخل الوعاء، والمخزون محسوب بالتكلفة (يقيّمه كثير من الفقهاء بسعر السوق يوم الحول). الحول هجري؛ نسبة 2.5% للسنة الهجرية و2.577% للسنة الميلادية. بدأ المصنع في أكتوبر 2026، فلا تجب الزكاة قبل تمام حول عليه. راجع مختصاً شرعياً قبل الإخراج.</p>
    ${app.meta.user.role === 'owner' && d.zakat > 0 ? `<div class="row"><button class="btn pri" id="zPost">تسجيل الزكاة المستحقة ${fmt(d.zakat)} ر.ي</button></div>` : ''}`;
  },

  inv: (d) => `<div class="tbl"><table><thead><tr><th>الصنف</th><th class="n">الكمية</th><th class="n">القيمة ر.ي</th><th class="n">متوسط التكلفة</th></tr></thead><tbody>
    ${d.rows.map((r) => `<tr><td>${h(r.name)}</td><td class="n"><span class="num">${fmt(r.qty, 1)}</span> ${h(r.unit)}</td>${td(r.value)}${td(r.avg, 2)}</tr>`).join('')}</tbody></table></div>`,
};

function paramsFor(kind) {
  const p = {};
  if (['claim', 'party'].includes(kind) && P.party) p.party = P.party;
  if (kind === 'ledger') p.account = P.account;
  if (['party', 'ledger'].includes(kind) && P.cur) p.cur = P.cur;
  if (RANGED.includes(kind)) p.frm = P.frm;
  if (RANGED.includes(kind) || ['claim', 'tb', 'aging', 'zakat'].includes(kind)) p.to = P.to;
  if (kind === 'budget') p.month = P.month;
  if (kind === 'cash') { p.horizon = P.horizon; if (P.cartons) p.cartons = numOrNull(P.cartons); }
  return p;
}

function meta(kind) {
  const period = kind === 'budget' ? 'شهر ' + P.month : kind === 'cash' ? `توقع ${P.horizon} يوماً من ${today()}` : RANGED.includes(kind) ? `الفترة من ${P.frm} إلى ${P.to}` : `حتى تاريخ ${P.to}`;
  return period;
}

export async function render(main, app) {
  if (app.opts?.report) { P.kind = app.opts.report; if (app.opts.party) P.party = app.opts.party; app.opts = {}; }
  const d = await api.get('/reports/' + P.kind, paramsFor(P.kind));
  if (d.party !== undefined && P.kind in { claim: 1, party: 1 }) P.party = d.party;
  main.innerHTML = `<section class="tab"><h2>التقارير</h2>
    <div class="seg" id="rSeg">${LIST.map(([k, l]) => `<button data-r="${k}" aria-pressed="${k === P.kind}">${l}</button>`).join('')}</div>
    <div class="panel" id="rptPanel"><h3>${h(d.title)}</h3>${BODY[P.kind](d, app)}<div class="row" data-noexport><button class="btn" id="rXls">⤓ تصدير Excel</button></div></div></section>`;
  main.querySelector('#rSeg').addEventListener('click', (e) => {
    const b = e.target.closest('[data-r]');
    if (b) { P.kind = b.dataset.r; render(main, app); }
  });
  main.querySelectorAll('[data-p]').forEach((el) => el.addEventListener('change', () => { P[el.dataset.p] = el.value; render(main, app); }));
  main.querySelector('#rXls').addEventListener('click', () => {
    const extra = P.kind === 'claim' || P.kind === 'party' ? P.party : P.kind === 'ledger' ? `${P.account} ${app.meta.accounts[P.account]?.name || ''}` : '';
    const panel = main.querySelector('#rptPanel').cloneNode(true);
    panel.querySelectorAll('.form, .row, button, datalist, h3:first-child').forEach((x) => { if (!x.querySelector('table')) x.remove(); });
    const metaLine = `${meta(P.kind)}   ·   المبالغ بالريال اليمني ما لم يُذكر غيره   ·   سعر الصرف ${fmt(app.meta.settings.fx)}   ·   أُصدر ${today()} بواسطة ${app.meta.user.label}`;
    saveXlsx(`${d.title}${extra ? ' - ' + extra : ''} ${today()}.xlsx`, [layoutSheet(d.title.slice(0, 31), d.title + (extra ? ' – ' + extra : ''), metaLine, panelBlocks(panel))]);
  });
  const post = (id, fn, done) => main.querySelector(id)?.addEventListener('click', async (e) => {
    const btn = e.currentTarget;
    busy(btn, true);
    try { const r = await fn(); toast(done(r)); await app.refresh(); } catch (err) { toast(err.message); busy(btn, false); }
  });
  post('#limSave', () => {
    const limits = {};
    main.querySelectorAll('[data-lim]').forEach((i) => { const v = numOrNull(i.value); if (v > 0) limits[i.dataset.lim] = v; });
    return api.put('/reports/aging/limits', { limits });
  }, () => 'حُفظت السقوف');
  post('#provPost', () => api.post('/reports/aging/provision', { date: P.to }), (r) => 'سُجّل المخصص – القيد ' + r.no);
  post('#fxReval', () => api.post('/reports/fxpos/revalue'), (r) => 'سُجلت إعادة التقييم – القيد ' + r.no);
  post('#zPost', () => api.post('/reports/zakat/post', { date: P.to }), (r) => 'سُجلت الزكاة المستحقة – القيد ' + r.no);
  post('#bgSave', () => {
    const values = {};
    main.querySelectorAll('[data-bg]').forEach((i) => { const v = numOrNull(i.value); if (v != null) values[i.dataset.bg] = v; });
    return api.put('/reports/budget', { month: P.month, values });
  }, () => 'حُفظت موازنة ' + P.month);
  main.querySelector('#bgSug')?.addEventListener('click', () => main.querySelectorAll('[data-bg]').forEach((i) => { if (!i.value) i.value = i.placeholder; }));
}

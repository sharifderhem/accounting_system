// Settings (§15): factory numbers, lock date, taxes, cost centers, parties, users, dual control.
import { api } from '../api.js';
import { busy, clearErrors, h, numOrNull, select, showError, toast } from '../util.js';

const FIELDS = [['fx', 'سعر الصرف (يمني لكل سعودي)'], ['priceSar', 'سعر بيع الكرتون ر.س'], ['kwhPrice', 'سعر الكيلو واط ر.ي'], ['rmPriceSarTon', 'سعر طن المواد الخام ر.س'],
  ['cartonCost', 'تكلفة الكرتون والكيس ر.ي'], ['bagKg', 'وزن كيس المواد كغ'], ['cartonNetKg', 'صافي غطايا الكرتون كغ'], ['capsPerCarton', 'غطايا في الكرتون'],
  ['capWeightG', 'وزن الغطاء غ'], ['pigmentGPerBag', 'صبغة لكل كيس مواد (غ)'], ['pigmentPriceSar', 'سعر كيس الصبغة ر.س'], ['pigmentCoverKg', 'كيس الصبغة يكفي (كغ مواد)'],
  ['usdSar', 'سعر الدولار بالسعودي'], ['plannedCartonsDay', 'الإنتاج المخطط (كرتون/يوم)'], ['collectionDays', 'مدة التحصيل من العملاء (يوم)'],
  ['minStockDays', 'تنبيه المخزون قبل النفاد بـ (يوم)'], ['cavities', 'فتحات القالب'], ['cycleSec', 'زمن الدورة ثانية'], ['shiftHours', 'ساعات الوردية'],
  ['chillerKw', 'قدرة المبرد ك.و'], ['chillerLoad', 'نسبة تشغيل المبرد (0–1)'], ['normalScrapPct', 'حد التنبيه للتالف %']];
const ROLE_HELP = {
  entry: 'يسجل المبيعات والحوالات والمصروفات وطلبات السلف. لا يرى الأرصدة ولا التقارير.',
  reviewer: 'يرى الرئيسية والتحليلات والتقارير والقيود والمطابقات للاطلاع فقط.',
  supervisor: 'يسجل الورديات وطلبات السلف فقط، ولا يرى أي أرقام مالية.',
  none: 'لا يرى شيئاً.',
};

export async function render(main, app) {
  const [s, users] = await Promise.all([api.get('/settings'), api.get('/users')]);
  const m = app.meta;
  const roleOpts = [['entry', 'مدخل بيانات'], ['reviewer', 'مراجع أو شريك'], ['supervisor', 'مشرف وردية'], ['none', 'بلا صلاحية']];
  const nIn = (k, l, v) => `<label class="f">${l}<input data-field="${k}" inputmode="decimal" class="ltr" value="${h(v ?? '')}"></label>`;
  main.innerHTML = `<section class="tab"><h2>الإعدادات</h2>
    <div class="panel" id="setPanel"><h3>أرقام المصنع</h3><div class="form">${FIELDS.map(([k, l]) => nIn(k, l, s[k])).join('')}
      <label class="f">بداية احتساب التكلفة<input type="date" data-field="costingStart" value="${h(s.costingStart)}"></label></div>
      <h3>إقفال الفترات</h3><div class="form"><label class="f">منع أي قيد بتاريخ حتى (إقفال)<input type="date" data-field="lockDate" value="${h(s.lockDate || '')}"></label></div>
      <p class="note">بعد مراجعة الشهر وتسوياته، أقفله هنا فلا يُسجَّل أو يُعكس أي قيد بتاريخ داخله. اتركه فارغاً لإبقاء كل الفترات مفتوحة.</p>
      <h3>الضرائب والزكاة</h3><div class="form">
        <label class="f">ضريبة القيمة المضافة${select('data-field="vatEnabled"', [['0', 'غير مفعّلة (لا ضرائب الآن)'], ['1', 'مفعّلة']], s.vatEnabled ? '1' : '0')}</label>
        ${nIn('vatRate', 'نسبة الضريبة %', s.vatRate)}<label class="f">الرقم الضريبي<input data-field="vatNo" class="ltr" value="${h(s.vatNo || '')}"></label>
        ${nIn('zakatRate', 'نسبة الزكاة %', s.zakatRate)}${nIn('nisabYer', 'النصاب ر.ي (85 غ ذهب)', s.nisabYer || '')}</div>
      <div class="row"><button class="btn pri" id="sSave">حفظ الإعدادات</button></div><div id="sMsg" role="status"></div></div>

    <div class="panel"><h3>الرقابة المزدوجة</h3>
      <label class="check"><input type="checkbox" id="dualCtl"${s.dualControl ? ' checked' : ''}> الحوالات الصادرة والمصروفات وصرف العملة تحتاج موافقة شخص ثانٍ</label>
      <p class="note">تعمل عند وجود مستخدم آخر معلَّم «يعتمد الطلبات». صاحب الطلب لا يعتمده أبداً، وهذا يشملك أنت: شريكك يعتمد طلباتك.</p></div>

    <div class="panel"><h3>المستخدمون والصلاحيات</h3>
      <p class="note">لا يفتح النظام أحد إلا بحساب تنشئه أنت. الصلاحيات مفروضة على الخادم.</p>
      <div class="tbl"><table><thead><tr><th>المستخدم</th><th>الدور</th><th>يعتمد الطلبات</th><th>نشِط</th><th>كلمة مرور جديدة</th><th></th></tr></thead><tbody>
      ${users.map((u) => u.role === 'owner' ? `<tr><td>${h(u.label)}<div class="note num">${h(u.username)}</div></td><td>المالك</td><td>✓ دائماً</td><td>✓</td><td colspan="2" class="note">غيّر كلمة مرورك من الأسفل</td></tr>`
        : `<tr data-user="${u.id}"><td><input data-k="label" value="${h(u.label)}" aria-label="الاسم"><div class="note num">${h(u.username)}</div></td>
          <td>${select('data-k="role" aria-label="الدور"', roleOpts, u.role)}</td>
          <td><input type="checkbox" data-k="approver" style="width:22px;min-height:22px"${u.approver ? ' checked' : ''}${['entry', 'reviewer'].includes(u.role) ? '' : ' disabled'} aria-label="يعتمد الطلبات"></td>
          <td><input type="checkbox" data-k="active" style="width:22px;min-height:22px"${u.active ? ' checked' : ''} aria-label="نشط"></td>
          <td><input data-k="password" type="password" autocomplete="new-password" placeholder="اتركه فارغاً" aria-label="كلمة مرور جديدة"></td>
          <td><button class="btn sm" data-usave>حفظ</button></td></tr>`).join('')}</tbody></table></div>
      <details id="newUser"><summary><b>إضافة مستخدم</b></summary><div class="form">
        <label class="f">اسم المستخدم (للدخول)<input data-field="username" class="ltr" autocapitalize="off" autocomplete="off"></label>
        <label class="f">الاسم الظاهر<input data-field="label"></label>
        <label class="f">كلمة المرور (8 أحرف على الأقل)<input data-field="password" type="password" autocomplete="new-password"></label>
        <label class="f">الدور${select('data-field="role" id="nuRole"', roleOpts.slice(0, 3), 'entry')}</label></div>
        <p class="note" id="roleHelp">${ROLE_HELP.entry}</p>
        <label class="check"><input type="checkbox" data-field="approver"> يعتمد الطلبات (لمدخل البيانات أو المراجع)</label>
        <div class="row"><button class="btn pri" id="uAdd">إنشاء الحساب</button></div><div id="uMsg" role="status"></div></details></div>

    <div class="grid2">
      <div class="panel"><h3>الأطراف</h3><div class="tbl"><table><thead><tr><th>الاسم</th><th>النوع</th></tr></thead><tbody>
        ${m.parties.map((p) => `<tr><td>${h(p.name)}</td><td>${h(m.partyTypes[p.type] || p.type)}</td></tr>`).join('')}</tbody></table></div>
        <div class="form" id="partyBox"><label class="f">اسم جديد<input data-field="name"></label><label class="f">النوع${select('data-field="type"', Object.entries(m.partyTypes), 'customer')}</label></div>
        <div class="row"><button class="btn" id="pAdd">إضافة طرف</button></div><div id="pMsg" role="status"></div></div>
      <div class="panel"><h3>مراكز التكلفة</h3><div class="tbl"><table><thead><tr><th>المركز</th><th>الرمز</th></tr></thead><tbody>
        ${m.costCenters.map((c) => `<tr><td>${h(c.name)}</td><td class="num">${h(c.id)}</td></tr>`).join('')}</tbody></table></div>
        <div class="form" id="ccBox"><label class="f">مركز جديد<input data-field="name" placeholder="مثال: ماكينة 2 – قالب 32"></label></div>
        <div class="row"><button class="btn" id="ccAdd">إضافة مركز</button></div><div id="ccMsg" role="status"></div></div>
    </div>

    <div class="panel" id="pwBox"><h3>كلمة مروري</h3><div class="form">
      <label class="f">الحالية<input data-field="current" type="password" autocomplete="current-password"></label>
      <label class="f">الجديدة (8 أحرف على الأقل)<input data-field="new" type="password" autocomplete="new-password"></label></div>
      <div class="row"><button class="btn" id="pwSave">تغيير كلمة المرور</button></div><div id="pwMsg" role="status"></div></div>
  </section>`;

  const q = (sel) => main.querySelector(sel);
  const run = async (btn, box, msg, fn, done) => {
    clearErrors(box);
    busy(btn, true);
    try { await fn(); toast(done); await app.refresh(); } catch (err) { if (msg) showError(box, msg, err); else toast(err.message); busy(btn, false); }
  };

  q('#sSave').addEventListener('click', (e) => {
    const panel = q('#setPanel');
    const body = {};
    for (const [k] of FIELDS) { const v = numOrNull(panel.querySelector(`[data-field="${k}"]`).value); if (v != null) body[k] = v; }
    for (const k of ['vatRate', 'zakatRate', 'nisabYer']) body[k] = numOrNull(panel.querySelector(`[data-field="${k}"]`).value) ?? 0;
    body.costingStart = panel.querySelector('[data-field="costingStart"]').value;
    body.lockDate = panel.querySelector('[data-field="lockDate"]').value;
    body.vatEnabled = panel.querySelector('[data-field="vatEnabled"]').value === '1';
    body.vatNo = panel.querySelector('[data-field="vatNo"]').value.trim();
    run(e.currentTarget, panel, q('#sMsg'), () => api.put('/settings', body), 'حُفظت الإعدادات');
  });
  q('#dualCtl').addEventListener('change', (e) => run(null, main, null, () => api.put('/settings', { dualControl: e.target.checked }), 'حُفظ'));
  main.querySelectorAll('[data-usave]').forEach((b) => b.addEventListener('click', () => {
    const row = b.closest('[data-user]');
    const get = (k) => row.querySelector(`[data-k="${k}"]`);
    const body = { label: get('label').value.trim(), role: get('role').value, approver: get('approver').checked, active: get('active').checked };
    if (get('password').value) body.password = get('password').value;
    run(b, row, null, () => api.patch(`/users/${row.dataset.user}`, body), 'حُفظ المستخدم');
  }));
  q('#nuRole').addEventListener('change', (e) => { q('#roleHelp').textContent = ROLE_HELP[e.target.value]; });
  q('#uAdd').addEventListener('click', (e) => {
    const box = q('#newUser');
    const v = (k) => box.querySelector(`[data-field="${k}"]`);
    const body = { username: v('username').value.trim(), label: v('label').value.trim(), password: v('password').value, role: v('role').value, approver: v('approver').checked };
    run(e.currentTarget, box, q('#uMsg'), () => api.post('/users', body), 'أُنشئ الحساب');
  });
  q('#pAdd').addEventListener('click', (e) => {
    const box = q('#partyBox');
    run(e.currentTarget, box, q('#pMsg'), () => api.post('/parties', { name: box.querySelector('[data-field="name"]').value.trim(), type: box.querySelector('[data-field="type"]').value }), 'أُضيف الطرف');
  });
  q('#ccAdd').addEventListener('click', (e) => {
    const box = q('#ccBox');
    run(e.currentTarget, box, q('#ccMsg'), () => api.post('/cost-centers', { name: box.querySelector('[data-field="name"]').value.trim() }), 'أُضيف المركز');
  });
  q('#pwSave').addEventListener('click', (e) => {
    const box = q('#pwBox');
    run(e.currentTarget, box, q('#pwMsg'), () => api.post('/auth/password', {
      current: box.querySelector('[data-field="current"]').value, new: box.querySelector('[data-field="new"]').value,
    }), 'تغيّرت كلمة المرور');
  });
}

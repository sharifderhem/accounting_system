// Home (§12.1): balances, KPIs, alerts, stock, customers and custody, recent shifts.
import { api } from '../api.js';
import { alertBox, fmt, h } from '../util.js';
import { costTable, kpi } from '../ui.js';

export async function render(main, app) {
  const d = await api.get('/home');
  const b = d.balances, k = d.kpis;
  main.innerHTML = `<section class="tab">
    <div class="split"><h2>الوضع اليوم</h2><span class="note num">${h(d.today)}</span></div>
    ${d.alerts.length ? `<div style="display:grid;gap:8px">${d.alerts.map((a) => alertBox(a.level, a.text)).join('')}</div>` : ''}
    <div class="kpis">
      ${kpi('حساب المصنع – سعودي', fmt(b.sar), `ر.س · متوسط سعره في الدفاتر ${b.sarAvgRate ? fmt(b.sarAvgRate, 2) : '—'}`)}
      ${kpi(`حساب المصنع – يمني${b.yer < 0 ? ' (مكشوف)' : ''}`, fmt(b.yer), `ر.ي${b.cash ? ` · الصندوق ${fmt(b.cash)} ر.ي` : ''}`)}
      ${kpi('المحافظ الإلكترونية', fmt(b.walletsTotal), `ر.ي · جيب ${fmt(b.wallets['1107'])} · إيزي ${fmt(b.wallets['1108'])} · فلوسك ${fmt(b.wallets['1109'])}`)}
      ${kpi('ذمم العملاء', fmt(b.customersSar), `ر.س ${d.customers.length ? '· ' + d.customers.length + ' عميل' : '· لا ذمم مفتوحة'}`)}
      ${kpi('كهرباء مدفوعة مقدماً', fmt(b.power), `ر.ي · تكفي نحو ${fmt(b.powerDays)} يوماً`)}
      ${kpi('كفاءة التشغيل', k.efficiency != null ? fmt(k.efficiency) + '%' : '—', k.shifts ? `من الطاقة القصوى · آخر ${k.shifts} وردية` : 'بعد اعتماد الورديات')}
      ${kpi('تكلفة الكرتون الفعلية', k.costPerCartonSar ? fmt(k.costPerCartonSar, 1) : '—', k.costPerCartonSar ? `ر.س · الهامش ${fmt(k.marginSar, 1)} من ${fmt(d.priceSar)}` : 'بعد اعتماد أول وردية')}
      ${kpi('مبيعات الشهر', fmt(k.monthSalesSar), `ر.س · ${fmt(k.monthSalesYer)} ر.ي`)}
      ${kpi('مجمل ربح الشهر', fmt(k.monthGrossSar), `ر.س · ${fmt(k.monthGrossYer)} ر.ي`)}
    </div>
    <div class="grid2">
      <div class="panel"><h3>المخزون</h3><div class="tbl"><table><thead><tr><th>الصنف</th><th class="n">الكمية</th><th class="n">يكفي</th><th class="n">القيمة ر.ي</th><th class="n">متوسط التكلفة</th></tr></thead><tbody>
        ${d.stock.map((s) => `<tr><td>${h(s.name)}</td><td class="n"><span class="num">${fmt(s.qty, s.account === '1302' ? 2 : 0)}</span> ${h(s.unit)}</td>
          <td class="n">${s.days != null ? `<span class="num">${fmt(s.days, 1)}</span> يوم` : '—'}</td><td class="n num">${fmt(s.value)}</td><td class="n num">${s.avg != null ? fmt(s.avg, 1) : '—'}</td></tr>`).join('')}
      </tbody></table></div><p class="note">الكميات من الدفاتر. سجّل جرداً فعلياً من «تسجيل حركة ← جرد مخزون» عند أي فرق.</p></div>
      <div class="panel"><h3>العملاء والعُهد والسلف</h3><div class="tbl"><table><thead><tr><th>الطرف</th><th class="n">ر.س</th><th class="n">ر.ي</th></tr></thead><tbody>
        ${d.customers.map((c) => `<tr><td>${h(c.party)}</td><td class="n num">${fmt(c.sar, 2)}</td><td class="n num">${fmt(c.yer)}</td></tr>`).join('') || '<tr><td colspan="3" class="note">كل حسابات العملاء مسددة</td></tr>'}
        ${d.custody.map((c) => `<tr><td>عهدة ${h(c.party)}</td><td class="n">—</td><td class="n num">${fmt(c.yer)}</td></tr>`).join('')}
        ${d.advances.map((c) => `<tr><td>سلفة ${h(c.party)}</td><td class="n">—</td><td class="n num">${fmt(c.yer)}</td></tr>`).join('')}
      </tbody></table></div></div>
    </div>
    <div class="panel"><div class="split"><h3>آخر الورديات المعتمدة</h3><button class="btn sm" id="toCost">تقرير التكلفة</button></div>
      ${d.recentShifts.length ? costTable(d.recentShifts, d.priceSar) : '<div class="empty">لم تُعتمد أي وردية بعد</div>'}</div>
  </section>`;
  main.querySelector('#toCost').addEventListener('click', () => app.go('reports', { report: 'cost' }));
}

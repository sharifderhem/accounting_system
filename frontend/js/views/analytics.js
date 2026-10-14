// Analytics (§12.2): change tiles, drivers, cost bridge, daily charts, shift comparison.
import { api } from '../api.js';
import { dShort, fmt, h } from '../util.js';
import { barChart, lineChart, pairBars, waterfall } from '../charts.js';

let period = 'week';

function tile(t) {
  if (t.cur == null) return `<div class="kpi"><div class="l">${t.label}</div><div class="v">—</div><div class="s">لا بيانات بعد</div></div>`;
  const v = fmt(t.cur, t.digits) + (t.unit === '%' ? '%' : '');
  let change = '<span class="note">لا فترة سابقة للمقارنة</span>';
  if (t.changePct != null) {
    const up = t.changePct > 0.01, down = t.changePct < -0.01;
    const good = !(up || down) ? null : (t.better === 'high') === up;
    change = good == null ? '<span class="chip">= دون تغيير</span>'
      : `<span class="chip ${good ? 'good' : 'bad'}">${up ? '▲' : '▼'} ${fmt(Math.abs(t.changePct), 1)}% · ${good ? 'تحسّن' : 'تراجع'}</span>`;
  }
  return `<div class="kpi"><div class="l">${t.label}</div><div class="v">${v}${t.unit !== '%' ? `<span class="s"> ${t.unit}</span>` : ''}</div><div class="s">${change}</div></div>`;
}

export async function render(main, app) {
  const d = await api.get('/analytics', { period });
  const label = {
    day: `يوم ${dShort(d.end)} مقابل اليوم السابق`,
    week: `آخر 7 أيام حتى ${dShort(d.end)} مقابل السبعة قبلها`,
    month: `آخر 30 يوماً حتى ${dShort(d.end)} مقابل الثلاثين قبلها`,
  }[d.period];
  const hasProd = d.chart.some((r) => r.cartons > 0);
  const M = d.shifts.morning, N = d.shifts.evening;
  main.innerHTML = `<section class="tab"><div class="split"><h2>التحليلات</h2>
      <div class="seg" id="perSeg">${[['day', 'يومي'], ['week', 'أسبوعي'], ['month', 'شهري']].map(([k, l]) => `<button data-per="${k}" aria-pressed="${k === period}">${l}</button>`).join('')}</div></div>
    <p class="lead">${label}. كل تغيير يظهر بسهم ووصف (تحسّن أو تراجع) مع اللون. مرّر الإصبع أو المؤشر على أي عمود لرؤية قيمته.</p>
    <div class="kpis">${d.tiles.map(tile).join('')}</div>
    <div class="panel"><h3>العوامل: ما الذي تحسّن وما الذي تراجع</h3>
      ${d.drivers.length ? `<div class="drv">${d.drivers.map((x) => `<div class="drv-r"><span class="chip ${x.good ? 'good' : 'bad'}">${x.good ? '▲ إيجابي' : '▼ سلبي'}</span><b>${h(x.title)}</b><span class="note">${h(x.text)}</span></div>`).join('')}</div>` : '<div class="empty">تظهر العوامل عندما تتوفر بيانات لفترتين.</div>'}</div>
    ${d.bridge ? `<div class="panel"><h3>لماذا تغيّرت تكلفة الكرتون؟ (ر.س)</h3>${waterfall(d.bridge)}<p class="note">الأحمر ▲ بند رفع تكلفة الكرتون والأخضر ▼ بند خفّضها؛ مجموع البنود يساوي الفرق بين الفترتين.</p></div>` : ''}
    <div class="panel"><div class="split"><h3>المصروفات والنثريات اليومية (ر.ي)</h3><span class="legend"><span><i style="background:var(--s1)"></i>أجور وإعاشة</span><span><i style="background:var(--s2)"></i>نثريات ومستلزمات</span></span></div>
      ${d.chart.some((r) => r.wages || r.petty) ? barChart(d.chart, [{ key: 'wages', name: 'أجور وإعاشة', color: '--s1' }, { key: 'petty', name: 'نثريات', color: '--s2' }], { unit: 'ر.ي' }) : '<div class="empty">لا مصروفات في آخر 30 يوماً</div>'}</div>
    <div class="panel"><h3>الإنتاج اليومي (كرتون)</h3>
      ${hasProd ? barChart(d.chart, [{ key: 'cartons', name: 'الإنتاج', color: '--s1' }], { ref: { value: d.capacityDay, label: `الطاقة القصوى ${fmt(d.capacityDay)}` }, unit: 'كرتون' }) : '<div class="empty">يظهر بعد اعتماد أول وردية</div>'}</div>
    <div class="panel"><h3>الطاقة اليومية (ك.و)</h3>
      ${hasProd ? barChart(d.chart, [{ key: 'kwh', name: 'الطاقة', color: '--s1' }], { unit: 'ك.و' }) + '<h3>الطاقة لكل كرتون (ك.و)</h3>' + lineChart(d.chart, 'kwhPer', { name: 'ك.و/كرتون' }) : '<div class="empty">يظهر بعد اعتماد أول وردية</div>'}
      <p class="note">تشمل عداد الماكينة وتقدير المبرد (${fmt(d.chillerKw, 2)} ك.و × ${fmt(d.chillerLoad * 100)}%). المبرد شبه ثابت، فالطاقة للكرتون تنخفض كلما زاد الإنتاج.</p></div>
    <div class="panel"><div class="split"><h3>مقارنة الورديتين</h3><span class="legend"><span><i style="background:var(--s1)"></i>صباحية (${M.n})</span><span><i style="background:var(--s2)"></i>مسائية (${N.n})</span></span></div>
      ${M.n || N.n ? `<div class="pbs">${pairBars('الإنتاج من الطاقة القصوى', M.eff, N.eff, { fmtV: (v) => fmt(v), unit: '%' })}${pairBars('نسبة التوقف', M.down, N.down, { unit: '%', better: 'low' })}${pairBars('الطاقة لكل كرتون', M.kwh, N.kwh, { unit: ' ك.و', better: 'low' })}${pairBars('تكلفة الكرتون', M.cost, N.cost, { unit: ' ر.س', better: 'low' })}</div>` : '<div class="empty">لا ورديات معتمدة في الفترة المختارة</div>'}</div>
  </section>`;
  main.querySelector('#perSeg').addEventListener('click', (e) => {
    const b = e.target.closest('[data-per]');
    if (b) { period = b.dataset.per; render(main, app); }
  });
}

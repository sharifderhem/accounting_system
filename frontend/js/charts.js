// Small SVG charts (from the prototype). Oldest day on the right to read naturally in RTL.
import { dShort, fmt, h } from './util.js';

const CW = () => Math.max(300, Math.min(760, ((document.getElementById('main')?.clientWidth) || 680) - 34));

function niceMax(v) {
  if (!(v > 0)) return 1;
  const p = Math.pow(10, Math.floor(Math.log10(v)));
  const m = v / p;
  return (m <= 1 ? 1 : m <= 2 ? 2 : m <= 2.5 ? 2.5 : m <= 5 ? 5 : 10) * p;
}

export function barChart(rows, series, { height = 200, ref = null, fmtV = (v) => fmt(v), unit = '' } = {}) {
  const W = CW(), L = 12, R = 56, T = 14, B = 26, iw = W - L - R, ih = height - T - B, n = rows.length;
  const tot = (r) => series.reduce((s, k) => s + (r[k.key] || 0), 0);
  const nice = niceMax(Math.max(1, ref?.value || 0, ...rows.map(tot)));
  const y = (v) => T + ih - v / nice * ih;
  const bw = Math.max(3, Math.min(22, iw / n * 0.62));
  const x = (i) => L + iw - (i + 0.5) * iw / n;
  let g = [0, nice / 2, nice].map((t) => `<line x1="${L}" x2="${L + iw}" y1="${y(t)}" y2="${y(t)}" stroke="var(--grid)"/>`
    + `<text x="${W - R + 6}" y="${y(t) + 4}" font-size="11" fill="var(--muted)" text-anchor="start">${fmtV(t)}</text>`).join('');
  const every = Math.ceil(n / Math.max(4, Math.floor(iw / 62)));
  rows.forEach((r, i) => {
    let base = 0;
    const cx = x(i);
    series.forEach((sv, si) => {
      const v = r[sv.key] || 0;
      if (v <= 0) return;
      const y1 = y(base + v), y0 = y(base) - (base > 0 ? 2 : 0);
      const top = series.slice(si + 1).every((k) => !(r[k.key] > 0));
      const rr = top ? Math.min(4, bw / 2, Math.max(0, y0 - y1)) : 0;
      g += `<path d="M${cx - bw / 2},${y0} V${y1 + rr} Q${cx - bw / 2},${y1} ${cx - bw / 2 + rr},${y1} H${cx + bw / 2 - rr} Q${cx + bw / 2},${y1} ${cx + bw / 2},${y1 + rr} V${y0} Z" fill="var(${sv.color})"/>`;
      base += v;
    });
    const tip = `${dShort(r.d)}: ${series.map((sv) => sv.name + ' ' + fmtV(r[sv.key] || 0)).join(' · ')}${series.length > 1 ? ' · المجموع ' + fmtV(tot(r)) : ''}${unit ? ' ' + unit : ''}`;
    g += `<rect x="${cx - iw / n / 2}" y="${T}" width="${iw / n}" height="${ih}" fill="transparent" data-tip="${h(tip)}"/>`;
    if (i % every === 0) g += `<text x="${cx}" y="${height - 8}" font-size="11" fill="var(--muted)" text-anchor="middle">${dShort(r.d)}</text>`;
  });
  if (ref) g += `<line x1="${L}" x2="${L + iw}" y1="${y(ref.value)}" y2="${y(ref.value)}" stroke="var(--muted)" stroke-dasharray="4 4"/>`
    + `<text x="${L + 4}" y="${y(ref.value) - 5}" font-size="11" fill="var(--muted)">${h(ref.label)}</text>`;
  g += `<line x1="${L}" x2="${L + iw}" y1="${T + ih}" y2="${T + ih}" stroke="var(--axis)"/>`;
  return `<svg viewBox="0 0 ${W} ${height}" class="chart" role="img">${g}</svg>`;
}

export function lineChart(rows, key, { height = 150, fmtV = (v) => fmt(v, 1), name = '' } = {}) {
  const W = CW(), L = 12, R = 56, T = 14, B = 26, iw = W - L - R, ih = height - T - B, n = rows.length;
  const pts = rows.map((r, i) => [i, r[key]]).filter((p) => p[1] != null && Number.isFinite(p[1]));
  if (!pts.length) return '';
  const nice = niceMax(Math.max(...pts.map((p) => p[1])) * 1.1 || 1);
  const y = (v) => T + ih - v / nice * ih, x = (i) => L + iw - (i + 0.5) * iw / n;
  let g = [0, nice / 2, nice].map((t) => `<line x1="${L}" x2="${L + iw}" y1="${y(t)}" y2="${y(t)}" stroke="var(--grid)"/>`
    + `<text x="${W - R + 6}" y="${y(t) + 4}" font-size="11" fill="var(--muted)">${fmtV(t)}</text>`).join('');
  g += `<polyline points="${pts.map((p) => x(p[0]) + ',' + y(p[1])).join(' ')}" fill="none" stroke="var(--s1)" stroke-width="2" stroke-linejoin="round"/>`;
  g += pts.map((p) => `<circle cx="${x(p[0])}" cy="${y(p[1])}" r="4" fill="var(--s1)" stroke="var(--surface)" stroke-width="2"/>`
    + `<circle cx="${x(p[0])}" cy="${y(p[1])}" r="12" fill="transparent" data-tip="${h(dShort(rows[p[0]].d) + ': ' + name + ' ' + fmtV(p[1]))}"/>`).join('');
  const every = Math.ceil(n / Math.max(4, Math.floor(iw / 62)));
  rows.forEach((r, i) => { if (i % every === 0) g += `<text x="${x(i)}" y="${height - 8}" font-size="11" fill="var(--muted)" text-anchor="middle">${dShort(r.d)}</text>`; });
  const last = pts[pts.length - 1];
  g += `<text x="${x(last[0])}" y="${y(last[1]) - 10}" font-size="11" font-weight="600" fill="var(--fg)" text-anchor="middle">${fmtV(last[1])}</text>`;
  return `<svg viewBox="0 0 ${W} ${height}" class="chart" role="img">${g}<line x1="${L}" x2="${L + iw}" y1="${T + ih}" y2="${T + ih}" stroke="var(--axis)"/></svg>`;
}

// Cost bridge: previous and current totals as tiles, component deltas as diverging bars.
// Red raised the cost, green lowered it; each bar also carries a sign so colour is never alone.
export function waterfall(bridge, { fmtV = (v) => fmt(v, 2) } = {}) {
  const W = CW(), rowH = 32, lab = Math.min(150, W * 0.36), vw = 58, mid = (W - lab) / 2, half = (W - lab) / 2 - vw;
  const deltas = bridge.deltas;
  const mx = Math.max(0.01, ...deltas.map((s) => Math.abs(s.value)));
  const height = deltas.length * rowH + 8;
  let g = `<line x1="${mid}" x2="${mid}" y1="0" y2="${height}" stroke="var(--axis)"/>`;
  deltas.forEach((s, i) => {
    const y = 4 + i * rowH, len = Math.max(2, Math.abs(s.value) / mx * half), up = s.value > 0, x = up ? mid - len : mid;
    g += `<text x="${W - 4}" y="${y + rowH / 2 + 4}" font-size="12" fill="var(--fg)" text-anchor="end">${h(s.label)}</text>`;
    g += `<rect x="${x}" y="${y + 7}" width="${len}" height="${rowH - 14}" rx="3" fill="${up ? 'var(--bad)' : 'var(--good)'}" data-tip="${h(s.label + ': ' + (up ? '+' : '') + fmtV(s.value) + ' ر.س للكرتون')}"/>`;
    g += `<text x="${up ? x - 5 : x + len + 5}" y="${y + rowH / 2 + 4}" font-size="12" font-weight="600" fill="var(--fg)" text-anchor="${up ? 'end' : 'start'}">${up ? '▲ +' : '▼ '}${fmtV(s.value)}</text>`;
  });
  const diff = bridge.current - bridge.previous;
  return `<div class="kpis" style="margin-bottom:8px"><div class="kpi"><div class="l">الفترة السابقة</div><div class="v">${fmtV(bridge.previous)}</div></div>`
    + `<div class="kpi"><div class="l">الفترة الحالية</div><div class="v">${fmtV(bridge.current)}</div><div class="s"><span class="chip ${diff > 0 ? 'bad' : 'good'}">${diff > 0 ? '▲ +' : '▼ '}${fmtV(diff)} · ${diff > 0 ? 'تراجع' : 'تحسّن'}</span></div></div></div>`
    + (deltas.length ? `<svg viewBox="0 0 ${W} ${height}" class="chart" role="img">${g}</svg>` : '<p class="note">لا تغيّر يُذكر في البنود.</p>');
}

// Morning vs evening small multiple.
export function pairBars(title, a, b, { fmtV = (v) => fmt(v, 1), better = 'high', unit = '' } = {}) {
  const mx = Math.max(a || 0, b || 0, 0.0001);
  const row = (lbl, v, col) => `<div class="pb-row"><span class="pb-l">${lbl}</span><span class="pb-track"><span class="pb-bar" style="width:${(v || 0) / mx * 100}%;background:var(${col})" data-tip="${h(lbl + ': ' + fmtV(v || 0) + unit)}"></span></span><span class="pb-v num">${v == null ? '—' : fmtV(v) + unit}</span></div>`;
  const win = a == null || b == null || Math.abs(a - b) < 1e-9 ? '' : ((better === 'high') === (a > b) ? 'الصباحية أفضل' : 'المسائية أفضل');
  return `<div class="pb"><div class="split"><b>${title}</b>${win ? `<span class="chip">★ ${win}</span>` : ''}</div>${row('صباحية', a, '--s1')}${row('مسائية', b, '--s2')}</div>`;
}

// One tooltip for every [data-tip] element, on hover or tap.
export function initTooltips() {
  const tip = document.createElement('div');
  tip.className = 'tip';
  tip.hidden = true;
  document.body.appendChild(tip);
  const show = (e) => {
    const t = e.target.closest?.('[data-tip]');
    if (!t) { tip.hidden = true; return; }
    tip.textContent = t.getAttribute('data-tip');
    tip.hidden = false;
    const x = Math.min(window.innerWidth - tip.offsetWidth - 8, Math.max(8, e.clientX - tip.offsetWidth / 2));
    tip.style.left = x + 'px';
    tip.style.top = Math.max(8, e.clientY - tip.offsetHeight - 12) + 'px';
  };
  document.addEventListener('pointermove', show);
  document.addEventListener('pointerdown', show);
  document.addEventListener('scroll', () => { tip.hidden = true; }, true);
}

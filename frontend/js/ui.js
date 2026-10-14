// Shared pieces: journal lines, entry previews, KPI tiles, cost table.
import { fmt, h, statusChip } from './util.js';

export function linesTable(lines, accounts) {
  return `<div class="tbl"><table><thead><tr><th>الحساب</th><th class="n">مدين ر.ي</th><th class="n">دائن ر.ي</th></tr></thead><tbody>${lines.map((l) => {
    const acc = accounts?.[l.a];
    const bits = [];
    if (l.party) bits.push(h(l.party));
    if (l.qty) bits.push(`<span class="num">${fmt(l.qty, l.qty % 1 ? 2 : 0)}</span> ${h(acc?.unit || '')}`);
    if (l.cur === 'SAR') bits.push(`<span class="num">${fmt(l.fc, 2)}</span> ر.س`);
    if (l.shift) bits.push(h(l.shift));
    return `<tr><td>${l.c ? '<span aria-hidden="true">&nbsp;&nbsp;&nbsp;</span>' : ''}<span class="num note">${h(l.a)}</span> ${h(acc?.name || l.a)}`
      + `${bits.length ? ` <span class="note">· ${bits.join(' · ')}</span>` : ''}${l.memo ? `<div class="note">${h(l.memo)}</div>` : ''}</td>`
      + `<td class="n num">${l.d ? fmt(l.d, 2) : ''}</td><td class="n num">${l.c ? fmt(l.c, 2) : ''}</td></tr>`;
  }).join('')}</tbody></table></div>`;
}

export function entryPreview(e, accounts, sources) {
  return `<div class="je"><div class="je-h"><span class="memo">${h(e.memo)}</span><span class="chip">${h(sources?.[e.src] || e.src)}</span>`
    + `${e.ref ? `<span class="chip num">${h(e.ref)}</span>` : ''}<span class="num note">${h(e.date)}</span></div>${linesTable(e.lines, accounts)}</div>`;
}

export function entryCard(e, accounts, sources, { canReverse = false, confirming = false } = {}) {
  const rev = e.status === 'reversed';
  const who = [e.created_by_label && `أنشأه ${h(e.created_by_label)}`, e.approved_by_label && `اعتمده ${h(e.approved_by_label)}`].filter(Boolean).join(' · ');
  return `<div class="je ${rev ? 'rev' : ''}"><div class="je-h"><span class="num note">${e.no}</span><span class="num note">${h(e.date)}</span>`
    + `<span class="memo">${h(e.memo)}</span><span class="chip">${h(sources[e.src] || e.src)}</span>${e.ref ? `<span class="chip num">${h(e.ref)}</span>` : ''}`
    + `${rev ? statusChip('reversed') : ''}${e.reverses_id ? '<span class="chip warn">↺ قيد عكسي</span>' : ''}`
    + `${canReverse && !rev && !e.reverses_id ? `<button class="btn sm" data-rev="${e.id}">عكس القيد</button>` : ''}</div>`
    + `${who ? `<div class="note" style="padding:4px 12px">${who}</div>` : ''}`
    + `${confirming ? `<div class="confirm"><span>سيُرحَّل قيد عكسي بتاريخ اليوم يلغي أثر هذا القيد.</span><button class="btn sm no" data-revok="${e.id}">تأكيد العكس</button><button class="btn sm" data-revno>إلغاء</button></div>` : ''}`
    + `${linesTable(e.lines, accounts)}</div>`;
}

export function kpi(label, value, sub = '') {
  return `<div class="kpi"><div class="l">${label}</div><div class="v">${value}</div>${sub ? `<div class="s">${sub}</div>` : ''}</div>`;
}

export function costTable(rows, priceSar) {
  return `<div class="tbl"><table><thead><tr><th>التاريخ</th><th>الوردية</th><th class="n">كراتين</th><th class="n">مواد كغ</th><th class="n">ك.و</th>`
    + `<th class="n">التكلفة ر.ي</th><th class="n">الكرتون ر.س</th><th class="n">الهامش ر.س</th></tr></thead><tbody>${rows.map((s) => `<tr><td class="num">${h(s.date)}</td>`
    + `<td>${h(s.shift)}</td><td class="n num">${fmt(s.cartons)}</td><td class="n num">${fmt(s.rmKg)}</td><td class="n num">${fmt(s.kwh)}</td>`
    + `<td class="n num">${fmt(s.total)}</td><td class="n num">${fmt(s.perSar, 2)}</td><td class="n num">${fmt(s.marginSar ?? (priceSar - s.perSar), 2)}</td></tr>`).join('')}</tbody></table></div>`;
}

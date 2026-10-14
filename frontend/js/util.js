// Small shared helpers: escaping, number formatting and parsing, dates, toasts, status chips.

export const $ = (id) => document.getElementById(id);
export const h = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

// Western digits with thousands separators (spec §1.9).
export const fmt = (x, d = 0) => (x < 0 ? '-' : '') + Math.abs(+x || 0).toLocaleString('en-US', { minimumFractionDigits: d, maximumFractionDigits: d });
export const money = (x, cur = 'ر.ي', d = 0) => `<span class="num">${fmt(x, d)}</span> ${cur}`;

// Accept Arabic-Indic digits (٠-٩) and Arabic separators (٫ ٬) as well as Western ones.
export function num(v) {
  if (v === '' || v == null) return NaN;
  const s = String(v).trim()
    .replace(/[٠-٩]/g, (d) => '٠١٢٣٤٥٦٧٨٩'.indexOf(d))
    .replace(/[۰-۹]/g, (d) => '۰۱۲۳۴۵۶۷۸۹'.indexOf(d))
    .replace(/[٬,\s]/g, '').replace('٫', '.');
  return s === '' ? NaN : +s;
}
// Number or null, for optional API fields.
export const numOrNull = (v) => { const n = num(v); return Number.isFinite(n) ? n : null; };

export const today = () => new Date().toLocaleDateString('en-CA', { timeZone: 'Asia/Aden' });
export const addDays = (d, n) => new Date(Date.parse(d + 'T00:00:00Z') + n * 864e5).toISOString().slice(0, 10);
export const dShort = (d) => d.slice(8, 10) + '/' + d.slice(5, 7);

export function toast(text) {
  const el = $('toast');
  el.textContent = text;
  el.hidden = false;
  clearTimeout(toast.t);
  toast.t = setTimeout(() => { el.hidden = true; }, 3200);
}

// Status always shows icon + word + colour (spec §18).
const STATUS = {
  pending: ['warn', '⏳', 'بانتظار الاعتماد'],
  approved: ['good', '✓', 'معتمد'],
  rejected: ['', '✕', 'مرفوض'],
  withdrawn: ['', '↩', 'مسحوب'],
  posted: ['good', '✓', 'مرحّل'],
  reversed: ['bad', '↺', 'معكوس'],
};
export function statusChip(status, label) {
  const [cls, icon, word] = STATUS[status] || ['', '', status];
  return `<span class="chip ${cls}">${icon} ${h(label || word)}</span>`;
}

export function alertBox(level, text) {
  const cls = { bad: 'alert bad', info: 'alert info', good: 'alert good' }[level] || 'alert';
  const icon = { bad: '⛔', info: 'ℹ', good: '✓' }[level] || '⚠';
  return `<div class="${cls}"><span aria-hidden="true">${icon}</span><span>${h(text)}</span></div>`;
}

// Show a server error next to the field it names, or in the message box.
export function showError(root, msgEl, err) {
  root.querySelectorAll('[aria-invalid]').forEach((el) => el.removeAttribute('aria-invalid'));
  root.querySelectorAll('.err').forEach((el) => el.remove());
  const field = err && err.field;
  const target = field ? root.querySelector(`[data-field="${CSS.escape(field)}"]`) : null;
  if (target) {
    target.setAttribute('aria-invalid', 'true');
    const p = document.createElement('div');
    p.className = 'err';
    p.textContent = err.message;
    (target.closest('label') || target).after(p);
    target.focus();
    if (msgEl) msgEl.innerHTML = '';
  } else if (msgEl) {
    msgEl.innerHTML = `<div class="msg bad">${h(err.message || err)}</div>`;
  }
}

export function clearErrors(root) {
  root.querySelectorAll('[aria-invalid]').forEach((el) => el.removeAttribute('aria-invalid'));
  root.querySelectorAll('.err').forEach((el) => el.remove());
}

// Read named inputs inside a container into an object. data-num marks number fields.
export function readForm(root) {
  const out = {};
  root.querySelectorAll('[data-field]').forEach((el) => {
    if (el.closest('[data-skip]')) return;
    const k = el.dataset.field;
    if (k.includes('.')) return; // nested line fields are read by the form itself
    if (el.type === 'checkbox') out[k] = el.checked;
    else if ('num' in el.dataset) out[k] = numOrNull(el.value);
    else out[k] = el.value.trim();
  });
  return out;
}

export function busy(btn, on) { if (btn) btn.disabled = on; }

export function select(attrs, options, selected) {
  return `<select ${attrs}>${options.map(([v, l]) => `<option value="${h(v)}"${String(v) === String(selected) ? ' selected' : ''}>${h(l)}</option>`).join('')}</select>`;
}

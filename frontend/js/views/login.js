import { api } from '../api.js';
import { busy, h } from '../util.js';

export function render(main, onLogin) {
  main.innerHTML = `<form class="gate panel" id="loginForm" autocomplete="on">
    <h2>تسجيل الدخول</h2>
    <p class="note" style="text-align:center">الحسابات يُنشئها صاحب المصنع فقط.</p>
    <label class="f">اسم المستخدم<input name="username" id="lgUser" autocomplete="username" autocapitalize="off" required></label>
    <label class="f">كلمة المرور<input name="password" id="lgPass" type="password" autocomplete="current-password" required></label>
    <button class="btn pri big" id="lgBtn" type="submit">دخول</button>
    <div id="lgMsg" role="alert"></div>
  </form>`;
  const form = main.querySelector('#loginForm');
  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const btn = form.querySelector('#lgBtn');
    busy(btn, true);
    try {
      const user = await api.post('/auth/login', { username: form.username.value.trim(), password: form.password.value });
      await onLogin(user);
    } catch (err) {
      form.querySelector('#lgMsg').innerHTML = `<div class="msg bad">${h(err.message)}</div>`;
      busy(btn, false);
    }
  });
  form.username.focus();
}

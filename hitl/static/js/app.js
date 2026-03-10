/* HITL Console — Frontend */

// ── State ────────────────────────────────────────
let token = localStorage.getItem('hitl_token') || '';
let currentUser = null;
let teams = [];
let activeTeam = '';
let activeView = 'inbox';
let activeFilter = 'pending';
let ws = null;

// ── Helpers ──────────────────────────────────────
function esc(s) { const d = document.createElement('div'); d.textContent = s || ''; return d.innerHTML; }

function toast(msg, type = 'success') {
  const c = document.getElementById('toasts');
  const el = document.createElement('div');
  el.className = `toast toast-${type}`;
  el.textContent = msg;
  c.appendChild(el);
  setTimeout(() => el.remove(), 3500);
}

function timeAgo(iso) {
  if (!iso) return '';
  const diff = (Date.now() - new Date(iso).getTime()) / 1000;
  if (diff < 60) return 'maintenant';
  if (diff < 3600) return Math.floor(diff / 60) + ' min';
  if (diff < 86400) return Math.floor(diff / 3600) + 'h';
  return Math.floor(diff / 86400) + 'j';
}

async function api(url, opts = {}) {
  const headers = { 'Content-Type': 'application/json' };
  if (token) headers['Authorization'] = `Bearer ${token}`;
  const res = await fetch(url, { headers, ...opts, body: opts.body ? JSON.stringify(opts.body) : undefined });
  if (res.status === 401) { doLogout(); throw new Error('Session expiree'); }
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || 'Erreur serveur');
  }
  return res.json();
}

function openModal(id) { document.getElementById(id).classList.add('active'); }
function closeModal(id) { document.getElementById(id).classList.remove('active'); }

// ── Auth ─────────────────────────────────────────
async function doLogin() {
  const email = document.getElementById('login-email').value.trim();
  const password = document.getElementById('login-password').value;
  const errEl = document.getElementById('login-error');
  errEl.style.display = 'none';
  try {
    const data = await api('/api/auth/login', { method: 'POST', body: { email, password } });
    token = data.token;
    localStorage.setItem('hitl_token', token);
    currentUser = data.user;
    onLoggedIn();
  } catch (e) {
    errEl.textContent = e.message;
    errEl.style.display = 'block';
  }
}

async function handleGoogleCredential(response) {
  const errEl = document.getElementById('login-error');
  errEl.style.display = 'none';
  try {
    const data = await api('/api/auth/google', { method: 'POST', body: { credential: response.credential } });
    token = data.token;
    localStorage.setItem('hitl_token', token);
    currentUser = data.user;
    onLoggedIn();
  } catch (e) {
    errEl.textContent = e.message;
    errEl.style.display = 'block';
  }
}

async function initGoogleSignIn() {
  try {
    const data = await fetch('/api/auth/google/client-id').then(r => r.json());
    if (!data.client_id) return;
    // Wait for Google Identity Services script to load
    const waitForGoogle = () => new Promise((resolve) => {
      if (typeof google !== 'undefined' && google.accounts) { resolve(); return; }
      let attempts = 0;
      const iv = setInterval(() => {
        attempts++;
        if (typeof google !== 'undefined' && google.accounts) { clearInterval(iv); resolve(); }
        else if (attempts > 50) { clearInterval(iv); resolve(); } // 5s timeout
      }, 100);
    });
    await waitForGoogle();
    if (typeof google === 'undefined' || !google.accounts) return;
    google.accounts.id.initialize({
      client_id: data.client_id,
      callback: handleGoogleCredential,
    });
    google.accounts.id.renderButton(
      document.getElementById('google-signin-btn'),
      { theme: 'filled_black', size: 'large', width: 300, text: 'signin_with', shape: 'pill' }
    );
  } catch (e) { console.warn('Google Sign-In init failed:', e); }
}

function doLogout() {
  token = '';
  currentUser = null;
  localStorage.removeItem('hitl_token');
  document.getElementById('app').style.display = 'none';
  document.getElementById('register-screen').style.display = 'none';
  document.getElementById('login-screen').style.display = 'flex';
  if (ws) { ws.close(); ws = null; }
}

function showRegister() {
  document.getElementById('login-screen').style.display = 'none';
  document.getElementById('register-screen').style.display = 'flex';
  document.getElementById('register-error').style.display = 'none';
}

function showLogin() {
  document.getElementById('register-screen').style.display = 'none';
  document.getElementById('login-screen').style.display = 'flex';
}

async function doRegister() {
  const email = document.getElementById('reg-email').value.trim();
  const culture = document.getElementById('reg-culture').value;
  const errEl = document.getElementById('register-error');
  errEl.style.display = 'none';

  if (!email || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
    errEl.textContent = 'Email invalide'; errEl.style.display = 'block'; return;
  }

  try {
    await api('/api/auth/register', { method: 'POST', body: { email, culture } });
    toast('Compte cree ! Un email de reinitialisation vous sera envoye.', 'success');
    showLogin();
    document.getElementById('login-email').value = email;
  } catch (e) {
    errEl.textContent = e.message;
    errEl.style.display = 'block';
  }
}

async function checkAuth() {
  if (!token) return false;
  try {
    currentUser = await api('/api/auth/me');
    return true;
  } catch { return false; }
}

async function onLoggedIn() {
  document.getElementById('login-screen').style.display = 'none';
  document.getElementById('app').style.display = 'flex';
  document.getElementById('top-user').textContent = currentUser.email;
  // Load teams
  teams = await api('/api/teams');
  if (teams.length > 0) {
    activeTeam = teams[0].id;
  }
  connectWS();
  switchView('inbox');
}

// ── WebSocket ────────────────────────────────────
function connectWS() {
  if (!activeTeam || !token) return;
  if (ws) ws.close();
  const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
  ws = new WebSocket(`${proto}//${location.host}/api/teams/${activeTeam}/ws?token=${token}`);
  ws.onmessage = (e) => {
    const evt = JSON.parse(e.data);
    if (evt.type === 'new_question' && activeView === 'inbox') loadInbox();
    if (evt.type === 'question_answered' && activeView === 'inbox') loadInbox();
  };
  ws.onclose = () => { setTimeout(connectWS, 5000); };
}

// ── Navigation ───────────────────────────────────
function switchView(view) {
  activeView = view;
  document.querySelectorAll('.sidebar-item').forEach(el => {
    el.classList.toggle('active', el.dataset.view === view);
  });
  if (view === 'inbox') loadInbox();
  else if (view === 'agents') loadAgents();
  else if (view === 'members') loadMembers();
  else if (view === 'reply') {} // loaded by openQuestion
}

function switchTeam(teamId) {
  activeTeam = teamId;
  connectWS();
  switchView(activeView);
}

function setFilter(f) {
  activeFilter = f;
  loadInbox();
}

// ── Team switcher HTML ───────────────────────────
function teamSwitcherHTML() {
  return `<div class="team-switcher">${teams.map(t =>
    `<button class="team-chip ${t.id === activeTeam ? 'active' : ''}" onclick="switchTeam('${esc(t.id)}')">${esc(t.name)}</button>`
  ).join('')}</div>`;
}

// ── Inbox ────────────────────────────────────────
async function loadInbox() {
  const content = document.getElementById('content');
  content.innerHTML = '<div class="loading">Chargement...</div>';
  try {
    const [questions, stats] = await Promise.all([
      api(`/api/teams/${activeTeam}/questions?status=${activeFilter === 'all' ? '' : activeFilter}&limit=50`),
      api(`/api/teams/${activeTeam}/questions/stats`),
    ]);
    // Update badge
    const badge = document.getElementById('badge-pending');
    if (stats.pending > 0) { badge.textContent = stats.pending; badge.style.display = 'inline'; }
    else { badge.style.display = 'none'; }

    let html = teamSwitcherHTML();
    html += `<div class="page-header">
      <span class="page-title">Inbox · ${esc(teams.find(t=>t.id===activeTeam)?.name || activeTeam)}</span>
      <div class="filters">
        ${['all','pending','answered'].map(f => `<button class="filter-chip ${activeFilter===f?'active':''}" onclick="setFilter('${f}')">${f.toUpperCase()}</button>`).join('')}
      </div>
    </div>`;

    if (questions.length === 0) {
      html += '<div class="empty-state">Aucune question en attente</div>';
    } else {
      questions.forEach(q => {
        const isRelance = q.remind_count > 0;
        html += `<div class="card ${q.status === 'pending' ? 'highlight' : ''}" style="cursor:pointer" onclick="openQuestion('${q.id}')">
          <div class="card-row">
            <div>
              <div class="card-tags">
                <span class="tag tag-accent">${esc(q.agent_id)}</span>
                ${isRelance ? '<span class="tag tag-yellow">RELANCE</span>' : ''}
                ${q.request_type === 'approval' ? '<span class="tag tag-green">APPROVAL</span>' : ''}
              </div>
              <div class="card-question">${esc(q.prompt)}</div>
            </div>
            <span class="card-time">il y a ${timeAgo(q.created_at)}</span>
          </div>
        </div>`;
      });
    }
    html += `<div class="stats-bar">${stats.pending} en attente · ${stats.relances} relances · ${stats.total} total</div>`;
    content.innerHTML = html;
  } catch (e) { content.innerHTML = `<div class="empty-state">${esc(e.message)}</div>`; }
}

// ── Reply ────────────────────────────────────────
async function openQuestion(qid) {
  activeView = 'reply';
  const content = document.getElementById('content');
  content.innerHTML = '<div class="loading">Chargement...</div>';
  try {
    const q = await api(`/api/questions/${qid}`);
    const teamName = teams.find(t => t.id === activeTeam)?.name || activeTeam;
    let ctxHtml = '';
    if (q.context && Object.keys(q.context).length > 0) {
      ctxHtml = Object.entries(q.context).map(([k,v]) =>
        `<span>${esc(k)}: <span>${esc(typeof v === 'string' ? v : JSON.stringify(v))}</span></span>`
      ).join('');
    }

    let html = `
      <div class="breadcrumb">
        <a onclick="switchView('inbox')">${esc(teamName)}</a><span>/</span>
        <a onclick="switchView('inbox')">INBOX</a><span>/</span>
        <span class="current">${esc(q.agent_id)}</span>
      </div>
      <div class="question-box">
        <div class="question-label">QUESTION</div>
        <div class="question-text">${esc(q.prompt)}</div>
        <div class="question-meta">
          <span>thread: <span>${esc(q.thread_id || '—')}</span></span>
          <span>type: <span>${esc(q.request_type)}</span></span>
          <span>recu: <span style="color:var(--yellow)">il y a ${timeAgo(q.created_at)}</span></span>
          ${ctxHtml}
        </div>
      </div>`;

    if (q.status === 'pending') {
      html += `
        <textarea class="reply-area" id="reply-text" placeholder="Ta reponse..."></textarea>
        <div class="reply-actions">
          <button class="btn btn-primary" onclick="submitAnswer('${q.id}', 'answer')">ENVOYER</button>
          ${q.request_type === 'approval' ? `
            <button class="btn btn-approve" onclick="submitAnswer('${q.id}', 'approve')">&#x2713; APPROVE</button>
            <button class="btn btn-reject" onclick="submitAnswer('${q.id}', 'reject')">&#x2717; REJECT</button>
          ` : ''}
        </div>`;
    } else {
      html += `
        <div class="card" style="margin-top:12px">
          <div class="question-label">REPONSE (${esc(q.status)})</div>
          <div style="font-size:12px;color:var(--text);margin-top:4px">${esc(q.response || '—')}</div>
          <div style="font-size:9px;color:var(--text-muted);margin-top:6px">
            par ${esc(q.reviewer || '—')} via ${esc(q.response_channel || '—')} · il y a ${timeAgo(q.answered_at)}
          </div>
        </div>`;
    }
    content.innerHTML = html;
  } catch (e) { content.innerHTML = `<div class="empty-state">${esc(e.message)}</div>`; }
}

async function submitAnswer(qid, action) {
  const response = document.getElementById('reply-text')?.value || '';
  if (action === 'answer' && !response.trim()) { toast('Reponse vide', 'error'); return; }
  try {
    await api(`/api/questions/${qid}/answer`, { method: 'POST', body: { response, action } });
    toast(action === 'approve' ? 'Approuve' : action === 'reject' ? 'Rejete' : 'Reponse envoyee');
    switchView('inbox');
  } catch (e) { toast(e.message, 'error'); }
}

// ── Agents ───────────────────────────────────────
async function loadAgents() {
  const content = document.getElementById('content');
  content.innerHTML = '<div class="loading">Chargement...</div>';
  try {
    const agents = await api(`/api/teams/${activeTeam}/agents`);
    const teamName = teams.find(t => t.id === activeTeam)?.name || activeTeam;
    let html = teamSwitcherHTML();
    html += `<div class="page-title" style="margin-bottom:14px">Agents · ${esc(teamName)}</div>`;

    if (agents.length === 0) {
      html += '<div class="empty-state">Aucun agent configure</div>';
    } else {
      agents.forEach(a => {
        const hasActivity = !!a.last_activity;
        html += `<div class="card">
          <div class="card-row" style="align-items:center">
            <div style="display:flex;align-items:center;gap:8px">
              <span class="status-dot ${hasActivity ? 'online' : 'offline'}"></span>
              <span style="font-size:12px;color:var(--text)">${esc(a.name)}</span>
              <span class="tag tag-accent">${esc(a.id)}</span>
            </div>
            <span class="card-time">${a.last_activity ? 'il y a ' + timeAgo(a.last_activity) : 'aucune activite'}</span>
          </div>
          <div class="agent-stats">
            <span>questions <span class="val">${a.total}</span></span>
            <span>en attente <span class="${a.pending > 0 ? 'val-warn' : 'val'}">${a.pending}</span></span>
            <span>type <span class="val">${esc(a.type)}</span></span>
          </div>
        </div>`;
      });
    }
    content.innerHTML = html;
  } catch (e) { content.innerHTML = `<div class="empty-state">${esc(e.message)}</div>`; }
}

// ── Members ──────────────────────────────────────
async function loadMembers() {
  const content = document.getElementById('content');
  content.innerHTML = '<div class="loading">Chargement...</div>';
  try {
    const members = await api(`/api/teams/${activeTeam}/members`);
    const teamName = teams.find(t => t.id === activeTeam)?.name || activeTeam;
    let html = teamSwitcherHTML();
    html += `<div class="page-header">
      <div class="page-title">Membres · ${esc(teamName)}</div>
      <button class="btn-invite" onclick="openModal('modal-invite')">+ Inviter</button>
    </div>`;

    if (members.length === 0) {
      html += '<div class="empty-state">Aucun membre</div>';
    } else {
      members.forEach(m => {
        const initial = (m.display_name || m.email)[0].toUpperCase();
        const isOnline = m.last_login && (Date.now() - new Date(m.last_login).getTime()) < 3600000;
        html += `<div class="card">
          <div class="member-row">
            <div class="member-info">
              <div class="member-avatar">${esc(initial)}</div>
              <div>
                <div class="member-name">${esc(m.display_name || m.email)}</div>
                <div class="member-email">${esc(m.email)}</div>
              </div>
            </div>
            <div class="member-right">
              <span class="tag ${m.team_role === 'admin' ? 'tag-yellow' : ''}" style="font-size:9px">${esc(m.team_role)}</span>
              <span class="status-dot ${isOnline ? 'online' : 'offline'}"></span>
              ${currentUser && currentUser.role === 'admin' ? `<div class="member-actions"><button onclick="removeMember('${m.id}')">retirer</button></div>` : ''}
            </div>
          </div>
        </div>`;
      });
    }
    content.innerHTML = html;
  } catch (e) { content.innerHTML = `<div class="empty-state">${esc(e.message)}</div>`; }
}

async function doInvite() {
  const email = document.getElementById('invite-email').value.trim();
  const name = document.getElementById('invite-name').value.trim();
  const password = document.getElementById('invite-password').value;
  const role = document.getElementById('invite-role').value;
  if (!email) { toast('Email requis', 'error'); return; }
  try {
    await api(`/api/teams/${activeTeam}/members`, {
      method: 'POST',
      body: { email, display_name: name, password, role },
    });
    toast('Membre invite');
    closeModal('modal-invite');
    loadMembers();
  } catch (e) { toast(e.message, 'error'); }
}

async function removeMember(userId) {
  if (!confirm('Retirer ce membre de l\'equipe ?')) return;
  try {
    await api(`/api/teams/${activeTeam}/members/${userId}`, { method: 'DELETE' });
    toast('Membre retire');
    loadMembers();
  } catch (e) { toast(e.message, 'error'); }
}

// ── Keyboard shortcuts ───────────────────────────
document.addEventListener('keydown', (e) => {
  if (e.key === 'Enter') {
    if (document.getElementById('login-screen').style.display === 'flex') doLogin();
    else if (document.getElementById('register-screen').style.display === 'flex') doRegister();
  }
  if (e.key === 'Escape') {
    document.querySelectorAll('.modal-overlay.active').forEach(m => m.classList.remove('active'));
  }
});

// ── Email validation hint ────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  const regEmail = document.getElementById('reg-email');
  const hint = document.getElementById('reg-email-hint');
  if (regEmail && hint) {
    regEmail.addEventListener('input', () => {
      const v = regEmail.value.trim();
      if (!v) { hint.textContent = ''; hint.style.color = ''; return; }
      if (/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(v)) {
        hint.textContent = 'Email valide'; hint.style.color = 'var(--green)';
      } else {
        hint.textContent = 'Format email invalide'; hint.style.color = 'var(--red)';
      }
    });
  }
});

// ── Init ─────────────────────────────────────────
(async () => {
  if (await checkAuth()) {
    onLoggedIn();
  }
  // Init Google Sign-In when library is loaded
  if (typeof google !== 'undefined') {
    initGoogleSignIn();
  } else {
    window.addEventListener('load', () => { initGoogleSignIn(); });
  }
})();

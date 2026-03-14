/* Production Manager — Frontend
   Vanilla JS SPA — Linear-inspired dark mode */

// ── State ────────────────────────────────────────
let token = localStorage.getItem('hitl_token') || '';
let currentUser = null;
let teams = [];
let activeTeam = '';
let activeView = 'pm-inbox'; // pm-inbox | pm-issues | pm-reviews | pm-pulse | pm-projects | project-detail | create-project | hitl-inbox | agents | members
let activeFilter = 'all';
let ws = null;
let selectedIssue = null;
let selectedProject = null;
let sidebarCollapsed = false;
let createProjectState = { step: 1, name: '', team: '', startDate: '', targetDate: '', aiIssues: [], aiRelations: [], aiDescription: '', chatMessages: [] };

// ── SVG Icons ────────────────────────────────────
const Icons = {
  inbox: '<svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"><polyline points="2 8 2 14 14 14 14 8"/><polyline points="5 5 8 8 11 5"/><line x1="8" y1="2" x2="8" y2="8"/></svg>',
  issues: '<svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"><circle cx="8" cy="8" r="6"/><circle cx="8" cy="8" r="2"/></svg>',
  reviews: '<svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"><path d="M2 4h12v8H4l-2 2V4z"/></svg>',
  pulse: '<svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"><polyline points="1 8 4 8 6 3 8 13 10 6 12 8 15 8"/></svg>',
  projects: '<svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="2" width="5" height="5" rx="1"/><rect x="9" y="2" width="5" height="5" rx="1"/><rect x="2" y="9" width="5" height="5" rx="1"/><rect x="9" y="9" width="5" height="5" rx="1"/></svg>',
  hitl: '<svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"><circle cx="8" cy="5" r="3"/><path d="M2 14c0-3 2.7-5 6-5s6 2 6 5"/></svg>',
  agents: '<svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"><rect x="3" y="2" width="10" height="12" rx="2"/><line x1="6" y1="6" x2="10" y2="6"/><line x1="6" y1="9" x2="9" y2="9"/></svg>',
  members: '<svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"><circle cx="6" cy="5" r="2.5"/><path d="M1 14c0-3 2.5-5 5-5s5 2 5 5"/><circle cx="11" cy="5" r="2"/><path d="M12 9c1.5.5 3 2 3 5"/></svg>',
  filter: '<svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"><line x1="2" y1="4" x2="14" y2="4"/><line x1="4" y1="8" x2="12" y2="8"/><line x1="6" y1="12" x2="10" y2="12"/></svg>',
  plus: '<svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"><line x1="8" y1="3" x2="8" y2="13"/><line x1="3" y1="8" x2="13" y2="8"/></svg>',
  back: '<svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="10 3 5 8 10 13"/></svg>',
  search: '<svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"><circle cx="7" cy="7" r="5"/><line x1="11" y1="11" x2="14" y2="14"/></svg>',
  // Status icons
  circle: '<svg width="12" height="12" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5"><circle cx="8" cy="8" r="5"/></svg>',
  circleDashed: '<svg width="12" height="12" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-dasharray="3 2"><circle cx="8" cy="8" r="5"/></svg>',
  halfCircle: '<svg width="12" height="12" viewBox="0 0 16 16" fill="none" stroke-width="1.5"><circle cx="8" cy="8" r="5" stroke="currentColor"/><path d="M8 3a5 5 0 0 1 0 10V3z" fill="currentColor"/></svg>',
  clock: '<svg width="12" height="12" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"><circle cx="8" cy="8" r="6"/><polyline points="8 5 8 8 10.5 9.5"/></svg>',
  check: '<svg width="12" height="12" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 8 7 12 13 4"/></svg>',
  lock: '<svg width="10" height="10" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"><rect x="3" y="8" width="10" height="6" rx="1"/><path d="M5 8V5a3 3 0 0 1 6 0v3"/></svg>',
};

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
  if (diff < 60) return 'now';
  if (diff < 3600) return Math.floor(diff / 60) + 'm';
  if (diff < 86400) return Math.floor(diff / 3600) + 'h';
  return Math.floor(diff / 86400) + 'd';
}

async function api(url, opts = {}) {
  const headers = { 'Content-Type': 'application/json' };
  if (token) headers['Authorization'] = `Bearer ${token}`;
  const res = await fetch(url, { headers, ...opts, body: opts.body ? JSON.stringify(opts.body) : undefined });
  const isAuthRoute = url.startsWith('/api/auth/');
  if (res.status === 401 && !isAuthRoute) { doLogout(); throw new Error('Session expired'); }
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || 'Server error');
  }
  return res.json();
}

function openModal(id) { document.getElementById(id).classList.add('active'); }
function closeModal(id) { document.getElementById(id).classList.remove('active'); }

// ── Shared Components ────────────────────────────
const AVATAR_COLORS = ['#6366f1', '#f59e0b', '#10b981', '#ef4444', '#8b5cf6', '#ec4899', '#06b6d4'];

function renderAvatar(name, size = 20) {
  if (!name) name = '?';
  const idx = name.charCodeAt(0) % AVATAR_COLORS.length;
  const initials = name.split(' ').map(n => n[0]).join('').slice(0, 2).toUpperCase();
  return `<div class="avatar" style="width:${size}px;height:${size}px;font-size:${size * 0.42}px;background:${AVATAR_COLORS[idx]}">${esc(initials)}</div>`;
}

function renderStatusIcon(status) {
  const map = {
    backlog: { icon: Icons.circleDashed, color: 'var(--text-quaternary)' },
    todo: { icon: Icons.circle, color: 'var(--accent-orange)' },
    'in-progress': { icon: Icons.halfCircle, color: 'var(--accent-yellow)' },
    'in-review': { icon: Icons.clock, color: 'var(--accent-blue)' },
    done: { icon: Icons.check, color: 'var(--accent-green)' },
  };
  const s = map[status] || map.backlog;
  return `<span class="status-icon ${status || 'backlog'}" style="color:${s.color}">${s.icon}</span>`;
}

function renderPriorityBadge(level) {
  const colors = { 1: 'var(--accent-red)', 2: 'var(--accent-orange)', 3: 'var(--accent-yellow)', 4: 'var(--text-quaternary)' };
  const color = colors[level] || colors[4];
  let html = `<div class="priority-badge p${level}">`;
  for (let i = 1; i <= 4; i++) {
    const active = i <= (5 - level);
    html += `<div class="bar" style="height:${3 + i * 2.5}px;background:${active ? color : 'var(--border-subtle)'};opacity:${active ? 1 : 0.3}"></div>`;
  }
  return html + '</div>';
}

function renderTag(label, color) {
  if (!color) {
    if (label === 'critical' || label === 'bug') color = 'var(--accent-red)';
    else if (label === 'feature') color = 'var(--accent-blue)';
    else color = 'var(--accent-purple)';
  }
  return `<span class="tag" style="color:${color};background:${color}18">${esc(label)}</span>`;
}

function renderSparkline(data, color = 'var(--accent-blue)', width = 80, height = 24) {
  if (!data || data.length < 2) return '';
  const max = Math.max(...data), min = Math.min(...data), range = max - min || 1;
  const pts = data.map((v, i) => `${(i / (data.length - 1)) * width},${height - ((v - min) / range) * height}`).join(' ');
  return `<span class="sparkline"><svg width="${width}" height="${height}" style="overflow:visible"><polyline points="${pts}" fill="none" stroke="${color}" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg></span>`;
}

function renderProgressBar(value, color = 'var(--accent-blue)', width = 80) {
  return `<div class="progress-bar" style="width:${width}px"><div class="progress-bar-fill" style="width:${Math.min(100, Math.max(0, value))}%;background:${color}"></div></div>`;
}

const STATUS_LABELS = { backlog: 'Backlog', todo: 'Todo', 'in-progress': 'In Progress', 'in-review': 'In Review', done: 'Done' };
const STATUS_COLORS = { backlog: 'var(--text-quaternary)', todo: 'var(--accent-orange)', 'in-progress': 'var(--accent-yellow)', 'in-review': 'var(--accent-blue)', done: 'var(--accent-green)' };
const STATUS_ORDER = ['in-progress', 'in-review', 'todo', 'backlog', 'done'];
const PROJECT_STATUS_CONFIG = {
  'on-track': { label: 'On Track', color: 'var(--accent-green)' },
  'at-risk': { label: 'At Risk', color: 'var(--accent-orange)' },
  'off-track': { label: 'Off Track', color: 'var(--accent-red)' },
};

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
    errEl.textContent = e.message; errEl.style.display = 'block';
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
    errEl.textContent = e.message; errEl.style.display = 'block';
  }
}

async function initGoogleSignIn() {
  try {
    const data = await fetch('/api/auth/google/client-id').then(r => r.json());
    if (!data.client_id) return;
    const waitForGoogle = () => new Promise((resolve) => {
      if (typeof google !== 'undefined' && google.accounts) { resolve(); return; }
      let attempts = 0;
      const iv = setInterval(() => {
        attempts++;
        if (typeof google !== 'undefined' && google.accounts) { clearInterval(iv); resolve(); }
        else if (attempts > 50) { clearInterval(iv); resolve(); }
      }, 100);
    });
    await waitForGoogle();
    if (typeof google === 'undefined' || !google.accounts) return;
    google.accounts.id.initialize({ client_id: data.client_id, callback: handleGoogleCredential });
    google.accounts.id.renderButton(document.getElementById('google-signin-btn'),
      { theme: 'filled_black', size: 'large', width: 300, text: 'signin_with', shape: 'pill' });
  } catch (e) { console.warn('Google Sign-In init failed:', e); }
}

function doLogout() {
  token = ''; currentUser = null;
  localStorage.removeItem('hitl_token');
  document.getElementById('app').style.display = 'none';
  document.getElementById('register-screen').style.display = 'none';
  document.getElementById('login-screen').style.display = 'flex';
  if (ws) { ws.close(); ws = null; }
}

function showRegister() {
  document.getElementById('login-screen').style.display = 'none';
  document.getElementById('register-screen').style.display = 'flex';
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
    toast('Account created! Waiting for admin approval.', 'success');
    showLogin();
    document.getElementById('login-email').value = email;
  } catch (e) { errEl.textContent = e.message; errEl.style.display = 'block'; }
}

async function checkAuth() {
  if (!token) return false;
  try {
    const res = await fetch('/api/auth/me', { headers: { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' } });
    if (!res.ok) { token = ''; localStorage.removeItem('hitl_token'); return false; }
    currentUser = await res.json();
    return true;
  } catch { token = ''; localStorage.removeItem('hitl_token'); return false; }
}

async function onLoggedIn() {
  document.getElementById('login-screen').style.display = 'none';
  document.getElementById('app').style.display = 'flex';
  teams = await api('/api/teams');
  if (teams.length > 0) activeTeam = teams[0].id;
  buildSidebar();
  connectWS();
  switchView('pm-inbox');
}

// ── WebSocket ────────────────────────────────────
function connectWS() {
  if (!activeTeam || !token) return;
  if (ws) ws.close();
  const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
  ws = new WebSocket(`${proto}//${location.host}/api/teams/${activeTeam}/ws?token=${token}`);
  ws.onmessage = (e) => {
    const evt = JSON.parse(e.data);
    if (evt.type === 'new_question' || evt.type === 'question_answered') {
      if (activeView === 'hitl-inbox') loadHitlInbox();
    }
    if (evt.type === 'pm_inbox') {
      refreshInboxBadge();
      if (activeView === 'pm-inbox') loadPmInbox();
    }
  };
  ws.onclose = () => { setTimeout(connectWS, 5000); };
}

// ── Sidebar ──────────────────────────────────────
function buildSidebar() {
  // Nav items
  const navItems = [
    { id: 'pm-inbox', label: 'Inbox', icon: Icons.inbox, badge: 'inbox-badge' },
    { id: 'pm-issues', label: 'Issues', icon: Icons.issues },
    { id: 'pm-reviews', label: 'Reviews', icon: Icons.reviews },
    { id: 'pm-pulse', label: 'Pulse', icon: Icons.pulse },
  ];
  document.getElementById('sidebar-nav').innerHTML = navItems.map(item =>
    `<button class="sidebar-item" data-view="${item.id}" onclick="switchView('${item.id}')">
      <span class="icon">${item.icon}</span>
      <span class="sidebar-label">${item.label}</span>
      ${item.badge ? `<span class="badge" id="${item.badge}" style="display:none">0</span>` : ''}
    </button>`
  ).join('');

  // Workspace items
  const wsItems = [
    { id: 'pm-projects', label: 'Projects', icon: Icons.projects },
  ];
  document.getElementById('sidebar-workspace').innerHTML = wsItems.map(item =>
    `<button class="sidebar-item" data-view="${item.id}" onclick="switchView('${item.id}')">
      <span class="icon">${item.icon}</span>
      <span class="sidebar-label">${item.label}</span>
    </button>`
  ).join('');

  // HITL section
  const hitlSection = document.createElement('div');
  hitlSection.innerHTML = `
    <div class="sidebar-section-label">HITL</div>
    <button class="sidebar-item" data-view="hitl-inbox" onclick="switchView('hitl-inbox')">
      <span class="icon">${Icons.hitl}</span><span class="sidebar-label">Questions</span>
      <span class="badge" id="hitl-badge" style="display:none">0</span>
    </button>
    <button class="sidebar-item" data-view="agents" onclick="switchView('agents')">
      <span class="icon">${Icons.agents}</span><span class="sidebar-label">Agents</span>
    </button>
    <button class="sidebar-item" data-view="members" onclick="switchView('members')">
      <span class="icon">${Icons.members}</span><span class="sidebar-label">Members</span>
    </button>`;
  const teamsLabel = document.getElementById('sidebar-teams-label');
  teamsLabel.parentNode.insertBefore(hitlSection, teamsLabel);

  // Teams
  document.getElementById('sidebar-teams').innerHTML = teams.map(t =>
    `<div class="sidebar-team" onclick="switchTeam('${esc(t.id)}')">
      <div class="sidebar-team-dot" style="background:${t.color || '#6366f1'}"></div>
      <span class="sidebar-team-name sidebar-label">${esc(t.name)}</span>
      <span class="sidebar-team-code">${esc(t.id).toUpperCase()}</span>
    </div>`
  ).join('');

  // User
  document.getElementById('sidebar-user').innerHTML = `
    ${renderAvatar(currentUser?.display_name || currentUser?.email || '?', 24)}
    <span class="sidebar-user-name sidebar-label">${esc(currentUser?.display_name || currentUser?.email || '')}</span>
    <button class="chat-clear-btn" style="margin-left:auto;font-size:8px;padding:2px 6px" onclick="doLogout()">logout</button>`;

  // Toggle
  document.getElementById('sidebar-toggle').onclick = () => {
    sidebarCollapsed = !sidebarCollapsed;
    document.getElementById('pm-sidebar').classList.toggle('collapsed', sidebarCollapsed);
  };

  refreshInboxBadge();
  refreshHitlBadge();
}

function switchTeam(teamId) {
  activeTeam = teamId;
  connectWS();
  switchView(activeView);
}

// ── Navigation ───────────────────────────────────
function switchView(view) {
  activeView = view;
  selectedIssue = null;
  document.querySelectorAll('.sidebar-item').forEach(el => {
    el.classList.toggle('active', el.dataset.view === view);
  });
  const header = document.getElementById('pm-header');
  const content = document.getElementById('pm-content');

  if (view === 'pm-inbox') { renderHeader('Inbox'); loadPmInbox(); }
  else if (view === 'pm-issues') { renderHeader('Issues', true); loadPmIssues(); }
  else if (view === 'pm-reviews') { renderHeader('Reviews'); loadPmReviews(); }
  else if (view === 'pm-pulse') { renderHeader('Pulse'); loadPmPulse(); }
  else if (view === 'pm-projects') { renderHeader('Projects', false, true); loadPmProjects(); }
  else if (view === 'project-detail') { loadProjectDetail(); }
  else if (view === 'create-project') { loadCreateProject(); }
  else if (view === 'hitl-inbox') { renderHeader('HITL Questions'); loadHitlInbox(); }
  else if (view === 'agents') { renderHeader('Agents'); loadAgents(); }
  else if (view === 'members') { renderHeader('Members', false, false, true); loadMembers(); }
}

function renderHeader(title, showIssueAdd = false, showProjectAdd = false, showMemberAdd = false) {
  const header = document.getElementById('pm-header');
  header.innerHTML = `
    <span class="pm-header-title">${esc(title)}</span>
    <div class="pm-header-right">
      ${showIssueAdd ? `<button class="pm-header-btn-add" onclick="openCreateIssueModal()" title="New Issue">${Icons.plus}</button>` : ''}
      ${showProjectAdd ? `<button class="pm-header-btn-add" onclick="startCreateProject()" title="New Project">${Icons.plus}</button>` : ''}
      ${showMemberAdd ? `<button class="pm-header-btn" onclick="openModal('modal-invite')">+ Invite</button>` : ''}
    </div>`;
}

// ── Badge helpers ────────────────────────────────
async function refreshInboxBadge() {
  try {
    const data = await api('/api/pm/inbox');
    const unread = data.unread || 0;
    const badge = document.getElementById('inbox-badge');
    if (badge) { badge.textContent = unread; badge.style.display = unread > 0 ? '' : 'none'; }
  } catch (e) { /* ignore */ }
}

async function refreshHitlBadge() {
  try {
    const stats = await api(`/api/teams/${activeTeam}/questions/stats`);
    const badge = document.getElementById('hitl-badge');
    if (badge) { badge.textContent = stats.pending; badge.style.display = stats.pending > 0 ? '' : 'none'; }
  } catch (e) { /* ignore */ }
}

// ══════════════════════════════════════════════════
// PM INBOX (Notifications)
// ══════════════════════════════════════════════════
let inboxTab = 'all';
async function loadPmInbox() {
  const content = document.getElementById('pm-content');
  content.innerHTML = '<div class="loading">Loading...</div>';
  try {
    const data = await api('/api/pm/inbox');
    const notifications = data.notifications || [];
    let filtered = notifications;
    if (inboxTab === 'mentions') filtered = notifications.filter(n => n.type === 'mention');
    else if (inboxTab === 'assigned') filtered = notifications.filter(n => n.type === 'assign');
    else if (inboxTab === 'reviews') filtered = notifications.filter(n => n.type === 'review');

    let html = renderTabBar(['All', 'Mentions', 'Assigned', 'Reviews'], ['all', 'mentions', 'assigned', 'reviews'], inboxTab, 'inboxTab', 'loadPmInbox');

    if (filtered.length === 0) {
      html += '<div class="empty-state">No notifications</div>';
    } else {
      filtered.forEach((n, i) => {
        html += `<div class="notification-row ${n.read ? 'read' : ''} stagger-in" style="animation-delay:${i * 60}ms" onclick="markNotifRead(${n.id})">
          ${!n.read ? '<div class="notification-unread-dot"></div>' : '<div style="width:6px;flex-shrink:0"></div>'}
          ${renderAvatar(n.avatar || 'System', 28)}
          <div class="notification-text">
            <div class="notification-text-main ${n.read ? '' : 'unread'}">${esc(n.text)}</div>
            <div class="notification-text-sub">${esc(n.issue_id || '')}</div>
          </div>
          <span class="notification-time">${timeAgo(n.created_at)}</span>
        </div>`;
      });
    }

    if (notifications.some(n => !n.read)) {
      html += `<div style="padding:12px 20px;text-align:right"><button class="btn btn-outline" onclick="markAllRead()" style="font-size:11px">Mark all read</button></div>`;
    }
    content.innerHTML = html;
  } catch (e) { content.innerHTML = `<div class="empty-state">${esc(e.message)}</div>`; }
}

async function markNotifRead(id) {
  try { await api(`/api/pm/inbox/${id}/read`, { method: 'PUT' }); } catch (e) { /* ignore */ }
  loadPmInbox();
}

async function markAllRead() {
  try { await api('/api/pm/inbox/read-all', { method: 'PUT' }); } catch (e) { /* ignore */ }
  refreshInboxBadge();
  loadPmInbox();
}

// ══════════════════════════════════════════════════
// PM ISSUES
// ══════════════════════════════════════════════════
let issueGroupBy = 'status';
let issueFilter = {};
async function loadPmIssues() {
  const content = document.getElementById('pm-content');
  content.innerHTML = '<div class="loading">Loading...</div>';
  try {
    let url = `/api/pm/issues?team_id=${activeTeam}`;
    if (issueFilter.status) url += `&status=${issueFilter.status}`;
    if (issueFilter.assignee) url += `&assignee=${issueFilter.assignee}`;
    const issues = await api(url);

    let html = '<div style="display:flex;height:100%">';
    html += '<div style="flex:1;overflow:auto">';
    html += renderTabBar(['Status', 'Team', 'Assignee', 'Dependency'], ['status', 'team', 'assignee', 'dependency'], issueGroupBy, 'issueGroupBy', 'loadPmIssues');

    const groups = groupIssues(issues, issueGroupBy);
    const sortedKeys = issueGroupBy === 'status' ? STATUS_ORDER.filter(s => groups[s]) : Object.keys(groups).sort();

    sortedKeys.forEach(key => {
      const items = groups[key];
      html += renderIssueGroupHeader(key, items.length, issueGroupBy);
      items.forEach((issue, i) => {
        html += renderIssueRow(issue, i);
      });
    });

    html += '</div>';
    html += '<div id="issue-detail-panel"></div>';
    html += '</div>';
    content.innerHTML = html;
  } catch (e) { content.innerHTML = `<div class="empty-state">${esc(e.message)}</div>`; }
}

function groupIssues(issues, by) {
  const groups = {};
  if (by === 'dependency') {
    groups['Blocked'] = issues.filter(i => i.is_blocked);
    groups['Blocking others'] = issues.filter(i => (i.blocking_count || 0) > 0 && !i.is_blocked);
    groups['No dependencies'] = issues.filter(i => !i.is_blocked && !(i.blocking_count || 0));
    Object.keys(groups).forEach(k => { if (groups[k].length === 0) delete groups[k]; });
    return groups;
  }
  issues.forEach(i => {
    const key = by === 'status' ? i.status : by === 'team' ? i.team_id : (i.assignee || 'Unassigned');
    if (!groups[key]) groups[key] = [];
    groups[key].push(i);
  });
  return groups;
}

function renderIssueGroupHeader(key, count, groupBy) {
  let icon = '';
  let label = key;
  if (groupBy === 'status') { icon = renderStatusIcon(key); label = STATUS_LABELS[key] || key; }
  else if (groupBy === 'dependency') {
    if (key === 'Blocked') icon = `<span style="color:var(--accent-red)">${Icons.lock}</span>`;
    else if (key === 'Blocking others') icon = `<span style="color:var(--accent-orange)">&#x26A0;</span>`;
    else icon = `<span style="color:var(--text-quaternary)">${Icons.check}</span>`;
  }
  return `<div class="issue-group-header">${icon}<span>${esc(label)}</span><span class="count">${count}</span></div>`;
}

function renderIssueRow(issue, idx) {
  const blocked = issue.is_blocked;
  const blockingCount = issue.blocking_count || 0;
  const blockedByCount = issue.blocked_by_count || 0;
  return `<div class="issue-row ${selectedIssue?.id === issue.id ? 'selected' : ''} stagger-in" style="animation-delay:${idx * 40}ms" onclick="selectIssue('${esc(issue.id)}')">
    ${renderPriorityBadge(issue.priority || 3)}
    <span class="issue-id">${esc(issue.id)}</span>
    ${renderStatusIcon(issue.status)}
    ${blocked ? `<span style="color:var(--accent-red);display:flex;align-items:center;flex-shrink:0">${Icons.lock}</span>` : ''}
    ${blockingCount > 0 ? `<span class="dependency-indicator blocking">&#x26A0; ${blockingCount}</span>` : ''}
    <span class="issue-title ${blocked ? 'blocked' : ''}">${esc(issue.title)}</span>
    <div class="issue-tags">${(issue.tags || []).slice(0, 2).map(t => renderTag(t)).join('')}</div>
    ${issue.assignee ? renderAvatar(issue.assignee, 20) : ''}
    <span class="issue-time">${timeAgo(issue.created_at)}</span>
  </div>`;
}

async function selectIssue(issueId) {
  try {
    const issue = await api(`/api/pm/issues/${issueId}`);
    selectedIssue = issue;
    const panel = document.getElementById('issue-detail-panel');
    if (!panel) return;
    panel.className = 'detail-panel slide-in';
    panel.innerHTML = renderIssueDetailPanel(issue);
  } catch (e) { toast(e.message, 'error'); }
}

function renderIssueDetailPanel(issue) {
  const blocked = issue.is_blocked;
  const relations = issue.relations || [];
  let html = `<div class="detail-panel-header">
    <span style="font-size:11px;color:var(--text-quaternary);font-weight:500">${esc(issue.id)}</span>
    <button class="detail-panel-close" onclick="closeDetailPanel()">&#x00D7;</button>
  </div>
  <div class="detail-panel-body">`;

  if (blocked) {
    html += `<div class="blocked-banner">${Icons.lock} Blocked by ${issue.blocked_by_count || '?'} issue(s)</div>`;
  }

  html += `<div class="detail-panel-title">${esc(issue.title)}</div>
    <div class="detail-props">
      <div class="detail-prop"><span class="detail-prop-label">Status</span><div class="detail-prop-value">${renderStatusIcon(issue.status)} <span style="font-size:12px">${esc(STATUS_LABELS[issue.status] || issue.status)}</span>${blocked ? '<span style="color:var(--accent-red);font-size:10px">+ blocked</span>' : ''}</div></div>
      <div class="detail-prop"><span class="detail-prop-label">Priority</span><div class="detail-prop-value">${renderPriorityBadge(issue.priority || 3)} <span style="font-size:12px">P${issue.priority || 3}</span></div></div>
      <div class="detail-prop"><span class="detail-prop-label">Assignee</span><div class="detail-prop-value">${issue.assignee ? renderAvatar(issue.assignee, 18) + `<span style="font-size:12px">${esc(issue.assignee)}</span>` : '<span style="font-size:12px;color:var(--text-quaternary)">Unassigned</span>'}</div></div>
      <div class="detail-prop"><span class="detail-prop-label">Team</span><div class="detail-prop-value"><span style="font-size:12px">${esc(issue.team_id)}</span></div></div>
      <div class="detail-prop"><span class="detail-prop-label">Created</span><div class="detail-prop-value"><span style="font-size:12px;color:var(--text-tertiary)">${timeAgo(issue.created_at)} ago</span></div></div>
    </div>
    <div style="display:flex;gap:4px;margin-top:12px;flex-wrap:wrap">${(issue.tags || []).map(t => renderTag(t)).join('')}</div>
    <div style="margin-top:20px">
      <div style="font-size:12px;font-weight:600;color:var(--text-secondary);margin-bottom:10px">Dependencies</div>`;

  if (relations.length === 0) {
    html += '<span style="font-size:12px;color:var(--text-quaternary)">No dependencies</span>';
  } else {
    relations.forEach(rel => {
      const typeLabel = rel.display_type || rel.type;
      const isBlocking = rel.type === 'blocks' || rel.type === 'blocked-by';
      const color = isBlocking ? 'var(--accent-red)' : rel.type === 'relates-to' ? 'var(--accent-blue)' : 'var(--accent-purple)';
      html += `<div style="display:flex;align-items:center;gap:8px;padding:6px 0;border-bottom:1px solid var(--border-subtle)">
        <span class="relation-badge" style="color:${color};background:${color}18">${esc(typeLabel)}</span>
        <span style="font-size:11px;color:var(--accent-blue);font-weight:500;cursor:pointer" onclick="selectIssue('${esc(rel.related_issue_id)}')">${esc(rel.related_issue_id)}</span>
        ${rel.related_status ? renderStatusIcon(rel.related_status) : ''}
        <span style="font-size:11px;color:var(--text-tertiary);overflow:hidden;text-overflow:ellipsis;white-space:nowrap;flex:1">${esc(rel.related_title || '')}</span>
        <button style="background:none;border:none;color:var(--text-quaternary);cursor:pointer;font-size:14px" onclick="deleteRelation(${rel.id},event)">&#x00D7;</button>
      </div>`;
    });
  }

  html += `<button class="btn btn-outline" style="margin-top:8px;font-size:11px" onclick="openAddRelationModal('${esc(issue.id)}')">+ Add dependency</button>`;
  html += '</div></div>';
  return html;
}

function closeDetailPanel() {
  selectedIssue = null;
  const panel = document.getElementById('issue-detail-panel');
  if (panel) { panel.className = ''; panel.innerHTML = ''; }
}

async function deleteRelation(relId, e) {
  e.stopPropagation();
  try {
    await api(`/api/pm/relations/${relId}`, { method: 'DELETE' });
    if (selectedIssue) selectIssue(selectedIssue.id);
  } catch (err) { toast(err.message, 'error'); }
}

function openAddRelationModal(sourceId) {
  document.getElementById('rel-source').value = sourceId;
  document.getElementById('rel-target').value = '';
  document.getElementById('rel-reason').value = '';
  openModal('modal-add-relation');
}

async function doAddRelation() {
  const source = document.getElementById('rel-source').value;
  const target = document.getElementById('rel-target').value.trim();
  const type = document.getElementById('rel-type').value;
  const reason = document.getElementById('rel-reason').value.trim();
  if (!target) { toast('Target issue required', 'error'); return; }
  try {
    await api(`/api/pm/issues/${source}/relations`, { method: 'POST', body: { type, target_issue_id: target, reason } });
    closeModal('modal-add-relation');
    toast('Dependency added');
    if (selectedIssue) selectIssue(source);
  } catch (e) { toast(e.message, 'error'); }
}

function openCreateIssueModal(projectId) {
  document.getElementById('issue-title').value = '';
  document.getElementById('issue-description').value = '';
  document.getElementById('issue-priority').value = '3';
  document.getElementById('issue-status').value = 'todo';
  document.getElementById('issue-assignee').value = '';
  document.getElementById('issue-tags').value = '';
  document.getElementById('issue-project-id').value = projectId || '';
  openModal('modal-create-issue');
}

async function doCreateIssue() {
  const title = document.getElementById('issue-title').value.trim();
  if (!title) { toast('Title required', 'error'); return; }
  const body = {
    title,
    description: document.getElementById('issue-description').value.trim(),
    priority: parseInt(document.getElementById('issue-priority').value),
    status: document.getElementById('issue-status').value,
    assignee: document.getElementById('issue-assignee').value.trim() || null,
    team_id: activeTeam,
    tags: document.getElementById('issue-tags').value.split(',').map(t => t.trim()).filter(Boolean),
  };
  const projectId = document.getElementById('issue-project-id').value;
  if (projectId) body.project_id = parseInt(projectId);
  try {
    await api('/api/pm/issues', { method: 'POST', body });
    closeModal('modal-create-issue');
    toast('Issue created');
    if (activeView === 'pm-issues') loadPmIssues();
    else if (activeView === 'project-detail' && selectedProject) loadProjectDetail();
  } catch (e) { toast(e.message, 'error'); }
}

// ══════════════════════════════════════════════════
// PM REVIEWS
// ══════════════════════════════════════════════════
let reviewTab = 'all';
async function loadPmReviews() {
  const content = document.getElementById('pm-content');
  content.innerHTML = '<div class="loading">Loading...</div>';
  try {
    const reviews = await api('/api/pm/reviews');
    let filtered = reviews;
    if (reviewTab === 'pending') filtered = reviews.filter(r => r.status === 'pending');
    else if (reviewTab === 'approved') filtered = reviews.filter(r => r.status === 'approved');
    else if (reviewTab === 'draft') filtered = reviews.filter(r => r.status === 'draft');

    let html = renderTabBar(['All PRs', 'Needs Review', 'Approved', 'Drafts'], ['all', 'pending', 'approved', 'draft'], reviewTab, 'reviewTab', 'loadPmReviews');

    if (filtered.length === 0) {
      html += '<div class="empty-state">No pull requests</div>';
    } else {
      filtered.forEach((pr, i) => {
        const statusClass = pr.status === 'changes_requested' ? 'changes' : pr.status;
        const statusLabel = pr.status === 'changes_requested' ? 'Changes' : pr.status === 'pending' ? 'Pending' : pr.status === 'approved' ? 'Approved' : 'Draft';
        html += `<div class="pr-row stagger-in" style="animation-delay:${i * 60}ms">
          ${renderAvatar(pr.author, 28)}
          <div style="flex:1;min-width:0">
            <div style="display:flex;align-items:center;gap:8px">
              <span style="font-size:11px;color:var(--accent-blue);font-weight:500">${esc(pr.id)}</span>
              <span style="font-size:13px;font-weight:500;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${esc(pr.title)}</span>
            </div>
            <div style="display:flex;align-items:center;gap:8px;margin-top:3px">
              <span style="font-size:11px;color:var(--text-quaternary)">${esc(pr.author)}</span>
              <span style="font-size:10px;color:var(--text-quaternary)">&#x2022;</span>
              <span style="font-size:11px;color:var(--text-quaternary)">${esc(pr.issue_id || '')}</span>
              <span style="font-size:10px;color:var(--text-quaternary)">&#x2022;</span>
              <span style="font-size:11px;color:var(--text-quaternary)">${pr.files || 0} files</span>
            </div>
          </div>
          <span class="pr-diff">+${pr.additions || 0} / -${pr.deletions || 0}</span>
          <span class="pr-status ${statusClass}">${statusLabel}</span>
        </div>`;
      });
    }
    content.innerHTML = html;
  } catch (e) { content.innerHTML = `<div class="empty-state">${esc(e.message)}</div>`; }
}

// ══════════════════════════════════════════════════
// PM PULSE (Metrics)
// ══════════════════════════════════════════════════
async function loadPmPulse() {
  const content = document.getElementById('pm-content');
  content.innerHTML = '<div class="loading">Loading...</div>';
  try {
    const pulse = await api('/api/pm/pulse');

    let html = '<div style="padding:20px;display:flex;flex-direction:column;gap:20px">';

    // Metrics row
    html += '<div class="metrics-grid">';
    const metrics = [
      { label: 'Velocity', value: pulse.velocity?.value ?? '—', sub: pulse.velocity?.sub ?? '', spark: pulse.velocity?.spark, color: 'var(--accent-blue)' },
      { label: 'Burndown', value: pulse.burndown?.value ?? '—', sub: pulse.burndown?.sub ?? '', spark: pulse.burndown?.spark, color: 'var(--accent-green)' },
      { label: 'Cycle Time', value: pulse.cycle_time?.value ?? '—', sub: pulse.cycle_time?.sub ?? '', spark: pulse.cycle_time?.spark, color: 'var(--accent-purple)' },
      { label: 'Throughput', value: pulse.throughput?.value ?? '—', sub: pulse.throughput?.sub ?? '', spark: pulse.throughput?.spark, color: 'var(--accent-orange)' },
    ];
    metrics.forEach(m => {
      html += `<div class="metric-card">
        <div class="metric-card-label">${esc(m.label)}</div>
        <div class="metric-card-body">
          <div><div class="metric-card-value">${esc(String(m.value))}</div><div class="metric-card-sub">${esc(m.sub)}</div></div>
          ${m.spark ? renderSparkline(m.spark, m.color) : ''}
        </div>
      </div>`;
    });
    html += '</div>';

    // Status Distribution
    const dist = pulse.status_distribution || {};
    const totalIssues = Object.values(dist).reduce((a, b) => a + b, 0) || 1;
    html += `<div class="metric-card">
      <div style="font-size:12px;font-weight:600;color:var(--text-secondary);margin-bottom:12px">Status Distribution</div>
      <div class="status-bar">
        ${['done', 'in-review', 'in-progress', 'todo', 'backlog'].map(s =>
          `<div class="status-bar-segment" style="flex:${dist[s] || 0};background:${STATUS_COLORS[s]}"></div>`
        ).join('')}
      </div>
      <div class="status-legend">
        ${['done', 'in-review', 'in-progress', 'todo', 'backlog'].map(s =>
          `<div class="status-legend-item">
            <div class="status-legend-dot" style="background:${STATUS_COLORS[s]}"></div>
            <span>${STATUS_LABELS[s]}</span>
            <span class="status-legend-count">${dist[s] || 0}</span>
            <span class="status-legend-pct">(${Math.round(((dist[s] || 0) / totalIssues) * 100)}%)</span>
          </div>`
        ).join('')}
      </div>
    </div>`;

    // Team Activity
    const teamActivity = pulse.team_activity || [];
    if (teamActivity.length > 0) {
      html += `<div class="metric-card">
        <div style="font-size:12px;font-weight:600;color:var(--text-secondary);margin-bottom:14px">Team Activity</div>
        <div style="display:flex;flex-direction:column;gap:10px">
          ${teamActivity.map(m => `<div style="display:flex;align-items:center;gap:12px;padding:6px 0">
            ${renderAvatar(m.name, 24)}
            <span style="font-size:12px;color:var(--text-primary);width:90px">${esc(m.name)}</span>
            ${renderProgressBar(m.total > 0 ? (m.completed / m.total) * 100 : 0, 'var(--accent-green)')}
            <span style="font-size:11px;color:var(--accent-green)">${m.completed} done</span>
            <span style="font-size:11px;color:var(--accent-yellow)">${m.active} active</span>
          </div>`).join('')}
        </div>
      </div>`;
    }

    // Dependency Health
    const depHealth = pulse.dependency_health || {};
    html += `<div class="metric-card">
      <div style="font-size:12px;font-weight:600;color:var(--text-secondary);margin-bottom:14px">Dependency Health</div>
      <div style="display:flex;gap:12px;margin-bottom:14px">
        <div class="metric-card" style="flex:1;padding:12px"><div class="metric-card-label">Blocked Issues</div><div class="metric-card-value" style="color:var(--accent-red)">${depHealth.blocked || 0}</div></div>
        <div class="metric-card" style="flex:1;padding:12px"><div class="metric-card-label">Blocking Issues</div><div class="metric-card-value" style="color:var(--accent-orange)">${depHealth.blocking || 0}</div></div>
        <div class="metric-card" style="flex:1;padding:12px"><div class="metric-card-label">Dep. Chains</div><div class="metric-card-value" style="color:var(--accent-yellow)">${depHealth.chains || 0}</div></div>
      </div>
      ${(depHealth.bottlenecks || []).map(b => `<div style="display:flex;align-items:center;gap:8px;padding:6px 0;border-bottom:1px solid var(--border-subtle)">
        ${renderStatusIcon(b.status)}
        <span style="font-size:11px;color:var(--accent-blue);font-weight:500;cursor:pointer" onclick="selectIssue('${esc(b.id)}')">${esc(b.id)}</span>
        <span style="font-size:12px;flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${esc(b.title)}</span>
        <span class="dependency-indicator blocked">Blocks ${b.impact || 0}</span>
        ${b.assignee ? renderAvatar(b.assignee, 18) : ''}
      </div>`).join('')}
    </div>`;

    html += '</div>';
    content.innerHTML = html;
  } catch (e) { content.innerHTML = `<div class="empty-state">${esc(e.message)}</div>`; }
}

// ══════════════════════════════════════════════════
// PM PROJECTS
// ══════════════════════════════════════════════════
async function loadPmProjects() {
  const content = document.getElementById('pm-content');
  content.innerHTML = '<div class="loading">Loading...</div>';
  try {
    const projects = await api('/api/pm/projects');
    if (projects.length === 0) {
      content.innerHTML = '<div class="empty-state">No projects yet. Click + to create one.</div>';
      return;
    }
    let html = '<div class="projects-grid">';
    projects.forEach((p, i) => {
      const sc = PROJECT_STATUS_CONFIG[p.status] || PROJECT_STATUS_CONFIG['on-track'];
      const progress = p.total_issues > 0 ? Math.round((p.completed_issues / p.total_issues) * 100) : 0;
      html += `<div class="project-card stagger-in" style="animation-delay:${i * 80}ms" onclick="openProject(${p.id})">
        <div class="project-card-header">
          <div class="project-card-dot" style="background:${p.color || '#6366f1'}"></div>
          <span class="project-card-name">${esc(p.name)}</span>
          <span class="project-card-status" style="color:${sc.color};background:${sc.color}18">${sc.label}</span>
        </div>
        <div class="project-card-progress">
          <div class="project-card-progress-info">
            <span style="color:var(--text-tertiary)">${p.completed_issues || 0}/${p.total_issues || 0} issues</span>
            <span style="font-weight:600;color:${p.color || '#6366f1'}">${progress}%</span>
          </div>
          <div class="project-card-progress-bar">
            <div class="project-card-progress-fill" style="width:${progress}%;background:${p.color || '#6366f1'}"></div>
          </div>
        </div>
        ${(p.blocked_count || 0) > 0 || (p.blocking_count || 0) > 0 ? `<div class="project-card-deps">
          ${(p.blocked_count || 0) > 0 ? `<span class="dependency-indicator blocked">&#x1F512; ${p.blocked_count} blocked</span>` : ''}
          ${(p.blocking_count || 0) > 0 ? `<span class="dependency-indicator blocking">&#x26A0; ${p.blocking_count} blocking</span>` : ''}
        </div>` : ''}
        <div class="project-card-footer">
          <div style="display:flex;align-items:center;gap:6px">${renderAvatar(p.lead, 20)}<span>${esc(p.lead)}</span></div>
          ${p.velocity ? renderSparkline(p.velocity, p.color || '#6366f1', 60, 20) : ''}
        </div>
      </div>`;
    });
    html += '</div>';
    content.innerHTML = html;
  } catch (e) { content.innerHTML = `<div class="empty-state">${esc(e.message)}</div>`; }
}

async function openProject(projectId) {
  selectedProject = projectId;
  activeView = 'project-detail';
  document.querySelectorAll('.sidebar-item').forEach(el => el.classList.toggle('active', el.dataset.view === 'pm-projects'));
  loadProjectDetail();
}

// ══════════════════════════════════════════════════
// PROJECT DETAIL
// ══════════════════════════════════════════════════
let projectDetailTab = 'issues';
async function loadProjectDetail() {
  if (!selectedProject) { switchView('pm-projects'); return; }
  const header = document.getElementById('pm-header');
  const content = document.getElementById('pm-content');
  content.innerHTML = '<div class="loading">Loading...</div>';

  try {
    const project = await api(`/api/pm/projects/${selectedProject}`);
    const issues = await api(`/api/pm/issues?project_id=${selectedProject}`);

    // Compute stats
    const statusCounts = { backlog: 0, todo: 0, 'in-progress': 0, 'in-review': 0, done: 0 };
    issues.forEach(i => { if (statusCounts[i.status] !== undefined) statusCounts[i.status]++; });
    const total = issues.length;
    const blockedCount = issues.filter(i => i.is_blocked).length;
    const blockingCount = issues.filter(i => (i.blocking_count || 0) > 0).length;
    const sc = PROJECT_STATUS_CONFIG[project.status] || PROJECT_STATUS_CONFIG['on-track'];

    // Header
    header.innerHTML = `
      <div style="display:flex;align-items:center;gap:6px;cursor:pointer;color:var(--text-tertiary);padding:4px 8px;border-radius:6px" onclick="switchView('pm-projects')">
        ${Icons.back}<span style="font-size:12px">Projects</span>
      </div>
      <div style="width:1px;height:16px;background:var(--border-subtle)"></div>
      <div style="width:10px;height:10px;border-radius:3px;background:${project.color || '#6366f1'}"></div>
      <span class="pm-header-title">${esc(project.name)}</span>
      <span style="font-size:10px;font-weight:500;padding:2px 8px;border-radius:4px;background:${sc.color}18;color:${sc.color}">${sc.label}</span>
      <div class="pm-header-right">
        <button class="pm-header-btn-add" onclick="openCreateIssueModal(${project.id})" title="New Issue">${Icons.plus}</button>
      </div>`;

    // Build content
    let html = '<div style="border-bottom:1px solid var(--border-subtle);padding:0 24px">';
    // Meta row
    html += `<div style="display:flex;align-items:center;gap:20px;padding-bottom:14px;font-size:12px">
      <div style="display:flex;align-items:center;gap:6px;color:var(--text-tertiary)">${renderAvatar(project.lead, 18)}<span>${esc(project.lead)}</span><span style="color:var(--text-quaternary);font-size:10px">Lead</span></div>
      ${project.start_date || project.target_date ? `<div style="display:flex;align-items:center;gap:4px;color:var(--text-tertiary)"><span>${esc(project.start_date || '?')} &#x2192; ${esc(project.target_date || '?')}</span></div>` : ''}
      <div style="display:flex;align-items:center;gap:4px;color:var(--text-tertiary)">${Icons.members}<span>${(project.members || []).length} members</span></div>
      ${blockedCount > 0 ? `<span class="dependency-indicator blocked">&#x1F512; ${blockedCount} blocked</span>` : ''}
      ${blockingCount > 0 ? `<span class="dependency-indicator blocking">&#x26A0; ${blockingCount} blocking</span>` : ''}
    </div>`;

    // Pipeline
    const pipelineSteps = [
      { key: 'backlog', label: 'Backlog' }, { key: 'todo', label: 'Todo' },
      { key: 'in-progress', label: 'In Progress' }, { key: 'in-review', label: 'In Review' }, { key: 'done', label: 'Done' },
    ];
    html += '<div class="workflow-pipeline">';
    pipelineSteps.forEach(step => {
      const count = statusCounts[step.key] || 0;
      const pct = total > 0 ? (count / total) * 100 : 0;
      const color = STATUS_COLORS[step.key];
      html += `<div style="flex:${Math.max(pct, 4)};display:flex;flex-direction:column;gap:4px">
        <div class="workflow-segment" style="background:${count > 0 ? color : 'var(--bg-tertiary)'};opacity:${count > 0 ? 1 : 0.3}"></div>
        <div class="workflow-segment-labels">
          <span class="workflow-segment-label">${step.label}</span>
          <span class="workflow-segment-count" style="color:${count > 0 ? color : 'var(--text-quaternary)'}">${count}</span>
        </div>
      </div>`;
    });
    html += '</div>';

    // Tabs
    html += renderTabBar(['Issues', 'Dependencies', 'Team', 'Activity'], ['issues', 'dependencies', 'team', 'activity'], projectDetailTab, 'projectDetailTab', 'loadProjectDetail');
    html += '</div>';

    // Tab content
    html += '<div style="flex:1;overflow:auto;display:flex">';
    if (projectDetailTab === 'issues') {
      html += renderProjectIssuesTab(issues);
    } else if (projectDetailTab === 'dependencies') {
      html += await renderProjectDependenciesTab(issues);
    } else if (projectDetailTab === 'team') {
      html += renderProjectTeamTab(project, issues);
    } else if (projectDetailTab === 'activity') {
      html += await renderProjectActivityTab(project.id);
    }
    html += '</div>';

    content.innerHTML = html;
  } catch (e) { content.innerHTML = `<div class="empty-state">${esc(e.message)}</div>`; }
}

function renderProjectIssuesTab(issues) {
  const groups = {};
  issues.forEach(i => { if (!groups[i.status]) groups[i.status] = []; groups[i.status].push(i); });
  let html = '<div style="flex:1;overflow:auto">';
  STATUS_ORDER.filter(s => groups[s]).forEach(status => {
    html += renderIssueGroupHeader(status, groups[status].length, 'status');
    groups[status].forEach((issue, i) => { html += renderIssueRow(issue, i); });
  });
  html += '</div><div id="issue-detail-panel"></div>';
  return html;
}

async function renderProjectDependenciesTab(issues) {
  // Fetch relations for all issues
  const allRelations = [];
  for (const issue of issues) {
    try {
      const rels = await api(`/api/pm/issues/${issue.id}/relations`);
      rels.forEach(r => {
        if (r.type === 'blocks' && issues.some(i => i.id === r.target_issue_id)) {
          allRelations.push(r);
        }
      });
    } catch (e) { /* skip */ }
  }

  const statusX = { backlog: 60, todo: 200, 'in-progress': 360, 'in-review': 520, done: 680 };
  const statusGroups = {};
  issues.forEach(i => { if (!statusGroups[i.status]) statusGroups[i.status] = []; statusGroups[i.status].push(i); });

  const nodes = issues.map(issue => {
    const group = statusGroups[issue.status] || [];
    const idx = group.indexOf(issue);
    return { ...issue, x: statusX[issue.status] || 60, y: 60 + idx * 80 };
  });

  const maxY = Math.max(...nodes.map(n => n.y), 100) + 80;

  let html = `<div style="flex:1;padding:24px;overflow:auto">
    <div style="font-size:12px;font-weight:600;color:var(--text-secondary);margin-bottom:16px">Dependency Graph</div>
    <div class="dep-graph"><svg width="760" height="${maxY}" style="overflow:visible">`;

  // Column headers
  Object.entries(statusX).forEach(([status, x]) => {
    html += `<text x="${x + 50}" y="40" font-size="10" font-weight="600" fill="${STATUS_COLORS[status]}" text-anchor="middle" font-family="inherit" opacity="0.6">${STATUS_LABELS[status]}</text>`;
  });

  // Edges
  allRelations.forEach(rel => {
    const from = nodes.find(n => n.id === rel.source_issue_id);
    const to = nodes.find(n => n.id === rel.target_issue_id);
    if (!from || !to) return;
    const dx = to.x - from.x - 100;
    html += `<path d="M${from.x + 100},${from.y + 18} C${from.x + 100 + dx * 0.5},${from.y + 18} ${to.x - dx * 0.5},${to.y + 18} ${to.x},${to.y + 18}" fill="none" stroke="var(--accent-red)" stroke-width="1.5" opacity="0.5"/>`;
    html += `<polygon points="${to.x},${to.y + 18} ${to.x - 6},${to.y + 14} ${to.x - 6},${to.y + 22}" fill="var(--accent-red)" opacity="0.6"/>`;
  });

  // Nodes
  nodes.forEach(node => {
    const strokeColor = node.is_blocked ? 'var(--accent-red)' : (STATUS_COLORS[node.status] || 'var(--text-quaternary)');
    html += `<g>
      <rect x="${node.x}" y="${node.y}" width="100" height="36" rx="6" fill="var(--bg-tertiary)" stroke="${strokeColor}" stroke-width="${node.is_blocked ? 1.5 : 1}"/>
      ${node.is_blocked ? `<rect x="${node.x}" y="${node.y}" width="100" height="36" rx="6" fill="var(--accent-red)" opacity="0.06"/>` : ''}
      <text x="${node.x + 10}" y="${node.y + 15}" font-size="10" font-weight="600" fill="var(--text-quaternary)" font-family="inherit">${esc(node.id)}</text>
      <text x="${node.x + 10}" y="${node.y + 27}" font-size="9" fill="${node.is_blocked ? 'var(--accent-red)' : 'var(--text-secondary)'}" font-family="inherit">${esc(node.title.length > 14 ? node.title.slice(0, 14) + '...' : node.title)}</text>
    </g>`;
  });

  html += '</svg></div>';
  html += `<div class="dep-legend">
    <div style="display:flex;align-items:center;gap:6px"><div style="width:20px;height:2px;background:var(--accent-red);border-radius:1px"></div><span>Blocks</span></div>
    <div style="display:flex;align-items:center;gap:6px"><div style="width:10px;height:10px;border-radius:3px;border:1.5px solid var(--accent-red);background:rgba(239,85,85,0.1)"></div><span>Blocked issue</span></div>
  </div></div>`;
  return html;
}

function renderProjectTeamTab(project, issues) {
  const members = project.members || [];
  let html = '<div style="flex:1;padding:24px"><div style="font-size:12px;font-weight:600;color:var(--text-secondary);margin-bottom:16px">Team Workload</div><div style="display:flex;flex-direction:column;gap:12px">';

  members.forEach((member, i) => {
    const memberIssues = issues.filter(x => x.assignee === member.user_name);
    const done = memberIssues.filter(x => x.status === 'done').length;
    const total = memberIssues.length;
    const blocked = memberIssues.filter(x => x.is_blocked).length;

    html += `<div class="metric-card stagger-in" style="animation-delay:${i * 80}ms">
      <div style="display:flex;align-items:center;gap:12px;margin-bottom:14px">
        ${renderAvatar(member.user_name, 32)}
        <div><div style="font-size:13px;font-weight:600">${esc(member.user_name)}</div><div style="font-size:11px;color:var(--text-tertiary)">${esc(member.role)}</div></div>
        <div style="flex:1"></div>
        <div style="text-align:right"><div style="font-size:18px;font-weight:700">${done}/${total}</div><div style="font-size:10px;color:var(--text-quaternary)">completed</div></div>
      </div>
      <div style="width:100%;height:4px;border-radius:2px;background:var(--bg-tertiary);margin-bottom:12px">
        <div style="width:${total > 0 ? (done / total) * 100 : 0}%;height:100%;border-radius:2px;background:var(--accent-green);transition:width 0.6s ease"></div>
      </div>
      <div style="display:flex;flex-direction:column;gap:4px">
        ${memberIssues.map(issue => `<div style="display:flex;align-items:center;gap:8px;padding:4px 8px;border-radius:4px;background:var(--bg-tertiary)">
          ${renderStatusIcon(issue.status)}
          ${issue.is_blocked ? `<span style="color:var(--accent-red);display:flex">${Icons.lock}</span>` : ''}
          <span style="font-size:11px;color:var(--text-quaternary);width:56px;flex-shrink:0">${esc(issue.id)}</span>
          <span style="font-size:12px;color:${issue.is_blocked ? 'var(--text-quaternary)' : 'var(--text-secondary)'};overflow:hidden;text-overflow:ellipsis;white-space:nowrap;opacity:${issue.is_blocked ? 0.6 : 1}">${esc(issue.title)}</span>
        </div>`).join('')}
      </div>
      ${blocked > 0 ? `<div style="margin-top:8px;font-size:10px;color:var(--accent-red);display:flex;align-items:center;gap:4px">${Icons.lock} ${blocked} task${blocked > 1 ? 's' : ''} blocked</div>` : ''}
    </div>`;
  });

  html += '</div></div>';
  return html;
}

async function renderProjectActivityTab(projectId) {
  try {
    const activity = await api(`/api/pm/projects/${projectId}/activity`);
    let html = '<div style="flex:1;padding:24px"><div style="font-size:12px;font-weight:600;color:var(--text-secondary);margin-bottom:16px">Recent Activity</div>';
    html += '<div class="timeline"><div class="timeline-line"></div>';
    activity.forEach((event, i) => {
      html += `<div class="timeline-event stagger-in" style="animation-delay:${i * 60}ms">
        <div class="timeline-dot"></div>
        <div class="timeline-text">
          <span class="timeline-user">${esc(event.user_name)}</span>
          <span>${esc(event.action)}</span>
          ${event.issue_id ? `<span class="timeline-issue">${esc(event.issue_id)}</span>` : ''}
          ${event.detail ? `<span class="timeline-detail"> &#x2014; ${esc(event.detail)}</span>` : ''}
        </div>
        <div class="timeline-time">${timeAgo(event.created_at)}</div>
      </div>`;
    });
    if (activity.length === 0) html += '<div class="empty-state">No activity yet</div>';
    html += '</div></div>';
    return html;
  } catch (e) { return `<div class="empty-state">${esc(e.message)}</div>`; }
}

// ══════════════════════════════════════════════════
// CREATE PROJECT FLOW
// ══════════════════════════════════════════════════
function startCreateProject() {
  createProjectState = { step: 1, name: '', team: '', startDate: '', targetDate: '', aiIssues: [], aiRelations: [], aiDescription: '', chatMessages: [] };
  activeView = 'create-project';
  document.querySelectorAll('.sidebar-item').forEach(el => el.classList.toggle('active', el.dataset.view === 'pm-projects'));
  loadCreateProject();
}

function loadCreateProject() {
  const header = document.getElementById('pm-header');
  const content = document.getElementById('pm-content');
  const s = createProjectState;

  // Stepper header
  const steps = ['Setup', 'AI Planning', 'Review'];
  header.innerHTML = `
    <div style="display:flex;align-items:center;gap:6px;cursor:pointer;color:var(--text-tertiary);padding:4px 8px;border-radius:6px" onclick="switchView('pm-projects')">
      ${Icons.back}<span style="font-size:12px">Projects</span>
    </div>
    <div style="width:1px;height:16px;background:var(--border-subtle)"></div>
    <span class="pm-header-title">New Project</span>
    <div class="pm-header-right">
      <div class="stepper">${steps.map((label, i) => {
        const stepNum = i + 1;
        const state = stepNum < s.step ? 'done' : stepNum === s.step ? 'current' : '';
        return `${i > 0 ? `<div class="stepper-connector ${stepNum <= s.step ? 'done' : ''}"></div>` : ''}
          <div class="stepper-step ${state}">${state === 'done' ? '&#x2713;' : stepNum}</div>
          <span class="stepper-label ${state}">${label}</span>`;
      }).join('')}</div>
    </div>`;

  if (s.step === 1) renderSetupStep(content);
  else if (s.step === 2) renderAIPlanningStep(content);
  else if (s.step === 3) renderReviewStep(content);
}

function renderSetupStep(content) {
  const s = createProjectState;
  content.innerHTML = `<div class="form-centered">
    <h2>Create a new project</h2>
    <div class="subtitle">Set up the basics, then let AI help you plan the details.</div>
    <div class="form-group">
      <label class="form-label">Project name <span class="required">*</span></label>
      <input class="form-input" id="cp-name" placeholder="e.g. API Microservices Migration" value="${esc(s.name)}" oninput="createProjectState.name=this.value;updateSetupBtn()" />
    </div>
    <div class="form-group">
      <label class="form-label">Team <span class="required">*</span></label>
      <div class="team-cards" id="cp-teams"></div>
    </div>
    <div style="display:flex;gap:12px">
      <div class="form-group" style="flex:1">
        <label class="form-label">Start date</label>
        <input class="form-input" type="date" id="cp-start" value="${s.startDate}" onchange="createProjectState.startDate=this.value" />
      </div>
      <div class="form-group" style="flex:1">
        <label class="form-label">Target date</label>
        <input class="form-input" type="date" id="cp-target" value="${s.targetDate}" onchange="createProjectState.targetDate=this.value" />
      </div>
    </div>
    <button class="btn btn-primary btn-full" id="cp-continue-btn" disabled onclick="goToAIPlanning()">Continue with AI Planning</button>
    <div style="text-align:center;margin-top:12px"><a style="font-size:12px;color:var(--accent-blue);cursor:pointer" onclick="skipToCreateProject()">Or skip and create empty project</a></div>
  </div>`;

  // Render team cards
  const teamsDiv = document.getElementById('cp-teams');
  teamsDiv.innerHTML = teams.map(t => `<div class="team-card ${s.team === t.id ? 'selected' : ''}" style="${s.team === t.id ? `border-color:${t.color || '#6366f1'};background:${(t.color || '#6366f1')}0f` : ''}" onclick="selectProjectTeam('${esc(t.id)}')">
    <div style="display:flex;align-items:center;gap:6px;margin-bottom:8px">
      <div style="width:10px;height:10px;border-radius:3px;background:${t.color || '#6366f1'}"></div>
      <span style="font-size:13px;font-weight:600">${esc(t.name)}</span>
    </div>
    ${s.team === t.id ? `<div style="font-size:10px;color:${t.color || '#6366f1'}">&#x2713; Selected</div>` : ''}
  </div>`).join('');

  updateSetupBtn();
}

function selectProjectTeam(teamId) {
  createProjectState.team = teamId;
  renderSetupStep(document.getElementById('pm-content'));
}

function updateSetupBtn() {
  const btn = document.getElementById('cp-continue-btn');
  if (btn) btn.disabled = !(createProjectState.name.trim() && createProjectState.team);
}

function goToAIPlanning() {
  createProjectState.step = 2;
  createProjectState.chatMessages = [
    { role: 'ai', content: `I'm ready to help you structure "${createProjectState.name}". Describe what you want to accomplish \u2014 goals, constraints, scope \u2014 and I'll propose a breakdown into issues with dependencies.` }
  ];
  loadCreateProject();
}

function renderAIPlanningStep(content) {
  const s = createProjectState;
  const team = teams.find(t => t.id === s.team);

  let chatHtml = s.chatMessages.map(m => {
    if (m.role === 'ai') {
      let body = `<div class="chat-bubble-content">${esc(m.content)}</div>`;
      if (m.issues) {
        body += `<hr style="border:none;border-top:1px solid var(--border-subtle);margin:8px 0">
          <div style="font-size:11px;font-weight:600;margin-bottom:6px">${m.issues.length} issues generated</div>
          <div style="background:var(--bg-tertiary);border-radius:6px;padding:8px">
            ${m.issues.map((iss, j) => `<div style="display:flex;align-items:center;gap:6px;padding:3px 0;animation:fadeSlideIn 0.3s ease ${j * 60}ms both">
              <span style="font-size:10px;color:var(--text-quaternary);width:40px">${esc(iss.id)}</span>
              ${renderStatusIcon(iss.status || 'todo')}
              ${renderPriorityBadge(iss.priority || 3)}
              <span style="font-size:11px;flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${esc(iss.title)}</span>
            </div>`).join('')}
          </div>`;
        if (m.relations && m.relations.length > 0) {
          body += `<div style="font-size:11px;font-weight:600;margin:8px 0 4px">${m.relations.length} dependencies</div>
            <div style="background:rgba(239,85,85,0.03);border-radius:6px;padding:8px">
              ${m.relations.map(r => `<div style="font-size:10px;padding:2px 0;color:var(--text-tertiary)">
                <span style="color:var(--accent-blue)">${esc(r.source)}</span> &#x2192; blocks &#x2192; <span style="color:var(--accent-blue)">${esc(r.target)}</span>
                ${r.reason ? `<span style="color:var(--text-quaternary)"> &#x2014; ${esc(r.reason)}</span>` : ''}
              </div>`).join('')}
            </div>`;
        }
      }
      return `<div class="chat-bubble chat-bubble-agent"><div class="chat-bubble-sender">AI Planner</div>${body}</div>`;
    } else {
      return `<div class="chat-bubble chat-bubble-user"><div class="chat-bubble-sender">You</div><div class="chat-bubble-content">${esc(m.content)}</div></div>`;
    }
  }).join('');

  content.innerHTML = `<div style="display:flex;height:100%">
    <div class="chat-container" style="flex:1">
      <div class="chat-header">
        <div class="chat-header-left">
          <div style="width:28px;height:28px;border-radius:50%;background:linear-gradient(135deg,var(--accent-purple),var(--accent-blue));display:flex;align-items:center;justify-content:center;font-size:14px;color:#fff">&#x2728;</div>
          <div><div class="chat-agent-name">AI Project Planner</div><div style="font-size:10px;color:var(--text-quaternary)">Helps you structure "${esc(s.name)}"</div></div>
        </div>
      </div>
      <div class="chat-messages" id="ai-chat-messages">${chatHtml}</div>
      <div class="chat-input-area">
        <textarea class="chat-input" id="ai-chat-input" placeholder="Describe your project..." rows="1"></textarea>
        <button class="chat-send-btn" id="ai-send-btn" onclick="sendAIChatMessage()">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/></svg>
        </button>
      </div>
      <div style="display:flex;justify-content:space-between;padding:8px 24px;border-top:1px solid var(--border-subtle)">
        <button class="btn btn-outline" onclick="createProjectState.step=1;loadCreateProject()">&#x2190; Back to Setup</button>
        ${s.aiIssues.length > 0 ? '<button class="btn btn-success" onclick="createProjectState.step=3;loadCreateProject()">Review &amp; Create &#x2192;</button>' : ''}
      </div>
    </div>
    <div style="width:300px;border-left:1px solid var(--border-subtle);background:var(--bg-secondary);padding:20px;overflow-y:auto">
      <div style="font-size:11px;letter-spacing:0.08em;color:var(--text-quaternary);text-transform:uppercase;margin-bottom:16px">Project Preview</div>
      <div style="display:flex;align-items:center;gap:8px;margin-bottom:12px">
        <div style="width:10px;height:10px;border-radius:3px;background:${team?.color || '#6366f1'}"></div>
        <span style="font-size:13px;font-weight:600">${esc(s.name)}</span>
      </div>
      <div style="font-size:11px;color:var(--text-tertiary);margin-bottom:12px">${esc(team?.name || s.team)}</div>
      ${s.aiDescription ? `<div style="font-size:12px;color:var(--text-secondary);margin-bottom:16px">${esc(s.aiDescription)}</div>` : ''}
      ${s.aiIssues.length > 0 ? `<div style="font-size:11px;color:var(--text-tertiary);margin-bottom:4px">Pipeline (${s.aiIssues.length} issues)</div>
        <div style="font-size:11px;color:var(--text-tertiary);margin-bottom:8px">Dependencies (${s.aiRelations.length})</div>
        ${s.aiRelations.map(r => `<div style="font-size:9px;padding:2px 6px;margin:2px 0;border-radius:3px;background:rgba(239,85,85,0.07);color:var(--text-tertiary)">${esc(r.source)} &#x2192; ${esc(r.target)}</div>`).join('')}` : `<div style="text-align:center;padding:30px 0;color:var(--text-quaternary)"><div style="font-size:20px;margin-bottom:8px">&#x2728;</div><div style="font-size:11px">Describe your project to get started</div></div>`}
    </div>
  </div>`;

  // Setup input handlers
  const input = document.getElementById('ai-chat-input');
  if (input) {
    input.focus();
    input.onkeydown = (e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendAIChatMessage(); } };
    input.oninput = () => { input.style.height = 'auto'; input.style.height = Math.min(input.scrollHeight, 120) + 'px'; };
  }
  // Scroll to bottom
  const msgs = document.getElementById('ai-chat-messages');
  if (msgs) msgs.scrollTop = msgs.scrollHeight;
}

async function sendAIChatMessage() {
  const input = document.getElementById('ai-chat-input');
  const msg = input?.value.trim();
  if (!msg) return;

  const s = createProjectState;
  s.chatMessages.push({ role: 'user', content: msg });
  input.value = '';
  renderAIPlanningStep(document.getElementById('pm-content'));

  // Show typing indicator
  const msgs = document.getElementById('ai-chat-messages');
  const typingEl = document.createElement('div');
  typingEl.className = 'chat-bubble chat-bubble-agent chat-typing';
  typingEl.innerHTML = '<div class="chat-bubble-sender">AI Planner</div><div class="chat-typing-dots"><span></span><span></span><span></span></div>';
  msgs.appendChild(typingEl);
  msgs.scrollTop = msgs.scrollHeight;

  try {
    const response = await api('/api/pm/ai/plan', { method: 'POST', body: {
      project_name: s.name, team_id: s.team, description: msg,
      existing_issues: s.aiIssues, existing_relations: s.aiRelations,
    }});

    if (response.issues && response.issues.length > 0) {
      s.aiIssues = response.issues;
      s.aiRelations = response.relations || [];
      s.aiDescription = response.description || '';
      s.chatMessages.push({ role: 'ai', content: response.message || 'Here is the breakdown:', issues: response.issues, relations: response.relations || [] });
      if (response.followup) {
        s.chatMessages.push({ role: 'ai', content: response.followup });
      }
    } else {
      s.chatMessages.push({ role: 'ai', content: response.message || response.reply || 'I could not generate issues. Please provide more details.' });
    }
  } catch (e) {
    s.chatMessages.push({ role: 'ai', content: `Error: ${e.message}. Please try again.` });
  }

  renderAIPlanningStep(document.getElementById('pm-content'));
}

function renderReviewStep(content) {
  const s = createProjectState;
  const team = teams.find(t => t.id === s.team);

  // Compute blocked flags
  const blockTargets = new Set();
  const blockSources = {};
  s.aiRelations.forEach(r => {
    if (r.type === 'blocks') {
      blockTargets.add(r.target);
      blockSources[r.source] = (blockSources[r.source] || 0) + 1;
    }
  });

  let html = `<div style="max-width:800px;margin:0 auto;padding:32px 48px;overflow:auto">
    <h2 style="font-size:20px;font-weight:700;margin-bottom:6px">Review your project</h2>
    <div style="font-size:13px;color:var(--text-tertiary);margin-bottom:24px">Everything looks good? You can still edit before creating.</div>
    <div class="metric-card" style="margin-bottom:24px">
      <div style="display:flex;align-items:center;gap:8px;margin-bottom:8px">
        <div style="width:12px;height:12px;border-radius:3px;background:${team?.color || '#6366f1'}"></div>
        <span style="font-size:16px;font-weight:700">${esc(s.name)}</span>
      </div>
      ${s.aiDescription ? `<div style="font-size:12px;color:var(--text-secondary);margin-bottom:10px">${esc(s.aiDescription)}</div>` : ''}
      <div style="display:flex;gap:16px;font-size:12px;color:var(--text-tertiary)">
        <span>${esc(team?.name || s.team)}</span>
        ${s.startDate ? `<span>${s.startDate} &#x2192; ${s.targetDate || '?'}</span>` : ''}
        <span style="color:var(--accent-blue)">${s.aiIssues.length} issues</span>
        <span style="color:var(--accent-red)">${s.aiRelations.length} dependencies</span>
      </div>
    </div>
    <div style="font-size:12px;font-weight:600;margin-bottom:8px">Issues (${s.aiIssues.length})</div>
    <div style="border:1px solid var(--border-subtle);border-radius:8px;margin-bottom:24px;overflow:hidden">`;

  s.aiIssues.forEach((issue, i) => {
    const isBlocked = blockTargets.has(issue.id);
    const isBlocking = blockSources[issue.id] || 0;
    html += `<div style="display:flex;align-items:center;gap:8px;padding:8px 12px;border-bottom:1px solid var(--border-subtle);animation:fadeSlideIn 0.3s ease ${i * 40}ms both">
      ${renderPriorityBadge(issue.priority || 3)}
      <span style="font-size:10px;color:var(--text-quaternary);width:40px">${esc(issue.id)}</span>
      ${renderStatusIcon(issue.status || 'todo')}
      ${isBlocked ? `<span style="color:var(--accent-red);display:flex">${Icons.lock}</span>` : ''}
      ${isBlocking > 0 ? `<span class="dependency-indicator blocking">&#x26A0; ${isBlocking}</span>` : ''}
      <span style="font-size:12px;flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;opacity:${isBlocked ? 0.5 : 1}">${esc(issue.title)}</span>
      ${(issue.tags || []).map(t => renderTag(t)).join('')}
    </div>`;
  });

  html += '</div>';

  if (s.aiRelations.length > 0) {
    html += `<div style="font-size:12px;font-weight:600;margin-bottom:8px">Dependencies (${s.aiRelations.length})</div>
      <div style="border:1px solid var(--border-subtle);border-radius:8px;margin-bottom:24px;overflow:hidden">`;
    s.aiRelations.forEach(r => {
      html += `<div style="display:flex;align-items:center;gap:8px;padding:8px 12px;border-bottom:1px solid var(--border-subtle);font-size:12px">
        <span style="color:var(--accent-blue);font-weight:500">${esc(r.source)}</span>
        <span class="relation-badge blocks">blocks</span>
        <span style="color:var(--accent-blue);font-weight:500">${esc(r.target)}</span>
        <span style="color:var(--text-quaternary);overflow:hidden;text-overflow:ellipsis;white-space:nowrap;max-width:300px;flex:1">${esc(r.reason || '')}</span>
      </div>`;
    });
    html += '</div>';
  }

  html += `<div style="display:flex;justify-content:flex-end;gap:8px;margin-top:16px">
    <button class="btn btn-outline" onclick="createProjectState.step=2;loadCreateProject()">&#x2190; Back to AI</button>
    <button class="btn btn-success" onclick="doCreateProject()">&#x2713; Create Project</button>
  </div></div>`;

  content.innerHTML = html;
}

async function doCreateProject() {
  const s = createProjectState;
  try {
    const project = await api('/api/pm/projects', { method: 'POST', body: {
      name: s.name, team_id: s.team, lead: currentUser?.display_name || currentUser?.email || '',
      color: teams.find(t => t.id === s.team)?.color || '#6366f1',
      description: s.aiDescription, start_date: s.startDate || null, target_date: s.targetDate || null,
    }});

    // Bulk create issues
    if (s.aiIssues.length > 0) {
      await api('/api/pm/issues/bulk', { method: 'POST', body: {
        project_id: project.id, team_id: s.team,
        issues: s.aiIssues.map(i => ({ title: i.title, description: i.description || '', priority: i.priority || 3, status: i.status || 'todo', tags: i.tags || [] })),
      }});
    }

    // Bulk create relations
    if (s.aiRelations.length > 0) {
      // Re-fetch issues to get real IDs
      const realIssues = await api(`/api/pm/issues?project_id=${project.id}`);
      const idMap = {};
      s.aiIssues.forEach((ai, idx) => { if (realIssues[idx]) idMap[ai.id] = realIssues[idx].id; });

      const mappedRelations = s.aiRelations.filter(r => idMap[r.source] && idMap[r.target]).map(r => ({
        type: r.type || 'blocks', source_id: idMap[r.source], target_id: idMap[r.target], reason: r.reason || '',
      }));
      if (mappedRelations.length > 0) {
        await api('/api/pm/relations/bulk', { method: 'POST', body: { relations: mappedRelations } });
      }
    }

    toast('Project created!');
    selectedProject = project.id;
    activeView = 'project-detail';
    loadProjectDetail();
  } catch (e) { toast(e.message, 'error'); }
}

async function skipToCreateProject() {
  const s = createProjectState;
  if (!s.name.trim() || !s.team) { toast('Name and team required', 'error'); return; }
  try {
    const project = await api('/api/pm/projects', { method: 'POST', body: {
      name: s.name, team_id: s.team, lead: currentUser?.display_name || currentUser?.email || '',
      color: teams.find(t => t.id === s.team)?.color || '#6366f1',
      start_date: s.startDate || null, target_date: s.targetDate || null,
    }});
    toast('Project created!');
    selectedProject = project.id;
    activeView = 'project-detail';
    loadProjectDetail();
  } catch (e) { toast(e.message, 'error'); }
}

// ══════════════════════════════════════════════════
// HITL INBOX (Legacy Questions)
// ══════════════════════════════════════════════════
let hitlFilter = 'pending';
async function loadHitlInbox() {
  const content = document.getElementById('pm-content');
  content.innerHTML = '<div class="loading">Loading...</div>';
  try {
    const [questions, stats] = await Promise.all([
      api(`/api/teams/${activeTeam}/questions?status=${hitlFilter === 'all' ? '' : hitlFilter}&limit=50`),
      api(`/api/teams/${activeTeam}/questions/stats`),
    ]);
    const badge = document.getElementById('hitl-badge');
    if (badge) { badge.textContent = stats.pending; badge.style.display = stats.pending > 0 ? '' : 'none'; }

    let html = renderTabBar(['All', 'Pending', 'Answered'], ['all', 'pending', 'answered'], hitlFilter, 'hitlFilter', 'loadHitlInbox');

    if (questions.length === 0) {
      html += '<div class="empty-state">No questions</div>';
    } else {
      const grouped = {};
      questions.forEach(q => { if (!grouped[q.agent_id]) grouped[q.agent_id] = []; grouped[q.agent_id].push(q); });

      Object.keys(grouped).sort().forEach(agentId => {
        const agentQuestions = grouped[agentId];
        const pendingCount = agentQuestions.filter(q => q.status === 'pending').length;
        html += `<div class="inbox-agent-group">
          <div class="inbox-agent-header" onclick="toggleGroup('hitl-${esc(agentId)}')">
            <div class="inbox-agent-left">
              <span class="inbox-agent-arrow" id="arrow-hitl-${esc(agentId)}">&#x25BC;</span>
              <span class="tag tag-accent">${esc(agentId)}</span>
              <span class="inbox-agent-count">${agentQuestions.length} question${agentQuestions.length > 1 ? 's' : ''}</span>
              ${pendingCount > 0 ? `<span class="inbox-pending-badge">${pendingCount} pending</span>` : ''}
            </div>
          </div>
          <div class="inbox-agent-questions" id="group-hitl-${esc(agentId)}">`;
        agentQuestions.forEach(q => {
          html += `<div class="card ${q.status === 'pending' ? 'highlight' : ''}" style="cursor:pointer" onclick="openHitlQuestion('${q.id}')">
            <div class="card-row">
              <div style="flex:1;min-width:0">
                <div class="card-tags">
                  ${q.status === 'pending' ? '<span class="tag tag-yellow">PENDING</span>' : `<span class="tag">${esc(q.status).toUpperCase()}</span>`}
                  ${q.request_type === 'approval' ? '<span class="tag tag-green">APPROVAL</span>' : ''}
                </div>
                <div class="card-question">${esc(q.prompt)}</div>
              </div>
              <span class="card-time">${timeAgo(q.created_at)}</span>
            </div>
          </div>`;
        });
        html += '</div></div>';
      });
    }
    html += `<div class="stats-bar">${stats.pending} pending &#x2022; ${stats.total} total</div>`;
    content.innerHTML = html;
  } catch (e) { content.innerHTML = `<div class="empty-state">${esc(e.message)}</div>`; }
}

function toggleGroup(groupId) {
  const group = document.getElementById('group-' + groupId);
  const arrow = document.getElementById('arrow-' + groupId);
  if (!group) return;
  const hidden = group.style.display === 'none';
  group.style.display = hidden ? 'block' : 'none';
  if (arrow) arrow.innerHTML = hidden ? '&#x25BC;' : '&#x25B6;';
}

async function openHitlQuestion(qid) {
  const content = document.getElementById('pm-content');
  content.innerHTML = '<div class="loading">Loading...</div>';
  try {
    const q = await api(`/api/questions/${qid}`);
    const options = (q.context && q.context.options) ? q.context.options : [];

    let html = `<div class="breadcrumb" style="padding:20px 20px 0">
      <a onclick="loadHitlInbox()">HITL</a><span>/</span><span class="current">${esc(q.agent_id)}</span>
    </div>
    <div style="padding:20px">
      <div class="question-box">
        <div class="question-label">QUESTION FROM ${esc(q.agent_id).toUpperCase()}</div>
        <div class="question-text">${esc(q.prompt)}</div>
        <div class="question-meta">
          <span>thread: <span>${esc(q.thread_id || '—')}</span></span>
          <span>type: <span>${esc(q.request_type)}</span></span>
          <span>received: <span style="color:var(--accent-yellow)">${timeAgo(q.created_at)} ago</span></span>
        </div>
      </div>`;

    if (q.status === 'pending') {
      if (options.length > 0) {
        html += '<div class="options-section"><div class="options-label">PROPOSED ANSWERS</div><div class="options-grid">';
        options.forEach((opt, i) => {
          const label = typeof opt === 'object' ? (opt.label || opt.value || JSON.stringify(opt)) : String(opt);
          const value = typeof opt === 'object' ? (opt.value || opt.label || JSON.stringify(opt)) : String(opt);
          html += `<button class="option-btn" onclick="document.getElementById('hitl-reply-text').value='${esc(value).replace(/'/g, "\\'")}';this.parentNode.querySelectorAll('.option-btn').forEach(b=>b.classList.remove('option-selected'));this.classList.add('option-selected')">
            <span class="option-letter">${String.fromCharCode(65 + i)}</span>
            <span class="option-text">${esc(label)}</span>
          </button>`;
        });
        html += '</div></div>';
      }
      html += `<div class="free-answer-section"><div class="options-label">FREE ANSWER</div>
        <textarea class="reply-area" id="hitl-reply-text" placeholder="Type your response..."></textarea>
      </div>
      <div class="reply-actions">
        <button class="btn btn-primary" onclick="submitHitlAnswer('${q.id}', 'answer')">SEND</button>
        ${q.request_type === 'approval' ? `
          <button class="btn btn-approve" onclick="submitHitlAnswer('${q.id}', 'approve')">&#x2713; APPROVE</button>
          <button class="btn btn-reject" onclick="submitHitlAnswer('${q.id}', 'reject')">&#x2717; REJECT</button>
        ` : ''}
      </div>`;
    } else {
      html += `<div class="card" style="margin-top:12px">
        <div class="question-label">RESPONSE (${esc(q.status)})</div>
        <div style="font-size:12px;color:var(--text-primary);margin-top:4px">${esc(q.response || '—')}</div>
        <div style="font-size:9px;color:var(--text-tertiary);margin-top:6px">by ${esc(q.reviewer || '—')} via ${esc(q.response_channel || '—')} &#x2022; ${timeAgo(q.answered_at)} ago</div>
      </div>`;
    }
    html += '</div>';
    content.innerHTML = html;
    const ta = document.getElementById('hitl-reply-text');
    if (ta) ta.focus();
  } catch (e) { content.innerHTML = `<div class="empty-state">${esc(e.message)}</div>`; }
}

async function submitHitlAnswer(qid, action) {
  const response = document.getElementById('hitl-reply-text')?.value || '';
  if (action === 'answer' && !response.trim()) { toast('Response is empty', 'error'); return; }
  try {
    await api(`/api/questions/${qid}/answer`, { method: 'POST', body: { response, action } });
    toast(action === 'approve' ? 'Approved' : action === 'reject' ? 'Rejected' : 'Response sent');
    loadHitlInbox();
  } catch (e) { toast(e.message, 'error'); }
}

// ══════════════════════════════════════════════════
// AGENTS
// ══════════════════════════════════════════════════
let activeAgent = null;
let chatMessages = [];
let chatLoading = false;

async function loadAgents() {
  const content = document.getElementById('pm-content');
  content.innerHTML = '<div class="loading">Loading...</div>';
  activeAgent = null;
  try {
    const agents = await api(`/api/teams/${activeTeam}/agents`);
    agents.sort((a, b) => a.id === 'orchestrator' ? -1 : b.id === 'orchestrator' ? 1 : a.name.localeCompare(b.name));
    let html = '<div class="agents-grid" style="padding:20px">';
    agents.forEach(a => {
      const hasActivity = !!a.last_activity;
      const isOrch = a.id === 'orchestrator';
      html += `<div class="card agent-card ${isOrch ? 'agent-card-orch' : ''}" onclick="openAgentChat('${esc(a.id)}', '${esc(a.name)}')">
        <div class="card-row" style="align-items:center">
          <div style="display:flex;align-items:center;gap:8px">
            <span class="status-dot ${hasActivity ? 'online' : 'offline'}"></span>
            <span style="font-size:12px;font-weight:${isOrch ? '700' : '400'}">${esc(a.name)}</span>
            <span class="tag tag-accent">${esc(a.id)}</span>
          </div>
          <span class="card-time">${a.last_activity ? timeAgo(a.last_activity) : ''}</span>
        </div>
        <div class="agent-stats">
          <span>questions <span class="val">${a.total}</span></span>
          <span>pending <span class="${a.pending > 0 ? 'val-warn' : 'val'}">${a.pending}</span></span>
        </div>
      </div>`;
    });
    html += '</div>';
    content.innerHTML = html;
  } catch (e) { content.innerHTML = `<div class="empty-state">${esc(e.message)}</div>`; }
}

async function openAgentChat(agentId, agentName) {
  activeAgent = { id: agentId, name: agentName };
  const content = document.getElementById('pm-content');
  content.innerHTML = `
    <div class="chat-container">
      <div class="chat-header">
        <div class="chat-header-left">
          <span style="cursor:pointer;color:var(--text-tertiary);margin-right:8px" onclick="loadAgents()">${Icons.back}</span>
          <span class="status-dot online"></span>
          <span class="chat-agent-name">${esc(agentName)}</span>
          <span class="tag tag-accent">${esc(agentId)}</span>
        </div>
        <button class="chat-clear-btn" onclick="clearAgentChat('${esc(agentId)}')">Clear</button>
      </div>
      <div class="chat-messages" id="chat-messages"><div class="loading">Loading...</div></div>
      <div class="chat-input-area">
        <textarea class="chat-input" id="chat-input" placeholder="Write your message..." rows="1"></textarea>
        <button class="chat-send-btn" id="chat-send-btn" onclick="sendChatMessage()">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/></svg>
        </button>
      </div>
    </div>`;

  try {
    chatMessages = await api(`/api/teams/${activeTeam}/agents/${agentId}/chat`);
    renderChatMessages();
  } catch (e) {
    document.getElementById('chat-messages').innerHTML = `<div class="chat-welcome"><div class="chat-welcome-icon">&#x2B21;</div><div>Start of conversation with <strong>${esc(agentName)}</strong></div></div>`;
  }

  const input = document.getElementById('chat-input');
  input.focus();
  input.onkeydown = (e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendChatMessage(); } };
  input.oninput = () => { input.style.height = 'auto'; input.style.height = Math.min(input.scrollHeight, 160) + 'px'; };
}

function renderChatMessages() {
  const container = document.getElementById('chat-messages');
  if (!container) return;
  if (chatMessages.length === 0) {
    container.innerHTML = `<div class="chat-welcome"><div class="chat-welcome-icon">&#x2B21;</div><div>Start of conversation with <strong>${esc(activeAgent?.name || '')}</strong></div></div>`;
    return;
  }
  let html = '';
  chatMessages.forEach(m => {
    const isUser = m.sender !== activeAgent?.id;
    const time = m.created_at ? new Date(m.created_at).toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit' }) : '';
    html += `<div class="chat-bubble ${isUser ? 'chat-bubble-user' : 'chat-bubble-agent'}">
      <div class="chat-bubble-sender">${isUser ? 'You' : esc(activeAgent?.name || m.sender)}</div>
      <div class="chat-bubble-content">${esc(m.content)}</div>
      <div class="chat-bubble-time">${time}</div>
    </div>`;
  });
  container.innerHTML = html;
  container.scrollTop = container.scrollHeight;
}

async function sendChatMessage() {
  if (chatLoading || !activeAgent) return;
  const input = document.getElementById('chat-input');
  const msg = input.value.trim();
  if (!msg) return;
  chatLoading = true;
  const sendBtn = document.getElementById('chat-send-btn');
  sendBtn.disabled = true;
  input.value = '';
  input.style.height = 'auto';

  chatMessages.push({ sender: currentUser.email, content: msg, created_at: new Date().toISOString() });
  renderChatMessages();

  try {
    const data = await api(`/api/teams/${activeTeam}/agents/${activeAgent.id}/chat`, { method: 'POST', body: { message: msg } });
    chatMessages.push({ sender: activeAgent.id, content: data.reply, created_at: new Date().toISOString() });
    renderChatMessages();
  } catch (e) { toast(e.message, 'error'); }
  finally { chatLoading = false; sendBtn.disabled = false; input.focus(); }
}

async function clearAgentChat(agentId) {
  if (!confirm('Clear conversation history?')) return;
  try {
    await api(`/api/teams/${activeTeam}/agents/${agentId}/chat`, { method: 'DELETE' });
    chatMessages = [];
    renderChatMessages();
    toast('History cleared');
  } catch (e) { toast(e.message, 'error'); }
}

// ══════════════════════════════════════════════════
// MEMBERS
// ══════════════════════════════════════════════════
async function loadMembers() {
  const content = document.getElementById('pm-content');
  content.innerHTML = '<div class="loading">Loading...</div>';
  try {
    const members = await api(`/api/teams/${activeTeam}/members`);
    let html = '<div style="padding:20px">';
    if (members.length === 0) {
      html += '<div class="empty-state">No members</div>';
    } else {
      members.forEach(m => {
        const initial = (m.display_name || m.email)[0].toUpperCase();
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
              <span class="tag ${m.team_role === 'admin' ? 'tag-yellow' : ''}">${esc(m.team_role)}</span>
              ${currentUser && currentUser.role === 'admin' ? `<div class="member-actions"><button onclick="removeMember('${m.id}')">remove</button></div>` : ''}
            </div>
          </div>
        </div>`;
      });
    }
    html += '</div>';
    content.innerHTML = html;
  } catch (e) { content.innerHTML = `<div class="empty-state">${esc(e.message)}</div>`; }
}

async function doInvite() {
  const email = document.getElementById('invite-email').value.trim();
  const name = document.getElementById('invite-name').value.trim();
  const password = document.getElementById('invite-password').value;
  const role = document.getElementById('invite-role').value;
  if (!email) { toast('Email required', 'error'); return; }
  try {
    await api(`/api/teams/${activeTeam}/members`, { method: 'POST', body: { email, display_name: name, password, role } });
    toast('Member invited');
    closeModal('modal-invite');
    loadMembers();
  } catch (e) { toast(e.message, 'error'); }
}

async function removeMember(userId) {
  if (!confirm('Remove this member?')) return;
  try {
    await api(`/api/teams/${activeTeam}/members/${userId}`, { method: 'DELETE' });
    toast('Member removed');
    loadMembers();
  } catch (e) { toast(e.message, 'error'); }
}

// ══════════════════════════════════════════════════
// UTILITIES
// ══════════════════════════════════════════════════
function renderTabBar(labels, values, activeVal, stateVar, reloadFn) {
  return `<div class="tab-bar">${labels.map((label, i) =>
    `<button class="tab-item ${values[i] === activeVal ? 'active' : ''}" onclick="${stateVar}='${values[i]}';${reloadFn}()">${label}</button>`
  ).join('')}</div>`;
}

// ── Keyboard shortcuts ───────────────────────────
document.addEventListener('keydown', (e) => {
  if (e.key === 'Enter') {
    if (document.getElementById('login-screen').style.display === 'flex') doLogin();
    else if (document.getElementById('register-screen').style.display === 'flex') doRegister();
  }
  if (e.key === 'Escape') {
    document.querySelectorAll('.modal-overlay.active').forEach(m => m.classList.remove('active'));
    closeDetailPanel();
  }
});

// ── Email validation hint ────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  const regEmail = document.getElementById('reg-email');
  const hint = document.getElementById('reg-email-hint');
  if (regEmail && hint) {
    regEmail.addEventListener('input', () => {
      const v = regEmail.value.trim();
      if (!v) { hint.textContent = ''; return; }
      if (/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(v)) { hint.textContent = 'Valid email'; hint.style.color = 'var(--accent-green)'; }
      else { hint.textContent = 'Invalid format'; hint.style.color = 'var(--accent-red)'; }
    });
  }
});

// ── Version ──────────────────────────────────────
async function loadVersion() {
  try {
    const data = await fetch('/api/version').then(r => r.json());
    let txt = data.version || 'dev';
    if (data.last_update) {
      try {
        const dt = new Date(data.last_update);
        txt += ' \u2014 ' + dt.toLocaleDateString('fr-FR') + ' ' + dt.toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit' });
      } catch (e) {}
    }
    document.querySelectorAll('.version-tag').forEach(el => { el.textContent = txt; });
  } catch (e) { /* ignore */ }
}

// ── Init ─────────────────────────────────────────
(async () => {
  loadVersion();
  if (await checkAuth()) {
    onLoggedIn();
  }
  if (typeof google !== 'undefined') { initGoogleSignIn(); }
  else { window.addEventListener('load', () => { initGoogleSignIn(); }); }
})();

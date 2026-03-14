/* LandGraph Admin — Frontend */

// ── State ──────────────────────────────────────────
let envEntries = [];
let mcpServers = {};
let mcpCatalog = [];
let mcpAccess = {};
let agents = {};
let agentGroups = [];
let llmProviders = {};

const MCP_CMD_HELP = {
  npx: "Execute un package Node.js depuis le registre npm sans l'installer globalement. C'est le plus courant pour les MCP parce que la majorite des serveurs MCP sont ecrits en TypeScript/JavaScript.",
  uvx: "L'equivalent de npx mais pour Python, via le gestionnaire uv. Il telecharge et execute un package Python en une commande.",
  python: "Execution directe d'un script Python local. Utile pour des serveurs MCP custom que tu developpes toi-meme.",
  node: "Execution directe d'un script Node.js local. Utile pour des serveurs MCP custom que tu developpes toi-meme.",
  docker: "Lance le serveur MCP dans un container isole. Plus lourd mais plus securise — le MCP n'a pas acces au systeme hote. Utile pour des serveurs qui ont besoin de dependances complexes ou pour isoler un MCP non fiable.",
  bunx: "Comme npx mais utilise Bun au lieu de Node.js. Plus rapide au demarrage (~3x plus rapide que Node pour le cold start). Peu utilise pour l'instant dans l'ecosysteme MCP.",
  deno: "Comme node mais avec Deno, qui a un modele de securite par permissions (acces reseau, fichiers, etc. doivent etre explicitement autorises). Marginal pour les MCP.",
};

// ── Utils ──────────────────────────────────────────
async function api(url, opts = {}) {
  const res = await fetch(url, {
    headers: { 'Content-Type': 'application/json' },
    ...opts,
    body: opts.body ? JSON.stringify(opts.body) : undefined,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || 'Erreur serveur');
  }
  return res.json();
}

function toast(msg, type = 'info') {
  const el = document.createElement('div');
  el.className = `toast toast-${type}`;
  el.textContent = msg;
  document.getElementById('toasts').appendChild(el);
  setTimeout(() => el.remove(), 4000);
}

function escHtml(s) {
  const d = document.createElement('div');
  d.textContent = s;
  return d.innerHTML;
}

function maskValue(val) {
  if (!val || val.length < 8) return val;
  return val.slice(0, 4) + '*'.repeat(Math.min(val.length - 8, 30)) + val.slice(-4);
}

// ── Navigation ─────────────────────────────────────
function showSection(name) {
  document.querySelectorAll('.section').forEach(s => s.classList.remove('active'));
  document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
  document.getElementById(`section-${name}`).classList.add('active');
  document.querySelector(`.nav-item[data-section="${name}"]`).classList.add('active');

  // Load data on section switch
  const loaders = { dashboard: loadDashboard, secrets: loadEnv, mcp: loadMCP, llm: loadLLM, teams: loadTeams, templates: loadTemplates, channels: loadChannels, chat: loadChat, monitoring: loadMonitoring, hitl: loadHitl, users: loadUsers, scripts: loadScripts };
  if (loaders[name]) loaders[name]();
}

// ── Dashboard ─────────────────────────────────────
async function loadDashboard() {
  const el = document.getElementById('dashboard-content');
  el.innerHTML = '<div class="loading">Chargement...</div>';

  const [gateway, containers, agents, teams, hitl, llm] = await Promise.allSettled([
    api('/api/monitoring/gateway'),
    api('/api/monitoring/containers'),
    api('/api/agents'),
    api('/api/teams'),
    api('/api/hitl/stats'),
    api('/api/llm/providers'),
  ]);

  let html = '';

  // Gateway status
  const gw = gateway.status === 'fulfilled' ? gateway.value : null;
  const gwOk = gw && gw.status === 'ok';
  html += `<div class="dash-card">
    <div class="dash-card-title">Gateway</div>
    <div class="dash-card-value"><span class="dash-status-dot ${gwOk ? 'dash-status-ok' : 'dash-status-err'}"></span>${gwOk ? 'En ligne' : 'Hors ligne'}</div>
    <div class="dash-card-sub">${gwOk ? 'v' + (gw.version || '?') : (gw?.error || 'Non joignable')}</div>
  </div>`;

  // Containers
  const ct = containers.status === 'fulfilled' ? (containers.value.containers || []) : [];
  const running = ct.filter(c => c.status && c.status.toLowerCase().includes('up')).length;
  html += `<div class="dash-card">
    <div class="dash-card-title">Containers</div>
    <div class="dash-card-value">${running} / ${ct.length}</div>
    <div class="dash-card-sub">en cours d'execution</div>
    <ul class="dash-card-list">${ct.map(c => {
      const up = c.status && c.status.toLowerCase().includes('up');
      return `<li><span><span class="dash-status-dot ${up ? 'dash-status-ok' : 'dash-status-err'}"></span>${escHtml(c.name)}</span><span style="font-size:0.75rem;color:var(--text-secondary)">${escHtml(c.status || '')}</span></li>`;
    }).join('')}</ul>
  </div>`;

  // Teams
  const tm = teams.status === 'fulfilled' ? (teams.value.teams || []) : [];
  html += `<div class="dash-card">
    <div class="dash-card-title">Equipes</div>
    <div class="dash-card-value">${tm.length}</div>
    <ul class="dash-card-list">${tm.map(t =>
      `<li><span>${escHtml(t.name || t.id)}</span><span class="tag tag-blue" style="font-size:0.7rem">${escHtml(t.id)}</span></li>`
    ).join('')}</ul>
  </div>`;

  // Agents
  const ag = agents.status === 'fulfilled' ? (agents.value || []) : [];
  html += `<div class="dash-card">
    <div class="dash-card-title">Agents</div>
    <div class="dash-card-value">${ag.length}</div>
    <ul class="dash-card-list">${ag.slice(0, 8).map(a =>
      `<li><span>${escHtml(a.name || a.id)}</span><span style="font-size:0.75rem;color:var(--text-secondary)">${escHtml(a.llm || '')}</span></li>`
    ).join('')}${ag.length > 8 ? `<li style="color:var(--text-secondary)">+${ag.length - 8} autres</li>` : ''}</ul>
  </div>`;

  // HITL
  const ht = hitl.status === 'fulfilled' ? hitl.value : {};
  html += `<div class="dash-card">
    <div class="dash-card-title">Validations HITL</div>
    <div class="dash-card-value">${ht.pending || 0}</div>
    <div class="dash-card-sub">en attente</div>
    <ul class="dash-card-list">
      <li><span>Total</span><span>${ht.total || 0}</span></li>
      <li><span>Approuvees</span><span style="color:#22c55e">${ht.approved || 0}</span></li>
      <li><span>Rejetees</span><span style="color:#ef4444">${ht.rejected || 0}</span></li>
    </ul>
  </div>`;

  // LLM Providers
  const lm = llm.status === 'fulfilled' ? llm.value : {};
  const provCount = Object.keys(lm.providers || {}).length;
  const defaultLlm = lm.default || '—';
  html += `<div class="dash-card">
    <div class="dash-card-title">Modeles LLM</div>
    <div class="dash-card-value">${provCount}</div>
    <div class="dash-card-sub">Defaut : ${escHtml(defaultLlm)}</div>
    <ul class="dash-card-list">${Object.entries(lm.providers || {}).slice(0, 6).map(([id, p]) =>
      `<li><span>${escHtml(id)}</span><span class="tag tag-blue" style="font-size:0.7rem">${escHtml(p.type)}</span></li>`
    ).join('')}${provCount > 6 ? `<li style="color:var(--text-secondary)">+${provCount - 6} autres</li>` : ''}</ul>
  </div>`;

  el.innerHTML = html;
}

// ── Modal helpers ──────────────────────────────────
function showModal(html, cssClass = '') {
  document.getElementById('modal-container').innerHTML = `
    <div class="modal-overlay" onclick="if(event.target===this)closeModal()">
      <div class="modal ${cssClass}">${html}</div>
    </div>`;
}

function closeModal(id) {
  if (id) {
    const el = document.getElementById(id);
    if (el) { el.style.display = 'none'; return; }
  }
  document.getElementById('modal-container').innerHTML = '';
}

let _confirmResolve = null;
function confirmModal(message) {
  return new Promise(resolve => {
    _confirmResolve = resolve;
    showModal(`
      <div class="modal-header">
        <h3>Confirmation</h3>
        <button class="btn-icon" onclick="_confirmAnswer(false)">&times;</button>
      </div>
      <p style="margin:1rem 0;white-space:pre-line">${escHtml(message)}</p>
      <div style="display:flex;gap:0.5rem;justify-content:flex-end">
        <button class="btn btn-outline btn-sm" onclick="_confirmAnswer(false)">Annuler</button>
        <button class="btn btn-primary btn-sm" onclick="_confirmAnswer(true)">Confirmer</button>
      </div>
    `, 'modal-confirm');
  });
}
function _confirmAnswer(val) {
  closeModal();
  if (_confirmResolve) { _confirmResolve(val); _confirmResolve = null; }
}

// ── Pipeline Steps helpers ────────────────────────

function renderPipelineSteps(containerId, steps) {
  const el = document.getElementById(containerId);
  if (!el) return;
  const rows = (steps || []).map((s, i) => `
    <div class="pipeline-step" data-idx="${i}">
      <div class="pipeline-step-header">
        <span class="pipeline-step-num">${i + 1}</span>
        <input class="pipeline-step-name" value="${escHtml(s.name || '')}" placeholder="Nom de l'etape" />
        <input class="pipeline-step-key" value="${escHtml(s.output_key || '')}" placeholder="output_key" />
        <button class="btn-icon pipeline-step-up" onclick="movePipelineStep('${containerId}',${i},-1)" title="Monter" ${i === 0 ? 'disabled' : ''}>&uarr;</button>
        <button class="btn-icon pipeline-step-down" onclick="movePipelineStep('${containerId}',${i},1)" title="Descendre" ${i === steps.length - 1 ? 'disabled' : ''}>&darr;</button>
        <button class="btn-icon pipeline-step-del" onclick="removePipelineStep('${containerId}',${i})" title="Supprimer">&times;</button>
      </div>
      <textarea class="pipeline-step-instr" placeholder="Instruction...">${escHtml(s.instruction || '')}</textarea>
    </div>
  `).join('');
  el.innerHTML = rows + `<button class="btn btn-outline btn-sm" onclick="addPipelineStep('${containerId}')" style="margin-top:0.5rem">+ Etape</button>`;
}

function getPipelineSteps(containerId) {
  const el = document.getElementById(containerId);
  if (!el) return [];
  return [...el.querySelectorAll('.pipeline-step')].map(row => ({
    name: row.querySelector('.pipeline-step-name').value.trim(),
    output_key: row.querySelector('.pipeline-step-key').value.trim(),
    instruction: row.querySelector('.pipeline-step-instr').value.trim(),
  })).filter(s => s.name);
}

function addPipelineStep(containerId) {
  const steps = getPipelineSteps(containerId);
  steps.push({ name: '', output_key: '', instruction: '' });
  renderPipelineSteps(containerId, steps);
}

function removePipelineStep(containerId, idx) {
  const steps = getPipelineSteps(containerId);
  steps.splice(idx, 1);
  renderPipelineSteps(containerId, steps);
}

function movePipelineStep(containerId, idx, dir) {
  const steps = getPipelineSteps(containerId);
  const target = idx + dir;
  if (target < 0 || target >= steps.length) return;
  [steps[idx], steps[target]] = [steps[target], steps[idx]];
  renderPipelineSteps(containerId, steps);
}

// ═══════════════════════════════════════════════════
// SECRETS (.env)
// ═══════════════════════════════════════════════════
async function loadEnv() {
  try {
    const data = await api('/api/env');
    envEntries = data.entries;
    renderEnv();
  } catch (e) {
    toast(e.message, 'error');
  }
}

function renderEnv() {
  const tbody = document.getElementById('env-table-body');
  const search = (document.getElementById('env-search')?.value || '').toLowerCase();
  const rows = envEntries.filter(e => e.key && (!search || e.key.toLowerCase().includes(search))).map((e, i) => `
    <tr>
      <td><code>${escHtml(e.key)}</code></td>
      <td>
        <span class="masked-value" id="env-val-${i}" data-masked="true" data-value="${escHtml(e.value)}">
          ${escHtml(maskValue(e.value))}
        </span>
        <button class="btn-icon" onclick="toggleEnvVisibility(${i})" title="Afficher/masquer">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>
        </button>
      </td>
      <td>
        <button class="btn-icon" onclick="editEnvEntry('${escHtml(e.key)}')" title="Modifier">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>
        </button>
        <button class="btn-icon danger" onclick="deleteEnvEntry('${escHtml(e.key)}')" title="Supprimer">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>
        </button>
      </td>
    </tr>
  `).join('');
  tbody.innerHTML = rows || '<tr><td colspan="3" style="text-align:center;color:var(--text-secondary)">Aucun secret configure. Le fichier .env sera cree au premier ajout.</td></tr>';
}

function toggleEnvVisibility(i) {
  const el = document.getElementById(`env-val-${i}`);
  const masked = el.getAttribute('data-masked') === 'true';
  if (masked) {
    el.textContent = el.getAttribute('data-value');
    el.setAttribute('data-masked', 'false');
  } else {
    el.textContent = maskValue(el.getAttribute('data-value'));
    el.setAttribute('data-masked', 'true');
  }
}

function showAddEnvModal() {
  showModal(`
    <div class="modal-header">
      <h3>Ajouter un secret</h3>
      <button class="btn-icon" onclick="closeModal()">&times;</button>
    </div>
    <div class="form-group">
      <label>Cle</label>
      <input id="new-env-key" placeholder="MA_VARIABLE" />
    </div>
    <div class="form-group">
      <label>Valeur</label>
      <input id="new-env-value" placeholder="valeur..." />
    </div>
    <div class="form-group">
      <label>Commentaire de section (optionnel)</label>
      <input id="new-env-comment" placeholder="# -- Ma Section --" />
    </div>
    <div class="modal-actions">
      <button class="btn btn-outline" onclick="closeModal()">Annuler</button>
      <button class="btn btn-primary" onclick="addEnvEntry()">Ajouter</button>
    </div>
  `);
}

async function addEnvEntry() {
  const key = document.getElementById('new-env-key').value.trim();
  const value = document.getElementById('new-env-value').value;
  const comment = document.getElementById('new-env-comment').value;
  if (!key) { toast('La cle est requise', 'error'); return; }
  try {
    await api('/api/env/add', { method: 'POST', body: { key, value, section_comment: comment } });
    toast('Secret ajoute', 'success');
    closeModal();
    loadEnv();
  } catch (e) { toast(e.message, 'error'); }
}

function editEnvEntry(key) {
  const entry = envEntries.find(e => e.key === key);
  showModal(`
    <div class="modal-header">
      <h3>Modifier: ${escHtml(entry.key)}</h3>
      <button class="btn-icon" onclick="closeModal()">&times;</button>
    </div>
    <div class="form-group">
      <label>Valeur</label>
      <div style="display:flex;gap:0.5rem">
        <input id="edit-env-value" value="${escHtml(entry.value)}" style="flex:1" />
        <button class="btn btn-outline btn-sm" onclick="pasteToEnvValue()">Coller</button>
      </div>
    </div>
    <div class="modal-actions">
      <button class="btn btn-outline" onclick="closeModal()">Annuler</button>
      <button class="btn btn-primary" onclick="saveEnvEntry('${escHtml(entry.key)}')">Sauvegarder</button>
    </div>
  `);
}

async function pasteToEnvValue() {
  const field = document.getElementById('edit-env-value');
  if (navigator.clipboard && navigator.clipboard.readText) {
    try {
      field.value = await navigator.clipboard.readText();
      return;
    } catch {}
  }
  // Fallback HTTP : focus + select pour Ctrl+V
  field.value = '';
  field.focus();
  toast('HTTPS requis pour le collage auto. Faites Ctrl+V dans le champ.', 'info');
}

async function saveEnvEntry(key) {
  const value = document.getElementById('edit-env-value').value;
  const updated = envEntries.map(e => e.key === key ? { ...e, value } : e);
  try {
    await api('/api/env', { method: 'PUT', body: { entries: updated } });
    toast('Secret modifie', 'success');
    closeModal();
    loadEnv();
  } catch (e) { toast(e.message, 'error'); }
}

async function deleteEnvEntry(key) {
  if (!(await confirmModal(`Supprimer "${key}" ?`))) return;
  try {
    await api('/api/env/delete', { method: 'POST', body: { key } });
    toast('Secret supprime', 'success');
    loadEnv();
  } catch (e) { toast(e.message, 'error'); }
}

// ═══════════════════════════════════════════════════
// MCP SERVICES — Catalogue-driven
// ═══════════════════════════════════════════════════
let mcpShowDeprecated = false;

async function loadMCP() {
  try {
    const data = await api('/api/mcp/catalog');
    mcpCatalog = data.servers;
    renderMCP();
  } catch (e) { toast(e.message, 'error'); }
}

function renderMCP() {
  const withParams = mcpCatalog.filter(c => c.env_vars.length > 0 && c.installed);
  const noParams = mcpCatalog.filter(c => c.env_vars.length === 0 && (mcpShowDeprecated || !c.deprecated));

  // ── Top: Services with parameters (installed only) ──
  const configuredEl = document.getElementById('mcp-configured');
  if (withParams.length === 0) {
    configuredEl.innerHTML = '<p style="color:var(--text-secondary);text-align:center;padding:1rem">Aucun service avec parametres installe.</p>';
  } else {
    configuredEl.innerHTML = `<table>
      <thead><tr><th>Service</th><th>Commande</th><th>Env</th><th>Agents</th><th>Actif</th><th>Actions</th></tr></thead>
      <tbody>${withParams.map(c => {
        const envStatus = c.env_vars.length === 0
          ? '<span class="tag tag-gray">aucune</span>'
          : c.env_vars.map(v =>
              `<span class="tag ${v.configured ? 'tag-green' : 'tag-red'}" title="${escHtml(v.desc)}">${escHtml(v.mapped_var || v.var)}</span>`
            ).join(' ');
        const agentTags = c.agents.length
          ? c.agents.map(a => `<span class="tag tag-blue">${escHtml(a)}</span>`).join(' ')
          : '<span style="color:var(--text-secondary);font-size:0.75rem">aucun</span>';
        return `<tr>
          <td>
            <strong>${escHtml(c.label)}</strong>
            <div style="font-size:0.7rem;color:var(--text-secondary)">${escHtml(c.id)}</div>
          </td>
          <td><code style="font-size:0.75rem">${escHtml(c.command)} ${escHtml(c.args)}</code></td>
          <td>${envStatus}</td>
          <td>${agentTags}</td>
          <td>
            <div class="toggle ${c.enabled ? 'active' : ''}" onclick="toggleMCP('${escHtml(c.id)}', ${!c.enabled})"></div>
          </td>
          <td>
            <button class="btn-icon" onclick="showMCPEnvModal('${escHtml(c.id)}')" title="Configurer env">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>
            </button>
            <button class="btn-icon danger" onclick="uninstallMCP('${escHtml(c.id)}')" title="Desinstaller">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>
            </button>
          </td>
        </tr>`;
      }).join('')}</tbody>
    </table>`;
  }

  // ── Bottom: Catalogue with Install / Activé buttons ──
  const catalogEl = document.getElementById('mcp-catalog');
  catalogEl.innerHTML = noParams.map(c => {
    let statusBtn;
    if (c.installed) {
      statusBtn = `<div class="toggle ${c.enabled ? 'active' : ''}" onclick="event.stopPropagation();toggleMCP('${escHtml(c.id)}', ${!c.enabled})" style="cursor:pointer"></div>`;
    } else {
      statusBtn = c.env_vars.length
        ? `<button class="btn btn-sm btn-primary" onclick="event.stopPropagation();showAddCatalogModal('${escHtml(c.id)}')">Installer</button>`
        : `<button class="btn btn-sm btn-primary" onclick="event.stopPropagation();quickInstallMcp('${escHtml(c.id)}')">Installer</button>`;
    }
    return `<div class="mcp-card${c.deprecated ? ' deprecated' : ''}">
      <div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:0.5rem">
        <div>
          <strong>${escHtml(c.label)}</strong>
          ${c.deprecated ? '<span class="tag tag-red" style="margin-left:0.5rem">deprecie</span>' : ''}
        </div>
        ${statusBtn}
      </div>
      <p style="font-size:0.8rem;color:var(--text-secondary);margin-bottom:0.5rem">${escHtml(c.description)}</p>
      <code style="font-size:0.7rem;color:var(--text-secondary)">${escHtml(c.command)} ${escHtml(c.args)}</code>
      ${c.env_vars.length ? `<div style="margin-top:0.5rem">${c.env_vars.map(v =>
        `<span class="tag ${v.configured ? 'tag-green' : 'tag-yellow'}" style="margin:0.1rem" title="${escHtml(v.desc)}">${escHtml(v.mapped_var || v.var)}</span>`
      ).join('')}</div>` : ''}
    </div>`;
  }).join('');
}

// ── Install service modal (dropdown-based) ──
function showAddCatalogModal(preselectedId) {
  const available = mcpCatalog.filter(c => !c.installed);
  if (available.length === 0) {
    toast('Tous les services du catalogue sont deja installes', 'info');
    return;
  }
  const selected = preselectedId
    ? mcpCatalog.find(c => c.id === preselectedId)
    : available[0];
  if (!selected) return;

  const options = available.map(c =>
    `<option value="${escHtml(c.id)}" ${c.id === selected.id ? 'selected' : ''}>${escHtml(c.label)} — ${escHtml(c.description)}</option>`
  ).join('');

  showModal(`
    <div class="modal-header">
      <h3>Installer un service MCP</h3>
      <button class="btn-icon" onclick="closeModal()">&times;</button>
    </div>
    <div class="form-group">
      <label>Service</label>
      <select id="mcp-install-select" onchange="onMCPServiceSelected()">
        ${options}
      </select>
    </div>
    <div id="mcp-install-details">${_renderInstallDetails(selected)}</div>
    <div class="modal-actions">
      <button class="btn btn-outline" onclick="closeModal()">Annuler</button>
      <button class="btn btn-primary" onclick="installSelectedService()">Enregistrer</button>
    </div>
  `, 'modal-wide');
}

function _normalizeInstanceId(name) {
  return name.replace(/[^a-zA-Z0-9]/g, '_').toUpperCase();
}

function _renderInstallDetails(item) {
  const hasEnv = item.env_vars.length > 0;
  const prefix = _normalizeInstanceId(item.id);

  const instanceHtml = hasEnv ? `
    <div class="form-group" style="margin-top:0.5rem">
      <label>Nom de l'instance</label>
      <input id="mcp-instance-name" value="${escHtml(item.id)}" oninput="_updateInstallEnvNames()" />
    </div>` : '';

  const envVarsHtml = hasEnv
    ? `<div style="margin-top:1rem">
        <label>Variables d'environnement</label>
        <div class="env-var-list" id="mcp-install-env-list">
          ${item.env_vars.map(v => {
            const envName = `${prefix}_${v.var}`;
            return `
            <div class="env-var-row">
              <div class="env-var-info">
                <code class="mcp-env-computed" data-base="${escHtml(v.var)}">${escHtml(envName)}</code>
                <span class="env-var-desc">${escHtml(v.desc)}</span>
              </div>
              <div class="env-var-action">
                <input class="mcp-install-env" data-var="${escHtml(v.var)}" placeholder="Valeur..." />
                <button class="btn btn-sm btn-outline" onclick="saveInstallEnvVar(this)" title="Enregistrer dans .env">
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z"/><polyline points="17 21 17 13 7 13 7 21"/><polyline points="7 3 7 8 15 8"/></svg>
                </button>
              </div>
            </div>`;
          }).join('')}
        </div>
      </div>`
    : '<p style="color:var(--text-secondary);font-size:0.85rem;margin-top:1rem">Aucune variable d\'environnement requise.</p>';

  return `
    ${instanceHtml}
    <div class="form-row" style="margin-top:0.5rem">
      <div class="form-group">
        <label>Commande</label>
        <input value="${escHtml(item.command)}" readonly style="opacity:0.6" />
      </div>
      <div class="form-group">
        <label>Arguments</label>
        <input value="${escHtml(item.args)}" readonly style="opacity:0.6" />
      </div>
    </div>
    <p class="mcp-cmd-help">${escHtml(MCP_CMD_HELP[item.command] || '')}</p>
    ${envVarsHtml}
  `;
}

function _updateInstallEnvNames() {
  const name = document.getElementById('mcp-instance-name')?.value.trim() || '';
  const prefix = _normalizeInstanceId(name || 'INSTANCE');
  document.querySelectorAll('.mcp-env-computed').forEach(el => {
    const base = el.getAttribute('data-base');
    el.textContent = `${prefix}_${base}`;
  });
}

async function saveInstallEnvVar(btn) {
  const row = btn.closest('.env-var-row');
  const input = row.querySelector('.mcp-install-env');
  const computedEl = row.querySelector('.mcp-env-computed');
  const varName = computedEl.textContent;
  const value = input.value.trim();
  if (!value) { toast('Valeur requise', 'error'); return; }
  try {
    await api('/api/env/add', { method: 'POST', body: { key: varName, value, section_comment: '' } });
    toast(`${varName} enregistre dans .env`, 'success');
    _markEnvVarConfigured(btn);
    input.value = '';
  } catch (e) {
    if (e.message.includes('already exists')) {
      try {
        const data = await api('/api/env');
        const entries = data.entries.map(en => en.key === varName ? { ...en, value } : en);
        await api('/api/env', { method: 'PUT', body: { entries } });
        toast(`${varName} mis a jour dans .env`, 'success');
        _markEnvVarConfigured(btn);
        input.value = '';
      } catch (e2) { toast(e2.message, 'error'); }
    } else { toast(e.message, 'error'); }
  }
}

function onMCPServiceSelected() {
  const id = document.getElementById('mcp-install-select').value;
  const item = mcpCatalog.find(c => c.id === id);
  if (item) {
    document.getElementById('mcp-install-details').innerHTML = _renderInstallDetails(item);
  }
}

async function setEnvVarFromInstall(varName, btn) {
  const input = btn.closest('.env-var-action').querySelector('input');
  const value = input.value.trim();
  if (!value) { toast('Valeur requise', 'error'); return; }
  try {
    await api('/api/env/add', { method: 'POST', body: { key: varName, value, section_comment: '' } });
    toast(`${varName} enregistre dans .env`, 'success');
    _markEnvVarConfigured(btn);
    input.value = '';
  } catch (e) {
    if (e.message.includes('already exists')) {
      try {
        const data = await api('/api/env');
        const entries = data.entries.map(en => en.key === varName ? { ...en, value } : en);
        await api('/api/env', { method: 'PUT', body: { entries } });
        toast(`${varName} mis a jour dans .env`, 'success');
        _markEnvVarConfigured(btn);
        input.value = '';
      } catch (e2) { toast(e2.message, 'error'); }
    } else { toast(e.message, 'error'); }
  }
}

function _markEnvVarConfigured(btn) {
  const row = btn.closest('.env-var-row');
  const tag = row.querySelector('.tag');
  if (tag) { tag.className = 'tag tag-green'; tag.textContent = 'configure'; }
}

async function quickInstallMcp(id) {
  try {
    await api(`/api/mcp/install/${id}`, { method: 'POST', body: { env_values: {}, env_mapping: {} } });
    toast(`Service "${id}" installe`, 'success');
    loadMCP().catch(() => {});
  } catch (e) { toast(e.message, 'error'); }
}

async function quickInstallCfgMcp(id) {
  try {
    await api(`/api/mcp/install/${id}`, { method: 'POST', body: { env_values: {}, env_mapping: {} } });
    toast(`Service "${id}" installe`, 'success');
    loadCfgMCP().catch(() => {});
  } catch (e) { toast(e.message, 'error'); }
}

async function quickInstallTplMcp(id) {
  try {
    await api(`/api/templates/mcp/install/${id}`, { method: 'POST', body: { env_values: {}, env_mapping: {} } });
    toast(`Service "${id}" installe`, 'success');
    loadTplMCP().catch(() => {});
  } catch (e) { toast(e.message, 'error'); }
}

async function installSelectedService() {
  const id = document.getElementById('mcp-install-select').value;
  // Build env mapping: {base_var: computed_var}
  const envMapping = {};
  document.querySelectorAll('.mcp-env-computed').forEach(el => {
    const base = el.getAttribute('data-base');
    envMapping[base] = el.textContent;
  });
  try {
    await api(`/api/mcp/install/${id}`, { method: 'POST', body: { env_values: {}, env_mapping: envMapping } });
    toast('Service MCP installe', 'success');
    closeModal();
    loadMCP();
  } catch (e) { toast(e.message, 'error'); }
}

async function uninstallMCP(id) {
  if (!(await confirmModal(`Desinstaller le serveur MCP "${id}" ?\nLes acces agents seront aussi retires.`))) return;
  try {
    await api(`/api/mcp/uninstall/${id}`, { method: 'POST' });
    toast('Serveur MCP desinstalle', 'success');
    loadMCP();
  } catch (e) { toast(e.message, 'error'); }
}

async function toggleMCP(id, enabled) {
  try {
    await api(`/api/mcp/toggle/${id}`, { method: 'PUT', body: { enabled } });
    loadMCP();
  } catch (e) { toast(e.message, 'error'); }
}

// Configure env vars for installed MCP
function showMCPEnvModal(id) {
  const item = mcpCatalog.find(c => c.id === id);
  if (!item || !item.env_vars.length) {
    toast('Aucune variable d\'environnement pour ce serveur', 'info');
    return;
  }
  showModal(`
    <div class="modal-header">
      <h3>Env : ${escHtml(item.label)}</h3>
      <button class="btn-icon" onclick="closeModal()">&times;</button>
    </div>
    <div class="env-var-list">
      ${item.env_vars.map(v => `
        <div class="env-var-row">
          <div class="env-var-info">
            <code>${escHtml(v.mapped_var || v.var)}</code>
            <span class="env-var-desc">${escHtml(v.desc)}</span>
            ${v.configured
              ? '<span class="tag tag-green">configure</span>'
              : '<span class="tag tag-red">manquant</span>'}
          </div>
          <div class="env-var-action">
            <input class="mcp-env-field" data-var="${escHtml(v.mapped_var || v.var)}" placeholder="Nouvelle valeur..." />
            <button class="btn btn-sm btn-outline" onclick="setEnvVarFromInstall('${escHtml(v.mapped_var || v.var)}', this)" title="Enregistrer dans .env">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z"/><polyline points="17 21 17 13 7 13 7 21"/><polyline points="7 3 7 8 15 8"/></svg>
            </button>
          </div>
        </div>
      `).join('')}
    </div>
    <div class="modal-actions">
      <button class="btn btn-outline" onclick="closeModal()">Fermer</button>
    </div>
  `);
}

function toggleDeprecated() {
  mcpShowDeprecated = !mcpShowDeprecated;
  const btn = document.getElementById('btn-show-deprecated');
  btn.textContent = mcpShowDeprecated ? 'Masquer deprecies' : 'Afficher deprecies';
  renderMCP();
}

// ═══════════════════════════════════════════════════
// AGENTS
// ═══════════════════════════════════════════════════
async function loadAgents() {
  try {
    const [agentsData, llmData, mcpData] = await Promise.all([
      api('/api/agents'),
      api('/api/llm/providers'),
      api('/api/mcp/catalog'),
    ]);
    agentGroups = agentsData.groups || [];
    // Flat map for edit/save lookups + build mcpAccess from per-team data
    agents = {};
    mcpAccess = {};
    agentGroups.forEach(g => {
      const teamAccess = g.mcp_access || {};
      Object.entries(g.agents).forEach(([id, a]) => {
        agents[id] = { ...a, _team_id: g.team_id, _team_dir: g.team_dir || g.team_id };
        if (teamAccess[id]) mcpAccess[id] = teamAccess[id];
      });
    });
    llmProviders = llmData;
    mcpCatalog = mcpData.servers;
    renderAgents();
  } catch (e) { toast(e.message, 'error'); }
}

function renderAgents() {
  const grid = document.getElementById('agents-grid');

  grid.innerHTML = agentGroups.map(g => {
    const orchId = g.orchestrator || '';
    const agentCards = Object.entries(g.agents).map(([id, a]) => {
      const mcpList = (mcpAccess[id] || []);
      const isOrch = id === orchId;
      return `<div class="agent-card${isOrch ? ' agent-orchestrator' : ''}" onclick="editAgent('${escHtml(id)}')">
        <div class="agent-card-header">
          <div>
            <h4>${isOrch ? '<span class="orch-badge" title="Orchestrateur">&#9733;</span> ' : ''}${escHtml(a.name)}</h4>
            <code style="font-size:0.75rem;color:var(--text-secondary)">${escHtml(id)}</code>
          </div>
          <button class="btn-icon danger" onclick="event.stopPropagation();deleteAgent('${escHtml(id)}')" title="Supprimer">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>
          </button>
        </div>
        <div class="agent-meta">
          <span class="tag tag-blue">temp: ${a.temperature}</span>
          <span class="tag tag-blue">tokens: ${a.max_tokens}</span>
          ${a.model ? `<span class="tag tag-yellow">${escHtml(a.model)}</span>` : ''}
          ${a.type ? `<span class="tag tag-gray">${escHtml(a.type)}</span>` : ''}
        </div>
        ${mcpList.length ? `<div class="agent-meta" style="margin-top:0.5rem">
          ${mcpList.map(m => `<span class="tag tag-green">${escHtml(m)}</span>`).join('')}
        </div>` : ''}
      </div>`;
    }).join('');
    return `<div class="agent-group">
      <h3 class="agent-group-title">
        ${escHtml(g.team_name)}<span style="font-weight:400;font-size:0.75rem;color:var(--text-secondary);margin-left:0.5rem">${escHtml(g.team_id)}</span>
        <button class="btn-icon" onclick="event.stopPropagation();editTeam('${escHtml(g.team_id)}')" title="Modifier l'equipe" style="margin-left:0.5rem;opacity:0.5">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M17 3a2.83 2.83 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5Z"/><path d="m15 5 4 4"/></svg>
        </button>
      </h3>
      ${g.team_description ? `<p style="font-size:0.8rem;color:var(--text-secondary);margin:-0.5rem 0 0.5rem 0">${escHtml(g.team_description)}</p>` : ''}
      <div class="agents-grid">${agentCards || '<p style="color:var(--text-secondary);padding:0.5rem">Aucun agent dans cette equipe.</p>'}</div>
    </div>`;
  }).join('');
}

// editTeam is defined in the Teams section below (with members support)

async function editAgent(id) {
  const a = agents[id];
  const providerNames = Object.keys(llmProviders.providers || {});
  const mcpList = mcpAccess[id] || [];
  let mcpInstalled = [];
  try { const d = await api('/api/mcp/servers'); mcpInstalled = Object.keys(d.servers || {}); } catch {}

  const mcpChips = mcpInstalled.length > 0
    ? mcpInstalled.map(sid => {
        const checked = mcpList.includes(sid);
        return `<label class="mcp-chip${checked ? ' active' : ''}" title="${escHtml(sid)}">
          <input type="checkbox" class="agent-mcp-cb" value="${escHtml(sid)}" ${checked ? 'checked' : ''} onchange="this.parentElement.classList.toggle('active',this.checked)" />
          ${escHtml(sid)}
        </label>`;
      }).join('')
    : '<p style="color:var(--text-secondary);font-size:0.8rem">Aucun serveur MCP installe.</p>';

  const isOrchestrator = a.type === 'orchestrator';
  const hasPipeline = a.type === 'pipeline' || (a.pipeline_steps && a.pipeline_steps.length > 0);
  const curType = isOrchestrator ? 'orchestrator' : (hasPipeline ? 'pipeline' : 'single');
  const hasOtherOrch = Object.entries(agents).some(([aid, ag]) => aid !== id && ag.type === 'orchestrator');

  showModal(`
    <div class="modal-header">
      <h3>Agent: ${escHtml(a.name)} (${escHtml(id)})</h3>
      <button class="btn-icon" onclick="closeModal()">&times;</button>
    </div>
    <div class="agent-tabs">
      <div class="agent-tab active" onclick="switchAgentTab('divers')">Divers</div>
      <div class="agent-tab" onclick="switchAgentTab('pipeline')">Pipeline Steps</div>
    </div>

    <!-- Tab: Divers -->
    <div id="agent-tab-divers" class="agent-tab-content active">
      <div class="form-row">
        <div class="form-group">
          <label>Nom</label>
          <input id="agent-edit-name" value="${escHtml(a.name)}" />
        </div>
        <div class="form-group">
          <label>Modele LLM</label>
          <select id="agent-edit-model">
            <option value="">-- Defaut (${escHtml(llmProviders.default || '')}) --</option>
            ${providerNames.map(p => `<option value="${p}" ${a.model === p ? 'selected' : ''}>${escHtml(p)} — ${escHtml(llmProviders.providers[p]?.description || '')}</option>`).join('')}
          </select>
        </div>
      </div>
      <div class="form-row">
        <div class="form-group">
          <label>Temperature</label>
          <input id="agent-edit-temp" type="number" step="0.1" min="0" max="2" value="${a.temperature}" />
        </div>
        <div class="form-group">
          <label>Max tokens</label>
          <input id="agent-edit-tokens" type="number" value="${a.max_tokens}" />
        </div>
      </div>
      <div class="form-group">
        <label>Type</label>
        <select id="agent-edit-type">
          <option value="single" ${curType==='single'?'selected':''}>Single</option>
          <option value="pipeline" ${curType==='pipeline'?'selected':''}>Pipeline</option>
          <option value="orchestrator" ${curType==='orchestrator'?'selected':''} ${hasOtherOrch && curType!=='orchestrator'?'disabled':''}>Orchestrator</option>
        </select>
      </div>
      <div class="form-group">
        <label>Services MCP autorises</label>
        <div class="mcp-chips">
          ${mcpChips}
        </div>
      </div>
    </div>

    <!-- Tab: Pipeline Steps -->
    <div id="agent-tab-pipeline" class="agent-tab-content">
      <p style="color:var(--text-secondary);font-size:0.85rem;margin-bottom:1rem">Definissez les etapes du pipeline. Chaque etape a un nom, une cle de sortie (output_key) et une instruction.</p>
      <div id="agent-edit-pipeline-steps" class="pipeline-steps-container"></div>
    </div>

    <div class="modal-actions">
      <button class="btn btn-outline" onclick="closeModal()">Annuler</button>
      <button class="btn btn-primary" onclick="saveAgent('${escHtml(id)}')">Sauvegarder</button>
    </div>
  `, 'modal-wide');
  renderPipelineSteps('agent-edit-pipeline-steps', a.pipeline_steps || []);
}

function switchPromptTab(tab) {
  const preview = document.getElementById('agent-prompt-preview');
  const editor = document.getElementById('agent-edit-prompt');
  const tabPreview = document.getElementById('prompt-tab-preview');
  const tabEdit = document.getElementById('prompt-tab-edit');
  if (tab === 'edit') {
    preview.style.display = 'none';
    editor.style.display = '';
    tabPreview.classList.remove('active');
    tabEdit.classList.add('active');
  } else {
    const raw = editor.value;
    preview.innerHTML = typeof marked !== 'undefined' ? marked.parse(raw) : escHtml(raw);
    preview.style.display = '';
    editor.style.display = 'none';
    tabPreview.classList.add('active');
    tabEdit.classList.remove('active');
  }
}

function switchAgentTab(tab) {
  document.querySelectorAll('.agent-tab').forEach(t => t.classList.remove('active'));
  document.querySelectorAll('.agent-tab-content').forEach(c => c.classList.remove('active'));
  document.querySelector(`.agent-tab[onclick*="'${tab}'"]`).classList.add('active');
  document.getElementById(`agent-tab-${tab}`).classList.add('active');
}

async function generatePrompt(textareaId, agentId, agentName) {
  const textarea = document.getElementById(textareaId);
  const btn = document.getElementById('btn-generate-prompt');
  if (!textarea || !btn) return;
  const info = textarea.value.trim();
  if (!info) { toast('Remplissez le prompt avant de generer', 'error'); return; }

  const prevText = btn.textContent;
  btn.disabled = true;
  btn.textContent = 'Generation...';

  try {
    const result = await api('/api/agents/generate-prompt', {
      method: 'POST',
      body: { agent_info: info, agent_id: agentId || '', agent_name: agentName || '' }
    });
    textarea.value = result.prompt;
    // Switch to edit sub-tab to show the result
    switchPromptTab('edit');
    toast('Prompt genere', 'success');
  } catch (e) {
    toast('Erreur generation: ' + e.message, 'error');
  } finally {
    btn.disabled = false;
    btn.textContent = prevText;
  }
}

async function saveAgent(id) {
  const name = document.getElementById('agent-edit-name').value.trim();
  const model = document.getElementById('agent-edit-model').value;
  const temperature = parseFloat(document.getElementById('agent-edit-temp').value);
  const max_tokens = parseInt(document.getElementById('agent-edit-tokens').value);
  const agentType = document.getElementById('agent-edit-type').value;
  if (agentType === 'orchestrator' && Object.entries(agents).some(([aid, ag]) => aid !== id && ag.type === 'orchestrator')) {
    toast('Un orchestrator existe deja dans cette equipe', 'error'); return;
  }
  const pipeline_steps = getPipelineSteps('agent-edit-pipeline-steps');
  const mcpCheckboxes = document.querySelectorAll('.agent-mcp-cb:checked');
  const mcpList = Array.from(mcpCheckboxes).map(cb => cb.value);

  const teamDir = agents[id]._team_dir || agents[id]._team_id || 'default';
  try {
    await Promise.all([
      api(`/api/agents/${id}`, {
        method: 'PUT',
        body: { id, name, model, temperature, max_tokens, prompt_file: '', type: agentType, pipeline_steps, team_id: agents[id]._team_id || 'default' }
      }),
      api(`/api/agents/mcp-access/${encodeURIComponent(teamDir)}/${encodeURIComponent(id)}`, { method: 'PUT', body: { servers: mcpList } }),
    ]);
    toast('Agent sauvegarde', 'success');
    closeModal();
    loadAgents();
  } catch (e) { toast(e.message, 'error'); }
}

async function showAddAgentModal() {
  const providerNames = Object.keys(llmProviders.providers || {});
  const teamOpts = agentGroups.map(g => `<option value="${escHtml(g.team_id)}">${escHtml(g.team_name)}</option>`).join('');

  // Load shared agents catalog
  let sharedList = [];
  try { const d = await api('/api/shared-agents'); sharedList = d.agents || []; } catch {}
  const agentOpts = sharedList.length
    ? sharedList.map(a => `<option value="${escHtml(a.id)}" data-name="${escHtml(a.name || a.id)}" data-llm="${escHtml(a.llm || '')}" data-temp="${a.temperature ?? 0.2}">${escHtml(a.name || a.id)} (${escHtml(a.id)})</option>`).join('')
    : '';

  showModal(`
    <div class="modal-header">
      <h3>Ajouter un agent</h3>
      <button class="btn-icon" onclick="closeModal()">&times;</button>
    </div>
    <div class="form-group">
      <label>Agent (catalogue)</label>
      <select id="agent-new-id" onchange="_onSharedAgentSelect()">
        <option value="">-- Choisir un agent --</option>
        ${agentOpts}
      </select>
      ${!sharedList.length ? '<p style="color:var(--text-secondary);font-size:0.8rem;margin-top:0.25rem">Aucun agent dans le catalogue. Creez-en d\'abord dans Templates &gt; Agents.</p>' : ''}
    </div>
    <div class="form-row">
      <div class="form-group">
        <label>Nom affiche</label>
        <input id="agent-new-name" placeholder="Mon Agent" />
      </div>
      <div class="form-group">
        <label>Equipe</label>
        <select id="agent-new-team">${teamOpts}</select>
      </div>
    </div>
    <div class="form-row">
      <div class="form-group">
        <label>Modele LLM</label>
        <select id="agent-new-model">
          <option value="">-- Defaut --</option>
          ${providerNames.map(p => `<option value="${p}">${escHtml(p)}</option>`).join('')}
        </select>
      </div>
      <div class="form-group">
        <label>Temperature</label>
        <input id="agent-new-temp" type="number" step="0.1" min="0" max="2" value="0.2" />
      </div>
    </div>
    <div class="form-group">
      <label>Type</label>
      <select id="agent-new-type">
        <option value="single" selected>Single</option>
        <option value="pipeline">Pipeline</option>
        <option value="orchestrator" ${Object.values(agents).some(ag => ag.type === 'orchestrator') ? 'disabled' : ''}>Orchestrator</option>
      </select>
    </div>
    <div class="modal-actions">
      <button class="btn btn-outline" onclick="closeModal()">Annuler</button>
      <button class="btn btn-primary" onclick="addAgent()">Ajouter</button>
    </div>
  `);
}

function _onSharedAgentSelect() {
  const sel = document.getElementById('agent-new-id');
  const opt = sel.selectedOptions[0];
  if (!opt || !opt.value) return;
  document.getElementById('agent-new-name').value = opt.dataset.name || opt.value;
  const llm = opt.dataset.llm || '';
  if (llm) {
    const modelSel = document.getElementById('agent-new-model');
    if (modelSel) modelSel.value = llm;
  }
  const temp = opt.dataset.temp;
  if (temp) document.getElementById('agent-new-temp').value = temp;
}

async function addAgent() {
  const id = document.getElementById('agent-new-id').value.trim();
  const name = document.getElementById('agent-new-name').value.trim();
  const model = document.getElementById('agent-new-model').value;
  const temperature = parseFloat(document.getElementById('agent-new-temp').value);
  const team_id = document.getElementById('agent-new-team')?.value || 'default';
  if (!id) { toast('Selectionnez un agent du catalogue', 'error'); return; }
  if (!name) { toast('Nom requis', 'error'); return; }
  const agentType = document.getElementById('agent-new-type').value;
  if (agentType === 'orchestrator' && Object.values(agents).some(ag => ag.type === 'orchestrator')) {
    toast('Un orchestrator existe deja dans cette equipe', 'error'); return;
  }
  // Load prompt + MCP from the shared agent catalog
  let prompt_content = '', mcp_access = [];
  try {
    const sa = await api(`/api/shared-agents/${encodeURIComponent(id)}`);
    prompt_content = sa.prompt_content || '';
    mcp_access = sa.mcp_access || [];
  } catch {}
  const teamDir = agentGroups.find(g => g.team_id === team_id)?.team_dir || team_id;
  try {
    await api('/api/agents', {
      method: 'POST',
      body: { id, name, model, temperature, max_tokens: 32768, prompt_content, prompt_file: '', type: agentType, pipeline_steps: [], team_id }
    });
    if (mcp_access.length) {
      await api(`/api/agents/mcp-access/${encodeURIComponent(teamDir)}/${encodeURIComponent(id)}`, { method: 'PUT', body: { servers: mcp_access } });
    }
    toast('Agent ajoute', 'success');
    closeModal();
    loadAgents();
  } catch (e) { toast(e.message, 'error'); }
}

async function deleteAgent(id) {
  if (!(await confirmModal(`Supprimer l'agent "${id}" ?`))) return;
  const tid = agents[id]?._team_id || 'default';
  try {
    await api(`/api/agents/${id}?team_id=${encodeURIComponent(tid)}`, { method: 'DELETE' });
    toast('Agent supprime', 'success');
    loadAgents();
  } catch (e) { toast(e.message, 'error'); }
}

// ═══════════════════════════════════════════════════
// LLM PROVIDERS
// ═══════════════════════════════════════════════════

const LLM_TYPES = ['anthropic', 'openai', 'azure', 'google', 'mistral', 'deepseek', 'moonshot', 'groq', 'ollama'];

async function loadLLM() {
  try {
    const data = await api('/api/llm/providers');
    llmProviders = data;
    renderLLM();
  } catch (e) { toast(e.message, 'error'); }
}

function renderLLM() {
  const providers = llmProviders.providers || {};
  const throttling = llmProviders.throttling || {};
  const defaultId = llmProviders.default || '';

  // Default select
  const sel = document.getElementById('llm-default-select');
  sel.innerHTML = `<option value="">-- Aucun --</option>` +
    Object.entries(providers).map(([id, p]) =>
      `<option value="${escHtml(id)}" ${id === defaultId ? 'selected' : ''}>${escHtml(id)} — ${escHtml(p.description || p.model)}</option>`
    ).join('');

  // Providers table
  const tbl = document.getElementById('llm-providers-table');
  if (Object.keys(providers).length === 0) {
    tbl.innerHTML = '<p style="color:var(--text-secondary);text-align:center;padding:1rem">Aucun provider configure.</p>';
  } else {
    tbl.innerHTML = `<table>
      <thead><tr><th>ID</th><th>Type</th><th>Modele</th><th>Cle API</th><th>Description</th><th style="width:100px">Actions</th></tr></thead>
      <tbody>${Object.entries(providers).map(([id, p]) => {
        const isDefault = id === defaultId;
        return `<tr>
          <td>
            <strong>${escHtml(id)}</strong>
            ${isDefault ? '<span class="tag tag-green" style="margin-left:0.5rem">defaut</span>' : ''}
          </td>
          <td><span class="tag tag-blue">${escHtml(p.type)}</span></td>
          <td><code style="font-size:0.8rem">${escHtml(p.model)}</code></td>
          <td>${p.env_key ? `<code style="font-size:0.75rem">${escHtml(p.env_key)}</code>` : '<span style="color:var(--text-secondary)">—</span>'}</td>
          <td style="font-size:0.8rem;color:var(--text-secondary)">${escHtml(p.description || '')}</td>
          <td>
            <button class="btn-icon" onclick="editProvider('${escHtml(id)}')" title="Modifier">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>
            </button>
            <button class="btn-icon danger" onclick="deleteProvider('${escHtml(id)}')" title="Supprimer">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>
            </button>
          </td>
        </tr>`;
      }).join('')}</tbody>
    </table>`;
  }

  // Throttling table
  const ttbl = document.getElementById('llm-throttling-table');
  if (Object.keys(throttling).length === 0) {
    ttbl.innerHTML = '<p style="color:var(--text-secondary);text-align:center;padding:1rem">Aucune regle de throttling.</p>';
  } else {
    ttbl.innerHTML = `<table>
      <thead><tr><th>Cle API</th><th>RPM</th><th>TPM</th><th style="width:100px">Actions</th></tr></thead>
      <tbody>${Object.entries(throttling).map(([key, t]) => `<tr>
        <td><code>${escHtml(key)}</code></td>
        <td>${t.rpm}</td>
        <td>${t.tpm.toLocaleString()}</td>
        <td>
          <button class="btn-icon" onclick="editThrottling('${escHtml(key)}', ${t.rpm}, ${t.tpm})" title="Modifier">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>
          </button>
          <button class="btn-icon danger" onclick="deleteThrottling('${escHtml(key)}')" title="Supprimer">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>
          </button>
        </td>
      </tr>`).join('')}</tbody>
    </table>`;
  }
}

async function setLLMDefault(providerId) {
  try {
    await api('/api/llm/providers/default', { method: 'PUT', body: { provider_id: providerId } });
    toast('Modele par defaut mis a jour', 'success');
    loadLLM();
  } catch (e) { toast(e.message, 'error'); }
}

function _providerTypeFields(type, values = {}) {
  let extra = '';
  if (type === 'azure') {
    extra = `<div id="llm-extra-fields">
      <div class="form-group">
        <label>Azure Endpoint</label>
        <input id="prov-azure-endpoint" value="${escHtml(values.azure_endpoint || '')}" placeholder="https://xxx.openai.azure.com/" />
      </div>
      <div class="form-row">
        <div class="form-group">
          <label>Azure Deployment</label>
          <input id="prov-azure-deployment" value="${escHtml(values.azure_deployment || '')}" />
        </div>
        <div class="form-group">
          <label>API Version</label>
          <input id="prov-api-version" value="${escHtml(values.api_version || '2024-12-01-preview')}" />
        </div>
      </div>
    </div>`;
  } else {
    extra = '<div id="llm-extra-fields"></div>';
  }
  return extra;
}

function _updateProviderTypeFields() {
  const type = document.getElementById('prov-type').value;
  const container = document.getElementById('llm-extra-fields');
  if (container) container.outerHTML = _providerTypeFields(type);
}

function showAddProviderModal() {
  showModal(`
    <div class="modal-header">
      <h3>Ajouter un provider LLM</h3>
      <button class="btn-icon" onclick="closeModal()">&times;</button>
    </div>
    <div class="form-row">
      <div class="form-group">
        <label>ID (unique)</label>
        <input id="prov-id" placeholder="mon-modele" />
      </div>
      <div class="form-group">
        <label>Type</label>
        <select id="prov-type" onchange="_updateProviderTypeFields()">
          ${LLM_TYPES.map(t => `<option value="${t}">${t}</option>`).join('')}
        </select>
      </div>
    </div>
    <div class="form-row">
      <div class="form-group">
        <label>Modele</label>
        <input id="prov-model" placeholder="gpt-4o, claude-sonnet-4-5..." />
      </div>
      <div class="form-group">
        <label>Cle API (env var)</label>
        <input id="prov-envkey" placeholder="OPENAI_API_KEY" />
      </div>
    </div>
    <div class="form-row">
      <div class="form-group">
        <label>Description</label>
        <input id="prov-desc" placeholder="Description du modele" />
      </div>
      <div class="form-group">
        <label>Base URL</label>
        <input id="prov-base-url" value="" placeholder="https://..." />
      </div>
    </div>
    ${_providerTypeFields('anthropic')}
    <div class="modal-actions">
      <button class="btn btn-outline" onclick="closeModal()">Annuler</button>
      <button class="btn btn-primary" onclick="addProvider()">Ajouter</button>
    </div>
  `);
}

async function addProvider() {
  const id = document.getElementById('prov-id').value.trim();
  const type = document.getElementById('prov-type').value;
  const model = document.getElementById('prov-model').value.trim();
  const env_key = document.getElementById('prov-envkey').value.trim();
  const description = document.getElementById('prov-desc').value.trim();
  if (!id || !model) { toast('ID et modele requis', 'error'); return; }
  const base_url = (document.getElementById('prov-base-url')?.value || '').trim();
  const body = { id, type, model, env_key, description, base_url, azure_endpoint: '', azure_deployment: '', api_version: '' };
  if (type === 'azure') {
    body.azure_endpoint = (document.getElementById('prov-azure-endpoint')?.value || '').trim();
    body.azure_deployment = (document.getElementById('prov-azure-deployment')?.value || '').trim();
    body.api_version = (document.getElementById('prov-api-version')?.value || '').trim();
  }
  try {
    await api('/api/llm/providers/provider', { method: 'POST', body });
    toast('Provider ajoute', 'success');
    closeModal();
    loadLLM();
  } catch (e) { toast(e.message, 'error'); }
}

function editProvider(id) {
  const p = llmProviders.providers[id];
  if (!p) return;
  showModal(`
    <div class="modal-header">
      <h3>Modifier : ${escHtml(id)}</h3>
      <button class="btn-icon" onclick="closeModal()">&times;</button>
    </div>
    <div class="form-row">
      <div class="form-group">
        <label>ID</label>
        <input id="prov-id" value="${escHtml(id)}" />
      </div>
      <div class="form-group">
        <label>Type</label>
        <select id="prov-type" onchange="_updateProviderTypeFields()">
          ${LLM_TYPES.map(t => `<option value="${t}" ${t === p.type ? 'selected' : ''}>${t}</option>`).join('')}
        </select>
      </div>
    </div>
    <div class="form-row">
      <div class="form-group">
        <label>Modele</label>
        <input id="prov-model" value="${escHtml(p.model)}" />
      </div>
      <div class="form-group">
        <label>Cle API (env var)</label>
        <input id="prov-envkey" value="${escHtml(p.env_key || '')}" />
      </div>
    </div>
    <div class="form-row">
      <div class="form-group">
        <label>Description</label>
        <input id="prov-desc" value="${escHtml(p.description || '')}" />
      </div>
      <div class="form-group">
        <label>Base URL</label>
        <input id="prov-base-url" value="${escHtml(p.base_url || '')}" placeholder="https://..." />
      </div>
    </div>
    ${_providerTypeFields(p.type, p)}
    <div class="modal-actions">
      <button class="btn btn-outline" onclick="closeModal()">Annuler</button>
      <button class="btn btn-primary" onclick="saveProvider('${escHtml(id)}')">Sauvegarder</button>
    </div>
  `);
}

async function saveProvider(originalId) {
  const id = document.getElementById('prov-id').value.trim();
  const type = document.getElementById('prov-type').value;
  const model = document.getElementById('prov-model').value.trim();
  const env_key = document.getElementById('prov-envkey').value.trim();
  const description = document.getElementById('prov-desc').value.trim();
  if (!id || !model) { toast('ID et modele requis', 'error'); return; }
  const base_url = (document.getElementById('prov-base-url')?.value || '').trim();
  const body = { id, type, model, env_key, description, base_url, azure_endpoint: '', azure_deployment: '', api_version: '' };
  if (type === 'azure') {
    body.azure_endpoint = (document.getElementById('prov-azure-endpoint')?.value || '').trim();
    body.azure_deployment = (document.getElementById('prov-azure-deployment')?.value || '').trim();
    body.api_version = (document.getElementById('prov-api-version')?.value || '').trim();
  }
  try {
    await api(`/api/llm/providers/provider/${originalId}`, { method: 'PUT', body });
    toast('Provider mis a jour', 'success');
    closeModal();
    loadLLM();
  } catch (e) { toast(e.message, 'error'); }
}

async function deleteProvider(id) {
  if (!(await confirmModal(`Supprimer le provider "${id}" ?`))) return;
  try {
    await api(`/api/llm/providers/provider/${id}`, { method: 'DELETE' });
    toast('Provider supprime', 'success');
    loadLLM();
  } catch (e) { toast(e.message, 'error'); }
}

// Throttling
function showAddThrottlingModal() {
  showModal(`
    <div class="modal-header">
      <h3>Ajouter une regle de throttling</h3>
      <button class="btn-icon" onclick="closeModal()">&times;</button>
    </div>
    <div class="form-group">
      <label>Cle API (env var)</label>
      <input id="throttle-key" placeholder="OPENAI_API_KEY" />
    </div>
    <div class="form-row">
      <div class="form-group">
        <label>RPM (requetes/min)</label>
        <input id="throttle-rpm" type="number" value="60" />
      </div>
      <div class="form-group">
        <label>TPM (tokens/min)</label>
        <input id="throttle-tpm" type="number" value="60000" />
      </div>
    </div>
    <div class="modal-actions">
      <button class="btn btn-outline" onclick="closeModal()">Annuler</button>
      <button class="btn btn-primary" onclick="saveThrottling()">Ajouter</button>
    </div>
  `);
}

function editThrottling(key, rpm, tpm) {
  showModal(`
    <div class="modal-header">
      <h3>Modifier throttling : ${escHtml(key)}</h3>
      <button class="btn-icon" onclick="closeModal()">&times;</button>
    </div>
    <div class="form-group">
      <label>Cle API</label>
      <input id="throttle-key" value="${escHtml(key)}" disabled style="opacity:0.5" />
    </div>
    <div class="form-row">
      <div class="form-group">
        <label>RPM (requetes/min)</label>
        <input id="throttle-rpm" type="number" value="${rpm}" />
      </div>
      <div class="form-group">
        <label>TPM (tokens/min)</label>
        <input id="throttle-tpm" type="number" value="${tpm}" />
      </div>
    </div>
    <div class="modal-actions">
      <button class="btn btn-outline" onclick="closeModal()">Annuler</button>
      <button class="btn btn-primary" onclick="saveThrottling()">Sauvegarder</button>
    </div>
  `);
}

async function saveThrottling() {
  const env_key = document.getElementById('throttle-key').value.trim();
  const rpm = parseInt(document.getElementById('throttle-rpm').value);
  const tpm = parseInt(document.getElementById('throttle-tpm').value);
  if (!env_key) { toast('Cle API requise', 'error'); return; }
  try {
    await api('/api/llm/providers/throttling', { method: 'PUT', body: { env_key, rpm, tpm } });
    toast('Throttling mis a jour', 'success');
    closeModal();
    loadLLM();
  } catch (e) { toast(e.message, 'error'); }
}

async function deleteThrottling(key) {
  if (!(await confirmModal(`Supprimer le throttling pour "${key}" ?`))) return;
  try {
    await api(`/api/llm/providers/throttling/${key}`, { method: 'DELETE' });
    toast('Throttling supprime', 'success');
    loadLLM();
  } catch (e) { toast(e.message, 'error'); }
}

// ═══════════════════════════════════════════════════
// CHAT LLM
// ═══════════════════════════════════════════════════

let chatMessages = [];

async function loadChat() {
  try {
    const data = await api('/api/llm/providers');
    const defaultId = data.default || '';
    const providers = data.providers || {};
    const sel = document.getElementById('chat-provider-select');
    sel.innerHTML = Object.entries(providers).map(([id, p]) =>
      `<option value="${escHtml(id)}" ${id === defaultId ? 'selected' : ''}>${escHtml(id)} (${escHtml(p.type)}) — ${escHtml(p.model)}</option>`
    ).join('');
  } catch (e) { /* ignore */ }
}

function renderChatMessages() {
  const container = document.getElementById('chat-messages');
  const empty = document.getElementById('chat-empty');
  if (chatMessages.length === 0) {
    if (!empty) {
      container.innerHTML = `<div class="chat-empty" id="chat-empty">
        <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="var(--text-secondary)" stroke-width="1"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>
        <p>Envoyez un message pour commencer une conversation avec le LLM par defaut.</p>
      </div>`;
    }
    return;
  }
  container.innerHTML = chatMessages.map(m => {
    if (m.role === 'user') {
      return `<div class="chat-msg user">${escHtml(m.content)}</div>`;
    } else if (m.role === 'error') {
      return `<div class="chat-msg error">${escHtml(m.content)}</div>`;
    } else {
      const html = typeof marked !== 'undefined' ? marked.parse(m.content) : escHtml(m.content);
      return `<div class="chat-msg assistant">${html}</div>`;
    }
  }).join('');
  container.scrollTop = container.scrollHeight;
}

async function sendChat() {
  const input = document.getElementById('chat-input');
  const text = input.value.trim();
  if (!text) return;

  chatMessages.push({ role: 'user', content: text });
  input.value = '';
  renderChatMessages();

  // Show typing indicator
  const container = document.getElementById('chat-messages');
  const typing = document.createElement('div');
  typing.className = 'chat-typing';
  typing.innerHTML = '<span>.</span><span>.</span><span>.</span>';
  container.appendChild(typing);
  container.scrollTop = container.scrollHeight;

  // Disable send
  const btn = document.getElementById('chat-send-btn');
  btn.disabled = true;

  try {
    const apiMessages = chatMessages.filter(m => m.role === 'user' || m.role === 'assistant');
    const providerId = document.getElementById('chat-provider-select')?.value || '';
    const result = await api('/api/chat', { method: 'POST', body: { messages: apiMessages, provider_id: providerId } });
    chatMessages.push({ role: 'assistant', content: result.content });
  } catch (e) {
    chatMessages.push({ role: 'error', content: e.message });
  }

  typing.remove();
  btn.disabled = false;
  renderChatMessages();
  input.focus();
}

function clearChat() {
  chatMessages = [];
  renderChatMessages();
}

// ═══════════════════════════════════════════════════
// SCRIPTS
// ═══════════════════════════════════════════════════
const SCRIPT_ICONS = {
  start: '<svg viewBox="0 0 24 24" fill="currentColor"><polygon points="5 3 19 12 5 21 5 3"/></svg>',
  stop: '<svg viewBox="0 0 24 24" fill="currentColor"><rect x="6" y="4" width="4" height="16"/><rect x="14" y="4" width="4" height="16"/></svg>',
  restart: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/></svg>',
  build: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z"/></svg>',
};

const SCRIPT_LABELS = {
  start: 'Demarrer',
  stop: 'Arreter',
  restart: 'Redemarrer',
  build: 'Build',
};

const SCRIPT_COLORS = {
  start: 'var(--success)',
  stop: 'var(--danger)',
  restart: 'var(--warning)',
  build: 'var(--accent)',
};

// ── Monitoring ───────────────────────────────────

let monAutoInterval = null;
let monAllLines = [];
let evtAutoInterval = null;

const EVT_COLORS = {
  agent_start: '#3b82f6', agent_complete: '#22c55e', agent_error: '#ef4444',
  agent_dispatch: '#8b5cf6', llm_call_start: '#6366f1', llm_call_end: '#6366f1',
  tool_call: '#f59e0b', pipeline_step_start: '#06b6d4', pipeline_step_end: '#06b6d4',
  human_gate_requested: '#ec4899', human_gate_responded: '#ec4899',
  phase_transition: '#f97316',
};

function showMonTab(tab) {
  document.querySelectorAll('[data-mon-tab]').forEach(t => t.classList.toggle('active', t.dataset.monTab === tab));
  document.querySelectorAll('.mon-tab-content').forEach(c => c.classList.toggle('active', c.id === `mon-tab-${tab}`));
  if (tab === 'mon-events') loadEvents();
  else if (tab === 'mon-logs') loadLogs();
  else if (tab === 'mon-containers') loadContainers();
}

function loadMonitoring() {
  const active = document.querySelector('[data-mon-tab].active');
  const tab = active ? active.dataset.monTab : 'mon-events';
  if (tab === 'mon-events') loadEvents();
  else if (tab === 'mon-logs') loadLogs();
  else loadContainers();
}

async function loadEvents() {
  const evtType = document.getElementById('evt-type-filter').value;
  const agentId = document.getElementById('evt-agent-filter').value.trim();
  const statusEl = document.getElementById('evt-gateway-status');
  const tbody = document.getElementById('evt-table-body');

  // Gateway health check
  try {
    const health = await api('/api/monitoring/gateway');
    statusEl.innerHTML = health.status === 'ok'
      ? `<span style="color:var(--success,#22c55e)">\u25CF Gateway connecte (v${health.version || '?'})</span>`
      : `<span style="color:var(--error)">\u25CF Gateway injoignable: ${health.error || '?'}</span>`;
  } catch (e) {
    statusEl.innerHTML = `<span style="color:var(--error)">\u25CF Gateway injoignable</span>`;
  }

  // Load events
  try {
    let url = '/api/monitoring/events?n=200';
    if (evtType) url += `&event_type=${evtType}`;
    if (agentId) url += `&agent_id=${agentId}`;
    const data = await api(url);
    const events = (data.events || []).reverse();

    if (!events.length) {
      tbody.innerHTML = '<tr><td colspan="4" style="color:var(--text-secondary);text-align:center">Aucun event</td></tr>';
      return;
    }

    tbody.innerHTML = events.map(e => {
      const color = EVT_COLORS[e.event] || 'var(--text-secondary)';
      const ts = e.timestamp ? e.timestamp.replace('T', ' ').substring(0, 19) : '';
      const dataStr = Object.entries(e.data || {})
        .filter(([k, v]) => v !== '' && v !== 0 && v !== null)
        .map(([k, v]) => `<span style="color:var(--text-secondary)">${escHtml(k)}=</span>${escHtml(String(v).substring(0, 80))}`)
        .join(' ');
      return `<tr>
        <td style="font-size:0.7rem;font-family:monospace;white-space:nowrap">${escHtml(ts)}</td>
        <td><span style="color:${color};font-weight:500;font-size:0.8rem">${escHtml(e.event)}</span></td>
        <td style="font-size:0.8rem">${escHtml(e.agent_id || '-')}</td>
        <td style="font-size:0.7rem;word-break:break-all">${dataStr || '-'}</td>
      </tr>`;
    }).join('');
  } catch (e) {
    tbody.innerHTML = `<tr><td colspan="4" style="color:var(--error)">Erreur: ${escHtml(e.message)}</td></tr>`;
  }
}

function toggleEventsAutoRefresh() {
  const btn = document.getElementById('evt-auto-btn');
  if (evtAutoInterval) {
    clearInterval(evtAutoInterval);
    evtAutoInterval = null;
    btn.textContent = 'Auto OFF';
    btn.style.background = '';
    btn.style.color = '';
  } else {
    evtAutoInterval = setInterval(loadEvents, 3000);
    btn.textContent = 'Auto 3s';
    btn.style.background = 'var(--success, #22c55e)';
    btn.style.color = '#fff';
  }
}

async function loadLogs() {
  const service = document.getElementById('mon-service').value;
  const lines = document.getElementById('mon-lines').value;
  try {
    const data = await api(`/api/monitoring/logs?service=${service}&lines=${lines}`);
    monAllLines = data.lines || [];
    filterLogs();
  } catch (e) {
    document.getElementById('mon-logs-output').textContent = 'Erreur: ' + e.message;
  }
}

function filterLogs() {
  const filter = (document.getElementById('mon-filter').value || '').toLowerCase();
  const out = document.getElementById('mon-logs-output');
  const filtered = filter ? monAllLines.filter(l => l.toLowerCase().includes(filter)) : monAllLines;
  out.innerHTML = filtered.map(l => {
    let cls = '';
    if (/\bERROR\b/i.test(l)) cls = 'log-error';
    else if (/\bWARN(ING)?\b/i.test(l)) cls = 'log-warn';
    else if (/\bDEBUG\b/i.test(l)) cls = 'log-debug';
    return `<div class="${cls}">${escHtml(l)}</div>`;
  }).join('') || '<div style="color:var(--text-secondary)">Aucun log</div>';
  if (document.getElementById('mon-autoscroll').checked) {
    out.scrollTop = out.scrollHeight;
  }
}

function toggleAutoRefresh() {
  const btn = document.getElementById('mon-auto-btn');
  if (monAutoInterval) {
    clearInterval(monAutoInterval);
    monAutoInterval = null;
    btn.textContent = 'Auto OFF';
    btn.style.background = '';
  } else {
    monAutoInterval = setInterval(loadLogs, 5000);
    btn.textContent = 'Auto 5s';
    btn.style.background = 'var(--success, #22c55e)';
    btn.style.color = '#fff';
  }
}

function formatPorts(portsStr) {
  if (!portsStr) return '';
  const host = window.location.hostname;
  return escHtml(portsStr).replace(/0\.0\.0\.0:(\d+)/g, (match, port) => {
    return `<a href="http://${host}:${port}" target="_blank" rel="noopener" style="color:var(--accent)">${host}:${port}</a>`;
  });
}

async function loadContainers() {
  const el = document.getElementById('mon-containers-list');
  try {
    const data = await api('/api/monitoring/containers');
    const containers = data.containers || [];
    if (!containers.length) { el.innerHTML = '<p style="color:var(--text-secondary)">Aucun container detecte</p>'; return; }
    el.innerHTML = `<table class="env-table" style="width:100%">
      <thead><tr><th>Container</th><th>Image</th><th>Etat</th><th>Status</th><th>Ports</th><th>Actions</th></tr></thead>
      <tbody>${containers.map(c => {
        const running = c.state === 'running';
        const dot = running ? '🟢' : '🔴';
        const isManaged = ['langgraph-api','langgraph-discord','langgraph-mail','langgraph-admin','langgraph-hitl','langgraph-outline','langgraph-minio'].includes(c.name);
        const actions = isManaged ? `
          <button class="btn btn-outline btn-sm" onclick="containerAction('${c.name}','restart')" style="font-size:0.7rem">Restart</button>
          ${running
            ? `<button class="btn btn-outline btn-sm" onclick="containerAction('${c.name}','stop')" style="font-size:0.7rem;color:var(--error)">Stop</button>`
            : `<button class="btn btn-outline btn-sm" onclick="containerAction('${c.name}','start')" style="font-size:0.7rem;color:var(--success,#22c55e)">Start</button>`
          }` : '';
        return `<tr>
          <td><strong>${dot} ${escHtml(c.name)}</strong></td>
          <td style="font-size:0.75rem;color:var(--text-secondary)">${escHtml(c.image)}</td>
          <td>${escHtml(c.state)}</td>
          <td style="font-size:0.75rem">${escHtml(c.status)}</td>
          <td style="font-size:0.75rem;color:var(--text-secondary)">${formatPorts(c.ports)}</td>
          <td>${actions}</td>
        </tr>`;
      }).join('')}</tbody></table>`;
  } catch (e) {
    el.innerHTML = `<p style="color:var(--error)">Erreur: ${escHtml(e.message)}</p>`;
  }
}

async function containerAction(name, action) {
  if (!confirm(`${action} le container ${name} ?`)) return;
  try {
    const data = await api(`/api/monitoring/container/${name}/${action}`, { method: 'POST' });
    showToast(data.message, 'success');
    setTimeout(loadContainers, 1500);
  } catch (e) {
    showToast('Erreur: ' + e.message, 'error');
  }
}

function loadScripts() {
  const grid = document.getElementById('scripts-grid');
  grid.innerHTML = ['start', 'stop', 'restart', 'build'].map(name => `
    <div class="script-btn" onclick="runScript('${name}')" style="border-color:${SCRIPT_COLORS[name]}20">
      <div style="color:${SCRIPT_COLORS[name]}">${SCRIPT_ICONS[name]}</div>
      <span>${SCRIPT_LABELS[name]}</span>
      <small>${name}.sh</small>
    </div>
  `).join('');
}

async function runScript(name) {
  const output = document.getElementById('script-output');
  output.textContent = `Execution de ${name}.sh...\n`;
  output.style.color = '#f59e0b';
  try {
    const data = await api('/api/scripts/run', { method: 'POST', body: { name } });
    output.style.color = data.code === 0 ? '#22c55e' : '#ef4444';
    output.textContent = (data.stdout || '') + (data.stderr ? '\n--- STDERR ---\n' + data.stderr : '');
    if (data.code === 0) toast(`${name}.sh termine`, 'success');
    else toast(`${name}.sh erreur (code ${data.code})`, 'error');
  } catch (e) {
    output.style.color = '#ef4444';
    output.textContent = `Erreur: ${e.message}`;
    toast(e.message, 'error');
  }
}

// ═══════════════════════════════════════════════════
// GIT (factorized: works for both configs + shared)
// ═══════════════════════════════════════════════════

// ── Git Service (remote repo creation/fetch) ────

const GIT_SERVICE_URLS = {
  github:    'https://api.github.com',
  gitlab:    'https://gitlab.com',
  gitea:     '',
  forgejo:   '',
  bitbucket: 'https://api.bitbucket.org/2.0',
};

// ── Factorized Git Service (works for both scopes) ──
// scope = 'shared' or 'configs'
// Each scope has HTML elements with a prefix: shared→'gs', configs→'cgs'
// Each scope maps to a git prefix: shared→'tpl-git', configs→'cfg-git'

const GIT_SVC = {
  shared:  { el: 'gs',  gitPrefix: 'tpl-git', repoKey: 'shared' },
  configs: { el: 'cgs', gitPrefix: 'cfg-git', repoKey: 'configs' },
};
const GIT_REPOS = { 'cfg-git': 'configs', 'tpl-git': 'shared' };
const GIT_LABELS = { configs: 'Configs', shared: 'Shared (Templates)' };

const _gitSvcInited = { shared: false, configs: false };

function _checkGitSvcBtns(scope) {
  const p = GIT_SVC[scope].el;
  const svc = document.getElementById(`${p}-service`).value;
  const url = document.getElementById(`${p}-url`).value.trim();
  const token = document.getElementById(`${p}-token`).value.trim();
  const repo = document.getElementById(`${p}-repo-name`).value.trim();
  const ready = svc && url && token && repo;
  const initBtn = document.getElementById(`${p}-btn-init`);
  const fetchBtn = document.getElementById(`${p}-btn-fetch`);
  const commitBtn = document.getElementById(`${p}-btn-commit`);
  const resetBtn = document.getElementById(`${p}-btn-reset`);
  if (!ready) {
    initBtn.style.display = 'none';
    fetchBtn.style.display = 'none';
    commitBtn.style.display = 'none';
    if (resetBtn) resetBtn.style.display = 'none';
  } else if (_gitSvcInited[scope]) {
    initBtn.style.display = 'none';
    fetchBtn.style.display = '';
    commitBtn.style.display = '';
    if (resetBtn) resetBtn.style.display = '';
    fetchBtn.disabled = false;
    commitBtn.disabled = false;
    if (resetBtn) resetBtn.disabled = false;
  } else {
    initBtn.style.display = '';
    fetchBtn.style.display = 'none';
    commitBtn.style.display = 'none';
    if (resetBtn) resetBtn.style.display = 'none';
    initBtn.disabled = false;
  }
}

function _onGitSvcChange(scope) {
  const p = GIT_SVC[scope].el;
  const svc = document.getElementById(`${p}-service`).value;
  const urlField = document.getElementById(`${p}-url`);
  if (svc && GIT_SERVICE_URLS[svc] !== undefined) {
    urlField.value = GIT_SERVICE_URLS[svc];
    urlField.placeholder = GIT_SERVICE_URLS[svc] || 'https://votre-instance.com';
  }
  _checkGitSvcBtns(scope);
}

async function _saveGitSvcConfig(scope) {
  const p = GIT_SVC[scope].el;
  await api(`/api/git-svc/${scope}/config`, { method: 'PUT', body: {
    service: document.getElementById(`${p}-service`).value,
    url: document.getElementById(`${p}-url`).value.trim(),
    login: document.getElementById(`${p}-login`).value.trim(),
    token: document.getElementById(`${p}-token`).value.trim(),
    repo_name: document.getElementById(`${p}-repo-name`).value.trim(),
  }});
}

async function loadGitSvcConfig(scope) {
  const p = GIT_SVC[scope].el;
  try {
    const cfg = await api(`/api/git-svc/${scope}/config`);
    document.getElementById(`${p}-service`).value = cfg.service || '';
    document.getElementById(`${p}-url`).value = cfg.url || '';
    document.getElementById(`${p}-login`).value = cfg.login || '';
    document.getElementById(`${p}-token`).value = cfg.token || '';
    document.getElementById(`${p}-repo-name`).value = cfg.repo_name || '';
    _checkGitSvcBtns(scope);
  } catch {}
}

function _buildRepoUrl(scope) {
  const p = GIT_SVC[scope].el;
  const svc = document.getElementById(`${p}-service`).value;
  const baseUrl = document.getElementById(`${p}-url`).value.trim();
  const login = document.getElementById(`${p}-login`).value.trim();
  const repoName = document.getElementById(`${p}-repo-name`).value.trim();
  if (svc === 'github') return `https://github.com/${login}/${repoName}.git`;
  if (svc === 'gitlab') return `${baseUrl.replace('/api/v4','').replace('api.','').replace('/api','') || 'https://gitlab.com'}/${login}/${repoName}.git`;
  if (svc === 'bitbucket') return `https://bitbucket.org/${login}/${repoName}.git`;
  return `${baseUrl.replace(/\/api\/v1$/,'').replace(/\/api$/,'')}/${login}/${repoName}.git`;
}

async function gitSvcInit(scope) {
  const { el: p, gitPrefix, repoKey } = GIT_SVC[scope];
  const repoName = document.getElementById(`${p}-repo-name`).value.trim();
  if (!repoName) { toast('Nom du depot requis', 'error'); return; }
  const btn = document.getElementById(`${p}-btn-init`);
  btn.disabled = true; btn.innerHTML = '<span class="spinner"></span> Verification...';
  try {
    await _saveGitSvcConfig(scope);
    const check = await api(`/api/git-svc/${scope}/check-repo`, { method: 'POST', body: { repo_name: repoName } });
    if (check.exists) {
      btn.innerHTML = '<span class="spinner"></span> Clonage...';
      let repoUrl = check.clone_url || _buildRepoUrl(scope);
      const result = await api(`/api/git-svc/${scope}/fetch-repo`, { method: 'POST', body: { repo_url: repoUrl } });
      toast(result.message || (result.ok ? 'Depot clone avec succes' : 'Erreur'), result.ok ? 'success' : 'error');
      loadRepoGit(gitPrefix);
    } else {
      const yes = await confirmModal('Le depot distant n\'existe pas.\n\nVoulez-vous le creer ?');
      if (!yes) return;
      btn.innerHTML = '<span class="spinner"></span> Creation...';
      const result = await api(`/api/git-svc/${scope}/create-repo`, { method: 'POST', body: { repo_name: repoName } });
      if (!result.ok) { toast(result.message || 'Erreur creation', 'error'); return; }
      toast(result.message || 'Depot cree', 'success');
      const init = await api(`/api/git/${repoKey}/init`, { method: 'POST' });
      if (init.ok) toast('Depot local initialise', 'success');
      loadRepoGit(gitPrefix);
    }
  } catch (e) { toast(e.message, 'error'); }
  finally { btn.disabled = false; btn.textContent = 'Init'; _checkGitSvcBtns(scope); }
}

async function gitSvcFetch(scope) {
  const { el: p, gitPrefix, repoKey } = GIT_SVC[scope];
  const repoName = document.getElementById(`${p}-repo-name`).value.trim();
  if (!repoName) { toast('Nom du depot requis', 'error'); return; }
  const btn = document.getElementById(`${p}-btn-fetch`);
  btn.disabled = true; btn.innerHTML = '<span class="spinner"></span> Fetch...';
  try {
    await _saveGitSvcConfig(scope);
    const repoUrl = _buildRepoUrl(scope);
    const result = await api(`/api/git-svc/${scope}/fetch-repo`, { method: 'POST', body: { repo_url: repoUrl } });
    toast(result.message || (result.ok ? 'Fetch OK' : 'Erreur'), result.ok ? 'success' : 'error');
    loadRepoGit(gitPrefix);
  } catch (e) { toast(e.message, 'error'); }
  finally { btn.disabled = false; btn.textContent = 'Fetch'; _checkGitSvcBtns(scope); }
}

async function gitSvcCommit(scope) {
  const { el: p, gitPrefix, repoKey } = GIT_SVC[scope];
  const btn = document.getElementById(`${p}-btn-commit`);
  btn.disabled = true; btn.innerHTML = '<span class="spinner"></span> Commit...';
  try {
    await _saveGitSvcConfig(scope);
    await api(`/api/git-svc/${scope}/sync-repo-config`, { method: 'POST' });
    const data = await api(`/api/git/${repoKey}/commit`, { method: 'POST', body: { message: 'Mise a jour depuis le dashboard' } });
    toast(data.message || (data.ok ? 'Commit OK' : 'Erreur'), data.ok ? 'success' : 'error');
    loadRepoGit(gitPrefix);
  } catch (e) { toast(e.message, 'error'); }
  finally { btn.disabled = false; btn.textContent = 'Commit'; _checkGitSvcBtns(scope); }
}

async function gitSvcReset(scope) {
  const { el: p, gitPrefix, repoKey } = GIT_SVC[scope];
  const status = await api(`/api/git/${repoKey}/status`);
  if (status.status && status.status !== '(aucun changement)' && status.status.trim()) {
    if (!(await confirmModal('Des modifications sont en cours et non commitees.\nToutes les modifications seront perdues.\n\nVoulez-vous continuer ?'))) return;
  } else {
    if (!(await confirmModal('Reset sur la version distante ?\nToutes les modifications locales seront ecrasees.'))) return;
  }
  const btn = document.getElementById(`${p}-btn-reset`);
  btn.disabled = true; btn.innerHTML = '<span class="spinner"></span> Reset...';
  try {
    const data = await api(`/api/git/${repoKey}/reset`, { method: 'POST' });
    toast(data.message || 'Reset effectue', data.ok ? 'success' : 'error');
    loadRepoGit(gitPrefix);
  } catch (e) { toast(e.message, 'error'); }
  finally { btn.disabled = false; btn.textContent = 'Reset'; _checkGitSvcBtns(scope); }
}

// Convenience wrappers for HTML onclick
function saveGitServiceConfig() { _saveGitSvcConfig('shared'); }
function loadGitServiceConfig() { loadGitSvcConfig('shared'); }

async function loadRepoGit(prefix) {
  const repoKey = GIT_REPOS[prefix];
  const scope = repoKey; // 'shared' or 'configs'
  try {
    const [status, cfg] = await Promise.all([
      api(`/api/git/${repoKey}/status`),
      api(`/api/git/repo-config/${repoKey}`),
    ]);
    document.getElementById(`${prefix}-path`).value = cfg.path || '';
    document.getElementById(`${prefix}-login`).value = cfg.login || '';
    document.getElementById(`${prefix}-password`).value = cfg.password || '';
    const inited = status.initialized;
    document.getElementById(`${prefix}-branch`).textContent = inited ? (status.branch || 'inconnu') : 'Non initialise';
    document.getElementById(`${prefix}-status`).textContent = inited ? (status.status || '(aucun changement)') : 'Git non initialise.';
    _gitSvcInited[scope] = inited;
    _checkGitSvcBtns(scope);
    if (inited) loadRepoGitCommits(prefix);
  } catch (e) { toast(e.message, 'error'); }
}

function loadCfgGit() { loadGitSvcConfig('configs'); loadRepoGit('cfg-git'); }

function loadTplGit() { loadGitServiceConfig(); loadRepoGit('tpl-git'); }

async function saveRepoGitConfig(prefix) {
  const repoKey = GIT_REPOS[prefix];
  try {
    await api(`/api/git/repo-config/${repoKey}`, {
      method: 'PUT',
      body: {
        path: document.getElementById(`${prefix}-path`).value.trim(),
        login: document.getElementById(`${prefix}-login`).value.trim(),
        password: document.getElementById(`${prefix}-password`).value.trim(),
      },
    });
    toast(`Configuration Git ${GIT_LABELS[repoKey]} enregistree`, 'success');
    loadRepoGit(prefix);
  } catch (e) { toast(e.message, 'error'); }
}

async function repoGitInit(prefix) {
  const repoKey = GIT_REPOS[prefix];
  try {
    const data = await api(`/api/git/${repoKey}/init`, { method: 'POST' });
    toast(data.message || (data.ok ? 'Initialise' : 'Erreur'), data.ok ? 'success' : 'error');
    loadRepoGit(prefix);
  } catch (e) { toast(e.message, 'error'); }
}

async function repoGitPull(prefix) {
  const repoKey = GIT_REPOS[prefix];
  try {
    const data = await api(`/api/git/${repoKey}/pull`, { method: 'POST', body: {} });
    if (!data.ok && data.uncommitted) {
      const yes = await confirmModal(data.message + '\n\nVoulez-vous continuer et ecraser ces modifications ?');
      if (!yes) return;
      const d2 = await api(`/api/git/${repoKey}/pull`, { method: 'POST', body: { force: true } });
      toast(d2.message || 'Erreur', d2.ok ? 'success' : 'error');
      loadRepoGit(prefix);
      return;
    }
    toast(data.message || 'Fetch effectue', data.ok ? 'success' : 'error');
    loadRepoGit(prefix);
  } catch (e) { toast(e.message, 'error'); }
}

let _gitCommitRepoKey = '';
let _gitCommitPrefix = '';
function showGitCommitModal(prefix) {
  _gitCommitPrefix = prefix;
  _gitCommitRepoKey = GIT_REPOS[prefix];
  const label = GIT_LABELS[_gitCommitRepoKey];
  showModal(`
    <div class="modal-header">
      <h3>Commit — ${label}</h3>
      <button class="btn-icon" onclick="closeModal()">&times;</button>
    </div>
    <p style="font-size:0.8rem;color:var(--text-secondary);margin-bottom:1rem">Commit et push du depot ${label} vers le depot distant.</p>
    <div class="form-group">
      <label>Message de commit</label>
      <input id="git-commit-msg" placeholder="Mise a jour configuration" />
    </div>
    <div class="modal-actions">
      <button class="btn btn-outline" onclick="closeModal()">Annuler</button>
      <button class="btn btn-success" onclick="gitCommit()">Commit &amp; Push</button>
    </div>
  `);
}

async function gitCommit() {
  const msg = document.getElementById('git-commit-msg').value.trim();
  if (!msg) { toast('Message requis', 'error'); return; }
  closeModal();
  try {
    const res = await fetch(`/api/git/${_gitCommitRepoKey}/commit`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: msg }),
    });
    const data = await res.json();
    console.log('gitCommit response:', res.status, data);
    if (res.ok && data.ok) {
      toast(data.message, 'success');
      loadRepoGit(_gitCommitPrefix);
      return;
    }
    // Push failed — propose force push
    const errMsg = data.message || data.detail || 'Push echoue';
    const yes = await confirmModal(errMsg + '\n\nVoulez-vous forcer l\'envoi et ecraser la version distante ?');
    if (yes) {
      const r2 = await fetch(`/api/git/${_gitCommitRepoKey}/commit`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: msg, force: true }),
      });
      const d2 = await r2.json();
      toast(d2.message || 'Erreur', d2.ok ? 'success' : 'error');
      loadRepoGit(_gitCommitPrefix);
    }
  } catch (e) { toast(e.message, 'error'); }
}

async function repoGitPushOnly(prefix) {
  const repoKey = GIT_REPOS[prefix];
  try {
    const data = await api(`/api/git/${repoKey}/push`, { method: 'POST', body: {} });
    if (data.ok) {
      toast(data.message, 'success');
      loadRepoGit(prefix);
      return;
    }
    const yes = await confirmModal(data.message + '\n\nVoulez-vous forcer l\'envoi et ecraser la version distante ?');
    if (yes) {
      const r2 = await api(`/api/git/${repoKey}/push`, { method: 'POST', body: { force: true } });
      toast(r2.message || 'Erreur', r2.ok ? 'success' : 'error');
      loadRepoGit(prefix);
    }
  } catch (e) { toast(e.message, 'error'); }
}

async function repoGitResetLocal(prefix) {
  if (!(await confirmModal('Supprimer tous les commits locaux non pushes ?\nLe depot local sera resynchronise avec le remote.'))) return;
  const repoKey = GIT_REPOS[prefix];
  try {
    const data = await api(`/api/git/${repoKey}/reset-to-remote`, { method: 'POST' });
    toast(data.message || 'Reset effectue', data.ok ? 'success' : 'error');
    loadRepoGit(prefix);
  } catch (e) { toast(e.message, 'error'); }
}

async function loadRepoGitCommits(prefix) {
  const repoKey = GIT_REPOS[prefix];
  const wrap = document.getElementById(`${prefix}-commits`);
  if (!wrap) return;
  try {
    const data = await api(`/api/git/${repoKey}/commits`);
    const commits = data.commits || [];
    if (!commits.length) {
      wrap.innerHTML = '<p style="color:var(--text-secondary);font-size:0.8rem;padding:0.5rem">Aucun commit.</p>';
      return;
    }
    const rows = commits.map(c => {
      const tags = c.tags.map(t => `<span class="commit-tag">${escHtml(t)}</span>`).join('');
      const dateStr = c.date ? c.date.substring(0, 16).replace('T', ' ') : '';
      return `<tr>
        <td class="commit-date">${escHtml(dateStr)}</td>
        <td class="commit-hash">${escHtml(c.short)}</td>
        <td>${tags}</td>
        <td>${escHtml(c.subject)}</td>
        <td style="white-space:nowrap">
          <button class="btn-view" onclick="repoGitView('${prefix}','${c.hash}')" title="Voir les fichiers">View</button>
          <button class="btn-revert" onclick="repoGitCheckout('${prefix}','${c.hash}')" title="Revenir a cette version">Restaurer</button>
        </td>
      </tr>`;
    }).join('');
    wrap.innerHTML = `<table class="commits-table">
      <thead><tr><th>Date</th><th>ID</th><th>Tag</th><th>Message</th><th></th></tr></thead>
      <tbody>${rows}</tbody>
    </table>`;
  } catch (e) {
    wrap.innerHTML = `<p style="color:#ef4444;font-size:0.8rem;padding:0.5rem">${escHtml(e.message)}</p>`;
  }
}

async function repoGitCheckout(prefix, hash) {
  const repoKey = GIT_REPOS[prefix];
  try {
    // Check for uncommitted changes first
    const status = await api(`/api/git/${repoKey}/status`);
    if (status.status && status.status !== '(aucun changement)' && status.status.trim()) {
      if (!(await confirmModal('Des modifications sont en cours et non commitees.\nToutes les modifications en cours vont etre perdues.\n\nVoulez-vous continuer ?'))) return;
    } else {
      if (!(await confirmModal('Revenir a la version ' + hash.substring(0, 7) + ' ?'))) return;
    }
    const data = await api(`/api/git/${repoKey}/checkout/${hash}`, { method: 'POST' });
    toast(data.message || 'Version restauree', data.ok ? 'success' : 'error');
    loadRepoGit(prefix);
  } catch (e) { toast(e.message, 'error'); }
}

// ── Version file browser ─────────────────────────
let _vbSessionId = null;

async function repoGitView(prefix, hash) {
  const repoKey = GIT_REPOS[prefix];
  const overlay = document.getElementById('modal-version-browser');
  const titleEl = document.getElementById('vb-title');
  const treeEl = document.getElementById('vb-tree');
  const fileEl = document.getElementById('vb-file-content');
  const pathEl = document.getElementById('vb-file-path');
  titleEl.textContent = 'Chargement...';
  treeEl.innerHTML = '<p style="padding:1rem;color:var(--text-secondary)">Clone en cours...</p>';
  fileEl.textContent = '';
  pathEl.textContent = '';
  overlay.classList.add('active');
  try {
    const data = await api(`/api/git/${repoKey}/version-browse/${hash}`, { method: 'POST' });
    if (!data.ok) { toast(data.message || 'Erreur', 'error'); overlay.classList.remove('active'); return; }
    _vbSessionId = data.session_id;
    titleEl.textContent = 'Version ' + hash.substring(0, 7);
    await _vbLoadTree('');
  } catch (e) {
    toast(e.message, 'error');
    overlay.classList.remove('active');
  }
}

async function _vbLoadTree(path) {
  const treeEl = document.getElementById('vb-tree');
  try {
    const data = await api(`/api/git/version-browse/${_vbSessionId}/tree?path=${encodeURIComponent(path)}`);
    let html = '';
    if (path) {
      const parent = path.includes('/') ? path.substring(0, path.lastIndexOf('/')) : '';
      html += `<div class="vb-item vb-dir" onclick="_vbLoadTree('${parent}')"><span class="vb-icon">&#x2190;</span> ..</div>`;
    }
    for (const item of (data.items || [])) {
      if (item.type === 'dir') {
        html += `<div class="vb-item vb-dir" onclick="_vbLoadTree('${item.path}')"><span class="vb-icon">&#x1F4C1;</span> ${escHtml(item.name)}</div>`;
      } else {
        html += `<div class="vb-item vb-file" onclick="_vbLoadFile('${item.path}')"><span class="vb-icon">&#x1F4C4;</span> ${escHtml(item.name)}</div>`;
      }
    }
    if (!data.items || !data.items.length) html = '<p style="padding:1rem;color:var(--text-secondary)">Repertoire vide</p>';
    treeEl.innerHTML = html;
  } catch (e) {
    treeEl.innerHTML = `<p style="padding:1rem;color:#ef4444">${escHtml(e.message)}</p>`;
  }
}

async function _vbLoadFile(path) {
  const fileEl = document.getElementById('vb-file-content');
  const pathEl = document.getElementById('vb-file-path');
  pathEl.textContent = path;
  fileEl.textContent = 'Chargement...';
  // highlight selected file
  document.querySelectorAll('.vb-item').forEach(el => el.classList.remove('selected'));
  const items = document.querySelectorAll('.vb-item.vb-file');
  items.forEach(el => { if (el.textContent.trim().endsWith(path.split('/').pop())) el.classList.add('selected'); });
  try {
    const data = await api(`/api/git/version-browse/${_vbSessionId}/file?path=${encodeURIComponent(path)}`);
    fileEl.textContent = data.content || '(vide)';
  } catch (e) {
    fileEl.textContent = 'Erreur: ' + e.message;
  }
}

async function closeVersionBrowser() {
  const overlay = document.getElementById('modal-version-browser');
  overlay.classList.remove('active');
  if (_vbSessionId) {
    try { await api(`/api/git/version-browse/${_vbSessionId}/close`, { method: 'POST' }); } catch (_) {}
    _vbSessionId = null;
  }
  document.getElementById('vb-file-content').textContent = '';
  document.getElementById('vb-tree').innerHTML = '';
}

// ═══════════════════════════════════════════════════
// TEAMS
// ═══════════════════════════════════════════════════
let teamsData = [];
let templatesData = [];

async function importArchive(type, input) {
  const file = input.files[0];
  if (!file) return;
  if (!confirm(`Importer "${file.name}" ?\n\nTous les fichiers existants seront remplaces. Les fichiers absents de l'archive seront supprimes.`)) {
    input.value = '';
    return;
  }
  const fd = new FormData();
  fd.append('file', file);
  try {
    const r = await fetch(`/api/import/${type}`, { method: 'POST', body: fd });
    const j = await r.json();
    if (!r.ok) throw new Error(j.detail || 'Erreur import');
    showToast(j.message || 'Import termine', 'success');
    if (type === 'configs') loadTeams();
    else loadTemplates();
  } catch (e) {
    showToast('Erreur import : ' + e.message, 'error');
  }
  input.value = '';
}

async function loadTeams() {
  // Load active config sub-tab
  const active = document.querySelector('[data-cfg-tab].active');
  const tab = active ? active.getAttribute('data-cfg-tab') : 'cfg-llm';
  showConfigTab(tab);
}

function toggleTeamBlock(headerEl) {
  const block = headerEl.closest('.team-block');
  block.classList.toggle('collapsed');
}

function renderTeams() {
  const grid = document.getElementById('teams-grid');
  if (!teamsData.length) {
    grid.innerHTML = '<p style="color:var(--text-secondary);padding:1rem">Aucune equipe configuree.</p>';
    return;
  }
  grid.innerHTML = teamsData.map((t, tIdx) => {
    const agentEntries = Object.entries(t.agents || {});
    const mcpAccess = t.mcp_access || {};
    const dir = t.directory || t.id;

    const orchId = t.orchestrator || '';
    const agentCards = agentEntries.map(([aid, a]) => {
      const mcpList = mcpAccess[aid] || [];
      const isOrch = aid === orchId;
      return `<div class="agent-card${isOrch ? ' agent-orchestrator' : ''}" style="cursor:pointer">
        <div class="agent-card-header">
          <div onclick="editCfgAgent('${escHtml(dir)}','${escHtml(aid)}')" style="flex:1;cursor:pointer">
            <h4>${isOrch ? '<span class="orch-badge" title="Orchestrateur">&#9733;</span> ' : ''}${escHtml(a.name)}</h4>
            <code style="font-size:0.75rem;color:var(--text-secondary)">${escHtml(aid)}</code>
          </div>
          <button class="btn-icon danger" onclick="event.stopPropagation();deleteCfgAgent('${escHtml(dir)}','${escHtml(aid)}')" title="Supprimer">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>
          </button>
        </div>
        <div class="agent-meta" onclick="editCfgAgent('${escHtml(dir)}','${escHtml(aid)}')">
          ${a.temperature != null ? `<span class="tag tag-blue">temp: ${a.temperature}</span>` : ''}
          ${a.max_tokens != null ? `<span class="tag tag-blue">tokens: ${a.max_tokens}</span>` : ''}
          ${a.llm || a.model ? `<span class="tag tag-yellow">${escHtml(a.llm || a.model)}</span>` : ''}
          ${a.type ? `<span class="tag tag-gray">${escHtml(a.type)}</span>` : ''}
          ${a.delivers_docs ? '<span class="tag tag-purple">Documentation</span>' : ''}
          ${a.delivers_code ? '<span class="tag tag-purple">Code</span>' : ''}
        </div>
        ${mcpList.length ? `<div class="agent-meta">
          ${mcpList.map(m => `<span class="tag tag-green">${escHtml(m)}</span>`).join('')}
        </div>` : ''}
      </div>`;
    }).join('');

    return `<div class="team-block">
      <div class="team-block-header">
        <div style="display:flex;align-items:center;gap:0.5rem;flex:1;cursor:pointer" onclick="toggleTeamBlock(this)">
          <svg class="team-chevron" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="6 9 12 15 18 9"/></svg>
          <h3 style="margin:0">
            ${escHtml(t.name || t.id)}
            <span style="font-weight:400;font-size:0.75rem;color:var(--text-secondary)">${escHtml(t.id)}</span>
            <code style="font-weight:400;font-size:0.7rem;color:var(--text-secondary)">config/Teams/${escHtml(dir)}/</code>
          </h3>
          <span class="tag tag-blue" style="margin-left:0.5rem">${agentEntries.length} agent${agentEntries.length > 1 ? 's' : ''}</span>
        </div>
        <div style="display:flex;gap:0.5rem">
          <button class="btn-icon" onclick="event.stopPropagation();editTeam(${tIdx})" title="Modifier l'equipe" style="opacity:0.5">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M17 3a2.83 2.83 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5Z"/><path d="m15 5 4 4"/></svg>
          </button>
          <button class="btn btn-primary btn-sm" onclick="showAddCfgAgentModal('${escHtml(dir)}')">+ Agent</button>
          <button class="btn btn-outline btn-sm" id="btn-wf-cfg-${escHtml(dir)}" onclick="showCfgWorkflow('${escHtml(dir)}')">Workflow</button>
          <button class="btn btn-outline btn-sm" onclick="showCfgRawRegistry('${escHtml(dir)}')">Raw</button>
          <button class="btn btn-outline btn-sm" style="color:var(--error)" onclick="deleteTeam('${escHtml(t.id)}')">Suppr</button>
        </div>
      </div>
      <div class="team-block-body">
        ${t.description ? `<p style="color:var(--text-secondary);margin:0 0 0.5rem 0;font-size:0.85rem">${escHtml(t.description)}</p>` : ''}
        <div class="team-block-meta">
          ${(t.discord_channels || []).map(c => `<span class="tag tag-green">#${escHtml(c)}</span>`).join('')}
        </div>
        <div class="agents-grid">
          ${agentEntries.length ? agentCards : '<p style="color:var(--text-secondary);padding:0.5rem">Aucun agent dans cette equipe. Cliquez sur "+ Agent" pour en ajouter.</p>'}
        </div>
      </div>
    </div>`;
  }).join('');
  // Validate workflows after render
  teamsData.forEach(t => {
    const dir = t.directory || t.id;
    _wfCheckStatus(dir, '/api/workflow', '/api/agents/registry', 'cfg');
  });
}

async function showAddCfgAgentModal(dir) {
  let sharedList = [], hasOrch = false;
  try {
    const d = await api('/api/shared-agents');
    sharedList = d.agents || [];
  } catch { /* ignore */ }
  try {
    const reg = await api(`/api/agents/registry/${encodeURIComponent(dir)}`);
    hasOrch = Object.values(reg.agents || reg || {}).some(a => a.type === 'orchestrator');
  } catch { /* ignore */ }
  const sortedSharedCfg = sharedList.slice().sort((a, b) => (a.name || a.id).localeCompare(b.name || b.id, 'fr'));
  showModal(`
    <div class="modal-header">
      <h3>Ajouter un agent</h3>
      <button class="btn-icon" onclick="closeModal()">&times;</button>
    </div>
    <div class="form-group">
      <label>Agent (catalogue)</label>
      <div style="position:relative">
        <input id="cfg-agent-filter" placeholder="Filtrer / choisir un agent..." autocomplete="off"
          oninput="_filterCfgAgentDropdown()" onfocus="_openCfgAgentDropdown()" />
        <input type="hidden" id="cfg-agent-new-id" />
        <div id="cfg-agent-dropdown" class="sa-dropdown" style="display:none">
          ${sortedSharedCfg.map(a => `<div class="sa-dropdown-item" data-id="${escHtml(a.id)}" data-name="${escHtml(a.name || a.id)}" onclick="_pickCfgAgent(this)">${escHtml(a.name || a.id)} <span style="color:var(--text-secondary);font-size:0.8rem">(${escHtml(a.id)})</span></div>`).join('')}
        </div>
      </div>
      ${!sharedList.length ? '<p style="color:var(--text-secondary);font-size:0.8rem;margin-top:0.25rem">Aucun agent dans le catalogue. Creez-en d\'abord dans Templates &gt; Agents.</p>' : ''}
    </div>
    <div class="form-group">
      <label>Type</label>
      <select id="cfg-agent-new-type">
        <option value="single" selected>Single</option>
        <option value="pipeline">Pipeline</option>
        <option value="orchestrator" ${hasOrch?'disabled':''}>Orchestrator</option>
      </select>
    </div>
    <div class="modal-actions">
      <button class="btn btn-outline" onclick="closeModal()">Annuler</button>
      <button class="btn btn-primary" onclick="addCfgAgent('${escHtml(dir)}')">Ajouter</button>
    </div>
  `, 'modal-tall');
}

function _filterCfgAgentDropdown() {
  const filter = (document.getElementById('cfg-agent-filter').value || '').toLowerCase();
  const dd = document.getElementById('cfg-agent-dropdown');
  dd.style.display = '';
  dd.querySelectorAll('.sa-dropdown-item').forEach(item => {
    const label = (item.dataset.name + ' ' + item.dataset.id).toLowerCase();
    item.style.display = label.includes(filter) ? '' : 'none';
  });
}
function _openCfgAgentDropdown() {
  document.getElementById('cfg-agent-dropdown').style.display = '';
  _filterCfgAgentDropdown();
}
function _pickCfgAgent(el) {
  const id = el.dataset.id, name = el.dataset.name;
  document.getElementById('cfg-agent-new-id').value = id;
  document.getElementById('cfg-agent-filter').value = name + ' (' + id + ')';
  document.getElementById('cfg-agent-dropdown').style.display = 'none';
}

async function addCfgAgent(dir) {
  const id = (document.getElementById('cfg-agent-new-id').value || '').trim();
  if (!id) { toast('Selectionnez un agent du catalogue', 'error'); return; }
  const agentType = document.getElementById('cfg-agent-new-type').value;
  if (agentType === 'orchestrator') {
    try {
      const reg = await api(`/api/agents/registry/${encodeURIComponent(dir)}`);
      if (Object.values(reg.agents || reg || {}).some(a => a.type === 'orchestrator')) {
        toast('Un orchestrator existe deja dans cette equipe', 'error'); return;
      }
    } catch { /* ignore */ }
  }
  try {
    await api('/api/agents', { method: 'POST', body: {
      id,
      name: id,
      type: agentType,
      team_id: dir,
    }});
    toast('Agent ajoute', 'success');
    closeModal();
    loadTeams();
  } catch (e) { toast(e.message, 'error'); }
}

async function editCfgAgent(dir, agentId) {
  const team = teamsData.find(t => (t.directory || t.id) === dir);
  if (!team || !team.agents[agentId]) { toast('Agent introuvable', 'error'); return; }
  const a = team.agents[agentId];

  // Agent properties are read-only (from Shared/Agents catalog)
  const mcpAccess = a.mcp_access || [];
  const mcpReadOnly = mcpAccess.length
    ? mcpAccess.map(id => `<span class="tag tag-green">${escHtml(id)}</span>`).join('')
    : '<span style="color:var(--text-secondary);font-size:0.85rem">Aucun</span>';
  const delivTags = [
    a.delivers_docs ? '<span class="tag tag-purple">Documentation</span>' : '',
    a.delivers_code ? '<span class="tag tag-purple">Code</span>' : '',
  ].filter(Boolean).join('') || '<span style="color:var(--text-secondary);font-size:0.85rem">Aucun</span>';

  const promptRaw = a.prompt_content || '';
  const promptHtml = typeof marked !== 'undefined' ? marked.parse(promptRaw) : escHtml(promptRaw);
  const hasPipeline = a.type === 'pipeline' || (a.pipeline_steps && a.pipeline_steps.length > 0);
  const isOrchestrator = a.type === 'orchestrator';
  const curType = isOrchestrator ? 'orchestrator' : (hasPipeline ? 'pipeline' : 'single');
  const hasOtherOrch = Object.entries(team.agents || {}).some(([aid, ag]) => aid !== agentId && ag.type === 'orchestrator');

  showModal(`
    <div class="modal-header">
      <h3>Agent: ${escHtml(a.name || agentId)} <span style="color:var(--text-secondary);font-weight:normal;font-size:0.85rem">(${escHtml(agentId)})</span></h3>
      <button class="btn-icon" onclick="closeModal()">&times;</button>
    </div>
    <div class="prompt-tabs" style="margin-bottom:0.5rem">
      <div class="prompt-tab active" id="cfg-modal-tab-info" onclick="switchCfgModalTab('info')">Signaletique</div>
      <div class="prompt-tab" id="cfg-modal-tab-prompt" onclick="switchCfgModalTab('prompt')">Prompt</div>
      <div class="prompt-tab" id="cfg-modal-tab-pipeline" onclick="switchCfgModalTab('pipeline')" style="${hasPipeline ? '' : 'display:none'}">Pipeline</div>
    </div>
    <div id="cfg-modal-pane-info">
      <div class="form-row">
        <div class="form-group">
          <label>Nom</label>
          <input value="${escHtml(a.name || agentId)}" readonly style="background:var(--bg-secondary)" />
        </div>
        <div class="form-group">
          <label>Modele LLM</label>
          <input value="${escHtml(a.llm || '(defaut)')}" readonly style="background:var(--bg-secondary)" />
        </div>
      </div>
      <div class="form-row">
        <div class="form-group">
          <label>Temperature</label>
          <input value="${a.temperature ?? ''}" readonly style="background:var(--bg-secondary)" />
        </div>
        <div class="form-group">
          <label>Max tokens</label>
          <input value="${a.max_tokens ?? ''}" readonly style="background:var(--bg-secondary)" />
        </div>
      </div>
      <div class="form-group">
        <label>Type</label>
        <select id="cfg-agent-edit-type" onchange="_onCfgTypeChange(this.value)">
          <option value="single" ${curType==='single'?'selected':''}>Single</option>
          <option value="pipeline" ${curType==='pipeline'?'selected':''}>Pipeline</option>
          <option value="orchestrator" ${curType==='orchestrator'?'selected':''} ${hasOtherOrch && curType!=='orchestrator'?'disabled':''}>Orchestrator</option>
        </select>
      </div>
      <div class="form-group">
        <label>Serveurs MCP autorises</label>
        <div style="display:flex;flex-wrap:wrap;gap:0.35rem;margin-top:0.25rem">${mcpReadOnly}</div>
      </div>
      <div class="form-group">
        <label>Type de livrable</label>
        <div style="display:flex;flex-wrap:wrap;gap:0.35rem;margin-top:0.25rem">${delivTags}</div>
      </div>
    </div>
    <div id="cfg-modal-pane-prompt" style="display:none">
      <div class="form-group">
        <label>Prompt</label>
        <div class="prompt-preview" id="cfg-agent-prompt-preview" style="max-height:500px;overflow-y:auto"></div>
      </div>
    </div>
    <div id="cfg-modal-pane-pipeline" style="display:none">
      <div class="form-group">
        <label>Pipeline Steps</label>
        <div id="cfg-pipeline-steps" class="pipeline-steps-container"></div>
      </div>
    </div>
    <div class="modal-actions">
      <button class="btn btn-outline" onclick="closeModal()">Annuler</button>
      <button class="btn btn-primary" onclick="saveCfgAgent('${escHtml(dir)}','${escHtml(agentId)}')">Sauvegarder</button>
    </div>
  `, 'modal-wide');
  // Set prompt after modal creation to avoid template literal issues with backticks
  const cfgPromptEl = document.getElementById('cfg-agent-prompt-preview');
  if (cfgPromptEl) cfgPromptEl.innerHTML = promptHtml;
  renderPipelineSteps('cfg-pipeline-steps', a.pipeline_steps || []);
}

function switchCfgModalTab(tab) {
  ['info', 'prompt', 'pipeline'].forEach(t => {
    const pane = document.getElementById('cfg-modal-pane-' + t);
    const tabEl = document.getElementById('cfg-modal-tab-' + t);
    if (pane) pane.style.display = t === tab ? '' : 'none';
    if (tabEl) tabEl.classList.toggle('active', t === tab);
  });
}

function _onCfgTypeChange(val) {
  const tabEl = document.getElementById('cfg-modal-tab-pipeline');
  if (tabEl) tabEl.style.display = val === 'pipeline' ? '' : 'none';
  if (val !== 'pipeline') {
    const pane = document.getElementById('cfg-modal-pane-pipeline');
    if (pane && pane.style.display !== 'none') switchCfgModalTab('info');
  }
}

async function saveCfgAgent(dir, agentId) {
  const agentType = document.getElementById('cfg-agent-edit-type').value;
  const team = teamsData.find(t => (t.directory || t.id) === dir);
  if (agentType === 'orchestrator' && Object.entries(team.agents || {}).some(([aid, ag]) => aid !== agentId && ag.type === 'orchestrator')) {
    toast('Un orchestrator existe deja dans cette equipe', 'error'); return;
  }
  const pipeline_steps = agentType === 'pipeline' ? getPipelineSteps('cfg-pipeline-steps') : [];
  try {
    await api(`/api/agents/${encodeURIComponent(agentId)}`, { method: 'PUT', body: {
      id: agentId, name: agentId,
      type: agentType,
      pipeline_steps,
      team_id: dir,
    }});
    toast('Agent sauvegarde', 'success');
    closeModal();
    loadTeams();
  } catch (e) { toast(e.message, 'error'); }
}

async function deleteCfgAgent(dir, agentId) {
  if (!(await confirmModal(`Supprimer l'agent "${agentId}" ?`))) return;
  try {
    await api(`/api/agents/${encodeURIComponent(agentId)}?team_id=${encodeURIComponent(dir)}`, { method: 'DELETE' });
    toast('Agent supprime', 'success');
    loadTeams();
  } catch (e) { toast(e.message, 'error'); }
}

async function showCfgRawRegistry(dir) {
  try {
    const data = await api(`/api/agents/registry/${encodeURIComponent(dir)}`);
    const json = JSON.stringify(data, null, 2);
    showModal(`
      <div class="modal-header">
        <h3>Registry JSON — config/Teams/${escHtml(dir)}/</h3>
        <button class="btn-icon" onclick="closeModal()">&times;</button>
      </div>
      <div class="form-group">
        <textarea id="cfg-raw-json" style="min-height:400px;font-family:monospace;font-size:0.8rem;white-space:pre;tab-size:2">${escHtml(json)}</textarea>
      </div>
      <div class="modal-actions">
        <button class="btn btn-outline" onclick="closeModal()">Annuler</button>
        <button class="btn btn-primary" onclick="saveCfgRawRegistry('${escHtml(dir)}')">Sauvegarder</button>
      </div>
    `, 'modal-wide');
  } catch (e) { toast(e.message, 'error'); }
}

async function saveCfgRawRegistry(dir) {
  const raw = document.getElementById('cfg-raw-json').value;
  let data;
  try { data = JSON.parse(raw); } catch { toast('JSON invalide', 'error'); return; }
  try {
    await api(`/api/agents/registry/${encodeURIComponent(dir)}`, { method: 'PUT', body: data });
    toast('Registry sauvegarde', 'success');
    closeModal();
    loadTeams();
  } catch (e) { toast(e.message, 'error'); }
}

async function showCfgWorkflow(dir) {
  openWorkflowEditor(dir, '/api/workflow', 'Configs/Teams');
}

let _hitlUsersList = [];
async function _loadHitlUsers(force) {
  if (_hitlUsersList.length && !force) return;
  try { _hitlUsersList = await api('/api/hitl/users'); } catch { _hitlUsersList = []; }
}
function _userSelectOptions(selectedEmail) {
  return `<option value="">-- Selectionner --</option>` +
    _hitlUsersList.filter(u => u.is_active).map(u =>
      `<option value="${escHtml(u.email)}" ${u.email === selectedEmail ? 'selected' : ''}>${escHtml(u.display_name || u.email)} (${escHtml(u.email)})</option>`
    ).join('');
}
function _renderMemberRows(container, members) {
  container.innerHTML = '';
  if (!members.length) members = [''];
  members.forEach((email, i) => {
    const isLast = i === members.length - 1;
    const row = document.createElement('div');
    row.style.cssText = 'display:flex;gap:6px;align-items:center;margin-bottom:4px';
    row.innerHTML = `<select class="team-member-select" style="flex:1">${_userSelectOptions(email)}</select>` +
      (isLast
        ? `<button type="button" class="btn-icon" onclick="_addMemberRow(this)" title="Ajouter">+</button>`
        : `<button type="button" class="btn-icon" onclick="this.parentElement.remove()" title="Supprimer" style="color:var(--text-secondary)">&#x1F5D1;</button>`);
    container.appendChild(row);
  });
}
function _addMemberRow(btn) {
  const container = btn.closest('.team-members-list');
  // Replace + with trash on current last row
  const rows = container.querySelectorAll('div');
  const lastRow = rows[rows.length - 1];
  const lastBtn = lastRow.querySelector('button');
  lastBtn.outerHTML = `<button type="button" class="btn-icon" onclick="this.parentElement.remove()" title="Supprimer" style="color:var(--text-secondary)">&#x1F5D1;</button>`;
  // Add new row with +
  const row = document.createElement('div');
  row.style.cssText = 'display:flex;gap:6px;align-items:center;margin-bottom:4px';
  row.innerHTML = `<select class="team-member-select" style="flex:1">${_userSelectOptions('')}</select>` +
    `<button type="button" class="btn-icon" onclick="_addMemberRow(this)" title="Ajouter">+</button>`;
  container.appendChild(row);
}
function _collectMembers() {
  return Array.from(document.querySelectorAll('.team-member-select'))
    .map(s => s.value).filter(Boolean);
}

async function showAddTeamModal() {
  // Load templates and users in parallel
  const [tplRes] = await Promise.allSettled([
    api('/api/templates').then(d => { templatesData = d.templates || []; }),
    _loadHitlUsers(),
  ]);
  if (tplRes.status === 'rejected') templatesData = [];
  const dirOpts = templatesData.map(tp => `<option value="${escHtml(tp.id)}">${escHtml(tp.name || tp.id)} (${tp.agent_count} agents)</option>`).join('');
  showModal(`
    <div class="modal-header">
      <h3>Nouvelle equipe</h3>
      <button class="btn-icon" onclick="closeModal()">&times;</button>
    </div>
    <div class="form-group">
      <label>Identifiant</label>
      <input id="team-id" placeholder="ex: data_team" oninput="this.value = this.value.replace(/[^a-z0-9_-]/gi, '').toLowerCase(); document.getElementById('team-dir').value = this.value ? 'config/Teams/' + this.value : ''" />
    </div>
    <div class="form-group">
      <label>Nom</label>
      <input id="team-name" placeholder="Equipe Produit" />
    </div>
    <div class="form-group">
      <label>Description</label>
      <input id="team-desc" placeholder="Description de l'equipe" />
    </div>
    <div class="form-group">
      <label>Repertoire</label>
      <input id="team-dir" readonly style="background:var(--bg-tertiary);color:var(--text-secondary)" />
    </div>
    <div class="form-group">
      <label>Creer a partir d'un template (Shared)</label>
      <select id="team-template">
        <option value="">(vide — equipe vierge)</option>
        ${dirOpts}
      </select>
    </div>
    <div class="form-group">
      <label>Channels Discord (un par ligne)</label>
      <textarea id="team-channels" rows="2" placeholder="1234567890" style="resize:vertical;min-height:auto"></textarea>
    </div>
    <div class="form-group">
      <label>Membres</label>
      <div class="team-members-list" id="team-members-list"></div>
    </div>
    <div class="modal-actions">
      <button class="btn btn-outline" onclick="closeModal()">Annuler</button>
      <button class="btn btn-primary" onclick="addTeam()">Enregistrer</button>
    </div>
  `);
  _renderMemberRows(document.getElementById('team-members-list'), ['']);
}

async function editTeam(idxOrId) {
  if (!teamsData.length) {
    try { const data = await api('/api/teams'); teamsData = data.teams || []; } catch (_) {}
  }
  const t = typeof idxOrId === 'number' ? teamsData[idxOrId] : teamsData.find(x => x.id === idxOrId);
  if (!t) { toast('Equipe introuvable', 'error'); return; }
  await _loadHitlUsers(true);
  // Find existing members for this team from HITL users data
  const existingMembers = _hitlUsersList
    .filter(u => (u.teams || []).some(tm => tm.team_id === t.id))
    .map(u => u.email);
  const agentIds = Object.keys(t.agents || {});
  const orchOpts = `<option value="">-- Aucun --</option>` +
    agentIds.map(aid => `<option value="${escHtml(aid)}" ${(t.orchestrator || '') === aid ? 'selected' : ''}>${escHtml((t.agents[aid] || {}).name || aid)} (${escHtml(aid)})</option>`).join('');
  showModal(`
    <div class="modal-header">
      <h3>Modifier: ${escHtml(t.name || t.id)}</h3>
      <button class="btn-icon" onclick="closeModal()">&times;</button>
    </div>
    <div class="form-group">
      <label>Identifiant</label>
      <input value="${escHtml(t.id)}" disabled />
    </div>
    <div class="form-group">
      <label>Nom</label>
      <input id="team-name" value="${escHtml(t.name || '')}" placeholder="Equipe Produit" />
    </div>
    <div class="form-group">
      <label>Description</label>
      <input id="team-desc" value="${escHtml(t.description || '')}" />
    </div>
    <div class="form-group">
      <label>Repertoire</label>
      <input id="team-dir" value="${escHtml(t.directory || t.id)}" disabled style="background:var(--bg-tertiary);color:var(--text-secondary)" />
    </div>
    <div class="form-group">
      <label>Orchestrateur</label>
      <select id="team-orchestrator">${orchOpts}</select>
    </div>
    <div class="form-group">
      <label>Channels Discord (un par ligne)</label>
      <textarea id="team-channels" rows="2" style="resize:vertical;min-height:auto">${(t.discord_channels || []).join('\n')}</textarea>
    </div>
    <div class="form-group">
      <label>Membres</label>
      <div class="team-members-list" id="team-members-list"></div>
    </div>
    <div class="modal-actions">
      <button class="btn btn-outline" onclick="closeModal()">Annuler</button>
      <button class="btn btn-primary" onclick="saveTeam('${escHtml(t.id)}')">Enregistrer</button>
    </div>
  `);
  _renderMemberRows(document.getElementById('team-members-list'), existingMembers.length ? existingMembers : ['']);
}

async function addTeam() {
  const id = (document.getElementById('team-id')?.value || '').trim().replace(/[^a-zA-Z0-9_-]/g, '_').toLowerCase();
  if (!id) { toast('Identifiant requis', 'error'); return; }
  const name = document.getElementById('team-name').value.trim();
  if (!name) { toast('Nom requis', 'error'); return; }
  const directory = id;
  const channels = document.getElementById('team-channels').value.split('\n').map(s => s.trim()).filter(Boolean);
  const template = document.getElementById('team-template')?.value || '';
  try {
    await api(`/api/teams/${encodeURIComponent(id)}`, { method: 'POST', body: {
      name,
      description: document.getElementById('team-desc').value.trim(),
      directory,
      discord_channels: channels,
      template,
      members: _collectMembers(),
    }});
    toast('Equipe ajoutee', 'success');
    closeModal();
    loadTeams();
  } catch (e) { toast(e.message, 'error'); }
}

async function saveTeam(id) {
  const name = document.getElementById('team-name').value.trim();
  if (!name) { toast('Nom requis', 'error'); return; }
  const directory = document.getElementById('team-dir').value.trim();
  const orchestrator = (document.getElementById('team-orchestrator') || document.getElementById('team-edit-orchestrator'))?.value || '';
  const channels = document.getElementById('team-channels')
    ? document.getElementById('team-channels').value.split('\n').map(s => s.trim()).filter(Boolean)
    : (document.getElementById('team-edit-channels')?.value || '').split(',').map(s => s.trim()).filter(Boolean);
  try {
    await api(`/api/teams/${encodeURIComponent(id)}`, { method: 'PUT', body: {
      name,
      description: (document.getElementById('team-desc') || document.getElementById('team-edit-desc'))?.value.trim() || '',
      directory,
      discord_channels: channels,
      orchestrator,
      members: _collectMembers(),
    }});
    toast('Equipe mise a jour', 'success');
    closeModal();
    loadTeams();
  } catch (e) { toast(e.message, 'error'); }
}

async function deleteTeam(id) {
  if (!(await confirmModal(`Supprimer l'equipe "${id}" ?`))) return;
  try {
    await api(`/api/teams/${encodeURIComponent(id)}`, { method: 'DELETE' });
    toast('Equipe supprimee', 'success');
    loadTeams();
  } catch (e) { toast(e.message, 'error'); }
}

// ═══════════════════════════════════════════════════
// CONFIG SUB-TABS (LLM, MCP, Teams)
// ═══════════════════════════════════════════════════
let cfgLlmData = {};
let cfgMcpData = {};

function showConfigTab(tabId) {
  document.querySelectorAll('.cfg-tab-content').forEach(c => c.classList.remove('active'));
  document.querySelectorAll('[data-cfg-tab]').forEach(t => t.classList.remove('active'));
  document.getElementById('cfg-tab-' + tabId).classList.add('active');
  document.querySelector(`[data-cfg-tab="${tabId}"]`).classList.add('active');
  // Show/hide save button depending on tab
  const saveWrap = document.getElementById('cfg-tab-save-btn');
  const saveBtn = document.getElementById('cfg-tab-save-action');
  const saveTabs = { 'cfg-mail': saveMail, 'cfg-misc': saveCfgMisc };
  if (saveTabs[tabId]) {
    saveWrap.style.display = '';
    saveBtn.onclick = saveTabs[tabId];
  } else {
    saveWrap.style.display = 'none';
  }
  if (tabId === 'cfg-llm') loadCfgLLM();
  else if (tabId === 'cfg-mcp') loadCfgMCP();
  else if (tabId === 'cfg-teams') loadCfgTeams();
  else if (tabId === 'cfg-mail') loadMail();
  else if (tabId === 'cfg-security') { loadApiKeys(); loadAuthConfig(); }
  else if (tabId === 'cfg-outline') loadOutlineConfig();
  else if (tabId === 'cfg-misc') loadCfgMisc();
  else if (tabId === 'cfg-git') loadCfgGit();
}

// ── Config Outline (Base de connaissances) ────────
let _outlineData = {};
const _defaultDeliverables = {
  prd: 'PRD / Cahier des charges',
  legal_review: 'Analyse juridique',
  architecture: 'Architecture technique',
  ux_design: 'Design UX/UI',
  project_plan: 'Plan de projet',
  technical_docs: 'Documentation technique',
  user_docs: 'Documentation utilisateur',
  qa_report: 'Rapport QA',
  deployment_plan: 'Plan de deploiement',
};

async function loadOutlineConfig() {
  try {
    _outlineData = await api('/api/outline-config');
    document.getElementById('outline-enabled').checked = _outlineData.enabled || false;
    document.getElementById('outline-collection-prefix').value = _outlineData.collection_prefix || 'LandGraph';
    document.getElementById('outline-url-env').value = _outlineData.url_env || 'OUTLINE_URL';
    document.getElementById('outline-api-key-env').value = _outlineData.api_key_env || 'OUTLINE_API_KEY';

    const ap = _outlineData.auto_publish || {};
    document.getElementById('outline-auto-publish').checked = ap.enabled || false;

    const deliverables = ap.deliverables || {};
    const container = document.getElementById('outline-deliverables-list');
    container.innerHTML = Object.entries(_defaultDeliverables).map(([key, label]) =>
      `<label style="display:flex;align-items:center;gap:0.4rem;font-size:0.85rem">
        <input type="checkbox" class="outline-deliv-cb" data-key="${key}" ${deliverables[key] ? 'checked' : ''} />
        ${escHtml(label)}
      </label>`
    ).join('');
  } catch (e) { toast(e.message, 'error'); }
}

async function saveOutlineConfig() {
  const deliverables = {};
  document.querySelectorAll('.outline-deliv-cb').forEach(cb => {
    deliverables[cb.dataset.key] = cb.checked;
  });
  const data = {
    enabled: document.getElementById('outline-enabled').checked,
    url_env: document.getElementById('outline-url-env').value || 'OUTLINE_URL',
    api_key_env: document.getElementById('outline-api-key-env').value || 'OUTLINE_API_KEY',
    collection_prefix: document.getElementById('outline-collection-prefix').value || 'LandGraph',
    phase_labels: _outlineData.phase_labels || {},
    auto_publish: {
      enabled: document.getElementById('outline-auto-publish').checked,
      deliverables,
    },
  };
  try {
    await api('/api/outline-config', { method: 'PUT', headers: {'Content-Type':'application/json'}, body: JSON.stringify(data) });
    toast('Configuration Outline sauvegardee', 'success');
  } catch (e) { toast(e.message, 'error'); }
}

async function testOutlineConnection() {
  const btn = document.getElementById('outline-test-btn');
  const result = document.getElementById('outline-test-result');
  btn.disabled = true;
  result.textContent = 'Test en cours...';
  result.style.color = 'var(--text-secondary)';
  try {
    const r = await api('/api/outline/test-connection', { method: 'POST' });
    if (r.ok) {
      result.textContent = `Connecte (${r.info.team || '?'} — ${r.info.user || '?'})`;
      result.style.color = 'var(--success)';
    } else {
      result.textContent = r.error || 'Erreur inconnue';
      result.style.color = 'var(--danger)';
    }
  } catch (e) {
    result.textContent = e.message;
    result.style.color = 'var(--danger)';
  }
  btn.disabled = false;
}

// ── Config Divers ─────────────────────────────────
let _miscData = {};

async function loadCfgMisc() {
  try {
    _miscData = await api('/api/others');
    // Populate SMTP + Template dropdowns from mail config
    const smtpSel = document.getElementById('misc-reset-smtp');
    const tplSel = document.getElementById('misc-reset-template');
    smtpSel.innerHTML = '<option value="">— aucun —</option>';
    tplSel.innerHTML = '<option value="">— aucun —</option>';
    try {
      const mailCfg = await api('/api/mail');
      const smtpList = Array.isArray(mailCfg.smtp) ? mailCfg.smtp : [];
      smtpList.forEach(s => {
        const label = `${s.name || 'sans nom'} (${s.host || '?'}:${s.port || '?'})`;
        smtpSel.innerHTML += `<option value="${escHtml(s.name)}">${escHtml(label)}</option>`;
      });
      const tplList = Array.isArray(mailCfg.templates) ? mailCfg.templates : [];
      tplList.forEach(t => {
        const label = `${t.name || 'sans nom'}${t.subject ? ' — ' + t.subject.substring(0, 40) : ''}`;
        tplSel.innerHTML += `<option value="${escHtml(t.name)}">${escHtml(label)}</option>`;
      });
    } catch (_) {}
    // Set values
    const pr = _miscData.password_reset || {};
    smtpSel.value = pr.smtp_name || '';
    tplSel.value = pr.template_name || '';
    // Domain / hosts
    const hosts = _miscData.hosts || {};
    document.getElementById('misc-host-admin').value = hosts.admin || '';
    document.getElementById('misc-host-hitl').value = hosts.hitl || '';
    document.getElementById('misc-host-api').value = hosts.api || '';
    document.getElementById('misc-host-openlit').value = hosts.openlit || '';
    document.getElementById('misc-host-outline').value = hosts.outline || '';
    document.getElementById('misc-host-postgres').value = hosts.postgres || '';
    document.getElementById('misc-host-redis').value = hosts.redis || '';
  } catch (e) { toast(e.message, 'error'); }
}

async function saveCfgMisc() {
  try {
    const data = {
      ..._miscData,
      hosts: {
        admin: document.getElementById('misc-host-admin').value.trim(),
        hitl: document.getElementById('misc-host-hitl').value.trim(),
        api: document.getElementById('misc-host-api').value.trim(),
        openlit: document.getElementById('misc-host-openlit').value.trim(),
        outline: document.getElementById('misc-host-outline').value.trim(),
        postgres: document.getElementById('misc-host-postgres').value.trim(),
        redis: document.getElementById('misc-host-redis').value.trim(),
      },
      password_reset: {
        smtp_name: document.getElementById('misc-reset-smtp').value,
        template_name: document.getElementById('misc-reset-template').value,
      }
    };
    await api('/api/others', { method: 'PUT', body: data });
    _miscData = data;
    toast('Configuration sauvegardee', 'success');
  } catch (e) { toast(e.message, 'error'); }
}

// ── Config LLM ────────────────────────────────────
async function loadCfgLLM() {
  try {
    cfgLlmData = await api('/api/llm/providers');
    renderCfgLLM();
  } catch (e) { toast(e.message, 'error'); }
}

function renderCfgLLM() {
  const providers = cfgLlmData.providers || {};
  const throttling = cfgLlmData.throttling || {};
  const defaultId = cfgLlmData.default || '';

  // Default select
  const sel = document.getElementById('cfg-llm-default-select');
  sel.innerHTML = `<option value="">-- Aucun --</option>` +
    Object.entries(providers).map(([id, p]) =>
      `<option value="${escHtml(id)}" ${id === defaultId ? 'selected' : ''}>${escHtml(id)} — ${escHtml(p.description || p.model)}</option>`
    ).join('');

  // Providers table
  const tbl = document.getElementById('cfg-llm-providers-table');
  if (Object.keys(providers).length === 0) {
    tbl.innerHTML = '<p style="color:var(--text-secondary);text-align:center;padding:1rem">Aucun provider configure.</p>';
  } else {
    tbl.innerHTML = `<table>
      <thead><tr><th>ID</th><th>Type</th><th>Modele</th><th>URL</th><th>Cle API</th><th>Description</th><th style="width:130px">Actions</th></tr></thead>
      <tbody>${Object.entries(providers).map(([id, p]) => {
        const isDefault = id === defaultId;
        const url = p.base_url || p.azure_endpoint || '';
        return `<tr>
          <td><strong>${escHtml(id)}</strong>${isDefault ? '<span class="tag tag-green" style="margin-left:0.5rem">defaut</span>' : ''}</td>
          <td><span class="tag tag-blue">${escHtml(p.type)}</span></td>
          <td><code style="font-size:0.8rem">${escHtml(p.model)}</code></td>
          <td>${url ? `<code style="font-size:0.75rem">${escHtml(url)}</code>` : '<span style="color:var(--text-secondary)">—</span>'}</td>
          <td>${p.env_key ? `<code style="font-size:0.75rem">${escHtml(p.env_key)}</code>` : '<span style="color:var(--text-secondary)">—</span>'}</td>
          <td style="font-size:0.8rem;color:var(--text-secondary)">${escHtml(p.description || '')}</td>
          <td>
            <button class="btn-icon" onclick="cloneCfgProvider('${escHtml(id)}')" title="Cloner">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>
            </button>
            <button class="btn-icon" onclick="editCfgProvider('${escHtml(id)}')" title="Modifier">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>
            </button>
            <button class="btn-icon danger" onclick="deleteCfgProvider('${escHtml(id)}')" title="Supprimer">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>
            </button>
          </td>
        </tr>`;
      }).join('')}</tbody>
    </table>`;
  }

  // Throttling table
  const ttbl = document.getElementById('cfg-llm-throttling-table');
  if (Object.keys(throttling).length === 0) {
    ttbl.innerHTML = '<p style="color:var(--text-secondary);text-align:center;padding:1rem">Aucune regle de throttling.</p>';
  } else {
    ttbl.innerHTML = `<table>
      <thead><tr><th>Cle API</th><th>RPM</th><th>TPM</th><th style="width:100px">Actions</th></tr></thead>
      <tbody>${Object.entries(throttling).map(([key, t]) => `<tr>
        <td><code>${escHtml(key)}</code></td>
        <td>${t.rpm}</td>
        <td>${t.tpm.toLocaleString()}</td>
        <td>
          <button class="btn-icon" onclick="editCfgThrottling('${escHtml(key)}', ${t.rpm}, ${t.tpm})" title="Modifier">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>
          </button>
          <button class="btn-icon danger" onclick="deleteCfgThrottling('${escHtml(key)}')" title="Supprimer">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>
          </button>
        </td>
      </tr>`).join('')}</tbody>
    </table>`;
  }
  filterCfgLLM();
}

function filterCfgLLM() {
  const q = (document.getElementById('cfg-llm-filter')?.value || '').toLowerCase();
  document.querySelectorAll('#cfg-llm-providers-table tbody tr').forEach(tr => {
    tr.style.display = tr.textContent.toLowerCase().includes(q) ? '' : 'none';
  });
}

async function setCfgLLMDefault(providerId) {
  try {
    await api('/api/llm/providers/default', { method: 'PUT', body: { provider_id: providerId } });
    toast('Modele par defaut mis a jour', 'success');
    loadCfgLLM();
  } catch (e) { toast(e.message, 'error'); }
}

function _uniqueProviderId(baseId, providers) {
  let candidate = baseId + '-copy';
  let n = 2;
  while (candidate in providers) { candidate = baseId + '-copy-' + n; n++; }
  return candidate;
}

function cloneCfgProvider(id) {
  const p = cfgLlmData.providers[id];
  if (!p) return;
  const newId = _uniqueProviderId(id, cfgLlmData.providers);
  showModal(`
    <div class="modal-header">
      <h3>Cloner provider (config)</h3>
      <button class="btn-icon" onclick="closeModal()">&times;</button>
    </div>
    <div class="form-row">
      <div class="form-group"><label>ID (unique)</label><input id="prov-id" value="${escHtml(newId)}" /></div>
      <div class="form-group"><label>Type</label>
        <select id="prov-type" onchange="_updateProviderTypeFields()">
          ${LLM_TYPES.map(t => `<option value="${t}" ${t === p.type ? 'selected' : ''}>${t}</option>`).join('')}
        </select>
      </div>
    </div>
    <div class="form-row">
      <div class="form-group"><label>Modele</label><input id="prov-model" value="${escHtml(p.model)}" /></div>
      <div class="form-group"><label>Cle API (env var)</label><input id="prov-envkey" value="${escHtml(p.env_key || '')}" /></div>
    </div>
    <div class="form-row">
      <div class="form-group"><label>Description</label><input id="prov-desc" value="${escHtml(p.description || '')}" /></div>
      <div class="form-group"><label>Base URL</label><input id="prov-base-url" value="${escHtml(p.base_url || '')}" placeholder="https://..." /></div>
    </div>
    ${_providerTypeFields(p.type, p)}
    <div class="modal-actions">
      <button class="btn btn-outline" onclick="closeModal()">Annuler</button>
      <button class="btn btn-primary" onclick="addCfgProvider()">Ajouter</button>
    </div>
  `);
}

function showAddCfgProviderModal() {
  showModal(`
    <div class="modal-header">
      <h3>Ajouter un provider (config)</h3>
      <button class="btn-icon" onclick="closeModal()">&times;</button>
    </div>
    <div class="form-row">
      <div class="form-group"><label>ID (unique)</label><input id="prov-id" placeholder="mon-modele" /></div>
      <div class="form-group"><label>Type</label>
        <select id="prov-type" onchange="_updateProviderTypeFields()">
          ${LLM_TYPES.map(t => `<option value="${t}">${t}</option>`).join('')}
        </select>
      </div>
    </div>
    <div class="form-row">
      <div class="form-group"><label>Modele</label><input id="prov-model" placeholder="gpt-4o, claude-sonnet-4-5..." /></div>
      <div class="form-group"><label>Cle API (env var)</label><input id="prov-envkey" placeholder="OPENAI_API_KEY" /></div>
    </div>
    <div class="form-row">
      <div class="form-group"><label>Description</label><input id="prov-desc" placeholder="Description du modele" /></div>
      <div class="form-group"><label>Base URL</label><input id="prov-base-url" value="" placeholder="https://..." /></div>
    </div>
    ${_providerTypeFields('anthropic')}
    <div class="modal-actions">
      <button class="btn btn-outline" onclick="closeModal()">Annuler</button>
      <button class="btn btn-primary" onclick="addCfgProvider()">Ajouter</button>
    </div>
  `);
}

async function addCfgProvider() {
  const { id, prov } = _readProviderForm();
  if (!id || !prov.model) { toast('ID et modele requis', 'error'); return; }
  try {
    await api('/api/llm/providers/provider', {
      method: 'POST',
      body: { id, ...prov },
    });
    toast('Provider ajoute', 'success');
    closeModal();
    loadCfgLLM();
  } catch (e) { toast(e.message, 'error'); }
}

function editCfgProvider(id) {
  const p = cfgLlmData.providers[id];
  if (!p) return;
  showModal(`
    <div class="modal-header">
      <h3>Modifier (config) : ${escHtml(id)}</h3>
      <button class="btn-icon" onclick="closeModal()">&times;</button>
    </div>
    <div class="form-row">
      <div class="form-group"><label>ID</label><input id="prov-id" value="${escHtml(id)}" /></div>
      <div class="form-group"><label>Type</label>
        <select id="prov-type" onchange="_updateProviderTypeFields()">
          ${LLM_TYPES.map(t => `<option value="${t}" ${t === p.type ? 'selected' : ''}>${t}</option>`).join('')}
        </select>
      </div>
    </div>
    <div class="form-row">
      <div class="form-group"><label>Modele</label><input id="prov-model" value="${escHtml(p.model)}" /></div>
      <div class="form-group"><label>Cle API (env var)</label><input id="prov-envkey" value="${escHtml(p.env_key || '')}" /></div>
    </div>
    <div class="form-row">
      <div class="form-group"><label>Description</label><input id="prov-desc" value="${escHtml(p.description || '')}" /></div>
      <div class="form-group"><label>Base URL</label><input id="prov-base-url" value="${escHtml(p.base_url || '')}" placeholder="https://..." /></div>
    </div>
    ${_providerTypeFields(p.type, p)}
    <div class="modal-actions">
      <button class="btn btn-outline" onclick="closeModal()">Annuler</button>
      <button class="btn btn-primary" onclick="saveCfgProvider('${escHtml(id)}')">Sauvegarder</button>
    </div>
  `);
}

async function saveCfgProvider(originalId) {
  const { id, prov } = _readProviderForm();
  if (!id || !prov.model) { toast('ID et modele requis', 'error'); return; }
  try {
    await api(`/api/llm/providers/provider/${encodeURIComponent(originalId)}`, {
      method: 'PUT',
      body: { id, ...prov },
    });
    toast('Provider mis a jour', 'success');
    closeModal();
    loadCfgLLM();
  } catch (e) { toast(e.message, 'error'); }
}

async function deleteCfgProvider(id) {
  if (!(await confirmModal(`Supprimer le provider "${id}" ?`))) return;
  try {
    await api(`/api/llm/providers/provider/${encodeURIComponent(id)}`, { method: 'DELETE' });
    toast('Provider supprime', 'success');
    loadCfgLLM();
  } catch (e) { toast(e.message, 'error'); }
}

async function copyCfgLLMFromTemplate() {
  try {
    const tplData = await api('/api/templates/llm');
    const tplProviders = tplData.providers || {};
    const tplThrottling = tplData.throttling || {};
    const cfgProviders = cfgLlmData.providers || {};
    const cfgThrottling = cfgLlmData.throttling || {};

    let addedP = 0, addedT = 0, skippedIdentical = 0;
    const conflicts = [];

    // Copy missing providers, detect conflicts
    for (const [id, prov] of Object.entries(tplProviders)) {
      if (!cfgProviders[id]) {
        await api('/api/llm/providers/provider', { method: 'POST', body: { id, ...prov } });
        addedP++;
      } else if (JSON.stringify(cfgProviders[id]) !== JSON.stringify(prov)) {
        conflicts.push({ id, existing: cfgProviders[id], imported: prov });
      } else {
        skippedIdentical++;
      }
    }

    // Copy missing throttling rules
    for (const [key, t] of Object.entries(tplThrottling)) {
      if (!cfgThrottling[key]) {
        await api('/api/llm/providers/throttling', { method: 'PUT', body: { env_key: key, rpm: t.rpm, tpm: t.tpm } });
        addedT++;
      }
    }

    // Copy default if not set
    if (!cfgLlmData.default && tplData.default && (cfgProviders[tplData.default] || tplProviders[tplData.default])) {
      await api('/api/llm/providers/default', { method: 'PUT', body: { provider_id: tplData.default } });
    }

    await loadCfgLLM();
    const summaryData = { added_providers: addedP, added_throttling: addedT, skipped_identical: skippedIdentical, conflicts };
    if (conflicts.length > 0) {
      showLlmConflictsModal(conflicts, '/api/llm/providers/resolve', loadCfgLLM, summaryData);
    } else {
      _llmUploadToast(summaryData);
    }
  } catch (e) { toast(e.message, 'error'); }
}

function _llmUploadToast(data) {
  const parts = [];
  if (data.added_providers) parts.push(`${data.added_providers} ajouté(s)`);
  if (data.added_throttling) parts.push(`${data.added_throttling} throttling ajouté(s)`);
  if (data.skipped_identical) parts.push(`${data.skipped_identical} identique(s)`);
  const nc = (data.conflicts || []).length;
  if (nc) parts.push(`${nc} conflit(s) à résoudre`);
  toast(parts.length ? parts.join(', ') : 'Aucun changement', nc ? 'warn' : (parts.length ? 'success' : 'info'));
}

function _diffKeys(a, b) {
  const keys = new Set([...Object.keys(a || {}), ...Object.keys(b || {})]);
  const diffs = [];
  for (const k of keys) {
    const va = JSON.stringify(a?.[k] ?? '—');
    const vb = JSON.stringify(b?.[k] ?? '—');
    if (va !== vb) diffs.push({ key: k, existing: a?.[k] ?? '—', imported: b?.[k] ?? '—' });
  }
  return diffs;
}

function showLlmConflictsModal(conflicts, resolveUrl, reloadFn, uploadData) {
  let rows = '';
  for (const c of conflicts) {
    const diffs = _diffKeys(c.existing, c.imported);
    const diffHtml = diffs.map(d =>
      `<tr><td style="color:var(--text-tertiary);padding:2px 8px">${d.key}</td>` +
      `<td style="color:#ef4444;padding:2px 8px;word-break:break-all">${typeof d.existing === 'object' ? JSON.stringify(d.existing) : d.existing}</td>` +
      `<td style="color:#22c55e;padding:2px 8px;word-break:break-all">${typeof d.imported === 'object' ? JSON.stringify(d.imported) : d.imported}</td></tr>`
    ).join('');
    rows += `
      <div style="border:1px solid var(--border);border-radius:6px;padding:10px;margin-bottom:8px">
        <label style="display:flex;align-items:center;gap:8px;cursor:pointer">
          <input type="checkbox" class="conflict-cb" data-id="${c.id}" checked />
          <strong>${c.id}</strong>
          <span style="font-size:11px;color:var(--text-tertiary)">${c.existing.name || ''} → ${c.imported.name || ''}</span>
        </label>
        <table style="font-size:11px;margin-top:6px;width:100%">
          <tr style="color:var(--text-tertiary)"><th style="text-align:left;padding:2px 8px">Champ</th><th style="text-align:left;padding:2px 8px">Actuel</th><th style="text-align:left;padding:2px 8px">Importé</th></tr>
          ${diffHtml}
        </table>
      </div>`;
  }
  showModal(`
    <div class="modal-header"><h3>Conflits détectés (${conflicts.length})</h3></div>
    <div class="modal-body" style="max-height:60vh;overflow-y:auto">
      <p style="font-size:12px;color:var(--text-secondary);margin-bottom:10px">Ces providers existent déjà avec des valeurs différentes. Cochez ceux que vous voulez remplacer par la version importée.</p>
      ${rows}
    </div>
    <div class="modal-footer">
      <button class="btn btn-secondary" onclick="_cancelLlmConflicts()">Annuler</button>
      <button class="btn btn-primary" onclick="_applyLlmConflicts()">Appliquer</button>
    </div>
  `, 'modal-lg');

  window._llmConflictCtx = { conflicts, resolveUrl, reloadFn, uploadData };
}

async function _applyLlmConflicts() {
  const ctx = window._llmConflictCtx;
  if (!ctx) return;
  const checked = document.querySelectorAll('.conflict-cb:checked');
  const overwrites = {};
  for (const cb of checked) {
    const id = cb.dataset.id;
    const c = ctx.conflicts.find(x => x.id === id);
    if (c) overwrites[id] = c.imported;
  }
  closeModal();
  const d = ctx.uploadData || {};
  const parts = [];
  if (d.added_providers) parts.push(`${d.added_providers} ajouté(s)`);
  if (d.added_throttling) parts.push(`${d.added_throttling} throttling ajouté(s)`);
  if (d.skipped_identical) parts.push(`${d.skipped_identical} identique(s)`);
  const nOverwrites = Object.keys(overwrites).length;
  const nSkipped = ctx.conflicts.length - nOverwrites;
  if (nOverwrites === 0) {
    if (nSkipped) parts.push(`${nSkipped} conflit(s) ignoré(s)`);
    toast(parts.length ? parts.join(', ') : 'Aucun changement', 'info');
    return;
  }
  try {
    const res = await api(ctx.resolveUrl, { method: 'POST', body: { overwrites } });
    parts.push(`${res.updated} mis à jour`);
    if (nSkipped) parts.push(`${nSkipped} conflit(s) ignoré(s)`);
    toast(parts.join(', '), 'success');
    ctx.reloadFn();
  } catch (e) { toast(e.message, 'error'); }
}

function _cancelLlmConflicts() {
  const ctx = window._llmConflictCtx;
  closeModal();
  if (ctx && ctx.uploadData) {
    const d = ctx.uploadData;
    const parts = [];
    if (d.added_providers) parts.push(`${d.added_providers} ajouté(s)`);
    if (d.added_throttling) parts.push(`${d.added_throttling} throttling ajouté(s)`);
    if (d.skipped_identical) parts.push(`${d.skipped_identical} identique(s)`);
    parts.push(`${(d.conflicts || []).length} conflit(s) ignoré(s)`);
    toast(parts.join(', '), 'info');
  }
}

function uploadCfgLLM() {
  const input = document.createElement('input');
  input.type = 'file';
  input.accept = '.json';
  input.onchange = async () => {
    const file = input.files[0];
    if (!file) return;
    const form = new FormData();
    form.append('file', file);
    try {
      const res = await fetch('/api/llm/providers/upload', { method: 'POST', body: form });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Erreur upload');
      await loadCfgLLM();
      if (data.conflicts && data.conflicts.length > 0) {
        showLlmConflictsModal(data.conflicts, '/api/llm/providers/resolve', loadCfgLLM, data);
      } else {
        _llmUploadToast(data);
      }
    } catch (e) { toast(e.message, 'error'); }
  };
  input.click();
}

function showAddCfgThrottlingModal() {
  showModal(`
    <div class="modal-header">
      <h3>Ajouter throttling (config)</h3>
      <button class="btn-icon" onclick="closeModal()">&times;</button>
    </div>
    <div class="form-group"><label>Cle API (env var)</label><input id="throttle-key" placeholder="OPENAI_API_KEY" /></div>
    <div class="form-row">
      <div class="form-group"><label>RPM (requetes/min)</label><input id="throttle-rpm" type="number" value="60" /></div>
      <div class="form-group"><label>TPM (tokens/min)</label><input id="throttle-tpm" type="number" value="60000" /></div>
    </div>
    <div class="modal-actions">
      <button class="btn btn-outline" onclick="closeModal()">Annuler</button>
      <button class="btn btn-primary" onclick="saveCfgThrottling()">Ajouter</button>
    </div>
  `);
}

function editCfgThrottling(key, rpm, tpm) {
  showModal(`
    <div class="modal-header">
      <h3>Modifier throttling (config) : ${escHtml(key)}</h3>
      <button class="btn-icon" onclick="closeModal()">&times;</button>
    </div>
    <div class="form-group"><label>Cle API</label><input id="throttle-key" value="${escHtml(key)}" disabled style="opacity:0.5" /></div>
    <div class="form-row">
      <div class="form-group"><label>RPM (requetes/min)</label><input id="throttle-rpm" type="number" value="${rpm}" /></div>
      <div class="form-group"><label>TPM (tokens/min)</label><input id="throttle-tpm" type="number" value="${tpm}" /></div>
    </div>
    <div class="modal-actions">
      <button class="btn btn-outline" onclick="closeModal()">Annuler</button>
      <button class="btn btn-primary" onclick="saveCfgThrottling()">Sauvegarder</button>
    </div>
  `);
}

async function saveCfgThrottling() {
  const env_key = document.getElementById('throttle-key').value.trim();
  const rpm = parseInt(document.getElementById('throttle-rpm').value);
  const tpm = parseInt(document.getElementById('throttle-tpm').value);
  if (!env_key) { toast('Cle API requise', 'error'); return; }
  try {
    await api('/api/llm/providers/throttling', {
      method: 'PUT',
      body: { env_key, rpm, tpm },
    });
    toast('Throttling mis a jour', 'success');
    closeModal();
    loadCfgLLM();
  } catch (e) { toast(e.message, 'error'); }
}

async function deleteCfgThrottling(key) {
  if (!(await confirmModal(`Supprimer le throttling pour "${key}" ?`))) return;
  try {
    await api(`/api/llm/providers/throttling/${encodeURIComponent(key)}`, { method: 'DELETE' });
    toast('Throttling supprime', 'success');
    loadCfgLLM();
  } catch (e) { toast(e.message, 'error'); }
}

// ── Config MCP (catalog-based, mirrors Services MCP) ──
let cfgMcpCatalog = [];
let cfgMcpShowDeprecated = false;

async function loadCfgMCP() {
  try {
    const data = await api('/api/mcp/catalog');
    cfgMcpCatalog = data.servers || [];
    renderCfgMCP();
  } catch (e) { toast(e.message, 'error'); }
}

function renderCfgMCP() {
  const withParams = cfgMcpCatalog.filter(c => c.env_vars.length > 0 && c.installed);
  const noParams = cfgMcpCatalog.filter(c => c.env_vars.length === 0 && (cfgMcpShowDeprecated || !c.deprecated));

  // ── Top: Services with parameters ──
  const configuredEl = document.getElementById('cfg-mcp-configured');
  if (withParams.length === 0) {
    configuredEl.innerHTML = '<p style="color:var(--text-secondary);text-align:center;padding:1rem">Aucun service avec parametres.</p>';
  } else {
    configuredEl.innerHTML = `<table>
      <thead><tr><th>Service</th><th>Commande</th><th>Env</th><th>Agents</th><th>Actif</th><th>Actions</th></tr></thead>
      <tbody>${withParams.map(c => {
        const envStatus = c.env_vars.length === 0
          ? '<span class="tag tag-gray">aucune</span>'
          : c.env_vars.map(v =>
              `<span class="tag ${v.configured ? 'tag-green' : 'tag-red'}" title="${escHtml(v.desc)}">${escHtml(v.mapped_var || v.var)}</span>`
            ).join(' ');
        const agentTags = c.agents.length
          ? c.agents.map(a => `<span class="tag tag-blue">${escHtml(a)}</span>`).join(' ')
          : '<span style="color:var(--text-secondary);font-size:0.75rem">aucun</span>';
        return `<tr>
          <td>
            <strong>${escHtml(c.label)}</strong>
            <div style="font-size:0.7rem;color:var(--text-secondary)">${escHtml(c.id)}</div>
          </td>
          <td><code style="font-size:0.75rem">${escHtml(c.command)} ${escHtml(c.args)}</code></td>
          <td>${envStatus}</td>
          <td>${agentTags}</td>
          <td>
            ${c.installed
              ? `<div class="toggle ${c.enabled ? 'active' : ''}" onclick="toggleCfgMcp('${escHtml(c.id)}', ${!c.enabled})"></div>`
              : '<span class="tag tag-gray">non installe</span>'}
          </td>
          <td>
            ${c.installed
              ? `<button class="btn-icon" onclick="showCfgMCPEnvModal('${escHtml(c.id)}')" title="Configurer env">
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>
                </button>
                <button class="btn-icon danger" onclick="uninstallCfgMcp('${escHtml(c.id)}')" title="Desinstaller">
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>
                </button>`
              : `<button class="btn btn-sm btn-primary" onclick="showAddCfgCatalogModal('${escHtml(c.id)}')">Installer</button>`}
          </td>
        </tr>`;
      }).join('')}</tbody>
    </table>`;
  }

  // ── Bottom: Catalogue with Install / Activé buttons ──
  const catalogEl = document.getElementById('cfg-mcp-catalog');
  catalogEl.innerHTML = noParams.map(c => {
    let statusBtn;
    if (c.installed) {
      statusBtn = `<div class="toggle ${c.enabled ? 'active' : ''}" onclick="event.stopPropagation();toggleCfgMcp('${escHtml(c.id)}', ${!c.enabled})" style="cursor:pointer"></div>`;
    } else {
      statusBtn = `<button class="btn btn-sm btn-primary" onclick="event.stopPropagation();quickInstallCfgMcp('${escHtml(c.id)}')">Installer</button>`;
    }
    return `<div class="mcp-card${c.deprecated ? ' deprecated' : ''}">
      <div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:0.5rem">
        <div>
          <strong>${escHtml(c.label)}</strong>
          ${c.deprecated ? '<span class="tag tag-red" style="margin-left:0.5rem">deprecie</span>' : ''}
        </div>
        ${statusBtn}
      </div>
      <p style="font-size:0.8rem;color:var(--text-secondary);margin-bottom:0.5rem">${escHtml(c.description)}</p>
      <code style="font-size:0.7rem;color:var(--text-secondary)">${escHtml(c.command)} ${escHtml(c.args)}</code>
      ${c.env_vars.length ? `<div style="margin-top:0.5rem">${c.env_vars.map(v =>
        `<span class="tag ${v.configured ? 'tag-green' : 'tag-yellow'}" style="margin:0.1rem" title="${escHtml(v.desc)}">${escHtml(v.mapped_var || v.var)}</span>`
      ).join('')}</div>` : ''}
    </div>`;
  }).join('');
}

function showAddCfgCatalogModal(preselectedId) {
  const available = cfgMcpCatalog.filter(c => !c.installed && c.env_vars.length > 0);
  if (available.length === 0) {
    toast('Tous les services du catalogue sont deja installes', 'info');
    return;
  }
  const selected = preselectedId
    ? cfgMcpCatalog.find(c => c.id === preselectedId)
    : available[0];
  if (!selected) return;

  const options = available.map(c =>
    `<option value="${escHtml(c.id)}" ${c.id === selected.id ? 'selected' : ''}>${escHtml(c.label)} — ${escHtml(c.description)}</option>`
  ).join('');

  showModal(`
    <div class="modal-header">
      <h3>Installer un service MCP (config)</h3>
      <button class="btn-icon" onclick="closeModal()">&times;</button>
    </div>
    <div class="form-group">
      <label>Service</label>
      <select id="mcp-cfg-install-select" onchange="onCfgMCPServiceSelected()">
        ${options}
      </select>
    </div>
    <div id="mcp-cfg-install-details">${_renderInstallDetails(selected)}</div>
    <div class="modal-actions">
      <button class="btn btn-outline" onclick="closeModal()">Annuler</button>
      <button class="btn btn-primary" onclick="installCfgSelectedService()">Enregistrer</button>
    </div>
  `, 'modal-wide');
}

function onCfgMCPServiceSelected() {
  const id = document.getElementById('mcp-cfg-install-select').value;
  const item = cfgMcpCatalog.find(c => c.id === id);
  if (item) {
    document.getElementById('mcp-cfg-install-details').innerHTML = _renderInstallDetails(item);
  }
}

async function installCfgSelectedService() {
  const id = document.getElementById('mcp-cfg-install-select').value;
  const envMapping = {};
  document.querySelectorAll('.mcp-env-computed').forEach(el => {
    const base = el.getAttribute('data-base');
    envMapping[base] = el.textContent;
  });
  try {
    await api(`/api/mcp/install/${id}`, { method: 'POST', body: { env_values: {}, env_mapping: envMapping } });
    toast('Service MCP installe', 'success');
    closeModal();
    loadCfgMCP();
  } catch (e) { toast(e.message, 'error'); }
}

async function uninstallCfgMcp(id) {
  if (!(await confirmModal(`Desinstaller le serveur MCP "${id}" ?`))) return;
  try {
    await api(`/api/mcp/uninstall/${id}`, { method: 'POST' });
    toast('Serveur MCP desinstalle', 'success');
    loadCfgMCP();
  } catch (e) { toast(e.message, 'error'); }
}

async function toggleCfgMcp(id, enabled) {
  try {
    await api(`/api/mcp/toggle/${id}`, { method: 'PUT', body: { enabled } });
    loadCfgMCP();
  } catch (e) { toast(e.message, 'error'); }
}

function showCfgMCPEnvModal(id) {
  const item = cfgMcpCatalog.find(c => c.id === id);
  if (!item || !item.env_vars.length) {
    toast('Aucune variable d\'environnement pour ce serveur', 'info');
    return;
  }
  showModal(`
    <div class="modal-header">
      <h3>Env : ${escHtml(item.label)} (config)</h3>
      <button class="btn-icon" onclick="closeModal()">&times;</button>
    </div>
    <div class="env-var-list">
      ${item.env_vars.map(v => `
        <div class="env-var-row">
          <div class="env-var-info">
            <code>${escHtml(v.mapped_var || v.var)}</code>
            <span class="env-var-desc">${escHtml(v.desc)}</span>
            ${v.configured
              ? '<span class="tag tag-green">configure</span>'
              : '<span class="tag tag-red">manquant</span>'}
          </div>
          <div class="env-var-action">
            <input class="mcp-env-field" data-var="${escHtml(v.mapped_var || v.var)}" placeholder="Nouvelle valeur..." />
            <button class="btn btn-sm btn-outline" onclick="setEnvVarFromInstall('${escHtml(v.mapped_var || v.var)}', this)" title="Enregistrer dans .env">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z"/><polyline points="17 21 17 13 7 13 7 21"/><polyline points="7 3 7 8 15 8"/></svg>
            </button>
          </div>
        </div>
      `).join('')}
    </div>
    <div class="modal-actions">
      <button class="btn btn-outline" onclick="closeModal()">Fermer</button>
    </div>
  `);
}

function toggleCfgDeprecated() {
  cfgMcpShowDeprecated = !cfgMcpShowDeprecated;
  const btn = document.getElementById('btn-cfg-show-deprecated');
  btn.textContent = cfgMcpShowDeprecated ? 'Masquer deprecies' : 'Afficher deprecies';
  renderCfgMCP();
}

async function copyCfgMCPFromTemplate() {
  try {
    const tplData = await api('/api/templates/mcp');
    const tplServers = tplData.servers || {};
    const cfgData = await api('/api/mcp/cfg-servers');
    const cfgServers = cfgData.servers || {};

    const missing = Object.entries(tplServers).filter(([id]) => !cfgServers[id]);
    if (missing.length === 0) {
      toast('Aucun service MCP manquant a copier', 'info');
      return;
    }

    // Copy servers directly (preserves args, params, etc.)
    await api('/api/mcp/copy-from-template', {
      method: 'POST',
      body: { server_ids: missing.map(([id]) => id) },
    });

    toast(`${missing.length} service(s) MCP copie(s) depuis le template`, 'success');
    loadCfgMCP();
  } catch (e) { toast(e.message, 'error'); }
}

// ── Config Teams (sub-tab) ────────────────────────
async function loadCfgTeams() {
  try {
    const data = await api('/api/teams');
    teamsData = data.teams || [];
    renderTeams();
  } catch (e) { toast(e.message, 'error'); }
}

// ── Config Git (Enregistrement) — delegates to factorized functions ──

// ═══════════════════════════════════════════════════
// TEMPLATES (sub-tabs: LLM, MCP, Teams)
// ═══════════════════════════════════════════════════
let tplLlmData = {};
let tplMcpData = {};
let tplTeamsData = { teams: [], channel_mapping: {} };

function showTemplateTab(tabId) {
  document.querySelectorAll('.tpl-tab-content').forEach(c => c.classList.remove('active'));
  document.querySelectorAll('[data-tpl-tab]').forEach(t => t.classList.remove('active'));
  document.getElementById('tpl-tab-' + tabId).classList.add('active');
  document.querySelector(`[data-tpl-tab="${tabId}"]`).classList.add('active');
  if (tabId === 'tpl-llm') loadTplLLM();
  else if (tabId === 'tpl-mcp') loadTplMCP();
  else if (tabId === 'tpl-agents') loadSharedAgents();
  else if (tabId === 'tpl-teams') loadTplTeamsList();
  else if (tabId === 'tpl-git') loadTplGit();
}

async function loadTemplates() {
  // Load active sub-tab
  const active = document.querySelector('[data-tpl-tab].active');
  const tab = active ? active.getAttribute('data-tpl-tab') : 'tpl-llm';
  showTemplateTab(tab);
}

// ── Shared Agents (Shared/Agents/{id}/) ──────────

let sharedAgentsData = [];
let saSelectedId = '';

async function loadSharedAgents() {
  try {
    const data = await api('/api/shared-agents');
    sharedAgentsData = (data.agents || []).sort((a, b) => (a.name || a.id).localeCompare(b.name || b.id, 'fr'));
  } catch { sharedAgentsData = []; }
  const prev = saSelectedId;
  const input = document.getElementById('sa-agent-filter');
  if (prev && sharedAgentsData.find(a => a.id === prev)) {
    const ag = sharedAgentsData.find(a => a.id === prev);
    input.value = ag.name || ag.id;
    selectSharedAgent(prev);
  } else {
    input.value = '';
    saSelectedId = '';
    document.getElementById('sa-agent-detail').innerHTML = '';
    _updateSaDeleteBtn();
  }
  _renderSaDropdown(sharedAgentsData);
}

function _renderSaDropdown(list) {
  const dd = document.getElementById('sa-agent-dropdown');
  dd.innerHTML = list.map(a =>
    `<div class="sa-dropdown-item${a.id === saSelectedId ? ' active' : ''}" data-id="${escHtml(a.id)}" onclick="_pickSharedAgent('${escHtml(a.id)}')">${escHtml(a.name || a.id)}</div>`
  ).join('') || '<div style="padding:8px;color:var(--text-muted);font-size:0.85rem">Aucun agent</div>';
}

function _filterSharedAgents() {
  const q = (document.getElementById('sa-agent-filter').value || '').toLowerCase();
  const filtered = sharedAgentsData.filter(a => (a.name || a.id).toLowerCase().includes(q) || a.id.toLowerCase().includes(q));
  _renderSaDropdown(filtered);
  _openSaDropdown();
}

function _openSaDropdown() {
  document.getElementById('sa-agent-dropdown').style.display = 'block';
}

function _closeSaDropdown() {
  setTimeout(() => { document.getElementById('sa-agent-dropdown').style.display = 'none'; }, 180);
}

function _toggleSaDropdown() {
  const dd = document.getElementById('sa-agent-dropdown');
  dd.style.display = dd.style.display === 'none' ? 'block' : 'none';
  if (dd.style.display === 'block') document.getElementById('sa-agent-filter').focus();
}

function _pickSharedAgent(id) {
  const ag = sharedAgentsData.find(a => a.id === id);
  document.getElementById('sa-agent-filter').value = ag ? (ag.name || ag.id) : id;
  document.getElementById('sa-agent-dropdown').style.display = 'none';
  selectSharedAgent(id);
}

function _updateSaDeleteBtn() {
  const btn = document.getElementById('sa-delete-btn');
  if (!btn) return;
  btn.disabled = !saSelectedId;
  btn.style.opacity = saSelectedId ? '1' : '0.5';
}

async function selectSharedAgent(id) {
  saSelectedId = id;
  _updateSaDeleteBtn();
  const detail = document.getElementById('sa-agent-detail');
  if (!id) { detail.innerHTML = ''; return; }
  let agent;
  try { agent = await api(`/api/shared-agents/${encodeURIComponent(id)}`); }
  catch (e) { toast(e.message, 'error'); return; }

  let llmNames = [], mcpInstalled = [];
  try { const d = await api('/api/templates/llm'); llmNames = Object.keys(d.providers || {}); } catch {}
  try { const d = await api('/api/mcp/servers'); mcpInstalled = Object.keys(d.servers || {}); } catch {}

  const llmOptions = '<option value="">-- Defaut --</option>' +
    llmNames.map(p => `<option value="${escHtml(p)}" ${p === (agent.llm || '') ? 'selected' : ''}>${escHtml(p)}</option>`).join('');
  const agentMcp = agent.mcp_access || [];
  const mcpTags = mcpInstalled.length
    ? mcpInstalled.map(id => {
        const chk = agentMcp.includes(id) ? 'checked' : '';
        return `<label class="mcp-check-tag ${chk ? 'active' : ''}"><input type="checkbox" value="${escHtml(id)}" ${chk} onchange="this.parentElement.classList.toggle('active',this.checked)" />${escHtml(id)}</label>`;
      }).join('')
    : '<span style="color:var(--text-secondary);font-size:0.85rem">Aucun serveur MCP installe</span>';

  const promptRaw = agent.prompt_content || '';
  const assignRaw = agent.assign_content || '';
  const unassignRaw = agent.unassign_content || '';

  detail.innerHTML = `
    <div class="prompt-tabs" style="margin-top:0.75rem">
      <div class="prompt-tab active" id="sa-tab-info" onclick="showSaSubTab('info')">Signaletique</div>
      <div class="prompt-tab" id="sa-tab-prompt" onclick="showSaSubTab('prompt')">Prompt</div>
      <div class="prompt-tab" id="sa-tab-assign" onclick="showSaSubTab('assign')">Assignations</div>
    </div>
    <div id="sa-subtab-info" style="padding:1rem 0">
      <div class="form-row">
        <div class="form-group"><label>ID</label><input id="sa-id" value="${escHtml(id)}" readonly style="background:var(--bg-secondary)" /></div>
        <div class="form-group"><label>Nom</label><input id="sa-name" value="${escHtml(agent.name || '')}" /></div>
      </div>
      <div class="form-group"><label>Description</label><textarea id="sa-desc" style="min-height:60px">${escHtml(agent.description || '')}</textarea></div>
      <div class="form-row">
        <div class="form-group"><label>Modele LLM</label><select id="sa-llm">${llmOptions}</select></div>
        <div class="form-group"><label>Temperature</label><input id="sa-temp" type="number" step="0.1" min="0" max="2" value="${agent.temperature ?? 0.3}" /></div>
        <div class="form-group"><label>Max Tokens</label><input id="sa-tokens" type="number" value="${agent.max_tokens ?? 32768}" /></div>
      </div>
      <div class="form-group">
        <label>Services MCP</label>
        <div class="mcp-check-tags" id="sa-mcp-tags">${mcpTags}</div>
      </div>
      <div class="form-group">
        <label>Type de livrable</label>
        <div style="display:flex;gap:1.5rem;margin-top:0.25rem">
          <label style="display:flex;align-items:center;gap:0.4rem;font-size:0.85rem;cursor:pointer">
            <input type="checkbox" id="sa-delivers-docs" ${agent.delivers_docs ? 'checked' : ''} /> Documentation
          </label>
          <label style="display:flex;align-items:center;gap:0.4rem;font-size:0.85rem;cursor:pointer">
            <input type="checkbox" id="sa-delivers-code" ${agent.delivers_code ? 'checked' : ''} /> Code
          </label>
        </div>
      </div>
      <div style="text-align:right;margin-top:1rem">
        <button class="btn btn-primary btn-sm" onclick="saveSharedAgent('${escHtml(id)}')">Sauvegarder</button>
      </div>
    </div>
    <div id="sa-subtab-prompt" style="padding:1rem 0;display:none">
      <div style="display:flex;justify-content:flex-end;margin-bottom:0.5rem">
        <button class="btn btn-outline btn-sm" onclick="generateSharedAgentPrompt('${escHtml(id)}')">Aide moi a creer mon agent</button>
      </div>
      <textarea id="sa-prompt-edit" style="min-height:400px;max-height:60vh;overflow-y:auto">${escHtml(promptRaw)}</textarea>
      <div style="text-align:right;margin-top:1rem">
        <button class="btn btn-primary btn-sm" onclick="saveSharedAgent('${escHtml(id)}')">Sauvegarder</button>
      </div>
    </div>
    <div id="sa-subtab-assign" style="padding:1rem 0;display:none">
      <div style="display:flex;justify-content:flex-end;margin-bottom:0.75rem">
        <button class="btn btn-outline btn-sm" id="sa-btn-gen-assign" onclick="generateSharedAgentAssign('${escHtml(id)}')">Generer les exemples d'assignation</button>
      </div>
      <div class="form-group">
        <label>Exemples de routing correct</label>
        <textarea id="sa-assign-edit" style="min-height:200px;max-height:30vh;overflow-y:auto">${escHtml(assignRaw)}</textarea>
      </div>
      <div style="display:flex;justify-content:flex-end;margin-top:1rem;margin-bottom:0.25rem">
        <button class="btn btn-outline btn-sm" id="sa-btn-gen-unassign" onclick="generateSharedAgentUnassign('${escHtml(id)}')">Generer les exemples de non-assignation</button>
      </div>
      <div class="form-group">
        <label>Exemples de routing incorrect</label>
        <textarea id="sa-unassign-edit" style="min-height:200px;max-height:30vh;overflow-y:auto">${escHtml(unassignRaw)}</textarea>
      </div>
      <div style="text-align:right;margin-top:1rem">
        <button class="btn btn-primary btn-sm" onclick="saveSharedAgentAssign('${escHtml(id)}')">Sauvegarder</button>
      </div>
    </div>`;
}

function showSaSubTab(tab) {
  document.getElementById('sa-subtab-info').style.display = tab === 'info' ? '' : 'none';
  document.getElementById('sa-subtab-prompt').style.display = tab === 'prompt' ? '' : 'none';
  document.getElementById('sa-subtab-assign').style.display = tab === 'assign' ? '' : 'none';
  document.getElementById('sa-tab-info').classList.toggle('active', tab === 'info');
  document.getElementById('sa-tab-prompt').classList.toggle('active', tab === 'prompt');
  document.getElementById('sa-tab-assign').classList.toggle('active', tab === 'assign');
}

async function saveSharedAgentAssign(id) {
  const assignContent = document.getElementById('sa-assign-edit').value;
  const unassignContent = document.getElementById('sa-unassign-edit').value;
  try {
    await api(`/api/shared-agents/${encodeURIComponent(id)}`, { method: 'PUT', body: {
      id,
      name: document.getElementById('sa-name').value.trim(),
      assign_content: assignContent,
      unassign_content: unassignContent,
    }});
    toast('Assignations sauvegardees', 'success');
  } catch (e) { toast(e.message, 'error'); }
}

async function generateSharedAgentAssign(id) {
  const name = document.getElementById('sa-name')?.value || id;
  const prompt = document.getElementById('sa-prompt-edit')?.value || '';
  const editor = document.getElementById('sa-assign-edit');
  const btn = document.getElementById('sa-btn-gen-assign');
  const savedContent = editor.value;
  const savedBtn = btn.innerHTML;
  btn.disabled = true; btn.innerHTML = '<span class="spinner"></span> Generation...';
  editor.disabled = true; editor.value = 'Generation en cours...';
  try {
    const result = await api('/api/agents/generate-assign', { method: 'POST', body: {
      agent_id: id, agent_name: name, agent_prompt: prompt
    }});
    editor.disabled = false;
    editor.value = result.content || '';
    toast('Exemples d\'assignation generes', 'success');
  } catch (e) {
    editor.disabled = false; editor.value = savedContent;
    toast(e.message, 'error');
  } finally { btn.disabled = false; btn.innerHTML = savedBtn; }
}

async function generateSharedAgentUnassign(id) {
  const name = document.getElementById('sa-name')?.value || id;
  const prompt = document.getElementById('sa-prompt-edit')?.value || '';
  const editor = document.getElementById('sa-unassign-edit');
  const btn = document.getElementById('sa-btn-gen-unassign');
  const savedContent = editor.value;
  const savedBtn = btn.innerHTML;
  btn.disabled = true; btn.innerHTML = '<span class="spinner"></span> Generation...';
  editor.disabled = true; editor.value = 'Generation en cours...';
  try {
    const result = await api('/api/agents/generate-unassign', { method: 'POST', body: {
      agent_id: id, agent_name: name, agent_prompt: prompt
    }});
    editor.disabled = false;
    editor.value = result.content || '';
    toast('Exemples de non-assignation generes', 'success');
  } catch (e) {
    editor.disabled = false; editor.value = savedContent;
    toast(e.message, 'error');
  } finally { btn.disabled = false; btn.innerHTML = savedBtn; }
}

// switchSaPromptTab removed — prompt tab is now editor-only

function showCreateSharedAgentModal() {
  showModal(`
    <div class="modal-header">
      <h3>Nouvel agent</h3>
      <button class="btn-icon" onclick="closeModal()">&times;</button>
    </div>
    <div class="form-group">
      <label>ID unique (lettres, chiffres, _)</label>
      <input id="sa-new-id" placeholder="mon_agent" pattern="[a-zA-Z0-9_]+" oninput="this.value=this.value.replace(/[^a-zA-Z0-9_]/g,'')" />
    </div>
    <div class="modal-actions">
      <button class="btn btn-outline" onclick="closeModal()">Annuler</button>
      <button class="btn btn-primary" onclick="createSharedAgent()">Creer</button>
    </div>
  `);
}

async function createSharedAgent() {
  const id = (document.getElementById('sa-new-id').value || '').trim();
  if (!id) { toast('ID requis', 'error'); return; }
  if (!/^[a-zA-Z0-9_]+$/.test(id)) { toast('ID invalide (lettres, chiffres, _ uniquement)', 'error'); return; }
  try {
    await api('/api/shared-agents', { method: 'POST', body: { id, name: id } });
    toast('Agent cree', 'success');
    closeModal();
    saSelectedId = id;
    loadSharedAgents();
  } catch (e) { toast(e.message, 'error'); }
}

async function saveSharedAgent(id) {
  const name = (document.getElementById('sa-name')?.value || '').trim();
  const description = document.getElementById('sa-desc')?.value || '';
  const llm = document.getElementById('sa-llm')?.value || '';
  const temperature = parseFloat(document.getElementById('sa-temp')?.value) || 0.3;
  const max_tokens = parseInt(document.getElementById('sa-tokens')?.value) || 32768;
  const prompt_content = document.getElementById('sa-prompt-edit')?.value || '';
  const mcp_access = [...document.querySelectorAll('#sa-mcp-tags input[type=checkbox]:checked')].map(cb => cb.value);
  const delivers_docs = document.getElementById('sa-delivers-docs')?.checked || false;
  const delivers_code = document.getElementById('sa-delivers-code')?.checked || false;
  if (!name) { toast('Nom requis', 'error'); return; }
  try {
    await api(`/api/shared-agents/${encodeURIComponent(id)}`, { method: 'PUT', body: {
      id, name, description, llm, temperature, max_tokens, mcp_access, prompt_content, delivers_docs, delivers_code
    }});
    toast('Agent sauvegarde', 'success');
    // Update dropdown + filter input without reloading detail (preserves active tab)
    const ag = sharedAgentsData.find(a => a.id === id);
    if (ag) ag.name = name;
    document.getElementById('sa-agent-filter').value = name || id;
    _renderSaDropdown(sharedAgentsData);
  } catch (e) { toast(e.message, 'error'); }
}

async function deleteSharedAgent(id) {
  if (!id) return;
  if (!(await confirmModal(`Supprimer l'agent "${id}" ?`))) return;
  try {
    await api(`/api/shared-agents/${encodeURIComponent(id)}`, { method: 'DELETE' });
    toast('Agent supprime', 'success');
    saSelectedId = '';
    loadSharedAgents();
  } catch (e) { toast(e.message, 'error'); }
}

function importSharedAgent() {
  const input = document.createElement('input');
  input.type = 'file';
  input.accept = '.zip';
  input.onchange = async () => {
    const file = input.files[0];
    if (!file) return;
    const form = new FormData();
    form.append('file', file);
    try {
      const res = await fetch('/api/shared-agents/import', { method: 'POST', body: form });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Erreur import');
      if (data.conflict) {
        // ID already exists — ask for a new name
        _showImportRenameModal(file, data.existing_id);
        return;
      }
      toast(`Agent "${data.id}" importe`, 'success');
      saSelectedId = data.id;
      loadSharedAgents();
    } catch (e) { toast(e.message, 'error'); }
  };
  input.click();
}

function _showImportRenameModal(file, existingId) {
  showModal(`
    <div class="modal-header">
      <h3>Agent "${existingId}" existe deja</h3>
      <button class="btn-icon" onclick="closeModal()">&times;</button>
    </div>
    <div class="form-group">
      <label>Choisir un nouvel ID</label>
      <input id="sa-import-rename" placeholder="nouvel_id" oninput="this.value=this.value.replace(/[^a-zA-Z0-9_]/g,'')" />
    </div>
    <div class="modal-actions">
      <button class="btn btn-outline" onclick="closeModal()">Annuler</button>
      <button class="btn btn-primary" id="sa-import-rename-btn">Importer</button>
    </div>
  `);
  // Store file ref and wire up button
  document.getElementById('sa-import-rename-btn').onclick = async () => {
    const newId = (document.getElementById('sa-import-rename').value || '').trim();
    if (!newId) { toast('ID requis', 'error'); return; }
    if (!/^[a-zA-Z0-9_]+$/.test(newId)) { toast('ID invalide', 'error'); return; }
    const form = new FormData();
    form.append('file', file);
    try {
      const res = await fetch(`/api/shared-agents/import?agent_id=${encodeURIComponent(newId)}`, { method: 'POST', body: form });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Erreur import');
      if (data.conflict) { toast(`L'agent "${newId}" existe aussi`, 'error'); return; }
      toast(`Agent "${data.id}" importe`, 'success');
      closeModal();
      saSelectedId = data.id;
      loadSharedAgents();
    } catch (e) { toast(e.message, 'error'); }
  };
}

async function generateSharedAgentPrompt(id) {
  const name = document.getElementById('sa-name')?.value || id;
  const desc = document.getElementById('sa-desc')?.value || '';
  const info = `Identifiant: ${id}\nNom: ${name}\nDescription: ${desc}`;
  const editor = document.getElementById('sa-prompt-edit');
  const btn = document.querySelector('[onclick*="generateSharedAgentPrompt"]');
  const savedContent = editor.value;
  const savedBtn = btn ? btn.innerHTML : '';
  editor.value = 'Generation en cours...';
  editor.disabled = true;
  if (btn) {
    btn.disabled = true;
    btn.innerHTML = '<span class="spinner"></span> Generation...';
  }
  try {
    const result = await api('/api/agents/generate-prompt', { method: 'POST', body: {
      agent_id: id, agent_name: name, agent_info: info
    }});
    editor.disabled = false;
    editor.value = result.prompt || '';
    toast('Prompt genere', 'success');
  } catch (e) {
    editor.disabled = false;
    editor.value = savedContent;
    toast(e.message, 'error');
  } finally {
    editor.disabled = false;
    if (btn) { btn.disabled = false; btn.innerHTML = savedBtn; }
  }
}

// ── Template Git (Enregistrement) — delegates to factorized functions ──

// ── Template LLM ──────────────────────────────────
async function loadTplLLM() {
  try {
    tplLlmData = await api('/api/templates/llm');
    renderTplLLM();
  } catch (e) { toast(e.message, 'error'); }
}

function renderTplLLM() {
  const providers = tplLlmData.providers || {};
  const throttling = tplLlmData.throttling || {};
  const defaultId = tplLlmData.default || '';

  // Default select
  const sel = document.getElementById('tpl-llm-default-select');
  sel.innerHTML = `<option value="">-- Aucun --</option>` +
    Object.entries(providers).map(([id, p]) =>
      `<option value="${escHtml(id)}" ${id === defaultId ? 'selected' : ''}>${escHtml(id)} — ${escHtml(p.description || p.model)}</option>`
    ).join('');

  // Providers table
  const tbl = document.getElementById('tpl-llm-providers-table');
  if (Object.keys(providers).length === 0) {
    tbl.innerHTML = '<p style="color:var(--text-secondary);text-align:center;padding:1rem">Aucun provider configure.</p>';
  } else {
    tbl.innerHTML = `<table>
      <thead><tr><th>ID</th><th>Type</th><th>Modele</th><th>URL</th><th>Cle API</th><th>Description</th><th style="width:130px">Actions</th></tr></thead>
      <tbody>${Object.entries(providers).map(([id, p]) => {
        const isDefault = id === defaultId;
        const url = p.base_url || p.azure_endpoint || '';
        return `<tr>
          <td><strong>${escHtml(id)}</strong>${isDefault ? '<span class="tag tag-green" style="margin-left:0.5rem">defaut</span>' : ''}</td>
          <td><span class="tag tag-blue">${escHtml(p.type)}</span></td>
          <td><code style="font-size:0.8rem">${escHtml(p.model)}</code></td>
          <td>${url ? `<code style="font-size:0.75rem">${escHtml(url)}</code>` : '<span style="color:var(--text-secondary)">—</span>'}</td>
          <td>${p.env_key ? `<code style="font-size:0.75rem">${escHtml(p.env_key)}</code>` : '<span style="color:var(--text-secondary)">—</span>'}</td>
          <td style="font-size:0.8rem;color:var(--text-secondary)">${escHtml(p.description || '')}</td>
          <td>
            <button class="btn-icon" onclick="cloneTplProvider('${escHtml(id)}')" title="Cloner">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>
            </button>
            <button class="btn-icon" onclick="editTplProvider('${escHtml(id)}')" title="Modifier">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>
            </button>
            <button class="btn-icon danger" onclick="deleteTplProvider('${escHtml(id)}')" title="Supprimer">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>
            </button>
          </td>
        </tr>`;
      }).join('')}</tbody>
    </table>`;
  }

  // Throttling table
  const ttbl = document.getElementById('tpl-llm-throttling-table');
  if (Object.keys(throttling).length === 0) {
    ttbl.innerHTML = '<p style="color:var(--text-secondary);text-align:center;padding:1rem">Aucune regle de throttling.</p>';
  } else {
    ttbl.innerHTML = `<table>
      <thead><tr><th>Cle API</th><th>RPM</th><th>TPM</th><th style="width:100px">Actions</th></tr></thead>
      <tbody>${Object.entries(throttling).map(([key, t]) => `<tr>
        <td><code>${escHtml(key)}</code></td>
        <td>${t.rpm}</td>
        <td>${t.tpm.toLocaleString()}</td>
        <td>
          <button class="btn-icon" onclick="editTplThrottling('${escHtml(key)}', ${t.rpm}, ${t.tpm})" title="Modifier">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>
          </button>
          <button class="btn-icon danger" onclick="deleteTplThrottling('${escHtml(key)}')" title="Supprimer">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>
          </button>
        </td>
      </tr>`).join('')}</tbody>
    </table>`;
  }
  filterTplLLM();
}

function filterTplLLM() {
  const q = (document.getElementById('tpl-llm-filter')?.value || '').toLowerCase();
  document.querySelectorAll('#tpl-llm-providers-table tbody tr').forEach(tr => {
    tr.style.display = tr.textContent.toLowerCase().includes(q) ? '' : 'none';
  });
}

async function setTplLLMDefault(providerId) {
  tplLlmData.default = providerId;
  try {
    await api('/api/templates/llm', { method: 'PUT', body: tplLlmData });
    toast('Modele par defaut du template mis a jour', 'success');
    loadTplLLM();
  } catch (e) { toast(e.message, 'error'); }
}

function uploadTplLLM() {
  const input = document.createElement('input');
  input.type = 'file';
  input.accept = '.json';
  input.onchange = async () => {
    const file = input.files[0];
    if (!file) return;
    const form = new FormData();
    form.append('file', file);
    try {
      const res = await fetch('/api/templates/llm/upload', { method: 'POST', body: form });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Erreur upload');
      await loadTplLLM();
      if (data.conflicts && data.conflicts.length > 0) {
        showLlmConflictsModal(data.conflicts, '/api/templates/llm/resolve', loadTplLLM, data);
      } else {
        _llmUploadToast(data);
      }
    } catch (e) { toast(e.message, 'error'); }
  };
  input.click();
}

function cloneTplProvider(id) {
  const p = tplLlmData.providers[id];
  if (!p) return;
  const newId = _uniqueProviderId(id, tplLlmData.providers);
  showModal(`
    <div class="modal-header">
      <h3>Cloner provider (template)</h3>
      <button class="btn-icon" onclick="closeModal()">&times;</button>
    </div>
    <div class="form-row">
      <div class="form-group"><label>ID (unique)</label><input id="prov-id" value="${escHtml(newId)}" /></div>
      <div class="form-group"><label>Type</label>
        <select id="prov-type" onchange="_updateProviderTypeFields()">
          ${LLM_TYPES.map(t => `<option value="${t}" ${t === p.type ? 'selected' : ''}>${t}</option>`).join('')}
        </select>
      </div>
    </div>
    <div class="form-row">
      <div class="form-group"><label>Modele</label><input id="prov-model" value="${escHtml(p.model)}" /></div>
      <div class="form-group"><label>Cle API (env var)</label><input id="prov-envkey" value="${escHtml(p.env_key || '')}" /></div>
    </div>
    <div class="form-row">
      <div class="form-group"><label>Description</label><input id="prov-desc" value="${escHtml(p.description || '')}" /></div>
      <div class="form-group"><label>Base URL</label><input id="prov-base-url" value="${escHtml(p.base_url || '')}" placeholder="https://..." /></div>
    </div>
    ${_providerTypeFields(p.type, p)}
    <div class="modal-actions">
      <button class="btn btn-outline" onclick="closeModal()">Annuler</button>
      <button class="btn btn-primary" onclick="addTplProvider()">Ajouter</button>
    </div>
  `);
}

function showAddTplProviderModal() {
  showModal(`
    <div class="modal-header">
      <h3>Ajouter un provider (template)</h3>
      <button class="btn-icon" onclick="closeModal()">&times;</button>
    </div>
    <div class="form-row">
      <div class="form-group"><label>ID (unique)</label><input id="prov-id" placeholder="mon-modele" /></div>
      <div class="form-group"><label>Type</label>
        <select id="prov-type" onchange="_updateProviderTypeFields()">
          ${LLM_TYPES.map(t => `<option value="${t}">${t}</option>`).join('')}
        </select>
      </div>
    </div>
    <div class="form-row">
      <div class="form-group"><label>Modele</label><input id="prov-model" placeholder="gpt-4o, claude-sonnet-4-5..." /></div>
      <div class="form-group"><label>Cle API (env var)</label><input id="prov-envkey" placeholder="OPENAI_API_KEY" /></div>
    </div>
    <div class="form-row">
      <div class="form-group"><label>Description</label><input id="prov-desc" placeholder="Description du modele" /></div>
      <div class="form-group"><label>Base URL</label><input id="prov-base-url" value="" placeholder="https://..." /></div>
    </div>
    ${_providerTypeFields('anthropic')}
    <div class="modal-actions">
      <button class="btn btn-outline" onclick="closeModal()">Annuler</button>
      <button class="btn btn-primary" onclick="addTplProvider()">Ajouter</button>
    </div>
  `);
}

function _readProviderForm() {
  const id = document.getElementById('prov-id').value.trim();
  const type = document.getElementById('prov-type').value;
  const model = document.getElementById('prov-model').value.trim();
  const env_key = document.getElementById('prov-envkey').value.trim();
  const description = document.getElementById('prov-desc').value.trim();
  const base_url = (document.getElementById('prov-base-url')?.value || '').trim();
  const prov = { type, model, description };
  if (env_key) prov.env_key = env_key;
  if (base_url) prov.base_url = base_url;
  if (type === 'azure') {
    const ae = (document.getElementById('prov-azure-endpoint')?.value || '').trim();
    const ad = (document.getElementById('prov-azure-deployment')?.value || '').trim();
    const av = (document.getElementById('prov-api-version')?.value || '').trim();
    if (ae) prov.azure_endpoint = ae;
    if (ad) prov.azure_deployment = ad;
    if (av) prov.api_version = av;
  }
  return { id, prov };
}

async function addTplProvider() {
  const { id, prov } = _readProviderForm();
  if (!id || !prov.model) { toast('ID et modele requis', 'error'); return; }
  if (!tplLlmData.providers) tplLlmData.providers = {};
  if (tplLlmData.providers[id]) { toast(`Provider "${id}" existe deja`, 'error'); return; }
  tplLlmData.providers[id] = prov;
  try {
    await api('/api/templates/llm', { method: 'PUT', body: tplLlmData });
    toast('Provider ajoute au template', 'success');
    closeModal();
    loadTplLLM();
  } catch (e) { toast(e.message, 'error'); }
}

function editTplProvider(id) {
  const p = tplLlmData.providers[id];
  if (!p) return;
  showModal(`
    <div class="modal-header">
      <h3>Modifier (template) : ${escHtml(id)}</h3>
      <button class="btn-icon" onclick="closeModal()">&times;</button>
    </div>
    <div class="form-row">
      <div class="form-group"><label>ID</label><input id="prov-id" value="${escHtml(id)}" /></div>
      <div class="form-group"><label>Type</label>
        <select id="prov-type" onchange="_updateProviderTypeFields()">
          ${LLM_TYPES.map(t => `<option value="${t}" ${t === p.type ? 'selected' : ''}>${t}</option>`).join('')}
        </select>
      </div>
    </div>
    <div class="form-row">
      <div class="form-group"><label>Modele</label><input id="prov-model" value="${escHtml(p.model)}" /></div>
      <div class="form-group"><label>Cle API (env var)</label><input id="prov-envkey" value="${escHtml(p.env_key || '')}" /></div>
    </div>
    <div class="form-row">
      <div class="form-group"><label>Description</label><input id="prov-desc" value="${escHtml(p.description || '')}" /></div>
      <div class="form-group"><label>Base URL</label><input id="prov-base-url" value="${escHtml(p.base_url || '')}" placeholder="https://..." /></div>
    </div>
    ${_providerTypeFields(p.type, p)}
    <div class="modal-actions">
      <button class="btn btn-outline" onclick="closeModal()">Annuler</button>
      <button class="btn btn-primary" onclick="saveTplProvider('${escHtml(id)}')">Sauvegarder</button>
    </div>
  `);
}

async function saveTplProvider(originalId) {
  const { id, prov } = _readProviderForm();
  if (!id || !prov.model) { toast('ID et modele requis', 'error'); return; }
  if (id !== originalId) {
    delete tplLlmData.providers[originalId];
    if (tplLlmData.default === originalId) tplLlmData.default = id;
  }
  tplLlmData.providers[id] = prov;
  try {
    await api('/api/templates/llm', { method: 'PUT', body: tplLlmData });
    toast('Provider mis a jour', 'success');
    closeModal();
    loadTplLLM();
  } catch (e) { toast(e.message, 'error'); }
}

async function deleteTplProvider(id) {
  if (!(await confirmModal(`Supprimer le provider "${id}" du template ?`))) return;
  delete tplLlmData.providers[id];
  if (tplLlmData.default === id) tplLlmData.default = '';
  try {
    await api('/api/templates/llm', { method: 'PUT', body: tplLlmData });
    toast('Provider supprime du template', 'success');
    loadTplLLM();
  } catch (e) { toast(e.message, 'error'); }
}

function showAddTplThrottlingModal() {
  showModal(`
    <div class="modal-header">
      <h3>Ajouter throttling (template)</h3>
      <button class="btn-icon" onclick="closeModal()">&times;</button>
    </div>
    <div class="form-group"><label>Cle API (env var)</label><input id="throttle-key" placeholder="OPENAI_API_KEY" /></div>
    <div class="form-row">
      <div class="form-group"><label>RPM (requetes/min)</label><input id="throttle-rpm" type="number" value="60" /></div>
      <div class="form-group"><label>TPM (tokens/min)</label><input id="throttle-tpm" type="number" value="60000" /></div>
    </div>
    <div class="modal-actions">
      <button class="btn btn-outline" onclick="closeModal()">Annuler</button>
      <button class="btn btn-primary" onclick="saveTplThrottling()">Ajouter</button>
    </div>
  `);
}

function editTplThrottling(key, rpm, tpm) {
  showModal(`
    <div class="modal-header">
      <h3>Modifier throttling (template) : ${escHtml(key)}</h3>
      <button class="btn-icon" onclick="closeModal()">&times;</button>
    </div>
    <div class="form-group"><label>Cle API</label><input id="throttle-key" value="${escHtml(key)}" disabled style="opacity:0.5" /></div>
    <div class="form-row">
      <div class="form-group"><label>RPM (requetes/min)</label><input id="throttle-rpm" type="number" value="${rpm}" /></div>
      <div class="form-group"><label>TPM (tokens/min)</label><input id="throttle-tpm" type="number" value="${tpm}" /></div>
    </div>
    <div class="modal-actions">
      <button class="btn btn-outline" onclick="closeModal()">Annuler</button>
      <button class="btn btn-primary" onclick="saveTplThrottling()">Sauvegarder</button>
    </div>
  `);
}

async function saveTplThrottling() {
  const env_key = document.getElementById('throttle-key').value.trim();
  const rpm = parseInt(document.getElementById('throttle-rpm').value);
  const tpm = parseInt(document.getElementById('throttle-tpm').value);
  if (!env_key) { toast('Cle API requise', 'error'); return; }
  if (!tplLlmData.throttling) tplLlmData.throttling = {};
  tplLlmData.throttling[env_key] = { rpm, tpm };
  try {
    await api('/api/templates/llm', { method: 'PUT', body: tplLlmData });
    toast('Throttling template mis a jour', 'success');
    closeModal();
    loadTplLLM();
  } catch (e) { toast(e.message, 'error'); }
}

async function deleteTplThrottling(key) {
  if (!(await confirmModal(`Supprimer le throttling pour "${key}" du template ?`))) return;
  delete tplLlmData.throttling[key];
  try {
    await api('/api/templates/llm', { method: 'PUT', body: tplLlmData });
    toast('Throttling supprime du template', 'success');
    loadTplLLM();
  } catch (e) { toast(e.message, 'error'); }
}

// ── Template MCP (catalog-based, mirrors Services MCP) ──
let tplMcpCatalog = [];
let tplMcpShowDeprecated = false;

async function loadTplMCP() {
  try {
    const data = await api('/api/templates/mcp/catalog');
    tplMcpCatalog = data.servers || [];
    renderTplMCP();
  } catch (e) { toast(e.message, 'error'); }
}

function renderTplMCP() {
  // Top: only services WITH env_vars (parameterized)
  const withParams = tplMcpCatalog.filter(c => c.env_vars.length > 0 && c.installed);
  // Bottom: only services WITHOUT env_vars
  const noParams = tplMcpCatalog.filter(c => c.env_vars.length === 0 && (tplMcpShowDeprecated || !c.deprecated));

  // ── Top: Services with parameters ──
  const configuredEl = document.getElementById('tpl-mcp-configured');
  if (withParams.length === 0) {
    configuredEl.innerHTML = '<p style="color:var(--text-secondary);text-align:center;padding:1rem">Aucun service avec parametres dans le catalogue.</p>';
  } else {
    configuredEl.innerHTML = `<table>
      <thead><tr><th>Service</th><th>Commande</th><th>Env</th><th>Actif</th><th>Actions</th></tr></thead>
      <tbody>${withParams.map(c => {
        const envStatus = c.env_vars.map(v =>
              `<span class="tag ${v.configured ? 'tag-green' : 'tag-red'}" title="${escHtml(v.desc)}">${escHtml(v.mapped_var || v.var)}</span>`
            ).join(' ');
        const installed = c.installed;
        return `<tr>
          <td>
            <strong>${escHtml(c.label)}</strong>
            <div style="font-size:0.7rem;color:var(--text-secondary)">${escHtml(c.id)}</div>
          </td>
          <td><code style="font-size:0.75rem">${escHtml(c.command)} ${escHtml(c.args)}</code></td>
          <td>${envStatus}</td>
          <td>
            ${installed
              ? `<div class="toggle ${c.enabled ? 'active' : ''}" onclick="toggleTplMCP('${escHtml(c.id)}', ${!c.enabled})"></div>`
              : `<button class="btn btn-sm btn-primary" onclick="showAddTplCatalogModal('${escHtml(c.id)}')">Installer</button>`}
          </td>
          <td>
            ${installed ? `<button class="btn-icon" onclick="showTplMCPEnvModal('${escHtml(c.id)}')" title="Configurer env">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>
            </button>
            <button class="btn-icon danger" onclick="uninstallTplMCP('${escHtml(c.id)}')" title="Desinstaller">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>
            </button>` : ''}
          </td>
        </tr>`;
      }).join('')}</tbody>
    </table>`;
  }

  // ── Bottom: Services without parameters ──
  const catalogEl = document.getElementById('tpl-mcp-catalog');
  catalogEl.innerHTML = noParams.map(c => {
    let statusBtn;
    if (c.installed) {
      statusBtn = `<div class="toggle ${c.enabled ? 'active' : ''}" onclick="event.stopPropagation();toggleTplMCP('${escHtml(c.id)}', ${!c.enabled})" style="cursor:pointer"></div>`;
    } else {
      statusBtn = `<button class="btn btn-sm btn-primary" onclick="event.stopPropagation();quickInstallTplMcp('${escHtml(c.id)}')">Installer</button>`;
    }
    return `<div class="mcp-card${c.deprecated ? ' deprecated' : ''}">
      <div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:0.5rem">
        <div>
          <strong>${escHtml(c.label)}</strong>
          ${c.deprecated ? '<span class="tag tag-red" style="margin-left:0.5rem">deprecie</span>' : ''}
        </div>
        ${statusBtn}
      </div>
      <p style="font-size:0.8rem;color:var(--text-secondary);margin-bottom:0.5rem">${escHtml(c.description)}</p>
      <code style="font-size:0.7rem;color:var(--text-secondary)">${escHtml(c.command)} ${escHtml(c.args)}</code>
    </div>`;
  }).join('');
}

function showAddTplCatalogModal(preselectedId) {
  const available = tplMcpCatalog.filter(c => !c.installed && c.env_vars.length > 0);
  if (available.length === 0) {
    toast('Tous les services du catalogue sont deja installes', 'info');
    return;
  }
  const selected = preselectedId
    ? tplMcpCatalog.find(c => c.id === preselectedId)
    : available[0];
  if (!selected) return;

  const options = available.map(c =>
    `<option value="${escHtml(c.id)}" ${c.id === selected.id ? 'selected' : ''}>${escHtml(c.label)} — ${escHtml(c.description)}</option>`
  ).join('');

  showModal(`
    <div class="modal-header">
      <h3>Installer un service MCP (template)</h3>
      <button class="btn-icon" onclick="closeModal()">&times;</button>
    </div>
    <div class="form-group">
      <label>Service</label>
      <select id="mcp-tpl-install-select" onchange="onTplMCPServiceSelected()">
        ${options}
      </select>
    </div>
    <div id="mcp-tpl-install-details">${_renderInstallDetails(selected)}</div>
    <div class="modal-actions">
      <button class="btn btn-outline" onclick="closeModal()">Annuler</button>
      <button class="btn btn-primary" onclick="installTplSelectedService()">Enregistrer</button>
    </div>
  `, 'modal-wide');
}

function onTplMCPServiceSelected() {
  const id = document.getElementById('mcp-tpl-install-select').value;
  const item = tplMcpCatalog.find(c => c.id === id);
  if (item) {
    document.getElementById('mcp-tpl-install-details').innerHTML = _renderInstallDetails(item);
  }
}

async function installTplSelectedService() {
  const id = document.getElementById('mcp-tpl-install-select').value;
  const envMapping = {};
  document.querySelectorAll('.mcp-env-computed').forEach(el => {
    const base = el.getAttribute('data-base');
    envMapping[base] = el.textContent;
  });
  try {
    await api(`/api/templates/mcp/install/${id}`, { method: 'POST', body: { env_values: {}, env_mapping: envMapping } });
    toast('Service MCP installe dans le template', 'success');
    closeModal();
    loadTplMCP();
  } catch (e) { toast(e.message, 'error'); }
}

async function uninstallTplMCP(id) {
  if (!(await confirmModal(`Desinstaller le serveur MCP "${id}" du template ?`))) return;
  try {
    await api(`/api/templates/mcp/uninstall/${id}`, { method: 'POST' });
    toast('Serveur MCP desinstalle du template', 'success');
    loadTplMCP();
  } catch (e) { toast(e.message, 'error'); }
}

async function toggleTplMCP(id, enabled) {
  try {
    await api(`/api/templates/mcp/toggle/${id}`, { method: 'PUT', body: { enabled } });
    loadTplMCP();
  } catch (e) { toast(e.message, 'error'); }
}

function showTplMCPEnvModal(id) {
  const item = tplMcpCatalog.find(c => c.id === id);
  if (!item || !item.env_vars.length) {
    toast('Aucune variable d\'environnement pour ce serveur', 'info');
    return;
  }
  showModal(`
    <div class="modal-header">
      <h3>Env : ${escHtml(item.label)} (template)</h3>
      <button class="btn-icon" onclick="closeModal()">&times;</button>
    </div>
    <div class="env-var-list">
      ${item.env_vars.map(v => `
        <div class="env-var-row">
          <div class="env-var-info">
            <code>${escHtml(v.mapped_var || v.var)}</code>
            <span class="env-var-desc">${escHtml(v.desc)}</span>
            ${v.configured
              ? '<span class="tag tag-green">configure</span>'
              : '<span class="tag tag-red">manquant</span>'}
          </div>
          <div class="env-var-action">
            <input class="mcp-env-field" data-var="${escHtml(v.mapped_var || v.var)}" placeholder="Nouvelle valeur..." />
            <button class="btn btn-sm btn-outline" onclick="setEnvVarFromInstall('${escHtml(v.mapped_var || v.var)}', this)" title="Enregistrer dans .env">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z"/><polyline points="17 21 17 13 7 13 7 21"/><polyline points="7 3 7 8 15 8"/></svg>
            </button>
          </div>
        </div>
      `).join('')}
    </div>
    <div class="modal-actions">
      <button class="btn btn-outline" onclick="closeModal()">Fermer</button>
    </div>
  `);
}

function toggleTplDeprecated() {
  tplMcpShowDeprecated = !tplMcpShowDeprecated;
  const btn = document.getElementById('btn-tpl-show-deprecated');
  btn.textContent = tplMcpShowDeprecated ? 'Masquer deprecies' : 'Afficher deprecies';
  renderTplMCP();
}

// ── Template Teams ────────────────────────────────
let tplTemplatesData = []; // from /api/templates (directories)

async function loadTplTeamsList() {
  try {
    // Load both: teams.json (metadata) and template directories (agents)
    const [teamsRes, tplRes] = await Promise.all([
      api('/api/templates/teams'),
      api('/api/templates'),
    ]);
    tplTeamsData = teamsRes;
    if (!Array.isArray(tplTeamsData.teams)) tplTeamsData.teams = [];
    tplTemplatesData = tplRes.templates || [];
    renderTplTeams();
  } catch (e) { toast(e.message, 'error'); }
}

function renderTplTeams() {
  const container = document.getElementById('tpl-teams-table');
  if (!tplTeamsData.teams.length) {
    container.innerHTML = '<p style="color:var(--text-secondary);padding:1rem">Aucune equipe configuree.</p>';
    return;
  }
  container.innerHTML = tplTeamsData.teams.map((t, i) => {
    // Find matching template directory
    const tpl = tplTemplatesData.find(tp => tp.id === t.directory) || null;
    const agentEntries = tpl ? Object.entries(tpl.agents) : [];
    const mcpAccess = tpl ? (tpl.mcp_access || {}) : {};
    const dir = t.directory || '';

    const orchId = t.orchestrator || '';
    const agentCards = agentEntries.map(([aid, a]) => {
      const mcpList = mcpAccess[aid] || [];
      const isOrch = aid === orchId;
      return `<div class="agent-card${isOrch ? ' agent-orchestrator' : ''}" style="cursor:pointer">
        <div class="agent-card-header">
          <div onclick="editTplAgent('${escHtml(dir)}','${escHtml(aid)}')" style="flex:1;cursor:pointer">
            <h4>${isOrch ? '<span class="orch-badge" title="Orchestrateur">&#9733;</span> ' : ''}${escHtml(a.name)}</h4>
            <code style="font-size:0.75rem;color:var(--text-secondary)">${escHtml(aid)}</code>
          </div>
          <button class="btn-icon danger" onclick="event.stopPropagation();deleteTplAgent('${escHtml(dir)}','${escHtml(aid)}')" title="Supprimer">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>
          </button>
        </div>
        <div class="agent-meta" onclick="editTplAgent('${escHtml(dir)}','${escHtml(aid)}')">
          <span class="tag tag-blue">temp: ${a.temperature}</span>
          <span class="tag tag-blue">tokens: ${a.max_tokens}</span>
          ${a.llm ? `<span class="tag tag-yellow">${escHtml(a.llm)}</span>` : ''}
          ${a.type ? `<span class="tag tag-gray">${escHtml(a.type)}</span>` : ''}
        </div>
        ${mcpList.length ? `<div class="agent-meta">
          ${mcpList.map(m => `<span class="tag tag-green">${escHtml(m)}</span>`).join('')}
        </div>` : ''}
      </div>`;
    }).join('');

    return `<div class="team-block">
      <div class="team-block-header">
        <div style="display:flex;align-items:center;gap:0.5rem;flex:1;cursor:pointer" onclick="toggleTeamBlock(this)">
          <svg class="team-chevron" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="6 9 12 15 18 9"/></svg>
          <h3 style="margin:0">
            ${escHtml(t.name)}
            <span style="font-weight:400;font-size:0.75rem;color:var(--text-secondary)">${escHtml(t.id)}</span>
            <code style="font-weight:400;font-size:0.7rem;color:var(--text-secondary)">Shared/Teams/${escHtml(dir)}/</code>
          </h3>
          <span class="tag tag-blue" style="margin-left:0.5rem">${agentEntries.length} agent${agentEntries.length > 1 ? 's' : ''}</span>
        </div>
        <div style="display:flex;gap:0.5rem">
          <button class="btn-icon" onclick="event.stopPropagation();editTplTeamQuick(${i})" title="Modifier l'equipe" style="opacity:0.5">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M17 3a2.83 2.83 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5Z"/><path d="m15 5 4 4"/></svg>
          </button>
          <button class="btn btn-primary btn-sm" onclick="showAddTplAgentModal('${escHtml(dir)}')">+ Agent</button>
          <button class="btn btn-outline btn-sm" id="btn-wf-tpl-${escHtml(dir)}" onclick="showTplWorkflow('${escHtml(dir)}')">Workflow</button>
          <button class="btn btn-outline btn-sm" onclick="showTplRawRegistry('${escHtml(dir)}')">Raw</button>
          <button class="btn btn-outline btn-sm" style="color:var(--error)" onclick="deleteTplTeam(${i})">Suppr</button>
        </div>
      </div>
      <div class="team-block-body">
        ${t.description ? `<p style="color:var(--text-secondary);margin:0 0 0.5rem 0;font-size:0.85rem">${escHtml(t.description)}</p>` : ''}
        <div class="team-block-meta">
          ${(t.discord_channels || []).map(c => `<span class="tag tag-green">#${escHtml(c)}</span>`).join('')}
        </div>
        <div class="agents-grid">
          ${agentCards || '<p style="color:var(--text-secondary);padding:0.5rem">Aucun agent dans ce template.</p>'}
        </div>
      </div>
    </div>`;
  }).join('');
  // Validate workflows after render
  tplTeamsData.teams.forEach(t => {
    const dir = t.directory || '';
    _wfCheckStatus(dir, '/api/templates/workflow', '/api/templates/registry', 'tpl');
  });
}

async function showAddTplAgentModal(dir) {
  let sharedList = [], hasOrch = false;
  try {
    const d = await api('/api/shared-agents');
    sharedList = d.agents || [];
  } catch { /* ignore */ }
  try {
    const reg = await api(`/api/templates/registry/${encodeURIComponent(dir)}`);
    hasOrch = Object.values(reg.agents || reg || {}).some(a => a.type === 'orchestrator');
  } catch { /* ignore */ }
  const sortedShared = sharedList.slice().sort((a, b) => (a.name || a.id).localeCompare(b.name || b.id, 'fr'));
  showModal(`
    <div class="modal-header">
      <h3>Ajouter un agent (template)</h3>
      <button class="btn-icon" onclick="closeModal()">&times;</button>
    </div>
    <div class="form-group">
      <label>Agent (catalogue)</label>
      <div style="position:relative">
        <input id="tpl-agent-filter" placeholder="Filtrer / choisir un agent..." autocomplete="off"
          oninput="_filterTplAgentDropdown()" onfocus="_openTplAgentDropdown()" />
        <input type="hidden" id="tpl-agent-new-id" />
        <div id="tpl-agent-dropdown" class="sa-dropdown" style="display:none">
          ${sortedShared.map(a => `<div class="sa-dropdown-item" data-id="${escHtml(a.id)}" data-name="${escHtml(a.name || a.id)}" onclick="_pickTplAgent(this)">${escHtml(a.name || a.id)} <span style="color:var(--text-secondary);font-size:0.8rem">(${escHtml(a.id)})</span></div>`).join('')}
        </div>
      </div>
      ${!sharedList.length ? '<p style="color:var(--text-secondary);font-size:0.8rem;margin-top:0.25rem">Aucun agent dans le catalogue. Creez-en d\'abord dans Templates &gt; Agents.</p>' : ''}
    </div>
    <div class="form-group">
      <label>Type</label>
      <select id="tpl-agent-new-type">
        <option value="single" selected>Single</option>
        <option value="pipeline">Pipeline</option>
        <option value="orchestrator" ${hasOrch?'disabled':''}>Orchestrator</option>
      </select>
    </div>
    <div class="modal-actions">
      <button class="btn btn-outline" onclick="closeModal()">Annuler</button>
      <button class="btn btn-primary" onclick="addTplAgent('${escHtml(dir)}')">Ajouter</button>
    </div>
  `, 'modal-tall');
}

function _filterTplAgentDropdown() {
  const filter = (document.getElementById('tpl-agent-filter').value || '').toLowerCase();
  const dd = document.getElementById('tpl-agent-dropdown');
  dd.style.display = '';
  dd.querySelectorAll('.sa-dropdown-item').forEach(item => {
    const label = (item.dataset.name + ' ' + item.dataset.id).toLowerCase();
    item.style.display = label.includes(filter) ? '' : 'none';
  });
}
function _openTplAgentDropdown() {
  document.getElementById('tpl-agent-dropdown').style.display = '';
  _filterTplAgentDropdown();
}
function _pickTplAgent(el) {
  const id = el.dataset.id, name = el.dataset.name;
  document.getElementById('tpl-agent-new-id').value = id;
  document.getElementById('tpl-agent-filter').value = name + ' (' + id + ')';
  document.getElementById('tpl-agent-dropdown').style.display = 'none';
}

async function addTplAgent(dir) {
  const id = (document.getElementById('tpl-agent-new-id').value || '').trim();
  if (!id) { toast('Selectionnez un agent du catalogue', 'error'); return; }
  const agentType = document.getElementById('tpl-agent-new-type').value;
  if (agentType === 'orchestrator') {
    try {
      const reg = await api(`/api/templates/registry/${encodeURIComponent(dir)}`);
      if (Object.values(reg.agents || reg || {}).some(a => a.type === 'orchestrator')) {
        toast('Un orchestrator existe deja dans cette equipe', 'error'); return;
      }
    } catch { /* ignore */ }
  }
  try {
    await api('/api/templates/agents', { method: 'POST', body: {
      id,
      name: id,
      type: agentType,
      team_id: dir,
    }});
    toast('Agent ajoute', 'success');
    closeModal();
    loadTplTeamsList();
  } catch (e) { toast(e.message, 'error'); }
}

async function editTplAgent(dir, agentId) {
  const tpl = tplTemplatesData.find(tp => tp.id === dir);
  if (!tpl || !tpl.agents[agentId]) { toast('Agent introuvable', 'error'); return; }
  const a = tpl.agents[agentId];

  // Agent properties are read-only (from Shared/Agents catalog)
  const mcpAccess = a.mcp_access || [];
  const mcpReadOnly = mcpAccess.length
    ? mcpAccess.map(id => `<span class="tag tag-green">${escHtml(id)}</span>`).join('')
    : '<span style="color:var(--text-secondary);font-size:0.85rem">Aucun</span>';
  const delivTags = [
    a.delivers_docs ? '<span class="tag tag-purple">Documentation</span>' : '',
    a.delivers_code ? '<span class="tag tag-purple">Code</span>' : '',
  ].filter(Boolean).join('') || '<span style="color:var(--text-secondary);font-size:0.85rem">Aucun</span>';

  const promptRaw = a.prompt_content || '';
  const promptHtml = typeof marked !== 'undefined' ? marked.parse(promptRaw) : escHtml(promptRaw);
  const hasPipeline = a.type === 'pipeline' || (a.pipeline_steps && a.pipeline_steps.length > 0);
  const isOrchestrator = a.type === 'orchestrator';
  const curType = isOrchestrator ? 'orchestrator' : (hasPipeline ? 'pipeline' : 'single');
  const hasOtherOrch = Object.entries(tpl.agents || {}).some(([aid, ag]) => aid !== agentId && ag.type === 'orchestrator');

  showModal(`
    <div class="modal-header">
      <h3>Agent: ${escHtml(a.name || agentId)} <span style="color:var(--text-secondary);font-weight:normal;font-size:0.85rem">(${escHtml(agentId)})</span></h3>
      <button class="btn-icon" onclick="closeModal()">&times;</button>
    </div>
    <div class="prompt-tabs" style="margin-bottom:0.5rem">
      <div class="prompt-tab active" id="tpl-modal-tab-info" onclick="switchTplModalTab('info')">Signaletique</div>
      <div class="prompt-tab" id="tpl-modal-tab-prompt" onclick="switchTplModalTab('prompt')">Prompt</div>
      <div class="prompt-tab" id="tpl-modal-tab-pipeline" onclick="switchTplModalTab('pipeline')" style="${hasPipeline ? '' : 'display:none'}">Pipeline</div>
    </div>
    <div id="tpl-modal-pane-info">
      <div class="form-row">
        <div class="form-group">
          <label>Nom</label>
          <input value="${escHtml(a.name || agentId)}" readonly style="background:var(--bg-secondary)" />
        </div>
        <div class="form-group">
          <label>Modele LLM</label>
          <input value="${escHtml(a.llm || '(defaut)')}" readonly style="background:var(--bg-secondary)" />
        </div>
      </div>
      <div class="form-row">
        <div class="form-group">
          <label>Temperature</label>
          <input value="${a.temperature ?? ''}" readonly style="background:var(--bg-secondary)" />
        </div>
        <div class="form-group">
          <label>Max tokens</label>
          <input value="${a.max_tokens ?? ''}" readonly style="background:var(--bg-secondary)" />
        </div>
      </div>
      <div class="form-group">
        <label>Type</label>
        <select id="tpl-agent-edit-type" onchange="_onTplTypeChange(this.value)">
          <option value="single" ${curType==='single'?'selected':''}>Single</option>
          <option value="pipeline" ${curType==='pipeline'?'selected':''}>Pipeline</option>
          <option value="orchestrator" ${curType==='orchestrator'?'selected':''} ${hasOtherOrch && curType!=='orchestrator'?'disabled':''}>Orchestrator</option>
        </select>
      </div>
      <div class="form-group">
        <label>Serveurs MCP autorises</label>
        <div style="display:flex;flex-wrap:wrap;gap:0.35rem;margin-top:0.25rem">${mcpReadOnly}</div>
      </div>
      <div class="form-group">
        <label>Type de livrable</label>
        <div style="display:flex;flex-wrap:wrap;gap:0.35rem;margin-top:0.25rem">${delivTags}</div>
      </div>
    </div>
    <div id="tpl-modal-pane-prompt" style="display:none">
      <div class="form-group">
        <label>Prompt</label>
        <div class="prompt-preview" id="tpl-agent-prompt-preview" style="max-height:500px;overflow-y:auto"></div>
      </div>
    </div>
    <div id="tpl-modal-pane-pipeline" style="display:none">
      <div class="form-group">
        <label>Pipeline Steps</label>
        <div id="tpl-pipeline-steps" class="pipeline-steps-container"></div>
      </div>
    </div>
    <div class="modal-actions">
      <button class="btn btn-outline" onclick="closeModal()">Annuler</button>
      <button class="btn btn-primary" onclick="saveTplAgent('${escHtml(dir)}','${escHtml(agentId)}')">Sauvegarder</button>
    </div>
  `, 'modal-wide');
  // Set prompt after modal creation to avoid template literal issues with backticks
  const promptEl = document.getElementById('tpl-agent-prompt-preview');
  if (promptEl) promptEl.innerHTML = promptHtml;
  renderPipelineSteps('tpl-pipeline-steps', a.pipeline_steps || []);
}

function switchTplModalTab(tab) {
  ['info', 'prompt', 'pipeline'].forEach(t => {
    const pane = document.getElementById('tpl-modal-pane-' + t);
    const tabEl = document.getElementById('tpl-modal-tab-' + t);
    if (pane) pane.style.display = t === tab ? '' : 'none';
    if (tabEl) tabEl.classList.toggle('active', t === tab);
  });
}

function _onTplTypeChange(val) {
  const tabEl = document.getElementById('tpl-modal-tab-pipeline');
  if (tabEl) tabEl.style.display = val === 'pipeline' ? '' : 'none';
  // If switching away from pipeline, hide the pane if it was active
  if (val !== 'pipeline') {
    const pane = document.getElementById('tpl-modal-pane-pipeline');
    if (pane && pane.style.display !== 'none') switchTplModalTab('info');
  }
}

async function saveTplAgent(dir, agentId) {
  const agentType = document.getElementById('tpl-agent-edit-type').value;
  const tpl = tplTemplatesData.find(tp => tp.id === dir);
  if (agentType === 'orchestrator' && Object.entries(tpl.agents || {}).some(([aid, ag]) => aid !== agentId && ag.type === 'orchestrator')) {
    toast('Un orchestrator existe deja dans cette equipe', 'error'); return;
  }
  const pipeline_steps = agentType === 'pipeline' ? getPipelineSteps('tpl-pipeline-steps') : [];
  try {
    await api(`/api/templates/agents/${encodeURIComponent(agentId)}`, { method: 'PUT', body: {
      id: agentId, name: agentId,
      type: agentType,
      pipeline_steps,
      team_id: dir,
    }});
    toast('Agent sauvegarde', 'success');
    closeModal();
    loadTplTeamsList();
  } catch (e) { toast(e.message, 'error'); }
}

async function deleteTplAgent(dir, agentId) {
  if (!(await confirmModal(`Supprimer l'agent "${agentId}" ?`))) return;
  try {
    await api(`/api/templates/agents/${encodeURIComponent(agentId)}?team_id=${encodeURIComponent(dir)}`, { method: 'DELETE' });
    toast('Agent supprime', 'success');
    loadTplTeamsList();
  } catch (e) { toast(e.message, 'error'); }
}

async function showTplRawRegistry(dir) {
  try {
    const data = await api(`/api/templates/registry/${encodeURIComponent(dir)}`);
    const json = JSON.stringify(data, null, 2);
    showModal(`
      <div class="modal-header">
        <h3>Registry JSON — Shared/Teams/${escHtml(dir)}/</h3>
        <button class="btn-icon" onclick="closeModal()">&times;</button>
      </div>
      <div class="form-group">
        <textarea id="tpl-raw-json" style="min-height:400px;font-family:monospace;font-size:0.8rem;white-space:pre;tab-size:2">${escHtml(json)}</textarea>
      </div>
      <div class="modal-actions">
        <button class="btn btn-outline" onclick="closeModal()">Annuler</button>
        <button class="btn btn-primary" onclick="saveTplRawRegistry('${escHtml(dir)}')">Sauvegarder</button>
      </div>
    `, 'modal-wide');
  } catch (e) { toast(e.message, 'error'); }
}

async function saveTplRawRegistry(dir) {
  const raw = document.getElementById('tpl-raw-json').value;
  let data;
  try { data = JSON.parse(raw); } catch { toast('JSON invalide', 'error'); return; }
  try {
    await api(`/api/templates/registry/${encodeURIComponent(dir)}`, { method: 'PUT', body: data });
    toast('Registry sauvegarde', 'success');
    closeModal();
    loadTplTeamsList();
  } catch (e) { toast(e.message, 'error'); }
}

function showTplWorkflow(dir) {
  openWorkflowEditor(dir, '/api/templates/workflow', 'Shared/Teams');
}

async function _saveTplTeams() {
  await api('/api/templates/teams', { method: 'PUT', body: tplTeamsData });
  toast('Equipes sauvegardees');
}

function showAddTplTeamModal() {
  showModal(`
    <div class="modal-header">
      <h3>Ajouter une equipe (template)</h3>
      <button class="btn-icon" onclick="closeModal()">&times;</button>
    </div>
    <div class="form-group">
      <label>ID</label>
      <input id="m-tpl-team-id" class="form-control" placeholder="mon_equipe" oninput="_onTplTeamIdInput()" />
      <span id="m-tpl-team-id-error" style="color:var(--danger);font-size:0.8rem;display:none"></span>
    </div>
    <div class="form-group"><label>Nom</label><input id="m-tpl-team-name" class="form-control" placeholder="Mon Equipe"></div>
    <div class="form-group"><label>Description</label><input id="m-tpl-team-desc" class="form-control"></div>
    <div class="form-group">
      <label>Repertoire (Shared/Teams/...)</label>
      <input id="m-tpl-team-dir" class="form-control" readonly style="opacity:0.6" />
    </div>
    <div class="form-group"><label>Channels Discord (virgule)</label><input id="m-tpl-team-channels" class="form-control"></div>
    <div class="modal-actions">
      <button class="btn btn-outline" onclick="closeModal()">Annuler</button>
      <button class="btn btn-primary" onclick="addTplTeam()">Ajouter</button>
    </div>
  `);
}

function _onTplTeamIdInput() {
  const el = document.getElementById('m-tpl-team-id');
  const errEl = document.getElementById('m-tpl-team-id-error');
  const dirEl = document.getElementById('m-tpl-team-dir');
  el.value = el.value.replace(/[^a-z0-9_-]/gi, '').toLowerCase();
  const raw = el.value;
  // Capitalize first letter of each segment for directory name
  const dir = raw ? raw.charAt(0).toUpperCase() + raw.slice(1) : '';
  dirEl.value = dir;
  // Check uniqueness against teams list and existing directories
  const existingIds = tplTeamsData.teams.map(t => t.id);
  const existingDirs = tplTemplatesData.map(t => t.id);
  if (raw && existingIds.includes(raw)) {
    el.style.border = '2px solid var(--danger)';
    errEl.textContent = `L'ID "${raw}" existe deja dans les equipes`;
    errEl.style.display = 'block';
  } else if (dir && existingDirs.includes(dir)) {
    el.style.border = '2px solid var(--danger)';
    errEl.textContent = `Le repertoire "${dir}" existe deja`;
    errEl.style.display = 'block';
  } else {
    el.style.border = '';
    errEl.style.display = 'none';
  }
}

async function addTplTeam() {
  const raw = document.getElementById('m-tpl-team-id').value.replace(/[^a-zA-Z0-9_-]/g, '_').toLowerCase().trim();
  if (!raw) { toast('ID requis', 'error'); return; }
  const errEl = document.getElementById('m-tpl-team-id-error');
  if (errEl && errEl.style.display !== 'none') { toast('ID invalide', 'error'); return; }
  const directory = document.getElementById('m-tpl-team-dir').value;
  if (!directory) { toast('Repertoire invalide', 'error'); return; }
  const channels = document.getElementById('m-tpl-team-channels').value.trim();
  tplTeamsData.teams.push({
    id: raw,
    name: document.getElementById('m-tpl-team-name').value.trim() || raw,
    description: document.getElementById('m-tpl-team-desc').value.trim(),
    directory,
    discord_channels: channels ? channels.split(',').map(s => s.trim()) : []
  });
  try {
    await _saveTplTeams();
    closeModal();
    loadTplTeamsList();
  } catch (e) {
    tplTeamsData.teams.pop();
    toast(e.message, 'error');
  }
}

function editTplTeam(idx) {
  const t = tplTeamsData.teams[idx];
  const tpl = tplTemplatesData.find(tp => tp.id === t.directory) || null;
  const agentIds = tpl ? Object.keys(tpl.agents || {}) : [];
  const orchOpts = `<option value="">-- Aucun --</option>` +
    agentIds.map(aid => `<option value="${escHtml(aid)}" ${(t.orchestrator || '') === aid ? 'selected' : ''}>${escHtml((tpl.agents[aid] || {}).name || aid)} (${escHtml(aid)})</option>`).join('');
  showModal(`
    <div class="modal-header">
      <h3>Modifier equipe (template)</h3>
      <button class="btn-icon" onclick="closeModal()">&times;</button>
    </div>
    <div class="form-group"><label>ID</label><input id="m-tpl-team-id" class="form-control" value="${escHtml(t.id)}" disabled></div>
    <div class="form-group"><label>Nom</label><input id="m-tpl-team-name" class="form-control" value="${escHtml(t.name)}"></div>
    <div class="form-group"><label>Description</label><input id="m-tpl-team-desc" class="form-control" value="${escHtml(t.description || '')}"></div>
    <div class="form-group">
      <label>Repertoire (Shared/Teams/...)</label>
      <input id="m-tpl-team-dir" class="form-control" value="${escHtml(t.directory || '')}" readonly style="opacity:0.6" />
    </div>
    <div class="form-group"><label>Orchestrateur</label><select id="m-tpl-team-orchestrator" class="form-control">${orchOpts}</select></div>
    <div class="form-group"><label>Channels Discord (virgule)</label><input id="m-tpl-team-channels" class="form-control" value="${(t.discord_channels || []).join(', ')}"></div>
    <div class="modal-actions">
      <button class="btn btn-outline" onclick="closeModal()">Annuler</button>
      <button class="btn btn-primary" onclick="saveTplTeam(${idx})">Sauvegarder</button>
    </div>
  `);
}

function editTplTeamQuick(idx) {
  const t = tplTeamsData.teams[idx];
  showModal(`
    <div class="modal-header">
      <h3>Equipe: ${escHtml(t.name || t.id)}</h3>
      <button class="btn-icon" onclick="closeModal()">&times;</button>
    </div>
    <div class="form-group">
      <label>Nom</label>
      <input id="m-tpl-team-qname" value="${escHtml(t.name || '')}" />
    </div>
    <div class="form-group">
      <label>Description</label>
      <input id="m-tpl-team-qdesc" value="${escHtml(t.description || '')}" />
    </div>
    <div class="modal-actions">
      <button class="btn btn-outline" onclick="closeModal()">Annuler</button>
      <button class="btn btn-primary" onclick="saveTplTeamQuick(${idx})">Sauvegarder</button>
    </div>
  `, 'modal-confirm');
}

async function saveTplTeamQuick(idx) {
  const name = document.getElementById('m-tpl-team-qname').value.trim();
  if (!name) { toast('Nom requis', 'error'); return; }
  tplTeamsData.teams[idx] = {
    ...tplTeamsData.teams[idx],
    name,
    description: document.getElementById('m-tpl-team-qdesc').value.trim(),
  };
  await _saveTplTeams();
  closeModal();
  loadTplTeamsList();
}

async function saveTplTeam(idx) {
  const channels = document.getElementById('m-tpl-team-channels').value.trim();
  const orchestrator = (document.getElementById('m-tpl-team-orchestrator') || {}).value || '';
  const updated = {
    ...tplTeamsData.teams[idx],
    name: document.getElementById('m-tpl-team-name').value.trim(),
    description: document.getElementById('m-tpl-team-desc').value.trim(),
    discord_channels: channels ? channels.split(',').map(s => s.trim()) : []
  };
  if (orchestrator) updated.orchestrator = orchestrator;
  else delete updated.orchestrator;
  tplTeamsData.teams[idx] = updated;
  await _saveTplTeams();
  closeModal();
  loadTplTeamsList();
}

async function deleteTplTeam(idx) {
  const t = tplTeamsData.teams[idx];
  if (!(await confirmModal(`Supprimer l'equipe "${t.name}" ?`))) return;
  tplTeamsData.teams.splice(idx, 1);
  await _saveTplTeams();
  loadTplTeamsList();
}

// ═══════════════════════════════════════════════════
// VISUAL WORKFLOW EDITOR
// ═══════════════════════════════════════════════════

let _wf = null; // current workflow editor state

async function openWorkflowEditor(dir, apiBase, label) {
  try {
    const raw = await api(`${apiBase}/${encodeURIComponent(dir)}`);
    const designBase = apiBase.replace('/workflow', '/workflow-design');
    let design = {};
    try { design = await api(`${designBase}/${encodeURIComponent(dir)}`); } catch {}
    const data = (raw && Object.keys(raw).length) ? raw : { phases: {}, transitions: [], parallel_groups: { description: '', order: ['A','B','C'] }, rules: {} };
    _wf = {
      dir, apiBase, designBase, label,
      data: JSON.parse(JSON.stringify(data)),
      selected: null,
      positions: (design && design.positions) ? design.positions : {},
      dragging: null,
      dragOffset: { x: 0, y: 0 },
      linking: null,
      linkMouse: null,
    };
    _wfCalcPositions();
    _wfOpenEditorUI();
  } catch (e) { toast(e.message, 'error'); }
}

function _wfOpenEditorUI() {
  const html = `
    <div class="wf-toolbar">
      <h3>Workflow — ${escHtml(_wf.label)}/${escHtml(_wf.dir)}/</h3>
      <div class="wf-toolbar-actions">
        <button class="btn btn-outline btn-sm" onclick="wfShowJSON()">JSON</button>
        <button class="btn btn-primary btn-sm" onclick="wfSave()">Sauvegarder</button>
        <button class="btn-icon" onclick="closeModal()">&times;</button>
      </div>
    </div>
    <div class="wf-body">
      <div class="wf-workspace" id="wf-workspace" onmousedown="wfWorkspaceClick(event)">
        <svg class="wf-arrows" id="wf-arrows">
          <defs>
            <marker id="wf-arrowhead" markerWidth="10" markerHeight="7" refX="10" refY="3.5" orient="auto">
              <polygon points="0 0, 10 3.5, 0 7" fill="var(--text-secondary)" />
            </marker>
          </defs>
        </svg>
        <div class="wf-workspace-inner" id="wf-workspace-inner"></div>
      </div>
      <div class="wf-sidebar">
        <div class="wf-toolbox" id="wf-toolbox">
          <h4>Boite a outils</h4>
          <button class="wf-toolbox-btn" onclick="wfAddPhase()">+ Ajouter une Phase</button>
        </div>
        <div class="wf-props" id="wf-props"></div>
      </div>
    </div>
  `;
  showModal(html, 'modal-workflow');
  wfRender();
}

function _wfCalcPositions() {
  const phases = Object.entries(_wf.data.phases || {});
  phases.sort((a, b) => (a[1].order || 0) - (b[1].order || 0));
  const startX = 60, startY = 80, spacingX = 280;
  phases.forEach(([id, _p], i) => {
    if (!_wf.positions[id]) {
      _wf.positions[id] = { x: startX + i * spacingX, y: startY };
    }
  });
}

function wfRender() {
  if (!_wf) return;
  const inner = document.getElementById('wf-workspace-inner');
  if (!inner) return;

  // Render phase blocks
  const phases = Object.entries(_wf.data.phases || {});
  phases.sort((a, b) => (a[1].order || 0) - (b[1].order || 0));
  let html = '';
  for (const [id, p] of phases) {
    const pos = _wf.positions[id] || { x: 100, y: 100 };
    const sel = _wf.selected === id ? ' wf-selected' : '';
    const agentIds = Object.keys(p.agents || {});
    const delIds = Object.keys(p.deliverables || {});
    html += `
      <div class="wf-phase${sel}" id="wf-p-${id}" data-id="${id}"
           style="left:${pos.x}px;top:${pos.y}px"
           onmousedown="wfPhaseMouseDown(event,'${id}')"
           onclick="wfSelectPhase(event,'${id}')"
           oncontextmenu="event.preventDefault()">
        <div class="wf-phase-head">
          <span>${escHtml(p.name || id)}</span>
          <span class="wf-phase-order">${p.order || '?'}</span>
        </div>
        <div class="wf-phase-body">
          <div class="wf-mini-label">Agents (${agentIds.length})</div>
          <div class="wf-mini-list">${agentIds.map(a => `<span class="wf-mini-chip${(p.agents[a]||{}).required?' required':''}">${escHtml(a)}</span>`).join('')}</div>
          <div class="wf-mini-label">Livrables (${delIds.length})</div>
          <div class="wf-mini-list">${delIds.map(d => `<span class="wf-mini-chip${(p.deliverables[d]||{}).required?' required':''}">${escHtml(d)}</span>`).join('')}</div>
        </div>
        <div class="wf-anchor wf-anchor-left" data-side="left" onmousedown="wfLinkStart(event,'${id}','left')"></div>
        <div class="wf-anchor wf-anchor-top" data-side="top" onmousedown="wfLinkStart(event,'${id}','top')"></div>
        <div class="wf-anchor wf-anchor-right" data-side="right" onmousedown="wfLinkStart(event,'${id}','right')"></div>
        <div class="wf-anchor wf-anchor-bottom" data-side="bottom" onmousedown="wfLinkStart(event,'${id}','bottom')"></div>
      </div>`;
  }
  inner.innerHTML = html;

  // Render arrows
  wfRenderArrows();
  // Render property grid
  wfRenderProps();
}

function _wfBezier(sx, sy, ex, ey, fromSide, toSide) {
  const dist = Math.max(60, Math.hypot(ex - sx, ey - sy) * 0.4);
  // Control point offsets based on side direction
  const dirs = { left: [-1, 0], right: [1, 0], top: [0, -1], bottom: [0, 1] };
  const [fdx, fdy] = dirs[fromSide] || dirs.right;
  const [tdx, tdy] = dirs[toSide] || dirs.left;
  const cx1 = sx + fdx * dist, cy1 = sy + fdy * dist;
  const cx2 = ex + tdx * dist, cy2 = ey + tdy * dist;
  return `M${sx},${sy} C${cx1},${cy1} ${cx2},${cy2} ${ex},${ey}`;
}

function wfRenderArrows() {
  const svg = document.getElementById('wf-arrows');
  if (!svg) return;
  const transitions = _wf.data.transitions || [];
  let paths = '';
  for (const t of transitions) {
    if (!_wf.positions[t.from] || !_wf.positions[t.to]) continue;
    const s = _wfAnchorPos(t.from, t.from_side || 'right');
    const e = _wfAnchorPos(t.to, t.to_side || 'left');
    const sx = s.x, sy = s.y, ex = e.x, ey = e.y;
    const d = _wfBezier(sx, sy, ex, ey, t.from_side || 'right', t.to_side || 'left');
    const gate = t.human_gate ? '(HG)' : '';
    // Invisible wide hit area for right-click
    const idx = transitions.indexOf(t);
    paths += `<path d="${d}" stroke="transparent" stroke-width="14" fill="none" style="pointer-events:stroke;cursor:pointer" onclick="wfSelectTransition(event,${idx})" oncontextmenu="wfArrowContextMenu(event,${idx})" />`;
    const isSel = _wf.selected && typeof _wf.selected === 'object' && _wf.selected.type === 'transition' && _wf.selected.idx === idx;
    paths += `<path d="${d}" ${isSel ? 'stroke="var(--accent)" stroke-width="3"' : ''} marker-end="url(#wf-arrowhead)" />`;
    // Label
    const lx = (sx + ex) / 2, ly = (sy + ey) / 2 - 8;
    if (gate) paths += `<text x="${lx}" y="${ly}" fill="var(--warning)" font-size="10" text-anchor="middle">${gate}</text>`;
  }
  // Draw temporary linking line
  if (_wf.linking && _wf.linkMouse) {
    const s = _wfAnchorPos(_wf.linking.id, _wf.linking.side);
    paths += `<line x1="${s.x}" y1="${s.y}" x2="${_wf.linkMouse.x}" y2="${_wf.linkMouse.y}" stroke-dasharray="6,4" />`;
  }
  svg.innerHTML = `<defs><marker id="wf-arrowhead" markerWidth="10" markerHeight="7" refX="10" refY="3.5" orient="auto"><polygon points="0 0, 10 3.5, 0 7" fill="var(--text-secondary)" /></marker></defs>` + paths;
}

function wfRenderProps() {
  const el = document.getElementById('wf-props');
  if (!el) return;
  if (_wf.selected && typeof _wf.selected === 'object' && _wf.selected.type === 'transition') {
    _wfRenderTransitionProps(el, _wf.selected.idx);
  } else if (_wf.selected && _wf.data.phases[_wf.selected]) {
    _wfRenderPhaseProps(el, _wf.selected);
  } else {
    _wfRenderWorkspaceProps(el);
  }
}

function _wfRenderWorkspaceProps(el) {
  const pg = _wf.data.parallel_groups || { description: '', order: ['A','B','C'] };
  const rules = _wf.data.rules || {};
  const WF_BOOL_RULES = [
    { key: 'critical_alert_blocks_transition', label: 'Alerte critique bloque la transition' },
    { key: 'human_gate_required_for_all_transitions', label: 'Human gate sur toutes les transitions' },
    { key: 'lead_dev_only_dispatcher_for_devs', label: 'Lead dev seul dispatcher pour les devs' },
    { key: 'qa_must_run_after_dev', label: 'QA doit tourner apres les devs' },
  ];
  let rulesHtml = WF_BOOL_RULES.map(r => {
    const checked = !!rules[r.key];
    return `<label class="wf-rule-check"><input type="checkbox" ${checked ? 'checked' : ''} onchange="wfToggleRule('${r.key}',this.checked)" /><span>${escHtml(r.label)}</span></label>`;
  }).join('');
  const maxPar = rules.max_agents_parallel;
  rulesHtml += `<div class="form-group" style="margin-top:0.5rem">
    <label>Max agents en parallele</label>
    <input type="number" min="1" max="20" value="${maxPar != null ? maxPar : ''}" placeholder="ex: 3"
           onchange="wfSetMaxParallel(this.value)" style="width:80px" />
  </div>`;

  // Build parallel groups list with usage check
  const pgOrder = pg.order || [];
  const pgUsed = _wfGetUsedGroups();
  let pgHtml = pgOrder.map(g => {
    const used = pgUsed.has(g);
    const isA = g === 'A';
    return `<div class="wf-prop-item">
      <span class="wf-item-label" style="font-weight:600">${escHtml(g)}</span>
      ${used ? '<span style="font-size:0.65rem;color:var(--text-secondary)">utilise</span>' : ''}
      <button class="btn-icon danger" onclick="wfRemovePG('${escHtml(g)}')" ${isA ? 'disabled title="Le groupe A ne peut pas etre supprime"' : ''}>x</button>
    </div>`;
  }).join('');

  el.innerHTML = `
    <h4>Proprietes du Workflow</h4>

    <div class="wf-props-section">
      <div class="wf-props-section-title">
        Groupes paralleles
        <button class="btn-icon" style="font-size:0.75rem" onclick="wfAddPG()">+</button>
      </div>
      <div class="form-group">
        <label>Description</label>
        <input value="${escHtml(pg.description || '')}" onchange="wfSetPGDesc(this.value)" />
      </div>
      ${pgHtml || '<div style="font-size:0.75rem;color:var(--text-secondary)">Aucun groupe</div>'}
    </div>

    <div class="wf-props-section">
      <div class="wf-props-section-title">Regles</div>
      ${rulesHtml}
    </div>
  `;
}

function _wfRenderTransitionProps(el, idx) {
  const t = (_wf.data.transitions || [])[idx];
  if (!t) { _wf.selected = null; _wfRenderWorkspaceProps(el); return; }
  const phaseIds = Object.keys(_wf.data.phases || {});
  const fromOpts = phaseIds.map(id => `<option value="${escHtml(id)}" ${id===t.from?'selected':''}>${escHtml(_wf.data.phases[id].name || id)}</option>`).join('');
  const toOpts = phaseIds.map(id => `<option value="${escHtml(id)}" ${id===t.to?'selected':''}>${escHtml(_wf.data.phases[id].name || id)}</option>`).join('');
  el.innerHTML = `
    <h4>
      Transition
      <button class="btn-icon danger" onclick="wfCtxDeleteTransition(${idx})" title="Supprimer">&#128465;</button>
    </h4>
    <div class="wf-props-section">
      <div class="form-group">
        <label>De</label>
        <select onchange="wfSetTransitionField(${idx},'from',this.value)">${fromOpts}</select>
      </div>
      <div class="form-group">
        <label>Vers</label>
        <select onchange="wfSetTransitionField(${idx},'to',this.value)">${toOpts}</select>
      </div>
      <div class="form-group">
        <label>Human Gate</label>
        <select onchange="wfSetTransitionField(${idx},'human_gate',this.value==='true')">
          <option value="true" ${t.human_gate ? 'selected' : ''}>Oui</option>
          <option value="false" ${!t.human_gate ? 'selected' : ''}>Non</option>
        </select>
      </div>
    </div>
  `;
}

function wfSetTransitionField(idx, field, val) {
  const t = (_wf.data.transitions || [])[idx];
  if (!t) return;
  t[field] = val;
  wfRender();
}

function wfSelectTransition(e, idx) {
  e.stopPropagation();
  _wf.selected = { type: 'transition', idx };
  wfRender();
}

function _wfRenderPhaseProps(el, phaseId) {
  const p = _wf.data.phases[phaseId];
  const agents = p.agents || {};
  const deliverables = p.deliverables || {};
  const exitConds = p.exit_conditions || {};
  const pgOrder = (_wf.data.parallel_groups && _wf.data.parallel_groups.order) || ['A'];

  // Agents — inline editable blocks
  const allAgentIds = Object.keys(agents);
  let agentsHtml = Object.entries(agents).map(([id, a]) => {
    const pgOpts = pgOrder.map(g => `<option value="${escHtml(g)}" ${g===a.parallel_group?'selected':''}>${g}</option>`).join('');
    const others = allAgentIds.filter(o => o !== id);
    const depsSet = new Set(a.depends_on || []);
    const delegSet = new Set(a.can_delegate_to || []);
    const depsChecks = others.length ? others.map(o =>
      `<label class="wf-inline-check"><input type="checkbox" ${depsSet.has(o)?'checked':''} onchange="_wfToggleAgentList('${phaseId}','${escHtml(id)}','depends_on','${escHtml(o)}',this.checked)" />${escHtml(o)}</label>`
    ).join('') : '<span style="font-size:0.65rem;color:var(--text-secondary)">--</span>';
    const delegChecks = others.length ? others.map(o =>
      `<label class="wf-inline-check"><input type="checkbox" ${delegSet.has(o)?'checked':''} onchange="_wfToggleAgentList('${phaseId}','${escHtml(id)}','can_delegate_to','${escHtml(o)}',this.checked)" />${escHtml(o)}</label>`
    ).join('') : '<span style="font-size:0.65rem;color:var(--text-secondary)">--</span>';
    const collapsed = _wf._collapsed && _wf._collapsed[`${phaseId}:${id}`];
    return `<div class="wf-inline-block${collapsed ? ' collapsed' : ''}">
      <div class="wf-inline-head" onclick="wfToggleCollapse('${phaseId}','${escHtml(id)}')">
        <span class="wf-collapse-arrow">${collapsed ? '\u25b6' : '\u25bc'}</span>
        <select class="wf-inline-agent-select" onclick="event.stopPropagation()" onchange="_wfChangeAgent('${phaseId}','${escHtml(id)}',this.value)" id="wf-agent-sel-${phaseId}-${escHtml(id)}"></select>
        <button class="btn-icon danger" onclick="event.stopPropagation();wfRemoveAgent('${phaseId}','${escHtml(id)}')">x</button>
      </div>
      <div class="wf-inline-fields"${collapsed ? ' style="display:none"' : ''}>
        <input placeholder="Role" value="${escHtml(a.role || '')}" onchange="_wfSetAgentField('${phaseId}','${escHtml(id)}','role',this.value)" />
        <div style="display:flex;gap:0.3rem">
          <select style="flex:1" onchange="_wfSetAgentField('${phaseId}','${escHtml(id)}','required',this.value==='true')">
            <option value="true" ${a.required?'selected':''}>Requis</option><option value="false" ${!a.required?'selected':''}>Optionnel</option>
          </select>
          <select style="width:50px" onchange="_wfSetAgentField('${phaseId}','${escHtml(id)}','parallel_group',this.value)">${pgOpts}</select>
        </div>
        <div class="wf-inline-label">Depends on</div>
        <div class="wf-inline-checks">${depsChecks}</div>
        <div class="wf-inline-label">Can delegate to</div>
        <div class="wf-inline-checks">${delegChecks}</div>
      </div>
    </div>`;
  }).join('');

  // Deliverables — inline editable blocks
  const agentIds = Object.keys(agents);
  let delsHtml = Object.entries(deliverables).map(([id, d]) => {
    const agOpts = agentIds.map(a => `<option value="${escHtml(a)}" ${a===d.agent?'selected':''}>${a}</option>`).join('');
    const colKey = `${phaseId}:del:${id}`;
    const collapsed = _wf._collapsed && _wf._collapsed[colKey];
    return `<div class="wf-inline-block${collapsed ? ' collapsed' : ''}">
      <div class="wf-inline-head" onclick="wfToggleCollapseKey('${colKey}',this)">
        <span class="wf-collapse-arrow">${collapsed ? '\u25b6' : '\u25bc'}</span>
        <span class="wf-inline-id">${escHtml(id)}</span>
        <button class="btn-icon danger" onclick="event.stopPropagation();wfRemoveDeliverable('${phaseId}','${escHtml(id)}')">x</button>
      </div>
      <div class="wf-inline-fields"${collapsed ? ' style="display:none"' : ''}>
        <input placeholder="Description" value="${escHtml(d.description || '')}" onchange="_wfSetDelField('${phaseId}','${escHtml(id)}','description',this.value)" />
        <div style="display:flex;gap:0.3rem">
          <select style="flex:1" onchange="_wfSetDelField('${phaseId}','${escHtml(id)}','agent',this.value)">${agOpts}</select>
          <select style="width:80px" onchange="_wfSetDelField('${phaseId}','${escHtml(id)}','required',this.value==='true')">
            <option value="true" ${d.required?'selected':''}>Requis</option><option value="false" ${!d.required?'selected':''}>Opt</option>
          </select>
        </div>
      </div>
    </div>`;
  }).join('');

  // Exit conditions — inline
  const WF_COND_KEYS = ['all_deliverables_complete','no_critical_alerts','human_gate','qa_verdict_go','no_critical_bugs','staging_validated'];
  let condsHtml = WF_COND_KEYS.map(k => {
    const checked = !!exitConds[k];
    return `<label class="wf-rule-check"><input type="checkbox" ${checked ? 'checked' : ''} onchange="wfToggleCondition('${phaseId}','${k}',this.checked)" /><span>${escHtml(k)}</span></label>`;
  }).join('');

  el.innerHTML = `
    <h4>
      Phase : ${escHtml(p.name || phaseId)}
      <button class="btn-icon danger" onclick="wfDeletePhase('${phaseId}')" title="Supprimer la phase">&#128465;</button>
    </h4>

    <div class="wf-props-section">
      <div class="form-group">
        <label>ID</label>
        <input value="${escHtml(phaseId)}" onchange="wfRenamePhase('${phaseId}',this.value)" />
      </div>
      <div class="form-group">
        <label>Nom</label>
        <input value="${escHtml(p.name || '')}" onchange="wfSetPhaseField('${phaseId}','name',this.value)" />
      </div>
      <div class="form-group">
        <label>Description</label>
        <input value="${escHtml(p.description || '')}" onchange="wfSetPhaseField('${phaseId}','description',this.value)" />
      </div>
      <div class="form-group">
        <label>Ordre</label>
        <input type="number" value="${p.order || 1}" min="1" onchange="wfSetPhaseField('${phaseId}','order',parseInt(this.value))" />
      </div>
      ${p.next_phase ? `<div class="form-group"><label>Phase suivante</label><input value="${escHtml(p.next_phase)}" onchange="wfSetPhaseField('${phaseId}','next_phase',this.value)" /></div>` : ''}
    </div>

    <div class="wf-props-section">
      <div class="wf-props-section-title">
        Agents (${Object.keys(agents).length})
      </div>
      ${agentsHtml || '<div style="font-size:0.75rem;color:var(--text-secondary)">Aucun agent</div>'}
      <select class="wf-add-select" id="wf-add-agent-${phaseId}" onchange="wfAddAgent('${phaseId}',this.value);this.value=''">
        <option value="">+ Ajouter un agent...</option>
      </select>
    </div>

    <div class="wf-props-section">
      <div class="wf-props-section-title">
        Livrables (${Object.keys(deliverables).length})
        <button class="btn-icon" style="font-size:0.75rem" onclick="wfAddDeliverable('${phaseId}')">+</button>
      </div>
      ${delsHtml || '<div style="font-size:0.75rem;color:var(--text-secondary)">Aucun livrable</div>'}
    </div>

    <div class="wf-props-section">
      <div class="wf-props-section-title">Conditions de sortie</div>
      ${condsHtml}
    </div>

    <div class="wf-props-section">
      <div class="wf-props-section-title">Transitions sortantes</div>
      ${(() => {
        const transitions = _wf.data.transitions || [];
        const outgoing = transitions.map((t, i) => ({ t, i })).filter(({ t }) => t.from === phaseId);
        if (outgoing.length === 0) return '<div style="font-size:0.75rem;color:var(--text-secondary)">Aucune transition</div>';
        return outgoing.map(({ t, i }) => {
          const toName = _wf.data.phases[t.to]?.name || t.to;
          return `<div class="wf-transition-item" style="cursor:pointer" onclick="wfSelectTransition(event,${i})">
            <span>Vers ${escHtml(toName)}</span>
            ${t.human_gate ? '<span class="tag tag-yellow" style="font-size:0.6rem;padding:0.05rem 0.3rem">HG</span>' : ''}
            <button class="btn-icon danger" style="margin-left:auto" onclick="event.stopPropagation();wfDeleteTransition(${i})">x</button>
          </div>`;
        }).join('');
      })()}
    </div>
  `;
  setTimeout(() => _wfLoadAgentSelect(phaseId), 0);
}

// ── Workspace interactions ──
function wfWorkspaceClick(e) {
  wfCloseContextMenu();
  if (e.target.closest('.wf-phase')) return;
  _wf.selected = null;
  wfRender();
}

function wfSelectPhase(e, id) {
  e.stopPropagation();
  _wf.selected = id;
  wfRender();
}

// ── Context menu ──
function wfPhaseContextMenu(e, id) {
  e.preventDefault();
  e.stopPropagation();
  wfCloseContextMenu();
  const ws = document.getElementById('wf-workspace');
  const rect = ws.getBoundingClientRect();
  const x = e.clientX - rect.left + ws.scrollLeft;
  const y = e.clientY - rect.top + ws.scrollTop;
  const menu = document.createElement('div');
  menu.className = 'wf-ctx-menu';
  menu.id = 'wf-ctx-menu';
  menu.style.left = x + 'px';
  menu.style.top = y + 'px';
  menu.innerHTML = `
    <div class="wf-ctx-item wf-ctx-danger" onclick="wfCtxDeletePhase('${id}')">Supprimer la phase</div>
  `;
  document.getElementById('wf-workspace-inner').appendChild(menu);
  setTimeout(() => document.addEventListener('mousedown', _wfCloseCtxOnClick, { once: true }), 0);
}

function wfArrowContextMenu(e, idx) {
  e.preventDefault();
  e.stopPropagation();
  wfCloseContextMenu();
  const ws = document.getElementById('wf-workspace');
  const rect = ws.getBoundingClientRect();
  const x = e.clientX - rect.left + ws.scrollLeft;
  const y = e.clientY - rect.top + ws.scrollTop;
  const t = (_wf.data.transitions || [])[idx];
  if (!t) return;
  const menu = document.createElement('div');
  menu.className = 'wf-ctx-menu';
  menu.id = 'wf-ctx-menu';
  menu.style.left = x + 'px';
  menu.style.top = y + 'px';
  menu.innerHTML = `
    <div class="wf-ctx-item" style="font-size:0.7rem;color:var(--text-secondary);cursor:default">${escHtml(t.from)} → ${escHtml(t.to)}</div>
    <div class="wf-ctx-item wf-ctx-danger" onclick="wfCtxDeleteTransition(${idx})">Supprimer la transition</div>
  `;
  document.getElementById('wf-workspace-inner').appendChild(menu);
  setTimeout(() => document.addEventListener('mousedown', _wfCloseCtxOnClick, { once: true }), 0);
}

function wfCtxDeleteTransition(idx) {
  wfCloseContextMenu();
  _wf.data.transitions.splice(idx, 1);
  if (_wf.selected && typeof _wf.selected === 'object' && _wf.selected.type === 'transition') {
    _wf.selected = null;
  }
  wfRender();
}

function _wfCloseCtxOnClick(e) {
  if (!e.target.closest('.wf-ctx-menu')) wfCloseContextMenu();
}

function wfCloseContextMenu() {
  const m = document.getElementById('wf-ctx-menu');
  if (m) m.remove();
}

function wfCtxDeletePhase(id) {
  wfCloseContextMenu();
  delete _wf.data.phases[id];
  delete _wf.positions[id];
  _wf.data.transitions = (_wf.data.transitions || []).filter(t => t.from !== id && t.to !== id);
  _wf.selected = null;
  wfRender();
}

// ── Drag phases ──
function wfPhaseMouseDown(e, id) {
  if (e.button !== 0) return;
  const el = document.getElementById(`wf-p-${id}`);
  if (!el) return;
  _wf.dragging = id;
  _wf.dragOffset = {
    x: e.clientX - (_wf.positions[id]?.x || 0),
    y: e.clientY - (_wf.positions[id]?.y || 0)
  };
  const ws = document.getElementById('wf-workspace');
  const scrollLeft = ws.scrollLeft;
  const scrollTop = ws.scrollTop;
  const rect = ws.getBoundingClientRect();
  _wf.dragOffset = {
    x: e.clientX - rect.left + scrollLeft - (_wf.positions[id]?.x || 0),
    y: e.clientY - rect.top + scrollTop - (_wf.positions[id]?.y || 0)
  };
  document.addEventListener('mousemove', _wfDragMove);
  document.addEventListener('mouseup', _wfDragEnd);
  e.preventDefault();
}

function _wfDragMove(e) {
  if (!_wf || !_wf.dragging) return;
  const ws = document.getElementById('wf-workspace');
  const rect = ws.getBoundingClientRect();
  const x = Math.max(0, e.clientX - rect.left + ws.scrollLeft - _wf.dragOffset.x);
  const y = Math.max(0, e.clientY - rect.top + ws.scrollTop - _wf.dragOffset.y);
  _wf.positions[_wf.dragging] = { x, y };
  const el = document.getElementById(`wf-p-${_wf.dragging}`);
  if (el) { el.style.left = x + 'px'; el.style.top = y + 'px'; }
  wfRenderArrows();
}

function _wfDragEnd() {
  if (_wf) {
    _wf.dragging = null;
    _wfSaveDesign();
  }
  document.removeEventListener('mousemove', _wfDragMove);
  document.removeEventListener('mouseup', _wfDragEnd);
}

function _wfSaveDesign() {
  if (!_wf) return;
  api(`${_wf.designBase}/${encodeURIComponent(_wf.dir)}`, {
    method: 'PUT',
    body: { positions: _wf.positions }
  }).catch(() => {});
}

// ── Link / draw arrows ──
function _wfAnchorPos(phaseId, side) {
  const el = document.getElementById(`wf-p-${phaseId}`);
  const pos = _wf.positions[phaseId] || { x: 0, y: 0 };
  const w = el ? el.offsetWidth : 200;
  const h = el ? el.offsetHeight : 80;
  if (side === 'left')   return { x: pos.x,         y: pos.y + h / 2 };
  if (side === 'top')    return { x: pos.x + w / 2,  y: pos.y };
  if (side === 'bottom') return { x: pos.x + w / 2,  y: pos.y + h };
  /* right */             return { x: pos.x + w,      y: pos.y + h / 2 };
}

function wfLinkStart(e, fromId, fromSide) {
  e.stopPropagation();
  e.preventDefault();
  _wf.linking = { id: fromId, side: fromSide };
  _wf.dragging = null;
  const ws = document.getElementById('wf-workspace');
  const rect = ws.getBoundingClientRect();
  _wf.linkMouse = { x: e.clientX - rect.left + ws.scrollLeft, y: e.clientY - rect.top + ws.scrollTop };
  document.addEventListener('mousemove', _wfLinkMove);
  document.addEventListener('mouseup', _wfLinkEnd);
}

function _wfLinkMove(e) {
  if (!_wf || !_wf.linking) return;
  const ws = document.getElementById('wf-workspace');
  const rect = ws.getBoundingClientRect();
  _wf.linkMouse = { x: e.clientX - rect.left + ws.scrollLeft, y: e.clientY - rect.top + ws.scrollTop };
  wfRenderArrows();
}

function _wfLinkEnd(e) {
  document.removeEventListener('mousemove', _wfLinkMove);
  document.removeEventListener('mouseup', _wfLinkEnd);
  if (!_wf || !_wf.linking) return;
  const fromId = _wf.linking.id;
  const fromSide = _wf.linking.side;
  _wf.linking = null;
  _wf.linkMouse = null;
  // Find target anchor or phase
  const target = document.elementFromPoint(e.clientX, e.clientY);
  const anchor = target ? target.closest('.wf-anchor') : null;
  const phaseEl = target ? target.closest('.wf-phase') : null;
  let toId = null, toSide = 'left';
  if (anchor && anchor.closest('.wf-phase')) {
    toId = anchor.closest('.wf-phase').dataset.id;
    toSide = anchor.dataset.side || 'left';
  } else if (phaseEl) {
    toId = phaseEl.dataset.id;
  }
  if (toId && toId !== fromId) {
    const exists = (_wf.data.transitions || []).some(t => t.from === fromId && t.to === toId);
    if (!exists) {
      if (!_wf.data.transitions) _wf.data.transitions = [];
      _wf.data.transitions.push({ from: fromId, to: toId, from_side: fromSide, to_side: toSide, human_gate: true });
    }
  }
  wfRender();
}

// ── Phase CRUD ──
function wfAddPhase() {
  const phases = _wf.data.phases || {};
  let num = Object.keys(phases).length + 1;
  let id = `phase_${num}`;
  while (phases[id]) { num++; id = `phase_${num}`; }
  const maxOrder = Object.values(phases).reduce((m, p) => Math.max(m, p.order || 0), 0);
  _wf.data.phases[id] = {
    name: `Phase ${num}`,
    description: '',
    order: maxOrder + 1,
    agents: {},
    deliverables: {},
    exit_conditions: { human_gate: true }
  };
  _wfCalcPositions();
  _wf.selected = id;
  wfRender();
}

function wfDeletePhase(id) {
  delete _wf.data.phases[id];
  delete _wf.positions[id];
  _wf.data.transitions = (_wf.data.transitions || []).filter(t => t.from !== id && t.to !== id);
  _wf.selected = null;
  wfRender();
}

function wfRenamePhase(oldId, newId) {
  newId = newId.trim().replace(/[^a-z0-9_-]/gi, '_').toLowerCase();
  if (!newId || newId === oldId) return;
  if (_wf.data.phases[newId]) { toast('Cet ID existe deja', 'error'); wfRender(); return; }
  // Move phase data
  _wf.data.phases[newId] = _wf.data.phases[oldId];
  delete _wf.data.phases[oldId];
  // Move position
  if (_wf.positions[oldId]) {
    _wf.positions[newId] = _wf.positions[oldId];
    delete _wf.positions[oldId];
  }
  // Update transitions
  for (const t of (_wf.data.transitions || [])) {
    if (t.from === oldId) t.from = newId;
    if (t.to === oldId) t.to = newId;
  }
  // Update next_phase references
  for (const p of Object.values(_wf.data.phases)) {
    if (p.next_phase === oldId) p.next_phase = newId;
  }
  // Update selection
  if (_wf.selected === oldId) _wf.selected = newId;
  wfRender();
}

function wfSetPhaseField(phaseId, field, val) {
  if (!_wf.data.phases[phaseId]) return;
  _wf.data.phases[phaseId][field] = val;
  if (field === 'order' || field === 'name') wfRender();
}

// ── Collapse agent blocks ──
function wfToggleCollapse(phaseId, agentId) {
  if (!_wf._collapsed) _wf._collapsed = {};
  const key = `${phaseId}:${agentId}`;
  _wf._collapsed[key] = !_wf._collapsed[key];
  const block = document.getElementById(`wf-agent-sel-${phaseId}-${agentId}`)?.closest('.wf-inline-block');
  if (!block) return;
  const fields = block.querySelector('.wf-inline-fields');
  const arrow = block.querySelector('.wf-collapse-arrow');
  if (_wf._collapsed[key]) {
    block.classList.add('collapsed');
    if (fields) fields.style.display = 'none';
    if (arrow) arrow.textContent = '\u25b6';
  } else {
    block.classList.remove('collapsed');
    if (fields) fields.style.display = '';
    if (arrow) arrow.textContent = '\u25bc';
  }
}

function wfToggleCollapseKey(key, headEl) {
  if (!_wf._collapsed) _wf._collapsed = {};
  _wf._collapsed[key] = !_wf._collapsed[key];
  const block = headEl.closest('.wf-inline-block');
  if (!block) return;
  const fields = block.querySelector('.wf-inline-fields');
  const arrow = block.querySelector('.wf-collapse-arrow');
  if (_wf._collapsed[key]) {
    block.classList.add('collapsed');
    if (fields) fields.style.display = 'none';
    if (arrow) arrow.textContent = '\u25b6';
  } else {
    block.classList.remove('collapsed');
    if (fields) fields.style.display = '';
    if (arrow) arrow.textContent = '\u25bc';
  }
}

// ── Agent CRUD within a phase (inline, no modal) ──
function wfAddAgent(phaseId, agentId) {
  if (!agentId) return;
  if (!_wf.data.phases[phaseId].agents) _wf.data.phases[phaseId].agents = {};
  if (_wf.data.phases[phaseId].agents[agentId]) { toast('Agent deja dans cette phase', 'error'); return; }
  _wf.data.phases[phaseId].agents[agentId] = {
    role: '',
    required: true,
    parallel_group: (_wf.data.parallel_groups && _wf.data.parallel_groups.order && _wf.data.parallel_groups.order[0]) || 'A'
  };
  wfRender();
}

async function _wfLoadAgentSelect(phaseId) {
  const assigned = new Set(Object.keys(_wf.data.phases[phaseId].agents || {}));
  const registryBase = _wf.apiBase.includes('templates') ? '/api/templates/registry' : '/api/agents/registry';
  let allAgents = [];
  try {
    const reg = await api(`${registryBase}/${encodeURIComponent(_wf.dir)}`);
    allAgents = Object.keys(reg.agents || reg || {});
  } catch {}
  // Populate the "add agent" select
  const addSel = document.getElementById(`wf-add-agent-${phaseId}`);
  if (addSel && addSel.options.length <= 1) {
    const available = allAgents.filter(a => !assigned.has(a));
    available.forEach(a => {
      const opt = document.createElement('option');
      opt.value = a;
      opt.textContent = a;
      addSel.appendChild(opt);
    });
    if (available.length === 0) {
      addSel.options[0].textContent = '(tous assignes)';
      addSel.disabled = true;
    }
  }
  // Populate each agent's identity select (current + available from registry)
  for (const agentId of assigned) {
    const sel = document.getElementById(`wf-agent-sel-${phaseId}-${agentId}`);
    if (!sel || sel.options.length > 0) continue;
    // Current agent (selected)
    const cur = document.createElement('option');
    cur.value = agentId;
    cur.textContent = agentId;
    cur.selected = true;
    sel.appendChild(cur);
    // Other available agents from registry (not already assigned)
    const others = allAgents.filter(a => a !== agentId && !assigned.has(a));
    others.forEach(a => {
      const opt = document.createElement('option');
      opt.value = a;
      opt.textContent = a;
      sel.appendChild(opt);
    });
  }
}

function _wfChangeAgent(phaseId, oldId, newId) {
  if (!newId || newId === oldId) return;
  const phase = _wf.data.phases[phaseId];
  if (!phase || !phase.agents) return;
  if (phase.agents[newId]) { toast('Agent deja dans cette phase', 'error'); wfRender(); return; }
  // Move agent data from oldId to newId
  phase.agents[newId] = phase.agents[oldId];
  delete phase.agents[oldId];
  // Update deliverables referencing old agent
  for (const d of Object.values(phase.deliverables || {})) {
    if (d.agent === oldId) d.agent = newId;
  }
  // Update depends_on / can_delegate_to referencing old agent
  for (const a of Object.values(phase.agents)) {
    if (a.depends_on) a.depends_on = a.depends_on.map(x => x === oldId ? newId : x);
    if (a.can_delegate_to) a.can_delegate_to = a.can_delegate_to.map(x => x === oldId ? newId : x);
  }
  wfRender();
}

// Inline field setters for agents
function _wfSetAgentField(phaseId, agentId, field, val) {
  const ag = _wf.data.phases[phaseId]?.agents?.[agentId];
  if (!ag) return;
  ag[field] = val;
}

function _wfToggleAgentList(phaseId, agentId, field, targetId, checked) {
  const ag = _wf.data.phases[phaseId]?.agents?.[agentId];
  if (!ag) return;
  if (!ag[field]) ag[field] = [];
  if (checked) {
    if (!ag[field].includes(targetId)) ag[field].push(targetId);
  } else {
    ag[field] = ag[field].filter(x => x !== targetId);
  }
  if (ag[field].length === 0) delete ag[field];
}

function wfRemoveAgent(phaseId, agentId) {
  delete _wf.data.phases[phaseId].agents[agentId];
  wfRender();
}

// ── Deliverable CRUD (inline, no modal) ──
function wfAddDeliverable(phaseId) {
  const agentIds = Object.keys(_wf.data.phases[phaseId].agents || {});
  if (agentIds.length === 0) { toast('Ajoutez d\'abord un agent a cette phase', 'error'); return; }
  if (!_wf.data.phases[phaseId].deliverables) _wf.data.phases[phaseId].deliverables = {};
  const existing = Object.keys(_wf.data.phases[phaseId].deliverables);
  let num = existing.length + 1;
  let id = `deliverable_${num}`;
  while (existing.includes(id)) { num++; id = `deliverable_${num}`; }
  _wf.data.phases[phaseId].deliverables[id] = {
    description: '',
    agent: agentIds[0],
    required: true
  };
  wfRender();
}

// Inline field setter for deliverables
function _wfSetDelField(phaseId, delId, field, val) {
  const d = _wf.data.phases[phaseId]?.deliverables?.[delId];
  if (!d) return;
  d[field] = val;
}

function wfRemoveDeliverable(phaseId, delId) {
  delete _wf.data.phases[phaseId].deliverables[delId];
  wfRender();
}

// ── Exit conditions (inline checkboxes) ──
function wfToggleCondition(phaseId, key, checked) {
  if (!_wf.data.phases[phaseId].exit_conditions) _wf.data.phases[phaseId].exit_conditions = {};
  if (checked) {
    _wf.data.phases[phaseId].exit_conditions[key] = true;
  } else {
    delete _wf.data.phases[phaseId].exit_conditions[key];
  }
}

// ── Transitions CRUD ──
function wfDeleteTransition(idx) {
  _wf.data.transitions.splice(idx, 1);
  wfRender();
}

// ── Rules CRUD ──
function wfToggleRule(key, checked) {
  if (!_wf.data.rules) _wf.data.rules = {};
  if (checked) {
    _wf.data.rules[key] = true;
  } else {
    delete _wf.data.rules[key];
  }
}

function wfSetMaxParallel(val) {
  if (!_wf.data.rules) _wf.data.rules = {};
  const n = parseInt(val, 10);
  if (isNaN(n) || val.trim() === '') {
    delete _wf.data.rules.max_agents_parallel;
  } else {
    _wf.data.rules.max_agents_parallel = n;
  }
}

// ── Parallel groups ──
function wfSetPGDesc(val) {
  if (!_wf.data.parallel_groups) _wf.data.parallel_groups = {};
  _wf.data.parallel_groups.description = val;
}

function _wfGetUsedGroups() {
  const used = new Set();
  for (const phase of Object.values(_wf.data.phases || {})) {
    for (const agent of Object.values(phase.agents || {})) {
      if (agent.parallel_group) used.add(agent.parallel_group);
    }
  }
  return used;
}

function wfAddPG() {
  if (!_wf.data.parallel_groups) _wf.data.parallel_groups = { description: '', order: [] };
  if (!_wf.data.parallel_groups.order) _wf.data.parallel_groups.order = [];
  const existing = _wf.data.parallel_groups.order;
  // Find next available letter
  let letter = 'A';
  for (let c = 65; c <= 90; c++) {
    const l = String.fromCharCode(c);
    if (!existing.includes(l)) { letter = l; break; }
  }
  existing.push(letter);
  wfRender();
}

function wfRemovePG(name) {
  if (name === 'A') { toast('Le groupe A ne peut pas etre supprime', 'error'); return; }
  if (!_wf.data.parallel_groups || !_wf.data.parallel_groups.order) return;
  // Reassign agents using this group to group A
  for (const phase of Object.values(_wf.data.phases || {})) {
    for (const agent of Object.values(phase.agents || {})) {
      if (agent.parallel_group === name) agent.parallel_group = 'A';
    }
  }
  _wf.data.parallel_groups.order = _wf.data.parallel_groups.order.filter(g => g !== name);
  wfRender();
}

// ── JSON view ──
function wfShowJSON() {
  showModal(`
    <div class="modal-header">
      <h3>Workflow JSON</h3>
      <button class="btn-icon" onclick="closeModal();wfRender()">&times;</button>
    </div>
    <div class="form-group">
      <textarea id="wf-raw-json" style="min-height:450px;font-family:monospace;font-size:0.8rem;white-space:pre;tab-size:2">${escHtml(JSON.stringify(_wf.data, null, 2))}</textarea>
    </div>
    <div class="modal-actions">
      <button class="btn btn-outline" onclick="closeModal();wfRender()">Annuler</button>
      <button class="btn btn-primary" onclick="wfImportJSON()">Importer</button>
    </div>
  `, 'modal-wide');
}

function wfImportJSON() {
  const raw = document.getElementById('wf-raw-json').value;
  let data;
  try { data = JSON.parse(raw); } catch { toast('JSON invalide', 'error'); return; }
  _wf.data = data;
  _wf.positions = {};
  _wf.selected = null;
  _wf._collapsed = {};
  // Close the JSON modal and reopen the workflow editor with new data
  closeModal();
  _wfCalcPositions();
  _wfSaveDesign();
  _wfOpenEditorUI();
}

// ═══════════════════════════════════════════════════
// CHANNELS
// ═══════════════════════════════════════════════════
let _mailData = {};
let _discordData = {};

function loadChannels() {
  loadDiscord();
}

// ── Discord ──
async function loadDiscord() {
  try {
    _discordData = await api('/api/discord');
    _renderDiscord();
  } catch (e) { toast(e.message, 'error'); }
}

function _renderDiscord() {
  const d = _discordData;
  const bot = d.bot || {};
  const ch = d.channels || {};
  const fmt = d.formatting || {};
  const to = d.timeouts || {};

  // General
  const toggle = document.getElementById('discord-enabled-toggle');
  if (d.enabled) toggle.classList.add('active'); else toggle.classList.remove('active');
  document.getElementById('discord-bot-prefix').value = bot.prefix || '!';
  document.getElementById('discord-bot-token-env').value = bot.token_env || '';
  document.getElementById('discord-bot-status').value = bot.status_message || '';

  // Channels
  document.getElementById('discord-ch-commands').value = ch.commands || '';
  document.getElementById('discord-ch-review').value = ch.review || '';
  document.getElementById('discord-ch-logs').value = ch.logs || '';
  document.getElementById('discord-ch-alerts').value = ch.alerts || '';
  document.getElementById('discord-guild-id').value = (d.guild || {}).id || '';

  // Aliases
  _renderDiscordAliases();

  // Formatting
  document.getElementById('discord-fmt-maxlen').value = fmt.max_message_length || 1900;
  const splitToggle = document.getElementById('discord-fmt-split');
  if (fmt.split_on_newlines !== false) splitToggle.classList.add('active'); else splitToggle.classList.remove('active');
  document.getElementById('discord-fmt-react-proc').value = fmt.reaction_processing || '';
  document.getElementById('discord-fmt-react-orch').value = fmt.reaction_orchestrator || '';

  // Timeouts
  document.getElementById('discord-to-api').value = to.api_call || '';
  document.getElementById('discord-to-gate').value = to.human_gate || '';
  document.getElementById('discord-to-reminders').value = (to.reminder_intervals || []).join(', ');
}

function _renderDiscordAliases() {
  const aliases = _discordData.aliases || {};
  const tbody = document.getElementById('discord-aliases-body');
  const rows = Object.entries(aliases).sort(([a], [b]) => a.localeCompare(b)).map(([alias, agent]) =>
    `<tr>
      <td><input class="discord-alias-key" value="${escHtml(alias)}" style="font-size:0.85rem" /></td>
      <td><input class="discord-alias-val" value="${escHtml(agent)}" style="font-size:0.85rem" /></td>
      <td><button class="btn-icon danger" onclick="this.closest('tr').remove()" title="Supprimer">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>
      </button></td>
    </tr>`
  ).join('');
  tbody.innerHTML = rows || '<tr><td colspan="3" style="text-align:center;color:var(--text-secondary)">Aucun alias</td></tr>';
}

function addDiscordAlias() {
  const tbody = document.getElementById('discord-aliases-body');
  // Remove "aucun alias" placeholder if present
  if (tbody.querySelector('td[colspan]')) tbody.innerHTML = '';
  tbody.insertAdjacentHTML('beforeend', `<tr>
    <td><input class="discord-alias-key" placeholder="alias" style="font-size:0.85rem" /></td>
    <td><input class="discord-alias-val" placeholder="agent_id" style="font-size:0.85rem" /></td>
    <td><button class="btn-icon danger" onclick="this.closest('tr').remove()" title="Supprimer">
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>
    </button></td>
  </tr>`);
}

function _collectDiscordData() {
  const _isActive = (id) => document.getElementById(id).classList.contains('active');
  // Collect aliases from table rows
  const aliases = {};
  document.querySelectorAll('#discord-aliases-body tr').forEach(row => {
    const key = row.querySelector('.discord-alias-key');
    const val = row.querySelector('.discord-alias-val');
    if (key && val && key.value.trim() && val.value.trim()) {
      aliases[key.value.trim()] = val.value.trim();
    }
  });
  const reminders = document.getElementById('discord-to-reminders').value
    .split(',').map(s => parseInt(s.trim())).filter(n => !isNaN(n));

  return {
    enabled: _isActive('discord-enabled-toggle'),
    default_channel: 'discord',
    bot: {
      token_env: document.getElementById('discord-bot-token-env').value.trim(),
      prefix: document.getElementById('discord-bot-prefix').value.trim() || '!',
      status_message: document.getElementById('discord-bot-status').value.trim(),
    },
    channels: {
      commands: document.getElementById('discord-ch-commands').value.trim(),
      review: document.getElementById('discord-ch-review').value.trim(),
      logs: document.getElementById('discord-ch-logs').value.trim(),
      alerts: document.getElementById('discord-ch-alerts').value.trim(),
    },
    guild: {
      id: document.getElementById('discord-guild-id').value.trim(),
    },
    aliases,
    formatting: {
      max_message_length: parseInt(document.getElementById('discord-fmt-maxlen').value) || 1900,
      split_on_newlines: _isActive('discord-fmt-split'),
      reaction_processing: document.getElementById('discord-fmt-react-proc').value,
      reaction_orchestrator: document.getElementById('discord-fmt-react-orch').value,
    },
    timeouts: {
      api_call: parseInt(document.getElementById('discord-to-api').value) || 30,
      human_gate: parseInt(document.getElementById('discord-to-gate').value) || 1800,
      reminder_intervals: reminders.length ? reminders : [120, 240, 480, 960],
    },
  };
}

async function saveDiscord() {
  try {
    const data = _collectDiscordData();
    await api('/api/discord', { method: 'PUT', body: data });
    _discordData = data;
    toast('Configuration Discord sauvegardee', 'success');
    // Restart discord-bot container if enabled
    if (data.enabled) {
      try {
        await api('/api/monitoring/container/discord-bot/restart', { method: 'POST' });
        toast('Container discord-bot redémarre', 'success');
      } catch (e) {
        toast('Config sauvegardee mais le container n\'a pas pu etre redémarre : ' + e.message, 'warning');
      }
    }
  } catch (e) { toast(e.message, 'error'); }
}

// ── Mail ──
async function loadMail() {
  try {
    _mailData = await api('/api/mail');
    _renderMail();
  } catch (e) { toast(e.message, 'error'); }
}

function _renderMail() {
  const d = _mailData;
  // Normalize smtp/imap/templates to arrays
  if (!Array.isArray(d.smtp)) d.smtp = d.smtp && typeof d.smtp === 'object' ? [{ name: 'default', ...d.smtp }] : [];
  if (!Array.isArray(d.imap)) d.imap = d.imap && typeof d.imap === 'object' ? [{ name: 'default', ...d.imap }] : [];
  if (!Array.isArray(d.templates)) {
    // Convert legacy dict to array
    const t = d.templates || {};
    d.templates = [];
    if (t.notification_subject) d.templates.push({ name: 'notification', subject: t.notification_subject, body: '' });
    if (t.question_subject) d.templates.push({ name: 'question', subject: t.question_subject, body: '' });
    if (t.approval_subject) d.templates.push({ name: 'approval', subject: t.approval_subject, body: t.approval_instructions || '' });
    if (t.reminder_prefix) d.templates.push({ name: 'reminder', subject: t.reminder_prefix, body: '' });
    if (t.footer_text) d.templates.push({ name: 'footer', subject: '', body: t.footer_text });
  }
  const listener = d.listener || {};
  const sec = d.security || {};

  // SMTP + IMAP lists
  _renderSmtpList();
  _renderImapList();

  // Listener
  document.getElementById('mail-listener-interval').value = listener.poll_interval || '';
  document.getElementById('mail-listener-allowed').value = (listener.allowed_senders || []).join('\n');
  document.getElementById('mail-listener-ignore').value = (listener.ignore_patterns || []).join('\n');

  // Templates list
  _renderTplMailList();

  // Security
  const secTls = document.getElementById('mail-sec-tls');
  if (sec.require_tls) secTls.classList.add('active'); else secTls.classList.remove('active');
  const secVerify = document.getElementById('mail-sec-verify');
  if (sec.verify_sender) secVerify.classList.add('active'); else secVerify.classList.remove('active');
  document.getElementById('mail-sec-maxsize').value = sec.max_body_size || '';

}

// ── SMTP list rendering ──
function _renderSmtpList() {
  const list = document.getElementById('mail-smtp-list');
  const entries = _mailData.smtp || [];
  if (entries.length === 0) {
    list.innerHTML = '<p style="color:var(--text-secondary);padding:1rem;font-size:0.85rem">Aucune configuration SMTP. Cliquez sur "+ Ajouter".</p>';
    return;
  }
  let html = '<table><thead><tr><th>Nom</th><th>Host</th><th>Port</th><th>TLS/SSL</th><th>Utilisateur</th><th>Expediteur</th><th>Actions</th></tr></thead><tbody>';
  entries.forEach((s, i) => {
    const flags = [s.use_tls ? 'TLS' : '', s.use_ssl ? 'SSL' : ''].filter(Boolean).join('+') || '—';
    html += `<tr>
      <td><strong>${escHtml(s.name || 'sans nom')}</strong></td>
      <td>${escHtml(s.host || '')}</td>
      <td>${s.port || ''}</td>
      <td>${flags}</td>
      <td>${escHtml(s.user || '')}</td>
      <td>${escHtml(s.from_address || '')}</td>
      <td style="white-space:nowrap">
        <button class="btn btn-outline btn-sm" onclick="showAddSmtpModal(${i})">Modifier</button>
        <button class="btn btn-outline btn-sm" onclick="deleteSmtpEntry(${i})" style="color:var(--error)">Supprimer</button>
      </td>
    </tr>`;
  });
  html += '</tbody></table>';
  list.innerHTML = html;
}

function showAddSmtpModal(idx) {
  const isNew = idx < 0;
  document.getElementById('modal-smtp-title').textContent = isNew ? 'Nouvelle configuration SMTP' : 'Modifier la configuration SMTP';
  document.getElementById('smtp-edit-idx').value = idx;

  // Fill preset dropdown
  const presetSel = document.getElementById('smtp-edit-preset');
  presetSel.innerHTML = '<option value="">— aucun —</option>';
  for (const [name, preset] of Object.entries(_mailData.presets || {})) {
    if (preset.smtp) {
      presetSel.innerHTML += `<option value="${escHtml(name)}">${name.charAt(0).toUpperCase() + name.slice(1)}${preset.notes ? ' — ' + escHtml(preset.notes.substring(0, 40)) : ''}</option>`;
    }
  }

  const entry = isNew ? {} : (_mailData.smtp || [])[idx] || {};
  document.getElementById('smtp-edit-name').value = entry.name || '';
  document.getElementById('smtp-edit-host').value = entry.host || '';
  document.getElementById('smtp-edit-port').value = entry.port || '';
  document.getElementById('smtp-edit-user').value = entry.user || '';
  document.getElementById('smtp-edit-password-env').value = entry.password_env || '';
  document.getElementById('smtp-edit-from-address').value = entry.from_address || '';
  document.getElementById('smtp-edit-from-name').value = entry.from_name || '';
  const tls = document.getElementById('smtp-edit-tls');
  if (entry.use_tls) tls.classList.add('active'); else tls.classList.remove('active');
  const ssl = document.getElementById('smtp-edit-ssl');
  if (entry.use_ssl) ssl.classList.add('active'); else ssl.classList.remove('active');

  document.getElementById('modal-smtp-edit').style.display = 'flex';
}

function applySmtpPreset() {
  const name = document.getElementById('smtp-edit-preset').value;
  if (!name) return;
  const preset = (_mailData.presets || {})[name];
  if (!preset || !preset.smtp) return;
  const s = preset.smtp;
  if (s.host) document.getElementById('smtp-edit-host').value = s.host;
  if (s.port) document.getElementById('smtp-edit-port').value = s.port;
  const tls = document.getElementById('smtp-edit-tls');
  if (s.use_tls) tls.classList.add('active'); else tls.classList.remove('active');
  const ssl = document.getElementById('smtp-edit-ssl');
  if (s.use_ssl) ssl.classList.add('active'); else ssl.classList.remove('active');
  toast(`Preset "${name}" applique`, 'success');
}

async function saveSmtpEntry() {
  const _isActive = (id) => document.getElementById(id).classList.contains('active');
  const name = document.getElementById('smtp-edit-name').value.trim();
  if (!name) { toast('Nom requis', 'error'); return; }
  const entry = {
    name,
    host: document.getElementById('smtp-edit-host').value.trim(),
    port: parseInt(document.getElementById('smtp-edit-port').value) || 587,
    use_tls: _isActive('smtp-edit-tls'),
    use_ssl: _isActive('smtp-edit-ssl'),
    user: document.getElementById('smtp-edit-user').value.trim(),
    password_env: document.getElementById('smtp-edit-password-env').value.trim(),
    from_address: document.getElementById('smtp-edit-from-address').value.trim(),
    from_name: document.getElementById('smtp-edit-from-name').value.trim(),
  };
  if (!Array.isArray(_mailData.smtp)) _mailData.smtp = [];
  const idx = parseInt(document.getElementById('smtp-edit-idx').value);
  if (idx >= 0 && idx < _mailData.smtp.length) {
    _mailData.smtp[idx] = entry;
  } else {
    _mailData.smtp.push(entry);
  }
  closeModal('modal-smtp-edit');
  await saveMail();
}

async function deleteSmtpEntry(idx) {
  const entry = (_mailData.smtp || [])[idx];
  if (!entry) return;
  if (!confirm(`Supprimer la configuration SMTP "${entry.name || idx}" ?`)) return;
  _mailData.smtp.splice(idx, 1);
  await saveMail();
}

// ── IMAP list rendering ──
function _renderImapList() {
  const list = document.getElementById('mail-imap-list');
  const entries = _mailData.imap || [];
  if (entries.length === 0) {
    list.innerHTML = '<p style="color:var(--text-secondary);padding:1rem;font-size:0.85rem">Aucune configuration IMAP. Cliquez sur "+ Ajouter".</p>';
    return;
  }
  let html = '<table><thead><tr><th>Nom</th><th>Host</th><th>Port</th><th>SSL</th><th>Utilisateur</th><th>Actions</th></tr></thead><tbody>';
  entries.forEach((s, i) => {
    html += `<tr>
      <td><strong>${escHtml(s.name || 'sans nom')}</strong></td>
      <td>${escHtml(s.host || '')}</td>
      <td>${s.port || ''}</td>
      <td>${s.use_ssl ? 'Oui' : 'Non'}</td>
      <td>${escHtml(s.user || '')}</td>
      <td style="white-space:nowrap">
        <button class="btn btn-outline btn-sm" onclick="showAddImapModal(${i})">Modifier</button>
        <button class="btn btn-outline btn-sm" onclick="deleteImapEntry(${i})" style="color:var(--error)">Supprimer</button>
      </td>
    </tr>`;
  });
  html += '</tbody></table>';
  list.innerHTML = html;
}

function showAddImapModal(idx) {
  const isNew = idx < 0;
  document.getElementById('modal-imap-title').textContent = isNew ? 'Nouvelle configuration IMAP' : 'Modifier la configuration IMAP';
  document.getElementById('imap-edit-idx').value = idx;

  // Fill preset dropdown
  const presetSel = document.getElementById('imap-edit-preset');
  presetSel.innerHTML = '<option value="">— aucun —</option>';
  for (const [name, preset] of Object.entries(_mailData.presets || {})) {
    if (preset.imap) {
      presetSel.innerHTML += `<option value="${escHtml(name)}">${name.charAt(0).toUpperCase() + name.slice(1)}${preset.notes ? ' — ' + escHtml(preset.notes.substring(0, 40)) : ''}</option>`;
    }
  }

  const entry = isNew ? {} : (_mailData.imap || [])[idx] || {};
  document.getElementById('imap-edit-name').value = entry.name || '';
  document.getElementById('imap-edit-host').value = entry.host || '';
  document.getElementById('imap-edit-port').value = entry.port || '';
  document.getElementById('imap-edit-user').value = entry.user || '';
  document.getElementById('imap-edit-password-env').value = entry.password_env || '';
  const ssl = document.getElementById('imap-edit-ssl');
  if (entry.use_ssl) ssl.classList.add('active'); else ssl.classList.remove('active');

  document.getElementById('modal-imap-edit').style.display = 'flex';
}

function applyImapPreset() {
  const name = document.getElementById('imap-edit-preset').value;
  if (!name) return;
  const preset = (_mailData.presets || {})[name];
  if (!preset || !preset.imap) return;
  const s = preset.imap;
  if (s.host) document.getElementById('imap-edit-host').value = s.host;
  if (s.port) document.getElementById('imap-edit-port').value = s.port;
  const ssl = document.getElementById('imap-edit-ssl');
  if (s.use_ssl) ssl.classList.add('active'); else ssl.classList.remove('active');
  toast(`Preset "${name}" applique`, 'success');
}

async function saveImapEntry() {
  const _isActive = (id) => document.getElementById(id).classList.contains('active');
  const name = document.getElementById('imap-edit-name').value.trim();
  if (!name) { toast('Nom requis', 'error'); return; }
  const entry = {
    name,
    host: document.getElementById('imap-edit-host').value.trim(),
    port: parseInt(document.getElementById('imap-edit-port').value) || 993,
    use_ssl: _isActive('imap-edit-ssl'),
    user: document.getElementById('imap-edit-user').value.trim(),
    password_env: document.getElementById('imap-edit-password-env').value.trim(),
  };
  if (!Array.isArray(_mailData.imap)) _mailData.imap = [];
  const idx = parseInt(document.getElementById('imap-edit-idx').value);
  if (idx >= 0 && idx < _mailData.imap.length) {
    _mailData.imap[idx] = entry;
  } else {
    _mailData.imap.push(entry);
  }
  closeModal('modal-imap-edit');
  await saveMail();
}

async function deleteImapEntry(idx) {
  const entry = (_mailData.imap || [])[idx];
  if (!entry) return;
  if (!confirm(`Supprimer la configuration IMAP "${entry.name || idx}" ?`)) return;
  _mailData.imap.splice(idx, 1);
  await saveMail();
}

// ── Templates list rendering ──
function _renderTplMailList() {
  const list = document.getElementById('mail-tpl-list');
  const entries = _mailData.templates || [];
  if (entries.length === 0) {
    list.innerHTML = '<p style="color:var(--text-secondary);padding:1rem;font-size:0.85rem">Aucun template. Cliquez sur "+ Ajouter".</p>';
    return;
  }
  let html = '<table><thead><tr><th>Nom</th><th>Subject</th><th>Body</th><th>Actions</th></tr></thead><tbody>';
  entries.forEach((t, i) => {
    const bodyPreview = (t.body || '').substring(0, 60).replace(/\n/g, ' ');
    html += `<tr>
      <td><strong>${escHtml(t.name || '')}</strong></td>
      <td>${escHtml(t.subject || '')}</td>
      <td style="color:var(--text-secondary);font-size:0.8rem">${escHtml(bodyPreview)}${(t.body || '').length > 60 ? '...' : ''}</td>
      <td style="white-space:nowrap">
        <button class="btn btn-outline btn-sm" onclick="showAddTplMailModal(${i})">Modifier</button>
        <button class="btn btn-outline btn-sm" onclick="deleteTplMailEntry(${i})" style="color:var(--error)">Supprimer</button>
      </td>
    </tr>`;
  });
  html += '</tbody></table>';
  list.innerHTML = html;
}

function showAddTplMailModal(idx) {
  const isNew = idx < 0;
  document.getElementById('modal-tpl-mail-title').textContent = isNew ? 'Nouveau template' : 'Modifier le template';
  document.getElementById('tpl-mail-edit-idx').value = idx;
  const entry = isNew ? {} : (_mailData.templates || [])[idx] || {};
  document.getElementById('tpl-mail-edit-name').value = entry.name || '';
  document.getElementById('tpl-mail-edit-subject').value = entry.subject || '';
  document.getElementById('tpl-mail-edit-body').value = entry.body || '';
  document.getElementById('modal-tpl-mail-edit').style.display = 'flex';
}

async function saveTplMailEntry() {
  const name = document.getElementById('tpl-mail-edit-name').value.trim();
  if (!name) { toast('Nom requis', 'error'); return; }
  if (!/^[a-zA-Z_]+$/.test(name)) { toast('Le nom ne doit contenir que des lettres et des _', 'error'); return; }
  const entry = {
    name,
    subject: document.getElementById('tpl-mail-edit-subject').value,
    body: document.getElementById('tpl-mail-edit-body').value,
  };
  if (!Array.isArray(_mailData.templates)) _mailData.templates = [];
  const idx = parseInt(document.getElementById('tpl-mail-edit-idx').value);
  if (idx >= 0 && idx < _mailData.templates.length) {
    _mailData.templates[idx] = entry;
  } else {
    _mailData.templates.push(entry);
  }
  closeModal('modal-tpl-mail-edit');
  await saveMail();
}

async function deleteTplMailEntry(idx) {
  const entry = (_mailData.templates || [])[idx];
  if (!entry) return;
  if (!confirm(`Supprimer le template "${entry.name || idx}" ?`)) return;
  _mailData.templates.splice(idx, 1);
  _renderTplMailList();
  await saveMail();
}

function _collectMailData() {
  const _isActive = (id) => document.getElementById(id).classList.contains('active');
  const _lines = (id) => document.getElementById(id).value.split('\n').map(l => l.trim()).filter(Boolean);

  return {
    smtp: _mailData.smtp || [],
    imap: _mailData.imap || [],
    listener: {
      poll_interval: parseInt(document.getElementById('mail-listener-interval').value) || 15,
      allowed_senders: _lines('mail-listener-allowed'),
      ignore_patterns: _lines('mail-listener-ignore'),
    },
    templates: _mailData.templates || [],
    security: {
      require_tls: _isActive('mail-sec-tls'),
      verify_sender: _isActive('mail-sec-verify'),
      max_body_size: parseInt(document.getElementById('mail-sec-maxsize').value) || 50000,
    },
    presets: _mailData.presets || {},
  };
}

async function saveMail() {
  try {
    const data = _collectMailData();
    await api('/api/mail', { method: 'PUT', body: data });
    _mailData = data;
    toast('Configuration mail sauvegardee', 'success');
    try {
      await api('/api/monitoring/container/mail-bot/restart', { method: 'POST' });
      toast('Container mail-bot redemarre', 'success');
    } catch (_) { /* container may not exist */ }
  } catch (e) { toast(e.message, 'error'); }
}

// ── Workflow status check (lightweight, called after team render) ──
async function _wfCheckStatus(dir, wfApiBase, registryApiBase, prefix) {
  const btn = document.getElementById(`btn-wf-${prefix}-${dir}`);
  if (!btn) return;
  try {
    const wfData = await api(`${wfApiBase}/${encodeURIComponent(dir)}`);
    if (!wfData || !wfData.phases || Object.keys(wfData.phases).length === 0) return;

    const reg = await api(`${registryApiBase}/${encodeURIComponent(dir)}`);
    const registryAgents = new Set(Object.keys(reg.agents || reg || {}));
    if (registryAgents.size === 0) return;

    let hasError = false;
    for (const [, phase] of Object.entries(wfData.phases)) {
      const phaseAgents = new Set(Object.keys(phase.agents || {}));
      // Check agents exist in registry
      for (const agentId of phaseAgents) {
        if (!registryAgents.has(agentId)) { hasError = true; break; }
        const cfg = phase.agents[agentId];
        if (Array.isArray(cfg.can_delegate_to) && cfg.can_delegate_to.some(r => !phaseAgents.has(r) || !registryAgents.has(r))) { hasError = true; break; }
        if (cfg.delegated_by && (!phaseAgents.has(cfg.delegated_by) || !registryAgents.has(cfg.delegated_by))) { hasError = true; break; }
        if (Array.isArray(cfg.depends_on) && cfg.depends_on.some(r => !phaseAgents.has(r) || !registryAgents.has(r))) { hasError = true; break; }
      }
      if (hasError) break;
      // Check deliverables
      for (const [, del] of Object.entries(phase.deliverables || {})) {
        if (del.agent && (!registryAgents.has(del.agent) || !phaseAgents.has(del.agent))) { hasError = true; break; }
      }
      if (hasError) break;
    }

    btn.style.borderColor = hasError ? 'var(--error)' : 'var(--success, #22c55e)';
    btn.style.color = hasError ? 'var(--error)' : 'var(--success, #22c55e)';
  } catch {
    // Workflow doesn't exist or API error — leave default style
  }
}

// ── Validation ──
async function _wfValidate() {
  const errors = [];
  const warnings = [];
  const phases = _wf.data.phases || {};
  const phaseIds = Object.keys(phases);

  // 1. Load agents_registry for this team
  const registryBase = _wf.apiBase.includes('templates') ? '/api/templates/registry' : '/api/agents/registry';
  let registryAgents = new Set();
  try {
    const reg = await api(`${registryBase}/${encodeURIComponent(_wf.dir)}`);
    registryAgents = new Set(Object.keys(reg.agents || reg || {}));
  } catch {
    warnings.push('Impossible de charger agents_registry.json — validation des agents ignoree');
  }

  // 2. Validate all agent references in the workflow
  for (const [phaseId, phase] of Object.entries(phases)) {
    const phaseName = phase.name || phaseId;
    const phaseAgents = new Set(Object.keys(phase.agents || {}));

    // 2a. Agents assigned to the phase must exist in the registry
    if (registryAgents.size > 0) {
      for (const agentId of phaseAgents) {
        if (!registryAgents.has(agentId)) {
          errors.push(`Phase "${phaseName}" : l'agent "${agentId}" n'existe pas dans agents_registry.json`);
        }
      }
    }

    for (const [agentId, agentCfg] of Object.entries(phase.agents || {})) {
      // 2b. can_delegate_to — must be in registry AND assigned in this phase
      if (Array.isArray(agentCfg.can_delegate_to)) {
        for (const ref of agentCfg.can_delegate_to) {
          if (registryAgents.size > 0 && !registryAgents.has(ref)) {
            errors.push(`Phase "${phaseName}" / ${agentId} : can_delegate_to "${ref}" n'existe pas dans agents_registry.json`);
          } else if (!phaseAgents.has(ref)) {
            errors.push(`Phase "${phaseName}" / ${agentId} : can_delegate_to "${ref}" n'est pas assigne dans cette phase`);
          }
        }
      }
      // 2c. delegated_by — must be in registry AND assigned in this phase
      if (agentCfg.delegated_by) {
        if (registryAgents.size > 0 && !registryAgents.has(agentCfg.delegated_by)) {
          errors.push(`Phase "${phaseName}" / ${agentId} : delegated_by "${agentCfg.delegated_by}" n'existe pas dans agents_registry.json`);
        } else if (!phaseAgents.has(agentCfg.delegated_by)) {
          errors.push(`Phase "${phaseName}" / ${agentId} : delegated_by "${agentCfg.delegated_by}" n'est pas assigne dans cette phase`);
        }
      }
      // 2d. depends_on — must be in registry AND assigned in this phase
      if (Array.isArray(agentCfg.depends_on)) {
        for (const ref of agentCfg.depends_on) {
          if (registryAgents.size > 0 && !registryAgents.has(ref)) {
            errors.push(`Phase "${phaseName}" / ${agentId} : depends_on "${ref}" n'existe pas dans agents_registry.json`);
          } else if (!phaseAgents.has(ref)) {
            errors.push(`Phase "${phaseName}" / ${agentId} : depends_on "${ref}" n'est pas assigne dans cette phase`);
          }
        }
      }
    }

    // 2e. Deliverables — agent must be in registry AND assigned in this phase
    for (const [delId, del] of Object.entries(phase.deliverables || {})) {
      if (del.agent) {
        if (registryAgents.size > 0 && !registryAgents.has(del.agent)) {
          errors.push(`Phase "${phaseName}" / livrable "${delId}" : l'agent "${del.agent}" n'existe pas dans agents_registry.json`);
        } else if (!phaseAgents.has(del.agent)) {
          errors.push(`Phase "${phaseName}" / livrable "${delId}" : l'agent "${del.agent}" n'est pas assigne dans cette phase`);
        }
      }
    }
  }

  // 3. Validate transitions reference existing phases
  for (const t of (_wf.data.transitions || [])) {
    if (t.from && !phaseIds.includes(t.from)) {
      errors.push(`Transition : la phase source "${t.from}" n'existe pas`);
    }
    if (t.to && !phaseIds.includes(t.to)) {
      errors.push(`Transition : la phase cible "${t.to}" n'existe pas`);
    }
  }

  // 4. Check phases have at least one agent
  for (const [phaseId, phase] of Object.entries(phases)) {
    if (!phase.agents || Object.keys(phase.agents).length === 0) {
      warnings.push(`Phase "${phase.name || phaseId}" : aucun agent assigne`);
    }
  }

  // 5. Check parallel_groups referenced by agents exist in the order list
  const pgOrder = (_wf.data.parallel_groups && _wf.data.parallel_groups.order) || [];
  for (const [phaseId, phase] of Object.entries(phases)) {
    for (const [agentId, agentCfg] of Object.entries(phase.agents || {})) {
      if (agentCfg.parallel_group && !pgOrder.includes(agentCfg.parallel_group)) {
        warnings.push(`Phase "${phase.name || phaseId}" / ${agentId} : groupe parallele "${agentCfg.parallel_group}" n'est pas dans l'ordre des groupes`);
      }
    }
  }

  return { errors, warnings };
}

// ── Save ──
async function wfSave() {
  try {
    const { errors, warnings } = await _wfValidate();
    if (errors.length > 0) {
      const msg = 'Erreurs de validation :\n\n' + errors.map(e => '- ' + e).join('\n')
        + (warnings.length ? '\n\nAvertissements :\n' + warnings.map(w => '- ' + w).join('\n') : '');
      showModal(`
        <div class="modal-header">
          <h3>Workflow invalide</h3>
          <button class="btn-icon" onclick="closeModal();_wfOpenEditorUI()">&times;</button>
        </div>
        <div style="max-height:400px;overflow:auto;white-space:pre-wrap;font-size:0.85rem;padding:1rem;background:var(--bg-secondary);border-radius:0.5rem;color:var(--text-error,#f87171)">${escHtml(msg)}</div>
        <div class="modal-actions">
          <button class="btn btn-outline" onclick="closeModal();_wfOpenEditorUI()">Corriger</button>
        </div>
      `);
      return;
    }
    if (warnings.length > 0) {
      const ok = await confirmModal('Avertissements :\n\n' + warnings.map(w => '- ' + w).join('\n') + '\n\nSauvegarder quand meme ?');
      if (!ok) return;
    }
    await Promise.all([
      api(`${_wf.apiBase}/${encodeURIComponent(_wf.dir)}`, { method: 'PUT', body: _wf.data }),
      api(`${_wf.designBase}/${encodeURIComponent(_wf.dir)}`, { method: 'PUT', body: { positions: _wf.positions } })
    ]);
    toast('Workflow sauvegarde', 'success');
  } catch (e) { toast(e.message, 'error'); }
}

// ═══════════════════════════════════════════════════
// API KEYS (Securite sub-tab)
// ═══════════════════════════════════════════════════

async function loadApiKeys() {
  const container = document.getElementById('api-keys-table');
  const statusEl = document.getElementById('mcp-secret-status');
  try {
    const data = await api('/api/keys');
    const keys = data.keys || [];
    if (keys.length === 0) {
      container.innerHTML = '<p style="color:var(--text-secondary);padding:1rem">Aucune cle API. Cliquez sur "+ Nouvelle cle" pour en creer une.</p>';
    } else {
      let html = '<table><thead><tr><th>Nom</th><th>Preview</th><th>Equipes</th><th>Agents</th><th>Scopes</th><th>Creee le</th><th>Expiration</th><th>Statut</th><th>Actions</th></tr></thead><tbody>';
      for (const k of keys) {
        const teams = Array.isArray(k.teams) ? k.teams.join(', ') : k.teams;
        const agents = Array.isArray(k.agents) ? k.agents.join(', ') : k.agents;
        const scopes = Array.isArray(k.scopes) ? k.scopes.join(', ') : (k.scopes || 'call_agent');
        const created = k.created_at ? new Date(k.created_at).toLocaleDateString('fr-FR') : '-';
        const expires = k.expires_at ? new Date(k.expires_at).toLocaleDateString('fr-FR') : 'Jamais';
        const status = k.revoked
          ? '<span class="tag tag-red">Revoquee</span>'
          : '<span class="tag tag-green">Active</span>';
        const actions = k.revoked
          ? `<button class="btn btn-outline btn-sm" onclick="deleteApiKey('${k.key_hash}')" style="color:var(--error)">Supprimer</button>`
          : `<button class="btn btn-outline btn-sm" onclick="revokeApiKey('${k.key_hash}')" style="color:var(--warning)">Revoquer</button>`;
        html += `<tr><td>${escHtml(k.name)}</td><td><code>${escHtml(k.preview)}</code></td><td>${escHtml(teams)}</td><td>${escHtml(agents)}</td><td>${escHtml(scopes)}</td><td>${created}</td><td>${expires}</td><td>${status}</td><td>${actions}</td></tr>`;
      }
      html += '</tbody></table>';
      container.innerHTML = html;
    }
    // Check MCP_SECRET status
    try {
      const env = await api('/api/env');
      const vars = env.entries || [];
      const hasSecret = vars.some(v => v.key === 'MCP_SECRET' && v.value);
      statusEl.innerHTML = hasSecret
        ? '<span class="tag tag-green">Configure</span>'
        : '<span class="tag tag-red">Non defini</span> — Ajoutez <code>MCP_SECRET</code> dans l\'onglet Secrets (.env)';
    } catch { statusEl.textContent = 'Erreur verification'; }
  } catch (e) {
    container.innerHTML = `<p style="color:var(--error)">Erreur : ${escHtml(e.message)}</p>`;
  }
}

async function showAddApiKeyModal() {
  document.getElementById('apikey-name').value = '';
  document.getElementById('apikey-expires').value = '';
  // Reset scopes
  document.querySelectorAll('#apikey-scopes-list input[type=checkbox]').forEach(cb => { cb.checked = false; });

  // Ensure teamsData is loaded
  if (!Array.isArray(teamsData) || teamsData.length === 0) {
    try {
      const data = await api('/api/teams');
      teamsData = data.teams || [];
    } catch (e) { /* ignore, will show empty selects */ }
  }

  // Populate teams select from teamsData
  const teamsSel = document.getElementById('apikey-teams');
  teamsSel.innerHTML = '<option value="*" selected>* (toutes)</option>';
  (teamsData || []).forEach(t => {
    teamsSel.innerHTML += `<option value="${escHtml(t.id)}">${escHtml(t.name || t.id)}</option>`;
  });

  // Populate agents select with team prefix
  const agentsSel = document.getElementById('apikey-agents');
  agentsSel.innerHTML = '<option value="*" selected>* (tous)</option>';
  const seen = new Set();
  (teamsData || []).forEach(t => {
    const teamLabel = escHtml(t.name || t.id);
    Object.keys(t.agents || {}).forEach(a => {
      if (!seen.has(a)) {
        seen.add(a);
        agentsSel.innerHTML += `<option value="${escHtml(a)}">${teamLabel} / ${escHtml(a)}</option>`;
      }
    });
  });

  document.getElementById('modal-add-apikey').style.display = 'flex';
}

async function createApiKey() {
  const name = document.getElementById('apikey-name').value.trim();
  if (!name) { toast('Nom requis', 'error'); return; }
  const teams = Array.from(document.getElementById('apikey-teams').selectedOptions).map(o => o.value);
  const agents = Array.from(document.getElementById('apikey-agents').selectedOptions).map(o => o.value);
  const expiresDays = document.getElementById('apikey-expires').value;
  const scopes = Array.from(document.querySelectorAll('#apikey-scopes-list input[type=checkbox]:checked')).map(cb => cb.value);
  if (scopes.length === 0) { toast('Selectionnez au moins un scope', 'error'); return; }
  const body = { name, teams, agents, scopes };
  if (expiresDays) {
    const d = new Date();
    d.setDate(d.getDate() + parseInt(expiresDays));
    body.expires_at = d.toISOString();
  }

  try {
    const r = await fetch('/api/keys', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    const data = await r.json();
    if (!r.ok) throw new Error(data.detail || 'Erreur creation');

    closeModal('modal-add-apikey');

    // Show the generated token
    document.getElementById('apikey-generated-token').value = data.token;
    const teamExample = teams[0] === '*' ? 'team1' : teams[0];
    const mcpConfig = JSON.stringify({
      "mcpServers": {
        "langgraph": {
          "url": `http://<IP>:8123/mcp/${teamExample}/sse`,
          "headers": { "Authorization": `Bearer ${data.token}` }
        }
      }
    }, null, 2);
    document.getElementById('apikey-mcp-config').value = mcpConfig;
    document.getElementById('modal-show-apikey').style.display = 'flex';

    loadApiKeys();
    toast('Cle API creee', 'success');
  } catch (e) { toast(e.message, 'error'); }
}

async function revokeApiKey(hash) {
  if (!confirm('Revoquer cette cle ? Les clients utilisant cette cle seront bloques.')) return;
  try {
    await fetch(`/api/keys/${hash}/revoke`, { method: 'POST' });
    toast('Cle revoquee', 'success');
    loadApiKeys();
  } catch (e) { toast(e.message, 'error'); }
}

async function deleteApiKey(hash) {
  if (!confirm('Supprimer definitivement cette cle ?')) return;
  try {
    await fetch(`/api/keys/${hash}`, { method: 'DELETE' });
    toast('Cle supprimee', 'success');
    loadApiKeys();
  } catch (e) { toast(e.message, 'error'); }
}

function copyApiKeyToClipboard() {
  const el = document.getElementById('apikey-generated-token');
  el.select();
  navigator.clipboard.writeText(el.value).then(
    () => toast('Cle copiee dans le presse-papier', 'success'),
    () => toast('Erreur copie', 'error')
  );
}

function copyApiKeyAndClose() {
  const el = document.getElementById('apikey-generated-token');
  el.select();
  navigator.clipboard.writeText(el.value).then(
    () => { toast('Cle copiee dans le presse-papier', 'success'); closeModal('modal-show-apikey'); },
    () => toast('Erreur copie', 'error')
  );
}

// ═══════════════════════════════════════════════════
// HITL (Validations)
// ═══════════════════════════════════════════════════

let hitlAutoInterval = null;

async function loadHitl() {
  try {
    const status = document.getElementById('hitl-status-filter')?.value || 'pending';
    const [requests, stats] = await Promise.all([
      api(`/api/hitl?status=${status}&limit=50`),
      api('/api/hitl/stats'),
    ]);
    renderHitlStats(stats);
    renderHitlList(requests);
    updateHitlBadge(stats.pending);
  } catch (e) {
    document.getElementById('hitl-list').innerHTML =
      `<div class="card"><div class="card-header"><h3>Erreur</h3></div><p style="padding:1rem;color:var(--red)">${escHtml(e.message)}</p></div>`;
    document.getElementById('hitl-stats').innerHTML = '';
  }
}

function updateHitlBadge(count) {
  const badge = document.getElementById('hitl-badge');
  if (!badge) return;
  if (count > 0) {
    badge.textContent = count;
    badge.style.display = 'inline-block';
  } else {
    badge.style.display = 'none';
  }
}

function renderHitlStats(stats) {
  const el = document.getElementById('hitl-stats');
  el.innerHTML = `
    <div class="stat-card" style="flex:1;min-width:120px">
      <div class="stat-value" style="color:#fbbf24">${stats.pending}</div>
      <div class="stat-label">En attente</div>
    </div>
    <div class="stat-card" style="flex:1;min-width:120px">
      <div class="stat-value" style="color:#4ade80">${stats.answered}</div>
      <div class="stat-label">Repondus</div>
    </div>
    <div class="stat-card" style="flex:1;min-width:120px">
      <div class="stat-value" style="color:#f87171">${stats.timeout}</div>
      <div class="stat-label">Timeout</div>
    </div>
    <div class="stat-card" style="flex:1;min-width:120px">
      <div class="stat-value" style="color:var(--text-secondary)">${stats.total}</div>
      <div class="stat-label">Total</div>
    </div>`;
}

function renderHitlList(requests) {
  const el = document.getElementById('hitl-list');
  if (!requests.length) {
    el.innerHTML = '<div class="card"><p style="padding:1.5rem;text-align:center;color:var(--text-secondary)">Aucune demande de validation.</p></div>';
    return;
  }

  el.innerHTML = requests.map(r => {
    const isExpired = r.expires_at && new Date(r.expires_at) < new Date();
    const isPending = r.status === 'pending' && !isExpired;

    const statusTag = {
      pending: isExpired
        ? '<span class="tag tag-red">expire</span>'
        : '<span class="tag tag-yellow">en attente</span>',
      answered: '<span class="tag tag-green">repondu</span>',
      timeout: '<span class="tag tag-red">timeout</span>',
      cancelled: '<span class="tag tag-gray">annule</span>',
    }[r.status] || `<span class="tag tag-gray">${escHtml(r.status)}</span>`;

    const typeIcon = r.request_type === 'approval' ? '&#x1f512;' : '&#x2753;';
    const typeLabel = r.request_type === 'approval' ? 'Validation' : 'Question';

    const createdAt = r.created_at ? new Date(r.created_at).toLocaleString('fr-FR') : '';
    const expiresAt = r.expires_at ? new Date(r.expires_at).toLocaleString('fr-FR') : '';

    const channelTag = `<span class="tag tag-blue">${escHtml(r.channel)}</span>`;
    const teamTag = `<span class="tag tag-gray">${escHtml(r.team_id)}</span>`;

    let responseHtml = '';
    if (r.status === 'answered' && r.response) {
      responseHtml = `<div style="margin-top:0.75rem;padding:0.75rem;background:var(--bg-secondary);border-radius:6px;border-left:3px solid #4ade80">
        <div style="font-size:0.75rem;color:var(--text-secondary);margin-bottom:0.25rem">
          Reponse de <strong>${escHtml(r.reviewer || '?')}</strong> via ${escHtml(r.response_channel || '?')}
          ${r.answered_at ? ' — ' + new Date(r.answered_at).toLocaleString('fr-FR') : ''}
        </div>
        <div style="font-size:0.85rem">${escHtml(r.response)}</div>
      </div>`;
    }

    let actionsHtml = '';
    if (isPending) {
      if (r.request_type === 'approval') {
        actionsHtml = `<div style="display:flex;gap:0.5rem;margin-top:0.75rem">
          <button class="btn btn-sm btn-primary" onclick="respondHitl('${r.id}', 'approve')">Approuver</button>
          <button class="btn btn-sm btn-outline" onclick="showHitlReviseModal('${r.id}')">Reviser</button>
          <button class="btn btn-sm" style="color:#f87171;border:1px solid #f87171" onclick="respondHitl('${r.id}', 'reject')">Rejeter</button>
          <button class="btn btn-sm btn-outline" style="margin-left:auto" onclick="cancelHitl('${r.id}')">Annuler</button>
        </div>`;
      } else {
        actionsHtml = `<div style="display:flex;gap:0.5rem;margin-top:0.75rem;align-items:center">
          <input type="text" id="hitl-reply-${r.id}" placeholder="Votre reponse..." style="flex:1;padding:0.4rem 0.6rem;border-radius:6px;border:1px solid var(--border);background:var(--bg-secondary);color:var(--text-primary);font-size:0.85rem">
          <button class="btn btn-sm btn-primary" onclick="respondHitlText('${r.id}')">Repondre</button>
          <button class="btn btn-sm btn-outline" onclick="cancelHitl('${r.id}')">Annuler</button>
        </div>`;
      }
    }

    let contextHtml = '';
    const ctx = r.context || {};
    const ctxText = ctx.details || ctx.context || '';
    if (ctxText) {
      contextHtml = `<div style="margin-top:0.5rem;font-size:0.8rem;color:var(--text-secondary);max-height:100px;overflow-y:auto">${escHtml(ctxText.substring(0, 500))}</div>`;
    }

    return `<div class="card" style="margin-bottom:0.75rem">
      <div class="card-header">
        <div style="display:flex;align-items:center;gap:0.5rem">
          <span style="font-size:1.1rem">${typeIcon}</span>
          <strong>${typeLabel}</strong>
          <span class="tag tag-blue" style="font-size:0.75rem">${escHtml(r.agent_id)}</span>
          ${teamTag}
          ${channelTag}
        </div>
        <div style="display:flex;align-items:center;gap:0.5rem">
          ${statusTag}
        </div>
      </div>
      <div style="padding:0 1rem 1rem">
        <div style="font-size:0.9rem;line-height:1.5">${escHtml(r.prompt)}</div>
        ${contextHtml}
        <div style="margin-top:0.5rem;font-size:0.7rem;color:var(--text-secondary)">
          Cree le ${createdAt}${expiresAt ? ` — Expire le ${expiresAt}` : ''}
          ${r.thread_id ? ` — Thread: ${escHtml(r.thread_id)}` : ''}
        </div>
        ${responseHtml}
        ${actionsHtml}
      </div>
    </div>`;
  }).join('');
}

async function respondHitl(id, response) {
  try {
    await api(`/api/hitl/${id}/respond`, {
      method: 'POST',
      body: { response, reviewer: 'admin' },
    });
    toast('Reponse envoyee', 'success');
    loadHitl();
  } catch (e) {
    toast(e.message, 'error');
  }
}

async function respondHitlText(id) {
  const input = document.getElementById(`hitl-reply-${id}`);
  const text = input?.value?.trim();
  if (!text) { toast('Reponse vide', 'error'); return; }
  await respondHitl(id, text);
}

function showHitlReviseModal(id) {
  showModal(`
    <div class="modal-header"><h3>Revision</h3></div>
    <div class="modal-body">
      <label>Commentaire de revision :</label>
      <textarea id="hitl-revise-text" rows="4" style="width:100%;margin-top:0.5rem;padding:0.5rem;border-radius:6px;border:1px solid var(--border);background:var(--bg-secondary);color:var(--text-primary);font-family:inherit;resize:vertical" placeholder="Decrivez les modifications demandees..."></textarea>
    </div>
    <div class="modal-footer">
      <button class="btn btn-outline" onclick="closeModal()">Annuler</button>
      <button class="btn btn-primary" onclick="submitHitlRevise('${id}')">Envoyer</button>
    </div>
  `);
}

async function submitHitlRevise(id) {
  const text = document.getElementById('hitl-revise-text')?.value?.trim();
  if (!text) { toast('Commentaire vide', 'error'); return; }
  closeModal();
  await respondHitl(id, `revise ${text}`);
}

async function cancelHitl(id) {
  try {
    await api(`/api/hitl/${id}/cancel`, { method: 'POST' });
    toast('Demande annulee', 'success');
    loadHitl();
  } catch (e) {
    toast(e.message, 'error');
  }
}

function toggleHitlAutoRefresh() {
  const btn = document.getElementById('hitl-auto-btn');
  if (hitlAutoInterval) {
    clearInterval(hitlAutoInterval);
    hitlAutoInterval = null;
    btn.textContent = 'Auto OFF';
  } else {
    hitlAutoInterval = setInterval(loadHitl, 10000);
    btn.textContent = 'Auto ON';
  }
}

// ═══════════════════════════════════════════════════
// AUTH CONFIG (hitl.json)
// ═══════════════════════════════════════════════════

async function loadAuthConfig() {
  try {
    const data = await api('/api/hitl-config');
    const auth = data.auth || {};
    const google = data.google_oauth || {};
    // Google fields
    const enabled = google.enabled || false;
    document.getElementById('auth-google-enabled').checked = enabled;
    document.getElementById('auth-google-client-id').value = google.client_id || '';
    document.getElementById('auth-google-secret-env').value = google.client_secret_env || 'GOOGLE_CLIENT_SECRET';
    document.getElementById('auth-google-domains').value = (google.allowed_domains || []).join(', ');
    document.getElementById('auth-google-fields').style.display = enabled ? 'block' : 'none';
    // Status badge
    const badge = document.getElementById('auth-google-status');
    if (enabled && google.client_id) {
      badge.textContent = 'Active'; badge.className = 'tag tag-green';
    } else {
      badge.textContent = 'Desactive'; badge.className = 'tag tag-red';
    }
    // General fields
    document.getElementById('auth-jwt-expire').value = auth.jwt_expire_hours || 24;
    document.getElementById('auth-default-role').value = auth.default_role || 'undefined';
    document.getElementById('auth-allow-registration').checked = auth.allow_registration !== false;
  } catch (e) { toast(e.message, 'error'); }
}

function toggleAuthGoogle() {
  const enabled = document.getElementById('auth-google-enabled').checked;
  document.getElementById('auth-google-fields').style.display = enabled ? 'block' : 'none';
}

async function saveAuthConfig() {
  const domainsRaw = document.getElementById('auth-google-domains').value.trim();
  const domains = domainsRaw ? domainsRaw.split(',').map(d => d.trim()).filter(Boolean) : [];
  const config = {
    auth: {
      jwt_expire_hours: parseInt(document.getElementById('auth-jwt-expire').value) || 24,
      allow_registration: document.getElementById('auth-allow-registration').checked,
      default_role: document.getElementById('auth-default-role').value
    },
    google_oauth: {
      enabled: document.getElementById('auth-google-enabled').checked,
      client_id: document.getElementById('auth-google-client-id').value.trim(),
      client_secret_env: document.getElementById('auth-google-secret-env').value.trim() || 'GOOGLE_CLIENT_SECRET',
      allowed_domains: domains
    }
  };
  try {
    await api('/api/hitl-config', { method: 'PUT', body: config });
    toast('Configuration enregistree.', 'success');
    loadAuthConfig();
  } catch (e) { toast(e.message, 'error'); }
}

// ═══════════════════════════════════════════════════
// HITL USERS
// ═══════════════════════════════════════════════════
let usersData = [];
let editingUserId = null;

async function loadUsers() {
  try {
    usersData = await api('/api/hitl/users');
    renderUsers();
  } catch (e) { toast(e.message, 'error'); }
}

function renderUsers() {
  const filter = (document.getElementById('users-filter')?.value || '').toLowerCase();
  const filtered = filter ? usersData.filter(u => u.email.toLowerCase().includes(filter)) : usersData;
  const container = document.getElementById('users-table');
  if (filtered.length === 0) {
    container.innerHTML = '<p style="color:var(--text-secondary);padding:1rem">Aucun utilisateur.</p>';
    return;
  }
  let html = `<table><thead><tr>
    <th>Email</th><th>Nom</th><th>Auth</th><th>Role</th><th>Equipes</th><th>Actif</th><th>Derniere connexion</th><th>Actions</th>
  </tr></thead><tbody>`;
  filtered.forEach(u => {
    const teamNames = (u.teams || []).map(t => `<span style="display:inline-block;font-size:0.7rem;padding:1px 5px;margin:1px;background:var(--bg-secondary);border:1px solid var(--border);border-radius:3px">${escHtml(t.team_id)}</span>`).join('');
    const authType = u.auth_type || 'local';
    const roleClass = u.role === 'admin' ? 'tag-yellow' : u.role === 'undefined' ? 'tag-red' : 'tag-blue';
    html += `<tr>
      <td>${escHtml(u.email)}</td>
      <td>${escHtml(u.display_name)}</td>
      <td><span class="tag" style="font-size:0.65rem">${escHtml(authType)}</span></td>
      <td><span class="tag ${roleClass}">${escHtml(u.role)}</span></td>
      <td>${teamNames || '<span style="color:var(--text-secondary)">—</span>'}</td>
      <td>${u.is_active ? '<span style="color:#4ade80">Oui</span>' : '<span style="color:#f87171">Non</span>'}</td>
      <td style="font-size:0.75rem;color:var(--text-secondary)">${u.last_login ? new Date(u.last_login).toLocaleString('fr') : '—'}</td>
      <td style="position:relative">
        <button class="btn btn-outline btn-sm" onclick="toggleUserMenu('${u.id}')">Actions ▾</button>
        <div id="user-menu-${u.id}" class="dropdown-menu" style="display:none;position:absolute;right:0;top:100%;z-index:50;min-width:220px;background:var(--bg-secondary);border:1px solid var(--border);border-radius:6px;box-shadow:0 4px 12px rgba(0,0,0,0.3);padding:4px 0">
          <div class="dropdown-item" onclick="editUser('${u.id}');closeUserMenus()" style="padding:6px 12px;cursor:pointer;font-size:0.8rem">Editer</div>
          <div class="dropdown-item" onclick="resendResetEmail('${u.id}','${escHtml(u.email)}');closeUserMenus()" style="padding:6px 12px;cursor:pointer;font-size:0.8rem">Renvoyer le mail de reset</div>
          <div style="border-top:1px solid var(--border);margin:4px 0"></div>
          <div class="dropdown-item" onclick="deleteUser('${u.id}','${escHtml(u.email)}');closeUserMenus()" style="padding:6px 12px;cursor:pointer;font-size:0.8rem;color:var(--red)">Supprimer</div>
        </div>
      </td>
    </tr>`;
  });
  html += '</tbody></table>';
  container.innerHTML = html;
}

async function showAddUserModal() {
  editingUserId = null;
  document.getElementById('modal-user-title').textContent = 'Nouvel utilisateur';
  document.getElementById('user-save-btn').textContent = 'Creer';
  document.getElementById('user-email').value = '';
  document.getElementById('user-email').disabled = false;
  document.getElementById('user-name').value = '';
  document.getElementById('user-role').value = 'member';
  document.getElementById('user-edit-fields').style.display = 'none';
  document.getElementById('user-create-hint').style.display = 'block';
  await populateTeamCheckboxes([]);
  document.getElementById('modal-user').style.display = 'flex';
}

async function editUser(uid) {
  const u = usersData.find(x => x.id === uid);
  if (!u) return;
  editingUserId = uid;
  document.getElementById('modal-user-title').textContent = 'Editer ' + u.email;
  document.getElementById('user-save-btn').textContent = 'Enregistrer';
  document.getElementById('user-email').value = u.email;
  document.getElementById('user-email').disabled = true;
  document.getElementById('user-name').value = u.display_name || '';
  document.getElementById('user-role').value = u.role;
  document.getElementById('user-edit-fields').style.display = 'block';
  document.getElementById('user-create-hint').style.display = 'none';
  const userTeamIds = (u.teams || []).map(t => t.team_id);
  await populateTeamCheckboxes(userTeamIds);
  document.getElementById('modal-user').style.display = 'flex';
}

let _allTeamsList = [];
async function _loadAllTeams() {
  try { const data = await api('/api/teams'); _allTeamsList = data.teams || []; } catch { _allTeamsList = []; }
}
function _teamSelectOptions(selectedId) {
  return `<option value="">-- Selectionner --</option>` +
    _allTeamsList.map(t =>
      `<option value="${escHtml(t.id)}" ${t.id === selectedId ? 'selected' : ''}>${escHtml(t.name || t.id)}</option>`
    ).join('');
}
function _renderTeamRows(container, teamIds) {
  container.innerHTML = '';
  if (!teamIds.length) teamIds = [''];
  teamIds.forEach((tid, i) => {
    const isLast = i === teamIds.length - 1;
    const row = document.createElement('div');
    row.style.cssText = 'display:flex;gap:6px;align-items:center;margin-bottom:4px';
    row.innerHTML = `<select class="user-team-select" style="flex:1">${_teamSelectOptions(tid)}</select>` +
      (isLast
        ? `<button type="button" class="btn-icon" onclick="_addTeamRow(this)" title="Ajouter">+</button>`
        : `<button type="button" class="btn-icon" onclick="this.parentElement.remove()" title="Supprimer" style="color:var(--text-secondary)">&#x1F5D1;</button>`);
    container.appendChild(row);
  });
}
function _addTeamRow(btn) {
  const container = btn.closest('#user-teams-checkboxes');
  const rows = container.querySelectorAll('div');
  const lastRow = rows[rows.length - 1];
  const lastBtn = lastRow.querySelector('button');
  lastBtn.outerHTML = `<button type="button" class="btn-icon" onclick="this.parentElement.remove()" title="Supprimer" style="color:var(--text-secondary)">&#x1F5D1;</button>`;
  const row = document.createElement('div');
  row.style.cssText = 'display:flex;gap:6px;align-items:center;margin-bottom:4px';
  row.innerHTML = `<select class="user-team-select" style="flex:1">${_teamSelectOptions('')}</select>` +
    `<button type="button" class="btn-icon" onclick="_addTeamRow(this)" title="Ajouter">+</button>`;
  container.appendChild(row);
}
function _collectUserTeams() {
  return Array.from(document.querySelectorAll('.user-team-select'))
    .map(s => s.value).filter(Boolean);
}

async function populateTeamCheckboxes(selectedIds) {
  await _loadAllTeams();
  const container = document.getElementById('user-teams-checkboxes');
  if (_allTeamsList.length === 0) {
    container.innerHTML = '<span style="color:var(--text-secondary);font-size:0.8rem">Aucune equipe configuree</span>';
    return;
  }
  _renderTeamRows(container, selectedIds.length ? selectedIds : ['']);
}

async function saveUser() {
  const email = document.getElementById('user-email').value.trim();
  const display_name = document.getElementById('user-name').value.trim();
  const role = document.getElementById('user-role').value;
  const teams = _collectUserTeams();

  if (!editingUserId && !email) { toast('Email requis', 'error'); return; }

  try {
    if (editingUserId) {
      const body = { display_name, role, is_active: true, teams };
      await api(`/api/hitl/users/${editingUserId}`, { method: 'PUT', body });
      toast('Utilisateur mis a jour', 'success');
    } else {
      const res = await api('/api/hitl/users', { method: 'POST', body: { email, role, teams } });
      toast(res.email_sent ? 'Utilisateur cree — email envoye' : 'Utilisateur cree — echec envoi email', res.email_sent ? 'success' : 'error');
    }
    closeModal('modal-user');
    loadUsers();
  } catch (e) { toast(e.message, 'error'); }
}

function toggleUserMenu(uid) {
  closeUserMenus();
  const menu = document.getElementById('user-menu-' + uid);
  if (menu) menu.style.display = menu.style.display === 'none' ? 'block' : 'none';
}

function closeUserMenus() {
  document.querySelectorAll('[id^="user-menu-"]').forEach(m => m.style.display = 'none');
}

// Close menus on click outside
document.addEventListener('click', (e) => {
  if (!e.target.closest('[id^="user-menu-"]') && !e.target.matches('[onclick*="toggleUserMenu"]')) {
    closeUserMenus();
  }
});

async function resendResetEmail(uid, email) {
  if (!confirm(`Renvoyer le mail de reinitialisation a ${email} ?`)) return;
  try {
    const res = await api(`/api/hitl/users/${uid}/resend-reset`, { method: 'POST' });
    toast(res.email_sent ? 'Email de reset envoye' : 'Echec envoi email', res.email_sent ? 'success' : 'error');
  } catch (e) { toast(e.message, 'error'); }
}

async function deleteUser(uid, email) {
  if (!confirm(`Supprimer l'utilisateur ${email} ? Cette action est irreversible.`)) return;
  try {
    await api(`/api/hitl/users/${uid}`, { method: 'DELETE' });
    toast('Utilisateur supprime', 'success');
    loadUsers();
  } catch (e) { toast(e.message, 'error'); }
}

// ═══════════════════════════════════════════════════
// INIT
// ═══════════════════════════════════════════════════
document.addEventListener('DOMContentLoaded', () => {
  loadDashboard();
  // Check HITL badge on startup
  api('/api/hitl/stats').then(s => updateHitlBadge(s.pending)).catch(() => {});
  // Load version tag
  fetch('/api/version').then(r => r.json()).then(d => {
    let txt = d.version || '';
    if (d.last_update) {
      try {
        const dt = new Date(d.last_update);
        txt += ' \u2014 ' + dt.toLocaleDateString('fr-FR') + ' ' + dt.toLocaleTimeString('fr-FR', {hour:'2-digit', minute:'2-digit'});
      } catch(e) {}
    }
    const sv = document.getElementById('sidebar-version');
    if (sv && d.version) sv.textContent = '(' + d.version + ')';
  }).catch(() => {});
});

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
  const loaders = { secrets: loadEnv, mcp: loadMCP, agents: loadAgents, llm: loadLLM, teams: loadTeams, templates: loadTemplates, chat: loadChat, scripts: loadScripts, git: loadGit };
  if (loaders[name]) loaders[name]();
}

// ── Modal helpers ──────────────────────────────────
function showModal(html, cssClass = '') {
  document.getElementById('modal-container').innerHTML = `
    <div class="modal-overlay" onclick="if(event.target===this)closeModal()">
      <div class="modal ${cssClass}">${html}</div>
    </div>`;
}

function closeModal() {
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
        <button class="btn-icon" onclick="editEnvEntry(${i})" title="Modifier">
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

function editEnvEntry(idx) {
  const entry = envEntries.filter(e => e.key)[idx];
  showModal(`
    <div class="modal-header">
      <h3>Modifier: ${escHtml(entry.key)}</h3>
      <button class="btn-icon" onclick="closeModal()">&times;</button>
    </div>
    <div class="form-group">
      <label>Valeur</label>
      <input id="edit-env-value" value="${escHtml(entry.value)}" />
    </div>
    <div class="modal-actions">
      <button class="btn btn-outline" onclick="closeModal()">Annuler</button>
      <button class="btn btn-primary" onclick="saveEnvEntry('${escHtml(entry.key)}')">Sauvegarder</button>
    </div>
  `);
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
  const installed = mcpCatalog.filter(c => c.installed);
  const catalog = mcpCatalog.filter(c => mcpShowDeprecated || !c.deprecated);

  // ── Top: Installed servers ──
  const configuredEl = document.getElementById('mcp-configured');
  if (installed.length === 0) {
    configuredEl.innerHTML = '<p style="color:var(--text-secondary);text-align:center;padding:1rem">Aucun serveur MCP installe. Choisissez-en dans le catalogue ci-dessous.</p>';
  } else {
    configuredEl.innerHTML = `<table>
      <thead><tr><th>Service</th><th>Commande</th><th>Env</th><th>Agents</th><th>Actif</th><th>Actions</th></tr></thead>
      <tbody>${installed.map(c => {
        const envStatus = c.env_vars.length === 0
          ? '<span class="tag tag-gray">aucune</span>'
          : c.env_vars.map(v =>
              `<span class="tag ${v.configured ? 'tag-green' : 'tag-red'}" title="${escHtml(v.desc)}">${escHtml(v.var)}</span>`
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
  catalogEl.innerHTML = catalog.map(c => {
    let statusBtn;
    if (c.installed && c.enabled) {
      statusBtn = '<span class="tag tag-green" style="padding:0.4rem 0.75rem;font-size:0.8rem">Active</span>';
    } else if (c.installed && !c.enabled) {
      statusBtn = '<span class="tag tag-yellow" style="padding:0.4rem 0.75rem;font-size:0.8rem">Desactive</span>';
    } else {
      statusBtn = `<button class="btn btn-sm btn-primary" onclick="event.stopPropagation();showAddCatalogModal('${escHtml(c.id)}')">Installer</button>`;
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
        `<span class="tag ${v.configured ? 'tag-green' : 'tag-yellow'}" style="margin:0.1rem" title="${escHtml(v.desc)}">${escHtml(v.var)}</span>`
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
            <code>${escHtml(v.var)}</code>
            <span class="env-var-desc">${escHtml(v.desc)}</span>
            ${v.configured
              ? '<span class="tag tag-green">configure</span>'
              : '<span class="tag tag-red">manquant</span>'}
          </div>
          <div class="env-var-action">
            <input class="mcp-env-field" data-var="${escHtml(v.var)}" placeholder="Nouvelle valeur..." />
            <button class="btn btn-sm btn-outline" onclick="setEnvVarFromInstall('${escHtml(v.var)}', this)" title="Enregistrer dans .env">
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
    const agentCards = Object.entries(g.agents).map(([id, a]) => {
      const mcpList = (mcpAccess[id] || []);
      return `<div class="agent-card" onclick="editAgent('${escHtml(id)}')">
        <div class="agent-card-header">
          <div>
            <h4>${escHtml(a.name)}</h4>
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

function editTeam(teamId) {
  const g = agentGroups.find(t => t.team_id === teamId);
  if (!g) return;
  showModal(`
    <div class="modal-header">
      <h3>Equipe: ${escHtml(g.team_name)}</h3>
      <button class="btn-icon" onclick="closeModal()">&times;</button>
    </div>
    <div class="form-group">
      <label>Nom</label>
      <input id="team-edit-name" value="${escHtml(g.team_name)}" />
    </div>
    <div class="form-group">
      <label>Description</label>
      <input id="team-edit-desc" value="${escHtml(g.team_description || '')}" />
    </div>
    <div class="form-group">
      <label>Channels Discord <span style="font-size:0.75rem;color:var(--text-secondary)">(IDs separes par des virgules)</span></label>
      <input id="team-edit-channels" value="${escHtml((g.discord_channels || []).join(', '))}" />
    </div>
    <div class="modal-actions">
      <button class="btn btn-outline" onclick="closeModal()">Annuler</button>
      <button class="btn btn-primary" onclick="saveTeam('${escHtml(teamId)}')">Sauvegarder</button>
    </div>
  `);
}

async function saveTeam(teamId) {
  const name = document.getElementById('team-edit-name').value.trim();
  const description = document.getElementById('team-edit-desc').value.trim();
  const channelsRaw = document.getElementById('team-edit-channels').value.trim();
  const discord_channels = channelsRaw ? channelsRaw.split(',').map(s => s.trim()).filter(Boolean) : [];
  if (!name) { toast('Le nom est requis', 'error'); return; }
  try {
    const g = agentGroups.find(t => t.team_id === teamId);
    await api(`/api/teams/${encodeURIComponent(teamId)}`, {
      method: 'PUT',
      body: { name, description, directory: g?.team_dir || teamId, discord_channels }
    });
    toast('Equipe sauvegardee', 'success');
    closeModal();
    loadAgents();
  } catch (e) { toast(e.message, 'error'); }
}

function editAgent(id) {
  const a = agents[id];
  const providerNames = Object.keys(llmProviders.providers || {});
  const mcpList = mcpAccess[id] || [];
  const availableMCP = mcpCatalog.filter(c => !c.deprecated);

  const mcpChips = availableMCP.length > 0
    ? availableMCP.map(c => {
        const checked = mcpList.includes(c.id);
        const installedClass = c.installed ? '' : ' not-installed';
        return `<label class="mcp-chip${checked ? ' active' : ''}${installedClass}" title="${escHtml(c.description || '')}">
          <input type="checkbox" class="agent-mcp-cb" value="${escHtml(c.id)}" ${checked ? 'checked' : ''} onchange="this.parentElement.classList.toggle('active',this.checked)" />
          ${escHtml(c.label)}
        </label>`;
      }).join('')
    : '<p style="color:var(--text-secondary);font-size:0.8rem">Aucun serveur MCP dans le catalogue.</p>';

  const promptRaw = a.prompt_content || '';
  const promptHtml = typeof marked !== 'undefined' ? marked.parse(promptRaw) : escHtml(promptRaw);

  showModal(`
    <div class="modal-header">
      <h3>Agent: ${escHtml(a.name)} (${escHtml(id)})</h3>
      <button class="btn-icon" onclick="closeModal()">&times;</button>
    </div>
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
      <label>Prompt (${escHtml(a.prompt)})</label>
      <div class="prompt-tabs">
        <div class="prompt-tab active" id="prompt-tab-preview" onclick="switchPromptTab('preview')">Apercu</div>
        <div class="prompt-tab" id="prompt-tab-edit" onclick="switchPromptTab('edit')">Editer</div>
      </div>
      <div class="prompt-preview" id="agent-prompt-preview">${promptHtml}</div>
      <textarea id="agent-edit-prompt" style="min-height:300px;display:none;border-radius:0 0.5rem 0.5rem 0.5rem">${escHtml(promptRaw)}</textarea>
    </div>
    <div class="form-group">
      <label>Services MCP autorises</label>
      <div class="mcp-chips">
        ${mcpChips}
      </div>
    </div>
    <div class="modal-actions">
      <button class="btn btn-outline" onclick="closeModal()">Annuler</button>
      <button class="btn btn-primary" onclick="saveAgent('${escHtml(id)}')">Sauvegarder</button>
    </div>
  `, 'modal-wide');
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

async function saveAgent(id) {
  const name = document.getElementById('agent-edit-name').value.trim();
  const model = document.getElementById('agent-edit-model').value;
  const temperature = parseFloat(document.getElementById('agent-edit-temp').value);
  const max_tokens = parseInt(document.getElementById('agent-edit-tokens').value);
  const prompt_content = document.getElementById('agent-edit-prompt').value;
  const mcpCheckboxes = document.querySelectorAll('.agent-mcp-cb:checked');
  const mcpList = Array.from(mcpCheckboxes).map(cb => cb.value);

  const teamDir = agents[id]._team_dir || agents[id]._team_id || 'default';
  try {
    await Promise.all([
      api(`/api/agents/${id}`, {
        method: 'PUT',
        body: { id, name, model, temperature, max_tokens, prompt_content, prompt_file: '', type: agents[id].type || '', pipeline_steps: agents[id].pipeline_steps || [], team_id: agents[id]._team_id || 'default' }
      }),
      api(`/api/agents/mcp-access/${encodeURIComponent(teamDir)}/${encodeURIComponent(id)}`, { method: 'PUT', body: { servers: mcpList } }),
    ]);
    toast('Agent sauvegarde', 'success');
    closeModal();
    loadAgents();
  } catch (e) { toast(e.message, 'error'); }
}

function showAddAgentModal() {
  const providerNames = Object.keys(llmProviders.providers || {});
  const teamOpts = agentGroups.map(g => `<option value="${escHtml(g.team_id)}">${escHtml(g.team_name)}</option>`).join('');
  const mcpInstalled = mcpCatalog.filter(c => c.installed);
  const mcpTags = mcpInstalled.length
    ? mcpInstalled.map(c => `<label class="mcp-check-tag"><input type="checkbox" value="${escHtml(c.id)}" onchange="this.parentElement.classList.toggle('active',this.checked)" />${escHtml(c.label)}</label>`).join('')
    : '<span style="color:var(--text-secondary);font-size:0.8rem">Aucun serveur MCP installe</span>';
  showModal(`
    <div class="modal-header">
      <h3>Nouvel agent</h3>
      <button class="btn-icon" onclick="closeModal()">&times;</button>
    </div>
    <div class="form-row">
      <div class="form-group">
        <label>ID (identifiant unique)</label>
        <input id="agent-new-id" placeholder="mon_agent" />
      </div>
      <div class="form-group">
        <label>Nom affiche</label>
        <input id="agent-new-name" placeholder="Mon Agent" />
      </div>
    </div>
    <div class="form-row">
      <div class="form-group">
        <label>Equipe</label>
        <select id="agent-new-team">${teamOpts}</select>
      </div>
      <div class="form-group">
        <label>Modele LLM</label>
        <select id="agent-new-model">
          <option value="">-- Defaut --</option>
          ${providerNames.map(p => `<option value="${p}">${escHtml(p)}</option>`).join('')}
        </select>
      </div>
    </div>
    <div class="form-group">
      <label>Temperature</label>
      <input id="agent-new-temp" type="number" step="0.1" min="0" max="2" value="0.2" />
    </div>
    <div class="form-group">
      <label>Services MCP</label>
      <div class="mcp-check-tags">${mcpTags}</div>
    </div>
    <div class="form-group">
      <label>Prompt initial</label>
      <textarea id="agent-new-prompt" style="min-height:150px" placeholder="# Mon Agent\n\nDescription du role..."></textarea>
    </div>
    <div class="modal-actions">
      <button class="btn btn-outline" onclick="closeModal()">Annuler</button>
      <button class="btn btn-primary" onclick="addAgent()">Creer</button>
    </div>
  `);
}

async function addAgent() {
  const id = document.getElementById('agent-new-id').value.trim();
  const name = document.getElementById('agent-new-name').value.trim();
  const model = document.getElementById('agent-new-model').value;
  const temperature = parseFloat(document.getElementById('agent-new-temp').value);
  const prompt_content = document.getElementById('agent-new-prompt').value;
  const team_id = document.getElementById('agent-new-team')?.value || 'default';
  if (!id || !name) { toast('ID et nom requis', 'error'); return; }
  const mcpChecked = [...document.querySelectorAll('#modal-container .mcp-check-tag input:checked')].map(cb => cb.value);
  const teamDir = agentGroups.find(g => g.team_id === team_id)?.team_dir || team_id;
  try {
    await api('/api/agents', {
      method: 'POST',
      body: { id, name, model, temperature, max_tokens: 32768, prompt_content, prompt_file: '', type: '', pipeline_steps: [], team_id }
    });
    if (mcpChecked.length) {
      await api(`/api/agents/mcp-access/${encodeURIComponent(teamDir)}/${encodeURIComponent(id)}`, { method: 'PUT', body: { servers: mcpChecked } });
    }
    toast('Agent cree', 'success');
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
    const provider = defaultId ? data.providers[defaultId] : null;
    const label = document.getElementById('chat-provider-label');
    if (provider) {
      label.innerHTML = `<span class="tag tag-blue">${escHtml(provider.type)}</span> <strong>${escHtml(defaultId)}</strong> — ${escHtml(provider.model)}`;
    } else {
      label.textContent = 'Aucun provider par defaut';
    }
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
    const result = await api('/api/chat', { method: 'POST', body: { messages: apiMessages } });
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
// GIT (dual repo: configs + shared)
// ═══════════════════════════════════════════════════
async function loadGit() {
  try {
    const [cfgStatus, sharedStatus, cfg] = await Promise.all([
      api('/api/git/configs/status'),
      api('/api/git/shared/status'),
      api('/api/git/config'),
    ]);
    const repos = cfg.repos || {};

    // Configs repo
    _fillGitRepoUI('configs', cfgStatus, repos.configs || {});
    // Shared repo
    _fillGitRepoUI('shared', sharedStatus, repos.shared || {});
  } catch (e) { toast(e.message, 'error'); }
}

function _fillGitRepoUI(key, status, cfg) {
  const inited = status.initialized;
  document.getElementById(`git-${key}-branch`).textContent = inited ? (status.branch || 'inconnu') : 'Non initialise';
  document.getElementById(`git-${key}-status`).textContent = inited ? (status.status || '(aucun changement)') : 'Git non initialise. Enregistrez la configuration puis cliquez Init.';
  document.getElementById(`git-${key}-log`).textContent = inited ? (status.log || '(vide)') : '';
  document.getElementById(`btn-git-${key}-init`).disabled = inited;
  document.getElementById(`btn-git-${key}-pull`).disabled = !inited;
  document.getElementById(`btn-git-${key}-commit`).disabled = !inited;
  document.getElementById(`git-cfg-${key}-path`).value = cfg.path || '';
  document.getElementById(`git-cfg-${key}-login`).value = cfg.login || '';
  document.getElementById(`git-cfg-${key}-password`).value = cfg.password || '';
}

async function saveGitConfig() {
  const body = {
    repos: {
      configs: {
        path: document.getElementById('git-cfg-configs-path').value.trim(),
        login: document.getElementById('git-cfg-configs-login').value.trim(),
        password: document.getElementById('git-cfg-configs-password').value.trim(),
      },
      shared: {
        path: document.getElementById('git-cfg-shared-path').value.trim(),
        login: document.getElementById('git-cfg-shared-login').value.trim(),
        password: document.getElementById('git-cfg-shared-password').value.trim(),
      },
    },
  };
  try {
    await api('/api/git/config', { method: 'PUT', body });
    toast('Configuration Git enregistree', 'success');
    loadGit();
  } catch (e) { toast(e.message, 'error'); }
}

async function gitInit(repoKey) {
  try {
    const data = await api(`/api/git/${repoKey}/init`, { method: 'POST' });
    toast(data.ok ? `Repository ${repoKey} initialise` : (data.message || 'Erreur'), data.ok ? 'success' : 'error');
    loadGit();
  } catch (e) { toast(e.message, 'error'); }
}

async function gitPull(repoKey) {
  try {
    const data = await api(`/api/git/${repoKey}/pull`, { method: 'POST' });
    if (data.code === 0) {
      toast(`Pull ${repoKey} reussi`, 'success');
    } else {
      const detail = (data.stderr || data.stdout || 'erreur inconnue').substring(0, 200);
      toast(`Pull ${repoKey} erreur: ${detail}`, 'error');
    }
    loadGit();
  } catch (e) { toast(e.message, 'error'); }
}

let _gitCommitRepoKey = '';
function showGitCommitModal(repoKey) {
  _gitCommitRepoKey = repoKey;
  const label = repoKey === 'configs' ? 'Configs' : 'Shared (Templates)';
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
  try {
    const data = await api(`/api/git/${_gitCommitRepoKey}/commit`, { method: 'POST', body: { message: msg } });
    toast(data.code === 0 ? 'Commit & push effectue' : (data.stderr || 'Erreur commit/push'), data.code === 0 ? 'success' : 'error');
    closeModal();
    loadGit();
  } catch (e) { toast(e.message, 'error'); }
}

// ═══════════════════════════════════════════════════
// TEAMS
// ═══════════════════════════════════════════════════
let teamsData = {};
let templatesData = [];

async function loadTeams() {
  try {
    const data = await api('/api/teams');
    teamsData = data.teams || [];
    renderTeams();
  } catch (e) { toast(e.message, 'error'); }
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
  grid.innerHTML = teamsData.map((t) => {
    const agentEntries = Object.entries(t.agents || {});
    const mcpAccess = t.mcp_access || {};
    const dir = t.directory || t.id;

    const agentCards = agentEntries.map(([aid, a]) => {
      const mcpList = mcpAccess[aid] || [];
      return `<div class="agent-card" style="cursor:pointer">
        <div class="agent-card-header">
          <div onclick="editCfgAgent('${escHtml(dir)}','${escHtml(aid)}')" style="flex:1;cursor:pointer">
            <h4>${escHtml(a.name)}</h4>
            <code style="font-size:0.75rem;color:var(--text-secondary)">${escHtml(aid)}</code>
          </div>
          <button class="btn-icon danger" onclick="event.stopPropagation();deleteCfgAgent('${escHtml(dir)}','${escHtml(aid)}')" title="Supprimer">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>
          </button>
        </div>
        <div class="agent-meta" onclick="editCfgAgent('${escHtml(dir)}','${escHtml(aid)}')">
          <span class="tag tag-blue">temp: ${a.temperature}</span>
          <span class="tag tag-blue">tokens: ${a.max_tokens}</span>
          ${a.llm || a.model ? `<span class="tag tag-yellow">${escHtml(a.llm || a.model)}</span>` : ''}
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
            ${escHtml(t.name || t.id)}
            <span style="font-weight:400;font-size:0.75rem;color:var(--text-secondary)">${escHtml(t.id)}</span>
            <code style="font-weight:400;font-size:0.7rem;color:var(--text-secondary)">Configs/Teams/${escHtml(dir)}/</code>
          </h3>
          <span class="tag tag-blue" style="margin-left:0.5rem">${agentEntries.length} agent${agentEntries.length > 1 ? 's' : ''}</span>
        </div>
        <div style="display:flex;gap:0.5rem">
          <button class="btn btn-primary btn-sm" onclick="showAddCfgAgentModal('${escHtml(dir)}')">+ Agent</button>
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
          ${agentCards || '<p style="color:var(--text-secondary);padding:0.5rem">Aucun agent dans cette equipe.</p>'}
        </div>
      </div>
    </div>`;
  }).join('');
}

async function showAddCfgAgentModal(dir) {
  let llmNames = [], mcpServerIds = [];
  try {
    const [llmData, mcpData] = await Promise.all([api('/api/templates/llm'), api('/api/mcp/servers')]);
    llmNames = Object.keys(llmData.providers || {});
    mcpServerIds = Object.keys(mcpData.servers || {});
  } catch { /* ignore */ }
  const llmOptions = `<option value="">-- Defaut --</option>` +
    llmNames.map(p => `<option value="${escHtml(p)}">${escHtml(p)}</option>`).join('');
  const mcpTags = mcpServerIds.length
    ? mcpServerIds.map(sid => `<label class="mcp-check-tag"><input type="checkbox" value="${escHtml(sid)}" onchange="this.parentElement.classList.toggle('active',this.checked)" />${escHtml(sid)}</label>`).join('')
    : '<span style="color:var(--text-secondary);font-size:0.8rem">Aucun serveur MCP installe</span>';
  showModal(`
    <div class="modal-header">
      <h3>Nouvel agent</h3>
      <button class="btn-icon" onclick="closeModal()">&times;</button>
    </div>
    <div class="form-row">
      <div class="form-group">
        <label>ID (identifiant unique)</label>
        <input id="cfg-agent-new-id" placeholder="mon_agent" />
      </div>
      <div class="form-group">
        <label>Nom affiche</label>
        <input id="cfg-agent-new-name" placeholder="Mon Agent" />
      </div>
    </div>
    <div class="form-row">
      <div class="form-group">
        <label>Modele LLM</label>
        <select id="cfg-agent-new-llm">${llmOptions}</select>
      </div>
    </div>
    <div class="form-row">
      <div class="form-group">
        <label>Temperature</label>
        <input id="cfg-agent-new-temp" type="number" step="0.1" min="0" max="2" value="0.3" />
      </div>
      <div class="form-group">
        <label>Max tokens</label>
        <input id="cfg-agent-new-tokens" type="number" value="32768" />
      </div>
    </div>
    <div class="form-group">
      <label>Services MCP</label>
      <div class="mcp-check-tags">${mcpTags}</div>
    </div>
    <div class="form-group">
      <label>Prompt initial</label>
      <textarea id="cfg-agent-new-prompt" style="min-height:120px" placeholder="# Mon Agent\n\nDescription du role..."></textarea>
    </div>
    <div class="modal-actions">
      <button class="btn btn-outline" onclick="closeModal()">Annuler</button>
      <button class="btn btn-primary" onclick="addCfgAgent('${escHtml(dir)}')">Ajouter</button>
    </div>
  `);
}

async function addCfgAgent(dir) {
  const id = (document.getElementById('cfg-agent-new-id').value || '').trim().replace(/[^a-zA-Z0-9_-]/g, '_').toLowerCase();
  const name = document.getElementById('cfg-agent-new-name').value.trim();
  if (!id || !name) { toast('ID et nom requis', 'error'); return; }
  const llm = document.getElementById('cfg-agent-new-llm').value;
  const temperature = parseFloat(document.getElementById('cfg-agent-new-temp').value) || 0.3;
  const max_tokens = parseInt(document.getElementById('cfg-agent-new-tokens').value) || 32768;
  const prompt_content = document.getElementById('cfg-agent-new-prompt').value || `# ${name}\n\n`;
  const mcpChecked = [...document.querySelectorAll('#modal-container .mcp-check-tag input:checked')].map(cb => cb.value);
  try {
    await api('/api/agents', { method: 'POST', body: {
      id, name, llm, temperature, max_tokens,
      prompt_content,
      prompt_file: `${id}.md`,
      team_id: dir,
    }});
    if (mcpChecked.length) {
      await api(`/api/agents/mcp-access/${encodeURIComponent(dir)}/${encodeURIComponent(id)}`, { method: 'PUT', body: { servers: mcpChecked } });
    }
    toast('Agent ajoute', 'success');
    closeModal();
    loadTeams();
  } catch (e) { toast(e.message, 'error'); }
}

async function editCfgAgent(dir, agentId) {
  const team = teamsData.find(t => (t.directory || t.id) === dir);
  if (!team || !team.agents[agentId]) { toast('Agent introuvable', 'error'); return; }
  const a = team.agents[agentId];
  // Load LLM providers + MCP servers in parallel
  let llmNames = [];
  let mcpServerIds = [];
  try {
    const [llmData, mcpData] = await Promise.all([
      api('/api/templates/llm'),
      api('/api/mcp/servers'),
    ]);
    llmNames = Object.keys(llmData.providers || {});
    mcpServerIds = Object.keys(mcpData.servers || {});
  } catch { /* ignore */ }
  const currentLlm = a.llm || a.model || '';
  const llmOptions = `<option value="">-- Defaut --</option>` +
    llmNames.map(p => `<option value="${escHtml(p)}" ${p === currentLlm ? 'selected' : ''}>${escHtml(p)}</option>`).join('');

  const agentMcp = (team.mcp_access || {})[agentId] || [];
  const mcpTags = mcpServerIds.map(sid => {
    const checked = agentMcp.includes(sid) ? 'checked' : '';
    return `<label class="mcp-check-tag ${checked ? 'active' : ''}">
      <input type="checkbox" value="${escHtml(sid)}" ${checked} onchange="this.parentElement.classList.toggle('active',this.checked)" />${escHtml(sid)}
    </label>`;
  }).join('');

  const promptRaw = a.prompt_content || '';
  const promptHtml = typeof marked !== 'undefined' ? marked.parse(promptRaw) : escHtml(promptRaw);

  showModal(`
    <div class="modal-header">
      <h3>Agent: ${escHtml(a.name)} (${escHtml(agentId)})</h3>
      <button class="btn-icon" onclick="closeModal()">&times;</button>
    </div>
    <div class="form-row">
      <div class="form-group">
        <label>Nom</label>
        <input id="cfg-agent-edit-name" value="${escHtml(a.name)}" />
      </div>
      <div class="form-group">
        <label>Modele LLM</label>
        <select id="cfg-agent-edit-llm">${llmOptions}</select>
      </div>
    </div>
    <div class="form-row">
      <div class="form-group">
        <label>Temperature</label>
        <input id="cfg-agent-edit-temp" type="number" step="0.1" min="0" max="2" value="${a.temperature}" />
      </div>
      <div class="form-group">
        <label>Max tokens</label>
        <input id="cfg-agent-edit-tokens" type="number" value="${a.max_tokens}" />
      </div>
    </div>
    <div class="form-group">
      <label>Prompt (${escHtml(a.prompt || agentId + '.md')})</label>
      <div class="prompt-tabs">
        <div class="prompt-tab active" id="cfg-prompt-tab-preview" onclick="switchCfgPromptTab('preview')">Apercu</div>
        <div class="prompt-tab" id="cfg-prompt-tab-edit" onclick="switchCfgPromptTab('edit')">Editer</div>
      </div>
      <div class="prompt-preview" id="cfg-agent-prompt-preview" style="max-height:400px;overflow-y:auto">${promptHtml}</div>
      <textarea id="cfg-agent-edit-prompt" style="min-height:300px;display:none;border-radius:0 0.5rem 0.5rem 0.5rem">${escHtml(promptRaw)}</textarea>
    </div>
    <div class="form-group">
      <label>Serveurs MCP autorises</label>
      <div class="mcp-check-tags" id="cfg-agent-mcp-tags">
        ${mcpTags || '<span style="color:var(--text-secondary);font-size:0.85rem">Aucun serveur MCP configure</span>'}
      </div>
    </div>
    <div class="modal-actions">
      <button class="btn btn-outline" onclick="closeModal()">Annuler</button>
      <button class="btn btn-primary" onclick="saveCfgAgent('${escHtml(dir)}','${escHtml(agentId)}')">Sauvegarder</button>
    </div>
  `, 'modal-wide');
}

function switchCfgPromptTab(tab) {
  const preview = document.getElementById('cfg-agent-prompt-preview');
  const editor = document.getElementById('cfg-agent-edit-prompt');
  const tabPreview = document.getElementById('cfg-prompt-tab-preview');
  const tabEdit = document.getElementById('cfg-prompt-tab-edit');
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

async function saveCfgAgent(dir, agentId) {
  const name = document.getElementById('cfg-agent-edit-name').value.trim();
  if (!name) { toast('Nom requis', 'error'); return; }
  const llm = document.getElementById('cfg-agent-edit-llm').value;
  const temperature = parseFloat(document.getElementById('cfg-agent-edit-temp').value);
  const max_tokens = parseInt(document.getElementById('cfg-agent-edit-tokens').value);
  const prompt_content = document.getElementById('cfg-agent-edit-prompt').value;
  const team = teamsData.find(t => (t.directory || t.id) === dir);
  const a = team.agents[agentId];
  // Collect checked MCP servers
  const mcpChecked = [...document.querySelectorAll('#cfg-agent-mcp-tags input[type=checkbox]:checked')].map(cb => cb.value);
  try {
    await Promise.all([
      api(`/api/agents/${encodeURIComponent(agentId)}`, { method: 'PUT', body: {
        id: agentId, name, llm, temperature, max_tokens,
        prompt_content,
        prompt_file: a.prompt || `${agentId}.md`,
        type: a.type || '',
        pipeline_steps: a.pipeline_steps || [],
        team_id: dir,
      }}),
      api(`/api/agents/mcp-access/${encodeURIComponent(dir)}/${encodeURIComponent(agentId)}`, { method: 'PUT', body: { servers: mcpChecked }}),
    ]);
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
        <h3>Registry JSON — Configs/Teams/${escHtml(dir)}/</h3>
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

async function showAddTeamModal() {
  // Load templates to offer as options
  try {
    const data = await api('/api/templates');
    templatesData = data.templates || [];
  } catch (e) { templatesData = []; }
  const dirOpts = templatesData.map(tp => `<option value="${escHtml(tp.id)}">${escHtml(tp.id)} (${tp.agent_count} agents)</option>`).join('');
  showModal(`
    <div class="modal-header">
      <h3>Nouvelle equipe</h3>
      <button class="btn-icon" onclick="closeModal()">&times;</button>
    </div>
    <div class="form-group">
      <label>Identifiant</label>
      <input id="team-id" placeholder="ex: data_team" />
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
      <label>Repertoire (Configs/Teams/...)</label>
      <select id="team-dir" class="form-control">
        <option value="">-- Saisie libre --</option>
        ${dirOpts}
      </select>
      <input id="team-dir-custom" class="form-control" placeholder="Ou saisir un nom de repertoire" style="margin-top:0.25rem">
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
      <textarea id="team-channels" rows="3" placeholder="1234567890"></textarea>
    </div>
    <div class="modal-actions">
      <button class="btn btn-outline" onclick="closeModal()">Annuler</button>
      <button class="btn btn-primary" onclick="addTeam()">Enregistrer</button>
    </div>
  `);
}

function editTeam(idx) {
  const t = teamsData[idx];
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
      <input id="team-dir" value="${escHtml(t.directory || t.id)}" />
    </div>
    <div class="form-group">
      <label>Channels Discord (un par ligne)</label>
      <textarea id="team-channels" rows="3">${(t.discord_channels || []).join('\n')}</textarea>
    </div>
    <div class="modal-actions">
      <button class="btn btn-outline" onclick="closeModal()">Annuler</button>
      <button class="btn btn-primary" onclick="saveTeam('${escHtml(t.id)}')">Enregistrer</button>
    </div>
  `);
}

async function addTeam() {
  const id = (document.getElementById('team-id')?.value || '').trim().replace(/[^a-zA-Z0-9_-]/g, '_').toLowerCase();
  if (!id) { toast('Identifiant requis', 'error'); return; }
  const name = document.getElementById('team-name').value.trim();
  if (!name) { toast('Nom requis', 'error'); return; }
  const dirSelect = document.getElementById('team-dir').value;
  const dirCustom = document.getElementById('team-dir-custom').value.trim();
  const directory = dirCustom || dirSelect || id;
  const channels = document.getElementById('team-channels').value.split('\n').map(s => s.trim()).filter(Boolean);
  const template = document.getElementById('team-template')?.value || '';
  try {
    await api(`/api/teams/${encodeURIComponent(id)}`, { method: 'POST', body: {
      name,
      description: document.getElementById('team-desc').value.trim(),
      directory,
      discord_channels: channels,
      template,
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
  const channels = document.getElementById('team-channels').value.split('\n').map(s => s.trim()).filter(Boolean);
  try {
    await api(`/api/teams/${encodeURIComponent(id)}`, { method: 'PUT', body: {
      name,
      description: document.getElementById('team-desc').value.trim(),
      directory,
      discord_channels: channels,
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
  else if (tabId === 'tpl-teams') loadTplTeamsList();
  else if (tabId === 'tpl-git') loadTplGit();
}

async function loadTemplates() {
  // Load active sub-tab
  const active = document.querySelector('[data-tpl-tab].active');
  const tab = active ? active.getAttribute('data-tpl-tab') : 'tpl-llm';
  showTemplateTab(tab);
}

// ── Template Git (Enregistrement) ─────────────────
async function loadTplGit() {
  try {
    const [status, cfg] = await Promise.all([
      api('/api/git/shared/status'),
      api('/api/git/config'),
    ]);
    const shared = cfg.repos?.shared || {};
    document.getElementById('tpl-git-path').value = shared.path || '';
    document.getElementById('tpl-git-login').value = shared.login || '';
    document.getElementById('tpl-git-password').value = shared.password || '';
    const inited = status.initialized;
    document.getElementById('tpl-git-branch').textContent = inited ? (status.branch || 'inconnu') : 'Non initialise';
    document.getElementById('tpl-git-status').textContent = inited ? (status.status || '(aucun changement)') : 'Git non initialise. Enregistrez la configuration puis cliquez Init.';
    document.getElementById('tpl-git-log').textContent = inited ? (status.log || '(vide)') : '';
    document.getElementById('btn-tpl-git-init').disabled = inited;
    document.getElementById('btn-tpl-git-pull').disabled = !inited;
    document.getElementById('btn-tpl-git-commit').disabled = !inited;
    if (inited) loadTplGitCommits();
  } catch (e) { toast(e.message, 'error'); }
}

async function saveTplGitConfig() {
  try {
    const current = await api('/api/git/config');
    const body = {
      repos: {
        configs: current.repos?.configs || { path: '', login: '', password: '' },
        shared: {
          path: document.getElementById('tpl-git-path').value.trim(),
          login: document.getElementById('tpl-git-login').value.trim(),
          password: document.getElementById('tpl-git-password').value.trim(),
        },
      },
    };
    await api('/api/git/config', { method: 'PUT', body });
    toast('Configuration Git Shared enregistree', 'success');
    loadTplGit();
  } catch (e) { toast(e.message, 'error'); }
}

async function tplGitInit() {
  try {
    const data = await api('/api/git/shared/init', { method: 'POST' });
    toast(data.ok ? 'Repository Shared initialise' : (data.message || 'Erreur'), data.ok ? 'success' : 'error');
    loadTplGit();
  } catch (e) { toast(e.message, 'error'); }
}

async function tplGitPull() {
  try {
    const data = await api('/api/git/shared/pull', { method: 'POST' });
    if (data.code === 0) {
      toast('Pull Shared reussi', 'success');
    } else {
      const detail = (data.stderr || data.stdout || 'erreur inconnue').substring(0, 200);
      toast(`Pull Shared erreur: ${detail}`, 'error');
    }
    loadTplGit();
  } catch (e) { toast(e.message, 'error'); }
}

async function loadTplGitCommits() {
  const wrap = document.getElementById('tpl-git-commits');
  if (!wrap) return;
  try {
    const data = await api('/api/git/shared/commits');
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
        <td><button class="btn-revert" onclick="tplGitCheckout('${c.hash}')" title="Revenir a cette version">&#8634;</button></td>
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

async function tplGitCheckout(hash) {
  if (!(await confirmModal('Revenir a cette version ?\nLes modifications non commitees seront verifiees avant.'))) return;
  try {
    const data = await api(`/api/git/shared/checkout/${hash}`, { method: 'POST' });
    toast(data.message || 'Version restauree', 'success');
    loadTplGit();
  } catch (e) {
    toast(e.message, 'error');
  }
}

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
      <thead><tr><th>ID</th><th>Type</th><th>Modele</th><th>Cle API</th><th>Description</th><th style="width:100px">Actions</th></tr></thead>
      <tbody>${Object.entries(providers).map(([id, p]) => {
        const isDefault = id === defaultId;
        return `<tr>
          <td><strong>${escHtml(id)}</strong>${isDefault ? '<span class="tag tag-green" style="margin-left:0.5rem">defaut</span>' : ''}</td>
          <td><span class="tag tag-blue">${escHtml(p.type)}</span></td>
          <td><code style="font-size:0.8rem">${escHtml(p.model)}</code></td>
          <td>${p.env_key ? `<code style="font-size:0.75rem">${escHtml(p.env_key)}</code>` : '<span style="color:var(--text-secondary)">—</span>'}</td>
          <td style="font-size:0.8rem;color:var(--text-secondary)">${escHtml(p.description || '')}</td>
          <td>
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
}

async function setTplLLMDefault(providerId) {
  tplLlmData.default = providerId;
  try {
    await api('/api/templates/llm', { method: 'PUT', body: tplLlmData });
    toast('Modele par defaut du template mis a jour', 'success');
    loadTplLLM();
  } catch (e) { toast(e.message, 'error'); }
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

// ── Template MCP ──────────────────────────────────
async function loadTplMCP() {
  try {
    tplMcpData = await api('/api/templates/mcp');
    renderTplMCP();
  } catch (e) { toast(e.message, 'error'); }
}

function renderTplMCP() {
  const servers = tplMcpData.servers || {};
  const tbl = document.getElementById('tpl-mcp-table');
  const entries = Object.entries(servers);
  if (entries.length === 0) {
    tbl.innerHTML = '<p style="color:var(--text-secondary);text-align:center;padding:1rem">Aucun serveur MCP dans le template. Ajoutez-en pour les inclure automatiquement dans les nouvelles equipes.</p>';
    return;
  }
  tbl.innerHTML = `<table>
    <thead><tr><th>Service</th><th>Commande</th><th>Variables d'env</th><th style="width:100px">Actions</th></tr></thead>
    <tbody>${entries.map(([id, s]) => {
      const envKeys = s.env ? Object.keys(s.env) : [];
      const envTags = envKeys.length
        ? envKeys.map(k => `<span class="tag tag-green" title="${escHtml(s.env[k])}">${escHtml(k)}</span>`).join(' ')
        : '<span class="tag tag-gray">aucune</span>';
      return `<tr>
        <td>
          <strong>${escHtml(id)}</strong>
        </td>
        <td><code style="font-size:0.75rem">${escHtml(s.command || '')} ${escHtml((s.args || []).join(' '))}</code></td>
        <td>${envTags}</td>
        <td>
          <button class="btn-icon" onclick="editTplMcp('${escHtml(id)}')" title="Modifier">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>
          </button>
          <button class="btn-icon danger" onclick="deleteTplMcp('${escHtml(id)}')" title="Supprimer">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>
          </button>
        </td>
      </tr>`;
    }).join('')}</tbody>
  </table>`;
}

let tplMcpCatalog = [];

async function showAddTplMcpModal() {
  // Load catalog
  try {
    const data = await api('/api/mcp/catalog');
    tplMcpCatalog = data.servers || [];
  } catch (e) { tplMcpCatalog = []; }
  const existing = Object.keys(tplMcpData.servers || {});
  // Services with env_vars can be instantiated multiple times (different IDs)
  // Services without env_vars are removed from the list once added
  const available = tplMcpCatalog.filter(c =>
    !c.deprecated && ((c.env_vars && c.env_vars.length > 0) || !existing.includes(c.id))
  );
  if (available.length === 0) {
    toast('Tous les services du catalogue sont deja ajoutes', 'info');
    return;
  }
  const options = available.map(c =>
    `<option value="${escHtml(c.id)}">${escHtml(c.label)} — ${escHtml(c.description)}</option>`
  ).join('');
  showModal(`
    <div class="modal-header">
      <h3>Ajouter un serveur MCP (template)</h3>
      <button class="btn-icon" onclick="closeModal()">&times;</button>
    </div>
    <div class="form-group">
      <label>Service</label>
      <select id="mcp-tpl-select" onchange="onTplMcpSelected()">
        ${options}
      </select>
    </div>
    <div id="mcp-tpl-details"></div>
    <div class="modal-actions">
      <button class="btn btn-outline" onclick="closeModal()">Annuler</button>
      <button class="btn btn-primary" onclick="addTplMcp()">Ajouter</button>
    </div>
  `, 'modal-wide');
  onTplMcpSelected();
}

function onTplMcpSelected() {
  const id = document.getElementById('mcp-tpl-select').value;
  const item = tplMcpCatalog.find(c => c.id === id);
  if (!item) return;
  document.getElementById('mcp-tpl-details').innerHTML = _renderTplMcpDetails(item);
}


function _renderTplMcpDetails(item) {
  const hasEnv = item.env_vars && item.env_vars.length > 0;
  const prefix = item.id.replace(/[^a-zA-Z0-9]/g, '_').toUpperCase();

  const idHtml = hasEnv ? `
    <div class="form-group" style="margin-top:0.5rem">
      <label>ID de l'instance</label>
      <input id="mcp-tpl-instance" value="${escHtml(item.id)}" oninput="_updateTplMcpEnvNames(); _validateTplMcpInstanceId()" />
      <span id="mcp-tpl-instance-error" style="color:var(--danger);font-size:0.8rem;display:none"></span>
    </div>` : '';

  const envHtml = hasEnv
    ? `<div style="margin-top:1rem">
        <label>Variables d'environnement</label>
        <div class="env-var-list" id="mcp-tpl-env-list">
          ${item.env_vars.map(v => {
            const envName = `${prefix}_${v.var}`;
            return `
            <div class="env-var-row">
              <div class="env-var-info">
                <span style="font-size:0.85rem">${escHtml(v.desc || v.var)}</span>
              </div>
              <div class="env-var-action" style="flex:none">
                <code class="mcp-tpl-env-computed" data-base="${escHtml(v.var)}" style="font-size:0.8rem;white-space:nowrap">${escHtml(envName)}</code>
              </div>
            </div>`;
          }).join('')}
        </div>
      </div>`
    : '<p style="color:var(--text-secondary);font-size:0.85rem;margin-top:1rem">Aucune variable d\'environnement requise.</p>';

  return `
    ${idHtml}
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
    ${envHtml}
  `;
}

function _updateTplMcpEnvNames() {
  const name = document.getElementById('mcp-tpl-instance')?.value.trim() || '';
  const prefix = name.replace(/[^a-zA-Z0-9]/g, '_').toUpperCase() || 'INSTANCE';
  document.querySelectorAll('.mcp-tpl-env-computed').forEach(el => {
    const base = el.getAttribute('data-base');
    el.textContent = `${prefix}_${base}`;
  });
}

function _validateTplMcpInstanceId() {
  const el = document.getElementById('mcp-tpl-instance');
  const errEl = document.getElementById('mcp-tpl-instance-error');
  if (!el || !errEl) return true;
  const id = el.value.trim();
  const existing = Object.keys(tplMcpData.servers || {});
  if (id && existing.includes(id)) {
    el.style.border = '2px solid var(--danger)';
    errEl.textContent = `L'ID "${id}" existe deja`;
    errEl.style.display = 'block';
    return false;
  }
  el.style.border = '';
  errEl.style.display = 'none';
  return true;
}

async function addTplMcp() {
  const selectEl = document.getElementById('mcp-tpl-select');
  const catalogId = selectEl.value;
  const item = tplMcpCatalog.find(c => c.id === catalogId);
  if (!item) { toast('Service introuvable', 'error'); return; }
  const instanceEl = document.getElementById('mcp-tpl-instance');
  const id = instanceEl ? instanceEl.value.trim() : catalogId;
  if (!id) { toast('ID requis', 'error'); return; }
  if (instanceEl && !_validateTplMcpInstanceId()) { toast('ID deja utilise', 'error'); return; }

  // Build env mapping from computed names
  const env = {};
  document.querySelectorAll('.mcp-tpl-env-computed').forEach(el => {
    const envName = el.textContent;
    env[el.getAttribute('data-base')] = `\${${envName}}`;
  });

  if (!tplMcpData.servers) tplMcpData.servers = {};
  tplMcpData.servers[id] = {
    command: item.command,
    args: item.args ? item.args.split(/\s+/) : [],
    env,
  };
  try {
    await api('/api/templates/mcp', { method: 'PUT', body: tplMcpData });
    toast('Serveur MCP ajoute au template', 'success');
    closeModal();
    loadTplMCP();
  } catch (e) { toast(e.message, 'error'); }
}

function editTplMcp(id) {
  const s = tplMcpData.servers[id];
  if (!s) return;
  // Try to find in catalog for env var descriptions
  const catalogItem = tplMcpCatalog.length ? tplMcpCatalog.find(c => c.id === id) : null;
  const envEntries = Object.entries(s.env || {});
  const envRows = envEntries.length
    ? envEntries.map(([k, v]) => {
        const desc = catalogItem ? (catalogItem.env_vars.find(ev => ev.var === k) || {}).desc || k : k;
        return `<div class="env-var-row">
          <div class="env-var-info"><span style="font-size:0.85rem">${escHtml(desc)}</span></div>
          <div class="env-var-action" style="flex:none"><code style="font-size:0.8rem">${escHtml(v)}</code></div>
        </div>`;
      }).join('')
    : '<p style="color:var(--text-secondary);font-size:0.85rem">Aucune variable.</p>';

  showModal(`
    <div class="modal-header">
      <h3>MCP (template) : ${escHtml(id)}</h3>
      <button class="btn-icon" onclick="closeModal()">&times;</button>
    </div>
    <div class="form-row">
      <div class="form-group">
        <label>Commande</label>
        <input value="${escHtml(s.command || '')}" readonly style="opacity:0.6" />
      </div>
      <div class="form-group">
        <label>Arguments</label>
        <input value="${escHtml((s.args || []).join(' '))}" readonly style="opacity:0.6" />
      </div>
    </div>
    <div style="margin-top:0.5rem">
      <label>Variables d'environnement</label>
      <div class="env-var-list">${envRows}</div>
    </div>
    <div class="modal-actions">
      <button class="btn btn-outline" onclick="closeModal()">Fermer</button>
    </div>
  `, 'modal-wide');
}

async function deleteTplMcp(id) {
  if (!(await confirmModal(`Supprimer le serveur MCP "${id}" du template ?`))) return;
  delete tplMcpData.servers[id];
  try {
    await api('/api/templates/mcp', { method: 'PUT', body: tplMcpData });
    toast('Serveur MCP supprime du template', 'success');
    loadTplMCP();
  } catch (e) { toast(e.message, 'error'); }
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

    const agentCards = agentEntries.map(([aid, a]) => {
      const mcpList = mcpAccess[aid] || [];
      return `<div class="agent-card" style="cursor:pointer">
        <div class="agent-card-header">
          <div onclick="editTplAgent('${escHtml(dir)}','${escHtml(aid)}')" style="flex:1;cursor:pointer">
            <h4>${escHtml(a.name)}</h4>
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
          <button class="btn btn-primary btn-sm" onclick="showAddTplAgentModal('${escHtml(dir)}')">+ Agent</button>
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
}

async function showAddTplAgentModal(dir) {
  let llmNames = [], mcpServerIds = [];
  try {
    const [llmData, mcpData] = await Promise.all([api('/api/templates/llm'), api('/api/templates/mcp')]);
    llmNames = Object.keys(llmData.providers || {});
    mcpServerIds = Object.keys(mcpData.servers || {});
  } catch { /* ignore */ }
  const llmOptions = `<option value="">-- Defaut --</option>` +
    llmNames.map(p => `<option value="${escHtml(p)}">${escHtml(p)}</option>`).join('');
  const mcpTags = mcpServerIds.length
    ? mcpServerIds.map(sid => `<label class="mcp-check-tag"><input type="checkbox" value="${escHtml(sid)}" onchange="this.parentElement.classList.toggle('active',this.checked)" />${escHtml(sid)}</label>`).join('')
    : '<span style="color:var(--text-secondary);font-size:0.8rem">Aucun serveur MCP dans le template</span>';
  showModal(`
    <div class="modal-header">
      <h3>Nouvel agent (template)</h3>
      <button class="btn-icon" onclick="closeModal()">&times;</button>
    </div>
    <div class="form-row">
      <div class="form-group">
        <label>ID (identifiant unique)</label>
        <input id="tpl-agent-new-id" placeholder="mon_agent" />
      </div>
      <div class="form-group">
        <label>Nom affiche</label>
        <input id="tpl-agent-new-name" placeholder="Mon Agent" />
      </div>
    </div>
    <div class="form-row">
      <div class="form-group">
        <label>Modele LLM</label>
        <select id="tpl-agent-new-llm">${llmOptions}</select>
      </div>
    </div>
    <div class="form-row">
      <div class="form-group">
        <label>Temperature</label>
        <input id="tpl-agent-new-temp" type="number" step="0.1" min="0" max="2" value="0.3" />
      </div>
      <div class="form-group">
        <label>Max tokens</label>
        <input id="tpl-agent-new-tokens" type="number" value="32768" />
      </div>
    </div>
    <div class="form-group">
      <label>Services MCP</label>
      <div class="mcp-check-tags">${mcpTags}</div>
    </div>
    <div class="form-group">
      <label>Prompt initial</label>
      <textarea id="tpl-agent-new-prompt" style="min-height:120px" placeholder="# Mon Agent\n\nDescription du role..."></textarea>
    </div>
    <div class="modal-actions">
      <button class="btn btn-outline" onclick="closeModal()">Annuler</button>
      <button class="btn btn-primary" onclick="addTplAgent('${escHtml(dir)}')">Ajouter</button>
    </div>
  `);
}

async function addTplAgent(dir) {
  const id = (document.getElementById('tpl-agent-new-id').value || '').trim().replace(/[^a-zA-Z0-9_-]/g, '_').toLowerCase();
  const name = document.getElementById('tpl-agent-new-name').value.trim();
  if (!id || !name) { toast('ID et nom requis', 'error'); return; }
  const llm = document.getElementById('tpl-agent-new-llm').value;
  const temperature = parseFloat(document.getElementById('tpl-agent-new-temp').value) || 0.3;
  const max_tokens = parseInt(document.getElementById('tpl-agent-new-tokens').value) || 32768;
  const prompt_content = document.getElementById('tpl-agent-new-prompt').value || `# ${name}\n\n`;
  const mcpChecked = [...document.querySelectorAll('#modal-container .mcp-check-tag input:checked')].map(cb => cb.value);
  try {
    await api('/api/templates/agents', { method: 'POST', body: {
      id, name, llm, temperature, max_tokens,
      prompt_content,
      prompt_file: `${id}.md`,
      team_id: dir,
    }});
    if (mcpChecked.length) {
      await api(`/api/templates/mcp-access/${encodeURIComponent(dir)}/${encodeURIComponent(id)}`, { method: 'PUT', body: { servers: mcpChecked } });
    }
    toast('Agent ajoute', 'success');
    closeModal();
    loadTplTeamsList();
  } catch (e) { toast(e.message, 'error'); }
}

async function editTplAgent(dir, agentId) {
  const tpl = tplTemplatesData.find(tp => tp.id === dir);
  if (!tpl || !tpl.agents[agentId]) { toast('Agent introuvable', 'error'); return; }
  const a = tpl.agents[agentId];
  // Load LLM providers + MCP servers in parallel
  let llmNames = [];
  let mcpServerIds = [];
  try {
    const [llmData, mcpData] = await Promise.all([
      api('/api/templates/llm'),
      api('/api/templates/mcp'),
    ]);
    llmNames = Object.keys(llmData.providers || {});
    mcpServerIds = Object.keys(mcpData.servers || {});
  } catch { /* ignore */ }
  const currentLlm = a.llm || a.model || '';
  const llmOptions = `<option value="">-- Defaut --</option>` +
    llmNames.map(p => `<option value="${escHtml(p)}" ${p === currentLlm ? 'selected' : ''}>${escHtml(p)}</option>`).join('');

  const agentMcp = (tpl.mcp_access || {})[agentId] || [];
  const mcpTags = mcpServerIds.map(sid => {
    const checked = agentMcp.includes(sid) ? 'checked' : '';
    return `<label class="mcp-check-tag ${checked ? 'active' : ''}">
      <input type="checkbox" value="${escHtml(sid)}" ${checked} onchange="this.parentElement.classList.toggle('active',this.checked)" />${escHtml(sid)}
    </label>`;
  }).join('');

  const promptRaw = a.prompt_content || '';
  const promptHtml = typeof marked !== 'undefined' ? marked.parse(promptRaw) : escHtml(promptRaw);

  showModal(`
    <div class="modal-header">
      <h3>Agent: ${escHtml(a.name)} (${escHtml(agentId)})</h3>
      <button class="btn-icon" onclick="closeModal()">&times;</button>
    </div>
    <div class="form-row">
      <div class="form-group">
        <label>Nom</label>
        <input id="tpl-agent-edit-name" value="${escHtml(a.name)}" />
      </div>
      <div class="form-group">
        <label>Modele LLM</label>
        <select id="tpl-agent-edit-llm">${llmOptions}</select>
      </div>
    </div>
    <div class="form-row">
      <div class="form-group">
        <label>Temperature</label>
        <input id="tpl-agent-edit-temp" type="number" step="0.1" min="0" max="2" value="${a.temperature}" />
      </div>
      <div class="form-group">
        <label>Max tokens</label>
        <input id="tpl-agent-edit-tokens" type="number" value="${a.max_tokens}" />
      </div>
    </div>
    <div class="form-group">
      <label>Prompt (${escHtml(a.prompt || agentId + '.md')})</label>
      <div class="prompt-tabs">
        <div class="prompt-tab active" id="tpl-prompt-tab-preview" onclick="switchTplPromptTab('preview')">Apercu</div>
        <div class="prompt-tab" id="tpl-prompt-tab-edit" onclick="switchTplPromptTab('edit')">Editer</div>
      </div>
      <div class="prompt-preview" id="tpl-agent-prompt-preview" style="max-height:400px;overflow-y:auto">${promptHtml}</div>
      <textarea id="tpl-agent-edit-prompt" style="min-height:300px;display:none;border-radius:0 0.5rem 0.5rem 0.5rem">${escHtml(promptRaw)}</textarea>
    </div>
    <div class="form-group">
      <label>Serveurs MCP autorises</label>
      <div class="mcp-check-tags" id="tpl-agent-mcp-tags">
        ${mcpTags || '<span style="color:var(--text-secondary);font-size:0.85rem">Aucun serveur MCP configure</span>'}
      </div>
    </div>
    <div class="modal-actions">
      <button class="btn btn-outline" onclick="closeModal()">Annuler</button>
      <button class="btn btn-primary" onclick="saveTplAgent('${escHtml(dir)}','${escHtml(agentId)}')">Sauvegarder</button>
    </div>
  `, 'modal-wide');
}

function switchTplPromptTab(tab) {
  const preview = document.getElementById('tpl-agent-prompt-preview');
  const editor = document.getElementById('tpl-agent-edit-prompt');
  const tabPreview = document.getElementById('tpl-prompt-tab-preview');
  const tabEdit = document.getElementById('tpl-prompt-tab-edit');
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

async function saveTplAgent(dir, agentId) {
  const name = document.getElementById('tpl-agent-edit-name').value.trim();
  if (!name) { toast('Nom requis', 'error'); return; }
  const llm = document.getElementById('tpl-agent-edit-llm').value;
  const temperature = parseFloat(document.getElementById('tpl-agent-edit-temp').value);
  const max_tokens = parseInt(document.getElementById('tpl-agent-edit-tokens').value);
  const prompt_content = document.getElementById('tpl-agent-edit-prompt').value;
  const tpl = tplTemplatesData.find(tp => tp.id === dir);
  const a = tpl.agents[agentId];
  const mcpChecked = [...document.querySelectorAll('#tpl-agent-mcp-tags input[type=checkbox]:checked')].map(cb => cb.value);
  try {
    await Promise.all([
      api(`/api/templates/agents/${encodeURIComponent(agentId)}`, { method: 'PUT', body: {
        id: agentId, name, llm, temperature, max_tokens,
        prompt_content,
        prompt_file: a.prompt || `${agentId}.md`,
        type: a.type || '',
        pipeline_steps: a.pipeline_steps || [],
        team_id: dir,
      }}),
      api(`/api/templates/mcp-access/${encodeURIComponent(dir)}/${encodeURIComponent(agentId)}`, { method: 'PUT', body: { servers: mcpChecked }}),
    ]);
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
  const raw = el.value.replace(/[^a-zA-Z0-9_-]/g, '_').toLowerCase();
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
    <div class="form-group"><label>Channels Discord (virgule)</label><input id="m-tpl-team-channels" class="form-control" value="${(t.discord_channels || []).join(', ')}"></div>
    <div class="modal-actions">
      <button class="btn btn-outline" onclick="closeModal()">Annuler</button>
      <button class="btn btn-primary" onclick="saveTplTeam(${idx})">Sauvegarder</button>
    </div>
  `);
}

async function saveTplTeam(idx) {
  const channels = document.getElementById('m-tpl-team-channels').value.trim();
  tplTeamsData.teams[idx] = {
    ...tplTeamsData.teams[idx],
    name: document.getElementById('m-tpl-team-name').value.trim(),
    description: document.getElementById('m-tpl-team-desc').value.trim(),
    discord_channels: channels ? channels.split(',').map(s => s.trim()) : []
  };
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
// INIT
// ═══════════════════════════════════════════════════
document.addEventListener('DOMContentLoaded', () => {
  loadEnv();
});

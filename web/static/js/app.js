/* LandGraph Admin — Frontend */

// ── State ──────────────────────────────────────────
let envEntries = [];
let mcpServers = {};
let mcpCatalog = [];
let mcpAccess = {};
let agents = {};
let llmProviders = {};

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
  const loaders = { secrets: loadEnv, mcp: loadMCP, agents: loadAgents, scripts: loadScripts, git: loadGit };
  if (loaders[name]) loaders[name]();
}

// ── Modal helpers ──────────────────────────────────
function showModal(html) {
  document.getElementById('modal-container').innerHTML = `
    <div class="modal-overlay" onclick="if(event.target===this)closeModal()">
      <div class="modal">${html}</div>
    </div>`;
}

function closeModal() {
  document.getElementById('modal-container').innerHTML = '';
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
  const rows = envEntries.filter(e => e.key).map((e, i) => `
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
  if (!confirm(`Supprimer "${key}" ?`)) return;
  try {
    await api('/api/env/delete', { method: 'POST', body: { key } });
    toast('Secret supprime', 'success');
    loadEnv();
  } catch (e) { toast(e.message, 'error'); }
}

// ═══════════════════════════════════════════════════
// MCP SERVICES
// ═══════════════════════════════════════════════════
async function loadMCP() {
  try {
    const [serversData, catalogData, accessData] = await Promise.all([
      api('/api/mcp/servers'),
      api('/api/mcp/catalog'),
      api('/api/mcp/access'),
    ]);
    mcpServers = serversData.servers;
    mcpCatalog = catalogData.servers;
    mcpAccess = accessData;
    renderMCP();
  } catch (e) { toast(e.message, 'error'); }
}

function renderMCP() {
  // Configured servers
  const configuredEl = document.getElementById('mcp-configured');
  const serverIds = Object.keys(mcpServers);
  if (serverIds.length === 0) {
    configuredEl.innerHTML = '<p style="color:var(--text-secondary);text-align:center;padding:1rem">Aucun serveur MCP configure.</p>';
  } else {
    configuredEl.innerHTML = `<table>
      <thead><tr><th>ID</th><th>Commande</th><th>Transport</th><th>Actif</th><th>Actions</th></tr></thead>
      <tbody>${serverIds.map(id => {
        const s = mcpServers[id];
        const args = Array.isArray(s.args) ? s.args.join(' ') : s.args;
        const enabled = s.enabled !== false;
        return `<tr>
          <td><strong>${escHtml(id)}</strong></td>
          <td><code>${escHtml(s.command)} ${escHtml(args)}</code></td>
          <td><span class="tag tag-blue">${s.transport || 'stdio'}</span></td>
          <td><span class="tag ${enabled ? 'tag-green' : 'tag-red'}">${enabled ? 'Oui' : 'Non'}</span></td>
          <td>
            <button class="btn-icon" onclick="editMCPServer('${escHtml(id)}')" title="Modifier">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>
            </button>
            <button class="btn-icon danger" onclick="deleteMCPServer('${escHtml(id)}')" title="Supprimer">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>
            </button>
          </td>
        </tr>`;
      }).join('')}</tbody>
    </table>`;
  }

  // Catalog
  const catalogEl = document.getElementById('mcp-catalog');
  catalogEl.innerHTML = mcpCatalog
    .filter(c => !c.deprecated)
    .map(c => {
      const installed = mcpServers.hasOwnProperty(c.id);
      return `<div class="mcp-card ${installed ? 'installed' : ''}">
        <div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:0.5rem">
          <strong>${escHtml(c.label)}</strong>
          ${installed
            ? '<span class="tag tag-green">Configure</span>'
            : `<button class="btn btn-sm btn-primary" onclick="installMCPFromCatalog('${escHtml(c.id)}')">Installer</button>`
          }
        </div>
        <p style="font-size:0.8rem;color:var(--text-secondary);margin-bottom:0.5rem">${escHtml(c.description)}</p>
        <code style="font-size:0.7rem;color:var(--text-secondary)">${escHtml(c.command)} ${escHtml(c.args)}</code>
        ${c.env_vars.length ? `<div style="margin-top:0.5rem">${c.env_vars.map(v =>
          `<span class="tag tag-yellow" style="margin:0.1rem">${escHtml(v.var)}</span>`
        ).join('')}</div>` : ''}
      </div>`;
    }).join('');
}

function showAddMCPModal() {
  const available = mcpCatalog.filter(c => !c.deprecated && !mcpServers.hasOwnProperty(c.id));
  showModal(`
    <div class="modal-header">
      <h3>Ajouter un serveur MCP</h3>
      <button class="btn-icon" onclick="closeModal()">&times;</button>
    </div>
    <div class="form-group">
      <label>Depuis le catalogue</label>
      <select id="mcp-catalog-select" onchange="fillMCPForm()">
        <option value="">-- Choisir ou configurer manuellement --</option>
        ${available.map(c => `<option value="${c.id}">${escHtml(c.label)} — ${escHtml(c.description)}</option>`).join('')}
      </select>
    </div>
    <div class="form-group">
      <label>ID</label>
      <input id="mcp-new-id" placeholder="mon-serveur" />
    </div>
    <div class="form-row">
      <div class="form-group">
        <label>Commande</label>
        <input id="mcp-new-cmd" placeholder="npx" />
      </div>
      <div class="form-group">
        <label>Arguments</label>
        <input id="mcp-new-args" placeholder="-y @package/name" />
      </div>
    </div>
    <div class="form-group">
      <label>Variables d'environnement (JSON)</label>
      <input id="mcp-new-env" placeholder='{"VAR_NAME": "ENV_VAR_NAME"}' value="{}" />
    </div>
    <div class="modal-actions">
      <button class="btn btn-outline" onclick="closeModal()">Annuler</button>
      <button class="btn btn-primary" onclick="addMCPServer()">Ajouter</button>
    </div>
  `);
}

function fillMCPForm() {
  const id = document.getElementById('mcp-catalog-select').value;
  const item = mcpCatalog.find(c => c.id === id);
  if (!item) return;
  document.getElementById('mcp-new-id').value = item.id;
  document.getElementById('mcp-new-cmd').value = item.command;
  document.getElementById('mcp-new-args').value = item.args;
  if (item.env_vars.length) {
    const env = {};
    item.env_vars.forEach(v => { env[v.var] = v.var; });
    document.getElementById('mcp-new-env').value = JSON.stringify(env);
  }
}

function installMCPFromCatalog(catalogId) {
  const item = mcpCatalog.find(c => c.id === catalogId);
  if (!item) return;
  showAddMCPModal();
  setTimeout(() => {
    document.getElementById('mcp-catalog-select').value = catalogId;
    fillMCPForm();
  }, 50);
}

async function addMCPServer() {
  const id = document.getElementById('mcp-new-id').value.trim();
  const command = document.getElementById('mcp-new-cmd').value.trim();
  const args = document.getElementById('mcp-new-args').value.trim();
  let env = {};
  try { env = JSON.parse(document.getElementById('mcp-new-env').value); } catch {}
  if (!id || !command) { toast('ID et commande requis', 'error'); return; }
  try {
    await api('/api/mcp/servers', { method: 'POST', body: { id, command, args, env, transport: 'stdio', enabled: true } });
    toast('Serveur MCP ajoute', 'success');
    closeModal();
    loadMCP();
  } catch (e) { toast(e.message, 'error'); }
}

function editMCPServer(id) {
  const s = mcpServers[id];
  const args = Array.isArray(s.args) ? s.args.join(' ') : s.args;
  showModal(`
    <div class="modal-header">
      <h3>Modifier: ${escHtml(id)}</h3>
      <button class="btn-icon" onclick="closeModal()">&times;</button>
    </div>
    <div class="form-row">
      <div class="form-group">
        <label>Commande</label>
        <input id="mcp-edit-cmd" value="${escHtml(s.command)}" />
      </div>
      <div class="form-group">
        <label>Arguments</label>
        <input id="mcp-edit-args" value="${escHtml(args)}" />
      </div>
    </div>
    <div class="form-group">
      <label>Variables d'environnement (JSON)</label>
      <input id="mcp-edit-env" value='${escHtml(JSON.stringify(s.env || {}))}' />
    </div>
    <div class="form-group">
      <label>
        <input type="checkbox" id="mcp-edit-enabled" ${s.enabled !== false ? 'checked' : ''} />
        Actif
      </label>
    </div>
    <div class="modal-actions">
      <button class="btn btn-outline" onclick="closeModal()">Annuler</button>
      <button class="btn btn-primary" onclick="saveMCPServer('${escHtml(id)}')">Sauvegarder</button>
    </div>
  `);
}

async function saveMCPServer(id) {
  const command = document.getElementById('mcp-edit-cmd').value.trim();
  const args = document.getElementById('mcp-edit-args').value.trim();
  const enabled = document.getElementById('mcp-edit-enabled').checked;
  let env = {};
  try { env = JSON.parse(document.getElementById('mcp-edit-env').value); } catch {}
  try {
    await api('/api/mcp/servers', { method: 'POST', body: { id, command, args, env, transport: 'stdio', enabled } });
    toast('Serveur MCP modifie', 'success');
    closeModal();
    loadMCP();
  } catch (e) { toast(e.message, 'error'); }
}

async function deleteMCPServer(id) {
  if (!confirm(`Supprimer le serveur MCP "${id}" ?`)) return;
  try {
    await api(`/api/mcp/servers/${id}`, { method: 'DELETE' });
    toast('Serveur MCP supprime', 'success');
    loadMCP();
  } catch (e) { toast(e.message, 'error'); }
}

// ═══════════════════════════════════════════════════
// AGENTS
// ═══════════════════════════════════════════════════
async function loadAgents() {
  try {
    const [agentsData, llmData, accessData] = await Promise.all([
      api('/api/agents'),
      api('/api/llm/providers'),
      api('/api/mcp/access'),
    ]);
    agents = agentsData.agents;
    llmProviders = llmData;
    mcpAccess = accessData;
    renderAgents();
  } catch (e) { toast(e.message, 'error'); }
}

function renderAgents() {
  const grid = document.getElementById('agents-grid');
  const providerNames = Object.keys(llmProviders.providers || {});

  grid.innerHTML = Object.entries(agents).map(([id, a]) => {
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
}

function editAgent(id) {
  const a = agents[id];
  const providerNames = Object.keys(llmProviders.providers || {});
  const mcpList = mcpAccess[id] || [];
  const allMCPIds = Object.keys(mcpServers || {});

  // Build MCP checkboxes — load servers first if needed
  const mcpCheckboxes = allMCPIds.length > 0
    ? allMCPIds.map(mid => `<label style="display:flex;align-items:center;gap:0.5rem;margin:0.25rem 0">
        <input type="checkbox" class="agent-mcp-cb" value="${escHtml(mid)}" ${mcpList.includes(mid) ? 'checked' : ''} />
        ${escHtml(mid)}
      </label>`).join('')
    : '<p style="color:var(--text-secondary);font-size:0.8rem">Aucun serveur MCP configure. Ajoutez-en dans la section MCP d\'abord.</p>';

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
      <textarea id="agent-edit-prompt" style="min-height:300px">${escHtml(a.prompt_content || '')}</textarea>
    </div>
    <div class="form-group">
      <label>Services MCP autorises</label>
      <div style="max-height:150px;overflow-y:auto;padding:0.5rem;background:var(--bg-input);border-radius:0.5rem">
        ${mcpCheckboxes}
      </div>
    </div>
    <div class="modal-actions">
      <button class="btn btn-outline" onclick="closeModal()">Annuler</button>
      <button class="btn btn-primary" onclick="saveAgent('${escHtml(id)}')">Sauvegarder</button>
    </div>
  `);
}

async function saveAgent(id) {
  const name = document.getElementById('agent-edit-name').value.trim();
  const model = document.getElementById('agent-edit-model').value;
  const temperature = parseFloat(document.getElementById('agent-edit-temp').value);
  const max_tokens = parseInt(document.getElementById('agent-edit-tokens').value);
  const prompt_content = document.getElementById('agent-edit-prompt').value;
  const mcpCheckboxes = document.querySelectorAll('.agent-mcp-cb:checked');
  const mcpList = Array.from(mcpCheckboxes).map(cb => cb.value);

  try {
    await Promise.all([
      api(`/api/agents/${id}`, {
        method: 'PUT',
        body: { id, name, model, temperature, max_tokens, prompt_content, prompt_file: '', type: agents[id].type || '', pipeline_steps: agents[id].pipeline_steps || [] }
      }),
      api('/api/mcp/access', { method: 'PUT', body: { agent_id: id, servers: mcpList } }),
    ]);
    toast('Agent sauvegarde', 'success');
    closeModal();
    loadAgents();
  } catch (e) { toast(e.message, 'error'); }
}

function showAddAgentModal() {
  const providerNames = Object.keys(llmProviders.providers || {});
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
  if (!id || !name) { toast('ID et nom requis', 'error'); return; }
  try {
    await api('/api/agents', {
      method: 'POST',
      body: { id, name, model, temperature, max_tokens: 32768, prompt_content, prompt_file: '', type: '', pipeline_steps: [] }
    });
    toast('Agent cree', 'success');
    closeModal();
    loadAgents();
  } catch (e) { toast(e.message, 'error'); }
}

async function deleteAgent(id) {
  if (!confirm(`Supprimer l'agent "${id}" ?`)) return;
  try {
    await api(`/api/agents/${id}`, { method: 'DELETE' });
    toast('Agent supprime', 'success');
    loadAgents();
  } catch (e) { toast(e.message, 'error'); }
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
// GIT
// ═══════════════════════════════════════════════════
async function loadGit() {
  try {
    const data = await api('/api/git/status');
    document.getElementById('git-branch').textContent = data.branch || 'inconnu';
    document.getElementById('git-status').textContent = data.status || '(aucun changement)';
    document.getElementById('git-log').textContent = data.log || '(vide)';
  } catch (e) { toast(e.message, 'error'); }
}

async function gitPull() {
  try {
    const data = await api('/api/git/pull', { method: 'POST' });
    toast(data.code === 0 ? 'Pull reussi' : 'Pull erreur', data.code === 0 ? 'success' : 'error');
    loadGit();
  } catch (e) { toast(e.message, 'error'); }
}

function showGitCommitModal() {
  showModal(`
    <div class="modal-header">
      <h3>Commit des configurations</h3>
      <button class="btn-icon" onclick="closeModal()">&times;</button>
    </div>
    <p style="font-size:0.8rem;color:var(--text-secondary);margin-bottom:1rem">Stage automatiquement Configs/ et prompts/</p>
    <div class="form-group">
      <label>Message de commit</label>
      <input id="git-commit-msg" placeholder="Mise a jour configuration agents" />
    </div>
    <div class="modal-actions">
      <button class="btn btn-outline" onclick="closeModal()">Annuler</button>
      <button class="btn btn-success" onclick="gitCommit()">Commit</button>
    </div>
  `);
}

async function gitCommit() {
  const msg = document.getElementById('git-commit-msg').value.trim();
  if (!msg) { toast('Message requis', 'error'); return; }
  try {
    const data = await api('/api/git/commit', { method: 'POST', body: { message: msg } });
    toast(data.code === 0 ? 'Commit effectue' : (data.stderr || 'Erreur commit'), data.code === 0 ? 'success' : 'error');
    closeModal();
    loadGit();
  } catch (e) { toast(e.message, 'error'); }
}

// ═══════════════════════════════════════════════════
// INIT
// ═══════════════════════════════════════════════════
document.addEventListener('DOMContentLoaded', () => {
  loadEnv();
});

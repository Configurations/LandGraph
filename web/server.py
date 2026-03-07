"""LandGraph Admin — FastAPI backend."""
import csv
import hashlib
import hmac
import io
import json
import logging
import os
import secrets
import subprocess
import asyncio
from pathlib import Path
from fastapi import FastAPI, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, Response
from pydantic import BaseModel
from dotenv import load_dotenv
import httpx

# In Docker: /project is the host's langgraph-project dir
# Local dev: use parent of web/
DOCKER_MODE = Path("/project").exists()

if DOCKER_MODE:
    PROJECT_DIR = Path("/project")
    CONFIGS = PROJECT_DIR / "config"
    PROMPTS = PROJECT_DIR / "prompts" / "v1"
    SCRIPTS = PROJECT_DIR
    ENV_FILE = PROJECT_DIR / ".env"
    GIT_DIR = PROJECT_DIR
else:
    ROOT = Path(__file__).resolve().parent.parent
    PROJECT_DIR = ROOT / "langgraph-project"
    CONFIGS = ROOT / "Configs"
    PROMPTS = ROOT / "prompts" / "v1"
    SCRIPTS = ROOT / "scripts"
    ENV_FILE = PROJECT_DIR / ".env" if PROJECT_DIR.exists() else ROOT / ".env"
    GIT_DIR = ROOT

load_dotenv(ENV_FILE, override=False)

MCP_SERVERS_FILE = CONFIGS / "mcp_servers.json"
MCP_ACCESS_FILE = CONFIGS / "agent_mcp_access.json"
MCP_CATALOG_FILE = SCRIPTS / "Infra" / "mcp_catalog.csv" if not DOCKER_MODE else CONFIGS / "mcp_catalog.csv"
AGENTS_FILE = CONFIGS / "agents_registry.json"
LLM_PROVIDERS_FILE = CONFIGS / "llm_providers.json"
TEAMS_FILE = CONFIGS / "teams.json"
GIT_CONFIG_FILE = CONFIGS / "git.json"

logging.basicConfig(
    level=logging.DEBUG if os.environ.get("DEBUG") else logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("landgraph-admin")

log.info("DOCKER_MODE=%s  ENV_FILE=%s  CONFIGS=%s  PROMPTS=%s", DOCKER_MODE, ENV_FILE, CONFIGS, PROMPTS)

app = FastAPI(title="LandGraph Admin")
_AUTH_SECRET = secrets.token_hex(32)  # session signing key (regenerated on restart)

# ── Auth ───────────────────────────────────────────

def _get_auth_credentials() -> tuple[str, str] | None:
    """Read admin credentials from .env or environment."""
    env_vars = {e["key"]: e["value"] for e in _parse_env(ENV_FILE) if e.get("key")}
    username = env_vars.get("WEB_ADMIN_USERNAME") or os.environ.get("WEB_ADMIN_USERNAME", "")
    password = env_vars.get("WEB_ADMIN_PASSWORD") or os.environ.get("WEB_ADMIN_PASSWORD", "")
    if username and password:
        return (username, password)
    return None


def _make_session_token(username: str) -> str:
    sig = hmac.new(_AUTH_SECRET.encode(), username.encode(), hashlib.sha256).hexdigest()
    return f"{username}:{sig}"


def _verify_session_token(token: str) -> bool:
    if ":" not in token:
        return False
    username, sig = token.split(":", 1)
    expected = hmac.new(_AUTH_SECRET.encode(), username.encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(sig, expected)


_LOGIN_PAGE = """<!DOCTYPE html>
<html lang="fr">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>LandGraph — Connexion</title>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
  <style>
    *{margin:0;padding:0;box-sizing:border-box}
    body{font-family:'Inter',sans-serif;background:#0f1117;color:#e4e4e7;display:flex;align-items:center;justify-content:center;min-height:100vh}
    .login-card{background:#1a1b23;border:1px solid #2a2b35;border-radius:12px;padding:2.5rem;width:100%;max-width:380px;box-shadow:0 8px 32px rgba(0,0,0,0.4)}
    .login-logo{text-align:center;margin-bottom:2rem}
    .login-logo h1{font-size:1.5rem;font-weight:700;background:linear-gradient(135deg,#818cf8,#6366f1);-webkit-background-clip:text;-webkit-text-fill-color:transparent}
    .login-logo span{display:block;font-size:0.8rem;color:#71717a;margin-top:0.25rem}
    .form-group{margin-bottom:1.25rem}
    .form-group label{display:block;font-size:0.8rem;font-weight:500;color:#a1a1aa;margin-bottom:0.4rem}
    .form-group input{width:100%;padding:0.6rem 0.75rem;background:#12131a;border:1px solid #2a2b35;border-radius:8px;color:#e4e4e7;font-size:0.9rem;font-family:inherit;outline:none;transition:border-color 0.2s}
    .form-group input:focus{border-color:#6366f1}
    .btn-login{width:100%;padding:0.65rem;background:linear-gradient(135deg,#6366f1,#818cf8);color:#fff;border:none;border-radius:8px;font-size:0.9rem;font-weight:600;font-family:inherit;cursor:pointer;transition:opacity 0.2s}
    .btn-login:hover{opacity:0.9}
    .error-msg{background:#371520;border:1px solid #5c1d33;color:#f87171;padding:0.5rem 0.75rem;border-radius:8px;font-size:0.8rem;margin-bottom:1rem;display:none}
  </style>
</head>
<body>
  <div class="login-card">
    <div class="login-logo">
      <h1>LandGraph</h1>
      <span>Administration</span>
    </div>
    <div class="error-msg" id="error-msg">Identifiants incorrects</div>
    <form onsubmit="return doLogin(event)">
      <div class="form-group">
        <label>Utilisateur</label>
        <input type="text" id="username" autocomplete="username" autofocus required>
      </div>
      <div class="form-group">
        <label>Mot de passe</label>
        <input type="password" id="password" autocomplete="current-password" required>
      </div>
      <button type="submit" class="btn-login">Se connecter</button>
    </form>
  </div>
  <script>
    async function doLogin(e) {
      e.preventDefault();
      document.getElementById('error-msg').style.display = 'none';
      const res = await fetch('/auth/login', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
          username: document.getElementById('username').value,
          password: document.getElementById('password').value
        })
      });
      if (res.ok) { window.location.href = '/'; }
      else { document.getElementById('error-msg').style.display = 'block'; }
    }
  </script>
</body>
</html>"""


# ── Static files ───────────────────────────────────
app.mount("/static", StaticFiles(directory=Path(__file__).parent / "static"), name="static")


@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    """Cookie-based auth + request logging."""
    log.debug("%s %s", request.method, request.url.path)
    creds = _get_auth_credentials()
    if creds is not None:
        path = request.url.path
        # Allow login routes and static assets for login page (fonts)
        if path in ("/auth/login", "/auth/logout"):
            return await call_next(request)
        token = request.cookies.get("lg_session", "")
        if not _verify_session_token(token):
            log.debug("Auth refused: %s %s", request.method, path)
            if path.startswith("/api/"):
                return Response(
                    content='{"detail":"Non authentifie"}',
                    status_code=401,
                    media_type="application/json",
                )
            return HTMLResponse(_LOGIN_PAGE, status_code=401)
    return await call_next(request)


class _LoginRequest(BaseModel):
    username: str
    password: str


@app.post("/auth/login")
async def auth_login(req: _LoginRequest):
    creds = _get_auth_credentials()
    if creds is None:
        return {"ok": True}
    if not (secrets.compare_digest(req.username.encode(), creds[0].encode())
            and secrets.compare_digest(req.password.encode(), creds[1].encode())):
        log.warning("Login failed for user '%s'", req.username)
        raise HTTPException(status_code=401, detail="Identifiants incorrects")
    log.info("Login success for user '%s'", req.username)
    token = _make_session_token(req.username)
    response = Response(content='{"ok":true}', media_type="application/json")
    response.set_cookie("lg_session", token, httponly=True, samesite="lax", max_age=86400 * 7)
    return response


@app.get("/auth/logout")
async def auth_logout():
    response = RedirectResponse("/", status_code=302)
    response.delete_cookie("lg_session")
    return response


@app.get("/")
async def index():
    return FileResponse(Path(__file__).parent / "static" / "index.html")


# ── Helpers ─────────────────────────────────────────

def _read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    content = path.read_text(encoding="utf-8").strip()
    if not content:
        return {}
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        return {}


def _write_json(path: Path, data: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _parse_env(path: Path) -> list[dict]:
    """Parse .env file into list of {key, value, comment}."""
    entries = []
    if not path.exists():
        return entries
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            entries.append({"key": "", "value": "", "comment": stripped})
            continue
        if "=" in stripped:
            k, v = stripped.split("=", 1)
            entries.append({"key": k.strip(), "value": v.strip(), "comment": ""})
        else:
            entries.append({"key": "", "value": "", "comment": stripped})
    return entries


def _write_env(path: Path, entries: list[dict]):
    lines = []
    for e in entries:
        if e.get("key"):
            lines.append(f"{e['key']}={e['value']}")
        else:
            lines.append(e.get("comment", ""))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _parse_mcp_catalog() -> list[dict]:
    """Parse mcp_catalog.csv."""
    items = []
    if not MCP_CATALOG_FILE.exists():
        return items
    for line in MCP_CATALOG_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split("|")
        if len(parts) >= 7:
            env_vars = []
            if len(parts) > 7 and parts[7].strip():
                for ev in parts[7].split(","):
                    kv = ev.split(":", 1)
                    env_vars.append({"var": kv[0].strip(), "desc": kv[1].strip() if len(kv) > 1 else ""})
            items.append({
                "deprecated": parts[0].strip() == "1",
                "id": parts[1].strip(),
                "label": parts[2].strip(),
                "description": parts[3].strip(),
                "command": parts[4].strip(),
                "args": parts[5].strip(),
                "transport": parts[6].strip(),
                "env_vars": env_vars,
            })
    return items


# ── API: Secrets (.env) ────────────────────────────

@app.get("/api/env")
async def get_env():
    return {"entries": _parse_env(ENV_FILE), "path": str(ENV_FILE)}


@app.get("/api/env/path")
async def get_env_path():
    """Return the current .env path and whether it exists."""
    return {"path": str(ENV_FILE), "exists": ENV_FILE.exists()}


class EnvUpdate(BaseModel):
    entries: list[dict]


@app.put("/api/env")
async def update_env(data: EnvUpdate):
    if not ENV_FILE.parent.exists():
        raise HTTPException(404, f"Directory {ENV_FILE.parent} not found")
    _write_env(ENV_FILE, data.entries)
    return {"ok": True}


class EnvEntry(BaseModel):
    key: str
    value: str
    section_comment: str = ""


@app.post("/api/env/add")
async def add_env_entry(entry: EnvEntry):
    entries = _parse_env(ENV_FILE)
    # Check duplicate
    for e in entries:
        if e["key"] == entry.key:
            raise HTTPException(409, f"Key {entry.key} already exists")
    if entry.section_comment:
        entries.append({"key": "", "value": "", "comment": entry.section_comment})
    entries.append({"key": entry.key, "value": entry.value, "comment": ""})
    _write_env(ENV_FILE, entries)
    return {"ok": True}


class EnvDelete(BaseModel):
    key: str


@app.post("/api/env/delete")
async def delete_env_entry(data: EnvDelete):
    entries = _parse_env(ENV_FILE)
    entries = [e for e in entries if e.get("key") != data.key]
    _write_env(ENV_FILE, entries)
    return {"ok": True}


# ── MCP helpers ────────────────────────────────────

def _write_mcp_catalog(items: list[dict]):
    """Write catalog back to CSV, preserving header comments."""
    lines = []
    if MCP_CATALOG_FILE.exists():
        for line in MCP_CATALOG_FILE.read_text(encoding="utf-8").splitlines():
            if line.strip().startswith("#") or not line.strip():
                lines.append(line)
            else:
                break
    for item in items:
        env_str = ",".join(
            f"{v['var']}:{v['desc']}" for v in item.get("env_vars", [])
        )
        dep = "1" if item.get("deprecated") else "0"
        lines.append(
            f"{dep}|{item['id']}|{item['label']}|{item['description']}"
            f"|{item['command']}|{item['args']}|{item['transport']}|{env_str}"
        )
    MCP_CATALOG_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _get_mcp_full() -> list[dict]:
    """Return catalog entries enriched with install status and agent access."""
    catalog = _parse_mcp_catalog()
    servers = _read_json(MCP_SERVERS_FILE).get("servers", {})
    access = _read_json(MCP_ACCESS_FILE)
    env_entries = {e["key"]: e["value"] for e in _parse_env(ENV_FILE) if e.get("key")}

    for item in catalog:
        srv = servers.get(item["id"])
        item["installed"] = srv is not None
        item["enabled"] = srv.get("enabled", True) if srv else False
        item["agents"] = [
            aid for aid, sids in access.items() if item["id"] in sids
        ]
        for ev in item.get("env_vars", []):
            val = env_entries.get(ev["var"], "")
            ev["configured"] = bool(val) and val != "A_CONFIGURER"
    return catalog


# ── API: MCP Catalog (pivot central) ──────────────

@app.get("/api/mcp/catalog")
async def get_mcp_catalog():
    return {"servers": _get_mcp_full()}


class MCPCatalogEntry(BaseModel):
    id: str
    label: str
    description: str
    command: str
    args: str
    transport: str = "stdio"
    env_vars: list[dict] = []
    deprecated: bool = False


@app.post("/api/mcp/catalog")
async def add_catalog_entry(entry: MCPCatalogEntry):
    catalog = _parse_mcp_catalog()
    if any(c["id"] == entry.id for c in catalog):
        raise HTTPException(409, f"ID '{entry.id}' existe deja dans le catalogue")
    catalog.append(entry.model_dump())
    _write_mcp_catalog(catalog)
    return {"ok": True}


@app.put("/api/mcp/catalog/{entry_id}")
async def update_catalog_entry(entry_id: str, entry: MCPCatalogEntry):
    catalog = _parse_mcp_catalog()
    found = False
    for i, c in enumerate(catalog):
        if c["id"] == entry_id:
            catalog[i] = entry.model_dump()
            found = True
            break
    if not found:
        raise HTTPException(404, f"ID '{entry_id}' introuvable")
    _write_mcp_catalog(catalog)
    return {"ok": True}


@app.delete("/api/mcp/catalog/{entry_id}")
async def delete_catalog_entry(entry_id: str):
    catalog = _parse_mcp_catalog()
    catalog = [c for c in catalog if c["id"] != entry_id]
    _write_mcp_catalog(catalog)
    # Also uninstall
    data = _read_json(MCP_SERVERS_FILE)
    if entry_id in data.get("servers", {}):
        del data["servers"][entry_id]
        _write_json(MCP_SERVERS_FILE, data)
    access = _read_json(MCP_ACCESS_FILE)
    changed = False
    for aid in access:
        if entry_id in access[aid]:
            access[aid].remove(entry_id)
            changed = True
    if changed:
        _write_json(MCP_ACCESS_FILE, access)
    return {"ok": True}


# ── API: MCP Install / Uninstall ──────────────────

class MCPInstallRequest(BaseModel):
    env_values: dict = {}
    env_mapping: dict = {}


@app.post("/api/mcp/install/{entry_id}")
async def install_mcp(entry_id: str, req: MCPInstallRequest):
    catalog = _parse_mcp_catalog()
    item = next((c for c in catalog if c["id"] == entry_id), None)
    if not item:
        raise HTTPException(404, f"ID '{entry_id}' introuvable dans le catalogue")

    # Add to mcp_servers.json
    data = _read_json(MCP_SERVERS_FILE)
    if "servers" not in data:
        data["servers"] = {}
    if req.env_mapping:
        env_map = req.env_mapping
    else:
        env_map = {ev["var"]: ev["var"] for ev in item.get("env_vars", [])}
    data["servers"][entry_id] = {
        "command": item["command"],
        "args": item["args"].split() if isinstance(item["args"], str) else item["args"],
        "transport": item.get("transport", "stdio"),
        "env": env_map,
        "enabled": True,
    }
    _write_json(MCP_SERVERS_FILE, data)

    # Add env vars to .env if provided
    if req.env_values:
        entries = _parse_env(ENV_FILE)
        existing_keys = {e["key"] for e in entries if e.get("key")}
        new_vars = []
        for k, v in req.env_values.items():
            if k in existing_keys:
                entries = [
                    {**e, "value": v} if e.get("key") == k else e
                    for e in entries
                ]
            else:
                new_vars.append({"key": k, "value": v, "comment": ""})
        if new_vars:
            entries.append({"key": "", "value": "", "comment": f"# -- MCP {entry_id} --"})
            entries.extend(new_vars)
        _write_env(ENV_FILE, entries)

    return {"ok": True}


@app.post("/api/mcp/uninstall/{entry_id}")
async def uninstall_mcp(entry_id: str):
    data = _read_json(MCP_SERVERS_FILE)
    if entry_id in data.get("servers", {}):
        del data["servers"][entry_id]
        _write_json(MCP_SERVERS_FILE, data)
    access = _read_json(MCP_ACCESS_FILE)
    changed = False
    for aid in access:
        if entry_id in access[aid]:
            access[aid].remove(entry_id)
            changed = True
    if changed:
        _write_json(MCP_ACCESS_FILE, access)
    return {"ok": True}


# ── API: MCP Toggle enable/disable ────────────────

class MCPToggle(BaseModel):
    enabled: bool


@app.put("/api/mcp/toggle/{entry_id}")
async def toggle_mcp(entry_id: str, req: MCPToggle):
    data = _read_json(MCP_SERVERS_FILE)
    if entry_id not in data.get("servers", {}):
        raise HTTPException(404, f"Serveur '{entry_id}' non installe")
    data["servers"][entry_id]["enabled"] = req.enabled
    _write_json(MCP_SERVERS_FILE, data)
    return {"ok": True}


# ── API: MCP Access per agent ──────────────────────

@app.get("/api/mcp/access")
async def get_mcp_access():
    return _read_json(MCP_ACCESS_FILE)


@app.get("/api/mcp/servers")
async def get_mcp_servers():
    data = _read_json(MCP_SERVERS_FILE)
    return {"servers": data.get("servers", {})}


class MCPAccessUpdate(BaseModel):
    agent_id: str
    servers: list[str]


@app.put("/api/mcp/access")
async def update_mcp_access(data: MCPAccessUpdate):
    access = _read_json(MCP_ACCESS_FILE)
    access[data.agent_id] = data.servers
    _write_json(MCP_ACCESS_FILE, access)
    return {"ok": True}


# ── API: Agents ────────────────────────────────────

@app.get("/api/agents")
async def get_agents():
    teams_data = _read_json(TEAMS_FILE)
    teams = teams_data.get("teams", {})
    # Fallback: if no teams configured, use the default AGENTS_FILE
    if not teams:
        teams = {"default": {"name": "Equipe par defaut", "agents_registry": AGENTS_FILE.name, "prompts_dir": PROMPTS.name}}
    groups = []
    for tid, tcfg in teams.items():
        registry_file = CONFIGS / tcfg.get("agents_registry", "agents_registry.json")
        prompts_dir = PROMPTS.parent / tcfg.get("prompts_dir", "v1")
        data = _read_json(registry_file)
        agents = data.get("agents", {})
        result = {}
        for aid, acfg in agents.items():
            prompt_file = prompts_dir / acfg.get("prompt", f"{aid}.md")
            prompt_content = ""
            if prompt_file.exists():
                prompt_content = prompt_file.read_text(encoding="utf-8")
            result[aid] = {**acfg, "prompt_content": prompt_content}
        groups.append({
            "team_id": tid,
            "team_name": tcfg.get("name", tid),
            "registry": tcfg.get("agents_registry", "agents_registry.json"),
            "prompts_dir": tcfg.get("prompts_dir", "v1"),
            "agents": result,
        })
    return {"groups": groups}


class AgentConfig(BaseModel):
    id: str
    name: str
    temperature: float = 0.2
    max_tokens: int = 32768
    prompt_file: str = ""
    prompt_content: str = ""
    model: str = ""
    type: str = ""
    pipeline_steps: list = []
    registry: str = "agents_registry.json"
    prompts_dir: str = "v1"


def _resolve_agent_paths(cfg_or_registry: str, prompts_dir: str = "v1"):
    registry_path = CONFIGS / cfg_or_registry
    prompts_path = PROMPTS.parent / prompts_dir
    return registry_path, prompts_path


@app.post("/api/agents")
async def add_agent(cfg: AgentConfig):
    registry_path, prompts_path = _resolve_agent_paths(cfg.registry, cfg.prompts_dir)
    data = _read_json(registry_path)
    if "agents" not in data:
        data["agents"] = {}
    if cfg.id in data["agents"]:
        raise HTTPException(409, f"Agent {cfg.id} already exists")

    prompt_file = cfg.prompt_file or f"{cfg.id}.md"
    agent_data = {
        "name": cfg.name,
        "temperature": cfg.temperature,
        "max_tokens": cfg.max_tokens,
        "prompt": prompt_file,
    }
    if cfg.model:
        agent_data["model"] = cfg.model
    if cfg.type:
        agent_data["type"] = cfg.type
    if cfg.pipeline_steps:
        agent_data["pipeline_steps"] = cfg.pipeline_steps

    data["agents"][cfg.id] = agent_data
    _write_json(registry_path, data)

    # Create prompt file
    prompts_path.mkdir(parents=True, exist_ok=True)
    prompt_path = prompts_path / prompt_file
    if not prompt_path.exists():
        prompt_path.write_text(cfg.prompt_content or f"# {cfg.name}\n\n", encoding="utf-8")

    return {"ok": True}


@app.put("/api/agents/{agent_id}")
async def update_agent(agent_id: str, cfg: AgentConfig):
    registry_path, prompts_path = _resolve_agent_paths(cfg.registry, cfg.prompts_dir)
    data = _read_json(registry_path)
    if agent_id not in data.get("agents", {}):
        raise HTTPException(404, f"Agent {agent_id} not found")

    existing = data["agents"][agent_id]
    existing["name"] = cfg.name
    existing["temperature"] = cfg.temperature
    existing["max_tokens"] = cfg.max_tokens
    if cfg.model:
        existing["model"] = cfg.model
    elif "model" in existing:
        del existing["model"]
    if cfg.type:
        existing["type"] = cfg.type
    if cfg.pipeline_steps:
        existing["pipeline_steps"] = cfg.pipeline_steps
    elif "pipeline_steps" in existing:
        del existing["pipeline_steps"]

    data["agents"][agent_id] = existing
    _write_json(registry_path, data)

    # Update prompt
    if cfg.prompt_content is not None:
        prompt_path = prompts_path / existing.get("prompt", f"{agent_id}.md")
        prompt_path.write_text(cfg.prompt_content, encoding="utf-8")

    return {"ok": True}


@app.delete("/api/agents/{agent_id}")
async def delete_agent(agent_id: str, registry: str = "agents_registry.json"):
    registry_path = CONFIGS / registry
    data = _read_json(registry_path)
    if agent_id not in data.get("agents", {}):
        raise HTTPException(404, f"Agent {agent_id} not found")
    del data["agents"][agent_id]
    _write_json(registry_path, data)
    return {"ok": True}


# ── API: LLM Providers ────────────────────────────

@app.get("/api/llm/providers")
async def get_llm_providers():
    return _read_json(LLM_PROVIDERS_FILE)


class LLMProviderEntry(BaseModel):
    id: str
    type: str
    model: str
    env_key: str = ""
    description: str = ""
    base_url: str = ""
    azure_endpoint: str = ""
    azure_deployment: str = ""
    api_version: str = ""


@app.post("/api/llm/providers/provider")
async def add_llm_provider(entry: LLMProviderEntry):
    data = _read_json(LLM_PROVIDERS_FILE)
    if "providers" not in data:
        data["providers"] = {}
    if entry.id in data["providers"]:
        raise HTTPException(409, f"Provider '{entry.id}' existe deja")
    prov = {"type": entry.type, "model": entry.model, "description": entry.description}
    if entry.env_key:
        prov["env_key"] = entry.env_key
    if entry.base_url:
        prov["base_url"] = entry.base_url
    if entry.type == "azure":
        if entry.azure_endpoint:
            prov["azure_endpoint"] = entry.azure_endpoint
        if entry.azure_deployment:
            prov["azure_deployment"] = entry.azure_deployment
        if entry.api_version:
            prov["api_version"] = entry.api_version
    data["providers"][entry.id] = prov
    _write_json(LLM_PROVIDERS_FILE, data)
    return {"ok": True}


@app.put("/api/llm/providers/provider/{provider_id}")
async def update_llm_provider(provider_id: str, entry: LLMProviderEntry):
    data = _read_json(LLM_PROVIDERS_FILE)
    if provider_id not in data.get("providers", {}):
        raise HTTPException(404, f"Provider '{provider_id}' introuvable")
    prov = {"type": entry.type, "model": entry.model, "description": entry.description}
    if entry.env_key:
        prov["env_key"] = entry.env_key
    if entry.base_url:
        prov["base_url"] = entry.base_url
    if entry.type == "azure":
        if entry.azure_endpoint:
            prov["azure_endpoint"] = entry.azure_endpoint
        if entry.azure_deployment:
            prov["azure_deployment"] = entry.azure_deployment
        if entry.api_version:
            prov["api_version"] = entry.api_version
    # If ID changed, remove old and add new
    if entry.id != provider_id:
        del data["providers"][provider_id]
        if data.get("default") == provider_id:
            data["default"] = entry.id
    data["providers"][entry.id] = prov
    _write_json(LLM_PROVIDERS_FILE, data)
    return {"ok": True}


@app.delete("/api/llm/providers/provider/{provider_id}")
async def delete_llm_provider(provider_id: str):
    data = _read_json(LLM_PROVIDERS_FILE)
    if provider_id not in data.get("providers", {}):
        raise HTTPException(404, f"Provider '{provider_id}' introuvable")
    del data["providers"][provider_id]
    if data.get("default") == provider_id:
        data["default"] = ""
    _write_json(LLM_PROVIDERS_FILE, data)
    return {"ok": True}


class LLMDefaultUpdate(BaseModel):
    provider_id: str


@app.put("/api/llm/providers/default")
async def set_llm_default(req: LLMDefaultUpdate):
    data = _read_json(LLM_PROVIDERS_FILE)
    if req.provider_id and req.provider_id not in data.get("providers", {}):
        raise HTTPException(404, f"Provider '{req.provider_id}' introuvable")
    data["default"] = req.provider_id
    _write_json(LLM_PROVIDERS_FILE, data)
    return {"ok": True}


class ThrottlingEntry(BaseModel):
    env_key: str
    rpm: int
    tpm: int


@app.put("/api/llm/providers/throttling")
async def update_throttling(entry: ThrottlingEntry):
    data = _read_json(LLM_PROVIDERS_FILE)
    if "throttling" not in data:
        data["throttling"] = {}
    data["throttling"][entry.env_key] = {"rpm": entry.rpm, "tpm": entry.tpm}
    _write_json(LLM_PROVIDERS_FILE, data)
    return {"ok": True}


@app.delete("/api/llm/providers/throttling/{env_key}")
async def delete_throttling(env_key: str):
    data = _read_json(LLM_PROVIDERS_FILE)
    if env_key in data.get("throttling", {}):
        del data["throttling"][env_key]
        _write_json(LLM_PROVIDERS_FILE, data)
    return {"ok": True}


# ── API: Chat LLM ─────────────────────────────────

# Default base URLs per provider type
_LLM_BASE_URLS = {
    "anthropic": "https://api.anthropic.com",
    "openai": "https://api.openai.com",
    "mistral": "https://api.mistral.ai",
    "deepseek": "https://api.deepseek.com",
    "groq": "https://api.groq.com/openai",
    "moonshot": "https://api.moonshot.cn",
    "ollama": "http://localhost:11434",
}


class ChatRequest(BaseModel):
    messages: list[dict]


@app.post("/api/chat")
async def chat(req: ChatRequest):
    data = _read_json(LLM_PROVIDERS_FILE)
    default_id = data.get("default", "")
    if not default_id or default_id not in data.get("providers", {}):
        raise HTTPException(400, "Aucun provider LLM par defaut configure")

    provider = data["providers"][default_id]
    ptype = provider["type"]
    model = provider["model"]
    env_key = provider.get("env_key", "")
    base_url = provider.get("base_url", "")

    # Resolve API key from .env or environment
    api_key = ""
    if env_key:
        env_entries = {e["key"]: e["value"] for e in _parse_env(ENV_FILE) if e.get("key")}
        api_key = env_entries.get(env_key, "") or os.environ.get(env_key, "")

    messages = req.messages

    try:
        async with httpx.AsyncClient(timeout=120) as client:
            if ptype == "anthropic":
                url = f"{base_url or _LLM_BASE_URLS['anthropic']}/v1/messages"
                system_msg = ""
                chat_msgs = []
                for m in messages:
                    if m["role"] == "system":
                        system_msg = m["content"]
                    else:
                        chat_msgs.append({"role": m["role"], "content": m["content"]})
                body = {"model": model, "max_tokens": 4096, "messages": chat_msgs}
                if system_msg:
                    body["system"] = system_msg
                resp = await client.post(
                    url,
                    headers={
                        "x-api-key": api_key,
                        "anthropic-version": "2023-06-01",
                        "content-type": "application/json",
                    },
                    json=body,
                )
                resp.raise_for_status()
                result = resp.json()
                content = result["content"][0]["text"] if result.get("content") else ""
                return {"role": "assistant", "content": content}

            elif ptype == "google":
                url = (
                    f"{base_url or 'https://generativelanguage.googleapis.com'}"
                    f"/v1beta/models/{model}:generateContent?key={api_key}"
                )
                contents = []
                for m in messages:
                    role = "user" if m["role"] == "user" else "model"
                    contents.append({"role": role, "parts": [{"text": m["content"]}]})
                resp = await client.post(
                    url,
                    json={"contents": contents},
                    headers={"content-type": "application/json"},
                )
                resp.raise_for_status()
                result = resp.json()
                content = (
                    result.get("candidates", [{}])[0]
                    .get("content", {})
                    .get("parts", [{}])[0]
                    .get("text", "")
                )
                return {"role": "assistant", "content": content}

            elif ptype == "azure":
                endpoint = provider.get("azure_endpoint", "").rstrip("/")
                deployment = provider.get("azure_deployment", "")
                api_version = provider.get("api_version", "2024-12-01-preview")
                url = f"{endpoint}/openai/deployments/{deployment}/chat/completions?api-version={api_version}"
                headers = {"api-key": api_key, "content-type": "application/json"}
                body = {"model": model, "messages": messages, "max_tokens": 4096}
                resp = await client.post(url, headers=headers, json=body)
                resp.raise_for_status()
                result = resp.json()
                content = result["choices"][0]["message"]["content"]
                return {"role": "assistant", "content": content}

            else:
                # OpenAI-compatible: openai, mistral, deepseek, groq, moonshot, ollama
                default_base = _LLM_BASE_URLS.get(ptype, "https://api.openai.com")
                url = f"{base_url or default_base}/v1/chat/completions"
                headers = {"content-type": "application/json"}
                if api_key:
                    headers["Authorization"] = f"Bearer {api_key}"
                body = {"model": model, "messages": messages, "max_tokens": 4096}
                resp = await client.post(url, headers=headers, json=body)
                resp.raise_for_status()
                result = resp.json()
                content = result["choices"][0]["message"]["content"]
                return {"role": "assistant", "content": content}

    except httpx.HTTPStatusError as e:
        error_body = e.response.text[:500]
        raise HTTPException(e.response.status_code, f"Erreur LLM: {error_body}")
    except httpx.ConnectError:
        raise HTTPException(502, "Impossible de se connecter au provider LLM")
    except Exception as e:
        raise HTTPException(500, f"Erreur: {str(e)}")


# ── API: Teams ────────────────────────────────────

@app.get("/api/teams")
async def get_teams():
    data = _read_json(TEAMS_FILE)
    return {
        "teams": data.get("teams", {}),
        "channel_mapping": data.get("channel_mapping", {}),
    }


class TeamEntry(BaseModel):
    name: str
    description: str = ""
    agents_registry: str = "agents_registry.json"
    llm_providers: str = "llm_providers.json"
    prompts_dir: str = "v1"
    mcp_access: str = "agent_mcp_access.json"
    discord_channels: list[str] = []


def _ensure_team_config_files(entry: TeamEntry):
    """Create referenced config files and prompts dir if they don't exist."""
    defaults = {
        entry.agents_registry: {"agents": {}},
        entry.llm_providers: {"providers": {}, "throttling": {}, "default": ""},
        entry.mcp_access: {},
    }
    for filename, skeleton in defaults.items():
        path = CONFIGS / filename
        if not path.exists():
            log.info("Creating missing config file: %s", path)
            _write_json(path, skeleton)
    prompts_path = PROMPTS.parent / entry.prompts_dir
    if not prompts_path.exists():
        log.info("Creating missing prompts dir: %s", prompts_path)
        prompts_path.mkdir(parents=True, exist_ok=True)


@app.post("/api/teams/{team_id}")
async def add_team(team_id: str, entry: TeamEntry):
    data = _read_json(TEAMS_FILE)
    teams = data.setdefault("teams", {})
    if team_id in teams:
        raise HTTPException(409, f"L'equipe '{team_id}' existe deja")
    teams[team_id] = entry.model_dump()
    _rebuild_channel_mapping(data)
    _ensure_team_config_files(entry)
    _write_json(TEAMS_FILE, data)
    return {"ok": True}


@app.put("/api/teams/{team_id}")
async def update_team(team_id: str, entry: TeamEntry):
    data = _read_json(TEAMS_FILE)
    teams = data.setdefault("teams", {})
    if team_id not in teams:
        raise HTTPException(404, f"Equipe '{team_id}' introuvable")
    teams[team_id] = entry.model_dump()
    _rebuild_channel_mapping(data)
    _ensure_team_config_files(entry)
    _write_json(TEAMS_FILE, data)
    return {"ok": True}


@app.delete("/api/teams/{team_id}")
async def delete_team(team_id: str):
    data = _read_json(TEAMS_FILE)
    teams = data.setdefault("teams", {})
    if team_id not in teams:
        raise HTTPException(404, f"Equipe '{team_id}' introuvable")
    if team_id == "default":
        raise HTTPException(400, "Impossible de supprimer l'equipe par defaut")
    del teams[team_id]
    _rebuild_channel_mapping(data)
    _write_json(TEAMS_FILE, data)
    return {"ok": True}


def _rebuild_channel_mapping(data: dict):
    """Rebuild channel_mapping from discord_channels in each team."""
    mapping = {}
    for tid, t in data.get("teams", {}).items():
        for ch in t.get("discord_channels", []):
            if ch:
                mapping[ch] = tid
    data["channel_mapping"] = mapping


def _ensure_gitignore():
    """Create .gitignore with default patterns if it doesn't exist."""
    gitignore = GIT_DIR / ".gitignore"
    if not gitignore.exists():
        log.info("Creating .gitignore in %s", GIT_DIR)
        gitignore.write_text("*.sh\n", encoding="utf-8")


# ── API: Git config ───────────────────────────────

@app.get("/api/git/config")
async def get_git_config():
    return _read_json(GIT_CONFIG_FILE)


class GitConfig(BaseModel):
    path: str = ""
    login: str = ""
    password: str = ""


@app.put("/api/git/config")
async def update_git_config(cfg: GitConfig):
    _write_json(GIT_CONFIG_FILE, cfg.model_dump())
    # Init git repo if not already initialized
    if not (GIT_DIR / ".git").exists():
        log.info("Initializing git repo in %s", GIT_DIR)
        subprocess.run(["git", "init"], cwd=str(GIT_DIR), capture_output=True, text=True, timeout=10)
        _ensure_gitignore()
    # Configure remote origin
    if cfg.path:
        login = cfg.login.strip()
        password = cfg.password.strip()
        if login and password:
            if "://" in cfg.path:
                scheme, rest = cfg.path.split("://", 1)
                remote_url = f"{scheme}://{login}:{password}@{rest}"
            else:
                remote_url = f"https://{login}:{password}@{cfg.path}"
        else:
            remote_url = cfg.path if "://" in cfg.path else f"https://{cfg.path}"
        # Remove existing origin then add
        subprocess.run(["git", "remote", "remove", "origin"], cwd=str(GIT_DIR), capture_output=True, text=True, timeout=5)
        subprocess.run(["git", "remote", "add", "origin", remote_url], cwd=str(GIT_DIR), capture_output=True, text=True, timeout=5)
        log.info("Git remote origin set to %s", cfg.path)
    return {"ok": True}


# ── API: Git operations ───────────────────────────

@app.get("/api/git/status")
async def git_status():
    try:
        initialized = (GIT_DIR / ".git").exists()
        if not initialized:
            return {"initialized": False, "status": "", "branch": "", "log": ""}
        result = subprocess.run(
            ["git", "status", "--short"],
            cwd=str(GIT_DIR), capture_output=True, text=True, timeout=10
        )
        branch = subprocess.run(
            ["git", "branch", "--show-current"],
            cwd=str(GIT_DIR), capture_output=True, text=True, timeout=10
        )
        log = subprocess.run(
            ["git", "log", "--oneline", "-10"],
            cwd=str(GIT_DIR), capture_output=True, text=True, timeout=10
        )
        return {
            "initialized": True,
            "status": result.stdout,
            "branch": branch.stdout.strip(),
            "log": log.stdout,
        }
    except Exception as e:
        raise HTTPException(500, str(e))


@app.post("/api/git/init")
async def git_init():
    """Initialize a git repo in GIT_DIR (git init + configure remote)."""
    log.info("Button pressed: Init Repository")
    try:
        git_dir = GIT_DIR / ".git"
        if git_dir.exists():
            return {"ok": True, "message": "Depot deja initialise"}
        log.info("git init in %s", GIT_DIR)
        subprocess.run(
            ["git", "config", "--global", "--add", "safe.directory", str(GIT_DIR)],
            capture_output=True, text=True, timeout=5,
        )
        result = subprocess.run(
            ["git", "init"],
            cwd=str(GIT_DIR), capture_output=True, text=True, timeout=10,
        )
        if result.returncode != 0:
            log.error("git init failed (code %d): %s", result.returncode, result.stderr)
            raise HTTPException(500, result.stderr)
        _ensure_gitignore()
        # Configure remote origin if git config exists
        cfg = _read_json(GIT_CONFIG_FILE)
        repo_path = cfg.get("path", "").strip()
        if repo_path:
            login = cfg.get("login", "").strip()
            password = cfg.get("password", "").strip()
            if login and password:
                if "://" in repo_path:
                    scheme, rest = repo_path.split("://", 1)
                    remote_url = f"{scheme}://{login}:{password}@{rest}"
                else:
                    remote_url = f"https://{login}:{password}@{repo_path}"
            else:
                remote_url = repo_path if "://" in repo_path else f"https://{repo_path}"
            subprocess.run(["git", "remote", "remove", "origin"], cwd=str(GIT_DIR), capture_output=True, text=True, timeout=5)
            subprocess.run(["git", "remote", "add", "origin", remote_url], cwd=str(GIT_DIR), capture_output=True, text=True, timeout=5)
            log.info("Git remote origin set to %s", repo_path)
        log.info("git init success")
        return {"ok": True, "message": "Depot initialise avec succes"}
    except HTTPException:
        raise
    except Exception as e:
        log.exception("git init exception")
        raise HTTPException(500, str(e))


@app.post("/api/git/pull")
async def git_pull():
    log.info("Button pressed: Pull")
    try:
        git_dir = GIT_DIR / ".git"
        if not git_dir.exists():
            # Clone into GIT_DIR using git config credentials
            cfg = _read_json(GIT_CONFIG_FILE)
            repo_path = cfg.get("path", "").strip()
            if not repo_path:
                raise HTTPException(400, "Chemin du depot non configure (Git > Depot distant)")
            login = cfg.get("login", "").strip()
            password = cfg.get("password", "").strip()
            if login and password:
                if "://" in repo_path:
                    scheme, rest = repo_path.split("://", 1)
                    clone_url = f"{scheme}://{login}:{password}@{rest}"
                else:
                    clone_url = f"https://{login}:{password}@{repo_path}"
            else:
                clone_url = repo_path if "://" in repo_path else f"https://{repo_path}"
            log.info("git pull: cloning %s into %s", repo_path, GIT_DIR)
            result = subprocess.run(
                ["git", "clone", clone_url, "."],
                cwd=str(GIT_DIR), capture_output=True, text=True, timeout=120,
                env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
            )
            _ensure_gitignore()
            if result.returncode != 0:
                log.error("git clone failed (code %d): %s", result.returncode, result.stderr)
            else:
                log.info("git clone success")
            return {"stdout": result.stdout, "stderr": result.stderr, "code": result.returncode}
        else:
            log.info("git pull in %s", GIT_DIR)
            result = subprocess.run(
                ["git", "pull"],
                cwd=str(GIT_DIR), capture_output=True, text=True, timeout=60
            )
            if result.returncode != 0:
                log.error("git pull failed (code %d): stdout=%s stderr=%s", result.returncode, result.stdout, result.stderr)
            else:
                log.info("git pull success: %s", result.stdout.strip())
            return {"stdout": result.stdout, "stderr": result.stderr, "code": result.returncode}
    except HTTPException:
        raise
    except Exception as e:
        log.exception("git pull exception")
        raise HTTPException(500, str(e))


class GitCommitRequest(BaseModel):
    message: str


@app.post("/api/git/commit")
async def git_commit(req: GitCommitRequest):
    """Stage all files in /project, commit and push."""
    log.info("Button pressed: Commit & Push")
    try:
        git_env = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}
        # Build remote URL with credentials for push
        cfg = _read_json(GIT_CONFIG_FILE)
        repo_path = cfg.get("path", "").strip()
        login = cfg.get("login", "").strip()
        password = cfg.get("password", "").strip()

        _ensure_gitignore()
        # Stage everything
        subprocess.run(
            ["git", "add", "-A"],
            cwd=str(GIT_DIR), capture_output=True, text=True, timeout=10
        )
        # Commit
        commit_result = subprocess.run(
            ["git", "commit", "-m", req.message],
            cwd=str(GIT_DIR), capture_output=True, text=True, timeout=30
        )
        if commit_result.returncode != 0:
            return {"stdout": commit_result.stdout, "stderr": commit_result.stderr, "code": commit_result.returncode}

        # Push
        if repo_path and login and password:
            if "://" in repo_path:
                scheme, rest = repo_path.split("://", 1)
                push_url = f"{scheme}://{login}:{password}@{rest}"
            else:
                push_url = f"https://{login}:{password}@{repo_path}"
            push_result = subprocess.run(
                ["git", "push", push_url],
                cwd=str(GIT_DIR), capture_output=True, text=True, timeout=60,
                env=git_env,
            )
        else:
            push_result = subprocess.run(
                ["git", "push"],
                cwd=str(GIT_DIR), capture_output=True, text=True, timeout=60,
                env=git_env,
            )
        return {"stdout": commit_result.stdout + "\n" + push_result.stdout,
                "stderr": push_result.stderr, "code": push_result.returncode}
    except Exception as e:
        raise HTTPException(500, str(e))


# ── API: Shell scripts ────────────────────────────

ALLOWED_SCRIPTS = {"start", "stop", "restart", "build"}


@app.get("/api/scripts")
async def list_scripts():
    """List available scripts."""
    scripts = []
    for name in ALLOWED_SCRIPTS:
        path = PROJECT_DIR / f"{name}.sh"
        if not path.exists():
            path = SCRIPTS / f"{name}.sh"
        scripts.append({"name": name, "exists": path.exists(), "path": str(path)})
    return {"scripts": scripts}


class ScriptRun(BaseModel):
    name: str


@app.post("/api/scripts/run")
async def run_script(req: ScriptRun):
    if req.name not in ALLOWED_SCRIPTS:
        raise HTTPException(400, f"Script '{req.name}' not allowed")

    # Look in project dir first, then scripts dir
    script_path = PROJECT_DIR / f"{req.name}.sh"
    if not script_path.exists() and not DOCKER_MODE:
        script_path = SCRIPTS / f"{req.name}.sh"
    if not script_path.exists():
        raise HTTPException(404, f"Script {req.name}.sh not found")

    try:
        result = subprocess.run(
            ["bash", str(script_path)],
            cwd=str(PROJECT_DIR),
            capture_output=True, text=True, timeout=180
        )
        return {"stdout": result.stdout, "stderr": result.stderr, "code": result.returncode}
    except subprocess.TimeoutExpired:
        return {"stdout": "", "stderr": "Timeout (180s)", "code": -1}
    except Exception as e:
        raise HTTPException(500, str(e))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)

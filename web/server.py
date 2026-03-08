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

# Fix git ownership issue in Docker (mounted volume has different owner)
if DOCKER_MODE:
    subprocess.run(
        ["git", "config", "--global", "--add", "safe.directory", "/project"],
        capture_output=True, timeout=5
    )
    subprocess.run(
        ["git", "config", "--global", "user.email", os.environ.get("GIT_USER_EMAIL", "admin@langgraph.local")],
        capture_output=True, timeout=5
    )
    subprocess.run(
        ["git", "config", "--global", "user.name", os.environ.get("GIT_USER_NAME", "LandGraph Admin")],
        capture_output=True, timeout=5
    )
    # Generate .gitignore if missing
    gitignore = Path("/project") / ".gitignore"
    if not gitignore.exists():
        gitignore.write_text(
            ".env\n*.key\n.venv/\n__pycache__/\n*.pyc\n"
            "data/backups/\n*.bak\n*.sh\n*.save\n*.example\n*.py\n",
            encoding="utf-8",
        )

if DOCKER_MODE:
    PROJECT_DIR = Path("/project")
    CONFIGS = PROJECT_DIR / "Configs"
    TEAMS_DIR = CONFIGS / "Teams"
    SHARED_DIR = PROJECT_DIR / "Shared"
    PROMPTS = TEAMS_DIR / "default"
    SCRIPTS = PROJECT_DIR
    ENV_FILE = PROJECT_DIR / ".env"
    GIT_DIR = PROJECT_DIR
else:
    ROOT = Path(__file__).resolve().parent.parent
    PROJECT_DIR = ROOT / "langgraph-project"
    CONFIGS = ROOT / "Configs"
    TEAMS_DIR = CONFIGS / "Teams"
    SHARED_DIR = ROOT / "Shared"
    PROMPTS = TEAMS_DIR / "default"
    SCRIPTS = ROOT / "scripts"
    ENV_FILE = PROJECT_DIR / ".env" if PROJECT_DIR.exists() else ROOT / ".env"
    GIT_DIR = ROOT

load_dotenv(ENV_FILE, override=False)

MCP_SERVERS_FILE = TEAMS_DIR / "mcp_servers.json"
MCP_ACCESS_FILE = TEAMS_DIR / "agent_mcp_access.json"
MCP_CATALOG_FILE = SCRIPTS / "Infra" / "mcp_catalog.csv" if not DOCKER_MODE else SHARED_DIR / "Teams" / "mcp_catalog.csv"
LLM_PROVIDERS_FILE = TEAMS_DIR / "llm_providers.json"
TEAMS_FILE = TEAMS_DIR / "teams.json"
GIT_CONFIG_FILE = TEAMS_DIR / "git.json"  # legacy dual-repo
SHARED_GIT_FILE = SHARED_DIR / "git.json"
CONFIGS_GIT_FILE = CONFIGS / "git.json"
SHARED_TEAMS_DIR = SHARED_DIR / "Teams"
SHARED_LLM_FILE = SHARED_TEAMS_DIR / "llm_providers.json"
SHARED_MCP_FILE = SHARED_TEAMS_DIR / "mcp_servers.json"
SHARED_TEAMS_FILE = SHARED_TEAMS_DIR / "teams.json"

logging.basicConfig(
    level=logging.DEBUG if os.environ.get("DEBUG") else logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("landgraph-admin")

log.info("DOCKER_MODE=%s  ENV_FILE=%s  CONFIGS=%s  PROMPTS=%s", DOCKER_MODE, ENV_FILE, CONFIGS, PROMPTS)

app = FastAPI(title="LandGraph Admin")
_AUTH_SECRET = secrets.token_hex(32)  # session signing key (regenerated on restart)

# ── Restore MCP servers from Shared on startup ────
def _restore_mcp_from_shared():
    """If Configs mcp_servers.json is empty but Shared has data, restore it."""
    try:
        cfg = _read_json(MCP_SERVERS_FILE)
        if cfg.get("servers"):
            return  # already populated
        shared = _read_json(SHARED_MCP_FILE)
        if shared.get("servers"):
            _write_json(MCP_SERVERS_FILE, shared)
            logging.info("Restored mcp_servers.json from Shared (%d servers)", len(shared["servers"]))
    except Exception as e:
        logging.warning("restore mcp from shared failed: %s", e)

_restore_mcp_from_shared()

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


# ── Helper: sync MCP servers to Shared ────────────

def _sync_mcp_to_shared():
    """Mirror MCP_SERVERS_FILE → SHARED_MCP_FILE so installs survive git pulls on Configs."""
    try:
        data = _read_json(MCP_SERVERS_FILE)
        SHARED_MCP_FILE.parent.mkdir(parents=True, exist_ok=True)
        _write_json(SHARED_MCP_FILE, data)
    except Exception as e:
        logging.warning("sync mcp→shared failed: %s", e)


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
    _sync_mcp_to_shared()

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
        _sync_mcp_to_shared()
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
    _sync_mcp_to_shared()
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

def _team_dir(team_id: str) -> Path:
    """Return the team folder path: Configs/Teams/<team_id>/."""
    return TEAMS_DIR / team_id


@app.get("/api/agents")
async def get_agents():
    teams = _read_teams_list()
    if not teams:
        teams = [{"id": "default", "name": "Equipe par defaut", "directory": "default"}]
    groups = []
    for tcfg in teams:
        tid = tcfg.get("id", "default")
        directory = tcfg.get("directory", tid)
        tdir = _team_dir(directory)
        registry_file = tdir / "agents_registry.json"
        data = _read_json(registry_file)
        agents = data.get("agents", {})
        result = {}
        for aid, acfg in agents.items():
            prompt_file = tdir / acfg.get("prompt", f"{aid}.md")
            prompt_content = ""
            if prompt_file.exists():
                prompt_content = prompt_file.read_text(encoding="utf-8")
            result[aid] = {**acfg, "prompt_content": prompt_content}
        mcp_access = _read_json(tdir / "agent_mcp_access.json") if (tdir / "agent_mcp_access.json").exists() else {}
        groups.append({
            "team_id": tid,
            "team_name": tcfg.get("name", tid),
            "team_description": tcfg.get("description", ""),
            "team_dir": directory,
            "discord_channels": tcfg.get("discord_channels", []),
            "orchestrator": tcfg.get("orchestrator", ""),
            "agents": result,
            "mcp_access": mcp_access,
        })
    return {"groups": groups}


class AgentConfig(BaseModel):
    id: str
    name: str
    temperature: float = 0.2
    max_tokens: int = 32768
    prompt_file: str = ""
    prompt_content: str = ""
    llm: str = ""
    type: str = ""
    pipeline_steps: list = []
    team_id: str = "default"


@app.post("/api/agents")
async def add_agent(cfg: AgentConfig):
    tdir = _team_dir(cfg.team_id)
    tdir.mkdir(parents=True, exist_ok=True)
    registry_path = tdir / "agents_registry.json"
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
    if cfg.llm:
        agent_data["llm"] = cfg.llm
    if cfg.type:
        agent_data["type"] = cfg.type
    if cfg.pipeline_steps:
        agent_data["pipeline_steps"] = cfg.pipeline_steps

    data["agents"][cfg.id] = agent_data
    _write_json(registry_path, data)

    # Create prompt file in team folder
    prompt_path = tdir / prompt_file
    if not prompt_path.exists():
        prompt_path.write_text(cfg.prompt_content or f"# {cfg.name}\n\n", encoding="utf-8")

    return {"ok": True}


@app.put("/api/agents/{agent_id}")
async def update_agent(agent_id: str, cfg: AgentConfig):
    tdir = _team_dir(cfg.team_id)
    registry_path = tdir / "agents_registry.json"
    data = _read_json(registry_path)
    if agent_id not in data.get("agents", {}):
        raise HTTPException(404, f"Agent {agent_id} not found")

    existing = data["agents"][agent_id]
    existing["name"] = cfg.name
    existing["temperature"] = cfg.temperature
    existing["max_tokens"] = cfg.max_tokens
    if cfg.llm:
        existing["llm"] = cfg.llm
    elif "llm" in existing:
        del existing["llm"]
    # Clean legacy "model" field
    existing.pop("model", None)
    if cfg.type:
        existing["type"] = cfg.type
    if cfg.pipeline_steps:
        existing["pipeline_steps"] = cfg.pipeline_steps
    elif "pipeline_steps" in existing:
        del existing["pipeline_steps"]

    data["agents"][agent_id] = existing
    _write_json(registry_path, data)

    # Update prompt in team folder
    if cfg.prompt_content is not None:
        prompt_path = tdir / existing.get("prompt", f"{agent_id}.md")
        prompt_path.write_text(cfg.prompt_content, encoding="utf-8")

    return {"ok": True}


@app.delete("/api/agents/{agent_id}")
async def delete_agent(agent_id: str, team_id: str = "default"):
    tdir = _team_dir(team_id)
    registry_path = tdir / "agents_registry.json"
    data = _read_json(registry_path)
    if agent_id not in data.get("agents", {}):
        raise HTTPException(404, f"Agent {agent_id} not found")
    prompt_file = data["agents"][agent_id].get("prompt", f"{agent_id}.md")
    del data["agents"][agent_id]
    _write_json(registry_path, data)
    # Delete prompt file
    prompt_path = tdir / prompt_file
    if prompt_path.exists():
        prompt_path.unlink()
        log.info("Deleted prompt file: %s", prompt_path)
    return {"ok": True}


@app.put("/api/agents/mcp-access/{directory}/{agent_id}")
async def update_agent_mcp_access(directory: str, agent_id: str, request: Request):
    """Update MCP access list for an agent in a Configs team directory."""
    body = await request.json()
    servers = body.get("servers", [])
    tdir = _team_dir(directory)
    access_path = tdir / "agent_mcp_access.json"
    access = _read_json(access_path)
    if servers:
        access[agent_id] = servers
    else:
        access.pop(agent_id, None)
    _write_json(access_path, access)
    return {"ok": True}


@app.get("/api/agents/registry/{directory}")
async def get_agents_registry(directory: str):
    """Return raw agents_registry.json for a Configs team directory."""
    tdir = _team_dir(directory)
    registry_path = tdir / "agents_registry.json"
    return _read_json(registry_path)


@app.put("/api/agents/registry/{directory}")
async def put_agents_registry(directory: str, request: Request):
    """Overwrite agents_registry.json for a Configs team directory."""
    data = await request.json()
    tdir = _team_dir(directory)
    tdir.mkdir(parents=True, exist_ok=True)
    _write_json(tdir / "agents_registry.json", data)
    return {"ok": True}


@app.put("/api/templates/mcp-access/{directory}/{agent_id}")
async def update_template_agent_mcp_access(directory: str, agent_id: str, request: Request):
    """Update MCP access list for an agent in a Shared template directory."""
    body = await request.json()
    servers = body.get("servers", [])
    tdir = SHARED_TEAMS_DIR / directory
    access_path = tdir / "agent_mcp_access.json"
    access = _read_json(access_path)
    if servers:
        access[agent_id] = servers
    else:
        access.pop(agent_id, None)
    _write_json(access_path, access)
    return {"ok": True}


@app.get("/api/templates/registry/{directory}")
async def get_templates_registry(directory: str):
    """Return raw agents_registry.json for a Shared template directory."""
    tdir = SHARED_TEAMS_DIR / directory
    return _read_json(tdir / "agents_registry.json")


@app.put("/api/templates/registry/{directory}")
async def put_templates_registry(directory: str, request: Request):
    """Overwrite agents_registry.json for a Shared template directory."""
    data = await request.json()
    tdir = SHARED_TEAMS_DIR / directory
    tdir.mkdir(parents=True, exist_ok=True)
    _write_json(tdir / "agents_registry.json", data)
    return {"ok": True}


# ── API: Workflow (per team) ──────────────────────

@app.get("/api/templates/workflow/{directory}")
async def get_template_workflow(directory: str):
    """Return Workflow.json for a Shared template directory."""
    tdir = SHARED_TEAMS_DIR / directory
    path = tdir / "Workflow.json"
    return _read_json(path) if path.exists() else {}


@app.put("/api/templates/workflow/{directory}")
async def put_template_workflow(directory: str, request: Request):
    """Overwrite Workflow.json for a Shared template directory."""
    data = await request.json()
    tdir = SHARED_TEAMS_DIR / directory
    tdir.mkdir(parents=True, exist_ok=True)
    _write_json(tdir / "Workflow.json", data)
    return {"ok": True}


@app.get("/api/workflow/{directory}")
async def get_workflow(directory: str):
    """Return Workflow.json for a Configs team directory."""
    tdir = TEAMS_DIR / directory
    path = tdir / "Workflow.json"
    return _read_json(path) if path.exists() else {}


@app.put("/api/workflow/{directory}")
async def put_workflow(directory: str, request: Request):
    """Overwrite Workflow.json for a Configs team directory."""
    data = await request.json()
    tdir = TEAMS_DIR / directory
    tdir.mkdir(parents=True, exist_ok=True)
    _write_json(tdir / "Workflow.json", data)
    return {"ok": True}


# ── API: Workflow Design (positions/layout) ───────

@app.get("/api/templates/workflow-design/{directory}")
async def get_template_workflow_design(directory: str):
    path = SHARED_TEAMS_DIR / directory / "workflows_design.json"
    return _read_json(path) if path.exists() else {}

@app.put("/api/templates/workflow-design/{directory}")
async def put_template_workflow_design(directory: str, request: Request):
    data = await request.json()
    tdir = SHARED_TEAMS_DIR / directory
    tdir.mkdir(parents=True, exist_ok=True)
    _write_json(tdir / "workflows_design.json", data)
    return {"ok": True}

@app.get("/api/workflow-design/{directory}")
async def get_workflow_design(directory: str):
    path = TEAMS_DIR / directory / "workflows_design.json"
    return _read_json(path) if path.exists() else {}

@app.put("/api/workflow-design/{directory}")
async def put_workflow_design(directory: str, request: Request):
    data = await request.json()
    tdir = TEAMS_DIR / directory
    tdir.mkdir(parents=True, exist_ok=True)
    _write_json(tdir / "workflows_design.json", data)
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


# ── API: Teams (Configs) ──────────────────────────


def _read_teams_list() -> list:
    """Read teams as a list (array format)."""
    data = _read_json(TEAMS_FILE)
    teams = data.get("teams", [])
    if isinstance(teams, list):
        return teams
    # Legacy dict format: convert to list
    return [{"id": tid, **tcfg} for tid, tcfg in teams.items()]


def _write_teams_list(teams: list):
    """Write teams list and rebuild channel_mapping."""
    mapping = {}
    for t in teams:
        for ch in t.get("discord_channels", []):
            if ch:
                mapping[ch] = t["id"]
    _write_json(TEAMS_FILE, {"teams": teams, "channel_mapping": mapping})


@app.get("/api/teams")
async def get_teams():
    teams = _read_teams_list()
    # Enrich each team with its agents and mcp_access
    enriched = []
    for t in teams:
        tid = t.get("id", "")
        directory = t.get("directory", tid)
        tdir = TEAMS_DIR / directory
        # Read agents
        reg = _read_json(tdir / "agents_registry.json") if (tdir / "agents_registry.json").exists() else {}
        agents_raw = reg.get("agents", {})
        agents_detail = {}
        for aid, acfg in agents_raw.items():
            prompt_file = tdir / acfg.get("prompt", f"{aid}.md")
            prompt_content = ""
            if prompt_file.exists():
                prompt_content = prompt_file.read_text(encoding="utf-8")
            agents_detail[aid] = {**acfg, "prompt_content": prompt_content}
        # Read MCP access
        mcp_access = _read_json(tdir / "agent_mcp_access.json") if (tdir / "agent_mcp_access.json").exists() else {}
        enriched.append({
            **t,
            "agents": agents_detail,
            "agent_count": len(agents_raw),
            "mcp_access": mcp_access,
        })
    return {"teams": enriched}


class TeamEntry(BaseModel):
    name: str
    description: str = ""
    directory: str = ""
    discord_channels: list[str] = []
    template: str = ""
    orchestrator: str = ""


def _ensure_team_folder(team_id: str, directory: str = "", template: str = ""):
    """Create or populate a team folder under Configs/Teams/<directory>/.
    If template is given, copy from Shared/Teams/<template>/.
    Otherwise create skeleton files."""
    import shutil
    folder = directory or team_id
    team_dir = TEAMS_DIR / folder
    if team_dir.exists():
        return
    if template:
        src = SHARED_TEAMS_DIR / template
        if src.is_dir():
            shutil.copytree(str(src), str(team_dir))
            log.info("Copied template '%s' to team '%s'", template, folder)
            return
        else:
            log.warning("Template '%s' not found, creating skeleton", template)
    team_dir.mkdir(parents=True, exist_ok=True)
    _write_json(team_dir / "agents_registry.json", {"agents": {}})
    _write_json(team_dir / "agent_mcp_access.json", {})
    log.info("Created skeleton team folder: %s", team_dir)


@app.post("/api/teams/{team_id}")
async def add_team(team_id: str, entry: TeamEntry):
    teams = _read_teams_list()
    if any(t["id"] == team_id for t in teams):
        raise HTTPException(409, f"L'equipe '{team_id}' existe deja")
    directory = entry.directory or team_id
    team_data = {
        "id": team_id,
        "name": entry.name,
        "description": entry.description,
        "directory": directory,
        "discord_channels": entry.discord_channels,
    }
    if entry.orchestrator:
        team_data["orchestrator"] = entry.orchestrator
    teams.append(team_data)
    _ensure_team_folder(team_id, directory, entry.template)
    _write_teams_list(teams)
    return {"ok": True}


@app.put("/api/teams/{team_id}")
async def update_team(team_id: str, entry: TeamEntry):
    teams = _read_teams_list()
    found = False
    for i, t in enumerate(teams):
        if t["id"] == team_id:
            updated = {
                "id": team_id,
                "name": entry.name,
                "description": entry.description,
                "directory": entry.directory or t.get("directory", team_id),
                "discord_channels": entry.discord_channels,
            }
            if entry.orchestrator:
                updated["orchestrator"] = entry.orchestrator
            teams[i] = updated
            found = True
            break
    if not found:
        raise HTTPException(404, f"Equipe '{team_id}' introuvable")
    _write_teams_list(teams)
    return {"ok": True}


@app.delete("/api/teams/{team_id}")
async def delete_team(team_id: str):
    teams = _read_teams_list()
    new_teams = [t for t in teams if t["id"] != team_id]
    if len(new_teams) == len(teams):
        raise HTTPException(404, f"Equipe '{team_id}' introuvable")
    _write_teams_list(new_teams)
    return {"ok": True}


# ── API: Templates ────────────────────────────────

@app.get("/api/templates")
async def list_templates():
    """List available team templates from Shared/Teams/."""
    templates = []
    if SHARED_TEAMS_DIR.exists():
        for d in sorted(SHARED_TEAMS_DIR.iterdir()):
            if d.is_dir():
                reg = _read_json(d / "agents_registry.json")
                agents_raw = reg.get("agents", {})
                agents_detail = {}
                for aid, acfg in agents_raw.items():
                    prompt_file = d / acfg.get("prompt", f"{aid}.md")
                    prompt_content = ""
                    if prompt_file.exists():
                        prompt_content = prompt_file.read_text(encoding="utf-8")
                    agents_detail[aid] = {**acfg, "prompt_content": prompt_content}
                mcp_access = _read_json(d / "agent_mcp_access.json") if (d / "agent_mcp_access.json").exists() else {}
                prompt_count = len([f for f in d.iterdir() if f.suffix == ".md"])
                templates.append({
                    "id": d.name,
                    "agents": agents_detail,
                    "agent_count": len(agents_raw),
                    "prompts": prompt_count,
                    "has_mcp_access": bool(mcp_access),
                    "mcp_access": mcp_access,
                })
    return {"templates": templates}


@app.get("/api/templates/llm")
async def get_template_llm():
    """Read shared LLM providers template."""
    return _read_json(SHARED_LLM_FILE)


@app.put("/api/templates/llm")
async def save_template_llm(request: Request):
    """Write shared LLM providers template."""
    data = await request.json()
    _write_json(SHARED_LLM_FILE, data)
    return {"ok": True}


@app.get("/api/templates/mcp")
async def get_template_mcp():
    """Read shared MCP servers template."""
    return _read_json(SHARED_MCP_FILE)


@app.put("/api/templates/mcp")
async def save_template_mcp(request: Request):
    """Write shared MCP servers template."""
    data = await request.json()
    _write_json(SHARED_MCP_FILE, data)
    return {"ok": True}


def _get_mcp_full_shared() -> list[dict]:
    """Return catalog entries enriched with install status from Shared MCP."""
    catalog = _parse_mcp_catalog()
    servers = _read_json(SHARED_MCP_FILE).get("servers", {})
    env_entries = {e["key"]: e["value"] for e in _parse_env(ENV_FILE) if e.get("key")}

    for item in catalog:
        srv = servers.get(item["id"])
        item["installed"] = srv is not None
        item["enabled"] = srv.get("enabled", True) if srv else False
        item["agents"] = []
        for ev in item.get("env_vars", []):
            val = env_entries.get(ev["var"], "")
            ev["configured"] = bool(val) and val != "A_CONFIGURER"
    return catalog


@app.get("/api/templates/mcp/catalog")
async def get_template_mcp_catalog():
    """Return catalog enriched with Shared install status."""
    return {"servers": _get_mcp_full_shared()}


@app.post("/api/templates/mcp/install/{entry_id}")
async def install_template_mcp(entry_id: str, req: MCPInstallRequest):
    """Install a catalog entry into Shared MCP."""
    catalog = _parse_mcp_catalog()
    item = next((c for c in catalog if c["id"] == entry_id), None)
    if not item:
        raise HTTPException(404, f"ID '{entry_id}' introuvable dans le catalogue")
    data = _read_json(SHARED_MCP_FILE)
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
    _write_json(SHARED_MCP_FILE, data)
    # Save env vars to .env if provided
    if req.env_values:
        entries = _parse_env(ENV_FILE)
        existing_keys = {e["key"] for e in entries if e.get("key")}
        new_vars = []
        for k, v in req.env_values.items():
            if k in existing_keys:
                entries = [{**e, "value": v} if e.get("key") == k else e for e in entries]
            else:
                new_vars.append({"key": k, "value": v, "comment": ""})
        if new_vars:
            entries.append({"key": "", "value": "", "comment": f"# -- MCP {entry_id} --"})
            entries.extend(new_vars)
        _write_env(ENV_FILE, entries)
    return {"ok": True}


@app.post("/api/templates/mcp/uninstall/{entry_id}")
async def uninstall_template_mcp(entry_id: str):
    """Uninstall a server from Shared MCP."""
    data = _read_json(SHARED_MCP_FILE)
    if entry_id in data.get("servers", {}):
        del data["servers"][entry_id]
        _write_json(SHARED_MCP_FILE, data)
    return {"ok": True}


@app.put("/api/templates/mcp/toggle/{entry_id}")
async def toggle_template_mcp(entry_id: str, req: MCPToggle):
    """Toggle enabled/disabled for a Shared MCP server."""
    data = _read_json(SHARED_MCP_FILE)
    if entry_id not in data.get("servers", {}):
        raise HTTPException(404, f"Serveur '{entry_id}' non installe dans Shared")
    data["servers"][entry_id]["enabled"] = req.enabled
    _write_json(SHARED_MCP_FILE, data)
    return {"ok": True}


@app.get("/api/templates/teams")
async def get_template_teams():
    """Read shared teams list."""
    return _read_json(SHARED_TEAMS_FILE)


@app.put("/api/templates/teams")
async def save_template_teams(request: Request):
    """Write shared teams list and ensure directories exist."""
    data = await request.json()
    _write_json(SHARED_TEAMS_FILE, data)
    # Create directories for new teams
    for team in data.get("teams", []):
        directory = team.get("directory", "")
        if directory:
            team_dir = SHARED_TEAMS_DIR / directory
            if not team_dir.exists():
                team_dir.mkdir(parents=True, exist_ok=True)
                _write_json(team_dir / "agents_registry.json", {"agents": {}})
                _write_json(team_dir / "agent_mcp_access.json", {})
                log.info("Created shared team folder: %s", team_dir)
    return {"ok": True}


def _shared_team_dir(directory: str) -> Path:
    return SHARED_TEAMS_DIR / directory


@app.post("/api/templates/agents")
async def add_template_agent(cfg: AgentConfig):
    """Add an agent to a Shared template directory."""
    tdir = _shared_team_dir(cfg.team_id)
    tdir.mkdir(parents=True, exist_ok=True)
    registry_path = tdir / "agents_registry.json"
    data = _read_json(registry_path)
    if "agents" not in data:
        data["agents"] = {}
    if cfg.id in data["agents"]:
        raise HTTPException(409, f"Agent {cfg.id} already exists")
    prompt_file = cfg.prompt_file or f"{cfg.id}.md"
    agent_data = {"name": cfg.name, "temperature": cfg.temperature, "max_tokens": cfg.max_tokens, "prompt": prompt_file}
    if cfg.llm:
        agent_data["llm"] = cfg.llm
    if cfg.type:
        agent_data["type"] = cfg.type
    if cfg.pipeline_steps:
        agent_data["pipeline_steps"] = cfg.pipeline_steps
    data["agents"][cfg.id] = agent_data
    _write_json(registry_path, data)
    prompt_path = tdir / prompt_file
    if not prompt_path.exists():
        prompt_path.write_text(cfg.prompt_content or f"# {cfg.name}\n\n", encoding="utf-8")
    return {"ok": True}


@app.put("/api/templates/agents/{agent_id}")
async def update_template_agent(agent_id: str, cfg: AgentConfig):
    """Update an agent in a Shared template directory."""
    tdir = _shared_team_dir(cfg.team_id)
    registry_path = tdir / "agents_registry.json"
    data = _read_json(registry_path)
    if agent_id not in data.get("agents", {}):
        raise HTTPException(404, f"Agent {agent_id} not found")
    existing = data["agents"][agent_id]
    existing["name"] = cfg.name
    existing["temperature"] = cfg.temperature
    existing["max_tokens"] = cfg.max_tokens
    if cfg.llm:
        existing["llm"] = cfg.llm
    elif "llm" in existing:
        del existing["llm"]
    existing.pop("model", None)
    if cfg.type:
        existing["type"] = cfg.type
    if cfg.pipeline_steps:
        existing["pipeline_steps"] = cfg.pipeline_steps
    elif "pipeline_steps" in existing:
        del existing["pipeline_steps"]
    data["agents"][agent_id] = existing
    _write_json(registry_path, data)
    if cfg.prompt_content is not None:
        prompt_path = tdir / existing.get("prompt", f"{agent_id}.md")
        prompt_path.write_text(cfg.prompt_content, encoding="utf-8")
    return {"ok": True}


@app.delete("/api/templates/agents/{agent_id}")
async def delete_template_agent(agent_id: str, team_id: str = ""):
    """Delete an agent from a Shared template directory."""
    tdir = _shared_team_dir(team_id)
    registry_path = tdir / "agents_registry.json"
    data = _read_json(registry_path)
    if agent_id not in data.get("agents", {}):
        raise HTTPException(404, f"Agent {agent_id} not found")
    prompt_file = data["agents"][agent_id].get("prompt", f"{agent_id}.md")
    del data["agents"][agent_id]
    _write_json(registry_path, data)
    prompt_path = tdir / prompt_file
    if prompt_path.exists():
        prompt_path.unlink()
        log.info("Deleted prompt file: %s", prompt_path)
    return {"ok": True}


def _ensure_gitignore(target_dir: Path):
    """Create .gitignore with default patterns if it doesn't exist."""
    gitignore = target_dir / ".gitignore"
    if not gitignore.exists():
        log.info("Creating .gitignore in %s", target_dir)
        gitignore.write_text("*.sh\n", encoding="utf-8")


def _build_remote_url(repo_path: str, login: str, password: str) -> str:
    """Build a git remote URL with optional credentials."""
    if login and password:
        if "://" in repo_path:
            scheme, rest = repo_path.split("://", 1)
            return f"{scheme}://{login}:{password}@{rest}"
        return f"https://{login}:{password}@{repo_path}"
    return repo_path if "://" in repo_path else f"https://{repo_path}"


def _git_configure_remote(target_dir: Path, repo_path: str, login: str, password: str):
    """Set origin remote on a git repo."""
    remote_url = _build_remote_url(repo_path, login, password)
    subprocess.run(["git", "remote", "remove", "origin"], cwd=str(target_dir), capture_output=True, text=True, timeout=5)
    subprocess.run(["git", "remote", "add", "origin", remote_url], cwd=str(target_dir), capture_output=True, text=True, timeout=5)
    log.info("Git remote origin set to %s in %s", repo_path, target_dir)


# ── API: Git config (dual repo: configs + shared) ─

@app.get("/api/git/config")
async def get_git_config():
    data = _read_json(GIT_CONFIG_FILE)
    # Migrate old single-repo format to dual-repo
    if "repos" not in data:
        old = {k: data.get(k, "") for k in ("path", "login", "password")}
        data = {
            "repos": {
                "configs": old,
                "shared": {"path": "", "login": "", "password": ""},
            }
        }
        _write_json(GIT_CONFIG_FILE, data)
    return data


class GitRepoConfig(BaseModel):
    path: str = ""
    login: str = ""
    password: str = ""


class GitConfigDual(BaseModel):
    repos: dict  # {"configs": {path, login, password}, "shared": {path, login, password}}


@app.put("/api/git/config")
async def update_git_config(cfg: GitConfigDual):
    _write_json(GIT_CONFIG_FILE, cfg.model_dump())
    # Configure each repo
    repo_dirs = {"configs": CONFIGS, "shared": SHARED_DIR}
    for repo_key, target_dir in repo_dirs.items():
        repo_cfg = cfg.repos.get(repo_key, {})
        repo_path = repo_cfg.get("path", "").strip()
        if not repo_path:
            continue
        target_dir.mkdir(parents=True, exist_ok=True)
        login = repo_cfg.get("login", "").strip()
        password = repo_cfg.get("password", "").strip()
        if not (target_dir / ".git").exists():
            log.info("Initializing git repo in %s", target_dir)
            subprocess.run(
                ["git", "config", "--global", "--add", "safe.directory", str(target_dir)],
                capture_output=True, text=True, timeout=5,
            )
            subprocess.run(["git", "init"], cwd=str(target_dir), capture_output=True, text=True, timeout=10)
            _ensure_gitignore(target_dir)
        _git_configure_remote(target_dir, repo_path, login, password)
    return {"ok": True}


# ── API: Git config per-repo (separate files) ────

def _git_file_for(repo_key: str) -> Path:
    """Return the git.json file path for a repo key."""
    files = {"configs": CONFIGS_GIT_FILE, "shared": SHARED_GIT_FILE}
    f = files.get(repo_key)
    if not f:
        raise HTTPException(400, f"Repo inconnu: {repo_key}. Utiliser 'configs' ou 'shared'.")
    return f


def _migrate_git_config():
    """Migrate old dual-repo git.json to per-repo files if needed."""
    old = _read_json(GIT_CONFIG_FILE)
    repos = old.get("repos", {})
    if not repos:
        return
    for key, cfg_file in [("shared", SHARED_GIT_FILE), ("configs", CONFIGS_GIT_FILE)]:
        if not cfg_file.exists() and repos.get(key):
            cfg_file.parent.mkdir(parents=True, exist_ok=True)
            _write_json(cfg_file, repos[key])


_migrate_git_config()


@app.get("/api/git/repo-config/{repo_key}")
async def get_repo_git_config(repo_key: str):
    cfg_file = _git_file_for(repo_key)
    data = _read_json(cfg_file) if cfg_file.exists() else {}
    return {"path": data.get("path", ""), "login": data.get("login", ""), "password": data.get("password", "")}


@app.put("/api/git/repo-config/{repo_key}")
async def save_repo_git_config(repo_key: str, request: Request):
    body = await request.json()
    cfg_file = _git_file_for(repo_key)
    cfg_file.parent.mkdir(parents=True, exist_ok=True)
    _write_json(cfg_file, {"path": body.get("path", ""), "login": body.get("login", ""), "password": body.get("password", "")})
    # Configure git repo
    target_dir = _get_repo_dir(repo_key)
    repo_path = body.get("path", "").strip()
    if repo_path:
        target_dir.mkdir(parents=True, exist_ok=True)
        login = body.get("login", "").strip()
        password = body.get("password", "").strip()
        if not (target_dir / ".git").exists():
            subprocess.run(["git", "config", "--global", "--add", "safe.directory", str(target_dir)], capture_output=True, text=True, timeout=5)
            subprocess.run(["git", "init"], cwd=str(target_dir), capture_output=True, text=True, timeout=10)
            _ensure_gitignore(target_dir)
        _git_configure_remote(target_dir, repo_path, login, password)
    return {"ok": True}


# ── API: Git operations (per-repo) ───────────────

def _get_repo_dir(repo_key: str) -> Path:
    """Return the directory for a repo key."""
    dirs = {"configs": CONFIGS, "shared": SHARED_DIR}
    d = dirs.get(repo_key)
    if not d:
        raise HTTPException(400, f"Repo inconnu: {repo_key}. Utiliser 'configs' ou 'shared'.")
    return d


def _get_repo_cfg(repo_key: str) -> dict:
    """Return git config for a specific repo."""
    cfg_file = _git_file_for(repo_key)
    if cfg_file.exists():
        return _read_json(cfg_file)
    # Fallback to legacy dual-repo file
    data = _read_json(GIT_CONFIG_FILE)
    repos = data.get("repos", {})
    return repos.get(repo_key, {})


@app.get("/api/git/{repo_key}/status")
async def git_status(repo_key: str):
    target_dir = _get_repo_dir(repo_key)
    try:
        initialized = (target_dir / ".git").exists()
        if not initialized:
            return {"initialized": False, "status": "", "branch": "", "log": ""}
        result = subprocess.run(
            ["git", "status", "--short"],
            cwd=str(target_dir), capture_output=True, text=True, timeout=10
        )
        branch = subprocess.run(
            ["git", "branch", "--show-current"],
            cwd=str(target_dir), capture_output=True, text=True, timeout=10
        )
        git_log = subprocess.run(
            ["git", "log", "--oneline", "-10"],
            cwd=str(target_dir), capture_output=True, text=True, timeout=10
        )
        return {
            "initialized": True,
            "status": result.stdout,
            "branch": branch.stdout.strip(),
            "log": git_log.stdout,
        }
    except Exception as e:
        raise HTTPException(500, str(e))


@app.post("/api/git/{repo_key}/init")
async def git_init(repo_key: str):
    """Initialize a git repo."""
    target_dir = _get_repo_dir(repo_key)
    log.info("Button pressed: Init Repository (%s)", repo_key)
    try:
        target_dir.mkdir(parents=True, exist_ok=True)
        if (target_dir / ".git").exists():
            return {"ok": True, "message": "Depot deja initialise"}
        log.info("git init in %s", target_dir)
        subprocess.run(
            ["git", "config", "--global", "--add", "safe.directory", str(target_dir)],
            capture_output=True, text=True, timeout=5,
        )
        result = subprocess.run(
            ["git", "init"],
            cwd=str(target_dir), capture_output=True, text=True, timeout=10,
        )
        if result.returncode != 0:
            log.error("git init failed (code %d): %s", result.returncode, result.stderr)
            raise HTTPException(500, result.stderr)
        _ensure_gitignore(target_dir)
        # Configure remote origin if config exists
        cfg = _get_repo_cfg(repo_key)
        repo_path = cfg.get("path", "").strip()
        if repo_path:
            login = cfg.get("login", "").strip()
            password = cfg.get("password", "").strip()
            _git_configure_remote(target_dir, repo_path, login, password)
        log.info("git init success for %s", repo_key)
        return {"ok": True, "message": "Depot initialise avec succes"}
    except HTTPException:
        raise
    except Exception as e:
        log.exception("git init exception")
        raise HTTPException(500, str(e))


@app.post("/api/git/{repo_key}/pull")
async def git_pull(repo_key: str):
    target_dir = _get_repo_dir(repo_key)
    log.info("Button pressed: Pull (%s)", repo_key)
    try:
        target_dir.mkdir(parents=True, exist_ok=True)
        cfg = _get_repo_cfg(repo_key)
        repo_path = cfg.get("path", "").strip()
        login = cfg.get("login", "").strip()
        password = cfg.get("password", "").strip()

        if not (target_dir / ".git").exists():
            # Clone
            if not repo_path:
                raise HTTPException(400, "Chemin du depot non configure")
            clone_url = _build_remote_url(repo_path, login, password)
            log.info("git clone %s into %s", repo_path, target_dir)
            result = subprocess.run(
                ["git", "clone", clone_url, "."],
                cwd=str(target_dir), capture_output=True, text=True, timeout=120,
                env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
            )
            _ensure_gitignore(target_dir)
            if result.returncode != 0:
                log.error("git clone failed (code %d): %s", result.returncode, result.stderr)
            else:
                log.info("git clone success for %s", repo_key)
            return {"stdout": result.stdout, "stderr": result.stderr, "code": result.returncode}
        else:
            # Pull
            log.info("git pull in %s", target_dir)
            if repo_path:
                _git_configure_remote(target_dir, repo_path, login, password)
            branch_result = subprocess.run(
                ["git", "branch", "--show-current"],
                cwd=str(target_dir), capture_output=True, text=True, timeout=10
            )
            branch = branch_result.stdout.strip() or "master"
            subprocess.run(
                ["git", "branch", "--set-upstream-to", f"origin/{branch}", branch],
                cwd=str(target_dir), capture_output=True, text=True, timeout=10
            )
            result = subprocess.run(
                ["git", "pull", "origin", branch],
                cwd=str(target_dir), capture_output=True, text=True, timeout=60,
                env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
            )
            if result.returncode != 0:
                log.error("git pull failed (code %d): %s %s", result.returncode, result.stdout, result.stderr)
            else:
                log.info("git pull success for %s: %s", repo_key, result.stdout.strip())
            return {"stdout": result.stdout, "stderr": result.stderr, "code": result.returncode}
    except HTTPException:
        raise
    except Exception as e:
        log.exception("git pull exception")
        raise HTTPException(500, str(e))


# ── API: Git Commits history + checkout ───────────

@app.get("/api/git/{repo_key}/commits")
async def git_commits(repo_key: str):
    """Return last 10 commits with date, hash, tags."""
    target_dir = _get_repo_dir(repo_key)
    if not (target_dir / ".git").exists():
        return {"commits": []}
    try:
        # format: hash|date|tags|subject
        result = subprocess.run(
            ["git", "log", "--pretty=format:%H|%ai|%D|%s", "-10"],
            cwd=str(target_dir), capture_output=True, text=True, timeout=10,
        )
        commits = []
        for line in result.stdout.strip().splitlines():
            if not line:
                continue
            parts = line.split("|", 3)
            full_hash = parts[0]
            date = parts[1] if len(parts) > 1 else ""
            refs = parts[2] if len(parts) > 2 else ""
            subject = parts[3] if len(parts) > 3 else ""
            # Extract tags from refs (e.g. "HEAD -> main, tag: v1.0")
            tags = [r.strip().replace("tag: ", "") for r in refs.split(",") if "tag:" in r]
            commits.append({
                "hash": full_hash,
                "short": full_hash[:7],
                "date": date.strip(),
                "tags": tags,
                "subject": subject.strip(),
            })
        return {"commits": commits}
    except Exception as e:
        raise HTTPException(500, str(e))


@app.post("/api/git/{repo_key}/checkout/{commit_hash}")
async def git_checkout(repo_key: str, commit_hash: str):
    """Checkout a specific commit. Refuses if there are uncommitted changes."""
    import re
    if not re.match(r'^[0-9a-f]{7,40}$', commit_hash):
        raise HTTPException(400, "Hash de commit invalide")
    target_dir = _get_repo_dir(repo_key)
    if not (target_dir / ".git").exists():
        raise HTTPException(400, "Repository non initialise")
    try:
        # Check for uncommitted changes
        status = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=str(target_dir), capture_output=True, text=True, timeout=10,
        )
        if status.stdout.strip():
            raise HTTPException(
                409,
                "Des modifications non commitees sont en attente. Commitez ou annulez-les avant de changer de version."
            )
        # Get current branch
        branch_result = subprocess.run(
            ["git", "branch", "--show-current"],
            cwd=str(target_dir), capture_output=True, text=True, timeout=10,
        )
        branch = branch_result.stdout.strip()
        # Reset branch to the target commit
        result = subprocess.run(
            ["git", "reset", "--hard", commit_hash],
            cwd=str(target_dir), capture_output=True, text=True, timeout=30,
        )
        if result.returncode != 0:
            raise HTTPException(500, f"git reset failed: {result.stderr}")
        log.info("git checkout %s to %s in %s", repo_key, commit_hash, target_dir)
        return {"ok": True, "message": f"Version restauree: {commit_hash[:7]}"}
    except HTTPException:
        raise
    except Exception as e:
        log.exception("git checkout exception")
        raise HTTPException(500, str(e))


class GitCommitRequest(BaseModel):
    message: str


@app.post("/api/git/{repo_key}/commit")
async def git_commit(repo_key: str, req: GitCommitRequest):
    """Stage all, commit and push."""
    target_dir = _get_repo_dir(repo_key)
    log.info("Button pressed: Commit & Push (%s)", repo_key)
    try:
        git_env = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}
        cfg = _get_repo_cfg(repo_key)
        repo_path = cfg.get("path", "").strip()
        login = cfg.get("login", "").strip()
        password = cfg.get("password", "").strip()

        _ensure_gitignore(target_dir)
        subprocess.run(
            ["git", "add", "-A"],
            cwd=str(target_dir), capture_output=True, text=True, timeout=10
        )
        commit_result = subprocess.run(
            ["git", "commit", "-m", req.message],
            cwd=str(target_dir), capture_output=True, text=True, timeout=30
        )
        if commit_result.returncode != 0:
            return {"stdout": commit_result.stdout, "stderr": commit_result.stderr, "code": commit_result.returncode}

        if repo_path and login and password:
            push_url = _build_remote_url(repo_path, login, password)
            push_result = subprocess.run(
                ["git", "push", push_url],
                cwd=str(target_dir), capture_output=True, text=True, timeout=60,
                env=git_env,
            )
        else:
            push_result = subprocess.run(
                ["git", "push"],
                cwd=str(target_dir), capture_output=True, text=True, timeout=60,
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

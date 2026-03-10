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
import zipfile
from pathlib import Path
import shutil
from fastapi import FastAPI, HTTPException, Request, UploadFile
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, Response, StreamingResponse
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
    CONFIGS = PROJECT_DIR / "config"
    TEAMS_DIR = CONFIGS / "Teams"
    SHARED_DIR = PROJECT_DIR / "Shared"
    PROMPTS = TEAMS_DIR / "default"
    SCRIPTS = PROJECT_DIR
    ENV_FILE = PROJECT_DIR / ".env"
    GIT_DIR = PROJECT_DIR
else:
    ROOT = Path(__file__).resolve().parent.parent
    PROJECT_DIR = ROOT / "langgraph-project"
    CONFIGS = ROOT / "config"
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
MAIL_FILE = CONFIGS / "mail.json"
DISCORD_FILE = CONFIGS / "discord.json"
HITL_FILE = CONFIGS / "hitl.json"
OTHERS_FILE = CONFIGS / "others.json"

logging.basicConfig(
    level=logging.DEBUG if os.environ.get("DEBUG") else logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("landgraph-admin")

log.info("DOCKER_MODE=%s  ENV_FILE=%s  CONFIGS=%s  PROMPTS=%s", DOCKER_MODE, ENV_FILE, CONFIGS, PROMPTS)

app = FastAPI(title="LandGraph Admin")
_AUTH_SECRET = secrets.token_hex(32)  # session signing key (regenerated on restart)

# ── JSON helpers (needed early for restore) ───────
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
        env_map = srv.get("env", {}) if srv else {}
        for ev in item.get("env_vars", []):
            mapped_name = env_map.get(ev["var"], ev["var"])
            ev["mapped_var"] = mapped_name
            val = env_entries.get(mapped_name, "")
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


# ── API: Mail ──────────────────────────────────────

@app.get("/api/mail")
async def get_mail():
    """Read mail.json config."""
    if not MAIL_FILE.exists():
        return {"smtp": [], "imap": [], "listener": {}, "templates": {}, "security": {}, "presets": {}}
    return _read_json(MAIL_FILE)


@app.put("/api/mail")
async def save_mail(request: Request):
    """Write mail.json config."""
    data = await request.json()
    _write_json(MAIL_FILE, data)
    return {"ok": True}


@app.get("/api/discord")
async def get_discord():
    """Read discord.json config."""
    if not DISCORD_FILE.exists():
        return {"enabled": True, "default_channel": "discord", "bot": {}, "channels": {}, "guild": {}, "aliases": {}, "formatting": {}, "timeouts": {}}
    return _read_json(DISCORD_FILE)


@app.put("/api/discord")
async def save_discord(request: Request):
    """Write discord.json config."""
    data = await request.json()
    _write_json(DISCORD_FILE, data)
    return {"ok": True}


@app.get("/api/hitl-config")
async def get_hitl_config():
    """Read hitl.json config."""
    if not HITL_FILE.exists():
        return {"auth": {"jwt_expire_hours": 24, "allow_registration": True, "default_role": "undefined"}, "google_oauth": {"enabled": False, "client_id": "", "client_secret_env": "GOOGLE_CLIENT_SECRET", "allowed_domains": []}}
    return _read_json(HITL_FILE)


@app.put("/api/hitl-config")
async def save_hitl_config(request: Request):
    """Write hitl.json config."""
    data = await request.json()
    _write_json(HITL_FILE, data)
    return {"ok": True}


@app.get("/api/others")
async def get_others():
    """Read others.json config."""
    if not OTHERS_FILE.exists():
        return {"password_reset": {"smtp_name": "", "from_address": ""}}
    return _read_json(OTHERS_FILE)


@app.put("/api/others")
async def save_others(request: Request):
    """Write others.json config."""
    data = await request.json()
    _write_json(OTHERS_FILE, data)
    return {"ok": True}


# ── API: Export ────────────────────────────────────

def _zip_directory(dir_path: Path) -> io.BytesIO:
    """Create a zip archive of a directory, return as BytesIO."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        for file in sorted(dir_path.rglob('*')):
            if file.is_file() and '.git' not in file.parts:
                arcname = file.relative_to(dir_path.parent)
                zf.write(file, arcname)
    buf.seek(0)
    return buf


@app.get("/api/export/shared")
async def export_shared():
    """Export Shared/ directory as a zip archive."""
    if not SHARED_DIR.exists():
        raise HTTPException(404, "Shared directory not found")
    buf = _zip_directory(SHARED_DIR)
    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": "attachment; filename=Shared.zip"},
    )


@app.get("/api/export/configs")
async def export_configs():
    """Export config/ directory as a zip archive."""
    if not CONFIGS.exists():
        raise HTTPException(404, "config directory not found")
    buf = _zip_directory(CONFIGS)
    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": "attachment; filename=config.zip"},
    )


def _import_zip_replace(target_dir: Path, data: bytes):
    """Extract zip archive into target_dir, removing files not in the archive."""
    import tempfile
    # Extract to a temp directory first
    tmp = Path(tempfile.mkdtemp())
    try:
        with zipfile.ZipFile(io.BytesIO(data), 'r') as zf:
            zf.extractall(tmp)
        # The archive root may contain the directory name (e.g. "Teams/" or "config/")
        # Detect: if tmp has a single subdirectory matching target_dir.name, use that
        children = [c for c in tmp.iterdir()]
        src = tmp
        if len(children) == 1 and children[0].is_dir():
            src = children[0]
        # Collect new file set (relative paths)
        new_files = set()
        for f in src.rglob('*'):
            if f.is_file():
                new_files.add(f.relative_to(src))
        # Remove existing files not in the archive
        if target_dir.exists():
            for f in list(target_dir.rglob('*')):
                if f.is_file() and '.git' not in f.parts:
                    rel = f.relative_to(target_dir)
                    if rel not in new_files:
                        f.unlink()
            # Clean empty directories
            for d in sorted(target_dir.rglob('*'), reverse=True):
                if d.is_dir() and not any(d.iterdir()):
                    d.rmdir()
        # Copy new files
        for rel in new_files:
            dest = target_dir / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src / rel, dest)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


@app.post("/api/import/shared")
async def import_shared(file: UploadFile):
    """Import a zip archive to replace Shared/Teams/ contents."""
    if not file.filename or not file.filename.endswith('.zip'):
        raise HTTPException(400, "Un fichier .zip est requis")
    data = await file.read()
    try:
        _import_zip_replace(SHARED_DIR, data)
    except zipfile.BadZipFile:
        raise HTTPException(400, "Fichier zip invalide")
    return {"ok": True, "message": "Import Shared termine"}


@app.post("/api/import/configs")
async def import_configs(file: UploadFile):
    """Import a zip archive to replace config/Teams/ contents."""
    if not file.filename or not file.filename.endswith('.zip'):
        raise HTTPException(400, "Un fichier .zip est requis")
    data = await file.read()
    try:
        _import_zip_replace(CONFIGS, data)
    except zipfile.BadZipFile:
        raise HTTPException(400, "Fichier zip invalide")
    return {"ok": True, "message": "Import config termine"}


# ── API: Monitoring ────────────────────────────────

GATEWAY_URL = os.getenv("LANGGRAPH_API_URL", "http://langgraph-api:8000")
ALLOWED_CONTAINERS = {"langgraph-api", "langgraph-discord", "langgraph-mail", "langgraph-admin"}


@app.get("/api/monitoring/logs")
async def get_logs(service: str = "langgraph-api", lines: int = 200):
    """Get Docker container logs."""
    if service not in ALLOWED_CONTAINERS:
        raise HTTPException(400, f"Service inconnu: {service}")
    lines = min(max(lines, 10), 5000)
    try:
        r = subprocess.run(
            ["docker", "logs", "--tail", str(lines), "--timestamps", service],
            capture_output=True, text=True, timeout=10,
        )
        # Docker writes normal logs to stdout, errors to stderr; combine both
        output = r.stdout + r.stderr
        return {"ok": True, "service": service, "lines": output.strip().split("\n") if output.strip() else []}
    except subprocess.TimeoutExpired:
        raise HTTPException(504, "Timeout lecture logs")
    except FileNotFoundError:
        raise HTTPException(500, "Docker CLI non disponible")


@app.get("/api/monitoring/containers")
async def get_containers():
    """Get Docker container statuses."""
    try:
        r = subprocess.run(
            ["docker", "ps", "-a", "--format", "{{.Names}}\t{{.Status}}\t{{.Image}}\t{{.Ports}}\t{{.State}}"],
            capture_output=True, text=True, timeout=10,
        )
        containers = []
        for line in r.stdout.strip().split("\n"):
            if not line.strip():
                continue
            parts = line.split("\t")
            if len(parts) >= 5:
                containers.append({
                    "name": parts[0],
                    "status": parts[1],
                    "image": parts[2],
                    "ports": parts[3],
                    "state": parts[4],
                })
        return {"ok": True, "containers": containers}
    except subprocess.TimeoutExpired:
        raise HTTPException(504, "Timeout")
    except FileNotFoundError:
        raise HTTPException(500, "Docker CLI non disponible")


@app.post("/api/monitoring/container/{name}/{action}")
async def container_action(name: str, action: str):
    """Start, stop or restart a container."""
    if name not in ALLOWED_CONTAINERS:
        raise HTTPException(400, f"Container non autorise: {name}")
    if action not in ("start", "stop", "restart"):
        raise HTTPException(400, f"Action non autorisee: {action}")
    try:
        r = subprocess.run(
            ["docker", action, name],
            capture_output=True, text=True, timeout=30,
        )
        if r.returncode != 0:
            raise HTTPException(500, r.stderr.strip() or f"Erreur {action}")
        return {"ok": True, "message": f"{name} {action} OK"}
    except subprocess.TimeoutExpired:
        raise HTTPException(504, "Timeout")


@app.get("/api/monitoring/events")
async def get_events(n: int = 100, event_type: str = "", agent_id: str = ""):
    """Proxy vers le bus d'events du gateway."""
    import httpx
    params = {"n": min(n, 500)}
    if event_type:
        params["event_type"] = event_type
    if agent_id:
        params["agent_id"] = agent_id
    try:
        r = httpx.get(f"{GATEWAY_URL}/events", params=params, timeout=5)
        return r.json()
    except Exception as e:
        return {"events": [], "error": str(e)}


@app.get("/api/monitoring/gateway")
async def gateway_health():
    """Health check du gateway."""
    import httpx
    try:
        r = httpx.get(f"{GATEWAY_URL}/health", timeout=5)
        return r.json()
    except Exception as e:
        return {"status": "unreachable", "error": str(e)}


# ── API: MCP API Keys (proxy to gateway) ──────────

@app.get("/api/keys")
async def list_api_keys():
    """List all API keys directly from DB."""
    import psycopg
    env = _env_dict()
    uri = env.get("DATABASE_URI", "")
    if not uri:
        raise HTTPException(500, "DATABASE_URI not configured")
    try:
        conn = psycopg.connect(uri, autocommit=True)
        with conn.cursor() as cur:
            cur.execute("""
                SELECT key_hash, name, preview, teams, agents, scopes,
                       created_at, expires_at, revoked
                FROM project.mcp_api_keys
                ORDER BY created_at DESC
            """)
            rows = cur.fetchall()
        conn.close()
        keys = [{
            "key_hash": r[0], "name": r[1], "preview": r[2],
            "teams": r[3], "agents": r[4], "scopes": r[5],
            "created_at": r[6].isoformat() if r[6] else None,
            "expires_at": r[7].isoformat() if r[7] else None,
            "revoked": r[8],
        } for r in rows]
        return {"keys": keys}
    except Exception as e:
        raise HTTPException(500, str(e))


class CreateKeyRequest(BaseModel):
    name: str
    teams: list[str] = ["*"]
    agents: list[str] = ["*"]
    scopes: list[str] = ["call_agent"]
    expires_at: str | None = None


@app.post("/api/keys")
async def create_api_key(req: CreateKeyRequest):
    """Generate a new MCP API key (HMAC-signed token, stored in DB)."""
    import base64
    import hmac as _hmac
    import psycopg
    env = _env_dict()
    secret = env.get("MCP_SECRET", "")
    uri = env.get("DATABASE_URI", "")
    if not secret:
        log.warning("create_api_key: MCP_SECRET not set in .env")
        raise HTTPException(400, "MCP_SECRET not set in .env — ajoutez MCP_SECRET=<votre-secret> dans le fichier .env")
    if not uri:
        log.warning("create_api_key: DATABASE_URI not configured")
        raise HTTPException(500, "DATABASE_URI not configured")

    # Build token: lg-<base64url(payload)>.<hmac-sha256[:16]>
    payload = {
        "teams": req.teams, "agents": req.agents,
        "scopes": req.scopes, "name": req.name,
    }
    if req.expires_at:
        payload["exp"] = req.expires_at
    payload_bytes = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
    payload_b64 = base64.urlsafe_b64encode(payload_bytes).decode().rstrip("=")
    sig = _hmac.new(secret.encode(), payload_bytes, hashlib.sha256).hexdigest()[:16]
    token = f"lg-{payload_b64}.{sig}"

    # Hash + preview
    key_hash = hashlib.sha256(token.encode()).hexdigest()
    preview = token[:6] + "..." + token[-4:] if len(token) > 12 else token[:4] + "..."

    try:
        conn = psycopg.connect(uri, autocommit=True)
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO project.mcp_api_keys
                    (key_hash, name, preview, teams, agents, scopes, expires_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (key_hash) DO NOTHING
            """, (key_hash, req.name, preview,
                  json.dumps(req.teams), json.dumps(req.agents),
                  json.dumps(req.scopes), req.expires_at))
        conn.close()
        return {"token": token, "preview": preview, "name": req.name}
    except Exception as e:
        log.error("create_api_key failed: %s", e, exc_info=True)
        raise HTTPException(500, str(e))


@app.post("/api/keys/{key_hash}/revoke")
async def revoke_api_key(key_hash: str):
    """Revoke an API key."""
    import psycopg
    uri = _env_dict().get("DATABASE_URI", "")
    if not uri:
        raise HTTPException(500, "DATABASE_URI not configured")
    try:
        conn = psycopg.connect(uri, autocommit=True)
        with conn.cursor() as cur:
            cur.execute("UPDATE project.mcp_api_keys SET revoked = true WHERE key_hash = %s", (key_hash,))
        conn.close()
        return {"status": "revoked"}
    except Exception as e:
        raise HTTPException(500, str(e))


@app.delete("/api/keys/{key_hash}")
async def delete_api_key(key_hash: str):
    """Delete an API key permanently."""
    import psycopg
    uri = _env_dict().get("DATABASE_URI", "")
    if not uri:
        raise HTTPException(500, "DATABASE_URI not configured")
    try:
        conn = psycopg.connect(uri, autocommit=True)
        with conn.cursor() as cur:
            cur.execute("DELETE FROM project.mcp_api_keys WHERE key_hash = %s", (key_hash,))
        conn.close()
        return {"status": "deleted"}
    except Exception as e:
        raise HTTPException(500, str(e))


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
    deleted = [t for t in teams if t["id"] == team_id]
    new_teams = [t for t in teams if t["id"] != team_id]
    if not deleted:
        raise HTTPException(404, f"Equipe '{team_id}' introuvable")
    _write_teams_list(new_teams)
    # Clean up the team directory
    directory = deleted[0].get("directory", team_id)
    team_dir = TEAMS_DIR / directory
    if team_dir.exists() and team_dir.is_dir():
        import shutil
        shutil.rmtree(team_dir, ignore_errors=True)
        log.info("Deleted team directory: %s", team_dir)
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
        env_map = srv.get("env", {}) if srv else {}
        for ev in item.get("env_vars", []):
            mapped_name = env_map.get(ev["var"], ev["var"])
            ev["mapped_var"] = mapped_name
            val = env_entries.get(mapped_name, "")
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
    log.info("Installed MCP '%s' into %s (%d servers total)", entry_id, SHARED_MCP_FILE, len(data["servers"]))
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
    """Create or update .gitignore with required patterns."""
    gitignore = target_dir / ".gitignore"
    required = ["*.sh", "git.json", "**/git.json"]
    if gitignore.exists():
        content = gitignore.read_text(encoding="utf-8")
        lines = [l.strip() for l in content.splitlines()]
        added = False
        for pat in required:
            if pat not in lines:
                content = content.rstrip("\n") + f"\n{pat}\n"
                added = True
        if added:
            gitignore.write_text(content, encoding="utf-8")
            log.info("Updated .gitignore in %s (added git.json)", target_dir)
    else:
        log.info("Creating .gitignore in %s", target_dir)
        gitignore.write_text("\n".join(required) + "\n", encoding="utf-8")


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


# ── API: Git Push only + Reset to remote ──────────

@app.post("/api/git/{repo_key}/push")
async def git_push_only(repo_key: str):
    """Push local commits to remote without committing."""
    target_dir = _get_repo_dir(repo_key)
    log.info("Button pressed: Push only (%s)", repo_key)
    try:
        git_env = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}
        cfg = _get_repo_cfg(repo_key)
        repo_path = cfg.get("path", "").strip()
        login = cfg.get("login", "").strip()
        password = cfg.get("password", "").strip()

        if repo_path:
            _git_configure_remote(target_dir, repo_path, login, password)

        branch_result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=str(target_dir), capture_output=True, text=True, timeout=10
        )
        branch = branch_result.stdout.strip()
        if not branch or branch == "HEAD":
            branch = "master"

        push_result = subprocess.run(
            ["git", "push", "origin", branch],
            cwd=str(target_dir), capture_output=True, text=True, timeout=60,
            env=git_env,
        )
        # Retry with --force if rejected (stale info from prior filter-branch, or non-fast-forward)
        if push_result.returncode != 0 and ("non-fast-forward" in push_result.stderr or "stale info" in push_result.stderr or "secret" in push_result.stderr.lower()):
            log.warning("git push rejected (%s), retrying with --force", repo_key)
            push_result = subprocess.run(
                ["git", "push", "--force", "origin", branch],
                cwd=str(target_dir), capture_output=True, text=True, timeout=60,
                env=git_env,
            )

        def _sanitize(text: str) -> str:
            if login and password:
                text = text.replace(f"{login}:{password}@", "***:***@")
                text = text.replace(password, "***")
            return text

        stdout = _sanitize(push_result.stdout)
        stderr = _sanitize(push_result.stderr)
        if push_result.returncode != 0:
            log.error("git push failed (%s, code %d): %s", repo_key, push_result.returncode, stderr[:500])
        else:
            log.info("git push success (%s): %s", repo_key, stdout[:200])
        return {"stdout": stdout, "stderr": stderr, "code": push_result.returncode}
    except Exception as e:
        log.exception("git push exception for %s", repo_key)
        raise HTTPException(500, str(e))


@app.post("/api/git/{repo_key}/reset-to-remote")
async def git_reset_to_remote(repo_key: str):
    """Reset local branch to match remote, discarding all local commits."""
    target_dir = _get_repo_dir(repo_key)
    log.info("Button pressed: Reset to remote (%s)", repo_key)
    try:
        git_env = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}
        cfg = _get_repo_cfg(repo_key)
        repo_path = cfg.get("path", "").strip()
        login = cfg.get("login", "").strip()
        password = cfg.get("password", "").strip()

        if repo_path:
            _git_configure_remote(target_dir, repo_path, login, password)

        # Fetch latest from remote
        subprocess.run(
            ["git", "fetch", "origin"],
            cwd=str(target_dir), capture_output=True, text=True, timeout=60,
            env=git_env,
        )

        branch_result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=str(target_dir), capture_output=True, text=True, timeout=10
        )
        branch = branch_result.stdout.strip()
        if not branch or branch == "HEAD":
            branch = "master"

        # Hard reset to remote branch
        result = subprocess.run(
            ["git", "reset", "--hard", f"origin/{branch}"],
            cwd=str(target_dir), capture_output=True, text=True, timeout=30,
        )
        log.info("git reset --hard origin/%s (%s): code=%d stdout=%s",
                 branch, repo_key, result.returncode, result.stdout[:200])
        if result.returncode == 0:
            return {"ok": True, "message": f"Reset effectue sur origin/{branch}"}
        else:
            return {"ok": False, "message": result.stderr[:300]}
    except Exception as e:
        log.exception("git reset exception for %s", repo_key)
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

        # Sanitize helper (defined early for use in all log outputs)
        def _sanitize(text: str) -> str:
            if login and password:
                text = text.replace(f"{login}:{password}@", "***:***@")
                text = text.replace(password, "***")
            return text

        # 1. Ensure .gitignore
        _ensure_gitignore(target_dir)

        # 2. Configure remote origin with credentials
        if repo_path:
            _git_configure_remote(target_dir, repo_path, login, password)
            log.info("git remote configured (%s): %s", repo_key, repo_path)
        else:
            log.warning("git commit (%s): no repo_path configured, push will use default remote", repo_key)

        # 3. Get current branch name
        branch_result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=str(target_dir), capture_output=True, text=True, timeout=10
        )
        branch = branch_result.stdout.strip()
        # If detached HEAD or empty, try symbolic-ref, then fall back to master/main
        if not branch or branch == "HEAD":
            sym_result = subprocess.run(
                ["git", "symbolic-ref", "--short", "HEAD"],
                cwd=str(target_dir), capture_output=True, text=True, timeout=10
            )
            branch = sym_result.stdout.strip()
        if not branch or branch == "HEAD":
            # Check if remote has main or master
            remote_result = subprocess.run(
                ["git", "branch", "-r"],
                cwd=str(target_dir), capture_output=True, text=True, timeout=10
            )
            if "origin/main" in remote_result.stdout:
                branch = "main"
            else:
                branch = "master"
        log.info("git commit flow (%s): branch=%s, dir=%s", repo_key, branch, target_dir)

        # 3b. Fix detached HEAD — checkout the branch
        head_check = subprocess.run(
            ["git", "symbolic-ref", "-q", "HEAD"],
            cwd=str(target_dir), capture_output=True, text=True, timeout=10
        )
        if head_check.returncode != 0:
            log.warning("Detached HEAD detected (%s), checking out %s", repo_key, branch)
            checkout_result = subprocess.run(
                ["git", "checkout", "-B", branch],
                cwd=str(target_dir), capture_output=True, text=True, timeout=10
            )
            log.info("git checkout -B %s (%s): code=%d stderr=%s",
                     branch, repo_key, checkout_result.returncode, checkout_result.stderr.strip()[:200])

        # 4. Set upstream tracking
        subprocess.run(
            ["git", "branch", "--set-upstream-to", f"origin/{branch}", branch],
            cwd=str(target_dir), capture_output=True, text=True, timeout=10
        )

        # 5. Clean up stuck rebase, stash, pull --rebase, restore
        rebase_merge = target_dir / ".git" / "rebase-merge"
        rebase_apply = target_dir / ".git" / "rebase-apply"
        if rebase_merge.exists() or rebase_apply.exists():
            log.warning("Stuck rebase detected (%s), aborting", repo_key)
            subprocess.run(
                ["git", "rebase", "--abort"],
                cwd=str(target_dir), capture_output=True, text=True, timeout=10
            )
        subprocess.run(
            ["git", "stash", "--include-untracked"],
            cwd=str(target_dir), capture_output=True, text=True, timeout=10
        )
        pull_result = subprocess.run(
            ["git", "pull", "--rebase", "origin", branch],
            cwd=str(target_dir), capture_output=True, text=True, timeout=60,
            env=git_env,
        )
        if pull_result.returncode != 0:
            log.warning("git pull --rebase failed (%s, code %d): stdout=%s stderr=%s",
                        repo_key, pull_result.returncode,
                        _sanitize(pull_result.stdout[:300]),
                        _sanitize(pull_result.stderr[:500]))
        else:
            log.info("git pull --rebase OK (%s): %s", repo_key, pull_result.stdout.strip()[:200])
        subprocess.run(
            ["git", "stash", "pop"],
            cwd=str(target_dir), capture_output=True, text=True, timeout=10
        )

        # 6. Stage all
        add_result = subprocess.run(
            ["git", "add", "-A"],
            cwd=str(target_dir), capture_output=True, text=True, timeout=10
        )
        log.info("git add -A (%s): code=%d", repo_key, add_result.returncode)

        # 7. Remove git.json from staging (root + subdirs)
        subprocess.run(
            ["git", "rm", "-r", "--cached", "--ignore-unmatch", "git.json"],
            cwd=str(target_dir), capture_output=True, text=True, timeout=10
        )
        find_result = subprocess.run(
            ["git", "ls-files", "--cached", "*/git.json"],
            cwd=str(target_dir), capture_output=True, text=True, timeout=10
        )
        for tracked_file in find_result.stdout.strip().splitlines():
            if tracked_file:
                subprocess.run(
                    ["git", "rm", "--cached", "--ignore-unmatch", tracked_file],
                    cwd=str(target_dir), capture_output=True, text=True, timeout=10
                )

        # 8. Commit
        commit_result = subprocess.run(
            ["git", "commit", "-m", req.message],
            cwd=str(target_dir), capture_output=True, text=True, timeout=30
        )
        nothing_to_commit = "nothing to commit" in commit_result.stdout
        log.info("git commit (%s): code=%d nothing_to_commit=%s stdout=%s stderr=%s",
                 repo_key, commit_result.returncode, nothing_to_commit,
                 commit_result.stdout[:200], commit_result.stderr[:200])
        # If commit failed for a real error (not just "nothing to commit"), check
        # if there are local commits ahead of remote before giving up
        if commit_result.returncode != 0 and not nothing_to_commit:
            return {"stdout": commit_result.stdout, "stderr": commit_result.stderr, "code": commit_result.returncode}
        # Always attempt push — there may be previous local commits not yet pushed

        # 9. Purge sensitive files from history ONLY if they actually exist
        history_rewritten = False
        diag_result = subprocess.run(
            ["git", "log", "--all", "--diff-filter=A", "--name-only", "--pretty=format:"],
            cwd=str(target_dir), capture_output=True, text=True, timeout=30
        )
        all_files = set(f.strip() for f in diag_result.stdout.splitlines() if f.strip())
        sensitive_patterns = ['git.json', '.env', '.key', '.pem']
        sensitive_in_history = [f for f in all_files if any(f.lower().endswith(p) or f.lower() == p for p in sensitive_patterns)]
        if sensitive_in_history:
            log.warning("Sensitive files in history (%s): %s — running filter-branch", repo_key, sensitive_in_history)
            sensitive_files = "git rm -r --cached --ignore-unmatch git.json .env *.key *.pem"
            purge_result = subprocess.run(
                ["git", "filter-branch", "--force", "--index-filter",
                 sensitive_files,
                 "--prune-empty", "--", "--all"],
                cwd=str(target_dir), capture_output=True, text=True, timeout=120,
                env={**git_env, "FILTER_BRANCH_SQUELCH_WARNING": "1"},
            )
            log.info("git filter-branch (%s): code=%d stdout=%s stderr=%s",
                     repo_key, purge_result.returncode,
                     purge_result.stdout[:300], purge_result.stderr[:300])
            # Check if history was actually changed (not just "unchanged")
            history_rewritten = purge_result.returncode == 0 and "is unchanged" not in purge_result.stderr
            if purge_result.returncode == 0:
                subprocess.run(
                    ["git", "update-ref", "-d", "refs/original/refs/heads/" + branch],
                    cwd=str(target_dir), capture_output=True, text=True, timeout=10
                )
                subprocess.run(
                    ["git", "reflog", "expire", "--expire=now", "--all"],
                    cwd=str(target_dir), capture_output=True, text=True, timeout=10
                )
                subprocess.run(
                    ["git", "gc", "--prune=now"],
                    cwd=str(target_dir), capture_output=True, text=True, timeout=30
                )
                log.info("git filter-branch cleanup done (%s)", repo_key)
        else:
            log.info("No sensitive files in history (%s), skipping filter-branch", repo_key)

        # 10. Push (use --force only if history was actually rewritten)
        if history_rewritten:
            log.info("History was rewritten, using --force for push (%s)", repo_key)
            push_cmd = ["git", "push", "--force", "origin", branch]
        elif repo_path:
            push_cmd = ["git", "push", "origin", branch]
        else:
            push_cmd = ["git", "push"]
        push_result = subprocess.run(
            push_cmd,
            cwd=str(target_dir), capture_output=True, text=True, timeout=60,
            env=git_env,
        )
        if push_result.returncode != 0 and "non-fast-forward" in push_result.stderr:
            log.warning("git push rejected non-fast-forward (%s), retrying with --force", repo_key)
            push_cmd_force = ["git", "push", "--force", "origin", branch]
            push_result = subprocess.run(
                push_cmd_force,
                cwd=str(target_dir), capture_output=True, text=True, timeout=60,
                env=git_env,
            )

        push_stdout = _sanitize(push_result.stdout)
        push_stderr = _sanitize(push_result.stderr)

        if push_result.returncode != 0:
            log.error("git push failed (%s, code %d): %s", repo_key, push_result.returncode, push_stderr[:500])
        else:
            log.info("git push success for %s", repo_key)

        return {"stdout": commit_result.stdout + "\n" + push_stdout,
                "stderr": push_stderr, "code": push_result.returncode}
    except Exception as e:
        log.exception("git commit/push exception for %s", repo_key)
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


# ── HITL (Human-In-The-Loop) ──────────────────────

def _get_hitl_conn():
    """Get a psycopg connection for HITL queries."""
    import psycopg
    uri = _env_dict().get("DATABASE_URI", "")
    if not uri:
        raise HTTPException(500, "DATABASE_URI not configured")
    return psycopg.connect(uri, autocommit=True)


def _env_dict() -> dict:
    """Read .env as dict."""
    return {e["key"]: e["value"] for e in _parse_env(ENV_FILE) if e.get("key")}


@app.get("/api/hitl")
async def list_hitl(status: str = "", team_id: str = "", limit: int = 50):
    try:
        conn = _get_hitl_conn()
    except Exception as e:
        raise HTTPException(500, str(e))
    try:
        with conn.cursor() as cur:
            clauses = []
            params = []
            if status:
                clauses.append("status = %s")
                params.append(status)
            if team_id:
                clauses.append("team_id = %s")
                params.append(team_id)
            where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
            cur.execute(f"""
                SELECT id, thread_id, agent_id, team_id, request_type, prompt,
                       context, channel, status, response, reviewer,
                       response_channel, created_at, answered_at, expires_at
                FROM project.hitl_requests
                {where}
                ORDER BY created_at DESC
                LIMIT %s
            """, (*params, limit))
            rows = cur.fetchall()
            return [_hitl_row(r) for r in rows]
    finally:
        conn.close()


@app.get("/api/hitl/stats")
async def hitl_stats():
    try:
        conn = _get_hitl_conn()
    except Exception as e:
        raise HTTPException(500, str(e))
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT status, COUNT(*)
                FROM project.hitl_requests
                GROUP BY status
            """)
            counts = {r[0]: r[1] for r in cur.fetchall()}
            return {
                "pending": counts.get("pending", 0),
                "answered": counts.get("answered", 0),
                "timeout": counts.get("timeout", 0),
                "cancelled": counts.get("cancelled", 0),
                "total": sum(counts.values()),
            }
    finally:
        conn.close()


class HitlResponse(BaseModel):
    response: str
    reviewer: str = "admin"


@app.post("/api/hitl/{request_id}/respond")
async def respond_hitl(request_id: str, req: HitlResponse):
    try:
        conn = _get_hitl_conn()
    except Exception as e:
        raise HTTPException(500, str(e))
    try:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE project.hitl_requests
                SET status = 'answered',
                    response = %s,
                    reviewer = %s,
                    response_channel = 'web',
                    answered_at = NOW()
                WHERE id = %s AND status = 'pending'
            """, (req.response, req.reviewer, request_id))
            if cur.rowcount == 0:
                raise HTTPException(404, "Request not found or already answered")
            return {"ok": True}
    finally:
        conn.close()


@app.post("/api/hitl/{request_id}/cancel")
async def cancel_hitl(request_id: str):
    try:
        conn = _get_hitl_conn()
    except Exception as e:
        raise HTTPException(500, str(e))
    try:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE project.hitl_requests
                SET status = 'cancelled', answered_at = NOW()
                WHERE id = %s AND status = 'pending'
            """, (request_id,))
            if cur.rowcount == 0:
                raise HTTPException(404, "Request not found or already processed")
            return {"ok": True}
    finally:
        conn.close()


def _hitl_row(r) -> dict:
    import json as _json
    ctx = r[6]
    if isinstance(ctx, str):
        try:
            ctx = _json.loads(ctx)
        except Exception:
            ctx = {}
    return {
        "id": str(r[0]),
        "thread_id": r[1],
        "agent_id": r[2],
        "team_id": r[3],
        "request_type": r[4],
        "prompt": r[5],
        "context": ctx or {},
        "channel": r[7],
        "status": r[8],
        "response": r[9],
        "reviewer": r[10],
        "response_channel": r[11],
        "created_at": r[12].isoformat() if r[12] else None,
        "answered_at": r[13].isoformat() if r[13] else None,
        "expires_at": r[14].isoformat() if r[14] else None,
    }


# ── HITL Users Management ────────────────────────────

@app.get("/api/hitl/users")
def hitl_list_users():
    import psycopg
    uri = _env_dict().get("DATABASE_URI", "")
    if not uri:
        raise HTTPException(500, "DATABASE_URI not configured")
    conn = psycopg.connect(uri, autocommit=True)
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT u.id, u.email, u.display_name, u.role, u.is_active,
                       u.created_at, u.last_login,
                       COALESCE(
                           json_agg(json_build_object('team_id', tm.team_id, 'role', tm.role))
                           FILTER (WHERE tm.team_id IS NOT NULL), '[]'
                       ) as teams,
                       COALESCE(u.auth_type, 'local') as auth_type
                FROM project.hitl_users u
                LEFT JOIN project.hitl_team_members tm ON tm.user_id = u.id
                GROUP BY u.id
                ORDER BY u.created_at DESC
            """)
            rows = cur.fetchall()
            return [{
                "id": str(r[0]), "email": r[1], "display_name": r[2],
                "role": r[3], "is_active": r[4],
                "created_at": r[5].isoformat() if r[5] else None,
                "last_login": r[6].isoformat() if r[6] else None,
                "teams": r[7] if isinstance(r[7], list) else json.loads(r[7] or "[]"),
                "auth_type": r[8],
            } for r in rows]
    finally:
        conn.close()


def _generate_password(length: int = 12) -> str:
    """Generate a strong random password."""
    import string
    alphabet = string.ascii_letters + string.digits + "!@#$%&*"
    while True:
        pw = ''.join(secrets.choice(alphabet) for _ in range(length))
        # Ensure at least one of each category
        if (any(c.islower() for c in pw) and any(c.isupper() for c in pw)
                and any(c.isdigit() for c in pw) and any(c in "!@#$%&*" for c in pw)):
            return pw


def _send_welcome_email(to_email: str, temp_password: str, reset_url: str):
    """Send welcome email with temporary password and reset link.

    Reads SMTP settings from config/mail.json.  The password is resolved
    from the env-var named in smtp.password_env (default SMTP_PASSWORD).
    """
    import smtplib
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText

    mail_cfg = _read_json(MAIL_FILE) if MAIL_FILE.exists() else {}
    smtp_cfg = mail_cfg.get("smtp", {})
    templates_cfg = mail_cfg.get("templates", {})

    smtp_host = smtp_cfg.get("host", "")
    smtp_port = int(smtp_cfg.get("port", 587))
    smtp_user = smtp_cfg.get("user", "")
    use_ssl = smtp_cfg.get("use_ssl", False)
    use_tls = smtp_cfg.get("use_tls", True)
    from_address = smtp_cfg.get("from_address", "") or smtp_user
    from_name = smtp_cfg.get("from_name", "LandGraph")

    # Resolve password from env var referenced in config
    password_env = smtp_cfg.get("password_env", "SMTP_PASSWORD")
    env = _env_dict()
    smtp_password = env.get(password_env, "")

    if not all([smtp_host, smtp_user, smtp_password]):
        logging.warning("SMTP not configured in mail.json — welcome email not sent")
        return False

    footer = templates_cfg.get("footer_text", "LandGraph Multi-Agent Platform")

    msg = MIMEMultipart("alternative")
    msg["From"] = f"{from_name} <{from_address}>"
    msg["To"] = to_email
    msg["Subject"] = "[LandGraph] Bienvenue — Activez votre compte"
    html = f"""\
<html><body style="font-family:sans-serif;color:#333">
<h2>Bienvenue sur LandGraph</h2>
<p>Un compte a ete cree pour vous.</p>
<p>Votre mot de passe temporaire : <code style="background:#f0f0f0;padding:4px 8px;border-radius:4px;font-size:1.1em">{temp_password}</code></p>
<p>Cliquez sur le lien ci-dessous pour definir votre mot de passe :</p>
<p><a href="{reset_url}" style="display:inline-block;padding:10px 24px;background:#3b82f6;color:white;text-decoration:none;border-radius:6px">Definir mon mot de passe</a></p>
<p style="color:#888;font-size:0.85em">Ce lien expire dans 24 heures. Si vous n'etes pas a l'origine de cette demande, ignorez cet email.</p>
<hr style="border:none;border-top:1px solid #eee;margin:2rem 0"/>
<p style="color:#aaa;font-size:0.8em">{footer}</p>
</body></html>"""
    msg.attach(MIMEText(html, "html"))
    try:
        if use_ssl:
            with smtplib.SMTP_SSL(smtp_host, smtp_port) as server:
                server.login(smtp_user, smtp_password)
                server.send_message(msg)
        else:
            with smtplib.SMTP(smtp_host, smtp_port) as server:
                if use_tls:
                    server.starttls()
                server.login(smtp_user, smtp_password)
                server.send_message(msg)
        return True
    except Exception as e:
        logging.error(f"Failed to send welcome email: {e}")
        return False


@app.post("/api/hitl/users")
async def hitl_create_user(req: Request):
    import psycopg
    from passlib.context import CryptContext
    body = await req.json()
    email = body.get("email", "").strip()
    role = body.get("role", "member")
    team_ids = body.get("teams", [])
    if not email:
        raise HTTPException(400, "Email requis")
    # Generate strong temporary password
    temp_password = _generate_password(12)
    pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto", bcrypt__truncate_error=False)
    hashed = pwd_ctx.hash(temp_password[:72])
    display_name = email.split("@")[0]
    uri = _env_dict().get("DATABASE_URI", "")
    if not uri:
        raise HTTPException(500, "DATABASE_URI not configured")
    conn = psycopg.connect(uri, autocommit=True)
    try:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO project.hitl_users (email, password_hash, display_name, role, auth_type)
                VALUES (%s, %s, %s, %s, 'local')
                RETURNING id
            """, (email, hashed, display_name, role))
            uid = cur.fetchone()[0]
            for tid in team_ids:
                cur.execute("""
                    INSERT INTO project.hitl_team_members (user_id, team_id, role)
                    VALUES (%s, %s, 'member')
                    ON CONFLICT DO NOTHING
                """, (uid, tid))
            # Generate reset token (JWT, 24h expiry)
            from jose import jwt as jose_jwt
            from datetime import datetime, timedelta, timezone
            reset_secret = _env_dict().get("MCP_SECRET", "change-me-hitl-secret")
            reset_token = jose_jwt.encode(
                {"sub": str(uid), "email": email, "purpose": "reset",
                 "exp": datetime.now(timezone.utc) + timedelta(hours=24)},
                reset_secret, algorithm="HS256"
            )
            # Build reset URL (HITL console on port 8090)
            hitl_host = _env_dict().get("HITL_PUBLIC_URL", "")
            if not hitl_host:
                # Fallback: same host as admin, port 8090
                hitl_host = "http://localhost:8090"
            reset_url = f"{hitl_host}/reset-password?token={reset_token}"
            # Send welcome email
            email_sent = _send_welcome_email(email, temp_password, reset_url)
        return {"ok": True, "id": str(uid), "email_sent": email_sent}
    except psycopg.errors.UniqueViolation:
        raise HTTPException(409, "Email deja utilise")
    finally:
        conn.close()


@app.put("/api/hitl/users/{user_id}")
async def hitl_update_user(user_id: str, req: Request):
    import psycopg
    from passlib.context import CryptContext
    body = await req.json()
    display_name = body.get("display_name", "").strip()
    role = body.get("role", "")
    password = body.get("password", "").strip()
    is_active = body.get("is_active", True)
    team_ids = body.get("teams", None)  # list or None (don't touch)
    uri = _env_dict().get("DATABASE_URI", "")
    if not uri:
        raise HTTPException(500, "DATABASE_URI not configured")
    conn = psycopg.connect(uri, autocommit=True)
    try:
        with conn.cursor() as cur:
            sets = ["display_name = %s", "is_active = %s"]
            params = [display_name, is_active]
            if role:
                sets.append("role = %s")
                params.append(role)
            if password:
                pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto", bcrypt__truncate_error=False)
                sets.append("password_hash = %s")
                params.append(pwd_ctx.hash(password[:72]))
            params.append(user_id)
            cur.execute(f"""
                UPDATE project.hitl_users SET {', '.join(sets)}
                WHERE id = %s
            """, params)
            # Update teams if provided
            if team_ids is not None:
                cur.execute("DELETE FROM project.hitl_team_members WHERE user_id = %s", (user_id,))
                for tid in team_ids:
                    cur.execute("""
                        INSERT INTO project.hitl_team_members (user_id, team_id, role)
                        VALUES (%s, %s, 'member')
                        ON CONFLICT DO NOTHING
                    """, (user_id, tid))
        return {"ok": True}
    finally:
        conn.close()


@app.delete("/api/hitl/users/{user_id}")
def hitl_delete_user(user_id: str):
    import psycopg
    uri = _env_dict().get("DATABASE_URI", "")
    if not uri:
        raise HTTPException(500, "DATABASE_URI not configured")
    conn = psycopg.connect(uri, autocommit=True)
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM project.hitl_users WHERE id = %s", (user_id,))
        return {"ok": True}
    finally:
        conn.close()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)

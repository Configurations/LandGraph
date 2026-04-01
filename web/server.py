"""ag.flow Admin — FastAPI backend."""
import csv
from datetime import datetime
import hashlib
import hmac
import io
import json
import logging
import os
import re
import secrets
import subprocess
import asyncio
import zipfile
from pathlib import Path
import shutil

# Log versions at startup
logging.basicConfig(level=logging.INFO)
_log = logging.getLogger(__name__)
try:
    import bcrypt as _bcrypt_mod
    _log.info("bcrypt version: %s", _bcrypt_mod.__version__)
except ImportError:
    pass
_version = "dev"
for _vp in ["/project/.version", str(Path(__file__).resolve().parent.parent / ".version")]:
    if os.path.isfile(_vp):
        _version = open(_vp).read().strip()
        break
_log.info("ag.flow version: %s", _version)
from fastapi import Body, FastAPI, File, HTTPException, Request, UploadFile
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, Response, StreamingResponse
from pydantic import BaseModel
from dotenv import load_dotenv
import httpx
import psycopg

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
        ["git", "config", "--global", "user.name", os.environ.get("GIT_USER_NAME", "ag.flow Admin")],
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

MCP_SERVERS_FILE = CONFIGS / "mcp_servers.json"
MCP_ACCESS_FILE = TEAMS_DIR / "agent_mcp_access.json"
MCP_CATALOG_FILE = SCRIPTS / "Infra" / "mcp_catalog.csv" if not DOCKER_MODE else SHARED_DIR / "Teams" / "mcp_catalog.csv"
LLM_PROVIDERS_FILE = CONFIGS / "llm_providers.json"
TEAMS_FILE = CONFIGS / "teams.json"
SHARED_GIT_FILE = SHARED_DIR / "git.json"
CONFIGS_GIT_FILE = CONFIGS / "git.json"
SHARED_TEAMS_DIR = SHARED_DIR / "Teams"
SHARED_AGENTS_DIR = SHARED_DIR / "Agents"
SHARED_LLM_FILE = SHARED_DIR / "llm_providers.json"
SHARED_MCP_FILE = SHARED_TEAMS_DIR / "mcp_servers.json"
SHARED_TEAMS_FILE = SHARED_TEAMS_DIR / "teams.json"
MAIL_FILE = SHARED_DIR / "mail.json"
DISCORD_FILE = SHARED_DIR / "discord.json"
HITL_FILE = SHARED_DIR / "hitl.json"
OTHERS_FILE = SHARED_DIR / "others.json"
OUTLINE_FILE = CONFIGS / "outline.json"

logging.basicConfig(
    level=logging.DEBUG if os.environ.get("DEBUG") else logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("landgraph-admin")

log.info("DOCKER_MODE=%s  ENV_FILE=%s  CONFIGS=%s  PROMPTS=%s", DOCKER_MODE, ENV_FILE, CONFIGS, PROMPTS)

app = FastAPI(title="ag.flow Admin")
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
  <title>Ag flow — Connexion</title>
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
    .login-version{text-align:center;margin-top:1.25rem;font-size:0.65rem;color:#52525b;letter-spacing:0.03em}
  </style>
</head>
<body>
  <div class="login-card">
    <div class="login-logo">
      <img src="/static/ag_flow_logo.svg" alt="ag.flow" style="width:180px;height:auto;filter:brightness(0) invert(1) brightness(0.85) sepia(1) hue-rotate(210deg) saturate(3)">
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
    <div class="login-version" id="login-version"></div>
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
    fetch('/api/version').then(r=>r.json()).then(d=>{
      let txt=d.version||'';
      if(d.last_update){try{const dt=new Date(d.last_update);txt+=' — '+dt.toLocaleDateString('fr-FR')+' '+dt.toLocaleTimeString('fr-FR',{hour:'2-digit',minute:'2-digit'})}catch(e){}}
      if(txt) document.getElementById('login-version').textContent=txt;
    }).catch(()=>{});
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
        # Allow login routes, static assets, and avatar images
        if path in ("/auth/login", "/auth/logout", "/api/version") or path.startswith("/static/") or path.startswith("/avatars/"):
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
    html = (Path(__file__).parent / "static" / "index.html").read_text(encoding="utf-8")
    return HTMLResponse(html, headers={"Cache-Control": "no-cache, no-store, must-revalidate"})


def _git_last_update() -> str:
    import subprocess
    for base in ["/project", str(Path(__file__).resolve().parent.parent)]:
        if os.path.isdir(os.path.join(base, ".git")):
            try:
                result = subprocess.run(
                    ["git", "log", "-1", "--format=%ci"],
                    cwd=base, capture_output=True, text=True, timeout=5,
                )
                if result.returncode == 0 and result.stdout.strip():
                    return result.stdout.strip()
            except Exception:
                pass
    return ""


@app.get("/api/version")
async def get_version():
    return {"version": _version, "last_update": _git_last_update()}


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


class EnvMerge(BaseModel):
    entries: list  # [{key, value}]


@app.post("/api/env/merge")
async def merge_env_entries(data: EnvMerge):
    """Merge entries into .env: add new keys, update existing ones."""
    existing = _parse_env(ENV_FILE)
    existing_map = {e["key"]: i for i, e in enumerate(existing) if e.get("key")}
    added, updated = 0, 0
    for entry in data.entries:
        key = entry.get("key", "").strip()
        value = entry.get("value", "")
        if not key:
            continue
        if key in existing_map:
            existing[existing_map[key]]["value"] = value
            updated += 1
        else:
            existing.append({"key": key, "value": value, "comment": ""})
            added += 1
    _write_env(ENV_FILE, existing)
    return {"ok": True, "added": added, "updated": updated}


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
    merged = {}
    for f in (MCP_SERVERS_FILE, SHARED_MCP_FILE):
        merged.update(_read_json(f).get("servers", {}))
    return {"servers": merged}


@app.get("/api/mcp/cfg-servers")
async def get_mcp_cfg_servers():
    """Return only config-scope MCP servers (not merged with templates)."""
    data = _read_json(MCP_SERVERS_FILE)
    return {"servers": data.get("servers", {})}


@app.post("/api/mcp/copy-from-template")
async def copy_mcp_from_template(request: Request):
    """Copy server configs directly from template to config (preserves args/params)."""
    body = await request.json()
    server_ids = body.get("server_ids", [])
    tpl_data = _read_json(SHARED_MCP_FILE)
    tpl_servers = tpl_data.get("servers", {})
    cfg_data = _read_json(MCP_SERVERS_FILE)
    if "servers" not in cfg_data:
        cfg_data["servers"] = {}
    added = 0
    for sid in server_ids:
        if sid in tpl_servers:
            cfg_data["servers"][sid] = tpl_servers[sid]
            added += 1
    _write_json(MCP_SERVERS_FILE, cfg_data)
    return {"ok": True, "added": added}


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
    """Return the team folder path: Configs/Teams/<directory>/.

    Accepts either a team id (e.g. 'team1') or a directory name (e.g. 'Team1').
    Resolves the id to the directory name via teams.json when possible.
    """
    teams = _read_teams_list()
    for t in teams:
        if t.get("id") == team_id:
            return TEAMS_DIR / t.get("directory", team_id)
    # Fallback: assume team_id is already a directory name
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
            # Merge catalog properties (name, llm, temperature, etc.) with registry overrides
            catalog = {}
            for cat_dir in [CFG_AGENTS_DIR / aid, SHARED_AGENTS_DIR / aid]:
                cat_file = cat_dir / "agent.json"
                if cat_file.exists():
                    catalog = json.loads(cat_file.read_text(encoding="utf-8"))
                    break
            merged = {**catalog, **acfg, "id": aid}
            prompt_file = tdir / acfg.get("prompt", f"{aid}.md")
            prompt_content = ""
            if prompt_file.exists():
                prompt_content = prompt_file.read_text(encoding="utf-8")
            if acfg.get("type") == "orchestrator":
                orch_prompt_file = tdir / "orchestrator_prompt.md"
                if orch_prompt_file.exists():
                    prompt_content = orch_prompt_file.read_text(encoding="utf-8")
            merged["prompt_content"] = prompt_content
            result[aid] = merged
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
    delegates_to: list = []
    team_id: str = "default"
    delivers_docs: bool | None = None
    delivers_code: bool | None = None
    delivers_design: bool | None = None
    delivers_automation: bool | None = None
    delivers_tasklist: bool | None = None
    delivers_specs: bool | None = None
    delivers_contract: bool | None = None
    avatar: str = ""


@app.post("/api/agents")
async def add_agent(cfg: AgentConfig):
    """Add an agent reference to a config team directory.

    Only stores type.
    Agent properties come from Shared/Agents/{id}/agent.json.
    """
    tdir = _team_dir(cfg.team_id)
    tdir.mkdir(parents=True, exist_ok=True)
    # Verify the shared agent exists
    agent_dir = SHARED_AGENTS_DIR / cfg.id
    if not (agent_dir / "agent.json").exists():
        raise HTTPException(404, f"Shared agent '{cfg.id}' introuvable dans le catalogue")
    registry_path = tdir / "agents_registry.json"
    data = _read_json(registry_path)
    if "agents" not in data:
        data["agents"] = {}
    if cfg.id in data["agents"]:
        raise HTTPException(409, f"Agent {cfg.id} already exists")
    # Store only reference: type
    agent_data: dict = {}
    if cfg.type:
        agent_data["type"] = cfg.type
    data["agents"][cfg.id] = agent_data
    _write_json(registry_path, data)
    return {"ok": True}


@app.put("/api/agents/{agent_id}")
async def update_agent(agent_id: str, cfg: AgentConfig):
    """Update an agent reference in a config team directory.

    Only type can be overridden per-team.
    """
    tdir = _team_dir(cfg.team_id)
    registry_path = tdir / "agents_registry.json"
    data = _read_json(registry_path)
    if agent_id not in data.get("agents", {}):
        raise HTTPException(404, f"Agent {agent_id} not found")
    existing = data["agents"][agent_id]
    if cfg.type:
        existing["type"] = cfg.type
    # delegates_to: list of agent keys this pipeline agent can delegate to
    old_delegates = existing.get("delegates_to", [])
    if cfg.delegates_to:
        existing["delegates_to"] = cfg.delegates_to
    elif "delegates_to" in existing:
        del existing["delegates_to"]
    data["agents"][agent_id] = existing
    _write_json(registry_path, data)
    # Invalidate orchestrator prompt if delegates_to changed
    if sorted(old_delegates) != sorted(cfg.delegates_to or []):
        tdir_team = _team_dir(cfg.team_id)
        team_dir_name = tdir_team.name
        _invalidate_orchestrator_prompt_for_team(team_dir_name)
    return {"ok": True}


@app.delete("/api/agents/{agent_id}")
async def delete_agent(agent_id: str, team_id: str = "default"):
    tdir = _team_dir(team_id)
    registry_path = tdir / "agents_registry.json"
    data = _read_json(registry_path)
    if agent_id not in data.get("agents", {}):
        raise HTTPException(404, f"Agent {agent_id} not found")
    if data["agents"][agent_id].get("type") == "orchestrator":
        raise HTTPException(403, "L'orchestrateur ne peut pas etre supprime")
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


# ── Phase file generation helper ──────────────────
def _generate_phase_files(workflow_data: dict, workflow_filename: str, output_dir: Path, team_id: str):
    """Generate one .md file per group from template + deliverables + agent orchestrator prompts."""
    phases = workflow_data.get("phases", {})
    prefix = f"{workflow_filename}.phase."
    # Purge existing phase files
    for f in output_dir.glob(f"{workflow_filename}.phase.*.md"):
        f.unlink(missing_ok=True)
    if not phases:
        return
    # Load template
    culture = os.getenv("CULTURE", "fr-fr")
    template_path = SHARED_DIR / "Models" / culture / "prompt-phase-orchestrator.md"
    if not template_path.exists():
        raise HTTPException(400, f"Template introuvable : {template_path.relative_to(SHARED_DIR)}")
    template = template_path.read_text(encoding="utf-8")
    errors = []
    generated = 0
    for phase_id, phase_data in phases.items():
        if phase_data.get("external_workflow"):
            continue
        phase_name = phase_data.get("name", phase_id)
        phase_desc = phase_data.get("description", "")
        project_context = f"{phase_name} : {phase_desc}"
        groups = phase_data.get("groups", [])
        if not groups:
            groups = [{"id": phase_id}]
        for group in groups:
            group_id = group.get("id", phase_id)
            deliverables = group.get("deliverables", [])
            # Build {deliverables} content
            deliv_parts = []
            agent_ids = set()
            for d in deliverables:
                name = d.get("Name") or d.get("name") or d.get("id", "")
                desc = d.get("description", "")
                agent_id = d.get("agent", "")
                if agent_id:
                    agent_ids.add(agent_id)
                agent_name = agent_id
                agent_dir = SHARED_AGENTS_DIR / agent_id
                agent_json_path = agent_dir / "agent.json"
                if agent_json_path.exists():
                    try:
                        aj = json.loads(agent_json_path.read_text(encoding="utf-8"))
                        agent_name = aj.get("name", agent_id)
                    except Exception:
                        pass
                section = f"## {name}\n{desc}\n\nCe livrable doit \u00eatre produit par : {agent_name}\n"
                deliv_parts.append(section)
            deliverables_content = "\n---\n\n".join(deliv_parts) if deliv_parts else "(aucun livrable)"
            # Build {agents} content from orch_{agent_id}.md
            agents_parts = []
            for aid in sorted(agent_ids):
                orch_path = SHARED_TEAMS_DIR / team_id / f"orch_{aid}.md"
                if not orch_path.exists():
                    errors.append(f"Fichier manquant : Shared/Teams/{team_id}/orch_{aid}.md")
                    continue
                agents_parts.append(orch_path.read_text(encoding="utf-8"))
            agents_content = "\n\n".join(agents_parts) if agents_parts else "(aucun agent)"
            # Resolve template
            content = template.replace("{project_context}", project_context)
            content = content.replace("{agents}", agents_content)
            content = content.replace("{deliverables}", deliverables_content)
            fname = f"{prefix}{phase_id}.{group_id}.md"
            (output_dir / fname).write_text(content, encoding="utf-8")
            generated += 1
    # ── Generate per-deliverable prompt files ──
    livr_prefix = f"{workflow_filename}.livr."
    for f in output_dir.glob(f"{workflow_filename}.livr.*.md"):
        f.unlink(missing_ok=True)
    deliv_template_path = SHARED_DIR / "Models" / culture / "prompt-delivrable.md"
    if not deliv_template_path.exists():
        errors.append(f"Template introuvable : Shared/Models/{culture}/prompt-delivrable.md")
    else:
        deliv_template = deliv_template_path.read_text(encoding="utf-8")
        for phase_id, phase_data in phases.items():
            if phase_data.get("external_workflow"):
                continue
            phase_name = phase_data.get("name", phase_id)
            phase_desc = phase_data.get("description", "")
            project_context = f"{phase_name}\n{phase_desc}"
            groups = phase_data.get("groups", [])
            if not groups:
                groups = [{"id": phase_id}]
            for group in groups:
                group_id = group.get("id", phase_id)
                for d in group.get("deliverables", []):
                    d_id = d.get("id", "")
                    d_name = d.get("Name") or d.get("name") or d_id
                    d_desc = d.get("description", "")
                    agent_id = d.get("agent", "")
                    if not agent_id:
                        continue
                    agent_dir = SHARED_AGENTS_DIR / agent_id
                    # Clean roles/missions/skills: remove items without matching files
                    d["roles"] = [r for r in d.get("roles", []) if (agent_dir / f"role_{r}.md").exists()]
                    d["missions"] = [m for m in d.get("missions", []) if (agent_dir / f"mission_{m}.md").exists()]
                    d["skills"] = [s for s in d.get("skills", []) if (agent_dir / f"skill_{s}.md").exists()]
                    # Build {agent_card}: identity + roles + missions + skills
                    card_parts = []
                    identity_path = agent_dir / "identity.md"
                    if not identity_path.exists():
                        errors.append(f"Fichier manquant : Shared/Agents/{agent_id}/identity.md")
                    else:
                        card_parts.append(identity_path.read_text(encoding="utf-8"))
                    for r in d["roles"]:
                        card_parts.append((agent_dir / f"role_{r}.md").read_text(encoding="utf-8"))
                    for m in d["missions"]:
                        card_parts.append((agent_dir / f"mission_{m}.md").read_text(encoding="utf-8"))
                    for s in d["skills"]:
                        card_parts.append((agent_dir / f"skill_{s}.md").read_text(encoding="utf-8"))
                    agent_card = "\n\n".join(card_parts) if card_parts else "(aucune carte agent)"
                    deliverable_content = f"## {d_name}\n{d_desc}"
                    # Resolve template
                    out = deliv_template.replace("{project_context}", project_context)
                    out = out.replace("{agent_card}", agent_card)
                    out = out.replace("{deliverable}", deliverable_content)
                    fname = f"{livr_prefix}{phase_id}.{group_id}.{d_id}.{agent_id}.md"
                    (output_dir / fname).write_text(out, encoding="utf-8")
                    generated += 1
    if errors:
        raise HTTPException(400, "\n".join(errors))
    _log.info("Generated %d phase files in %s", generated, output_dir)


# ── Orchestrator prompt generation per group ──────

_DELIVERABLE_FIELDS = ("id", "Name", "agent", "type", "description", "depends_on", "required", "category", "roles", "missions", "skills")


def _build_group_json(workflow_data: dict, phase_id: str, phase_data: dict, group_index: int, group: dict) -> str:
    """Build the JSON payload for a single group to inject into the orchestrator template."""
    deliverables = []
    for d in group.get("deliverables", []):
        deliverables.append({k: d.get(k) for k in _DELIVERABLE_FIELDS if d.get(k) is not None})
    payload = {
        "phase_id": phase_id,
        "phase_name": phase_data.get("name", phase_id),
        "phase_order": phase_data.get("order", 0),
        "group_id": group.get("id", str(group_index)),
        "group_order": group_index,
        "total_groups": len(phase_data.get("groups", [])),
        "deliverables": deliverables,
        "exit_conditions": phase_data.get("exit_conditions", {}),
        "next_phase": phase_data.get("next_phase", ""),
        "rules": workflow_data.get("rules", {}),
    }
    return json.dumps(payload, indent=2, ensure_ascii=False)


async def _generate_orchestrator_prompts(workflow_data: dict, workflow_name: str, culture: str | None = None) -> dict:
    """For each phase/group, call the admin LLM with the orchestrator template and save the result."""
    c = culture or _CULTURE
    models_dir = SHARED_DIR / "Models" / c
    template_path = models_dir / "orchestrator-prompt.md"
    if not template_path.exists():
        raise HTTPException(404, f"Template introuvable: Models/{c}/orchestrator-prompt.md")
    template_content = template_path.read_text(encoding="utf-8")
    models_dir.mkdir(parents=True, exist_ok=True)

    prefix = f"{workflow_name}.wrk."
    for f in models_dir.glob(f"{workflow_name}.wrk.phase.*.md"):
        f.unlink(missing_ok=True)

    phases = workflow_data.get("phases", {})
    generated = []
    errors = []

    for phase_id, phase_data in phases.items():
        groups = phase_data.get("groups", [])
        for group_index, group in enumerate(groups):
            group_id = group.get("id", str(group_index))
            fname = f"{prefix}phase.{phase_id}.{group_id}.md"
            try:
                group_json = _build_group_json(workflow_data, phase_id, phase_data, group_index, group)
                filled = template_content.replace("{group_json}", group_json)
                result = await chat(ChatRequest(messages=[{"role": "user", "content": filled}], use_admin_llm=True))
                output = result.get("content", "").strip()
                (models_dir / fname).write_text(output, encoding="utf-8")
                generated.append(fname)
                _log.info("Generated orchestrator prompt: %s", fname)
            except Exception as exc:
                _log.error("Failed to generate prompt for %s/%s: %s", phase_id, group_id, exc)
                errors.append(f"{phase_id}/{group_id}: {exc}")

    _log.info("Orchestrator prompts: %d generated, %d errors", len(generated), len(errors))
    return {"ok": True, "generated": len(generated), "removed": removed, "errors": errors, "files": generated}


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
    _generate_phase_files(data, "Workflow", tdir, directory)
    return {"ok": True}


@app.post("/api/templates/workflow/{directory}/generate-prompts")
async def generate_template_workflow_prompts(directory: str):
    """Generate orchestrator prompts for each group of a Shared template workflow."""
    tdir = SHARED_TEAMS_DIR / directory
    path = tdir / "Workflow.json"
    if not path.exists():
        raise HTTPException(404, "Workflow.json introuvable")
    data = _read_json(path)
    return await _generate_orchestrator_prompts(data, "Workflow")


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
    _generate_phase_files(data, "Workflow", tdir, directory)
    return {"ok": True}


@app.post("/api/workflow/{directory}/generate-prompts")
async def generate_workflow_prompts(directory: str):
    """Generate orchestrator prompts for each group of a Configs team workflow."""
    tdir = TEAMS_DIR / directory
    path = tdir / "Workflow.json"
    if not path.exists():
        raise HTTPException(404, "Workflow.json introuvable")
    data = _read_json(path)
    return await _generate_orchestrator_prompts(data, "Workflow")


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
    api_key: str = ""
    max_tokens: int = 0
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
    if entry.api_key:
        prov["api_key"] = entry.api_key
    if entry.max_tokens:
        prov["max_tokens"] = entry.max_tokens
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
async def update_llm_provider(provider_id: str, request: Request):
    """Read file from disk, overwrite the provider entry, write back."""
    body = await request.json()
    data = _read_json(LLM_PROVIDERS_FILE)
    if provider_id not in data.get("providers", {}):
        raise HTTPException(404, f"Provider '{provider_id}' introuvable")
    new_id = body.pop("id", provider_id)
    # Overwrite the entire provider entry with what the frontend sent
    if new_id != provider_id:
        del data["providers"][provider_id]
        if data.get("default") == provider_id:
            data["default"] = new_id
        if data.get("admin_llm") == provider_id:
            data["admin_llm"] = new_id
    data["providers"][new_id] = body
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


async def _test_embedding_for_file(provider_id: str, llm_file: Path) -> dict:
    """Test if a provider supports embeddings, update config, return result."""
    data = _read_json(llm_file)
    providers = data.get("providers", {})
    if provider_id not in providers:
        raise HTTPException(404, f"Provider '{provider_id}' introuvable")
    p = providers[provider_id]
    ptype = p.get("type", "")
    model = p.get("model", "")
    base_url = p.get("base_url", "")
    api_key = p.get("api_key", "") or (os.environ.get(p.get("env_key", ""), "") if p.get("env_key") else "")

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            if ptype == "ollama":
                url = f"{base_url.rstrip('/')}/api/embeddings"
                resp = await client.post(url, json={"model": model, "prompt": "test embedding"})
                resp.raise_for_status()
                vector = resp.json().get("embedding", [])
            else:
                # OpenAI-compatible (openai, azure, mistral, deepseek, groq, etc.)
                url = f"{base_url.rstrip('/')}/embeddings" if base_url else "https://api.openai.com/v1/embeddings"
                headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
                resp = await client.post(url, json={"model": model, "input": "test embedding"}, headers=headers)
                resp.raise_for_status()
                resp_data = resp.json()
                vector = resp_data.get("data", [{}])[0].get("embedding", [])

        if not vector:
            p["embedding"] = False
            p.pop("embedding_dimension", None)
            _write_json(llm_file, data)
            return {"ok": False, "error": "Empty embedding vector returned"}

        dimension = len(vector)
        p["embedding"] = True
        p["embedding_dimension"] = dimension
        _write_json(llm_file, data)
        return {"ok": True, "dimension": dimension}

    except httpx.HTTPStatusError as e:
        p["embedding"] = False
        p.pop("embedding_dimension", None)
        _write_json(llm_file, data)
        status = e.response.status_code
        detail = e.response.text[:200]
        return {"ok": False, "error": f"HTTP {status}: {detail}"}
    except Exception as e:
        p["embedding"] = False
        p.pop("embedding_dimension", None)
        _write_json(llm_file, data)
        return {"ok": False, "error": str(e)}


@app.post("/api/llm/providers/test-embedding/{provider_id}")
async def test_embedding_provider(provider_id: str):
    return await _test_embedding_for_file(provider_id, LLM_PROVIDERS_FILE)


@app.post("/api/templates/llm/test-embedding/{provider_id}")
async def test_embedding_template(provider_id: str):
    return await _test_embedding_for_file(provider_id, SHARED_LLM_FILE)


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


@app.put("/api/llm/providers/admin")
async def set_llm_admin(req: LLMDefaultUpdate):
    data = _read_json(LLM_PROVIDERS_FILE)
    if req.provider_id and req.provider_id not in data.get("providers", {}):
        raise HTTPException(404, f"Provider '{req.provider_id}' introuvable")
    data["admin_llm"] = req.provider_id
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


def _merge_llm_upload(uploaded: dict, data: dict) -> dict:
    """Merge uploaded LLM providers into existing data, detecting conflicts."""
    if "providers" not in data:
        data["providers"] = {}
    if "throttling" not in data:
        data["throttling"] = {}

    added_p = added_t = skipped_identical = 0
    conflicts = []
    for pid, prov in uploaded.get("providers", {}).items():
        if pid not in data["providers"]:
            data["providers"][pid] = prov
            added_p += 1
        elif data["providers"][pid] != prov:
            conflicts.append({"id": pid, "existing": data["providers"][pid], "imported": prov})
        else:
            skipped_identical += 1
    for key, thr in uploaded.get("throttling", {}).items():
        if key not in data["throttling"]:
            data["throttling"][key] = thr
            added_t += 1
    if not data.get("default") and uploaded.get("default"):
        data["default"] = uploaded["default"]
    return {"added_providers": added_p, "added_throttling": added_t,
            "skipped_identical": skipped_identical, "conflicts": conflicts}


@app.post("/api/llm/providers/upload")
async def upload_llm_providers(file: UploadFile):
    """Upload a llm_providers.json file — merge providers & throttling into config."""
    if not file.filename or not file.filename.endswith('.json'):
        raise HTTPException(400, "Un fichier .json est requis")
    raw = await file.read()
    try:
        uploaded = json.loads(raw)
    except json.JSONDecodeError:
        raise HTTPException(400, "JSON invalide")

    data = _read_json(LLM_PROVIDERS_FILE)
    result = _merge_llm_upload(uploaded, data)
    _write_json(LLM_PROVIDERS_FILE, data)
    return {"ok": True, **result}


@app.post("/api/llm/providers/resolve")
async def resolve_llm_conflicts(body: dict = Body(...)):
    """Apply user-chosen conflict resolutions for config LLM providers."""
    overwrites = body.get("overwrites", {})
    if not overwrites:
        return {"ok": True, "updated": 0}
    data = _read_json(LLM_PROVIDERS_FILE)
    updated = 0
    for pid, prov in overwrites.items():
        data.setdefault("providers", {})[pid] = prov
        updated += 1
    _write_json(LLM_PROVIDERS_FILE, data)
    return {"ok": True, "updated": updated}


@app.post("/api/templates/llm/upload")
async def upload_template_llm(file: UploadFile):
    """Upload a llm_providers.json file — merge into shared template."""
    if not file.filename or not file.filename.endswith('.json'):
        raise HTTPException(400, "Un fichier .json est requis")
    raw = await file.read()
    try:
        uploaded = json.loads(raw)
    except json.JSONDecodeError:
        raise HTTPException(400, "JSON invalide")

    data = _read_json(SHARED_LLM_FILE)
    result = _merge_llm_upload(uploaded, data)
    _write_json(SHARED_LLM_FILE, data)
    return {"ok": True, **result}


@app.post("/api/templates/llm/resolve")
async def resolve_template_llm_conflicts(body: dict = Body(...)):
    """Apply user-chosen conflict resolutions for template LLM providers."""
    overwrites = body.get("overwrites", {})
    if not overwrites:
        return {"ok": True, "updated": 0}
    data = _read_json(SHARED_LLM_FILE)
    updated = 0
    for pid, prov in overwrites.items():
        data.setdefault("providers", {})[pid] = prov
        updated += 1
    _write_json(SHARED_LLM_FILE, data)
    return {"ok": True, "updated": updated}


# ── API: Agent Catalog (Shared/Agents/{id}/) ──────

class SharedAgentEntry(BaseModel):
    id: str
    name: str = ""
    description: str | None = None
    type: str | None = None
    llm: str | None = None
    temperature: float | None = None
    max_tokens: int | None = None
    mcp_access: list[str] | None = None
    prompt_content: str | None = None
    assign_content: str | None = None
    unassign_content: str | None = None
    identity_content: str | None = None
    docker_mode: bool | None = None
    docker_image: str | None = None
    delivers_docs: bool | None = None
    delivers_code: bool | None = None
    delivers_design: bool | None = None
    delivers_automation: bool | None = None
    delivers_tasklist: bool | None = None
    delivers_specs: bool | None = None
    delivers_contract: bool | None = None
    avatar: str | None = None


def _list_shared_agents() -> list[dict]:
    """List all agents from Shared/Agents/*/agent.json."""
    SHARED_AGENTS_DIR.mkdir(parents=True, exist_ok=True)
    agents = []
    for d in sorted(SHARED_AGENTS_DIR.iterdir()):
        if d.is_dir():
            cfg_file = d / "agent.json"
            if cfg_file.exists():
                cfg = json.loads(cfg_file.read_text(encoding="utf-8"))
                cfg["id"] = d.name
                # Load prompt if exists
                prompt_file = d / "prompt.md"
                if prompt_file.exists():
                    cfg["prompt_content"] = prompt_file.read_text(encoding="utf-8")
                # Load role/mission/skill names (lightweight, no content)
                cfg["role_names"] = []
                cfg["mission_names"] = []
                cfg["skill_names"] = []
                for f in sorted(d.iterdir()):
                    if not f.is_file() or f.suffix != ".md":
                        continue
                    stem = f.stem
                    if stem.startswith("role_"):
                        cfg["role_names"].append(stem[5:])
                    elif stem.startswith("mission_"):
                        cfg["mission_names"].append(stem[8:])
                    elif stem.startswith("skill_"):
                        cfg["skill_names"].append(stem[6:])
                agents.append(cfg)
    return agents


CFG_AGENTS_DIR = CONFIGS / "Agents"


def _list_agents(base_dir: Path) -> list[dict]:
    """List all agents from a base_dir/*/agent.json."""
    base_dir.mkdir(parents=True, exist_ok=True)
    agents = []
    for d in sorted(base_dir.iterdir()):
        if d.is_dir():
            cfg_file = d / "agent.json"
            if cfg_file.exists():
                cfg = json.loads(cfg_file.read_text(encoding="utf-8"))
                cfg["id"] = d.name
                prompt_file = d / "prompt.md"
                if prompt_file.exists():
                    cfg["prompt_content"] = prompt_file.read_text(encoding="utf-8")
                cfg["role_names"] = []
                cfg["mission_names"] = []
                cfg["skill_names"] = []
                for f in sorted(d.iterdir()):
                    if not f.is_file() or f.suffix != ".md":
                        continue
                    stem = f.stem
                    if stem.startswith("role_"):
                        cfg["role_names"].append(stem[5:])
                    elif stem.startswith("mission_"):
                        cfg["mission_names"].append(stem[8:])
                    elif stem.startswith("skill_"):
                        cfg["skill_names"].append(stem[6:])
                agents.append(cfg)
    return agents


def _get_agent_detail(base_dir: Path, agent_id: str) -> dict:
    agent_dir = base_dir / agent_id
    cfg_file = agent_dir / "agent.json"
    if not cfg_file.exists():
        raise HTTPException(404, f"Agent '{agent_id}' introuvable")
    cfg = json.loads(cfg_file.read_text(encoding="utf-8"))
    cfg["id"] = agent_id
    for key, fname in [("prompt_content", "prompt.md"), ("assign_content", f"{agent_id}_assign.md"),
                        ("unassign_content", f"{agent_id}_unassign.md"), ("identity_content", "identity.md")]:
        fpath = agent_dir / fname
        cfg[key] = fpath.read_text(encoding="utf-8") if fpath.exists() else ""
    cfg["roles"] = []
    cfg["missions"] = []
    cfg["skills"] = []
    if agent_dir.exists():
        for f in sorted(agent_dir.iterdir()):
            if not f.is_file() or f.suffix != ".md":
                continue
            stem = f.stem
            if stem.startswith("role_"):
                cfg["roles"].append({"name": stem[5:], "content": f.read_text(encoding="utf-8")})
            elif stem.startswith("mission_"):
                cfg["missions"].append({"name": stem[8:], "content": f.read_text(encoding="utf-8")})
            elif stem.startswith("skill_"):
                cfg["skills"].append({"name": stem[6:], "content": f.read_text(encoding="utf-8")})
    return cfg


def _create_agent(base_dir: Path, entry):
    if not entry.id or not entry.id.replace("_", "").isalnum():
        raise HTTPException(400, "ID invalide (lettres, chiffres, _ uniquement)")
    agent_dir = base_dir / entry.id
    if agent_dir.exists():
        raise HTTPException(409, f"Agent '{entry.id}' existe deja")
    agent_dir.mkdir(parents=True)
    cfg = {
        "name": entry.name or entry.id,
        "description": entry.description or "",
        "type": entry.type or "single",
        "llm": entry.llm or "",
        "temperature": entry.temperature or 0.3,
        "max_tokens": entry.max_tokens or 32768,
        "mcp_access": entry.mcp_access or [],
        "delivers_docs": entry.delivers_docs or False,
        "delivers_code": entry.delivers_code or False,
        "delivers_design": entry.delivers_design or False,
        "delivers_automation": entry.delivers_automation or False,
        "delivers_tasklist": entry.delivers_tasklist or False,
        "delivers_specs": entry.delivers_specs or False,
        "delivers_contract": entry.delivers_contract or False,
    }
    (agent_dir / "agent.json").write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")
    new_prompt = PROMPTS_DIR / "New.md"
    prompt = new_prompt.read_text(encoding="utf-8") if new_prompt.exists() else f"# {entry.name or entry.id}\n\n"
    if entry.prompt_content:
        prompt = entry.prompt_content
    (agent_dir / "prompt.md").write_text(prompt, encoding="utf-8")
    return {"ok": True}


def _update_agent(base_dir: Path, agent_id: str, entry):
    agent_dir = base_dir / agent_id
    if not agent_dir.exists():
        raise HTTPException(404, f"Agent '{agent_id}' introuvable")
    cfg_file = agent_dir / "agent.json"
    cfg = json.loads(cfg_file.read_text(encoding="utf-8")) if cfg_file.exists() else {}
    for field in ["name", "description", "type", "llm", "temperature", "max_tokens", "mcp_access",
                   "docker_mode", "docker_image", "delivers_docs", "delivers_code", "delivers_design",
                   "delivers_automation", "delivers_tasklist", "delivers_specs", "delivers_contract",
                   "avatar"]:
        val = getattr(entry, field, None)
        if val is not None:
            if field == "name":
                cfg[field] = val or agent_id
            else:
                cfg[field] = val
    (agent_dir / "agent.json").write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")
    if entry.prompt_content is not None:
        (agent_dir / "prompt.md").write_text(entry.prompt_content, encoding="utf-8")
    if entry.assign_content is not None:
        (agent_dir / f"{agent_id}_assign.md").write_text(entry.assign_content, encoding="utf-8")
    if entry.unassign_content is not None:
        (agent_dir / f"{agent_id}_unassign.md").write_text(entry.unassign_content, encoding="utf-8")
    if entry.identity_content is not None:
        (agent_dir / "identity.md").write_text(entry.identity_content, encoding="utf-8")
    return {"ok": True}


def _delete_agent(base_dir: Path, agent_id: str):
    agent_dir = base_dir / agent_id
    if not agent_dir.exists():
        raise HTTPException(404, f"Agent '{agent_id}' introuvable")
    shutil.rmtree(agent_dir)
    return {"ok": True}


def _put_agent_file(base_dir: Path, agent_id: str, filename: str, content: str):
    agent_dir = base_dir / agent_id
    if not agent_dir.exists():
        raise HTTPException(404, f"Agent '{agent_id}' introuvable")
    safe = filename.replace("-", "_")
    if not safe.replace("_", "").isalnum():
        raise HTTPException(400, "Nom de fichier invalide")
    (agent_dir / f"{safe}.md").write_text(content, encoding="utf-8")
    return {"ok": True}


def _delete_agent_file(base_dir: Path, agent_id: str, filename: str):
    agent_dir = base_dir / agent_id
    if not agent_dir.exists():
        raise HTTPException(404, f"Agent '{agent_id}' introuvable")
    safe = filename.replace("-", "_")
    target = agent_dir / f"{safe}.md"
    if not target.exists():
        raise HTTPException(404, "Fichier introuvable")
    target.unlink()
    return {"ok": True}


# ── Shared agents routes (Configuration / Templates) ──

@app.get("/api/shared-agents")
async def get_shared_agents():
    return {"agents": _list_agents(SHARED_AGENTS_DIR)}


@app.get("/api/shared-agents/{agent_id}")
async def get_shared_agent(agent_id: str):
    return _get_agent_detail(SHARED_AGENTS_DIR, agent_id)

@app.post("/api/shared-agents")
async def create_shared_agent(entry: SharedAgentEntry):
    r = _create_agent(SHARED_AGENTS_DIR, entry)
    return r

@app.put("/api/shared-agents/{agent_id}")
async def update_shared_agent(agent_id: str, entry: SharedAgentEntry):
    r = _update_agent(SHARED_AGENTS_DIR, agent_id, entry)
    _invalidate_orchestrator_prompts(agent_id)
    return r

@app.delete("/api/shared-agents/{agent_id}")
async def delete_shared_agent(agent_id: str):
    r = _delete_agent(SHARED_AGENTS_DIR, agent_id)
    _invalidate_orchestrator_prompts(agent_id)
    return r

@app.put("/api/shared-agents/{agent_id}/files/{filename}")
async def put_shared_agent_file(agent_id: str, filename: str, request: Request):
    body = await request.json()
    r = _put_agent_file(SHARED_AGENTS_DIR, agent_id, filename, body.get("content", ""))
    _invalidate_orchestrator_prompts(agent_id)
    return r

@app.delete("/api/shared-agents/{agent_id}/files/{filename}")
async def delete_shared_agent_file(agent_id: str, filename: str):
    r = _delete_agent_file(SHARED_AGENTS_DIR, agent_id, filename)
    return {"ok": True}

def _parse_chat_blocks(raw: str) -> dict:
    """Parse structured XML blocks from LLM chat response."""
    import re
    result = {"display": [], "files": []}

    # Display blocks: conflict, confidence, missing_info
    for tag in ("conflict", "confidence", "missing_info"):
        pattern = rf"<{tag}(?:\s+[^>]*)?>(.+?)</{tag}>"
        m = re.search(pattern, raw, re.DOTALL)
        if m:
            content = m.group(0)  # full tag including attributes
            result["display"].append({"tag": tag, "content": content.strip()})

    # File blocks: identity (single), role/mission/skill (multiple with name attr)
    # identity
    m = re.search(r"<identity>(.*?)</identity>", raw, re.DOTALL)
    if m:
        result["files"].append({"filename": "identity", "content": m.group(1).strip()})

    # role, mission, skill — with name attribute
    for tag in ("role", "mission", "skill"):
        for m in re.finditer(rf'<{tag}\s+name="([^"]+)">(.*?)</{tag}>', raw, re.DOTALL):
            name = m.group(1)
            result["files"].append({"filename": f"{tag}_{name}", "content": m.group(2).strip()})

    # files_to_delete block
    dtm = re.search(r"<files_to_delete>(.*?)</files_to_delete>", raw, re.DOTALL)
    if dtm:
        result["files_to_delete"] = [
            line.strip() for line in dtm.group(1).strip().splitlines()
            if line.strip()
        ]
    else:
        result["files_to_delete"] = []

    return result


@app.post("/api/shared-agents/{agent_id}/chat")
async def chat_shared_agent(agent_id: str, request: Request):
    """Chat with the agent builder LLM using GenerateAgent.md as system prompt."""
    agent_dir = SHARED_AGENTS_DIR / agent_id
    if not agent_dir.exists():
        raise HTTPException(404, f"Agent '{agent_id}' introuvable")
    body = await request.json()
    message = body.get("message", "")

    # Load agent description from agent.json
    agent_description = ""
    cfg_file = agent_dir / "agent.json"
    if cfg_file.exists():
        cfg = json.loads(cfg_file.read_text(encoding="utf-8"))
        agent_description = cfg.get("description", "")

    # Snapshot all existing .md files (exclude chat/ subdirectory)
    existing_md_files = {}
    for f in sorted(agent_dir.iterdir()):
        if f.is_dir():
            continue
        if f.is_file() and f.suffix == ".md":
            existing_md_files[f.stem] = f

    # Build {current_profile} from snapshot
    profile_parts = []
    for stem, f in existing_md_files.items():
        content = f.read_text(encoding="utf-8")
        profile_parts.append(f" --------------- {f.name} ---------------\n{content}")
    current_profile = "\n\n".join(profile_parts) if profile_parts else "(aucun fichier de profil)"

    # Load GenerateAgent.md and inject variables into system prompt
    meta_path = PROMPTS_DIR / "GenerateAgent.md"
    if not meta_path.exists():
        raise HTTPException(500, "Meta-prompt GenerateAgent.md introuvable")
    system_prompt = meta_path.read_text(encoding="utf-8").replace("{current_profile}", current_profile).replace("{agent_id}", agent_id).replace("{agent_description}", agent_description)

    # User message is just the user's input
    user_msg = message

    # Build messages list: system + current user message (no history — each call is self-contained)
    messages = [{"role": "system", "content": system_prompt}]
    messages.append({"role": "user", "content": user_msg})

    try:
        result = await chat(ChatRequest(messages=messages, use_admin_llm=True))
        raw = result.get("content", "")
    except Exception as e:
        return {"response": f"Chat indisponible: {e}", "display": [], "file_status": []}

    # Historize chat in agent_dir/chat/
    from datetime import datetime
    chat_dir = agent_dir / "chat"
    chat_dir.mkdir(exist_ok=True)
    ts = datetime.now().strftime("%y%m%d%H%M%S")
    (chat_dir / f"{ts}_send.md").write_text(json.dumps(messages, indent=2, ensure_ascii=False), encoding="utf-8")
    (chat_dir / f"{ts}_response.md").write_text(raw, encoding="utf-8")

    # Parse structured blocks
    parsed = _parse_chat_blocks(raw)

    # Write file blocks from LLM response, removing each from the snapshot dict
    file_status = []
    for fb in parsed["files"]:
        fname = fb["filename"]
        safe = fname.replace("-", "_")
        if not safe.replace("_", "").isalnum():
            continue
        filepath = agent_dir / f"{safe}.md"
        existing = filepath.read_text(encoding="utf-8").strip() if filepath.exists() else ""
        new_content = fb["content"]
        if existing == new_content:
            file_status.append({"name": safe, "status": "unchanged"})
        else:
            filepath.write_text(new_content, encoding="utf-8")
            file_status.append({"name": safe, "status": "updated"})
        existing_md_files.pop(safe, None)

    # Delete orphan .md files not returned by the LLM
    for stem, fpath in existing_md_files.items():
        fpath.unlink()
        file_status.append({"name": stem, "status": "deleted"})

    return {
        "response": raw,
        "display": parsed["display"],
        "file_status": file_status,
    }


@app.post("/api/shared-agents/import")
async def import_shared_agent(file: UploadFile, agent_id: str | None = None):
    """Import an agent from a zip file containing agent.json + prompt.md.
    If agent_id is provided, use it as the directory name (rename).
    Otherwise, use the root folder name from the zip."""
    data = await file.read()
    try:
        zf = zipfile.ZipFile(io.BytesIO(data), 'r')
    except zipfile.BadZipFile:
        raise HTTPException(400, "Fichier zip invalide")

    # Detect the agent id from the zip structure
    names = [n for n in zf.namelist() if not n.startswith('__MACOSX')]
    # Find root folder: first path component of the first entry
    roots = set()
    for n in names:
        parts = n.strip('/').split('/')
        if parts and parts[0]:
            roots.add(parts[0])

    if len(roots) == 1:
        zip_root = roots.pop()
    else:
        zip_root = None

    # Determine final agent id
    final_id = agent_id or zip_root
    if not final_id or not final_id.replace("_", "").replace("-", "").isalnum():
        raise HTTPException(400, "Impossible de determiner l'ID de l'agent depuis le zip")

    agent_dir = SHARED_AGENTS_DIR / final_id
    # Check conflict
    if agent_dir.exists() and not agent_id:
        # Return conflict so frontend can ask for a new name
        return {"conflict": True, "existing_id": final_id}

    agent_dir.mkdir(parents=True, exist_ok=True)

    # Extract files into agent_dir
    for entry in names:
        parts = entry.strip('/').split('/')
        # Strip the root folder prefix if there is one
        if zip_root and parts[0] == zip_root:
            rel_parts = parts[1:]
        else:
            rel_parts = parts
        if not rel_parts or not rel_parts[-1]:
            continue  # directory entry
        rel_path = '/'.join(rel_parts)
        dest = agent_dir / rel_path
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(zf.read(entry))

    zf.close()
    return {"ok": True, "id": final_id}


# ── Production agents routes (config/Agents/) ──

@app.get("/api/prod-agents")
async def get_prod_agents():
    return {"agents": _list_agents(CFG_AGENTS_DIR)}

@app.get("/api/prod-agents/{agent_id}")
async def get_prod_agent(agent_id: str):
    return _get_agent_detail(CFG_AGENTS_DIR, agent_id)

@app.post("/api/prod-agents")
async def create_prod_agent(entry: SharedAgentEntry):
    return _create_agent(CFG_AGENTS_DIR, entry)

@app.put("/api/prod-agents/{agent_id}")
async def update_prod_agent(agent_id: str, entry: SharedAgentEntry):
    return _update_agent(CFG_AGENTS_DIR, agent_id, entry)

@app.delete("/api/prod-agents/{agent_id}")
async def delete_prod_agent(agent_id: str):
    return _delete_agent(CFG_AGENTS_DIR, agent_id)

@app.put("/api/prod-agents/{agent_id}/files/{filename}")
async def put_prod_agent_file(agent_id: str, filename: str, request: Request):
    body = await request.json()
    return _put_agent_file(CFG_AGENTS_DIR, agent_id, filename, body.get("content", ""))

@app.delete("/api/prod-agents/{agent_id}/files/{filename}")
async def delete_prod_agent_file(agent_id: str, filename: str):
    return _delete_agent_file(CFG_AGENTS_DIR, agent_id, filename)

@app.post("/api/prod-agents/copy-from-config")
async def copy_prod_agents_from_config(request: Request):
    """Copy selected agent directories from Shared/Agents/ to config/Agents/."""
    body = await request.json()
    agent_ids = body.get("agent_ids", [])
    if not agent_ids:
        raise HTTPException(400, "Aucun agent selectionne")
    CFG_AGENTS_DIR.mkdir(parents=True, exist_ok=True)
    copied = 0
    for aid in agent_ids:
        src = SHARED_AGENTS_DIR / aid
        if not src.exists():
            continue
        dst = CFG_AGENTS_DIR / aid
        if dst.exists():
            shutil.rmtree(dst)
        shutil.copytree(src, dst)
        copied += 1
    return {"ok": True, "copied": copied}

@app.post("/api/prod-agents/import")
async def import_prod_agent(file: UploadFile, agent_id: str | None = None):
    """Import an agent zip into config/Agents/."""
    data = await file.read()
    try:
        zf = zipfile.ZipFile(io.BytesIO(data), 'r')
    except zipfile.BadZipFile:
        raise HTTPException(400, "Fichier zip invalide")
    names = [n for n in zf.namelist() if not n.startswith('__MACOSX')]
    roots = set()
    for n in names:
        parts = n.strip('/').split('/')
        if parts and parts[0]:
            roots.add(parts[0])
    zip_root = roots.pop() if len(roots) == 1 else None
    final_id = agent_id or zip_root
    if not final_id or not final_id.replace("_", "").replace("-", "").isalnum():
        raise HTTPException(400, "Impossible de determiner l'ID de l'agent depuis le zip")
    agent_dir = CFG_AGENTS_DIR / final_id
    if agent_dir.exists() and not agent_id:
        return {"conflict": True, "existing_id": final_id}
    agent_dir.mkdir(parents=True, exist_ok=True)
    for entry in names:
        parts = entry.strip('/').split('/')
        if zip_root and parts[0] == zip_root:
            rel_parts = parts[1:]
        else:
            rel_parts = parts
        if not rel_parts or not rel_parts[-1]:
            continue
        dest = agent_dir / '/'.join(rel_parts)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(zf.read(entry))
    zf.close()
    return {"ok": True, "id": final_id}


# ── API: Mail ──────────────────────────────────────

@app.get("/api/templates/mail")
async def get_mail():
    """Read mail.json config from Shared/."""
    if not MAIL_FILE.exists():
        return {"smtp": [], "imap": [], "listener": {}, "templates": {}, "security": {}, "presets": {}}
    return _read_json(MAIL_FILE)


@app.put("/api/templates/mail")
async def save_mail(request: Request):
    """Write mail.json config to Shared/."""
    data = await request.json()
    _write_json(MAIL_FILE, data)
    return {"ok": True}


@app.get("/api/templates/discord")
async def get_discord():
    """Read discord.json config from Shared/."""
    if not DISCORD_FILE.exists():
        return {"enabled": True, "default_channel": "discord", "bot": {}, "channels": {}, "guild": {}, "aliases": {}, "formatting": {}, "timeouts": {}}
    return _read_json(DISCORD_FILE)


@app.put("/api/templates/discord")
async def save_discord(request: Request):
    """Write discord.json config to Shared/."""
    data = await request.json()
    _write_json(DISCORD_FILE, data)
    return {"ok": True}


@app.get("/api/templates/hitl-config")
async def get_hitl_config():
    """Read hitl.json config from Shared/."""
    if not HITL_FILE.exists():
        return {"auth": {"jwt_expire_hours": 24, "allow_registration": True, "default_role": "undefined"}, "google_oauth": {"enabled": False, "client_id": "", "client_secret_env": "GOOGLE_CLIENT_SECRET", "allowed_domains": []}}
    return _read_json(HITL_FILE)


@app.put("/api/templates/hitl-config")
async def save_hitl_config(request: Request):
    """Write hitl.json config to Shared/."""
    data = await request.json()
    _write_json(HITL_FILE, data)
    return {"ok": True}


@app.get("/api/templates/others")
async def get_others():
    """Read others.json config from Shared/."""
    if not OTHERS_FILE.exists():
        return {"password_reset": {"smtp_name": "", "from_address": ""}}
    return _read_json(OTHERS_FILE)


@app.put("/api/templates/others")
async def save_others(request: Request):
    """Write others.json config to Shared/."""
    data = await request.json()
    _write_json(OTHERS_FILE, data)
    return {"ok": True}


# ── API: Outline ──────────────────────────────────

@app.get("/api/outline-config")
async def get_outline_config():
    """Read outline.json config."""
    if not OUTLINE_FILE.exists():
        return {
            "enabled": False, "url_env": "OUTLINE_URL", "api_key_env": "OUTLINE_API_KEY",
            "collection_prefix": "ag.flow", "phase_labels": {},
            "auto_publish": {"enabled": False, "deliverables": {}},
        }
    return _read_json(OUTLINE_FILE)


@app.put("/api/outline-config")
async def save_outline_config(request: Request):
    """Write outline.json config."""
    data = await request.json()
    _write_json(OUTLINE_FILE, data)
    return {"ok": True}


@app.post("/api/outline/test-connection")
async def test_outline_connection():
    """Test Outline API connection."""
    import httpx as _httpx
    cfg = _read_json(OUTLINE_FILE) if OUTLINE_FILE.exists() else {}
    url_env = cfg.get("url_env", "OUTLINE_URL")
    key_env = cfg.get("api_key_env", "OUTLINE_API_KEY")
    base_url = os.getenv(url_env, "").rstrip("/")
    api_key = os.getenv(key_env, "")
    if not base_url or not api_key:
        return {"ok": False, "error": f"Variables {url_env} et/ou {key_env} non definies dans .env"}
    try:
        async with _httpx.AsyncClient(timeout=15) as client:
            r = await client.post(
                f"{base_url}/api/auth.info", json={},
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            )
            r.raise_for_status()
            data = r.json().get("data", {})
            return {
                "ok": True,
                "info": {
                    "user": data.get("user", {}).get("name", ""),
                    "team": data.get("team", {}).get("name", ""),
                },
            }
    except Exception as e:
        return {"ok": False, "error": str(e)}


@app.get("/api/outline/documents/{thread_id}")
async def get_outline_documents(thread_id: str):
    """Get tracked Outline documents for a thread."""
    try:
        conn = psycopg.connect(os.getenv("DATABASE_URI"), autocommit=True)
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT id, thread_id, team_id, agent_id, phase, deliverable_key, "
                    "outline_document_id, outline_url, version, content_hash, created_at, updated_at "
                    "FROM project.outline_documents WHERE thread_id=%s ORDER BY phase, deliverable_key",
                    (thread_id,),
                )
                cols = [d[0] for d in cur.description]
                rows = [dict(zip(cols, row)) for row in cur.fetchall()]
                # Serialize datetimes
                for row in rows:
                    for k in ("created_at", "updated_at"):
                        if row.get(k):
                            row[k] = row[k].isoformat()
                    row["id"] = str(row["id"])
                return {"documents": rows}
        finally:
            conn.close()
    except Exception as e:
        return {"documents": [], "error": str(e)}


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
    provider_id: str = ""
    use_admin_llm: bool = False
    scope: str = "production"  # "production" -> config/, "configuration" -> Shared/


@app.post("/api/chat")
async def chat(req: ChatRequest):
    default_key = "admin_llm" if req.use_admin_llm else "default"
    # Production scope reads config/, Configuration scope reads Shared/
    llm_file = SHARED_LLM_FILE if req.scope == "configuration" else LLM_PROVIDERS_FILE
    data = _read_json(llm_file)
    chosen_id = req.provider_id or data.get(default_key, "") or data.get("default", "")
    if not chosen_id or chosen_id not in data.get("providers", {}):
        raise HTTPException(400, f"Aucun provider LLM configure dans {llm_file.name}")

    provider = data["providers"][chosen_id]
    ptype = provider["type"]
    model = provider["model"]
    max_tokens = provider.get("max_tokens", 4096)
    env_key = provider.get("env_key", "")
    base_url = provider.get("base_url", "")

    # Resolve API key: direct api_key in config takes priority, then env_key from .env
    api_key = provider.get("api_key", "")
    if not api_key and env_key:
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
                body = {"model": model, "max_tokens": max_tokens, "messages": chat_msgs}
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
                body = {"model": model, "messages": messages, "max_tokens": max_tokens}
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
                body = {"model": model, "messages": messages, "max_tokens": max_tokens}
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


# ── API: Config Check ─────────────────────────────

@app.get("/api/config/check")
async def config_check():
    """Validate configuration coherence. Returns errors and warnings."""
    issues = []  # {level: 'error'|'warning', category, message}

    # 1. Check .env secrets referenced by LLM providers
    env_entries = {e["key"]: e["value"] for e in _parse_env(ENV_FILE) if e.get("key")}
    llm_data = _read_json(CONFIGS / "llm_providers.json") if (CONFIGS / "llm_providers.json").exists() else {}

    # Collect LLM IDs actually used by agents or as default
    used_llm_ids = set()
    default_llm = llm_data.get("default", "")
    if default_llm:
        used_llm_ids.add(default_llm)
    teams_list = _read_teams_list()
    for tcfg in teams_list:
        tid = tcfg.get("id", "")
        directory = tcfg.get("directory", tid)
        tdir = _team_dir(directory)
        reg_path = tdir / "agents_registry.json"
        if reg_path.exists():
            reg = _read_json(reg_path)
            for aid, aconf in reg.get("agents", {}).items():
                agent_llm = aconf.get("llm", "")
                if agent_llm:
                    used_llm_ids.add(agent_llm)

    for pid, pconf in llm_data.get("providers", {}).items():
        env_key = pconf.get("env_key", "")
        if not env_key:
            continue
        # Skip providers not used by any agent or as default
        if pid not in used_llm_ids:
            continue
        if env_key not in env_entries:
            issues.append({"level": "error", "category": "secrets", "message": f"LLM provider '{pid}' reference la variable '{env_key}' — introuvable dans .env"})
        elif not env_entries[env_key].strip():
            issues.append({"level": "warning", "category": "secrets", "message": f"LLM provider '{pid}' : la variable '{env_key}' est vide dans .env"})

    # 1b. Check .env secrets referenced by MCP servers
    mcp_data = _read_json(MCP_SERVERS_FILE) if MCP_SERVERS_FILE.exists() else {}
    for sid, sconf in mcp_data.get("servers", {}).items():
        for param_name, env_var in sconf.get("env", {}).items():
            if env_var not in env_entries:
                issues.append({"level": "error", "category": "mcp", "message": f"MCP '{sid}' : variable '{env_var}' (param {param_name}) absente du .env"})
            elif not env_entries[env_var].strip():
                issues.append({"level": "warning", "category": "mcp", "message": f"MCP '{sid}' : variable '{env_var}' (param {param_name}) vide dans .env"})

    # 2. Check critical env vars
    critical_vars = ["DATABASE_URI", "REDIS_URI"]
    for var in critical_vars:
        if var not in env_entries:
            issues.append({"level": "error", "category": "secrets", "message": f"Variable critique '{var}' absente du .env"})
        elif not env_entries[var].strip():
            issues.append({"level": "warning", "category": "secrets", "message": f"Variable critique '{var}' vide dans .env"})

    # 3. Check teams and agents
    teams = teams_list
    for tcfg in teams:
        tid = tcfg.get("id", "")
        directory = tcfg.get("directory", tid)
        tdir = _team_dir(directory)

        # Check registry exists
        reg_path = tdir / "agents_registry.json"
        if not reg_path.exists():
            issues.append({"level": "error", "category": "teams", "message": f"Equipe '{tid}' : agents_registry.json introuvable dans {directory}/"})
            continue

        reg = _read_json(reg_path)
        agent_ids = set(reg.get("agents", {}).keys())

        # Check each agent has a name
        for aid, aconf in reg.get("agents", {}).items():
            # Name can come from registry or shared/config agent catalog
            has_name = bool(aconf.get("name"))
            if not has_name:
                for cat_dir in [SHARED_DIR / "Agents" / aid, CFG_AGENTS_DIR / aid]:
                    cat_file = cat_dir / "agent.json"
                    if cat_file.exists():
                        cat = json.loads(cat_file.read_text(encoding="utf-8"))
                        if cat.get("name"):
                            has_name = True
                            break
            if not has_name:
                issues.append({"level": "warning", "category": "agents", "message": f"Agent '{aid}' (equipe {tid}) : champ 'name' manquant"})

            # Check prompt file exists (skip orchestrator — prompt is generated)
            if aconf.get("type") == "orchestrator":
                continue
            prompt_file = aconf.get("prompt", f"{aid}.md")
            prompt_path = tdir / prompt_file
            if not prompt_path.exists():
                # Check shared agents fallback (prompt.md or identity.md)
                shared_found = False
                for base in [SHARED_DIR / "Agents" / aid / "prompt.md",
                             SHARED_DIR / "Agents" / aid / "identity.md",
                             CFG_AGENTS_DIR / aid / "prompt.md",
                             CFG_AGENTS_DIR / aid / "identity.md"]:
                    if base.exists():
                        shared_found = True
                        break
                if not shared_found:
                    issues.append({"level": "warning", "category": "agents", "message": f"Agent '{aid}' (equipe {tid}) : prompt '{prompt_file}' introuvable"})

        # 3b. Validate JSON blocks in prompts and pipeline step instructions
        import re as _re_check
        def _check_json_blocks(text, label):
            for m in _re_check.finditer(r'```json\s*\n([\s\S]*?)\n\s*```', text):
                try:
                    json.loads(m.group(1).strip())
                except json.JSONDecodeError as e:
                    issues.append({"level": "warning", "category": "prompts", "message": f"{label} : JSON invalide — {str(e)[:120]}"})

        for aid, aconf in reg.get("agents", {}).items():
            # Check team prompt
            prompt_file = aconf.get("prompt", f"{aid}.md")
            prompt_path = tdir / prompt_file
            if prompt_path.exists():
                _check_json_blocks(prompt_path.read_text(encoding="utf-8"), f"Prompt '{aid}' (equipe {tid})")
            else:
                # Check shared agent prompt
                shared_prompt = SHARED_DIR / "Agents" / aid / "prompt.md"
                if shared_prompt.exists():
                    _check_json_blocks(shared_prompt.read_text(encoding="utf-8"), f"Prompt '{aid}' (shared)")
        # 4. Check workflow references valid agents
        wf_path = tdir / "Workflow.json"
        if not wf_path.exists():
            wf_path = tdir / "workflow.json"
        if wf_path.exists():
            wf = _read_json(wf_path)
            for pid, pconf in wf.get("phases", {}).items():
                # Agents in phase must exist in registry
                for agent_in_phase in pconf.get("agents", {}).keys():
                    if agent_in_phase not in agent_ids:
                        issues.append({"level": "error", "category": "workflow", "message": f"Phase '{pid}' (equipe {tid}) : agent '{agent_in_phase}' n'existe pas dans le registry"})

                # Deliverables must be fully configured
                phase_agents = set(pconf.get("agents", {}).keys())
                phase_deliverables = set(pconf.get("deliverables", {}).keys())
                for dk, dconf in pconf.get("deliverables", {}).items():
                    dlabel = f"Phase '{pid}' livrable '{dk}' (equipe {tid})"

                    # Agent must be set
                    d_agent = dconf.get("agent", "")
                    if not d_agent:
                        issues.append({"level": "error", "category": "workflow", "message": f"{dlabel} : champ 'agent' manquant"})
                    elif d_agent not in agent_ids:
                        issues.append({"level": "error", "category": "workflow", "message": f"{dlabel} : agent '{d_agent}' n'existe pas dans le registry"})
                    elif d_agent not in phase_agents:
                        issues.append({"level": "error", "category": "workflow", "message": f"{dlabel} : agent '{d_agent}' n'est pas assigne a cette phase"})

                    # Type must be set
                    if not dconf.get("type"):
                        issues.append({"level": "warning", "category": "workflow", "message": f"{dlabel} : champ 'type' non renseigne"})

                    # Description recommended
                    if not dconf.get("description", "").strip():
                        issues.append({"level": "warning", "category": "workflow", "message": f"{dlabel} : champ 'description' vide"})

                    # Check depends_on references valid deliverables
                    for dep_dk in dconf.get("depends_on", []):
                        if dep_dk not in phase_deliverables:
                            issues.append({"level": "error", "category": "workflow", "message": f"{dlabel} : depends_on '{dep_dk}' n'existe pas dans les livrables de la phase"})

                # Transitions target valid phases
            phase_ids = set(wf.get("phases", {}).keys())
            for tr in wf.get("transitions", []):
                if tr.get("from") not in phase_ids:
                    tr_from = tr.get("from", "?")
                    issues.append({"level": "error", "category": "workflow", "message": f"Transition from='{tr_from}' (equipe {tid}) : phase source inconnue"})
                if tr.get("to") not in phase_ids:
                    tr_to = tr.get("to", "?")
                    issues.append({"level": "error", "category": "workflow", "message": f"Transition to='{tr_to}' (equipe {tid}) : phase cible inconnue"})
        else:
            issues.append({"level": "warning", "category": "workflow", "message": f"Equipe '{tid}' : Workflow.json introuvable"})

    # 4a. Check docker_mode agents have valid docker_image
    for sa_dir in sorted(SHARED_AGENTS_DIR.iterdir()) if SHARED_AGENTS_DIR.exists() else []:
        agent_json = sa_dir / "agent.json"
        if not agent_json.exists():
            continue
        sa = _read_json(agent_json)
        if not sa.get("docker_mode"):
            continue
        aid = sa_dir.name
        img = (sa.get("docker_image") or "").strip()
        if not img:
            issues.append({"level": "error", "category": "agents", "message": f"Agent '{aid}' : docker_mode actif mais aucune image Docker configuree"})
        else:
            # docker_image can be a Dockerfile name (e.g. "Dockerfile.claude-code") or an image name
            # Convert Dockerfile name to image prefix: agflow-{label}
            check_name = img
            if img.startswith("Dockerfile"):
                dot_idx = img.find(".")
                label = img[dot_idx + 1:] if dot_idx >= 0 else img
                check_name = f"agflow-{label.lower()}"
            try:
                r = subprocess.run(["docker", "images", "--filter", f"reference={check_name}", "-q"],
                                   capture_output=True, timeout=5, text=True)
                if r.returncode != 0 or not r.stdout.strip():
                    issues.append({"level": "warning", "category": "agents", "message": f"Agent '{aid}' : image Docker '{img}' non compilee"})
            except Exception:
                issues.append({"level": "warning", "category": "agents", "message": f"Agent '{aid}' : impossible de verifier l'image Docker '{img}'"})

    # 4b. Check orchestrator_prompt.md exists for each team
    for tcfg in teams:
        tid = tcfg.get("id", "")
        directory = tcfg.get("directory", tid)
        stdir = SHARED_TEAMS_DIR / directory
        if stdir.exists() and not (stdir / "orchestrator_prompt.md").exists():
            issues.append({"level": "error", "category": "agents", "message": f"Equipe '{tid}' : orchestrator_prompt.md manquant — construisez-le depuis Templates > Equipes"})

    # 5. System prompts contain illustrative JSON examples with placeholders — skip validation

    errors = [i for i in issues if i["level"] == "error"]
    warnings = [i for i in issues if i["level"] == "warning"]
    return {"ok": len(errors) == 0, "errors": errors, "warnings": warnings, "total": len(issues)}


# ── API: Cultures ─────────────────────────────────

CULTURES_FILE = SHARED_DIR / "cultures.json"
_CULTURE = os.getenv("CULTURE", "fr-fr")


def _load_cultures() -> list:
    if CULTURES_FILE.exists():
        return json.loads(CULTURES_FILE.read_text(encoding="utf-8")).get("cultures", [])
    return []


def _save_cultures(cultures: list):
    CULTURES_FILE.parent.mkdir(parents=True, exist_ok=True)
    CULTURES_FILE.write_text(json.dumps({"cultures": cultures}, indent=2, ensure_ascii=False), encoding="utf-8")


@app.get("/api/templates/cultures")
async def list_cultures():
    """List all cultures. Returns all (reference) and which are enabled."""
    return {"cultures": _load_cultures(), "default": _CULTURE}


class CultureToggle(BaseModel):
    enabled: bool


@app.put("/api/templates/cultures/{key}")
async def toggle_culture(key: str, body: CultureToggle):
    """Enable or disable a culture."""
    cultures = _load_cultures()
    found = False
    for c in cultures:
        if c["key"] == key:
            c["enabled"] = body.enabled
            found = True
            break
    if not found:
        raise HTTPException(404, f"Culture '{key}' introuvable")
    _save_cultures(cultures)
    return {"ok": True}


# ── API: I18n Translations (Shared/i18n/{culture}.json) ───────────

I18N_DIR = SHARED_DIR / "i18n"


def _i18n_path(culture: str) -> Path:
    if ".." in culture or "/" in culture or "\\" in culture:
        raise HTTPException(400, "Culture invalide")
    return I18N_DIR / f"{culture}.json"


def _load_i18n(culture: str) -> dict:
    p = _i18n_path(culture)
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    return {}


def _save_i18n(culture: str, data: dict):
    I18N_DIR.mkdir(parents=True, exist_ok=True)
    p = _i18n_path(culture)
    p.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


@app.get("/api/templates/i18n")
async def list_i18n(culture: str | None = None):
    c = culture or _CULTURE
    translations = _load_i18n(c)
    default_translations = _load_i18n(_CULTURE) if c != _CULTURE else translations
    return {
        "culture": c,
        "translations": translations,
        "default_keys": sorted(default_translations.keys()),
    }


class I18nValue(BaseModel):
    value: str


@app.put("/api/templates/i18n/{key:path}")
async def set_i18n(key: str, body: I18nValue, culture: str | None = None):
    c = culture or _CULTURE
    data = _load_i18n(c)
    data[key] = body.value
    _save_i18n(c, data)
    return {"ok": True}


@app.delete("/api/templates/i18n/{key:path}")
async def delete_i18n(key: str, culture: str | None = None):
    c = culture or _CULTURE
    data = _load_i18n(c)
    if key not in data:
        raise HTTPException(404, f"Cle '{key}' introuvable")
    del data[key]
    _save_i18n(c, data)
    return {"ok": True}


# ── API: Prompt Templates & Generation ───────────

PROMPTS_BASE = SHARED_DIR / "Prompts"
PROMPTS_DIR = PROMPTS_BASE / _CULTURE  # default culture for legacy endpoint


def _prompts_dir(culture: str | None = None) -> Path:
    """Return the prompts directory for a given culture (validated)."""
    c = culture or _CULTURE
    if ".." in c or "/" in c or "\\" in c:
        raise HTTPException(400, "Culture invalide")
    return PROMPTS_BASE / c


# ── API: Deliverable Types (Shared/deliverable_types.json) ─────

DELIVERABLE_TYPES_FILE = SHARED_DIR / "deliverable_types.json"

# Default deliverable types (seeded on first read)
_DEFAULT_DELIVERABLE_TYPES = [
    {"key": "delivers_docs", "label": "Documentation"},
    {"key": "delivers_code", "label": "Code"},
    {"key": "delivers_design", "label": "Maquette & Design"},
    {"key": "delivers_automation", "label": "Automatisme"},
    {"key": "delivers_tasklist", "label": "Liste de taches"},
    {"key": "delivers_specs", "label": "Specifications & Contrat"},
]


def _load_deliverable_types() -> list[dict]:
    if DELIVERABLE_TYPES_FILE.exists():
        return json.loads(DELIVERABLE_TYPES_FILE.read_text(encoding="utf-8"))
    # Seed with defaults
    _save_deliverable_types(_DEFAULT_DELIVERABLE_TYPES)
    return list(_DEFAULT_DELIVERABLE_TYPES)


def _save_deliverable_types(types: list[dict]):
    DELIVERABLE_TYPES_FILE.write_text(json.dumps(types, indent=2, ensure_ascii=False), encoding="utf-8")


@app.get("/api/templates/deliverable-types")
async def list_deliverable_types():
    return {"types": _load_deliverable_types()}


class DeliverableTypeCreate(BaseModel):
    key: str
    label: str


@app.post("/api/templates/deliverable-types")
async def create_deliverable_type(entry: DeliverableTypeCreate):
    key = entry.key.strip()
    label = entry.label.strip()
    if not key or not key.replace("_", "").isalnum():
        raise HTTPException(400, "Cle invalide")
    types = _load_deliverable_types()
    if any(t["key"] == key for t in types):
        raise HTTPException(409, f"Le type '{key}' existe deja")
    types.append({"key": key, "label": label})
    _save_deliverable_types(types)
    return {"ok": True}


@app.delete("/api/templates/deliverable-types/{key}")
async def delete_deliverable_type(key: str):
    types = _load_deliverable_types()
    new_types = [t for t in types if t["key"] != key]
    if len(new_types) == len(types):
        raise HTTPException(404, f"Type '{key}' introuvable")
    _save_deliverable_types(new_types)
    return {"ok": True}


CFG_PROMPTS_BASE = CONFIGS / "Prompts"


def _resolve_prompts_dir(base: Path, culture: str | None = None) -> Path:
    c = culture or _CULTURE
    if ".." in c or "/" in c or "\\" in c:
        raise HTTPException(400, "Culture invalide")
    return base / c


def _list_prompts(base: Path, culture: str | None = None) -> list:
    d = _resolve_prompts_dir(base, culture)
    d.mkdir(parents=True, exist_ok=True)
    return [{"name": f.name, "content": f.read_text(encoding="utf-8")} for f in sorted(d.glob("*.md"))]


class PromptTemplateUpdate(BaseModel):
    content: str


def _put_prompt(base: Path, name: str, content: str, culture: str | None = None):
    _name_check_md(name)
    d = _resolve_prompts_dir(base, culture)
    d.mkdir(parents=True, exist_ok=True)
    (d / name).write_text(content, encoding="utf-8")
    return {"ok": True}


def _delete_prompt(base: Path, name: str, culture: str | None = None):
    if ".." in name or "/" in name or "\\" in name:
        raise HTTPException(400, "Nom invalide")
    path = _resolve_prompts_dir(base, culture) / name
    if not path.exists():
        raise HTTPException(404, f"Prompt '{name}' introuvable")
    path.unlink()
    return {"ok": True}


# Configuration (Templates) routes
@app.get("/api/templates/prompts")
async def list_template_prompts(culture: str | None = None):
    return {"culture": culture or _CULTURE, "prompts": _list_prompts(PROMPTS_BASE, culture)}

@app.get("/api/templates/prompts/{name}")
async def get_template_prompt(name: str, culture: str | None = None):
    if ".." in name or "/" in name or "\\" in name:
        raise HTTPException(400, "Nom invalide")
    path = _resolve_prompts_dir(PROMPTS_BASE, culture) / name
    if not path.exists():
        raise HTTPException(404, f"Prompt '{name}' introuvable")
    return {"name": name, "content": path.read_text(encoding="utf-8")}

@app.put("/api/templates/prompts/{name}")
async def put_template_prompt(name: str, body: PromptTemplateUpdate, culture: str | None = None):
    return _put_prompt(PROMPTS_BASE, name, body.content, culture)

@app.delete("/api/templates/prompts/{name}")
async def delete_template_prompt(name: str, culture: str | None = None):
    return _delete_prompt(PROMPTS_BASE, name, culture)


# Production routes
@app.get("/api/prod-prompts")
async def list_prod_prompts(culture: str | None = None):
    return {"culture": culture or _CULTURE, "prompts": _list_prompts(CFG_PROMPTS_BASE, culture)}

@app.put("/api/prod-prompts/{name}")
async def put_prod_prompt(name: str, body: PromptTemplateUpdate, culture: str | None = None):
    return _put_prompt(CFG_PROMPTS_BASE, name, body.content, culture)

@app.delete("/api/prod-prompts/{name}")
async def delete_prod_prompt(name: str, culture: str | None = None):
    return _delete_prompt(CFG_PROMPTS_BASE, name, culture)

@app.post("/api/prod-prompts/copy-from-config")
async def copy_prod_prompts_from_config(request: Request, culture: str | None = None):
    """Copy selected prompt files from Shared/Prompts/ to config/Prompts/."""
    body = await request.json()
    names = body.get("names", [])
    if not names:
        raise HTTPException(400, "Aucun prompt selectionne")
    src_dir = _resolve_prompts_dir(PROMPTS_BASE, culture)
    dst_dir = _resolve_prompts_dir(CFG_PROMPTS_BASE, culture)
    dst_dir.mkdir(parents=True, exist_ok=True)
    copied = 0
    for name in names:
        src = src_dir / name
        if src.exists():
            shutil.copy2(src, dst_dir / name)
            copied += 1
    return {"ok": True, "copied": copied}


# ── API: Models (factorized for templates + production) ─────────────

MODELS_BASE = SHARED_DIR / "Models"
CFG_MODELS_BASE = CONFIGS / "Models"


def _resolve_models_dir(base: Path, culture: str | None = None) -> Path:
    c = culture or _CULTURE
    if ".." in c or "/" in c or "\\" in c:
        raise HTTPException(400, "Culture invalide")
    return base / c


def _list_models(base: Path, culture: str | None = None) -> list:
    d = _resolve_models_dir(base, culture)
    d.mkdir(parents=True, exist_ok=True)
    return [{"name": f.name, "content": f.read_text(encoding="utf-8")} for f in sorted(d.glob("*.md"))]


def _name_check_md(name: str):
    if ".." in name or "/" in name or "\\" in name:
        raise HTTPException(400, "Nom invalide")
    if not name.endswith(".md"):
        raise HTTPException(400, "Le nom doit finir par .md")


class ModelTemplateUpdate(BaseModel):
    content: str


def _put_model(base: Path, name: str, content: str, culture: str | None = None):
    _name_check_md(name)
    d = _resolve_models_dir(base, culture)
    d.mkdir(parents=True, exist_ok=True)
    (d / name).write_text(content, encoding="utf-8")
    return {"ok": True}


def _delete_model(base: Path, name: str, culture: str | None = None):
    if ".." in name or "/" in name or "\\" in name:
        raise HTTPException(400, "Nom invalide")
    path = _resolve_models_dir(base, culture) / name
    if not path.exists():
        raise HTTPException(404, f"Model '{name}' introuvable")
    path.unlink()
    return {"ok": True}


# Keep legacy helper for other code using _models_dir
def _models_dir(culture: str | None = None) -> Path:
    return _resolve_models_dir(MODELS_BASE, culture)


# Configuration (Templates) routes
@app.get("/api/templates/models")
async def list_template_models(culture: str | None = None):
    return {"culture": culture or _CULTURE, "models": _list_models(MODELS_BASE, culture)}

@app.get("/api/templates/models/{name}")
async def get_template_model(name: str, culture: str | None = None):
    if ".." in name or "/" in name or "\\" in name:
        raise HTTPException(400, "Nom invalide")
    path = _resolve_models_dir(MODELS_BASE, culture) / name
    if not path.exists():
        raise HTTPException(404, f"Model '{name}' introuvable")
    return {"name": name, "content": path.read_text(encoding="utf-8")}

@app.put("/api/templates/models/{name}")
async def put_template_model(name: str, body: ModelTemplateUpdate, culture: str | None = None):
    return _put_model(MODELS_BASE, name, body.content, culture)

@app.delete("/api/templates/models/{name}")
async def delete_template_model(name: str, culture: str | None = None):
    return _delete_model(MODELS_BASE, name, culture)


# Production routes
@app.get("/api/prod-models")
async def list_prod_models(culture: str | None = None):
    return {"culture": culture or _CULTURE, "models": _list_models(CFG_MODELS_BASE, culture)}

@app.put("/api/prod-models/{name}")
async def put_prod_model(name: str, body: ModelTemplateUpdate, culture: str | None = None):
    return _put_model(CFG_MODELS_BASE, name, body.content, culture)

@app.delete("/api/prod-models/{name}")
async def delete_prod_model(name: str, culture: str | None = None):
    return _delete_model(CFG_MODELS_BASE, name, culture)

@app.post("/api/prod-models/copy-from-config")
async def copy_prod_models_from_config(request: Request, culture: str | None = None):
    """Copy selected model files from Shared/Models/ to config/Models/."""
    body = await request.json()
    names = body.get("names", [])
    if not names:
        raise HTTPException(400, "Aucun model selectionne")
    src_dir = _resolve_models_dir(MODELS_BASE, culture)
    dst_dir = _resolve_models_dir(CFG_MODELS_BASE, culture)
    dst_dir.mkdir(parents=True, exist_ok=True)
    copied = 0
    for name in names:
        src = src_dir / name
        if src.exists():
            shutil.copy2(src, dst_dir / name)
            copied += 1
    return {"ok": True, "copied": copied}


# ── API: Dockerfiles (factorized for templates + production) ─────


DOCKERFILES_DIR = SHARED_DIR / "Dockerfiles"
CFG_DOCKERFILES_DIR = CONFIGS / "Dockerfiles"

_DOCKERFILES_DIRS = {"templates": DOCKERFILES_DIR, "production": CFG_DOCKERFILES_DIR}


def _dockerfile_name_check(name: str):
    if ".." in name or "/" in name or "\\" in name:
        raise HTTPException(400, "Nom invalide")


def _list_dockerfiles(base_dir: Path) -> list:
    base_dir.mkdir(parents=True, exist_ok=True)
    files = []
    for f in sorted(base_dir.iterdir()):
        if f.is_file() and f.name.startswith("Dockerfile"):
            dot_idx = f.name.find(".")
            label = f.name[dot_idx + 1:] if dot_idx >= 0 else f.name
            ep_path = base_dir / f"entrypoint.{label}.sh"
            df_content = f.read_text(encoding="utf-8")
            ep_content = ep_path.read_text(encoding="utf-8") if ep_path.exists() else ""
            content_hash = hashlib.sha256((df_content + ep_content).encode("utf-8")).hexdigest()[:8]
            image_tag = f"agflow-{label.lower()}:{content_hash}"
            try:
                r = subprocess.run(["docker", "image", "inspect", image_tag], capture_output=True, timeout=5)
                image_built = r.returncode == 0
            except Exception:
                image_built = False
            files.append({"name": f.name, "content": df_content, "entrypoint_name": f"entrypoint.{label}.sh", "entrypoint_content": ep_content, "image_tag": image_tag, "image_built": image_built})
    return files


def _get_dockerfile(base_dir: Path, name: str) -> dict:
    _dockerfile_name_check(name)
    path = base_dir / name
    if not path.exists():
        raise HTTPException(404, f"Dockerfile '{name}' introuvable")
    return {"name": name, "content": path.read_text(encoding="utf-8")}


class DockerfileUpdate(BaseModel):
    content: str
    entrypoint_content: str | None = None


def _put_dockerfile(base_dir: Path, name: str, body: DockerfileUpdate):
    _dockerfile_name_check(name)
    base_dir.mkdir(parents=True, exist_ok=True)
    is_new = not (base_dir / name).exists()
    (base_dir / name).write_text(body.content, encoding="utf-8")
    dot_idx = name.find(".")
    label = name[dot_idx + 1:] if dot_idx >= 0 else name
    ep_path = base_dir / f"entrypoint.{label}.sh"
    if is_new and not ep_path.exists():
        ep_path.write_text("#!/bin/bash\nset -e\n\nexec \"$@\"\n", encoding="utf-8")
    if body.entrypoint_content is not None:
        ep_path.write_text(body.entrypoint_content, encoding="utf-8")
    return {"ok": True}


def _delete_dockerfile(base_dir: Path, name: str):
    _dockerfile_name_check(name)
    path = base_dir / name
    if not path.exists():
        raise HTTPException(404, f"Dockerfile '{name}' introuvable")
    path.unlink()
    if name.startswith("Dockerfile"):
        dot_idx = name.find(".")
        label = name[dot_idx + 1:] if dot_idx >= 0 else name
        ep_path = base_dir / f"entrypoint.{label}.sh"
        if ep_path.exists():
            ep_path.unlink()
    return {"ok": True}


def _build_dockerfile_info(base_dir: Path, name: str):
    _dockerfile_name_check(name)
    dockerfile_path = base_dir / name
    if not dockerfile_path.exists():
        raise HTTPException(404, f"Dockerfile '{name}' introuvable")
    dot_idx = name.find(".")
    tag = name[dot_idx + 1:] if dot_idx >= 0 else "default"
    df_content = dockerfile_path.read_text(encoding="utf-8")
    ep_path = base_dir / f"entrypoint.{tag}.sh"
    ep_content = ep_path.read_text(encoding="utf-8") if ep_path.exists() else ""
    content_hash = hashlib.sha256((df_content + ep_content).encode("utf-8")).hexdigest()[:8]
    image_name = f"agflow-{tag.lower()}:{content_hash}"
    return base_dir, image_name, name


# Templates routes
@app.get("/api/templates/dockerfiles")
async def list_template_dockerfiles():
    return {"files": _list_dockerfiles(DOCKERFILES_DIR)}

@app.get("/api/templates/dockerfiles/{name}")
async def get_template_dockerfile(name: str):
    return _get_dockerfile(DOCKERFILES_DIR, name)

@app.put("/api/templates/dockerfiles/{name}")
async def put_template_dockerfile(name: str, body: DockerfileUpdate):
    return _put_dockerfile(DOCKERFILES_DIR, name, body)

@app.delete("/api/templates/dockerfiles/{name}")
async def delete_template_dockerfile(name: str):
    return _delete_dockerfile(DOCKERFILES_DIR, name)

@app.post("/api/templates/dockerfiles/{name}/build")
async def build_template_dockerfile(name: str, no_cache: bool = False):
    return _stream_docker_build(DOCKERFILES_DIR, name, no_cache)

# Production routes
@app.get("/api/dockerfiles")
async def list_prod_dockerfiles():
    return {"files": _list_dockerfiles(CFG_DOCKERFILES_DIR)}

@app.get("/api/dockerfiles/{name}")
async def get_prod_dockerfile(name: str):
    return _get_dockerfile(CFG_DOCKERFILES_DIR, name)

@app.put("/api/dockerfiles/{name}")
async def put_prod_dockerfile(name: str, body: DockerfileUpdate):
    return _put_dockerfile(CFG_DOCKERFILES_DIR, name, body)

@app.delete("/api/dockerfiles/{name}")
async def delete_prod_dockerfile(name: str):
    return _delete_dockerfile(CFG_DOCKERFILES_DIR, name)

@app.post("/api/dockerfiles/{name}/build")
async def build_prod_dockerfile(name: str, no_cache: bool = False):
    return _stream_docker_build(CFG_DOCKERFILES_DIR, name, no_cache)


def _stream_docker_build(base_dir: Path, name: str, no_cache: bool):
    base_dir, image_name, name = _build_dockerfile_info(base_dir, name)
    _err_words = ("error", "failed", "invalid", "denied", "not found", "cannot", "fatal", "COPY failed")

    async def stream_build():
        try:
            cmd = ["docker", "build", "-f", name, "-t", image_name]
            if no_cache:
                cmd.append("--no-cache")
            cmd.append(".")
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
                cwd=str(base_dir),
            )
            async for raw in proc.stdout:
                text = raw.decode("utf-8", errors="replace").rstrip()
                if text:
                    is_err = any(p in text for p in _err_words)
                    yield f"data: {json.dumps({'line': text, 'error': is_err})}\n\n"
            await proc.wait()
            yield f"data: {json.dumps({'done': True, 'ok': proc.returncode == 0, 'image': image_name})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'done': True, 'ok': False, 'error': str(e)})}\n\n"

    return StreamingResponse(stream_build(), media_type="text/event-stream", headers={"Cache-Control": "no-store"})


# ── API: Template Projects (Shared/Projects/) ─────────────

SHARED_PROJECTS_DIR = SHARED_DIR / "Projects"
CFG_PROJECTS_DIR = CONFIGS / "Projects"


def _list_projects(base_dir: Path) -> list:
    projects = []
    if base_dir.exists():
        for d in sorted(base_dir.iterdir()):
            if d.is_dir():
                cfg_file = d / "project.json"
                cfg = json.loads(cfg_file.read_text(encoding="utf-8")) if cfg_file.exists() else {}
                workflows = [f.stem.removesuffix(".wrk") for f in sorted(d.glob("*.wrk.json"))]
                projects.append({"id": d.name, "name": cfg.get("name", d.name), "description": cfg.get("description", ""), "team": cfg.get("team", ""), "embedding_provider": cfg.get("embedding_provider", ""), "workflows": workflows})
    return projects


class ProjectCreate(BaseModel):
    id: str
    name: str
    description: str = ""
    team: str = ""


class ProjectUpdate(BaseModel):
    name: str
    description: str = ""
    team: str = ""
    embedding_provider: str = ""


def _create_project(base_dir: Path, entry: ProjectCreate):
    pid = entry.id.strip()
    if not pid or not pid.replace("_", "").replace("-", "").isalnum():
        raise HTTPException(400, "ID invalide (lettres, chiffres, _, - uniquement)")
    project_dir = base_dir / pid
    if project_dir.exists():
        raise HTTPException(409, f"Le projet '{pid}' existe deja")
    project_dir.mkdir(parents=True)
    cfg = {"name": entry.name.strip(), "description": entry.description.strip(), "team": entry.team.strip()}
    (project_dir / "project.json").write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")
    return {"ok": True}


def _update_project(base_dir: Path, project_id: str, entry: ProjectUpdate):
    if ".." in project_id or "/" in project_id or "\\" in project_id:
        raise HTTPException(400, "ID invalide")
    project_dir = base_dir / project_id
    if not project_dir.exists():
        raise HTTPException(404, f"Projet '{project_id}' introuvable")
    cfg_file = project_dir / "project.json"
    cfg = json.loads(cfg_file.read_text(encoding="utf-8")) if cfg_file.exists() else {}
    cfg["name"] = entry.name.strip()
    cfg["description"] = entry.description.strip()
    cfg["team"] = entry.team.strip()
    if entry.embedding_provider:
        cfg["embedding_provider"] = entry.embedding_provider.strip()
    elif "embedding_provider" in cfg and not entry.embedding_provider:
        del cfg["embedding_provider"]
    cfg_file.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")
    return {"ok": True}


def _update_project_chats(base_dir: Path, project_id: str, chats: list, models_base: Path = MODELS_BASE):
    if ".." in project_id or "/" in project_id or "\\" in project_id:
        raise HTTPException(400, "ID invalide")
    project_dir = base_dir / project_id
    if not project_dir.exists():
        raise HTTPException(404, f"Projet '{project_id}' introuvable")
    cfg_file = project_dir / "project.json"
    cfg = json.loads(cfg_file.read_text(encoding="utf-8")) if cfg_file.exists() else {}
    team_id = cfg.get("team", "")
    culture = os.getenv("CULTURE", "fr-fr")
    errors = []
    for chat in chats:
        chat_id = chat.get("id", "")
        chat_type = chat.get("type", "onboarding")
        source_prompt = chat.get("source_prompt", "")
        agents = chat.get("agents", [])
        if not chat_id or not source_prompt:
            continue
        # Load source prompt template
        prompt_path = models_base / culture / source_prompt
        if not prompt_path.exists():
            errors.append(f"Prompt introuvable : Shared/Models/{culture}/{source_prompt}")
            continue
        template = prompt_path.read_text(encoding="utf-8")
        # Build {agents} from orch_{agent_id}.md
        agents_parts = []
        for aid in agents:
            orch_path = SHARED_TEAMS_DIR / team_id / f"orch_{aid}.md"
            if not orch_path.exists():
                errors.append(f"Fichier manquant : Shared/Teams/{team_id}/orch_{aid}.md")
                continue
            agents_parts.append(orch_path.read_text(encoding="utf-8"))
        agents_content = "\n\n".join(agents_parts) if agents_parts else "(aucun agent)"
        # Resolve template
        content = template.replace("{agents}", agents_content)
        # Write local prompt file
        local_name = f"{chat_id}.{chat_type}.md"
        (project_dir / local_name).write_text(content, encoding="utf-8")
        chat["prompt"] = local_name
        # ── Generate per-agent prompt files ──
        source_agent_prompt = chat.get("source_agent_prompt", "prompt-delivrable.md")
        deliv_template_path = models_base / culture / source_agent_prompt
        if not deliv_template_path.exists():
            errors.append(f"Model introuvable : Shared/Models/{culture}/{source_agent_prompt}")
        else:
            deliv_template = deliv_template_path.read_text(encoding="utf-8")
            agent_config = chat.get("agent_config", {})
            agent_prompts = {}
            for aid in agents:
                agent_dir = SHARED_AGENTS_DIR / aid
                cfg_a = agent_config.get(aid, {})
                # Build {agent_card}: identity + roles + missions + skills
                card_parts = []
                identity_path = agent_dir / "identity.md"
                if identity_path.exists():
                    card_parts.append(identity_path.read_text(encoding="utf-8"))
                for r in cfg_a.get("roles", []):
                    rp = agent_dir / f"role_{r}.md"
                    if rp.exists():
                        card_parts.append(rp.read_text(encoding="utf-8"))
                for m in cfg_a.get("missions", []):
                    mp = agent_dir / f"mission_{m}.md"
                    if mp.exists():
                        card_parts.append(mp.read_text(encoding="utf-8"))
                for s in cfg_a.get("skills", []):
                    sp = agent_dir / f"skill_{s}.md"
                    if sp.exists():
                        card_parts.append(sp.read_text(encoding="utf-8"))
                agent_card = "\n\n".join(card_parts) if card_parts else "(aucune carte agent)"
                mission_content = "Conversation avec l'utilisateur pour explorer et structurer son projet dans ton domaine d'expertise."
                project_context = f"{chat_id}\n{chat_type}"
                out = deliv_template.replace("{project_context}", project_context)
                out = out.replace("{agent_card}", agent_card)
                out = out.replace("{mission}", mission_content)
                out = out.replace("{deliverable}", mission_content)
                agent_fname = f"{chat_id}.{chat_type}.{aid}.md"
                (project_dir / agent_fname).write_text(out, encoding="utf-8")
                agent_prompts[aid] = agent_fname
            chat["agent_prompts"] = agent_prompts
    cfg["chats"] = chats
    cfg_file.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")
    if errors:
        raise HTTPException(400, "\n".join(errors))
    return {"ok": True}


def _delete_project(base_dir: Path, project_id: str):
    if ".." in project_id or "/" in project_id or "\\" in project_id:
        raise HTTPException(400, "ID invalide")
    project_dir = base_dir / project_id
    if not project_dir.exists():
        raise HTTPException(404, f"Projet '{project_id}' introuvable")
    shutil.rmtree(project_dir)
    return {"ok": True}


# Configuration (Templates) routes
@app.get("/api/templates/projects")
async def list_template_projects():
    return {"projects": _list_projects(SHARED_PROJECTS_DIR)}

@app.post("/api/templates/projects")
async def create_template_project(entry: ProjectCreate):
    return _create_project(SHARED_PROJECTS_DIR, entry)

@app.put("/api/templates/projects/{project_id}")
async def update_template_project(project_id: str, entry: ProjectUpdate):
    return _update_project(SHARED_PROJECTS_DIR, project_id, entry)

@app.delete("/api/templates/projects/{project_id}")
async def delete_template_project(project_id: str):
    return _delete_project(SHARED_PROJECTS_DIR, project_id)

@app.put("/api/templates/projects/{project_id}/chats")
async def update_template_project_chats(project_id: str, request: Request):
    data = await request.json()
    return _update_project_chats(SHARED_PROJECTS_DIR, project_id, data.get("chats", []))

@app.get("/api/templates/projects/{project_id}/chat-prompt/{filename}")
async def read_template_chat_prompt(project_id: str, filename: str):
    project_dir = _project_dir_or_404(project_id)
    if ".." in filename or "/" in filename or "\\" in filename:
        raise HTTPException(400, "Nom de fichier invalide")
    filepath = project_dir / filename
    if not filepath.exists():
        raise HTTPException(404, "Fichier prompt introuvable")
    return {"filename": filename, "content": filepath.read_text(encoding="utf-8")}


# Production routes
@app.get("/api/prod-projects")
async def list_prod_projects():
    return {"projects": _list_projects(CFG_PROJECTS_DIR)}

@app.post("/api/prod-projects")
async def create_prod_project(entry: ProjectCreate):
    return _create_project(CFG_PROJECTS_DIR, entry)

@app.put("/api/prod-projects/{project_id}")
async def update_prod_project(project_id: str, entry: ProjectUpdate):
    return _update_project(CFG_PROJECTS_DIR, project_id, entry)

@app.delete("/api/prod-projects/{project_id}")
async def delete_prod_project(project_id: str):
    return _delete_project(CFG_PROJECTS_DIR, project_id)

@app.put("/api/prod-projects/{project_id}/chats")
async def update_prod_project_chats(project_id: str, request: Request):
    data = await request.json()
    return _update_project_chats(CFG_PROJECTS_DIR, project_id, data.get("chats", []), models_base=CFG_MODELS_BASE)

@app.get("/api/prod-projects/{project_id}/chat-prompt/{filename}")
async def read_prod_chat_prompt(project_id: str, filename: str):
    project_dir = _cfg_project_dir_or_404(project_id)
    if ".." in filename or "/" in filename or "\\" in filename:
        raise HTTPException(400, "Nom de fichier invalide")
    filepath = project_dir / filename
    if not filepath.exists():
        raise HTTPException(404, "Fichier prompt introuvable")
    return {"filename": filename, "content": filepath.read_text(encoding="utf-8")}

@app.post("/api/prod-projects/copy-from-config")
async def copy_prod_projects_from_config(request: Request):
    """Copy selected project directories from Shared/Projects/ to config/Projects/."""
    body = await request.json()
    project_ids = body.get("project_ids", [])
    if not project_ids:
        raise HTTPException(400, "Aucun projet selectionne")
    CFG_PROJECTS_DIR.mkdir(parents=True, exist_ok=True)
    copied = 0
    for pid in project_ids:
        src = SHARED_PROJECTS_DIR / pid
        if not src.exists():
            continue
        dst = CFG_PROJECTS_DIR / pid
        if dst.exists():
            shutil.rmtree(dst)
        shutil.copytree(src, dst)
        copied += 1
    return {"ok": True, "copied": copied}


def _project_dir_or_404(project_id: str) -> Path:
    if ".." in project_id or "/" in project_id or "\\" in project_id:
        raise HTTPException(400, "ID invalide")
    d = SHARED_PROJECTS_DIR / project_id
    if not d.exists():
        raise HTTPException(404, f"Projet '{project_id}' introuvable")
    return d


def _cfg_project_dir_or_404(project_id: str) -> Path:
    if ".." in project_id or "/" in project_id or "\\" in project_id:
        raise HTTPException(400, "ID invalide")
    d = CFG_PROJECTS_DIR / project_id
    if not d.exists():
        raise HTTPException(404, f"Projet '{project_id}' introuvable")
    return d


def _wf_name_safe(name: str) -> str:
    if ".." in name or "/" in name or "\\" in name or not name.replace("_", "").replace("-", "").isalnum():
        raise HTTPException(400, "Nom de workflow invalide")
    return name


class WorkflowCreate(BaseModel):
    name: str
    team: str = ""


@app.post("/api/templates/projects/{project_id}/workflows")
async def create_project_workflow(project_id: str, entry: WorkflowCreate):
    project_dir = _project_dir_or_404(project_id)
    name = _wf_name_safe(entry.name.strip())
    wf = project_dir / f"{name}.wrk.json"
    if wf.exists():
        raise HTTPException(409, f"Le workflow '{name}' existe deja")
    data = {"phases": {}}
    if entry.team.strip():
        data["team"] = entry.team.strip()
    wf.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return {"ok": True}


class WorkflowGenerate(BaseModel):
    name: str
    prompt: str
    team: str = ""


@app.post("/api/templates/projects/{project_id}/workflows/generate")
async def generate_project_workflow(project_id: str, entry: WorkflowGenerate):
    """Generate a workflow using CreateWorkflow.md system prompt and save it."""
    import re as _re
    project_dir = _project_dir_or_404(project_id)
    name = _wf_name_safe(entry.name.strip())
    wf_path = project_dir / f"{name}.wrk.json"
    if wf_path.exists():
        raise HTTPException(409, f"Le workflow '{name}' existe deja")

    # Load system prompt template
    meta_path = PROMPTS_DIR / "CreateWorkflow.md"
    if not meta_path.exists():
        raise HTTPException(500, "Meta-prompt CreateWorkflow.md introuvable")
    system_template = meta_path.read_text(encoding="utf-8")

    # Build {project_prompt} from project.json + user prompt
    cfg_file = project_dir / "project.json"
    project_cfg = json.loads(cfg_file.read_text(encoding="utf-8")) if cfg_file.exists() else {}
    project_prompt_parts = []
    if project_cfg.get("name"):
        project_prompt_parts.append(f"Nom du projet : {project_cfg['name']}")
    if project_cfg.get("description"):
        project_prompt_parts.append(f"Description : {project_cfg['description']}")
    if project_cfg.get("team"):
        project_prompt_parts.append(f"Equipe : {project_cfg['team']}")
    project_prompt_parts.append(entry.prompt.strip())
    project_prompt = "\n".join(project_prompt_parts)

    # Build {available_agents} from team registry + Shared/Agents/{agent_id}/
    agents_parts = []
    _team_id = entry.team or project_cfg.get("team", "")
    _team_dir = None
    if _team_id and SHARED_TEAMS_FILE.exists():
        _teams_cfg = json.loads(SHARED_TEAMS_FILE.read_text(encoding="utf-8"))
        for t in _teams_cfg.get("teams", []):
            if t["id"].lower() == _team_id.lower():
                _team_dir = SHARED_TEAMS_DIR / t["directory"]
                break
    # Read team agents_registry.json
    _registry_agents = {}
    if _team_dir:
        _reg_file = _team_dir / "agents_registry.json"
        if _reg_file.exists():
            _registry_agents = json.loads(_reg_file.read_text(encoding="utf-8")).get("agents", {})
    # Build available_agents from registry
    for agent_id in sorted(_registry_agents):
        acfg_reg = _registry_agents[agent_id]
        if acfg_reg.get("type") == "orchestrator":
            continue
        sa_dir = SHARED_AGENTS_DIR / agent_id
        lines = [f"- **{agent_id}**"]
        # Description from Shared/Agents/{agent_id}/agent.json
        agent_json = sa_dir / "agent.json" if sa_dir.is_dir() else None
        if agent_json and agent_json.exists():
            acfg = json.loads(agent_json.read_text(encoding="utf-8"))
            desc = acfg.get("description", "")
            if desc:
                lines[0] += f" : {desc}"
        lines.append("")
        agents_parts.append("\n".join(lines))
    available_agents = "\n\n".join(agents_parts) if agents_parts else "(aucun agent disponible)"

    # Build {workflow_spec} from docs/workflow-model.md
    specs_path = PROJECT_DIR / "docs" / "workflow-model.md"
    if not specs_path.exists():
        specs_path = Path(__file__).resolve().parent.parent / "docs" / "workflow-model.md"
    workflow_spec = specs_path.read_text(encoding="utf-8") if specs_path.exists() else "(specifications non disponibles)"

    # Inject placeholders
    team_id = entry.team or project_cfg.get("team", "")
    system_prompt = system_template.replace("{project_prompt}", project_prompt).replace("{team_id}", team_id).replace("{available_agents}", available_agents).replace("{workflow_spec}", workflow_spec)
    user_msg = "Genere le workflow complet pour ce projet. Retourne uniquement le JSON."

    # Trace: save prompt to project chat directory
    from datetime import datetime as _dt
    chat_dir = project_dir / "chat"
    chat_dir.mkdir(exist_ok=True)
    ts = _dt.now().strftime("%y%m%d-%H%M%S")
    trace_content = f"# System Prompt\n\n{system_prompt}\n\n# User Message\n\n{user_msg}\n"
    (chat_dir / f"{ts}_create.md").write_text(trace_content, encoding="utf-8")

    try:
        result = await chat(ChatRequest(messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_msg},
        ], use_admin_llm=True, scope="configuration"))
        raw = result.get("content", "")
    except Exception as e:
        raise HTTPException(500, f"Generation echouee: {e}")

    # Trace: save response
    (chat_dir / f"{ts}_response.md").write_text(raw, encoding="utf-8")

    # Extract JSON from response (handle markdown code blocks)
    json_match = _re.search(r"```(?:json)?\s*\n?(.*?)```", raw, _re.DOTALL)
    json_str = json_match.group(1).strip() if json_match else raw.strip()

    try:
        workflow_data = json.loads(json_str)
    except json.JSONDecodeError:
        raise HTTPException(422, "Le LLM n'a pas retourne un JSON valide.")

    wf_path.write_text(json.dumps(workflow_data, indent=2, ensure_ascii=False), encoding="utf-8")
    return {"ok": True, "workflow": workflow_data}


@app.get("/api/templates/projects/{project_id}/workflows/{wf_name}")
async def get_project_workflow(project_id: str, wf_name: str):
    project_dir = _project_dir_or_404(project_id)
    name = _wf_name_safe(wf_name)
    wf = project_dir / f"{name}.wrk.json"
    if not wf.exists():
        raise HTTPException(404, f"Workflow '{name}' introuvable")
    return {"name": name, "content": wf.read_text(encoding="utf-8")}


class WorkflowUpdate(BaseModel):
    content: str


@app.put("/api/templates/projects/{project_id}/workflows/{wf_name}")
async def put_project_workflow(project_id: str, wf_name: str, entry: WorkflowUpdate):
    project_dir = _project_dir_or_404(project_id)
    name = _wf_name_safe(wf_name)
    content = entry.content.strip()
    try:
        json.loads(content)
    except json.JSONDecodeError as e:
        raise HTTPException(400, f"JSON invalide: {e}")
    (project_dir / f"{name}.wrk.json").write_text(content, encoding="utf-8")
    return {"ok": True}


@app.delete("/api/templates/projects/{project_id}/workflows/{wf_name}")
async def delete_project_workflow(project_id: str, wf_name: str):
    project_dir = _project_dir_or_404(project_id)
    name = _wf_name_safe(wf_name)
    wf = project_dir / f"{name}.wrk.json"
    if not wf.exists():
        raise HTTPException(404, f"Workflow '{name}' introuvable")
    wf.unlink()
    # Also delete associated design + phase prompt files
    for f in project_dir.glob(f"{name}.wrk.design.json"):
        f.unlink()
    for f in project_dir.glob(f"{name}.wrk.phase.*.md"):
        f.unlink()
    return {"ok": True}


@app.get("/api/templates/projects/{project_id}/project-json")
async def get_project_json(project_id: str):
    """Return the raw project.json metadata (workflows with mode, priority, depends_on)."""
    project_dir = _project_dir_or_404(project_id)
    pj = project_dir / "project.json"
    if not pj.exists():
        return {"workflows": []}
    return json.loads(pj.read_text(encoding="utf-8"))


@app.get("/api/templates/projects/{project_id}/workflows/{wf_name}/phase-files")
async def list_workflow_phase_files(project_id: str, wf_name: str):
    """List .wrk.phase.{id}.md files for a workflow."""
    project_dir = _project_dir_or_404(project_id)
    name = _wf_name_safe(wf_name)
    prefix = f"{name}.wrk.phase."
    suffix = ".md"
    files = []
    for f in sorted(project_dir.iterdir()):
        if f.name.startswith(prefix) and f.name.endswith(suffix):
            phase_id = f.name[len(prefix):-len(suffix)]
            files.append({"phase_id": phase_id, "filename": f.name})
    return {"files": files}


@app.get("/api/templates/projects/{project_id}/workflows/{wf_name}/phase-files/{phase_id}")
async def read_workflow_phase_file(project_id: str, wf_name: str, phase_id: str):
    """Read a single phase prompt file."""
    project_dir = _project_dir_or_404(project_id)
    name = _wf_name_safe(wf_name)
    if ".." in phase_id or "/" in phase_id or "\\" in phase_id:
        raise HTTPException(400, "phase_id invalide")
    filepath = project_dir / f"{name}.wrk.phase.{phase_id}.md"
    if not filepath.exists():
        raise HTTPException(404, "Fichier phase introuvable")
    return {"phase_id": phase_id, "filename": filepath.name, "content": filepath.read_text(encoding="utf-8")}


@app.get("/api/templates/projects/{project_id}/workflows/{wf_name}/livr-files/{livr_id}")
async def read_workflow_livr_file(project_id: str, wf_name: str, livr_id: str):
    """Read a single deliverable prompt file."""
    project_dir = _project_dir_or_404(project_id)
    name = _wf_name_safe(wf_name)
    if ".." in livr_id or "/" in livr_id or "\\" in livr_id:
        raise HTTPException(400, "livr_id invalide")
    filepath = project_dir / f"{name}.wrk.livr.{livr_id}.md"
    if not filepath.exists():
        raise HTTPException(404, "Fichier livrable introuvable")
    return {"livr_id": livr_id, "filename": filepath.name, "content": filepath.read_text(encoding="utf-8")}


# ── API: Project Workflow — visual editor endpoints ────
# These follow the same pattern as /api/templates/workflow/{dir}
# Used by openWorkflowEditor(wfName, '/api/templates/project-workflow/{project_id}', ...)

# ── Factored workflow helpers (shared by template + prod) ──────

def _check_external_cycles(project_dir: Path, workflow_name: str, visited: set = None) -> list:
    """Detect cycles in external phase references."""
    if visited is None:
        visited = set()
    if workflow_name in visited:
        return [f"Cycle detecte: {' -> '.join(visited)} -> {workflow_name}"]
    visited = visited | {workflow_name}
    wf_path = project_dir / workflow_name
    if not wf_path.exists():
        return [f"Workflow '{workflow_name}' introuvable"]
    data = _read_json(wf_path)
    phases = data.get("phases", {})
    phase_list = list(phases.values()) if isinstance(phases, dict) else (phases if isinstance(phases, list) else [])
    errors = []
    for phase in phase_list:
        if phase.get("type") == "external":
            ext_wf = phase.get("external_workflow", "")
            if ext_wf:
                errors.extend(_check_external_cycles(project_dir, ext_wf, visited))
    return errors


def _wf_get(project_dir: Path, wf_name: str):
    """Read a {name}.wrk.json workflow file."""
    name = _wf_name_safe(wf_name)
    wf = project_dir / f"{name}.wrk.json"
    return _read_json(wf) if wf.exists() else {}


async def _wf_put(project_dir: Path, wf_name: str, request: Request):
    """Write a {name}.wrk.json workflow file with validation."""
    name = _wf_name_safe(wf_name)
    data = await request.json()
    # Strip positions — they belong in the design file
    data.pop("positions", None)
    current_file = f"{name}.wrk.json"
    # Validate external phases
    phases = data.get("phases", {})
    phase_list = list(phases.values()) if isinstance(phases, dict) else (phases if isinstance(phases, list) else [])
    for phase in phase_list:
        if phase.get("type") == "external":
            ext_wf = phase.get("external_workflow", "")
            if ext_wf:
                if ext_wf == current_file:
                    raise HTTPException(400, f"Phase '{phase.get('name', '?')}' reference le workflow courant")
                if not (project_dir / ext_wf).exists():
                    raise HTTPException(400, f"Workflow externe introuvable: {ext_wf}")
                cycle_errors = _check_external_cycles(project_dir, ext_wf, {current_file})
                if cycle_errors:
                    raise HTTPException(400, cycle_errors[0])
    _write_json(project_dir / current_file, data)
    team_id = data.get("team", "")
    _generate_phase_files(data, f"{name}.wrk", project_dir, team_id)
    return {"ok": True}


def _wf_get_design(project_dir: Path, wf_name: str):
    """Read a {name}.wrk.design.json layout file."""
    name = _wf_name_safe(wf_name)
    path = project_dir / f"{name}.wrk.design.json"
    return _read_json(path) if path.exists() else {}


async def _wf_put_design(project_dir: Path, wf_name: str, request: Request):
    """Write a {name}.wrk.design.json layout file."""
    name = _wf_name_safe(wf_name)
    data = await request.json()
    _write_json(project_dir / f"{name}.wrk.design.json", data)
    return {"ok": True}


def _wf_list_available(project_dir: Path):
    """List *.wrk.json files in a project directory."""
    results = []
    for f in sorted(project_dir.iterdir()):
        if f.suffix == ".json" and f.stem.endswith(".wrk"):
            data = _read_json(f)
            name = data.get("name", "")
            if not name:
                phases = data.get("phases", {})
                if isinstance(phases, dict) and phases:
                    first = next(iter(phases.values()))
                    name = first.get("name", f.stem)
                elif isinstance(phases, list) and phases:
                    name = phases[0].get("name", f.stem)
                else:
                    name = f.stem.replace(".wrk", "")
            results.append({"filename": f.name, "name": name})
    return results


# ── Template project workflow endpoints (Shared/Projects) ─────

@app.get("/api/templates/project-workflow/{project_id}/{wf_name}")
async def get_project_workflow_editor(project_id: str, wf_name: str):
    return _wf_get(_project_dir_or_404(project_id), wf_name)

@app.put("/api/templates/project-workflow/{project_id}/{wf_name}")
async def put_project_workflow_editor(project_id: str, wf_name: str, request: Request):
    return await _wf_put(_project_dir_or_404(project_id), wf_name, request)

@app.get("/api/templates/projects/{project_id}/available-workflows")
async def list_available_workflows(project_id: str):
    return _wf_list_available(_project_dir_or_404(project_id))

@app.get("/api/templates/project-workflow-design/{project_id}/{wf_name}")
async def get_project_workflow_design(project_id: str, wf_name: str):
    return _wf_get_design(_project_dir_or_404(project_id), wf_name)

@app.put("/api/templates/project-workflow-design/{project_id}/{wf_name}")
async def put_project_workflow_design(project_id: str, wf_name: str, request: Request):
    return await _wf_put_design(_project_dir_or_404(project_id), wf_name, request)


# ── API: Production Project Workflows ──────────────────────────

@app.post("/api/prod-projects/{project_id}/workflows")
async def create_prod_project_workflow(project_id: str, entry: WorkflowCreate):
    project_dir = _cfg_project_dir_or_404(project_id)
    name = _wf_name_safe(entry.name.strip())
    wf = project_dir / f"{name}.wrk.json"
    if wf.exists():
        raise HTTPException(409, f"Le workflow '{name}' existe deja")
    data = {"phases": {}}
    if entry.team.strip():
        data["team"] = entry.team.strip()
    wf.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return {"ok": True}


@app.post("/api/prod-projects/{project_id}/workflows/generate")
async def generate_prod_project_workflow(project_id: str, entry: WorkflowGenerate):
    """Generate a workflow for a production project."""
    import re as _re
    project_dir = _cfg_project_dir_or_404(project_id)
    name = _wf_name_safe(entry.name.strip())
    wf_path = project_dir / f"{name}.wrk.json"
    if wf_path.exists():
        raise HTTPException(409, f"Le workflow '{name}' existe deja")
    # Production: read from config/Prompts first, fallback to Shared/Prompts
    _cfg_meta = _resolve_prompts_dir(CFG_PROMPTS_BASE) / "CreateWorkflow.md"
    meta_path = _cfg_meta if _cfg_meta.exists() else PROMPTS_DIR / "CreateWorkflow.md"
    if not meta_path.exists():
        raise HTTPException(500, "Meta-prompt CreateWorkflow.md introuvable")
    system_template = meta_path.read_text(encoding="utf-8")
    cfg_file = project_dir / "project.json"
    project_cfg = json.loads(cfg_file.read_text(encoding="utf-8")) if cfg_file.exists() else {}
    project_prompt_parts = []
    if project_cfg.get("name"):
        project_prompt_parts.append(f"Nom du projet : {project_cfg['name']}")
    if project_cfg.get("description"):
        project_prompt_parts.append(f"Description : {project_cfg['description']}")
    if project_cfg.get("team"):
        project_prompt_parts.append(f"Equipe : {project_cfg['team']}")
    project_prompt_parts.append(entry.prompt.strip())
    project_prompt = "\n".join(project_prompt_parts)
    agents_parts = []
    _team_id = entry.team or project_cfg.get("team", "")
    _team_dir = None
    if _team_id and SHARED_TEAMS_FILE.exists():
        _teams_cfg = json.loads(SHARED_TEAMS_FILE.read_text(encoding="utf-8"))
        for t in _teams_cfg.get("teams", []):
            if t["id"].lower() == _team_id.lower():
                _team_dir = SHARED_TEAMS_DIR / t["directory"]
                break
    _registry_agents = {}
    if _team_dir:
        _reg_file = _team_dir / "agents_registry.json"
        if _reg_file.exists():
            _registry_agents = json.loads(_reg_file.read_text(encoding="utf-8")).get("agents", {})
    for agent_id in sorted(_registry_agents):
        acfg_reg = _registry_agents[agent_id]
        if acfg_reg.get("type") == "orchestrator":
            continue
        sa_dir = SHARED_AGENTS_DIR / agent_id
        lines = [f"- **{agent_id}**"]
        agent_json = sa_dir / "agent.json" if sa_dir.is_dir() else None
        if agent_json and agent_json.exists():
            acfg = json.loads(agent_json.read_text(encoding="utf-8"))
            desc = acfg.get("description", "")
            if desc:
                lines[0] += f" : {desc}"
        lines.append("")
        agents_parts.append("\n".join(lines))
    available_agents = "\n\n".join(agents_parts) if agents_parts else "(aucun agent disponible)"
    specs_path = PROJECT_DIR / "docs" / "workflow-model.md"
    if not specs_path.exists():
        specs_path = Path(__file__).resolve().parent.parent / "docs" / "workflow-model.md"
    workflow_spec = specs_path.read_text(encoding="utf-8") if specs_path.exists() else "(specifications non disponibles)"
    team_id = entry.team or project_cfg.get("team", "")
    system_prompt = system_template.replace("{project_prompt}", project_prompt).replace("{team_id}", team_id).replace("{available_agents}", available_agents).replace("{workflow_spec}", workflow_spec)
    user_msg = "Genere le workflow complet pour ce projet. Retourne uniquement le JSON."
    from datetime import datetime as _dt
    chat_dir = project_dir / "chat"
    chat_dir.mkdir(exist_ok=True)
    ts = _dt.now().strftime("%y%m%d-%H%M%S")
    trace_content = f"# System Prompt\n\n{system_prompt}\n\n# User Message\n\n{user_msg}\n"
    (chat_dir / f"{ts}_create.md").write_text(trace_content, encoding="utf-8")
    try:
        result = await chat(ChatRequest(messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_msg},
        ], use_admin_llm=True, scope="production"))
        raw = result.get("content", "")
    except Exception as e:
        raise HTTPException(500, f"Generation echouee: {e}")
    (chat_dir / f"{ts}_response.md").write_text(raw, encoding="utf-8")
    json_match = _re.search(r"```(?:json)?\s*\n?(.*?)```", raw, _re.DOTALL)
    json_str = json_match.group(1).strip() if json_match else raw.strip()
    try:
        workflow_data = json.loads(json_str)
    except json.JSONDecodeError:
        raise HTTPException(422, "Le LLM n'a pas retourne un JSON valide.")
    wf_path.write_text(json.dumps(workflow_data, indent=2, ensure_ascii=False), encoding="utf-8")
    return {"ok": True, "workflow": workflow_data}


@app.get("/api/prod-projects/{project_id}/workflows/{wf_name}")
async def get_prod_project_workflow(project_id: str, wf_name: str):
    project_dir = _cfg_project_dir_or_404(project_id)
    name = _wf_name_safe(wf_name)
    wf = project_dir / f"{name}.wrk.json"
    if not wf.exists():
        raise HTTPException(404, f"Workflow '{name}' introuvable")
    return {"name": name, "content": wf.read_text(encoding="utf-8")}


@app.put("/api/prod-projects/{project_id}/workflows/{wf_name}")
async def put_prod_project_workflow(project_id: str, wf_name: str, entry: WorkflowUpdate):
    project_dir = _cfg_project_dir_or_404(project_id)
    name = _wf_name_safe(wf_name)
    content = entry.content.strip()
    try:
        json.loads(content)
    except json.JSONDecodeError as e:
        raise HTTPException(400, f"JSON invalide: {e}")
    (project_dir / f"{name}.wrk.json").write_text(content, encoding="utf-8")
    return {"ok": True}


@app.delete("/api/prod-projects/{project_id}/workflows/{wf_name}")
async def delete_prod_project_workflow(project_id: str, wf_name: str):
    project_dir = _cfg_project_dir_or_404(project_id)
    name = _wf_name_safe(wf_name)
    wf = project_dir / f"{name}.wrk.json"
    if not wf.exists():
        raise HTTPException(404, f"Workflow '{name}' introuvable")
    wf.unlink()
    # Also delete associated design + phase prompt files
    for f in project_dir.glob(f"{name}.wrk.design.json"):
        f.unlink()
    for f in project_dir.glob(f"{name}.wrk.phase.*.md"):
        f.unlink()
    for f in project_dir.glob(f"{name}.wrk.livr.*.md"):
        f.unlink()
    return {"ok": True}


@app.get("/api/prod-projects/{project_id}/project-json")
async def get_prod_project_json(project_id: str):
    """Return the raw project.json metadata for a production project."""
    project_dir = _cfg_project_dir_or_404(project_id)
    pj = project_dir / "project.json"
    if not pj.exists():
        return {"workflows": []}
    return json.loads(pj.read_text(encoding="utf-8"))


@app.get("/api/prod-projects/{project_id}/workflows/{wf_name}/phase-files")
async def list_prod_workflow_phase_files(project_id: str, wf_name: str):
    """List .wrk.phase.{id}.md files for a production project workflow."""
    project_dir = _cfg_project_dir_or_404(project_id)
    name = _wf_name_safe(wf_name)
    prefix = f"{name}.wrk.phase."
    suffix = ".md"
    files = []
    for f in sorted(project_dir.iterdir()):
        if f.name.startswith(prefix) and f.name.endswith(suffix):
            phase_id = f.name[len(prefix):-len(suffix)]
            files.append({"phase_id": phase_id, "filename": f.name})
    return {"files": files}


@app.get("/api/prod-projects/{project_id}/workflows/{wf_name}/phase-files/{phase_id}")
async def read_prod_workflow_phase_file(project_id: str, wf_name: str, phase_id: str):
    """Read a single phase prompt file from a production project."""
    project_dir = _cfg_project_dir_or_404(project_id)
    name = _wf_name_safe(wf_name)
    if ".." in phase_id or "/" in phase_id or "\\" in phase_id:
        raise HTTPException(400, "phase_id invalide")
    filepath = project_dir / f"{name}.wrk.phase.{phase_id}.md"
    if not filepath.exists():
        raise HTTPException(404, "Fichier phase introuvable")
    return {"phase_id": phase_id, "filename": filepath.name, "content": filepath.read_text(encoding="utf-8")}


@app.get("/api/prod-projects/{project_id}/workflows/{wf_name}/livr-files/{livr_id}")
async def read_prod_workflow_livr_file(project_id: str, wf_name: str, livr_id: str):
    """Read a single deliverable prompt file from a production project."""
    project_dir = _cfg_project_dir_or_404(project_id)
    name = _wf_name_safe(wf_name)
    if ".." in livr_id or "/" in livr_id or "\\" in livr_id:
        raise HTTPException(400, "livr_id invalide")
    filepath = project_dir / f"{name}.wrk.livr.{livr_id}.md"
    if not filepath.exists():
        raise HTTPException(404, "Fichier livrable introuvable")
    return {"livr_id": livr_id, "filename": filepath.name, "content": filepath.read_text(encoding="utf-8")}


@app.get("/api/prod-projects/{project_id}/available-workflows")
async def list_prod_available_workflows(project_id: str):
    """List available .wrk.json files in a production project directory."""
    project_dir = _cfg_project_dir_or_404(project_id)
    workflows = []
    for f in sorted(project_dir.glob("*.wrk.json")):
        name = f.name.replace(".wrk.json", "")
        workflows.append({"name": name, "filename": f.name})
    return {"workflows": workflows}


@app.post("/api/prod-projects/{project_id}/orchestrator/build")
async def build_prod_orchestrator_prompt_endpoint(project_id: str):
    """Build orchestrator prompt for a production project's team."""
    project_dir = _cfg_project_dir_or_404(project_id)
    project_json = project_dir / "project.json"
    if not project_json.exists():
        raise HTTPException(404, "project.json introuvable")
    project_cfg = json.loads(project_json.read_text(encoding="utf-8"))
    team = project_cfg.get("team", "").strip()
    if not team:
        raise HTTPException(400, "Le projet n'a pas d'equipe (champ 'team' vide)")
    return await build_team_orchestrator_prompt(team)


# Production project workflow — visual editor endpoints (same logic, config/ dir)

@app.get("/api/prod-project-workflow/{project_id}/{wf_name}")
async def get_prod_project_workflow_editor(project_id: str, wf_name: str):
    return _wf_get(_cfg_project_dir_or_404(project_id), wf_name)

@app.put("/api/prod-project-workflow/{project_id}/{wf_name}")
async def put_prod_project_workflow_editor(project_id: str, wf_name: str, request: Request):
    return await _wf_put(_cfg_project_dir_or_404(project_id), wf_name, request)

@app.get("/api/prod-projects/{project_id}/available-workflows")
async def list_prod_available_workflows(project_id: str):
    return _wf_list_available(_cfg_project_dir_or_404(project_id))

@app.get("/api/prod-project-workflow-design/{project_id}/{wf_name}")
async def get_prod_project_workflow_design(project_id: str, wf_name: str):
    return _wf_get_design(_cfg_project_dir_or_404(project_id), wf_name)

@app.put("/api/prod-project-workflow-design/{project_id}/{wf_name}")
async def put_prod_project_workflow_design(project_id: str, wf_name: str, request: Request):
    return await _wf_put_design(_cfg_project_dir_or_404(project_id), wf_name, request)


@app.get("/api/prompts/templates/{name}")
async def get_prompt_template(name: str):
    """Return content of a prompt template (legacy, uses default culture)."""
    if ".." in name or "/" in name or "\\" in name:
        raise HTTPException(400, "Nom de template invalide")
    path = PROMPTS_DIR / f"{name}.md"
    if not path.exists():
        raise HTTPException(404, f"Template '{name}' introuvable")
    return {"content": path.read_text(encoding="utf-8")}


class GenerateMissionRequest(BaseModel):
    agent_prompt: str = ""
    step_name: str = ""
    step_key: str = ""
    current_instruction: str = ""


@app.post("/api/agents/generate-mission")
async def generate_mission(req: GenerateMissionRequest):
    """Use Missions.md meta-prompt + agent prompt + current instruction to generate a better mission."""
    meta_path = PROMPTS_DIR / "Missions.md"
    if not meta_path.exists():
        raise HTTPException(500, "Meta-prompt Missions.md introuvable")
    system_prompt = meta_path.read_text(encoding="utf-8")

    user_msg = ""
    if req.agent_prompt:
        user_msg += f"<profil>\n{req.agent_prompt[:12000]}\n</profil>\n\n"
    if req.step_name:
        user_msg += f"Etape : {req.step_name}"
        if req.step_key:
            user_msg += f" (cle: {req.step_key})"
        user_msg += "\n\n"
    user_msg += f"<mission>\n{req.current_instruction}\n</mission>\n\n"
    user_msg += "Genere l'instruction de mission optimisee. Reponds uniquement avec le contenu de l'instruction, sans bloc de code markdown, sans explication."

    chat_req = ChatRequest(messages=[
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_msg},
    ], use_admin_llm=True)
    result = await chat(chat_req)
    return {"instruction": result["content"]}


class GenerateDescriptionRequest(BaseModel):
    deliverable_key: str = ""
    current_description: str = ""
    agent_id: str = ""
    agent_name: str = ""
    deliverable_type: str = ""
    phase_name: str = ""
    project_description: str = ""
    project_id: str = ""


@app.post("/api/agents/generate-description")
async def generate_description(req: GenerateDescriptionRequest):
    """Use WriteDescription.md meta-prompt to help write a deliverable description."""
    meta_path = PROMPTS_DIR / "WriteDescription.md"
    if not meta_path.exists():
        raise HTTPException(500, "Meta-prompt WriteDescription.md introuvable")
    prompt_template = meta_path.read_text(encoding="utf-8")

    # Replace template variables
    prompt = prompt_template.replace("{deliverable_key}", req.deliverable_key)
    prompt = prompt.replace("{current_description}", req.current_description)
    prompt = prompt.replace("{agent_id}", req.agent_id)
    prompt = prompt.replace("{agent_name}", req.agent_name)
    prompt = prompt.replace("{deliverable_type}", req.deliverable_type)
    prompt = prompt.replace("{phase_name}", req.phase_name)
    prompt = prompt.replace("{project_description}", req.project_description)

    # Trace: log to project chat directory
    from datetime import datetime as _dt
    chat_dir = None
    if req.project_id:
        chat_dir = SHARED_PROJECTS_DIR / req.project_id / "chat"
        chat_dir.mkdir(parents=True, exist_ok=True)
    ts = _dt.now().strftime("%y%m%d-%H%M%S")
    if chat_dir:
        (chat_dir / f"{ts}_writedesc_send.md").write_text(prompt, encoding="utf-8")

    chat_req = ChatRequest(messages=[
        {"role": "user", "content": prompt},
    ], use_admin_llm=True)
    result = await chat(chat_req)
    raw = result.get("content", "")

    if chat_dir:
        (chat_dir / f"{ts}_writedesc_response.md").write_text(raw, encoding="utf-8")

    return {"description": raw}


class GeneratePromptRequest(BaseModel):
    agent_info: str
    agent_id: str = ""
    agent_name: str = ""


@app.post("/api/agents/generate-prompt")
async def generate_prompt(req: GeneratePromptRequest):
    """Use the default LLM to generate a structured agent prompt from user input."""
    # Load the createAgent meta-prompt as system instruction
    meta_path = PROMPTS_DIR / "createAgent.md"
    if not meta_path.exists():
        raise HTTPException(500, "Meta-prompt createAgent.md introuvable")
    system_prompt = meta_path.read_text(encoding="utf-8")

    # Build user message with context
    user_msg = ""
    if req.agent_id:
        user_msg += f"Identifiant de l'agent : {req.agent_id}\n"
    if req.agent_name:
        user_msg += f"Nom affiche : {req.agent_name}\n"
    user_msg += f"\nVoici les informations fournies par l'utilisateur :\n\n{req.agent_info}"
    user_msg += "\n\nGenere le prompt complet de l'agent en suivant la structure definie. Reponds uniquement avec le contenu du prompt Markdown, sans bloc de code, sans explication."

    # Reuse the /api/chat logic
    chat_req = ChatRequest(messages=[
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_msg},
    ], use_admin_llm=True)
    result = await chat(chat_req)
    return {"prompt": result["content"]}


class GenerateAssignRequest(BaseModel):
    agent_id: str
    agent_name: str = ""
    agent_prompt: str = ""


@app.post("/api/agents/generate-assign")
async def generate_assign(req: GenerateAssignRequest):
    """Use the default LLM to generate correct assignment routing examples."""
    meta_path = PROMPTS_DIR / "Assignations.md"
    if not meta_path.exists():
        raise HTTPException(500, "Meta-prompt Assignations.md introuvable")
    prompt_text = req.agent_prompt[:8000] if req.agent_prompt else "(aucun prompt fourni)"
    context = (
        f"<agent_prompt>\n{prompt_text}\n</agent_prompt>\n\n"
        f"Agent: {req.agent_name or req.agent_id} (id: {req.agent_id})\n"
        "Genere les exemples demandes. Reponds uniquement avec le JSON, sans bloc de code markdown, sans explication."
    )
    system_prompt = meta_path.read_text(encoding="utf-8")
    result = await chat(ChatRequest(messages=[
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": context},
    ], use_admin_llm=True))
    return {"content": result["content"]}


@app.post("/api/agents/generate-unassign")
async def generate_unassign(req: GenerateAssignRequest):
    """Use the default LLM to generate incorrect assignment routing examples."""
    meta_path = PROMPTS_DIR / "UnAssignation.md"
    if not meta_path.exists():
        raise HTTPException(500, "Meta-prompt UnAssignation.md introuvable")
    prompt_text = req.agent_prompt[:8000] if req.agent_prompt else "(aucun prompt fourni)"
    context = (
        f"<agent_prompt>\n{prompt_text}\n</agent_prompt>\n\n"
        f"Agent: {req.agent_name or req.agent_id} (id: {req.agent_id})\n"
        "Genere les exemples demandes. Reponds uniquement avec le JSON, sans bloc de code markdown, sans explication."
    )
    system_prompt = meta_path.read_text(encoding="utf-8")
    result = await chat(ChatRequest(messages=[
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": context},
    ], use_admin_llm=True))
    return {"content": result["content"]}


class SkillMatchRequest(BaseModel):
    agent_id: str
    description: str = ""


@app.post("/api/templates/projects/{project_id}/deliverable-skillmatch")
async def deliverable_skillmatch(project_id: str, req: SkillMatchRequest):
    """Use SkillMatcher.md to auto-select roles/missions/skills for a deliverable."""
    _project_dir_or_404(project_id)
    agent_dir = SHARED_AGENTS_DIR / req.agent_id
    if not agent_dir.exists():
        raise HTTPException(404, f"Agent '{req.agent_id}' introuvable")

    # Load SkillMatcher.md system prompt
    meta_path = PROMPTS_DIR / "SkillMatcher.md"
    if not meta_path.exists():
        raise HTTPException(500, "Meta-prompt SkillMatcher.md introuvable")
    system_prompt = meta_path.read_text(encoding="utf-8")

    # Build {agent_profile} from all .md files
    profile_parts = []
    for f in sorted(agent_dir.iterdir()):
        if f.is_file() and f.suffix == ".md" and not f.name.endswith("_assign.md") and not f.name.endswith("_unassign.md"):
            if f.parent.name == "chat":
                continue
            content = f.read_text(encoding="utf-8")
            profile_parts.append(f"--------------- {f.name} ---------------\n{content}")
    # Also check chat/ subdirectory exclusion (files are in agent_dir directly)
    agent_profile = "\n\n".join(profile_parts) if profile_parts else "(aucun profil)"

    # Build {deliverable} context
    deliverable_ctx = json.dumps({"description": req.description, "agent_id": req.agent_id}, ensure_ascii=False, indent=2)

    # Inject into system prompt
    system_prompt = system_prompt.replace("{deliverable}", deliverable_ctx).replace("{agent_profile}", agent_profile)

    user_msg = "Analyse le livrable et le profil agent. Retourne uniquement le JSON demande, sans bloc de code markdown."

    result = await chat(ChatRequest(messages=[
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_msg},
    ], use_admin_llm=True))

    # Trace in chat/ directory
    from datetime import datetime
    chat_dir = agent_dir / "chat"
    chat_dir.mkdir(exist_ok=True)
    ts = datetime.now().strftime("%y%m%d%H%M%S")
    (chat_dir / f"{ts}_skillmatch_send.md").write_text(
        json.dumps([{"role": "system", "content": system_prompt}, {"role": "user", "content": user_msg}], indent=2, ensure_ascii=False),
        encoding="utf-8"
    )
    (chat_dir / f"{ts}_skillmatch_response.md").write_text(result.get("content", ""), encoding="utf-8")

    # Parse JSON from response
    raw = result.get("content", "")
    import re as _re
    # Try to extract JSON from response (may be wrapped in markdown code block)
    json_match = _re.search(r'\{[\s\S]*\}', raw)
    if json_match:
        try:
            parsed = json.loads(json_match.group())
            # Extract role/mission/skill names from selected_files
            roles = [e["file"].removeprefix("role_").removesuffix(".md") for e in (parsed.get("selected_files", {}).get("roles", []))]
            missions = [e["file"].removeprefix("mission_").removesuffix(".md") for e in (parsed.get("selected_files", {}).get("missions", []))]
            skills = [e["file"].removeprefix("skill_").removesuffix(".md") for e in (parsed.get("selected_files", {}).get("skills", []))]
            full_profile = parsed.get("full_profile", False)
            return {"roles": roles, "missions": missions, "skills": skills, "full_profile": full_profile}
        except (json.JSONDecodeError, KeyError):
            pass
    raise HTTPException(500, f"Reponse LLM non parseable: {raw[:500]}")


@app.post("/api/prod-projects/{project_id}/deliverable-skillmatch")
async def prod_deliverable_skillmatch(project_id: str, req: SkillMatchRequest):
    """Use SkillMatcher.md to auto-select roles/missions/skills for a deliverable (prod scope)."""
    _cfg_project_dir_or_404(project_id)
    # Reuse template implementation but skip its _project_dir_or_404 check
    agent_dir = SHARED_AGENTS_DIR / req.agent_id
    if not agent_dir.exists():
        raise HTTPException(404, f"Agent '{req.agent_id}' introuvable")
    meta_path = PROMPTS_DIR / "SkillMatcher.md"
    if not meta_path.exists():
        raise HTTPException(500, "Meta-prompt SkillMatcher.md introuvable")
    system_prompt = meta_path.read_text(encoding="utf-8")
    profile_parts = []
    for f in sorted(agent_dir.iterdir()):
        if f.is_file() and f.suffix == ".md" and not f.name.endswith("_assign.md") and not f.name.endswith("_unassign.md"):
            if f.parent.name == "chat":
                continue
            content = f.read_text(encoding="utf-8")
            profile_parts.append(f"--------------- {f.name} ---------------\n{content}")
    agent_profile = "\n\n".join(profile_parts) if profile_parts else "(aucun profil)"
    deliverable_ctx = json.dumps({"description": req.description, "agent_id": req.agent_id}, ensure_ascii=False, indent=2)
    system_prompt = system_prompt.replace("{deliverable}", deliverable_ctx).replace("{agent_profile}", agent_profile)
    user_msg = "Analyse le livrable et le profil agent. Retourne uniquement le JSON demande, sans bloc de code markdown."
    result = await chat(ChatRequest(messages=[
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_msg},
    ], use_admin_llm=True))
    from datetime import datetime
    chat_dir = agent_dir / "chat"
    chat_dir.mkdir(exist_ok=True)
    ts = datetime.now().strftime("%y%m%d%H%M%S")
    (chat_dir / f"{ts}_skillmatch_send.md").write_text(
        json.dumps([{"role": "system", "content": system_prompt}, {"role": "user", "content": user_msg}], indent=2, ensure_ascii=False),
        encoding="utf-8"
    )
    (chat_dir / f"{ts}_skillmatch_response.md").write_text(result.get("content", ""), encoding="utf-8")
    raw = result.get("content", "")
    import re as _re
    json_match = _re.search(r'\{[\s\S]*\}', raw)
    if json_match:
        try:
            parsed = json.loads(json_match.group())
            roles = [e["file"].removeprefix("role_").removesuffix(".md") for e in (parsed.get("selected_files", {}).get("roles", []))]
            missions = [e["file"].removeprefix("mission_").removesuffix(".md") for e in (parsed.get("selected_files", {}).get("missions", []))]
            skills = [e["file"].removeprefix("skill_").removesuffix(".md") for e in (parsed.get("selected_files", {}).get("skills", []))]
            full_profile = parsed.get("full_profile", False)
            return {"roles": roles, "missions": missions, "skills": skills, "full_profile": full_profile}
        except (json.JSONDecodeError, KeyError):
            pass
    raise HTTPException(500, f"Reponse LLM non parseable: {raw[:500]}")


@app.post("/api/templates/projects/{project_id}/orchestrator/build")
async def build_orchestrator_prompt_endpoint(project_id: str):
    """Build orchestrator prompt for the project's team — delegates to team build."""
    project_dir = _project_dir_or_404(project_id)
    project_json = project_dir / "project.json"
    if not project_json.exists():
        raise HTTPException(404, "project.json introuvable")
    project_cfg = json.loads(project_json.read_text(encoding="utf-8"))
    team = project_cfg.get("team", "").strip()
    if not team:
        raise HTTPException(400, "Le projet n'a pas d'equipe (champ 'team' vide)")
    return await build_team_orchestrator_prompt(team)


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
    # Pre-load shared agents catalog for merging
    shared_agents_map = {}
    if SHARED_AGENTS_DIR.exists():
        for sa_dir in SHARED_AGENTS_DIR.iterdir():
            if sa_dir.is_dir():
                cfg_file = sa_dir / "agent.json"
                if cfg_file.exists():
                    cfg = json.loads(cfg_file.read_text(encoding="utf-8"))
                    cfg["id"] = sa_dir.name
                    prompt_file = sa_dir / "prompt.md"
                    if prompt_file.exists():
                        cfg["prompt_content"] = prompt_file.read_text(encoding="utf-8")
                    # Extended files: identity, roles, missions, skills
                    identity_file = sa_dir / "identity.md"
                    cfg["identity_content"] = identity_file.read_text(encoding="utf-8") if identity_file.exists() else ""
                    cfg["roles"] = []
                    cfg["missions"] = []
                    cfg["skills"] = []
                    for f in sorted(sa_dir.iterdir()):
                        if not f.is_file() or f.suffix != ".md":
                            continue
                        stem = f.stem
                        if stem.startswith("role_"):
                            cfg["roles"].append({"name": stem[5:], "content": f.read_text(encoding="utf-8")})
                        elif stem.startswith("mission_"):
                            cfg["missions"].append({"name": stem[8:], "content": f.read_text(encoding="utf-8")})
                        elif stem.startswith("skill_"):
                            cfg["skills"].append({"name": stem[6:], "content": f.read_text(encoding="utf-8")})
                    shared_agents_map[sa_dir.name] = cfg
    # Enrich each team with its agents (merged from shared catalog)
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
            # Merge: shared agent properties + team overrides (type)
            shared = shared_agents_map.get(aid, {})
            merged = {**shared}
            if acfg.get("type"):
                merged["type"] = acfg["type"]
            if "id" not in merged:
                merged["id"] = aid
            # Orchestrator exception: prefer built prompt (orchestrator_prompt.md), fallback to registry prompt
            if acfg.get("type") == "orchestrator":
                team_prompt_file = tdir / "orchestrator_prompt.md"
                if not team_prompt_file.exists():
                    team_prompt_file = tdir / acfg.get("prompt", f"{aid}.md")
                if team_prompt_file.exists():
                    merged["prompt_content"] = team_prompt_file.read_text(encoding="utf-8")
            # Fallback: if shared agent not found, try config/Agents catalog
            if not shared:
                for cat_dir in [CFG_AGENTS_DIR / aid]:
                    cat_file = cat_dir / "agent.json"
                    if cat_file.exists():
                        cat = json.loads(cat_file.read_text(encoding="utf-8"))
                        merged = {**cat, **acfg, "id": aid}
                        break
                else:
                    merged = {**acfg, "id": aid}
                prompt_file = tdir / acfg.get("prompt", f"{aid}.md")
                if prompt_file.exists():
                    merged["prompt_content"] = prompt_file.read_text(encoding="utf-8")
            agents_detail[aid] = merged
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
    members: list[str] = []  # list of user emails to grant access


def _sync_team_members(team_id: str, member_emails: list[str]):
    """Sync hitl_team_members for team_id: set exactly the given emails."""
    uri = _env_dict().get("DATABASE_URI", "")
    if not uri or not member_emails:
        return
    import psycopg
    conn = psycopg.connect(uri, autocommit=True)
    try:
        with conn.cursor() as cur:
            # Remove existing members for this team
            cur.execute("DELETE FROM project.hitl_team_members WHERE team_id = %s", (team_id,))
            # Add new members
            for email in member_emails:
                cur.execute(
                    """INSERT INTO project.hitl_team_members (user_id, team_id, role)
                       SELECT id, %s, 'member' FROM project.hitl_users WHERE email = %s
                       ON CONFLICT (user_id, team_id) DO NOTHING""",
                    (team_id, email),
                )
    finally:
        conn.close()


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
    _write_json(team_dir / "agents_registry.json", {"agents": {
        "orchestrator": {
            "name": "Orchestrateur",
            "temperature": 0.2,
            "max_tokens": 4096,
            "prompt": "orchestrator.md",
            "type": "orchestrator"
        }
    }})
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
    _ensure_team_folder(team_id, directory, entry.template)
    # Auto-detect orchestrator from registry if not explicitly set
    if not entry.orchestrator:
        registry_file = TEAMS_DIR / (directory or team_id) / "agents_registry.json"
        if registry_file.exists():
            reg = _read_json(registry_file)
            agents = reg.get("agents", {})
            for aid, acfg in agents.items():
                if isinstance(acfg, dict) and acfg.get("type") == "orchestrator":
                    team_data["orchestrator"] = aid
                    break
    teams.append(team_data)
    _write_teams_list(teams)
    if entry.members:
        _sync_team_members(team_id, entry.members)
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
                "directory": t.get("directory", team_id),
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
    _sync_team_members(team_id, entry.members)
    return {"ok": True}


@app.delete("/api/teams/{team_id}")
async def delete_team(team_id: str):
    teams = _read_teams_list()
    deleted = [t for t in teams if t["id"] == team_id]
    new_teams = [t for t in teams if t["id"] != team_id]
    if not deleted:
        raise HTTPException(404, f"Equipe '{team_id}' introuvable")
    _write_teams_list(new_teams)
    # Remove all team memberships from DB
    uri = _env_dict().get("DATABASE_URI", "")
    if uri:
        import psycopg
        conn = psycopg.connect(uri, autocommit=True)
        try:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM project.hitl_team_members WHERE team_id = %s", (team_id,))
        finally:
            conn.close()
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
    """List available team templates from Shared/Teams/.

    The registry only stores references (type).
    Agent properties are resolved from Shared/Agents/{id}/agent.json + prompt.md.
    """
    # Build name lookup from teams.json
    teams_cfg = _read_json(SHARED_TEAMS_FILE) if SHARED_TEAMS_FILE.exists() else {}
    name_map = {}
    for t in teams_cfg.get("teams", []):
        directory = t.get("directory", "")
        if directory:
            name_map[directory] = t.get("name", directory)
    # Pre-load shared agents catalog for merging
    shared_agents_map = {}
    if SHARED_AGENTS_DIR.exists():
        for sa_dir in SHARED_AGENTS_DIR.iterdir():
            if sa_dir.is_dir():
                cfg_file = sa_dir / "agent.json"
                if cfg_file.exists():
                    cfg = json.loads(cfg_file.read_text(encoding="utf-8"))
                    cfg["id"] = sa_dir.name
                    prompt_file = sa_dir / "prompt.md"
                    if prompt_file.exists():
                        cfg["prompt_content"] = prompt_file.read_text(encoding="utf-8")
                    # Extended files: identity, roles, missions, skills
                    identity_file = sa_dir / "identity.md"
                    cfg["identity_content"] = identity_file.read_text(encoding="utf-8") if identity_file.exists() else ""
                    cfg["roles"] = []
                    cfg["missions"] = []
                    cfg["skills"] = []
                    for f in sorted(sa_dir.iterdir()):
                        if not f.is_file() or f.suffix != ".md":
                            continue
                        stem = f.stem
                        if stem.startswith("role_"):
                            cfg["roles"].append({"name": stem[5:], "content": f.read_text(encoding="utf-8")})
                        elif stem.startswith("mission_"):
                            cfg["missions"].append({"name": stem[8:], "content": f.read_text(encoding="utf-8")})
                        elif stem.startswith("skill_"):
                            cfg["skills"].append({"name": stem[6:], "content": f.read_text(encoding="utf-8")})
                    shared_agents_map[sa_dir.name] = cfg
    templates = []
    if SHARED_TEAMS_DIR.exists():
        for d in sorted(SHARED_TEAMS_DIR.iterdir()):
            if d.is_dir():
                reg = _read_json(d / "agents_registry.json")
                agents_raw = reg.get("agents", {})
                agents_detail = {}
                for aid, acfg in agents_raw.items():
                    # Merge: shared agent properties + team overrides (type, delegates_to, avatar)
                    shared = shared_agents_map.get(aid, {})
                    merged = {**shared}
                    if acfg.get("type"):
                        merged["type"] = acfg["type"]
                    if acfg.get("delegates_to"):
                        merged["delegates_to"] = acfg["delegates_to"]
                    if acfg.get("avatar"):
                        merged["avatar"] = acfg["avatar"]
                    if "id" not in merged:
                        merged["id"] = aid
                    # Fallback: if shared agent not found, try config/Agents catalog
                    if not shared:
                        for cat_dir in [CFG_AGENTS_DIR / aid]:
                            cat_file = cat_dir / "agent.json"
                            if cat_file.exists():
                                cat = json.loads(cat_file.read_text(encoding="utf-8"))
                                merged = {**cat, **acfg, "id": aid}
                                break
                        else:
                            merged = {**acfg, "id": aid}
                        prompt_file = d / acfg.get("prompt", f"{aid}.md")
                        if prompt_file.exists():
                            merged["prompt_content"] = prompt_file.read_text(encoding="utf-8")
                    # For orchestrator type, load orchestrator_prompt.md from team dir
                    if merged.get("type") == "orchestrator":
                        orch_prompt_file = d / "orchestrator_prompt.md"
                        if orch_prompt_file.exists():
                            merged["prompt_content"] = orch_prompt_file.read_text(encoding="utf-8")
                    agents_detail[aid] = merged
                orch_exists = (d / "orchestrator_prompt.md").exists()
                orch_stale = _check_orchestrator_prompt_staleness(d) if orch_exists else False
                mcp_access = _read_json(d / "agent_mcp_access.json") if (d / "agent_mcp_access.json").exists() else {}
                templates.append({
                    "id": d.name,
                    "name": name_map.get(d.name, d.name),
                    "agents": agents_detail,
                    "agent_count": len(agents_raw),
                    "mcp_access": mcp_access,
                    "orchestrator_prompt_exists": orch_exists,
                    "orchestrator_prompt_stale": orch_stale,
                    "report_exists": (d / "report.md").exists(),
                })
    return {"templates": templates}


# ── Production teams endpoints (config/Teams/) ──

@app.get("/api/prod-teams")
async def get_prod_teams():
    """Read production teams list from config/teams.json."""
    return _read_json(TEAMS_FILE) if TEAMS_FILE.exists() else {"teams": [], "channel_mapping": {}}


@app.put("/api/prod-teams")
async def save_prod_teams(request: Request):
    """Write production teams list and ensure directories exist."""
    data = await request.json()
    _write_json(TEAMS_FILE, data)
    for team in data.get("teams", []):
        directory = team.get("directory", "")
        if directory:
            team_dir = TEAMS_DIR / directory
            if not team_dir.exists():
                team_dir.mkdir(parents=True, exist_ok=True)
                _write_json(team_dir / "agents_registry.json", {"agents": {
                    "orchestrator": {
                        "name": "Orchestrateur",
                        "temperature": 0.2,
                        "max_tokens": 4096,
                        "prompt": "orchestrator.md",
                        "type": "orchestrator"
                    }
                }})
                _write_json(team_dir / "agent_mcp_access.json", {})
    return {"ok": True}


@app.get("/api/prod-teams-detail")
async def list_prod_teams_detail():
    """List production team templates from config/Teams/, merging with config/Agents/."""
    teams_cfg = _read_json(TEAMS_FILE) if TEAMS_FILE.exists() else {}
    name_map = {t.get("directory", ""): t.get("name", "") for t in teams_cfg.get("teams", []) if t.get("directory")}
    agents_map = {}
    if CFG_AGENTS_DIR.exists():
        for sa_dir in CFG_AGENTS_DIR.iterdir():
            if sa_dir.is_dir():
                cfg_file = sa_dir / "agent.json"
                if cfg_file.exists():
                    cfg = json.loads(cfg_file.read_text(encoding="utf-8"))
                    cfg["id"] = sa_dir.name
                    agents_map[sa_dir.name] = cfg
    templates = []
    if TEAMS_DIR.exists():
        for d in sorted(TEAMS_DIR.iterdir()):
            if d.is_dir():
                reg = _read_json(d / "agents_registry.json") if (d / "agents_registry.json").exists() else {}
                agents_raw = reg.get("agents", {})
                agents_detail = {}
                for aid, acfg in agents_raw.items():
                    shared = agents_map.get(aid, {})
                    merged = {**shared}
                    for k in ("type", "delegates_to", "avatar"):
                        if acfg.get(k):
                            merged[k] = acfg[k]
                    if "id" not in merged:
                        merged["id"] = aid
                    if not shared:
                        # Try Shared/Agents catalog as secondary fallback
                        sa_file = SHARED_AGENTS_DIR / aid / "agent.json"
                        if sa_file.exists():
                            cat = json.loads(sa_file.read_text(encoding="utf-8"))
                            merged = {**cat, **acfg, "id": aid}
                        else:
                            merged = {**acfg, "id": aid}
                    agents_detail[aid] = merged
                mcp_access = _read_json(d / "agent_mcp_access.json") if (d / "agent_mcp_access.json").exists() else {}
                templates.append({
                    "id": d.name,
                    "name": name_map.get(d.name, d.name),
                    "agents": agents_detail,
                    "agent_count": len(agents_raw),
                    "mcp_access": mcp_access,
                })
    return {"templates": templates}


@app.post("/api/prod-teams/copy-from-config")
async def copy_prod_teams_from_config(request: Request):
    """Copy selected team directories from Shared/Teams/ to config/Teams/."""
    body = await request.json()
    team_ids = body.get("team_ids", [])
    if not team_ids:
        raise HTTPException(400, "Aucune equipe selectionnee")
    # Read source teams metadata
    src_teams = _read_json(SHARED_TEAMS_FILE) if SHARED_TEAMS_FILE.exists() else {}
    src_list = src_teams.get("teams", [])
    # Read/init destination teams metadata
    dst_teams = _read_json(TEAMS_FILE) if TEAMS_FILE.exists() else {"teams": [], "channel_mapping": {}}
    dst_ids = {t["id"] for t in dst_teams.get("teams", [])}
    copied = 0
    avatars_copied = 0
    for tid in team_ids:
        src_team = next((t for t in src_list if t.get("id") == tid), None)
        if not src_team:
            continue
        directory = src_team.get("directory", "")
        if not directory:
            continue
        src_dir = SHARED_TEAMS_DIR / directory
        if not src_dir.exists():
            continue
        dst_dir = TEAMS_DIR / directory
        if dst_dir.exists():
            shutil.rmtree(dst_dir)
        shutil.copytree(src_dir, dst_dir)
        # Copy avatar images referenced by agents
        avatar_theme = src_team.get("avatar_theme", "")
        if avatar_theme:
            src_avatar_dir = AVATARS_DIR / avatar_theme
            dst_avatar_dir = CONFIGS / "Avatars" / avatar_theme
            if src_avatar_dir.exists():
                dst_avatar_dir.mkdir(parents=True, exist_ok=True)
                # Copy referenced images only
                registry_path = src_dir / "agents_registry.json"
                referenced_files = set()
                if registry_path.exists():
                    reg = _read_json(registry_path)
                    for agent_cfg in reg.get("agents", {}).values():
                        avatar_file = agent_cfg.get("avatar", "")
                        if avatar_file:
                            referenced_files.add(avatar_file)
                for fname in referenced_files:
                    src_file = src_avatar_dir / fname
                    if src_file.exists():
                        shutil.copy2(src_file, dst_avatar_dir / fname)
                        avatars_copied += 1
        # Add to teams.json if not already there
        if tid not in dst_ids:
            dst_teams["teams"].append(src_team)
            dst_ids.add(tid)
        else:
            # Update existing team entry (avatar_theme may have changed)
            for i, dt in enumerate(dst_teams["teams"]):
                if dt.get("id") == tid:
                    dst_teams["teams"][i] = src_team
                    break
        copied += 1
    _write_json(TEAMS_FILE, dst_teams)
    return {"ok": True, "copied": copied, "avatars_copied": avatars_copied}


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
                _write_json(team_dir / "agents_registry.json", {"agents": {
                    "orchestrator": {
                        "name": "Orchestrateur",
                        "temperature": 0.2,
                        "max_tokens": 4096,
                        "prompt": "orchestrator.md",
                        "type": "orchestrator"
                    }
                }})
                _write_json(team_dir / "agent_mcp_access.json", {})
                log.info("Created shared team folder: %s", team_dir)
    return {"ok": True}


def _shared_team_dir(directory: str) -> Path:
    """Resolve team id or directory name to Shared/Teams/<directory>/."""
    teams = _read_teams_list()
    for t in teams:
        if t.get("id") == directory:
            return SHARED_TEAMS_DIR / t.get("directory", directory)
    return SHARED_TEAMS_DIR / directory


@app.post("/api/templates/agents")
async def add_template_agent(cfg: AgentConfig):
    """Add an agent reference to a Shared template directory.

    Only stores type.
    Agent properties come from Shared/Agents/{id}/agent.json.
    """
    tdir = _shared_team_dir(cfg.team_id)
    tdir.mkdir(parents=True, exist_ok=True)
    # Verify the shared agent exists
    agent_dir = SHARED_AGENTS_DIR / cfg.id
    if not (agent_dir / "agent.json").exists():
        raise HTTPException(404, f"Shared agent '{cfg.id}' introuvable dans le catalogue")
    registry_path = tdir / "agents_registry.json"
    data = _read_json(registry_path)
    if "agents" not in data:
        data["agents"] = {}
    if cfg.id in data["agents"]:
        raise HTTPException(409, f"Agent {cfg.id} already exists")
    # Store only reference: type
    agent_data: dict = {}
    if cfg.type:
        agent_data["type"] = cfg.type
    data["agents"][cfg.id] = agent_data
    _write_json(registry_path, data)
    _invalidate_orchestrator_prompt_for_team(cfg.team_id)
    return {"ok": True}


@app.put("/api/templates/agents/{agent_id}")
async def update_template_agent(agent_id: str, cfg: AgentConfig):
    """Update an agent reference in a Shared template directory.

    Only type can be overridden per-team.
    """
    tdir = _shared_team_dir(cfg.team_id)
    registry_path = tdir / "agents_registry.json"
    data = _read_json(registry_path)
    if agent_id not in data.get("agents", {}):
        raise HTTPException(404, f"Agent {agent_id} not found")
    existing = data["agents"][agent_id]
    old_delegates = sorted(existing.get("delegates_to", []))
    if cfg.type:
        existing["type"] = cfg.type
    if cfg.delegates_to:
        existing["delegates_to"] = cfg.delegates_to
    elif "delegates_to" in existing:
        del existing["delegates_to"]
    # Avatar field
    if cfg.avatar:
        existing["avatar"] = cfg.avatar
    elif "avatar" in existing and not cfg.avatar:
        del existing["avatar"]
    data["agents"][agent_id] = existing
    _write_json(registry_path, data)
    # Only invalidate orchestrator prompt if delegates_to changed
    if old_delegates != sorted(cfg.delegates_to or []):
        _invalidate_orchestrator_prompt_for_team(cfg.team_id)
    return {"ok": True}


@app.delete("/api/templates/agents/{agent_id}")
async def delete_template_agent(agent_id: str, team_id: str = ""):
    """Delete an agent from a Shared template directory."""
    tdir = _shared_team_dir(team_id)
    registry_path = tdir / "agents_registry.json"
    data = _read_json(registry_path)
    if agent_id not in data.get("agents", {}):
        raise HTTPException(404, f"Agent {agent_id} not found")
    if data["agents"][agent_id].get("type") == "orchestrator":
        raise HTTPException(403, "L'orchestrateur ne peut pas etre supprime")
    prompt_file = data["agents"][agent_id].get("prompt", f"{agent_id}.md")
    del data["agents"][agent_id]
    _write_json(registry_path, data)
    prompt_path = tdir / prompt_file
    if prompt_path.exists():
        prompt_path.unlink()
        log.info("Deleted prompt file: %s", prompt_path)
    _invalidate_orchestrator_prompt_for_team(team_id)
    return {"ok": True}


# ── Production agents-in-team (config/Teams/) ──────

def _cfg_team_dir(directory: str) -> Path:
    if ".." in directory or "/" in directory or "\\" in directory:
        raise HTTPException(400, "Directory invalide")
    return TEAMS_DIR / directory


@app.post("/api/prod-team-agents")
async def add_prod_team_agent(cfg: AgentConfig):
    tdir = _cfg_team_dir(cfg.team_id)
    tdir.mkdir(parents=True, exist_ok=True)
    agent_dir = CFG_AGENTS_DIR / cfg.id
    if not (agent_dir / "agent.json").exists():
        raise HTTPException(404, f"Agent '{cfg.id}' introuvable dans config/Agents/")
    registry_path = tdir / "agents_registry.json"
    data = _read_json(registry_path) if registry_path.exists() else {"agents": {}}
    if "agents" not in data:
        data["agents"] = {}
    if cfg.id in data["agents"]:
        raise HTTPException(409, f"Agent {cfg.id} existe deja")
    agent_data = {}
    if cfg.type:
        agent_data["type"] = cfg.type
    data["agents"][cfg.id] = agent_data
    _write_json(registry_path, data)
    return {"ok": True}


@app.put("/api/prod-team-agents/{agent_id}")
async def update_prod_team_agent(agent_id: str, cfg: AgentConfig):
    tdir = _cfg_team_dir(cfg.team_id)
    registry_path = tdir / "agents_registry.json"
    data = _read_json(registry_path) if registry_path.exists() else {"agents": {}}
    if agent_id not in data.get("agents", {}):
        raise HTTPException(404, f"Agent {agent_id} introuvable")
    existing = data["agents"][agent_id]
    if cfg.type:
        existing["type"] = cfg.type
    if cfg.delegates_to:
        existing["delegates_to"] = cfg.delegates_to
    elif "delegates_to" in existing:
        del existing["delegates_to"]
    # Avatar field
    if cfg.avatar:
        existing["avatar"] = cfg.avatar
    elif "avatar" in existing and not cfg.avatar:
        del existing["avatar"]
    data["agents"][agent_id] = existing
    _write_json(registry_path, data)
    return {"ok": True}


@app.delete("/api/prod-team-agents/{agent_id}")
async def delete_prod_team_agent(agent_id: str, team_id: str = ""):
    tdir = _cfg_team_dir(team_id)
    registry_path = tdir / "agents_registry.json"
    data = _read_json(registry_path) if registry_path.exists() else {"agents": {}}
    if agent_id not in data.get("agents", {}):
        raise HTTPException(404, f"Agent {agent_id} introuvable")
    if data["agents"][agent_id].get("type") == "orchestrator":
        raise HTTPException(403, "L'orchestrateur ne peut pas etre supprime")
    del data["agents"][agent_id]
    _write_json(registry_path, data)
    return {"ok": True}


# ── Orchestrator prompt build & invalidation ──────


def _check_orchestrator_prompt_staleness(tdir: Path) -> bool:
    """Check if orchestrator_prompt.md is older than source .md files in Shared/Agents/."""
    prompt_file = tdir / "orchestrator_prompt.md"
    if not prompt_file.exists():
        return False
    prompt_mtime = prompt_file.stat().st_mtime
    reg_file = tdir / "agents_registry.json"
    if not reg_file.exists():
        return False
    reg = json.loads(reg_file.read_text(encoding="utf-8"))
    for aid in reg.get("agents", {}):
        agent_dir = SHARED_AGENTS_DIR / aid
        if not agent_dir.is_dir():
            continue
        for f in agent_dir.iterdir():
            if f.is_file() and f.suffix == ".md" and f.stat().st_mtime > prompt_mtime:
                log.info("Stale orchestrator_prompt.md for %s (source %s newer)", tdir.name, f.name)
                return True
    return False


def _invalidate_orchestrator_prompts(agent_id: str):
    """Delete orchestrator_prompt.md from all teams that reference agent_id."""
    if not SHARED_TEAMS_FILE.exists():
        return
    teams_cfg = json.loads(SHARED_TEAMS_FILE.read_text(encoding="utf-8"))
    for t in teams_cfg.get("teams", []):
        tdir = SHARED_TEAMS_DIR / t.get("directory", t["id"])
        reg_file = tdir / "agents_registry.json"
        if not reg_file.exists():
            continue
        reg = json.loads(reg_file.read_text(encoding="utf-8"))
        if agent_id in reg.get("agents", {}):
            prompt_file = tdir / "orchestrator_prompt.md"
            if prompt_file.exists():
                prompt_file.unlink()
                log.info("Invalidated orchestrator prompt for team %s (agent %s changed)", t["id"], agent_id)


def _invalidate_orchestrator_prompt_for_team(team_dir: str):
    """Delete orchestrator_prompt.md for a specific team."""
    tdir = _shared_team_dir(team_dir)
    prompt_file = tdir / "orchestrator_prompt.md"
    if prompt_file.exists():
        prompt_file.unlink()
        log.info("Invalidated orchestrator prompt for team dir %s", team_dir)


@app.post("/api/templates/teams/{team_dir}/orchestrator/build")
async def build_team_orchestrator_prompt(team_dir: str):
    """Build orchestrator prompt for a template team."""
    tdir = _shared_team_dir(team_dir)
    return await _build_orchestrator_prompt(tdir, team_dir)


async def _build_orchestrator_prompt_old(tdir: Path, team_dir: str):
    """Old build function — dead code, kept temporarily."""
    tdir = _shared_team_dir(team_dir)
    reg_file = tdir / "agents_registry.json"
    if not reg_file.exists():
        raise HTTPException(404, f"agents_registry.json introuvable pour {team_dir}")

    registry = json.loads(reg_file.read_text(encoding="utf-8"))
    agents = registry.get("agents", {})

    # Topological sort: managers before their subordinates
    _parents = {}
    for aid, acfg in agents.items():
        for sub in acfg.get("delegates_to", []):
            _parents.setdefault(sub, set()).add(aid)
    _in_degree = {aid: len(_parents.get(aid, set())) for aid in agents}
    _queue = [aid for aid, deg in _in_degree.items() if deg == 0]
    sorted_agent_ids = []
    while _queue:
        _queue.sort()
        aid = _queue.pop(0)
        sorted_agent_ids.append(aid)
        for sub in agents[aid].get("delegates_to", []):
            if sub in _in_degree:
                _in_degree[sub] -= 1
                if _in_degree[sub] == 0:
                    _queue.append(sub)
    for aid in agents:
        if aid not in sorted_agent_ids:
            sorted_agent_ids.append(aid)

    # Load translateOrchestrator.md template
    template_path = SHARED_DIR / "Prompts" / _CULTURE / "translateOrchestrator.md"
    if not template_path.exists():
        raise HTTPException(404, f"Template translateOrchestrator.md introuvable pour culture {_CULTURE}")
    template = template_path.read_text(encoding="utf-8")

    # Pre-compute boss relationships: agent_id -> list of boss agent_ids
    boss_map = {}
    for aid, acfg in agents.items():
        for sub_id in acfg.get("delegates_to", []):
            boss_map.setdefault(sub_id, []).append(aid)

    # Helper: resolve agent name from catalog
    def _resolve_name(aid):
        for cat in [SHARED_AGENTS_DIR / aid / "agent.json", CFG_AGENTS_DIR / aid / "agent.json"]:
            if cat.exists():
                return json.loads(cat.read_text(encoding="utf-8")).get("name", aid)
        return agents.get(aid, {}).get("name", aid)

    # Process each agent individually: one LLM call per agent, with hash-based cache
    chat_dir = tdir / "chat"
    chat_dir.mkdir(exist_ok=True)
    cache_dir = tdir / "tmp"
    cache_dir.mkdir(exist_ok=True)
    ts = datetime.now().strftime("%y%m%d-%H%M%S")
    all_cards = []

    for agent_id in sorted_agent_ids:
        agent_cfg = agents[agent_id]
        if agent_cfg.get("type") == "orchestrator" or agent_id == "orchestrator":
            continue

        # Resolve agent name from catalog (not registry)
        agent_name = agent_id
        agent_catalog_dir = None
        for cat_dir in [SHARED_AGENTS_DIR / agent_id, CFG_AGENTS_DIR / agent_id]:
            cat_file = cat_dir / "agent.json"
            if cat_file.exists():
                cat_data = json.loads(cat_file.read_text(encoding="utf-8"))
                agent_name = cat_data.get("name", agent_id)
                agent_catalog_dir = cat_dir
                break

        # Build agent_profile from all .md files in agent catalog dir
        profile_parts = []
        if agent_catalog_dir and agent_catalog_dir.is_dir():
            for f in sorted(agent_catalog_dir.iterdir()):
                if f.is_file() and f.suffix == ".md":
                    content = f.read_text(encoding="utf-8").strip()
                    if content:
                        label = f.stem.split("_")[0]
                        profile_parts.append(f"{label} : {content}")

        # Also read description from agent.json
        agent_json = agent_catalog_dir / "agent.json" if agent_catalog_dir and agent_catalog_dir.is_dir() else None
        description = ""
        if agent_json and agent_json.exists():
            acfg_data = json.loads(agent_json.read_text(encoding="utf-8"))
            description = acfg_data.get("description", "")
        if description:
            profile_parts.insert(0, f"{description}\n")

        # Inject hierarchy block (Boss/Sub relationships)
        hierarchy_lines = []
        for sub_id in agent_cfg.get("delegates_to", []):
            sub_name = _resolve_name(sub_id)
            hierarchy_lines.append(f"-  Sub : {sub_name} id {sub_id}")
        for boss_id in boss_map.get(agent_id, []):
            boss_name = _resolve_name(boss_id)
            hierarchy_lines.append(f"-  managed_by : id {boss_id} {boss_name}")
        if hierarchy_lines:
            hierarchy_block = "\n".join(hierarchy_lines) + "\n"
            insert_pos = 1 if description else 0
            profile_parts.insert(insert_pos, hierarchy_block)

        agent_profile = "\n".join(profile_parts) if profile_parts else "(aucun profil disponible)"

        # Inject into template for this agent
        agent_prompt = template.replace("{agent_profile}", agent_profile).replace("{agent_id}", agent_id).replace("{agent_name}", agent_name)

        # Check cache: hash the prompt, look for tmp/{hash}.xml
        prompt_hash = hashlib.sha256(agent_prompt.encode("utf-8")).hexdigest()
        cache_file = cache_dir / f"{prompt_hash}.xml"

        if cache_file.exists():
            card = cache_file.read_text(encoding="utf-8").strip()
            log.info("Orchestrator card for agent %s loaded from cache (%s)", agent_id, prompt_hash[:12])
        else:
            # Log send
            send_file = chat_dir / f"{ts}_orchestrator_build_{agent_id}_send.md"
            send_file.write_text(agent_prompt, encoding="utf-8")

            try:
                result = await chat(ChatRequest(messages=[
                    {"role": "user", "content": agent_prompt},
                ], use_admin_llm=True))
                card = result.get("content", "").strip()
                resp_file = chat_dir / f"{ts}_orchestrator_build_{agent_id}_response.md"
                resp_file.write_text(card, encoding="utf-8")
                # Save to cache
                cache_file.write_text(card, encoding="utf-8")
                log.info("Orchestrator card built for agent %s in team %s", agent_id, team_dir)
            except Exception as e:
                log.warning("LLM call failed for agent %s orchestrator card: %s", agent_id, e)
                all_cards.append((agent_id, agent_name, f"<!-- Erreur: {e} -->"))
                continue

        all_cards.append((agent_id, agent_name, card))

        # Save individual agent orchestrator card (cleaned)
        clean_card = re.sub(r"</?(?:orchestrator_card|card)[^>]*>", "", card).strip()
        orch_agent_file = tdir / f"orch_{agent_id}.md"
        orch_agent_file.write_text(f"### {agent_name} - id : {agent_id}\n{clean_card}\n", encoding="utf-8")

    # Assemble all cards, strip XML tags and add agent header
    stripped_cards = []
    for aid, aname, card in all_cards:
        clean = re.sub(r"</?orchestrator_card[^>]*>", "", card).strip()
        stripped_cards.append(f"### {aname} - id : {aid}\n\n{clean}")
    content = "\n\n".join(stripped_cards)

    # Save to team directory
    output_file = tdir / "orchestrator_prompt.md"
    output_file.write_text(content, encoding="utf-8")
    log.info("Orchestrator prompt built for team %s: %s", team_dir, output_file)

    return {"ok": True, "content": content}


@app.post("/api/prod-teams/{team_dir}/orchestrator/build")
async def build_prod_team_orchestrator_prompt(team_dir: str):
    """Build orchestrator prompt for a production team — delegates to same logic."""
    # Reuse the same function but with config/Teams/ directory
    tdir = _cfg_team_dir(team_dir)
    reg_file = tdir / "agents_registry.json"
    if not reg_file.exists():
        raise HTTPException(404, f"agents_registry.json introuvable pour {team_dir}")
    # Temporarily swap _shared_team_dir resolution for the build
    # The build function uses SHARED_AGENTS_DIR which is fine for catalog lookup
    # We just need to make sure it reads from the right team dir
    return await _build_orchestrator_prompt(tdir, team_dir)


async def _build_orchestrator_prompt(tdir: Path, team_dir: str):
    """Shared orchestrator prompt build logic."""
    reg_file = tdir / "agents_registry.json"
    if not reg_file.exists():
        raise HTTPException(404, f"agents_registry.json introuvable pour {team_dir}")

    registry = json.loads(reg_file.read_text(encoding="utf-8"))
    agents = registry.get("agents", {})

    _parents = {}
    for aid, acfg in agents.items():
        for sub in acfg.get("delegates_to", []):
            _parents.setdefault(sub, set()).add(aid)
    _in_degree = {aid: len(_parents.get(aid, set())) for aid in agents}
    _queue = [aid for aid, deg in _in_degree.items() if deg == 0]
    sorted_agent_ids = []
    while _queue:
        _queue.sort()
        aid = _queue.pop(0)
        sorted_agent_ids.append(aid)
        for sub in agents[aid].get("delegates_to", []):
            if sub in _in_degree:
                _in_degree[sub] -= 1
                if _in_degree[sub] == 0:
                    _queue.append(sub)
    for aid in agents:
        if aid not in sorted_agent_ids:
            sorted_agent_ids.append(aid)

    template_path = SHARED_DIR / "Prompts" / _CULTURE / "translateOrchestrator.md"
    if not template_path.exists():
        raise HTTPException(404, f"Template translateOrchestrator.md introuvable pour culture {_CULTURE}")
    template = template_path.read_text(encoding="utf-8")

    boss_map = {}
    for aid, acfg in agents.items():
        for sub_id in acfg.get("delegates_to", []):
            boss_map.setdefault(sub_id, []).append(aid)

    def _resolve_name(aid):
        for cat in [SHARED_AGENTS_DIR / aid / "agent.json", CFG_AGENTS_DIR / aid / "agent.json"]:
            if cat.exists():
                return json.loads(cat.read_text(encoding="utf-8")).get("name", aid)
        return agents.get(aid, {}).get("name", aid)

    chat_dir = tdir / "chat"
    chat_dir.mkdir(exist_ok=True)
    cache_dir = tdir / "tmp"
    cache_dir.mkdir(exist_ok=True)
    ts = datetime.now().strftime("%y%m%d-%H%M%S")
    all_cards = []

    for agent_id in sorted_agent_ids:
        agent_cfg = agents[agent_id]
        if agent_cfg.get("type") == "orchestrator" or agent_id == "orchestrator":
            continue

        agent_name = _resolve_name(agent_id)
        agent_catalog_dir = None
        for cat_dir in [SHARED_AGENTS_DIR / agent_id, CFG_AGENTS_DIR / agent_id]:
            if cat_dir.is_dir():
                agent_catalog_dir = cat_dir
                break

        profile_parts = []
        if agent_catalog_dir and agent_catalog_dir.is_dir():
            for f in sorted(agent_catalog_dir.iterdir()):
                if f.is_file() and f.suffix == ".md":
                    content = f.read_text(encoding="utf-8").strip()
                    if content:
                        label = f.stem.split("_")[0]
                        profile_parts.append(f"{label} : {content}")

        agent_json = agent_catalog_dir / "agent.json" if agent_catalog_dir else None
        description = ""
        if agent_json and agent_json.exists():
            acfg_data = json.loads(agent_json.read_text(encoding="utf-8"))
            description = acfg_data.get("description", "")
        if description:
            profile_parts.insert(0, f"{description}\n")

        hierarchy_lines = []
        for sub_id in agent_cfg.get("delegates_to", []):
            hierarchy_lines.append(f"-  Sub : {_resolve_name(sub_id)} id {sub_id}")
        for boss_id in boss_map.get(agent_id, []):
            hierarchy_lines.append(f"-  managed_by : id {boss_id} {_resolve_name(boss_id)}")
        if hierarchy_lines:
            insert_pos = 1 if description else 0
            profile_parts.insert(insert_pos, "\n".join(hierarchy_lines) + "\n")

        agent_profile = "\n".join(profile_parts) if profile_parts else "(aucun profil disponible)"
        agent_prompt = template.replace("{agent_profile}", agent_profile).replace("{agent_id}", agent_id).replace("{agent_name}", agent_name)

        prompt_hash = hashlib.sha256(agent_prompt.encode("utf-8")).hexdigest()
        cache_file = cache_dir / f"{prompt_hash}.xml"

        if cache_file.exists():
            card = cache_file.read_text(encoding="utf-8").strip()
        else:
            send_file = chat_dir / f"{ts}_orchestrator_build_{agent_id}_send.md"
            send_file.write_text(agent_prompt, encoding="utf-8")
            try:
                result = await chat(ChatRequest(messages=[{"role": "user", "content": agent_prompt}], use_admin_llm=True))
                card = result.get("content", "").strip()
                (chat_dir / f"{ts}_orchestrator_build_{agent_id}_response.md").write_text(card, encoding="utf-8")
                cache_file.write_text(card, encoding="utf-8")
            except Exception as e:
                all_cards.append((agent_id, agent_name, f"<!-- Erreur: {e} -->"))
                continue

        all_cards.append((agent_id, agent_name, card))
        clean_card = re.sub(r"</?(?:orchestrator_card|card)[^>]*>", "", card).strip()
        (tdir / f"orch_{agent_id}.md").write_text(f"### {agent_name} - id : {agent_id}\n{clean_card}\n", encoding="utf-8")

    stripped_cards = []
    for aid, aname, card in all_cards:
        clean = re.sub(r"</?orchestrator_card[^>]*>", "", card).strip()
        stripped_cards.append(f"### {aname} - id : {aid}\n\n{clean}")
    content = "\n\n".join(stripped_cards)

    (tdir / "orchestrator_prompt.md").write_text(content, encoding="utf-8")
    return {"ok": True, "content": content}


@app.post("/api/templates/teams/{team_dir}/coherence/check")
async def check_team_coherence(team_dir: str):
    """Run coherence check on a team using CheckTeamCoherence.md + LLM."""
    tdir = _shared_team_dir(team_dir)
    reg_file = tdir / "agents_registry.json"
    if not reg_file.exists():
        raise HTTPException(404, f"agents_registry.json introuvable pour {team_dir}")

    orch_file = tdir / "orchestrator_prompt.md"
    if not orch_file.exists():
        raise HTTPException(400, "orchestrator_prompt.md introuvable — construisez-le d'abord")

    # Load CheckTeamCoherence.md template
    template_path = SHARED_DIR / "Prompts" / _CULTURE / "CheckTeamCoherence.md"
    if not template_path.exists():
        raise HTTPException(404, f"CheckTeamCoherence.md introuvable pour culture {_CULTURE}")
    template = template_path.read_text(encoding="utf-8")

    orchestrator_cards = orch_file.read_text(encoding="utf-8")
    registry = json.loads(reg_file.read_text(encoding="utf-8"))
    team_registry = json.dumps(registry.get("agents", {}), indent=2, ensure_ascii=False)

    prompt = template.replace("{orchestrator_cards}", orchestrator_cards).replace("{team_registry}", team_registry)

    # Log send
    chat_dir = tdir / "chat"
    chat_dir.mkdir(exist_ok=True)
    ts = datetime.now().strftime("%y%m%d-%H%M%S")
    send_file = chat_dir / f"{ts}_coherence_check_send.md"
    send_file.write_text(prompt, encoding="utf-8")

    try:
        result = await chat(ChatRequest(messages=[
            {"role": "user", "content": prompt},
        ], use_admin_llm=True))
        content = result.get("content", "").strip()
        resp_file = chat_dir / f"{ts}_coherence_check_response.md"
        resp_file.write_text(content, encoding="utf-8")
    except Exception as e:
        raise HTTPException(500, f"Erreur LLM: {e}")

    # Convert XML diagnostic to Markdown report
    report_lines = [f"# Rapport de coherence — {team_dir}", f"*Genere le {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*", ""]

    for section, title in [
        ("summary", "Resume"),
        ("critical", "Problemes critiques"),
        ("warnings", "Avertissements"),
        ("ghost_references", "References fantomes"),
        ("actions", "Actions correctives"),
    ]:
        match = re.search(f"<{section}>(.*?)</{section}>", content, re.DOTALL)
        body = match.group(1).strip() if match else "N/A"
        report_lines.append(f"## {title}")
        report_lines.append("")
        report_lines.append(body)
        report_lines.append("")

    report = "\n".join(report_lines)
    report_file = tdir / "report.md"
    report_file.write_text(report, encoding="utf-8")
    log.info("Coherence report saved for team %s: %s", team_dir, report_file)

    return {"ok": True, "content": report}


@app.get("/api/templates/teams/{team_dir}/coherence/report")
async def get_team_coherence_report(team_dir: str):
    """Read existing coherence report for a team."""
    tdir = _shared_team_dir(team_dir)
    report_file = tdir / "report.md"
    if not report_file.exists():
        raise HTTPException(404, "Aucun rapport disponible")
    return {"ok": True, "content": report_file.read_text(encoding="utf-8")}


# ── Git helpers ───────────────────────────────────

def _get_repo_dir(repo_key: str) -> Path:
    """Return the directory for a repo key."""
    dirs = {"configs": CONFIGS, "shared": SHARED_DIR}
    d = dirs.get(repo_key)
    if not d:
        raise HTTPException(400, f"Repo inconnu: {repo_key}. Utiliser 'configs' ou 'shared'.")
    return d


def _git_file_for(repo_key: str) -> Path:
    """Return the git.json file path for a repo key."""
    files = {"configs": CONFIGS_GIT_FILE, "shared": SHARED_GIT_FILE}
    f = files.get(repo_key)
    if not f:
        raise HTTPException(400, f"Repo inconnu: {repo_key}. Utiliser 'configs' ou 'shared'.")
    return f


def _get_repo_cfg(repo_key: str) -> dict:
    """Return git config for a specific repo, with fallback to git_service.json."""
    cfg_file = _git_file_for(repo_key)
    if cfg_file.exists():
        data = _read_json(cfg_file)
        if data.get("path"):
            return data
    # Fallback: derive from git_service.json
    if SHARED_GIT_FILE.exists():
        svc = _read_json(SHARED_GIT_FILE)
        login = svc.get("login", "")
        token = svc.get("token", "")
        if login and token:
            return {"path": "", "login": login, "password": token}
    return {}


def _ensure_gitignore(target_dir: Path):
    """Create or update .gitignore with required patterns."""
    gitignore = target_dir / ".gitignore"
    required = ["*.sh", "git.json", "**/git.json", "__pycache__/", "*.pyc"]
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
    else:
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
    subprocess.run(["git", "remote", "remove", "origin"], cwd=str(target_dir),
                   capture_output=True, text=True, timeout=5)
    subprocess.run(["git", "remote", "add", "origin", remote_url], cwd=str(target_dir),
                   capture_output=True, text=True, timeout=5)


def _git_detect_branch(target_dir: Path) -> str:
    """Detect the current branch name with robust fallbacks."""
    # Try current branch
    r = subprocess.run(["git", "branch", "--show-current"], cwd=str(target_dir),
                       capture_output=True, text=True, timeout=10)
    branch = r.stdout.strip()
    if branch:
        return branch
    # Check remote branches for main/master
    r = subprocess.run(["git", "branch", "-r"], cwd=str(target_dir),
                       capture_output=True, text=True, timeout=10)
    if "origin/main" in r.stdout:
        return "main"
    return "master"


def _git_sanitize(text: str, login: str, password: str) -> str:
    """Remove credentials from git output."""
    if login and password:
        text = text.replace(f"{login}:{password}@", "***:***@")
        text = text.replace(password, "***")
    return text


# ── API: Git config per-repo ─────────────────────

@app.get("/api/git/repo-config/{repo_key}")
async def get_repo_git_config(repo_key: str):
    cfg_file = _git_file_for(repo_key)
    data = _read_json(cfg_file) if cfg_file.exists() else {}
    return {"path": data.get("path", ""), "login": data.get("login", ""), "password": data.get("password", "")}


@app.put("/api/git/repo-config/{repo_key}")
async def save_repo_git_config(repo_key: str, request: Request):
    """Save git config and configure remote (only place where remote is set)."""
    body = await request.json()
    cfg_file = _git_file_for(repo_key)
    cfg_file.parent.mkdir(parents=True, exist_ok=True)
    _write_json(cfg_file, {
        "path": body.get("path", ""),
        "login": body.get("login", ""),
        "password": body.get("password", ""),
    })
    # Configure remote if repo already initialized
    target_dir = _get_repo_dir(repo_key)
    repo_path = body.get("path", "").strip()
    if repo_path and (target_dir / ".git").exists():
        login = body.get("login", "").strip()
        password = body.get("password", "").strip()
        _git_configure_remote(target_dir, repo_path, login, password)
    return {"ok": True}


# ── API: Git service (remote repo creation) ──────

GIT_SERVICES = {
    "github":    {"name": "GitHub",    "url": "https://api.github.com"},
    "gitlab":    {"name": "GitLab",    "url": "https://gitlab.com"},
    "gitea":     {"name": "Gitea",     "url": ""},
    "forgejo":   {"name": "Forgejo",   "url": ""},
    "bitbucket": {"name": "Bitbucket", "url": "https://api.bitbucket.org/2.0"},
}


@app.get("/api/git-service/types")
async def git_service_types():
    return {"services": GIT_SERVICES}


def _git_svc_file(scope: str) -> Path:
    """Return the git service config file for a scope."""
    if scope == "configs":
        return CONFIGS_GIT_FILE
    return SHARED_GIT_FILE


@app.get("/api/git-svc/{scope}/config")
async def get_git_svc_config(scope: str):
    f = _git_svc_file(scope)
    data = _read_json(f) if f.exists() else {}
    return {
        "service": data.get("service", ""),
        "url": data.get("url", ""),
        "login": data.get("login", ""),
        "token": data.get("token", ""),
        "repo_name": data.get("repo_name", ""),
    }


@app.put("/api/git-svc/{scope}/config")
async def save_git_svc_config(scope: str, request: Request):
    body = await request.json()
    f = _git_svc_file(scope)
    f.parent.mkdir(parents=True, exist_ok=True)
    existing = _read_json(f) if f.exists() else {}
    existing.update({
        "service": body.get("service", ""),
        "url": body.get("url", ""),
        "login": body.get("login", ""),
        "token": body.get("token", ""),
        "repo_name": body.get("repo_name", ""),
    })
    _write_json(f, existing)
    return {"ok": True}


async def _git_service_create_repo(service: str, base_url: str, login: str, token: str,
                                    repo_name: str, private: bool = True) -> dict:
    """Create a remote repo via the git service API. Returns {ok, clone_url, message}."""
    headers = {"Accept": "application/json"}
    async with httpx.AsyncClient(timeout=30) as client:
        if service == "github":
            headers["Authorization"] = f"token {token}"
            r = await client.post(f"{base_url}/user/repos", headers=headers,
                                  json={"name": repo_name, "private": private, "auto_init": False})
            if r.status_code == 201:
                return {"ok": True, "clone_url": r.json().get("clone_url", "")}
            if r.status_code == 422:
                return {"ok": False, "message": "Le depot existe deja sur GitHub"}
            return {"ok": False, "message": f"GitHub {r.status_code}: {r.text[:300]}"}

        elif service == "gitlab":
            headers["PRIVATE-TOKEN"] = token
            r = await client.post(f"{base_url}/api/v4/projects", headers=headers,
                                  json={"name": repo_name, "visibility": "private" if private else "public"})
            if r.status_code == 201:
                return {"ok": True, "clone_url": r.json().get("http_url_to_repo", "")}
            if r.status_code == 400 and "already been taken" in r.text:
                return {"ok": False, "message": "Le depot existe deja sur GitLab"}
            return {"ok": False, "message": f"GitLab {r.status_code}: {r.text[:300]}"}

        elif service in ("gitea", "forgejo"):
            headers["Authorization"] = f"token {token}"
            r = await client.post(f"{base_url}/api/v1/user/repos", headers=headers,
                                  json={"name": repo_name, "private": private, "auto_init": False})
            if r.status_code == 201:
                return {"ok": True, "clone_url": r.json().get("clone_url", "")}
            if r.status_code == 409:
                return {"ok": False, "message": f"Le depot existe deja sur {service.title()}"}
            return {"ok": False, "message": f"{service.title()} {r.status_code}: {r.text[:300]}"}

        elif service == "bitbucket":
            r = await client.post(
                f"{base_url}/repositories/{login}/{repo_name}",
                headers=headers, auth=(login, token),
                json={"scm": "git", "is_private": private})
            if r.status_code == 200:
                links = r.json().get("links", {}).get("clone", [])
                clone = next((l["href"] for l in links if l["name"] == "https"), "")
                return {"ok": True, "clone_url": clone}
            if r.status_code == 400 and "already exists" in r.text:
                return {"ok": False, "message": "Le depot existe deja sur Bitbucket"}
            return {"ok": False, "message": f"Bitbucket {r.status_code}: {r.text[:300]}"}

        return {"ok": False, "message": f"Service inconnu: {service}"}


@app.post("/api/git-svc/{scope}/sync-repo-config")
async def git_svc_sync_repo_config(scope: str):
    """Sync git service credentials into the repo's git.json and configure remote."""
    repo_key = "configs" if scope == "configs" else "shared"
    svc_file = _git_svc_file(scope)
    svc = _read_json(svc_file) if svc_file.exists() else {}
    login = svc.get("login", "")
    token = svc.get("token", "")
    cfg_file = _git_file_for(repo_key)
    repo_cfg = _read_json(cfg_file) if cfg_file.exists() else {}
    if login or token:
        repo_cfg["login"] = login
        repo_cfg["password"] = token
        cfg_file.parent.mkdir(parents=True, exist_ok=True)
        _write_json(cfg_file, repo_cfg)
    repo_path = repo_cfg.get("path", "").strip()
    target_dir = _get_repo_dir(repo_key)
    if repo_path and (target_dir / ".git").exists():
        _git_configure_remote(target_dir, repo_path, login, token)
    return {"ok": True}


async def _git_service_check_repo_exists(service: str, base_url: str, login: str, token: str,
                                          repo_name: str) -> dict:
    """Check if a remote repo exists. Returns {exists: bool, clone_url: str}."""
    headers = {"Accept": "application/json"}
    async with httpx.AsyncClient(timeout=15) as client:
        try:
            if service == "github":
                headers["Authorization"] = f"token {token}"
                r = await client.get(f"{base_url}/repos/{login}/{repo_name}", headers=headers)
                if r.status_code == 200:
                    return {"exists": True, "clone_url": r.json().get("clone_url", "")}
                return {"exists": False}
            elif service == "gitlab":
                headers["PRIVATE-TOKEN"] = token
                encoded = f"{login}%2F{repo_name}"
                r = await client.get(f"{base_url}/api/v4/projects/{encoded}", headers=headers)
                if r.status_code == 200:
                    return {"exists": True, "clone_url": r.json().get("http_url_to_repo", "")}
                return {"exists": False}
            elif service in ("gitea", "forgejo"):
                headers["Authorization"] = f"token {token}"
                r = await client.get(f"{base_url}/api/v1/repos/{login}/{repo_name}", headers=headers)
                if r.status_code == 200:
                    return {"exists": True, "clone_url": r.json().get("clone_url", "")}
                return {"exists": False}
            elif service == "bitbucket":
                r = await client.get(f"{base_url}/repositories/{login}/{repo_name}",
                                     headers=headers, auth=(login, token))
                if r.status_code == 200:
                    links = r.json().get("links", {}).get("clone", [])
                    clone = next((l["href"] for l in links if l["name"] == "https"), "")
                    return {"exists": True, "clone_url": clone}
                return {"exists": False}
        except Exception:
            pass
    return {"exists": False}


@app.post("/api/git-svc/{scope}/check-repo")
async def git_svc_check_repo(scope: str, request: Request):
    """Check if a remote repo exists on the git service."""
    body = await request.json()
    svc_file = _git_svc_file(scope)
    cfg = _read_json(svc_file) if svc_file.exists() else {}
    service = cfg.get("service", "")
    base_url = cfg.get("url", "").rstrip("/")
    login = cfg.get("login", "")
    token = cfg.get("token", "")
    repo_name = body.get("repo_name", "").strip()
    if not service or not base_url or not token or not repo_name:
        raise HTTPException(400, "Service, URL, token et nom du depot sont requis")
    return await _git_service_check_repo_exists(service, base_url, login, token, repo_name)


@app.post("/api/git-svc/{scope}/create-repo")
async def git_svc_create_repo(scope: str, request: Request):
    """Create a new repo on the remote git service."""
    body = await request.json()
    repo_key = "configs" if scope == "configs" else "shared"
    svc_file = _git_svc_file(scope)
    cfg = _read_json(svc_file) if svc_file.exists() else {}
    service = cfg.get("service", "")
    base_url = cfg.get("url", "").rstrip("/")
    login = cfg.get("login", "")
    token = cfg.get("token", "")
    repo_name = body.get("repo_name", "").strip()
    if not service or not base_url or not token or not repo_name:
        raise HTTPException(400, "Service, URL, token et nom du depot sont requis")
    result = await _git_service_create_repo(service, base_url, login, token, repo_name)
    if not result["ok"]:
        return result
    clone_url = result.get("clone_url", "")
    if clone_url:
        cfg_file = _git_file_for(repo_key)
        cfg_file.parent.mkdir(parents=True, exist_ok=True)
        _write_json(cfg_file, {"path": clone_url, "login": login, "password": token})
        target_dir = _get_repo_dir(repo_key)
        if (target_dir / ".git").exists():
            _git_configure_remote(target_dir, clone_url, login, token)
    return {"ok": True, "clone_url": clone_url, "message": f"Depot '{repo_name}' cree avec succes"}


@app.post("/api/git-svc/{scope}/fetch-repo")
async def git_svc_fetch_repo(scope: str, request: Request):
    """Fetch (clone) an existing remote repo into a local repo directory."""
    body = await request.json()
    repo_key = "configs" if scope == "configs" else "shared"
    repo_url = body.get("repo_url", "").strip()
    if not repo_url:
        raise HTTPException(400, "repo_url requis")
    svc_file = _git_svc_file(scope)
    cfg = _read_json(svc_file) if svc_file.exists() else {}
    login = cfg.get("login", "")
    token = cfg.get("token", "")
    cfg_file = _git_file_for(repo_key)
    cfg_file.parent.mkdir(parents=True, exist_ok=True)
    _write_json(cfg_file, {"path": repo_url, "login": login, "password": token})
    target_dir = _get_repo_dir(repo_key)
    target_dir.mkdir(parents=True, exist_ok=True)
    try:
        git_env = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}
        remote_url = _build_remote_url(repo_url, login, token)
        if (target_dir / ".git").exists():
            _git_configure_remote(target_dir, repo_url, login, token)
            r = subprocess.run(["git", "pull", "origin"], cwd=str(target_dir),
                               capture_output=True, text=True, timeout=60, env=git_env)
        else:
            subprocess.run(["git", "config", "--global", "--add", "safe.directory", str(target_dir)],
                           capture_output=True, text=True, timeout=5)
            r = subprocess.run(["git", "clone", remote_url, "."], cwd=str(target_dir),
                               capture_output=True, text=True, timeout=120, env=git_env)
        stderr = _git_sanitize(r.stderr, login, token)
        if r.returncode != 0:
            return {"ok": False, "message": f"Erreur: {stderr[:300]}"}
        return {"ok": True, "message": "Depot recupere avec succes"}
    except Exception as e:
        raise HTTPException(500, str(e))


@app.post("/api/git/{repo_key}/reset")
async def git_reset(repo_key: str):
    """Hard reset to remote: git fetch origin + git reset --hard origin/{branch} + git clean -fd."""
    target_dir = _get_repo_dir(repo_key)
    if not (target_dir / ".git").exists():
        raise HTTPException(400, "Repository non initialise")
    try:
        git_env = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}
        branch = _git_detect_branch(target_dir)
        subprocess.run(["git", "fetch", "origin"], cwd=str(target_dir),
                       capture_output=True, text=True, timeout=60, env=git_env)
        subprocess.run(["git", "reset", "--hard", f"origin/{branch}"], cwd=str(target_dir),
                       capture_output=True, text=True, timeout=30)
        subprocess.run(["git", "clean", "-fd"], cwd=str(target_dir),
                       capture_output=True, text=True, timeout=30)
        return {"ok": True, "message": f"Reset sur origin/{branch} effectue"}
    except Exception as e:
        raise HTTPException(500, str(e))


# ── API: Git operations ──────────────────────────

@app.get("/api/git/{repo_key}/status")
async def git_status(repo_key: str):
    target_dir = _get_repo_dir(repo_key)
    initialized = (target_dir / ".git").exists()
    if not initialized:
        return {"initialized": False, "status": "", "branch": "", "log": ""}
    try:
        status = subprocess.run(["git", "status", "--short"], cwd=str(target_dir),
                                capture_output=True, text=True, timeout=10)
        branch = subprocess.run(["git", "branch", "--show-current"], cwd=str(target_dir),
                                capture_output=True, text=True, timeout=10)
        git_log = subprocess.run(["git", "log", "--oneline", "-10"], cwd=str(target_dir),
                                 capture_output=True, text=True, timeout=10)
        return {
            "initialized": True,
            "status": status.stdout,
            "branch": branch.stdout.strip(),
            "log": git_log.stdout,
        }
    except Exception as e:
        raise HTTPException(500, str(e))


@app.post("/api/git/{repo_key}/init")
async def git_init(repo_key: str):
    """Initialize git repo, configure remote, create initial commit."""
    target_dir = _get_repo_dir(repo_key)
    log.info("Git init (%s) in %s", repo_key, target_dir)
    try:
        target_dir.mkdir(parents=True, exist_ok=True)
        if (target_dir / ".git").exists():
            return {"ok": True, "message": "Depot deja initialise"}
        # Init
        subprocess.run(["git", "config", "--global", "--add", "safe.directory", str(target_dir)],
                       capture_output=True, text=True, timeout=5)
        result = subprocess.run(["git", "init"], cwd=str(target_dir),
                                capture_output=True, text=True, timeout=10)
        if result.returncode != 0:
            raise HTTPException(500, result.stderr)
        _ensure_gitignore(target_dir)
        # Configure remote
        cfg = _get_repo_cfg(repo_key)
        repo_path = cfg.get("path", "").strip()
        if repo_path:
            _git_configure_remote(target_dir, repo_path, cfg.get("login", ""), cfg.get("password", ""))
        # Initial commit so HEAD exists
        subprocess.run(["git", "add", "-A"], cwd=str(target_dir),
                       capture_output=True, text=True, timeout=10)
        subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=str(target_dir),
                       capture_output=True, text=True, timeout=10)
        log.info("Git init success for %s", repo_key)
        return {"ok": True, "message": "Depot initialise avec succes"}
    except HTTPException:
        raise
    except Exception as e:
        log.exception("Git init exception")
        raise HTTPException(500, str(e))


class GitPullRequest(BaseModel):
    force: bool = False

@app.post("/api/git/{repo_key}/pull")
async def git_pull(repo_key: str, req: GitPullRequest = GitPullRequest()):
    """Pull from remote. If not initialized, does init + fetch + reset."""
    target_dir = _get_repo_dir(repo_key)
    log.info("Git pull (%s)", repo_key)
    try:
        target_dir.mkdir(parents=True, exist_ok=True)
        git_env = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}
        cfg = _get_repo_cfg(repo_key)
        repo_path = cfg.get("path", "").strip()
        login = cfg.get("login", "").strip()
        password = cfg.get("password", "").strip()

        if not repo_path:
            raise HTTPException(400, "Chemin du depot non configure")

        if not (target_dir / ".git").exists():
            # Init + fetch + checkout (works with non-empty dir unlike clone)
            subprocess.run(["git", "config", "--global", "--add", "safe.directory", str(target_dir)],
                           capture_output=True, text=True, timeout=5)
            subprocess.run(["git", "init"], cwd=str(target_dir),
                           capture_output=True, text=True, timeout=10)
            _git_configure_remote(target_dir, repo_path, login, password)
            fetch_r = subprocess.run(["git", "fetch", "origin"], cwd=str(target_dir),
                                     capture_output=True, text=True, timeout=120, env=git_env)
            if fetch_r.returncode != 0:
                stderr = _git_sanitize(fetch_r.stderr, login, password)
                return {"ok": False, "message": f"Fetch echoue: {stderr[:300]}"}
            # Detect default branch from remote
            branch = _git_detect_branch(target_dir)
            subprocess.run(["git", "checkout", "-B", branch, f"origin/{branch}"], cwd=str(target_dir),
                           capture_output=True, text=True, timeout=30)
            subprocess.run(["git", "branch", f"--set-upstream-to=origin/{branch}", branch], cwd=str(target_dir),
                           capture_output=True, text=True, timeout=5)
            _ensure_gitignore(target_dir)
            return {"ok": True, "message": f"Pull initial reussi (branche {branch})"}
        else:
            # Fetch + reset hard to remote branch
            branch = _git_detect_branch(target_dir)
            # Check for uncommitted changes
            status_r = subprocess.run(["git", "status", "--porcelain"], cwd=str(target_dir),
                                      capture_output=True, text=True, timeout=10)
            has_changes = bool(status_r.stdout.strip())
            fetch_r = subprocess.run(["git", "fetch", "origin"], cwd=str(target_dir),
                                     capture_output=True, text=True, timeout=120, env=git_env)
            stderr = _git_sanitize(fetch_r.stderr, login, password)
            if fetch_r.returncode != 0:
                log.error("Git fetch failed (%s): %s", repo_key, stderr[:300])
                return {"ok": False, "message": f"Fetch echoue: {stderr[:300]}"}
            if has_changes and not req.force:
                return {"ok": False, "uncommitted": True, "message": "Des modifications locales non commitees seront perdues."}
            reset_r = subprocess.run(["git", "reset", "--hard", f"origin/{branch}"], cwd=str(target_dir),
                                     capture_output=True, text=True, timeout=30)
            if reset_r.returncode != 0:
                return {"ok": False, "message": f"Reset echoue: {reset_r.stderr[:300]}"}
            log.info("Git fetch + reset success (%s)", repo_key)
            return {"ok": True, "message": f"Fetch reussi (branche {branch})"}
    except HTTPException:
        raise
    except Exception as e:
        log.exception("Git pull exception")
        raise HTTPException(500, str(e))


class GitCommitRequest(BaseModel):
    message: str
    force: bool = False


@app.post("/api/git/{repo_key}/commit")
async def git_commit(repo_key: str, req: GitCommitRequest):
    """Stage all, commit and push. No filter-branch, no force push."""
    target_dir = _get_repo_dir(repo_key)
    log.info("Git commit & push (%s)", repo_key)
    try:
        git_env = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}
        cfg = _get_repo_cfg(repo_key)
        repo_path = cfg.get("path", "").strip()
        login = cfg.get("login", "").strip()
        password = cfg.get("password", "").strip()

        _ensure_gitignore(target_dir)
        branch = _git_detect_branch(target_dir)

        # 1. Stage all, then unstage git.json
        subprocess.run(["git", "add", "-A"], cwd=str(target_dir),
                       capture_output=True, text=True, timeout=10)
        subprocess.run(["git", "rm", "-r", "--cached", "--ignore-unmatch", "git.json"],
                       cwd=str(target_dir), capture_output=True, text=True, timeout=10)

        # 2. Commit
        commit_r = subprocess.run(["git", "commit", "-m", req.message], cwd=str(target_dir),
                                  capture_output=True, text=True, timeout=30)
        nothing = "nothing to commit" in commit_r.stdout
        if commit_r.returncode != 0 and not nothing:
            return {"ok": False, "message": commit_r.stderr[:300] or commit_r.stdout[:300]}

        # 3. Push
        if repo_path:
            push_cmd = ["git", "push", "origin", branch]
            if req.force:
                push_cmd = ["git", "push", "--force", "origin", branch]
            push_r = subprocess.run(push_cmd, cwd=str(target_dir),
                                    capture_output=True, text=True, timeout=60, env=git_env)
            stderr = _git_sanitize(push_r.stderr, login, password)
            if push_r.returncode != 0:
                return {"ok": False, "non_fast_forward": True, "message": stderr[:300] or "Push echoue"}

        if nothing:
            return {"ok": True, "message": "Rien a commiter, depot a jour"}
        log.info("Git commit & push success (%s)", repo_key)
        return {"ok": True, "message": "Commit et push effectues"}
    except Exception as e:
        log.exception("Git commit exception for %s", repo_key)
        raise HTTPException(500, str(e))


class GitPushRequest(BaseModel):
    force: bool = False

@app.post("/api/git/{repo_key}/push")
async def git_push_only(repo_key: str, req: GitPushRequest = GitPushRequest()):
    """Push local commits to remote."""
    target_dir = _get_repo_dir(repo_key)
    log.info("Git push (%s, force=%s)", repo_key, req.force)
    try:
        git_env = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}
        cfg = _get_repo_cfg(repo_key)
        login = cfg.get("login", "").strip()
        password = cfg.get("password", "").strip()
        branch = _git_detect_branch(target_dir)

        push_cmd = ["git", "push", "origin", branch]
        if req.force:
            push_cmd = ["git", "push", "--force", "origin", branch]
        result = subprocess.run(push_cmd, cwd=str(target_dir),
                                capture_output=True, text=True, timeout=60, env=git_env)
        stderr = _git_sanitize(result.stderr, login, password)
        if result.returncode != 0:
            return {"ok": False, "non_fast_forward": True, "message": stderr[:300] or "Push echoue"}
        return {"ok": True, "message": "Push effectue"}
    except Exception as e:
        log.exception("Git push exception for %s", repo_key)
        raise HTTPException(500, str(e))


@app.post("/api/git/{repo_key}/reset-to-remote")
async def git_reset_to_remote(repo_key: str):
    """Reset local to match remote, discarding all local changes."""
    target_dir = _get_repo_dir(repo_key)
    log.info("Git reset to remote (%s)", repo_key)
    try:
        git_env = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}
        subprocess.run(["git", "fetch", "origin"], cwd=str(target_dir),
                       capture_output=True, text=True, timeout=60, env=git_env)
        branch = _git_detect_branch(target_dir)
        result = subprocess.run(["git", "reset", "--hard", f"origin/{branch}"], cwd=str(target_dir),
                                capture_output=True, text=True, timeout=30)
        if result.returncode == 0:
            return {"ok": True, "message": f"Reset effectue sur origin/{branch}"}
        return {"ok": False, "message": result.stderr[:300]}
    except Exception as e:
        log.exception("Git reset exception for %s", repo_key)
        raise HTTPException(500, str(e))


# ── API: Git Commits history + checkout ───────────

@app.get("/api/git/{repo_key}/commits")
async def git_commits(repo_key: str):
    """Return last 10 commits."""
    target_dir = _get_repo_dir(repo_key)
    if not (target_dir / ".git").exists():
        return {"commits": []}
    try:
        result = subprocess.run(
            ["git", "log", "--pretty=format:%H|%ai|%D|%s", "-10"],
            cwd=str(target_dir), capture_output=True, text=True, timeout=10)
        commits = []
        for line in result.stdout.strip().splitlines():
            if not line:
                continue
            parts = line.split("|", 3)
            full_hash = parts[0]
            date = parts[1] if len(parts) > 1 else ""
            refs = parts[2] if len(parts) > 2 else ""
            subject = parts[3] if len(parts) > 3 else ""
            tags = [r.strip().replace("tag: ", "") for r in refs.split(",") if "tag:" in r]
            commits.append({
                "hash": full_hash, "short": full_hash[:7],
                "date": date.strip(), "tags": tags, "subject": subject.strip(),
            })
        return {"commits": commits}
    except Exception as e:
        raise HTTPException(500, str(e))


@app.post("/api/git/{repo_key}/checkout/{commit_hash}")
async def git_checkout(repo_key: str, commit_hash: str):
    """Rollback to an old commit's content on top of the latest remote commit.
    1. fetch + reset --hard origin/branch + clean -fd  (go to latest)
    2. git checkout <hash>  (get old version's files)
    3. Copy all files (except .git) to a temp dir
    4. fetch + reset --hard origin/branch + clean -fd  (back to latest)
    5. Delete working tree (except .git), copy temp files over
    Result: content from old commit, HEAD on latest remote commit."""
    import re, shutil, tempfile
    if not re.match(r'^[0-9a-f]{7,40}$', commit_hash):
        raise HTTPException(400, "Hash de commit invalide")
    target_dir = _get_repo_dir(repo_key)
    if not (target_dir / ".git").exists():
        raise HTTPException(400, "Repository non initialise")
    try:
        git_env = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}
        branch = _git_detect_branch(target_dir)

        def _reset_to_latest():
            subprocess.run(["git", "fetch", "origin"], cwd=str(target_dir),
                           capture_output=True, text=True, timeout=60, env=git_env)
            subprocess.run(["git", "reset", "--hard", f"origin/{branch}"], cwd=str(target_dir),
                           capture_output=True, text=True, timeout=30)
            subprocess.run(["git", "clean", "-fd"], cwd=str(target_dir),
                           capture_output=True, text=True, timeout=30)

        # 1. Reset to latest remote version
        _reset_to_latest()

        # 2. Checkout the old version
        co_r = subprocess.run(["git", "checkout", commit_hash], cwd=str(target_dir),
                               capture_output=True, text=True, timeout=30)
        if co_r.returncode != 0:
            _reset_to_latest()
            raise HTTPException(500, f"Checkout echoue: {co_r.stderr[:300]}")

        # 3. Copy all files (except .git) to a temp dir
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            for item in target_dir.iterdir():
                if item.name == ".git":
                    continue
                dest = tmp_path / item.name
                if item.is_dir():
                    shutil.copytree(str(item), str(dest))
                else:
                    shutil.copy2(str(item), str(dest))

            # 4. Reset back to latest remote version
            subprocess.run(["git", "checkout", branch], cwd=str(target_dir),
                           capture_output=True, text=True, timeout=30)
            _reset_to_latest()

            # 5. Delete working tree (except .git), copy temp files over
            for item in target_dir.iterdir():
                if item.name == ".git":
                    continue
                if item.is_dir():
                    shutil.rmtree(item)
                else:
                    item.unlink()
            for item in tmp_path.iterdir():
                dest = target_dir / item.name
                if item.is_dir():
                    shutil.copytree(str(item), str(dest))
                else:
                    shutil.copy2(str(item), str(dest))

        return {"ok": True, "message": f"Version {commit_hash[:7]} restauree. Faites un Commit pour la conserver."}
    except HTTPException:
        raise
    except Exception as e:
        log.exception("Git checkout exception")
        raise HTTPException(500, str(e))


# ── API: Git version browser (temp clone + checkout) ──

_version_temp_dirs: dict[str, tuple[Path, float]] = {}  # session_id -> (work_dir, created_at)
_VB_SESSION_TTL = 1800  # 30 minutes


def _vb_cleanup_stale():
    """Remove version-browse sessions older than TTL."""
    import shutil, time
    now = time.time()
    expired = [sid for sid, (_, ts) in _version_temp_dirs.items() if now - ts > _VB_SESSION_TTL]
    for sid in expired:
        work_dir, _ = _version_temp_dirs.pop(sid, (None, 0))
        if work_dir and work_dir.exists():
            shutil.rmtree(str(work_dir.parent), ignore_errors=True)


def _vb_cleanup_orphans():
    """Remove any lgview_* temp dirs left from previous runs."""
    import shutil, tempfile, glob
    tmp_root = tempfile.gettempdir()
    for d in glob.glob(os.path.join(tmp_root, "lgview_*")):
        shutil.rmtree(d, ignore_errors=True)
        log.info("Cleaned orphan version-browse dir: %s", d)


# Clean orphans on import (server startup)
_vb_cleanup_orphans()


@app.post("/api/git/{repo_key}/version-browse/{commit_hash}")
async def git_version_browse(repo_key: str, commit_hash: str):
    """Clone repo into temp dir and checkout a specific commit for browsing."""
    import re, shutil, tempfile, time, uuid
    # Clean stale sessions before creating a new one
    _vb_cleanup_stale()
    if not re.match(r'^[0-9a-f]{7,40}$', commit_hash):
        raise HTTPException(400, "Hash de commit invalide")
    target_dir = _get_repo_dir(repo_key)
    if not (target_dir / ".git").exists():
        raise HTTPException(400, "Repository non initialise")
    cfg = _get_repo_cfg(repo_key)
    repo_path = cfg.get("path", "")
    login = cfg.get("login", "")
    password = cfg.get("password", "")
    try:
        git_env = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}
        tmp = tempfile.mkdtemp(prefix="lgview_")
        tmp_path = Path(tmp)
        if repo_path:
            remote_url = _build_remote_url(repo_path, login, password)
            r = subprocess.run(["git", "clone", remote_url, "repo"], cwd=str(tmp_path),
                               capture_output=True, text=True, timeout=120, env=git_env)
            if r.returncode != 0:
                shutil.rmtree(tmp, ignore_errors=True)
                stderr = _git_sanitize(r.stderr, login, password)
                raise HTTPException(500, f"Clone echoue: {stderr[:300]}")
            work_dir = tmp_path / "repo"
        else:
            r = subprocess.run(["git", "clone", str(target_dir), "repo"], cwd=str(tmp_path),
                               capture_output=True, text=True, timeout=60, env=git_env)
            if r.returncode != 0:
                shutil.rmtree(tmp, ignore_errors=True)
                raise HTTPException(500, f"Clone local echoue: {r.stderr[:300]}")
            work_dir = tmp_path / "repo"
        co = subprocess.run(["git", "checkout", commit_hash], cwd=str(work_dir),
                            capture_output=True, text=True, timeout=30, env=git_env)
        if co.returncode != 0:
            shutil.rmtree(tmp, ignore_errors=True)
            raise HTTPException(500, f"Checkout echoue: {co.stderr[:300]}")
        session_id = str(uuid.uuid4())[:12]
        _version_temp_dirs[session_id] = (work_dir, time.time())
        return {"ok": True, "session_id": session_id}
    except HTTPException:
        raise
    except Exception as e:
        log.exception("Version browse exception")
        raise HTTPException(500, str(e))


@app.get("/api/git/version-browse/{session_id}/tree")
async def git_version_tree(session_id: str, path: str = ""):
    """List files/dirs at a path in a temp version browse session."""
    entry = _version_temp_dirs.get(session_id)
    work_dir = entry[0] if entry else None
    if not work_dir or not work_dir.exists():
        raise HTTPException(404, "Session introuvable ou expiree")
    target = work_dir / path if path else work_dir
    if not target.exists():
        raise HTTPException(404, f"Chemin introuvable: {path}")
    if not str(target.resolve()).startswith(str(work_dir.resolve())):
        raise HTTPException(403, "Acces interdit")
    items = []
    try:
        for item in sorted(target.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower())):
            if item.name == ".git":
                continue
            items.append({
                "name": item.name,
                "type": "dir" if item.is_dir() else "file",
                "path": str(item.relative_to(work_dir)).replace("\\", "/"),
            })
    except Exception as e:
        raise HTTPException(500, str(e))
    return {"items": items}


@app.get("/api/git/version-browse/{session_id}/file")
async def git_version_file(session_id: str, path: str = ""):
    """Read file content from a temp version browse session."""
    entry = _version_temp_dirs.get(session_id)
    work_dir = entry[0] if entry else None
    if not work_dir or not work_dir.exists():
        raise HTTPException(404, "Session introuvable ou expiree")
    if not path:
        raise HTTPException(400, "path requis")
    target = work_dir / path
    if not target.exists():
        raise HTTPException(404, f"Fichier introuvable: {path}")
    if not str(target.resolve()).startswith(str(work_dir.resolve())):
        raise HTTPException(403, "Acces interdit")
    if target.is_dir():
        raise HTTPException(400, "C'est un repertoire, pas un fichier")
    try:
        content = target.read_text(encoding="utf-8", errors="replace")
        # Limit to 100KB
        if len(content) > 100_000:
            content = content[:100_000] + "\n\n--- [tronque a 100KB] ---"
        return {"ok": True, "content": content, "path": path}
    except Exception as e:
        return {"ok": False, "content": f"Erreur lecture: {e}", "path": path}


@app.post("/api/git/version-browse/{session_id}/close")
async def git_version_close(session_id: str):
    """Clean up a temp version browse session."""
    import shutil
    entry = _version_temp_dirs.pop(session_id, None)
    if entry:
        work_dir = entry[0]
        if work_dir and work_dir.exists():
            shutil.rmtree(str(work_dir.parent), ignore_errors=True)
    return {"ok": True}


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
    """Send welcome/reset email using others.json + mail.json config.

    Reads password_reset config from others.json (smtp_name, template_name,
    from_address) and resolves SMTP + template from mail.json.
    Template variables: ${mail}, ${pwd}, ${UrlService}
    """
    import smtplib
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText

    others_cfg = _read_json(OTHERS_FILE) if OTHERS_FILE.exists() else {}
    reset_cfg = others_cfg.get("password_reset", {})
    mail_cfg = _read_json(MAIL_FILE) if MAIL_FILE.exists() else {}

    # Resolve SMTP by name from others.json
    smtp_name = reset_cfg.get("smtp_name", "")
    smtp_list = mail_cfg.get("smtp", [])
    if isinstance(smtp_list, dict):
        smtp_list = [smtp_list]
    smtp_cfg = next((s for s in smtp_list if s.get("name") == smtp_name), smtp_list[0] if smtp_list else {})

    smtp_host = smtp_cfg.get("host", "")
    smtp_port = int(smtp_cfg.get("port", 587))
    smtp_user = smtp_cfg.get("user", "")
    use_ssl = smtp_cfg.get("use_ssl", False)
    use_tls = smtp_cfg.get("use_tls", True)
    from_address = smtp_cfg.get("from_address", "") or smtp_user
    from_name = smtp_cfg.get("from_name", "ag.flow")

    # Resolve password from env var
    password_env = smtp_cfg.get("password_env", "SMTP_PASSWORD")
    env = _env_dict()
    smtp_password = env.get(password_env, "")

    if not all([smtp_host, smtp_user, smtp_password]):
        logging.warning("SMTP not configured — welcome email not sent (smtp_name=%s)", smtp_name)
        return False

    # Resolve template by name from others.json
    tpl_name = reset_cfg.get("template_name", "")
    tpl_list = mail_cfg.get("templates", [])
    if isinstance(tpl_list, dict):
        tpl_list = []
    tpl = next((t for t in tpl_list if t.get("name") == tpl_name), None)

    # Variable mapping
    variables = {"${mail}": to_email, "${pwd}": temp_password, "${UrlService}": reset_url}

    def _replace_vars(text: str) -> str:
        for k, v in variables.items():
            text = text.replace(k, v)
        return text

    if tpl:
        subject = _replace_vars(tpl.get("subject", "[LangGraph] Reinitialisation mot de passe"))
        body_text = _replace_vars(tpl.get("body", ""))
    else:
        subject = "[LangGraph] Bienvenue — Activez votre compte"
        body_text = ""

    # Build HTML (use template body if available, else default)
    if body_text:
        # Convert newlines to <br> for HTML
        html_body = body_text.replace("\n", "<br/>")
        html = f'<html><body style="font-family:sans-serif;color:#333">{html_body}</body></html>'
    else:
        from urllib.parse import quote
        default_link = f"{reset_url}/reset-password?mail={quote(to_email)}&pwd={quote(temp_password)}"
        html = f"""\
<html><body style="font-family:sans-serif;color:#333">
<h2>Bienvenue sur ag.flow</h2>
<p>Un compte a ete cree pour vous (<code>{to_email}</code>).</p>
<p>Votre mot de passe temporaire : <code style="background:#f0f0f0;padding:4px 8px;border-radius:4px;font-size:1.1em">{temp_password}</code></p>
<p>Cliquez sur le lien ci-dessous pour definir votre mot de passe :</p>
<p><a href="{default_link}" style="display:inline-block;padding:10px 24px;background:#3b82f6;color:white;text-decoration:none;border-radius:6px">Definir mon mot de passe</a></p>
</body></html>"""

    msg = MIMEMultipart("alternative")
    msg["From"] = f"{from_name} <{from_address}>"
    msg["To"] = to_email
    msg["Subject"] = subject
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
        logging.error("Failed to send welcome email: %s", e)
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
    # 1. Generate temporary password
    temp_password = _generate_password(12)
    # 2. Send reset email (before saving — if email fails, don't create user)
    hitl_host = _env_dict().get("HITL_PUBLIC_URL", "")
    if not hitl_host:
        hitl_host = "http://localhost:8090"
    reset_url = hitl_host.rstrip("/")
    email_sent = _send_welcome_email(email, temp_password, reset_url)
    # 3. Hash password and save to DB
    pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")
    hashed = pwd_ctx.hash(temp_password.encode("utf-8")[:72].decode("utf-8", errors="ignore"))
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
        return {"ok": True, "id": str(uid), "email_sent": email_sent}
    except psycopg.errors.UniqueViolation:
        raise HTTPException(409, "Email deja utilise")
    finally:
        conn.close()


@app.post("/api/hitl/users/{user_id}/resend-reset")
async def hitl_resend_reset(user_id: str):
    """Regenerate temp password and resend reset email."""
    import psycopg
    from passlib.context import CryptContext
    uri = _env_dict().get("DATABASE_URI", "")
    if not uri:
        raise HTTPException(500, "DATABASE_URI not configured")
    conn = psycopg.connect(uri, autocommit=True)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT email FROM project.hitl_users WHERE id = %s", (user_id,))
            row = cur.fetchone()
            if not row:
                raise HTTPException(404, "Utilisateur non trouve")
            email = row[0]
            # Generate new temp password
            temp_password = _generate_password(12)
            # Send reset email first
            hitl_host = _env_dict().get("HITL_PUBLIC_URL", "")
            if not hitl_host:
                hitl_host = "http://localhost:8090"
            reset_url = hitl_host.rstrip("/")
            email_sent = _send_welcome_email(email, temp_password, reset_url)
            # Then hash and update password
            pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")
            hashed = pwd_ctx.hash(temp_password.encode("utf-8")[:72].decode("utf-8", errors="ignore"))
            cur.execute("UPDATE project.hitl_users SET password_hash = %s WHERE id = %s", (hashed, user_id))
        return {"ok": True, "email_sent": email_sent}
    finally:
        conn.close()


@app.put("/api/hitl/users/{user_id}")
async def hitl_update_user(user_id: str, req: Request):
    import psycopg
    body = await req.json()
    display_name = body.get("display_name", "").strip()
    role = body.get("role", "")
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


# ── Avatar Management ───────────────────────────────────────────
AVATARS_DIR = SHARED_DIR / "Avatars"

DEFAULT_AVATAR_PROMPT = """# Avatar Generator

Generate a portrait avatar for the character **{character}**.

Style: {theme_description}

Requirements:
- Square format (1024x1024)
- Face/bust portrait
- Professional quality
- Consistent style within the theme
- No text in the image

Character description: Create a unique visual identity for {character} that reflects their role and personality. The avatar should be immediately recognizable and work well at small sizes (48px).
"""


def _avatar_slug(name: str) -> str:
    """Slugify a name for avatar theme/character directory names."""
    return re.sub(r'[^a-z0-9-]', '', name.lower().replace(' ', '-').replace('_', '-'))


async def _call_admin_llm(prompt: str) -> str:
    """Call the admin LLM provider to generate text."""
    # Configuration scope: Shared/ first, then config/
    data = _read_json(SHARED_LLM_FILE)
    if not data.get("providers"):
        data = _read_json(LLM_PROVIDERS_FILE)
    if not data.get("providers"):
        raise HTTPException(500, "No LLM providers configured")

    providers = data["providers"]
    admin_id = data.get("admin_llm") or data.get("default", "")
    if not admin_id or admin_id not in providers:
        # Fallback: pick the first provider
        admin_id = next(iter(providers))
    provider = providers[admin_id]

    ptype = provider.get("type", "openai")
    model = provider.get("model", "")
    env_key = provider.get("env_key", "")
    api_key = os.environ.get(env_key, "") if env_key else ""
    temperature = provider.get("temperature", 0.7)
    max_tokens = provider.get("max_tokens", 4096)

    async with httpx.AsyncClient(timeout=120) as client:
        if ptype == "anthropic":
            resp = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": model,
                    "max_tokens": max_tokens,
                    "temperature": temperature,
                    "messages": [{"role": "user", "content": prompt}],
                },
            )
            resp.raise_for_status()
            content_blocks = resp.json().get("content", [])
            return "".join(b.get("text", "") for b in content_blocks)

        elif ptype == "google":
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
            resp = await client.post(
                url,
                headers={"content-type": "application/json"},
                json={
                    "contents": [{"parts": [{"text": prompt}]}],
                    "generationConfig": {"temperature": temperature, "maxOutputTokens": max_tokens},
                },
            )
            resp.raise_for_status()
            candidates = resp.json().get("candidates", [])
            if candidates:
                parts = candidates[0].get("content", {}).get("parts", [])
                return "".join(p.get("text", "") for p in parts)
            return ""

        elif ptype == "ollama":
            base_url = provider.get("base_url", "http://localhost:11434")
            resp = await client.post(
                f"{base_url}/api/chat",
                json={
                    "model": model,
                    "messages": [{"role": "user", "content": prompt}],
                    "stream": False,
                    "options": {"temperature": temperature},
                },
            )
            resp.raise_for_status()
            return resp.json().get("message", {}).get("content", "")

        else:
            # OpenAI-compatible (openai, azure, deepseek, moonshot, groq, mistral)
            if ptype == "azure":
                endpoint = provider.get("azure_endpoint", "").rstrip("/")
                deployment = provider.get("azure_deployment", model)
                api_ver = provider.get("api_version", "2024-12-01-preview")
                url = f"{endpoint}/openai/deployments/{deployment}/chat/completions?api-version={api_ver}"
                headers = {"api-key": api_key, "content-type": "application/json"}
            elif ptype == "deepseek":
                url = "https://api.deepseek.com/v1/chat/completions"
                headers = {"Authorization": f"Bearer {api_key}", "content-type": "application/json"}
            elif ptype == "moonshot":
                url = "https://api.moonshot.cn/v1/chat/completions"
                headers = {"Authorization": f"Bearer {api_key}", "content-type": "application/json"}
            elif ptype == "groq":
                url = "https://api.groq.com/openai/v1/chat/completions"
                headers = {"Authorization": f"Bearer {api_key}", "content-type": "application/json"}
            elif ptype == "mistral":
                url = "https://api.mistral.ai/v1/chat/completions"
                headers = {"Authorization": f"Bearer {api_key}", "content-type": "application/json"}
            else:
                url = "https://api.openai.com/v1/chat/completions"
                headers = {"Authorization": f"Bearer {api_key}", "content-type": "application/json"}

            resp = await client.post(
                url,
                headers=headers,
                json={
                    "model": model,
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                    "messages": [{"role": "user", "content": prompt}],
                },
            )
            resp.raise_for_status()
            choices = resp.json().get("choices", [])
            if choices:
                return choices[0].get("message", {}).get("content", "")
            return ""


# ── Avatar helpers (shared logic for Configuration + Production) ──

def _avatar_list_themes(base_dir: Path, url_prefix: str):
    base_dir.mkdir(parents=True, exist_ok=True)
    themes = []
    for d in sorted(base_dir.iterdir()):
        if not d.is_dir():
            continue
        characters = [f.stem for f in d.iterdir() if f.suffix == ".md" and f.name != "prompt.md"]
        image_count = sum(1 for f in d.rglob("*.png"))
        entry = {"slug": d.name, "name": d.name, "description": "", "character_count": len(characters), "image_count": image_count}
        prompt_file = d / "prompt.md"
        if prompt_file.exists():
            for line in prompt_file.read_text(encoding="utf-8").strip().splitlines():
                stripped = line.strip()
                if stripped and not stripped.startswith("#"):
                    entry["description"] = stripped
                    break
        themes.append(entry)
    return themes

def _avatar_create_theme(base_dir: Path, body: dict):
    name = body.get("name", "").strip()
    if not name:
        raise HTTPException(400, "name is required")
    slug = _avatar_slug(name)
    if not slug:
        raise HTTPException(400, "Invalid theme name")
    theme_dir = base_dir / slug
    if theme_dir.exists():
        return {"slug": slug, "name": name, "exists": True}
    theme_dir.mkdir(parents=True, exist_ok=True)
    description = body.get("description", "").strip()
    prompt_content = DEFAULT_AVATAR_PROMPT.replace("{theme_description}", description or name)
    (theme_dir / "prompt.md").write_text(prompt_content, encoding="utf-8")
    return {"slug": slug, "name": name}

def _avatar_get_theme(base_dir: Path, url_prefix: str, theme: str):
    theme_dir = base_dir / theme
    if not theme_dir.exists() or not theme_dir.is_dir():
        raise HTTPException(404, f"Theme '{theme}' not found")
    prompt_file = theme_dir / "prompt.md"
    prompt_template = prompt_file.read_text(encoding="utf-8") if prompt_file.exists() else ""
    characters = []
    for f in sorted(theme_dir.glob("*.md")):
        if f.name == "prompt.md":
            continue
        char_name = f.stem
        images = sorted([
            {"filename": img.name, "url": f"{url_prefix}/{theme}/{img.name}"}
            for img in theme_dir.iterdir()
            if img.is_file() and img.name.startswith(char_name + ".") and img.suffix.lower() in (".png", ".jpg", ".webp")
        ])
        prompt_content = f.read_text(encoding="utf-8") if f.exists() else ""
        characters.append({"name": char_name, "images": images, "prompt": prompt_content})
    return {"name": theme, "prompt_template": prompt_template, "characters": characters}

def _avatar_delete_theme(base_dir: Path, theme: str):
    theme_dir = base_dir / theme
    if not theme_dir.exists() or not theme_dir.is_dir():
        raise HTTPException(404, f"Theme '{theme}' not found")
    shutil.rmtree(theme_dir)
    return {"ok": True}

def _avatar_get_prompt(base_dir: Path, theme: str):
    prompt_file = base_dir / theme / "prompt.md"
    if not prompt_file.exists():
        raise HTTPException(404, f"Theme '{theme}' or prompt.md not found")
    return {"content": prompt_file.read_text(encoding="utf-8")}

def _avatar_put_prompt(base_dir: Path, theme: str, body: dict):
    theme_dir = base_dir / theme
    if not theme_dir.exists():
        raise HTTPException(404, f"Theme '{theme}' not found")
    (theme_dir / "prompt.md").write_text(body.get("content", ""), encoding="utf-8")
    return {"ok": True}

def _avatar_list_characters(base_dir: Path, url_prefix: str, theme: str):
    theme_dir = base_dir / theme
    if not theme_dir.exists():
        raise HTTPException(404, f"Theme '{theme}' not found")
    characters = []
    for f in sorted(theme_dir.iterdir()):
        if f.suffix != ".md" or f.name == "prompt.md":
            continue
        slug = f.stem
        images = sorted([img.name for img in theme_dir.iterdir() if img.suffix == ".png" and img.name.startswith(slug + ".")])
        characters.append({"slug": slug, "name": slug, "images": images, "image_urls": [f"{url_prefix}/{theme}/{img}" for img in images]})
    return {"characters": characters}

async def _avatar_create_character(base_dir: Path, theme: str, body: dict):
    theme_dir = base_dir / theme
    if not theme_dir.exists():
        raise HTTPException(404, f"Theme '{theme}' not found")
    character = body.get("character", "").strip()
    if not character:
        raise HTTPException(400, "character is required")
    slug = _avatar_slug(character)
    if not slug:
        raise HTTPException(400, "Invalid character name")
    char_file = theme_dir / f"{slug}.md"
    if char_file.exists():
        raise HTTPException(409, f"Character '{slug}' already exists in theme '{theme}'")
    prompt_file = theme_dir / "prompt.md"
    template = prompt_file.read_text(encoding="utf-8") if prompt_file.exists() else DEFAULT_AVATAR_PROMPT
    gen_prompt = (
        f"Based on this avatar theme template:\n\n{template}\n\n"
        f"Generate a detailed, specific image generation prompt for the character: {character}\n\n"
        f"The prompt should describe the visual appearance, style, colors, and mood "
        f"for generating a portrait avatar of this character. "
        f"Output ONLY the image generation prompt text, nothing else."
    )
    try:
        result = await _call_admin_llm(gen_prompt)
    except httpx.HTTPStatusError as exc:
        raise HTTPException(502, f"LLM call failed: {exc.response.status_code}")
    except Exception as exc:
        raise HTTPException(502, f"LLM call failed: {exc}")
    char_file.write_text(result.strip(), encoding="utf-8")
    return {"slug": slug, "name": character, "content": result.strip()}

def _avatar_get_character(base_dir: Path, theme: str, character: str):
    char_file = base_dir / theme / f"{character}.md"
    if not char_file.exists():
        raise HTTPException(404, f"Character '{character}' not found in theme '{theme}'")
    return {"slug": character, "content": char_file.read_text(encoding="utf-8")}

def _avatar_put_character(base_dir: Path, theme: str, character: str, body: dict):
    char_file = base_dir / theme / f"{character}.md"
    if not char_file.exists():
        raise HTTPException(404, f"Character '{character}' not found in theme '{theme}'")
    char_file.write_text(body.get("content") or body.get("prompt") or "", encoding="utf-8")
    return {"ok": True}

def _avatar_delete_character(base_dir: Path, theme: str, character: str):
    theme_dir = base_dir / theme
    if not theme_dir.exists():
        raise HTTPException(404, f"Theme '{theme}' not found")
    char_file = theme_dir / f"{character}.md"
    deleted_files = []
    if char_file.exists():
        char_file.unlink()
        deleted_files.append(char_file.name)
    for img in list(theme_dir.iterdir()):
        if img.suffix == ".png" and img.name.startswith(character + "."):
            img.unlink()
            deleted_files.append(img.name)
    if not deleted_files:
        raise HTTPException(404, f"Character '{character}' not found in theme '{theme}'")
    return {"ok": True, "deleted": deleted_files}

async def _avatar_generate_image(base_dir: Path, url_prefix: str, theme: str, character: str):
    import base64 as b64
    theme_dir = base_dir / theme
    char_file = theme_dir / f"{character}.md"
    if not char_file.exists():
        raise HTTPException(404, f"Character '{character}' not found in theme '{theme}'")
    char_prompt = char_file.read_text(encoding="utf-8").strip()
    if not char_prompt:
        raise HTTPException(400, "Le prompt du personnage est vide — editez-le avant de generer une image")
    data = _read_json(SHARED_LLM_FILE)
    if not data.get("providers"):
        data = _read_json(LLM_PROVIDERS_FILE)
    providers = data.get("providers", {})
    dalle_provider = None
    for pid, prov in providers.items():
        model_name = prov.get("model", "").lower()
        prov_type = prov.get("type", "").lower()
        if "dall-e" in model_name or "dalle" in model_name or prov_type == "dall-e":
            dalle_provider = prov
            break
    if not dalle_provider:
        openai_key = os.environ.get("OPENAI_API_KEY", "")
        if not openai_key:
            raise HTTPException(400, "No DALL-E provider configured and no OPENAI_API_KEY found")
        dalle_provider = {"type": "openai", "model": "dall-e-3", "env_key": "OPENAI_API_KEY"}
    env_key = dalle_provider.get("env_key", "OPENAI_API_KEY")
    api_key = os.environ.get(env_key, "")
    if not api_key:
        raise HTTPException(400, f"API key not set: {env_key}")
    model = dalle_provider.get("model", "dall-e-3")
    async with httpx.AsyncClient(timeout=120) as client:
        resp = await client.post("https://api.openai.com/v1/images/generations", headers={"Authorization": f"Bearer {api_key}", "content-type": "application/json"}, json={"model": model, "prompt": char_prompt[:4000], "n": 1, "size": "1024x1024", "response_format": "b64_json"})
        if resp.status_code != 200:
            raise HTTPException(502, f"DALL-E API error ({resp.status_code}): {resp.text[:500]}")
        result = resp.json()
    b64_data = result.get("data", [{}])[0].get("b64_json", "")
    if not b64_data:
        raise HTTPException(502, "No image data returned from DALL-E")
    image_bytes = b64.b64decode(b64_data)
    existing = [f.name for f in theme_dir.iterdir() if f.suffix == ".png" and f.name.startswith(character + ".")]
    next_num = len(existing) + 1
    filename = f"{character}.{next_num}.png"
    (theme_dir / filename).write_bytes(image_bytes)
    return {"filename": filename, "url": f"{url_prefix}/{theme}/{filename}"}

def _avatar_list_all_images(base_dir: Path, url_prefix: str, theme: str):
    theme_dir = base_dir / theme
    if not theme_dir.exists():
        raise HTTPException(404, f"Theme '{theme}' not found")
    results = []
    for f in sorted(theme_dir.iterdir()):
        if not f.is_file() or f.suffix.lower() not in (".png", ".jpg", ".webp"):
            continue
        parts = f.stem.split(".")
        char_name = parts[0] if parts else f.stem
        results.append({"filename": f.name, "url": f"{url_prefix}/{theme}/{f.name}", "character": char_name})
    return results

def _avatar_list_char_images(base_dir: Path, url_prefix: str, theme: str, character: str):
    theme_dir = base_dir / theme
    if not theme_dir.exists():
        raise HTTPException(404, f"Theme '{theme}' not found")
    images = sorted([f.name for f in theme_dir.iterdir() if f.suffix == ".png" and f.name.startswith(character + ".")])
    return {"images": images, "urls": [f"{url_prefix}/{theme}/{img}" for img in images]}

async def _avatar_upload_image(base_dir: Path, url_prefix: str, theme: str, character: str, file: UploadFile):
    theme_dir = base_dir / theme
    slug = _avatar_slug(character)
    if not theme_dir.exists():
        raise HTTPException(404, f"Theme '{theme}' not found")
    content = await file.read()
    ext = os.path.splitext(file.filename or "img.png")[1].lower()
    if ext not in (".png", ".jpg", ".jpeg", ".webp"):
        raise HTTPException(400, "Format image non supporte (png, jpg, webp)")
    existing = sorted(theme_dir.glob(f"{slug}.*.png")) + sorted(theme_dir.glob(f"{slug}.*.jpg")) + sorted(theme_dir.glob(f"{slug}.*.webp"))
    next_num = len(existing) + 1
    filename = f"{slug}.{next_num}{ext}"
    (theme_dir / filename).write_bytes(content)
    return {"filename": filename, "url": f"{url_prefix}/{theme}/{filename}"}

def _avatar_delete_image(base_dir: Path, theme: str, character: str, filename: str):
    filepath = base_dir / theme / filename
    if not filepath.exists():
        raise HTTPException(404, f"Image '{filename}' not found")
    if not filename.startswith(character + "."):
        raise HTTPException(400, f"Image '{filename}' does not belong to character '{character}'")
    filepath.unlink()
    return {"ok": True}


# ── Configuration avatar endpoints (Shared/Avatars) ─────────────

@app.get("/api/avatars/themes")
async def list_avatar_themes():
    return _avatar_list_themes(AVATARS_DIR, "/avatars")

@app.post("/api/avatars/themes")
async def create_avatar_theme(body: dict = Body(...)):
    return _avatar_create_theme(AVATARS_DIR, body)

@app.get("/api/avatars/themes/{theme}")
async def get_avatar_theme(theme: str):
    return _avatar_get_theme(AVATARS_DIR, "/avatars", theme)

@app.delete("/api/avatars/themes/{theme}")
async def delete_avatar_theme(theme: str):
    return _avatar_delete_theme(AVATARS_DIR, theme)

@app.get("/api/avatars/themes/{theme}/prompt")
async def get_avatar_theme_prompt(theme: str):
    return _avatar_get_prompt(AVATARS_DIR, theme)

@app.put("/api/avatars/themes/{theme}/prompt")
async def update_avatar_theme_prompt(theme: str, body: dict = Body(...)):
    return _avatar_put_prompt(AVATARS_DIR, theme, body)

@app.get("/api/avatars/themes/{theme}/characters")
async def list_avatar_characters(theme: str):
    return _avatar_list_characters(AVATARS_DIR, "/avatars", theme)

@app.post("/api/avatars/themes/{theme}/characters")
async def create_avatar_character(theme: str, body: dict = Body(...)):
    return await _avatar_create_character(AVATARS_DIR, theme, body)

@app.get("/api/avatars/themes/{theme}/characters/{character}")
async def get_avatar_character(theme: str, character: str):
    return _avatar_get_character(AVATARS_DIR, theme, character)

@app.put("/api/avatars/themes/{theme}/characters/{character}")
async def update_avatar_character(theme: str, character: str, body: dict = Body(...)):
    return _avatar_put_character(AVATARS_DIR, theme, character, body)

@app.delete("/api/avatars/themes/{theme}/characters/{character}")
async def delete_avatar_character(theme: str, character: str):
    return _avatar_delete_character(AVATARS_DIR, theme, character)

@app.post("/api/avatars/themes/{theme}/characters/{character}/generate")
async def generate_avatar_image(theme: str, character: str):
    return await _avatar_generate_image(AVATARS_DIR, "/avatars", theme, character)

@app.get("/api/avatars/themes/{theme}/all-images")
async def list_all_theme_images(theme: str):
    return _avatar_list_all_images(AVATARS_DIR, "/avatars", theme)

@app.get("/api/avatars/themes/{theme}/characters/{character}/images")
async def list_avatar_images(theme: str, character: str):
    return _avatar_list_char_images(AVATARS_DIR, "/avatars", theme, character)

@app.post("/api/avatars/themes/{theme}/characters/{character}/upload")
async def upload_avatar_image(theme: str, character: str, file: UploadFile = File(...)):
    return await _avatar_upload_image(AVATARS_DIR, "/avatars", theme, character, file)

@app.delete("/api/avatars/themes/{theme}/characters/{character}/images/{filename}")
async def delete_avatar_image(theme: str, character: str, filename: str):
    return _avatar_delete_image(AVATARS_DIR, theme, character, filename)


# Mount avatar images as static files
AVATARS_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/avatars", StaticFiles(directory=str(AVATARS_DIR)), name="avatars")


# ── Production avatar endpoints (config/Avatars) ────────────────

PROD_AVATARS_DIR = CONFIGS / "Avatars"
PROD_AVATARS_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/prod-avatars", StaticFiles(directory=str(PROD_AVATARS_DIR)), name="prod-avatars")

@app.get("/api/prod-avatars/themes")
async def list_prod_avatar_themes():
    return _avatar_list_themes(PROD_AVATARS_DIR, "/prod-avatars")

@app.post("/api/prod-avatars/themes")
async def create_prod_avatar_theme(body: dict = Body(...)):
    return _avatar_create_theme(PROD_AVATARS_DIR, body)

@app.get("/api/prod-avatars/themes/{theme}")
async def get_prod_avatar_theme(theme: str):
    return _avatar_get_theme(PROD_AVATARS_DIR, "/prod-avatars", theme)

@app.delete("/api/prod-avatars/themes/{theme}")
async def delete_prod_avatar_theme(theme: str):
    return _avatar_delete_theme(PROD_AVATARS_DIR, theme)

@app.get("/api/prod-avatars/themes/{theme}/prompt")
async def get_prod_avatar_theme_prompt(theme: str):
    return _avatar_get_prompt(PROD_AVATARS_DIR, theme)

@app.put("/api/prod-avatars/themes/{theme}/prompt")
async def update_prod_avatar_theme_prompt(theme: str, body: dict = Body(...)):
    return _avatar_put_prompt(PROD_AVATARS_DIR, theme, body)

@app.get("/api/prod-avatars/themes/{theme}/characters")
async def list_prod_avatar_characters(theme: str):
    return _avatar_list_characters(PROD_AVATARS_DIR, "/prod-avatars", theme)

@app.post("/api/prod-avatars/themes/{theme}/characters")
async def create_prod_avatar_character(theme: str, body: dict = Body(...)):
    return await _avatar_create_character(PROD_AVATARS_DIR, theme, body)

@app.get("/api/prod-avatars/themes/{theme}/characters/{character}")
async def get_prod_avatar_character(theme: str, character: str):
    return _avatar_get_character(PROD_AVATARS_DIR, theme, character)

@app.put("/api/prod-avatars/themes/{theme}/characters/{character}")
async def update_prod_avatar_character(theme: str, character: str, body: dict = Body(...)):
    return _avatar_put_character(PROD_AVATARS_DIR, theme, character, body)

@app.delete("/api/prod-avatars/themes/{theme}/characters/{character}")
async def delete_prod_avatar_character(theme: str, character: str):
    return _avatar_delete_character(PROD_AVATARS_DIR, theme, character)

@app.post("/api/prod-avatars/themes/{theme}/characters/{character}/generate")
async def generate_prod_avatar_image(theme: str, character: str):
    return await _avatar_generate_image(PROD_AVATARS_DIR, "/prod-avatars", theme, character)

@app.get("/api/prod-avatars/themes/{theme}/all-images")
async def list_all_prod_theme_images(theme: str):
    return _avatar_list_all_images(PROD_AVATARS_DIR, "/prod-avatars", theme)

@app.get("/api/prod-avatars/themes/{theme}/characters/{character}/images")
async def list_prod_avatar_char_images(theme: str, character: str):
    return _avatar_list_char_images(PROD_AVATARS_DIR, "/prod-avatars", theme, character)

@app.post("/api/prod-avatars/themes/{theme}/characters/{character}/upload")
async def upload_prod_avatar_image(theme: str, character: str, file: UploadFile = File(...)):
    return await _avatar_upload_image(PROD_AVATARS_DIR, "/prod-avatars", theme, character, file)

@app.delete("/api/prod-avatars/themes/{theme}/characters/{character}/images/{filename}")
async def delete_prod_avatar_image(theme: str, character: str, filename: str):
    return _avatar_delete_image(PROD_AVATARS_DIR, theme, character, filename)


@app.post("/api/prod-avatars/import-from-config")
async def import_avatars_from_config(body: dict = Body(...)):
    """Import avatar themes/images from Shared/Avatars to config/Avatars.

    Body: { "themes": ["theme1"], "characters": {"theme1": ["char1", "char2"]} }
    If characters is empty for a theme, copies the entire theme.
    Returns info about what was overwritten.
    """
    theme_names = body.get("themes", [])
    char_filter = body.get("characters", {})  # theme -> [characters] or empty=all
    if not theme_names:
        raise HTTPException(400, "Aucun theme selectionne")

    imported = []
    overwritten = []
    for tname in theme_names:
        src_dir = AVATARS_DIR / tname
        if not src_dir.exists():
            continue
        dst_dir = PROD_AVATARS_DIR / tname
        chars_to_copy = char_filter.get(tname, [])

        if not chars_to_copy:
            # Copy entire theme
            existed = dst_dir.exists()
            if existed:
                overwritten.append(tname)
                shutil.rmtree(dst_dir)
            shutil.copytree(src_dir, dst_dir)
            imported.append({"theme": tname, "mode": "full", "overwritten": existed})
        else:
            # Copy only selected characters + their images
            dst_dir.mkdir(parents=True, exist_ok=True)
            # Always copy prompt.md
            src_prompt = src_dir / "prompt.md"
            if src_prompt.exists():
                shutil.copy2(src_prompt, dst_dir / "prompt.md")
            for char_name in chars_to_copy:
                # Copy .md file
                src_md = src_dir / f"{char_name}.md"
                if src_md.exists():
                    dst_md = dst_dir / f"{char_name}.md"
                    char_existed = dst_md.exists()
                    shutil.copy2(src_md, dst_md)
                # Copy all images for this character
                imgs_copied = 0
                for f in src_dir.iterdir():
                    if f.is_file() and f.name.startswith(char_name + ".") and f.suffix.lower() in (".png", ".jpg", ".webp"):
                        dst_img = dst_dir / f.name
                        if dst_img.exists():
                            overwritten.append(f"{tname}/{f.name}")
                        shutil.copy2(f, dst_img)
                        imgs_copied += 1
                imported.append({"theme": tname, "character": char_name, "images": imgs_copied})

    return {"ok": True, "imported": imported, "overwritten": overwritten}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)

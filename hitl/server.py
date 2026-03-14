"""HITL Console — Standalone FastAPI app for Human-In-The-Loop management."""
import json
import logging
import os
import time

# Log version at startup
logging.basicConfig(level=logging.INFO)
_log = logging.getLogger(__name__)
try:
    for _vp in ["/project/.version", "/app/.version", os.path.join(os.path.dirname(__file__), "..", ".version")]:
        if os.path.isfile(_vp):
            _log.info("LandGraph version: %s", open(_vp).read().strip())
            break
    else:
        _log.info("LandGraph version: dev (no .version file)")
except Exception:
    pass
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from typing import Optional

import psycopg
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel
from starlette.requests import Request

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s %(message)s")
logger = logging.getLogger("hitl-console")

# ── Config ──────────────────────────────────────
DATABASE_URI = os.getenv("DATABASE_URI", "")
JWT_ALGORITHM = "HS256"


def _load_hitl_config() -> dict:
    """Load hitl.json from config directory."""
    for path in ["/app/config/hitl.json", "config/hitl.json"]:
        if os.path.exists(path):
            with open(path) as f:
                return json.load(f)
    return {}


_hitl_cfg = _load_hitl_config()
_auth_cfg = _hitl_cfg.get("auth", {})
_google_cfg = _hitl_cfg.get("google_oauth", {})

JWT_SECRET = os.getenv("HITL_JWT_SECRET", os.getenv("MCP_SECRET", "change-me-hitl-secret"))
JWT_EXPIRE_HOURS = int(_auth_cfg.get("jwt_expire_hours", 24))
GOOGLE_ENABLED = _google_cfg.get("enabled", False)
GOOGLE_CLIENT_ID = _google_cfg.get("client_id", "")
GOOGLE_ALLOWED_DOMAINS = _google_cfg.get("allowed_domains", [])

pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")


def _truncate_pw(password: str) -> str:
    """Truncate password to 72 bytes (bcrypt limit)."""
    return password.encode("utf-8")[:72].decode("utf-8", errors="ignore")


def get_conn():
    return psycopg.connect(DATABASE_URI, autocommit=True)


# ── Config file helpers ────────────────────────────
_CONFIG_DIR = None

def _find_config_dir():
    global _CONFIG_DIR
    if _CONFIG_DIR:
        return _CONFIG_DIR
    for candidate in ["/app/config", "config", "../config"]:
        if os.path.isdir(candidate) and os.path.isfile(os.path.join(candidate, "teams.json")):
            _CONFIG_DIR = candidate
            return _CONFIG_DIR
    return "config"

def _read_config(filename):
    path = os.path.join(_find_config_dir(), filename)
    if os.path.isfile(path):
        with open(path) as f:
            return json.load(f)
    return {}


def _send_reset_email(to_email: str, temp_password: str):
    """Send reset email using others.json + mail.json config."""
    import smtplib
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText
    from urllib.parse import quote

    others_cfg = _read_config("others.json")
    reset_cfg = others_cfg.get("password_reset", {})
    mail_cfg = _read_config("mail.json")

    # Resolve SMTP
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
    from_name = smtp_cfg.get("from_name", "LandGraph")

    password_env = smtp_cfg.get("password_env", "SMTP_PASSWORD")
    smtp_password = os.getenv(password_env, "")

    if not all([smtp_host, smtp_user, smtp_password]):
        logger.warning("SMTP not configured — reset email not sent")
        return False

    # Resolve template
    tpl_name = reset_cfg.get("template_name", "")
    tpl_list = mail_cfg.get("templates", [])
    if isinstance(tpl_list, dict):
        tpl_list = []
    tpl = next((t for t in tpl_list if t.get("name") == tpl_name), None)

    # Build reset URL
    hitl_host = os.getenv("HITL_PUBLIC_URL", "http://localhost:8090").rstrip("/")
    variables = {"${mail}": to_email, "${pwd}": temp_password, "${UrlService}": hitl_host}

    def _replace_vars(text):
        for k, v in variables.items():
            text = text.replace(k, v)
        return text

    if tpl:
        subject = _replace_vars(tpl.get("subject", "[LangGraph] Reinitialisation mot de passe"))
        body_text = _replace_vars(tpl.get("body", ""))
    else:
        subject = "[LangGraph] Bienvenue — Activez votre compte"
        body_text = ""

    if body_text:
        html = f'<html><body style="font-family:sans-serif;color:#333">{body_text.replace(chr(10), "<br/>")}</body></html>'
    else:
        default_link = f"{hitl_host}/reset-password?mail={quote(to_email)}&pwd={quote(temp_password)}"
        html = f"""\
<html><body style="font-family:sans-serif;color:#333">
<h2>Bienvenue sur LandGraph</h2>
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
        logger.error("Failed to send reset email: %s", e)
        return False


def _ensure_pm_tables(cur):
    """Create Production Manager tables if they don't exist."""
    cur.execute("""
        CREATE TABLE IF NOT EXISTS project.pm_issue_counters (
            team_id TEXT PRIMARY KEY,
            next_seq INTEGER DEFAULT 1
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS project.pm_projects (
            id SERIAL PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT DEFAULT '',
            lead TEXT NOT NULL,
            team_id TEXT NOT NULL,
            color TEXT DEFAULT '#6366f1',
            status TEXT DEFAULT 'on-track' CHECK (status IN ('on-track', 'at-risk', 'off-track')),
            start_date DATE,
            target_date DATE,
            created_by TEXT,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            updated_at TIMESTAMPTZ DEFAULT NOW()
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS project.pm_project_members (
            project_id INTEGER REFERENCES project.pm_projects(id) ON DELETE CASCADE,
            user_name TEXT NOT NULL,
            role TEXT DEFAULT 'member' CHECK (role IN ('lead', 'member')),
            PRIMARY KEY(project_id, user_name)
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS project.pm_issues (
            id TEXT PRIMARY KEY,
            project_id INTEGER REFERENCES project.pm_projects(id) ON DELETE SET NULL,
            title TEXT NOT NULL,
            description TEXT DEFAULT '',
            status TEXT DEFAULT 'backlog' CHECK (status IN ('backlog', 'todo', 'in-progress', 'in-review', 'done')),
            priority INTEGER DEFAULT 3 CHECK (priority BETWEEN 1 AND 4),
            assignee TEXT,
            team_id TEXT NOT NULL,
            tags TEXT[] DEFAULT '{}',
            created_by TEXT,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            updated_at TIMESTAMPTZ DEFAULT NOW()
        )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_pm_issues_project ON project.pm_issues(project_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_pm_issues_status ON project.pm_issues(status)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_pm_issues_team ON project.pm_issues(team_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_pm_issues_assignee ON project.pm_issues(assignee)")
    cur.execute("""
        CREATE TABLE IF NOT EXISTS project.pm_issue_relations (
            id SERIAL PRIMARY KEY,
            type TEXT NOT NULL CHECK (type IN ('blocks', 'relates-to', 'parent', 'duplicates')),
            source_issue_id TEXT NOT NULL REFERENCES project.pm_issues(id) ON DELETE CASCADE,
            target_issue_id TEXT NOT NULL REFERENCES project.pm_issues(id) ON DELETE CASCADE,
            reason TEXT DEFAULT '',
            created_by TEXT,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            UNIQUE(type, source_issue_id, target_issue_id)
        )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_pm_relations_source ON project.pm_issue_relations(source_issue_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_pm_relations_target ON project.pm_issue_relations(target_issue_id)")
    cur.execute("""
        CREATE TABLE IF NOT EXISTS project.pm_pull_requests (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            author TEXT NOT NULL,
            issue_id TEXT REFERENCES project.pm_issues(id) ON DELETE SET NULL,
            status TEXT DEFAULT 'draft' CHECK (status IN ('pending', 'approved', 'changes_requested', 'draft')),
            additions INTEGER DEFAULT 0,
            deletions INTEGER DEFAULT 0,
            files INTEGER DEFAULT 0,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            updated_at TIMESTAMPTZ DEFAULT NOW()
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS project.pm_inbox (
            id SERIAL PRIMARY KEY,
            user_email TEXT NOT NULL,
            type TEXT NOT NULL CHECK (type IN ('mention', 'assign', 'comment', 'status', 'review', 'blocked', 'unblocked', 'dependency_added')),
            text TEXT NOT NULL,
            issue_id TEXT,
            related_issue_id TEXT,
            relation_type TEXT,
            avatar TEXT,
            read BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMPTZ DEFAULT NOW()
        )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_pm_inbox_user ON project.pm_inbox(user_email, read, created_at DESC)")
    cur.execute("""
        CREATE TABLE IF NOT EXISTS project.pm_activity (
            id SERIAL PRIMARY KEY,
            project_id INTEGER REFERENCES project.pm_projects(id) ON DELETE CASCADE,
            user_name TEXT NOT NULL,
            action TEXT NOT NULL,
            issue_id TEXT,
            detail TEXT,
            created_at TIMESTAMPTZ DEFAULT NOW()
        )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_pm_activity_project ON project.pm_activity(project_id, created_at DESC)")
    logger.info("PM tables ensured")


# ── Startup: seed admin user if none ────────────
def _seed_admin():
    """Create default admin if no users exist. Also ensures schema is up-to-date."""
    email = os.getenv("HITL_ADMIN_EMAIL", "admin@langgraph.local")
    password = os.getenv("HITL_ADMIN_PASSWORD", "admin")
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            # Ensure culture column exists
            cur.execute("""
                ALTER TABLE project.hitl_users
                ADD COLUMN IF NOT EXISTS culture TEXT DEFAULT 'fr'
            """)
            # Ensure chat messages table exists
            cur.execute("""
                CREATE TABLE IF NOT EXISTS project.hitl_chat_messages (
                    id SERIAL PRIMARY KEY,
                    team_id TEXT NOT NULL,
                    agent_id TEXT NOT NULL,
                    thread_id TEXT NOT NULL,
                    sender TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at TIMESTAMPTZ DEFAULT NOW()
                )
            """)
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_hitl_chat_thread
                ON project.hitl_chat_messages (team_id, agent_id, thread_id, created_at)
            """)
            # PG NOTIFY trigger for real-time chat updates
            cur.execute("""
                CREATE OR REPLACE FUNCTION notify_hitl_chat() RETURNS trigger AS $$
                BEGIN
                    PERFORM pg_notify('hitl_chat', json_build_object(
                        'id', NEW.id,
                        'team_id', NEW.team_id,
                        'agent_id', NEW.agent_id,
                        'thread_id', NEW.thread_id,
                        'sender', NEW.sender,
                        'content', LEFT(NEW.content, 4000),
                        'created_at', NEW.created_at
                    )::text);
                    RETURN NEW;
                END;
                $$ LANGUAGE plpgsql
            """)
            cur.execute("""
                DROP TRIGGER IF EXISTS hitl_chat_notify ON project.hitl_chat_messages
            """)
            cur.execute("""
                CREATE TRIGGER hitl_chat_notify
                AFTER INSERT ON project.hitl_chat_messages
                FOR EACH ROW EXECUTE FUNCTION notify_hitl_chat()
            """)
            # Ensure PM tables exist
            _ensure_pm_tables(cur)
            cur.execute("SELECT COUNT(*) FROM project.hitl_users")
            if cur.fetchone()[0] == 0:
                hashed = pwd_ctx.hash(_truncate_pw(password))
                cur.execute("""
                    INSERT INTO project.hitl_users (email, password_hash, display_name, role)
                    VALUES (%s, %s, %s, 'admin')
                    RETURNING id
                """, (email, hashed, "Admin"))
                uid = cur.fetchone()[0]
                # Give admin access to all teams from teams.json
                teams = _load_teams()
                for t in teams:
                    cur.execute("""
                        INSERT INTO project.hitl_team_members (user_id, team_id, role)
                        VALUES (%s, %s, 'admin')
                        ON CONFLICT DO NOTHING
                    """, (uid, t["id"]))
                logger.info(f"Seeded admin user: {email}")
    finally:
        conn.close()


def _load_teams() -> list[dict]:
    """Load teams from teams.json."""
    for path in ["/app/config/Teams/teams.json", "config/Teams/teams.json"]:
        if os.path.exists(path):
            with open(path) as f:
                data = json.load(f)
            return data.get("teams", [])
    return []


import asyncio
import threading

_pg_listener_stop = threading.Event()


def _pg_listen_loop():
    """Background thread: LISTEN on 'hitl_chat' channel and dispatch to WebSocket clients."""
    while not _pg_listener_stop.is_set():
        try:
            conn = psycopg.connect(DATABASE_URI, autocommit=True)
            conn.execute("LISTEN hitl_chat")
            logger.info("[pg-listen] Listening on 'hitl_chat' channel")
            while not _pg_listener_stop.is_set():
                # poll with timeout so we can check the stop flag
                for notify in conn.notifies(timeout=2):
                    try:
                        payload = json.loads(notify.payload)
                        team_id = payload.get("team_id", "")
                        agent_id = payload.get("agent_id", "")
                        thread_id = payload.get("thread_id", "")
                        # Dispatch to WebSocket subscribers
                        _dispatch_chat_event(team_id, agent_id, payload)
                    except Exception as e:
                        logger.warning(f"[pg-listen] Bad payload: {e}")
            conn.close()
        except Exception as e:
            logger.warning(f"[pg-listen] Connection error: {e}")
            if not _pg_listener_stop.is_set():
                time.sleep(3)  # reconnect after delay


# Chat WS subscriptions: {team_id: {websocket: agent_id_or_None}}
_ws_chat_subs: dict[str, dict] = {}
_event_loop = None


def _dispatch_chat_event(team_id: str, agent_id: str, payload: dict):
    """Called from PG listener thread — schedule async dispatch on the event loop."""
    loop = _event_loop
    if loop and loop.is_running():
        asyncio.run_coroutine_threadsafe(_async_dispatch_chat(team_id, agent_id, payload), loop)


async def _async_dispatch_chat(team_id: str, agent_id: str, payload: dict):
    """Send chat_message event to all WS clients watching this agent in this team."""
    event = {"type": "chat_message", "data": payload}
    subs = _ws_chat_subs.get(team_id, {})
    for ws, sub_agent_id in list(subs.items()):
        if sub_agent_id == agent_id:
            try:
                await ws.send_json(event)
            except Exception:
                pass
    # Also notify ALL team connections (for inbox badge refresh etc.)
    for ws in list(_ws_connections.get(team_id, [])):
        try:
            await ws.send_json({"type": "chat_activity", "agent_id": agent_id})
        except Exception:
            pass


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _event_loop
    _event_loop = asyncio.get_running_loop()

    # Retry DB connection (postgres may still be in recovery)
    for attempt in range(1, 11):
        try:
            _seed_admin()
            break
        except psycopg.OperationalError as e:
            logger.warning(f"DB not ready (attempt {attempt}/10): {e}")
            if attempt == 10:
                raise
            time.sleep(3)

    # Start PG LISTEN background thread
    _pg_listener_stop.clear()
    listener_thread = threading.Thread(target=_pg_listen_loop, daemon=True, name="pg-listen")
    listener_thread.start()
    logger.info("HITL Console started (with PG LISTEN)")

    yield

    # Shutdown
    _pg_listener_stop.set()
    _event_loop = None


app = FastAPI(title="HITL Console", lifespan=lifespan)
app.mount("/static", StaticFiles(directory="static"), name="static")


# ── Auth helpers ────────────────────────────────
class LoginRequest(BaseModel):
    email: str
    password: str


class RegisterRequest(BaseModel):
    email: str
    culture: str = "fr"


class TokenData(BaseModel):
    user_id: str
    email: str
    role: str
    teams: list[str]


def create_token(user_id: str, email: str, role: str, teams: list[str]) -> str:
    payload = {
        "sub": user_id,
        "email": email,
        "role": role,
        "teams": teams,
        "exp": datetime.now(timezone.utc) + timedelta(hours=JWT_EXPIRE_HOURS),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_token(token: str) -> TokenData:
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return TokenData(
            user_id=payload["sub"],
            email=payload["email"],
            role=payload["role"],
            teams=payload.get("teams", []),
        )
    except JWTError:
        raise HTTPException(401, "Token invalide")


def get_current_user(request: Request) -> TokenData:
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(401, "Token manquant")
    return decode_token(auth[7:])


# ── Auth routes ─────────────────────────────────
@app.post("/api/auth/login")
def login(req: LoginRequest):
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, email, password_hash, display_name, role, is_active,
                       COALESCE(auth_type, 'local') as auth_type
                FROM project.hitl_users WHERE email = %s
            """, (req.email,))
            row = cur.fetchone()
            if not row:
                raise HTTPException(401, "Email ou mot de passe incorrect")
            # Google users cannot login with password
            if row[6] == 'google':
                raise HTTPException(400, "Ce compte utilise Google. Connectez-vous avec Google.")
            truncated_input = _truncate_pw(req.password)
            verify_ok = row[2] and pwd_ctx.verify(truncated_input, row[2])
            logger.info("LOGIN email=%s verify=%s hash_prefix=%s",
                        req.email, verify_ok, (row[2] or "")[:20])
            if not verify_ok:
                raise HTTPException(401, "Email ou mot de passe incorrect")
            if not row[5]:
                raise HTTPException(403, "Compte desactive")
            if row[4] == 'undefined':
                raise HTTPException(403, "Votre compte est en attente de validation par un administrateur")
            user_id = str(row[0])
            # Get teams
            cur.execute("""
                SELECT team_id, role FROM project.hitl_team_members WHERE user_id = %s
            """, (row[0],))
            teams = [r[0] for r in cur.fetchall()]
            # Update last_login
            cur.execute("UPDATE project.hitl_users SET last_login = NOW() WHERE id = %s", (row[0],))
        token = create_token(user_id, row[1], row[4], teams)
        return {
            "token": token,
            "user": {
                "id": user_id,
                "email": row[1],
                "display_name": row[3],
                "role": row[4],
                "teams": teams,
            },
        }
    finally:
        conn.close()


@app.post("/api/auth/register")
def register(req: RegisterRequest):
    import re, secrets, string
    if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", req.email):
        raise HTTPException(400, "Email invalide")
    # Generate temporary password
    alphabet = string.ascii_letters + string.digits + "!@#$%"
    temp_password = ''.join(secrets.choice(alphabet) for _ in range(12))
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM project.hitl_users WHERE email = %s", (req.email,))
            if cur.fetchone():
                raise HTTPException(409, "Cet email est deja utilise")
            hashed = pwd_ctx.hash(_truncate_pw(temp_password))
            display_name = req.email.split("@")[0]
            culture = req.culture or "fr"
            cur.execute("""
                INSERT INTO project.hitl_users (email, password_hash, display_name, role, auth_type, culture)
                VALUES (%s, %s, %s, 'undefined', 'local', %s)
                RETURNING id
            """, (req.email, hashed, display_name, culture))
            uid = str(cur.fetchone()[0])
        # Send reset email
        _send_reset_email(req.email, temp_password)
        return {"ok": True, "id": uid, "message": "Compte cree. Un email de reinitialisation vous sera envoye."}
    finally:
        conn.close()


class GoogleAuthRequest(BaseModel):
    credential: str  # Google ID token


@app.post("/api/auth/google")
def google_login(req: GoogleAuthRequest):
    """Authenticate via Google ID token."""
    import httpx
    # Re-read config so admin dashboard changes take effect
    cfg = _load_hitl_config()
    g = cfg.get("google_oauth", {})
    g_enabled = g.get("enabled", False)
    g_client_id = g.get("client_id", "")
    g_allowed_domains = g.get("allowed_domains", [])
    if not g_enabled or not g_client_id:
        raise HTTPException(500, "Google OAuth non configure")
    # Verify Google ID token via Google's tokeninfo endpoint
    resp = httpx.get(f"https://oauth2.googleapis.com/tokeninfo?id_token={req.credential}", timeout=10)
    if resp.status_code != 200:
        raise HTTPException(401, "Token Google invalide")
    google_data = resp.json()
    # Verify audience matches our client ID
    if google_data.get("aud") != g_client_id:
        raise HTTPException(401, "Token Google invalide (audience)")
    email = google_data.get("email", "")
    if not email or str(google_data.get("email_verified", "")).lower() != "true":
        raise HTTPException(401, "Email Google non verifie")
    # Check allowed domains
    if g_allowed_domains:
        domain = email.split("@")[1] if "@" in email else ""
        if domain not in g_allowed_domains:
            raise HTTPException(403, f"Le domaine {domain} n'est pas autorise")
    display_name = google_data.get("name", email.split("@")[0])
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            # Check if user exists
            cur.execute("""
                SELECT id, email, display_name, role, is_active,
                       COALESCE(auth_type, 'local') as auth_type
                FROM project.hitl_users WHERE email = %s
            """, (email,))
            row = cur.fetchone()
            if row:
                # Existing user
                if not row[4]:
                    raise HTTPException(403, "Compte desactive")
                user_id = str(row[0])
                role = row[3]
                display_name = row[2]
                cur.execute("UPDATE project.hitl_users SET last_login = NOW() WHERE id = %s", (row[0],))
            else:
                # New user — create with role 'undefined', no password
                cur.execute("""
                    INSERT INTO project.hitl_users (email, password_hash, display_name, role, auth_type)
                    VALUES (%s, NULL, %s, 'undefined', 'google')
                    RETURNING id
                """, (email, display_name))
                user_id = str(cur.fetchone()[0])
                role = "undefined"
            if role == 'undefined':
                raise HTTPException(403, "Votre compte est en attente de validation par un administrateur")
            # Get teams
            cur.execute("SELECT team_id, role FROM project.hitl_team_members WHERE user_id = %s", (user_id,))
            teams = [r[0] for r in cur.fetchall()]
        token = create_token(user_id, email, role, teams)
        return {
            "token": token,
            "user": {
                "id": user_id,
                "email": email,
                "display_name": display_name,
                "role": role,
                "teams": teams,
            },
        }
    finally:
        conn.close()


@app.get("/api/auth/google/client-id")
def google_client_id():
    """Return Google Client ID for frontend (public, no auth needed).
    Re-reads hitl.json each time so changes from the admin dashboard take effect."""
    cfg = _load_hitl_config()
    g = cfg.get("google_oauth", {})
    if not g.get("enabled", False):
        return {"client_id": ""}
    return {"client_id": g.get("client_id", "")}


@app.get("/api/auth/me")
def get_me(user: TokenData = Depends(get_current_user)):
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, email, display_name, role
                FROM project.hitl_users WHERE id = %s
            """, (user.user_id,))
            row = cur.fetchone()
            if not row:
                raise HTTPException(404)
            cur.execute("SELECT team_id, role FROM project.hitl_team_members WHERE user_id = %s", (row[0],))
            teams = [{"team_id": r[0], "role": r[1]} for r in cur.fetchall()]
        return {"id": str(row[0]), "email": row[1], "display_name": row[2], "role": row[3], "teams": teams}
    finally:
        conn.close()


# ── Teams ───────────────────────────────────────
@app.get("/api/teams")
def list_teams(user: TokenData = Depends(get_current_user)):
    """Return teams the user has access to, enriched with names from teams.json."""
    all_teams = {t["id"]: t for t in _load_teams()}
    result = []
    for tid in user.teams:
        info = all_teams.get(tid, {})
        result.append({
            "id": tid,
            "name": info.get("name", tid),
            "directory": info.get("directory", tid),
        })
    return result


# ── Questions (HITL requests) ───────────────────
@app.get("/api/teams/{team_id}/questions")
def list_questions(
    team_id: str,
    status: Optional[str] = None,
    limit: int = 50,
    user: TokenData = Depends(get_current_user),
):
    if team_id not in user.teams and user.role != "admin":
        raise HTTPException(403, "Acces interdit a cette equipe")
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            clauses = ["team_id = %s"]
            params: list = [team_id]
            if status and status != "all":
                clauses.append("status = %s")
                params.append(status)
            where = "WHERE " + " AND ".join(clauses)
            cur.execute(f"""
                SELECT id, thread_id, agent_id, team_id, request_type, prompt,
                       context, channel, status, response, reviewer,
                       response_channel, created_at, answered_at, expires_at,
                       reminded_at, COALESCE(remind_count, 0)
                FROM project.hitl_requests
                {where}
                ORDER BY created_at DESC
                LIMIT %s
            """, (*params, limit))
            rows = cur.fetchall()
            return [_question_row(r) for r in rows]
    finally:
        conn.close()


@app.get("/api/teams/{team_id}/questions/stats")
def question_stats(team_id: str, user: TokenData = Depends(get_current_user)):
    if team_id not in user.teams and user.role != "admin":
        raise HTTPException(403)
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT status, COUNT(*) FROM project.hitl_requests
                WHERE team_id = %s GROUP BY status
            """, (team_id,))
            counts = {r[0]: r[1] for r in cur.fetchall()}
            cur.execute("""
                SELECT COUNT(*) FROM project.hitl_requests
                WHERE team_id = %s AND reminded_at IS NOT NULL AND status = 'pending'
            """, (team_id,))
            relances = cur.fetchone()[0]
        return {
            "pending": counts.get("pending", 0),
            "answered": counts.get("answered", 0),
            "timeout": counts.get("timeout", 0),
            "total": sum(counts.values()),
            "relances": relances,
        }
    finally:
        conn.close()


@app.get("/api/questions/{question_id}")
def get_question(question_id: str, user: TokenData = Depends(get_current_user)):
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, thread_id, agent_id, team_id, request_type, prompt,
                       context, channel, status, response, reviewer,
                       response_channel, created_at, answered_at, expires_at,
                       reminded_at, COALESCE(remind_count, 0)
                FROM project.hitl_requests WHERE id = %s
            """, (question_id,))
            row = cur.fetchone()
            if not row:
                raise HTTPException(404)
            q = _question_row(row)
            if q["team_id"] not in user.teams and user.role != "admin":
                raise HTTPException(403)
            return q
    finally:
        conn.close()


class AnswerRequest(BaseModel):
    response: str
    action: str = "answer"  # answer | approve | reject


@app.post("/api/questions/{question_id}/answer")
def answer_question(question_id: str, req: AnswerRequest, user: TokenData = Depends(get_current_user)):
    status_map = {"answer": "answered", "approve": "answered", "reject": "answered"}
    new_status = status_map.get(req.action, "answered")
    response_text = req.response
    if req.action == "approve":
        response_text = response_text or "approved"
    elif req.action == "reject":
        response_text = response_text or "rejected"

    conn = get_conn()
    try:
        with conn.cursor() as cur:
            # Check access
            cur.execute("SELECT team_id, status FROM project.hitl_requests WHERE id = %s", (question_id,))
            row = cur.fetchone()
            if not row:
                raise HTTPException(404)
            if row[0] not in user.teams and user.role != "admin":
                raise HTTPException(403)
            if row[1] != "pending":
                raise HTTPException(400, "Cette question n'est plus en attente")
            cur.execute("""
                UPDATE project.hitl_requests
                SET status = %s, response = %s, reviewer = %s, response_channel = 'web',
                    answered_at = NOW()
                WHERE id = %s AND status = 'pending'
            """, (new_status, response_text, user.email, question_id))
            if cur.rowcount == 0:
                raise HTTPException(409, "Deja traitee")
        return {"ok": True, "status": new_status}
    finally:
        conn.close()


# ── Agents (from registry) ─────────────────────
@app.get("/api/teams/{team_id}/agents")
def list_agents(team_id: str, user: TokenData = Depends(get_current_user)):
    if team_id not in user.teams and user.role != "admin":
        raise HTTPException(403)
    all_teams = {t["id"]: t for t in _load_teams()}
    team = all_teams.get(team_id)
    if not team:
        raise HTTPException(404, "Equipe inconnue")
    directory = team.get("directory", team_id)
    # Load agents_registry.json
    agents = {}
    for base in ["/app/config/Teams", "config/Teams"]:
        path = os.path.join(base, directory, "agents_registry.json")
        if os.path.exists(path):
            with open(path) as f:
                data = json.load(f)
            agents = data.get("agents", {})
            break
    # Enrich with question stats
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT agent_id,
                       COUNT(*) FILTER (WHERE status = 'pending') as pending,
                       COUNT(*) as total,
                       MAX(created_at) as last_activity
                FROM project.hitl_requests
                WHERE team_id = %s
                GROUP BY agent_id
            """, (team_id,))
            stats = {}
            for r in cur.fetchall():
                stats[r[0]] = {"pending": r[1], "total": r[2], "last_activity": r[3].isoformat() if r[3] else None}
    finally:
        conn.close()
    result = []
    for aid, aconf in agents.items():
        s = stats.get(aid, {})
        result.append({
            "id": aid,
            "name": aconf.get("name", aid),
            "type": aconf.get("type", "single"),
            "pending": s.get("pending", 0),
            "total": s.get("total", 0),
            "last_activity": s.get("last_activity"),
        })
    return result


# ── Members ─────────────────────────────────────
@app.get("/api/teams/{team_id}/members")
def list_members(team_id: str, user: TokenData = Depends(get_current_user)):
    if team_id not in user.teams and user.role != "admin":
        raise HTTPException(403)
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT u.id, u.email, u.display_name, u.role as global_role,
                       tm.role as team_role, u.last_login, u.is_active
                FROM project.hitl_team_members tm
                JOIN project.hitl_users u ON u.id = tm.user_id
                WHERE tm.team_id = %s
                ORDER BY u.display_name
            """, (team_id,))
            return [{
                "id": str(r[0]), "email": r[1], "display_name": r[2],
                "global_role": r[3], "team_role": r[4],
                "last_login": r[5].isoformat() if r[5] else None,
                "is_active": r[6],
            } for r in cur.fetchall()]
    finally:
        conn.close()


class InviteRequest(BaseModel):
    email: str
    display_name: str = ""
    password: str = ""
    role: str = "member"


@app.post("/api/teams/{team_id}/members")
def invite_member(team_id: str, req: InviteRequest, user: TokenData = Depends(get_current_user)):
    if team_id not in user.teams and user.role != "admin":
        raise HTTPException(403)
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            # Check if user exists
            cur.execute("SELECT id FROM project.hitl_users WHERE email = %s", (req.email,))
            row = cur.fetchone()
            if row:
                uid = row[0]
            else:
                pw = req.password or "changeme"
                hashed = pwd_ctx.hash(_truncate_pw(pw))
                cur.execute("""
                    INSERT INTO project.hitl_users (email, password_hash, display_name, role)
                    VALUES (%s, %s, %s, 'member')
                    RETURNING id
                """, (req.email, hashed, req.display_name or req.email.split("@")[0]))
                uid = cur.fetchone()[0]
            # Add to team
            cur.execute("""
                INSERT INTO project.hitl_team_members (user_id, team_id, role)
                VALUES (%s, %s, %s)
                ON CONFLICT (user_id, team_id) DO UPDATE SET role = EXCLUDED.role
            """, (uid, team_id, req.role))
        return {"ok": True, "user_id": str(uid)}
    finally:
        conn.close()


@app.delete("/api/teams/{team_id}/members/{user_id}")
def remove_member(team_id: str, user_id: str, user: TokenData = Depends(get_current_user)):
    if user.role != "admin":
        raise HTTPException(403, "Admin requis")
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                DELETE FROM project.hitl_team_members
                WHERE user_id = %s AND team_id = %s
            """, (user_id, team_id))
        return {"ok": True}
    finally:
        conn.close()


# ── WebSocket (notifications temps reel) ────────
_ws_connections: dict[str, list[WebSocket]] = {}


@app.websocket("/api/teams/{team_id}/ws")
async def ws_team(websocket: WebSocket, team_id: str):
    # Auth via query param
    token = websocket.query_params.get("token", "")
    try:
        user = decode_token(token)
    except HTTPException:
        await websocket.close(code=4001, reason="Unauthorized")
        return
    if team_id not in user.teams and user.role != "admin":
        await websocket.close(code=4003, reason="Forbidden")
        return
    await websocket.accept()
    _ws_connections.setdefault(team_id, []).append(websocket)
    _ws_chat_subs.setdefault(team_id, {})[websocket] = None
    try:
        while True:
            raw = await websocket.receive_text()
            # Handle client commands
            try:
                msg = json.loads(raw)
                if msg.get("type") == "watch_chat":
                    # Subscribe to a specific agent's chat
                    _ws_chat_subs[team_id][websocket] = msg.get("agent_id")
                elif msg.get("type") == "unwatch_chat":
                    _ws_chat_subs[team_id][websocket] = None
            except (json.JSONDecodeError, KeyError):
                pass
    except WebSocketDisconnect:
        _ws_connections[team_id].remove(websocket)
        _ws_chat_subs.get(team_id, {}).pop(websocket, None)


async def notify_team(team_id: str, event: dict):
    for ws in _ws_connections.get(team_id, []):
        try:
            await ws.send_json(event)
        except Exception:
            pass


# ── Helpers ─────────────────────────────────────
def _question_row(r) -> dict:
    ctx = r[6]
    if isinstance(ctx, str):
        ctx = json.loads(ctx or "{}")
    return {
        "id": str(r[0]),
        "thread_id": r[1],
        "agent_id": r[2],
        "team_id": r[3],
        "request_type": r[4],
        "prompt": r[5],
        "context": ctx,
        "channel": r[7],
        "status": r[8],
        "response": r[9],
        "reviewer": r[10],
        "response_channel": r[11],
        "created_at": r[12].isoformat() if r[12] else None,
        "answered_at": r[13].isoformat() if r[13] else None,
        "expires_at": r[14].isoformat() if r[14] else None,
        "reminded_at": r[15].isoformat() if r[15] else None,
        "remind_count": r[16] or 0,
    }


# ── Password reset ────────────────────────────────
class ResetPasswordRequest(BaseModel):
    email: str
    old_password: str
    new_password: str


@app.post("/api/auth/reset-password")
def reset_password(req: ResetPasswordRequest):
    if len(req.new_password) < 6:
        raise HTTPException(400, "Le nouveau mot de passe doit faire au moins 6 caracteres")
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, password_hash, COALESCE(auth_type, 'local') as auth_type
                FROM project.hitl_users WHERE email = %s
            """, (req.email,))
            row = cur.fetchone()
            if not row:
                raise HTTPException(401, "Email ou mot de passe incorrect")
            if row[2] == 'google':
                raise HTTPException(400, "Ce compte utilise Google. Le mot de passe ne peut pas etre modifie.")
            truncated_old = _truncate_pw(req.old_password)
            verify_ok = row[1] and pwd_ctx.verify(truncated_old, row[1])
            logger.info("RESET uid=%s old_verify=%s stored_hash_prefix=%s",
                        row[0], verify_ok, (row[1] or "")[:20])
            if not verify_ok:
                raise HTTPException(401, "Ancien mot de passe incorrect")
            truncated_new = _truncate_pw(req.new_password)
            new_hash = pwd_ctx.hash(truncated_new)
            # Verify immediately that the new hash matches
            verify_new = pwd_ctx.verify(truncated_new, new_hash)
            logger.info("RESET uid=%s new_hash_prefix=%s verify_new=%s",
                        row[0], new_hash[:20], verify_new)
            cur.execute("UPDATE project.hitl_users SET password_hash = %s WHERE id = %s", (new_hash, row[0]))
        return {"ok": True, "message": "Mot de passe mis a jour"}
    finally:
        conn.close()


# ── Agent Chat ─────────────────────────────────
def _get_gateway_url() -> str:
    """Read gateway URL from others.json (hosts.api), env var, or default."""
    others = _read_config("others.json")
    url = (others.get("hosts", {}).get("api") or "").strip()
    if url:
        return url.rstrip("/")
    return os.getenv("LANGGRAPH_API_URL", "http://langgraph-api:8000")


class ChatRequest(BaseModel):
    message: str


@app.get("/api/teams/{team_id}/agents/{agent_id}/chat")
def get_chat_history(team_id: str, agent_id: str, user: TokenData = Depends(get_current_user)):
    """Get chat history for an agent in a team."""
    if team_id not in user.teams and user.role != "admin":
        raise HTTPException(403)
    thread_id = f"hitl-chat-{team_id}-{agent_id}"
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, sender, content, created_at
                FROM project.hitl_chat_messages
                WHERE team_id = %s AND agent_id = %s AND thread_id = %s
                ORDER BY created_at ASC
                LIMIT 200
            """, (team_id, agent_id, thread_id))
            return [{
                "id": r[0], "sender": r[1], "content": r[2],
                "created_at": r[3].isoformat() if r[3] else None,
            } for r in cur.fetchall()]
    finally:
        conn.close()


@app.post("/api/teams/{team_id}/agents/{agent_id}/chat")
def send_chat_message(team_id: str, agent_id: str, req: ChatRequest, user: TokenData = Depends(get_current_user)):
    """Send a message to an agent and get a response via gateway."""
    if team_id not in user.teams and user.role != "admin":
        raise HTTPException(403)
    import httpx

    thread_id = f"hitl-chat-{team_id}-{agent_id}"
    conn = get_conn()
    try:
        # Save user message
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO project.hitl_chat_messages (team_id, agent_id, thread_id, sender, content)
                VALUES (%s, %s, %s, %s, %s)
            """, (team_id, agent_id, thread_id, user.email, req.message))

        # Call gateway /invoke
        # orchestrator = mode orchestre (pas de direct_agent), autres = mode direct
        invoke_payload = {
            "messages": [{"role": "user", "content": req.message}],
            "thread_id": thread_id,
            "project_id": f"hitl-{team_id}",
            "channel_id": "",
        }
        if agent_id != "orchestrator":
            invoke_payload["direct_agent"] = agent_id
        try:
            resp = httpx.post(f"{_get_gateway_url()}/invoke", json=invoke_payload, timeout=120)
            if resp.status_code == 200:
                data = resp.json()
                agent_reply = data.get("output", "")
            else:
                agent_reply = f"Erreur gateway ({resp.status_code}): {resp.text[:200]}"
        except httpx.ConnectError:
            agent_reply = "Le service LangGraph API n'est pas accessible."
        except Exception as e:
            agent_reply = f"Erreur: {str(e)[:200]}"

        # Save agent response
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO project.hitl_chat_messages (team_id, agent_id, thread_id, sender, content)
                VALUES (%s, %s, %s, %s, %s)
            """, (team_id, agent_id, thread_id, agent_id, agent_reply))

        return {"ok": True, "reply": agent_reply}
    finally:
        conn.close()


@app.delete("/api/teams/{team_id}/agents/{agent_id}/chat")
def clear_chat(team_id: str, agent_id: str, user: TokenData = Depends(get_current_user)):
    """Clear chat history for an agent."""
    if team_id not in user.teams and user.role != "admin":
        raise HTTPException(403)
    thread_id = f"hitl-chat-{team_id}-{agent_id}"
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                DELETE FROM project.hitl_chat_messages
                WHERE team_id = %s AND agent_id = %s AND thread_id = %s
            """, (team_id, agent_id, thread_id))
        return {"ok": True}
    finally:
        conn.close()


# ── Production Manager (PM) ─────────────────────

class PMProjectCreate(BaseModel):
    name: str
    description: str = ''
    lead: str
    team_id: str
    color: str = '#6366f1'
    status: str = 'on-track'
    start_date: Optional[str] = None
    target_date: Optional[str] = None
    members: list[str] = []


class PMIssueCreate(BaseModel):
    title: str
    description: str = ''
    project_id: Optional[int] = None
    status: str = 'backlog'
    priority: int = 3
    assignee: Optional[str] = None
    team_id: str = ''
    tags: list[str] = []


class PMIssueUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    priority: Optional[int] = None
    assignee: Optional[str] = None
    tags: Optional[list[str]] = None
    project_id: Optional[int] = None


class PMRelationCreate(BaseModel):
    type: str  # blocks | relates-to | parent | duplicates
    target_issue_id: str
    reason: str = ''


class PMPRCreate(BaseModel):
    id: str
    title: str
    author: str
    issue_id: Optional[str] = None
    status: str = 'draft'
    additions: int = 0
    deletions: int = 0
    files: int = 0


# ── PM helpers ──────────────────────────────────

def _next_issue_id(team_id: str, conn) -> str:
    """Get and increment the next issue sequence number for a team."""
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO project.pm_issue_counters (team_id, next_seq)
            VALUES (%s, 2)
            ON CONFLICT (team_id) DO UPDATE SET next_seq = project.pm_issue_counters.next_seq + 1
            RETURNING next_seq - 1
        """, (team_id,))
        seq = cur.fetchone()[0]
    prefix = team_id.upper().replace(" ", "").replace("-", "")[:6]
    return f"{prefix}-{seq:03d}"


def _compute_blocked_flags(issues: list[dict], conn) -> list[dict]:
    """For a list of issues, compute is_blocked, blocked_by_count, blocking_count.

    An issue is blocked only if at least one of its 'blocked-by' (inverse of 'blocks')
    relations points to an issue whose status is NOT 'done'.
    """
    if not issues:
        return issues
    issue_ids = [i["id"] for i in issues]
    with conn.cursor() as cur:
        # Issues blocked BY others — only count blockers that are NOT done
        cur.execute("""
            SELECT r.target_issue_id, COUNT(*)
            FROM project.pm_issue_relations r
            JOIN project.pm_issues blocker ON blocker.id = r.source_issue_id
            WHERE r.type = 'blocks'
              AND r.target_issue_id = ANY(%s)
              AND blocker.status != 'done'
            GROUP BY r.target_issue_id
        """, (issue_ids,))
        blocked_by = {r[0]: r[1] for r in cur.fetchall()}

        # Issues this issue BLOCKS (this issue is the source of a 'blocks' relation)
        cur.execute("""
            SELECT source_issue_id, COUNT(*)
            FROM project.pm_issue_relations
            WHERE type = 'blocks' AND source_issue_id = ANY(%s)
            GROUP BY source_issue_id
        """, (issue_ids,))
        blocking = {r[0]: r[1] for r in cur.fetchall()}

    for issue in issues:
        iid = issue["id"]
        issue["blocked_by_count"] = blocked_by.get(iid, 0)
        issue["blocking_count"] = blocking.get(iid, 0)
        issue["is_blocked"] = issue["blocked_by_count"] > 0
    return issues


def _log_activity(project_id: int, user_name: str, action: str, issue_id: str, detail: str, conn):
    """Insert an activity record."""
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO project.pm_activity (project_id, user_name, action, issue_id, detail)
            VALUES (%s, %s, %s, %s, %s)
        """, (project_id, user_name, action, issue_id, detail))


def _create_notification(user_email: str, notif_type: str, text: str, issue_id: str, avatar: str, conn):
    """Insert an inbox notification."""
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO project.pm_inbox (user_email, type, text, issue_id, avatar)
            VALUES (%s, %s, %s, %s, %s)
        """, (user_email, notif_type, text, issue_id, avatar))


# ── PM Projects ─────────────────────────────────

@app.get("/api/pm/projects")
def pm_list_projects(user: TokenData = Depends(get_current_user)):
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT p.id, p.name, p.description, p.lead, p.team_id, p.color,
                       p.status, p.start_date, p.target_date, p.created_by,
                       p.created_at, p.updated_at
                FROM project.pm_projects p
                ORDER BY p.created_at DESC
            """)
            projects = []
            for r in cur.fetchall():
                pid = r[0]
                # Count issues by status
                cur.execute("""
                    SELECT status, COUNT(*) FROM project.pm_issues
                    WHERE project_id = %s GROUP BY status
                """, (pid,))
                status_counts = {row[0]: row[1] for row in cur.fetchall()}
                total = sum(status_counts.values())
                done = status_counts.get("done", 0)
                progress = round(done / total * 100) if total > 0 else 0

                # Blocked / blocking counts (only count if blocker is NOT done)
                cur.execute("""
                    SELECT COUNT(DISTINCT r.target_issue_id)
                    FROM project.pm_issue_relations r
                    JOIN project.pm_issues target ON target.id = r.target_issue_id
                    JOIN project.pm_issues blocker ON blocker.id = r.source_issue_id
                    WHERE r.type = 'blocks' AND target.project_id = %s
                      AND blocker.status != 'done'
                """, (pid,))
                blocked = cur.fetchone()[0]
                cur.execute("""
                    SELECT COUNT(DISTINCT r.source_issue_id)
                    FROM project.pm_issue_relations r
                    JOIN project.pm_issues i ON i.id = r.source_issue_id
                    WHERE r.type = 'blocks' AND i.project_id = %s
                """, (pid,))
                blocking = cur.fetchone()[0]

                # Members
                cur.execute("""
                    SELECT user_name, role FROM project.pm_project_members
                    WHERE project_id = %s
                """, (pid,))
                members = [{"user_name": m[0], "role": m[1]} for m in cur.fetchall()]

                projects.append({
                    "id": pid, "name": r[1], "description": r[2], "lead": r[3],
                    "team_id": r[4], "color": r[5], "status": r[6],
                    "start_date": r[7].isoformat() if r[7] else None,
                    "target_date": r[8].isoformat() if r[8] else None,
                    "created_by": r[9],
                    "created_at": r[10].isoformat() if r[10] else None,
                    "updated_at": r[11].isoformat() if r[11] else None,
                    "progress": progress,
                    "completed_issues": done, "total_issues": total,
                    "blocked_count": blocked, "blocking_count": blocking,
                    "members": members,
                })
        return projects
    finally:
        conn.close()


@app.post("/api/pm/projects")
def pm_create_project(req: PMProjectCreate, user: TokenData = Depends(get_current_user)):
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO project.pm_projects
                    (name, description, lead, team_id, color, status, start_date, target_date, created_by)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
            """, (req.name, req.description, req.lead, req.team_id, req.color,
                  req.status, req.start_date, req.target_date, user.email))
            pid = cur.fetchone()[0]
            # Add lead as member with role 'lead'
            cur.execute("""
                INSERT INTO project.pm_project_members (project_id, user_name, role)
                VALUES (%s, %s, 'lead')
                ON CONFLICT DO NOTHING
            """, (pid, req.lead))
            # Add other members
            for m in req.members:
                if m != req.lead:
                    cur.execute("""
                        INSERT INTO project.pm_project_members (project_id, user_name, role)
                        VALUES (%s, %s, 'member')
                        ON CONFLICT DO NOTHING
                    """, (pid, m))
        _log_activity(pid, user.email, "created_project", None, req.name, conn)
        return {"ok": True, "id": pid}
    finally:
        conn.close()


@app.get("/api/pm/projects/{project_id}")
def pm_get_project(project_id: int, user: TokenData = Depends(get_current_user)):
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, name, description, lead, team_id, color, status,
                       start_date, target_date, created_by, created_at, updated_at
                FROM project.pm_projects WHERE id = %s
            """, (project_id,))
            r = cur.fetchone()
            if not r:
                raise HTTPException(404, "Projet non trouve")

            # Issues
            cur.execute("""
                SELECT id, title, description, status, priority, assignee, team_id,
                       tags, created_by, created_at, updated_at
                FROM project.pm_issues WHERE project_id = %s
                ORDER BY created_at
            """, (project_id,))
            issues = []
            for ir in cur.fetchall():
                issues.append({
                    "id": ir[0], "title": ir[1], "description": ir[2],
                    "status": ir[3], "priority": ir[4], "assignee": ir[5],
                    "team_id": ir[6], "tags": ir[7] or [],
                    "created_by": ir[8],
                    "created_at": ir[9].isoformat() if ir[9] else None,
                    "updated_at": ir[10].isoformat() if ir[10] else None,
                    "project_id": project_id,
                })
            issues = _compute_blocked_flags(issues, conn)

            total = len(issues)
            done = sum(1 for i in issues if i["status"] == "done")
            progress = round(done / total * 100) if total > 0 else 0
            blocked = sum(1 for i in issues if i.get("isBlocked"))
            blocking = sum(1 for i in issues if i.get("blockingCount", 0) > 0)

            # Members
            cur.execute("""
                SELECT user_name, role FROM project.pm_project_members
                WHERE project_id = %s
            """, (project_id,))
            members = [{"user_name": m[0], "role": m[1]} for m in cur.fetchall()]

        return {
            "id": r[0], "name": r[1], "description": r[2], "lead": r[3],
            "team_id": r[4], "color": r[5], "status": r[6],
            "start_date": r[7].isoformat() if r[7] else None,
            "target_date": r[8].isoformat() if r[8] else None,
            "created_by": r[9],
            "created_at": r[10].isoformat() if r[10] else None,
            "updated_at": r[11].isoformat() if r[11] else None,
            "progress": progress, "completed": done, "total": total,
            "blocked": blocked, "blocking": blocking,
            "members": members, "issues": issues,
        }
    finally:
        conn.close()


@app.put("/api/pm/projects/{project_id}")
def pm_update_project(project_id: int, req: dict, user: TokenData = Depends(get_current_user)):
    allowed = {"name", "description", "lead", "color", "status", "start_date", "target_date"}
    updates = {k: v for k, v in req.items() if k in allowed}
    if not updates:
        raise HTTPException(400, "Rien a mettre a jour")
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            # Check exists
            cur.execute("SELECT status FROM project.pm_projects WHERE id = %s", (project_id,))
            row = cur.fetchone()
            if not row:
                raise HTTPException(404, "Projet non trouve")
            old_status = row[0]

            set_parts = []
            params = []
            for k, v in updates.items():
                set_parts.append(f"{k} = %s")
                params.append(v)
            set_parts.append("updated_at = NOW()")
            params.append(project_id)
            cur.execute(f"""
                UPDATE project.pm_projects SET {', '.join(set_parts)}
                WHERE id = %s
            """, params)
        if "status" in updates and updates["status"] != old_status:
            _log_activity(project_id, user.email, "status_changed",
                          None, f"{old_status} → {updates['status']}", conn)
        return {"ok": True}
    finally:
        conn.close()


@app.delete("/api/pm/projects/{project_id}")
def pm_delete_project(project_id: int, user: TokenData = Depends(get_current_user)):
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM project.pm_projects WHERE id = %s", (project_id,))
            if cur.rowcount == 0:
                raise HTTPException(404, "Projet non trouve")
        return {"ok": True}
    finally:
        conn.close()


# ── PM Issues ───────────────────────────────────

@app.get("/api/pm/issues")
def pm_list_issues(
    team_id: Optional[str] = None,
    project_id: Optional[int] = None,
    status: Optional[str] = None,
    assignee: Optional[str] = None,
    user: TokenData = Depends(get_current_user),
):
    conn = get_conn()
    try:
        clauses = []
        params: list = []
        if team_id:
            clauses.append("team_id = %s")
            params.append(team_id)
        if project_id is not None:
            clauses.append("project_id = %s")
            params.append(project_id)
        if status:
            clauses.append("status = %s")
            params.append(status)
        if assignee:
            clauses.append("assignee = %s")
            params.append(assignee)
        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        with conn.cursor() as cur:
            cur.execute(f"""
                SELECT id, project_id, title, description, status, priority,
                       assignee, team_id, tags, created_by, created_at, updated_at
                FROM project.pm_issues
                {where}
                ORDER BY created_at DESC
            """, params)
            issues = []
            for r in cur.fetchall():
                issues.append({
                    "id": r[0], "project_id": r[1], "title": r[2],
                    "description": r[3], "status": r[4], "priority": r[5],
                    "assignee": r[6], "team_id": r[7], "tags": r[8] or [],
                    "created_by": r[9],
                    "created_at": r[10].isoformat() if r[10] else None,
                    "updated_at": r[11].isoformat() if r[11] else None,
                })
        issues = _compute_blocked_flags(issues, conn)
        return issues
    finally:
        conn.close()


@app.post("/api/pm/issues")
def pm_create_issue(req: PMIssueCreate, user: TokenData = Depends(get_current_user)):
    if not req.team_id:
        raise HTTPException(400, "team_id requis")
    conn = get_conn()
    try:
        issue_id = _next_issue_id(req.team_id, conn)
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO project.pm_issues
                    (id, project_id, title, description, status, priority, assignee, team_id, tags, created_by)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (issue_id, req.project_id, req.title, req.description, req.status,
                  req.priority, req.assignee, req.team_id, req.tags, user.email))
        if req.project_id:
            _log_activity(req.project_id, user.email, "created_issue", issue_id, req.title, conn)
        return {"ok": True, "id": issue_id}
    finally:
        conn.close()


@app.get("/api/pm/issues/{issue_id}")
def pm_get_issue(issue_id: str, user: TokenData = Depends(get_current_user)):
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, project_id, title, description, status, priority,
                       assignee, team_id, tags, created_by, created_at, updated_at
                FROM project.pm_issues WHERE id = %s
            """, (issue_id,))
            r = cur.fetchone()
            if not r:
                raise HTTPException(404, "Issue non trouvee")
            issue = {
                "id": r[0], "project_id": r[1], "title": r[2],
                "description": r[3], "status": r[4], "priority": r[5],
                "assignee": r[6], "team_id": r[7], "tags": r[8] or [],
                "created_by": r[9],
                "created_at": r[10].isoformat() if r[10] else None,
                "updated_at": r[11].isoformat() if r[11] else None,
            }
            # Relations where this issue is source
            cur.execute("""
                SELECT r.id, r.type, r.target_issue_id, r.reason, r.created_at,
                       i.title, i.status
                FROM project.pm_issue_relations r
                JOIN project.pm_issues i ON i.id = r.target_issue_id
                WHERE r.source_issue_id = %s
            """, (issue_id,))
            outgoing = [{"id": rel[0], "type": rel[1], "display_type": rel[1],
                         "related_issue_id": rel[2], "reason": rel[3],
                         "created_at": rel[4].isoformat() if rel[4] else None,
                         "related_title": rel[5], "related_status": rel[6]}
                        for rel in cur.fetchall()]
            # Relations where this issue is target — compute inverse type
            _inverse = {"blocks": "blocked-by", "parent": "sub-task",
                        "relates-to": "relates-to", "duplicates": "duplicates"}
            cur.execute("""
                SELECT r.id, r.type, r.source_issue_id, r.reason, r.created_at,
                       i.title, i.status
                FROM project.pm_issue_relations r
                JOIN project.pm_issues i ON i.id = r.source_issue_id
                WHERE r.target_issue_id = %s
            """, (issue_id,))
            incoming = [{"id": rel[0],
                         "type": _inverse.get(rel[1], rel[1]),
                         "display_type": _inverse.get(rel[1], rel[1]),
                         "related_issue_id": rel[2], "reason": rel[3],
                         "created_at": rel[4].isoformat() if rel[4] else None,
                         "related_title": rel[5], "related_status": rel[6]}
                        for rel in cur.fetchall()]
            issue["relations"] = outgoing + incoming
        _compute_blocked_flags([issue], conn)
        return issue
    finally:
        conn.close()


@app.put("/api/pm/issues/{issue_id}")
def pm_update_issue(issue_id: str, req: PMIssueUpdate, user: TokenData = Depends(get_current_user)):
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT status, project_id FROM project.pm_issues WHERE id = %s", (issue_id,))
            row = cur.fetchone()
            if not row:
                raise HTTPException(404, "Issue non trouvee")
            old_status = row[0]
            project_id = row[1]

            updates = {}
            if req.title is not None:
                updates["title"] = req.title
            if req.description is not None:
                updates["description"] = req.description
            if req.status is not None:
                updates["status"] = req.status
            if req.priority is not None:
                updates["priority"] = req.priority
            if req.assignee is not None:
                updates["assignee"] = req.assignee
            if req.tags is not None:
                updates["tags"] = req.tags
            if req.project_id is not None:
                updates["project_id"] = req.project_id
                project_id = req.project_id

            if not updates:
                raise HTTPException(400, "Rien a mettre a jour")

            set_parts = []
            params = []
            for k, v in updates.items():
                set_parts.append(f"{k} = %s")
                params.append(v)
            set_parts.append("updated_at = NOW()")
            params.append(issue_id)
            cur.execute(f"""
                UPDATE project.pm_issues SET {', '.join(set_parts)}
                WHERE id = %s
            """, params)

            # Re-fetch updated issue
            cur.execute("""
                SELECT id, project_id, title, description, status, priority,
                       assignee, team_id, tags, created_by, created_at, updated_at
                FROM project.pm_issues WHERE id = %s
            """, (issue_id,))
            r = cur.fetchone()
            issue = {
                "id": r[0], "project_id": r[1], "title": r[2],
                "description": r[3], "status": r[4], "priority": r[5],
                "assignee": r[6], "team_id": r[7], "tags": r[8] or [],
                "created_by": r[9],
                "created_at": r[10].isoformat() if r[10] else None,
                "updated_at": r[11].isoformat() if r[11] else None,
            }

        if req.status is not None and req.status != old_status and project_id:
            _log_activity(project_id, user.email, "status_changed",
                          issue_id, f"{old_status} → {req.status}", conn)

        _compute_blocked_flags([issue], conn)
        return issue
    finally:
        conn.close()


@app.delete("/api/pm/issues/{issue_id}")
def pm_delete_issue(issue_id: str, user: TokenData = Depends(get_current_user)):
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM project.pm_issues WHERE id = %s", (issue_id,))
            if cur.rowcount == 0:
                raise HTTPException(404, "Issue non trouvee")
        return {"ok": True}
    finally:
        conn.close()


class PMBulkIssuesRequest(BaseModel):
    issues: list[PMIssueCreate]
    project_id: int
    team_id: str


@app.post("/api/pm/issues/bulk")
def pm_bulk_create_issues(req: PMBulkIssuesRequest, user: TokenData = Depends(get_current_user)):
    conn = get_conn()
    try:
        id_mapping = {}  # temp_index -> real_id
        created_ids = []
        for idx, issue in enumerate(req.issues):
            issue_id = _next_issue_id(req.team_id, conn)
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO project.pm_issues
                        (id, project_id, title, description, status, priority, assignee, team_id, tags, created_by)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (issue_id, req.project_id, issue.title, issue.description,
                      issue.status, issue.priority, issue.assignee, req.team_id,
                      issue.tags, user.email))
            id_mapping[str(idx)] = issue_id
            created_ids.append(issue_id)
        _log_activity(req.project_id, user.email, "bulk_created_issues",
                      None, f"{len(created_ids)} issues", conn)
        return {"ok": True, "ids": created_ids, "id_mapping": id_mapping}
    finally:
        conn.close()


# ── PM Relations ────────────────────────────────

@app.get("/api/pm/issues/{issue_id}/relations")
def pm_list_relations(issue_id: str, user: TokenData = Depends(get_current_user)):
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            # Outgoing relations (this issue is source)
            cur.execute("""
                SELECT r.id, r.type, r.target_issue_id, r.reason, r.created_at,
                       i.title, i.status
                FROM project.pm_issue_relations r
                JOIN project.pm_issues i ON i.id = r.target_issue_id
                WHERE r.source_issue_id = %s
            """, (issue_id,))
            outgoing = [{"id": rel[0], "type": rel[1], "target_issue_id": rel[2],
                         "reason": rel[3],
                         "created_at": rel[4].isoformat() if rel[4] else None,
                         "target_title": rel[5], "target_status": rel[6],
                         "direction": "outgoing"}
                        for rel in cur.fetchall()]

            # Incoming relations (this issue is target)
            cur.execute("""
                SELECT r.id, r.type, r.source_issue_id, r.reason, r.created_at,
                       i.title, i.status
                FROM project.pm_issue_relations r
                JOIN project.pm_issues i ON i.id = r.source_issue_id
                WHERE r.target_issue_id = %s
            """, (issue_id,))
            _inv = {"blocks": "blocked-by", "parent": "sub-task",
                    "relates-to": "relates-to", "duplicates": "duplicates"}
            incoming = [{"id": rel[0],
                         "type": _inv.get(rel[1], rel[1]),
                         "source_issue_id": rel[2], "reason": rel[3],
                         "created_at": rel[4].isoformat() if rel[4] else None,
                         "source_title": rel[5], "source_status": rel[6],
                         "direction": "incoming"}
                        for rel in cur.fetchall()]
        return outgoing + incoming
    finally:
        conn.close()


@app.post("/api/pm/issues/{issue_id}/relations")
def pm_create_relation(issue_id: str, req: PMRelationCreate, user: TokenData = Depends(get_current_user)):
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO project.pm_issue_relations (type, source_issue_id, target_issue_id, reason, created_by)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING id
            """, (req.type, issue_id, req.target_issue_id, req.reason, user.email))
            rel_id = cur.fetchone()[0]
            # Log activity if issue has a project
            cur.execute("SELECT project_id FROM project.pm_issues WHERE id = %s", (issue_id,))
            row = cur.fetchone()
            if row and row[0]:
                _log_activity(row[0], user.email, "added_relation",
                              issue_id, f"{req.type} → {req.target_issue_id}", conn)
        return {"ok": True, "id": rel_id}
    finally:
        conn.close()


@app.delete("/api/pm/relations/{relation_id}")
def pm_delete_relation(relation_id: int, user: TokenData = Depends(get_current_user)):
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM project.pm_issue_relations WHERE id = %s", (relation_id,))
            if cur.rowcount == 0:
                raise HTTPException(404, "Relation non trouvee")
        return {"ok": True}
    finally:
        conn.close()


class PMBulkRelation(BaseModel):
    source_id: str
    target_id: str
    type: str
    reason: str = ''


class PMBulkRelationsRequest(BaseModel):
    relations: list[PMBulkRelation]
    id_mapping: dict[str, str] = {}


@app.post("/api/pm/relations/bulk")
def pm_bulk_create_relations(req: PMBulkRelationsRequest, user: TokenData = Depends(get_current_user)):
    conn = get_conn()
    try:
        created = 0
        with conn.cursor() as cur:
            for rel in req.relations:
                # Map temp IDs to real IDs if mapping provided
                source = req.id_mapping.get(rel.source_id, rel.source_id)
                target = req.id_mapping.get(rel.target_id, rel.target_id)
                try:
                    cur.execute("""
                        INSERT INTO project.pm_issue_relations (type, source_issue_id, target_issue_id, reason, created_by)
                        VALUES (%s, %s, %s, %s, %s)
                        ON CONFLICT DO NOTHING
                    """, (rel.type, source, target, rel.reason, user.email))
                    created += cur.rowcount
                except Exception as e:
                    logger.warning("Bulk relation failed: %s", e)
        return {"ok": True, "created": created}
    finally:
        conn.close()


# ── PM Pull Requests ────────────────────────────

@app.get("/api/pm/reviews")
def pm_list_reviews(status: Optional[str] = None, user: TokenData = Depends(get_current_user)):
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            if status:
                cur.execute("""
                    SELECT id, title, author, issue_id, status, additions, deletions,
                           files, created_at, updated_at
                    FROM project.pm_pull_requests WHERE status = %s
                    ORDER BY created_at DESC
                """, (status,))
            else:
                cur.execute("""
                    SELECT id, title, author, issue_id, status, additions, deletions,
                           files, created_at, updated_at
                    FROM project.pm_pull_requests
                    ORDER BY created_at DESC
                """)
            return [{"id": r[0], "title": r[1], "author": r[2], "issue_id": r[3],
                     "status": r[4], "additions": r[5], "deletions": r[6],
                     "files": r[7],
                     "created_at": r[8].isoformat() if r[8] else None,
                     "updated_at": r[9].isoformat() if r[9] else None}
                    for r in cur.fetchall()]
    finally:
        conn.close()


@app.post("/api/pm/reviews")
def pm_create_review(req: PMPRCreate, user: TokenData = Depends(get_current_user)):
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO project.pm_pull_requests (id, title, author, issue_id, status, additions, deletions, files)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (id) DO UPDATE SET title = EXCLUDED.title, status = EXCLUDED.status, updated_at = NOW()
            """, (req.id, req.title, req.author, req.issue_id, req.status,
                  req.additions, req.deletions, req.files))
        return {"ok": True, "id": req.id}
    finally:
        conn.close()


@app.put("/api/pm/reviews/{pr_id}")
def pm_update_review(pr_id: str, req: dict, user: TokenData = Depends(get_current_user)):
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            new_status = req.get("status")
            if not new_status:
                raise HTTPException(400, "status requis")
            cur.execute("""
                UPDATE project.pm_pull_requests SET status = %s, updated_at = NOW()
                WHERE id = %s
            """, (new_status, pr_id))
            if cur.rowcount == 0:
                raise HTTPException(404, "PR non trouvee")
        return {"ok": True}
    finally:
        conn.close()


# ── PM Inbox ────────────────────────────────────

@app.get("/api/pm/inbox")
def pm_inbox(user: TokenData = Depends(get_current_user)):
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, type, text, issue_id, related_issue_id, relation_type,
                       avatar, read, created_at
                FROM project.pm_inbox
                WHERE user_email = %s
                ORDER BY created_at DESC
                LIMIT 100
            """, (user.email,))
            notifs = [{"id": r[0], "type": r[1], "text": r[2], "issue_id": r[3],
                       "related_issue_id": r[4], "relation_type": r[5],
                       "avatar": r[6], "read": r[7],
                       "created_at": r[8].isoformat() if r[8] else None}
                      for r in cur.fetchall()]
            cur.execute("""
                SELECT COUNT(*) FROM project.pm_inbox
                WHERE user_email = %s AND read = FALSE
            """, (user.email,))
            unread = cur.fetchone()[0]
        return {"notifications": notifs, "unread": unread}
    finally:
        conn.close()


@app.put("/api/pm/inbox/{notif_id}/read")
def pm_mark_read(notif_id: int, user: TokenData = Depends(get_current_user)):
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE project.pm_inbox SET read = TRUE
                WHERE id = %s AND user_email = %s
            """, (notif_id, user.email))
        return {"ok": True}
    finally:
        conn.close()


@app.put("/api/pm/inbox/read-all")
def pm_mark_all_read(user: TokenData = Depends(get_current_user)):
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE project.pm_inbox SET read = TRUE
                WHERE user_email = %s AND read = FALSE
            """, (user.email,))
        return {"ok": True, "updated": cur.rowcount}
    finally:
        conn.close()


# ── PM Activity ─────────────────────────────────

@app.get("/api/pm/projects/{project_id}/activity")
def pm_project_activity(project_id: int, user: TokenData = Depends(get_current_user)):
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, user_name, action, issue_id, detail, created_at
                FROM project.pm_activity
                WHERE project_id = %s
                ORDER BY created_at DESC
                LIMIT 50
            """, (project_id,))
            return [{"id": r[0], "user_name": r[1], "action": r[2],
                     "issue_id": r[3], "detail": r[4],
                     "created_at": r[5].isoformat() if r[5] else None}
                    for r in cur.fetchall()]
    finally:
        conn.close()


# ── PM Pulse (metrics) ──────────────────────────

@app.get("/api/pm/pulse")
def pm_pulse(user: TokenData = Depends(get_current_user)):
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            # Status distribution
            cur.execute("""
                SELECT status, COUNT(*) FROM project.pm_issues GROUP BY status
            """)
            status_dist = {r[0]: r[1] for r in cur.fetchall()}

            # Team activity: per-member stats
            cur.execute("""
                SELECT assignee,
                       COUNT(*) FILTER (WHERE status = 'done') as completed,
                       COUNT(*) FILTER (WHERE status = 'in-progress') as in_progress
                FROM project.pm_issues
                WHERE assignee IS NOT NULL
                GROUP BY assignee
            """)
            team_activity = [{"member": r[0], "completed": r[1], "inProgress": r[2]}
                             for r in cur.fetchall()]

            # Dependency health — only count if blocker is NOT done
            cur.execute("""
                SELECT COUNT(DISTINCT r.target_issue_id)
                FROM project.pm_issue_relations r
                JOIN project.pm_issues blocker ON blocker.id = r.source_issue_id
                WHERE r.type = 'blocks' AND blocker.status != 'done'
            """)
            blocked_count = cur.fetchone()[0]
            cur.execute("""
                SELECT COUNT(DISTINCT source_issue_id) FROM project.pm_issue_relations
                WHERE type = 'blocks'
            """)
            blocking_count = cur.fetchone()[0]
            # Chains of depth >= 2 (A blocks B blocks C)
            cur.execute("""
                SELECT COUNT(DISTINCT r1.source_issue_id)
                FROM project.pm_issue_relations r1
                JOIN project.pm_issue_relations r2 ON r1.target_issue_id = r2.source_issue_id
                WHERE r1.type = 'blocks' AND r2.type = 'blocks'
            """)
            chains = cur.fetchone()[0]

            # Bottlenecks: issues that block the most others
            cur.execute("""
                SELECT r.source_issue_id, i.title, i.status, i.assignee,
                       COUNT(*) as impact
                FROM project.pm_issue_relations r
                JOIN project.pm_issues i ON i.id = r.source_issue_id
                WHERE r.type = 'blocks'
                GROUP BY r.source_issue_id, i.title, i.status, i.assignee
                ORDER BY impact DESC
                LIMIT 10
            """)
            bottlenecks = [{"id": r[0], "title": r[1], "status": r[2],
                            "assignee": r[3], "impact": r[4]}
                           for r in cur.fetchall()]

            # Team activity enrichment: name, total, completed, active
            team_members = [{"name": t["member"], "total": t["completed"] + t["inProgress"],
                             "completed": t["completed"], "active": t["inProgress"]}
                            for t in team_activity]

        return {
            "status_distribution": status_dist,
            "team_activity": team_members,
            "dependency_health": {
                "blocked": blocked_count,
                "blocking": blocking_count,
                "chains": chains,
                "bottlenecks": bottlenecks,
            },
            "velocity": {"value": "—", "sub": "calculated at runtime"},
            "burndown": {"value": "—", "sub": "calculated at runtime"},
            "cycle_time": {"value": "—", "sub": "calculated at runtime"},
            "throughput": {"value": "—", "sub": "calculated at runtime"},
        }
    finally:
        conn.close()


# ── PM AI Planning ──────────────────────────────

class PMAIPlanRequest(BaseModel):
    description: str
    project_name: Optional[str] = ''
    project_id: Optional[int] = None
    team_id: str = ''
    existing_issues: Optional[list] = None
    existing_relations: Optional[list] = None


@app.post("/api/pm/ai/plan")
def pm_ai_plan(req: PMAIPlanRequest, user: TokenData = Depends(get_current_user)):
    """Send project description to gateway for AI planning."""
    import httpx

    gateway_url = _get_gateway_url()
    invoke_payload = {
        "messages": [{"role": "user", "content": req.description}],
        "thread_id": f"pm-plan-{req.team_id}-{int(time.time())}",
        "project_id": f"pm-{req.team_id}",
        "channel_id": "",
        "direct_agent": "planner",
    }
    try:
        resp = httpx.post(f"{gateway_url}/invoke", json=invoke_payload, timeout=120)
        if resp.status_code == 200:
            return resp.json()
        else:
            raise HTTPException(resp.status_code, f"Gateway error: {resp.text[:500]}")
    except httpx.ConnectError:
        raise HTTPException(502, "Le service LangGraph API n'est pas accessible")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Erreur: {str(e)[:300]}")


# ── SPA fallback ────────────────────────────────
@app.get("/reset-password")
def reset_password_page():
    return HTMLResponse(open("static/reset-password.html").read())


@app.get("/")
def index():
    return HTMLResponse(open("static/index.html").read())


@app.get("/health")
def health():
    return {"status": "ok", "service": "hitl-console"}


def _read_version() -> str:
    for vp in ["/project/.version", "/app/.version", os.path.join(os.path.dirname(__file__), "..", ".version")]:
        if os.path.isfile(vp):
            return open(vp).read().strip()
    return "dev"


def _git_last_update() -> str:
    import subprocess
    for base in ["/project", "/app", os.path.join(os.path.dirname(__file__), "..")]:
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
def get_version():
    return {"version": _read_version(), "last_update": _git_last_update()}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8090)

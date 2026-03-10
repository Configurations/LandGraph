"""HITL Console — Standalone FastAPI app for Human-In-The-Loop management."""
import json
import logging
import os
import time
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


@asynccontextmanager
async def lifespan(app: FastAPI):
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
    logger.info("HITL Console started")
    yield


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
            if not row[2] or not pwd_ctx.verify(_truncate_pw(req.password), row[2]):
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
    try:
        while True:
            await websocket.receive_text()  # Keep alive
    except WebSocketDisconnect:
        _ws_connections[team_id].remove(websocket)


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
            if not row[1] or not pwd_ctx.verify(_truncate_pw(req.old_password), row[1]):
                raise HTTPException(401, "Ancien mot de passe incorrect")
            new_hash = pwd_ctx.hash(_truncate_pw(req.new_password))
            cur.execute("UPDATE project.hitl_users SET password_hash = %s WHERE id = %s", (new_hash, row[0]))
        return {"ok": True, "message": "Mot de passe mis a jour"}
    finally:
        conn.close()


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


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8090)

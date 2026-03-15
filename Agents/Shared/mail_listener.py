"""Mail Listener — Poll IMAP et injecte les messages dans le gateway.

Equivalent du discord_listener.py mais pour le canal email.
Tourne dans un container separe (mail-bot) ou en thread dans langgraph-api.

Fonctionnement :
  1. Poll IMAP toutes les POLL_INTERVAL secondes
  2. Detecte les nouveaux mails adresses a l'agent
  3. Parse le sujet pour identifier le thread/agent
  4. Appelle POST /invoke sur le gateway
  5. Le gateway repond via EmailChannel (SMTP)
"""
import asyncio
import email as emaillib
import imaplib
import json
import logging
import os
import re
import time
from datetime import datetime, timezone

import aiohttp
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger("mail_listener")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s %(message)s")

for _vp in ["/project/.version", os.path.join(os.path.dirname(__file__), "..", ".version")]:
    if os.path.isfile(_vp):
        logger.info("ag.flow version: %s", open(_vp).read().strip())
        break
else:
    logger.info("ag.flow version: dev")

# ── Config ───────────────────────────────────
def _load_mail_config() -> dict:
    try:
        from agents.shared.team_resolver import find_global_file
        import json as _json
        path = find_global_file("mail.json")
        if path:
            with open(path) as f:
                return _json.load(f)
    except Exception:
        pass
    return {}

_mail_conf = _load_mail_config()
_imap_conf = _mail_conf.get("imap", {})
_listener_conf = _mail_conf.get("listener", {})
_smtp_conf = _mail_conf.get("smtp", {})

IMAP_HOST = _imap_conf.get("host", os.getenv("IMAP_HOST", "imap.gmail.com"))
IMAP_PORT = _imap_conf.get("port", int(os.getenv("IMAP_PORT", "993")))
IMAP_USE_SSL = _imap_conf.get("use_ssl", True)
IMAP_USER = _imap_conf.get("user", "") or os.getenv("IMAP_USER", "")
IMAP_PASSWORD = os.getenv(_imap_conf.get("password_env", "IMAP_PASSWORD"), "")
SMTP_FROM = _smtp_conf.get("from_address", "") or os.getenv("SMTP_FROM", IMAP_USER)

API_URL = os.getenv("LANGGRAPH_API_URL", "http://langgraph-api:8000")
POLL_INTERVAL = _listener_conf.get("poll_interval", int(os.getenv("MAIL_POLL_INTERVAL", "15")))
ALLOWED_SENDERS = _listener_conf.get("allowed_senders", [])
IGNORE_PATTERNS = _listener_conf.get("ignore_patterns", ["noreply@", "no-reply@", "mailer-daemon@"])

# Fallback si allowed_senders est une string env
if not ALLOWED_SENDERS:
    env_senders = os.getenv("MAIL_ALLOWED_SENDERS", "")
    if env_senders:
        ALLOWED_SENDERS = [s.strip() for s in env_senders.split(",")]

# ID du dernier mail traite (pour ne pas re-traiter)
_last_seen_uid = None

# Pattern pour extraire l'agent d'un sujet : [LangGraph] agent_name — ...
# Ou commande directe : !agent lead_dev ...
SUBJECT_AGENT_PATTERN = re.compile(r'!agent\s+(\S+)', re.IGNORECASE)
SUBJECT_ALIAS_PATTERN = re.compile(r'!a\s+(\S+)', re.IGNORECASE)

# Aliases (memes que discord_listener)
AGENT_ALIASES = {
    "analyste": "requirements_analyst", "analyst": "requirements_analyst",
    "designer": "ux_designer", "ux": "ux_designer",
    "architecte": "architect", "archi": "architect",
    "planificateur": "planner", "planning": "planner",
    "lead": "lead_dev", "leaddev": "lead_dev",
    "frontend": "dev_frontend_web", "front": "dev_frontend_web",
    "backend": "dev_backend_api", "back": "dev_backend_api",
    "mobile": "dev_mobile",
    "qa": "qa_engineer", "test": "qa_engineer", "qualite": "qa_engineer",
    "devops": "devops_engineer", "ops": "devops_engineer",
    "docs": "docs_writer", "doc": "docs_writer", "documentaliste": "docs_writer",
    "avocat": "legal_advisor", "legal": "legal_advisor", "juridique": "legal_advisor",
}


def _connect_imap():
    """Connecte a la boite IMAP."""
    if IMAP_USE_SSL:
        imap = imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT)
    else:
        imap = imaplib.IMAP4(IMAP_HOST, IMAP_PORT)
    imap.login(IMAP_USER, IMAP_PASSWORD)
    return imap


def _extract_body(msg) -> str:
    """Extrait le texte brut, sans le quoted text."""
    body = ""
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain":
                payload = part.get_payload(decode=True)
                if payload:
                    body = payload.decode("utf-8", errors="replace")
                break
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            body = payload.decode("utf-8", errors="replace")

    if not body:
        return ""

    # Retirer le quoted text
    clean = []
    for line in body.split("\n"):
        s = line.strip()
        if s.startswith(">"):
            break
        if s.startswith("On ") and s.endswith("wrote:"):
            break
        if s.startswith("Le ") and ("a ecrit" in s or "a écrit" in s):
            break
        if s == "-- ":
            break
        if s.startswith("-----Original Message-----"):
            break
        if s.startswith("________________________________"):
            break
        clean.append(line)

    return "\n".join(clean).strip()


def _parse_command(subject: str, body: str) -> dict:
    """Parse un mail entrant pour determiner l'action.

    Retourne {type, agent_id, content, thread_id}
    """
    subject_lower = subject.lower().strip()
    body_clean = body.strip()
    first_line = body_clean.split("\n")[0].strip() if body_clean else ""

    # Commande !agent dans le sujet
    m = SUBJECT_AGENT_PATTERN.search(subject)
    if m:
        agent_name = m.group(1).lower()
        agent_id = AGENT_ALIASES.get(agent_name, agent_name)
        # Le body est la tache
        content = body_clean or subject.split(agent_name, 1)[-1].strip()
        return {"type": "direct", "agent_id": agent_id, "content": content, "thread_id": ""}

    # Commande !a alias dans le sujet
    m = SUBJECT_ALIAS_PATTERN.search(subject)
    if m:
        alias = m.group(1).lower()
        agent_id = AGENT_ALIASES.get(alias, alias)
        content = body_clean or subject.split(alias, 1)[-1].strip()
        return {"type": "direct", "agent_id": agent_id, "content": content, "thread_id": ""}

    # Commande !agent dans le body (premiere ligne)
    m = SUBJECT_AGENT_PATTERN.search(first_line)
    if m:
        agent_name = m.group(1).lower()
        agent_id = AGENT_ALIASES.get(agent_name, agent_name)
        content = "\n".join(body_clean.split("\n")[1:]).strip() or first_line.split(agent_name, 1)[-1].strip()
        return {"type": "direct", "agent_id": agent_id, "content": content, "thread_id": ""}

    # Commande !reset
    if "!reset" in subject_lower or first_line.lower() == "!reset":
        return {"type": "reset", "agent_id": "", "content": "", "thread_id": ""}

    # Commande !status
    if "!status" in subject_lower or first_line.lower() == "!status":
        return {"type": "status", "agent_id": "", "content": "", "thread_id": ""}

    # Message normal → orchestrateur
    content = body_clean or subject
    return {"type": "orchestrate", "agent_id": "", "content": content, "thread_id": ""}


def _get_thread_id(from_addr: str) -> str:
    """Genere un thread_id stable a partir de l'adresse email."""
    # Nettoyer l'adresse (enlever le nom)
    match = re.search(r'[\w.+-]+@[\w.-]+', from_addr)
    addr = match.group(0) if match else from_addr
    # Utiliser l'adresse comme thread_id (stable entre les mails)
    return f"mail-{addr.replace('@', '-at-').replace('.', '-')}"


def _is_allowed_sender(from_addr: str) -> bool:
    """Verifie si l'expediteur est autorise et pas dans les patterns ignores."""
    from_lower = from_addr.lower()

    # Ignorer les patterns (noreply, mailer-daemon, etc.)
    for pattern in IGNORE_PATTERNS:
        if pattern.lower() in from_lower:
            return False

    # Si pas de whitelist, tout le monde est autorise
    if not ALLOWED_SENDERS:
        return True

    return any(a.lower() in from_lower for a in ALLOWED_SENDERS)


async def _call_gateway(payload: dict) -> dict:
    """Appelle le gateway et retourne la reponse."""
    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(
                f"{API_URL}/invoke", json=payload,
                timeout=aiohttp.ClientTimeout(total=35)
            ) as resp:
                if resp.status == 200:
                    return await resp.json()
                logger.error(f"Gateway error: {resp.status}")
                return {"output": f"Erreur API: {resp.status}"}
        except Exception as e:
            logger.error(f"Gateway call error: {e}")
            return {"output": f"Erreur: {str(e)[:200]}"}


async def _send_reply(to: str, subject: str, body: str, reference_id: str = ""):
    """Envoie une reponse email via le EmailChannel."""
    from agents.shared.channels import get_channel
    ch = get_channel("email")
    await asyncio.to_thread(ch._send_email, to, subject, body, reference_id)


async def _handle_status(from_addr: str, message_id: str):
    """Gere la commande !status."""
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(f"{API_URL}/status", timeout=aiohttp.ClientTimeout(total=10)) as resp:
                data = await resp.json()
                reply = f"Agents: {data.get('total_agents', '?')} | Teams: {data.get('teams', [])}"
        except Exception as e:
            reply = f"Erreur: {e}"
    await _send_reply(from_addr, "Re: [LangGraph] Status", reply, message_id)


async def _handle_reset(from_addr: str, thread_id: str, message_id: str):
    """Gere la commande !reset."""
    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(
                f"{API_URL}/reset", json={"thread_id": thread_id},
                timeout=aiohttp.ClientTimeout(total=10)
            ) as resp:
                if resp.status == 200:
                    reply = "State reinitialise."
                else:
                    reply = f"Erreur reset: {resp.status}"
        except Exception as e:
            reply = f"Erreur: {e}"
    await _send_reply(from_addr, "Re: [LangGraph] Reset", reply, message_id)


async def _handle_message(from_addr: str, command: dict, thread_id: str, message_id: str):
    """Gere un message (direct ou orchestre)."""
    payload = {
        "messages": [{"role": "user", "content": command["content"]}],
        "thread_id": thread_id,
        "channel_id": from_addr,  # Pour le EmailChannel, channel_id = adresse email
    }
    if command["type"] == "direct" and command["agent_id"]:
        payload["direct_agent"] = command["agent_id"]

    result = await _call_gateway(payload)
    output = result.get("output", "Pas de reponse.")

    agent_name = command.get("agent_id", "Orchestrateur")
    await _send_reply(
        from_addr,
        f"Re: [LangGraph] {agent_name}",
        output,
        message_id
    )


async def poll_once():
    """Un cycle de polling IMAP."""
    global _last_seen_uid

    try:
        imap = _connect_imap()
        imap.select("INBOX")

        # Chercher les mails non lus
        _, msg_ids = imap.search(None, "UNSEEN")
        if not msg_ids[0]:
            imap.logout()
            return

        uids = msg_ids[0].split()
        logger.info(f"Mail: {len(uids)} nouveaux messages")

        for uid in uids:
            try:
                _, msg_data = imap.fetch(uid, "(RFC822)")
                raw = msg_data[0][1]
                msg = emaillib.message_from_bytes(raw)

                from_addr = msg.get("From", "")
                subject = msg.get("Subject", "")
                message_id = msg.get("Message-ID", "")

                # Ignorer nos propres mails
                if SMTP_FROM and SMTP_FROM in from_addr:
                    continue

                # Ignorer les mails LangGraph (reponses automatiques)
                if msg.get("X-LangGraph"):
                    continue

                # Verifier l'expediteur
                if not _is_allowed_sender(from_addr):
                    logger.warning(f"Mail: sender not allowed: {from_addr}")
                    continue

                # Ignorer les reponses a nos propres threads (gerees par channels.py)
                references = msg.get("References", "") + " " + msg.get("In-Reply-To", "")
                if "langgraph-" in references:
                    logger.debug(f"Mail: skip reply to our thread: {subject}")
                    continue

                body = _extract_body(msg)
                if not body and not subject:
                    continue

                logger.info(f"Mail from {from_addr}: {subject[:80]}")

                command = _parse_command(subject, body)
                thread_id = _get_thread_id(from_addr)

                if command["type"] == "status":
                    await _handle_status(from_addr, message_id)
                elif command["type"] == "reset":
                    await _handle_reset(from_addr, thread_id, message_id)
                else:
                    await _handle_message(from_addr, command, thread_id, message_id)

            except Exception as e:
                logger.error(f"Mail processing error: {e}")
                continue

        imap.logout()

    except imaplib.IMAP4.error as e:
        logger.error(f"IMAP error (verifier credentials): {e}")
    except Exception as e:
        logger.error(f"Mail poll error: {e}")


async def run_listener():
    """Boucle principale du mail listener."""
    logger.info(f"Mail listener starting: {IMAP_USER}@{IMAP_HOST}:{IMAP_PORT} (poll every {POLL_INTERVAL}s)")

    if not IMAP_USER or not IMAP_PASSWORD:
        logger.error("IMAP_USER ou IMAP_PASSWORD manquant — mail listener desactive")
        return

    # Test de connexion
    try:
        imap = _connect_imap()
        imap.select("INBOX")
        _, msg_ids = imap.search(None, "ALL")
        total = len(msg_ids[0].split()) if msg_ids[0] else 0
        imap.logout()
        logger.info(f"Mail listener connecte — {total} mails dans INBOX")
    except Exception as e:
        logger.error(f"Mail listener: connexion IMAP impossible: {e}")
        return

    while True:
        try:
            await poll_once()
        except Exception as e:
            logger.error(f"Mail listener error: {e}")
        await asyncio.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    if not IMAP_USER:
        logger.error("IMAP_USER manquant")
        exit(1)
    asyncio.run(run_listener())

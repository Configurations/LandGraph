"""Message Channels — Interface abstraite + implementations Discord, Email.

Usage :
    from agents.shared.channels import get_channel
    ch = get_channel("discord")   # ou "email"
    await ch.send("123456", "Hello")
"""
import asyncio
import logging
import os
import time
import uuid
from abc import ABC, abstractmethod
from datetime import datetime, timezone

import aiohttp
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger("channels")

REMINDER_INTERVALS = [120, 240, 480, 960]
DEFAULT_TIMEOUT = 1800


# ══════════════════════════════════════════════
# Interface abstraite
# ══════════════════════════════════════════════

class MessageChannel(ABC):

    @abstractmethod
    async def send(self, channel_id: str, message: str) -> bool:
        ...

    @abstractmethod
    async def ask(self, channel_id: str, agent_name: str, question: str,
                  context: str = "", timeout: int = DEFAULT_TIMEOUT) -> dict:
        ...

    @abstractmethod
    async def approve(self, channel_id: str, agent_name: str, summary: str,
                      details: str = "", timeout: int = DEFAULT_TIMEOUT) -> dict:
        ...

    def send_sync(self, channel_id: str, message: str) -> bool:
        return _run_async(self.send(channel_id, message))

    def ask_sync(self, channel_id: str, agent_name: str, question: str,
                 context: str = "", timeout: int = DEFAULT_TIMEOUT) -> dict:
        return _run_async(self.ask(channel_id, agent_name, question, context, timeout))

    def approve_sync(self, channel_id: str, agent_name: str, summary: str,
                     details: str = "", timeout: int = DEFAULT_TIMEOUT) -> dict:
        return _run_async(self.approve(channel_id, agent_name, summary, details, timeout))


def _run_async(coro):
    try:
        loop = asyncio.new_event_loop()
        result = loop.run_until_complete(coro)
        loop.close()
        return result
    except Exception as e:
        logger.error(f"Sync wrapper error: {e}")
        return None


# ══════════════════════════════════════════════
# Discord
# ══════════════════════════════════════════════

class DiscordChannel(MessageChannel):

    def __init__(self):
        conf = self._load_config()
        bot = conf.get("bot", {})
        formatting = conf.get("formatting", {})
        timeouts = conf.get("timeouts", {})

        self.token = os.getenv(bot.get("token_env", "DISCORD_BOT_TOKEN"), "")
        self.max_msg_len = formatting.get("max_message_length", 1900)
        self.reminder_intervals = timeouts.get("reminder_intervals", REMINDER_INTERVALS)

    def _load_config(self) -> dict:
        try:
            from agents.shared.team_resolver import find_global_file
            import json
            path = find_global_file("discord.json")
            if path:
                with open(path) as f:
                    return json.load(f)
        except Exception:
            pass
        return {}

    def _headers(self):
        return {"Authorization": f"Bot {self.token}", "Content-Type": "application/json"}

    def _url(self, channel_id: str):
        return f"https://discord.com/api/v10/channels/{channel_id}/messages"

    async def send(self, channel_id: str, message: str) -> bool:
        if not self.token or not channel_id:
            return False
        async with aiohttp.ClientSession() as session:
            for chunk in [message[i:i+self.max_msg_len] for i in range(0, len(message), self.max_msg_len)]:
                try:
                    async with session.post(self._url(channel_id), headers=self._headers(),
                                            json={"content": chunk}) as resp:
                        if resp.status not in (200, 201):
                            logger.error(f"Discord send: {resp.status}")
                            return False
                except Exception as e:
                    logger.error(f"Discord send: {e}")
                    return False
        return True

    async def ask(self, channel_id: str, agent_name: str, question: str,
                  context: str = "", timeout: int = DEFAULT_TIMEOUT) -> dict:
        if not self.token or not channel_id:
            return {"answered": False, "response": "", "author": "", "timed_out": True}

        asked_at = datetime.now(timezone.utc).strftime("%H:%M UTC")
        msg = f"❓ **{agent_name} a besoin d'une reponse**\n\n{question}\n"
        if context:
            msg += f"\n*Contexte : {context[:500]}*\n"
        msg += f"\n💬 Repondez directement dans ce channel.\n⏰ Timeout : {timeout // 60} min"

        async with aiohttp.ClientSession() as session:
            try:
                async with session.post(self._url(channel_id), headers=self._headers(),
                                        json={"content": msg}) as resp:
                    if resp.status not in (200, 201):
                        return {"answered": False, "response": "", "author": "", "timed_out": False}
                    anchor_id = (await resp.json())["id"]
            except Exception as e:
                logger.error(f"Discord ask: {e}")
                return {"answered": False, "response": "", "author": "", "timed_out": False}

            return await self._poll_response(session, channel_id, anchor_id, agent_name, asked_at, timeout)

    async def approve(self, channel_id: str, agent_name: str, summary: str,
                      details: str = "", timeout: int = DEFAULT_TIMEOUT) -> dict:
        if not self.token or not channel_id:
            return {"approved": True, "response": "auto-approve", "reviewer": "system", "timed_out": False}

        asked_at = datetime.now(timezone.utc).strftime("%H:%M UTC")
        msg = f"🔒 **Validation requise — {agent_name}**\n\n**Resume :** {summary}\n"
        if details:
            msg += f"\n{details[:1500]}\n"
        msg += (f"\n**Repondez dans ce channel :**\n"
                f"  `approve` — valider\n  `revise <commentaire>` — modifier\n  `reject` — rejeter\n"
                f"\n⏰ Timeout : {timeout // 60} min")

        async with aiohttp.ClientSession() as session:
            try:
                async with session.post(self._url(channel_id), headers=self._headers(),
                                        json={"content": msg}) as resp:
                    if resp.status not in (200, 201):
                        return {"approved": True, "response": "discord error", "reviewer": "system", "timed_out": False}
                    anchor_id = (await resp.json())["id"]
            except Exception as e:
                logger.error(f"Discord approve: {e}")
                return {"approved": True, "response": f"error: {e}", "reviewer": "system", "timed_out": False}

            return await self._poll_approval(session, channel_id, anchor_id, agent_name, asked_at, timeout)

    async def _poll_response(self, session, channel_id, anchor_id, agent_name, asked_at, timeout):
        start = time.time()
        reminder_idx = 0
        next_reminder = start + (self.reminder_intervals[0] if self.reminder_intervals else timeout)

        while time.time() - start < timeout:
            await asyncio.sleep(5)
            now = time.time()

            if now >= next_reminder and reminder_idx < len(self.reminder_intervals):
                try:
                    await session.post(self._url(channel_id), headers=self._headers(), json={
                        "content": f"⏳ **{agent_name}** attend toujours une reponse (posee a {asked_at})"})
                except Exception:
                    pass
                reminder_idx += 1
                next_reminder = (now + self.reminder_intervals[reminder_idx]) if reminder_idx < len(self.reminder_intervals) else start + timeout

            try:
                async with session.get(self._url(channel_id), headers=self._headers(),
                                       params={"after": anchor_id, "limit": 20}) as resp:
                    if resp.status != 200:
                        continue
                    messages = await resp.json()
                for m in messages:
                    if m.get("author", {}).get("bot", False):
                        continue
                    content = m.get("content", "").strip()
                    author = m.get("author", {}).get("username", "unknown")
                    if content.startswith("!") or len(content) < 2:
                        continue
                    await session.post(self._url(channel_id), headers=self._headers(), json={
                        "content": f"📝 **{agent_name}** a recu votre reponse."})
                    return {"answered": True, "response": content, "author": author, "timed_out": False}
            except Exception:
                continue

        await self.send(channel_id, f"⏰ **{agent_name}** — pas de reponse apres {timeout // 60} min.")
        return {"answered": False, "response": "", "author": "", "timed_out": True}

    async def _poll_approval(self, session, channel_id, anchor_id, agent_name, asked_at, timeout):
        start = time.time()
        reminder_idx = 0
        next_reminder = start + (self.reminder_intervals[0] if self.reminder_intervals else timeout)

        while time.time() - start < timeout:
            await asyncio.sleep(5)
            now = time.time()

            if now >= next_reminder and reminder_idx < len(self.reminder_intervals):
                try:
                    await session.post(self._url(channel_id), headers=self._headers(), json={
                        "content": f"⏳ **{agent_name}** attend toujours votre validation (demande a {asked_at})"})
                except Exception:
                    pass
                reminder_idx += 1
                next_reminder = (now + self.reminder_intervals[reminder_idx]) if reminder_idx < len(self.reminder_intervals) else start + timeout

            try:
                async with session.get(self._url(channel_id), headers=self._headers(),
                                       params={"after": anchor_id, "limit": 20}) as resp:
                    if resp.status != 200:
                        continue
                    messages = await resp.json()
                for m in messages:
                    if m.get("author", {}).get("bot", False):
                        continue
                    content = m.get("content", "").strip().lower()
                    author = m.get("author", {}).get("username", "unknown")
                    raw = m.get("content", "")
                    if content.startswith("approve") or content in ("ok", "yes"):
                        await session.post(self._url(channel_id), headers=self._headers(), json={
                            "content": f"✅ **Approuve** par {author}."})
                        return {"approved": True, "response": raw, "reviewer": author, "timed_out": False}
                    if content.startswith("revise"):
                        await session.post(self._url(channel_id), headers=self._headers(), json={
                            "content": f"🔄 **Revision** demandee par {author}."})
                        return {"approved": False, "response": raw[6:].strip(), "reviewer": author, "timed_out": False}
                    if content.startswith("reject"):
                        await session.post(self._url(channel_id), headers=self._headers(), json={
                            "content": f"❌ **Rejete** par {author}."})
                        return {"approved": False, "response": "rejected", "reviewer": author, "timed_out": False}
            except Exception:
                continue

        await self.send(channel_id, f"⏰ **{agent_name}** — pas de validation apres {timeout // 60} min. Escalade.")
        return {"approved": False, "response": "timeout", "reviewer": None, "timed_out": True}


# ══════════════════════════════════════════════
# Email (SMTP + IMAP)
# ══════════════════════════════════════════════

class EmailChannel(MessageChannel):
    """Canal email. Le channel_id est l'adresse email du destinataire."""

    def __init__(self):
        conf = self._load_config()
        smtp = conf.get("smtp", {})
        imap = conf.get("imap", {})
        templates = conf.get("templates", {})
        security = conf.get("security", {})

        # SMTP
        self.smtp_host = smtp.get("host", "smtp.gmail.com")
        self.smtp_port = smtp.get("port", 587)
        self.smtp_use_tls = smtp.get("use_tls", True)
        self.smtp_use_ssl = smtp.get("use_ssl", False)
        self.smtp_user = smtp.get("user", "") or os.getenv("SMTP_USER", "")
        self.smtp_password = os.getenv(smtp.get("password_env", "SMTP_PASSWORD"), "")
        self.from_addr = smtp.get("from_address", "") or self.smtp_user
        self.from_name = smtp.get("from_name", "LangGraph Agent")

        # IMAP
        self.imap_host = imap.get("host", "imap.gmail.com")
        self.imap_port = imap.get("port", 993)
        self.imap_use_ssl = imap.get("use_ssl", True)
        self.imap_user = imap.get("user", "") or self.smtp_user
        self.imap_password = os.getenv(imap.get("password_env", "IMAP_PASSWORD"), self.smtp_password)

        # Templates
        self.tpl_notification = templates.get("notification_subject", "LangGraph — Notification")
        self.tpl_question = templates.get("question_subject", "[LangGraph] {agent_name} — Question")
        self.tpl_approval = templates.get("approval_subject", "[LangGraph] {agent_name} — Validation requise")
        self.tpl_reminder = templates.get("reminder_prefix", "Rappel : ")
        self.tpl_footer = templates.get("footer_text", "LangGraph Multi-Agent Platform")
        self.tpl_approval_instructions = templates.get("approval_instructions",
            "Repondez avec UN des mots suivants en debut de message :\n\n"
            "  approve  → valider et continuer\n  revise   → modifier\n  reject   → rejeter")

        # Security
        self.require_tls = security.get("require_tls", True)
        self.max_body_size = security.get("max_body_size", 50000)

        if self.smtp_user:
            logger.info(f"EmailChannel: {self.smtp_user} via {self.smtp_host}:{self.smtp_port}")

    def _load_config(self) -> dict:
        """Charge mail.json via team_resolver, avec fallback valeurs par defaut."""
        try:
            from agents.shared.team_resolver import find_global_file
            import json
            path = find_global_file("mail.json")
            if path:
                with open(path) as f:
                    conf = json.load(f)
                logger.info(f"EmailChannel config loaded from {path}")
                return conf
        except Exception as e:
            logger.warning(f"EmailChannel: could not load mail.json: {e}")
        return {}

    def _send_email(self, to: str, subject: str, body: str, reference_id: str = "") -> str:
        """Envoie un email. Retourne le Message-ID genere, ou '' si echec."""
        import smtplib
        from email.mime.text import MIMEText
        from email.mime.multipart import MIMEMultipart
        from email.utils import formataddr, formatdate

        if not self.smtp_user:
            logger.warning("Email: SMTP_USER non configure")
            return ""

        message_id = f"<langgraph-{uuid.uuid4().hex[:12]}@{self.from_addr.split('@')[-1]}>"

        msg = MIMEMultipart("alternative")
        msg["From"] = formataddr((self.from_name, self.from_addr))
        msg["To"] = to
        msg["Subject"] = subject
        msg["Date"] = formatdate(localtime=True)
        msg["Message-ID"] = message_id

        # Pour le threading : In-Reply-To et References
        if reference_id:
            msg["In-Reply-To"] = reference_id
            msg["References"] = reference_id

        # Header custom pour identifier les mails LangGraph
        msg["X-LangGraph"] = "true"
        msg["X-LangGraph-Subject"] = subject

        # Version texte
        msg.attach(MIMEText(body, "plain", "utf-8"))

        # Version HTML
        html_lines = []
        for line in body.split("\n"):
            if line.startswith("  "):
                html_lines.append(f"<code>{line}</code><br>")
            elif line.startswith("**") and line.endswith("**"):
                html_lines.append(f"<strong>{line[2:-2]}</strong><br>")
            else:
                html_lines.append(f"{line}<br>")
        html_body = "\n".join(html_lines)
        msg.attach(MIMEText(
            f'<html><body style="font-family: Arial, sans-serif; line-height: 1.6;">'
            f'{html_body}'
            f'<hr style="margin-top:20px;"><small style="color:#888;">{self.tpl_footer}</small>'
            f'</body></html>',
            "html", "utf-8"
        ))

        try:
            if self.smtp_use_ssl:
                # SSL direct (port 465 typiquement)
                with smtplib.SMTP_SSL(self.smtp_host, self.smtp_port) as server:
                    server.login(self.smtp_user, self.smtp_password)
                    server.send_message(msg)
            else:
                # STARTTLS (port 587 typiquement)
                with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
                    if self.smtp_use_tls:
                        server.starttls()
                    server.login(self.smtp_user, self.smtp_password)
                    server.send_message(msg)

            logger.info(f"Email sent to {to}: {subject} [{message_id}]")
            return message_id
        except smtplib.SMTPAuthenticationError as e:
            logger.error(f"Email auth error (verifier App Password): {e}")
            return ""
        except smtplib.SMTPConnectError as e:
            logger.error(f"Email connect error (verifier SMTP_HOST:SMTP_PORT): {e}")
            return ""
        except Exception as e:
            logger.error(f"Email send error: {e}")
            return ""

    def _check_replies(self, reference_id: str = "", subject_filter: str = "",
                        since_time: datetime = None) -> list:
        """Verifie les reponses par IMAP. Filtre par Reference ou Subject."""
        import imaplib
        import email as emaillib

        if not self.imap_user:
            return []

        replies = []
        try:
            if self.imap_use_ssl:
                imap = imaplib.IMAP4_SSL(self.imap_host, self.imap_port)
            else:
                imap = imaplib.IMAP4(self.imap_host, self.imap_port)

            imap.login(self.imap_user, self.imap_password)
            imap.select("INBOX")

            # Construire le critere de recherche
            criteria = []
            if since_time:
                date_str = since_time.strftime("%d-%b-%Y")
                criteria.append(f'SINCE "{date_str}"')
            if subject_filter:
                # Echapper les guillemets dans le sujet
                safe_subject = subject_filter.replace('"', '')
                criteria.append(f'SUBJECT "{safe_subject}"')

            search_str = f'({" ".join(criteria)})' if criteria else "ALL"
            _, msg_ids = imap.search(None, search_str)

            if not msg_ids[0]:
                imap.logout()
                return []

            for mid in msg_ids[0].split():
                try:
                    _, msg_data = imap.fetch(mid, "(RFC822)")
                    raw = msg_data[0][1]
                    msg = emaillib.message_from_bytes(raw)

                    # Filtrer par Reference/In-Reply-To si on a un message_id
                    if reference_id:
                        refs = msg.get("References", "") + " " + msg.get("In-Reply-To", "")
                        if reference_id not in refs:
                            continue

                    # Ignorer nos propres mails
                    from_addr = msg.get("From", "")
                    if self.from_addr in from_addr:
                        continue

                    # Extraire le body texte
                    body = self._extract_body(msg)
                    if not body:
                        continue

                    # Parser la date
                    msg_date = None
                    date_str = msg.get("Date", "")
                    if date_str:
                        try:
                            msg_date = emaillib.utils.parsedate_to_datetime(date_str)
                        except Exception:
                            pass

                    # Filtrer par date
                    if since_time and msg_date and msg_date <= since_time:
                        continue

                    replies.append({
                        "content": body,
                        "author": from_addr,
                        "date": msg_date,
                        "message_id": msg.get("Message-ID", ""),
                    })
                except Exception as e:
                    logger.warning(f"IMAP parse error for mid {mid}: {e}")
                    continue

            imap.logout()

        except imaplib.IMAP4.error as e:
            logger.error(f"IMAP auth/protocol error: {e}")
        except Exception as e:
            logger.warning(f"IMAP check error: {e}")

        # Trier par date (plus recent en premier)
        replies.sort(key=lambda r: r.get("date") or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
        return replies

    def _extract_body(self, msg) -> str:
        """Extrait le texte brut d'un email en retirant le quoted text."""
        import email as emaillib

        body = ""
        if msg.is_multipart():
            for part in msg.walk():
                ct = part.get_content_type()
                if ct == "text/plain":
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

        # Retirer le quoted text (reponse precedente)
        clean_lines = []
        for line in body.split("\n"):
            stripped = line.strip()
            # Detecter le debut du quote
            if stripped.startswith(">"):
                break
            if stripped.startswith("On ") and stripped.endswith("wrote:"):
                break
            if stripped.startswith("Le ") and ("a ecrit" in stripped or "a écrit" in stripped):
                break
            if stripped == f"-- ":  # signature separator
                break
            if stripped.startswith("-----Original Message-----"):
                break
            if stripped.startswith("________________________________"):
                break
            clean_lines.append(line)

        return "\n".join(clean_lines).strip()

    async def send(self, channel_id: str, message: str) -> bool:
        result = await asyncio.to_thread(
            self._send_email, channel_id, self.tpl_notification, message
        )
        return bool(result)

    async def ask(self, channel_id: str, agent_name: str, question: str,
                  context: str = "", timeout: int = DEFAULT_TIMEOUT) -> dict:
        subject = self.tpl_question.format(agent_name=agent_name)
        body = (
            f"{agent_name} a besoin d'une reponse :\n\n"
            f"{question}\n"
        )
        if context:
            body += f"\nContexte : {context[:500]}\n"
        body += (
            f"\n---\n"
            f"Repondez directement a cet email.\n"
            f"Timeout : {timeout // 60} min\n"
        )

        message_id = await asyncio.to_thread(self._send_email, channel_id, subject, body)
        if not message_id:
            return {"answered": False, "response": "", "author": "", "timed_out": False}

        # Rappel email a mi-timeout
        reminder_sent = False

        start_time = datetime.now(timezone.utc)
        start = time.time()
        while time.time() - start < timeout:
            await asyncio.sleep(30)

            # Rappel a mi-timeout
            elapsed = time.time() - start
            if not reminder_sent and elapsed > timeout / 2:
                await asyncio.to_thread(
                    self._send_email, channel_id,
                    f"Re: {subject}",
                    f"Rappel : {agent_name} attend toujours votre reponse.\n\nQuestion initiale : {question[:300]}",
                    message_id
                )
                reminder_sent = True

            replies = await asyncio.to_thread(
                self._check_replies, message_id, subject, start_time
            )
            if replies:
                r = replies[0]
                # Confirmer reception
                await asyncio.to_thread(
                    self._send_email, channel_id,
                    f"Re: {subject}",
                    f"Reponse recue. {agent_name} traite votre message.",
                    message_id
                )
                return {"answered": True, "response": r["content"], "author": r["author"], "timed_out": False}

        # Timeout
        await asyncio.to_thread(
            self._send_email, channel_id,
            f"Re: {subject}",
            f"Timeout : pas de reponse apres {timeout // 60} min. {agent_name} continue avec son meilleur jugement.",
            message_id
        )
        return {"answered": False, "response": "", "author": "", "timed_out": True}

    async def approve(self, channel_id: str, agent_name: str, summary: str,
                      details: str = "", timeout: int = DEFAULT_TIMEOUT) -> dict:
        subject = self.tpl_approval.format(agent_name=agent_name)
        body = (
            f"**Validation requise — {agent_name}**\n\n"
            f"Resume : {summary}\n"
        )
        if details:
            body += f"\n{details[:1500]}\n"
        body += (
            f"\n---\n"
            f"{self.tpl_approval_instructions}\n"
            f"\nTimeout : {timeout // 60} min\n"
        )

        message_id = await asyncio.to_thread(self._send_email, channel_id, subject, body)
        if not message_id:
            return {"approved": True, "response": "email send error", "reviewer": "system", "timed_out": False}

        reminder_sent = False
        start_time = datetime.now(timezone.utc)
        start = time.time()

        while time.time() - start < timeout:
            await asyncio.sleep(30)

            elapsed = time.time() - start
            if not reminder_sent and elapsed > timeout / 2:
                await asyncio.to_thread(
                    self._send_email, channel_id,
                    f"Re: {subject}",
                    f"Rappel : {agent_name} attend toujours votre validation.\n\nResume : {summary[:300]}",
                    message_id
                )
                reminder_sent = True

            replies = await asyncio.to_thread(
                self._check_replies, message_id, subject, start_time
            )
            for r in replies:
                content = r["content"].strip().lower()
                author = r["author"]
                raw = r["content"]

                if content.startswith("approve") or content in ("ok", "yes", "oui"):
                    await asyncio.to_thread(
                        self._send_email, channel_id,
                        f"Re: {subject}", f"Approuve par {author}. Les agents continuent.",
                        message_id)
                    return {"approved": True, "response": raw, "reviewer": author, "timed_out": False}

                if content.startswith("revise"):
                    comment = raw[6:].strip() if len(raw) > 6 else ""
                    await asyncio.to_thread(
                        self._send_email, channel_id,
                        f"Re: {subject}", f"Revision demandee par {author}.",
                        message_id)
                    return {"approved": False, "response": comment, "reviewer": author, "timed_out": False}

                if content.startswith("reject"):
                    await asyncio.to_thread(
                        self._send_email, channel_id,
                        f"Re: {subject}", f"Rejete par {author}.",
                        message_id)
                    return {"approved": False, "response": "rejected", "reviewer": author, "timed_out": False}

        # Timeout
        await asyncio.to_thread(
            self._send_email, channel_id,
            f"Re: {subject}",
            f"Timeout : pas de validation apres {timeout // 60} min. Escalade automatique.",
            message_id
        )
        return {"approved": False, "response": "timeout", "reviewer": None, "timed_out": True}


# ══════════════════════════════════════════════
# Registry + Factory
# ══════════════════════════════════════════════

_channels = {}


def get_channel(channel_type: str = "discord") -> MessageChannel:
    if channel_type not in _channels:
        if channel_type == "discord":
            _channels[channel_type] = DiscordChannel()
        elif channel_type == "email":
            _channels[channel_type] = EmailChannel()
        else:
            logger.warning(f"Canal inconnu: {channel_type}, fallback discord")
            _channels[channel_type] = DiscordChannel()
    return _channels[channel_type]


def get_default_channel_type() -> str:
    """Retourne le type de canal par defaut. Priorite : env > mail.json > discord."""
    env = os.getenv("DEFAULT_CHANNEL", "")
    if env:
        return env
    try:
        from agents.shared.team_resolver import find_global_file
        import json
        path = find_global_file("mail.json")
        if path:
            with open(path) as f:
                conf = json.load(f)
            return conf.get("default_channel", "discord")
    except Exception:
        pass
    return "discord"


def get_default_channel() -> MessageChannel:
    return get_channel(get_default_channel_type())

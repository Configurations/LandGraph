"""Email service — send reset/welcome emails via SMTP."""

from __future__ import annotations

import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any
from urllib.parse import quote

import structlog

from core.config import load_json_config, settings

log = structlog.get_logger(__name__)


def _resolve_smtp_config() -> tuple[dict[str, Any], dict[str, Any]]:
    """Load SMTP config and password reset config from config files."""
    others_cfg = load_json_config("others.json")
    reset_cfg = others_cfg.get("password_reset", {})
    mail_cfg = load_json_config("mail.json")
    return reset_cfg, mail_cfg


def _find_smtp(mail_cfg: dict[str, Any], smtp_name: str) -> dict[str, Any]:
    """Find the SMTP server config by name."""
    smtp_list = mail_cfg.get("smtp", [])
    if isinstance(smtp_list, dict):
        smtp_list = [smtp_list]
    if not smtp_list:
        return {}
    matched = next(
        (s for s in smtp_list if s.get("name") == smtp_name),
        smtp_list[0],
    )
    return matched


def _replace_vars(text: str, variables: dict[str, str]) -> str:
    """Replace template variables in text."""
    for key, value in variables.items():
        text = text.replace(key, value)
    return text


async def send_reset_email(to_email: str, temp_password: str) -> bool:
    """Send a reset/welcome email with a temporary password."""
    reset_cfg, mail_cfg = _resolve_smtp_config()

    smtp_name = reset_cfg.get("smtp_name", "")
    smtp_cfg = _find_smtp(mail_cfg, smtp_name)

    smtp_host = smtp_cfg.get("host", "")
    smtp_port = int(smtp_cfg.get("port", 587))
    smtp_user = smtp_cfg.get("user", "")
    use_ssl = smtp_cfg.get("use_ssl", False)
    use_tls = smtp_cfg.get("use_tls", True)
    from_address = smtp_cfg.get("from_address", "") or smtp_user
    from_name = smtp_cfg.get("from_name", "ag.flow")

    password_env = smtp_cfg.get("password_env", "SMTP_PASSWORD")
    smtp_password = os.getenv(password_env, "")

    if not all([smtp_host, smtp_user, smtp_password]):
        log.warning("smtp_not_configured", email=to_email)
        return False

    # Build template variables
    hitl_url = settings.hitl_public_url.rstrip("/")
    variables = {
        "${mail}": to_email,
        "${pwd}": temp_password,
        "${UrlService}": hitl_url,
    }

    # Resolve template
    tpl_name = reset_cfg.get("template_name", "")
    tpl_list = mail_cfg.get("templates", [])
    if isinstance(tpl_list, dict):
        tpl_list = []
    tpl = next((t for t in tpl_list if t.get("name") == tpl_name), None)

    if tpl:
        subject = _replace_vars(tpl.get("subject", "[ag.flow] Reset password"), variables)
        body_text = _replace_vars(tpl.get("body", ""), variables)
    else:
        subject = "[ag.flow] Bienvenue — Activez votre compte"
        body_text = ""

    if body_text:
        nl = chr(10)
        html = (
            '<html><body style="font-family:sans-serif;color:#333">'
            + body_text.replace(nl, "<br/>")
            + "</body></html>"
        )
    else:
        reset_link = "{}/reset-password?mail={}&pwd={}".format(
            hitl_url, quote(to_email), quote(temp_password),
        )
        html = (
            '<html><body style="font-family:sans-serif;color:#333">'
            "<h2>Bienvenue sur ag.flow</h2>"
            "<p>Un compte a ete cree pour vous "
            "(<code>{email}</code>).</p>"
            "<p>Votre mot de passe temporaire : "
            '<code style="background:#f0f0f0;padding:4px 8px;'
            'border-radius:4px;font-size:1.1em">{pwd}</code></p>'
            "<p>Cliquez ci-dessous pour definir votre mot de passe :</p>"
            '<p><a href="{link}" style="display:inline-block;padding:10px 24px;'
            'background:#3b82f6;color:white;text-decoration:none;'
            'border-radius:6px">Definir mon mot de passe</a></p>'
            "</body></html>"
        ).format(email=to_email, pwd=temp_password, link=reset_link)

    msg = MIMEMultipart("alternative")
    msg["From"] = "{} <{}>".format(from_name, from_address)
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
        log.info("reset_email_sent", email=to_email)
        return True
    except Exception as exc:
        log.error("reset_email_failed", email=to_email, error=str(exc))
        return False

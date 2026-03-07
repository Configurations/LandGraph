"""Human Gate — Validation humaine via Discord REST API avec rappels."""
import asyncio
import json
import logging
import os
import time
from datetime import datetime, timezone

import aiohttp
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger("human_gate")

DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN", "")
DISCORD_CHANNEL_REVIEW = os.getenv("DISCORD_CHANNEL_REVIEW", "")

REMINDER_INTERVALS = [120, 240, 480, 960]  # 2, 4, 8, 16 min
TOTAL_TIMEOUT = 1800  # 30 minutes


async def request_approval(agent_name: str, summary: str, details: str = "",
                            channel_id: str = "", timeout: int = TOTAL_TIMEOUT) -> dict:
    """
    Poste une demande de validation dans Discord et attend la reponse.
    Envoie des rappels periodiques.
    """
    channel = channel_id or DISCORD_CHANNEL_REVIEW
    if not DISCORD_BOT_TOKEN or not channel:
        logger.warning("Human gate: pas de token ou channel — auto-approve")
        return {"approved": True, "response": "auto-approve", "reviewer": "system", "timed_out": False}

    url = f"https://discord.com/api/v10/channels/{channel}/messages"
    headers = {"Authorization": f"Bot {DISCORD_BOT_TOKEN}", "Content-Type": "application/json"}

    asked_at = datetime.now(timezone.utc).strftime("%H:%M UTC")
    message = (
        f"🔒 **Validation requise — {agent_name}**\n\n"
        f"**Resume :** {summary}\n"
    )
    if details:
        message += f"\n{details[:1500]}\n"
    message += (
        f"\n**Repondez dans ce channel :**\n"
        f"  `approve` — valider et continuer\n"
        f"  `revise <commentaire>` — demander des modifications\n"
        f"  `reject` — rejeter\n"
        f"\n⏰ Timeout : {timeout // 60} min"
    )

    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(url, headers=headers, json={"content": message}) as resp:
                if resp.status not in (200, 201):
                    logger.error(f"Human gate: Discord POST failed {resp.status}")
                    return {"approved": True, "response": "discord error — auto-approve", "reviewer": "system", "timed_out": False}
                msg_data = await resp.json()
                request_msg_id = msg_data["id"]
        except Exception as e:
            logger.error(f"Human gate: {e}")
            return {"approved": True, "response": f"error — auto-approve: {e}", "reviewer": "system", "timed_out": False}

        logger.info(f"Human gate: waiting for approval (timeout={timeout}s)")
        start = time.time()
        reminder_idx = 0
        next_reminder = start + (REMINDER_INTERVALS[0] if REMINDER_INTERVALS else timeout)

        while time.time() - start < timeout:
            await asyncio.sleep(5)
            now = time.time()

            # Rappel
            if now >= next_reminder and reminder_idx < len(REMINDER_INTERVALS):
                try:
                    await session.post(url, headers=headers, json={
                        "content": f"⏳ **{agent_name}** attend toujours votre validation (demande a {asked_at})"
                    })
                except Exception:
                    pass
                reminder_idx += 1
                if reminder_idx < len(REMINDER_INTERVALS):
                    next_reminder = now + REMINDER_INTERVALS[reminder_idx]
                else:
                    next_reminder = start + timeout

            # Chercher une reponse
            try:
                params = {"after": request_msg_id, "limit": 20}
                async with session.get(url, headers=headers, params=params) as resp:
                    if resp.status != 200:
                        continue
                    messages = await resp.json()

                for msg in messages:
                    if msg.get("author", {}).get("bot", False):
                        continue

                    content = msg.get("content", "").strip().lower()
                    author = msg.get("author", {}).get("username", "unknown")

                    if content.startswith("approve") or content == "ok" or content == "yes":
                        logger.info(f"Human gate: APPROVED by {author}")
                        await session.post(url, headers=headers, json={
                            "content": f"✅ **Approuve** par {author}. Les agents continuent."
                        })
                        return {"approved": True, "response": msg.get("content", ""), "reviewer": author, "timed_out": False}

                    elif content.startswith("revise"):
                        comment = msg.get("content", "")[6:].strip()
                        logger.info(f"Human gate: REVISION by {author}: {comment}")
                        await session.post(url, headers=headers, json={
                            "content": f"🔄 **Revision** demandee par {author}."
                        })
                        return {"approved": False, "response": comment, "reviewer": author, "timed_out": False}

                    elif content.startswith("reject"):
                        logger.info(f"Human gate: REJECTED by {author}")
                        await session.post(url, headers=headers, json={
                            "content": f"❌ **Rejete** par {author}."
                        })
                        return {"approved": False, "response": "rejected", "reviewer": author, "timed_out": False}

            except Exception as e:
                logger.warning(f"Human gate poll error: {e}")
                continue

        # Timeout
        logger.warning(f"Human gate: timeout after {timeout}s")
        try:
            async with aiohttp.ClientSession() as session2:
                await session2.post(url, headers=headers, json={
                    "content": f"⏰ **{agent_name}** — pas de validation apres {timeout // 60} min. Escalade automatique."
                })
        except Exception:
            pass
        return {"approved": False, "response": "timeout", "reviewer": None, "timed_out": True}


def request_approval_sync(agent_name: str, summary: str, details: str = "",
                           channel_id: str = "", timeout: int = TOTAL_TIMEOUT) -> dict:
    """Version synchrone."""
    try:
        loop = asyncio.new_event_loop()
        result = loop.run_until_complete(
            request_approval(agent_name, summary, details, channel_id, timeout)
        )
        loop.close()
        return result
    except Exception as e:
        logger.error(f"Human gate sync error: {e}")
        return {"approved": True, "response": f"error — auto-approve: {e}", "reviewer": "system", "timed_out": False}

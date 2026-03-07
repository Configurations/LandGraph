"""Human Gate — Validation humaine via Discord REST API (pas de bot, juste HTTP)."""
import asyncio
import json
import logging
import os
import time

import aiohttp
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger("human_gate")

DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN", "")
DISCORD_CHANNEL_REVIEW = os.getenv("DISCORD_CHANNEL_REVIEW", "")


async def request_approval(agent_name: str, summary: str, details: str = "",
                            channel_id: str = "", timeout: int = 300) -> dict:
    """
    Poste une demande de validation dans Discord et attend la reponse.

    Retourne:
        {"approved": bool, "response": str, "reviewer": str, "timed_out": bool}
    """
    channel = channel_id or DISCORD_CHANNEL_REVIEW
    if not DISCORD_BOT_TOKEN or not channel:
        logger.warning("Human gate: pas de token ou channel configure — auto-approve")
        return {"approved": True, "response": "auto-approve (pas de channel review)", "reviewer": "system", "timed_out": False}

    url = f"https://discord.com/api/v10/channels/{channel}/messages"
    headers = {"Authorization": f"Bot {DISCORD_BOT_TOKEN}", "Content-Type": "application/json"}

    # Formater le message
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
        f"\n⏰ Timeout : {timeout // 60} min (auto-escalade si pas de reponse)"
    )

    # Poster la demande
    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(url, headers=headers, json={"content": message}) as resp:
                if resp.status not in (200, 201):
                    logger.error(f"Human gate: Discord POST failed {resp.status}")
                    return {"approved": True, "response": "discord error — auto-approve", "reviewer": "system", "timed_out": False}
                msg_data = await resp.json()
                request_msg_id = msg_data["id"]
                request_timestamp = msg_data["timestamp"]
        except Exception as e:
            logger.error(f"Human gate: {e}")
            return {"approved": True, "response": f"error — auto-approve: {e}", "reviewer": "system", "timed_out": False}

        # Poller les messages pour une reponse
        logger.info(f"Human gate: waiting for approval (timeout={timeout}s)")
        start = time.time()
        poll_interval = 5  # secondes entre chaque poll

        while time.time() - start < timeout:
            await asyncio.sleep(poll_interval)

            try:
                # Lire les messages recents du channel (apres notre message)
                params = {"after": request_msg_id, "limit": 20}
                async with session.get(url, headers=headers, params=params) as resp:
                    if resp.status != 200:
                        continue
                    messages = await resp.json()

                for msg in messages:
                    # Ignorer les bots
                    if msg.get("author", {}).get("bot", False):
                        continue

                    content = msg.get("content", "").strip().lower()
                    author = msg.get("author", {}).get("username", "unknown")

                    if content.startswith("approve") or content == "ok" or content == "yes":
                        logger.info(f"Human gate: APPROVED by {author}")
                        # Poster confirmation
                        await session.post(url, headers=headers, json={
                            "content": f"✅ **Approuve** par {author}. Les agents continuent."
                        })
                        return {"approved": True, "response": msg.get("content", ""), "reviewer": author, "timed_out": False}

                    elif content.startswith("revise"):
                        comment = msg.get("content", "")[6:].strip()
                        logger.info(f"Human gate: REVISION requested by {author}: {comment}")
                        await session.post(url, headers=headers, json={
                            "content": f"🔄 **Revision** demandee par {author}. Commentaire transmis aux agents."
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
        async with aiohttp.ClientSession() as session2:
            await session2.post(url, headers=headers, json={
                "content": f"⏰ **Timeout** — pas de reponse apres {timeout // 60} min. Escalade automatique."
            })

        return {"approved": False, "response": "timeout", "reviewer": None, "timed_out": True}


def request_approval_sync(agent_name: str, summary: str, details: str = "",
                           channel_id: str = "", timeout: int = 300) -> dict:
    """Version synchrone pour appel depuis les agents."""
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

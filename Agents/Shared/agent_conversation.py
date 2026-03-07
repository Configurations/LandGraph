"""Agent Conversation — Les agents posent des questions aux humains via Discord."""
import asyncio
import logging
import os
import time

import aiohttp
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger("agent_conversation")

DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN", "")


async def ask_human(agent_name: str, question: str, channel_id: str,
                     context: str = "", timeout: int = 300) -> dict:
    """
    Pose une question ouverte a l'humain dans Discord et attend la reponse.

    Retourne:
        {"answered": bool, "response": str, "author": str, "timed_out": bool}
    """
    if not DISCORD_BOT_TOKEN or not channel_id:
        logger.warning("ask_human: pas de token ou channel — skip")
        return {"answered": False, "response": "", "author": "", "timed_out": True}

    url = f"https://discord.com/api/v10/channels/{channel_id}/messages"
    headers = {"Authorization": f"Bot {DISCORD_BOT_TOKEN}", "Content-Type": "application/json"}

    # Formater la question
    message = f"❓ **{agent_name} a besoin d'une reponse**\n\n{question}\n"
    if context:
        message += f"\n*Contexte : {context[:500]}*\n"
    message += f"\n💬 Repondez directement dans ce channel.\n⏰ Timeout : {timeout // 60} min"

    async with aiohttp.ClientSession() as session:
        # Poster la question
        try:
            async with session.post(url, headers=headers, json={"content": message}) as resp:
                if resp.status not in (200, 201):
                    logger.error(f"ask_human: Discord POST failed {resp.status}")
                    return {"answered": False, "response": "", "author": "", "timed_out": False}
                msg_data = await resp.json()
                question_msg_id = msg_data["id"]
        except Exception as e:
            logger.error(f"ask_human: {e}")
            return {"answered": False, "response": "", "author": "", "timed_out": False}

        # Poller les reponses
        logger.info(f"ask_human: [{agent_name}] waiting for answer (timeout={timeout}s)")
        start = time.time()

        while time.time() - start < timeout:
            await asyncio.sleep(5)

            try:
                params = {"after": question_msg_id, "limit": 20}
                async with session.get(url, headers=headers, params=params) as resp:
                    if resp.status != 200:
                        continue
                    messages = await resp.json()

                for msg in messages:
                    if msg.get("author", {}).get("bot", False):
                        continue

                    content = msg.get("content", "").strip()
                    author = msg.get("author", {}).get("username", "unknown")

                    # Ignorer les commandes
                    if content.startswith("!"):
                        continue

                    # Ignorer les messages trop courts
                    if len(content) < 2:
                        continue

                    logger.info(f"ask_human: [{agent_name}] got answer from {author}: {content[:100]}")

                    # Confirmer la reception
                    await session.post(url, headers=headers, json={
                        "content": f"📝 **{agent_name}** a recu votre reponse. Traitement en cours..."
                    })

                    return {"answered": True, "response": content, "author": author, "timed_out": False}

            except Exception as e:
                logger.warning(f"ask_human poll error: {e}")
                continue

        logger.warning(f"ask_human: [{agent_name}] timeout")
        return {"answered": False, "response": "", "author": "", "timed_out": True}


def ask_human_sync(agent_name: str, question: str, channel_id: str,
                    context: str = "", timeout: int = 300) -> dict:
    """Version synchrone pour appel depuis les agents."""
    try:
        loop = asyncio.new_event_loop()
        result = loop.run_until_complete(
            ask_human(agent_name, question, channel_id, context, timeout)
        )
        loop.close()
        return result
    except Exception as e:
        logger.error(f"ask_human_sync error: {e}")
        return {"answered": False, "response": "", "author": "", "timed_out": False}

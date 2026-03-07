"""Discord Listener — Commandes !agent, !new, !status + routing normal."""
import os
import logging
import aiohttp
import asyncio
import discord
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger("discord_listener")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s %(message)s")

TOKEN = os.getenv("DISCORD_BOT_TOKEN")
CHANNEL_COMMANDS = os.getenv("DISCORD_CHANNEL_COMMANDS", "")
API_URL = os.getenv("LANGGRAPH_API_URL", "http://langgraph-api:8000")

intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)

active_projects = {}

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


def get_thread_id(message):
    if isinstance(message.channel, discord.Thread):
        return f"discord-thread-{message.channel.id}"
    return f"project-channel-{message.channel.id}"


@client.event
async def on_ready():
    logger.info(f"Bot connecte : {client.user}")


@client.event
async def on_message(message):
    if message.author == client.user:
        return

    if CHANNEL_COMMANDS and str(message.channel.id) != CHANNEL_COMMANDS:
        if not (isinstance(message.channel, discord.Thread) and
                str(message.channel.parent_id) == CHANNEL_COMMANDS):
            return

    if len(message.content) < 3:
        return

    content = message.content.strip()

    # ── !new — nouveau projet ────────────────
    if content.lower().startswith("!new"):
        project_name = content[4:].strip() or "nouveau-projet"
        active_projects[str(message.channel.id)] = project_name
        await message.reply(f"🆕 **{project_name}** — nouveau contexte.")
        return

    # ── !reset — purger le state du channel ──
    if content.lower() == "!reset":
        thread_id = get_thread_id(message)
        try:
            async with aiohttp.ClientSession() as session:
                payload = {"thread_id": thread_id}
                async with session.post(
                    f"{API_URL}/reset", json=payload,
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as resp:
                    if resp.status == 200:
                        await message.reply("🗑️ State reinitialise. Nouveau depart.")
                    else:
                        await message.reply(f"Erreur reset: {resp.status}")
        except Exception as e:
            await message.reply(f"Erreur: {str(e)[:200]}")
        return

    # ── !status ──────────────────────────────
    if content.lower() == "!status":
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{API_URL}/status", timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    data = await resp.json()
                    await message.reply(f"📊 {data.get('total_agents')} agents | API ok")
        except Exception as e:
            await message.reply(f"Erreur: {e}")
        return

    # ── !agent <id> <tache> — routing direct ─
    if content.lower().startswith("!agent ") or content.lower().startswith("!a "):
        parts = content.split(maxsplit=2)
        if len(parts) < 3:
            await message.reply("Usage : `!agent <nom> <tache>`\nExemple : `!agent lead_dev Cree un repo GitHub PerformanceTracker`")
            return

        agent_name = parts[1].lower()
        task = parts[2]

        # Resoudre l'alias
        agent_id = AGENT_ALIASES.get(agent_name, agent_name)

        await message.add_reaction("⚡")

        try:
            async with aiohttp.ClientSession() as session:
                payload = {
                    "messages": [{"role": "user", "content": task}],
                    "thread_id": get_thread_id(message),
                    "channel_id": str(message.channel.id),
                    "direct_agent": agent_id,
                }
                async with session.post(
                    f"{API_URL}/invoke", json=payload,
                    timeout=aiohttp.ClientTimeout(total=30),
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        await message.reply(data.get("output", "Lance."))
                    else:
                        await message.reply(f"Erreur API: {resp.status}")
        except Exception as e:
            await message.reply(f"Erreur: {str(e)[:200]}")
        return

    # ── Message normal — orchestrateur ───────
    logger.info(f"Message de {message.author}: {content[:100]}")
    await message.add_reaction("✅")

    try:
        async with aiohttp.ClientSession() as session:
            payload = {
                "messages": [{"role": "user", "content": content}],
                "thread_id": get_thread_id(message),
                "channel_id": str(message.channel.id),
            }
            async with session.post(
                f"{API_URL}/invoke", json=payload,
                timeout=aiohttp.ClientTimeout(total=30),
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    output = data.get("output", "Pas de reponse.")
                    if len(output) > 1900:
                        for chunk in [output[i:i+1900] for i in range(0, len(output), 1900)]:
                            await message.reply(chunk)
                    else:
                        await message.reply(output)
                else:
                    await message.reply(f"Erreur API: {resp.status}")
    except asyncio.TimeoutError:
        await message.reply("⏳ Traitement en cours...")
    except Exception as e:
        await message.reply(f"Erreur: {str(e)[:200]}")


if __name__ == "__main__":
    if not TOKEN:
        logger.error("DISCORD_BOT_TOKEN manquant")
        exit(1)
    client.run(TOKEN)

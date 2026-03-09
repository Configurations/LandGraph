"""Discord Listener — Commandes !agent, !new, !status + routing normal. Config via discord.json."""
import os
import json
import logging
import aiohttp
import asyncio
import discord
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger("discord_listener")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s %(message)s")


# ── Config depuis discord.json ───────────────
def _load_discord_config() -> dict:
    try:
        from agents.shared.team_resolver import find_global_file
        path = find_global_file("discord.json")
        if path:
            with open(path) as f:
                return json.load(f)
    except Exception:
        pass
    return {}

_conf = _load_discord_config()
_bot_conf = _conf.get("bot", {})
_channels_conf = _conf.get("channels", {})
_formatting = _conf.get("formatting", {})
_timeouts = _conf.get("timeouts", {})

TOKEN = os.getenv(_bot_conf.get("token_env", "DISCORD_BOT_TOKEN"), "")
PREFIX = _bot_conf.get("prefix", "!")
CHANNEL_COMMANDS = _channels_conf.get("commands", "") or os.getenv("DISCORD_CHANNEL_COMMANDS", "")
API_URL = os.getenv("LANGGRAPH_API_URL", "http://langgraph-api:8000")
MAX_MSG_LEN = _formatting.get("max_message_length", 1900)
REACTION_DIRECT = _formatting.get("reaction_processing", "⚡")
REACTION_ORCH = _formatting.get("reaction_orchestrator", "✅")
API_TIMEOUT = _timeouts.get("api_call", 30)

AGENT_ALIASES = _conf.get("aliases", {})
# Fallback si discord.json absent ou vide
if not AGENT_ALIASES:
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

intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)

active_projects = {}


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
    cl = content.lower()

    # ── !new — nouveau projet ────────────────
    if cl.startswith(f"{PREFIX}new"):
        project_name = content[len(PREFIX)+3:].strip() or "nouveau-projet"
        active_projects[str(message.channel.id)] = project_name
        await message.reply(f"🆕 **{project_name}** — nouveau contexte.")
        return

    # ── !reset — purger le state du channel ──
    if cl == f"{PREFIX}reset":
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
    if cl == f"{PREFIX}status":
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{API_URL}/status", timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    data = await resp.json()
                    await message.reply(f"📊 {data.get('total_agents')} agents | API ok")
        except Exception as e:
            await message.reply(f"Erreur: {e}")
        return

    # ── !agent <id> <tache> — routing direct ─
    if cl.startswith(f"{PREFIX}agent ") or cl.startswith(f"{PREFIX}a "):
        parts = content.split(maxsplit=2)
        if len(parts) < 3:
            await message.reply("Usage : `!agent <nom> <tache>`\nExemple : `!agent lead_dev Cree un repo GitHub PerformanceTracker`")
            return

        agent_name = parts[1].lower()
        task = parts[2]

        # Resoudre l'alias
        agent_id = AGENT_ALIASES.get(agent_name, agent_name)

        await message.add_reaction(REACTION_DIRECT)

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
                    timeout=aiohttp.ClientTimeout(total=API_TIMEOUT),
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
    await message.add_reaction(REACTION_ORCH)

    try:
        async with aiohttp.ClientSession() as session:
            payload = {
                "messages": [{"role": "user", "content": content}],
                "thread_id": get_thread_id(message),
                "channel_id": str(message.channel.id),
            }
            async with session.post(
                f"{API_URL}/invoke", json=payload,
                timeout=aiohttp.ClientTimeout(total=API_TIMEOUT),
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    output = data.get("output", "Pas de reponse.")
                    if len(output) > MAX_MSG_LEN:
                        for chunk in [output[i:i+MAX_MSG_LEN] for i in range(0, len(output), MAX_MSG_LEN)]:
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

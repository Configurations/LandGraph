#!/bin/bash
###############################################################################
# Script 13 : Fix thread persistence — un thread_id par projet, pas par message
#
# Probleme : chaque message Discord cree un nouveau thread_id,
#            donc l'Orchestrateur perd le contexte entre les messages.
# Fix : thread_id base sur le channel (un projet = un channel ou un thread Discord)
#
# Usage : ./13-fix-thread-persistence.sh
###############################################################################
set -euo pipefail

PROJECT_DIR="$HOME/langgraph-project"

echo "==========================================="
echo "  Script 13 : Thread persistence"
echo "==========================================="
echo ""

cd "${PROJECT_DIR}"

# ── 1. Nouveau discord_listener avec thread_id persistant ────────────────────
echo "[1/2] Mise a jour discord_listener.py..."

cat > agents/discord_listener.py << 'PYTHON'
"""Discord Listener — Thread persistant par channel/thread Discord."""
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

# ── Thread ID persistant ─────────────────────
# Logique : 
#   - Si le message est dans un thread Discord -> thread_id = thread Discord id
#   - Sinon -> thread_id = "project-{channel_id}" (persistant par channel)
#   - Commande "!new" -> reset le thread_id (nouveau projet)

# Stocke le projet actif par channel
active_projects = {}  # {channel_id: project_name}


def get_thread_id(message) -> str:
    """Determine le thread_id a utiliser."""
    # Si c'est un thread Discord, utiliser l'id du thread
    if isinstance(message.channel, discord.Thread):
        return f"discord-thread-{message.channel.id}"
    
    # Sinon utiliser un thread persistant par channel
    return f"project-channel-{message.channel.id}"


def get_project_id(message) -> str:
    """Determine le project_id."""
    channel_id = str(message.channel.id)
    return active_projects.get(channel_id, "default")


@client.event
async def on_ready():
    logger.info(f"Bot connecte : {client.user}")


@client.event
async def on_message(message):
    if message.author == client.user:
        return

    if CHANNEL_COMMANDS and str(message.channel.id) != CHANNEL_COMMANDS:
        # Accepter aussi les threads dans le channel commandes
        if not (isinstance(message.channel, discord.Thread) and 
                str(message.channel.parent_id) == CHANNEL_COMMANDS):
            return

    if len(message.content) < 3:
        return

    content = message.content.strip()

    # ── Commande !new — nouveau projet ───────
    if content.lower().startswith("!new"):
        project_name = content[4:].strip() or "nouveau-projet"
        channel_id = str(message.channel.id)
        active_projects[channel_id] = project_name
        
        # Creer un thread Discord pour ce projet
        try:
            thread = await message.create_thread(
                name=f"Projet: {project_name[:80]}",
                auto_archive_duration=1440,  # 24h
            )
            await thread.send(
                f"🆕 **Nouveau projet** : {project_name}\n"
                f"Thread ID : `project-channel-{channel_id}`\n"
                f"Envoyez votre brief ici."
            )
            logger.info(f"Nouveau projet: {project_name} -> thread {thread.id}")
        except Exception:
            await message.reply(
                f"🆕 **Nouveau projet** : {project_name}\n"
                f"Les messages suivants dans ce channel continueront ce projet."
            )
        return

    # ── Commande !status — voir l'etat du projet ─
    if content.lower() == "!status":
        thread_id = get_thread_id(message)
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{API_URL}/status", timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    data = await resp.json()
                    await message.reply(
                        f"📊 **Status**\n"
                        f"Thread: `{thread_id}`\n"
                        f"Agents: {data.get('total_agents', 'N/A')}\n"
                        f"API: {data.get('status', 'unknown')}"
                    )
        except Exception as e:
            await message.reply(f"Erreur status: {e}")
        return

    # ── Message normal — envoyer a l'API ─────
    logger.info(f"Message de {message.author}: {content[:100]} | thread={get_thread_id(message)}")

    await message.add_reaction("✅")

    try:
        async with aiohttp.ClientSession() as session:
            payload = {
                "messages": [{"role": "user", "content": content}],
                "thread_id": get_thread_id(message),
                "project_id": get_project_id(message),
                "channel_id": str(message.channel.id),
            }

            async with session.post(
                f"{API_URL}/invoke",
                json=payload,
                timeout=aiohttp.ClientTimeout(total=30),
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    output = data.get("output", "Pas de reponse.")

                    if len(output) > 1900:
                        chunks = [output[i:i + 1900] for i in range(0, len(output), 1900)]
                        for chunk in chunks:
                            await message.reply(chunk)
                    else:
                        await message.reply(output)
                else:
                    error = await resp.text()
                    logger.error(f"API error {resp.status}: {error[:200]}")
                    await message.reply(f"Erreur API: {resp.status}")

    except asyncio.TimeoutError:
        await message.reply("⏳ Traitement en cours. Les resultats arriveront dans ce channel.")
    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
        await message.reply(f"Erreur: {str(e)[:200]}")


if __name__ == "__main__":
    if not TOKEN:
        logger.error("DISCORD_BOT_TOKEN manquant")
        exit(1)
    client.run(TOKEN)
PYTHON

echo "  -> discord_listener.py mis a jour (thread persistant)"

# ── 2. Mettre a jour le gateway pour supporter les messages de suivi ─────────
echo "[2/2] Mise a jour gateway (messages de suivi)..."

# Le gateway doit charger le state existant au lieu d'en creer un vierge
cat > /tmp/fix_gateway.py << 'FIXPY'
import re

with open("agents/gateway.py", "r") as f:
    content = f.read()

# Remplacer le bloc qui cree un state vierge par un qui charge l'existant
old_state = '''        state = {
            "messages": msgs,
            "project_id": request.project_id,
            "project_phase": "discovery",
            "project_metadata": {},
            "agent_outputs": {},
            "legal_alerts": [],
            "decision_history": [],
            "current_assignments": {},
            "blockers": [],
            "human_feedback_log": [],
            "notifications_log": [],
        }'''

new_state = '''        # Charger le state existant ou en creer un nouveau
        existing = None
        try:
            existing = graph.get_state(config)
        except Exception:
            pass

        if existing and existing.values and existing.values.get("decision_history"):
            # State existant — ajouter le nouveau message
            state = dict(existing.values)
            state["messages"] = list(state.get("messages", [])) + msgs
        else:
            # Nouveau state
            state = {
                "messages": msgs,
                "project_id": request.project_id,
                "project_phase": "discovery",
                "project_metadata": {},
                "agent_outputs": {},
                "legal_alerts": [],
                "decision_history": [],
                "current_assignments": {},
                "blockers": [],
                "human_feedback_log": [],
                "notifications_log": [],
            }'''

if "existing = None" not in content:
    content = content.replace(old_state, new_state)
    with open("agents/gateway.py", "w") as f:
        f.write(content)
    print("Gateway patched — state persistence")
else:
    print("Gateway already patched")
FIXPY

python3 /tmp/fix_gateway.py
rm -f /tmp/fix_gateway.py

echo "  -> Gateway mis a jour (charge le state existant)"

# ── Rebuild ──────────────────────────────────
echo ""
echo "Rebuild..."
docker compose up -d --build langgraph-api discord-bot
sleep 12

H=$(curl -s http://localhost:8123/health)
echo "Health: ${H}"

echo ""
echo "==========================================="
echo "  Thread persistence installe."
echo ""
echo "  Comportement :"
echo "  - Chaque message dans #commandes continue le meme projet"
echo "  - L'Orchestrateur retrouve les livrables precedents"
echo "  - Commande !new [nom] : demarre un nouveau projet"  
echo "  - Commande !status : voir l'etat du projet"
echo ""
echo "  Test :"
echo "  1. Envoyez le brief dans #commandes"
echo "  2. Attendez les resultats"
echo "  3. Envoyez : 'Fait moi un resume des User Stories'"
echo "  4. L'Orchestrateur devrait retrouver le contexte"
echo "==========================================="

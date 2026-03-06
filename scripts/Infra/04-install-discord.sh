#!/bin/bash
###############################################################################
# Script 4 : Installation du bot Discord MCP (communication agents <-> humain)
# VERSION CONSOLIDEE (integre le listener asynchrone du fix 10)
#
# A executer depuis la VM Ubuntu, apres le script 03.
# Pre-requis :
#   - Script 03 execute (projet ~/langgraph-project existe)
#   - Bot Discord cree sur https://discord.com/developers/applications
#   - Token bot + IDs des channels renseignes dans .env
#
# Usage : ./04-install-discord.sh
###############################################################################
set -euo pipefail

PROJECT_DIR="$HOME/langgraph-project"

echo "==========================================="
echo "  Script 4 : Installation Discord MCP"
echo "==========================================="
echo ""

# ── Verification pre-requis ──────────────────────────────────────────────────
if [ ! -d "${PROJECT_DIR}" ]; then
    echo "ERREUR : ${PROJECT_DIR} n'existe pas. Executez d'abord 03-install-langgraph.sh"
    exit 1
fi

if [ ! -f "${PROJECT_DIR}/.env" ]; then
    echo "ERREUR : ${PROJECT_DIR}/.env n'existe pas."
    exit 1
fi

cd "${PROJECT_DIR}"

# ── 1. Verifier les variables Discord dans .env ─────────────────────────────
echo "[1/7] Verification du .env..."

# Ajouter les variables Discord si absentes
if ! grep -q "DISCORD_BOT_TOKEN" .env; then
    echo "" >> .env
    cat >> .env << 'EOF'

# ── Discord MCP ──────────────────────────────
DISCORD_BOT_TOKEN=VOTRE-TOKEN-BOT-DISCORD
DISCORD_CHANNEL_REVIEW=ID-DU-CHANNEL-HUMAN-REVIEW
DISCORD_CHANNEL_LOGS=ID-DU-CHANNEL-AGENT-LOGS
DISCORD_CHANNEL_ALERTS=ID-DU-CHANNEL-ALERTS
DISCORD_CHANNEL_COMMANDS=ID-DU-CHANNEL-COMMANDES
DISCORD_GUILD_ID=ID-DE-VOTRE-SERVEUR
EOF
    echo "  -> Variables Discord ajoutees dans .env"
    echo "  -> PENSEZ A REMPLIR LES VALEURS !"
else
    echo "  -> Variables Discord deja presentes dans .env"
fi

# Verifier que le token n'est pas la valeur par defaut
DISCORD_TOKEN=$(grep "DISCORD_BOT_TOKEN" .env | cut -d= -f2)
if [ "$DISCORD_TOKEN" = "VOTRE-TOKEN-BOT-DISCORD" ] || [ -z "$DISCORD_TOKEN" ]; then
    echo ""
    echo "  ATTENTION : DISCORD_BOT_TOKEN n'est pas configure."
    echo "  Le bot ne pourra pas se connecter tant que vous"
    echo "  n'aurez pas renseigne un vrai token."
    echo ""
    echo "  Pour obtenir un token :"
    echo "  1. https://discord.com/developers/applications"
    echo "  2. New Application -> nommer 'LangGraph Agent'"
    echo "  3. Onglet Bot -> Reset Token -> copier"
    echo "  4. Activer MESSAGE CONTENT INTENT"
    echo "  5. OAuth2 -> URL Generator -> scopes: bot, applications.commands"
    echo "  6. Permissions: Send Messages, Read History, Add Reactions,"
    echo "     Embed Links, Attach Files, Use Slash Commands"
    echo ""
fi

# ── 2. Installer les dependances Python ──────────────────────────────────────
echo "[2/7] Installation des dependances Python..."
source .venv/bin/activate
pip install -q discord.py aiohttp

# ── 3. Creer agents/shared/ si necessaire ────────────────────────────────────
echo "[3/7] Creation des fichiers Discord..."
mkdir -p agents/shared

# ── 4. discord_tools.py (outils MCP + human-in-the-loop) ────────────────────
echo "[4/7] Creation de agents/shared/discord_tools.py..."
cat > agents/shared/__init__.py << 'PYTHON'
PYTHON

cat > agents/shared/discord_tools.py << 'PYTHON'
"""
Discord MCP tools pour la communication agents <-> humain.
Utilise par tous les agents pour les notifications et le human-in-the-loop.
"""
import os
import asyncio
import threading
import discord
from discord import Intents, Client
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN")
CHANNEL_REVIEW = int(os.getenv("DISCORD_CHANNEL_REVIEW", "0"))
CHANNEL_LOGS = int(os.getenv("DISCORD_CHANNEL_LOGS", "0"))
CHANNEL_ALERTS = int(os.getenv("DISCORD_CHANNEL_ALERTS", "0"))

# ── Client Discord (singleton) ──────────────
intents = Intents.default()
intents.message_content = True
client = Client(intents=intents)

_client_ready = asyncio.Event()

@client.event
async def on_ready():
    print(f"Discord bot connecte : {client.user}")
    _client_ready.set()


# ── Fonctions utilitaires ────────────────────

async def send_notification(channel_id: int, message: str, embed: dict = None):
    """Envoie une notification sans attendre de reponse."""
    await _client_ready.wait()
    channel = client.get_channel(channel_id)
    if channel is None:
        channel = await client.fetch_channel(channel_id)

    if embed:
        discord_embed = discord.Embed(
            title=embed.get("title", ""),
            description=embed.get("description", ""),
            color=embed.get("color", 0x6366F1),
        )
        for field in embed.get("fields", []):
            discord_embed.add_field(
                name=field["name"],
                value=field["value"],
                inline=field.get("inline", False),
            )
        await channel.send(content=message, embed=discord_embed)
    else:
        await channel.send(content=message)


async def request_human_approval(
    channel_id: int,
    agent_name: str,
    question: str,
    context: str = "",
    timeout: int = 300,
) -> dict:
    """
    Envoie une demande de validation et attend la reponse humaine.
    Retourne: {"approved": bool, "response": str, "timed_out": bool}
    """
    await _client_ready.wait()
    channel = client.get_channel(channel_id)
    if channel is None:
        channel = await client.fetch_channel(channel_id)

    embed = discord.Embed(
        title=f"Validation requise - {agent_name}",
        description=question,
        color=0xF59E0B,
    )
    if context:
        embed.add_field(name="Contexte", value=context[:1024], inline=False)
    embed.add_field(
        name="Actions",
        value="Repondre `approve` ou `revise` (+ commentaire optionnel)",
        inline=False,
    )
    embed.set_footer(text=f"Timeout: {timeout}s - sans reponse = escalade")

    msg = await channel.send(embed=embed)
    await msg.add_reaction("\u2705")
    await msg.add_reaction("\U0001f504")

    def check(m):
        return (
            m.channel.id == channel_id
            and not m.author.bot
            and m.reference is not None
            and m.reference.message_id == msg.id
        ) or (
            m.channel.id == channel_id
            and not m.author.bot
            and m.content.lower().startswith(("approve", "revise"))
        )

    try:
        reply = await client.wait_for("message", check=check, timeout=timeout)
        content = reply.content.lower().strip()
        approved = content.startswith("approve") or content == "ok" or content == "yes"
        return {
            "approved": approved,
            "response": reply.content,
            "timed_out": False,
            "reviewer": str(reply.author),
        }
    except asyncio.TimeoutError:
        await channel.send(f"Timeout - pas de reponse pour `{agent_name}`. Escalade automatique.")
        return {
            "approved": False,
            "response": "",
            "timed_out": True,
            "reviewer": None,
        }


async def send_alert(message: str, severity: str = "warning"):
    """Envoie une alerte dans le channel #alerts."""
    colors = {"info": 0x6366F1, "warning": 0xF59E0B, "error": 0xF43F5E, "critical": 0xFF0000}
    icons = {"info": "info", "warning": "warning", "error": "error", "critical": "critical"}

    embed = discord.Embed(
        title=f"Alerte - {severity.upper()}",
        description=message,
        color=colors.get(severity, 0xF59E0B),
    )
    await send_notification(CHANNEL_ALERTS, "", embed=embed)


async def send_phase_transition(from_phase: str, to_phase: str, details: str = ""):
    """Log une transition de phase dans #orchestrateur-logs."""
    embed = discord.Embed(
        title="Transition de phase",
        description=f"**{from_phase}** -> **{to_phase}**",
        color=0x10B981,
    )
    if details:
        embed.add_field(name="Details", value=details[:1024], inline=False)
    await send_notification(CHANNEL_LOGS, "", embed=embed)


# ── Integration LangGraph ────────────────────

def create_discord_tools_for_langgraph():
    """
    Retourne des tools LangChain utilisables dans les agents LangGraph.
    """
    from langchain_core.tools import tool

    @tool
    def notify_discord(channel: str, message: str) -> str:
        """Envoie une notification Discord. channel: 'logs' | 'review' | 'alerts'"""
        channel_map = {
            "logs": CHANNEL_LOGS,
            "review": CHANNEL_REVIEW,
            "alerts": CHANNEL_ALERTS,
        }
        channel_id = channel_map.get(channel, CHANNEL_LOGS)
        asyncio.run_coroutine_threadsafe(
            send_notification(channel_id, message), client.loop
        )
        return f"Message envoye dans #{channel}"

    @tool
    def request_approval(question: str, context: str = "") -> dict:
        """Demande une validation humaine via Discord. Bloque jusqu'a reponse."""
        future = asyncio.run_coroutine_threadsafe(
            request_human_approval(
                CHANNEL_REVIEW,
                agent_name="Agent",
                question=question,
                context=context,
            ),
            client.loop,
        )
        return future.result(timeout=600)

    return [notify_discord, request_approval]


# ── Demarrage du bot (dans un thread separe) ─

def start_discord_bot():
    """Lance le bot Discord dans un thread background."""
    loop = asyncio.new_event_loop()

    def run():
        asyncio.set_event_loop(loop)
        loop.run_until_complete(client.start(BOT_TOKEN))

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    return client
PYTHON

# ── 5. discord_listener.py (ecoute #commandes) ──────────────────────────────
echo "[5/7] Creation de agents/discord_listener.py (version asynchrone)..."
cat > agents/discord_listener.py << 'PYTHON'
"""Discord Listener — Ecoute #commandes et forward vers LangGraph API."""
import os
import asyncio
import logging
import aiohttp
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


@client.event
async def on_ready():
    logger.info(f"Bot connecte : {client.user}")


@client.event
async def on_message(message):
    # Ignorer les messages du bot
    if message.author == client.user:
        return

    # Ignorer si pas dans #commandes
    if CHANNEL_COMMANDS and str(message.channel.id) != CHANNEL_COMMANDS:
        return

    # Ignorer les messages courts
    if len(message.content) < 5:
        return

    logger.info(f"Message recu de {message.author}: {message.content[:100]}")

    # Reaction pour confirmer la reception
    await message.add_reaction("\u2705")

    try:
        # Appeler l'API LangGraph avec le channel_id pour les callbacks
        async with aiohttp.ClientSession() as session:
            payload = {
                "messages": [{"role": "user", "content": message.content}],
                "thread_id": f"discord-{message.id}",
                "project_id": "default",
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

                    # Discord limite a 2000 chars
                    if len(output) > 1900:
                        chunks = [output[i:i+1900] for i in range(0, len(output), 1900)]
                        for chunk in chunks:
                            await message.reply(chunk)
                    else:
                        await message.reply(output)

                else:
                    error = await resp.text()
                    logger.error(f"API error {resp.status}: {error[:200]}")
                    await message.reply(f"Erreur API: {resp.status}")

    except asyncio.TimeoutError:
        await message.reply("L'orchestrateur prend du temps. Les resultats seront postes quand les agents auront termine.")
    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
        await message.reply(f"Erreur: {str(e)[:200]}")


if __name__ == "__main__":
    if not TOKEN:
        logger.error("DISCORD_BOT_TOKEN manquant dans .env")
        exit(1)
    client.run(TOKEN)
PYTHON

# ── 6. Dockerfile.discord ───────────────────────────────────────────────────
echo "[6/7] Creation du Dockerfile.discord..."
cat > Dockerfile.discord << 'DOCKERFILE'
FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential curl \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir \
    discord.py>=2.4.0 \
    python-dotenv>=1.0.0 \
    langchain-core>=0.3.0 \
    aiohttp>=3.10.0

COPY agents/shared/ ./agents/shared/
COPY agents/discord_listener.py ./agents/discord_listener.py

CMD ["python", "agents/discord_listener.py"]
DOCKERFILE

# ── 7. Ajouter le service discord-bot dans docker-compose.yml ────────────────
echo "[7/7] Ajout du service discord-bot dans docker-compose.yml..."

if grep -q "discord-bot:" docker-compose.yml; then
    echo "  -> Service discord-bot deja present dans docker-compose.yml"
else
    # Inserer le service discord-bot avant la derniere ligne (fermeture YAML implicite)
    # On ajoute a la fin du fichier, juste avant le dernier bloc
    cat >> docker-compose.yml << 'YAML'

  # ── Discord Bot (MCP Agent Communication) ───
  discord-bot:
    build:
      context: .
      dockerfile: Dockerfile.discord
    container_name: langgraph-discord
    restart: unless-stopped
    env_file:
      - .env
    depends_on:
      langgraph-api:
        condition: service_healthy
    networks:
      - langgraph-net
YAML
    echo "  -> Service discord-bot ajoute dans docker-compose.yml"
fi

# ── Mise a jour de requirements.txt ──────────────────────────────────────────
if ! grep -q "discord.py" requirements.txt; then
    echo "discord.py>=2.4.0" >> requirements.txt
    echo "aiohttp>=3.10.0" >> requirements.txt
    echo "  -> discord.py et aiohttp ajoutes dans requirements.txt"
fi

# ── Resume ───────────────────────────────────────────────────────────────────
echo ""
echo "==========================================="
echo "  Discord MCP installe avec succes."
echo ""
echo "  Fichiers crees :"
echo "    agents/shared/discord_tools.py  (outils MCP)"
echo "    agents/discord_listener.py      (listener #commandes)"
echo "    Dockerfile.discord              (image Docker)"
echo ""
echo "  Prochaines etapes :"
echo ""
echo "  1. Configurez le .env avec vos vrais tokens :"
echo "     nano ${PROJECT_DIR}/.env"
echo ""
echo "  2. Testez le bot en standalone :"
echo "     cd ${PROJECT_DIR}"
echo "     source .venv/bin/activate"
echo "     python agents/discord_listener.py"
echo ""
echo "  3. Lancez via Docker Compose (stack complete) :"
echo "     docker compose up -d"
echo ""
echo "  4. Dans Discord #commandes, envoyez un message"
echo "     pour verifier que le bot repond."
echo ""
echo "  Structure Discord recommandee :"
echo "    #orchestrateur-logs  (transitions de phase)"
echo "    #human-review        (validations human-in-the-loop)"
echo "    #alerts              (erreurs, escalades)"
echo "    #commandes           (vos instructions aux agents)"
echo "    #rapports            (resumes)"
echo "==========================================="

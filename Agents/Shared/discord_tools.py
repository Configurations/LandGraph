"""Discord MCP tools pour la communication agents <-> humain (human-in-the-loop)."""
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

intents = Intents.default()
intents.message_content = True
client = Client(intents=intents)

_client_ready = asyncio.Event()


@client.event
async def on_ready():
    print(f"Discord bot connecte : {client.user}")
    _client_ready.set()


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
                name=field["name"], value=field["value"],
                inline=field.get("inline", False),
            )
        await channel.send(content=message, embed=discord_embed)
    else:
        await channel.send(content=message)


async def request_human_approval(channel_id: int, agent_name: str, question: str,
                                  context: str = "", timeout: int = 300) -> dict:
    """Envoie une demande de validation et attend la reponse humaine."""
    await _client_ready.wait()
    channel = client.get_channel(channel_id)
    if channel is None:
        channel = await client.fetch_channel(channel_id)

    embed = discord.Embed(
        title=f"Validation requise - {agent_name}",
        description=question, color=0xF59E0B,
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
            (m.channel.id == channel_id and not m.author.bot
             and m.reference is not None
             and m.reference.message_id == msg.id)
            or (m.channel.id == channel_id and not m.author.bot
                and m.content.lower().startswith(("approve", "revise")))
        )

    try:
        reply = await client.wait_for("message", check=check, timeout=timeout)
        content = reply.content.lower().strip()
        approved = content.startswith("approve") or content == "ok" or content == "yes"
        return {
            "approved": approved, "response": reply.content,
            "timed_out": False, "reviewer": str(reply.author),
        }
    except asyncio.TimeoutError:
        await channel.send(
            f"Timeout - pas de reponse pour `{agent_name}`. Escalade automatique."
        )
        return {"approved": False, "response": "", "timed_out": True, "reviewer": None}


async def send_alert(message: str, severity: str = "warning"):
    """Envoie une alerte dans le channel #alerts."""
    colors = {
        "info": 0x6366F1, "warning": 0xF59E0B,
        "error": 0xF43F5E, "critical": 0xFF0000,
    }
    embed = discord.Embed(
        title=f"Alerte - {severity.upper()}",
        description=message, color=colors.get(severity, 0xF59E0B),
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


def create_discord_tools_for_langgraph():
    """Retourne des tools LangChain utilisables dans les agents LangGraph."""
    from langchain_core.tools import tool

    @tool
    def notify_discord(channel: str, message: str) -> str:
        """Envoie une notification Discord. channel: 'logs' | 'review' | 'alerts'"""
        channel_map = {"logs": CHANNEL_LOGS, "review": CHANNEL_REVIEW, "alerts": CHANNEL_ALERTS}
        channel_id = channel_map.get(channel, CHANNEL_LOGS)
        asyncio.run_coroutine_threadsafe(send_notification(channel_id, message), client.loop)
        return f"Message envoye dans #{channel}"

    @tool
    def request_approval(question: str, context: str = "") -> dict:
        """Demande une validation humaine via Discord. Bloque jusqu'a reponse."""
        future = asyncio.run_coroutine_threadsafe(
            request_human_approval(
                CHANNEL_REVIEW, agent_name="Agent",
                question=question, context=context,
            ),
            client.loop,
        )
        return future.result(timeout=600)

    return [notify_discord, request_approval]


def start_discord_bot():
    """Lance le bot Discord dans un thread background."""
    loop = asyncio.new_event_loop()

    def run():
        asyncio.set_event_loop(loop)
        loop.run_until_complete(client.start(BOT_TOKEN))

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    return client

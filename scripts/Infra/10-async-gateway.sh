#!/bin/bash
###############################################################################
# Script 10 : Gateway asynchrone — reponse immediate + agents en background
#
# Probleme : le gateway attend que tous les agents finissent (5-15 min)
#            avant de repondre -> timeout Discord.
# Fix : repondre immediatement avec la decision de l'Orchestrateur,
#       lancer les agents en background, poster les resultats dans Discord.
#
# Usage : ./10-async-gateway.sh
###############################################################################
set -euo pipefail

PROJECT_DIR="$HOME/langgraph-project"

echo "==========================================="
echo "  Script 10 : Gateway asynchrone"
echo "==========================================="
echo ""

cd "${PROJECT_DIR}"

# ── 1. Nouveau gateway asynchrone ────────────────────────────────────────────
echo "[1/2] Installation du gateway asynchrone..."

cat > agents/gateway.py << 'PYTHON'
"""FastAPI Gateway — Asynchrone. Repond immediatement, agents en background."""
import asyncio
import json
import logging
import os
from datetime import datetime, timezone

import psycopg
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, BackgroundTasks
from pydantic import BaseModel

load_dotenv()
logger = logging.getLogger("gateway")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s %(message)s")

app = FastAPI(title="LangGraph Multi-Agent API", version="0.4.0")

# ── Imports agents ───────────────────────────
from agents.requirements_analyst import agent as analyst_agent
from agents.ux_designer import agent as ux_agent
from agents.architect import agent as architect_agent
from agents.planner import agent as planner_agent
from agents.lead_dev import agent as lead_dev_agent
from agents.dev_frontend_web import agent as frontend_agent
from agents.dev_backend_api import agent as backend_agent
from agents.dev_mobile import agent as mobile_agent
from agents.qa_engineer import agent as qa_agent
from agents.devops_engineer import agent as devops_agent
from agents.docs_writer import agent as docs_agent
from agents.legal_advisor import agent as legal_agent

from agents.orchestrator import orchestrator_node, route_after_orchestrator
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.postgres import PostgresSaver

# ── Discord notification ─────────────────────
DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN", "")
DISCORD_CHANNEL_LOGS = os.getenv("DISCORD_CHANNEL_LOGS", "")
DISCORD_CHANNEL_COMMANDS = os.getenv("DISCORD_CHANNEL_COMMANDS", "")

async def post_to_discord(channel_id: str, message: str):
    """Poste un message dans un channel Discord via l'API REST."""
    if not DISCORD_BOT_TOKEN or not channel_id:
        logger.warning("Discord not configured, skipping notification")
        return

    import aiohttp
    url = f"https://discord.com/api/v10/channels/{channel_id}/messages"
    headers = {
        "Authorization": f"Bot {DISCORD_BOT_TOKEN}",
        "Content-Type": "application/json",
    }

    # Discord limite a 2000 chars par message
    chunks = [message[i:i+1900] for i in range(0, len(message), 1900)]

    async with aiohttp.ClientSession() as session:
        for chunk in chunks:
            payload = {"content": chunk}
            try:
                async with session.post(url, headers=headers, json=payload) as resp:
                    if resp.status != 200:
                        logger.error(f"Discord POST failed: {resp.status}")
            except Exception as e:
                logger.error(f"Discord error: {e}")


# ── Agent map ────────────────────────────────
AGENT_MAP = {
    "requirements_analyst": analyst_agent, "ux_designer": ux_agent,
    "architect": architect_agent, "planner": planner_agent,
    "lead_dev": lead_dev_agent, "dev_frontend_web": frontend_agent,
    "dev_backend_api": backend_agent, "dev_mobile": mobile_agent,
    "qa_engineer": qa_agent, "devops_engineer": devops_agent,
    "docs_writer": docs_agent, "legal_advisor": legal_agent,
}

# ── Graph (orchestrateur seul pour la reponse rapide) ────────────────────────
def build_orchestrator_only_graph():
    """Graphe qui execute SEULEMENT l'orchestrateur (pour la reponse immediate)."""
    graph = StateGraph(dict)
    graph.add_node("orchestrator", orchestrator_node)
    graph.set_entry_point("orchestrator")
    graph.add_edge("orchestrator", END)
    return graph

GRAPH = None
def get_orchestrator_graph():
    global GRAPH
    if GRAPH is None:
        db_uri = os.getenv("DATABASE_URI")
        conn = psycopg.connect(db_uri, autocommit=True)
        cp = PostgresSaver(conn)
        cp.setup()
        GRAPH = build_orchestrator_only_graph().compile(checkpointer=cp)
        logger.info("Orchestrator graph ready")
    return GRAPH


# ── Background agent runner ──────────────────
async def run_agents_background(state: dict, decisions: list, thread_id: str, channel_id: str):
    """Execute les agents dispatches en background et poste les resultats dans Discord."""
    logger.info(f"[background] Starting agents for thread {thread_id}")

    # Extraire les agents a lancer
    agents_to_run = []
    for decision in decisions:
        for action in decision.get("actions", []):
            if isinstance(action, dict) and action.get("action") == "dispatch_agent":
                target = action.get("target", "")
                if target in AGENT_MAP:
                    agents_to_run.append({
                        "agent_id": target,
                        "agent": AGENT_MAP[target],
                        "task": action.get("task") or "",
                    })

    if not agents_to_run:
        logger.info("[background] No agents to run")
        return

    # Executer chaque agent
    for agent_info in agents_to_run:
        agent_id = agent_info["agent_id"]
        agent_callable = agent_info["agent"]
        task = agent_info["task"]

        logger.info(f"[background] Running {agent_id}...")

        try:
            # Notifier Discord que l'agent demarre
            await post_to_discord(
                channel_id,
                f"⏳ **{agent_id}** commence son travail...\nTache : {task[:200]}"
            )

            # Executer l'agent (synchrone dans un thread pool)
            result_state = await asyncio.to_thread(agent_callable, dict(state))

            # Extraire le resultat
            agent_output = result_state.get("agent_outputs", {}).get(agent_id, {})
            status = agent_output.get("status", "unknown")
            confidence = agent_output.get("confidence", "N/A")

            # Mettre a jour le state global
            state["agent_outputs"] = result_state.get("agent_outputs", state.get("agent_outputs", {}))

            # Formater le resultat pour Discord
            result_msg = f"✅ **{agent_id}** termine — status={status}, confidence={confidence}\n"

            deliverables = agent_output.get("deliverables", {})
            if isinstance(deliverables, dict):
                result_msg += f"Livrables : {', '.join(deliverables.keys())}\n"

                for key, val in list(deliverables.items())[:3]:
                    if isinstance(val, str):
                        preview = val[:500] + "..." if len(val) > 500 else val
                    elif isinstance(val, (dict, list)):
                        preview = json.dumps(val, ensure_ascii=False, default=str)[:500] + "..."
                    else:
                        preview = str(val)[:500]
                    result_msg += f"\n**{key}** :\n{preview}\n"

            # Poster dans Discord
            await post_to_discord(channel_id, result_msg)

            logger.info(f"[background] {agent_id} done — status={status}")

        except Exception as e:
            logger.error(f"[background] {agent_id} failed: {e}", exc_info=True)
            await post_to_discord(
                channel_id,
                f"❌ **{agent_id}** erreur : {str(e)[:300]}"
            )

    # Quand tous les agents ont fini, poster un resume
    completed = list(state.get("agent_outputs", {}).keys())
    await post_to_discord(
        channel_id,
        f"📋 **Phase Discovery terminee**\nAgents completes : {', '.join(completed)}\n"
        f"Prochaine etape : validation humaine pour passer en phase Design."
    )


# ── Endpoints ────────────────────────────────

@app.get("/health")
async def health():
    return {"status": "ok", "service": "langgraph-multi-agent", "version": "0.4.0"}

@app.get("/status")
async def status():
    return {"agents": list(AGENT_MAP) + ["orchestrator"], "total_agents": len(AGENT_MAP) + 1}


class InvokeRequest(BaseModel):
    messages: list[dict]
    thread_id: str = "default"
    project_id: str = "default"
    channel_id: str = ""

class InvokeResponse(BaseModel):
    output: str
    thread_id: str
    decisions: list = []
    agents_dispatched: list = []


@app.post("/invoke", response_model=InvokeResponse)
async def invoke(request: InvokeRequest, background_tasks: BackgroundTasks):
    try:
        graph = get_orchestrator_graph()
        config = {"configurable": {"thread_id": request.thread_id}}

        msgs = [(m.get("role", "user"), m.get("content", "")) for m in request.messages]

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
        }

        # Etape 1 : Orchestrateur SEUL (rapide, ~5-10 secondes)
        result = graph.invoke(state, config)

        decisions = result.get("decision_history", [])

        # Extraire les agents dispatches
        agents_dispatched = []
        for d in decisions:
            for a in d.get("actions", []):
                if isinstance(a, dict) and a.get("action") == "dispatch_agent":
                    target = a.get("target", "")
                    task = (a.get("task") or "")[:200]
                    if target:
                        agents_dispatched.append({"agent": target, "task": task})

        # Formater la reponse immediate
        output_parts = []
        for i, d in enumerate(decisions, 1):
            dtype = d.get("decision_type", "unknown")
            conf = d.get("confidence", 0)
            reasoning = d.get("reasoning", "")[:300]
            output_parts.append(f"**Decision {i}** : {dtype} (confiance: {conf})\n{reasoning}")

        if agents_dispatched:
            output_parts.append("\n**Agents lances en arriere-plan :**")
            for ad in agents_dispatched:
                output_parts.append(f"  ⏳ {ad['agent']} : {ad['task']}")
            output_parts.append("\nLes resultats seront postes dans ce channel quand les agents auront termine.")

        output_text = "\n\n".join(output_parts) if output_parts else "Orchestrateur en attente."

        # Etape 2 : Lancer les agents en BACKGROUND
        if agents_dispatched:
            channel_id = request.channel_id or DISCORD_CHANNEL_COMMANDS or DISCORD_CHANNEL_LOGS
            background_tasks.add_task(
                run_agents_background,
                result,  # state avec les decisions
                decisions,
                request.thread_id,
                channel_id,
            )

        return InvokeResponse(
            output=output_text,
            thread_id=request.thread_id,
            decisions=decisions,
            agents_dispatched=[ad["agent"] for ad in agents_dispatched],
        )

    except Exception as e:
        logger.error(f"Invoke error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.on_event("startup")
async def startup():
    try:
        get_orchestrator_graph()
        logger.info("Async gateway ready")
    except Exception as e:
        logger.error(f"Init error: {e}")
PYTHON

echo "  -> gateway.py asynchrone installe"

# ── 2. Mettre a jour le discord_listener pour passer le channel_id ───────────
echo "[2/2] Mise a jour du discord_listener..."

cat > agents/discord_listener.py << 'PYTHON'
"""Discord Listener — Ecoute #commandes et forward vers LangGraph API."""
import os
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
    await message.add_reaction("✅")

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
                    agents = data.get("agents_dispatched", [])

                    # Reponse immediate (decision de l'orchestrateur)
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
        await message.reply("⏳ L'orchestrateur prend du temps. Les resultats seront postes quand les agents auront termine.")
    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
        await message.reply(f"Erreur: {str(e)[:200]}")


import asyncio

if __name__ == "__main__":
    if not TOKEN:
        logger.error("DISCORD_BOT_TOKEN manquant dans .env")
        exit(1)
    client.run(TOKEN)
PYTHON

echo "  -> discord_listener.py mis a jour (timeout 30s, channel_id passe)"

# ── Rebuild ──────────────────────────────────
echo ""
echo "Rebuild..."
docker compose up -d --build langgraph-api discord-bot
sleep 12

H=$(curl -s http://localhost:8123/health)
echo "Health: ${H}"

echo ""
echo "==========================================="
echo "  Gateway asynchrone installee."
echo ""
echo "  Comportement :"
echo "  1. Brief arrive dans Discord"
echo "  2. Orchestrateur analyse (5-10s)"
echo "  3. Reponse IMMEDIATE : 'J'ai dispatche Analyste + Avocat'"
echo "  4. Agents travaillent en background (2-15 min)"
echo "  5. Chaque agent poste son resultat dans Discord quand il finit"
echo "  6. Quand tous les agents sont finis -> resume poste"
echo "==========================================="

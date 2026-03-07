#!/bin/bash
###############################################################################
# Script 16 : Acceleration — Routing direct + parallelisme reel
#
# Problemes resolus :
#   - L'Orchestrateur fait 10+ decisions avant de router
#   - Les agents "paralleles" sont executes sequentiellement
#   - Pas de moyen de cibler un agent directement
#
# Solutions :
#   - Commande !agent <id> <tache> : bypass l'Orchestrateur
#   - Execution async reelle (asyncio.gather)
#   - Timeout par agent (5 min max)
#
# Usage : ./16-speedup.sh
###############################################################################
set -euo pipefail

PROJECT_DIR="$HOME/langgraph-project"

echo "==========================================="
echo "  Script 16 : Acceleration"
echo "==========================================="
echo ""

cd "${PROJECT_DIR}"

# ── 1. Mettre a jour le gateway pour le routing direct + vrai parallelisme ───
echo "[1/3] Mise a jour du gateway..."

cat > agents/gateway.py << 'PYTHON'
"""FastAPI Gateway — Routing direct + parallelisme reel."""
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

app = FastAPI(title="LangGraph Multi-Agent API", version="0.5.0")

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

DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN", "")

AGENT_MAP = {
    "requirements_analyst": analyst_agent, "analyste": analyst_agent,
    "ux_designer": ux_agent, "designer": ux_agent,
    "architect": architect_agent, "architecte": architect_agent,
    "planner": planner_agent, "planificateur": planner_agent,
    "lead_dev": lead_dev_agent,
    "dev_frontend_web": frontend_agent, "frontend": frontend_agent,
    "dev_backend_api": backend_agent, "backend": backend_agent,
    "dev_mobile": mobile_agent, "mobile": mobile_agent,
    "qa_engineer": qa_agent, "qa": qa_agent,
    "devops_engineer": devops_agent, "devops": devops_agent,
    "docs_writer": docs_agent, "documentaliste": docs_agent, "docs": docs_agent,
    "legal_advisor": legal_agent, "avocat": legal_agent,
}

# IDs canoniques (pour le graphe LangGraph)
CANONICAL_AGENTS = {
    "requirements_analyst": analyst_agent, "ux_designer": ux_agent,
    "architect": architect_agent, "planner": planner_agent,
    "lead_dev": lead_dev_agent, "dev_frontend_web": frontend_agent,
    "dev_backend_api": backend_agent, "dev_mobile": mobile_agent,
    "qa_engineer": qa_agent, "devops_engineer": devops_agent,
    "docs_writer": docs_agent, "legal_advisor": legal_agent,
}

# ── Discord notification ─────────────────────
async def post_to_discord(channel_id, message):
    if not DISCORD_BOT_TOKEN or not channel_id:
        return
    import aiohttp
    url = f"https://discord.com/api/v10/channels/{channel_id}/messages"
    headers = {"Authorization": f"Bot {DISCORD_BOT_TOKEN}", "Content-Type": "application/json"}
    async with aiohttp.ClientSession() as session:
        for chunk in [message[i:i+1900] for i in range(0, len(message), 1900)]:
            try:
                async with session.post(url, headers=headers, json={"content": chunk}) as resp:
                    if resp.status not in (200, 201):
                        logger.error(f"Discord POST: {resp.status}")
            except Exception as e:
                logger.error(f"Discord: {e}")


# ── Orchestrator graph ───────────────────────
def build_orchestrator_graph():
    graph = StateGraph(dict)
    graph.add_node("orchestrator", orchestrator_node)
    graph.set_entry_point("orchestrator")
    graph.add_edge("orchestrator", END)
    return graph

GRAPH = None
def get_orchestrator_graph():
    global GRAPH
    if GRAPH is None:
        c = psycopg.connect(os.getenv("DATABASE_URI"), autocommit=True)
        cp = PostgresSaver(c); cp.setup()
        GRAPH = build_orchestrator_graph().compile(checkpointer=cp)
        logger.info("Orchestrator graph ready")
    return GRAPH


# ── Background : execution d'un agent unique ─
async def run_single_agent(agent_id, agent_callable, state, channel_id):
    """Execute un seul agent avec timeout."""
    logger.info(f"[background] Running {agent_id}...")
    try:
        result_state = await asyncio.wait_for(
            asyncio.to_thread(agent_callable, dict(state)),
            timeout=300  # 5 min max par agent
        )
        state["agent_outputs"] = result_state.get("agent_outputs", state.get("agent_outputs", {}))
        logger.info(f"[background] {agent_id} done")
        return result_state
    except asyncio.TimeoutError:
        logger.error(f"[background] {agent_id} timeout (5min)")
        await post_to_discord(channel_id, f"⏰ **{agent_id}** timeout (5 minutes)")
        return state
    except Exception as e:
        logger.error(f"[background] {agent_id} error: {e}")
        await post_to_discord(channel_id, f"❌ **{agent_id}** erreur : {str(e)[:300]}")
        return state


# ── Background : execution parallele reelle ──
async def run_agents_parallel(agents_to_run, state, channel_id):
    """Execute plusieurs agents en parallele reel."""
    tasks = []
    for agent_info in agents_to_run:
        agent_id = agent_info["agent_id"]
        agent_callable = agent_info["agent"]
        # Chaque agent recoit sa propre copie du state
        tasks.append(run_single_agent(agent_id, agent_callable, dict(state), channel_id))

    results = await asyncio.gather(*tasks, return_exceptions=True)

    # Merger les outputs
    merged_outputs = dict(state.get("agent_outputs", {}))
    for r in results:
        if isinstance(r, dict) and "agent_outputs" in r:
            merged_outputs.update(r.get("agent_outputs", {}))

    completed = list(merged_outputs.keys())
    await post_to_discord(channel_id,
        f"📋 Agents termines : {', '.join(completed)}")


# ── Background : routing via orchestrateur ───
async def run_orchestrated(state, decisions, channel_id):
    """Route via l'Orchestrateur puis lance les agents en parallele."""
    agents_to_run = []
    for d in decisions:
        for a in d.get("actions", []):
            if isinstance(a, dict) and a.get("action") == "dispatch_agent":
                target = a.get("target", "")
                if target in CANONICAL_AGENTS:
                    agents_to_run.append({
                        "agent_id": target,
                        "agent": CANONICAL_AGENTS[target],
                        "task": a.get("task") or "",
                    })

    if agents_to_run:
        await run_agents_parallel(agents_to_run, state, channel_id)
    else:
        await post_to_discord(channel_id, "Orchestrateur n'a dispatche aucun agent.")


# ── Endpoints ────────────────────────────────

@app.get("/health")
async def health():
    return {"status": "ok", "service": "langgraph-multi-agent", "version": "0.5.0"}

@app.get("/status")
async def status():
    return {"agents": list(CANONICAL_AGENTS) + ["orchestrator"], "total_agents": len(CANONICAL_AGENTS) + 1}


class InvokeRequest(BaseModel):
    messages: list[dict]
    thread_id: str = "default"
    project_id: str = "default"
    channel_id: str = ""
    direct_agent: str = ""  # Si rempli, bypass l'orchestrateur

class InvokeResponse(BaseModel):
    output: str
    thread_id: str
    decisions: list = []
    agents_dispatched: list = []


@app.post("/invoke", response_model=InvokeResponse)
async def invoke(request: InvokeRequest, background_tasks: BackgroundTasks):
    try:
        channel_id = request.channel_id
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
            "_discord_channel_id": channel_id,
        }

        # ── Mode direct : bypass orchestrateur ───
        if request.direct_agent:
            agent_id = request.direct_agent.lower().strip()
            if agent_id not in AGENT_MAP:
                return InvokeResponse(
                    output=f"Agent inconnu : {agent_id}\nDisponibles : {', '.join(CANONICAL_AGENTS.keys())}",
                    thread_id=request.thread_id,
                )

            agent_callable = AGENT_MAP[agent_id]
            # Trouver l'ID canonique
            canonical_id = agent_id
            for cid, cagent in CANONICAL_AGENTS.items():
                if cagent is agent_callable:
                    canonical_id = cid
                    break

            background_tasks.add_task(
                run_agents_parallel,
                [{"agent_id": canonical_id, "agent": agent_callable}],
                state,
                channel_id,
            )

            return InvokeResponse(
                output=f"⚡ **{canonical_id}** lance directement.\nResultats dans ce channel.",
                thread_id=request.thread_id,
                agents_dispatched=[canonical_id],
            )

        # ── Mode orchestrateur ───────────────────
        graph = get_orchestrator_graph()
        config = {"configurable": {"thread_id": request.thread_id}}

        result = graph.invoke(state, config)
        decisions = result.get("decision_history", [])

        # Formater la reponse
        agents_dispatched = []
        output_parts = []
        for i, d in enumerate(decisions, 1):
            dtype = d.get("decision_type", "unknown")
            conf = d.get("confidence", 0)
            reasoning = d.get("reasoning", "")[:200]
            output_parts.append(f"**Decision {i}** : {dtype} (confiance: {conf})\n{reasoning}")
            for a in d.get("actions", []):
                if isinstance(a, dict) and a.get("action") == "dispatch_agent":
                    target = a.get("target", "")
                    task = (a.get("task") or "")[:150]
                    if target:
                        agents_dispatched.append(target)
                        output_parts.append(f"  ⏳ {target} : {task}")

        if agents_dispatched:
            output_parts.append("\nResultats dans ce channel.")

        output_text = "\n\n".join(output_parts) if output_parts else "Orchestrateur en attente."

        # Lancer les agents en parallele reel
        if agents_dispatched:
            result["_discord_channel_id"] = channel_id
            background_tasks.add_task(run_orchestrated, result, decisions, channel_id)

        return InvokeResponse(
            output=output_text,
            thread_id=request.thread_id,
            decisions=decisions,
            agents_dispatched=agents_dispatched,
        )

    except Exception as e:
        logger.error(f"Invoke error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.on_event("startup")
async def startup():
    try:
        get_orchestrator_graph()
        logger.info("Gateway v0.5.0 ready — direct routing + parallel")
    except Exception as e:
        logger.error(f"Init error: {e}")
PYTHON

echo "  -> gateway.py v0.5.0 (routing direct + parallelisme reel)"

# ── 2. Mettre a jour le discord_listener avec la commande !agent ─────────────
echo "[2/3] Mise a jour discord_listener (commande !agent)..."

cat > agents/discord_listener.py << 'PYTHON'
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

    # ── !status ──────────────────────────────
    if content.lower() == "!status":
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{API_URL}/status", timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    data = await resp.json()
                    await message.reply(f"📊 {data.get('total_agents')} agents | API v{data.get('version', '?')}")
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
PYTHON

echo "  -> discord_listener.py mis a jour (commande !agent)"

# ── 3. Rebuild ───────────────────────────────────────────────────────────────
echo "[3/3] Rebuild..."

docker compose up -d --build langgraph-api discord-bot
sleep 12

H=$(curl -s http://localhost:8123/health)
echo ""
echo "  Health: ${H}"

echo ""
echo "==========================================="
echo "  Acceleration activee."
echo ""
echo "  Nouvelles commandes Discord :"
echo "  !agent lead_dev Cree un repo GitHub PerformanceTracker"
echo "  !agent analyste Produis le PRD de PerformanceTracker"
echo "  !agent avocat Audit RGPD du projet"
echo "  !a backend Implemente POST /api/v1/users"
echo ""
echo "  Aliases disponibles :"
echo "  analyste, designer, architecte, lead, frontend,"
echo "  backend, mobile, qa, devops, docs, avocat"
echo ""
echo "  Ameliorations :"
echo "  - !agent bypass l'Orchestrateur (reponse en ~10s)"
echo "  - Agents executes en parallele reel (asyncio.gather)"
echo "  - Timeout 5 min par agent"
echo "==========================================="

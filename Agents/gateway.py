"""FastAPI Gateway v0.6.0 — Routing direct + parallelisme + thread persistence."""
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

app = FastAPI(title="LangGraph Multi-Agent API", version="0.6.0")

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

CANONICAL_AGENTS = {
    "requirements_analyst": analyst_agent, "ux_designer": ux_agent,
    "architect": architect_agent, "planner": planner_agent,
    "lead_dev": lead_dev_agent, "dev_frontend_web": frontend_agent,
    "dev_backend_api": backend_agent, "dev_mobile": mobile_agent,
    "qa_engineer": qa_agent, "devops_engineer": devops_agent,
    "docs_writer": docs_agent, "legal_advisor": legal_agent,
}


# ── Discord ──────────────────────────────────
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
                        logger.error(f"Discord: {resp.status}")
            except Exception as e:
                logger.error(f"Discord: {e}")


# ── Checkpointer + Graph ─────────────────────
DB_CONN = None
CHECKPOINTER = None
GRAPH = None


def get_checkpointer():
    global DB_CONN, CHECKPOINTER
    if CHECKPOINTER is None:
        DB_CONN = psycopg.connect(os.getenv("DATABASE_URI"), autocommit=True)
        CHECKPOINTER = PostgresSaver(DB_CONN)
        CHECKPOINTER.setup()
    return CHECKPOINTER


def build_orchestrator_graph():
    graph = StateGraph(dict)
    graph.add_node("orchestrator", orchestrator_node)
    graph.set_entry_point("orchestrator")
    graph.add_edge("orchestrator", END)
    return graph


def get_orchestrator_graph():
    global GRAPH
    if GRAPH is None:
        GRAPH = build_orchestrator_graph().compile(checkpointer=get_checkpointer())
        logger.info("Orchestrator graph ready")
    return GRAPH


def new_state(msgs, project_id, channel_id):
    return {
        "messages": msgs,
        "project_id": project_id,
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


def load_or_create_state(thread_id, msgs, project_id, channel_id):
    """Charge le state existant ou en cree un nouveau."""
    graph = get_orchestrator_graph()
    config = {"configurable": {"thread_id": thread_id}}

    try:
        existing = graph.get_state(config)
        if existing and existing.values and existing.values.get("agent_outputs"):
            state = dict(existing.values)
            old_msgs = list(state.get("messages", []))
            old_msgs.extend(msgs)
            state["messages"] = old_msgs
            state["_discord_channel_id"] = channel_id

            outputs = list(state.get("agent_outputs", {}).keys())
            logger.info(f"State loaded for {thread_id} — {len(outputs)} outputs: {outputs}")
            return state
    except Exception as e:
        logger.warning(f"Could not load state for {thread_id}: {e}")

    logger.info(f"New state for {thread_id}")
    return new_state(msgs, project_id, channel_id)


# ── Background runners ───────────────────────
async def run_single_agent(agent_id, agent_callable, state, channel_id):
    try:
        result = await asyncio.wait_for(
            asyncio.to_thread(agent_callable, dict(state)), timeout=300)
        state["agent_outputs"] = result.get("agent_outputs", state.get("agent_outputs", {}))
        logger.info(f"[bg] {agent_id} done")
        return result
    except asyncio.TimeoutError:
        logger.error(f"[bg] {agent_id} timeout")
        await post_to_discord(channel_id, f"⏰ **{agent_id}** timeout (5min)")
        return state
    except Exception as e:
        logger.error(f"[bg] {agent_id} error: {e}")
        await post_to_discord(channel_id, f"❌ **{agent_id}** erreur : {str(e)[:300]}")
        return state


async def run_agents_parallel(agents_to_run, state, channel_id):
    tasks = [run_single_agent(a["agent_id"], a["agent"], dict(state), channel_id) for a in agents_to_run]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    merged = dict(state.get("agent_outputs", {}))
    for r in results:
        if isinstance(r, dict) and "agent_outputs" in r:
            merged.update(r.get("agent_outputs", {}))
    await post_to_discord(channel_id, f"📋 Agents termines : {', '.join(merged.keys())}")


async def run_orchestrated(state, decisions, channel_id):
    agents = []
    for d in decisions:
        for a in d.get("actions", []):
            if isinstance(a, dict) and a.get("action") == "dispatch_agent":
                t = a.get("target", "")
                if t in CANONICAL_AGENTS:
                    agents.append({"agent_id": t, "agent": CANONICAL_AGENTS[t]})
    if agents:
        await run_agents_parallel(agents, state, channel_id)
    else:
        await post_to_discord(channel_id, "Aucun agent dispatche.")


# ── Endpoints ────────────────────────────────
@app.get("/health")
async def health():
    return {"status": "ok", "service": "langgraph-multi-agent", "version": "0.6.0"}

@app.get("/status")
async def status():
    return {"agents": list(CANONICAL_AGENTS) + ["orchestrator"], "total_agents": len(CANONICAL_AGENTS) + 1}


class InvokeRequest(BaseModel):
    messages: list[dict]
    thread_id: str = "default"
    project_id: str = "default"
    channel_id: str = ""
    direct_agent: str = ""

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

        # ── Mode direct ──────────────────────
        if request.direct_agent:
            agent_id = request.direct_agent.lower().strip()
            if agent_id not in AGENT_MAP:
                return InvokeResponse(
                    output=f"Agent inconnu : {agent_id}\nDisponibles : {', '.join(CANONICAL_AGENTS.keys())}",
                    thread_id=request.thread_id)

            agent_callable = AGENT_MAP[agent_id]
            canonical_id = agent_id
            for cid, ca in CANONICAL_AGENTS.items():
                if ca is agent_callable:
                    canonical_id = cid; break

            state = load_or_create_state(request.thread_id, msgs, request.project_id, channel_id)

            background_tasks.add_task(
                run_agents_parallel,
                [{"agent_id": canonical_id, "agent": agent_callable}],
                state, channel_id)

            # Info contexte
            existing = list(state.get("agent_outputs", {}).keys())
            ctx_info = f"\n📦 Contexte : {', '.join(existing)}" if existing else ""

            return InvokeResponse(
                output=f"⚡ **{canonical_id}** lance directement.{ctx_info}\nResultats dans ce channel.",
                thread_id=request.thread_id, agents_dispatched=[canonical_id])

        # ── Mode orchestrateur ───────────────
        state = load_or_create_state(request.thread_id, msgs, request.project_id, channel_id)

        graph = get_orchestrator_graph()
        config = {"configurable": {"thread_id": request.thread_id}}
        result = graph.invoke(state, config)

        decisions = result.get("decision_history", [])

        agents_dispatched = []
        output_parts = []

        existing_outputs = list(result.get("agent_outputs", {}).keys())
        if existing_outputs:
            output_parts.append(f"📦 Contexte charge : {', '.join(existing_outputs)}")

        for i, d in enumerate(decisions, 1):
            dtype = d.get("decision_type", "unknown")
            conf = d.get("confidence", 0)
            reasoning = d.get("reasoning", "")[:200]
            output_parts.append(f"**Decision {i}** : {dtype} (confiance: {conf})\n{reasoning}")
            for a in d.get("actions", []):
                if isinstance(a, dict) and a.get("action") == "dispatch_agent":
                    t = a.get("target", "")
                    task = (a.get("task") or "")[:150]
                    if t:
                        agents_dispatched.append(t)
                        output_parts.append(f"  ⏳ {t} : {task}")

        if agents_dispatched:
            output_parts.append("\nResultats dans ce channel.")

        output_text = "\n\n".join(output_parts) if output_parts else "Orchestrateur en attente."

        if agents_dispatched:
            result["_discord_channel_id"] = channel_id
            background_tasks.add_task(run_orchestrated, result, decisions, channel_id)

        return InvokeResponse(
            output=output_text, thread_id=request.thread_id,
            decisions=decisions, agents_dispatched=agents_dispatched)

    except Exception as e:
        logger.error(f"Invoke error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.on_event("startup")
async def startup():
    try:
        get_orchestrator_graph()
        logger.info("Gateway v0.6.0 ready — persistence + direct + parallel")
    except Exception as e:
        logger.error(f"Init error: {e}")

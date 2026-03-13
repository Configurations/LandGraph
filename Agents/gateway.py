"""FastAPI Gateway v0.6.0 — Routing direct + parallelisme + thread persistence."""
import asyncio
import json
import logging
import os
from datetime import datetime, timezone
from agents.shared.event_bus import bus, Event

import psycopg
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, BackgroundTasks, Request
from pydantic import BaseModel

load_dotenv()
logger = logging.getLogger("gateway")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s %(message)s")

# Log version at startup
for _vp in ["/project/.version", os.path.join(os.path.dirname(__file__), "..", ".version")]:
    if os.path.isfile(_vp):
        logger.info("LandGraph version: %s", open(_vp).read().strip())
        break
else:
    logger.info("LandGraph version: dev")

app = FastAPI(title="LangGraph Multi-Agent API", version="0.6.0")

from agents.shared.agent_loader import get_agents
from agents.shared.team_resolver import get_team_for_channel, get_all_team_ids
from agents.orchestrator import orchestrator_node, route_after_orchestrator
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.postgres import PostgresSaver


# Aliases — charges depuis discord.json ou fallback
def _load_aliases() -> dict:
    try:
        from agents.shared.team_resolver import find_global_file
        path = find_global_file("discord.json")
        if path:
            import json
            with open(path) as f:
                return json.load(f).get("aliases", {})
    except Exception:
        pass
    return {
        "analyste": "requirements_analyst", "analyst": "requirements_analyst",
        "designer": "ux_designer", "ux": "ux_designer",
        "architecte": "architect", "archi": "architect",
        "lead": "lead_dev", "leaddev": "lead_dev",
        "frontend": "dev_frontend_web", "front": "dev_frontend_web",
        "backend": "dev_backend_api", "back": "dev_backend_api",
        "mobile": "dev_mobile",
        "qa": "qa_engineer", "test": "qa_engineer",
        "devops": "devops_engineer", "ops": "devops_engineer",
        "docs": "docs_writer", "doc": "docs_writer",
        "avocat": "legal_advisor", "legal": "legal_advisor",
    }

ALIASES = _load_aliases()


def resolve_agents(channel_id: str = ""):
    """Resout les agents pour un channel (equipe)."""
    team_id = get_team_for_channel(channel_id) if channel_id else "default"
    canonical = get_agents(team_id)
    agent_map = dict(canonical)
    for alias, cid in ALIASES.items():
        if cid in canonical:
            agent_map[alias] = canonical[cid]
    return canonical, agent_map, team_id


# ── Canal de communication ────────────────────
async def post_to_channel(channel_id, message, thread_id=""):
    """Envoie un message via le canal par defaut (Discord, Email, etc.).
    Si thread_id commence par 'hitl-chat-', ecrit dans hitl_chat_messages a la place."""
    if not channel_id and not thread_id:
        return
    # HITL chat callback — store in DB instead of channel
    if thread_id and thread_id.startswith("hitl-chat-"):
        try:
            parts = thread_id.split("-", 4)  # hitl-chat-{team_id}-{agent_id}
            if len(parts) >= 4:
                team_id_part = parts[2]
                agent_id_part = "-".join(parts[3:])
                conn = psycopg.connect(os.getenv("DATABASE_URI"), autocommit=True)
                try:
                    with conn.cursor() as cur:
                        cur.execute("""
                            INSERT INTO project.hitl_chat_messages (team_id, agent_id, thread_id, sender, content)
                            VALUES (%s, %s, %s, %s, %s)
                        """, (team_id_part, agent_id_part, thread_id, agent_id_part, str(message)[:4000]))
                finally:
                    conn.close()
                logger.info(f"[hitl-chat] Saved message for {thread_id}")
                return
        except Exception as e:
            logger.error(f"[hitl-chat] Failed to save message: {e}")
    if not channel_id:
        return
    from agents.shared.channels import get_default_channel
    ch = get_default_channel()
    await ch.send(channel_id, message)


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


def new_state(msgs, project_id, channel_id, team_id="default"):
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
        "_team_id": team_id,
    }


def load_or_create_state(thread_id, msgs, project_id, channel_id, team_id="default"):
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
            state["_team_id"] = team_id

            outputs = list(state.get("agent_outputs", {}).keys())
            logger.info(f"State loaded for {thread_id} — {len(outputs)} outputs: {outputs}")
            return state
    except Exception as e:
        logger.warning(f"Could not load state for {thread_id}: {e}")

    logger.info(f"New state for {thread_id}")
    return new_state(msgs, project_id, channel_id, team_id)


# ── Background runners ───────────────────────
async def run_single_agent(agent_id, agent_callable, state, channel_id, thread_id=""):
    try:
        result = await asyncio.wait_for(
            asyncio.to_thread(agent_callable, dict(state)), timeout=2100)
        state["agent_outputs"] = result.get("agent_outputs", state.get("agent_outputs", {}))
        logger.info(f"[bg] {agent_id} done")
        # Post agent output to channel/HITL
        output = result.get("agent_outputs", {}).get(agent_id, {})
        if output and isinstance(output, dict):
            deliverable = output.get("deliverable", output.get("summary", ""))
            if deliverable:
                agent_name = output.get("agent_name", agent_id)
                await post_to_channel(channel_id, f"**{agent_name}** :\n{deliverable[:3000]}", thread_id)
            # Auto-publish to Outline if enabled
            await _maybe_publish_to_outline(state, agent_id, output)
        return result
    except asyncio.TimeoutError:
        logger.error(f"[bg] {agent_id} timeout")
        await post_to_channel(channel_id, f"⏰ **{agent_id}** timeout (35min)", thread_id)
        return state
    except Exception as e:
        logger.error(f"[bg] {agent_id} error: {e}")
        await post_to_channel(channel_id, f"❌ **{agent_id}** erreur : {str(e)[:300]}", thread_id)
        return state


async def run_agents_parallel(agents_to_run, state, channel_id, thread_id="default", _depth=0):
    MAX_CHAIN_DEPTH = 5  # max groupes enchaines automatiquement
    tasks = [run_single_agent(a["agent_id"], a["agent"], dict(state), channel_id, thread_id) for a in agents_to_run]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    merged = dict(state.get("agent_outputs", {}))
    for r in results:
        if isinstance(r, dict) and "agent_outputs" in r:
            merged.update(r.get("agent_outputs", {}))

    # Sauvegarder le state mis a jour dans le checkpointer
    state["agent_outputs"] = merged
    try:
        graph = get_orchestrator_graph()
        config = {"configurable": {"thread_id": thread_id}}
        graph.update_state(config, state)
        logger.info(f"State saved for {thread_id} — {len(merged)} outputs: {list(merged.keys())}")
    except Exception as e:
        logger.error(f"Could not save state for {thread_id}: {e}")

    # Message de fin
    if len(agents_to_run) > 1:
        names = []
        for a in agents_to_run:
            aid = a["agent_id"]
            output = merged.get(aid, {})
            name = output.get("agent_name", getattr(a.get("agent"), "agent_name", aid))
            status = output.get("status", "?")
            emoji = "✅" if status == "complete" else "❌" if status == "blocked" else "⏳"
            names.append(f"{emoji} {name}")
        await post_to_channel(channel_id, f"📋 **Recap** : {' | '.join(names)}", thread_id)

    # ── Auto-dispatch : le workflow engine decide s'il y a un groupe suivant ──
    if _depth >= MAX_CHAIN_DEPTH:
        logger.warning(f"[workflow] Max chain depth ({MAX_CHAIN_DEPTH}) reached, stopping auto-dispatch")
        await post_to_channel(channel_id, f"⚠️ Profondeur max atteinte ({MAX_CHAIN_DEPTH} groupes). Relancez si nécessaire.", thread_id)
        return

    try:
        from agents.shared.workflow_engine import get_agents_to_dispatch, can_transition
        team_id = state.get("_team_id", "team1")
        current_phase = state.get("project_phase", "discovery")

        # Verifier s'il y a de nouveaux agents a lancer (groupe B apres A, etc.)
        next_agents = get_agents_to_dispatch(current_phase, merged, team_id)
        if next_agents:
            # Resoudre les agents callables
            canonical_agents, _, _ = resolve_agents(channel_id)
            next_to_run = []
            for na in next_agents:
                aid = na["agent_id"]
                if aid in canonical_agents:
                    next_to_run.append({"agent_id": aid, "agent": canonical_agents[aid]})
                    logger.info(f"[workflow] Auto-dispatch: {aid} (group {na.get('parallel_group', '?')})")

            if next_to_run:
                for a in next_to_run:
                    bus.emit(Event("agent_dispatch", agent_id=a["agent_id"],
                                   thread_id=thread_id, team_id=team_id,
                                   data={"trigger": "workflow_auto", "depth": _depth + 1}))
                await post_to_channel(channel_id,
                    f"⚡ Workflow : groupe suivant → {', '.join(a['agent_id'] for a in next_to_run)}", thread_id)
                await run_agents_parallel(next_to_run, state, channel_id, thread_id, _depth + 1)
                return  # Le recursif gere la suite

        # Verifier si la phase est complete → proposer transition
        transition = can_transition(current_phase, merged, state.get("legal_alerts", []), team_id)
        if transition["allowed"]:
            next_phase = transition["next_phase"]
            needs_gate = transition.get("needs_human_gate", True)
            if needs_gate:
                await post_to_channel(channel_id,
                    f"🚦 **Phase {current_phase} complete !**\n"
                    f"Transition vers **{next_phase}** possible.\n"
                    f"Repondez `approve` pour continuer ou `revise` pour corriger.", thread_id)
            else:
                # Auto-transition
                state["project_phase"] = next_phase
                try:
                    graph.update_state(config, state)
                    logger.info(f"Auto-transition: {current_phase} → {next_phase}")
                except Exception:
                    pass
                bus.emit(Event("phase_transition", thread_id=thread_id, team_id=team_id,
                               data={"from_phase": current_phase, "to_phase": next_phase, "auto": True}))
                await post_to_channel(channel_id,
                    f"✅ Transition automatique : **{current_phase}** → **{next_phase}**", thread_id)

    except Exception as e:
        logger.warning(f"Workflow auto-dispatch error: {e}")


async def run_orchestrated(state, decisions, channel_id, thread_id="default", canonical_agents=None):
    if canonical_agents is None:
        canonical_agents, _, _ = resolve_agents(channel_id)
    agents = []
    for d in decisions:
        dtype = d.get("decision_type", "")
        for a in d.get("actions", []):
            if isinstance(a, dict):
                action = a.get("action", "")

                # Dispatch agent
                if action == "dispatch_agent":
                    t = a.get("target", "")
                    if t in canonical_agents:
                        agents.append({"agent_id": t, "agent": canonical_agents[t]})

                # Phase transition — mettre a jour le state
                if action == "human_gate" and dtype == "phase_transition":
                    from_phase = a.get("from_phase", state.get("project_phase", ""))
                    to_phase = a.get("to_phase", "")
                    if to_phase:
                        await post_to_channel(channel_id,
                            f"🚦 **HUMAN GATE** — {from_phase} → {to_phase}\n"
                            f"Repondez `approve` pour continuer ou `revise` pour corriger.", thread_id)

    if agents:
        await run_agents_parallel(agents, state, channel_id, thread_id)
    elif not any(d.get("decision_type") == "phase_transition" for d in decisions):
        await post_to_channel(channel_id, "Aucun agent dispatche.", thread_id)


# ── Outline auto-publish ─────────────────────
async def _maybe_publish_to_outline(state: dict, agent_id: str, output: dict):
    """Publish deliverables to Outline if auto-publish is enabled."""
    try:
        from agents.shared.outline_client import is_enabled, _auto_publish_enabled, publish_deliverable
        if not is_enabled():
            return
        deliverables = output.get("deliverables", {})
        if not deliverables:
            return
        thread_id = state.get("project_id", "default")
        team_id = state.get("_team_id", "default")
        phase = state.get("project_phase", "discovery")
        project_name = state.get("project_metadata", {}).get("name", "")
        for key, content in deliverables.items():
            if _auto_publish_enabled(key):
                result = await publish_deliverable(
                    thread_id=thread_id, team_id=team_id, agent_id=agent_id,
                    phase=phase, key=key, content=content, project_name=project_name,
                )
                if result:
                    logger.info(f"[outline] Auto-published {key} → {result.get('url', '')}")
    except ImportError:
        pass
    except Exception as e:
        logger.warning(f"[outline] Auto-publish error: {e}")


# ── Endpoints ────────────────────────────────
@app.get("/health")
async def health():
    return {"status": "ok", "service": "langgraph-multi-agent", "version": "0.6.0"}

@app.get("/status")
async def status():
    teams = get_all_team_ids()
    default_agents, _, _ = resolve_agents()
    return {
        "agents": list(default_agents) + ["orchestrator"],
        "total_agents": len(default_agents) + 1,
        "teams": teams,
    }


@app.get("/workflow/status/{thread_id}")
async def workflow_status(thread_id: str):
    """Retourne l'etat du workflow pour un thread donne."""
    from agents.shared.workflow_engine import get_workflow_status, can_transition
    try:
        graph = get_orchestrator_graph()
        config = {"configurable": {"thread_id": thread_id}}
        existing = graph.get_state(config)
        if not existing or not existing.values:
            return {"error": "Thread introuvable"}
        state = existing.values
        current_phase = state.get("project_phase", "discovery")
        agent_outputs = state.get("agent_outputs", {})
        wf_status = get_workflow_status(current_phase, agent_outputs)
        transition = can_transition(current_phase, agent_outputs, state.get("legal_alerts", []))
        wf_status["transition"] = transition
        return wf_status
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class ResetRequest(BaseModel):
    thread_id: str

@app.post("/reset")
async def reset(request: ResetRequest):
    """Purge le state d'un thread."""
    try:
        graph = get_orchestrator_graph()
        config = {"configurable": {"thread_id": request.thread_id}}
        # Ecraser avec un state vierge
        graph.update_state(config, new_state([], "default", "", "default"))
        logger.info(f"State reset for {request.thread_id}")
        return {"status": "ok", "thread_id": request.thread_id}
    except Exception as e:
        logger.error(f"Reset error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


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

        # Resoudre l'equipe pour ce channel
        canonical_agents, agent_map, team_id = resolve_agents(channel_id)
        logger.info(f"Team: {team_id} ({len(canonical_agents)} agents)")

        # ── Mode direct ──────────────────────
        if request.direct_agent:
            agent_id = request.direct_agent.lower().strip()
            if agent_id not in agent_map:
                return InvokeResponse(
                    output=f"Agent inconnu : {agent_id}\nDisponibles : {', '.join(canonical_agents.keys())}",
                    thread_id=request.thread_id)

            agent_callable = agent_map[agent_id]
            canonical_id = agent_id
            for cid, ca in canonical_agents.items():
                if ca is agent_callable:
                    canonical_id = cid; break

            state = load_or_create_state(request.thread_id, msgs, request.project_id, channel_id, team_id)

            # Trouver le nom lisible
            agent_display = getattr(agent_callable, "agent_name", canonical_id)

            bus.emit(Event("agent_dispatch", agent_id=canonical_id,
                           thread_id=request.thread_id, team_id=team_id,
                           data={"trigger": "direct", "task": msgs[0][1][:200] if msgs else ""}))
            background_tasks.add_task(
                run_agents_parallel,
                [{"agent_id": canonical_id, "agent": agent_callable}],
                state, channel_id, request.thread_id)

            existing = list(state.get("agent_outputs", {}).keys())
            ctx_info = f"\n📦 Contexte charge : {len(existing)} livrables" if existing else ""

            return InvokeResponse(
                output=f"⏳ **{agent_display}** travaille...{ctx_info}",
                thread_id=request.thread_id, agents_dispatched=[canonical_id])

        # ── Mode orchestrateur ───────────────
        state = load_or_create_state(request.thread_id, msgs, request.project_id, channel_id, team_id)

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
            background_tasks.add_task(run_orchestrated, result, decisions, channel_id, request.thread_id, canonical_agents)

        return InvokeResponse(
            output=output_text, thread_id=request.thread_id,
            decisions=decisions, agents_dispatched=agents_dispatched)

    except Exception as e:
        logger.error(f"Invoke error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/events")
async def get_events(n: int = 100, event_type: str = "", agent_id: str = "", thread_id: str = ""):
    """Retourne les derniers events du bus d'observabilite."""
    return {"events": bus.recent(n=min(n, 500), event_type=event_type,
                                 agent_id=agent_id, thread_id=thread_id)}


# ── API Keys CRUD ─────────────────────────────
class CreateKeyRequest(BaseModel):
    name: str
    teams: list[str] = ["*"]
    agents: list[str] = ["*"]
    scopes: list[str] = ["call_agent"]
    expires_at: str | None = None


@app.post("/api/keys")
async def create_api_key(req: CreateKeyRequest):
    """Generate a new MCP API key."""
    from agents.shared.mcp_auth import generate_token, db_register_key, token_preview
    try:
        token = generate_token(req.name, req.teams, req.agents, req.scopes, req.expires_at)
        db_register_key(token, req.name, req.teams, req.agents, req.scopes, req.expires_at)
        return {"token": token, "preview": token_preview(token), "name": req.name}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Create key error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/keys")
async def list_api_keys():
    """List all API keys (admin)."""
    from agents.shared.mcp_auth import db_list_keys
    try:
        return {"keys": db_list_keys()}
    except Exception as e:
        logger.error(f"List keys error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/keys/{key_hash}/revoke")
async def revoke_api_key(key_hash: str):
    """Revoke an API key."""
    from agents.shared.mcp_auth import db_revoke_key
    try:
        db_revoke_key(key_hash)
        return {"status": "revoked"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/keys/{key_hash}")
async def delete_api_key(key_hash: str):
    """Delete an API key permanently."""
    from agents.shared.mcp_auth import db_delete_key
    try:
        db_delete_key(key_hash)
        return {"status": "deleted"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Outline manual publish ────────────────────
class OutlinePublishRequest(BaseModel):
    thread_id: str
    team_id: str = "default"
    agent_id: str = ""
    phase: str = ""
    key: str = ""
    content: str = ""
    project_name: str = ""


@app.post("/outline/publish")
async def outline_publish(req: OutlinePublishRequest):
    """Manually publish a deliverable to Outline."""
    try:
        from agents.shared.outline_client import publish_deliverable, is_enabled
        if not is_enabled():
            raise HTTPException(status_code=400, detail="Outline integration is disabled")
        result = await publish_deliverable(
            thread_id=req.thread_id, team_id=req.team_id, agent_id=req.agent_id,
            phase=req.phase, key=req.key, content=req.content, project_name=req.project_name,
        )
        if result:
            return {"ok": True, **result}
        raise HTTPException(status_code=500, detail="Publication failed")
    except ImportError:
        raise HTTPException(status_code=500, detail="outline_client module not available")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── MCP SSE routes ────────────────────────────
try:
    from agents.shared.mcp_server import mount_mcp_routes
    mount_mcp_routes(app)
except Exception as e:
    logger.warning(f"MCP server mount failed: {e}")


@app.on_event("startup")
async def startup():
    # ── OpenLIT auto-instrumentation ──
    try:
        import openlit
        openlit.init(
            otlp_endpoint=os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://openlit:4318"),
            application_name="langgraph-api",
            environment=os.getenv("OPENLIT_ENV", "production"),
        )
        logger.info("OpenLIT instrumentation active")
    except ImportError:
        logger.info("OpenLIT SDK not installed — skipping auto-instrumentation")
    except Exception as e:
        logger.warning(f"OpenLIT init failed: {e}")

    try:
        get_orchestrator_graph()
        logger.info("Gateway v0.6.0 ready — persistence + direct + parallel + MCP")
    except Exception as e:
        logger.error(f"Init error: {e}")

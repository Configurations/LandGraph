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
        logger.info("ag.flow version: %s", open(_vp).read().strip())
        break
else:
    logger.info("ag.flow version: dev")

app = FastAPI(title="LangGraph Multi-Agent API", version="0.6.0")

from agents.shared.agent_loader import get_agents
from agents.shared.team_resolver import get_team_for_channel, get_all_team_ids
from agents.orchestrator import orchestrator_node, route_after_orchestrator
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer


def _default_team() -> str:
    """Return first configured team ID (avoids 'default' fallback errors)."""
    ids = get_all_team_ids()
    return ids[0] if ids else "team1"


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
    team_id = get_team_for_channel(channel_id) if channel_id else _default_team()
    return resolve_agents_by_team(team_id)


def resolve_agents_by_team(team_id: str):
    """Resout les agents pour un team_id explicite."""
    canonical = get_agents(team_id)
    agent_map = dict(canonical)
    for alias, cid in ALIASES.items():
        if cid in canonical:
            agent_map[alias] = canonical[cid]
    return canonical, agent_map, team_id


# ── Canal de communication ────────────────────
async def post_to_channel(channel_id, message, thread_id=""):
    """Envoie un message via le canal par defaut (Discord, Email, etc.).
    Si thread_id commence par 'hitl-chat-' ou 'onboarding-', ecrit en DB."""
    if not channel_id and not thread_id:
        return
    # Onboarding callback — store in dispatcher_task_events for HITL console
    if thread_id and thread_id.startswith("onboarding-"):
        try:
            conn = psycopg.connect(os.getenv("DATABASE_URI"), autocommit=True)
            try:
                with conn.cursor() as cur:
                    cur.execute("""
                        INSERT INTO project.dispatcher_task_events (task_id, event_type, data)
                        SELECT t.id, 'progress', %s::jsonb
                        FROM project.dispatcher_tasks t
                        WHERE t.thread_id = %s
                        ORDER BY t.created_at DESC LIMIT 1
                    """, (json.dumps({"data": str(message)[:4000]}), thread_id))
            finally:
                conn.close()
            logger.info(f"[onboarding] Saved event for {thread_id}")
            return
        except Exception as e:
            logger.error(f"[onboarding] Failed to save event: {e}")
    # HITL chat callback — store in hitl_chat_messages instead of channel
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
        serde = JsonPlusSerializer(
            allowed_msgpack_modules=[("agents.orchestrator", "DecisionType"),
                                     ("agents.orchestrator", "ActionType")]
        )
        CHECKPOINTER = PostgresSaver(DB_CONN, serde=serde)
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


def _read_project_language(project_slug):
    """Read language from .project file on disk."""
    if not project_slug:
        return "fr"
    ag_flow_root = os.environ.get("AG_FLOW_ROOT", "/root/ag.flow")
    dot_project = os.path.join(ag_flow_root, "projects", project_slug, ".project")
    try:
        if os.path.isfile(dot_project):
            with open(dot_project, encoding="utf-8") as f:
                for line in f:
                    if line.strip().startswith("language:"):
                        return line.split(":", 1)[1].strip()
    except Exception:
        pass
    return "fr"


def new_state(msgs, project_id, channel_id, team_id="", project_slug=""):
    lang = _read_project_language(project_slug)
    return {
        "messages": msgs,
        "project_id": project_id,
        "project_slug": project_slug,
        "project_phase": "discovery",
        "project_metadata": {"language": lang},
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


def load_or_create_state(thread_id, msgs, project_id, channel_id, team_id="", project_slug=""):
    """Charge le state existant ou en cree un nouveau. (sync — appeler via to_thread)"""
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
            # Update project_slug if provided (may be set later via HITL)
            if project_slug:
                state["project_slug"] = project_slug
            # Ensure language is set in project_metadata
            meta = state.get("project_metadata", {})
            if not meta.get("language"):
                meta["language"] = _read_project_language(project_slug or state.get("project_slug", ""))
                state["project_metadata"] = meta

            outputs = list(state.get("agent_outputs", {}).keys())
            logger.info(f"State loaded for {thread_id} — {len(outputs)} outputs: {outputs}")
            return state
    except Exception as e:
        logger.warning(f"Could not load state for {thread_id}: {e}")

    logger.info(f"New state for {thread_id}")
    return new_state(msgs, project_id, channel_id, team_id, project_slug)


async def load_or_create_state_async(thread_id, msgs, project_id, channel_id, team_id="", project_slug=""):
    """Async wrapper — ne bloque pas l'event loop."""
    return await asyncio.to_thread(
        load_or_create_state, thread_id, msgs, project_id, channel_id, team_id, project_slug)


# ── Background runners ───────────────────────
async def run_single_agent(agent_id, agent_callable, state, channel_id, thread_id=""):
    try:
        result = await asyncio.wait_for(
            asyncio.to_thread(agent_callable, dict(state)), timeout=2100)
        state["agent_outputs"] = result.get("agent_outputs", state.get("agent_outputs", {}))
        logger.info(f"[bg] {agent_id} done")
        # Persist agent output (base_agent already posts to channel)
        output = result.get("agent_outputs", {}).get(agent_id, {})
        if output and isinstance(output, dict):
            # Persist deliverable to filesystem
            await _persist_deliverable_to_fs(state, agent_id, output)
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


async def run_single_deliverable(deliv_info, state, channel_id, thread_id=""):
    """Run a single deliverable: inject _deliverable_dispatch and call the agent."""
    agent_id = deliv_info["agent_id"]
    agent_callable = deliv_info["agent"]
    step_key = deliv_info["step"]
    output_key = f"{agent_id}:{step_key}"
    try:
        local_state = dict(state)
        local_state["_deliverable_dispatch"] = {
            "step": step_key,
            "step_name": deliv_info.get("step_name", deliv_info.get("deliverable_key", step_key)),
            "instruction": deliv_info.get("instruction", ""),
        }
        result = await asyncio.wait_for(
            asyncio.to_thread(agent_callable, local_state), timeout=2100)
        state["agent_outputs"] = result.get("agent_outputs", state.get("agent_outputs", {}))
        logger.info(f"[bg] deliverable {output_key} done")
        output = result.get("agent_outputs", {}).get(output_key, {})
        if output and isinstance(output, dict):
            await _persist_deliverable_to_fs(state, output_key, output)
        return result
    except asyncio.TimeoutError:
        logger.error(f"[bg] deliverable {output_key} timeout")
        await post_to_channel(channel_id, f"⏰ **{output_key}** timeout (35min)", thread_id)
        return state
    except Exception as e:
        logger.error(f"[bg] deliverable {output_key} error: {e}")
        await post_to_channel(channel_id, f"❌ **{output_key}** erreur : {str(e)[:300]}", thread_id)
        return state


async def run_deliverables_parallel(deliverables_to_run, state, channel_id, thread_id="default", _depth=0):
    """Run deliverables in parallel, then auto-dispatch next group."""
    MAX_CHAIN_DEPTH = 5
    # Set disk check context so workflow_engine can skip already-produced deliverables
    from agents.shared.workflow_engine import set_disk_check_context
    slug = state.get("project_slug", "")
    if slug:
        set_disk_check_context(slug, state.get("_team_id", "team1"),
                               state.get("_workflow", "main"),
                               state.get("_iteration", 1),
                               state.get("project_phase", ""))
    tasks = [run_single_deliverable(d, dict(state), channel_id, thread_id) for d in deliverables_to_run]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    merged = dict(state.get("agent_outputs", {}))
    for r in results:
        if isinstance(r, dict) and "agent_outputs" in r:
            merged.update(r.get("agent_outputs", {}))

    state["agent_outputs"] = merged
    try:
        graph = get_orchestrator_graph()
        config = {"configurable": {"thread_id": thread_id}}
        await asyncio.to_thread(graph.update_state, config, state)
        logger.info(f"State saved for {thread_id} — {len(merged)} outputs")
    except Exception as e:
        logger.error(f"Could not save state for {thread_id}: {e}")

    # Recap
    if len(deliverables_to_run) > 1:
        names = []
        for d in deliverables_to_run:
            ok = f"{d['agent_id']}:{d['step']}"
            output = merged.get(ok, {})
            status = output.get("status", "?")
            emoji = "✅" if status == "complete" else "❌" if status == "blocked" else "⏳"
            names.append(f"{emoji} {ok}")
        await post_to_channel(channel_id, f"📋 **Recap livrables** : {' | '.join(names)}", thread_id)

    # Auto-dispatch next group
    if _depth >= MAX_CHAIN_DEPTH:
        logger.warning(f"[workflow] Max chain depth ({MAX_CHAIN_DEPTH}) reached")
        return

    try:
        from agents.shared.workflow_engine import get_deliverables_to_dispatch, can_transition
        team_id = state.get("_team_id", "team1")
        current_phase = state.get("project_phase", "discovery")

        next_deliverables = get_deliverables_to_dispatch(current_phase, merged, team_id)
        if next_deliverables:
            resolved = _resolve_deliverables(next_deliverables, team_id, channel_id)
            if resolved:
                for d in resolved:
                    bus.emit(Event("agent_dispatch", agent_id=f"{d['agent_id']}:{d['step']}",
                                    thread_id=thread_id, team_id=team_id,
                                    data={"trigger": "workflow_auto", "depth": _depth + 1}))
                await post_to_channel(channel_id,
                    f"⚡ Workflow : livrables suivants → {', '.join(d['agent_id'] + ':' + d['step'] for d in resolved)}", thread_id)
                await run_deliverables_parallel(resolved, state, channel_id, thread_id, _depth + 1)
                return

        # Generate synthesis when phase complete
        await _maybe_generate_synthesis(state, current_phase, merged)

        # Check phase completion
        transition = can_transition(current_phase, merged, state.get("legal_alerts", []), team_id)
        if transition["allowed"]:
            next_phase = transition["next_phase"]
            needs_gate = transition.get("needs_human_gate", True)
            if needs_gate:
                await post_to_channel(channel_id,
                    f"🚦 **Phase {current_phase} complete !**\nTransition vers **{next_phase}** possible.", thread_id)
                await _create_hitl_phase_request(
                    thread_id, team_id, current_phase, next_phase, merged)
            else:
                state["project_phase"] = next_phase
                try:
                    await asyncio.to_thread(graph.update_state, config, state)
                except Exception:
                    pass
                bus.emit(Event("phase_transition", thread_id=thread_id, team_id=team_id,
                               data={"from_phase": current_phase, "to_phase": next_phase, "auto": True}))
                await post_to_channel(channel_id,
                    f"✅ Transition automatique : **{current_phase}** → **{next_phase}**", thread_id)

    except Exception as e:
        logger.warning(f"Deliverable auto-dispatch error: {e}")


def _resolve_deliverables(deliverable_specs, team_id, channel_id):
    """Resolve deliverable specs to runnable dicts with agent instances and instructions."""
    from agents.shared.agent_loader import get_step_instruction
    canonical_agents, _, _ = resolve_agents(channel_id)
    resolved = []
    for spec in deliverable_specs:
        aid = spec["agent_id"]
        if aid not in canonical_agents:
            logger.warning(f"Agent {aid} not found for deliverable {spec['deliverable_key']}")
            continue
        instruction = get_step_instruction(aid, spec["step"], team_id)
        if not instruction:
            instruction = spec.get("description", "")
        # Get step name from registry
        step_name = spec.get("description", spec["step"])
        from agents.shared.team_resolver import load_team_json
        registry = load_team_json(team_id, "agents_registry.json") or {}
        for s in registry.get("agents", {}).get(aid, {}).get("steps", []):
            if s.get("output_key") == spec["step"]:
                step_name = s.get("name", step_name)
                break
        resolved.append({
            "deliverable_key": spec["deliverable_key"],
            "agent_id": aid,
            "step": spec["step"],
            "agent": canonical_agents[aid],
            "instruction": instruction,
            "step_name": step_name,
        })
    return resolved


async def run_agents_parallel(agents_to_run, state, channel_id, thread_id="default", _depth=0):
    MAX_CHAIN_DEPTH = 5  # max groupes enchaines automatiquement
    # Set disk check context for workflow_engine
    from agents.shared.workflow_engine import set_disk_check_context
    slug = state.get("project_slug", "")
    if slug:
        set_disk_check_context(slug, state.get("_team_id", "team1"),
                               state.get("_workflow", "main"),
                               state.get("_iteration", 1),
                               state.get("project_phase", ""))
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
        await asyncio.to_thread(graph.update_state, config, state)
        logger.info(f"State saved for {thread_id} — {len(merged)} outputs: {list(merged.keys())}")
    except Exception as e:
        logger.error(f"Could not save state for {thread_id}: {e}")

    # Sync issue statuses with workflow
    await _sync_issues_with_workflow(state, agents_to_run, merged)

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
        from agents.shared.workflow_engine import get_deliverables_to_dispatch, can_transition
        team_id = state.get("_team_id", "team1")
        current_phase = state.get("project_phase", "discovery")

        # Try deliverable-based dispatch first (new flow)
        next_deliverables = get_deliverables_to_dispatch(current_phase, merged, team_id)
        if next_deliverables:
            resolved = _resolve_deliverables(next_deliverables, team_id, channel_id)
            if resolved:
                await post_to_channel(channel_id,
                    f"⚡ Workflow : livrables suivants → {', '.join(d['agent_id'] + ':' + d['step'] for d in resolved)}", thread_id)
                await run_deliverables_parallel(resolved, state, channel_id, thread_id, _depth + 1)
                return

        # Generate _synthesis.md when phase is complete
        await _maybe_generate_synthesis(state, current_phase, merged)

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
                # Insert HITL request for the web console
                await _create_hitl_phase_request(
                    thread_id, team_id, current_phase, next_phase, merged)
            else:
                # Auto-transition
                state["project_phase"] = next_phase
                try:
                    await asyncio.to_thread(graph.update_state, config, state)
                    logger.info(f"Auto-transition: {current_phase} → {next_phase}")
                except Exception:
                    pass
                bus.emit(Event("phase_transition", thread_id=thread_id, team_id=team_id,
                               data={"from_phase": current_phase, "to_phase": next_phase, "auto": True}))
                await post_to_channel(channel_id,
                    f"✅ Transition automatique : **{current_phase}** → **{next_phase}**", thread_id)

    except Exception as e:
        logger.warning(f"Workflow auto-dispatch error: {e}")


async def _create_hitl_phase_request(thread_id: str, team_id: str,
                                      current_phase: str, next_phase: str,
                                      agent_outputs: dict):
    """Insert a phase validation request into hitl_requests for the HITL console."""
    try:
        uri = os.getenv("DATABASE_URI")
        if not uri:
            return
        # Build deliverables summary from agent outputs
        deliverables = {}
        for agent_id, output in agent_outputs.items():
            if isinstance(output, dict):
                deliverables[agent_id] = {
                    k: v for k, v in output.items()
                    if k not in ("status", "confidence", "agent_id")
                }
            elif isinstance(output, str):
                deliverables[agent_id] = output[:2000]

        context = {
            "type": "phase_validation",
            "current_phase": current_phase,
            "next_phase": next_phase,
            "deliverables": deliverables,
        }
        prompt = (f"Phase '{current_phase}' terminée. "
                  f"Validez-vous la transition vers '{next_phase}' ?")

        with psycopg.connect(uri, autocommit=True) as conn:
            with conn.cursor() as cur:
                # Check for existing pending phase_validation for this thread
                cur.execute("""
                    SELECT id FROM project.hitl_requests
                    WHERE thread_id = %s AND status = 'pending'
                      AND context::text LIKE '%%"type": "phase_validation"%%'
                    LIMIT 1
                """, (thread_id,))
                if cur.fetchone():
                    logger.info(f"[hitl] Phase validation already pending for {thread_id}, skipping")
                    return
                cur.execute("""
                    INSERT INTO project.hitl_requests
                    (thread_id, agent_id, team_id, request_type, prompt, context, channel, status)
                    VALUES (%s, %s, %s, 'approval', %s, %s::jsonb, 'web', 'pending')
                """, (thread_id, "orchestrator", team_id, prompt, json.dumps(context)))
        logger.info(f"[hitl] Phase validation request created: {current_phase} → {next_phase}")
        bus.emit(Event("human_gate_requested", agent_id="orchestrator",
                        thread_id=thread_id, team_id=team_id,
                        data={"phase": current_phase, "next_phase": next_phase}))
    except Exception as e:
        logger.warning(f"[hitl] Failed to create phase validation request: {e}")


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


# ── Phase synthesis generation ────────────────
async def _maybe_generate_synthesis(state: dict, phase: str, agent_outputs: dict):
    """Generate _synthesis.md for the phase if project_slug is set and phase has deliverables."""
    slug = state.get("project_slug", "")
    if not slug:
        return
    try:
        from agents.shared.project_store import read_synthesis, write_synthesis, _phase_dir, _legacy_deliverables_dir
        team_id = state.get("_team_id", "team1")
        workflow = state.get("_workflow", "main")
        iteration = state.get("_iteration")
        # Skip if synthesis already exists for this phase
        if read_synthesis(slug, phase, team_id=team_id, workflow=workflow, iteration=iteration):
            return
        # Collect all deliverables for this phase (new structure + legacy fallback)
        phase_deliverables = {}
        from agents.shared.project_store import get_current_iteration
        it = iteration or get_current_iteration(slug, team_id, workflow, phase)
        phase_path = _phase_dir(slug, team_id, workflow, it, phase)
        # New structure: walk agent subdirectories
        if os.path.isdir(phase_path):
            for agent_dir_name in os.listdir(phase_path):
                agent_path = os.path.join(phase_path, agent_dir_name)
                if os.path.isdir(agent_path):
                    for fname in os.listdir(agent_path):
                        if fname.endswith(".md"):
                            fpath = os.path.join(agent_path, fname)
                            try:
                                with open(fpath, "r", encoding="utf-8") as f:
                                    phase_deliverables[f"{agent_dir_name}/{fname[:-3]}"] = f.read()
                            except Exception:
                                pass
        # Legacy fallback
        if not phase_deliverables:
            legacy_dir = _legacy_deliverables_dir(slug, phase)
            if os.path.isdir(legacy_dir):
                for fname in os.listdir(legacy_dir):
                    if fname.endswith(".md") and not fname.startswith("_"):
                        fpath = os.path.join(legacy_dir, fname)
                        try:
                            with open(fpath, "r", encoding="utf-8") as f:
                                phase_deliverables[fname[:-3]] = f.read()
                        except Exception:
                            pass
        if not phase_deliverables:
            return
        # Use LLM to generate synthesis
        synthesis = await asyncio.to_thread(_generate_synthesis_llm, phase, phase_deliverables)
        if synthesis:
            write_synthesis(slug, phase, synthesis, team_id=team_id, workflow=workflow, iteration=iteration)
            logger.info(f"[synthesis] Generated _synthesis.md for {slug}/{phase}")
    except Exception as e:
        logger.warning(f"[synthesis] Error generating synthesis for {phase}: {e}")


def _generate_synthesis_llm(phase: str, deliverables: dict) -> str:
    """Call LLM to condense phase deliverables into a synthesis."""
    try:
        from agents.shared.llm_provider import create_llm
        from agents.shared.rate_limiter import throttled_invoke
        llm = create_llm(provider_name=None, temperature=0.2, max_tokens=4096)
        content = ""
        for agent_id, text in deliverables.items():
            content += f"\n\n## {agent_id}\n\n{text[:8000]}"
        msgs = [
            {"role": "system", "content": (
                "Tu es un synthetiseur de projet. Condense les livrables de la phase en une synthese "
                "structuree et actionnable. Garde les decisions cles, les contraintes, les risques, "
                "et les recommandations. Format Markdown. Sois concis mais complet."
            )},
            {"role": "user", "content": (
                f"Phase: {phase}\n\nLivrables des agents:\n{content}\n\n"
                "Produis une synthese structuree de cette phase."
            )},
        ]
        result = throttled_invoke(llm, msgs)
        return result.content if isinstance(result.content, str) else str(result.content)
    except Exception as e:
        logger.error(f"[synthesis] LLM call failed: {e}")
        # Fallback: concatenate without LLM
        lines = [f"# Synthese — {phase}\n"]
        for agent_id, text in deliverables.items():
            lines.append(f"## {agent_id}\n\n{text[:4000]}\n")
        return "\n".join(lines)


# ── Filesystem deliverable persistence ────────
async def _sync_issues_with_workflow(state: dict, agents_to_run: list, merged: dict):
    """Sync PM issue statuses based on workflow agent activity."""
    try:
        raw_pid = state.get("project_id", "")
        # Extract numeric PM project ID from "pm-team1-3" format
        if not raw_pid or not raw_pid.startswith("pm-"):
            return
        parts = raw_pid.split("-")
        if len(parts) < 3:
            return
        try:
            project_id = int(parts[-1])
        except ValueError:
            return
        phase = state.get("project_phase", "discovery")
        agents_running = [a["agent_id"] for a in agents_to_run
                          if merged.get(a["agent_id"], {}).get("status") not in ("complete", "blocked", "error")]
        agents_done = [a["agent_id"] for a in agents_to_run
                       if merged.get(a["agent_id"], {}).get("status") == "complete"]
        hitl_url = os.environ.get("HITL_URL", "http://langgraph-hitl:8090")
        import httpx
        async with httpx.AsyncClient(timeout=5) as client:
            await client.post(f"{hitl_url}/api/pm/sync-workflow", json={
                "project_id": project_id,
                "phase": phase,
                "agents_running": agents_running,
                "agents_done": agents_done,
            }, headers={"Authorization": f"Bearer {_get_internal_token()}"})
    except Exception as e:
        logger.debug(f"[sync] Issue sync skipped: {e}")


def _get_internal_token():
    """Generate a minimal internal JWT for service-to-service calls."""
    import jwt, hashlib
    raw = os.environ.get("HITL_JWT_SECRET", os.environ.get("MCP_SECRET", "dev"))
    # Ensure key is at least 32 bytes for HS256 (RFC 7518 §3.2)
    secret = raw if len(raw) >= 32 else hashlib.sha256(raw.encode()).hexdigest()
    return jwt.encode({"sub": "system", "email": "system@internal", "role": "admin", "teams": []}, secret, algorithm="HS256")


async def _persist_deliverable_to_fs(state: dict, agent_id: str, output: dict):
    """Write agent deliverable to filesystem and index in pgvector."""
    try:
        slug = state.get("project_slug", "")
        if not slug:
            return
        phase = state.get("project_phase", "discovery")
        team_id = state.get("_team_id", "team1")
        workflow = state.get("_workflow", "main")
        iteration = state.get("_iteration")
        from agents.shared.project_store import persist_deliverable
        await asyncio.to_thread(persist_deliverable, slug, phase, agent_id, output,
                                team_id=team_id, workflow=workflow, iteration=iteration)
        # Index in pgvector (non-blocking, best-effort)
        await _index_in_rag(state, agent_id, output)
    except Exception as e:
        logger.warning(f"[project_store] Persist error: {e}")


# ── pgvector RAG indexing ─────────────────────
async def _index_in_rag(state: dict, agent_id: str, output: dict):
    """Index deliverable chunks in pgvector for semantic search."""
    try:
        from agents.shared.rag_service import index_document, DocumentMetadata
        deliverables = output.get("deliverables", {})
        if not deliverables:
            text = output.get("deliverable", output.get("summary", ""))
            if text:
                deliverables = {"deliverable": text}
            else:
                return
        phase = state.get("project_phase", "discovery")
        project_name = state.get("project_metadata", {}).get("name", state.get("project_slug", ""))
        # Concatenate all deliverables into one document for indexing
        content_parts = []
        for key, val in deliverables.items():
            content_parts.append(f"## {key}\n\n{str(val)}")
        content = "\n\n".join(content_parts)
        meta = DocumentMetadata(
            source_type="deliverable",
            source_agent=agent_id,
            project_name=project_name,
            phase=phase,
            language=state.get("project_metadata", {}).get("language", "fr"),
        )
        chunks = await asyncio.to_thread(index_document, content, meta)
        if chunks:
            logger.info(f"[rag] Indexed {chunks} chunks for {agent_id}/{phase}")
    except ImportError:
        pass  # rag_service deps not installed
    except Exception as e:
        logger.warning(f"[rag] Index error for {agent_id}: {e}")


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
        thread_id = state.get("project_id", "")
        team_id = state.get("_team_id", "") or _default_team()
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


class PhaseTransitionRequest(BaseModel):
    thread_id: str
    from_phase: str
    to_phase: str


@app.post("/workflow/transition")
async def workflow_transition(req: PhaseTransitionRequest, background_tasks: BackgroundTasks):
    """Transition de phase declenchee par la console HITL apres approbation humaine."""
    try:
        graph = get_orchestrator_graph()
        config = {"configurable": {"thread_id": req.thread_id}}
        existing = await asyncio.to_thread(graph.get_state, config)
        if not existing or not existing.values:
            raise HTTPException(404, "Thread introuvable")
        state = existing.values
        current = state.get("project_phase", "")
        if current != req.from_phase:
            raise HTTPException(400, f"Phase actuelle est '{current}', pas '{req.from_phase}'")
        state["project_phase"] = req.to_phase
        await asyncio.to_thread(graph.update_state, config, state)
        logger.info(f"Phase transition (HITL approved): {req.from_phase} → {req.to_phase}")
        bus.emit(Event("phase_transition", thread_id=req.thread_id,
                        team_id=state.get("_team_id", _default_team()),
                        data={"from_phase": req.from_phase, "to_phase": req.to_phase,
                              "source": "hitl_console"}))

        # Create empty phase directory for next phase
        team_id = state.get("_team_id", _default_team())
        slug = state.get("project_slug", "")
        if slug:
            try:
                from agents.shared.project_store import _phase_dir, get_current_iteration, start_new_iteration
                workflow = state.get("_workflow", "main")
                iteration = start_new_iteration(slug, team_id, workflow, req.to_phase)
                state["_iteration"] = iteration
                phase_path = _phase_dir(slug, team_id, workflow, iteration, req.to_phase)
                os.makedirs(phase_path, exist_ok=True)
                logger.info(f"Created phase dir: {phase_path}")
                await asyncio.to_thread(graph.update_state, config, state)
            except Exception as e:
                logger.warning(f"Could not create phase dir: {e}")

        # Auto-dispatch deliverables for next phase
        channel_id = state.get("_channel_id", "")
        merged = state.get("agent_outputs", {})
        from agents.shared.workflow_engine import get_deliverables_to_dispatch
        next_deliverables = get_deliverables_to_dispatch(req.to_phase, merged, team_id)
        if next_deliverables:
            resolved = _resolve_deliverables(next_deliverables, team_id, channel_id)
            if resolved:
                background_tasks.add_task(
                    run_deliverables_parallel, resolved, state, channel_id, req.thread_id)
                logger.info(f"Auto-dispatching {req.to_phase} deliverables: {[d['deliverable_key'] for d in next_deliverables]}")

        return {"ok": True, "from_phase": req.from_phase, "to_phase": req.to_phase}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, str(e))


@app.get("/workflow/status/{thread_id}")
async def workflow_status(thread_id: str):
    """Retourne l'etat du workflow pour un thread donne."""
    from agents.shared.workflow_engine import get_workflow_status, can_transition
    try:
        graph = get_orchestrator_graph()
        config = {"configurable": {"thread_id": thread_id}}
        existing = await asyncio.to_thread(graph.get_state, config)
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


@app.get("/workflow/deliverables/{thread_id}")
async def workflow_deliverables(thread_id: str):
    """Retourne les livrables (agent_outputs) d'un thread."""
    try:
        graph = get_orchestrator_graph()
        config = {"configurable": {"thread_id": thread_id}}
        existing = await asyncio.to_thread(graph.get_state, config)
        if not existing or not existing.values:
            return {"error": "Thread introuvable"}
        state = existing.values
        outputs = state.get("agent_outputs", {})
        return {
            "thread_id": thread_id,
            "phase": state.get("project_phase", "discovery"),
            "project_name": state.get("project_metadata", {}).get("name", ""),
            "deliverables": {
                agent_id: {
                    "agent_name": out.get("agent_name", agent_id) if isinstance(out, dict) else agent_id,
                    "status": out.get("status", "unknown") if isinstance(out, dict) else "complete",
                    "confidence": out.get("confidence", 0) if isinstance(out, dict) else 0,
                    "timestamp": out.get("timestamp", "") if isinstance(out, dict) else "",
                    "content": out.get("deliverables", out) if isinstance(out, dict) else out,
                }
                for agent_id, out in outputs.items()
            },
        }
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
        await asyncio.to_thread(graph.update_state, config, new_state([], "", "", _default_team()))
        logger.info(f"State reset for {request.thread_id}")
        return {"status": "ok", "thread_id": request.thread_id}
    except Exception as e:
        logger.error(f"Reset error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/reload-config")
async def reload_config():
    """Reload agents and workflow from disk (clear caches)."""
    from agents.shared.agent_loader import reload_agents
    from agents.shared.workflow_engine import reload_workflow
    reload_agents()
    reload_workflow()
    logger.info("Config reloaded (agents + workflow caches cleared)")
    return {"ok": True}


class PhaseResetRequest(BaseModel):
    thread_id: str
    phase: str

class CheckPhaseRequest(BaseModel):
    thread_id: str
    phase: str
    team_id: str = "team1"


@app.post("/workflow/check-phase")
async def check_phase(request: CheckPhaseRequest, background_tasks: BackgroundTasks):
    """Check if all required deliverables are validated. If so, propose phase transition."""
    try:
        graph = get_orchestrator_graph()
        config = {"configurable": {"thread_id": request.thread_id}}
        existing = await asyncio.to_thread(graph.get_state, config)
        if not existing or not existing.values:
            raise HTTPException(404, "Thread introuvable")
        state = existing.values
        current_phase = state.get("project_phase", "")
        if current_phase != request.phase:
            return {"ok": True, "action": "none", "reason": f"Phase actuelle est '{current_phase}', pas '{request.phase}'"}

        merged = state.get("agent_outputs", {})
        team_id = request.team_id or state.get("_team_id", _default_team())

        from agents.shared.workflow_engine import can_transition, get_deliverables_to_dispatch
        # Check if there are still deliverables to dispatch
        pending = get_deliverables_to_dispatch(current_phase, merged, team_id)
        if pending:
            return {"ok": True, "action": "none", "reason": f"{len(pending)} livrable(s) encore a produire"}

        transition = can_transition(current_phase, merged, state.get("legal_alerts", []), team_id)
        if not transition["allowed"]:
            return {"ok": True, "action": "none", "reason": transition.get("reason", "Phase pas complete")}

        next_phase = transition["next_phase"]
        needs_gate = transition.get("needs_human_gate", True)
        channel_id = state.get("_channel_id", "")

        if needs_gate:
            await _create_hitl_phase_request(
                request.thread_id, team_id, current_phase, next_phase, merged)
            await post_to_channel(channel_id,
                f"🚦 **Phase {current_phase} complete !** Transition vers **{next_phase}** possible.", request.thread_id)
            return {"ok": True, "action": "phase_gate", "current": current_phase, "next": next_phase}
        else:
            state["project_phase"] = next_phase
            await asyncio.to_thread(graph.update_state, config, state)
            bus.emit(Event("phase_transition", thread_id=request.thread_id, team_id=team_id,
                           data={"from_phase": current_phase, "to_phase": next_phase, "auto": True}))
            await post_to_channel(channel_id,
                f"✅ Transition automatique : **{current_phase}** → **{next_phase}**", request.thread_id)
            return {"ok": True, "action": "auto_transition", "current": current_phase, "next": next_phase}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, str(e))


@app.post("/workflow/reset-phase")
async def reset_phase(request: PhaseResetRequest):
    """Reset workflow state to a given phase, clearing outputs from that phase onward."""
    phase_order = ["discovery", "design", "build", "ship", "iterate"]
    try:
        phase_idx = phase_order.index(request.phase)
    except ValueError:
        raise HTTPException(400, f"Unknown phase: {request.phase}")
    try:
        graph = get_orchestrator_graph()
        config = {"configurable": {"thread_id": request.thread_id}}
        existing = await asyncio.to_thread(graph.get_state, config)
        if not existing or not existing.values:
            raise HTTPException(404, "Thread not found")
        state = existing.values
        # Remove agent_outputs for reset phases
        from agents.shared.workflow_engine import load_workflow
        team_id = state.get("_team_id", _default_team())
        wf = load_workflow(team_id)
        phases_to_clear = phase_order[phase_idx:]
        # Build set of deliverable keys (agent_id:step) belonging to phases being reset
        deliverable_keys_to_clear = set()
        agents_only_in_cleared = set()  # agents that appear ONLY in cleared phases
        agents_in_kept = set()  # agents that appear in kept phases
        for pid in phase_order:
            pconf = wf.get("phases", {}).get(pid, {})
            phase_agents = set(pconf.get("agents", {}).keys())
            if pid in phases_to_clear:
                for deliv_name, deliv_conf in pconf.get("deliverables", {}).items():
                    agent_id = deliv_conf.get("agent", "")
                    deliverable_keys_to_clear.add(f"{agent_id}:{deliv_name}")
                agents_only_in_cleared.update(phase_agents)
            else:
                agents_in_kept.update(phase_agents)
        # Agents shared with kept phases should NOT have legacy keys removed
        agents_only_in_cleared -= agents_in_kept
        outputs = state.get("agent_outputs", {})
        keys_to_remove = []
        for key in outputs:
            if ":" in key:
                # New format (agent_id:step) — only remove if deliverable belongs to a cleared phase
                if key in deliverable_keys_to_clear:
                    keys_to_remove.append(key)
            else:
                # Legacy format (agent_id only) — only remove if agent is NOT shared with a kept phase
                if key in agents_only_in_cleared:
                    keys_to_remove.append(key)
        for key in keys_to_remove:
            outputs.pop(key, None)
        state["agent_outputs"] = outputs
        state["project_phase"] = request.phase
        await asyncio.to_thread(graph.update_state, config, state)
        logger.info(f"Phase reset to {request.phase} for {request.thread_id} — cleared {len(keys_to_remove)} outputs: {keys_to_remove}")
        return {"ok": True, "phase": request.phase, "cleared_outputs": keys_to_remove}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, str(e))


class InvokeRequest(BaseModel):
    messages: list[dict]
    thread_id: str = ""
    project_id: str = ""
    project_slug: str = ""
    channel_id: str = ""
    team_id: str = ""
    direct_agent: str = ""
    deliverable_step: str = ""  # If set, run only this step (for remark re-invocation)
    system_prompt: str = ""  # Optional system prompt injected by HITL chat

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
        if request.system_prompt:
            msgs.insert(0, ("system", request.system_prompt))

        # Resoudre l'equipe pour ce channel (ou team_id explicite)
        if request.team_id:
            canonical_agents, agent_map, team_id = resolve_agents_by_team(request.team_id)
        else:
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

            state = await load_or_create_state_async(request.thread_id, msgs, request.project_id, channel_id, team_id, request.project_slug)

            # Trouver le nom lisible
            agent_display = getattr(agent_callable, "agent_name", canonical_id)

            bus.emit(Event("agent_dispatch", agent_id=canonical_id,
                           thread_id=request.thread_id, team_id=team_id,
                           data={"trigger": "direct", "task": msgs[0][1][:200] if msgs else ""}))

            if request.deliverable_step:
                # Remark re-invocation: run single deliverable step with the message as instruction
                task_msg = msgs[0][1] if msgs else ""
                deliverable_info = {
                    "deliverable_key": request.deliverable_step,
                    "agent_id": canonical_id,
                    "step": request.deliverable_step,
                    "agent": agent_callable,
                    "instruction": task_msg,
                    "step_name": request.deliverable_step,
                }
                background_tasks.add_task(
                    run_deliverables_parallel,
                    [deliverable_info], state, channel_id, request.thread_id)
            else:
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
        state = await load_or_create_state_async(request.thread_id, msgs, request.project_id, channel_id, team_id, request.project_slug)

        graph = get_orchestrator_graph()
        config = {"configurable": {"thread_id": request.thread_id}}
        result = await asyncio.to_thread(graph.invoke, state, config)

        all_decisions = result.get("decision_history", [])
        # Only act on the LAST decision (current invoke), not the full history
        decisions = all_decisions[-1:] if all_decisions else []

        agents_dispatched = []
        output_parts = []

        existing_outputs = list(result.get("agent_outputs", {}).keys())
        if existing_outputs:
            output_parts.append(f"📦 Contexte charge : {', '.join(existing_outputs)}")

        for i, d in enumerate(decisions, 1):
            dtype = d.get("decision_type", "unknown")
            conf = d.get("confidence", 0)
            reasoning = d.get("reasoning", "")[:200]
            output_parts.append(f"**Decision** : {dtype} (confiance: {conf})\n{reasoning}")
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
    team_id: str = ""
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
    # ── Langfuse observability ──
    try:
        from agents.shared.langfuse_setup import init_langfuse
        init_langfuse()
    except Exception as e:
        logger.warning(f"Langfuse init failed: {e}")

    try:
        get_orchestrator_graph()
        logger.info("Gateway v0.6.0 ready — persistence + direct + parallel + MCP")
    except Exception as e:
        logger.error(f"Init error: {e}")

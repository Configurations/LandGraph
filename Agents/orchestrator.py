"""
Orchestrateur (Meta-Agent PM) — Agent LangGraph Production
══════════════════════════════════════════════════════════

Cerveau central du systeme multi-agent. Route les taches, gere le cycle
de vie projet, decide quand impliquer l'humain via Discord.

Ne fait JAMAIS le travail d'un agent. Route, decide, coordonne.
"""

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, Optional

import psycopg
from dotenv import load_dotenv
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
from langgraph.checkpoint.postgres import PostgresSaver

load_dotenv()

logger = logging.getLogger("orchestrator")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s %(message)s")


# ══════════════════════════════════════════════
# CONFIGURATION — depuis agents_registry.json
# ══════════════════════════════════════════════

def _load_orchestrator_config(team_id: str = "") -> dict:
    """Charge la config de l'orchestrateur depuis le registry de l'equipe."""
    from agents.shared.team_resolver import load_team_json, get_team_info
    if not team_id:
        from agents.shared.team_resolver import get_teams_config
        teams = get_teams_config().get("teams", [])
        team_id = teams[0]["id"] if teams else ""
    # Get orchestrator ID from teams.json
    orch_id = get_team_info(team_id).get("orchestrator", "")
    registry = load_team_json(team_id, "agents_registry.json")
    # Lookup by ID first, fallback to type search
    conf = registry.get("agents", {}).get(orch_id, {}) if orch_id else {}
    if not conf:
        for aid, acfg in registry.get("agents", {}).items():
            if acfg.get("type") == "orchestrator":
                conf = acfg
                break
    if conf:
        logger.info("Orchestrator config [%s]: llm=%s", team_id, conf.get("llm", "default"))
    return conf

_orch_config = _load_orchestrator_config()

CONFIG = {
    "llm": _orch_config.get("llm", ""),
    "model": os.getenv("ORCHESTRATOR_MODEL", _orch_config.get("model", "claude-sonnet-4-5-20250929")),
    "temperature": float(os.getenv("ORCHESTRATOR_TEMPERATURE", str(_orch_config.get("temperature", 0.2)))),
    "max_tokens": int(os.getenv("ORCHESTRATOR_MAX_TOKENS", str(_orch_config.get("max_tokens", 4096)))),
}


def _load_agent_ids(team_id: str = "") -> list[str]:
    """Charge la liste des agents depuis le registry de l'equipe (hors orchestrator)."""
    from agents.shared.team_resolver import load_team_json
    registry = load_team_json(team_id, "agents_registry.json")
    return [aid for aid, cfg in registry.get("agents", {}).items() if cfg.get("type") != "orchestrator"]


# ══════════════════════════════════════════════
# SYSTEM PROMPT
# ══════════════════════════════════════════════

def load_system_prompt(team_id: str = "") -> str:
    """Charge le system prompt depuis le dossier de l'equipe. Pas de cache : le prompt
    est recalcule a chaque phase (il integre le contexte workflow courant)."""
    from agents.shared.team_resolver import find_team_file
    prompt_file = _orch_config.get("prompt", "orchestrator.md")
    path = find_team_file(team_id, prompt_file)
    if not path:
        raise FileNotFoundError(
            f"Prompt orchestrateur obligatoire : '{prompt_file}' introuvable "
            f"pour l'equipe '{team_id}'. Verifiez config/{team_id}/{prompt_file}."
        )
    logger.info(f"Orchestrator prompt [{team_id}]: {path}")
    with open(path, "r") as f:
        return f.read()


# ══════════════════════════════════════════════
# LLM
# ══════════════════════════════════════════════

def get_llm():
    from agents.shared.llm_provider import create_llm
    return create_llm(
        provider_name=CONFIG["llm"] or None,
        temperature=CONFIG["temperature"],
        max_tokens=CONFIG["max_tokens"],
    )


# ══════════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════════


def detect_loop(history: list[dict], agent_id: str, max_loops: int = 3) -> bool:
    """Detecte si un agent est dispatche en boucle sans progres."""
    recent = [
        d for d in history[-20:]
        if any(
            a.get("target") == agent_id
            for a in d.get("actions", [])
            if a.get("action") == "dispatch_agent"
        )
    ]
    return len(recent) >= max_loops


def has_critical_legal_alert(alerts: list[dict]) -> bool:
    """Verifie s'il y a une alerte juridique critique non resolue."""
    return any(
        a.get("level") == "critical" and not a.get("resolved", False)
        for a in alerts
    )



def _load_context_template(team_id: str, filename: str) -> str:
    """Load a context template from Models/{culture}/ via team_resolver."""
    culture = os.getenv("CULTURE", "fr-fr")
    # Try config/Models/{culture}/ first, then Shared/Models/{culture}/
    for base in ["/app/config", "/app/Shared", "config", "Shared"]:
        path = os.path.join(base, "Models", culture, filename)
        if os.path.isfile(path):
            with open(path, "r", encoding="utf-8") as f:
                return f.read()
    logger.warning("Context template not found: %s/%s", culture, filename)
    return ""


# ══════════════════════════════════════════════
# STATE DEFINITION
# ══════════════════════════════════════════════

from typing import TypedDict, Annotated


class ProjectState(TypedDict, total=False):
    # Messages (LangGraph managed)
    messages: Annotated[list, add_messages]

    # Projet
    project_id: str
    project_phase: str
    project_metadata: dict

    # Outputs des agents
    agent_outputs: dict  # {livrable_id: {status, content, agent, timestamp}}

    # Orchestrateur
    current_assignments: dict  # {agent_id: task}
    decision_history: list  # Liste des decisions (tool_calls, output, agents_dispatched)
    blockers: list  # Blocages actifs

    # Juridique
    legal_alerts: list  # Alertes de l'avocat

    # QA
    qa_verdict: dict  # {status: go/no_go, details}

    # DevOps
    deploy_status: dict  # {environment, status, url}

    # Routing (injected by gateway)
    _team_id: str
    _discord_channel_id: str
    _project_slug: str

    # Humain
    human_feedback_log: list  # Reponses aux human gates

    # Discord
    notifications_log: list  # Trace des notifications envoyees


# ══════════════════════════════════════════════
# ORCHESTRATOR NODE
# ══════════════════════════════════════════════

def orchestrator_node(state: dict) -> dict:
    """
    Noeud principal de l'orchestrateur.
    Recoit un evenement, raisonne, produit une decision de routing.
    """
    from agents.shared.team_resolver import require_team_id
    project_id = state.get("project_id", "default")
    team_id = require_team_id(state)
    messages = state.get("messages", [])

    if not messages:
        logger.warning("No messages in state — nothing to route")
        return state

    try:
        # ── Pre-check : blocage juridique (pas besoin d'appel LLM) ──
        if has_critical_legal_alert(state.get("legal_alerts", [])):
            logger.warning("Critical legal alert — blocking")
            history = list(state.get("decision_history", []))
            history.append({
                "tool_calls": [],
                "output": "Alerte juridique critical non resolue. Blocage automatique.",
                "has_question": True,
                "agents_dispatched": [],
            })
            state["decision_history"] = history
            state["_orchestrator_output"] = "Alerte juridique critical non resolue. Blocage automatique."
            state["_agents_dispatched"] = []
            state["_has_question"] = True
            return state
        else:
            # ── Construire le contexte pour le LLM ──
            last_message = messages[-1]
            if hasattr(last_message, "content"):
                last_content = last_message.content
            elif isinstance(last_message, (list, tuple)) and len(last_message) >= 2:
                last_content = str(last_message[1])
            elif isinstance(last_message, dict):
                last_content = last_message.get("content", str(last_message))
            else:
                last_content = str(last_message)

            # ── Workflow engine — enrichir le contexte ──
            from agents.shared.workflow_engine import (
                get_agents_to_dispatch, can_transition, check_phase_complete, get_workflow_status
            )
            current_phase = state.get("project_phase", "discovery")
            agent_outputs = state.get("agent_outputs", {})
            allowed_agents = state.get("_allowed_agents", [])

            phase_check = check_phase_complete(current_phase, agent_outputs, team_id)
            transition_check = can_transition(current_phase, agent_outputs, state.get("legal_alerts", []), team_id)
            suggested_agents = get_agents_to_dispatch(current_phase, agent_outputs, team_id)

            # In onboarding mode, restrict to allowed agents only
            if allowed_agents:
                suggested_agents = [a for a in suggested_agents if a.get("agent_id") in allowed_agents]

            context = {
                "last_event": last_content,
                "current_phase": current_phase,
                "agent_outputs_keys": list(agent_outputs.keys()),
                "agent_outputs_status": {
                    k: v.get("status", "unknown") for k, v in agent_outputs.items() if isinstance(v, dict)
                },
                "active_blockers": state.get("blockers", []),
                "current_assignments": state.get("current_assignments", {}),
                "recent_decisions": state.get("decision_history", [])[-5:],
                "legal_alerts": state.get("legal_alerts", []),
                "qa_verdict": state.get("qa_verdict", {}),
                # Workflow engine recommendations
                "workflow": {
                    "phase_complete": phase_check["complete"],
                    "missing_agents": phase_check.get("missing_agents", []),
                    "missing_deliverables": phase_check.get("missing_deliverables", []),
                    "can_transition": transition_check["allowed"],
                    "next_phase": transition_check.get("next_phase", ""),
                    "transition_reason": transition_check.get("reason", ""),
                    "suggested_agents_to_dispatch": [
                        {"agent_id": a["agent_id"], "role": a["role"]}
                        for a in suggested_agents
                    ],
                },
            }

            # ── Appel LLM avec tools ──
            from agents.shared.rate_limiter import throttled_invoke
            from agents.shared.orchestrator_tools import get_orchestrator_tools, set_context
            from langchain_core.messages import ToolMessage

            override_prompt = ""
            for m in messages:
                role = m[0] if isinstance(m, (list, tuple)) else m.get("role", "")
                content = m[1] if isinstance(m, (list, tuple)) else m.get("content", "")
                if role == "system" and content:
                    override_prompt = content
                    break
            base_prompt = override_prompt or load_system_prompt(team_id)
            system_prompt = base_prompt

            # Build context for tools
            from agents.shared.team_resolver import get_team_info
            team_info = get_team_info(team_id)
            orchestrator_id = team_info.get("orchestrator", "orchestrator")
            tool_ctx = {
                "thread_id": state.get("_thread_id", ""),
                "team_id": team_id,
                "orchestrator_id": orchestrator_id,
                "agent_id": orchestrator_id,
                "channel_id": state.get("_discord_channel_id", ""),
                "project_slug": state.get("project_slug", ""),
                "workflow_id": state.get("_workflow_id"),
                "workflow_name": "onboarding",
                "phase_id": state.get("_phase_id"),
                "group_key": "A",
                "current_phase": current_phase or "discovery",
                "task_id": "",
                "allowed_agents": allowed_agents,
                "decision_history": state.get("decision_history", []),
                "agents_dispatched": [],
                "has_question": False,
            }
            set_context(tool_ctx)

            # Set deliverable context for save_deliverable tool
            from agents.shared.deliverable_tools import set_deliverable_context
            set_deliverable_context(tool_ctx)

            tools = get_orchestrator_tools()
            llm = get_llm()
            llm_t = llm.bind_tools(tools)

            # Build user message from template
            suggested_ids = [a["agent_id"] for a in suggested_agents]
            if override_prompt:
                template = _load_context_template(team_id, "orchestrator-context-onboarding.md")
                agents_list = ", ".join(allowed_agents) if allowed_agents else ", ".join(suggested_ids) or "aucun"
                constraint = ""
                if allowed_agents:
                    constraint = "ATTENTION : Tu ne peux dispatcher QUE ces agents : {}. Aucun autre.".format(", ".join(allowed_agents))
                # Count past tool calls from decision history
                history = state.get("decision_history", [])
                question_count = sum(
                    1 for d in history
                    for tc in d.get("tool_calls", [])
                    if tc.get("name") == "ask_human"
                )
                dispatch_count = sum(
                    1 for d in history
                    for tc in d.get("tool_calls", [])
                    if tc.get("name") == "dispatch_agent"
                )
                if dispatch_count >= 6:
                    phase_instruction = "Tu as dispatche {} agents et pose {} questions. Le cadrage est TERMINE. Utilise human_gate maintenant pour passer a la phase suivante.".format(dispatch_count, question_count)
                elif question_count >= 5:
                    phase_instruction = "Tu as pose {} questions. Dispatche des agents ou utilise human_gate.".format(question_count)
                elif question_count >= 3:
                    phase_instruction = "Tu as pose {} questions. Envisage de dispatcher un agent.".format(question_count)
                else:
                    phase_instruction = ""
                user_content = template.replace(
                    "{user_message}", last_content[:500]
                ).replace(
                    "{phase}", current_phase
                ).replace(
                    "{agents_list}", agents_list
                ).replace(
                    "{agents_constraint}", constraint
                ).replace(
                    "{question_count}", str(question_count)
                ).replace(
                    "{dispatch_count}", str(dispatch_count)
                ).replace(
                    "{phase_instruction}", phase_instruction
                )
            else:
                template = _load_context_template(team_id, "orchestrator-context-workflow.md")
                suggested_str = ", ".join(a["agent_id"] for a in suggested_agents) or "aucun"
                phase_complete_str = "oui" if phase_check["complete"] else "non"
                transition_str = "oui -> {}".format(transition_check.get("next_phase", "")) if transition_check["allowed"] else "non"
                user_content = template.replace(
                    "{context_json}", json.dumps(context, indent=2, default=str)
                ).replace(
                    "{suggested_agents}", suggested_str
                ).replace(
                    "{phase_complete}", phase_complete_str
                ).replace(
                    "{transition}", transition_str
                )

            msgs = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ]

            # ReAct loop
            max_iters = 8
            final_text = ""
            from agents.shared.langfuse_setup import get_langfuse_callbacks
            _thread = state.get("_thread_id", "") or config.get("configurable", {}).get("thread_id", "")

            for iteration in range(max_iters):
                use_llm = llm_t
                # Last iteration: strip tools to force text response
                if iteration == max_iters - 1:
                    use_llm = llm
                    logger.info("[orchestrator] ReAct: last iter, stripping tools")

                resp = throttled_invoke(use_llm, msgs, provider_name=CONFIG["llm"],
                                         callbacks=get_langfuse_callbacks(session_id=_thread, trace_name="orchestrator"))
                msgs.append(resp)

                if not resp.tool_calls:
                    final_text = resp.content if isinstance(resp.content, str) else str(resp.content)
                    logger.info("[orchestrator] ReAct done — %d iters, text=%dc", iteration + 1, len(final_text))
                    break

                # Execute tool calls
                for tc in resp.tool_calls:
                    tn, ta = tc["name"], tc["args"]
                    logger.info("[orchestrator] Tool: %s(%s)", tn, json.dumps(ta, default=str)[:200])
                    result = "Tool not found"
                    for t in tools:
                        if t.name == tn:
                            try:
                                # Try sync first, fallback to async for MCP tools
                                try:
                                    result = t.invoke(ta)
                                except NotImplementedError:
                                    import asyncio as _aio
                                    try:
                                        loop = _aio.get_event_loop()
                                        if loop.is_running():
                                            import concurrent.futures
                                            with concurrent.futures.ThreadPoolExecutor() as pool:
                                                result = pool.submit(_aio.run, t.ainvoke(ta)).result()
                                        else:
                                            result = _aio.run(t.ainvoke(ta))
                                    except RuntimeError:
                                        result = _aio.run(t.ainvoke(ta))
                                if isinstance(result, (dict, list)):
                                    result = json.dumps(result, ensure_ascii=False, default=str)
                                result = str(result)[:5000]
                            except Exception as e:
                                result = "Tool error: {}".format(e)
                                logger.error("[orchestrator] Tool %s: %s", tn, e)
                            break
                    msgs.append(ToolMessage(content=result, tool_call_id=tc["id"]))

                    # Terminal tools: stop the loop
                    if tn in ("ask_human", "human_gate"):
                        final_text = ""
                        break

                # If a terminal tool was called, exit the loop
                if tool_ctx.get("has_question"):
                    break

            # ── Persister les tool calls dans l'historique ──
            history = list(state.get("decision_history", []))
            tool_calls_log = []
            for m in msgs:
                if hasattr(m, "tool_calls") and m.tool_calls:
                    for tc in m.tool_calls:
                        tool_calls_log.append({"name": tc["name"], "args": tc["args"]})
            history.append({
                "tool_calls": tool_calls_log,
                "output": final_text[:500] if final_text else "",
                "has_question": tool_ctx.get("has_question", False),
                "agents_dispatched": [d["agent_id"] for d in tool_ctx.get("agents_dispatched", [])],
            })
            state["decision_history"] = history

            # Update assignments from dispatches
            assignments = dict(state.get("current_assignments", {}))
            for d in tool_ctx.get("agents_dispatched", []):
                assignments[d["agent_id"]] = d["task"][:200]
            state["current_assignments"] = assignments

            # Store output text and dispatch info for gateway
            state["_orchestrator_output"] = final_text
            state["_agents_dispatched"] = [d["agent_id"] for d in tool_ctx.get("agents_dispatched", [])]
            state["_has_question"] = tool_ctx.get("has_question", False)
            state["_dispatched_tasks"] = tool_ctx.get("agents_dispatched", [])

            logger.info(
                "Decision: tools=%s | dispatched=%s | has_question=%s",
                [tc["name"] for tc in tool_calls_log],
                state["_agents_dispatched"],
                state["_has_question"],
            )

            return state

    except Exception as e:
        logger.error("Orchestrator error: %s", e)
        _append_error_decision(state, project_id, "Erreur interne: {}".format(e))
        return state


def _append_error_decision(state: dict, project_id: str, error_msg: str):
    """Ajoute une decision d'erreur."""
    history = list(state.get("decision_history", []))
    history.append({
        "tool_calls": [],
        "output": "Erreur orchestrateur: {}".format(error_msg[:200]),
        "has_question": False,
        "agents_dispatched": [],
        "error": error_msg,
    })
    state["decision_history"] = history
    state["_orchestrator_output"] = "Erreur orchestrateur: {}".format(error_msg[:200])
    state["_agents_dispatched"] = []
    state["_has_question"] = False


# ══════════════════════════════════════════════
# ROUTING LOGIC
# ══════════════════════════════════════════════

def route_after_orchestrator(state: dict) -> str:
    """Determine le prochain noeud apres l'orchestrateur."""
    from agents.shared.team_resolver import require_team_id
    team_id = require_team_id(state)
    agent_ids = _load_agent_ids(team_id)

    dispatched = state.get("_agents_dispatched", [])
    has_question = state.get("_has_question", False)

    if has_question:
        return "human_gate"

    for agent_id in dispatched:
        if agent_id in agent_ids:
            return agent_id

    return "end"


# ══════════════════════════════════════════════
# PLACEHOLDER NODES (a remplacer agent par agent)
# ══════════════════════════════════════════════

def human_gate_node(state: dict) -> dict:
    """
    Human gate — attend la validation humaine via le canal configure (Discord, Email, etc.).
    Envoie une demande d'approbation et attend la reponse (timeout 30 min).
    """
    from agents.shared.human_gate import request_approval_sync

    phase = state.get("project_phase", "inconnue")
    team_id = state.get("_team_id", "default")
    channel_id = state.get("_discord_channel_id", "")

    # Construire le resume a partir de la derniere decision
    summary = f"Validation requise — phase « {phase} »"
    details = ""
    decisions = state.get("decision_history", [])
    if decisions:
        last = decisions[-1]
        output = last.get("output", "") or last.get("reasoning", "")
        if output:
            details = output

    logger.info(f"🚦 Human gate — demande approbation (team={team_id}, phase={phase})")

    result = request_approval_sync(
        agent_name="Orchestrateur",
        summary=summary,
        details=details,
        channel_id=channel_id,
        team_id=team_id,
    )

    approved = result.get("approved", False)
    reviewer = result.get("reviewer", "unknown")
    response_text = result.get("response", "")
    timed_out = result.get("timed_out", False)

    feedback = list(state.get("human_feedback_log", []))
    feedback.append({
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "response": "approve" if approved else "reject",
        "reviewer": reviewer,
        "comment": response_text,
        "timed_out": timed_out,
        "source": "human_gate",
    })
    state["human_feedback_log"] = feedback

    if timed_out:
        logger.warning("🚦 Human gate — timeout, aucune reponse")
    elif approved:
        logger.info(f"🚦 Human gate — approuve par {reviewer}")
    else:
        logger.info(f"🚦 Human gate — rejete par {reviewer} : {response_text}")

    return state


def placeholder_agent_node(state: dict) -> dict:
    """Placeholder pour les agents pas encore implementes."""
    dispatched_tasks = state.get("_dispatched_tasks", [])
    for d in dispatched_tasks:
        agent = d.get("agent_id", "unknown")
        task = d.get("task", "no task")
        logger.info("Placeholder [%s] — tache: %s", agent, task)

        # Simuler un output "complete"
        outputs = dict(state.get("agent_outputs", {}))
        outputs["{}_output".format(agent)] = {
            "status": "complete",
            "agent": agent,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "content": "[PLACEHOLDER] Simulated output for {}".format(task),
        }
        state["agent_outputs"] = outputs
    return state


# ══════════════════════════════════════════════
# GRAPH BUILDER
# ══════════════════════════════════════════════

def build_graph(team_id: str = ""):
    """Construit le graphe LangGraph complet avec les agents du registry."""
    agent_ids = _load_agent_ids(team_id)
    logger.info(f"Building graph [{team_id}]: {len(agent_ids)} agents: {agent_ids}")

    graph = StateGraph(dict)

    # Noeud principal
    graph.add_node("orchestrator", orchestrator_node)
    graph.add_node("human_gate", human_gate_node)

    # Noeuds agents depuis le registry
    for agent_id in agent_ids:
        graph.add_node(agent_id, placeholder_agent_node)

    # Entry point
    graph.set_entry_point("orchestrator")

    # Routing conditionnel apres l'orchestrateur
    routing_map = {agent_id: agent_id for agent_id in agent_ids}
    routing_map["human_gate"] = "human_gate"
    routing_map["orchestrator"] = "orchestrator"
    routing_map["end"] = END

    graph.add_conditional_edges("orchestrator", route_after_orchestrator, routing_map)

    # Chaque agent retourne a l'orchestrateur
    for agent_id in agent_ids:
        graph.add_edge(agent_id, "orchestrator")

    # Human gate retourne a l'orchestrateur
    graph.add_edge("human_gate", "orchestrator")

    return graph


def get_compiled_graph():
    """Compile le graphe avec checkpointer Postgres."""
    db_uri = os.getenv("DATABASE_URI")
    conn = psycopg.connect(db_uri, autocommit=True)
    checkpointer = PostgresSaver(conn)
    checkpointer.setup()
    return build_graph().compile(checkpointer=checkpointer)


# ══════════════════════════════════════════════
# TEST
# ══════════════════════════════════════════════

if __name__ == "__main__":
    print("=" * 60)
    print("  Test Orchestrateur — Agent Production")
    print("=" * 60)
    print()

    graph = get_compiled_graph()
    config = {"configurable": {"thread_id": "test-orchestrator-prod"}}

    # Test 1 : initialisation de projet
    print("📋 Test 1 — Initialisation de projet")
    result = graph.invoke(
        {
            "messages": [(
                "user",
                "Nouveau projet : application web de gestion de taches. "
                "Stack React + FastAPI + PostgreSQL. "
                "Fonctionnalites : auth, CRUD taches, dashboard. "
                "Deadline : 2 mois."
            )],
            "project_id": "proj_test_001",
            "project_phase": "discovery",
            "agent_outputs": {},
            "legal_alerts": [],
            "decision_history": [],
            "current_assignments": {},
            "blockers": [],
        },
        config,
    )

    decisions = result.get("decision_history", [])
    if decisions:
        last = decisions[-1]
        print("  Tool calls : {}".format([tc["name"] for tc in last.get("tool_calls", [])]))
        print("  Dispatched : {}".format(last.get("agents_dispatched", [])))
        print("  Has question : {}".format(last.get("has_question", False)))
        print("  Output : {}...".format(last.get("output", "")[:100]))
    else:
        print("  Pas de decision generee")

    print()
    print("✅ Orchestrateur production operationnel !")

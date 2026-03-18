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
from enum import Enum
from typing import Any, Optional

import psycopg
from dotenv import load_dotenv
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
from langgraph.checkpoint.postgres import PostgresSaver
from pydantic import BaseModel, Field

load_dotenv()

logger = logging.getLogger("orchestrator")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s %(message)s")


# ══════════════════════════════════════════════
# ENUMS & MODELS
# ══════════════════════════════════════════════

class ProjectPhase(str, Enum):
    DISCOVERY = "discovery"
    DESIGN = "design"
    BUILD = "build"
    SHIP = "ship"
    ITERATE = "iterate"


class DecisionType(str, Enum):
    ROUTE = "route"
    ESCALATE = "escalate"
    WAIT = "wait"
    PHASE_TRANSITION = "phase_transition"
    PARALLEL_DISPATCH = "parallel_dispatch"


class ActionType(str, Enum):
    DISPATCH_AGENT = "dispatch_agent"
    HUMAN_GATE = "human_gate"
    NOTIFY_DISCORD = "notify_discord"
    ESCALATE_HUMAN = "escalate_human"
    RETRY_AGENT = "retry_agent"
    BLOCK = "block"


class RoutingAction(BaseModel):
    action: ActionType
    target: Optional[str] = None
    task: Optional[str] = None
    channel: Optional[str] = None
    message: Optional[str] = None
    inputs_from_state: Optional[list[str]] = None
    scope: Optional[str] = None
    reason: Optional[str] = None
    from_phase: Optional[str] = None
    to_phase: Optional[str] = None


class RoutingDecision(BaseModel):
    decision_type: DecisionType
    project_id: str = "default"
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: str = Field(min_length=10)
    actions: list[RoutingAction] = Field(min_length=1)


# ══════════════════════════════════════════════
# CONFIGURATION
# ══════════════════════════════════════════════

# ══════════════════════════════════════════════
# CONFIGURATION — depuis agents_registry.json
# ══════════════════════════════════════════════

def _load_orchestrator_config(team_id: str = "team1") -> dict:
    """Charge la config de l'orchestrateur depuis le registry de l'equipe."""
    from agents.shared.team_resolver import load_team_json
    registry = load_team_json(team_id, "agents_registry.json")
    conf = registry.get("agents", {}).get("orchestrator", {})
    if conf:
        logger.info(f"Orchestrator config [{team_id}]: llm={conf.get('llm', 'default')}")
    return conf

_orch_config = _load_orchestrator_config()

CONFIG = {
    "llm": _orch_config.get("llm", ""),
    "model": os.getenv("ORCHESTRATOR_MODEL", _orch_config.get("model", "claude-sonnet-4-5-20250929")),
    "temperature": float(os.getenv("ORCHESTRATOR_TEMPERATURE", str(_orch_config.get("temperature", 0.2)))),
    "max_tokens": int(os.getenv("ORCHESTRATOR_MAX_TOKENS", str(_orch_config.get("max_tokens", 4096)))),
    "confidence_threshold": float(os.getenv("ORCHESTRATOR_CONFIDENCE_THRESHOLD", "0.7")),
}

# Phase requirements — livrables requis pour chaque transition
PHASE_REQUIREMENTS: dict[str, list[str]] = {
    "discovery": ["prd", "user_stories", "acceptance_criteria", "moscow_matrix"],
    "design": [
        "wireframes", "mockups", "design_tokens",
        "adrs", "c4_diagrams", "openapi_specs",
        "sprint_backlog", "roadmap", "risk_register",
        "accessibility_report",
    ],
    "build": ["source_code", "qa_verdict_go", "ux_audit", "test_coverage_ok"],
    "ship": [
        "cicd_pipeline", "staging_deploy_ok",
        "documentation_published", "legal_documents",
        "production_deploy_ok",
    ],
}

# Agents du systeme
AGENT_IDS = [
    "requirements_analyst",
    "ux_designer",
    "architect",
    "planner",
    "lead_dev",
    "qa_engineer",
    "devops_engineer",
    "docs_writer",
    "legal_advisor",
]


# ══════════════════════════════════════════════
# SYSTEM PROMPT
# ══════════════════════════════════════════════

def load_system_prompt(team_id: str = "team1") -> str:
    """Charge le system prompt depuis le dossier de l'equipe."""
    from agents.shared.team_resolver import find_team_file
    prompt_file = _orch_config.get("prompt", "orchestrator.md")
    path = find_team_file(team_id, prompt_file)
    if path:
        logger.info(f"Orchestrator prompt [{team_id}]: {path}")
        with open(path, "r") as f:
            return f.read()

    # Fallback : prompt inline minimal
    return """Tu es l'Orchestrateur, cerveau central d'un systeme multi-agent LangGraph.
Tu routes les taches vers le bon agent, geres les transitions de phase,
et decides quand impliquer l'humain.

Agents disponibles : requirements_analyst, ux_designer, architect, planner,
lead_dev, qa_engineer, devops_engineer, docs_writer, legal_advisor.

Phases : discovery -> design -> build -> ship -> iterate.

Reponds TOUJOURS en JSON valide avec cette structure :
{
  "decision_type": "route | escalate | wait | phase_transition | parallel_dispatch",
  "confidence": 0.0-1.0,
  "reasoning": "explication de ta decision",
  "actions": [
    {"action": "dispatch_agent | human_gate | notify_discord | escalate_human | retry_agent | block",
     "target": "agent_id", "task": "description"}
  ]
}"""


SYSTEM_PROMPT = load_system_prompt()


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

def check_phase_requirements(agent_outputs: dict, phase: str) -> tuple[bool, list[str]]:
    """Verifie si tous les livrables requis pour la phase sont presents."""
    required = PHASE_REQUIREMENTS.get(phase, [])
    missing = [r for r in required if r not in agent_outputs or
               agent_outputs[r].get("status") != "complete"]
    return len(missing) == 0, missing


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


def parse_llm_decision(raw: str, project_id: str) -> RoutingDecision:
    """Parse la reponse LLM en RoutingDecision validee."""
    clean = raw.strip()
    if "```json" in clean:
        clean = clean.split("```json")[1].split("```")[0].strip()
    elif "```" in clean:
        clean = clean.split("```")[1].split("```")[0].strip()

    data = json.loads(clean)
    data["project_id"] = project_id
    # Normalize common LLM aliases for decision_type
    dt_aliases = {"dispatch": "parallel_dispatch", "dispatch_agent": "parallel_dispatch",
                   "dispatch_agents": "parallel_dispatch", "route_agent": "route",
                   "transition": "phase_transition", "human_gate": "escalate",
                   "escalate_human": "escalate", "escalate_to_human": "escalate"}
    dt = data.get("decision_type", "")
    if dt in dt_aliases:
        data["decision_type"] = dt_aliases[dt]
    return RoutingDecision(**data)


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
    decision_history: list  # Liste des RoutingDecision
    blockers: list  # Blocages actifs

    # Juridique
    legal_alerts: list  # Alertes de l'avocat

    # QA
    qa_verdict: dict  # {status: go/no_go, details}

    # DevOps
    deploy_status: dict  # {environment, status, url}

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
    project_id = state.get("project_id", "default")
    team_id = state.get("_team_id", "team1")
    messages = state.get("messages", [])

    if not messages:
        logger.warning("No messages in state — nothing to route")
        return state

    try:
        # ── Pre-check : blocage juridique (pas besoin d'appel LLM) ──
        if has_critical_legal_alert(state.get("legal_alerts", [])):
            decision = RoutingDecision(
                decision_type=DecisionType.ESCALATE,
                project_id=project_id,
                confidence=1.0,
                reasoning="Alerte juridique critical non resolue. Blocage automatique.",
                actions=[
                    RoutingAction(
                        action=ActionType.BLOCK,
                        scope="phase_transition",
                        reason="Alerte juridique critical",
                    ),
                    RoutingAction(
                        action=ActionType.ESCALATE_HUMAN,
                        channel="#human-review",
                        message="🚨 Alerte juridique critical bloquante.",
                    ),
                ],
            )
        else:
            # ── Construire le contexte pour le LLM ──
            last_message = messages[-1]
            last_content = (
                last_message.content
                if hasattr(last_message, "content")
                else str(last_message)
            )

            # ── Workflow engine — enrichir le contexte ──
            from agents.shared.workflow_engine import (
                get_agents_to_dispatch, can_transition, check_phase_complete, get_workflow_status
            )
            current_phase = state.get("project_phase", "discovery")
            agent_outputs = state.get("agent_outputs", {})

            phase_check = check_phase_complete(current_phase, agent_outputs, team_id)
            transition_check = can_transition(current_phase, agent_outputs, state.get("legal_alerts", []), team_id)
            suggested_agents = get_agents_to_dispatch(current_phase, agent_outputs, team_id)

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

            # ── Appel LLM ──
            from agents.shared.rate_limiter import throttled_invoke
            system_prompt = load_system_prompt(team_id)
            llm = get_llm()
            msgs = [
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": (
                        f"Contexte du projet :\n"
                        f"```json\n{json.dumps(context, indent=2, default=str)}\n```\n\n"
                        f"Le workflow engine te recommande de dispatcher : "
                        f"{', '.join(a['agent_id'] for a in suggested_agents) or 'aucun (phase complete ou en attente)'}.\n"
                        f"Phase complete : {'oui' if phase_check['complete'] else 'non'}. "
                        f"Transition possible : {'oui → ' + transition_check.get('next_phase', '') if transition_check['allowed'] else 'non — ' + transition_check.get('reason', '')}.\n\n"
                        f"IMPORTANT : Respecte les recommandations du workflow engine. "
                        f"Si la phase est complete et la transition possible, propose un human_gate. "
                        f"Sinon, dispatche les agents suggeres.\n\n"
                        f"Produis ta decision de routing en JSON valide."
                    ),
                },
            ]
            from agents.shared.langfuse_setup import get_langfuse_callbacks
            response = throttled_invoke(llm, msgs, provider_name=CONFIG["llm"], callbacks=get_langfuse_callbacks())

            raw = (
                response.content
                if isinstance(response.content, str)
                else str(response.content)
            )
            decision = parse_llm_decision(raw, project_id)

        # ── Post-check : detection de boucles ──
        for action in decision.actions:
            if action.action == ActionType.DISPATCH_AGENT and action.target:
                if detect_loop(state.get("decision_history", []), action.target):
                    logger.warning(f"Loop detected on {action.target}")
                    decision = RoutingDecision(
                        decision_type=DecisionType.ESCALATE,
                        project_id=project_id,
                        confidence=0.3,
                        reasoning=f"Boucle detectee sur {action.target} (>3 dispatch sans progres).",
                        actions=[
                            RoutingAction(
                                action=ActionType.ESCALATE_HUMAN,
                                channel="#human-review",
                                message=f"🔄 Boucle sur {action.target}. Intervention requise.",
                            )
                        ],
                    )
                    break

        # ── Seuil de confiance ──
        if decision.confidence < 0.4 and decision.decision_type != DecisionType.ESCALATE:
            decision.decision_type = DecisionType.ESCALATE
            decision.actions.append(
                RoutingAction(
                    action=ActionType.ESCALATE_HUMAN,
                    channel="#human-review",
                    message=f"🟡 Confiance {decision.confidence}. {decision.reasoning[:200]}",
                )
            )
        elif decision.confidence < CONFIG["confidence_threshold"]:
            decision.actions.append(
                RoutingAction(
                    action=ActionType.NOTIFY_DISCORD,
                    channel="#orchestrateur-logs",
                    message=f"⚠️ LOW_CONFIDENCE ({decision.confidence})",
                )
            )

        # ── Persister la decision ──
        history = list(state.get("decision_history", []))
        history.append(decision.model_dump())
        state["decision_history"] = history

        # Mettre a jour les assignments
        assignments = dict(state.get("current_assignments", {}))
        for a in decision.actions:
            if a.action == ActionType.DISPATCH_AGENT and a.target:
                assignments[a.target] = a.task or "assigned"
        state["current_assignments"] = assignments

        # ── Log ──
        logger.info(
            f"Decision: {decision.decision_type.value} | "
            f"Confidence: {decision.confidence} | "
            f"Actions: {[a.action.value for a in decision.actions]}"
        )

        return state

    except json.JSONDecodeError as e:
        logger.error(f"JSON parse error: {e}")
        _append_error_decision(state, project_id, f"Erreur parsing JSON: {e}")
        return state
    except Exception as e:
        logger.error(f"Orchestrator error: {e}")
        _append_error_decision(state, project_id, f"Erreur interne: {e}")
        return state


def _append_error_decision(state: dict, project_id: str, error_msg: str):
    """Ajoute une decision d'erreur avec escalade."""
    history = list(state.get("decision_history", []))
    history.append({
        "decision_type": "escalate",
        "project_id": project_id,
        "confidence": 0.0,
        "reasoning": error_msg,
        "actions": [{
            "action": "escalate_human",
            "channel": "#human-review",
            "message": f"❌ Orchestrateur en erreur: {error_msg[:200]}",
        }],
    })
    state["decision_history"] = history


# ══════════════════════════════════════════════
# ROUTING LOGIC
# ══════════════════════════════════════════════

def route_after_orchestrator(state: dict) -> str:
    """Determine le prochain noeud apres l'orchestrateur."""
    decisions = state.get("decision_history", [])
    if not decisions:
        return "orchestrator"

    last_decision = decisions[-1]
    for action in last_decision.get("actions", []):
        action_type = action.get("action")
        target = action.get("target")

        if action_type == "dispatch_agent" and target in AGENT_IDS:
            return target
        if action_type in ("human_gate", "escalate_human", "block"):
            return "human_gate"

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
        reasoning = last.get("reasoning", "")
        if reasoning:
            details = reasoning

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
    decisions = state.get("decision_history", [])
    if decisions:
        last = decisions[-1]
        for action in last.get("actions", []):
            if action.get("action") == "dispatch_agent":
                agent = action.get("target", "unknown")
                task = action.get("task", "no task")
                logger.info(f"📌 Placeholder [{agent}] — tache: {task}")

                # Simuler un output "complete"
                outputs = dict(state.get("agent_outputs", {}))
                outputs[f"{agent}_output"] = {
                    "status": "complete",
                    "agent": agent,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "content": f"[PLACEHOLDER] Simulated output for {task}",
                }
                state["agent_outputs"] = outputs
    return state


# ══════════════════════════════════════════════
# GRAPH BUILDER
# ══════════════════════════════════════════════

def build_graph():
    """Construit le graphe LangGraph complet."""
    graph = StateGraph(dict)

    # Noeud principal
    graph.add_node("orchestrator", orchestrator_node)
    graph.add_node("human_gate", human_gate_node)

    # Noeuds agents (placeholders pour l'instant)
    for agent_id in AGENT_IDS:
        graph.add_node(agent_id, placeholder_agent_node)

    # Entry point
    graph.set_entry_point("orchestrator")

    # Routing conditionnel apres l'orchestrateur
    routing_map = {agent_id: agent_id for agent_id in AGENT_IDS}
    routing_map["human_gate"] = "human_gate"
    routing_map["orchestrator"] = "orchestrator"
    routing_map["end"] = END

    graph.add_conditional_edges("orchestrator", route_after_orchestrator, routing_map)

    # Chaque agent retourne a l'orchestrateur
    for agent_id in AGENT_IDS:
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
        print(f"  Decision : {last.get('decision_type')}")
        print(f"  Confiance : {last.get('confidence')}")
        print(f"  Reasoning : {last.get('reasoning', '')[:100]}...")
        for action in last.get("actions", []):
            print(f"  Action : {action.get('action')} → {action.get('target', 'N/A')}")
    else:
        print("  ⚠️ Pas de decision generee")

    print()
    print("✅ Orchestrateur production operationnel !")

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


def _load_agent_ids(team_id: str = "team1") -> list[str]:
    """Charge la liste des agents depuis le registry de l'equipe (hors orchestrator)."""
    from agents.shared.team_resolver import load_team_json
    registry = load_team_json(team_id, "agents_registry.json")
    return [aid for aid, cfg in registry.get("agents", {}).items() if cfg.get("type") != "orchestrator"]


# ══════════════════════════════════════════════
# SYSTEM PROMPT
# ══════════════════════════════════════════════

def load_system_prompt(team_id: str = "team1") -> str:
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


def parse_llm_decision(raw: str, project_id: str) -> RoutingDecision:
    """Parse la reponse LLM en RoutingDecision validee."""
    import re as _re

    clean = raw.strip()
    if "```json" in clean:
        clean = clean.split("```json")[1].split("```")[0].strip()
    elif "```" in clean:
        clean = clean.split("```")[1].split("```")[0].strip()

    # Try to find JSON in the response (LLM may wrap in text)
    data = None
    try:
        data = json.loads(clean)
    except (json.JSONDecodeError, ValueError):
        # Try to extract JSON object from text
        match = _re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', clean, _re.DOTALL)
        if match:
            try:
                data = json.loads(match.group())
            except (json.JSONDecodeError, ValueError):
                pass

    if data is None:
        # LLM responded in plain text — treat as escalation with the text as message
        logger.warning("JSON parse failed, treating as escalation: %s", clean[:200])
        return RoutingDecision(
            decision_type=DecisionType.ESCALATE,
            project_id=project_id,
            confidence=0.5,
            reasoning=clean[:500] if clean else "Le LLM n'a pas retourne de JSON valide.",
            actions=[RoutingAction(
                action=ActionType.ESCALATE_HUMAN,
                message=clean[:300] if clean else "Reponse non structuree du LLM.",
            )],
        )
    # Unwrap if LLM wrapped in a key like "routing_decision" or "decision"
    for wrapper_key in ("routing_decision", "decision", "response"):
        if wrapper_key in data and isinstance(data[wrapper_key], dict):
            data = data[wrapper_key]
            break
    # Handle various LLM format quirks

    # decision_type aliases
    if "decision_type" not in data:
        for alias in ("decision", "action", "type", "routing_type"):
            if alias in data and isinstance(data[alias], str):
                data["decision_type"] = data.pop(alias)
                break

    # confidence: default to 0.8 if missing
    if "confidence" not in data:
        data["confidence"] = 0.8

    # reasoning: default from any text field
    if "reasoning" not in data:
        for alias in ("reason", "explanation", "justification", "rationale", "message"):
            if alias in data and isinstance(data[alias], str):
                data["reasoning"] = data.pop(alias)
                break
        if "reasoning" not in data:
            data["reasoning"] = "Decision automatique"

    # actions: reconstruct from various formats
    if "actions" not in data:
        actions = []
        # "agents_to_dispatch" or "agents" array
        for alias in ("agents_to_dispatch", "agents", "dispatched_agents", "dispatch"):
            if alias in data and isinstance(data[alias], list):
                for item in data.pop(alias):
                    if isinstance(item, dict):
                        actions.append({
                            "action": "dispatch_agent",
                            "target": item.get("agent_id") or item.get("target") or item.get("id") or item.get("agent", ""),
                            "task": item.get("task") or item.get("instruction") or item.get("description", ""),
                        })
                    elif isinstance(item, str):
                        actions.append({"action": "dispatch_agent", "target": item, "task": ""})
                break
        # Single target/task at root level
        if not actions and ("target" in data or "task" in data or "agent" in data or "agent_id" in data):
            actions.append({
                "action": "dispatch_agent",
                "target": data.pop("target", data.pop("agent_id", data.pop("agent", ""))),
                "task": data.pop("task", data.pop("instruction", "")),
            })
        if actions:
            data["actions"] = actions
        else:
            data["actions"] = [{"action": "escalate_human", "message": data.get("reasoning", "Pas d'action identifiee")}]

    # Infer decision_type from actions if still missing
    if "decision_type" not in data:
        has_dispatch = any(a.get("action") == "dispatch_agent" for a in data.get("actions", []))
        data["decision_type"] = "parallel_dispatch" if has_dispatch else "escalate"

    data["project_id"] = project_id
    # Normalize common LLM aliases for decision_type
    dt_aliases = {"dispatch": "parallel_dispatch", "dispatch_agent": "parallel_dispatch",
                   "dispatch_agents": "parallel_dispatch", "route_agent": "route",
                   "transition": "phase_transition", "human_gate": "escalate",
                   "escalate_human": "escalate", "escalate_to_human": "escalate",
                   "ask_human": "escalate", "ask": "escalate", "question": "escalate"}
    dt = data.get("decision_type", "")
    if dt in dt_aliases:
        data["decision_type"] = dt_aliases[dt]
    # Normalize action types in actions array
    action_aliases = {"ask_human": "escalate_human", "ask": "escalate_human",
                      "question": "escalate_human", "notify": "notify_discord",
                      "dispatch": "dispatch_agent", "gate": "human_gate"}
    for a in data.get("actions", []):
        if isinstance(a, dict) and a.get("action") in action_aliases:
            a["action"] = action_aliases[a["action"]]
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

            # ── Appel LLM ──
            from agents.shared.rate_limiter import throttled_invoke
            # Check if an override system prompt was injected (e.g., onboarding chat prompt)
            override_prompt = ""
            for m in messages:
                role = m[0] if isinstance(m, (list, tuple)) else m.get("role", "")
                content = m[1] if isinstance(m, (list, tuple)) else m.get("content", "")
                if role == "system" and content:
                    override_prompt = content
                    break
            base_prompt = override_prompt or load_system_prompt(team_id)
            # Ensure routing format instructions are always present
            routing_format = (
                "\n\n--- FORMAT DE SORTIE OBLIGATOIRE ---\n"
                "Produis ta decision en JSON valide avec cette structure :\n"
                '{"decision_type": "route|escalate|wait|phase_transition|parallel_dispatch",\n'
                ' "confidence": 0.0-1.0,\n'
                ' "reasoning": "explication",\n'
                ' "actions": [{"action": "dispatch_agent|escalate_human|ask_human", "target": "agent_id", "task": "description"}]}\n'
            )
            system_prompt = base_prompt + routing_format if override_prompt else base_prompt
            llm = get_llm()
            if override_prompt:
                # Simplified user message for onboarding — avoid overwhelming small models
                suggested_ids = [a["agent_id"] for a in suggested_agents]
                agents_list = ', '.join(allowed_agents) if allowed_agents else ', '.join(suggested_ids) or 'aucun'
                constraint = f"\nATTENTION : Tu ne peux dispatcher QUE ces agents : {', '.join(allowed_agents)}. Aucun autre." if allowed_agents else ""
                user_content = (
                    f"Message utilisateur : {last_content[:500]}\n\n"
                    f"Phase : {current_phase}. "
                    f"Agents disponibles : {agents_list}.{constraint}\n\n"
                    f"Reponds en JSON valide."
                )
            else:
                user_content = (
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
                )
            msgs = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ]
            from agents.shared.langfuse_setup import get_langfuse_callbacks
            _thread = state.get("_thread_id", "") or config.get("configurable", {}).get("thread_id", "")
            response = throttled_invoke(llm, msgs, provider_name=CONFIG["llm"], callbacks=get_langfuse_callbacks(session_id=_thread, trace_name="orchestrator"))

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

    team_id = state.get("_team_id", "team1")
    agent_ids = _load_agent_ids(team_id)

    last_decision = decisions[-1]
    for action in last_decision.get("actions", []):
        action_type = action.get("action")
        target = action.get("target")

        if action_type == "dispatch_agent" and target in agent_ids:
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

def build_graph(team_id: str = "team1"):
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
        print(f"  Decision : {last.get('decision_type')}")
        print(f"  Confiance : {last.get('confidence')}")
        print(f"  Reasoning : {last.get('reasoning', '')[:100]}...")
        for action in last.get("actions", []):
            print(f"  Action : {action.get('action')} → {action.get('target', 'N/A')}")
    else:
        print("  ⚠️ Pas de decision generee")

    print()
    print("✅ Orchestrateur production operationnel !")

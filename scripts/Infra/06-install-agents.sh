#!/bin/bash
###############################################################################
# Script 6 : Installation des agents LangGraph (equipe complete)
# VERSION CONSOLIDEE (integre scripts 04 + fix 07/08/09/10/11)
#   - 04 : Discord bot (discord_tools, discord_listener, Dockerfile.discord)
#   - 07 : gateway multi-agent
#   - 08 : context + max_tokens
#   - 09 : pipeline mode (base_agent, analyst 3 etapes, legal 2 etapes)
#   - 10 : gateway asynchrone + discord_listener mis a jour
#   - 11 : streaming resultats Discord (notification par etape pipeline)
#
# A executer depuis la VM Ubuntu (apres les scripts 03 et 05).
# Usage : ./06-install-agents.sh
###############################################################################
set -euo pipefail

PROJECT_DIR="$HOME/langgraph-project"
REPO_RAW="https://raw.githubusercontent.com/Configurations/LandGraph/refs/heads/main"

echo "==========================================="
echo "  Script 6 : Installation des agents"
echo "  (version consolidee)"
echo "==========================================="
echo ""

cd "${PROJECT_DIR}"
[ ! -f .env ] && echo "ERREUR : .env introuvable." && exit 1

# ── 1. Structure ─────────────────────────────
echo "[1/11] Structure..."
mkdir -p agents/shared prompts/v1
touch agents/__init__.py agents/shared/__init__.py

# ── 2. Prompts ───────────────────────────────
echo "[2/11] Telechargement des prompts..."
PROMPTS=(orchestrator requirements_analyst ux_designer architect planner lead_dev dev_frontend_web dev_backend_api dev_mobile qa_engineer devops_engineer docs_writer legal_advisor)
DL=0
for name in "${PROMPTS[@]}"; do
    T="prompts/v1/${name}.md"
    if wget -qO "$T" "${REPO_RAW}/prompts/${name}.md" 2>/dev/null && [ -s "$T" ]; then
        DL=$((DL+1))
    elif wget -qO "$T" "${REPO_RAW}/prompts/v1/${name}.md" 2>/dev/null && [ -s "$T" ]; then
        DL=$((DL+1))
    else
        echo "Tu es ${name}, agent LangGraph. Reponds en JSON: {agent_id, status, confidence, deliverables}." > "$T"
    fi
done
echo "  -> ${DL}/${#PROMPTS[@]} prompts"

# ── 3. shared/state.py ──────────────────────
echo "[3/11] ProjectState..."
cat > agents/shared/state.py << 'PY'
from typing import TypedDict, Annotated
from langgraph.graph.message import add_messages
class ProjectState(TypedDict, total=False):
    messages: Annotated[list, add_messages]
    project_id: str
    project_phase: str
    project_metadata: dict
    agent_outputs: dict
    current_assignments: dict
    decision_history: list
    blockers: list
    legal_alerts: list
    qa_verdict: dict
    deploy_status: dict
    human_feedback_log: list
    notifications_log: list
PY

# ── 4. shared/base_agent.py (pipeline + max_tokens 32768 + streaming Discord) ─
echo "[4/11] BaseAgent (pipeline + streaming Discord par etape)..."
cat > agents/shared/base_agent.py << 'PYTHON'
"""BaseAgent — Pipeline multi-etapes avec notification Discord par etape."""
import json, logging, os
from datetime import datetime, timezone
from dotenv import load_dotenv
from langchain_anthropic import ChatAnthropic

load_dotenv()
logger = logging.getLogger(__name__)

DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN", "")


def _post_to_discord_sync(channel_id: str, message: str):
    """Post synchrone vers Discord (pour les agents qui tournent dans des threads)."""
    if not DISCORD_BOT_TOKEN or not channel_id:
        return

    import requests
    url = f"https://discord.com/api/v10/channels/{channel_id}/messages"
    headers = {"Authorization": f"Bot {DISCORD_BOT_TOKEN}", "Content-Type": "application/json"}

    chunks = [message[i:i + 1900] for i in range(0, len(message), 1900)]
    for chunk in chunks:
        try:
            resp = requests.post(url, headers=headers, json={"content": chunk}, timeout=10)
            if resp.status_code not in (200, 201):
                logger.error(f"Discord POST failed: {resp.status_code}")
        except Exception as e:
            logger.error(f"Discord error: {e}")


def _format_deliverable(key: str, val) -> str:
    """Formate un livrable pour Discord (lisible, pas trop long)."""
    if isinstance(val, str):
        return val[:1500] + "..." if len(val) > 1500 else val
    elif isinstance(val, dict):
        parts = []
        for k, v in val.items():
            if isinstance(v, str):
                parts.append(f"**{k}** : {v[:300]}{'...' if len(v) > 300 else ''}")
            elif isinstance(v, list):
                parts.append(f"**{k}** : {len(v)} elements")
            elif isinstance(v, dict):
                parts.append(f"**{k}** : {json.dumps(v, ensure_ascii=False, default=str)[:300]}...")
            else:
                parts.append(f"**{k}** : {v}")
        return "\n".join(parts[:10])
    elif isinstance(val, list):
        if len(val) == 0:
            return "(vide)"
        parts = []
        for item in val[:5]:
            if isinstance(item, dict):
                summary = " | ".join(f"{k}={str(v)[:80]}" for k, v in list(item.items())[:4])
                parts.append(f"  - {summary}")
            else:
                parts.append(f"  - {str(item)[:200]}")
        result = "\n".join(parts)
        if len(val) > 5:
            result += f"\n  ... et {len(val) - 5} de plus"
        return result
    else:
        return str(val)[:500]


class BaseAgent:
    agent_id = "base"
    agent_name = "Base Agent"
    default_model = "claude-sonnet-4-5-20250929"
    default_temperature = 0.3
    default_max_tokens = 32768
    prompt_filename = "base.md"
    pipeline_steps = []

    def __init__(self):
        self.model = os.getenv(f"{self.agent_id.upper()}_MODEL", self.default_model)
        self.temperature = float(os.getenv(f"{self.agent_id.upper()}_TEMPERATURE", str(self.default_temperature)))
        self.max_tokens = int(os.getenv(f"{self.agent_id.upper()}_MAX_TOKENS", str(self.default_max_tokens)))
        self.system_prompt = self._load_prompt()

    def _load_prompt(self):
        for p in [
            os.path.join(os.path.dirname(__file__), "..", "..", "prompts", "v1", self.prompt_filename),
            os.path.join("/app", "prompts", "v1", self.prompt_filename),
        ]:
            a = os.path.abspath(p)
            if os.path.exists(a):
                logger.info(f"[{self.agent_id}] Prompt: {a}")
                return open(a).read()
        return f"Tu es {self.agent_name}. JSON: {{agent_id, status, confidence, deliverables}}"

    def get_llm(self):
        return ChatAnthropic(model=self.model, temperature=self.temperature, max_tokens=self.max_tokens)

    def _extract_brief(self, state):
        m = state.get("project_metadata", {})
        if isinstance(m, dict) and m.get("brief"):
            return m["brief"]
        for msg in state.get("messages", []):
            if isinstance(msg, tuple) and len(msg) == 2 and msg[0] == "user" and len(msg[1]) > 20:
                return msg[1]
            elif hasattr(msg, "content"):
                c = msg.content if isinstance(msg.content, str) else str(msg.content)
                if len(c) > 20:
                    return c
        return "Aucun brief."

    def _extract_task(self, state):
        for d in reversed(state.get("decision_history", [])):
            for a in d.get("actions", []):
                if isinstance(a, dict) and a.get("target") == self.agent_id:
                    return a.get("task") or ""
                elif hasattr(a, "target") and a.target == self.agent_id:
                    return a.task or ""
        return ""

    def _get_channel_id(self, state):
        """Recupere le channel Discord depuis le state ou les env vars."""
        return state.get("_discord_channel_id", "") or os.getenv("DISCORD_CHANNEL_COMMANDS", "") or os.getenv("DISCORD_CHANNEL_LOGS", "")

    def build_context(self, state):
        o = state.get("agent_outputs", {})
        return {
            "project_phase": state.get("project_phase", "unknown"),
            "project_metadata": state.get("project_metadata", {}),
            "brief": self._extract_brief(state),
            "task": self._extract_task(state),
            "existing_outputs": list(o.keys()),
            "relevant_outputs": {
                k: {"status": v.get("status"), "keys": list(v.get("deliverables", {}).keys())}
                for k, v in o.items() if v.get("status") == "complete"
            },
        }

    def parse_response(self, raw):
        c = raw.strip()
        if "```json" in c:
            c = c.split("```json")[1].split("```")[0].strip()
        elif "```" in c:
            c = c.split("```")[1].split("```")[0].strip()
        return json.loads(c)

    def _call_llm(self, instruction, context, previous_results=None):
        llm = self.get_llm()
        user_content = f"Contexte du projet :\n```json\n{json.dumps(context, indent=2, default=str)}\n```\n\n"
        if previous_results:
            prev_str = json.dumps(previous_results, indent=2, default=str, ensure_ascii=False)
            if len(prev_str) > 15000:
                prev_str = prev_str[:15000] + "\n... (tronque pour le context window)"
            user_content += f"Resultats des etapes precedentes :\n```json\n{prev_str}\n```\n\n"
        user_content += f"Instruction : {instruction}\n\nReponds UNIQUEMENT en JSON valide."
        response = llm.invoke([
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": user_content},
        ])
        raw = response.content if isinstance(response.content, str) else str(response.content)
        logger.info(f"[{self.agent_id}] LLM response: {len(raw)} chars")
        return raw

    def _run_pipeline(self, state):
        context = self.build_context(state)
        channel_id = self._get_channel_id(state)
        deliverables = {}

        for i, step in enumerate(self.pipeline_steps, 1):
            step_name = step["name"]
            instruction = step["instruction"]
            output_key = step["output_key"]

            logger.info(f"[{self.agent_id}] Pipeline {i}/{len(self.pipeline_steps)}: {step_name}")
            _post_to_discord_sync(channel_id,
                f"**{self.agent_name}** — etape {i}/{len(self.pipeline_steps)} : **{step_name}**...")

            raw = self._call_llm(instruction, context, deliverables if deliverables else None)

            try:
                parsed = self.parse_response(raw)
                if output_key in parsed:
                    deliverables[output_key] = parsed[output_key]
                elif "deliverables" in parsed and output_key in parsed["deliverables"]:
                    deliverables[output_key] = parsed["deliverables"][output_key]
                else:
                    deliverables[output_key] = parsed

                logger.info(f"[{self.agent_id}] Etape {step_name}: OK")
                formatted = _format_deliverable(output_key, deliverables[output_key])
                _post_to_discord_sync(channel_id,
                    f"**{self.agent_name}** — **{step_name}** termine\n\n{formatted}")

            except json.JSONDecodeError as e:
                logger.error(f"[{self.agent_id}] Etape {step_name} JSON fail: {e}")
                deliverables[output_key] = {"raw": raw[:8000], "parse_error": str(e)[:100]}
                _post_to_discord_sync(channel_id,
                    f"**{self.agent_name}** — **{step_name}** : reponse trop longue, output brut preserve.")

        _post_to_discord_sync(channel_id,
            f"**{self.agent_name}** termine — {len(self.pipeline_steps)} etapes completees.\n"
            f"Livrables : {', '.join(deliverables.keys())}")

        return {
            "agent_id": self.agent_id,
            "status": "complete",
            "confidence": 0.85,
            "deliverables": deliverables,
            "pipeline_steps_completed": len(self.pipeline_steps),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def _run_single(self, state):
        context = self.build_context(state)
        channel_id = self._get_channel_id(state)

        _post_to_discord_sync(channel_id, f"**{self.agent_name}** travaille...")

        raw = self._call_llm(context.get("task", "Produis ton livrable."), context)

        try:
            output = self.parse_response(raw)
        except json.JSONDecodeError as e:
            logger.error(f"[{self.agent_id}] JSON fail: {e}")
            output = {
                "agent_id": self.agent_id, "status": "complete", "confidence": 0.6,
                "deliverables": {"raw_output": raw[:8000]}, "parse_note": str(e)[:100],
            }

        output["agent_id"] = self.agent_id
        output["timestamp"] = datetime.now(timezone.utc).isoformat()

        status = output.get("status", "unknown")
        conf = output.get("confidence", "N/A")
        deliverables = output.get("deliverables", {})
        msg = f"**{self.agent_name}** termine — status={status}, confidence={conf}\n"
        if isinstance(deliverables, dict):
            for key in list(deliverables.keys())[:5]:
                formatted = _format_deliverable(key, deliverables[key])
                msg += f"\n**{key}** :\n{formatted}\n"
        _post_to_discord_sync(channel_id, msg)

        return output

    def __call__(self, state):
        try:
            logger.info(f"[{self.agent_id}] Start — pipeline={len(self.pipeline_steps)} steps")

            if self.pipeline_steps:
                output = self._run_pipeline(state)
            else:
                output = self._run_single(state)

            ao = dict(state.get("agent_outputs", {}))
            ao[self.agent_id] = output
            state["agent_outputs"] = ao

            msgs = list(state.get("messages", []))
            msgs.append(("assistant", f"[{self.agent_id}] status={output.get('status')}"))
            state["messages"] = msgs

            logger.info(f"[{self.agent_id}] Done — status={output.get('status')}")
            return state

        except Exception as e:
            logger.error(f"[{self.agent_id}] EXC: {e}", exc_info=True)
            channel_id = self._get_channel_id(state)
            _post_to_discord_sync(channel_id, f"**{self.agent_name}** erreur : {str(e)[:300]}")

            ao = dict(state.get("agent_outputs", {}))
            ao[self.agent_id] = {
                "agent_id": self.agent_id, "status": "blocked",
                "error": str(e), "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            state["agent_outputs"] = ao
            return state
PYTHON

echo "  -> Modules partages crees"

# ── 5. Agents specialistes ───────────────────
echo "[5/11] Agents specialistes..."

# -- Analyste en mode pipeline (3 etapes : PRD -> User Stories -> MoSCoW) --
cat > agents/requirements_analyst.py << 'PYTHON'
"""Analyste (Requirements Agent) — Pipeline 3 etapes : PRD, User Stories, MoSCoW."""
from agents.shared.base_agent import BaseAgent


class AnalystAgent(BaseAgent):
    agent_id = "requirements_analyst"
    agent_name = "Analyste"
    default_temperature = 0.3
    default_max_tokens = 32768
    prompt_filename = "requirements_analyst.md"

    pipeline_steps = [
        {
            "name": "PRD",
            "output_key": "prd",
            "instruction": (
                "Produis le PRD (Product Requirements Document) en JSON. "
                "Sections obligatoires : context_and_problem, objectives (KPIs), "
                "personas (2-4 avec besoins et frustrations), "
                "scope (in_scope + out_of_scope), "
                "functional_requirements (par domaine), "
                "non_functional_requirements (performance, securite, accessibilite, scalabilite — marquer [IMPLICITE] si infere), "
                "constraints (technical, business, regulatory), "
                "assumptions_and_risks, glossary. "
                "Format : {\"prd\": {\"context_and_problem\": \"...\", \"objectives\": [...], ...}}"
            ),
        },
        {
            "name": "User Stories",
            "output_key": "user_stories",
            "instruction": (
                "A partir du PRD produit a l'etape precedente, genere les User Stories. "
                "Format INVEST : Independante, Negociable, Valorisable, Estimable, Small, Testable. "
                "Chaque story : id (US-001), persona, action, benefit, "
                "acceptance_criteria (2-5 criteres Given/When/Then). "
                "Format : {\"user_stories\": [{\"id\": \"US-001\", \"persona\": \"...\", \"action\": \"...\", "
                "\"benefit\": \"...\", \"acceptance_criteria\": [{\"given\": \"...\", \"when\": \"...\", \"then\": \"...\"}]}]}"
            ),
        },
        {
            "name": "MoSCoW",
            "output_key": "moscow_matrix",
            "instruction": (
                "A partir des User Stories produites, classe chaque story en MoSCoW. "
                "Must Have = le produit ne fonctionne pas sans. "
                "Should Have = important mais pas bloquant MVP. "
                "Could Have = nice-to-have. "
                "Won't Have = explicitement exclu. "
                "Justifie chaque classification. "
                "Format : {\"moscow_matrix\": {\"must_have\": [{\"story_id\": \"US-001\", \"justification\": \"...\"}], "
                "\"should_have\": [...], \"could_have\": [...], \"wont_have\": [...]}}"
            ),
        },
    ]

    def build_context(self, state):
        return {
            "project_phase": state.get("project_phase", "discovery"),
            "project_metadata": state.get("project_metadata", {}),
            "brief": self._extract_brief(state),
            "task": self._extract_task(state),
            "existing_outputs": list(state.get("agent_outputs", {}).keys()),
        }


agent = AnalystAgent()
PYTHON

# -- Avocat en mode pipeline (2 etapes : Audit -> Alertes) --
cat > agents/legal_advisor.py << 'PYTHON'
"""Avocat (Legal Agent) — Pipeline 2 etapes : Audit reglementaire, Rapport."""
from agents.shared.base_agent import BaseAgent


class LegalAdvisorAgent(BaseAgent):
    agent_id = "legal_advisor"
    agent_name = "Avocat"
    default_temperature = 0.2
    default_max_tokens = 32768
    prompt_filename = "legal_advisor.md"

    pipeline_steps = [
        {
            "name": "Audit reglementaire",
            "output_key": "regulatory_audit",
            "instruction": (
                "Effectue l'audit reglementaire du projet. "
                "Identifie : juridictions applicables, reglementations (RGPD, ePrivacy, etc.), "
                "donnees personnelles collectees et leur sensibilite, "
                "obligations de consentement, risques juridiques. "
                "Inclus le disclaimer : 'Analyse automatisee, ne remplace pas un avocat qualifie.' "
                "Format : {\"regulatory_audit\": {\"disclaimer\": \"...\", \"jurisdictions\": [...], "
                "\"regulations\": [...], \"data_sensitivity\": [...], \"risks\": [...]}}"
            ),
        },
        {
            "name": "Alertes et recommandations",
            "output_key": "alerts",
            "instruction": (
                "A partir de l'audit reglementaire, produis les alertes et recommandations. "
                "Niveaux : info (recommandation), warning (risque modere), critical (bloquant). "
                "Les alertes critical BLOQUENT la transition de phase. "
                "Format : {\"alerts\": [{\"level\": \"info|warning|critical\", \"category\": \"...\", "
                "\"description\": \"...\", \"recommendation\": \"...\", \"resolved\": false}]}"
            ),
        },
    ]

    def build_context(self, state):
        outputs = state.get("agent_outputs", {})
        return {
            "project_phase": state.get("project_phase", "discovery"),
            "brief": self._extract_brief(state),
            "task": self._extract_task(state),
            "prd": outputs.get("requirements_analyst", {}).get("deliverables", {}).get("prd"),
            "user_stories": outputs.get("requirements_analyst", {}).get("deliverables", {}).get("user_stories"),
            "existing_legal_alerts": state.get("legal_alerts", []),
        }


agent = LegalAdvisorAgent()
PYTHON

# -- Autres agents (single-shot) --
for AGENT_DEF in \
  "ux_designer:Designer UX:0.4:32768:ux_designer.md" \
  "architect:Architecte:0.2:32768:architect.md" \
  "planner:Planificateur:0.2:32768:planner.md" \
  "lead_dev:Lead Dev:0.2:16384:lead_dev.md" \
  "dev_frontend_web:Dev Frontend Web:0.2:32768:dev_frontend_web.md" \
  "dev_backend_api:Dev Backend API:0.2:32768:dev_backend_api.md" \
  "dev_mobile:Dev Mobile:0.2:32768:dev_mobile.md" \
  "qa_engineer:QA Engineer:0.2:32768:qa_engineer.md" \
  "devops_engineer:DevOps Engineer:0.2:32768:devops_engineer.md" \
  "docs_writer:Documentaliste:0.3:32768:docs_writer.md"; do

  IFS=':' read -r AID ANAME ATEMP AMAX APROMPT <<< "${AGENT_DEF}"

  cat > "agents/${AID}.py" << PYEOF
"""${ANAME}"""
from agents.shared.base_agent import BaseAgent

class Agent(BaseAgent):
    agent_id = "${AID}"
    agent_name = "${ANAME}"
    default_temperature = ${ATEMP}
    default_max_tokens = ${AMAX}
    prompt_filename = "${APROMPT}"

    def build_context(self, state):
        o = state.get("agent_outputs", {})
        return {
            "project_phase": state.get("project_phase", "unknown"),
            "project_metadata": state.get("project_metadata", {}),
            "brief": self._extract_brief(state),
            "task": self._extract_task(state),
            "existing_outputs": list(o.keys()),
            "relevant_outputs": {k: {"status": v.get("status"), "deliverables_keys": list(v.get("deliverables", {}).keys())} for k, v in o.items() if v.get("status") == "complete"},
        }

agent = Agent()
PYEOF
done

echo "  -> 12 agents crees (analyst pipeline 3 etapes, legal pipeline 2 etapes, 10 single-shot)"

# ── 6. Orchestrateur ─────────────────────────
echo "[6/11] Orchestrateur..."
if wget -qO agents/orchestrator.py "${REPO_RAW}/prompts/orchestrator.py" 2>/dev/null && [ -s agents/orchestrator.py ]; then
    echo "  -> telecharge"
else
    echo "  -> conserve (local)"
fi

# ── 7. Gateway asynchrone ────────────────────
echo "[7/11] Gateway asynchrone..."

cat > agents/gateway.py << 'PY'
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

# ── Graph (orchestrateur seul pour la reponse rapide) ────────────
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

    for agent_info in agents_to_run:
        agent_id = agent_info["agent_id"]
        agent_callable = agent_info["agent"]
        task = agent_info["task"]

        logger.info(f"[background] Running {agent_id}...")

        try:
            # L'agent poste ses propres resultats dans Discord via BaseAgent
            result_state = await asyncio.to_thread(agent_callable, dict(state))

            agent_output = result_state.get("agent_outputs", {}).get(agent_id, {})
            status = agent_output.get("status", "unknown")

            state["agent_outputs"] = result_state.get("agent_outputs", state.get("agent_outputs", {}))

            logger.info(f"[background] {agent_id} done — status={status}")

        except Exception as e:
            logger.error(f"[background] {agent_id} failed: {e}", exc_info=True)
            await post_to_discord(
                channel_id,
                f"**{agent_id}** erreur : {str(e)[:300]}"
            )

    completed = list(state.get("agent_outputs", {}).keys())
    await post_to_discord(
        channel_id,
        f"**Phase Discovery terminee**\nAgents completes : {', '.join(completed)}\n"
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

        result = graph.invoke(state, config)
        decisions = result.get("decision_history", [])

        agents_dispatched = []
        for d in decisions:
            for a in d.get("actions", []):
                if isinstance(a, dict) and a.get("action") == "dispatch_agent":
                    target = a.get("target", "")
                    task = (a.get("task") or "")[:200]
                    if target:
                        agents_dispatched.append({"agent": target, "task": task})

        output_parts = []
        for i, d in enumerate(decisions, 1):
            dtype = d.get("decision_type", "unknown")
            conf = d.get("confidence", 0)
            reasoning = d.get("reasoning", "")[:300]
            output_parts.append(f"**Decision {i}** : {dtype} (confiance: {conf})\n{reasoning}")

        if agents_dispatched:
            output_parts.append("\n**Agents lances en arriere-plan :**")
            for ad in agents_dispatched:
                output_parts.append(f"  {ad['agent']} : {ad['task']}")
            output_parts.append("\nLes resultats seront postes dans ce channel quand les agents auront termine.")

        output_text = "\n\n".join(output_parts) if output_parts else "Orchestrateur en attente."

        if agents_dispatched:
            channel_id = request.channel_id or DISCORD_CHANNEL_COMMANDS or DISCORD_CHANNEL_LOGS
            result["_discord_channel_id"] = channel_id
            background_tasks.add_task(
                run_agents_background,
                result,
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
PY

echo "  -> gateway.py asynchrone installe"

# ── 8. Variables Discord dans .env ────────────
echo "[8/11] Configuration Discord dans .env..."
if ! grep -q "DISCORD_BOT_TOKEN" .env; then
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

# ── 9. Discord listener + tools ──────────────
echo "[9/11] Discord listener et tools..."

cat > agents/shared/discord_tools.py << 'PYTHON'
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
            discord_embed.add_field(name=field["name"], value=field["value"], inline=field.get("inline", False))
        await channel.send(content=message, embed=discord_embed)
    else:
        await channel.send(content=message)


async def request_human_approval(channel_id: int, agent_name: str, question: str, context: str = "", timeout: int = 300) -> dict:
    """Envoie une demande de validation et attend la reponse humaine."""
    await _client_ready.wait()
    channel = client.get_channel(channel_id)
    if channel is None:
        channel = await client.fetch_channel(channel_id)

    embed = discord.Embed(title=f"Validation requise - {agent_name}", description=question, color=0xF59E0B)
    if context:
        embed.add_field(name="Contexte", value=context[:1024], inline=False)
    embed.add_field(name="Actions", value="Repondre `approve` ou `revise` (+ commentaire optionnel)", inline=False)
    embed.set_footer(text=f"Timeout: {timeout}s - sans reponse = escalade")

    msg = await channel.send(embed=embed)
    await msg.add_reaction("\u2705")
    await msg.add_reaction("\U0001f504")

    def check(m):
        return (m.channel.id == channel_id and not m.author.bot and m.reference is not None and m.reference.message_id == msg.id) or \
               (m.channel.id == channel_id and not m.author.bot and m.content.lower().startswith(("approve", "revise")))

    try:
        reply = await client.wait_for("message", check=check, timeout=timeout)
        content = reply.content.lower().strip()
        approved = content.startswith("approve") or content == "ok" or content == "yes"
        return {"approved": approved, "response": reply.content, "timed_out": False, "reviewer": str(reply.author)}
    except asyncio.TimeoutError:
        await channel.send(f"Timeout - pas de reponse pour `{agent_name}`. Escalade automatique.")
        return {"approved": False, "response": "", "timed_out": True, "reviewer": None}


async def send_alert(message: str, severity: str = "warning"):
    """Envoie une alerte dans le channel #alerts."""
    colors = {"info": 0x6366F1, "warning": 0xF59E0B, "error": 0xF43F5E, "critical": 0xFF0000}
    embed = discord.Embed(title=f"Alerte - {severity.upper()}", description=message, color=colors.get(severity, 0xF59E0B))
    await send_notification(CHANNEL_ALERTS, "", embed=embed)


async def send_phase_transition(from_phase: str, to_phase: str, details: str = ""):
    """Log une transition de phase dans #orchestrateur-logs."""
    embed = discord.Embed(title="Transition de phase", description=f"**{from_phase}** -> **{to_phase}**", color=0x10B981)
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
            request_human_approval(CHANNEL_REVIEW, agent_name="Agent", question=question, context=context), client.loop)
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
PYTHON

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
    if message.author == client.user:
        return
    if CHANNEL_COMMANDS and str(message.channel.id) != CHANNEL_COMMANDS:
        return
    if len(message.content) < 5:
        return

    logger.info(f"Message recu de {message.author}: {message.content[:100]}")
    await message.add_reaction("\u2705")

    try:
        async with aiohttp.ClientSession() as session:
            payload = {
                "messages": [{"role": "user", "content": message.content}],
                "thread_id": f"discord-{message.id}",
                "project_id": "default",
                "channel_id": str(message.channel.id),
            }
            async with session.post(f"{API_URL}/invoke", json=payload, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    output = data.get("output", "Pas de reponse.")
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

echo "  -> discord_tools.py + discord_listener.py crees"

# ── 10. Dockerfile.discord + service docker-compose ──
echo "[10/11] Dockerfile.discord + service docker-compose..."

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

if ! grep -q "discord-bot:" docker-compose.yml; then
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
else
    echo "  -> Service discord-bot deja present"
fi

if ! grep -q "discord.py" requirements.txt; then
    echo "discord.py>=2.4.0" >> requirements.txt
    echo "aiohttp>=3.10.0" >> requirements.txt
fi

echo "  -> Dockerfile.discord + service docker-compose crees"

# ── 11. Dockerfile + rebuild + validation ─────
echo "[11/11] Rebuild et validation..."

grep -q "COPY prompts/" Dockerfile 2>/dev/null || sed -i '/COPY config\//a COPY prompts/ ./prompts/' Dockerfile
grep -q "^requests" requirements.txt || echo "requests>=2.31.0" >> requirements.txt

docker compose up -d --build langgraph-api discord-bot
sleep 12

AC=$(ls -1 agents/*.py 2>/dev/null | grep -v __init__ | grep -v gateway | wc -l)
PC=$(ls -1 prompts/v1/*.md 2>/dev/null | wc -l)
echo "  Agents: ${AC} | Prompts: ${PC}"

H=$(curl -s http://localhost:8123/health 2>/dev/null || echo error)
S=$(curl -s http://localhost:8123/status 2>/dev/null || echo '{}')
NA=$(echo "$S" | python3 -c "import sys,json;print(json.load(sys.stdin).get('total_agents',0))" 2>/dev/null || echo 0)
echo "  Health: ${H}"
echo "  API Agents: ${NA}"

echo ""
echo "  Agents installes :"
echo "  - Orchestrateur (routing)"
echo "  - Analyste (pipeline 3 etapes : PRD -> User Stories -> MoSCoW)"
echo "  - Designer UX, Architecte, Planificateur, Lead Dev"
echo "  - Dev Frontend Web, Dev Backend API, Dev Mobile"
echo "  - QA Engineer, DevOps Engineer, Documentaliste"
echo "  - Avocat (pipeline 2 etapes : Audit -> Alertes)"
echo ""
echo "  Gateway : mode asynchrone (reponse immediate + agents en background)"
echo ""
echo "  Testez : Discord #commandes ou curl localhost:8123/invoke"
echo "==========================================="

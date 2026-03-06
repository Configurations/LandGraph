#!/bin/bash
###############################################################################
# Script 6 : Installation des agents LangGraph (equipe complete)
# VERSION CONSOLIDEE (integre fix 07/08/09/10)
#   - 07 : gateway multi-agent
#   - 08 : context + max_tokens
#   - 09 : pipeline mode (base_agent, analyst 3 etapes, legal 2 etapes)
#   - 10 : gateway asynchrone + discord_listener mis a jour
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
echo "[1/8] Structure..."
mkdir -p agents/shared prompts/v1
touch agents/__init__.py agents/shared/__init__.py

# ── 2. Prompts ───────────────────────────────
echo "[2/8] Telechargement des prompts..."
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
echo "[3/8] ProjectState..."
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

# ── 4. shared/base_agent.py (pipeline mode + max_tokens 32768) ────
echo "[4/8] BaseAgent (pipeline mode + max_tokens 32768)..."
cat > agents/shared/base_agent.py << 'PYTHON'
"""BaseAgent — Classe de base avec mode pipeline multi-etapes."""
import json, logging, os
from datetime import datetime, timezone
from dotenv import load_dotenv
from langchain_anthropic import ChatAnthropic

load_dotenv()
logger = logging.getLogger(__name__)


class BaseAgent:
    agent_id = "base"
    agent_name = "Base Agent"
    default_model = "claude-sonnet-4-5-20250929"
    default_temperature = 0.3
    default_max_tokens = 32768
    prompt_filename = "base.md"

    # Pipeline : liste d'etapes. Si vide, mode single-shot.
    # Chaque etape = {"name": "...", "instruction": "...", "output_key": "..."}
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
        """Appel LLM unique avec contexte et resultats precedents."""
        llm = self.get_llm()

        user_content = f"Contexte du projet :\n```json\n{json.dumps(context, indent=2, default=str)}\n```\n\n"

        if previous_results:
            user_content += f"Resultats des etapes precedentes :\n```json\n{json.dumps(previous_results, indent=2, default=str, ensure_ascii=False)[:10000]}\n```\n\n"

        user_content += f"Instruction : {instruction}\n\nReponds UNIQUEMENT en JSON valide, sans texte avant ou apres."

        response = llm.invoke([
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": user_content},
        ])

        raw = response.content if isinstance(response.content, str) else str(response.content)
        logger.info(f"[{self.agent_id}] LLM response: {len(raw)} chars")
        return raw

    def _run_pipeline(self, state):
        """Execute les etapes du pipeline sequentiellement."""
        context = self.build_context(state)
        deliverables = {}

        for i, step in enumerate(self.pipeline_steps, 1):
            step_name = step["name"]
            instruction = step["instruction"]
            output_key = step["output_key"]

            logger.info(f"[{self.agent_id}] Pipeline etape {i}/{len(self.pipeline_steps)}: {step_name}")

            raw = self._call_llm(instruction, context, deliverables if deliverables else None)

            try:
                parsed = self.parse_response(raw)
                if output_key in parsed:
                    deliverables[output_key] = parsed[output_key]
                elif "deliverables" in parsed and output_key in parsed["deliverables"]:
                    deliverables[output_key] = parsed["deliverables"][output_key]
                else:
                    deliverables[output_key] = parsed
                logger.info(f"[{self.agent_id}] Etape {step_name}: OK ({output_key})")
            except json.JSONDecodeError as e:
                logger.error(f"[{self.agent_id}] Etape {step_name} JSON fail: {e}")
                deliverables[output_key] = {"raw": raw[:8000], "parse_error": str(e)[:100]}

        return {
            "agent_id": self.agent_id,
            "status": "complete",
            "confidence": 0.85,
            "deliverables": deliverables,
            "pipeline_steps_completed": len(self.pipeline_steps),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def _run_single(self, state):
        """Mode single-shot (comportement original)."""
        context = self.build_context(state)
        raw = self._call_llm(
            context.get("task", "Produis ton livrable complet."),
            context,
        )

        try:
            output = self.parse_response(raw)
        except json.JSONDecodeError as e:
            logger.error(f"[{self.agent_id}] JSON fail: {e}")
            output = {
                "agent_id": self.agent_id,
                "status": "complete",
                "confidence": 0.6,
                "deliverables": {"raw_output": raw[:8000]},
                "parse_note": str(e)[:100],
            }

        output["agent_id"] = self.agent_id
        output["timestamp"] = datetime.now(timezone.utc).isoformat()
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

            logger.info(f"[{self.agent_id}] Done — status={output.get('status')} conf={output.get('confidence')}")
            return state

        except Exception as e:
            logger.error(f"[{self.agent_id}] EXC: {e}", exc_info=True)
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
echo "[5/8] Agents specialistes..."

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
echo "[6/8] Orchestrateur..."
if wget -qO agents/orchestrator.py "${REPO_RAW}/prompts/orchestrator.py" 2>/dev/null && [ -s agents/orchestrator.py ]; then
    echo "  -> telecharge"
else
    echo "  -> conserve (local)"
fi

# ── 7. Gateway asynchrone ────────────────────
echo "[7/8] Gateway asynchrone..."

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
            await post_to_discord(
                channel_id,
                f"**{agent_id}** commence son travail...\nTache : {task[:200]}"
            )

            result_state = await asyncio.to_thread(agent_callable, dict(state))

            agent_output = result_state.get("agent_outputs", {}).get(agent_id, {})
            status = agent_output.get("status", "unknown")
            confidence = agent_output.get("confidence", "N/A")

            state["agent_outputs"] = result_state.get("agent_outputs", state.get("agent_outputs", {}))

            result_msg = f"**{agent_id}** termine — status={status}, confidence={confidence}\n"

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

            await post_to_discord(channel_id, result_msg)
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

# ── 8. Dockerfile + rebuild + validation ─────
echo "[8/8] Rebuild et validation..."

grep -q "COPY prompts/" Dockerfile 2>/dev/null || sed -i '/COPY config\//a COPY prompts/ ./prompts/' Dockerfile

docker compose up -d --build langgraph-api
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

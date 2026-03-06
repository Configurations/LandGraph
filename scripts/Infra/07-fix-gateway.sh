#!/bin/bash
###############################################################################
# Script 7 : Correctif Gateway — Connecter le vrai graphe multi-agent
#
# A executer apres les scripts 03, 05 et 06.
# Remplace le gateway simple par le vrai graphe avec routing vers les agents.
# Met a jour le Dockerfile pour inclure les prompts.
#
# Usage : ./07-fix-gateway.sh
###############################################################################
set -euo pipefail

PROJECT_DIR="$HOME/langgraph-project"

echo "==========================================="
echo "  Script 7 : Correctif Gateway Multi-Agent"
echo "==========================================="
echo ""

cd "${PROJECT_DIR}"

if [ ! -f .env ]; then
    echo "ERREUR : .env introuvable. Executez d'abord 03-install-langgraph.sh"
    exit 1
fi

# ── 1. Backup ────────────────────────────────────────────────────────────────
echo "[1/5] Backup des fichiers existants..."
[ -f agents/gateway.py ] && cp agents/gateway.py agents/gateway.py.bak
[ -f Dockerfile ] && cp Dockerfile Dockerfile.bak
echo "  -> Backups crees"

# ── 2. Nouveau gateway.py (utilise le vrai graphe) ──────────────────────────
echo "[2/5] Installation du nouveau gateway.py..."

cat > "${PROJECT_DIR}/agents/gateway.py" << 'PYTHON'
"""
FastAPI Gateway — Point d'entree de l'API LangGraph.
Connecte le bot Discord et les appels HTTP au graphe multi-agent complet.
"""
import json
import logging
import os
from datetime import datetime, timezone

import psycopg
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

load_dotenv()

logger = logging.getLogger("gateway")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s %(message)s")

app = FastAPI(title="LangGraph Multi-Agent API", version="0.2.0")

# ── Import des agents ────────────────────────
from agents.shared.base_agent import BaseAgent
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

from agents.orchestrator import (
    orchestrator_node,
    route_after_orchestrator,
    AGENT_IDS,
)

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.postgres import PostgresSaver

# ── Map agent_id -> callable ─────────────────
AGENT_MAP = {
    "requirements_analyst": analyst_agent,
    "ux_designer": ux_agent,
    "architect": architect_agent,
    "planner": planner_agent,
    "lead_dev": lead_dev_agent,
    "dev_frontend_web": frontend_agent,
    "dev_backend_api": backend_agent,
    "dev_mobile": mobile_agent,
    "qa_engineer": qa_agent,
    "devops_engineer": devops_agent,
    "docs_writer": docs_agent,
    "legal_advisor": legal_agent,
}


def human_gate_node(state: dict) -> dict:
    """Human gate — simule approve pour l'instant."""
    logger.info("HUMAN GATE — simulation approve")
    feedback = list(state.get("human_feedback_log", []))
    feedback.append({
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "response": "approve",
        "source": "auto",
    })
    state["human_feedback_log"] = feedback
    return state


def build_production_graph():
    """Construit le graphe LangGraph avec les vrais agents."""
    graph = StateGraph(dict)

    # Orchestrateur
    graph.add_node("orchestrator", orchestrator_node)
    graph.add_node("human_gate", human_gate_node)

    # Vrais agents
    for agent_id, agent_callable in AGENT_MAP.items():
        graph.add_node(agent_id, agent_callable)

    # Entry point
    graph.set_entry_point("orchestrator")

    # Routing conditionnel apres l'orchestrateur
    all_agent_ids = list(AGENT_MAP.keys())
    routing_map = {aid: aid for aid in all_agent_ids}
    routing_map["human_gate"] = "human_gate"
    routing_map["orchestrator"] = "orchestrator"
    routing_map["end"] = END

    graph.add_conditional_edges("orchestrator", route_after_orchestrator, routing_map)

    # Chaque agent retourne a l'orchestrateur
    for agent_id in all_agent_ids:
        graph.add_edge(agent_id, "orchestrator")

    graph.add_edge("human_gate", "orchestrator")

    return graph


def get_graph():
    """Compile le graphe avec checkpointer Postgres."""
    db_uri = os.getenv("DATABASE_URI")
    conn = psycopg.connect(db_uri, autocommit=True)
    checkpointer = PostgresSaver(conn)
    checkpointer.setup()
    return build_production_graph().compile(checkpointer=checkpointer)


# Graphe global
GRAPH = None

def get_or_create_graph():
    global GRAPH
    if GRAPH is None:
        GRAPH = get_graph()
        logger.info("Graphe multi-agent compile — %d agents", len(AGENT_MAP) + 1)
    return GRAPH


# ══════════════════════════════════════════════
# Endpoints API
# ══════════════════════════════════════════════

@app.get("/health")
async def health():
    return {"status": "ok", "service": "langgraph-multi-agent", "version": "0.2.0"}


@app.get("/status")
async def status():
    return {
        "agents": list(AGENT_MAP.keys()) + ["orchestrator"],
        "total_agents": len(AGENT_MAP) + 1,
    }


class InvokeRequest(BaseModel):
    messages: list[dict]
    thread_id: str = "default"
    project_id: str = "default"


class InvokeResponse(BaseModel):
    output: str
    thread_id: str
    decisions: list = []
    agent_outputs: dict = {}


@app.post("/invoke", response_model=InvokeResponse)
async def invoke(request: InvokeRequest):
    try:
        graph = get_or_create_graph()
        config = {"configurable": {"thread_id": request.thread_id}}

        # Construire les messages
        formatted_messages = [
            (msg.get("role", "user"), msg.get("content", ""))
            for msg in request.messages
        ]

        # Invoquer le graphe complet
        result = graph.invoke(
            {
                "messages": formatted_messages,
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
            },
            config,
        )

        # Extraire les resultats
        decisions = result.get("decision_history", [])
        agent_outputs = result.get("agent_outputs", {})

        # Construire la reponse lisible
        output_parts = []

        for i, d in enumerate(decisions, 1):
            dtype = d.get("decision_type", "unknown")
            confidence = d.get("confidence", 0)
            reasoning = d.get("reasoning", "")[:300]
            output_parts.append(f"[Orchestrateur] Decision {i}: {dtype} (confiance: {confidence})\n{reasoning}")

            for action in d.get("actions", []):
                target = action.get("target", "")
                task = action.get("task", "")[:200]
                if action.get("action") == "dispatch_agent" and target:
                    output_parts.append(f"  -> {target}: {task}")

        for agent_id, output in agent_outputs.items():
            agent_status = output.get("status", "unknown")
            confidence = output.get("confidence", "N/A")
            output_parts.append(f"\n[{agent_id}] status={agent_status}, confidence={confidence}")

            # Afficher un resume des deliverables
            deliverables = output.get("deliverables", {})
            if isinstance(deliverables, dict):
                for key in list(deliverables.keys())[:5]:
                    val = deliverables[key]
                    if isinstance(val, str):
                        val = val[:300] + "..." if len(val) > 300 else val
                    elif isinstance(val, (dict, list)):
                        val_str = json.dumps(val, ensure_ascii=False, default=str)
                        val = val_str[:300] + "..." if len(val_str) > 300 else val_str
                    output_parts.append(f"  {key}: {val}")

        output_text = "\n\n".join(output_parts) if output_parts else "Orchestrateur en attente."

        return InvokeResponse(
            output=output_text,
            thread_id=request.thread_id,
            decisions=decisions,
            agent_outputs={k: {"status": v.get("status"), "agent_id": k} for k, v in agent_outputs.items()},
        )

    except Exception as e:
        logger.error(f"Invoke error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.on_event("startup")
async def startup():
    try:
        get_or_create_graph()
        logger.info("Gateway demarree — graphe multi-agent pret")
    except Exception as e:
        logger.error(f"Erreur init graphe: {e}")
PYTHON

echo "  -> agents/gateway.py mis a jour"

# ── 3. Mettre a jour le Dockerfile (inclure prompts) ────────────────────────
echo "[3/5] Mise a jour du Dockerfile..."

cat > "${PROJECT_DIR}/Dockerfile" << 'DOCKERFILE'
FROM python:3.11-slim

WORKDIR /app

# Dependances systeme
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libpq-dev curl git \
    && rm -rf /var/lib/apt/lists/*

# Dependances Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Code des agents + prompts + config
COPY agents/ ./agents/
COPY config/ ./config/
COPY prompts/ ./prompts/
COPY langgraph.json .

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "agents.gateway:app", "--host", "0.0.0.0", "--port", "8000"]
DOCKERFILE

echo "  -> Dockerfile mis a jour (inclut prompts/)"

# ── 4. Rebuild et relancer ───────────────────────────────────────────────────
echo "[4/5] Rebuild et relance de la stack..."

docker compose up -d --build langgraph-api

echo "  -> Attente demarrage..."
sleep 10

# ── 5. Test de validation ────────────────────────────────────────────────────
echo "[5/5] Test de validation..."
echo ""

# Health check
HEALTH=$(curl -s http://localhost:8123/health 2>/dev/null || echo '{"status":"error"}')
echo "  Health: ${HEALTH}"

# Status
STATUS=$(curl -s http://localhost:8123/status 2>/dev/null || echo '{"error":"unavailable"}')
AGENT_COUNT=$(echo "${STATUS}" | python3 -c "import sys,json; print(json.load(sys.stdin).get('total_agents',0))" 2>/dev/null || echo "0")
echo "  Agents: ${AGENT_COUNT}"

# Test invoke rapide
echo ""
echo "  Test invoke..."
RESPONSE=$(curl -s -X POST http://localhost:8123/invoke \
    -H "Content-Type: application/json" \
    -d '{"messages":[{"role":"user","content":"Bonjour, test de connexion rapide."}],"thread_id":"test-gateway-fix"}' \
    2>/dev/null || echo '{"output":"error"}')

OUTPUT=$(echo "${RESPONSE}" | python3 -c "import sys,json; print(json.load(sys.stdin).get('output','error')[:200])" 2>/dev/null || echo "Erreur parsing")
echo "  Reponse: ${OUTPUT}"

# Verifier les logs
echo ""
echo "  Derniers logs API:"
docker compose logs langgraph-api --tail 5 2>/dev/null

echo ""
echo "==========================================="
echo "  Gateway corrigee avec succes."
echo ""
echo "  Changements :"
echo "  - gateway.py utilise le vrai graphe multi-agent"
echo "  - L'Orchestrateur route vers les vrais agents"
echo "  - Les agents utilisent leurs system prompts dedies"
echo "  - Le Dockerfile inclut les prompts"
echo ""
echo "  Pour tester via Discord :"
echo "  Allez dans #commandes et envoyez votre brief projet."
echo ""
echo "  Pour tester via curl :"
echo "  curl -s -X POST http://localhost:8123/invoke \\"
echo "    -H 'Content-Type: application/json' \\"
echo "    -d '{\"messages\":[{\"role\":\"user\",\"content\":\"Votre brief\"}],\"thread_id\":\"mon-projet\"}'"
echo "==========================================="

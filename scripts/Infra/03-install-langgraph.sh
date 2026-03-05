#!/bin/bash
###############################################################################
# Script 3/3 : Installation de LangGraph + Infrastructure de donnees
#
# A executer depuis la VM Ubuntu (apres le script 02).
# Usage : ./03-install-langgraph.sh
###############################################################################
set -euo pipefail

PROJECT_DIR="$HOME/langgraph-project"

echo "==========================================="
echo "  Script 3/3 : Installation LangGraph"
echo "==========================================="
echo ""

# ── Verification pre-requis ──────────────────────────────────────────────────
if ! command -v docker &> /dev/null; then
    echo "ERREUR : Docker n'est pas installe. Executez d'abord 02-install-docker.sh"
    exit 1
fi

if ! docker info &> /dev/null 2>&1; then
    echo "ERREUR : Docker n'est pas accessible. Avez-vous re-login apres le script 02 ?"
    exit 1
fi

# ── 1. Arborescence du projet ────────────────────────────────────────────────
echo "[1/7] Creation de l'arborescence du projet..."
mkdir -p "${PROJECT_DIR}"/{agents,config,data/backups,scripts,prompts/v1}
cd "${PROJECT_DIR}"

# ── 2. Fichier .env ─────────────────────────────────────────────────────────
echo "[2/7] Creation du fichier .env..."
if [ ! -f .env ]; then
    cat > .env << 'EOF'
# ── LLM ──────────────────────────────────────
ANTHROPIC_API_KEY=sk-ant-api03-VOTRE-CLE-ICI

# ── LangSmith (optionnel, pour le tracing) ───
LANGSMITH_API_KEY=lsv2-VOTRE-CLE-ICI
LANGCHAIN_TRACING_V2=true
LANGCHAIN_PROJECT=langgraph-multi-agent

# ── PostgreSQL ───────────────────────────────
POSTGRES_DB=langgraph
POSTGRES_USER=langgraph
POSTGRES_PASSWORD=CHANGEZ-MOI-EN-PROD

# ── Redis ────────────────────────────────────
REDIS_PASSWORD=CHANGEZ-MOI-AUSSI

# ── LangGraph ────────────────────────────────
DATABASE_URI=postgres://langgraph:CHANGEZ-MOI-EN-PROD@langgraph-postgres:5432/langgraph?sslmode=disable
REDIS_URI=redis://:CHANGEZ-MOI-AUSSI@langgraph-redis:6379/0
EOF
    chmod 600 .env
    echo "  -> .env cree. PENSEZ A MODIFIER LES VALEURS PAR DEFAUT !"
else
    echo "  -> .env existe deja, conservation du fichier existant."
fi

# Copie template
cp -n .env .env.example 2>/dev/null || true

# ── 3. Script SQL init ──────────────────────────────────────────────────────
echo "[3/7] Creation du schema PostgreSQL..."
cat > config/init.sql << 'SQL'
-- Extensions pour LangGraph + RAG
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Schema pour les artefacts projet
CREATE SCHEMA IF NOT EXISTS project;

-- Table de metadonnees des agents
CREATE TABLE IF NOT EXISTS project.agent_registry (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name VARCHAR(100) NOT NULL UNIQUE,
    description TEXT,
    system_prompt_version VARCHAR(50),
    config JSONB DEFAULT '{}',
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Table des artefacts produits par les agents
CREATE TABLE IF NOT EXISTS project.artifacts (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    agent_id UUID REFERENCES project.agent_registry(id),
    artifact_type VARCHAR(50) NOT NULL,
    content JSONB NOT NULL,
    version INTEGER DEFAULT 1,
    phase VARCHAR(50),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Index pour les recherches frequentes
CREATE INDEX IF NOT EXISTS idx_artifacts_agent ON project.artifacts(agent_id);
CREATE INDEX IF NOT EXISTS idx_artifacts_phase ON project.artifacts(phase);
CREATE INDEX IF NOT EXISTS idx_artifacts_type ON project.artifacts(artifact_type);
SQL

# ── 4. Docker Compose (stack complete) ───────────────────────────────────────
echo "[4/7] Creation du docker-compose.yml..."
cat > docker-compose.yml << 'YAML'

volumes:
  postgres-data:
    driver: local
  redis-data:
    driver: local

networks:
  langgraph-net:
    driver: bridge

services:
  # ── PostgreSQL 16 + pgvector ───────────────
  langgraph-postgres:
    image: pgvector/pgvector:pg16
    container_name: langgraph-postgres
    restart: unless-stopped
    ports:
      - "127.0.0.1:5432:5432"
    environment:
      POSTGRES_DB: ${POSTGRES_DB}
      POSTGRES_USER: ${POSTGRES_USER}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
    volumes:
      - postgres-data:/var/lib/postgresql/data
      - ./config/init.sql:/docker-entrypoint-initdb.d/init.sql
    command:
      - postgres
      - -c
      - shared_preload_libraries=vector
      - -c
      - max_connections=200
      - -c
      - shared_buffers=256MB
      - -c
      - effective_cache_size=1GB
      - -c
      - work_mem=16MB
    healthcheck:
      test: pg_isready -U ${POSTGRES_USER} -d ${POSTGRES_DB}
      interval: 10s
      timeout: 3s
      retries: 5
      start_period: 15s
    networks:
      - langgraph-net

  # ── Redis 7 ────────────────────────────────
  langgraph-redis:
    image: redis:7-alpine
    container_name: langgraph-redis
    restart: unless-stopped
    ports:
      - "127.0.0.1:6379:6379"
    command: >
      redis-server
      --requirepass ${REDIS_PASSWORD}
      --maxmemory 512mb
      --maxmemory-policy allkeys-lru
      --appendonly yes
    volumes:
      - redis-data:/data
    healthcheck:
      test: redis-cli -a ${REDIS_PASSWORD} ping
      interval: 5s
      timeout: 2s
      retries: 5
    networks:
      - langgraph-net

  # ── LangGraph Agent Server ─────────────────
  langgraph-api:
    build:
      context: .
      dockerfile: Dockerfile
    container_name: langgraph-api
    restart: unless-stopped
    ports:
      - "127.0.0.1:8123:8000"
    depends_on:
      langgraph-postgres:
        condition: service_healthy
      langgraph-redis:
        condition: service_healthy
    env_file:
      - .env
    environment:
      DATABASE_URI: ${DATABASE_URI}
      REDIS_URI: ${REDIS_URI}
    volumes:
      - ./agents:/app/agents
      - ./config:/app/config
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 5s
      retries: 3
      start_period: 20s
    networks:
      - langgraph-net
YAML

# ── 5. Dockerfile + requirements.txt ────────────────────────────────────────
echo "[5/7] Creation du Dockerfile et requirements.txt..."
cat > Dockerfile << 'DOCKERFILE'
FROM python:3.11-slim

WORKDIR /app

# Dependances systeme
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libpq-dev curl git \
    && rm -rf /var/lib/apt/lists/*

# Dependances Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Code des agents
COPY agents/ ./agents/
COPY config/ ./config/
COPY langgraph.json .

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "agents.gateway:app", "--host", "0.0.0.0", "--port", "8000"]
DOCKERFILE

cat > requirements.txt << 'TXT'
langgraph>=0.3.0
langgraph-checkpoint-postgres>=2.0.0
langchain-anthropic>=0.3.0
langchain-core>=0.3.0
langsmith>=0.2.0
anthropic>=0.40.0
pydantic>=2.0
psycopg[binary]>=3.2.0
psycopg-pool>=3.2.0
redis>=5.0.0
python-dotenv>=1.0.0
fastapi>=0.115.0
uvicorn>=0.32.0
TXT

# ── 6. Environnement Python local + agent de test ───────────────────────────
echo "[6/7] Installation de l'environnement Python local..."
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip -q
pip install -q \
  langgraph langgraph-checkpoint-postgres \
  langchain-anthropic langchain-core langsmith \
  anthropic pydantic 'psycopg[binary]' psycopg-pool \
  redis python-dotenv fastapi uvicorn

# Configuration LangGraph
cat > langgraph.json << 'JSON'
{
  "dependencies": ["."],
  "graphs": {
    "orchestrator": "./agents/orchestrator.py:graph"
  },
  "env": ".env"
}
JSON

# Agent orchestrateur minimal de test
cat > agents/__init__.py << 'PYTHON'
PYTHON

cat > agents/orchestrator.py << 'PYTHON'
"""
Orchestrateur minimal - valide que LangGraph + Anthropic + Postgres fonctionnent.
"""
import os
from dotenv import load_dotenv
from typing import TypedDict, Annotated
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
from langgraph.checkpoint.postgres import PostgresSaver
from langchain_anthropic import ChatAnthropic
from psycopg_pool import ConnectionPool

load_dotenv()

# ── State ────────────────────────────────────
class AgentState(TypedDict):
    messages: Annotated[list, add_messages]
    phase: str

# ── LLM ──────────────────────────────────────
llm = ChatAnthropic(
    model="claude-sonnet-4-5-20250929",
    max_tokens=2000,
    temperature=0.3,
)

# ── Nodes ────────────────────────────────────
def orchestrator(state: AgentState) -> dict:
    """Le noeud orchestrateur analyse et repond."""
    response = llm.invoke(state["messages"])
    return {"messages": [response]}

def should_continue(state: AgentState) -> str:
    """Decide si on continue ou on s'arrete."""
    last_message = state["messages"][-1]
    if hasattr(last_message, "tool_calls") and last_message.tool_calls:
        return "continue"
    return "end"

# ── Graph ────────────────────────────────────
workflow = StateGraph(AgentState)
workflow.add_node("orchestrator", orchestrator)
workflow.set_entry_point("orchestrator")
workflow.add_conditional_edges(
    "orchestrator",
    should_continue,
    {"continue": "orchestrator", "end": END},
)

# ── Compile avec checkpoint Postgres ─────────
DB_URI = os.getenv("DATABASE_URI")

def get_graph():
    """Factory pour obtenir le graphe compile."""
    pool = ConnectionPool(conninfo=DB_URI)
    checkpointer = PostgresSaver(pool)
    checkpointer.setup()
    return workflow.compile(checkpointer=checkpointer)

# ── Test direct ──────────────────────────────
if __name__ == "__main__":
    graph = get_graph()
    config = {"configurable": {"thread_id": "test-001"}}

    result = graph.invoke(
        {
            "messages": [("user", "Dis-moi bonjour et confirme que tu es operationnel.")],
            "phase": "test",
        },
        config,
    )

    print("\nReponse de l'agent :")
    print(result["messages"][-1].content)
    print("\nLangGraph est operationnel sur Proxmox !")
PYTHON

# .gitignore
cat > .gitignore << 'GIT'
.env
*.key
.venv/
__pycache__/
*.pyc
data/backups/
GIT

# ── 7. Demarrage de l'infrastructure ────────────────────────────────────────
echo "[7/7] Demarrage de PostgreSQL + Redis..."
docker compose up -d langgraph-postgres langgraph-redis

echo ""
echo "Attente que les services soient healthy..."
sleep 10

# Verification
echo ""
echo "--- Statut des containers ---"
docker compose ps
echo ""

# Test Postgres
if docker exec langgraph-postgres pg_isready -U langgraph -d langgraph &> /dev/null; then
    echo "  PostgreSQL : OK"
else
    echo "  PostgreSQL : EN ATTENTE (peut prendre quelques secondes)"
fi

# Test Redis
if docker exec langgraph-redis redis-cli -a "$(grep REDIS_PASSWORD .env | cut -d= -f2)" ping 2>/dev/null | grep -q PONG; then
    echo "  Redis      : OK"
else
    echo "  Redis      : EN ATTENTE (peut prendre quelques secondes)"
fi

echo ""
echo "==========================================="
echo "  LangGraph installe avec succes."
echo ""
echo "  Prochaines etapes :"
echo "  1. Editez .env avec vos vraies cles API :"
echo "     nano ${PROJECT_DIR}/.env"
echo ""
echo "  2. Testez l'agent orchestrateur :"
echo "     cd ${PROJECT_DIR}"
echo "     source .venv/bin/activate"
echo "     python agents/orchestrator.py"
echo ""
echo "  3. Pour la stack complete (avec l'API) :"
echo "     docker compose up -d"
echo ""
echo "  4. Pour l'observabilite (Langfuse) :"
echo "     Voir le fichier langgraph-proxmox-install.md"
echo "     section Phase 6"
echo "==========================================="

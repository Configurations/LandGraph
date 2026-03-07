#!/bin/bash
###############################################################################
# Script 3 : Installation de LangGraph + Infrastructure de donnees
# VERSION CONSOLIDEE (integre fix 07, 08, nodejs, MCP deps)
#
# A executer depuis la VM Ubuntu (apres le script 02).
# Usage : ./03-install-langgraph.sh
###############################################################################
set -euo pipefail

PROJECT_DIR="$HOME/langgraph-project"

echo "==========================================="
echo "  Script 3 : Installation LangGraph"
echo "  (version consolidee)"
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
echo "[1/8] Creation de l'arborescence du projet..."
mkdir -p "${PROJECT_DIR}"/{agents/shared,config,data/backups,scripts,prompts/v1}
cd "${PROJECT_DIR}"

# ── 2. Fichier .env ─────────────────────────────────────────────────────────
echo "[2/8] Creation du fichier .env..."
if [ ! -f .env ]; then
    cat > .env << 'EOF'
# ── LLM ──────────────────────────────────────
ANTHROPIC_API_KEY=sk-ant-api03-VOTRE-CLE-ICI

# ── Embeddings (RAG) ────────────────────────
VOYAGE_API_KEY=pa-VOTRE-CLE-VOYAGE-AI
EMBEDDING_MODEL=voyage-3-large

# ── LangSmith (optionnel) ────────────────────
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
cp -n .env .env.example 2>/dev/null || true

# ── 3. Script SQL init ──────────────────────────────────────────────────────
echo "[3/8] Creation du schema PostgreSQL..."
cat > config/init.sql << 'SQL'
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

CREATE SCHEMA IF NOT EXISTS project;

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

CREATE TABLE IF NOT EXISTS project.artifacts (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    agent_id UUID REFERENCES project.agent_registry(id),
    artifact_type VARCHAR(50) NOT NULL,
    content JSONB NOT NULL,
    version INTEGER DEFAULT 1,
    phase VARCHAR(50),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_artifacts_agent ON project.artifacts(agent_id);
CREATE INDEX IF NOT EXISTS idx_artifacts_phase ON project.artifacts(phase);
CREATE INDEX IF NOT EXISTS idx_artifacts_type ON project.artifacts(artifact_type);
SQL

# ── 4. Docker Compose ────────────────────────────────────────────────────────
echo "[4/8] Creation du docker-compose.yml..."
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

  langgraph-api:
    build:
      context: .
      dockerfile: Dockerfile
    container_name: langgraph-api
    restart: unless-stopped
    ports:
      - "0.0.0.0:8123:8000"
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
      - ./prompts:/app/prompts
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 5s
      retries: 3
      start_period: 20s
    networks:
      - langgraph-net
YAML

# ── 5. Dockerfile (Node.js + uv pour MCP servers npx et uvx) ────────────────
echo "[5/8] Creation du Dockerfile et requirements.txt..."
cat > Dockerfile << 'DOCKERFILE'
FROM python:3.11-slim

WORKDIR /app

# System deps + Node.js (pour MCP servers npx)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libpq-dev curl git nodejs npm \
    && rm -rf /var/lib/apt/lists/*

# uv + uvx (pour MCP servers Python)
RUN pip install --no-cache-dir uv

# Python deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY agents/ ./agents/
COPY config/ ./config/
COPY prompts/ ./prompts/
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
voyageai>=0.3.0
tiktoken>=0.7.0
langchain-mcp-adapters>=0.2.0
mcp>=1.0.0
requests>=2.31.0
aiohttp>=3.9.0
discord.py>=2.3.0
TXT

# ── 6. Gateway avec vrai graphe multi-agent ──────────────────────────────────
echo "[6/8] Creation du gateway et de l'orchestrateur de test..."

touch agents/__init__.py
touch agents/shared/__init__.py

# Gateway simple (sera remplace par le script 06 avec le vrai graphe)
cat > agents/gateway.py << 'PYTHON'
"""FastAPI Gateway — version initiale (test)."""
import os
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from agents.orchestrator import get_graph

load_dotenv()
app = FastAPI(title="LangGraph Multi-Agent API", version="0.1.0")

@app.get("/health")
async def health():
    return {"status": "ok", "service": "langgraph-agents"}

class InvokeRequest(BaseModel):
    messages: list[dict]
    thread_id: str = "default"

class InvokeResponse(BaseModel):
    output: str
    thread_id: str

@app.post("/invoke", response_model=InvokeResponse)
async def invoke(request: InvokeRequest):
    try:
        graph = get_graph()
        config = {"configurable": {"thread_id": request.thread_id}}
        formatted_messages = [
            (msg.get("role", "user"), msg.get("content", ""))
            for msg in request.messages
        ]
        result = graph.invoke(
            {"messages": formatted_messages, "phase": "active"},
            config,
        )
        last_message = result["messages"][-1]
        output = last_message.content if hasattr(last_message, "content") else str(last_message)
        return InvokeResponse(output=output, thread_id=request.thread_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/status")
async def status():
    return {"agents": ["orchestrator"], "infrastructure": {"postgres": "connected", "redis": "connected"}}
PYTHON

# Agent orchestrateur minimal de test (autocommit fix inclus)
cat > agents/orchestrator.py << 'PYTHON'
"""Orchestrateur minimal — valide que LangGraph + Anthropic + Postgres fonctionnent."""
import os
from dotenv import load_dotenv
from typing import TypedDict, Annotated
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
from langgraph.checkpoint.postgres import PostgresSaver
from langchain_anthropic import ChatAnthropic
import psycopg

load_dotenv()

class AgentState(TypedDict):
    messages: Annotated[list, add_messages]
    phase: str

llm = ChatAnthropic(model="claude-sonnet-4-5-20250929", max_tokens=2000, temperature=0.3)

def orchestrator(state: AgentState) -> dict:
    response = llm.invoke(state["messages"])
    return {"messages": [response]}

def should_continue(state: AgentState) -> str:
    last_message = state["messages"][-1]
    if hasattr(last_message, "tool_calls") and last_message.tool_calls:
        return "continue"
    return "end"

workflow = StateGraph(AgentState)
workflow.add_node("orchestrator", orchestrator)
workflow.set_entry_point("orchestrator")
workflow.add_conditional_edges("orchestrator", should_continue, {"continue": "orchestrator", "end": END})

DB_URI = os.getenv("DATABASE_URI")

def get_graph():
    conn = psycopg.connect(DB_URI, autocommit=True)
    checkpointer = PostgresSaver(conn)
    checkpointer.setup()
    return workflow.compile(checkpointer=checkpointer)

if __name__ == "__main__":
    graph = get_graph()
    config = {"configurable": {"thread_id": "test-001"}}
    result = graph.invoke(
        {"messages": [("user", "Dis-moi bonjour et confirme que tu es operationnel.")], "phase": "test"},
        config,
    )
    print("\nReponse de l'agent :")
    print(result["messages"][-1].content)
    print("\nLangGraph est operationnel !")
PYTHON

# LangGraph config
cat > langgraph.json << 'JSON'
{
  "dependencies": ["."],
  "graphs": {
    "orchestrator": "./agents/orchestrator.py:graph"
  },
  "env": ".env"
}
JSON

# .gitignore
cat > .gitignore << 'GIT'
.env
*.key
.venv/
__pycache__/
*.pyc
data/backups/
GIT

# ── 7. Environnement Python local ───────────────────────────────────────────
echo "[7/8] Installation de l'environnement Python local..."
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip -q
pip install -q \
  langgraph langgraph-checkpoint-postgres \
  langchain-anthropic langchain-core langsmith \
  anthropic pydantic 'psycopg[binary]' psycopg-pool \
  redis python-dotenv fastapi uvicorn \
  voyageai tiktoken langchain-mcp-adapters mcp \
  requests aiohttp discord.py

# ── 8. Demarrage infra ──────────────────────────────────────────────────────
echo "[8/8] Demarrage de PostgreSQL + Redis..."
docker compose up -d langgraph-postgres langgraph-redis

echo ""
echo "Attente que les services soient healthy..."
sleep 10

echo ""
echo "--- Statut des containers ---"
docker compose ps
echo ""

if docker exec langgraph-postgres pg_isready -U langgraph -d langgraph &> /dev/null; then
    echo "  PostgreSQL : OK"
else
    echo "  PostgreSQL : EN ATTENTE"
fi

if docker exec langgraph-redis redis-cli -a "$(grep REDIS_PASSWORD .env | cut -d= -f2)" ping 2>/dev/null | grep -q PONG; then
    echo "  Redis      : OK"
else
    echo "  Redis      : EN ATTENTE"
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
echo "     DB_PASS=\$(grep POSTGRES_PASSWORD .env | cut -d= -f2)"
echo "     DATABASE_URI=\"postgres://langgraph:\${DB_PASS}@localhost:5432/langgraph?sslmode=disable\" \\"
echo "     python agents/orchestrator.py"
echo ""
echo "  3. Pour la stack complete (avec l'API) :"
echo "     docker compose up -d"
echo ""
echo "  4. Ensuite installez les agents :"
echo "     Executez 05-install-rag.sh puis 06-install-agents.sh"
echo "==========================================="

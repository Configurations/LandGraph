#!/bin/bash
###############################################################################
# Script 3 : Installation de LangGraph + Infrastructure
# VERSION v2 — Telecharge tout depuis GitHub, zero heredoc
#
# A executer depuis la VM Ubuntu (apres le script 02).
# Usage : ./03-install-langgraph.sh
###############################################################################
set -euo pipefail

PROJECT_DIR="$HOME/langgraph-project"
REPO_RAW="https://raw.githubusercontent.com/Configurations/LandGraph/refs/heads/main"

echo "==========================================="
echo "  Script 3 : Installation LangGraph v2"
echo "==========================================="
echo ""

# ── Verification pre-requis ──────────────────
if ! command -v docker &> /dev/null; then
    echo "ERREUR : Docker non installe. Executez 02-install-docker.sh"
    exit 1
fi
if ! docker info &> /dev/null 2>&1; then
    echo "ERREUR : Docker non accessible. Re-login apres le script 02 ?"
    exit 1
fi

# ── 1. Arborescence ──────────────────────────
echo "[1/6] Arborescence..."
mkdir -p "${PROJECT_DIR}"/{agents/shared,config/Teams,scripts,data/backups,Shared/Teams}
mkdir -p /opt/langgraph-data/{postgres,redis}
cd "${PROJECT_DIR}"

# ── 2. Fichiers de config depuis GitHub ──────
echo "[2/6] Telechargement des fichiers de config..."

wget -qO docker-compose.yml "${REPO_RAW}/docker-compose.yml" 2>/dev/null || { echo "ERREUR: docker-compose.yml"; exit 1; }
wget -qO env.example "${REPO_RAW}/env.example" 2>/dev/null || { echo "ERREUR: env.example"; exit 1; }
wget -qO Dockerfile "${REPO_RAW}/Dockerfile" 2>/dev/null || { echo "ERREUR: Dockerfile"; exit 1; }
wget -qO Dockerfile.admin "${REPO_RAW}/Dockerfile.admin" 2>/dev/null || true
wget -qO Dockerfile.discord "${REPO_RAW}/Dockerfile.discord" 2>/dev/null || true
wget -qO requirements.txt "${REPO_RAW}/requirements.txt" 2>/dev/null || { echo "ERREUR: requirements.txt"; exit 1; }
wget -qO scripts/init.sql "${REPO_RAW}/scripts/init.sql" 2>/dev/null || { echo "ERREUR: init.sql"; exit 1; }
wget -qO Shared/Teams/llm_providers.json "${REPO_RAW}/Shared/Teams/llm_providers.json" 2>/dev/null || true
wget -qO Shared/Teams/mcp_servers.json "${REPO_RAW}/Shared/Teams/mcp_servers.json" 2>/dev/null || true
wget -qO Shared/Teams/teams.json "${REPO_RAW}/Shared/Teams/teams.json" 2>/dev/null || true
wget -qO Shared/Teams/mcp_catalog.csv "${REPO_RAW}/Shared/Teams/mcp_catalog.csv" 2>/dev/null || true
wget -qO config/.gitignore "${REPO_RAW}/gitignore" 2>/dev/null || true
wget -qO Shared/.gitignore "${REPO_RAW}/gitignore" 2>/dev/null || true

echo "  -> Fichiers telecharges"

# Scripts utilitaires (start, stop, restart, build)
for s in start.sh stop.sh restart.sh build.sh; do
    wget -qO "${s}" "${REPO_RAW}/${s}" 2>/dev/null || true
done
chmod +x start.sh stop.sh restart.sh build.sh
echo "  -> Scripts : start.sh, stop.sh, restart.sh, build.sh"

# ── 3. Fichier .env ──────────────────────────
echo "[3/6] Fichier .env..."
if [ ! -f .env ]; then
    cp env.example .env
    chmod 600 .env
    echo "  -> .env cree depuis le template. PENSEZ A MODIFIER LES VALEURS !"
else
    echo "  -> .env existe deja, conserve"
fi

# ── 4. Init Python ───────────────────────────
echo "[4/6] Touches Python..."
touch agents/__init__.py agents/shared/__init__.py


# ── 4b. Code Python agents ──────────────────
echo "[4b/6] Code Python agents..."

# Shared modules
SHARED_FILES=(base_agent.py agent_loader.py llm_provider.py rate_limiter.py mcp_client.py team_resolver.py workflow_engine.py human_gate.py agent_conversation.py discord_tools.py state.py __init__.py)
for f in "${SHARED_FILES[@]}"; do
    wget -qO "agents/shared/${f}" "${REPO_RAW}/Agents/Shared/${f}" 2>/dev/null || true
done

# Main agents
MAIN_FILES=(orchestrator.py gateway.py discord_listener.py)
for f in "${MAIN_FILES[@]}"; do
    wget -qO "agents/${f}" "${REPO_RAW}/Agents/${f}" 2>/dev/null || true
done


# ── 5. Environnement Python local ───────────
echo "[5/6] Environnement Python local..."
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip -q
pip install -q -r requirements.txt

# ── 6. Demarrage infra ──────────────────────
echo "[6/6] Demarrage PostgreSQL + Redis..."
docker compose up -d langgraph-postgres langgraph-redis

echo ""
echo "Attente des services..."
sleep 10

echo ""
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
echo "  LangGraph installe."
echo ""
echo "  Prochaines etapes :"
echo "  1. Editez .env : nano ${PROJECT_DIR}/.env"
echo "  2. Installez le RAG : ./05-install-rag.sh"
echo "  3. Installez les agents : ./06-install-agents.sh"
echo "  4. Configurez les MCP : ./14-install-mcp.sh"
echo "==========================================="

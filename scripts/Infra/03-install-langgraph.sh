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
mkdir -p "${PROJECT_DIR}"/{agents/shared,config,data/backups,prompts/v1}
mkdir -p /opt/langgraph-data/{postgres,redis}
cd "${PROJECT_DIR}"

# ── 2. Fichiers de config depuis GitHub ──────
echo "[2/6] Telechargement des fichiers de config..."

wget -qO docker-compose.yml "${REPO_RAW}/Configs/docker-compose.yml" 2>/dev/null || { echo "ERREUR: docker-compose.yml"; exit 1; }
wget -qO Dockerfile "${REPO_RAW}/Configs/Dockerfile" 2>/dev/null || { echo "ERREUR: Dockerfile"; exit 1; }
wget -qO Dockerfile.discord "${REPO_RAW}/scripts/Infra/Dockerfile.discord" 2>/dev/null || true
wget -qO requirements.txt "${REPO_RAW}/Configs/requirements.txt" 2>/dev/null || { echo "ERREUR: requirements.txt"; exit 1; }
wget -qO config/init.sql "${REPO_RAW}/Configs/init.sql" 2>/dev/null || { echo "ERREUR: init.sql"; exit 1; }
wget -qO langgraph.json "${REPO_RAW}/Configs/langgraph.json" 2>/dev/null || true
wget -qO .gitignore "${REPO_RAW}/Configs/gitignore" 2>/dev/null || true

echo "  -> Fichiers telecharges"

# ── 3. Fichier .env ──────────────────────────
echo "[3/6] Fichier .env..."
if [ ! -f .env ]; then
    wget -qO .env "${REPO_RAW}/Configs/env.example" 2>/dev/null || {
        echo "ERREUR: env.example non trouve"
        exit 1
    }
    chmod 600 .env
    echo "  -> .env cree depuis le template. PENSEZ A MODIFIER LES VALEURS !"
else
    echo "  -> .env existe deja, conserve"
fi

# ── 4. Init Python ───────────────────────────
echo "[4/6] Touches Python..."
touch agents/__init__.py agents/shared/__init__.py

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

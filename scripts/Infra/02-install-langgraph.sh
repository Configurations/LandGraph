#!/bin/bash
###############################################################################
# Script 3 : Installation de LangGraph + Infrastructure
# VERSION v3 — Telecharge tout depuis GitHub, zero heredoc
#
# A executer depuis la VM Ubuntu (apres le script 02).
# Usage : ./03-install-langgraph.sh
###############################################################################
set -euo pipefail

PROJECT_DIR="$HOME/langgraph-project"
REPO_RAW="https://raw.githubusercontent.com/Configurations/LandGraph/refs/heads/main"

echo "=================================================================="
echo "  Script 3 : Installation LangGraph v3     version 8 - 2026-03    "
echo "=================================================================="
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
echo "[1/7] Arborescence..."
mkdir -p "${PROJECT_DIR}"/{agents/shared,config/Teams,scripts,data/backups,Shared/Teams}
mkdir -p /opt/langgraph-data/{postgres,redis,openlit-clickhouse,openlit}
cd "${PROJECT_DIR}"

# ── 2. Fichiers de config depuis GitHub ──────
echo "[2/7] Telechargement des fichiers de config..."

wget -qO docker-compose.yml "${REPO_RAW}/docker-compose.yml" 2>/dev/null || { echo "ERREUR: docker-compose.yml"; exit 1; }
wget -qO env.example "${REPO_RAW}/env.example" 2>/dev/null || { echo "ERREUR: env.example"; exit 1; }
wget -qO Dockerfile "${REPO_RAW}/Dockerfile" 2>/dev/null || { echo "ERREUR: Dockerfile"; exit 1; }
wget -qO Dockerfile.admin "${REPO_RAW}/Dockerfile.admin" 2>/dev/null || true
wget -qO Dockerfile.discord "${REPO_RAW}/Dockerfile.discord" 2>/dev/null || true
wget -qO Dockerfile.mail "${REPO_RAW}/Dockerfile.mail" 2>/dev/null || true
wget -qO requirements.txt "${REPO_RAW}/requirements.txt" 2>/dev/null || { echo "ERREUR: requirements.txt"; exit 1; }

wget -qO scripts/init.sql "${REPO_RAW}/scripts/init.sql" 2>/dev/null || { echo "ERREUR: init.sql"; exit 1; }

wget -qO Shared/Teams/llm_providers.json "${REPO_RAW}/Shared/Teams/llm_providers.json" 2>/dev/null || true
wget -qO Shared/Teams/mcp_servers.json "${REPO_RAW}/Shared/Teams/mcp_servers.json" 2>/dev/null || true
wget -qO Shared/Teams/teams.json "${REPO_RAW}/Shared/Teams/teams.json" 2>/dev/null || true
wget -qO Shared/Teams/mcp_catalog.csv "${REPO_RAW}/Shared/Teams/mcp_catalog.csv" 2>/dev/null || true
wget -qO Shared/Teams/.gitignore "${REPO_RAW}/gitignore"  2>/dev/null || { echo "ERREUR: gitignore"; exit 1; }
wget -qO config/Teams/.gitignore "${REPO_RAW}/gitignore" 2>/dev/null || { echo "ERREUR: gitignore"; exit 1; }


[ -f config/langgraph.json ] || wget -qO config/langgraph.json "${REPO_RAW}/config/langgraph.json" 2>/dev/null || { echo "ERREUR: langgraph.json"; exit 1; }
[ -f config/mail.json ]      || wget -qO config/mail.json "${REPO_RAW}/config/mail.json" 2>/dev/null || { echo "ERREUR: mail.json"; exit 1; }
[ -f config/discord.json ]   || wget -qO config/discord.json "${REPO_RAW}/config/discord.json" 2>/dev/null || { echo "ERREUR: discord.json"; exit 1; }

echo "  -> Fichiers telecharges"


# Scripts utilitaires (start, stop, restart, build)
for s in start.sh stop.sh restart.sh build.sh update.sh; do
wget -qO "${s}" "${REPO_RAW}/${s}" 2>/dev/null || true
done
chmod +x start.sh stop.sh restart.sh build.sh  update.sh
echo "  -> Scripts : start.sh, stop.sh, restart.sh, build.sh  update.sh"

# ── 3. Fichier .env ──────────────────────────
echo "[3/7] Fichier .env..."
if [ ! -f .env ]; then
    cp env.example .env
    chmod 600 .env
    echo "  -> .env cree depuis le template. PENSEZ A MODIFIER LES VALEURS !"
else
    echo "  -> .env existe deja, conserve"
fi

# ── 4. Init Python ───────────────────────────
echo "[4/7] Touches Python..."
touch agents/__init__.py agents/shared/__init__.py


# ── 4b. Code Python agents ──────────────────
echo "[4b/7] Code Python agents..."

# Shared modules
SHARED_FILES=(base_agent.py agent_loader.py llm_provider.py rate_limiter.py mcp_client.py mcp_auth.py mcp_server.py team_resolver.py workflow_engine.py channels.py human_gate.py agent_conversation.py discord_tools.py event_bus.py state.py __init__.py)
for f in "${SHARED_FILES[@]}"; do
    wget -qO "agents/shared/${f}" "${REPO_RAW}/Agents/Shared/${f}" 2>/dev/null || true
done

# Main agents
MAIN_FILES=(orchestrator.py gateway.py discord_listener.py mail_listener.py)
for f in "${MAIN_FILES[@]}"; do
    wget -qO "agents/${f}" "${REPO_RAW}/Agents/${f}" 2>/dev/null || true
done

echo "  -> Code agents telecharge"

# ── 4c. Admin web ────────────────────────────
echo "[4c/7] Admin web..."
mkdir -p web/static/css web/static/js
wget -qO web/requirements.txt "${REPO_RAW}/web/requirements.txt" 2>/dev/null || true
wget -qO web/server.py "${REPO_RAW}/web/server.py" 2>/dev/null || true
wget -qO web/static/index.html "${REPO_RAW}/web/static/index.html" 2>/dev/null || true
wget -qO web/static/css/style.css "${REPO_RAW}/web/static/css/style.css" 2>/dev/null || true
wget -qO web/static/js/app.js "${REPO_RAW}/web/static/js/app.js" 2>/dev/null || true
echo "  -> Admin web telecharge"

# ── 4d. Config globale ───────────────────────
echo "[4d/7] Config globale..."

# Copier les fichiers globaux dans config/ (team_resolver les cherche ici)
cp Shared/Teams/teams.json config/teams.json 2>/dev/null || true
cp Shared/Teams/llm_providers.json config/llm_providers.json 2>/dev/null || true
cp Shared/Teams/mcp_servers.json config/mcp_servers.json 2>/dev/null || true

# config/ — fichiers par defaut si absents
[ ! -f config/agent_mcp_access.json ] && echo '{}' > config/agent_mcp_access.json
[ ! -f config/webhooks.json ] && echo '{"webhooks":[]}' > config/webhooks.json

echo "  -> Config globale OK"


# ── 5. Environnement Python local ───────────
echo "[5/7] Environnement Python local..."
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip -q
pip install -q -r requirements.txt

# ── 6. Demarrage infra ──────────────────────
echo "[6/7] Demarrage PostgreSQL + Redis..."
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

# ── 7. Demarrage complet ────────────────────
echo "[7/7] build..."
./build.sh

echo ""
sleep 12
docker compose ps
echo ""

# Verification
if curl -sf http://localhost:8123/health > /dev/null 2>&1; then
    echo "  API        : OK"
else
    echo "  API        : EN ATTENTE"
fi
if curl -sf http://localhost:8080/ > /dev/null 2>&1; then
    echo "  Admin web  : OK"
else
    echo "  Admin web  : EN ATTENTE"
fi
if curl -sf http://localhost:8090/ > /dev/null 2>&1; then
    echo "  hitl web  : OK"
else
    echo "  hitl web  : EN ATTENTE"
fi
if curl -sf http://localhost:3000/ > /dev/null 2>&1; then
    echo "  OpenLIT    : OK"
else
    echo "  OpenLIT    : EN ATTENTE"
fi

echo ""
echo "==========================================="
echo "  LangGraph installe."
echo ""
echo "  Prochaines etapes :"
echo "  1. Editez .env : nano ${PROJECT_DIR}/.env"
echo "     (ANTHROPIC_API_KEY, DISCORD_BOT_TOKEN, mots de passe)"
echo "  2. Redemarrez : ./restart.sh"
echo "  3. Accedez au dashboard : http://<IP>:8080"
echo "  4. Creez votre premiere equipe depuis le dashboard"
echo ""
echo "  Optionnel :"
echo "  - RAG : ./03-install-rag.sh"
echo "==========================================="

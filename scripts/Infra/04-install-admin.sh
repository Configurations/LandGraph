#!/bin/bash
###############################################################################
# Script 15 : Installation du panneau d'administration web LandGraph
#
# A executer depuis la VM Ubuntu (apres le script 03).
# Usage : ./15-install-admin.sh
###############################################################################
set -euo pipefail

PROJECT_DIR="$HOME/langgraph-project"
REPO_RAW="https://raw.githubusercontent.com/Configurations/LandGraph/refs/heads/main"

echo "==========================================="
echo "  Script 15 : Installation Admin Web"
echo "==========================================="
echo ""

# ── Verification pre-requis ──────────────────
if [ ! -d "${PROJECT_DIR}" ]; then
    echo "ERREUR : ${PROJECT_DIR} n'existe pas. Executez 03-install-langgraph.sh d'abord."
    exit 1
fi

cd "${PROJECT_DIR}"

# ── 1. Telecharger les fichiers web ──────────
echo "[1/4] Telechargement des fichiers admin web..."
mkdir -p web/static/css web/static/js

wget -qO Dockerfile.admin "${REPO_RAW}/Dockerfile.admin" 2>/dev/null || { echo "ERREUR: Dockerfile.admin"; exit 1; }
wget -qO web/requirements.txt "${REPO_RAW}/web/requirements.txt" 2>/dev/null || { echo "ERREUR: web/requirements.txt"; exit 1; }
wget -qO web/server.py "${REPO_RAW}/web/server.py" 2>/dev/null || { echo "ERREUR: web/server.py"; exit 1; }
wget -qO web/static/index.html "${REPO_RAW}/web/static/index.html" 2>/dev/null || { echo "ERREUR: index.html"; exit 1; }
wget -qO web/static/css/style.css "${REPO_RAW}/web/static/css/style.css" 2>/dev/null || { echo "ERREUR: style.css"; exit 1; }
wget -qO web/static/js/app.js "${REPO_RAW}/web/static/js/app.js" 2>/dev/null || { echo "ERREUR: app.js"; exit 1; }

echo "  -> Fichiers telecharges"

# ── 2. Mettre a jour docker-compose.yml ──────
echo "[2/4] Mise a jour docker-compose.yml..."
wget -qO docker-compose.yml "${REPO_RAW}/docker-compose.yml" 2>/dev/null || { echo "ERREUR: docker-compose.yml"; exit 1; }
echo "  -> docker-compose.yml mis a jour"

# ── 3. Configs et repertoires (avant Docker) ──
echo "[3/4] Preparation configs et repertoires..."

# Creer les repertoires AVANT le demarrage Docker
# (sinon le bind mount .:/project ne voit pas les sous-repertoires)
mkdir -p config/Teams
mkdir -p Shared/Teams

# config/Teams — fichiers par defaut si absents
if [ ! -f config/Teams/mcp_servers.json ]; then
    echo '{"servers": {}}' > config/Teams/mcp_servers.json
    echo "  -> config/Teams/mcp_servers.json cree"
fi
if [ ! -f config/Teams/agent_mcp_access.json ]; then
    echo '{}' > config/Teams/agent_mcp_access.json
    echo "  -> config/Teams/agent_mcp_access.json cree"
fi
if [ ! -f config/Teams/llm_providers.json ]; then
    echo '{"providers": {}, "default": ""}' > config/Teams/llm_providers.json
    echo "  -> config/Teams/llm_providers.json cree"
fi
if [ ! -f config/Teams/teams.json ]; then
    echo '{"teams": {}, "channel_mapping": {}}' > config/Teams/teams.json
    echo "  -> config/Teams/teams.json cree"
fi

# Shared/Teams — telecharger depuis GitHub
wget -qO Shared/Teams/mcp_catalog.csv "${REPO_RAW}/Shared/Teams/mcp_catalog.csv" 2>/dev/null || true
wget -qO Shared/Teams/llm_providers.json "${REPO_RAW}/Shared/Teams/llm_providers.json" 2>/dev/null || true
wget -qO Shared/Teams/mcp_servers.json "${REPO_RAW}/Shared/Teams/mcp_servers.json" 2>/dev/null || true
wget -qO Shared/Teams/teams.json "${REPO_RAW}/Shared/Teams/teams.json" 2>/dev/null || true
echo "  -> config/Teams/ et Shared/Teams/ prets"

# ── 4. Build et demarrage ────────────────────
echo "[4/4] Build et demarrage du conteneur admin..."
docker compose stop langgraph-admin 2>/dev/null || true
docker compose rm -f langgraph-admin 2>/dev/null || true
docker compose build --no-cache langgraph-admin
docker compose up -d langgraph-admin

echo ""
sleep 5
docker compose ps langgraph-admin
echo ""

# Verification
if curl -sf http://localhost:8080/ > /dev/null 2>&1; then
    echo "  Admin web : OK"
else
    echo "  Admin web : en attente de demarrage..."
fi

echo ""
echo "==========================================="
echo "  Admin web installe !"
echo ""
echo "  Acces : http://<IP-VM>:8080"
echo ""
echo "  IMPORTANT : Pensez a securiser l'acces"
echo "  (firewall, reverse proxy avec auth, etc.)"
echo "==========================================="

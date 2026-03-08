#!/bin/bash
###############################################################################
# Script 6 : Installation des agents LangGraph
# VERSION v4 — Registry JSON + loader dynamique
#
# Les agents sont definis dans Configs/agents_registry.json
# Le code est telecharge depuis Agents/ sur GitHub
#
# Usage : ./06-install-agents.sh
###############################################################################
set -euo pipefail

PROJECT_DIR="$HOME/langgraph-project"
REPO_RAW="https://raw.githubusercontent.com/Configurations/LandGraph/refs/heads/main"

echo "==========================================="
echo "  Script 6 : Installation des agents v4"
echo "==========================================="
echo ""

cd "${PROJECT_DIR}"
[ ! -f .env ] && echo "ERREUR : .env introuvable." && exit 1

# ── 1. Structure ─────────────────────────────
echo "[1/7] Structure..."
mkdir -p agents/shared prompts/v1 config
touch agents/__init__.py agents/shared/__init__.py

# ── 2. Prompts ───────────────────────────────
echo "[2/7] Prompts..."
PROMPTS=(orchestrator requirements_analyst ux_designer architect planner lead_dev dev_frontend_web dev_backend_api dev_mobile qa_engineer devops_engineer docs_writer legal_advisor)
DL=0
for name in "${PROMPTS[@]}"; do
    T="prompts/v1/${name}.md"
    if wget -qO "$T" "${REPO_RAW}/prompts/${name}.md" 2>/dev/null && [ -s "$T" ]; then DL=$((DL+1))
    elif wget -qO "$T" "${REPO_RAW}/prompts/v1/${name}.md" 2>/dev/null && [ -s "$T" ]; then DL=$((DL+1))
    else echo "Tu es ${name}, agent LangGraph. Reponds en JSON: {agent_id, status, confidence, deliverables}." > "$T"; fi
done
echo "  -> ${DL}/${#PROMPTS[@]} prompts"

# ── 3. Config (agents_registry.json) ─────────
echo "[3/7] Config..."
wget -qO config/agents_registry.json "${REPO_RAW}/Configs/agents_registry.json" 2>/dev/null || echo "  -> agents_registry.json: conserve local"
wget -qO config/llm_providers.json "${REPO_RAW}/Configs/llm_providers.json" 2>/dev/null || echo "  -> llm_providers.json: conserve local"
wget -qO config/teams.json "${REPO_RAW}/Configs/teams.json" 2>/dev/null || echo "  -> teams.json: conserve local"
AGENT_COUNT=$(python3 -c "import json;print(len(json.load(open('config/agents_registry.json')).get('agents',{})))" 2>/dev/null || echo 0)
echo "  -> ${AGENT_COUNT} agents dans le registry"

# ── 4. Code Python (Shared + gateway + discord) ─
echo "[4/7] Code Python..."
SHARED_FILES=(base_agent.py mcp_client.py agent_loader.py state.py discord_tools.py human_gate.py agent_conversation.py rate_limiter.py llm_provider.py __init__.py)
for f in "${SHARED_FILES[@]}"; do
    wget -qO "agents/shared/${f}" "${REPO_RAW}/Agents/Shared/${f}" 2>/dev/null || true
done

MAIN_FILES=(orchestrator.py gateway.py discord_listener.py)
for f in "${MAIN_FILES[@]}"; do
    wget -qO "agents/${f}" "${REPO_RAW}/Agents/${f}" 2>/dev/null || echo "  -> ${f}: non trouve"
done
echo "  -> Code telecharge"

# ── 5. Discord ───────────────────────────────
echo "[5/7] Discord..."

wget -qO Dockerfile.discord "${REPO_RAW}/scripts/Infra/Dockerfile.discord" 2>/dev/null || \
cat > Dockerfile.discord << 'DKFILE'
FROM python:3.11-slim
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY agents/ ./agents/
COPY config/ ./config/
COPY prompts/ ./prompts/
CMD ["python", "agents/discord_listener.py"]
DKFILE

if ! grep -q "discord-bot" docker-compose.yml 2>/dev/null; then
    cat >> docker-compose.yml << 'YAML'

  discord-bot:
    build:
      context: .
      dockerfile: Dockerfile.discord
    container_name: langgraph-discord
    restart: unless-stopped
    depends_on:
      langgraph-api:
        condition: service_healthy
    env_file:
      - .env
    environment:
      LANGGRAPH_API_URL: http://langgraph-api:8000
    networks:
      - langgraph-net
YAML
    echo "  -> discord-bot ajoute"
fi

if ! grep -q "DISCORD_BOT_TOKEN" .env; then
    cat >> .env << 'EOF'

# ── Discord ──────────────────────────────────
DISCORD_BOT_TOKEN=VOTRE-TOKEN-BOT
DISCORD_CHANNEL_COMMANDS=ID-CHANNEL-COMMANDES
DISCORD_CHANNEL_LOGS=ID-CHANNEL-LOGS
DISCORD_CHANNEL_ALERTS=ID-CHANNEL-ALERTS
DISCORD_CHANNEL_REVIEW=ID-CHANNEL-REVIEW
DISCORD_GUILD_ID=ID-SERVEUR
EOF
    echo "  -> Variables Discord ajoutees (a remplir !)"
fi

# ── 6. Dependencies ──────────────────────────
echo "[6/7] Dependencies..."
for dep in "requests>=2.31.0" "aiohttp>=3.9.0" "discord.py>=2.3.0" "langchain-mcp-adapters>=0.2.0" "mcp>=1.0.0"; do
    grep -q "$(echo $dep | cut -d'>' -f1)" requirements.txt 2>/dev/null || echo "$dep" >> requirements.txt
done
grep -q "COPY prompts/" Dockerfile 2>/dev/null || sed -i '/COPY config\//a COPY prompts/ ./prompts/' Dockerfile

# ── 7. Rebuild ───────────────────────────────
echo "[7/7] Rebuild..."
docker compose up -d --build langgraph-api discord-bot
sleep 12

H=$(curl -s http://localhost:8123/health 2>/dev/null || echo error)
S=$(curl -s http://localhost:8123/status 2>/dev/null | python3 -c "import sys,json;print(json.load(sys.stdin).get('total_agents',0))" 2>/dev/null || echo 0)

echo ""
echo "  Health: ${H} | Agents: ${S}"
echo ""
echo "  Pour ajouter un agent : editez config/agents_registry.json"
echo "  Pour ajouter un prompt : ajoutez prompts/v1/<agent_id>.md"
echo ""
echo "  Commandes Discord :"
echo "    !agent lead_dev Cree un repo GitHub"
echo "    !a avocat Audit RGPD"
echo "    !status / !new MonProjet"
echo ""
echo "==========================================="

#!/bin/bash
###############################################################################
# Script 6 : Installation des agents LangGraph (equipe complete)
# VERSION CONSOLIDEE v2 (integre 04+07+08+09+10+11+13+15+16)
#
# A executer depuis la VM Ubuntu (apres les scripts 03 et 05).
# Usage : ./06-install-agents.sh
###############################################################################
set -euo pipefail

PROJECT_DIR="$HOME/langgraph-project"
REPO_RAW="https://raw.githubusercontent.com/Configurations/LandGraph/refs/heads/main"

echo "==========================================="
echo "  Script 6 : Installation des agents v2"
echo "==========================================="
echo ""

cd "${PROJECT_DIR}"
[ ! -f .env ] && echo "ERREUR : .env introuvable." && exit 1

# ── 1. Structure ─────────────────────────────
echo "[1/9] Structure..."
mkdir -p agents/shared prompts/v1 config
touch agents/__init__.py agents/shared/__init__.py

# ── 2. Prompts ───────────────────────────────
echo "[2/9] Prompts..."
PROMPTS=(orchestrator requirements_analyst ux_designer architect planner lead_dev dev_frontend_web dev_backend_api dev_mobile qa_engineer devops_engineer docs_writer legal_advisor)
DL=0
for name in "${PROMPTS[@]}"; do
    T="prompts/v1/${name}.md"
    if wget -qO "$T" "${REPO_RAW}/prompts/${name}.md" 2>/dev/null && [ -s "$T" ]; then DL=$((DL+1))
    elif wget -qO "$T" "${REPO_RAW}/prompts/v1/${name}.md" 2>/dev/null && [ -s "$T" ]; then DL=$((DL+1))
    else echo "Tu es ${name}, agent LangGraph. Reponds en JSON: {agent_id, status, confidence, deliverables}." > "$T"; fi
done
echo "  -> ${DL}/${#PROMPTS[@]} prompts"

# ── 3. ProjectState ──────────────────────────
echo "[3/9] ProjectState..."
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

# ── 4. Telechargement des modules Python ─────
echo "[4/9] Modules Python (BaseAgent, gateway, discord, mcp_client)..."

# BaseAgent
wget -qO agents/shared/base_agent.py "${REPO_RAW}/Agents/shared/base_agent.py" 2>/dev/null || echo "  -> base_agent.py: utilise local"
# MCP Client
wget -qO agents/shared/mcp_client.py "${REPO_RAW}/Agents/shared/mcp_client.py" 2>/dev/null || echo "  -> mcp_client.py: utilise local"
# Discord tools
wget -qO agents/shared/discord_tools.py "${REPO_RAW}/Agents/shared/discord_tools.py" 2>/dev/null || true
# Gateway
wget -qO agents/gateway.py "${REPO_RAW}/Agents/gateway.py" 2>/dev/null || echo "  -> gateway.py: utilise local"
# Discord listener
wget -qO agents/discord_listener.py "${REPO_RAW}/Agents/discord_listener.py" 2>/dev/null || echo "  -> discord_listener.py: utilise local"

echo "  -> Modules telecharges"

# ── 5. Agents specialistes ───────────────────
echo "[5/9] Agents..."

# Analyste pipeline 3 etapes
cat > agents/requirements_analyst.py << 'PYTHON'
"""Analyste — Pipeline 3 etapes."""
from agents.shared.base_agent import BaseAgent
class AnalystAgent(BaseAgent):
    agent_id = "requirements_analyst"; agent_name = "Analyste"
    default_temperature = 0.3; default_max_tokens = 32768; prompt_filename = "requirements_analyst.md"
    pipeline_steps = [
        {"name":"PRD","output_key":"prd","instruction":"Produis le PRD en JSON. Sections: context_and_problem, objectives, personas, scope, functional_requirements, non_functional_requirements, constraints, assumptions_and_risks, glossary. Format: {\"prd\": {...}}"},
        {"name":"User Stories","output_key":"user_stories","instruction":"A partir du PRD, genere les User Stories INVEST. Chaque: id, persona, action, benefit, acceptance_criteria (Given/When/Then). Format: {\"user_stories\": [...]}"},
        {"name":"MoSCoW","output_key":"moscow_matrix","instruction":"Classe chaque User Story en MoSCoW avec justification. Format: {\"moscow_matrix\": {\"must_have\":[...], \"should_have\":[...], \"could_have\":[...], \"wont_have\":[...]}}"},
    ]
    def build_context(self, state):
        return {"project_phase":state.get("project_phase","discovery"),"project_metadata":state.get("project_metadata",{}),"brief":self._extract_brief(state),"task":self._extract_task(state),"existing_outputs":list(state.get("agent_outputs",{}).keys())}
agent = AnalystAgent()
PYTHON

# Avocat pipeline 2 etapes
cat > agents/legal_advisor.py << 'PYTHON'
"""Avocat — Pipeline 2 etapes."""
from agents.shared.base_agent import BaseAgent
class LegalAdvisorAgent(BaseAgent):
    agent_id = "legal_advisor"; agent_name = "Avocat"
    default_temperature = 0.2; default_max_tokens = 32768; prompt_filename = "legal_advisor.md"
    pipeline_steps = [
        {"name":"Audit reglementaire","output_key":"regulatory_audit","instruction":"Audit: juridictions, reglementations, donnees sensibles, consentement, risques. Disclaimer obligatoire. Format: {\"regulatory_audit\": {...}}"},
        {"name":"Alertes","output_key":"alerts","instruction":"Alertes: info/warning/critical. Critical = bloquant. Format: {\"alerts\": [{\"level\":\"...\",\"category\":\"...\",\"description\":\"...\",\"recommendation\":\"...\"}]}"},
    ]
    def build_context(self, state):
        o = state.get("agent_outputs", {})
        return {"project_phase":state.get("project_phase","discovery"),"brief":self._extract_brief(state),"task":self._extract_task(state),
                "prd":o.get("requirements_analyst",{}).get("deliverables",{}).get("prd"),"user_stories":o.get("requirements_analyst",{}).get("deliverables",{}).get("user_stories")}
agent = LegalAdvisorAgent()
PYTHON

# Autres agents single-shot
for AD in \
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
  IFS=':' read -r AID ANAME ATEMP AMAX APROMPT <<< "${AD}"
  cat > "agents/${AID}.py" << PYEOF
"""${ANAME}"""
from agents.shared.base_agent import BaseAgent
class Agent(BaseAgent):
    agent_id = "${AID}"; agent_name = "${ANAME}"
    default_temperature = ${ATEMP}; default_max_tokens = ${AMAX}; prompt_filename = "${APROMPT}"
    def build_context(self, state):
        o = state.get("agent_outputs", {})
        return {"project_phase":state.get("project_phase","unknown"),"project_metadata":state.get("project_metadata",{}),"brief":self._extract_brief(state),"task":self._extract_task(state),"existing_outputs":list(o.keys()),
                "relevant_outputs":{k:{"status":v.get("status"),"keys":list(v.get("deliverables",{}).keys())} for k,v in o.items() if v.get("status")=="complete"}}
agent = Agent()
PYEOF
done
echo "  -> 12 agents"

# ── 6. Orchestrateur ─────────────────────────
echo "[6/9] Orchestrateur..."
wget -qO agents/orchestrator.py "${REPO_RAW}/prompts/orchestrator.py" 2>/dev/null || echo "  -> conserve local"

# ── 7. Discord config ────────────────────────
echo "[7/9] Discord config..."

# Dockerfile.discord
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

# Ajouter discord-bot au docker-compose si absent
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

# Variables Discord
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

# ── 8. Dependencies ──────────────────────────
echo "[8/9] Dependencies..."
for dep in "requests>=2.31.0" "aiohttp>=3.9.0" "discord.py>=2.3.0" "langchain-mcp-adapters>=0.2.0" "mcp>=1.0.0"; do
    grep -q "$(echo $dep | cut -d'>' -f1)" requirements.txt 2>/dev/null || echo "$dep" >> requirements.txt
done

# ── 9. Rebuild ───────────────────────────────
echo "[9/9] Rebuild..."
grep -q "COPY prompts/" Dockerfile 2>/dev/null || sed -i '/COPY config\//a COPY prompts/ ./prompts/' Dockerfile

docker compose up -d --build langgraph-api discord-bot
sleep 12

H=$(curl -s http://localhost:8123/health 2>/dev/null || echo error)
S=$(curl -s http://localhost:8123/status 2>/dev/null | python3 -c "import sys,json;print(json.load(sys.stdin).get('total_agents',0))" 2>/dev/null || echo 0)

echo ""
echo "  Health: ${H} | Agents: ${S}"
echo ""
echo "  Commandes Discord :"
echo "    !agent lead_dev Cree un repo GitHub"
echo "    !agent analyste Produis le PRD"
echo "    !a avocat Audit RGPD"
echo "    !status / !new MonProjet"
echo ""
echo "==========================================="

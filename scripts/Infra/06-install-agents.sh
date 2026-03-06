#!/bin/bash
###############################################################################
# Script 6 : Installation des agents LangGraph (equipe complete)
#
# A executer depuis la VM Ubuntu (apres les scripts 03 et 05).
# Installe les 10 agents + 3 sous-agents + structure partagee.
#
# Usage : ./06-install-agents.sh
###############################################################################
set -euo pipefail

PROJECT_DIR="$HOME/langgraph-project"
REPO_RAW="https://raw.githubusercontent.com/Configurations/LandGraph/refs/heads/main"

echo "==========================================="
echo "  Script 6 : Installation des agents"
echo "  (10 agents + 3 sous-agents)"
echo "==========================================="
echo ""

# ── Verification pre-requis ──────────────────────────────────────────────────
cd "${PROJECT_DIR}"

if [ ! -f .env ]; then
    echo "ERREUR : .env introuvable. Executez d'abord 03-install-langgraph.sh"
    exit 1
fi

# ── 1. Structure des dossiers ────────────────────────────────────────────────
echo "[1/6] Creation de la structure..."
mkdir -p "${PROJECT_DIR}/agents/shared"
mkdir -p "${PROJECT_DIR}/prompts/v1"
touch "${PROJECT_DIR}/agents/__init__.py"
touch "${PROJECT_DIR}/agents/shared/__init__.py"
echo "  -> Structure creee"

# ── 2. Telecharger les system prompts depuis le repo ─────────────────────────
echo "[2/6] Telechargement des system prompts..."

PROMPT_FILES=(
    "orchestrator"
    "requirements_analyst"
    "ux_designer"
    "architect"
    "planner"
    "lead_dev"
    "dev_frontend_web"
    "dev_backend_api"
    "dev_mobile"
    "qa_engineer"
    "devops_engineer"
    "docs_writer"
    "legal_advisor"
)

DOWNLOADED=0
for name in "${PROMPT_FILES[@]}"; do
    TARGET="${PROJECT_DIR}/prompts/v1/${name}.md"
    # Essayer d'abord prompts/{name}.md (structure actuelle du repo)
    URL_FLAT="${REPO_RAW}/prompts/${name}.md"
    # Puis prompts/v1/{name}.md (structure alternative)
    URL_V1="${REPO_RAW}/prompts/v1/${name}.md"
    if wget -qO "${TARGET}" "${URL_FLAT}" 2>/dev/null && [ -s "${TARGET}" ]; then
        DOWNLOADED=$((DOWNLOADED + 1))
    elif wget -qO "${TARGET}" "${URL_V1}" 2>/dev/null && [ -s "${TARGET}" ]; then
        DOWNLOADED=$((DOWNLOADED + 1))
    else
        echo "  -> ATTENTION : ${name}.md non trouve sur le repo (sera cree localement)"
    fi
done
echo "  -> ${DOWNLOADED}/${#PROMPT_FILES[@]} prompts telecharges"

# Creer les prompts manquants avec un fallback minimal
for name in "${PROMPT_FILES[@]}"; do
    TARGET="${PROJECT_DIR}/prompts/v1/${name}.md"
    if [ ! -s "${TARGET}" ]; then
        echo "  -> Creation du prompt fallback pour ${name}..."
        echo "Tu es ${name}, agent specialise dans un systeme multi-agent LangGraph." > "${TARGET}"
        echo "Reponds en JSON structure avec les champs : agent_id, status, confidence, deliverables." >> "${TARGET}"
    fi
done

# ── 3. Module partage : ProjectState ─────────────────────────────────────────
echo "[3/6] Creation des modules partages..."

cat > "${PROJECT_DIR}/agents/shared/state.py" << 'PYTHON'
"""ProjectState — Schema d'etat partage entre tous les agents."""
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
PYTHON

# ── 4. Module partage : BaseAgent ────────────────────────────────────────────
cat > "${PROJECT_DIR}/agents/shared/base_agent.py" << 'PYTHON'
"""BaseAgent — Classe de base pour tous les agents specialistes."""
import json, logging, os
from datetime import datetime, timezone
from dotenv import load_dotenv
from langchain_anthropic import ChatAnthropic

load_dotenv()
logger = logging.getLogger(__name__)

class BaseAgent:
    agent_id: str = "base"
    agent_name: str = "Base Agent"
    default_model: str = "claude-sonnet-4-5-20250929"
    default_temperature: float = 0.3
    default_max_tokens: int = 8192
    prompt_filename: str = "base.md"

    def __init__(self):
        self.model = os.getenv(f"{self.agent_id.upper()}_MODEL", self.default_model)
        self.temperature = float(os.getenv(f"{self.agent_id.upper()}_TEMPERATURE", str(self.default_temperature)))
        self.max_tokens = int(os.getenv(f"{self.agent_id.upper()}_MAX_TOKENS", str(self.default_max_tokens)))
        self.system_prompt = self._load_prompt()

    def _load_prompt(self) -> str:
        paths = [
            os.path.join(os.path.dirname(__file__), "..", "..", "prompts", "v1", self.prompt_filename),
            os.path.join("/app", "prompts", "v1", self.prompt_filename),
        ]
        for path in paths:
            abs_path = os.path.abspath(path)
            if os.path.exists(abs_path):
                with open(abs_path, "r") as f:
                    logger.info(f"[{self.agent_id}] Prompt: {abs_path}")
                    return f.read()
        logger.warning(f"[{self.agent_id}] Prompt non trouve, fallback")
        return f"Tu es {self.agent_name}. Reponds en JSON: {{agent_id, status, confidence, deliverables}}"

    def get_llm(self) -> ChatAnthropic:
        return ChatAnthropic(model=self.model, temperature=self.temperature, max_tokens=self.max_tokens)

    def build_context(self, state: dict) -> dict:
        return {"project_phase": state.get("project_phase"), "project_metadata": state.get("project_metadata", {})}

    def parse_response(self, raw: str) -> dict:
        clean = raw.strip()
        if "```json" in clean: clean = clean.split("```json")[1].split("```")[0].strip()
        elif "```" in clean: clean = clean.split("```")[1].split("```")[0].strip()
        return json.loads(clean)

    def __call__(self, state: dict) -> dict:
        try:
            context = self.build_context(state)
            llm = self.get_llm()
            response = llm.invoke([
                {"role": "system", "content": self.system_prompt},
                {"role": "user", "content": f"Contexte :\n```json\n{json.dumps(context, indent=2, default=str)}\n```\nProduis ton livrable en JSON valide."},
            ])
            raw = response.content if isinstance(response.content, str) else str(response.content)
            output = self.parse_response(raw)
            output["agent_id"] = self.agent_id
            output["timestamp"] = datetime.now(timezone.utc).isoformat()
            agent_outputs = dict(state.get("agent_outputs", {}))
            agent_outputs[self.agent_id] = output
            state["agent_outputs"] = agent_outputs
            messages = list(state.get("messages", []))
            messages.append(("assistant", f"[{self.agent_id}] status={output.get('status')}"))
            state["messages"] = messages
            logger.info(f"[{self.agent_id}] status={output.get('status')}")
            return state
        except Exception as e:
            logger.error(f"[{self.agent_id}] Error: {e}")
            agent_outputs = dict(state.get("agent_outputs", {}))
            agent_outputs[self.agent_id] = {"agent_id": self.agent_id, "status": "blocked", "error": str(e), "timestamp": datetime.now(timezone.utc).isoformat()}
            state["agent_outputs"] = agent_outputs
            return state
PYTHON

echo "  -> shared/state.py et shared/base_agent.py crees"

# ── 5. Agents specialistes ───────────────────────────────────────────────────
echo "[4/6] Creation des agents specialistes..."

# --- Requirements Analyst ---
cat > "${PROJECT_DIR}/agents/requirements_analyst.py" << 'PYTHON'
"""Analyste (Requirements Agent)"""
from agents.shared.base_agent import BaseAgent

class AnalystAgent(BaseAgent):
    agent_id = "requirements_analyst"
    agent_name = "Analyste"
    default_temperature = 0.3
    default_max_tokens = 8192
    prompt_filename = "requirements_analyst.md"

    def build_context(self, state: dict) -> dict:
        return {
            "project_phase": state.get("project_phase", "discovery"),
            "project_metadata": state.get("project_metadata", {}),
            "existing_outputs": list(state.get("agent_outputs", {}).keys()),
        }

agent = AnalystAgent()
PYTHON

# --- UX Designer ---
cat > "${PROJECT_DIR}/agents/ux_designer.py" << 'PYTHON'
"""Designer UX/Ergonome"""
from agents.shared.base_agent import BaseAgent

class UXDesignerAgent(BaseAgent):
    agent_id = "ux_designer"
    agent_name = "Designer UX/Ergonome"
    default_temperature = 0.4
    default_max_tokens = 8192
    prompt_filename = "ux_designer.md"

    def build_context(self, state: dict) -> dict:
        outputs = state.get("agent_outputs", {})
        return {
            "project_phase": state.get("project_phase", "design"),
            "project_metadata": state.get("project_metadata", {}),
            "prd": outputs.get("requirements_analyst", {}).get("deliverables", {}).get("prd"),
            "user_stories": outputs.get("requirements_analyst", {}).get("deliverables", {}).get("user_stories"),
        }

agent = UXDesignerAgent()
PYTHON

# --- Architect ---
cat > "${PROJECT_DIR}/agents/architect.py" << 'PYTHON'
"""Architecte (Design Agent)"""
from agents.shared.base_agent import BaseAgent

class ArchitectAgent(BaseAgent):
    agent_id = "architect"
    agent_name = "Architecte"
    default_model = "claude-opus-4-5-20250929"
    default_temperature = 0.2
    default_max_tokens = 16384
    prompt_filename = "architect.md"

    def build_context(self, state: dict) -> dict:
        outputs = state.get("agent_outputs", {})
        return {
            "project_phase": state.get("project_phase", "design"),
            "project_metadata": state.get("project_metadata", {}),
            "prd": outputs.get("requirements_analyst", {}).get("deliverables", {}).get("prd"),
            "user_stories": outputs.get("requirements_analyst", {}).get("deliverables", {}).get("user_stories"),
            "wireframes": outputs.get("ux_designer", {}).get("deliverables", {}).get("wireframes"),
            "mockups": outputs.get("ux_designer", {}).get("deliverables", {}).get("mockups"),
        }

agent = ArchitectAgent()
PYTHON

# --- Planner ---
cat > "${PROJECT_DIR}/agents/planner.py" << 'PYTHON'
"""Planificateur (Planning Agent)"""
from agents.shared.base_agent import BaseAgent

class PlannerAgent(BaseAgent):
    agent_id = "planner"
    agent_name = "Planificateur"
    default_temperature = 0.2
    default_max_tokens = 8192
    prompt_filename = "planner.md"

    def build_context(self, state: dict) -> dict:
        outputs = state.get("agent_outputs", {})
        return {
            "project_phase": state.get("project_phase", "design"),
            "project_metadata": state.get("project_metadata", {}),
            "user_stories": outputs.get("requirements_analyst", {}).get("deliverables", {}).get("user_stories"),
            "adrs": outputs.get("architect", {}).get("deliverables", {}).get("adrs"),
            "openapi_spec": outputs.get("architect", {}).get("deliverables", {}).get("openapi_spec"),
        }

agent = PlannerAgent()
PYTHON

# --- Lead Dev ---
cat > "${PROJECT_DIR}/agents/lead_dev.py" << 'PYTHON'
"""Lead Dev (Supervisor)"""
from agents.shared.base_agent import BaseAgent

class LeadDevAgent(BaseAgent):
    agent_id = "lead_dev"
    agent_name = "Lead Dev"
    default_temperature = 0.2
    default_max_tokens = 4096
    prompt_filename = "lead_dev.md"
    SUB_AGENTS = ["dev_frontend_web", "dev_backend_api", "dev_mobile"]

    def build_context(self, state: dict) -> dict:
        outputs = state.get("agent_outputs", {})
        return {
            "project_phase": "build",
            "project_metadata": state.get("project_metadata", {}),
            "sprint_backlog": outputs.get("planner", {}).get("deliverables", {}).get("sprint_backlog"),
            "adrs": outputs.get("architect", {}).get("deliverables", {}).get("adrs"),
            "openapi_spec": outputs.get("architect", {}).get("deliverables", {}).get("openapi_spec"),
            "design_tokens": outputs.get("ux_designer", {}).get("deliverables", {}).get("design_tokens"),
            "mockups": outputs.get("ux_designer", {}).get("deliverables", {}).get("mockups"),
            "current_assignments": state.get("current_assignments", {}),
        }

agent = LeadDevAgent()
PYTHON

# --- Dev Frontend Web ---
cat > "${PROJECT_DIR}/agents/dev_frontend_web.py" << 'PYTHON'
"""Dev Frontend Web — React/Next.js/TypeScript/Tailwind"""
from agents.shared.base_agent import BaseAgent

class DevFrontendWebAgent(BaseAgent):
    agent_id = "dev_frontend_web"
    agent_name = "Dev Frontend Web"
    default_temperature = 0.2
    default_max_tokens = 16384
    prompt_filename = "dev_frontend_web.md"

    def build_context(self, state: dict) -> dict:
        outputs = state.get("agent_outputs", {})
        return {
            "project_phase": "build",
            "openapi_spec": outputs.get("architect", {}).get("deliverables", {}).get("openapi_spec"),
            "design_tokens": outputs.get("ux_designer", {}).get("deliverables", {}).get("design_tokens"),
            "mockups": outputs.get("ux_designer", {}).get("deliverables", {}).get("mockups"),
            "task": state.get("current_assignments", {}).get("dev_frontend_web", ""),
        }

agent = DevFrontendWebAgent()
PYTHON

# --- Dev Backend API ---
cat > "${PROJECT_DIR}/agents/dev_backend_api.py" << 'PYTHON'
"""Dev Backend/API — Python/FastAPI/SQLAlchemy/Alembic"""
from agents.shared.base_agent import BaseAgent

class DevBackendApiAgent(BaseAgent):
    agent_id = "dev_backend_api"
    agent_name = "Dev Backend/API"
    default_temperature = 0.2
    default_max_tokens = 16384
    prompt_filename = "dev_backend_api.md"

    def build_context(self, state: dict) -> dict:
        outputs = state.get("agent_outputs", {})
        return {
            "project_phase": "build",
            "openapi_spec": outputs.get("architect", {}).get("deliverables", {}).get("openapi_spec"),
            "data_models": outputs.get("architect", {}).get("deliverables", {}).get("data_models"),
            "adrs": outputs.get("architect", {}).get("deliverables", {}).get("adrs"),
            "task": state.get("current_assignments", {}).get("dev_backend_api", ""),
        }

agent = DevBackendApiAgent()
PYTHON

# --- Dev Mobile ---
cat > "${PROJECT_DIR}/agents/dev_mobile.py" << 'PYTHON'
"""Dev Mobile — React Native/Expo/TypeScript"""
from agents.shared.base_agent import BaseAgent

class DevMobileAgent(BaseAgent):
    agent_id = "dev_mobile"
    agent_name = "Dev Mobile"
    default_temperature = 0.2
    default_max_tokens = 16384
    prompt_filename = "dev_mobile.md"

    def build_context(self, state: dict) -> dict:
        outputs = state.get("agent_outputs", {})
        return {
            "project_phase": "build",
            "openapi_spec": outputs.get("architect", {}).get("deliverables", {}).get("openapi_spec"),
            "design_tokens": outputs.get("ux_designer", {}).get("deliverables", {}).get("design_tokens"),
            "mockups": outputs.get("ux_designer", {}).get("deliverables", {}).get("mockups"),
            "task": state.get("current_assignments", {}).get("dev_mobile", ""),
        }

agent = DevMobileAgent()
PYTHON

# --- QA Engineer ---
cat > "${PROJECT_DIR}/agents/qa_engineer.py" << 'PYTHON'
"""QA Engineer (Testing Agent)"""
from agents.shared.base_agent import BaseAgent

class QAEngineerAgent(BaseAgent):
    agent_id = "qa_engineer"
    agent_name = "QA Engineer"
    default_temperature = 0.2
    default_max_tokens = 8192
    prompt_filename = "qa_engineer.md"

    def build_context(self, state: dict) -> dict:
        outputs = state.get("agent_outputs", {})
        return {
            "project_phase": state.get("project_phase", "build"),
            "user_stories": outputs.get("requirements_analyst", {}).get("deliverables", {}).get("user_stories"),
            "source_code": {k: v for k, v in outputs.items() if k.startswith("dev_")},
            "acceptance_criteria": outputs.get("requirements_analyst", {}).get("deliverables", {}).get("user_stories"),
        }

agent = QAEngineerAgent()
PYTHON

# --- DevOps Engineer ---
cat > "${PROJECT_DIR}/agents/devops_engineer.py" << 'PYTHON'
"""DevOps Engineer (Infra Agent)"""
from agents.shared.base_agent import BaseAgent

class DevOpsEngineerAgent(BaseAgent):
    agent_id = "devops_engineer"
    agent_name = "DevOps Engineer"
    default_temperature = 0.2
    default_max_tokens = 8192
    prompt_filename = "devops_engineer.md"

    def build_context(self, state: dict) -> dict:
        outputs = state.get("agent_outputs", {})
        return {
            "project_phase": state.get("project_phase", "ship"),
            "project_metadata": state.get("project_metadata", {}),
            "adrs": outputs.get("architect", {}).get("deliverables", {}).get("adrs"),
            "stack_decision": outputs.get("architect", {}).get("deliverables", {}).get("stack_decision"),
            "qa_verdict": state.get("qa_verdict", {}),
        }

agent = DevOpsEngineerAgent()
PYTHON

# --- Docs Writer ---
cat > "${PROJECT_DIR}/agents/docs_writer.py" << 'PYTHON'
"""Documentaliste (Docs Agent)"""
from agents.shared.base_agent import BaseAgent

class DocsWriterAgent(BaseAgent):
    agent_id = "docs_writer"
    agent_name = "Documentaliste"
    default_temperature = 0.3
    default_max_tokens = 8192
    prompt_filename = "docs_writer.md"

    def build_context(self, state: dict) -> dict:
        outputs = state.get("agent_outputs", {})
        return {
            "project_phase": state.get("project_phase", "ship"),
            "project_metadata": state.get("project_metadata", {}),
            "prd": outputs.get("requirements_analyst", {}).get("deliverables", {}).get("prd"),
            "adrs": outputs.get("architect", {}).get("deliverables", {}).get("adrs"),
            "openapi_spec": outputs.get("architect", {}).get("deliverables", {}).get("openapi_spec"),
            "all_outputs": list(outputs.keys()),
        }

agent = DocsWriterAgent()
PYTHON

# --- Legal Advisor ---
cat > "${PROJECT_DIR}/agents/legal_advisor.py" << 'PYTHON'
"""Avocat (Legal Agent)"""
from agents.shared.base_agent import BaseAgent

class LegalAdvisorAgent(BaseAgent):
    agent_id = "legal_advisor"
    agent_name = "Avocat"
    default_temperature = 0.2
    default_max_tokens = 8192
    prompt_filename = "legal_advisor.md"

    def build_context(self, state: dict) -> dict:
        outputs = state.get("agent_outputs", {})
        return {
            "project_phase": state.get("project_phase", "discovery"),
            "project_metadata": state.get("project_metadata", {}),
            "prd": outputs.get("requirements_analyst", {}).get("deliverables", {}).get("prd"),
            "user_stories": outputs.get("requirements_analyst", {}).get("deliverables", {}).get("user_stories"),
            "source_code_agents": [k for k in outputs if k.startswith("dev_")],
            "existing_legal_alerts": state.get("legal_alerts", []),
        }

agent = LegalAdvisorAgent()
PYTHON

echo "  -> 12 agents crees (9 specialistes + 3 sous-agents dev)"

# ── 5. Orchestrateur (deja genere, on le telecharge) ────────────────────────
echo "[5/6] Installation de l'orchestrateur production..."

# Telecharger depuis le repo (essayer les deux chemins possibles)
if wget -qO "${PROJECT_DIR}/agents/orchestrator.py" "${REPO_RAW}/prompts/orchestrator.py" 2>/dev/null && [ -s "${PROJECT_DIR}/agents/orchestrator.py" ]; then
    echo "  -> orchestrator.py telecharge depuis prompts/"
elif wget -qO "${PROJECT_DIR}/agents/orchestrator.py" "${REPO_RAW}/prompts/v1/orchestrator.py" 2>/dev/null && [ -s "${PROJECT_DIR}/agents/orchestrator.py" ]; then
    echo "  -> orchestrator.py telecharge depuis prompts/v1/"
else
    echo "  -> orchestrator.py conserve (version locale)"
fi

# ── 6. Test de validation ────────────────────────────────────────────────────
echo "[6/6] Validation de l'installation..."
echo ""

source "${PROJECT_DIR}/.venv/bin/activate" 2>/dev/null || true

# Verifier les fichiers
AGENTS_COUNT=$(ls -1 "${PROJECT_DIR}/agents/"*.py 2>/dev/null | grep -v __init__ | grep -v gateway | wc -l)
PROMPTS_COUNT=$(ls -1 "${PROJECT_DIR}/prompts/v1/"*.md 2>/dev/null | wc -l)

echo "  Fichiers agents Python : ${AGENTS_COUNT}"
echo "  Fichiers system prompts : ${PROMPTS_COUNT}"

# Verifier les imports
echo ""
echo "  Test d'import des modules..."
IMPORT_OK=0
IMPORT_FAIL=0
for agent_file in "${PROJECT_DIR}/agents/"*.py; do
    agent_name=$(basename "${agent_file}" .py)
    if [ "${agent_name}" = "__init__" ] || [ "${agent_name}" = "gateway" ] || [ "${agent_name}" = "discord_listener" ]; then
        continue
    fi
    if python -c "import agents.${agent_name}" 2>/dev/null; then
        IMPORT_OK=$((IMPORT_OK + 1))
    else
        IMPORT_FAIL=$((IMPORT_FAIL + 1))
        echo "    ERREUR import : agents.${agent_name}"
    fi
done
echo "  -> Imports OK : ${IMPORT_OK}, Erreurs : ${IMPORT_FAIL}"

# Lister les agents
echo ""
echo "  Equipe installee :"
echo "  ┌─────────────────────────────────────────────────┐"
echo "  │ 🎯  Orchestrateur       (orchestrator)          │"
echo "  │ 📋  Analyste            (requirements_analyst)  │"
echo "  │ 🎨  Designer UX         (ux_designer)           │"
echo "  │ 🏗️  Architecte          (architect)              │"
echo "  │ 📅  Planificateur       (planner)               │"
echo "  │ ⚡  Lead Dev            (lead_dev)              │"
echo "  │   🌐  Dev Frontend Web  (dev_frontend_web)      │"
echo "  │   🔧  Dev Backend/API   (dev_backend_api)       │"
echo "  │   📱  Dev Mobile        (dev_mobile)            │"
echo "  │ 🔍  QA Engineer         (qa_engineer)           │"
echo "  │ 🚀  DevOps Engineer     (devops_engineer)       │"
echo "  │ 📝  Documentaliste      (docs_writer)           │"
echo "  │ ⚖️  Avocat              (legal_advisor)          │"
echo "  └─────────────────────────────────────────────────┘"

echo ""
echo "==========================================="
echo "  Agents installes avec succes."
echo ""
echo "  Structure creee :"
echo "  agents/"
echo "  ├── shared/"
echo "  │   ├── state.py          (ProjectState partage)"
echo "  │   ├── base_agent.py     (classe de base)"
echo "  │   ├── rag_service.py    (si script 05 execute)"
echo "  │   └── discord_tools.py  (si script 04 execute)"
echo "  ├── orchestrator.py       (Meta-Agent PM)"
echo "  ├── requirements_analyst.py"
echo "  ├── ux_designer.py"
echo "  ├── architect.py"
echo "  ├── planner.py"
echo "  ├── lead_dev.py"
echo "  ├── dev_frontend_web.py"
echo "  ├── dev_backend_api.py"
echo "  ├── dev_mobile.py"
echo "  ├── qa_engineer.py"
echo "  ├── devops_engineer.py"
echo "  ├── docs_writer.py"
echo "  ├── legal_advisor.py"
echo "  └── gateway.py"
echo ""
echo "  Prochaines etapes :"
echo "  1. Committez vos system prompts dans prompts/v1/"
echo "     (depuis votre repo Configurations/LandGraph)"
echo ""
echo "  2. Rebuild l'image Docker :"
echo "     docker compose up -d --build langgraph-api"
echo ""
echo "  3. Testez l'orchestrateur :"
echo "     DB_PASS=\$(grep POSTGRES_PASSWORD .env | cut -d= -f2)"
echo "     DATABASE_URI=\"postgres://langgraph:\${DB_PASS}@localhost:5432/langgraph?sslmode=disable\" \\"
echo "     python agents/orchestrator.py"
echo ""
echo "  4. Testez via Discord (#commandes) :"
echo "     \"Nouveau projet : app de gestion de taches\""
echo "==========================================="

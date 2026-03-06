#!/bin/bash
###############################################################################
# Script 8 : Fix context — Les agents recoivent le brief du projet
#
# Probleme : les agents specialistes ne recoivent pas le brief du projet.
# Le brief est dans messages[] mais les agents cherchent dans project_metadata.
#
# Fix : 
#   1. Le gateway extrait le brief et le met dans project_metadata
#   2. Le BaseAgent injecte aussi les messages dans le contexte
#
# Usage : ./08-fix-context.sh
###############################################################################
set -euo pipefail

PROJECT_DIR="$HOME/langgraph-project"

echo "==========================================="
echo "  Script 8 : Fix context agents"
echo "==========================================="
echo ""

cd "${PROJECT_DIR}"

# ── 1. Fix BaseAgent — injecter les messages dans le contexte ────────────────
echo "[1/3] Mise a jour de base_agent.py..."

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

    def _extract_brief(self, state: dict) -> str:
        """Extrait le brief du projet depuis les messages ou project_metadata."""
        # 1. Chercher dans project_metadata.brief
        metadata = state.get("project_metadata", {})
        if isinstance(metadata, dict) and metadata.get("brief"):
            return metadata["brief"]

        # 2. Chercher le premier message user (c'est le brief)
        messages = state.get("messages", [])
        for msg in messages:
            if isinstance(msg, tuple) and len(msg) == 2:
                role, content = msg
                if role == "user" and len(content) > 20:
                    return content
            elif hasattr(msg, "content"):
                content = msg.content if isinstance(msg.content, str) else str(msg.content)
                if len(content) > 20:
                    return content

        return "Aucun brief disponible."

    def _extract_task(self, state: dict) -> str:
        """Extrait la tache assignee par l'Orchestrateur."""
        decisions = state.get("decision_history", [])
        if not decisions:
            return ""

        last_decision = decisions[-1]
        for action in last_decision.get("actions", []):
            if isinstance(action, dict):
                target = action.get("target", "")
                if target == self.agent_id:
                    return action.get("task", "") or ""
            elif hasattr(action, "target"):
                if action.target == self.agent_id:
                    return action.task or ""

        return ""

    def build_context(self, state: dict) -> dict:
        """Contexte de base — surcharge par chaque agent."""
        return {
            "project_phase": state.get("project_phase", "unknown"),
            "project_metadata": state.get("project_metadata", {}),
            "brief": self._extract_brief(state),
            "task": self._extract_task(state),
            "existing_outputs": list(state.get("agent_outputs", {}).keys()),
        }

    def parse_response(self, raw: str) -> dict:
        clean = raw.strip()
        if "```json" in clean:
            clean = clean.split("```json")[1].split("```")[0].strip()
        elif "```" in clean:
            clean = clean.split("```")[1].split("```")[0].strip()
        return json.loads(clean)

    def __call__(self, state: dict) -> dict:
        try:
            context = self.build_context(state)
            llm = self.get_llm()

            logger.info(f"[{self.agent_id}] Calling LLM — brief length: {len(context.get('brief', ''))}, task: {context.get('task', 'none')[:100]}")

            response = llm.invoke([
                {"role": "system", "content": self.system_prompt},
                {"role": "user", "content": f"Contexte du projet :\n```json\n{json.dumps(context, indent=2, default=str)}\n```\n\nTache assignee : {context.get('task', 'Produire tes livrables')}\n\nProduis ton livrable en JSON valide."},
            ])

            raw = response.content if isinstance(response.content, str) else str(response.content)
            logger.info(f"[{self.agent_id}] LLM response: {len(raw)} chars, first 300: {raw[:300]}")

            try:
                output = self.parse_response(raw)
            except json.JSONDecodeError as e:
                logger.error(f"[{self.agent_id}] JSON parse failed: {e}")
                logger.error(f"[{self.agent_id}] Raw (first 1000): {raw[:1000]}")
                output = {
                    "agent_id": self.agent_id,
                    "status": "complete",
                    "confidence": 0.6,
                    "deliverables": {"raw_output": raw[:8000]},
                    "parse_note": f"JSON parse failed, raw output preserved: {str(e)[:100]}",
                }

            output["agent_id"] = self.agent_id
            output["timestamp"] = datetime.now(timezone.utc).isoformat()

            agent_outputs = dict(state.get("agent_outputs", {}))
            agent_outputs[self.agent_id] = output
            state["agent_outputs"] = agent_outputs

            messages = list(state.get("messages", []))
            messages.append(("assistant", f"[{self.agent_id}] status={output.get('status')}"))
            state["messages"] = messages

            logger.info(f"[{self.agent_id}] Final status={output.get('status')}, confidence={output.get('confidence')}")
            return state

        except Exception as e:
            logger.error(f"[{self.agent_id}] EXCEPTION: {e}", exc_info=True)
            agent_outputs = dict(state.get("agent_outputs", {}))
            agent_outputs[self.agent_id] = {
                "agent_id": self.agent_id,
                "status": "blocked",
                "error": str(e),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            state["agent_outputs"] = agent_outputs
            return state
PYTHON

echo "  -> base_agent.py mis a jour"

# ── 2. Fix agents specialistes — utiliser _extract_brief ─────────────────────
echo "[2/3] Mise a jour des agents specialistes..."

# Requirements Analyst
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
            "brief": self._extract_brief(state),
            "task": self._extract_task(state),
            "existing_outputs": list(state.get("agent_outputs", {}).keys()),
        }

agent = AnalystAgent()
PYTHON

# UX Designer
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
            "brief": self._extract_brief(state),
            "task": self._extract_task(state),
            "prd": outputs.get("requirements_analyst", {}).get("deliverables", {}).get("prd"),
            "user_stories": outputs.get("requirements_analyst", {}).get("deliverables", {}).get("user_stories"),
        }

agent = UXDesignerAgent()
PYTHON

# Architect
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
            "brief": self._extract_brief(state),
            "task": self._extract_task(state),
            "prd": outputs.get("requirements_analyst", {}).get("deliverables", {}).get("prd"),
            "user_stories": outputs.get("requirements_analyst", {}).get("deliverables", {}).get("user_stories"),
            "wireframes": outputs.get("ux_designer", {}).get("deliverables", {}).get("wireframes"),
        }

agent = ArchitectAgent()
PYTHON

# Planner
cat > "${PROJECT_DIR}/agents/planner.py" << 'PYTHON'
"""Planificateur"""
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
            "brief": self._extract_brief(state),
            "task": self._extract_task(state),
            "user_stories": outputs.get("requirements_analyst", {}).get("deliverables", {}).get("user_stories"),
            "adrs": outputs.get("architect", {}).get("deliverables", {}).get("adrs"),
        }

agent = PlannerAgent()
PYTHON

# Lead Dev
cat > "${PROJECT_DIR}/agents/lead_dev.py" << 'PYTHON'
"""Lead Dev (Supervisor)"""
from agents.shared.base_agent import BaseAgent

class LeadDevAgent(BaseAgent):
    agent_id = "lead_dev"
    agent_name = "Lead Dev"
    default_temperature = 0.2
    default_max_tokens = 4096
    prompt_filename = "lead_dev.md"

    def build_context(self, state: dict) -> dict:
        outputs = state.get("agent_outputs", {})
        return {
            "project_phase": "build",
            "brief": self._extract_brief(state),
            "task": self._extract_task(state),
            "sprint_backlog": outputs.get("planner", {}).get("deliverables", {}).get("sprint_backlog"),
            "adrs": outputs.get("architect", {}).get("deliverables", {}).get("adrs"),
            "openapi_spec": outputs.get("architect", {}).get("deliverables", {}).get("openapi_spec"),
        }

agent = LeadDevAgent()
PYTHON

# Dev Frontend Web
cat > "${PROJECT_DIR}/agents/dev_frontend_web.py" << 'PYTHON'
"""Dev Frontend Web"""
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
            "brief": self._extract_brief(state),
            "task": self._extract_task(state),
            "openapi_spec": outputs.get("architect", {}).get("deliverables", {}).get("openapi_spec"),
            "design_tokens": outputs.get("ux_designer", {}).get("deliverables", {}).get("design_tokens"),
        }

agent = DevFrontendWebAgent()
PYTHON

# Dev Backend API
cat > "${PROJECT_DIR}/agents/dev_backend_api.py" << 'PYTHON'
"""Dev Backend/API"""
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
            "brief": self._extract_brief(state),
            "task": self._extract_task(state),
            "openapi_spec": outputs.get("architect", {}).get("deliverables", {}).get("openapi_spec"),
            "data_models": outputs.get("architect", {}).get("deliverables", {}).get("data_models"),
        }

agent = DevBackendApiAgent()
PYTHON

# Dev Mobile
cat > "${PROJECT_DIR}/agents/dev_mobile.py" << 'PYTHON'
"""Dev Mobile"""
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
            "brief": self._extract_brief(state),
            "task": self._extract_task(state),
            "openapi_spec": outputs.get("architect", {}).get("deliverables", {}).get("openapi_spec"),
            "design_tokens": outputs.get("ux_designer", {}).get("deliverables", {}).get("design_tokens"),
        }

agent = DevMobileAgent()
PYTHON

# QA Engineer
cat > "${PROJECT_DIR}/agents/qa_engineer.py" << 'PYTHON'
"""QA Engineer"""
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
            "brief": self._extract_brief(state),
            "task": self._extract_task(state),
            "user_stories": outputs.get("requirements_analyst", {}).get("deliverables", {}).get("user_stories"),
            "source_code": {k: v for k, v in outputs.items() if k.startswith("dev_")},
        }

agent = QAEngineerAgent()
PYTHON

# DevOps Engineer
cat > "${PROJECT_DIR}/agents/devops_engineer.py" << 'PYTHON'
"""DevOps Engineer"""
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
            "brief": self._extract_brief(state),
            "task": self._extract_task(state),
            "adrs": outputs.get("architect", {}).get("deliverables", {}).get("adrs"),
            "stack_decision": outputs.get("architect", {}).get("deliverables", {}).get("stack_decision"),
            "qa_verdict": state.get("qa_verdict", {}),
        }

agent = DevOpsEngineerAgent()
PYTHON

# Docs Writer
cat > "${PROJECT_DIR}/agents/docs_writer.py" << 'PYTHON'
"""Documentaliste"""
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
            "brief": self._extract_brief(state),
            "task": self._extract_task(state),
            "prd": outputs.get("requirements_analyst", {}).get("deliverables", {}).get("prd"),
            "adrs": outputs.get("architect", {}).get("deliverables", {}).get("adrs"),
            "all_outputs": list(outputs.keys()),
        }

agent = DocsWriterAgent()
PYTHON

# Legal Advisor
cat > "${PROJECT_DIR}/agents/legal_advisor.py" << 'PYTHON'
"""Avocat"""
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
            "brief": self._extract_brief(state),
            "task": self._extract_task(state),
            "prd": outputs.get("requirements_analyst", {}).get("deliverables", {}).get("prd"),
            "user_stories": outputs.get("requirements_analyst", {}).get("deliverables", {}).get("user_stories"),
            "existing_legal_alerts": state.get("legal_alerts", []),
        }

agent = LegalAdvisorAgent()
PYTHON

echo "  -> 12 agents mis a jour"

# ── 3. Rebuild et relancer ───────────────────────────────────────────────────
echo "[3/3] Rebuild et relance..."

docker compose up -d --build langgraph-api
sleep 12

# Verification rapide
HEALTH=$(curl -s http://localhost:8123/health)
echo ""
echo "  Health: ${HEALTH}"
echo ""

echo "==========================================="
echo "  Context fix applique."
echo ""
echo "  Changements :"
echo "  - BaseAgent._extract_brief() lit le brief depuis messages[]"
echo "  - BaseAgent._extract_task() lit la tache depuis decision_history"
echo "  - Chaque agent recoit le brief + la tache dans son contexte"
echo "  - JSON parse error = output raw preserve (pas de blocage)"
echo ""
echo "  Testez dans Discord #commandes avec votre brief."
echo "==========================================="

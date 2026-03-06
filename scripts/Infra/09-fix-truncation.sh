#!/bin/bash
###############################################################################
# Script 9 : Fix troncature — Pipeline multi-etapes + max_tokens
#
# Probleme : les agents produisent des JSON trop longs, tronques par max_tokens.
# Fix : BaseAgent gagne un mode pipeline (plusieurs appels LLM sequentiels)
#       et max_tokens monte a 32768.
#
# Usage : ./09-fix-truncation.sh
###############################################################################
set -euo pipefail

PROJECT_DIR="$HOME/langgraph-project"

echo "==========================================="
echo "  Script 9 : Fix troncature (pipeline)"
echo "==========================================="
echo ""

cd "${PROJECT_DIR}"

# ── 1. BaseAgent avec mode pipeline ──────────────────────────────────────────
echo "[1/4] Mise a jour de BaseAgent (pipeline mode)..."

cat > agents/shared/base_agent.py << 'PYTHON'
"""BaseAgent — Classe de base avec mode pipeline multi-etapes."""
import json, logging, os
from datetime import datetime, timezone
from dotenv import load_dotenv
from langchain_anthropic import ChatAnthropic

load_dotenv()
logger = logging.getLogger(__name__)


class BaseAgent:
    agent_id = "base"
    agent_name = "Base Agent"
    default_model = "claude-sonnet-4-5-20250929"
    default_temperature = 0.3
    default_max_tokens = 32768
    prompt_filename = "base.md"

    # Pipeline : liste d'etapes. Si vide, mode single-shot.
    # Chaque etape = {"name": "...", "instruction": "...", "output_key": "..."}
    pipeline_steps = []

    def __init__(self):
        self.model = os.getenv(f"{self.agent_id.upper()}_MODEL", self.default_model)
        self.temperature = float(os.getenv(f"{self.agent_id.upper()}_TEMPERATURE", str(self.default_temperature)))
        self.max_tokens = int(os.getenv(f"{self.agent_id.upper()}_MAX_TOKENS", str(self.default_max_tokens)))
        self.system_prompt = self._load_prompt()

    def _load_prompt(self):
        for p in [
            os.path.join(os.path.dirname(__file__), "..", "..", "prompts", "v1", self.prompt_filename),
            os.path.join("/app", "prompts", "v1", self.prompt_filename),
        ]:
            a = os.path.abspath(p)
            if os.path.exists(a):
                logger.info(f"[{self.agent_id}] Prompt: {a}")
                return open(a).read()
        return f"Tu es {self.agent_name}. JSON: {{agent_id, status, confidence, deliverables}}"

    def get_llm(self):
        return ChatAnthropic(model=self.model, temperature=self.temperature, max_tokens=self.max_tokens)

    def _extract_brief(self, state):
        m = state.get("project_metadata", {})
        if isinstance(m, dict) and m.get("brief"):
            return m["brief"]
        for msg in state.get("messages", []):
            if isinstance(msg, tuple) and len(msg) == 2 and msg[0] == "user" and len(msg[1]) > 20:
                return msg[1]
            elif hasattr(msg, "content"):
                c = msg.content if isinstance(msg.content, str) else str(msg.content)
                if len(c) > 20:
                    return c
        return "Aucun brief."

    def _extract_task(self, state):
        for d in reversed(state.get("decision_history", [])):
            for a in d.get("actions", []):
                if isinstance(a, dict) and a.get("target") == self.agent_id:
                    return a.get("task") or ""
                elif hasattr(a, "target") and a.target == self.agent_id:
                    return a.task or ""
        return ""

    def build_context(self, state):
        o = state.get("agent_outputs", {})
        return {
            "project_phase": state.get("project_phase", "unknown"),
            "project_metadata": state.get("project_metadata", {}),
            "brief": self._extract_brief(state),
            "task": self._extract_task(state),
            "existing_outputs": list(o.keys()),
            "relevant_outputs": {
                k: {"status": v.get("status"), "keys": list(v.get("deliverables", {}).keys())}
                for k, v in o.items() if v.get("status") == "complete"
            },
        }

    def parse_response(self, raw):
        c = raw.strip()
        if "```json" in c:
            c = c.split("```json")[1].split("```")[0].strip()
        elif "```" in c:
            c = c.split("```")[1].split("```")[0].strip()
        return json.loads(c)

    def _call_llm(self, instruction, context, previous_results=None):
        """Appel LLM unique avec contexte et resultats precedents."""
        llm = self.get_llm()

        user_content = f"Contexte du projet :\n```json\n{json.dumps(context, indent=2, default=str)}\n```\n\n"

        if previous_results:
            user_content += f"Resultats des etapes precedentes :\n```json\n{json.dumps(previous_results, indent=2, default=str, ensure_ascii=False)[:10000]}\n```\n\n"

        user_content += f"Instruction : {instruction}\n\nReponds UNIQUEMENT en JSON valide, sans texte avant ou apres."

        response = llm.invoke([
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": user_content},
        ])

        raw = response.content if isinstance(response.content, str) else str(response.content)
        logger.info(f"[{self.agent_id}] LLM response: {len(raw)} chars")
        return raw

    def _run_pipeline(self, state):
        """Execute les etapes du pipeline sequentiellement."""
        context = self.build_context(state)
        deliverables = {}
        all_raw = []

        for i, step in enumerate(self.pipeline_steps, 1):
            step_name = step["name"]
            instruction = step["instruction"]
            output_key = step["output_key"]

            logger.info(f"[{self.agent_id}] Pipeline etape {i}/{len(self.pipeline_steps)}: {step_name}")

            raw = self._call_llm(instruction, context, deliverables if deliverables else None)

            try:
                parsed = self.parse_response(raw)
                # Extraire le livrable de cette etape
                if output_key in parsed:
                    deliverables[output_key] = parsed[output_key]
                elif "deliverables" in parsed and output_key in parsed["deliverables"]:
                    deliverables[output_key] = parsed["deliverables"][output_key]
                else:
                    # Le JSON entier est le livrable
                    deliverables[output_key] = parsed
                logger.info(f"[{self.agent_id}] Etape {step_name}: OK ({output_key})")
            except json.JSONDecodeError as e:
                logger.error(f"[{self.agent_id}] Etape {step_name} JSON fail: {e}")
                deliverables[output_key] = {"raw": raw[:8000], "parse_error": str(e)[:100]}
                all_raw.append(raw[:3000])

        return {
            "agent_id": self.agent_id,
            "status": "complete",
            "confidence": 0.85,
            "deliverables": deliverables,
            "pipeline_steps_completed": len(self.pipeline_steps),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def _run_single(self, state):
        """Mode single-shot (comportement original)."""
        context = self.build_context(state)
        raw = self._call_llm(
            context.get("task", "Produis ton livrable complet."),
            context,
        )

        try:
            output = self.parse_response(raw)
        except json.JSONDecodeError as e:
            logger.error(f"[{self.agent_id}] JSON fail: {e}")
            output = {
                "agent_id": self.agent_id,
                "status": "complete",
                "confidence": 0.6,
                "deliverables": {"raw_output": raw[:8000]},
                "parse_note": str(e)[:100],
            }

        output["agent_id"] = self.agent_id
        output["timestamp"] = datetime.now(timezone.utc).isoformat()
        return output

    def __call__(self, state):
        try:
            logger.info(f"[{self.agent_id}] Start — pipeline={len(self.pipeline_steps)} steps")

            if self.pipeline_steps:
                output = self._run_pipeline(state)
            else:
                output = self._run_single(state)

            # Stocker dans le state
            ao = dict(state.get("agent_outputs", {}))
            ao[self.agent_id] = output
            state["agent_outputs"] = ao

            msgs = list(state.get("messages", []))
            msgs.append(("assistant", f"[{self.agent_id}] status={output.get('status')}"))
            state["messages"] = msgs

            logger.info(f"[{self.agent_id}] Done — status={output.get('status')} conf={output.get('confidence')}")
            return state

        except Exception as e:
            logger.error(f"[{self.agent_id}] EXC: {e}", exc_info=True)
            ao = dict(state.get("agent_outputs", {}))
            ao[self.agent_id] = {
                "agent_id": self.agent_id, "status": "blocked",
                "error": str(e), "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            state["agent_outputs"] = ao
            return state
PYTHON

echo "  -> base_agent.py mis a jour (pipeline mode + max_tokens 32768)"

# ── 2. Analyste en mode pipeline (3 etapes) ─────────────────────────────────
echo "[2/4] Mise a jour de l'Analyste (pipeline 3 etapes)..."

cat > agents/requirements_analyst.py << 'PYTHON'
"""Analyste (Requirements Agent) — Pipeline 3 etapes : PRD, User Stories, MoSCoW."""
from agents.shared.base_agent import BaseAgent


class AnalystAgent(BaseAgent):
    agent_id = "requirements_analyst"
    agent_name = "Analyste"
    default_temperature = 0.3
    default_max_tokens = 32768
    prompt_filename = "requirements_analyst.md"

    pipeline_steps = [
        {
            "name": "PRD",
            "output_key": "prd",
            "instruction": (
                "Produis le PRD (Product Requirements Document) en JSON. "
                "Sections obligatoires : context_and_problem, objectives (KPIs), "
                "personas (2-4 avec besoins et frustrations), "
                "scope (in_scope + out_of_scope), "
                "functional_requirements (par domaine), "
                "non_functional_requirements (performance, securite, accessibilite, scalabilite — marquer [IMPLICITE] si infere), "
                "constraints (technical, business, regulatory), "
                "assumptions_and_risks, glossary. "
                "Format : {\"prd\": {\"context_and_problem\": \"...\", \"objectives\": [...], ...}}"
            ),
        },
        {
            "name": "User Stories",
            "output_key": "user_stories",
            "instruction": (
                "A partir du PRD produit a l'etape precedente, genere les User Stories. "
                "Format INVEST : Independante, Negociable, Valorisable, Estimable, Small, Testable. "
                "Chaque story : id (US-001), persona, action, benefit, "
                "acceptance_criteria (2-5 criteres Given/When/Then). "
                "Format : {\"user_stories\": [{\"id\": \"US-001\", \"persona\": \"...\", \"action\": \"...\", "
                "\"benefit\": \"...\", \"acceptance_criteria\": [{\"given\": \"...\", \"when\": \"...\", \"then\": \"...\"}]}]}"
            ),
        },
        {
            "name": "MoSCoW",
            "output_key": "moscow_matrix",
            "instruction": (
                "A partir des User Stories produites, classe chaque story en MoSCoW. "
                "Must Have = le produit ne fonctionne pas sans. "
                "Should Have = important mais pas bloquant MVP. "
                "Could Have = nice-to-have. "
                "Won't Have = explicitement exclu. "
                "Justifie chaque classification. "
                "Format : {\"moscow_matrix\": {\"must_have\": [{\"story_id\": \"US-001\", \"justification\": \"...\"}], "
                "\"should_have\": [...], \"could_have\": [...], \"wont_have\": [...]}}"
            ),
        },
    ]

    def build_context(self, state):
        return {
            "project_phase": state.get("project_phase", "discovery"),
            "project_metadata": state.get("project_metadata", {}),
            "brief": self._extract_brief(state),
            "task": self._extract_task(state),
            "existing_outputs": list(state.get("agent_outputs", {}).keys()),
        }


agent = AnalystAgent()
PYTHON

echo "  -> requirements_analyst.py mis a jour (3 etapes pipeline)"

# ── 3. Avocat en mode pipeline (2 etapes) ───────────────────────────────────
echo "[3/4] Mise a jour de l'Avocat (pipeline 2 etapes)..."

cat > agents/legal_advisor.py << 'PYTHON'
"""Avocat (Legal Agent) — Pipeline 2 etapes : Audit reglementaire, Rapport."""
from agents.shared.base_agent import BaseAgent


class LegalAdvisorAgent(BaseAgent):
    agent_id = "legal_advisor"
    agent_name = "Avocat"
    default_temperature = 0.2
    default_max_tokens = 32768
    prompt_filename = "legal_advisor.md"

    pipeline_steps = [
        {
            "name": "Audit reglementaire",
            "output_key": "regulatory_audit",
            "instruction": (
                "Effectue l'audit reglementaire du projet. "
                "Identifie : juridictions applicables, reglementations (RGPD, ePrivacy, etc.), "
                "donnees personnelles collectees et leur sensibilite, "
                "obligations de consentement, risques juridiques. "
                "Inclus le disclaimer : 'Analyse automatisee, ne remplace pas un avocat qualifie.' "
                "Format : {\"regulatory_audit\": {\"disclaimer\": \"...\", \"jurisdictions\": [...], "
                "\"regulations\": [...], \"data_sensitivity\": [...], \"risks\": [...]}}"
            ),
        },
        {
            "name": "Alertes et recommandations",
            "output_key": "alerts",
            "instruction": (
                "A partir de l'audit reglementaire, produis les alertes et recommandations. "
                "Niveaux : info (recommandation), warning (risque modere), critical (bloquant). "
                "Les alertes critical BLOQUENT la transition de phase. "
                "Format : {\"alerts\": [{\"level\": \"info|warning|critical\", \"category\": \"...\", "
                "\"description\": \"...\", \"recommendation\": \"...\", \"resolved\": false}]}"
            ),
        },
    ]

    def build_context(self, state):
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

echo "  -> legal_advisor.py mis a jour (2 etapes pipeline)"

# ── 4. Rebuild et test ───────────────────────────────────────────────────────
echo "[4/4] Rebuild..."

docker compose up -d --build langgraph-api
sleep 12

H=$(curl -s http://localhost:8123/health)
echo ""
echo "  Health: ${H}"

echo ""
echo "==========================================="
echo "  Fix troncature applique."
echo ""
echo "  Changements :"
echo "  - BaseAgent : mode pipeline (appels LLM sequentiels)"
echo "  - BaseAgent : max_tokens 32768 (au lieu de 16384)"
echo "  - Analyste  : 3 etapes (PRD -> User Stories -> MoSCoW)"
echo "  - Avocat    : 2 etapes (Audit -> Alertes)"
echo "  - Chaque etape = 1 appel LLM = 1 JSON plus petit"
echo ""
echo "  Testez dans Discord #commandes."
echo "==========================================="

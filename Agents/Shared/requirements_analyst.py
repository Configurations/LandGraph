"""Analyste — Pipeline 3 etapes : PRD, User Stories, MoSCoW."""
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
                "Produis le PRD en JSON. Sections: context_and_problem, objectives (KPIs), "
                "personas (2-4), scope (in/out), functional_requirements, "
                "non_functional_requirements, constraints, assumptions_and_risks, glossary. "
                "Format: {\"prd\": {...}}"
            ),
        },
        {
            "name": "User Stories",
            "output_key": "user_stories",
            "instruction": (
                "A partir du PRD, genere les User Stories INVEST. "
                "Chaque: id (US-001), persona, action, benefit, "
                "acceptance_criteria (Given/When/Then). "
                "Format: {\"user_stories\": [...]}"
            ),
        },
        {
            "name": "MoSCoW",
            "output_key": "moscow_matrix",
            "instruction": (
                "Classe chaque User Story en MoSCoW avec justification. "
                "Format: {\"moscow_matrix\": {\"must_have\":[...], "
                "\"should_have\":[...], \"could_have\":[...], \"wont_have\":[...]}}"
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

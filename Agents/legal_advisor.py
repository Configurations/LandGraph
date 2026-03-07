"""Avocat — Pipeline 2 etapes : Audit, Alertes."""
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
                "Audit reglementaire: juridictions, reglementations (RGPD, ePrivacy), "
                "donnees sensibles, consentement, risques. Disclaimer obligatoire. "
                "Format: {\"regulatory_audit\": {...}}"
            ),
        },
        {
            "name": "Alertes et recommandations",
            "output_key": "alerts",
            "instruction": (
                "Alertes: info/warning/critical. Critical = bloquant. "
                "Format: {\"alerts\": [{\"level\":\"...\",\"category\":\"...\","
                "\"description\":\"...\",\"recommendation\":\"...\"}]}"
            ),
        },
    ]

    def build_context(self, state):
        o = state.get("agent_outputs", {})
        return {
            "project_phase": state.get("project_phase", "discovery"),
            "brief": self._extract_brief(state),
            "task": self._extract_task(state),
            "prd": o.get("requirements_analyst", {}).get("deliverables", {}).get("prd"),
            "user_stories": o.get("requirements_analyst", {}).get("deliverables", {}).get("user_stories"),
        }


agent = LegalAdvisorAgent()

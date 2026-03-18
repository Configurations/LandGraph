"""
prompt_builder.py — Builds orchestrator prompt dynamically from agent catalog.

Reads the orchestrator identity template from Shared/Agents/orchestrator/identity.md
and injects {Agents_identity}, {Agents_role}, {Agents_missions} variables built from
each agent's catalog files (identity.md, role_*.md, mission_*.md).
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

log = logging.getLogger(__name__)


def _resolve_agent_dir(shared_agents_dir: Path, agent_id: str) -> Path | None:
    """Find agent directory with case-insensitive matching."""
    exact = shared_agents_dir / agent_id
    if exact.exists():
        return exact
    if not shared_agents_dir.exists():
        return None
    lower = agent_id.lower()
    for d in shared_agents_dir.iterdir():
        if d.is_dir() and d.name.lower() == lower:
            return d
    return None


def build_orchestrator_prompt(
    project_dir: str | Path,
    *,
    shared_agents_dir: str | Path | None = None,
    shared_teams_dir: str | Path | None = None,
) -> str:
    """Build the orchestrator prompt for a project and save it.

    Parameters
    ----------
    project_dir : Path
        Path to ``Shared/Projects/{project_id}/``.
    shared_agents_dir : Path, optional
        Path to ``Shared/Agents/``.  When *None* it is derived as
        ``project_dir / ../../Agents``.
    shared_teams_dir : Path, optional
        Path to ``Shared/Teams/``.  When *None* it is derived as
        ``project_dir / ../../Teams``.

    Returns
    -------
    str
        The generated prompt content (also saved to
        ``project_dir/prompt_orchestrator.md``).
    """
    project_dir = Path(project_dir)
    shared_root = project_dir.parent.parent  # Shared/
    if shared_agents_dir is None:
        shared_agents_dir = shared_root / "Agents"
    else:
        shared_agents_dir = Path(shared_agents_dir)
    if shared_teams_dir is None:
        shared_teams_dir = shared_root / "Teams"
    else:
        shared_teams_dir = Path(shared_teams_dir)

    # 1. Read project.json → team
    project_json = project_dir / "project.json"
    if not project_json.exists():
        raise FileNotFoundError(f"project.json introuvable dans {project_dir}")
    project_cfg = json.loads(project_json.read_text(encoding="utf-8"))
    team = project_cfg.get("team", "").strip()
    if not team:
        raise ValueError("Le projet n'a pas d'equipe (champ 'team' vide)")

    # 2. Resolve team dir → agents_registry.json
    team_dir = shared_teams_dir / team
    registry_file = team_dir / "agents_registry.json"
    if not registry_file.exists():
        raise FileNotFoundError(f"agents_registry.json introuvable dans {team_dir}")
    registry = json.loads(registry_file.read_text(encoding="utf-8"))
    agents = registry.get("agents", {})

    # 3. Read orchestrator identity template
    orch_dir = _resolve_agent_dir(shared_agents_dir, "orchestrator")
    if orch_dir is None:
        raise FileNotFoundError(
            f"Dossier orchestrateur introuvable dans {shared_agents_dir}"
        )
    template_file = orch_dir / "identity.md"
    if not template_file.exists():
        raise FileNotFoundError(
            f"Template orchestrateur introuvable : {template_file}"
        )
    template = template_file.read_text(encoding="utf-8")

    # 4. Build the 4 variables from non-orchestrator agents
    identity_rows = []
    role_blocks = []
    mission_blocks = []
    skill_blocks = []

    for agent_id, agent_cfg in agents.items():
        # Skip orchestrator
        if agent_cfg.get("type") == "orchestrator" or agent_id == "orchestrator":
            continue

        agent_name = agent_cfg.get("name", agent_id)
        agent_catalog_dir = _resolve_agent_dir(shared_agents_dir, agent_id)

        # Read description from catalog agent.json
        description = ""
        if agent_catalog_dir is not None:
            catalog_json = agent_catalog_dir / "agent.json"
            if catalog_json.exists():
                catalog_cfg = json.loads(catalog_json.read_text(encoding="utf-8"))
                description = catalog_cfg.get("description", "")

        # Identity
        identity_text = ""
        if agent_catalog_dir is not None:
            identity_file = agent_catalog_dir / "identity.md"
            if identity_file.exists():
                identity_text = identity_file.read_text(encoding="utf-8").strip()
        identity_rows.append(
            f"| `{agent_id}` | {agent_name} | {description} | {identity_text} |"
        )

        # Roles (role_*.md)
        role_items = []
        if agent_catalog_dir is not None:
            for f in sorted(agent_catalog_dir.glob("role_*.md")):
                content = f.read_text(encoding="utf-8").strip()
                if content:
                    role_items.append(f"  - {content}")
        if role_items:
            role_blocks.append(
                f"- **{agent_name}**\n" + "\n".join(role_items)
            )

        # Missions (mission_*.md)
        mission_items = []
        if agent_catalog_dir is not None:
            for f in sorted(agent_catalog_dir.glob("mission_*.md")):
                content = f.read_text(encoding="utf-8").strip()
                if content:
                    mission_items.append(f"  - {content}")
        if mission_items:
            mission_blocks.append(
                f"- **{agent_name}**\n" + "\n".join(mission_items)
            )

        # Skills (skill_*.md)
        skill_items = []
        if agent_catalog_dir is not None:
            for f in sorted(agent_catalog_dir.glob("skill_*.md")):
                content = f.read_text(encoding="utf-8").strip()
                if content:
                    skill_items.append(f"  - {content}")
        if skill_items:
            skill_blocks.append(
                f"- **{agent_name}**\n" + "\n".join(skill_items)
            )

    # Format variables
    agents_identity = (
        "| Cle | Nom | Description | Identite |\n|---|---|---|---|\n"
        + "\n".join(identity_rows)
        if identity_rows
        else "(aucun agent)"
    )
    agents_role = "\n\n".join(role_blocks) if role_blocks else "(aucun role)"
    agents_missions = (
        "\n\n".join(mission_blocks) if mission_blocks else "(aucune mission)"
    )
    agents_skills = (
        "\n\n".join(skill_blocks) if skill_blocks else "(aucune competence)"
    )

    # 5. Replace placeholders in template
    prompt = template.replace("{Agents_identity}", agents_identity)
    prompt = prompt.replace("{Agents_role}", agents_role)
    prompt = prompt.replace("{Agents_missions}", agents_missions)
    prompt = prompt.replace("{Agents_skills}", agents_skills)

    # 6. Save to project dir
    output_file = project_dir / "prompt_orchestrator.md"
    output_file.write_text(prompt, encoding="utf-8")
    log.info("Prompt orchestrateur genere : %s", output_file)

    return prompt

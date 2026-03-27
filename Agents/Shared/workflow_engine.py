"""Workflow Engine — Lit workflow.json via team_resolver, valide les transitions."""
import logging
import os
from agents.shared.team_resolver import load_team_json

logger = logging.getLogger("workflow_engine")

_workflows = {}

# Cached project context for disk checks (set by gateway before dispatch)
_disk_check_ctx = {}  # {slug, team_id, workflow, iteration, phase}


def set_disk_check_context(slug: str, team_id: str, workflow: str = "main",
                           iteration: int = 1, phase: str = ""):
    """Set context for deliverable-on-disk checks. Called by gateway before dispatch."""
    global _disk_check_ctx
    _disk_check_ctx = {"slug": slug, "team_id": team_id, "workflow": workflow,
                       "iteration": iteration, "phase": phase}


def _check_deliverable_on_disk(agent_id: str, step: str) -> str:
    """Check if a deliverable file exists on disk. Returns 'complete' if found, '' otherwise."""
    ctx = _disk_check_ctx
    if not ctx.get("slug"):
        return ""
    ag_flow = os.environ.get("AG_FLOW_ROOT", "/root/ag.flow")
    # Scan all iterations for this phase
    base = os.path.join(ag_flow, "projects", ctx["slug"], ctx["team_id"], ctx["workflow"])
    if not os.path.isdir(base):
        return ""
    phase = ctx.get("phase", "")
    for entry in os.listdir(base):
        if ":" not in entry:
            continue
        entry_phase = entry.split(":", 1)[1]
        if phase and entry_phase != phase:
            continue
        deliv_path = os.path.join(base, entry, agent_id, f"{step}.md")
        if os.path.isfile(deliv_path) and os.path.getsize(deliv_path) > 50:
            logger.info(f"Deliverable {agent_id}:{step} found on disk, skipping dispatch")
            return "complete"
    return ""


def load_workflow(team_id: str = "team1") -> dict:
    if team_id in _workflows:
        return _workflows[team_id]
    data = load_team_json(team_id, "Workflow.json")
    if not data:
        data = load_team_json(team_id, "workflow.json")
    if data:
        _workflows[team_id] = data
        logger.info(f"Workflow [{team_id}]: {list(data.get('phases', {}).keys())}")
    else:
        logger.warning(f"Workflow [{team_id}] not found")
        _workflows[team_id] = {"phases": {}, "transitions": [], "rules": {}}
    return _workflows[team_id]


def reload_workflow(team_id: str = None):
    """Clear workflow cache. If team_id is None, clear all."""
    if team_id:
        _workflows.pop(team_id, None)
    else:
        _workflows.clear()
    logger.info(f"Workflow cache cleared: {team_id or 'all'}")


def get_phase(phase_id: str, team_id: str = "team1") -> dict:
    return load_workflow(team_id).get("phases", {}).get(phase_id, {})


def get_phase_agents(phase_id: str, team_id: str = "team1") -> dict:
    """Derive agents dict from groups deliverables."""
    phase = get_phase(phase_id, team_id)
    agents = {}
    for group in phase.get("groups", []):
        for d in group.get("deliverables", []):
            aid = d.get("agent", "")
            if aid and aid not in agents:
                agents[aid] = {"role": aid}
    return agents


def get_agents_for_group(phase_id: str, group: str, team_id: str = "team1") -> list:
    """Return unique agent ids for a given group."""
    phase = get_phase(phase_id, team_id)
    for g in phase.get("groups", []):
        if g.get("id") == group:
            return list(set(d.get("agent", "") for d in g.get("deliverables", []) if d.get("agent")))
    return []


def get_ordered_groups(phase_id: str, team_id: str = "team1") -> list:
    """Return group ids in array order."""
    phase = get_phase(phase_id, team_id)
    return [g.get("id", "") for g in phase.get("groups", [])]


def get_required_deliverables(phase_id: str, team_id: str = "team1") -> list:
    """Return list of output keys (GROUP:id) for required deliverables."""
    phase = get_phase(phase_id, team_id)
    result = []
    for group in phase.get("groups", []):
        gid = group.get("id", "")
        for d in group.get("deliverables", []):
            if d.get("required"):
                result.append(f"{gid}:{d['id']}")
    return result


def get_deliverables_for_group(phase_id: str, group_id: str, team_id: str = "team1") -> list:
    """Return deliverable dicts for a given group."""
    phase = get_phase(phase_id, team_id)
    for g in phase.get("groups", []):
        if g.get("id") == group_id:
            return g.get("deliverables", [])
    return []


def get_exit_conditions(phase_id: str, team_id: str = "team1") -> dict:
    return get_phase(phase_id, team_id).get("exit_conditions", {})


def get_next_phase(current_phase: str, team_id: str = "team1") -> str:
    for t in load_workflow(team_id).get("transitions", []):
        if t["from"] == current_phase:
            return t["to"]
    return ""


def get_rules(team_id: str = "team1") -> dict:
    return load_workflow(team_id).get("rules", {})


def check_phase_complete(phase_id: str, agent_outputs: dict, team_id: str = "team1") -> dict:
    phase = get_phase(phase_id, team_id)
    if not phase:
        return {"complete": False, "missing_agents": [], "missing_deliverables": [],
                "issues": [f"Phase '{phase_id}' inconnue"]}

    missing_deliverables = []
    for group in phase.get("groups", []):
        gid = group.get("id", "")
        for d in group.get("deliverables", []):
            if not d.get("required"):
                continue
            output_key = f"{gid}:{d['id']}"
            output = agent_outputs.get(output_key, {})
            if output and output.get("status") in ("complete", "pending_review", "approved"):
                continue
            missing_deliverables.append(output_key)

    return {
        "complete": not missing_deliverables,
        "missing_agents": [],
        "missing_deliverables": missing_deliverables,
        "issues": [],
    }


def can_transition(current_phase: str, agent_outputs: dict, legal_alerts: list = None, team_id: str = "team1") -> dict:
    next_phase = get_next_phase(current_phase, team_id)
    if not next_phase:
        return {"allowed": False, "next_phase": "", "reason": "Pas de phase suivante", "missing": []}

    check = check_phase_complete(current_phase, agent_outputs, team_id)
    if not check["complete"]:
        reasons = []
        if check["missing_agents"]:
            reasons.append(f"Agents manquants: {', '.join(check['missing_agents'])}")
        if check["missing_deliverables"]:
            reasons.append(f"Livrables manquants: {', '.join(check['missing_deliverables'])}")
        if check["issues"]:
            reasons.append(f"Problemes: {', '.join(check['issues'])}")
        return {"allowed": False, "next_phase": next_phase, "reason": " | ".join(reasons),
                "missing": check["missing_agents"] + check["missing_deliverables"]}

    exit_conds = get_exit_conditions(current_phase, team_id)
    if exit_conds.get("no_critical_alerts") and legal_alerts:
        critical = [a for a in legal_alerts if a.get("level") == "critical" and not a.get("resolved")]
        if critical:
            return {"allowed": False, "next_phase": next_phase,
                    "reason": f"{len(critical)} alerte(s) critique(s)", "missing": []}

    return {"allowed": True, "next_phase": next_phase, "reason": "Phase complete",
            "missing": [], "needs_human_gate": exit_conds.get("human_gate", False)}


def _get_boss_map(team_id: str) -> dict:
    """Build a map of agent_id -> boss_id from the team registry's delegates_to."""
    registry = load_team_json(team_id, "agents_registry.json")
    if not registry:
        return {}
    boss_map = {}
    for agent_id, conf in registry.get("agents", {}).items():
        for sub in conf.get("delegates_to", []):
            boss_map[sub] = agent_id
    return boss_map


def get_agents_to_dispatch(phase_id: str, agent_outputs: dict, team_id: str = "team1") -> list:
    """Derive agents to dispatch from deliverables to dispatch.
    If an agent has a Boss (another agent with delegates_to containing it),
    dispatch the Boss instead."""
    deliverables = get_deliverables_to_dispatch(phase_id, agent_outputs, team_id)
    boss_map = _get_boss_map(team_id)
    seen = set()
    result = []
    for d in deliverables:
        aid = d["agent_id"]
        # If agent has a boss, dispatch boss instead
        dispatch_id = boss_map.get(aid, aid)
        if dispatch_id not in seen:
            seen.add(dispatch_id)
            result.append({
                "agent_id": dispatch_id,
                "role": dispatch_id,
                "required": d.get("required", True),
                "parallel_group": d.get("parallel_group", "A"),
            })
    return result


def get_deliverables_to_dispatch(phase_id: str, agent_outputs: dict, team_id: str = "team1") -> list:
    """Return deliverables ready to dispatch. Groups are sequential: A must finish before B starts.
    Output key in agent_outputs = GROUP:deliverable_id."""
    phase = get_phase(phase_id, team_id)
    if not phase:
        return []

    groups = phase.get("groups", [])
    if not groups:
        return []

    max_parallel = get_rules(team_id).get("max_agents_parallel", 5)
    to_dispatch = []

    for idx, group in enumerate(groups):
        gid = group.get("id", "")

        # Check all previous groups' required deliverables are done
        prev_done = True
        for prev_group in groups[:idx]:
            pgid = prev_group.get("id", "")
            for d in prev_group.get("deliverables", []):
                if not d.get("required"):
                    continue
                output_key = f"{pgid}:{d['id']}"
                status = agent_outputs.get(output_key, {}).get("status", "")
                if status not in ("complete", "pending_review", "approved"):
                    prev_done = False
                    break
            if not prev_done:
                break
        if not prev_done:
            break

        # Dispatch deliverables in current group that are not yet done
        for d in group.get("deliverables", []):
            output_key = f"{gid}:{d['id']}"
            existing = agent_outputs.get(output_key, {}).get("status", "")
            # Fallback: check disk
            if not existing:
                existing = _check_deliverable_on_disk(d.get("agent", ""), d["id"])
            if existing in ("complete", "pending_review", "approved"):
                continue
            to_dispatch.append({
                "deliverable_key": f"{gid}:{d['id']}",
                "agent_id": d.get("agent", ""),
                "step": d["id"],
                "parallel_group": gid,
                "required": d.get("required", True),
                "type": d.get("type", ""),
                "description": d.get("description", d["id"]),
            })

        if to_dispatch:
            break  # Only dispatch one group at a time

    return to_dispatch[:max_parallel]


def get_workflow_status(current_phase: str, agent_outputs: dict, team_id: str = "team1") -> dict:
    wf = load_workflow(team_id)
    status = {"current_phase": current_phase, "phases": {}}
    for pid, pconf in wf.get("phases", {}).items():
        check = check_phase_complete(pid, agent_outputs, team_id)
        # Build agents status from groups
        agents_status = {}
        for group in pconf.get("groups", []):
            gid = group.get("id", "")
            for d in group.get("deliverables", []):
                aid = d.get("agent", "")
                if aid and aid not in agents_status:
                    output_key = f"{gid}:{d['id']}"
                    output = agent_outputs.get(output_key, {})
                    agents_status[aid] = {
                        "name": aid,
                        "required": d.get("required", False),
                        "status": output.get("status", "pending"),
                        "group": gid,
                    }
        # Build deliverable defs from groups
        deliv_defs = {}
        for group in pconf.get("groups", []):
            gid = group.get("id", "")
            for d in group.get("deliverables", []):
                dk = f"{gid}:{d['id']}"
                deliv_defs[dk] = {
                    "agent": d.get("agent", ""),
                    "required": d.get("required", False),
                    "type": d.get("type", ""),
                    "description": d.get("description", d["id"]),
                    "step": d["id"],
                    "depends_on": d.get("depends_on", []),
                }
        status["phases"][pid] = {
            "name": pconf.get("name", pid), "order": pconf.get("order", 0),
            "complete": check["complete"], "current": pid == current_phase,
            "agents": agents_status,
            "missing": check.get("missing_agents", []) + check.get("missing_deliverables", []),
            "deliverable_defs": deliv_defs,
        }
    return status

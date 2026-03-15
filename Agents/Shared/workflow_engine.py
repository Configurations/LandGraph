"""Workflow Engine — Lit workflow.json via team_resolver, valide les transitions."""
import logging
from agents.shared.team_resolver import load_team_json

logger = logging.getLogger("workflow_engine")

_workflows = {}


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


def get_phase(phase_id: str, team_id: str = "team1") -> dict:
    return load_workflow(team_id).get("phases", {}).get(phase_id, {})


def get_phase_agents(phase_id: str, team_id: str = "team1") -> dict:
    return get_phase(phase_id, team_id).get("agents", {})


def get_agents_for_group(phase_id: str, group: str, team_id: str = "team1") -> list:
    agents = get_phase_agents(phase_id, team_id)
    return [aid for aid, conf in agents.items() if conf.get("parallel_group") == group]


def get_ordered_groups(phase_id: str, team_id: str = "team1") -> list:
    agents = get_phase_agents(phase_id, team_id)
    return sorted(set(conf.get("parallel_group", "A") for conf in agents.values()))


def get_required_deliverables(phase_id: str, team_id: str = "team1") -> list:
    phase = get_phase(phase_id, team_id)
    return [k for k, v in phase.get("deliverables", {}).items() if v.get("required")]


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
        return {"complete": False, "missing_agents": [], "missing_deliverables": [], "issues": [f"Phase '{phase_id}' inconnue"]}

    issues, missing_agents, missing_deliverables = [], [], []

    for aid, aconf in phase.get("agents", {}).items():
        if not aconf.get("required"):
            continue
        output = agent_outputs.get(aid, {})
        if not output:
            missing_agents.append(aid)
        elif output.get("status") != "complete":
            issues.append(f"{aid}: status={output.get('status', 'missing')}")

    for dk, dconf in phase.get("deliverables", {}).items():
        if not dconf.get("required"):
            continue
        aid = dconf.get("agent", "")
        deliverables = agent_outputs.get(aid, {}).get("deliverables", {})
        if dk not in deliverables:
            missing_deliverables.append(f"{dk} (de {aid})")

    return {
        "complete": not missing_agents and not missing_deliverables and not issues,
        "missing_agents": missing_agents,
        "missing_deliverables": missing_deliverables,
        "issues": issues,
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


def get_agents_to_dispatch(phase_id: str, agent_outputs: dict, team_id: str = "team1") -> list:
    agents = get_phase_agents(phase_id, team_id)
    if not agents:
        return []

    groups = get_ordered_groups(phase_id, team_id)
    max_parallel = get_rules(team_id).get("max_agents_parallel", 3)
    to_dispatch = []

    for group in groups:
        group_agents = get_agents_for_group(phase_id, group, team_id)

        # Groupes precedents termines ?
        prev_done = True
        for pg in [g for g in groups if g < group]:
            for aid in get_agents_for_group(phase_id, pg, team_id):
                if agents[aid].get("required") and agent_outputs.get(aid, {}).get("status") != "complete":
                    prev_done = False
                    break
        if not prev_done:
            break

        for aid in group_agents:
            conf = agents[aid]
            if agent_outputs.get(aid, {}).get("status") == "complete":
                continue
            if conf.get("delegated_by"):
                continue
            deps = conf.get("depends_on", [])
            if all(agent_outputs.get(d, {}).get("status") == "complete" for d in deps):
                to_dispatch.append({"agent_id": aid, "role": conf.get("role", ""),
                                    "required": conf.get("required", False),
                                    "parallel_group": conf.get("parallel_group", "A")})

        if to_dispatch:
            break

    return to_dispatch[:max_parallel]


def get_workflow_status(current_phase: str, agent_outputs: dict, team_id: str = "team1") -> dict:
    wf = load_workflow(team_id)
    status = {"current_phase": current_phase, "phases": {}}
    for pid, pconf in wf.get("phases", {}).items():
        check = check_phase_complete(pid, agent_outputs, team_id)
        agents_status = {}
        for aid, aconf in pconf.get("agents", {}).items():
            output = agent_outputs.get(aid, {})
            agents_status[aid] = {
                "name": aconf.get("role", aid),
                "required": aconf.get("required", False),
                "status": output.get("status", "pending"),
                "group": aconf.get("parallel_group", "A"),
            }
        # Deliverable definitions from Workflow.json
        deliv_defs = {}
        for dk, dv in pconf.get("deliverables", {}).items():
            deliv_defs[dk] = {
                "agent": dv.get("agent", ""),
                "required": dv.get("required", False),
                "type": dv.get("type", ""),
                "description": dv.get("description", dk),
            }
        status["phases"][pid] = {
            "name": pconf.get("name", pid), "order": pconf.get("order", 0),
            "complete": check["complete"], "current": pid == current_phase,
            "agents": agents_status,
            "missing": check.get("missing_agents", []) + check.get("missing_deliverables", []),
            "deliverable_defs": deliv_defs,
        }
    return status

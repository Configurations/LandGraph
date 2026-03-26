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

    # Check deliverable-level completion (keyed by agent_id:step)
    for dk, dconf in phase.get("deliverables", {}).items():
        if not dconf.get("required"):
            continue
        aid = dconf.get("agent", "")
        step = dconf.get("step", dconf.get("pipeline_step", dk))
        output_key = f"{aid}:{step}"
        output = agent_outputs.get(output_key, {})
        if output and output.get("status") == "complete":
            continue
        # Fallback: check legacy format (agent_outputs[agent_id].deliverables[step or dk])
        legacy_output = agent_outputs.get(aid, {})
        if legacy_output.get("status") in ("complete", "pending_review", "approved"):
            legacy_delivs = legacy_output.get("deliverables", {})
            if step in legacy_delivs or dk in legacy_delivs:
                continue
        missing_deliverables.append(f"{dk} ({output_key})")

    # Check agent-level: an agent is considered missing if ALL its deliverables are missing
    for aid, aconf in phase.get("agents", {}).items():
        if not aconf.get("required"):
            continue
        agent_dels = [dk for dk, dv in phase.get("deliverables", {}).items() if dv.get("agent") == aid]
        if agent_dels:
            # Agent completion is derived from its deliverables
            continue
        # Agent with no deliverables in workflow — check legacy
        output = agent_outputs.get(aid, {})
        if not output:
            missing_agents.append(aid)
        elif output.get("status") != "complete":
            issues.append(f"{aid}: status={output.get('status', 'missing')}")

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


def get_deliverables_to_dispatch(phase_id: str, agent_outputs: dict, team_id: str = "team1") -> list:
    """Return deliverables ready to dispatch in the current phase.
    Each deliverable maps to one agent + one step.
    Returns list of dicts: {deliverable_key, agent_id, step, parallel_group, required, type, description}."""
    phase = get_phase(phase_id, team_id)
    if not phase:
        return []

    deliverables = phase.get("deliverables", {})
    agents = phase.get("agents", {})
    if not deliverables:
        return []

    groups = get_ordered_groups(phase_id, team_id)
    max_parallel = get_rules(team_id).get("max_agents_parallel", 5)
    to_dispatch = []

    for group in groups:
        # Check if previous groups' required deliverables are done
        prev_done = True
        for pg in [g for g in groups if g < group]:
            pg_agents = set(get_agents_for_group(phase_id, pg, team_id))
            for dk, dconf in deliverables.items():
                if dconf.get("agent", "") not in pg_agents:
                    continue
                if not dconf.get("required"):
                    continue
                d_agent = dconf.get("agent", "")
                d_step = dconf.get("step", dconf.get("pipeline_step", dk))
                output_key = f"{d_agent}:{d_step}"
                prev_status = agent_outputs.get(output_key, {}).get("status", "")
                # Fallback legacy
                if not prev_status:
                    leg = agent_outputs.get(d_agent, {})
                    if leg.get("status") in ("complete", "pending_review", "approved"):
                        if d_step in leg.get("deliverables", {}) or dk in leg.get("deliverables", {}):
                            prev_status = leg.get("status")
                if prev_status not in ("complete", "pending_review", "approved"):
                    prev_done = False
                    break
            if not prev_done:
                break
        if not prev_done:
            break

        group_agents = set(get_agents_for_group(phase_id, group, team_id))

        for dk, dconf in deliverables.items():
            agent_id = dconf.get("agent", "")
            if agent_id not in group_agents:
                continue
            aconf = agents.get(agent_id, {})
            if aconf.get("delegated_by"):
                continue
            deps = aconf.get("depends_on", [])
            # Check agent-level depends_on: all deliverables of dep agents must be done
            deps_ok = True
            for dep_aid in deps:
                dep_dels = [d for d in deliverables.values()
                            if d.get("agent") == dep_aid and d.get("required")]
                def _dep_done(dep_aid, d):
                    s = agent_outputs.get(f"{dep_aid}:{d.get('step', d.get('pipeline_step', ''))}", {}).get("status", "")
                    if not s:
                        leg = agent_outputs.get(dep_aid, {})
                        if leg.get("status") in ("complete", "pending_review", "approved"):
                            st = d.get("step", d.get("pipeline_step", ""))
                            if st in leg.get("deliverables", {}):
                                return True
                    return s in ("complete", "pending_review", "approved")
                if any(not _dep_done(dep_aid, d) for d in dep_dels):
                    deps_ok = False
                    break
            if not deps_ok:
                continue

            # Check deliverable-level depends_on
            deliv_deps = dconf.get("depends_on", [])
            deliv_deps_ok = True
            for dep_dk in deliv_deps:
                dep_dconf = deliverables.get(dep_dk, {})
                dep_agent = dep_dconf.get("agent", "")
                dep_step = dep_dconf.get("step", dep_dconf.get("pipeline_step", dep_dk))
                dep_output_key = f"{dep_agent}:{dep_step}" if dep_agent else dep_dk
                dep_status = agent_outputs.get(dep_output_key, {}).get("status", "")
                # Legacy fallback
                if not dep_status and dep_agent:
                    leg = agent_outputs.get(dep_agent, {})
                    if leg.get("status") in ("complete", "pending_review", "approved"):
                        if dep_step in leg.get("deliverables", {}) or dep_dk in leg.get("deliverables", {}):
                            dep_status = leg.get("status")
                if dep_status not in ("complete", "pending_review", "approved"):
                    deliv_deps_ok = False
                    break
            if not deliv_deps_ok:
                continue

            step = dconf.get("step", dconf.get("pipeline_step", dk))
            output_key = f"{agent_id}:{step}"
            existing_status = agent_outputs.get(output_key, {}).get("status", "")
            # Fallback: check legacy format (agent_outputs[agent_id].deliverables[step])
            if not existing_status:
                legacy = agent_outputs.get(agent_id, {})
                if legacy.get("status") in ("complete", "pending_review", "approved"):
                    legacy_delivs = legacy.get("deliverables", {})
                    if step in legacy_delivs or dk in legacy_delivs:
                        existing_status = legacy.get("status")
            # Fallback: check if deliverable file exists on disk (state may have been lost)
            if not existing_status:
                existing_status = _check_deliverable_on_disk(agent_id, step)
            # Don't re-dispatch if already complete, pending review, or approved
            if existing_status in ("complete", "pending_review", "approved"):
                continue

            to_dispatch.append({
                "deliverable_key": dk,
                "agent_id": agent_id,
                "step": step,
                "parallel_group": aconf.get("parallel_group", "A"),
                "required": dconf.get("required", True),
                "type": dconf.get("type", ""),
                "description": dconf.get("description", dk),
            })

        if to_dispatch:
            break  # Only dispatch one group at a time

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
                "step": dv.get("step", dv.get("pipeline_step", "")),
                "depends_on": dv.get("depends_on", []),
            }
        status["phases"][pid] = {
            "name": pconf.get("name", pid), "order": pconf.get("order", 0),
            "complete": check["complete"], "current": pid == current_phase,
            "agents": agents_status,
            "missing": check.get("missing_agents", []) + check.get("missing_deliverables", []),
            "deliverable_defs": deliv_defs,
        }
    return status

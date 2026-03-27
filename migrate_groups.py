#!/usr/bin/env python3
"""Migrate .wrk.json files from agents+deliverables to groups format."""
import json
import os
import sys


def migrate_phase(phase: dict) -> dict:
    """Convert a phase from old format (agents+deliverables) to new (groups)."""
    if phase.get("type") == "external":
        return phase
    # Already migrated?
    if "groups" in phase:
        return phase

    agents = phase.get("agents", {})
    deliverables = phase.get("deliverables", {})

    # 1. Collect groups from agents' parallel_group
    group_map: dict[str, list] = {}
    for agent_id, agent_conf in agents.items():
        gid = agent_conf.get("parallel_group", "A")
        if gid not in group_map:
            group_map[gid] = []

    # Ensure at least group A exists
    if not group_map:
        group_map["A"] = []

    # 2. Distribute deliverables into groups based on their agent
    for dk, dconf in deliverables.items():
        agent_id = dconf.get("agent", "")
        agent_conf = agents.get(agent_id, {})
        gid = agent_conf.get("parallel_group", "A")
        if gid not in group_map:
            group_map[gid] = []

        # Parse old key format: "agent_id:pipeline_step" or just the key
        parts = dk.split(":", 1)
        del_id = parts[1] if len(parts) > 1 else dconf.get("pipeline_step", dk)

        # Convert depends_on from "agent:step" to "GROUP:step"
        new_depends = []
        for dep in dconf.get("depends_on", []):
            dep_parts = dep.split(":", 1)
            if len(dep_parts) == 2:
                dep_agent, dep_step = dep_parts
                dep_agent_conf = agents.get(dep_agent, {})
                dep_gid = dep_agent_conf.get("parallel_group", "A")
                new_depends.append(f"{dep_gid}:{dep_step}")
            else:
                new_depends.append(dep)

        new_del = {
            "id": del_id,
            "Name": dconf.get("name", dconf.get("description", dk)[:60] if dconf.get("description") else dk),
            "agent": agent_id,
            "required": dconf.get("required", True),
            "type": dconf.get("type", ""),
            "description": dconf.get("description", ""),
            "depends_on": new_depends,
        }
        # Preserve optional fields
        for field in ("roles", "missions", "skills", "category"):
            if field in dconf:
                new_del[field] = dconf[field]

        group_map[gid].append(new_del)

    # 3. Build groups array sorted by id
    groups = [{"id": gid, "deliverables": dels}
              for gid, dels in sorted(group_map.items())]

    # 4. Build new phase
    new_phase = {"name": phase.get("name", ""), "order": phase.get("order", 0)}
    if phase.get("description"):
        new_phase["description"] = phase["description"]
    new_phase["groups"] = groups
    new_phase["exit_conditions"] = phase.get("exit_conditions", {})
    if phase.get("next_phase"):
        new_phase["next_phase"] = phase["next_phase"]
    return new_phase


def migrate_workflow(data: dict) -> dict:
    """Migrate a full workflow dict."""
    new_data = {}
    new_phases = {}
    for pid, phase in data.get("phases", {}).items():
        new_phases[pid] = migrate_phase(phase)
    new_data["phases"] = new_phases
    new_data["transitions"] = data.get("transitions", [])
    new_data["rules"] = data.get("rules", {})
    # Keep team, categories if present
    if "team" in data:
        new_data["team"] = data["team"]
    if "categories" in data:
        new_data["categories"] = data["categories"]
    # Remove old parallel_groups root (not copied)
    return new_data


def migrate_file(filepath: str, dry_run: bool = False) -> bool:
    """Migrate a single .wrk.json file. Returns True if changed."""
    with open(filepath, encoding="utf-8") as f:
        data = json.load(f)

    migrated = migrate_workflow(data)

    if dry_run:
        print(f"  [DRY RUN] {filepath}")
        print(json.dumps(migrated, indent=2, ensure_ascii=False)[:500])
        return True

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(migrated, f, indent=2, ensure_ascii=False)
    print(f"  [MIGRATED] {filepath}")
    return True


def main():
    dry_run = "--dry-run" in sys.argv
    dirs = sys.argv[1:] if sys.argv[1:] else ["Shared/Projects"]
    dirs = [d for d in dirs if d != "--dry-run"]

    for base_dir in dirs:
        if not os.path.isdir(base_dir):
            print(f"SKIP: {base_dir} not found")
            continue
        for root, _, files in os.walk(base_dir):
            for fname in files:
                if fname.endswith(".wrk.json"):
                    migrate_file(os.path.join(root, fname), dry_run)


if __name__ == "__main__":
    main()

"""Analysis service — orchestrator-driven project analysis conversation."""

from __future__ import annotations

import json
import os
from typing import Any, Optional

import httpx
import structlog

from core.config import settings, _find_config_dir, load_teams
from core.database import execute, fetch_all, fetch_one
from schemas.rag import AnalysisMessage

log = structlog.get_logger(__name__)

ONBOARDING_THREAD_PREFIX = "onboarding-"
_HTTP_TIMEOUT = 30
_MAX_CONVERSATION_CONTEXT = 20


# ── Helpers ──────────────────────────────────────────────────────


async def _resolve_orchestrator(team_id: str) -> dict[str, str]:
    """Find orchestrator agent from agents_registry.json."""
    teams = load_teams()
    team_dir = ""
    for t in teams:
        if t["id"] == team_id:
            team_dir = t.get("directory", "")
            break
    if not team_dir:
        raise ValueError(f"Team {team_id} not found")

    config_dir = _find_config_dir()
    for candidate in [
        os.path.join(config_dir, "Teams", team_dir, "agents_registry.json"),
        os.path.join(config_dir, team_dir, "agents_registry.json"),
    ]:
        if os.path.isfile(candidate):
            with open(candidate, encoding="utf-8") as f:
                registry = json.load(f)
            for aid, cfg in registry.get("agents", {}).items():
                if cfg.get("type") == "orchestrator":
                    return {"agent_id": aid, "name": cfg.get("name", aid)}
            break

    raise ValueError(f"No orchestrator found for team {team_id}")


def _build_instruction(
    project_slug: str,
    project_name: str,
    team_name: str,
    documents: list[str],
) -> str:
    doc_list = "\n".join(f"- {d}" for d in documents) if documents else "(aucun document)"
    return (
        f"Tu es l'orchestrateur de l'equipe {team_name}. "
        f"Un nouveau projet '{project_name}' (slug: {project_slug}) vient d'etre cree.\n\n"
        f"Documents fournis :\n{doc_list}\n\n"
        "Ta mission :\n"
        "1. Analyse les documents fournis via le RAG\n"
        "2. Pose des questions pour clarifier le perimetre, les objectifs, les contraintes\n"
        "3. Delegue aux agents specialises si necessaire\n"
        "4. Quand le projet est clair, produis une synthese structuree\n"
    )


def _build_relaunch_instruction(
    conversation: list[AnalysisMessage],
    new_message: str,
) -> str:
    recent = conversation[-_MAX_CONVERSATION_CONTEXT:]
    lines = []
    for m in recent:
        prefix = "Agent" if m.sender == "agent" else "Utilisateur"
        lines.append(f"[{prefix}] {m.content[:500]}")
    history = "\n".join(lines)
    return (
        "Voici l'historique de la conversation d'analyse du projet :\n\n"
        f"{history}\n\n"
        f"Nouveau message de l'utilisateur : {new_message}\n\n"
        "Continue l'analyse en tenant compte de ce nouveau message."
    )


def _uploads_dir(slug: str) -> str:
    return os.path.join(settings.ag_flow_root, "projects", slug, "uploads")


async def _load_deduced_prompt(
    project_slug: str,
    project_name: str,
    documents: list[str],
) -> Optional[str]:
    """Load the orchestrator prompt deduced at step 3 of the wizard.

    Returns the prompt content with project context injected, or None if
    no deduced prompt is available (fallback to default instruction).
    """
    from services import wizard_data_service
    from services.project_type_service import _shared_projects_dir

    step3 = await wizard_data_service.get_step(project_slug, 3)
    if not step3:
        return None

    type_id = step3.get("selectedTypeId", "")
    prompt_filename = step3.get("orchestratorPrompt", "")
    if not type_id or not prompt_filename:
        return None

    prompt_path = os.path.join(_shared_projects_dir(), type_id, prompt_filename)
    if not os.path.isfile(prompt_path):
        log.warning(
            "deduced_prompt_not_found",
            slug=project_slug,
            path=prompt_path,
        )
        return None

    with open(prompt_path, encoding="utf-8") as f:
        prompt_content = f.read()

    doc_list = "\n".join(f"- {d}" for d in documents) if documents else "(aucun document)"
    return (
        f"Nouveau projet : {project_name} (slug: {project_slug})\n\n"
        f"Documents fournis (consultables via RAG) :\n{doc_list}\n\n"
        f"---\n\n{prompt_content}"
    )


# ── Public API ───────────────────────────────────────────────────


async def start_analysis(
    project_slug: str,
    team_id: str,
    workflow_id: Optional[int] = None,
) -> dict[str, Any]:
    """Launch the team orchestrator to analyze the project."""
    orch = await _resolve_orchestrator(team_id)
    agent_id = orch["agent_id"]

    proj = await fetch_one(
        "SELECT name FROM project.pm_projects WHERE slug = $1",
        project_slug,
    )
    project_name = proj["name"] if proj else project_slug

    teams = load_teams()
    team_name = team_id
    for t in teams:
        if t["id"] == team_id:
            team_name = t.get("name", team_id)
            break

    uploads = _uploads_dir(project_slug)
    documents: list[str] = []
    if os.path.isdir(uploads):
        documents = [f for f in os.listdir(uploads) if not f.startswith(".")]

    thread_id = f"{ONBOARDING_THREAD_PREFIX}{project_slug}"
    rag_endpoint = f"{settings.hitl_internal_url}/api/internal/rag/search"

    # Try to load deduced orchestrator prompt from create-project.json
    instruction = await _load_deduced_prompt(project_slug, project_name, documents)
    if not instruction:
        instruction = _build_instruction(project_slug, project_name, team_name, documents)

    # Create a tracking task row in dispatcher_tasks (for event storage)
    task_row = await fetch_one(
        """INSERT INTO project.dispatcher_tasks
           (agent_id, team_id, thread_id, project_slug, phase, instruction, status, docker_image)
           VALUES ($1, $2, $3, $4, 'discovery', $5, 'running', 'gateway')
           RETURNING id""",
        agent_id, team_id, thread_id, project_slug, instruction[:4000],
    )
    task_id = str(task_row["id"]) if task_row else ""

    # Call gateway /invoke instead of dispatcher (full multi-agent orchestration)
    gateway_url = settings.langgraph_api_url or "http://langgraph-api:8000"
    invoke_payload: dict[str, Any] = {
        "messages": [{"role": "user", "content": instruction}],
        "team_id": team_id,
        "thread_id": thread_id,
        "project_slug": project_slug,
    }

    try:
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                f"{gateway_url}/invoke", json=invoke_payload,
            )
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPError as exc:
        log.error("analysis_dispatch_failed", slug=project_slug, error=str(exc))
        await execute(
            "UPDATE project.dispatcher_tasks SET status = 'failure', error_message = $1 WHERE id = $2::uuid",
            str(exc)[:500], task_id,
        )
        return {"error": "gateway_unavailable"}

    # Store orchestrator decisions as progress event
    decisions = data.get("decisions", [])
    agents_dispatched = data.get("agents_dispatched", [])
    await execute(
        """INSERT INTO project.dispatcher_task_events (task_id, event_type, data)
           VALUES ($1::uuid, 'progress', $2::jsonb)""",
        task_id,
        json.dumps({"data": data.get("output", ""), "agents_dispatched": agents_dispatched},
                    ensure_ascii=False),
    )

    await execute(
        "UPDATE project.pm_projects SET analysis_task_id = $1, analysis_status = 'in_progress' WHERE slug = $2",
        task_id, project_slug,
    )

    log.info("analysis_started", slug=project_slug, task_id=task_id, agent_id=agent_id,
             agents_dispatched=agents_dispatched)
    return {"task_id": task_id, "agent_id": agent_id, "status": "started"}


async def _sync_status(project_slug: str, task_id: str) -> str:
    """Sync analysis_status with dispatcher state and pending questions."""
    thread_id = f"{ONBOARDING_THREAD_PREFIX}{project_slug}"

    pending = await fetch_one(
        "SELECT id FROM project.hitl_requests WHERE thread_id = $1 AND status = 'pending' LIMIT 1",
        thread_id,
    )
    if pending:
        await execute(
            "UPDATE project.pm_projects SET analysis_status = 'waiting_input' WHERE slug = $1",
            project_slug,
        )
        return "waiting_input"

    # Check task status from dispatcher_tasks table directly (gateway writes here)
    task_row = await fetch_one(
        "SELECT status FROM project.dispatcher_tasks WHERE id = $1::uuid", task_id,
    )
    if not task_row:
        return "in_progress"

    status = task_row.get("status", "")
    if status in ("success",):
        new_status = "completed"
    elif status in ("failure", "timeout", "cancelled"):
        new_status = "failed"
    else:
        new_status = "in_progress"

    await execute(
        "UPDATE project.pm_projects SET analysis_status = $1 WHERE slug = $2",
        new_status, project_slug,
    )
    return new_status


async def get_analysis_status(project_slug: str) -> dict[str, Any]:
    """Get analysis status, syncing with dispatcher."""
    row = await fetch_one(
        "SELECT analysis_task_id, analysis_status FROM project.pm_projects WHERE slug = $1",
        project_slug,
    )
    if not row or not row.get("analysis_task_id"):
        return {
            "status": "not_started",
            "task_id": None,
            "has_pending_question": False,
            "pending_request_id": None,
        }

    task_id = row["analysis_task_id"]
    current = row.get("analysis_status") or "not_started"

    if current not in ("completed", "failed", "not_started"):
        current = await _sync_status(project_slug, task_id)

    thread_id = f"{ONBOARDING_THREAD_PREFIX}{project_slug}"
    pending = await fetch_one(
        "SELECT id FROM project.hitl_requests WHERE thread_id = $1 AND status = 'pending' LIMIT 1",
        thread_id,
    )

    return {
        "status": current,
        "task_id": task_id,
        "has_pending_question": pending is not None,
        "pending_request_id": str(pending["id"]) if pending else None,
    }


async def get_conversation(project_slug: str) -> list[AnalysisMessage]:
    """Merge dispatcher events + HITL requests + rag_conversations."""
    thread_id = f"{ONBOARDING_THREAD_PREFIX}{project_slug}"
    messages: list[AnalysisMessage] = []

    # 1. Dispatcher events via thread_id
    event_rows = await fetch_all(
        """
        SELECT e.id, e.event_type, e.data, e.created_at
        FROM project.dispatcher_task_events e
        JOIN project.dispatcher_tasks t ON e.task_id = t.id
        WHERE t.thread_id = $1
        ORDER BY e.created_at ASC
        """,
        thread_id,
    )
    for r in event_rows:
        etype = r["event_type"]
        data = r["data"] if isinstance(r["data"], dict) else {}
        content = data.get("data", data.get("content", str(data)))
        if isinstance(content, dict):
            content = json.dumps(content, ensure_ascii=False)

        msg_type = etype if etype in ("progress", "artifact", "result") else "progress"

        messages.append(AnalysisMessage(
            id=f"evt-{r['id']}",
            sender="agent",
            type=msg_type,
            content=str(content)[:5000],
            artifact_key=data.get("key") if etype == "artifact" else None,
            created_at=r["created_at"].isoformat(),
        ))

    # 2. HITL requests (questions + answers)
    hitl_rows = await fetch_all(
        """
        SELECT id, prompt, response, status, created_at, answered_at
        FROM project.hitl_requests
        WHERE thread_id = $1
        ORDER BY created_at ASC
        """,
        thread_id,
    )
    for r in hitl_rows:
        messages.append(AnalysisMessage(
            id=f"q-{r['id']}",
            sender="agent",
            type="question",
            content=r["prompt"],
            request_id=str(r["id"]),
            status=r["status"],
            created_at=r["created_at"].isoformat(),
        ))
        if r["status"] == "answered" and r["response"]:
            ts = r["answered_at"] or r["created_at"]
            messages.append(AnalysisMessage(
                id=f"a-{r['id']}",
                sender="user",
                type="reply",
                content=r["response"],
                request_id=str(r["id"]),
                created_at=ts.isoformat(),
            ))

    # 3. User free messages from rag_conversations
    conv_rows = await fetch_all(
        """
        SELECT id, sender, content, created_at
        FROM project.rag_conversations
        WHERE project_slug = $1
        ORDER BY created_at ASC
        """,
        project_slug,
    )
    for r in conv_rows:
        messages.append(AnalysisMessage(
            id=f"msg-{r['id']}",
            sender=r["sender"],
            type="reply" if r["sender"] == "user" else "progress",
            content=r["content"],
            created_at=r["created_at"].isoformat(),
        ))

    messages.sort(key=lambda m: m.created_at)
    return messages


async def reply_to_question(
    project_slug: str,
    request_id: str,
    response: str,
    reviewer: str,
) -> dict[str, Any]:
    """Reply to an agent HITL question."""
    thread_id = f"{ONBOARDING_THREAD_PREFIX}{project_slug}"

    row = await fetch_one(
        "SELECT id, thread_id, status FROM project.hitl_requests WHERE id = $1::uuid",
        request_id,
    )
    if not row:
        raise ValueError("Question not found")
    if row["thread_id"] != thread_id:
        raise ValueError("Question does not belong to this project")
    if row["status"] != "pending":
        raise ValueError("Question already answered")

    await execute(
        """
        UPDATE project.hitl_requests
        SET status = 'answered', response = $1, reviewer = $2,
            response_channel = 'hitl-console', answered_at = NOW()
        WHERE id = $3::uuid
        """,
        response, reviewer, request_id,
    )

    await execute(
        "UPDATE project.pm_projects SET analysis_status = 'in_progress' WHERE slug = $1",
        project_slug,
    )

    return {"ok": True}


async def send_free_message(
    project_slug: str,
    content: str,
    user_email: str,
) -> dict[str, Any]:
    """Send a free message — cancel current task and relaunch agent."""
    await execute(
        "INSERT INTO project.rag_conversations (project_slug, sender, content) VALUES ($1, $2, $3)",
        project_slug, "user", content,
    )

    proj = await fetch_one(
        "SELECT team_id, analysis_task_id FROM project.pm_projects WHERE slug = $1",
        project_slug,
    )
    if not proj:
        raise ValueError("Project not found")

    team_id = proj["team_id"]
    old_task_id = proj["analysis_task_id"]

    conversation = await get_conversation(project_slug)
    instruction = _build_relaunch_instruction(conversation, content)

    thread_id = f"{ONBOARDING_THREAD_PREFIX}{project_slug}"

    # Call gateway /invoke (full multi-agent orchestration)
    gateway_url = settings.langgraph_api_url or "http://langgraph-api:8000"
    invoke_payload: dict[str, Any] = {
        "messages": [{"role": "user", "content": instruction}],
        "team_id": team_id,
        "thread_id": thread_id,
        "project_slug": project_slug,
    }

    try:
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                f"{gateway_url}/invoke", json=invoke_payload,
            )
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPError as exc:
        log.error("analysis_relaunch_failed", slug=project_slug, error=str(exc))
        return {"error": "gateway_unavailable"}

    # Store progress event
    if old_task_id:
        await execute(
            """INSERT INTO project.dispatcher_task_events (task_id, event_type, data)
               VALUES ($1::uuid, 'progress', $2::jsonb)""",
            old_task_id,
            json.dumps({"data": data.get("output", "")}, ensure_ascii=False),
        )

    await execute(
        "UPDATE project.pm_projects SET analysis_status = 'in_progress' WHERE slug = $1",
        project_slug,
    )

    return {"task_id": old_task_id or "", "status": "started"}

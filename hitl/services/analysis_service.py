"""Analysis service — orchestrator-driven project analysis conversation."""

from __future__ import annotations

import json
import os
from typing import Any, Optional

import httpx
import structlog

from core.config import settings, _find_config_dir, load_json_config, load_teams
from core.database import execute, fetch_all, fetch_one
from schemas.rag import AnalysisMessage

log = structlog.get_logger(__name__)

ONBOARDING_THREAD_PREFIX = "onboarding-"
_HTTP_TIMEOUT = 30


async def _resolve_thread_id(project_slug: str) -> str:
    """Resolve the thread_id for a project: workflow-{id} if available, fallback to onboarding-{slug}."""
    row = await fetch_one(
        "SELECT onboarding_workflow_id FROM project.pm_projects WHERE slug = $1",
        project_slug,
    )
    wf_id = row["onboarding_workflow_id"] if row else None
    if wf_id:
        return "workflow-{}".format(wf_id)
    return "{}{}".format(ONBOARDING_THREAD_PREFIX, project_slug)


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
    culture = os.getenv("CULTURE", "fr-fr")
    for base in ["/app/config", "/app/Shared", "config", "Shared"]:
        path = os.path.join(base, "Models", culture, "orchestrator-initial-instruction.md")
        if os.path.isfile(path):
            with open(path, encoding="utf-8") as f:
                template = f.read()
            return template.replace(
                "{team_name}", team_name
            ).replace(
                "{project_name}", project_name
            ).replace(
                "{project_slug}", project_slug
            ).replace(
                "{doc_list}", doc_list
            )
    return f"Nouveau projet '{project_name}' cree. Documents : {doc_list}"



def _uploads_dir(slug: str) -> str:
    return os.path.join(settings.ag_flow_root, "projects", slug, "uploads")


def _resolve_embedding_provider(project_slug: str) -> str:
    """Read embedding_provider from the project type's project.json."""
    from services.project_type_service import _shared_projects_dir
    from services import wizard_data_service
    import asyncio

    # Try to get type_id from wizard data (sync wrapper)
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # We're in an async context, use a direct DB call
            return ""
    except RuntimeError:
        pass
    return ""


async def _resolve_embedding_provider_async(project_slug: str) -> str:
    """Read embedding_provider from the project type's project.json (async)."""
    from services.project_type_service import _shared_projects_dir
    from services import wizard_data_service

    step3 = await wizard_data_service.get_step(project_slug, 3)
    if not step3:
        return ""
    type_id = step3.get("selectedTypeId", "")
    if not type_id:
        return ""
    type_dir = os.path.join(_shared_projects_dir(), type_id)
    pj_path = os.path.join(type_dir, "project.json")
    if not os.path.isfile(pj_path):
        return ""
    try:
        with open(pj_path, encoding="utf-8") as f:
            pj = json.load(f)
        return pj.get("embedding_provider", "")
    except Exception:
        return ""


async def _index_project_documents(
    project_slug: str,
    embedding_provider: str = "",
    task_id: str = "",
) -> tuple[int, list[str]]:
    """Index all uploaded documents into RAG with adaptive retry strategy.

    Strategy:
    - Warm-up: send a single embedding call and wait for it to succeed (model loading)
    - Then sequential first chunk
    - On first success → switch to parallel mode, reset wait to 2s
    - On error → switch to sequential, wait 2s, retry same chunk
    - On repeated error → double wait (4s, 8s, 16s... max 60s)
    - On success after error → back to parallel, reset wait to 2s
    """
    import asyncio as _aio
    from core.i18n import msg as _msg
    from services import rag_service
    from services import upload_service

    uploads = _uploads_dir(project_slug)
    if not os.path.isdir(uploads):
        return 0, []

    # Collect all (filename, chunk_index, chunk_text, content_type) tuples
    all_items: list[tuple[str, int, str, str]] = []
    file_set: set[str] = set()

    for root, _dirs, files in os.walk(uploads):
        for fname in sorted(files):
            if fname.startswith("."):
                continue
            filepath = os.path.join(root, fname)
            rel_name = os.path.relpath(filepath, uploads)
            text = upload_service.extract_text(filepath)
            if not text.strip():
                continue
            ext = os.path.splitext(fname)[1].lower()
            content_type = "text/markdown" if ext == ".md" else "text/plain"
            # Delete old entries
            await execute(
                "DELETE FROM project.rag_documents WHERE project_slug = $1 AND filename = $2",
                project_slug, rel_name,
            )
            chunks = rag_service.chunk_text(text)
            for idx, chunk in enumerate(chunks):
                all_items.append((rel_name, idx, chunk, content_type))
            if chunks:
                file_set.add(rel_name)

    if not all_items:
        return 0, []

    total = len(all_items)
    pool = rag_service.get_pool()
    indexed = 0
    wait_time = 2.0
    max_wait = 60.0
    last_progress_pct = -1

    async def _embed_and_store(item: tuple[str, int, str, str]) -> bool:
        """Embed one chunk and store it. Returns True on success."""
        rel_name, idx, chunk, ct = item
        vec = await rag_service.get_embedding(chunk, provider_id=embedding_provider)
        vec_str = "[" + ",".join(str(v) for v in vec) + "]"
        await pool.execute(
            """INSERT INTO project.rag_documents
               (project_slug, filename, content_type, chunk_index, content, embedding)
               VALUES ($1, $2, $3, $4, $5, $6::vector)""",
            project_slug, rel_name, ct, idx, chunk, vec_str,
        )
        return True

    async def _post_progress(done: int, total_count: int):
        nonlocal last_progress_pct
        pct = int(done * 100 / total_count) if total_count else 100
        if pct == last_progress_pct:
            return
        last_progress_pct = pct
        if task_id:
            msg = _msg("indexation_progress", done=done, total=total_count, pct=pct)
            await execute(
                """INSERT INTO project.dispatcher_task_events (task_id, event_type, data)
                   VALUES ($1::uuid, 'progress', $2::jsonb)""",
                task_id,
                json.dumps({"data": msg}, ensure_ascii=False),
            )

    max_retries = 10
    retries = 0

    # Warm-up: force the embedding model to load
    warmup_wait = 2.0
    for warmup_attempt in range(15):
        try:
            await rag_service.get_embedding("warmup", provider_id=embedding_provider)
            log.info("embedding_warmup_ok", attempt=warmup_attempt + 1)
            break
        except Exception:
            log.info("embedding_warmup_wait", attempt=warmup_attempt + 1, wait=warmup_wait)
            if task_id:
                await execute(
                    """INSERT INTO project.dispatcher_task_events (task_id, event_type, data)
                       VALUES ($1::uuid, 'progress', $2::jsonb)""",
                    task_id,
                    json.dumps({"data": _msg("embedding_warmup", attempt=warmup_attempt + 1)}, ensure_ascii=False),
                )
            await _aio.sleep(warmup_wait)
            warmup_wait = min(warmup_wait * 1.5, 30.0)

    # Sequential indexation with retry
    for i, item in enumerate(all_items):
        while True:
            try:
                await _embed_and_store(item)
                indexed += 1
                retries = 0
                wait_time = 2.0
                await _post_progress(indexed, total)
                break
            except Exception as exc:
                retries += 1
                if retries >= max_retries:
                    log.error("embedding_skip", chunk=i, retries=retries, error=str(exc)[:100])
                    retries = 0
                    wait_time = 2.0
                    break
                log.warning("embedding_retry", chunk=i, wait=wait_time, retry=retries, error=str(exc)[:100])
                await _aio.sleep(wait_time)
                wait_time = min(wait_time * 2, max_wait)

    await _post_progress(indexed, total)
    log.info("rag_indexation_complete", slug=project_slug, indexed=indexed, total=total)
    return indexed, sorted(file_set)


async def _generate_documents_synthesis(
    project_slug: str,
    filenames: list[str],
    total_chunks: int,
    embedding_provider: str = "",
) -> str:
    """Generate a max 30-line synthesis of indexed documents via RAG search."""
    from core.i18n import msg as _msg
    from services import rag_service

    results = await rag_service.search(project_slug, "project description overview objectives features", top_k=10, embedding_provider=embedding_provider)
    if not results:
        return _msg("documents_no_content", file_count=len(filenames), chunk_count=total_chunks)

    synthesis_lines = [
        _msg("documents_indexed", file_count=len(filenames), chunk_count=total_chunks),
        "",
    ]
    for r in results[:8]:
        first_line = r.content.strip().split("\n")[0][:120]
        synthesis_lines.append(f"- [{r.filename}] {first_line}")

    return "\n".join(synthesis_lines[:30])


async def _load_deduced_prompt(
    project_slug: str,
    project_name: str,
    documents: list[str],
) -> Optional[str]:
    """Load the orchestrator prompt deduced at step 3 of the wizard.

    First tries to load the onboarding chat prompt from the project type config.
    Falls back to the legacy phase prompt if no chat is configured.
    Returns the prompt content with project context injected, or None.
    """
    from services import wizard_data_service
    from services.project_type_service import _shared_projects_dir

    step3 = await wizard_data_service.get_step(project_slug, 3)
    if not step3:
        return None

    type_id = step3.get("selectedTypeId", "")
    if not type_id:
        return None

    type_dir = os.path.join(_shared_projects_dir(), type_id)

    # Try onboarding chat prompt from project.json
    selected_chat_id = step3.get("selectedChatId", "")
    pj_path = os.path.join(type_dir, "project.json")
    if os.path.isfile(pj_path):
        try:
            with open(pj_path, encoding="utf-8") as f:
                pj = json.load(f)
            chats = pj.get("chats", [])
            # Use selectedChatId if set, otherwise fall back to first onboarding chat
            onboarding_chat = None
            if selected_chat_id:
                onboarding_chat = next((c for c in chats if c.get("id") == selected_chat_id), None)
            if not onboarding_chat:
                onboarding_chat = next((c for c in chats if c.get("type") == "onboarding"), None)
            if onboarding_chat:
                prompt_file = onboarding_chat.get("prompt", "")
                if prompt_file:
                    prompt_path = os.path.join(type_dir, prompt_file)
                    if os.path.isfile(prompt_path):
                        with open(prompt_path, encoding="utf-8") as f:
                            prompt_content = f.read()
                        doc_list = "\n".join(f"- {d}" for d in documents) if documents else "(aucun document)"
                        return (
                            f"Nouveau projet : {project_name} (slug: {project_slug})\n\n"
                            f"Documents fournis (consultables via RAG) :\n{doc_list}\n\n"
                            f"---\n\n{prompt_content}"
                        )
        except Exception:
            pass

    # Fallback: legacy phase prompt
    prompt_filename = step3.get("orchestratorPrompt", "")
    if not prompt_filename:
        return None

    prompt_path = os.path.join(type_dir, prompt_filename)
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


class OnboardingConfig:
    """Resolved onboarding chat config with prompt contents."""

    def __init__(self):
        self.system_prompt: str = ""
        self.agent_prompts: dict[str, str] = {}
        self.agent_tools: dict[str, list[str]] = {}  # per-agent allowed MCP tools
        self.agents: list[str] = []
        self.error: str = ""


async def _load_onboarding_config(project_slug: str) -> OnboardingConfig:
    """Load orchestrator prompt + per-agent prompts from the onboarding chat config.

    Raises errors in the returned object if required properties are missing,
    so the caller can surface them to the user.
    """
    from services import wizard_data_service
    from services.project_type_service import _shared_projects_dir

    cfg = OnboardingConfig()

    step3 = await wizard_data_service.get_step(project_slug, 3)
    if not step3:
        cfg.error = "Aucune donnee wizard step 3. Relancez le processus de creation."
        return cfg

    type_id = step3.get("selectedTypeId", "")
    if not type_id:
        cfg.error = "Aucun type de projet selectionne (step 3). Revenez au wizard."
        return cfg

    selected_chat_id = step3.get("selectedChatId", "")
    type_dir = os.path.join(_shared_projects_dir(), type_id)
    pj_path = os.path.join(type_dir, "project.json")

    if not os.path.isfile(pj_path):
        cfg.error = f"project.json introuvable pour le type '{type_id}'. Verifiez la configuration."
        return cfg

    try:
        with open(pj_path, encoding="utf-8") as f:
            pj = json.load(f)
    except Exception as exc:
        cfg.error = f"Erreur lecture project.json: {exc}"
        return cfg

    chats = pj.get("chats", [])
    onboarding_chat = None
    if selected_chat_id:
        onboarding_chat = next((c for c in chats if c.get("id") == selected_chat_id), None)
    if not onboarding_chat:
        onboarding_chat = next((c for c in chats if c.get("type") == "onboarding"), None)

    if not onboarding_chat:
        cfg.error = f"Aucun chat onboarding dans le type '{type_id}'. Corrigez la configuration du type de projet."
        return cfg

    # Orchestrator prompt
    prompt_file = onboarding_chat.get("prompt", "")
    if not prompt_file:
        cfg.error = f"Propriete 'prompt' manquante sur le chat '{onboarding_chat.get('id', '?')}'. Corrigez le type de projet."
        return cfg

    prompt_path = os.path.join(type_dir, prompt_file)
    if not os.path.isfile(prompt_path):
        cfg.error = f"Fichier prompt '{prompt_file}' introuvable dans '{type_id}'. Regenerez les prompts du type de projet."
        return cfg

    with open(prompt_path, encoding="utf-8") as f:
        cfg.system_prompt = f.read()

    cfg.agents = onboarding_chat.get("agents", [])

    # Per-agent tools from agent_config
    agent_config = onboarding_chat.get("agent_config", {})
    for agent_id, acfg in agent_config.items():
        if "tools" in acfg:
            cfg.agent_tools[agent_id] = acfg["tools"]

    # Per-agent prompts
    agent_prompts_map = onboarding_chat.get("agent_prompts", {})
    if not agent_prompts_map:
        cfg.error = f"Propriete 'agent_prompts' manquante sur le chat '{onboarding_chat.get('id', '?')}'. Corrigez le type de projet."
        return cfg

    for agent_id, filename in agent_prompts_map.items():
        agent_path = os.path.join(type_dir, filename)
        if os.path.isfile(agent_path):
            with open(agent_path, encoding="utf-8") as f:
                cfg.agent_prompts[agent_id] = f.read()
        else:
            log.warning("onboarding_agent_prompt_missing", agent=agent_id, file=filename)

    return cfg


# ── Public API ───────────────────────────────────────────────────


async def start_analysis(
    project_slug: str,
    team_id: str,
    workflow_id: Optional[int] = None,
) -> dict[str, Any]:
    """Launch the analysis pipeline: returns immediately, runs indexation + gateway in background."""
    import asyncio as _aio

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

    # Load onboarding chat config (orchestrator prompt + agent prompts)
    onboarding = await _load_onboarding_config(project_slug)
    if onboarding.error:
        log.error("onboarding_config_error", slug=project_slug, error=onboarding.error)
        return {"error": onboarding.error}

    # Build instruction from deduced prompt or fallback
    deduced_prompt = await _load_deduced_prompt(project_slug, project_name, documents)
    instruction = deduced_prompt or _build_instruction(project_slug, project_name, team_name, documents)

    # Create onboarding workflow + first phase
    wf_row = await fetch_one(
        """INSERT INTO project.project_workflows
           (project_slug, team_id, workflow_name, workflow_type, workflow_json_path, status, iteration)
           VALUES ($1, $2, 'onboarding', 'onboarding', '', 'active', 1)
           RETURNING id""",
        project_slug, team_id,
    )
    workflow_id = wf_row["id"] if wf_row else None

    phase_row = None
    if workflow_id:
        phase_row = await fetch_one(
            """INSERT INTO project.workflow_phases
               (workflow_id, phase_key, phase_name, group_key, phase_order, group_order, iteration, status)
               VALUES ($1, 'discovery', 'Comprendre le besoin', 'A', 0, 0, 1, 'running')
               RETURNING id""",
            workflow_id,
        )
        if phase_row:
            await execute(
                "UPDATE project.project_workflows SET current_phase_id = $1 WHERE id = $2",
                phase_row["id"], workflow_id,
            )

    phase_id = phase_row["id"] if phase_row else None
    thread_id = "workflow-{}".format(workflow_id) if workflow_id else "onboarding-{}".format(project_slug)

    # Create tracking task row (so indexation progress can post events immediately)
    task_row = await fetch_one(
        """INSERT INTO project.dispatcher_tasks
           (agent_id, team_id, thread_id, project_slug, phase, instruction, status, docker_image, workflow_id, phase_id)
           VALUES ($1, $2, $3, $4, 'discovery', $5, 'running', 'gateway', $6, $7)
           RETURNING id""",
        agent_id, team_id, thread_id, project_slug, instruction[:4000], workflow_id, phase_id,
    )
    task_id = str(task_row["id"]) if task_row else ""

    await execute(
        "UPDATE project.pm_projects SET analysis_task_id = $1, analysis_status = 'in_progress', onboarding_workflow_id = $2 WHERE slug = $3",
        task_id, workflow_id, project_slug,
    )

    # Launch background pipeline: indexation → synthesis → gateway call
    _aio.create_task(_run_analysis_pipeline(
        project_slug=project_slug,
        project_name=project_name,
        team_id=team_id,
        team_name=team_name,
        agent_id=agent_id,
        thread_id=thread_id,
        task_id=task_id,
        workflow_id=workflow_id,
        phase_id=phase_id,
        documents=documents,
        instruction=instruction,
        onboarding=onboarding,
    ))

    # Return immediately — frontend polls for progress
    return {"task_id": task_id, "workflow_id": workflow_id, "agent_id": agent_id, "status": "started"}


async def _run_analysis_pipeline(
    project_slug: str,
    project_name: str,
    team_id: str,
    team_name: str,
    agent_id: str,
    thread_id: str,
    task_id: str,
    workflow_id: int | None,
    phase_id: int | None,
    documents: list[str],
    instruction: str,
    onboarding: OnboardingConfig,
) -> None:
    """Background pipeline: index documents → synthesize → call gateway."""
    try:
        # Resolve embedding provider
        embedding_provider = await _resolve_embedding_provider_async(project_slug)
        log.info("embedding_provider", slug=project_slug, provider=embedding_provider or "(global)")

        # Check if documents are already indexed (skip if so)
        existing_chunks = await fetch_one(
            "SELECT COUNT(*) as cnt FROM project.rag_documents WHERE project_slug = $1",
            project_slug,
        )
        already_indexed = (existing_chunks["cnt"] if existing_chunks else 0) > 0

        if already_indexed:
            total_chunks = existing_chunks["cnt"]
            log.info("documents_already_indexed", slug=project_slug, chunks=total_chunks)
            if task_id:
                await execute(
                    """INSERT INTO project.dispatcher_task_events (task_id, event_type, data)
                       VALUES ($1::uuid, 'progress', $2::jsonb)""",
                    task_id,
                    json.dumps({"data": f"Documents deja indexes ({total_chunks} chunks) — indexation ignoree."}, ensure_ascii=False),
                )
            # Get filenames for synthesis
            file_rows = await fetch_all(
                "SELECT DISTINCT filename FROM project.rag_documents WHERE project_slug = $1",
                project_slug,
            )
            indexed_files = [r["filename"] for r in file_rows]
        else:
            # Index documents into RAG (with progress events)
            total_chunks, indexed_files = await _index_project_documents(
                project_slug, embedding_provider=embedding_provider, task_id=task_id,
            )
            log.info("documents_indexed", slug=project_slug, files=len(indexed_files), chunks=total_chunks)

        # Generate and store synthesis
        if indexed_files:
            synthesis = await _generate_documents_synthesis(project_slug, indexed_files, total_chunks, embedding_provider=embedding_provider)
        else:
            synthesis = "Aucun document a indexer."
        if task_id and synthesis:
            await execute(
                """INSERT INTO project.dispatcher_task_events (task_id, event_type, data)
                   VALUES ($1::uuid, 'progress', $2::jsonb)""",
                task_id,
                json.dumps({"data": synthesis}, ensure_ascii=False),
            )

        # Resolve placeholders in onboarding prompts
        from services import rag_service
        # Search for project overview content, excluding HTML/mockup files
        rag_results = await rag_service.search(project_slug, "project description objectives features architecture requirements specifications", top_k=20, embedding_provider=embedding_provider)
        # Filter out HTML, CSS, and code files — keep docs, specs, README
        _skip_ext = (".html", ".css", ".dart", ".js", ".ts", ".jsx", ".tsx", ".sh", ".yaml", ".yml", ".json", ".toml")
        rag_filtered = [r for r in rag_results if not any(r.filename.endswith(ext) for ext in _skip_ext)]
        if not rag_filtered:
            rag_filtered = rag_results[:10]  # fallback to all if nothing left
        rag_context = "\n\n".join(
            f"[{r.filename}] {r.content[:300]}" for r in rag_filtered[:5]
        ) if rag_filtered else "(aucun document pertinent dans le RAG)"

        doc_list = "\n".join(f"- {d}" for d in documents) if documents else "(aucun document)"
        project_context = (
            f"Nom : {project_name}\n"
            f"Slug : {project_slug}\n"
            f"Documents fournis :\n{doc_list}\n"
            f"Documents indexes : {len(indexed_files)} fichiers, {total_chunks} chunks"
        )

        # Project description for injection into prompts
        project_description = (
            f"Projet : {project_name}\n"
            f"Slug : {project_slug}\n"
            f"Documents fournis :\n{doc_list}\n\n"
            f"Synthese des documents :\n{synthesis}"
        )

        def _resolve_prompt(template: str) -> str:
            """Replace all placeholders in a prompt template."""
            result = template
            result = result.replace("{rag_context}", rag_context)
            result = result.replace("{project}", project_context)
            result = result.replace("{project_name}", project_name)
            result = result.replace("{project_slug}", project_slug)
            result = result.replace("{project_description}", project_description)
            return result

        # Check if the LLM provider has inject_rag enabled
        llm_data = load_json_config("llm_providers.json")
        default_provider_id = llm_data.get("default", "")
        default_provider = llm_data.get("providers", {}).get(default_provider_id, {})
        inject_rag = default_provider.get("inject_rag", False)
        log.info("inject_rag_mode", provider=default_provider_id, inject_rag=inject_rag)

        system_prompt = _resolve_prompt(onboarding.system_prompt)
        resolved_agent_prompts = {}
        for aid, prompt in onboarding.agent_prompts.items():
            resolved = _resolve_prompt(prompt)
            if inject_rag:
                # Inject RAG context directly into the agent prompt
                resolved += (
                    "\n\n--- DOCUMENTS DU PROJET (extraits RAG) ---\n"
                    "Voici les extraits les plus pertinents des documents du projet. "
                    "Utilise ces informations pour produire ton livrable.\n\n"
                    f"{rag_context}\n"
                    "--- FIN DES DOCUMENTS ---\n"
                )
            resolved_agent_prompts[aid] = resolved

        # Call gateway /invoke (full multi-agent orchestration)
        gateway_url = settings.langgraph_api_url or "http://langgraph-api:8000"
        invoke_payload: dict[str, Any] = {
            "messages": [{"role": "user", "content": instruction}],
            "team_id": team_id,
            "thread_id": thread_id,
            "project_slug": project_slug,
            "workflow_id": workflow_id,
            "phase_id": phase_id,
            "system_prompt": system_prompt,
            "agent_prompts": resolved_agent_prompts,
            "agent_tools": onboarding.agent_tools,
            "inject_rag": inject_rag,
            "allowed_agents": onboarding.agents,
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
            return

        # Store output as progress event (questions are created by ask_human tool directly)
        output_text = data.get("output", "")
        agents_dispatched = data.get("agents_dispatched", [])
        has_question = any(
            tc.get("name") in ("ask_human", "human_gate")
            for d in data.get("decisions", [])
            for tc in d.get("tool_calls", [])
        )

        if output_text and not has_question:
            await execute(
                """INSERT INTO project.dispatcher_task_events (task_id, event_type, data)
                   VALUES ($1::uuid, 'progress', $2::jsonb)""",
                task_id,
                json.dumps({"data": output_text, "agents_dispatched": agents_dispatched},
                            ensure_ascii=False),
            )

        if has_question:
            await execute(
                "UPDATE project.dispatcher_tasks SET status = 'waiting_hitl' WHERE id = $1::uuid",
                task_id,
            )

        log.info("analysis_pipeline_complete", slug=project_slug, task_id=task_id,
                 agents_dispatched=agents_dispatched)

    except Exception as exc:
        log.error("analysis_pipeline_error", slug=project_slug, error=str(exc))
        if task_id:
            await execute(
                "UPDATE project.dispatcher_tasks SET status = 'failure', error_message = $1 WHERE id = $2::uuid",
                str(exc)[:500], task_id,
            )


async def _sync_status(project_slug: str, task_id: str) -> str:
    """Sync analysis_status with dispatcher state and pending questions."""
    thread_id = await _resolve_thread_id(project_slug)

    pending = await fetch_one(
        "SELECT id FROM project.hitl_requests WHERE thread_id = $1 AND status = 'pending' LIMIT 1",
        thread_id,
    )
    if pending:
        await execute(
            "UPDATE project.pm_projects SET analysis_status = 'waiting_hitl' WHERE slug = $1",
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
        "SELECT analysis_task_id, analysis_status, onboarding_workflow_id FROM project.pm_projects WHERE slug = $1",
        project_slug,
    )
    if not row or not row.get("analysis_task_id"):
        return {
            "status": "not_started",
            "task_id": None,
            "workflow_id": None,
            "has_pending_question": False,
            "pending_request_id": None,
        }

    task_id = row["analysis_task_id"]
    workflow_id = row.get("onboarding_workflow_id")
    current = row.get("analysis_status") or "not_started"

    if current not in ("completed", "failed", "not_started"):
        current = await _sync_status(project_slug, task_id)

    # Use workflow-based thread_id if available, fallback to legacy
    if workflow_id:
        thread_id = "workflow-{}".format(workflow_id)
    else:
        thread_id = "{}{}".format(ONBOARDING_THREAD_PREFIX, project_slug)
    pending = await fetch_one(
        "SELECT id, request_type FROM project.hitl_requests WHERE thread_id = $1 AND status = 'pending' LIMIT 1",
        thread_id,
    )

    return {
        "status": current,
        "task_id": task_id,
        "workflow_id": workflow_id,
        "has_pending_question": pending is not None,
        "pending_request_id": str(pending["id"]) if pending else None,
        "pending_request_type": pending["request_type"] if pending else None,
    }


async def get_conversation(project_slug: str) -> list[AnalysisMessage]:
    """Merge dispatcher events + HITL requests + rag_conversations."""
    # Use workflow-based thread_id if available
    proj_row = await fetch_one(
        "SELECT team_id, onboarding_workflow_id FROM project.pm_projects WHERE slug = $1", project_slug,
    )
    workflow_id = proj_row.get("onboarding_workflow_id") if proj_row else None
    if workflow_id:
        thread_id = "workflow-{}".format(workflow_id)
    else:
        thread_id = "{}{}".format(ONBOARDING_THREAD_PREFIX, project_slug)
    messages: list[AnalysisMessage] = []

    # Resolve orchestrator ID from team config
    proj_team = proj_row
    default_agent_id = ""
    if proj_team:
        teams_data = load_teams()
        for t in teams_data:
            if t.get("id") == proj_team["team_id"]:
                default_agent_id = t.get("orchestrator", "")
                break

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
        content = data.get("data", data.get("content", ""))
        if isinstance(content, dict):
            content = json.dumps(content, ensure_ascii=False) if content else ""
        content = str(content).strip() if content else ""
        if not content:
            continue  # skip empty events

        msg_type = etype if etype in ("progress", "artifact", "result") else "progress"
        evt_agent_id = data.get("agent_id", "") or default_agent_id

        messages.append(AnalysisMessage(
            id=f"evt-{r['id']}",
            sender="agent",
            type=msg_type,
            content=content,
            agent_id=evt_agent_id or None,
            artifact_key=data.get("key") if etype == "artifact" else evt_agent_id or None,
            created_at=r["created_at"].isoformat(),
        ))

    # 2. HITL requests (questions + answers)
    hitl_rows = await fetch_all(
        """
        SELECT id, agent_id, prompt, response, status, request_type, created_at, answered_at
        FROM project.hitl_requests
        WHERE thread_id = $1
        ORDER BY created_at ASC
        """,
        thread_id,
    )
    for r in hitl_rows:
        # Skip approval requests — they are not chat messages
        if r.get("request_type") == "approval":
            continue
        messages.append(AnalysisMessage(
            id=f"q-{r['id']}",
            sender="agent",
            type="question",
            content=r["prompt"],
            agent_id=r.get("agent_id"),
            request_id=str(r["id"]),
            status=r["status"],
            created_at=r["created_at"].isoformat(),
        ))
        if r["status"] == "answered" and r["response"]:
            ts = r["answered_at"] or r["created_at"]
            prompt_summary = (r["prompt"] or "")[:200].replace("(((?", "").replace(")))", "").strip()
            messages.append(AnalysisMessage(
                id=f"a-{r['id']}",
                sender="user",
                type="reply",
                content=r["response"],
                request_id=str(r["id"]),
                in_reply_to=prompt_summary,
                created_at=ts.isoformat(),
            ))

    # 3. Agent outputs from gateway state
    try:
        gateway_url = settings.langgraph_api_url or "http://langgraph-api:8000"
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(f"{gateway_url}/workflow/status/{thread_id}")
            if resp.status_code == 200:
                state_data = resp.json()
                agent_outputs = state_data.get("agent_outputs", {})
                for agent_id, output in agent_outputs.items():
                    if isinstance(output, dict):
                        # Format deliverable output
                        content_parts = []
                        for k, v in output.items():
                            if k in ("status", "confidence", "agent_id"):
                                continue
                            text = v if isinstance(v, str) else json.dumps(v, ensure_ascii=False)
                            if text:
                                content_parts.append(f"**{k}**\n{text[:3000]}")
                        content = "\n\n".join(content_parts)
                    elif isinstance(output, str):
                        content = output
                    else:
                        content = str(output)
                    if content.strip():
                        messages.append(AnalysisMessage(
                            id=f"agent-{agent_id}",
                            sender="agent",
                            type="artifact",
                            content=f"📄 **{agent_id}**\n\n{content}",
                            artifact_key=agent_id,
                            created_at=messages[-1].created_at if messages else "",
                        ))
    except Exception:
        pass  # gateway unavailable, skip agent outputs

    # 4. User free messages from rag_conversations
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

    # Resolve agent avatars
    agent_ids_used = {m.agent_id for m in messages if m.agent_id}
    if agent_ids_used:
        try:
            from services.avatar_resolver import resolve_agent_avatar
            proj_row = await fetch_one(
                "SELECT team_id FROM project.pm_projects WHERE slug = $1", project_slug,
            )
            team_id = proj_row["team_id"] if proj_row else ""
            if team_id:
                for m in messages:
                    if m.agent_id:
                        avatar = resolve_agent_avatar(team_id, m.agent_id)
                        m.agent_avatar = avatar
                        log.info("avatar_resolved", agent_id=m.agent_id, avatar=avatar)
        except Exception as exc:
            log.error("avatar_resolution_error", error=str(exc))

    messages.sort(key=lambda m: m.created_at)
    return messages


async def reply_to_question(
    project_slug: str,
    request_id: str,
    response: str,
    reviewer: str,
) -> dict[str, Any]:
    """Reply to an agent HITL question."""
    thread_id = await _resolve_thread_id(project_slug)

    row = await fetch_one(
        "SELECT id, thread_id, status, context FROM project.hitl_requests WHERE id = $1::uuid",
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

    # Auto-index conversation exchange into RAG
    try:
        prompt_text = row.get("prompt", "") if row else ""
        exchange = "Q: {}\nR: {}".format(prompt_text[:1000], response[:2000])
        embedding_provider = await _resolve_embedding_provider_async(project_slug)
        from services import rag_service
        await rag_service.index_document(
            project_slug, "conversation/exchange-{}".format(request_id[:8]),
            exchange, content_type="conversation", embedding_provider=embedding_provider,
        )
        log.info("conversation_indexed", slug=project_slug, request_id=request_id[:8])
    except Exception as exc:
        log.warning("conversation_index_failed", slug=project_slug, error=str(exc)[:200])

    # Check if this is the onboarding final validation
    ctx = row.get("context") or {}
    if isinstance(ctx, str):
        try:
            ctx = json.loads(ctx)
        except (json.JSONDecodeError, ValueError):
            ctx = {}
    is_final = ctx.get("onboarding_final", False)
    response_lower = response.strip().lower()
    user_says_yes = response_lower.startswith("oui") or response_lower.startswith("1. oui") or "recapitulatif" in response_lower

    if is_final and user_says_yes:
        await execute(
            "UPDATE project.pm_projects SET analysis_status = 'completed' WHERE slug = $1",
            project_slug,
        )
        # Store completion event for frontend
        proj_row = await fetch_one(
            "SELECT analysis_task_id FROM project.pm_projects WHERE slug = $1", project_slug,
        )
        if proj_row and proj_row.get("analysis_task_id"):
            await execute(
                """INSERT INTO project.dispatcher_task_events (task_id, event_type, data)
                   VALUES ($1::uuid, 'result', $2::jsonb)""",
                proj_row["analysis_task_id"],
                json.dumps({"data": "ONBOARDING_COMPLETE"}),
            )
        log.info("onboarding_completed", slug=project_slug)
        return {"ok": True, "status": "completed"}

    await execute(
        "UPDATE project.pm_projects SET analysis_status = 'in_progress' WHERE slug = $1",
        project_slug,
    )

    # Relaunch the pipeline with the user's response
    try:
        result = await send_free_message(project_slug, response, reviewer, skip_store=True)
        log.info("onboarding_relaunched_from_reply", slug=project_slug)
        return result
    except Exception as exc:
        log.error("onboarding_relaunch_from_reply_failed", slug=project_slug, error=str(exc))
        return {"ok": True}


async def _call_llm_simple(system_prompt: str, user_message: str, max_tokens: int = 4096) -> str:
    """Call the default LLM provider directly (no gateway, no tools, no orchestrator)."""
    llm_data = load_json_config("llm_providers.json")
    provider_id = llm_data.get("default", "")
    provider = llm_data.get("providers", {}).get(provider_id, {})
    if not provider:
        log.error("no_llm_provider_configured")
        return ""

    ptype = provider["type"]
    model = provider["model"]
    env_key = provider.get("env_key", "")
    base_url = provider.get("base_url", "")
    api_key = provider.get("api_key", "")
    if not api_key and env_key:
        api_key = os.environ.get(env_key, "")

    import asyncio as _aio
    max_retries = 4
    wait = 5.0
    for attempt in range(max_retries):
        try:
            async with httpx.AsyncClient(timeout=90) as client:
                if ptype == "anthropic":
                    url = "{}/v1/messages".format(base_url or "https://api.anthropic.com")
                    resp = await client.post(url, headers={
                        "x-api-key": api_key,
                        "anthropic-version": "2023-06-01",
                        "content-type": "application/json",
                    }, json={
                        "model": model, "max_tokens": max_tokens,
                        "system": system_prompt,
                        "messages": [{"role": "user", "content": user_message}],
                    })
                elif ptype in ("openai", "deepseek", "groq", "moonshot"):
                    url = "{}/v1/chat/completions".format(base_url or "https://api.openai.com")
                    resp = await client.post(url, headers={
                        "Authorization": "Bearer {}".format(api_key),
                        "Content-Type": "application/json",
                    }, json={
                        "model": model, "max_tokens": max_tokens,
                        "messages": [
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_message},
                        ],
                    })
                elif ptype == "ollama":
                    url = "{}/api/chat".format(base_url or "http://host.docker.internal:11434")
                    resp = await client.post(url, json={
                        "model": model, "stream": False,
                        "messages": [
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_message},
                        ],
                    })
                else:
                    log.warning("unsupported_llm_type", type=ptype)
                    return ""

                if resp.status_code == 429:
                    log.warning("_call_llm_rate_limited", attempt=attempt + 1, wait=wait)
                    await _aio.sleep(wait)
                    wait = min(wait * 2, 60)
                    continue
                resp.raise_for_status()

                if ptype == "anthropic":
                    return "".join(b.get("text", "") for b in resp.json().get("content", []))
                elif ptype == "ollama":
                    return resp.json().get("message", {}).get("content", "")
                else:
                    return resp.json().get("choices", [{}])[0].get("message", {}).get("content", "")
        except Exception as exc:
            if "429" in str(exc) and attempt < max_retries - 1:
                log.warning("_call_llm_rate_limited", attempt=attempt + 1, wait=wait)
                await _aio.sleep(wait)
                wait = min(wait * 2, 60)
                continue
            log.error("_call_llm_simple_failed", type=ptype, error=str(exc)[:200])
            return ""
    return ""


def _load_prompt_template(name: str) -> str:
    """Load a prompt template from Prompts/{culture}/."""
    culture = os.getenv("CULTURE", "fr-fr")
    for base in ["/app/config", "/app/Shared", "config", "Shared"]:
        path = os.path.join(base, "Prompts", culture, name)
        if os.path.isfile(path):
            with open(path, encoding="utf-8") as f:
                return f.read()
    return ""


def _load_recap_template() -> str:
    return _load_prompt_template("onboarding-recap.md")


def _load_agent_card(agent_id: str) -> str:
    """Load agent profile (identity + roles/missions/skills) from Shared/Agents/."""
    for base in ["/app/Shared/Agents", "Shared/Agents"]:
        agent_dir = os.path.join(base, agent_id)
        if not os.path.isdir(agent_dir):
            continue
        parts = []
        for f in sorted(os.listdir(agent_dir)):
            fpath = os.path.join(agent_dir, f)
            if os.path.isfile(fpath) and (f.endswith(".md") or f.endswith(".md_")) and f != "prompt.md":
                with open(fpath, encoding="utf-8") as fh:
                    content = fh.read().strip()
                if content and len(content) > 20:
                    parts.append("--- {} ---\n{}".format(f, content))
        return "\n\n".join(parts) if parts else "(aucun profil)"
    return "(agent introuvable)"


async def _invoke_mcp_tool_async(tool, args: dict) -> Any:
    """Invoke an MCP tool that may be async-only."""
    import asyncio as _aio
    try:
        return tool.invoke(args)
    except NotImplementedError:
        try:
            loop = _aio.get_event_loop()
            if loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    return pool.submit(_aio.run, tool.ainvoke(args)).result()
            else:
                return _aio.run(tool.ainvoke(args))
        except RuntimeError:
            return _aio.run(tool.ainvoke(args))


async def get_project_summary(project_slug: str) -> dict[str, Any]:
    """Generate a project summary using LLM + MCP Memory + RAG + conversation."""

    # 1. Get facts from MCP Memory (via gateway API, not direct import)
    facts: list[dict[str, Any]] = []
    memory_text = "(aucun fait enregistre)"
    try:
        # MCP Memory runs in the API container, not HITL — skip direct import
        # Facts are available via RAG index (indexed during onboarding)
        pass
    except Exception as exc:
        log.warning("summary_memory_error", slug=project_slug, error=str(exc))

    # 2. Get RAG documents + conversation facts
    rag_text = "(aucun document)"
    conversation_facts_text = "(aucun echange indexe)"
    try:
        embedding_provider = await _resolve_embedding_provider_async(project_slug)
        from services import rag_service
        results = await rag_service.search(
            project_slug, "project summary objectives features users constraints architecture",
            top_k=20, embedding_provider=embedding_provider,
        )
        if results:
            doc_lines = []
            conv_lines_rag = []
            for r in results[:15]:
                if r.filename.startswith("conversation/"):
                    conv_lines_rag.append(r.content[:500])
                else:
                    doc_lines.append("[{}]\n{}".format(r.filename, r.content[:400]))
            if doc_lines:
                rag_text = "\n\n---\n\n".join(doc_lines[:10])
            if conv_lines_rag:
                conversation_facts_text = "\n\n---\n\n".join(conv_lines_rag[:10])
    except Exception as exc:
        log.warning("summary_rag_error", slug=project_slug, error=str(exc))

    # 3. Get conversation history
    conversation = await get_conversation(project_slug)
    conv_lines = []
    for m in conversation[-30:]:
        prefix = "Agent" if m.sender == "agent" else "Utilisateur"
        conv_lines.append("[{}] {}".format(prefix, m.content[:300]))
    conversation_text = "\n".join(conv_lines) if conv_lines else "(aucune conversation)"

    # 4. Load recap template and inject variables
    template = _load_recap_template()
    if not template:
        return {"project_name": project_slug, "summary": "", "facts": facts, "rag_summary": rag_text}

    prompt = template.replace(
        "{memory_facts}", memory_text
    ).replace(
        "{conversation_facts}", conversation_facts_text
    ).replace(
        "{rag_documents}", rag_text
    ).replace(
        "{conversation_history}", conversation_text
    )

    # 5. Call LLM directly with recap prompt to generate the summary
    summary = ""
    if prompt:
        summary = await _call_llm_simple(prompt, "Produis le recapitulatif complet du projet.")
        if summary:
            log.info("summary_generated", slug=project_slug, length=len(summary))

    # Read deliverable files from project directory
    ag_flow_root = os.getenv("AG_FLOW_ROOT", settings.ag_flow_root)
    proj_team = await fetch_one(
        "SELECT team_id FROM project.pm_projects WHERE slug = $1", project_slug,
    )
    team_for_file = proj_team["team_id"] if proj_team else ""
    deliverables: list[dict[str, str]] = []
    project_dir = os.path.join(ag_flow_root, "projects", project_slug, team_for_file) if team_for_file else ""
    if project_dir and os.path.isdir(project_dir):
        for root, _dirs, files in os.walk(project_dir):
            for fname in sorted(files):
                if fname.endswith(".md"):
                    fpath = os.path.join(root, fname)
                    try:
                        with open(fpath, encoding="utf-8") as f:
                            content = f.read()
                        rel = os.path.relpath(fpath, project_dir)
                        deliverables.append({"name": fname, "path": rel, "content": content})
                    except Exception:
                        pass

    # Use recap deliverable as summary if LLM didn't produce one
    if not summary and deliverables:
        _recap_keywords = ("recap", "cadrage", "summary", "synthese")
        for d in deliverables:
            if any(kw in d["name"].lower() for kw in _recap_keywords):
                summary = d["content"]
                log.info("summary_loaded_from_file", path=d["path"])
                break

    # Final fallback: raw data
    if not summary:
        summary = "# Recapitulatif {}\n\n## Faits valides\n{}\n\n## Documents\n{}".format(
            project_slug, memory_text, rag_text,
        )

    # 7. Generate per-agent syntheses
    agent_syntheses: list[dict[str, str]] = []
    synthesis_template = _load_prompt_template("agent-synthesis.md")
    if synthesis_template and deliverables:
        # Group deliverables by agent
        agent_fragments: dict[str, list[str]] = {}
        for d in deliverables:
            parts = d["path"].split("/") if "/" in d["path"] else d["path"].split("\\")
            agent = parts[-2] if len(parts) >= 2 else "unknown"
            agent_fragments.setdefault(agent, []).append(
                "--- {} ---\n{}".format(d["name"], d["content"][:2000])
            )

        # Check for existing syntheses on disk
        existing_syntheses = {}
        if project_dir:
            for d in deliverables:
                if d["name"].endswith("_synthesis.md"):
                    agent_name = d["name"].replace("_synthesis.md", "")
                    existing_syntheses[agent_name] = d["content"]

        async def _generate_one_synthesis(agent_id: str, fragments: list[str]) -> dict[str, str] | None:
            # Use cached synthesis if available
            if agent_id in existing_syntheses:
                return {"agent": agent_id, "content": existing_syntheses[agent_id]}
            agent_card = _load_agent_card(agent_id)
            fragments_text = "\n\n".join(fragments[:20])
            prompt = synthesis_template.replace(
                "{agent_name}", agent_id
            ).replace(
                "{agent_card}", agent_card
            ).replace(
                "{conversation}", conversation_text[:5000]
            ).replace(
                "{fragments}", fragments_text[:8000]
            )
            content = await _call_llm_simple(prompt, "Produis la synthese structuree du projet dans ton domaine d'expertise.")
            if content and len(content) > 100:
                # Save to disk for cache
                if project_dir:
                    synth_dir = os.path.join(project_dir, "syntheses")
                    os.makedirs(synth_dir, exist_ok=True)
                    synth_path = os.path.join(synth_dir, "{}_synthesis.md".format(agent_id))
                    with open(synth_path, "w", encoding="utf-8") as f:
                        f.write(content)
                log.info("agent_synthesis_generated", agent=agent_id, length=len(content))
                return {"agent": agent_id, "content": content}
            log.warning("agent_synthesis_empty", agent=agent_id)
            return None

        # Generate sequentially to avoid rate limiting
        for aid, frags in agent_fragments.items():
            r = await _generate_one_synthesis(aid, frags)
            if r:
                agent_syntheses.append(r)

    proj_row = await fetch_one(
        "SELECT name FROM project.pm_projects WHERE slug = $1", project_slug,
    )
    project_name = proj_row["name"] if proj_row else project_slug

    return {
        "project_name": project_name,
        "summary": summary,
        "facts": facts,
        "rag_summary": rag_text,
        "deliverables": [{"name": d["name"], "path": d["path"], "content": d["content"]} for d in deliverables],
        "agent_syntheses": agent_syntheses,
    }


async def send_free_message(
    project_slug: str,
    content: str,
    user_email: str,
    skip_store: bool = False,
) -> dict[str, Any]:
    """Send a free message — cancel current task and relaunch agent."""
    if not skip_store:
        await execute(
            "INSERT INTO project.rag_conversations (project_slug, sender, content) VALUES ($1, $2, $3)",
            project_slug, "user", content,
        )
        # Auto-index user message into RAG
        try:
            embedding_provider = await _resolve_embedding_provider_async(project_slug)
            from services import rag_service
            import hashlib as _hl
            msg_hash = _hl.md5(content[:200].encode()).hexdigest()[:8]
            await rag_service.index_document(
                project_slug, "conversation/user-msg-{}".format(msg_hash),
                content, content_type="conversation", embedding_provider=embedding_provider,
            )
        except Exception as exc:
            log.warning("user_msg_index_failed", slug=project_slug, error=str(exc)[:200])

    proj = await fetch_one(
        "SELECT team_id, analysis_task_id, onboarding_workflow_id FROM project.pm_projects WHERE slug = $1",
        project_slug,
    )
    if not proj:
        raise ValueError("Project not found")

    team_id = proj["team_id"]
    old_task_id = proj["analysis_task_id"]
    workflow_id = proj.get("onboarding_workflow_id")

    # Build thread_id from workflow_id if available, fallback to legacy
    if workflow_id:
        thread_id = "workflow-{}".format(workflow_id)
    else:
        thread_id = "{}{}".format(ONBOARDING_THREAD_PREFIX, project_slug)

    # Don't relaunch if the final validation question is pending
    has_final = await fetch_one(
        "SELECT id FROM project.hitl_requests WHERE thread_id = $1 AND status = 'pending' AND context::text LIKE '%%onboarding_final%%' LIMIT 1",
        thread_id,
    )
    if has_final:
        log.info("skip_relaunch_final_pending", slug=project_slug)
        return {"ok": True, "status": "final_pending"}

    # Read phase_id from current workflow
    phase_id = None
    if workflow_id:
        wf_row = await fetch_one(
            "SELECT current_phase_id FROM project.project_workflows WHERE id = $1",
            workflow_id,
        )
        phase_id = wf_row["current_phase_id"] if wf_row else None

    # Load onboarding config (system prompt + agent prompts)
    onboarding = await _load_onboarding_config(project_slug)

    # Resolve placeholders in prompts
    embedding_provider = await _resolve_embedding_provider_async(project_slug)
    from services import rag_service
    rag_results = await rag_service.search(project_slug, "project description objectives features architecture requirements", top_k=20, embedding_provider=embedding_provider)
    _skip_ext = (".html", ".css", ".dart", ".js", ".ts", ".jsx", ".tsx", ".sh", ".yaml", ".yml", ".json", ".toml")
    rag_filtered = [r for r in rag_results if not any(r.filename.endswith(ext) for ext in _skip_ext)]
    if not rag_filtered:
        rag_filtered = rag_results[:10]
    rag_context = "\n\n".join(
        f"[{r.filename}] {r.content[:300]}" for r in rag_filtered[:5]
    ) if rag_filtered else "(aucun document pertinent)"

    proj_row = await fetch_one("SELECT name FROM project.pm_projects WHERE slug = $1", project_slug)
    project_name = proj_row["name"] if proj_row else project_slug

    def _resolve(template):
        return template.replace("{rag_context}", rag_context).replace("{project}", project_name).replace("{project_name}", project_name).replace("{project_slug}", project_slug).replace("{project_description}", f"Projet: {project_name}")

    system_prompt = _resolve(onboarding.system_prompt) if not onboarding.error else ""
    resolved_agent_prompts = {aid: _resolve(p) for aid, p in onboarding.agent_prompts.items()}

    # Check inject_rag mode
    llm_data = load_json_config("llm_providers.json")
    default_provider_id = llm_data.get("default", "")
    default_provider = llm_data.get("providers", {}).get(default_provider_id, {})
    inject_rag = default_provider.get("inject_rag", False)

    if inject_rag:
        for aid in resolved_agent_prompts:
            resolved_agent_prompts[aid] += (
                "\n\n--- DOCUMENTS DU PROJET (extraits RAG) ---\n" + rag_context + "\n--- FIN ---\n"
            )

    # Send the user's response as a simple message on the existing thread
    # LangGraph keeps the full conversation context via checkpoints
    gateway_url = settings.langgraph_api_url or "http://langgraph-api:8000"
    invoke_payload: dict[str, Any] = {
        "messages": [{"role": "user", "content": content}],
        "team_id": team_id,
        "thread_id": thread_id,
        "project_slug": project_slug,
        "workflow_id": workflow_id,
        "phase_id": phase_id,
        "system_prompt": system_prompt,
        "agent_prompts": resolved_agent_prompts,
        "agent_tools": onboarding.agent_tools,
        "inject_rag": inject_rag,
        "allowed_agents": onboarding.agents,
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

    # Store progress event only if no question was asked (questions go via hitl_requests)
    has_question = any(
        tc.get("name") in ("ask_human", "human_gate")
        for d in data.get("decisions", [])
        for tc in d.get("tool_calls", [])
    )
    output_text = data.get("output", "")
    if old_task_id and output_text and not has_question:
        await execute(
            """INSERT INTO project.dispatcher_task_events (task_id, event_type, data)
               VALUES ($1::uuid, 'progress', $2::jsonb)""",
            old_task_id,
            json.dumps({"data": output_text}, ensure_ascii=False),
        )
    if has_question and old_task_id:
        await execute(
            "UPDATE project.dispatcher_tasks SET status = 'waiting_hitl' WHERE id = $1::uuid",
            old_task_id,
        )

    await execute(
        "UPDATE project.pm_projects SET analysis_status = 'in_progress' WHERE slug = $1",
        project_slug,
    )

    return {"task_id": old_task_id or "", "status": "started"}

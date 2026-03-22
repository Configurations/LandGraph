"""Tests for services/project_type_service.py — project templates."""

from __future__ import annotations

import json
import os
from unittest.mock import AsyncMock, patch

import pytest


SAMPLE_PROJECT_JSON = {
    "name": "SaaS Starter",
    "description": "Standard SaaS project template",
    "team": "team1",
    "workflows": [
        {
            "name": "Discovery",
            "filename": "discovery.wrk.json",
            "type": "discovery",
            "mode": "sequential",
            "priority": 90,
        },
        {
            "name": "Design",
            "filename": "design.wrk.json",
            "type": "design",
            "mode": "sequential",
            "priority": 80,
            "depends_on": "Discovery",
        },
    ],
}


# ── list_project_types ───────────────────────────────────────


@pytest.mark.asyncio
@patch("services.project_type_service._shared_projects_dir")
@patch("os.path.isdir", return_value=True)
@patch("os.listdir", return_value=["saas-starter", "mobile-app"])
@patch("services.project_type_service._read_project_json")
async def test_list_project_types_reads_from_shared(
    mock_read, mock_listdir, mock_isdir, mock_dir,
):
    """list_project_types reads all directories from Shared/Projects/."""
    mock_dir.return_value = "/app/Shared/Projects"
    # sorted listdir: mobile-app, saas-starter → side_effect in that order
    mock_read.side_effect = [None, SAMPLE_PROJECT_JSON]

    from services.project_type_service import list_project_types

    result = await list_project_types()

    assert len(result) == 1
    assert result[0].id == "saas-starter"
    assert result[0].name == "SaaS Starter"
    assert len(result[0].workflows) == 2


# ── get_project_type ─────────────────────────────────────────


@pytest.mark.asyncio
@patch("services.project_type_service._list_workflow_files", return_value=[])
@patch("services.project_type_service._read_project_json")
@patch("services.project_type_service._shared_projects_dir")
async def test_get_project_type_returns_type_with_workflows(
    mock_dir, mock_read, mock_files,
):
    """get_project_type returns a type with its workflow templates."""
    mock_dir.return_value = "/app/Shared/Projects"
    mock_read.return_value = SAMPLE_PROJECT_JSON

    from services.project_type_service import get_project_type

    result = await get_project_type("saas-starter")

    assert result is not None
    assert result.id == "saas-starter"
    assert result.name == "SaaS Starter"
    assert len(result.workflows) == 2
    assert result.workflows[0].name == "Discovery"
    assert result.workflows[1].depends_on == "Discovery"


@pytest.mark.asyncio
@patch("services.project_type_service._read_project_json", return_value=None)
@patch("services.project_type_service._shared_projects_dir")
async def test_get_project_type_returns_none_when_missing(mock_dir, mock_read):
    """get_project_type returns None when project.json does not exist."""
    mock_dir.return_value = "/app/Shared/Projects"

    from services.project_type_service import get_project_type

    result = await get_project_type("nonexistent")
    assert result is None


# ── apply_project_type ───────────────────────────────────────


@pytest.mark.asyncio
@patch("services.project_type_service.create_workflow", new_callable=AsyncMock)
@patch("services.project_type_service.get_project_type", new_callable=AsyncMock)
async def test_apply_project_type_creates_n_workflows(mock_get, mock_create):
    """apply_project_type creates one workflow per template entry."""
    from schemas.project_type import ProjectTypeResponse, WorkflowTemplate
    from schemas.workflow import ProjectWorkflowResponse

    mock_get.return_value = ProjectTypeResponse(
        id="saas-starter",
        name="SaaS Starter",
        description="",
        team="team1",
        workflows=[
            WorkflowTemplate(name="Discovery", filename="discovery.wrk.json", priority=90),
            WorkflowTemplate(name="Design", filename="design.wrk.json", priority=80, depends_on="Discovery"),
        ],
    )
    mock_create.side_effect = [
        ProjectWorkflowResponse(id=1, project_slug="tracker", workflow_name="Discovery", workflow_type="custom", workflow_json_path="/a", status="pending", mode="sequential", priority=90, iteration=1),
        ProjectWorkflowResponse(id=2, project_slug="tracker", workflow_name="Design", workflow_type="custom", workflow_json_path="/b", status="pending", mode="sequential", priority=80, iteration=1, depends_on_workflow_id=1),
    ]

    from services.project_type_service import apply_project_type

    ids = await apply_project_type("tracker", "saas-starter")

    assert ids == [1, 2]
    assert mock_create.call_count == 2

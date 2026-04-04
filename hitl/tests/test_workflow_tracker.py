"""Tests for workflow_tracker — workflow phases tracking."""

from __future__ import annotations

import json
import os
import sys
from unittest.mock import AsyncMock, patch, MagicMock

import pytest

# ── Setup: inject mock core.database into sys.modules before importing workflow_tracker ──
# workflow_tracker uses lazy imports: `from core.database import fetch_one`
# We need core.database to exist as a module with mockable attributes.
_mock_core = MagicMock()
_mock_core.database = MagicMock()
_mock_core.database.fetch_one = AsyncMock()
_mock_core.database.execute = AsyncMock()
sys.modules.setdefault("core", _mock_core)
sys.modules.setdefault("core.database", _mock_core.database)

# Now add the Agents/Shared path and import
# In Docker: /app/agents/shared/  |  Locally: ../../Agents/Shared/
for _candidate in [
    "/app/agents/shared",
    os.path.join(os.path.dirname(__file__), "..", "..", "Agents", "Shared"),
    os.path.join(os.path.dirname(__file__), "..", "..", "agents", "shared"),
]:
    if os.path.isdir(_candidate):
        sys.path.insert(0, _candidate)
        break
from workflow_tracker import (
    file_find_phase_def,
    file_find_phase_by_key,
    file_find_first_group,
    file_find_next_group,
    file_has_human_gate,
    build_deliverable_path,
    db_get_workflow,
    db_get_phase,
    db_check_human_gate,
    db_create_phase,
    db_create_next_group,
    db_create_workflow,
    resolve_next_phase,
    resolve_create_external_workflow,
    db_get_current_position,
    MAX_EXTERNAL_DEPTH,
    MAX_POSITION_DEPTH,
)

# Import conftest from the hitl/tests directory explicitly
import importlib.util
_conftest_path = os.path.join(os.path.dirname(__file__), "conftest.py")
_conftest_spec = importlib.util.spec_from_file_location("hitl_conftest", _conftest_path)
_conftest_mod = importlib.util.module_from_spec(_conftest_spec)
_conftest_spec.loader.exec_module(_conftest_mod)
FakeRecord = _conftest_mod.FakeRecord
make_record = _conftest_mod.make_record


# ══════════════════════════════════════════════
# Helpers — sample Workflow.json content
# ══════════════════════════════════════════════

SIMPLE_WORKFLOW = {
    "phases": {
        "discovery": {
            "name": "Discovery",
            "order": 0,
            "groups": [
                {"id": "A", "order": 0},
                {"id": "B", "order": 1},
            ],
        },
        "design": {
            "name": "Design",
            "order": 1,
            "groups": [
                {"id": "A", "order": 0},
            ],
            "exit_conditions": {"human_gate": True},
        },
        "build": {
            "name": "Build",
            "order": 2,
            "groups": [
                {"id": "A", "order": 0},
                {"id": "B", "order": 1},
                {"id": "C", "order": 2},
            ],
        },
    },
}

EXTERNAL_WORKFLOW = {
    "phases": {
        "sub_phase": {
            "name": "Sub Phase",
            "order": 0,
            "type": "external",
            "external_workflow": "nested.wrk.json",
            "groups": [{"id": "A", "order": 0}],
        },
    },
}

EMPTY_WORKFLOW = {"phases": {}}


def _write_workflow(tmp_path, name, content):
    """Write a Workflow.json file and return its path."""
    p = tmp_path / name
    p.write_text(json.dumps(content), encoding="utf-8")
    return str(p)


# ══════════════════════════════════════════════
# FILE — file_find_phase_def
# ══════════════════════════════════════════════


class TestFileFindPhaseDef:
    def test_find_phase_by_order_zero(self, tmp_path):
        path = _write_workflow(tmp_path, "wf.json", SIMPLE_WORKFLOW)
        result = file_find_phase_def(path, 0)
        assert result is not None
        key, pdef = result
        assert key == "discovery"
        assert pdef["name"] == "Discovery"

    def test_find_phase_by_order_one(self, tmp_path):
        path = _write_workflow(tmp_path, "wf.json", SIMPLE_WORKFLOW)
        result = file_find_phase_def(path, 1)
        assert result is not None
        key, _ = result
        assert key == "design"

    def test_find_phase_by_order_two(self, tmp_path):
        path = _write_workflow(tmp_path, "wf.json", SIMPLE_WORKFLOW)
        result = file_find_phase_def(path, 2)
        assert result is not None
        key, _ = result
        assert key == "build"

    def test_find_phase_nonexistent_order(self, tmp_path):
        path = _write_workflow(tmp_path, "wf.json", SIMPLE_WORKFLOW)
        result = file_find_phase_def(path, 99)
        assert result is None

    def test_find_phase_empty_path(self):
        result = file_find_phase_def("", 0)
        assert result is None

    def test_find_phase_none_path(self):
        result = file_find_phase_def(None, 0)
        assert result is None

    def test_find_phase_missing_file(self, tmp_path):
        result = file_find_phase_def(str(tmp_path / "nope.json"), 0)
        assert result is None

    def test_find_phase_empty_workflow(self, tmp_path):
        path = _write_workflow(tmp_path, "wf.json", EMPTY_WORKFLOW)
        result = file_find_phase_def(path, 0)
        assert result is None


# ══════════════════════════════════════════════
# FILE — file_find_phase_by_key
# ══════════════════════════════════════════════


class TestFileFindPhaseByKey:
    def test_find_existing_key(self, tmp_path):
        path = _write_workflow(tmp_path, "wf.json", SIMPLE_WORKFLOW)
        pdef = file_find_phase_by_key(path, "design")
        assert pdef is not None
        assert pdef["name"] == "Design"

    def test_find_missing_key(self, tmp_path):
        path = _write_workflow(tmp_path, "wf.json", SIMPLE_WORKFLOW)
        assert file_find_phase_by_key(path, "nonexistent") is None

    def test_find_key_empty_path(self):
        assert file_find_phase_by_key("", "discovery") is None

    def test_find_key_none_path(self):
        assert file_find_phase_by_key(None, "discovery") is None


# ══════════════════════════════════════════════
# FILE — file_find_first_group
# ══════════════════════════════════════════════


class TestFileFindFirstGroup:
    def test_first_group_multiple(self):
        phase_def = SIMPLE_WORKFLOW["phases"]["build"]
        key, order = file_find_first_group(phase_def)
        assert key == "A"
        assert order == 0

    def test_first_group_single(self):
        phase_def = SIMPLE_WORKFLOW["phases"]["design"]
        key, order = file_find_first_group(phase_def)
        assert key == "A"
        assert order == 0

    def test_first_group_empty_groups(self):
        key, order = file_find_first_group({"groups": []})
        assert key == "A"
        assert order == 0

    def test_first_group_no_groups_key(self):
        key, order = file_find_first_group({})
        assert key == "A"
        assert order == 0

    def test_first_group_unsorted_input(self):
        phase_def = {
            "groups": [
                {"id": "C", "order": 2},
                {"id": "A", "order": 0},
                {"id": "B", "order": 1},
            ]
        }
        key, order = file_find_first_group(phase_def)
        assert key == "A"
        assert order == 0


# ══════════════════════════════════════════════
# FILE — file_find_next_group
# ══════════════════════════════════════════════


class TestFileFindNextGroup:
    def test_next_group_exists(self):
        phase_def = SIMPLE_WORKFLOW["phases"]["discovery"]
        result = file_find_next_group(phase_def, 0)
        assert result is not None
        key, order = result
        assert key == "B"
        assert order == 1

    def test_next_group_last(self):
        phase_def = SIMPLE_WORKFLOW["phases"]["discovery"]
        result = file_find_next_group(phase_def, 1)
        assert result is None

    def test_next_group_middle(self):
        phase_def = SIMPLE_WORKFLOW["phases"]["build"]
        result = file_find_next_group(phase_def, 0)
        assert result is not None
        assert result == ("B", 1)

    def test_next_group_skip_to_c(self):
        phase_def = SIMPLE_WORKFLOW["phases"]["build"]
        result = file_find_next_group(phase_def, 1)
        assert result is not None
        assert result == ("C", 2)

    def test_next_group_empty_groups(self):
        result = file_find_next_group({"groups": []}, 0)
        assert result is None

    def test_next_group_no_groups_key(self):
        result = file_find_next_group({}, 0)
        assert result is None


# ══════════════════════════════════════════════
# FILE — file_has_human_gate
# ══════════════════════════════════════════════


class TestFileHasHumanGate:
    def test_has_human_gate_true(self, tmp_path):
        path = _write_workflow(tmp_path, "wf.json", SIMPLE_WORKFLOW)
        assert file_has_human_gate(path, "design") is True

    def test_has_human_gate_false(self, tmp_path):
        path = _write_workflow(tmp_path, "wf.json", SIMPLE_WORKFLOW)
        assert file_has_human_gate(path, "discovery") is False

    def test_has_human_gate_missing_phase(self, tmp_path):
        path = _write_workflow(tmp_path, "wf.json", SIMPLE_WORKFLOW)
        assert file_has_human_gate(path, "nonexistent") is False


# ══════════════════════════════════════════════
# build_deliverable_path
# ══════════════════════════════════════════════


class TestBuildDeliverablePath:
    @patch.dict(os.environ, {"AG_FLOW_ROOT": "/app"})
    def test_standard_path(self):
        workflow = {"id": 42, "workflow_name": "my_wf"}
        phase = {"id": 7, "phase_key": "discovery", "group_key": "A"}
        result = build_deliverable_path("my-project", "team1", workflow, phase, "analyst", "prd")
        assert result == os.path.join(
            "/app", "projects", "my-project", "team1",
            "42:my_wf", "7:discovery-A", "analyst", "prd.md",
        )

    def test_path_contains_all_segments(self):
        """Verify build_deliverable_path assembles all components.

        Note: On Windows, os.path.join interprets 'N:name' as a drive letter,
        which breaks the path. This function is designed for Linux (Docker).
        We mock os.path.join to use posixpath.join for a reliable test.
        """
        import posixpath
        os.environ["AG_FLOW_ROOT"] = "/custom/root"
        try:
            workflow = {"id": 42, "workflow_name": "my_wf"}
            phase = {"id": 7, "phase_key": "discovery", "group_key": "A"}
            with patch("workflow_tracker.os.path.join", side_effect=posixpath.join):
                result = build_deliverable_path("slug", "t1", workflow, phase, "analyst", "prd")
            assert result == "/custom/root/projects/slug/t1/42:my_wf/7:discovery-A/analyst/prd.md"
        finally:
            del os.environ["AG_FLOW_ROOT"]

    def test_default_root_fallback(self):
        """When AG_FLOW_ROOT is unset, defaults to /app."""
        import posixpath
        env_backup = os.environ.pop("AG_FLOW_ROOT", None)
        try:
            workflow = {"id": 10, "workflow_name": "wf"}
            phase = {"id": 20, "phase_key": "build", "group_key": "B"}
            with patch("workflow_tracker.os.path.join", side_effect=posixpath.join):
                result = build_deliverable_path("proj", "team1", workflow, phase, "dev", "code")
            assert result.startswith("/app/projects/")
            assert result.endswith("/dev/code.md")
            assert "10:wf" in result
            assert "20:build-B" in result
        finally:
            if env_backup is not None:
                os.environ["AG_FLOW_ROOT"] = env_backup


# ══════════════════════════════════════════════
# DB — db_get_workflow
# ══════════════════════════════════════════════


class TestDbGetWorkflow:
    @pytest.mark.asyncio
    @patch("core.database.fetch_one", new_callable=AsyncMock)
    async def test_get_workflow_found(self, mock_fetch):
        mock_fetch.return_value = make_record(id=1, workflow_name="wf1")
        result = await db_get_workflow(1)
        assert result["id"] == 1
        mock_fetch.assert_awaited_once()

    @pytest.mark.asyncio
    @patch("core.database.fetch_one", new_callable=AsyncMock)
    async def test_get_workflow_not_found(self, mock_fetch):
        mock_fetch.return_value = None
        result = await db_get_workflow(999)
        assert result is None

    @pytest.mark.asyncio
    async def test_get_workflow_zero_id(self):
        result = await db_get_workflow(0)
        assert result is None

    @pytest.mark.asyncio
    async def test_get_workflow_none_id(self):
        result = await db_get_workflow(None)
        assert result is None


# ══════════════════════════════════════════════
# DB — db_get_phase
# ══════════════════════════════════════════════


class TestDbGetPhase:
    @pytest.mark.asyncio
    @patch("core.database.fetch_one", new_callable=AsyncMock)
    async def test_get_phase_found(self, mock_fetch):
        mock_fetch.return_value = make_record(id=10, phase_key="discovery")
        result = await db_get_phase(10)
        assert result["phase_key"] == "discovery"

    @pytest.mark.asyncio
    async def test_get_phase_zero_id(self):
        result = await db_get_phase(0)
        assert result is None


# ══════════════════════════════════════════════
# DB — db_check_human_gate
# ══════════════════════════════════════════════


class TestDbCheckHumanGate:
    @pytest.mark.asyncio
    @patch("core.database.fetch_one", new_callable=AsyncMock)
    async def test_gate_pending(self, mock_fetch):
        # First call (pending check) returns a row
        mock_fetch.return_value = make_record(id=1)
        result = await db_check_human_gate(42, "design")
        assert result == "pending"

    @pytest.mark.asyncio
    @patch("core.database.fetch_one", new_callable=AsyncMock)
    async def test_gate_approved(self, mock_fetch):
        # First call (pending) returns None, second call (answered) returns approved
        mock_fetch.side_effect = [None, make_record(response="approved")]
        result = await db_check_human_gate(42, "design")
        assert result == "approved"

    @pytest.mark.asyncio
    @patch("core.database.fetch_one", new_callable=AsyncMock)
    async def test_gate_rejected(self, mock_fetch):
        mock_fetch.side_effect = [None, make_record(response="rejected")]
        result = await db_check_human_gate(42, "design")
        assert result == "rejected"

    @pytest.mark.asyncio
    @patch("core.database.fetch_one", new_callable=AsyncMock)
    async def test_gate_not_created(self, mock_fetch):
        mock_fetch.side_effect = [None, None]
        result = await db_check_human_gate(42, "design")
        assert result == "not_created"


# ══════════════════════════════════════════════
# DB — db_create_workflow
# ══════════════════════════════════════════════


class TestDbCreateWorkflow:
    @pytest.mark.asyncio
    @patch("core.database.fetch_one", new_callable=AsyncMock)
    async def test_create_workflow_success(self, mock_fetch):
        mock_fetch.return_value = make_record(id=99, workflow_name="child")
        result = await db_create_workflow(1, "child", "child.wrk.json")
        assert result["id"] == 99
        mock_fetch.assert_awaited_once()


# ══════════════════════════════════════════════
# DB — db_create_phase / db_create_next_group
# ══════════════════════════════════════════════


class TestDbCreatePhase:
    @pytest.mark.asyncio
    @patch("core.database.execute", new_callable=AsyncMock)
    @patch("core.database.fetch_one", new_callable=AsyncMock)
    async def test_create_phase_updates_current(self, mock_fetch, mock_exec):
        mock_fetch.return_value = make_record(id=50, phase_key="discovery")
        result = await db_create_phase(1, "discovery", "Discovery", "A", 0, 0, 1)
        assert result["id"] == 50
        # Verify current_phase_id was updated
        mock_exec.assert_awaited_once()
        args = mock_exec.call_args
        assert args[0][1] == 50  # new phase id
        assert args[0][2] == 1   # workflow_id

    @pytest.mark.asyncio
    @patch("core.database.execute", new_callable=AsyncMock)
    @patch("core.database.fetch_one", new_callable=AsyncMock)
    async def test_create_phase_with_depends_on(self, mock_fetch, mock_exec):
        mock_fetch.return_value = make_record(id=51, depends_on_workflow_id=10)
        result = await db_create_phase(1, "ext", "External", "A", 0, 0, 1, depends_on_workflow_id=10)
        assert result["id"] == 51


class TestDbCreateNextGroup:
    @pytest.mark.asyncio
    @patch("core.database.execute", new_callable=AsyncMock)
    @patch("core.database.fetch_one", new_callable=AsyncMock)
    async def test_create_next_group_delegates(self, mock_fetch, mock_exec):
        mock_fetch.return_value = make_record(id=60, group_key="B")
        result = await db_create_next_group(1, "discovery", "Discovery", 0, "B", 1, 1)
        assert result["id"] == 60
        assert result["group_key"] == "B"


# ══════════════════════════════════════════════
# RESOLVE — resolve_next_phase
# ══════════════════════════════════════════════


class TestResolveNextPhase:
    @pytest.mark.asyncio
    @patch("workflow_tracker.db_create_next_group", new_callable=AsyncMock)
    @patch("workflow_tracker.db_get_workflow", new_callable=AsyncMock)
    async def test_next_group_in_same_phase(self, mock_get_wf, mock_create_ng, tmp_path):
        path = _write_workflow(tmp_path, "wf.json", SIMPLE_WORKFLOW)
        mock_get_wf.return_value = make_record(
            id=1, workflow_json_path=path, iteration=1,
        )
        mock_create_ng.return_value = make_record(id=70, group_key="B")

        result = await resolve_next_phase(1, 0, 0)
        assert result is not None
        assert result["group_key"] == "B"
        mock_create_ng.assert_awaited_once()

    @pytest.mark.asyncio
    @patch("workflow_tracker.db_create_phase", new_callable=AsyncMock)
    @patch("workflow_tracker.db_get_workflow", new_callable=AsyncMock)
    async def test_advance_to_next_phase_no_gate(self, mock_get_wf, mock_create, tmp_path):
        path = _write_workflow(tmp_path, "wf.json", SIMPLE_WORKFLOW)
        mock_get_wf.return_value = make_record(
            id=1, workflow_json_path=path, iteration=1,
        )
        mock_create.return_value = make_record(id=80, phase_key="design")

        # discovery has no human_gate, last group is order=1
        result = await resolve_next_phase(1, 0, 1)
        assert result is not None
        assert result["phase_key"] == "design"

    @pytest.mark.asyncio
    @patch("workflow_tracker.db_check_human_gate", new_callable=AsyncMock)
    @patch("workflow_tracker.db_get_workflow", new_callable=AsyncMock)
    async def test_blocked_by_human_gate_pending(self, mock_get_wf, mock_gate, tmp_path):
        path = _write_workflow(tmp_path, "wf.json", SIMPLE_WORKFLOW)
        mock_get_wf.return_value = make_record(
            id=1, workflow_json_path=path, iteration=1,
        )
        mock_gate.return_value = "pending"

        # design (order=1) has human_gate, last group is order=0
        result = await resolve_next_phase(1, 1, 0)
        assert result is None

    @pytest.mark.asyncio
    @patch("workflow_tracker.db_check_human_gate", new_callable=AsyncMock)
    @patch("workflow_tracker.db_get_workflow", new_callable=AsyncMock)
    async def test_blocked_by_human_gate_not_created(self, mock_get_wf, mock_gate, tmp_path):
        path = _write_workflow(tmp_path, "wf.json", SIMPLE_WORKFLOW)
        mock_get_wf.return_value = make_record(
            id=1, workflow_json_path=path, iteration=1,
        )
        mock_gate.return_value = "not_created"

        result = await resolve_next_phase(1, 1, 0)
        assert result is None

    @pytest.mark.asyncio
    @patch("workflow_tracker.db_check_human_gate", new_callable=AsyncMock)
    @patch("workflow_tracker.db_get_workflow", new_callable=AsyncMock)
    async def test_blocked_by_human_gate_rejected(self, mock_get_wf, mock_gate, tmp_path):
        path = _write_workflow(tmp_path, "wf.json", SIMPLE_WORKFLOW)
        mock_get_wf.return_value = make_record(
            id=1, workflow_json_path=path, iteration=1,
        )
        mock_gate.return_value = "rejected"

        result = await resolve_next_phase(1, 1, 0)
        assert result is None

    @pytest.mark.asyncio
    @patch("workflow_tracker.db_create_phase", new_callable=AsyncMock)
    @patch("workflow_tracker.db_check_human_gate", new_callable=AsyncMock)
    @patch("workflow_tracker.db_get_workflow", new_callable=AsyncMock)
    async def test_human_gate_approved_advances(self, mock_get_wf, mock_gate, mock_create, tmp_path):
        path = _write_workflow(tmp_path, "wf.json", SIMPLE_WORKFLOW)
        mock_get_wf.return_value = make_record(
            id=1, workflow_json_path=path, iteration=1,
        )
        mock_gate.return_value = "approved"
        mock_create.return_value = make_record(id=90, phase_key="build")

        # design (order=1) gate approved -> advance to build (order=2)
        result = await resolve_next_phase(1, 1, 0)
        assert result is not None
        assert result["phase_key"] == "build"

    @pytest.mark.asyncio
    @patch("workflow_tracker.db_get_workflow", new_callable=AsyncMock)
    async def test_workflow_terminated_no_next(self, mock_get_wf, tmp_path):
        path = _write_workflow(tmp_path, "wf.json", SIMPLE_WORKFLOW)
        mock_get_wf.return_value = make_record(
            id=1, workflow_json_path=path, iteration=1,
        )
        # build is order=2, last group C is order=2, no order=3 phase
        result = await resolve_next_phase(1, 2, 2)
        assert result is None

    @pytest.mark.asyncio
    @patch("workflow_tracker.db_get_workflow", new_callable=AsyncMock)
    async def test_workflow_not_found(self, mock_get_wf):
        mock_get_wf.return_value = None
        result = await resolve_next_phase(1, 0, 0)
        assert result is None

    @pytest.mark.asyncio
    @patch("workflow_tracker.db_get_workflow", new_callable=AsyncMock)
    async def test_workflow_no_json_path(self, mock_get_wf):
        mock_get_wf.return_value = make_record(id=1, workflow_json_path=None)
        result = await resolve_next_phase(1, 0, 0)
        assert result is None

    @pytest.mark.asyncio
    @patch("workflow_tracker.db_get_workflow", new_callable=AsyncMock)
    async def test_phase_order_not_found(self, mock_get_wf, tmp_path):
        path = _write_workflow(tmp_path, "wf.json", SIMPLE_WORKFLOW)
        mock_get_wf.return_value = make_record(
            id=1, workflow_json_path=path, iteration=1,
        )
        result = await resolve_next_phase(1, 99, 0)
        assert result is None

    @pytest.mark.asyncio
    @patch("workflow_tracker.resolve_create_external_workflow", new_callable=AsyncMock)
    @patch("workflow_tracker.db_create_phase", new_callable=AsyncMock)
    @patch("workflow_tracker.db_get_workflow", new_callable=AsyncMock)
    async def test_next_phase_external_creates_child(self, mock_get_wf, mock_create_ph, mock_ext, tmp_path):
        """When the next phase is external, resolve_create_external_workflow is called."""
        wf = {
            "phases": {
                "phase0": {
                    "name": "Phase 0",
                    "order": 0,
                    "groups": [{"id": "A", "order": 0}],
                },
                "phase1": {
                    "name": "External Phase",
                    "order": 1,
                    "type": "external",
                    "external_workflow": "child.wrk.json",
                    "groups": [{"id": "A", "order": 0}],
                },
            },
        }
        path = _write_workflow(tmp_path, "wf.json", wf)
        mock_get_wf.return_value = make_record(
            id=1, workflow_json_path=path, iteration=1,
        )
        mock_ext.return_value = make_record(id=500, workflow_name="child")
        mock_create_ph.return_value = make_record(id=100, phase_key="phase1")

        # Advance from phase0 (order=0, last group order=0) to phase1
        result = await resolve_next_phase(1, 0, 0)
        assert result is not None
        mock_ext.assert_awaited_once()


# ══════════════════════════════════════════════
# RESOLVE — resolve_create_external_workflow
# ══════════════════════════════════════════════


class TestResolveCreateExternalWorkflow:
    @pytest.mark.asyncio
    @patch("workflow_tracker.db_create_phase", new_callable=AsyncMock)
    @patch("workflow_tracker.db_create_workflow", new_callable=AsyncMock)
    async def test_create_simple_external(self, mock_create_wf, mock_create_ph, tmp_path):
        path = _write_workflow(tmp_path, "simple_ext.wrk.json", SIMPLE_WORKFLOW)
        mock_create_wf.return_value = make_record(id=100, workflow_name="simple_ext")
        mock_create_ph.return_value = make_record(id=200, phase_key="discovery")

        result = await resolve_create_external_workflow(1, path)
        assert result is not None
        assert result["id"] == 100
        mock_create_ph.assert_awaited_once()

    @pytest.mark.asyncio
    @patch("workflow_tracker.db_create_workflow", new_callable=AsyncMock)
    async def test_create_external_db_returns_none(self, mock_create_wf):
        mock_create_wf.return_value = None
        result = await resolve_create_external_workflow(1, "doesnt_matter.wrk.json")
        assert result is None

    @pytest.mark.asyncio
    @patch("workflow_tracker.db_create_phase", new_callable=AsyncMock)
    @patch("workflow_tracker.db_create_workflow", new_callable=AsyncMock)
    async def test_create_external_no_phases(self, mock_create_wf, mock_create_ph, tmp_path):
        path = _write_workflow(tmp_path, "empty.wrk.json", EMPTY_WORKFLOW)
        mock_create_wf.return_value = make_record(id=101, workflow_name="empty")

        result = await resolve_create_external_workflow(1, path)
        assert result is not None
        assert result["id"] == 101
        # No phase created because workflow is empty
        mock_create_ph.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_depth_limit_raises_at_max(self):
        with pytest.raises(ValueError, match="Profondeur max"):
            await resolve_create_external_workflow(1, "x.wrk.json", _depth=MAX_EXTERNAL_DEPTH)

    @pytest.mark.asyncio
    async def test_depth_limit_raises_above_max(self):
        with pytest.raises(ValueError, match="Profondeur max"):
            await resolve_create_external_workflow(1, "x.wrk.json", _depth=MAX_EXTERNAL_DEPTH + 5)

    @pytest.mark.asyncio
    @patch("workflow_tracker.db_create_workflow", new_callable=AsyncMock)
    async def test_depth_just_below_limit_ok(self, mock_wf):
        """Depth MAX_EXTERNAL_DEPTH - 1 should not raise (but may fail on DB)."""
        mock_wf.return_value = None  # Stops recursion early
        result = await resolve_create_external_workflow(
            1, "x.wrk.json", _depth=MAX_EXTERNAL_DEPTH - 1,
        )
        assert result is None

    @pytest.mark.asyncio
    @patch("workflow_tracker.db_create_phase", new_callable=AsyncMock)
    @patch("workflow_tracker.db_create_workflow", new_callable=AsyncMock)
    async def test_recursive_external_one_level(self, mock_create_wf, mock_create_ph, tmp_path):
        """External workflow whose first phase is also external -> recurse once."""
        nested_wf = {
            "phases": {
                "inner": {
                    "name": "Inner",
                    "order": 0,
                    "groups": [{"id": "A", "order": 0}],
                },
            },
        }
        nested_path = _write_workflow(tmp_path, "nested.wrk.json", nested_wf)

        outer_wf = {
            "phases": {
                "ext_phase": {
                    "name": "Ext Phase",
                    "order": 0,
                    "type": "external",
                    "external_workflow": nested_path,
                    "groups": [{"id": "A", "order": 0}],
                },
            },
        }
        outer_path = _write_workflow(tmp_path, "outer.wrk.json", outer_wf)

        # First call creates outer child, second creates nested child
        mock_create_wf.side_effect = [
            make_record(id=200, workflow_name="outer"),
            make_record(id=201, workflow_name="nested"),
        ]
        mock_create_ph.return_value = make_record(id=300, phase_key="ext_phase")

        result = await resolve_create_external_workflow(1, outer_path)
        assert result is not None
        assert result["id"] == 200
        assert mock_create_wf.await_count == 2

    @pytest.mark.asyncio
    @patch("workflow_tracker.db_create_phase", new_callable=AsyncMock)
    @patch("workflow_tracker.db_create_workflow", new_callable=AsyncMock)
    async def test_first_phase_order_1_fallback(self, mock_create_wf, mock_create_ph, tmp_path):
        """If no phase at order 0, falls back to order 1."""
        wf = {
            "phases": {
                "start": {
                    "name": "Start",
                    "order": 1,
                    "groups": [{"id": "A", "order": 0}],
                },
            },
        }
        path = _write_workflow(tmp_path, "fallback.wrk.json", wf)
        mock_create_wf.return_value = make_record(id=300, workflow_name="fallback")
        mock_create_ph.return_value = make_record(id=400, phase_key="start")

        result = await resolve_create_external_workflow(1, path)
        assert result is not None
        mock_create_ph.assert_awaited_once()


# ══════════════════════════════════════════════
# RESOLVE — db_get_current_position
# ══════════════════════════════════════════════


class TestDbGetCurrentPosition:
    @pytest.mark.asyncio
    @patch("workflow_tracker.db_get_workflow", new_callable=AsyncMock)
    async def test_workflow_not_found(self, mock_get_wf):
        mock_get_wf.return_value = None
        result = await db_get_current_position(999)
        assert result["error"] == "Workflow not found"

    @pytest.mark.asyncio
    @patch("workflow_tracker.db_get_workflow", new_callable=AsyncMock)
    async def test_not_started_none_phase_id(self, mock_get_wf):
        mock_get_wf.return_value = make_record(id=1, current_phase_id=None)
        result = await db_get_current_position(1)
        assert result["status"] == "not_started"
        assert result["phase"] is None

    @pytest.mark.asyncio
    @patch("workflow_tracker.db_get_workflow", new_callable=AsyncMock)
    async def test_not_started_missing_key(self, mock_get_wf):
        """current_phase_id key absent from dict -> .get() returns None."""
        mock_get_wf.return_value = make_record(id=1)
        result = await db_get_current_position(1)
        assert result["status"] == "not_started"

    @pytest.mark.asyncio
    @patch("workflow_tracker.db_get_phase", new_callable=AsyncMock)
    @patch("workflow_tracker.db_get_workflow", new_callable=AsyncMock)
    async def test_phase_not_found_error(self, mock_get_wf, mock_get_ph):
        mock_get_wf.return_value = make_record(id=1, current_phase_id=10)
        mock_get_ph.return_value = None
        result = await db_get_current_position(1)
        assert result["status"] == "error"

    @pytest.mark.asyncio
    @patch("workflow_tracker.db_get_phase", new_callable=AsyncMock)
    @patch("workflow_tracker.db_get_workflow", new_callable=AsyncMock)
    async def test_active_phase_pending(self, mock_get_wf, mock_get_ph):
        mock_get_wf.return_value = make_record(id=1, current_phase_id=10)
        mock_get_ph.return_value = make_record(
            id=10, status="pending", completed_at=None, depends_on_workflow_id=None,
        )
        result = await db_get_current_position(1)
        assert result["status"] == "pending"
        assert result["phase"]["id"] == 10
        assert result["workflow"]["id"] == 1

    @pytest.mark.asyncio
    @patch("workflow_tracker.db_get_phase", new_callable=AsyncMock)
    @patch("workflow_tracker.db_get_workflow", new_callable=AsyncMock)
    async def test_phase_completed(self, mock_get_wf, mock_get_ph):
        mock_get_wf.return_value = make_record(id=1, current_phase_id=10)
        mock_get_ph.return_value = make_record(
            id=10, status="done", completed_at="2026-01-01", depends_on_workflow_id=None,
        )
        result = await db_get_current_position(1)
        assert result["status"] == "phase_completed"

    @pytest.mark.asyncio
    @patch("workflow_tracker.db_get_phase", new_callable=AsyncMock)
    @patch("workflow_tracker.db_get_workflow", new_callable=AsyncMock)
    async def test_follows_external_dependency(self, mock_get_wf, mock_get_ph):
        """Phase depends on external workflow -> recurse into child."""
        mock_get_wf.side_effect = [
            make_record(id=1, current_phase_id=10),
            make_record(id=2, current_phase_id=20),
        ]
        mock_get_ph.side_effect = [
            make_record(id=10, status="pending", completed_at=None, depends_on_workflow_id=2),
            make_record(id=20, status="in_progress", completed_at=None, depends_on_workflow_id=None),
        ]
        result = await db_get_current_position(1)
        assert result["status"] == "in_progress"
        assert result["phase"]["id"] == 20

    @pytest.mark.asyncio
    async def test_depth_limit_returns_error(self):
        result = await db_get_current_position(1, _depth=MAX_POSITION_DEPTH)
        assert "error" in result
        assert "Profondeur max" in result["error"]

    @pytest.mark.asyncio
    @patch("workflow_tracker.db_get_phase", new_callable=AsyncMock)
    @patch("workflow_tracker.db_get_workflow", new_callable=AsyncMock)
    async def test_depth_limit_via_recursion_cycle(self, mock_get_wf, mock_get_ph):
        """Simulate a cycle: every phase depends on the same workflow."""
        mock_get_wf.return_value = make_record(id=1, current_phase_id=10)
        mock_get_ph.return_value = make_record(
            id=10, status="pending", completed_at=None, depends_on_workflow_id=1,
        )
        result = await db_get_current_position(1)
        assert "error" in result

    @pytest.mark.asyncio
    @patch("workflow_tracker.db_get_phase", new_callable=AsyncMock)
    @patch("workflow_tracker.db_get_workflow", new_callable=AsyncMock)
    async def test_status_from_phase_unknown(self, mock_get_wf, mock_get_ph):
        """When phase has no status key, returns 'unknown'."""
        mock_get_wf.return_value = make_record(id=1, current_phase_id=10)
        mock_get_ph.return_value = make_record(
            id=10, completed_at=None, depends_on_workflow_id=None,
        )
        result = await db_get_current_position(1)
        assert result["status"] == "unknown"


# ══════════════════════════════════════════════
# Constants
# ══════════════════════════════════════════════


class TestConstants:
    def test_max_external_depth_value(self):
        assert MAX_EXTERNAL_DEPTH == 10

    def test_max_position_depth_value(self):
        assert MAX_POSITION_DEPTH == 10

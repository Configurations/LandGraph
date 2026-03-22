"""E2E test configuration — environment variables and shared constants.

All URLs default to AGT1 local ports. Override via env vars when running
from outside the Docker network (e.g. DISPATCHER_URL=http://192.168.10.147:8070).
"""

import os

import pytest

# ── Service URLs ──────────────────────────────────────
DISPATCHER_URL = os.getenv("DISPATCHER_URL", "http://localhost:8070")
HITL_URL = os.getenv("HITL_URL", "http://localhost:8090")
WS_URL = os.getenv("WS_URL", "ws://localhost:8090")

# ── Auth credentials (seeded admin on AGT1) ──────────
ADMIN_EMAIL = os.getenv("HITL_ADMIN_EMAIL", "admin@langgraph.local")
ADMIN_PASSWORD = os.getenv("HITL_ADMIN_PASSWORD", "admin")

# ── Test identifiers ─────────────────────────────────
TEST_TEAM_ID = os.getenv("TEST_TEAM_ID", "team1")
TEST_AGENT_IMAGE = "agflow-test-agent:latest"
TEST_PROJECT_SLUG = "e2e-test-project"
TEST_PROJECT_NAME = "E2E Test Project"
AG_FLOW_ROOT = os.getenv("AG_FLOW_ROOT", "/root/ag.flow")

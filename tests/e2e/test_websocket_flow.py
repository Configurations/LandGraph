"""E2E test: WebSocket real-time events from HITL console.

Scenario:
  1. Login to get JWT
  2. Connect WebSocket to /api/teams/{team_id}/ws?token=JWT
  3. Verify connection accepted (no 4001 close)
  4. Wait for a ping from server (keepalive within 45s)
  5. Send pong response
  6. Disconnect cleanly

Requires: HITL console (port 8090) running on AGT1.
Uses: websockets library (pip install websockets).
"""

import json
import time

import pytest

from tests.e2e.conftest import (
    ADMIN_EMAIL,
    ADMIN_PASSWORD,
    HITL_URL,
    TEST_TEAM_ID,
    WS_URL,
)
from tests.e2e.helpers import check_health, login


_hitl_ok = check_health(HITL_URL)

skip_no_hitl = pytest.mark.skipif(
    not _hitl_ok, reason=f"HITL console not reachable at {HITL_URL}"
)

try:
    import websockets  # noqa: F401
    _ws_available = True
except ImportError:
    _ws_available = False

skip_no_ws_lib = pytest.mark.skipif(
    not _ws_available, reason="websockets library not installed"
)


@pytest.fixture(scope="module")
def admin_token():
    if not _hitl_ok:
        pytest.skip("HITL console not available")
    return login(HITL_URL, ADMIN_EMAIL, ADMIN_PASSWORD)


@skip_no_hitl
@skip_no_ws_lib
class TestWebSocket:
    """WebSocket connectivity and keepalive."""

    def test_ws_connect_and_receive_ping(self, admin_token):
        """Connect WS, wait for server ping, respond with pong."""
        import asyncio
        import websockets

        async def _run():
            url = f"{WS_URL}/api/teams/{TEST_TEAM_ID}/ws?token={admin_token}"
            print(f"  Connecting to {WS_URL}/api/teams/{TEST_TEAM_ID}/ws")

            async with websockets.connect(url, close_timeout=5) as ws:
                print("  WebSocket connected")

                # Wait for a message (server sends ping within 45s)
                # We use a shorter timeout to keep the test fast
                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=50)
                    msg = json.loads(raw)
                    print(f"  Received: {msg}")
                    assert msg.get("type") in ("ping", "question_new", "question_answered", "chat_message")

                    if msg["type"] == "ping":
                        await ws.send(json.dumps({"type": "pong"}))
                        print("  Sent pong")
                except asyncio.TimeoutError:
                    pytest.fail("No message received from WS within 50s")

                print("  Closing WebSocket")

        asyncio.get_event_loop().run_until_complete(_run())

    def test_ws_bad_token_rejected(self):
        """Connection with invalid token gets closed with 4001."""
        import asyncio
        import websockets

        async def _run():
            url = f"{WS_URL}/api/teams/{TEST_TEAM_ID}/ws?token=invalid-token"
            print(f"  Connecting with bad token...")

            try:
                async with websockets.connect(url, close_timeout=5) as ws:
                    # Server accepts then closes with 4001
                    try:
                        raw = await asyncio.wait_for(ws.recv(), timeout=5)
                        # If we get a message, the server didn't reject us
                        pytest.fail(f"Expected close, got message: {raw}")
                    except websockets.ConnectionClosed as e:
                        assert e.code == 4001
                        print(f"  Correctly rejected: code={e.code} reason={e.reason}")
            except websockets.ConnectionClosed as e:
                assert e.code == 4001
                print(f"  Correctly rejected at connect: code={e.code}")

        asyncio.get_event_loop().run_until_complete(_run())

    def test_ws_watch_chat(self, admin_token):
        """Send watch_chat command and verify no error."""
        import asyncio
        import websockets

        async def _run():
            url = f"{WS_URL}/api/teams/{TEST_TEAM_ID}/ws?token={admin_token}"

            async with websockets.connect(url, close_timeout=5) as ws:
                print("  Connected, sending watch_chat")
                await ws.send(json.dumps({
                    "type": "watch_chat",
                    "agent_id": "lead_dev",
                }))
                print("  Sent watch_chat command")

                # Wait briefly for any error or ping
                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=10)
                    msg = json.loads(raw)
                    print(f"  Received after watch_chat: {msg}")
                    # Should be a normal message (ping, etc.) — not an error close
                except asyncio.TimeoutError:
                    print("  No response within 10s (acceptable — server just registered the watch)")

                # Unwatch
                await ws.send(json.dumps({"type": "unwatch_chat"}))
                print("  Sent unwatch_chat")

        asyncio.get_event_loop().run_until_complete(_run())

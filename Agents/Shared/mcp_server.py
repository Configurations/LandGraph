"""MCP SSE Server — expose LandGraph agents as MCP tools per team."""
import asyncio
import json
import logging
import os
from datetime import datetime, timezone

from mcp.server import Server
from mcp.server.sse import SseServerTransport
from mcp.types import TextContent, Tool

logger = logging.getLogger("mcp_server")


def _build_tools_for_team(team_id: str, allowed_agents: list | None = None) -> list[dict]:
    """Load agent registry for a team and return tool definitions."""
    from agents.shared.agent_loader import get_agents
    agents = get_agents(team_id)
    tools = []
    for agent_id, agent_callable in agents.items():
        if agent_id == "orchestrator":
            continue
        if allowed_agents and "*" not in allowed_agents and agent_id not in allowed_agents:
            continue
        name = getattr(agent_callable, "agent_name", agent_id)
        desc = getattr(agent_callable, "description", f"Agent {name}")
        tools.append({
            "agent_id": agent_id,
            "name": name,
            "description": desc,
            "callable": agent_callable,
        })
    return tools


def create_mcp_server(team_id: str, allowed_agents: list | None = None) -> Server:
    """Create an MCP Server instance with tools for the given team."""
    server = Server(f"langgraph-{team_id}")
    agent_tools = _build_tools_for_team(team_id, allowed_agents)

    @server.list_tools()
    async def list_tools() -> list[Tool]:
        result = []
        for t in agent_tools:
            result.append(Tool(
                name=t["agent_id"],
                description=f"{t['name']} — {t['description']}",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "task": {
                            "type": "string",
                            "description": "The task or instruction for this agent",
                        },
                        "thread_id": {
                            "type": "string",
                            "description": "Thread ID for context persistence (optional)",
                            "default": f"mcp-{team_id}",
                        },
                    },
                    "required": ["task"],
                },
            ))
        return result

    @server.call_tool()
    async def call_tool(name: str, arguments: dict) -> list[TextContent]:
        # Find the agent
        agent_info = None
        for t in agent_tools:
            if t["agent_id"] == name:
                agent_info = t
                break

        if agent_info is None:
            return [TextContent(type="text", text=f"Unknown agent: {name}")]

        task = arguments.get("task", "")
        thread_id = arguments.get("thread_id", f"mcp-{team_id}")

        logger.info(f"[MCP] {team_id}/{name}: {task[:100]}")

        try:
            from agents.shared.event_bus import bus, Event
            bus.emit(Event("agent_dispatch", agent_id=name,
                           thread_id=thread_id, team_id=team_id,
                           data={"trigger": "mcp", "task": task[:200]}))

            # Build state and run agent
            state = {
                "messages": [("user", task)],
                "project_id": f"mcp-{team_id}",
                "project_phase": "discovery",
                "project_metadata": {},
                "agent_outputs": {},
                "legal_alerts": [],
                "decision_history": [],
                "current_assignments": {},
                "blockers": [],
                "human_feedback_log": [],
                "notifications_log": [],
                "_discord_channel_id": "",
                "_team_id": team_id,
            }

            result = await asyncio.wait_for(
                asyncio.to_thread(agent_info["callable"], state),
                timeout=2100,
            )

            # Extract output
            outputs = result.get("agent_outputs", {})
            agent_output = outputs.get(name, {})
            content = agent_output.get("content", str(agent_output))
            if isinstance(content, dict):
                content = json.dumps(content, ensure_ascii=False, indent=2)

            return [TextContent(type="text", text=content)]

        except asyncio.TimeoutError:
            return [TextContent(type="text", text=f"Agent {name} timed out (35min)")]
        except Exception as e:
            logger.error(f"[MCP] {name} error: {e}", exc_info=True)
            return [TextContent(type="text", text=f"Error: {str(e)[:500]}")]

    return server


def mount_mcp_routes(app):
    """Mount MCP SSE endpoints on the FastAPI app."""
    from starlette.requests import Request
    from starlette.responses import Response
    from agents.shared.mcp_auth import validate_token

    # Store active transports per session
    _transports: dict[str, SseServerTransport] = {}

    @app.get("/mcp/{team_id}/sse")
    async def mcp_sse(team_id: str, request: Request):
        """SSE endpoint — MCP client connects here."""
        # Auth
        auth = request.headers.get("authorization", "")
        token = auth.removeprefix("Bearer ").strip() if auth.startswith("Bearer") else ""
        if not token:
            return Response("Missing Authorization header", status_code=401)

        claims = validate_token(token, team_id)
        if claims is None:
            return Response("Invalid or unauthorized token", status_code=403)

        allowed_agents = claims.get("agents", ["*"])
        server = create_mcp_server(team_id, allowed_agents)

        # Create SSE transport for this session
        messages_path = f"/mcp/{team_id}/messages/"
        sse_transport = SseServerTransport(messages_path)

        async with sse_transport.connect_sse(
            request.scope, request.receive, request._send
        ) as (read_stream, write_stream):
            await server.run(
                read_stream, write_stream,
                server.create_initialization_options(),
            )

    @app.post("/mcp/{team_id}/messages/")
    async def mcp_messages(team_id: str, request: Request):
        """Message endpoint — MCP client posts JSON-RPC here."""
        # The SseServerTransport handles this via its internal routing
        # This endpoint exists as a placeholder; actual handling is done
        # by the SSE transport's handle_post_message
        return Response("Use SSE connection", status_code=400)

    logger.info("MCP SSE routes mounted at /mcp/{team_id}/sse")

"""Human Gate — Validation humaine via le canal configure (Discord, Email, etc.)."""
import logging
import os
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger("human_gate")

DEFAULT_TIMEOUT = 1800


async def request_approval(agent_name: str, summary: str, details: str = "",
                            channel_id: str = "", timeout: int = DEFAULT_TIMEOUT,
                            channel_type: str = "",
                            thread_id: str = "", team_id: str = "default") -> dict:
    from agents.shared.channels import get_channel, get_default_channel_type
    ctype = channel_type or get_default_channel_type()
    cid = channel_id or os.getenv("DISCORD_CHANNEL_REVIEW", "")
    ch = get_channel(ctype)
    return await ch.approve(cid, agent_name, summary, details, timeout,
                            thread_id=thread_id, team_id=team_id)


def request_approval_sync(agent_name: str, summary: str, details: str = "",
                           channel_id: str = "", timeout: int = DEFAULT_TIMEOUT,
                           channel_type: str = "",
                           thread_id: str = "", team_id: str = "default") -> dict:
    from agents.shared.channels import get_channel, get_default_channel_type, _run_async
    ctype = channel_type or get_default_channel_type()
    cid = channel_id or os.getenv("DISCORD_CHANNEL_REVIEW", "")
    ch = get_channel(ctype)
    result = _run_async(ch.approve(cid, agent_name, summary, details, timeout,
                                    thread_id=thread_id, team_id=team_id))
    if result is None:
        return {"approved": True, "response": "error — auto-approve", "reviewer": "system", "timed_out": False}
    return result

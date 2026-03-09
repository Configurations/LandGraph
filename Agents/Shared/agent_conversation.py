"""Agent Conversation — Les agents posent des questions aux humains via le canal configure."""
import logging
import os
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger("agent_conversation")

DEFAULT_TIMEOUT = 1800


async def ask_human(agent_name: str, question: str, channel_id: str,
                     context: str = "", timeout: int = DEFAULT_TIMEOUT,
                     channel_type: str = "") -> dict:
    from agents.shared.channels import get_channel, get_default_channel_type
    ctype = channel_type or get_default_channel_type()
    ch = get_channel(ctype)
    return await ch.ask(channel_id, agent_name, question, context, timeout)


def ask_human_sync(agent_name: str, question: str, channel_id: str,
                    context: str = "", timeout: int = DEFAULT_TIMEOUT,
                    channel_type: str = "") -> dict:
    from agents.shared.channels import get_channel, get_default_channel_type, _run_async
    ctype = channel_type or get_default_channel_type()
    ch = get_channel(ctype)
    result = _run_async(ch.ask(channel_id, agent_name, question, context, timeout))
    if result is None:
        return {"answered": False, "response": "", "author": "", "timed_out": True}
    return result

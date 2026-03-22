"""PG NOTIFY channel constants.

KEEP IN SYNC with dispatcher/core/channels.py
"""

# Shared channels (dispatcher ↔ console)
CH_HITL_REQUEST = "hitl_request"
CH_HITL_RESPONSE = "hitl_response"
CH_TASK_PROGRESS = "task_progress"
CH_TASK_ARTIFACT = "task_artifact"

# Console-only channels
CH_HITL_CHAT = "hitl_chat"
CH_PM_INBOX = "pm_inbox"

# All channels the console listens on
ALL_CHANNELS = [
    CH_HITL_REQUEST,
    CH_HITL_RESPONSE,
    CH_TASK_PROGRESS,
    CH_TASK_ARTIFACT,
    CH_HITL_CHAT,
    CH_PM_INBOX,
]

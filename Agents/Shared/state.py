"""ProjectState — Schema d'etat partage entre tous les agents."""
from typing import TypedDict, Annotated
from langgraph.graph.message import add_messages


class ProjectState(TypedDict, total=False):
    messages: Annotated[list, add_messages]
    project_id: str
    project_phase: str
    project_metadata: dict
    agent_outputs: dict
    current_assignments: dict
    decision_history: list
    blockers: list
    legal_alerts: list
    qa_verdict: dict
    deploy_status: dict
    human_feedback_log: list
    notifications_log: list

"""Wizard step Pydantic v2 schemas."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class WizardStepBody(BaseModel):
    """Request body when saving a wizard step."""

    data: dict[str, Any] = Field(default_factory=dict)

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field, model_validator


class TaskMessage(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    task_name: str
    queue: str = "default"
    args: list[Any] = Field(default_factory=list)
    kwargs: dict[str, Any] = Field(default_factory=dict)
    eta: datetime | None = None

    model_config = {"arbitrary_types_allowed": True}

    @model_validator(mode="after")
    def _normalize_eta_timezone(self) -> TaskMessage:
        if self.eta is not None and self.eta.tzinfo is None:
            self.eta = self.eta.replace(tzinfo=UTC)
        return self

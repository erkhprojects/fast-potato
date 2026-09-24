from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field, model_validator


class TaskMessage(BaseModel):
    """
    Wire format for one task invocation.

    ``payload`` is the task's input model dumped with ``model_dump(mode="json")``,
    or None for tasks that take no input. Pydantic owns all (de)serialization.
    """

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    task_name: str
    queue: str = "default"
    payload: dict[str, Any] | None = None
    eta: datetime | None = None

    @model_validator(mode="after")
    def _normalize_eta_timezone(self) -> TaskMessage:
        if self.eta is not None and self.eta.tzinfo is None:
            self.eta = self.eta.replace(tzinfo=UTC)
        return self

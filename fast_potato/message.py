from __future__ import annotations

import types
import typing
import uuid
from datetime import UTC, datetime
from typing import Any, get_args, get_origin

from pydantic import BaseModel, Field, model_validator


def serialize_value(value: Any) -> Any:
    """Recursively serialize an argument to a JSON-safe structure."""
    if isinstance(value, BaseModel):
        return {
            "__pydantic__": type(value).__qualname__,
            "data": value.model_dump(mode="json"),
        }
    if isinstance(value, list):
        return [serialize_value(v) for v in value]
    if isinstance(value, dict):
        return {k: serialize_value(v) for k, v in value.items()}
    return value


def deserialize_value(
    val: Any,
    annotation: Any = None,
    globals_dict: dict[str, Any] | None = None,
) -> Any:
    """
    Recursively deserialize arguments back into their target types.

    Reconstructs Pydantic models serialized as:
    ``{"__pydantic__": "ModelName", "data": {...}}``
    or plain dicts when the parameter annotation expects a BaseModel subclass.
    """
    # 1. Handle Union types (e.g. User | None or Optional[User])
    if get_origin(annotation) in (typing.Union, types.UnionType):
        for u_arg in get_args(annotation):
            if isinstance(u_arg, type) and issubclass(u_arg, BaseModel):
                try:
                    return deserialize_value(val, u_arg, globals_dict)
                except Exception:
                    pass

    # 2. Reconstruct from explicit Pydantic serialization envelope
    if isinstance(val, dict) and "__pydantic__" in val and "data" in val:
        cls_name = val["__pydantic__"]
        data = val["data"]

        # Check annotation first
        if isinstance(annotation, type) and issubclass(annotation, BaseModel):
            return annotation.model_validate(data)

        # Fallback to module globals of the task function
        if globals_dict and cls_name in globals_dict:
            target_cls = globals_dict[cls_name]
            if isinstance(target_cls, type) and issubclass(target_cls, BaseModel):
                return target_cls.model_validate(data)

        return data

    # 3. Model expected by annotation and raw dict provided
    if (
        isinstance(annotation, type)
        and issubclass(annotation, BaseModel)
        and isinstance(val, dict)
    ):
        return annotation.model_validate(val)

    # 4. List annotations (e.g. list[User])
    if get_origin(annotation) is list and isinstance(val, list):
        args = get_args(annotation)
        item_type = args[0] if args else Any
        return [deserialize_value(item, item_type, globals_dict) for item in val]

    # 5. Nested untyped lists or dicts
    if isinstance(val, list):
        return [deserialize_value(item, Any, globals_dict) for item in val]
    if isinstance(val, dict):
        return {k: deserialize_value(v, Any, globals_dict) for k, v in val.items()}

    return val


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

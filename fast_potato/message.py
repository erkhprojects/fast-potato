from __future__ import annotations

import inspect
import types
import typing
import uuid
from abc import ABC, abstractmethod
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any, get_args, get_origin

from pydantic import BaseModel, Field, model_validator


def _is_tagged_dict(val: Any) -> bool:
    return isinstance(val, dict) and "__type__" in val and "data" in val


def _matches_type_name(model_cls: type[BaseModel], type_name: str) -> bool:
    return (
        model_cls.__name__ == type_name
        or getattr(model_cls, "__qualname__", "") == type_name
    )


def _get_model_candidates(annotation: Any) -> list[type[BaseModel]]:
    """Extract all BaseModel subclasses from an annotation (Union or single model)."""
    if get_origin(annotation) in (typing.Union, types.UnionType):
        return [
            u_arg
            for u_arg in get_args(annotation)
            if isinstance(u_arg, type) and issubclass(u_arg, BaseModel)
        ]
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        return [annotation]
    return []


def _deserialize_tagged_model(
    val: dict[str, Any],
    candidates: list[type[BaseModel]],
    annotation: Any,
) -> BaseModel:
    """Deserialize a tagged payload ({"__type__": ..., "data": ...}) against candidate models."""
    type_name = val["__type__"]
    data = val["data"]
    for model_cls in candidates:
        if _matches_type_name(model_cls, type_name):
            return model_cls.model_validate(data)

    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        target_desc = f"expected model '{annotation.__name__}'"
    else:
        target_desc = f"union '{annotation}'"
    raise TypeError(
        f"Cannot deserialize payload with __type__='{type_name}' into {target_desc}. "
        f"No matching model found in candidates."
    )


# --- Strategy Interface & Concrete Implementations ---


class BaseTypeStrategy(ABC):
    """Abstract base class for type-specific serialization and deserialization strategies."""

    @abstractmethod
    def can_handle(self, annotation: Any) -> bool:
        """Return True if this strategy handles the given parameter type annotation."""
        ...

    @abstractmethod
    def deserialize(
        self,
        val: Any,
        annotation: Any,
        dispatcher: Callable[[Any, Any], Any],
    ) -> Any:
        """Deserialize val according to annotation, using dispatcher for recursive calls."""
        ...

    def can_serialize(self, val: Any) -> bool:
        """Return True if this strategy handles serializing this runtime value. Defaults to False."""
        return False

    def serialize(
        self,
        val: Any,
        dispatcher: Callable[[Any], Any],
    ) -> Any:
        """Serialize val to a JSON-safe structure. Defaults to returning val."""
        return val


class UnionTypeStrategy(BaseTypeStrategy):
    """Strategy for Union types (e.g. User | Profile | None or Optional[User])."""

    def can_handle(self, annotation: Any) -> bool:
        return get_origin(annotation) in (typing.Union, types.UnionType)

    def deserialize(
        self,
        val: Any,
        annotation: Any,
        dispatcher: Callable[[Any, Any], Any],
    ) -> Any:
        if val is None and type(None) in get_args(annotation):
            return None

        candidates = _get_model_candidates(annotation)

        # Disambiguate via __type__ tag against Union candidates
        if _is_tagged_dict(val):
            return _deserialize_tagged_model(val, candidates, annotation)

        # Untagged dictionary in union (e.g. {"name": "Alice", "age": 30})
        if isinstance(val, dict):
            for model_cls in candidates:
                try:
                    return model_cls.model_validate(val)
                except Exception:
                    pass

            # Try non-BaseModel union arguments via dispatcher (e.g. custom types in Point | None)
            for u_arg in get_args(annotation):
                if u_arg is not type(None) and not (
                    isinstance(u_arg, type) and issubclass(u_arg, BaseModel)
                ):
                    try:
                        res = dispatcher(val, u_arg)
                        if res is not val:
                            return res
                    except Exception:
                        pass

            if dict in get_args(annotation) or any(
                get_origin(arg) is dict for arg in get_args(annotation)
            ):
                return val
            raise TypeError(
                f"Cannot deserialize untagged dict into union '{annotation}'. "
                f"Payload did not match any candidate model."
            )
        return val


class PydanticModelStrategy(BaseTypeStrategy):
    """Strategy for single Pydantic BaseModel types (e.g. User)."""

    def can_handle(self, annotation: Any) -> bool:
        return isinstance(annotation, type) and issubclass(annotation, BaseModel)

    def deserialize(
        self,
        val: Any,
        annotation: Any,
        dispatcher: Callable[[Any, Any], Any],
    ) -> Any:
        if _is_tagged_dict(val):
            return _deserialize_tagged_model(val, [annotation], annotation)
        if isinstance(val, dict):
            return annotation.model_validate(val)
        if isinstance(val, annotation):
            return val
        return annotation.model_validate(val)

    def can_serialize(self, val: Any) -> bool:
        return isinstance(val, BaseModel)

    def serialize(
        self,
        val: Any,
        dispatcher: Callable[[Any], Any],
    ) -> Any:
        return {
            "__type__": type(val).__name__,
            "data": val.model_dump(mode="json"),
        }


class ListTypeStrategy(BaseTypeStrategy):
    """Strategy for list types (e.g. list[User] or list[int])."""

    def can_handle(self, annotation: Any) -> bool:
        return get_origin(annotation) is list

    def deserialize(
        self,
        val: Any,
        annotation: Any,
        dispatcher: Callable[[Any, Any], Any],
    ) -> Any:
        if isinstance(val, list):
            args = get_args(annotation)
            item_type = args[0] if args else Any
            return [dispatcher(item, item_type) for item in val]
        return val

    def can_serialize(self, val: Any) -> bool:
        return isinstance(val, list)

    def serialize(
        self,
        val: Any,
        dispatcher: Callable[[Any], Any],
    ) -> Any:
        return [dispatcher(item) for item in val]


class DictTypeStrategy(BaseTypeStrategy):
    """Strategy for dict types (e.g. dict[str, User] or dict[str, int])."""

    def can_handle(self, annotation: Any) -> bool:
        return get_origin(annotation) is dict

    def deserialize(
        self,
        val: Any,
        annotation: Any,
        dispatcher: Callable[[Any, Any], Any],
    ) -> Any:
        if isinstance(val, dict):
            args = get_args(annotation)
            val_type = args[1] if len(args) > 1 else Any
            return {k: dispatcher(v, val_type) for k, v in val.items()}
        return val

    def can_serialize(self, val: Any) -> bool:
        return isinstance(val, dict)

    def serialize(
        self,
        val: Any,
        dispatcher: Callable[[Any], Any],
    ) -> Any:
        return {k: dispatcher(v) for k, v in val.items()}


class PassThroughStrategy(BaseTypeStrategy):
    """Fallback strategy for primitives and unhandled/untyped values (e.g. int, str, float, bool, Any)."""

    def can_handle(self, annotation: Any) -> bool:
        return True

    def deserialize(
        self,
        val: Any,
        annotation: Any,
        dispatcher: Callable[[Any, Any], Any],
    ) -> Any:
        return val

    def can_serialize(self, val: Any) -> bool:
        return True

    def serialize(
        self,
        val: Any,
        dispatcher: Callable[[Any], Any],
    ) -> Any:
        return val


# --- Dispatcher Registry ---


class TypeDispatcher:
    """Registry and dispatcher coordinating type-specific serialization and deserialization."""

    def __init__(
        self,
        custom_strategies: list[BaseTypeStrategy] | None = None,
        prioritize_custom: bool = False,
    ) -> None:
        # Default built-in strategies are ALWAYS available
        default_builtins: list[BaseTypeStrategy] = [
            UnionTypeStrategy(),
            PydanticModelStrategy(),
            ListTypeStrategy(),
            DictTypeStrategy(),
        ]
        if custom_strategies:
            if prioritize_custom:
                self._strategies: list[BaseTypeStrategy] = (
                    list(custom_strategies) + default_builtins
                )
            else:
                self._strategies = (
                    default_builtins + list(custom_strategies)
                )
        else:
            self._strategies = default_builtins
        self._fallback: BaseTypeStrategy = PassThroughStrategy()

    @property
    def strategies(self) -> list[BaseTypeStrategy]:
        """List of active strategies in resolution order."""
        return list(self._strategies)

    def register_strategy(
        self, strategy: BaseTypeStrategy, at_front: bool = False
    ) -> None:
        """Register a custom strategy. Appends by default to preserve built-in strategy priority."""
        if at_front:
            self._strategies.insert(0, strategy)
        else:
            self._strategies.append(strategy)

    def find_strategy(self, annotation: Any) -> BaseTypeStrategy:
        """Find the matching strategy for a given type annotation."""
        if annotation is None or annotation is inspect.Parameter.empty:
            raise TypeError(
                "Type annotation cannot be None or empty. "
                "All parameters must have an explicit type annotation."
            )
        if annotation is Any:
            return self._fallback
        for strategy in self._strategies:
            if strategy.can_handle(annotation):
                return strategy
        return self._fallback

    def serialize(self, val: Any) -> Any:
        """Recursively serialize a value to a JSON-safe structure."""
        for strategy in self._strategies:
            if strategy.can_serialize(val):
                return strategy.serialize(val, self.serialize)
        return self._fallback.serialize(val, self.serialize)

    def deserialize(self, val: Any, annotation: Any = None) -> Any:
        """Recursively deserialize an argument back into its target type."""
        if annotation is None or annotation is inspect.Parameter.empty:
            raise TypeError(
                "Type annotation cannot be None or empty. "
                "All parameters must have an explicit type annotation."
            )
        strategy = self.find_strategy(annotation)
        return strategy.deserialize(val, annotation, self.deserialize)


default_dispatcher = TypeDispatcher()


def serialize_value(value: Any) -> Any:
    """Recursively serialize an argument to a JSON-safe structure with type tagging for models."""
    return default_dispatcher.serialize(value)


def deserialize_value(val: Any, annotation: Any = None) -> Any:
    """Recursively deserialize arguments back into their target types guided by parameter annotations."""
    if annotation is None or annotation is inspect.Parameter.empty:
        raise TypeError(
            "Type annotation cannot be None or empty. "
            "All parameters must have an explicit type annotation."
        )
    return default_dispatcher.deserialize(val, annotation)



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

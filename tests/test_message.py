from datetime import UTC, datetime
from typing import Any, Optional

import pytest
from pydantic import BaseModel

from fast_potato.message import (
    BaseTypeStrategy,
    TaskMessage,
    TypeDispatcher,
    deserialize_value,
    serialize_value,
)


class Address(BaseModel):
    city: str
    country: str


class User(BaseModel):
    name: str
    age: int
    address: Address


class SimpleItem(BaseModel):
    id: int
    label: str


class Profile(BaseModel):
    id: int
    label: str


class TestTaskMessage:
    def test_default_fields(self):
        msg = TaskMessage(task_name="test.task")
        assert msg.task_name == "test.task"
        assert msg.queue == "default"
        assert isinstance(msg.id, str) and len(msg.id) > 0
        assert msg.args == []
        assert msg.kwargs == {}
        assert msg.eta is None

    def test_naive_eta_normalized_to_utc(self):
        naive = datetime(2030, 1, 1, 12, 0, 0)
        msg = TaskMessage(task_name="test.task", eta=naive)
        assert msg.eta is not None
        assert msg.eta.tzinfo == UTC
        assert msg.eta.year == 2030

    def test_timezone_aware_eta_preserved(self):
        aware = datetime(2030, 1, 1, 12, 0, 0, tzinfo=UTC)
        msg = TaskMessage(task_name="test.task", eta=aware)
        assert msg.eta == aware


class TestSerializeValue:
    def test_primitives_returned_as_is(self):
        assert serialize_value(123) == 123
        assert serialize_value("hello") == "hello"
        assert serialize_value(3.14) == 3.14
        assert serialize_value(True) is True
        assert serialize_value(None) is None

    def test_pydantic_model_serialized_with_type_tag(self):
        item = SimpleItem(id=1, label="widget")
        serialized = serialize_value(item)
        assert serialized == {
            "__type__": "SimpleItem",
            "data": {"id": 1, "label": "widget"},
        }

    def test_nested_pydantic_model(self):
        user = User(name="Alice", age=30, address=Address(city="Berlin", country="DE"))
        serialized = serialize_value(user)
        assert serialized == {
            "__type__": "User",
            "data": {
                "name": "Alice",
                "age": 30,
                "address": {"city": "Berlin", "country": "DE"},
            },
        }

    def test_list_of_models(self):
        items = [SimpleItem(id=1, label="a"), SimpleItem(id=2, label="b")]
        serialized = serialize_value(items)
        assert serialized == [
            {"__type__": "SimpleItem", "data": {"id": 1, "label": "a"}},
            {"__type__": "SimpleItem", "data": {"id": 2, "label": "b"}},
        ]

    def test_dict_with_models(self):
        payload = {"item": SimpleItem(id=99, label="special")}
        serialized = serialize_value(payload)
        assert serialized == {
            "item": {
                "__type__": "SimpleItem",
                "data": {"id": 99, "label": "special"},
            }
        }


class TestDeserializeValue:
    def test_primitives_returned_as_is(self):
        assert deserialize_value(42, int) == 42
        assert deserialize_value("text", str) == "text"
        assert deserialize_value(None, int | None) is None

    def test_tagged_dict_deserialization_matching_annotation(self):
        data = {"__type__": "SimpleItem", "data": {"id": 10, "label": "parsed"}}
        result = deserialize_value(data, SimpleItem)
        assert isinstance(result, SimpleItem)
        assert result.id == 10
        assert result.label == "parsed"

    def test_untagged_raw_dict_deserialization_matching_annotation(self):
        data = {"id": 10, "label": "parsed"}
        result = deserialize_value(data, SimpleItem)
        assert isinstance(result, SimpleItem)
        assert result.id == 10
        assert result.label == "parsed"

    def test_any_annotation_passes_through(self):
        raw = {"k": "v", "num": 123}
        assert deserialize_value(raw, Any) == raw

    def test_none_or_missing_annotation_raises_type_error(self):
        raw = {"k": "v"}
        with pytest.raises(TypeError, match="Type annotation cannot be None or empty"):
            deserialize_value(raw, None)

        with pytest.raises(TypeError, match="Type annotation cannot be None or empty"):
            deserialize_value(raw)

    def test_typed_list_deserialization(self):
        data_list = [
            {"__type__": "SimpleItem", "data": {"id": 1, "label": "first"}},
            {"__type__": "SimpleItem", "data": {"id": 2, "label": "second"}},
        ]
        result = deserialize_value(data_list, list[SimpleItem])
        assert isinstance(result, list)
        assert len(result) == 2
        assert all(isinstance(x, SimpleItem) for x in result)
        assert result[0].id == 1
        assert result[1].id == 2

    def test_typed_dict_deserialization(self):
        data_map = {
            "first": {"__type__": "SimpleItem", "data": {"id": 1, "label": "alpha"}},
            "second": {"__type__": "SimpleItem", "data": {"id": 2, "label": "beta"}},
        }
        result = deserialize_value(data_map, dict[str, SimpleItem])
        assert isinstance(result, dict)
        assert isinstance(result["first"], SimpleItem)
        assert result["first"].label == "alpha"
        assert isinstance(result["second"], SimpleItem)

    def test_union_or_optional_deserialization(self):
        data = {"__type__": "SimpleItem", "data": {"id": 7, "label": "union"}}
        # PEP 604 Union syntax
        result = deserialize_value(data, SimpleItem | None)
        assert isinstance(result, SimpleItem)
        assert result.id == 7

        # None with optional
        assert deserialize_value(None, SimpleItem | None) is None

        # typing.Optional syntax
        result2 = deserialize_value(data, Optional[SimpleItem])  # noqa: UP045
        assert isinstance(result2, SimpleItem)
        assert result2.id == 7

    def test_union_multiple_models_disambiguation(self):
        # Both SimpleItem and Profile have the same shape: id: int, label: str
        tagged_simple = {"__type__": "SimpleItem", "data": {"id": 1, "label": "item"}}
        tagged_profile = {"__type__": "Profile", "data": {"id": 2, "label": "prof"}}

        UnionTypeAnnotation = SimpleItem | Profile | None

        res_simple = deserialize_value(tagged_simple, UnionTypeAnnotation)
        assert isinstance(res_simple, SimpleItem)
        assert res_simple.id == 1

        res_profile = deserialize_value(tagged_profile, UnionTypeAnnotation)
        assert isinstance(res_profile, Profile)
        assert res_profile.id == 2

        assert deserialize_value(None, UnionTypeAnnotation) is None

    def test_union_unknown_type_raises_type_error(self):
        tagged = {"__type__": "UnknownModel", "data": {"id": 1, "label": "test"}}
        with pytest.raises(TypeError, match="Cannot deserialize payload with __type__='UnknownModel'"):
            deserialize_value(tagged, SimpleItem | Profile | None)

    def test_union_unmatched_untagged_dict_raises_type_error(self):
        data = {"random_key": "random_val"}
        with pytest.raises(TypeError, match="Cannot deserialize untagged dict into union"):
            deserialize_value(data, SimpleItem | Profile | None)

    def test_single_model_type_mismatch_raises_type_error(self):
        tagged = {"__type__": "Profile", "data": {"id": 1, "label": "test"}}
        with pytest.raises(TypeError, match="Cannot deserialize payload with __type__='Profile' into expected model 'SimpleItem'"):
            deserialize_value(tagged, SimpleItem)


class TestSerializationRoundTrip:
    def test_model_round_trip(self):
        original = User(
            name="Bob",
            age=25,
            address=Address(city="Tokyo", country="JP"),
        )
        serialized = serialize_value(original)
        restored = deserialize_value(serialized, User)
        assert restored == original

    def test_list_of_models_round_trip(self):
        original = [
            SimpleItem(id=1, label="alpha"),
            SimpleItem(id=2, label="beta"),
        ]
        serialized = serialize_value(original)
        restored = deserialize_value(serialized, list[SimpleItem])
        assert restored == original

    def test_union_round_trip_disambiguation(self):
        item = SimpleItem(id=10, label="roundtrip")
        profile = Profile(id=20, label="prof_roundtrip")

        UnionTypeAnnotation = SimpleItem | Profile | None

        assert deserialize_value(serialize_value(item), UnionTypeAnnotation) == item
        assert deserialize_value(serialize_value(profile), UnionTypeAnnotation) == profile
        assert deserialize_value(serialize_value(None), UnionTypeAnnotation) is None

    def test_task_message_json_round_trip(self):
        user = User(
            name="Charlie",
            age=35,
            address=Address(city="Paris", country="FR"),
        )
        msg = TaskMessage(
            task_name="greet",
            args=[serialize_value(user), 42],
            kwargs={"tag": "vip"},
            eta=datetime(2030, 6, 1, 12, 0, 0, tzinfo=UTC),
        )
        json_str = msg.model_dump_json()
        restored_msg = TaskMessage.model_validate_json(json_str)

        assert restored_msg.id == msg.id
        assert restored_msg.task_name == msg.task_name
        assert restored_msg.eta == msg.eta

        restored_user = deserialize_value(restored_msg.args[0], User)
        assert restored_user == user
        assert restored_msg.args[1] == 42


class Point:
    """Non-Pydantic domain object for custom strategy testing."""

    def __init__(self, x: int, y: int) -> None:
        self.x = x
        self.y = y

    def __eq__(self, other: object) -> bool:
        return isinstance(other, Point) and self.x == other.x and self.y == other.y


class PointStrategy(BaseTypeStrategy):
    """Custom strategy for non-Pydantic Point class."""

    def can_handle(self, annotation: Any) -> bool:
        return annotation is Point

    def deserialize(
        self,
        val: Any,
        annotation: Any,
        dispatcher: Any,
    ) -> Any:
        if isinstance(val, dict) and val.get("__point__"):
            return Point(val["x"], val["y"])
        return val

    def can_serialize(self, val: Any) -> bool:
        return isinstance(val, Point)

    def serialize(
        self,
        val: Any,
        dispatcher: Any,
    ) -> Any:
        return {"__point__": True, "x": val.x, "y": val.y}


class TestCustomTypeStrategy:
    def test_custom_strategy_round_trip(self):
        dispatcher = TypeDispatcher()
        dispatcher.register_strategy(PointStrategy())

        pt = Point(10, 20)
        serialized = dispatcher.serialize(pt)
        assert serialized == {"__point__": True, "x": 10, "y": 20}

        restored = dispatcher.deserialize(serialized, Point)
        assert isinstance(restored, Point)
        assert restored == pt

    def test_custom_strategy_in_nested_list(self):
        dispatcher = TypeDispatcher()
        dispatcher.register_strategy(PointStrategy())

        pts = [Point(1, 2), Point(3, 4)]
        serialized = dispatcher.serialize(pts)
        assert serialized == [
            {"__point__": True, "x": 1, "y": 2},
            {"__point__": True, "x": 3, "y": 4},
        ]

        restored = dispatcher.deserialize(serialized, list[Point])
        assert isinstance(restored, list)
        assert len(restored) == 2
        assert all(isinstance(p, Point) for p in restored)
        assert restored == pts

    def test_custom_strategy_in_dict(self):
        dispatcher = TypeDispatcher()
        dispatcher.register_strategy(PointStrategy())

        data = {"origin": Point(0, 0), "target": Point(5, 5)}
        serialized = dispatcher.serialize(data)
        assert serialized == {
            "origin": {"__point__": True, "x": 0, "y": 0},
            "target": {"__point__": True, "x": 5, "y": 5},
        }

        restored = dispatcher.deserialize(serialized, dict[str, Point])
        assert isinstance(restored, dict)
        assert restored == data

    def test_custom_strategy_in_union_with_none(self):
        dispatcher = TypeDispatcher(custom_strategies=[PointStrategy()])

        pt = Point(7, 8)
        serialized = dispatcher.serialize(pt)
        restored = dispatcher.deserialize(serialized, Point | None)
        assert isinstance(restored, Point)
        assert restored == pt

        assert dispatcher.deserialize(None, Point | None) is None

    def test_builtin_strategies_always_available_and_prioritized(self):
        dispatcher = TypeDispatcher(custom_strategies=[PointStrategy()])

        # Built-in Pydantic model is still fully handled by PydanticModelStrategy
        item = SimpleItem(id=99, label="still_works")
        serialized = dispatcher.serialize(item)
        assert serialized == {
            "__type__": "SimpleItem",
            "data": {"id": 99, "label": "still_works"},
        }

        restored = dispatcher.deserialize(serialized, SimpleItem)
        assert isinstance(restored, SimpleItem)
        assert restored.id == 99

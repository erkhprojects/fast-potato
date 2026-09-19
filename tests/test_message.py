from datetime import UTC, datetime
from typing import Any, Optional

from pydantic import BaseModel

from fast_potato.message import (
    TaskMessage,
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

    def test_pydantic_model_serialized_to_envelope(self):
        item = SimpleItem(id=1, label="widget")
        serialized = serialize_value(item)
        assert isinstance(serialized, dict)
        assert serialized["__pydantic__"] == "SimpleItem"
        assert serialized["data"] == {"id": 1, "label": "widget"}

    def test_nested_pydantic_model(self):
        user = User(name="Alice", age=30, address=Address(city="Berlin", country="DE"))
        serialized = serialize_value(user)
        assert serialized["__pydantic__"] == "User"
        assert serialized["data"]["address"] == {"city": "Berlin", "country": "DE"}

    def test_list_of_models(self):
        items = [SimpleItem(id=1, label="a"), SimpleItem(id=2, label="b")]
        serialized = serialize_value(items)
        assert isinstance(serialized, list)
        assert len(serialized) == 2
        assert serialized[0]["__pydantic__"] == "SimpleItem"
        assert serialized[1]["__pydantic__"] == "SimpleItem"

    def test_dict_with_models(self):
        payload = {"item": SimpleItem(id=99, label="special")}
        serialized = serialize_value(payload)
        assert serialized["item"]["__pydantic__"] == "SimpleItem"


class TestDeserializeValue:
    def test_primitives_returned_as_is(self):
        assert deserialize_value(42, int) == 42
        assert deserialize_value("text", str) == "text"
        assert deserialize_value(None, int | None) is None

    def test_envelope_deserialization_matching_annotation(self):
        envelope = {"__pydantic__": "SimpleItem", "data": {"id": 10, "label": "parsed"}}
        result = deserialize_value(envelope, SimpleItem)
        assert isinstance(result, SimpleItem)
        assert result.id == 10
        assert result.label == "parsed"

    def test_envelope_deserialization_via_globals_dict_fallback(self):
        envelope = {"__pydantic__": "SimpleItem", "data": {"id": 20, "label": "fallback"}}
        result = deserialize_value(envelope, Any, globals_dict=globals())
        assert isinstance(result, SimpleItem)
        assert result.id == 20
        assert result.label == "fallback"

    def test_envelope_returns_raw_data_if_class_not_found(self):
        envelope = {"__pydantic__": "NonexistentClass", "data": {"k": "v"}}
        result = deserialize_value(envelope, Any, globals_dict={})
        assert result == {"k": "v"}

    def test_raw_dict_coerced_when_annotation_is_basemodel(self):
        raw = {"id": 5, "label": "raw_dict"}
        result = deserialize_value(raw, SimpleItem)
        assert isinstance(result, SimpleItem)
        assert result.id == 5

    def test_typed_list_deserialization(self):
        envelopes = [
            {"__pydantic__": "SimpleItem", "data": {"id": 1, "label": "first"}},
            {"__pydantic__": "SimpleItem", "data": {"id": 2, "label": "second"}},
        ]
        result = deserialize_value(envelopes, list[SimpleItem])
        assert isinstance(result, list)
        assert len(result) == 2
        assert all(isinstance(x, SimpleItem) for x in result)

    def test_union_or_optional_deserialization(self):
        envelope = {"__pydantic__": "SimpleItem", "data": {"id": 7, "label": "union"}}
        # PEP 604 Union syntax
        result = deserialize_value(envelope, SimpleItem | None)
        assert isinstance(result, SimpleItem)
        assert result.id == 7

        # typing.Optional syntax
        result2 = deserialize_value(envelope, Optional[SimpleItem])  # noqa: UP045
        assert isinstance(result2, SimpleItem)
        assert result2.id == 7

    def test_nested_untyped_structures(self):
        nested = {
            "wrapper": [
                {"__pydantic__": "SimpleItem", "data": {"id": 100, "label": "deep"}}
            ]
        }
        result = deserialize_value(nested, globals_dict=globals())
        item = result["wrapper"][0]
        assert isinstance(item, SimpleItem)
        assert item.id == 100


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

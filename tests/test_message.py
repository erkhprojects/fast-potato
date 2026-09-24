from datetime import UTC, datetime

from pydantic import BaseModel

from fast_potato.message import TaskMessage


class Address(BaseModel):
    city: str
    country: str


class User(BaseModel):
    name: str
    age: int
    address: Address


class TestTaskMessage:
    def test_default_fields(self):
        msg = TaskMessage(task_name="test.task")
        assert msg.task_name == "test.task"
        assert msg.queue == "default"
        assert isinstance(msg.id, str) and len(msg.id) > 0
        assert msg.payload is None
        assert msg.eta is None

    def test_payload_stored(self):
        msg = TaskMessage(task_name="test.task", payload={"id": 1, "label": "a"})
        assert msg.payload == {"id": 1, "label": "a"}

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


class TestTaskMessageRoundTrip:
    def test_task_message_json_round_trip(self):
        user = User(
            name="Charlie",
            age=35,
            address=Address(city="Paris", country="FR"),
        )
        msg = TaskMessage(
            task_name="greet",
            queue="users",
            payload=user.model_dump(mode="json"),
            eta=datetime(2030, 6, 1, 12, 0, 0, tzinfo=UTC),
        )
        json_str = msg.model_dump_json()
        restored_msg = TaskMessage.model_validate_json(json_str)

        assert restored_msg == msg
        assert User.model_validate(restored_msg.payload) == user

    def test_no_payload_json_round_trip(self):
        msg = TaskMessage(task_name="tick")
        restored_msg = TaskMessage.model_validate_json(msg.model_dump_json())
        assert restored_msg == msg
        assert restored_msg.payload is None

import pytest
from bson import ObjectId
from fastapi import HTTPException
from datetime import datetime, timedelta

from backend.routers.api_utils import (
    ok, json_safe, to_object_id, serialize_doc, serialize_recipe,
    serialize_history, duration_seconds
)


def test_ok_wraps_data():
    result = ok({"key": "value"})
    assert result == {"ok": True, "data": {"key": "value"}}


def test_ok_none():
    result = ok(None)
    assert result == {"ok": True, "data": None}


def test_ok_list():
    result = ok([1, 2, 3])
    assert result["ok"] is True
    assert result["data"] == [1, 2, 3]


def test_json_safe_converts_objectid():
    oid = ObjectId("aaaaaaaaaaaaaaaaaaaaaaaa")
    result = json_safe({"_id": oid})
    assert result["_id"] == "aaaaaaaaaaaaaaaaaaaaaaaa"


def test_json_safe_passthrough():
    assert json_safe("hello") == "hello"
    assert json_safe(42) == 42
    assert json_safe(None) is None


def test_to_object_id_valid():
    oid_str = "aaaaaaaaaaaaaaaaaaaaaaaa"
    result = to_object_id(oid_str)
    assert isinstance(result, ObjectId)
    assert str(result) == oid_str


def test_to_object_id_invalid_raises_422():
    with pytest.raises(HTTPException) as exc_info:
        to_object_id("not-valid")
    assert exc_info.value.status_code == 422


def test_serialize_doc_converts_id():
    oid = ObjectId("aaaaaaaaaaaaaaaaaaaaaaaa")
    doc = {"_id": oid, "name": "Test"}
    result = serialize_doc(doc)
    assert result["_id"] == "aaaaaaaaaaaaaaaaaaaaaaaa"
    assert result["name"] == "Test"


def test_serialize_doc_none():
    assert serialize_doc(None) is None


def test_serialize_recipe_sorts_steps():
    oid = ObjectId("aaaaaaaaaaaaaaaaaaaaaaaa")
    doc = {
        "_id": oid,
        "name": "Espresso",
        "steps": [
            {"order": 2, "label": "Third"},
            {"order": 0, "label": "First"},
            {"order": 1, "label": "Second"},
        ]
    }
    result = serialize_recipe(doc)
    assert [s["label"] for s in result["steps"]] == ["First", "Second", "Third"]


def test_serialize_recipe_empty_steps():
    oid = ObjectId("aaaaaaaaaaaaaaaaaaaaaaaa")
    result = serialize_recipe({"_id": oid, "name": "Empty", "steps": []})
    assert result["steps"] == []


def test_serialize_recipe_none():
    assert serialize_recipe(None) is None


def test_duration_seconds():
    start = datetime(2024, 1, 1, 10, 0, 0)
    end = datetime(2024, 1, 1, 10, 5, 30)
    result = duration_seconds({"started_at": start, "completed_at": end})
    assert result == 330.0


def test_duration_seconds_missing_fields():
    assert duration_seconds({}) is None
    assert duration_seconds({"started_at": datetime.utcnow()}) is None


def test_serialize_history_includes_duration():
    oid = ObjectId("aaaaaaaaaaaaaaaaaaaaaaaa")
    start = datetime(2024, 1, 1, 10, 0, 0)
    end = datetime(2024, 1, 1, 10, 3, 0)
    doc = {
        "_id": oid,
        "session_id": "s1",
        "user_id": "u1",
        "started_at": start,
        "completed_at": end,
    }
    result = serialize_history(doc)
    assert result["duration_seconds"] == 180.0


def test_serialize_history_none():
    assert serialize_history(None) is None

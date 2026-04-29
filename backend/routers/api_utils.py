from datetime import datetime
from typing import Any

from bson import ObjectId
from fastapi import HTTPException
from fastapi.encoders import jsonable_encoder


def ok(data: Any = None) -> dict:
    return {"ok": True, "data": json_safe(data)}


def json_safe(data: Any) -> Any:
    return jsonable_encoder(data, custom_encoder={ObjectId: str})


def to_object_id(id_str: str) -> ObjectId:
    try:
        return ObjectId(id_str)
    except Exception:
        raise HTTPException(status_code=422, detail="validation error")


def serialize_doc(doc: dict | None) -> dict | None:
    if doc is None:
        return None
    result = dict(doc)
    if "_id" in result:
        result["_id"] = str(result["_id"])
    return json_safe(result)


def serialize_recipe(doc: dict | None) -> dict | None:
    result = serialize_doc(doc)
    if result is None:
        return None
    result["steps"] = sorted(result.get("steps", []), key=lambda step: step.get("order", 0))
    return result


def duration_seconds(doc: dict) -> float | None:
    started_at = doc.get("started_at")
    completed_at = doc.get("completed_at")
    if isinstance(started_at, datetime) and isinstance(completed_at, datetime):
        return (completed_at - started_at).total_seconds()
    return None


def serialize_history(doc: dict | None) -> dict | None:
    result = serialize_doc(doc)
    if result is None:
        return None
    original_duration = duration_seconds(doc)
    result["duration_seconds"] = original_duration
    return result

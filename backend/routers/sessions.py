from datetime import datetime, timedelta
import logging

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

import backend.state as st
from backend.database import get_db
from backend.models.history import HistoryModel
from backend.models.session import BrewSessionModel, SessionCreate
from backend.models.user import UserPublic
from backend.routers.api_utils import ok, serialize_doc, serialize_recipe, to_object_id
from backend.routers.auth import get_current_user

router = APIRouter()
logger = logging.getLogger(__name__)


class SelectRecipeBody(BaseModel):
    recipe_id: str


class DeviceDisplayBody(BaseModel):
    esp_id: str = "ESP32_BAR_01"
    line1: str | None = None
    line2: str | None = None
    line3: str | None = None


async def _active_session_for_user(user_id: str) -> dict | None:
    db = get_db()
    return await db.brew_sessions.find_one({"user_id": user_id, "status": "active"})


async def _resumable_session_for_user(user_id: str) -> dict | None:
    db = get_db()
    cutoff = datetime.utcnow() - timedelta(minutes=10)
    return await db.brew_sessions.find_one(
        {
            "user_id": user_id,
            "status": "abandoned",
            "completed_at": {"$gte": cutoff},
        },
        sort=[("completed_at", -1)],
    )


async def _abandon_active_sessions_for_user(user_id: str, reason: str) -> int:
    from backend.routers.ws import _abandon_session

    db = get_db()
    cursor = db.brew_sessions.find({"user_id": user_id, "status": "active"})
    count = 0
    async for session_doc in cursor:
        session_id = str(session_doc["_id"])
        try:
            await _abandon_session(session_id, reason)
            count += 1
        except Exception:
            logger.exception("Failed to abandon active session %s", session_id)
    return count


async def _active_recipe(recipe_id: str) -> dict | None:
    db = get_db()
    return await db.recipes.find_one({"_id": to_object_id(recipe_id), "active": True})


async def _send_display_status(
    esp_id: str,
    line1: str,
    line2: str = "",
    line3: str = "",
) -> None:
    from backend.routers.ws import _send

    await _send(st.esp_sockets.get(esp_id), {
        "event": "display_status",
        "line1": line1[:21],
        "line2": line2[:21],
        "line3": line3[:21],
    })


def _sync_entry_from_session(session_id: str, session_doc: dict, user: UserPublic) -> None:
    entry = st.sessions.get(session_id)
    if entry:
        entry.recipe_id = session_doc["recipe_id"]
        entry.current_step = session_doc.get("current_step", 0)
        entry.last_seen = session_doc.get("last_seen", datetime.utcnow())
    else:
        st.sessions[session_id] = st.SessionEntry(
            esp_id=session_doc["esp_id"],
            user={"id": user.id, "name": user.name, "role": user.role},
            recipe_id=session_doc["recipe_id"],
            current_step=session_doc.get("current_step", 0),
            last_seen=session_doc.get("last_seen", datetime.utcnow()),
        )
    st.esp_registry[session_doc["esp_id"]] = session_id


async def _write_history(session_id: str, session_doc: dict, user: UserPublic) -> None:
    db = get_db()
    existing = await db.history.find_one({"session_id": session_id})
    if existing:
        return
    recipe_doc = await db.recipes.find_one({"_id": to_object_id(session_doc["recipe_id"])})
    completed_at = datetime.utcnow()
    history = HistoryModel(
        session_id=session_id,
        user_id=session_doc["user_id"],
        recipe_id=session_doc["recipe_id"],
        recipe_name=recipe_doc["name"] if recipe_doc else "Unknown",
        worker_name=user.name,
        cooked_by_admin=user.role == "admin",
        started_at=session_doc["started_at"],
        completed_at=completed_at,
    )
    await db.history.insert_one(history.model_dump(by_alias=True, exclude_none=True))


async def _notify_complete(session_id: str, session_doc: dict) -> None:
    from backend.routers.ws import _send

    entry = st.sessions.get(session_id)
    esp_id = entry.esp_id if entry else session_doc.get("esp_id")
    if entry:
        await _send(entry.browser_ws, {"event": "session_complete"})
    await _send(st.esp_sockets.get(esp_id), {"event": "session_complete"})
    if esp_id:
        st.esp_registry.pop(esp_id, None)
    st.sessions.pop(session_id, None)


@router.post("/select-recipe")
async def select_recipe(
    body: SelectRecipeBody,
    user: UserPublic = Depends(get_current_user),
):
    db = get_db()
    session_doc = await _active_session_for_user(user.id)
    if not session_doc:
        raise HTTPException(status_code=404, detail="No active session")
    recipe_doc = await _active_recipe(body.recipe_id)
    if not recipe_doc:
        raise HTTPException(status_code=404, detail="Recipe not found")

    session_id = str(session_doc["_id"])
    now = datetime.utcnow()
    await db.brew_sessions.update_one(
        {"_id": session_doc["_id"]},
        {"$set": {"recipe_id": body.recipe_id, "current_step": 0, "last_seen": now}},
    )
    session_doc["recipe_id"] = body.recipe_id
    session_doc["current_step"] = 0
    session_doc["last_seen"] = now
    _sync_entry_from_session(session_id, session_doc, user)
    return ok({"session_id": session_id, "recipe": serialize_recipe(recipe_doc)})


@router.post("/display-status")
async def display_status(
    body: DeviceDisplayBody,
    user: UserPublic = Depends(get_current_user),
):
    await _send_display_status(
        body.esp_id,
        body.line1 or "Worker logged in",
        body.line2 if body.line2 is not None else user.name,
        body.line3 if body.line3 is not None else "Choose recipe",
    )
    return ok({"status": "sent", "esp_online": body.esp_id in st.esp_sockets})


@router.get("/current")
async def get_current_session(user: UserPublic = Depends(get_current_user)):
    db = get_db()
    session_doc = await _active_session_for_user(user.id)
    if not session_doc:
        session_doc = await _resumable_session_for_user(user.id)
        if session_doc:
            now = datetime.utcnow()
            await db.brew_sessions.update_one(
                {"_id": session_doc["_id"]},
                {
                    "$set": {"status": "active", "last_seen": now},
                    "$unset": {"completed_at": ""},
                },
            )
            session_doc["status"] = "active"
            session_doc["last_seen"] = now
            session_doc.pop("completed_at", None)
            _sync_entry_from_session(str(session_doc["_id"]), session_doc, user)
        else:
            return ok({
                "session": None,
                "recipe": None,
                "resume_available": False,
            })

    recipe_doc = await db.recipes.find_one({"_id": to_object_id(session_doc["recipe_id"])})
    abandoned = await _resumable_session_for_user(user.id)
    return ok({
        "session": serialize_doc(session_doc),
        "recipe": serialize_recipe(recipe_doc),
        "resume_available": abandoned is not None,
    })


@router.patch("/current/heartbeat")
async def heartbeat(user: UserPublic = Depends(get_current_user)):
    db = get_db()
    now = datetime.utcnow()
    result = await db.brew_sessions.find_one_and_update(
        {"user_id": user.id, "status": "active"},
        {"$set": {"last_seen": now}},
    )
    if not result:
        raise HTTPException(status_code=404, detail="No active session")
    session_id = str(result["_id"])
    if session_id in st.sessions:
        st.sessions[session_id].last_seen = now
    return ok({"ok": True})


@router.post("/current/discard")
async def discard_current_session(user: UserPublic = Depends(get_current_user)):
    count = await _abandon_active_sessions_for_user(user.id, "discarded")
    if count == 0:
        raise HTTPException(status_code=404, detail="No active session")
    return ok({"status": "discarded", "discarded_count": count})


@router.post("/current/drop")
async def drop_current_session(user: UserPublic = Depends(get_current_user)):
    count = await _abandon_active_sessions_for_user(user.id, "dropped")
    if count == 0:
        raise HTTPException(status_code=404, detail="No active session")
    return ok({"status": "abandoned", "dropped_count": count})


@router.post("/current/ping-close")
async def ping_close(request: Request):
    return ok({"status": "closed"})


@router.post("", status_code=201)
async def create_session(
    body: SessionCreate,
    user: UserPublic = Depends(get_current_user),
):
    db = get_db()
    logger.info(
        "Create session requested: user_id=%s user_name=%s recipe_id=%s esp_id=%s",
        user.id,
        user.name,
        body.recipe_id,
        body.esp_id,
    )

    recipe_doc = await _active_recipe(body.recipe_id)
    if not recipe_doc:
        logger.warning("Create session failed: recipe not found recipe_id=%s", body.recipe_id)
        raise HTTPException(status_code=404, detail="Recipe not found")

    await _abandon_active_sessions_for_user(user.id, "replaced")

    session = BrewSessionModel(
        user_id=user.id,
        recipe_id=body.recipe_id,
        esp_id=body.esp_id,
    )
    doc = session.model_dump(by_alias=True, exclude_none=True)
    result = await db.brew_sessions.insert_one(doc)
    session_id = str(result.inserted_id)

    entry = st.SessionEntry(
        esp_id=body.esp_id,
        user={"id": user.id, "name": user.name, "role": user.role},
        recipe_id=body.recipe_id,
        current_step=0,
        last_seen=datetime.utcnow(),
    )
    st.sessions[session_id] = entry
    st.esp_registry[body.esp_id] = session_id
    logger.info(
        "Session created: session_id=%s user_id=%s recipe_id=%s esp_id=%s esp_socket=%s",
        session_id,
        user.id,
        body.recipe_id,
        body.esp_id,
        body.esp_id in st.esp_sockets,
    )
    await _send_display_status(body.esp_id, "Brew session", "Started", recipe_doc["name"])

    return ok({"session_id": session_id})


@router.post("/{session_id}/complete")
async def complete_session(
    session_id: str,
    user: UserPublic = Depends(get_current_user),
):
    db = get_db()
    session_doc = await db.brew_sessions.find_one({"_id": to_object_id(session_id)})
    if not session_doc:
        raise HTTPException(status_code=404, detail="Session not found")
    if user.role != "admin" and session_doc["user_id"] != user.id:
        raise HTTPException(status_code=403, detail="Access denied")

    now = datetime.utcnow()
    await db.brew_sessions.update_one(
        {"_id": ObjectId(session_id)},
        {"$set": {"status": "completed", "completed_at": now}},
    )
    session_doc["completed_at"] = now
    session_doc["status"] = "completed"
    await _write_history(session_id, session_doc, user)
    await _notify_complete(session_id, session_doc)
    return ok(None)

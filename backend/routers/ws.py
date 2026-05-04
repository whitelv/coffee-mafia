import asyncio
import json
import logging
from datetime import datetime, timedelta

import numpy as np
from bson import ObjectId
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from fastapi.encoders import jsonable_encoder

import backend.state as st
from backend.config import settings
from backend.database import get_db
from backend.models.history import HistoryModel
from backend.routers.auth import create_jwt, decode_jwt

logger = logging.getLogger(__name__)
router = APIRouter()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _send(ws: WebSocket | None, payload: dict) -> None:
    if ws is None:
        logger.warning("WebSocket send skipped; no socket for payload event=%s", payload.get("event"))
        return
    try:
        encoded = jsonable_encoder(payload, custom_encoder={ObjectId: str})
        await ws.send_text(json.dumps(encoded))
        logger.debug("WebSocket sent event=%s", payload.get("event"))
    except Exception:
        logger.exception("WebSocket send failed for event=%s", payload.get("event"))


async def _abandon_session(session_id: str, reason: str = "timeout") -> None:
    entry = st.sessions.get(session_id)
    db = get_db()
    session_doc = await db.brew_sessions.find_one({"_id": ObjectId(session_id)})
    if entry is None and session_doc is None:
        return

    now = datetime.utcnow()
    status = "discarded" if reason == "discarded" else "abandoned"
    await db.brew_sessions.update_one(
        {"_id": ObjectId(session_id)},
        {"$set": {"status": status, "completed_at": now, "abandon_reason": reason}},
    )

    esp_id = entry.esp_id if entry else session_doc.get("esp_id")
    browser_ws = entry.browser_ws if entry else None

    await _send(browser_ws, {"event": "session_abandoned"})
    esp_ws = st.esp_sockets.get(esp_id)
    await _send(esp_ws, {"event": "session_abandoned"})
    if esp_id:
        st.esp_registry.pop(esp_id, None)
    st.sessions.pop(session_id, None)


async def stale_session_watchdog() -> None:
    while True:
        await asyncio.sleep(60)
        now = datetime.utcnow()
        cutoff = now - timedelta(seconds=60)
        db = get_db()
        cursor = db.brew_sessions.find({
            "status": "active",
            "last_seen": {"$lt": cutoff},
        })
        async for doc in cursor:
            session_id = str(doc["_id"])
            logger.info("Abandoning stale session %s", session_id)
            await _abandon_session(session_id, "timeout")


def _check_weight_stable(entry: st.SessionEntry) -> bool:
    window = entry.weight_window
    if len(window) < 10:
        return False
    if entry.weight_target is None or entry.weight_tolerance is None:
        return False
    arr = np.array(list(window), dtype=float)
    latest = arr[-1]
    return (
        float(np.std(arr)) < settings.esp_weight_stable_stddev
        and abs(latest - entry.weight_target) <= entry.weight_tolerance
    )


def _step_display_lines(step: dict | None) -> tuple[str, str, str]:
    if not step:
        return ("Brew session", "No step", "")

    step_type = step.get("type", "")
    label = str(step.get("label") or step_type or "Step")

    if step_type == "weight":
        target = step.get("target_value")
        line3 = f"Target: {target}g" if target is not None else ""
        return ("Weight step", label, line3)
    if step_type == "timer":
        seconds = step.get("target_value")
        line3 = f"Timer: {seconds}s" if seconds is not None else ""
        return ("Timer step", label, line3)
    if step_type == "instruction":
        text = str(step.get("instruction_text") or "")
        return ("Instruction", label, text)
    return ("Brew step", label, "")


async def _send_display_status(
    esp_id: str | None,
    line1: str,
    line2: str = "",
    line3: str = "",
) -> None:
    if not esp_id:
        return
    esp_ws = st.esp_sockets.get(esp_id)
    await _send(esp_ws, {
        "event": "display_status",
        "line1": line1[:21],
        "line2": line2[:21],
        "line3": line3[:21],
    })


async def _sync_esp_display_to_step(entry: st.SessionEntry, recipe_data: dict | None) -> None:
    if not recipe_data:
        return
    steps = recipe_data.get("steps", [])
    if entry.current_step >= len(steps):
        return
    line1, line2, line3 = _step_display_lines(steps[entry.current_step])
    await _send_display_status(entry.esp_id, line1, line2, line3)


async def _complete_session(session_id: str, entry: st.SessionEntry) -> None:
    db = get_db()
    now = datetime.utcnow()
    session_doc = await db.brew_sessions.find_one({"_id": ObjectId(session_id)})
    await db.brew_sessions.update_one(
        {"_id": ObjectId(session_id)},
        {"$set": {"status": "completed", "completed_at": now}},
    )
    if session_doc:
        recipe_doc = await db.recipes.find_one({"_id": ObjectId(entry.recipe_id)})
        history = HistoryModel(
            session_id=session_id,
            user_id=entry.user["id"],
            recipe_id=entry.recipe_id,
            recipe_name=recipe_doc["name"] if recipe_doc else "Unknown",
            worker_name=entry.user["name"],
            cooked_by_admin=entry.user.get("role") == "admin",
            started_at=session_doc["started_at"],
            completed_at=now,
        )
        await db.history.insert_one(
            history.model_dump(by_alias=True, exclude_none=True)
        )
    await _send(entry.browser_ws, {"event": "session_complete"})
    esp_ws = st.esp_sockets.get(entry.esp_id)
    await _send(esp_ws, {"event": "session_complete"})
    st.esp_registry.pop(entry.esp_id, None)
    st.sessions.pop(session_id, None)


# ---------------------------------------------------------------------------
# ESP32 WebSocket endpoint
# ---------------------------------------------------------------------------

@router.websocket("/ws/esp/{esp_id}")
async def esp_websocket(websocket: WebSocket, esp_id: str) -> None:
    await websocket.accept()
    st.esp_sockets[esp_id] = websocket
    logger.info("ESP32 connected: %s", esp_id)

    # Notify browser if a session is active for this esp
    session_id = st.esp_registry.get(esp_id)
    if session_id and session_id in st.sessions:
        await _send(st.sessions[session_id].browser_ws, {"event": "esp_reconnected"})

    try:
        while True:
            raw = await websocket.receive_text()
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                continue
            event = msg.get("event")

            if event == "rfid_scan":
                await _handle_rfid_scan(esp_id, msg)
            elif event == "weight_reading":
                await _handle_weight_reading(esp_id, msg)
            elif event == "heartbeat":
                await _handle_heartbeat(esp_id)
            elif event == "tare_done":
                await _handle_tare_done(esp_id)

    except WebSocketDisconnect:
        pass
    finally:
        st.esp_sockets.pop(esp_id, None)
        logger.info("ESP32 disconnected: %s", esp_id)
        session_id = st.esp_registry.get(esp_id)
        if session_id and session_id in st.sessions:
            await _send(st.sessions[session_id].browser_ws, {"event": "esp_disconnected"})


async def _handle_rfid_scan(esp_id: str, msg: dict) -> None:
    uid = msg.get("uid", "")
    db = get_db()
    esp_ws = st.esp_sockets.get(esp_id)
    logger.info("RFID scan received: esp_id=%s uid=%s esp_socket=%s", esp_id, uid, esp_ws is not None)

    user_doc = await db.users.find_one({"rfid_uid": uid})
    if not user_doc:
        logger.warning("RFID auth failed: unknown card uid=%s", uid)
        await _send(esp_ws, {"event": "auth_fail", "reason": "unknown_card"})
        return

    user = {
        "id": str(user_doc["_id"]),
        "name": user_doc["name"],
        "role": user_doc["role"],
    }

    # Check for resumable abandoned session (last 10 minutes)
    cutoff = datetime.utcnow() - timedelta(minutes=10)
    abandoned = await db.brew_sessions.find_one({
        "user_id": user["id"],
        "status": "abandoned",
        "completed_at": {"$gte": cutoff},
    })
    resume_available = abandoned is not None

    token = create_jwt(user["id"], user["name"], user["role"])
    st.pending_auth[esp_id] = st.PendingAuth(
        token=token,
        user=user,
        session_id=str(abandoned["_id"]) if abandoned else None,
        resume_available=resume_available,
    )
    logger.info(
        "RFID auth ok: esp_id=%s uid=%s user_id=%s name=%s",
        esp_id,
        uid,
        user["id"],
        user["name"],
    )
    await _send(esp_ws, {
        "event": "auth_ok",
        "token": token,
        "user": {"name": user["name"], "role": user["role"]},
        "resume_available": resume_available,
    })


async def _handle_weight_reading(esp_id: str, msg: dict) -> None:
    session_id = st.esp_registry.get(esp_id)
    if not session_id:
        return
    entry = st.sessions.get(session_id)
    if not entry or not entry.weight_streaming:
        return

    try:
        value = float(msg.get("value", 0))
    except (TypeError, ValueError):
        return
    entry.weight_window.append(value)

    if _check_weight_stable(entry):
        entry.weight_streaming = False
        esp_ws = st.esp_sockets.get(esp_id)
        await _send(esp_ws, {"event": "stop_weight"})
        await _send(entry.browser_ws, {"event": "weight_stable", "value": round(value, 1)})
    else:
        await _send(
            entry.browser_ws,
            {"event": "weight_update", "value": round(value, 1), "stable": False},
        )


async def _handle_tare_done(esp_id: str) -> None:
    session_id = st.esp_registry.get(esp_id)
    if not session_id:
        return
    entry = st.sessions.get(session_id)
    if not entry:
        return
    await _send(entry.browser_ws, {"event": "tare_done"})


async def _handle_heartbeat(esp_id: str) -> None:
    session_id = st.esp_registry.get(esp_id)
    if not session_id:
        return
    entry = st.sessions.get(session_id)
    if not entry:
        return
    entry.last_seen = datetime.utcnow()
    db = get_db()
    await db.brew_sessions.update_one(
        {"_id": ObjectId(session_id)},
        {"$set": {"last_seen": entry.last_seen}},
    )


# ---------------------------------------------------------------------------
# Browser WebSocket endpoint
# ---------------------------------------------------------------------------

async def _browser_websocket_handler(
    websocket: WebSocket,
    session_id: str,
    token: str,
) -> None:
    await websocket.accept()

    try:
        claims = decode_jwt(token)
    except Exception:
        await websocket.close(code=4001, reason="unauthorized")
        return

    entry = st.sessions.get(session_id)

    if entry is None:
        db = get_db()
        try:
            object_id = ObjectId(session_id)
        except Exception:
            await websocket.close(code=4004, reason="session not found")
            return
        session_doc = await db.brew_sessions.find_one({
            "_id": object_id,
            "status": "active",
        })
        if not session_doc:
            await websocket.close(code=4004, reason="session not found")
            return
        entry = st.SessionEntry(
            esp_id=session_doc.get("esp_id"),
            user={"id": claims["sub"], "name": claims.get("name", ""), "role": claims["role"]},
            recipe_id=session_doc.get("recipe_id"),
            current_step=session_doc.get("current_step", 0),
            last_seen=session_doc.get("last_seen", datetime.utcnow()),
        )
        st.sessions[session_id] = entry
        if entry.esp_id:
            st.esp_registry[entry.esp_id] = session_id

    entry.browser_ws = websocket
    logger.info("Browser connected to session %s", session_id)

    if entry.esp_id in st.esp_sockets:
        await _send(websocket, {"event": "esp_reconnected"})

    db = get_db()
    recipe_doc = await db.recipes.find_one({"_id": ObjectId(entry.recipe_id)})
    recipe_data = None
    if recipe_doc:
        recipe_doc["_id"] = str(recipe_doc["_id"])
        recipe_data = recipe_doc

    await _send(websocket, {
        "event": "session_state",
        "status": "active",
        "current_step": entry.current_step,
        "recipe": recipe_data,
    })
    await _sync_esp_display_to_step(entry, recipe_data)

    try:
        while True:
            raw = await websocket.receive_text()
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                continue
            event = msg.get("event")

            if event == "start_weight":
                await _handle_start_weight(session_id, entry, msg, recipe_data)
            elif event == "next_step":
                await _handle_next_step(session_id, entry, recipe_data)
            elif event == "tare_scale":
                await _handle_tare_scale(entry)
            elif event == "ping":
                await _send(websocket, {"event": "pong"})

    except WebSocketDisconnect:
        pass
    finally:
        if st.sessions.get(session_id):
            st.sessions[session_id].browser_ws = None
        logger.info("Browser disconnected from session %s", session_id)


@router.websocket("/ws/browser/{session_id}")
async def browser_websocket(websocket: WebSocket, session_id: str, token: str = "") -> None:
    await _browser_websocket_handler(websocket, session_id, token)


@router.websocket("/ws/session/{session_id}")
async def browser_websocket_legacy(websocket: WebSocket, session_id: str, token: str = "") -> None:
    await websocket.accept()
    try:
        decode_jwt(token)
        logger.warning("Legacy browser WebSocket quarantined: session=%s", session_id)
    except Exception:
        logger.warning("Legacy browser WebSocket quarantined with invalid token: session=%s", session_id)
    try:
        while True:
            await asyncio.sleep(3600)
    except WebSocketDisconnect:
        pass
    finally:
        logger.debug("Legacy browser WebSocket disconnected: session=%s", session_id)


async def _handle_start_weight(
    session_id: str,
    entry: st.SessionEntry,
    msg: dict,
    recipe_data: dict | None,
) -> None:
    if not recipe_data:
        return
    steps = recipe_data.get("steps", [])
    if entry.current_step >= len(steps):
        return
    step = steps[entry.current_step]
    if step.get("type") != "weight":
        return
    try:
        target = float(msg.get("target"))
    except (TypeError, ValueError):
        target = step.get("target_value")
    if target is None:
        return

    entry.weight_target = target
    entry.weight_tolerance = step.get("tolerance")
    entry.weight_streaming = True
    entry.weight_window.clear()
    esp_ws = st.esp_sockets.get(entry.esp_id)
    await _send(esp_ws, {"event": "request_weight", "target": target})
    await _sync_esp_display_to_step(entry, recipe_data)


async def _handle_next_step(
    session_id: str,
    entry: st.SessionEntry,
    recipe_data: dict | None,
) -> None:
    if not recipe_data:
        return
    steps = recipe_data.get("steps", [])
    entry.current_step += 1
    entry.weight_streaming = False
    entry.weight_window.clear()
    entry.weight_target = None
    entry.weight_tolerance = None

    esp_ws = st.esp_sockets.get(entry.esp_id)
    await _send(esp_ws, {"event": "stop_weight"})

    db = get_db()
    await db.brew_sessions.update_one(
        {"_id": ObjectId(session_id)},
        {"$set": {"current_step": entry.current_step}},
    )

    if entry.current_step >= len(steps):
        await _complete_session(session_id, entry)
    else:
        next_step = steps[entry.current_step]
        await _send(entry.browser_ws, {
            "event": "step_advance",
            "step_index": entry.current_step,
            "step": next_step,
        })
        await _sync_esp_display_to_step(entry, recipe_data)


async def _handle_tare_scale(entry: st.SessionEntry) -> None:
    esp_ws = st.esp_sockets.get(entry.esp_id)
    await _send(esp_ws, {"event": "tare_scale"})

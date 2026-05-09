import pytest
from unittest.mock import AsyncMock, MagicMock
from bson import ObjectId
from datetime import datetime

import backend.state as st


def _recipe_doc(oid=None):
    oid = oid or ObjectId("cccccccccccccccccccccccc")
    return {"_id": oid, "name": "Espresso", "active": True, "steps": []}


def _session_doc(user_id="aaaaaaaaaaaaaaaaaaaaaaaa"):
    return {
        "_id": ObjectId("bbbbbbbbbbbbbbbbbbbbbbbb"),
        "user_id": user_id,
        "recipe_id": "cccccccccccccccccccccccc",
        "esp_id": "ESP32_BAR_01",
        "status": "active",
        "current_step": 0,
        "last_seen": datetime.utcnow(),
        "started_at": datetime.utcnow(),
    }


@pytest.mark.asyncio
async def test_create_session_no_auth(app_client):
    response = await app_client.post("/api/sessions", json={"recipe_id": "r1", "esp_id": "e1"})
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_create_session_recipe_not_found(app_client, mock_db, client_token):
    mock_db.recipes.find_one = AsyncMock(return_value=None)

    class EmptyCursor:
        def __aiter__(self): return self
        async def __anext__(self): raise StopAsyncIteration

    mock_db.brew_sessions.find = MagicMock(return_value=EmptyCursor())
    mock_db.brew_sessions.find_one = AsyncMock(return_value=None)

    payload = {"recipe_id": "aaaaaaaaaaaaaaaaaaaaaaaa", "esp_id": "ESP32_BAR_01"}
    response = await app_client.post("/api/sessions", json=payload, headers={"Authorization": f"Bearer {client_token}"})
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_create_session_success(app_client, mock_db, client_token):
    recipe = _recipe_doc()
    mock_db.recipes.find_one = AsyncMock(return_value=recipe)

    class EmptyCursor:
        def __aiter__(self): return self
        async def __anext__(self): raise StopAsyncIteration

    mock_db.brew_sessions.find = MagicMock(return_value=EmptyCursor())
    new_oid = ObjectId("dddddddddddddddddddddddd")
    mock_db.brew_sessions.insert_one = AsyncMock(return_value=MagicMock(inserted_id=new_oid))

    st.esp_sockets.clear()
    payload = {"recipe_id": str(recipe["_id"]), "esp_id": "ESP32_BAR_01"}
    response = await app_client.post("/api/sessions", json=payload, headers={"Authorization": f"Bearer {client_token}"})
    assert response.status_code == 201
    data = response.json()
    assert data["ok"] is True
    assert "session_id" in data["data"]
    st.sessions.pop(str(new_oid), None)
    st.esp_registry.pop("ESP32_BAR_01", None)


@pytest.mark.asyncio
async def test_get_current_session_no_session(app_client, mock_db, client_token):
    mock_db.brew_sessions.find_one = AsyncMock(return_value=None)
    response = await app_client.get("/api/sessions/current", headers={"Authorization": f"Bearer {client_token}"})
    assert response.status_code == 200
    data = response.json()
    assert data["data"]["session"] is None


@pytest.mark.asyncio
async def test_heartbeat_no_session(app_client, mock_db, client_token):
    mock_db.brew_sessions.find_one_and_update = AsyncMock(return_value=None)
    response = await app_client.patch("/api/sessions/current/heartbeat", headers={"Authorization": f"Bearer {client_token}"})
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_heartbeat_success(app_client, mock_db, client_token):
    session = _session_doc()
    mock_db.brew_sessions.find_one_and_update = AsyncMock(return_value=session)
    response = await app_client.patch("/api/sessions/current/heartbeat", headers={"Authorization": f"Bearer {client_token}"})
    assert response.status_code == 200
    assert response.json()["ok"] is True


@pytest.mark.asyncio
async def test_discard_no_session(app_client, mock_db, client_token):
    class EmptyCursor:
        def __aiter__(self): return self
        async def __anext__(self): raise StopAsyncIteration

    mock_db.brew_sessions.find = MagicMock(return_value=EmptyCursor())
    response = await app_client.post("/api/sessions/current/discard", headers={"Authorization": f"Bearer {client_token}"})
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_ping_close_always_ok(app_client, client_token):
    response = await app_client.post("/api/sessions/current/ping-close", headers={"Authorization": f"Bearer {client_token}"})
    assert response.status_code == 200
    assert response.json()["data"]["status"] == "closed"

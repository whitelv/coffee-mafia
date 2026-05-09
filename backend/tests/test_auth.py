import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timedelta
from fastapi import HTTPException
from httpx import AsyncClient, ASGITransport

from backend.routers.auth import create_jwt, decode_jwt
from backend.config import settings


# --- Pure function tests ---

def test_create_jwt_returns_string():
    token = create_jwt("user123", "Alice", "client")
    assert isinstance(token, str)
    assert len(token) > 0


def test_decode_jwt_valid():
    token = create_jwt("user123", "Alice", "client")
    payload = decode_jwt(token)
    assert payload["sub"] == "user123"
    assert payload["name"] == "Alice"
    assert payload["role"] == "client"


def test_decode_jwt_invalid_raises_401():
    with pytest.raises(HTTPException) as exc_info:
        decode_jwt("not.a.valid.token")
    assert exc_info.value.status_code == 401


def test_decode_jwt_tampered_raises_401():
    token = create_jwt("user123", "Alice", "client")
    tampered = token[:-5] + "XXXXX"
    with pytest.raises(HTTPException) as exc_info:
        decode_jwt(tampered)
    assert exc_info.value.status_code == 401


def test_jwt_contains_expiry():
    token = create_jwt("user123", "Alice", "admin")
    payload = decode_jwt(token)
    assert "exp" in payload
    exp = datetime.utcfromtimestamp(payload["exp"])
    assert exp > datetime.utcnow()


def test_jwt_admin_role():
    token = create_jwt("admin1", "Boss", "admin")
    payload = decode_jwt(token)
    assert payload["role"] == "admin"


# --- Auth router endpoint tests ---

@pytest.mark.asyncio
async def test_auth_status_esp_offline(app_client):
    import backend.state as st
    st.esp_sockets.clear()
    st.pending_auth.clear()
    response = await app_client.get("/auth/status?esp_id=ESP_UNKNOWN")
    assert response.status_code == 200
    assert response.json()["status"] == "esp_offline"


@pytest.mark.asyncio
async def test_auth_status_waiting_when_esp_connected(app_client):
    import backend.state as st
    from unittest.mock import MagicMock
    st.pending_auth.clear()
    st.esp_sockets["ESP32_BAR_01"] = MagicMock()
    response = await app_client.get("/auth/status?esp_id=ESP32_BAR_01")
    assert response.status_code == 200
    assert response.json()["status"] == "waiting"
    del st.esp_sockets["ESP32_BAR_01"]


@pytest.mark.asyncio
async def test_auth_status_returns_authenticated_when_pending(app_client):
    import backend.state as st
    from datetime import datetime, timedelta
    token = create_jwt("user1", "Alice", "client")
    st.pending_auth["ESP32_BAR_01"] = st.PendingAuth(
        token=token,
        user={"id": "user1", "name": "Alice", "role": "client"},
        session_id=None,
        resume_available=False,
        expires_at=datetime.utcnow() + timedelta(seconds=30),
    )
    response = await app_client.get("/auth/status?esp_id=ESP32_BAR_01")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "authenticated"
    assert data["token"] == token


@pytest.mark.asyncio
async def test_rfid_scan_unknown_user(app_client, mock_db):
    mock_db.users.find_one = AsyncMock(return_value=None)
    response = await app_client.post("/auth/rfid", json={"rfid_uid": "UNKNOWN", "esp_id": "ESP32_BAR_01"})
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_rfid_scan_known_user(app_client, mock_db):
    from bson import ObjectId
    user_doc = {
        "_id": ObjectId("aaaaaaaaaaaaaaaaaaaaaaaa"),
        "rfid_uid": "AABBCCDD",
        "name": "Alice",
        "role": "client",
    }
    mock_db.users.find_one = AsyncMock(side_effect=[user_doc, None])
    mock_db.brew_sessions.find_one = AsyncMock(return_value=None)
    response = await app_client.post("/auth/rfid", json={"rfid_uid": "AABBCCDD", "esp_id": "ESP32_BAR_01"})
    assert response.status_code == 200
    data = response.json()
    assert "token" in data
    assert data["resume_available"] is False

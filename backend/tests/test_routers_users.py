import pytest
from unittest.mock import AsyncMock, MagicMock
from bson import ObjectId


def _user_doc(uid="aaaaaaaaaaaaaaaaaaaaaaaa", rfid="AABBCCDD", name="Alice", role="client"):
    return {"_id": ObjectId(uid), "rfid_uid": rfid, "name": name, "role": role}


@pytest.mark.asyncio
async def test_list_users_requires_admin(app_client, client_token):
    response = await app_client.get("/api/users", headers={"Authorization": f"Bearer {client_token}"})
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_list_users_as_admin(app_client, mock_db, admin_token):
    doc = _user_doc()

    class OneCursor:
        def __init__(self): self._done = False
        def sort(self, *a, **kw): return self
        def __aiter__(self): return self
        async def __anext__(self):
            if not self._done:
                self._done = True
                return doc
            raise StopAsyncIteration

    mock_db.users.find = MagicMock(return_value=OneCursor())
    response = await app_client.get("/api/users", headers={"Authorization": f"Bearer {admin_token}"})
    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert len(data["data"]) == 1


@pytest.mark.asyncio
async def test_create_user_requires_admin(app_client, client_token):
    payload = {"rfid_uid": "AABBCCDD", "name": "Alice", "role": "client"}
    response = await app_client.post("/api/users", json=payload, headers={"Authorization": f"Bearer {client_token}"})
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_create_user_duplicate_rfid(app_client, mock_db, admin_token):
    mock_db.users.find_one = AsyncMock(return_value=_user_doc())
    payload = {"rfid_uid": "AABBCCDD", "name": "Alice", "role": "client"}
    response = await app_client.post("/api/users", json=payload, headers={"Authorization": f"Bearer {admin_token}"})
    assert response.status_code == 409


@pytest.mark.asyncio
async def test_create_user_success(app_client, mock_db, admin_token):
    oid = ObjectId("aaaaaaaaaaaaaaaaaaaaaaaa")
    new_doc = _user_doc()
    mock_db.users.find_one = AsyncMock(side_effect=[None, new_doc])
    mock_db.users.insert_one = AsyncMock(return_value=MagicMock(inserted_id=oid))
    payload = {"rfid_uid": "AABBCCDD", "name": "Alice", "role": "client"}
    response = await app_client.post("/api/users", json=payload, headers={"Authorization": f"Bearer {admin_token}"})
    assert response.status_code == 201
    assert response.json()["data"]["name"] == "Alice"


@pytest.mark.asyncio
async def test_update_user_requires_admin(app_client, client_token):
    oid = "aaaaaaaaaaaaaaaaaaaaaaaa"
    payload = {"name": "Bob", "rfid_uid": "BBCC", "role": "client"}
    response = await app_client.put(f"/api/users/{oid}", json=payload, headers={"Authorization": f"Bearer {client_token}"})
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_update_user_not_found(app_client, mock_db, admin_token):
    mock_db.users.find_one = AsyncMock(return_value=None)
    mock_db.users.find_one_and_update = AsyncMock(return_value=None)
    oid = "aaaaaaaaaaaaaaaaaaaaaaaa"
    payload = {"name": "Bob", "rfid_uid": "BBCC", "role": "client"}
    response = await app_client.put(f"/api/users/{oid}", json=payload, headers={"Authorization": f"Bearer {admin_token}"})
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_delete_user_requires_admin(app_client, client_token):
    oid = "aaaaaaaaaaaaaaaaaaaaaaaa"
    response = await app_client.delete(f"/api/users/{oid}", headers={"Authorization": f"Bearer {client_token}"})
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_delete_user_not_found(app_client, mock_db, admin_token):
    mock_db.users.find_one = AsyncMock(return_value=None)
    oid = "aaaaaaaaaaaaaaaaaaaaaaaa"
    response = await app_client.delete(f"/api/users/{oid}", headers={"Authorization": f"Bearer {admin_token}"})
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_delete_user_success(app_client, mock_db, admin_token):
    oid = ObjectId("aaaaaaaaaaaaaaaaaaaaaaaa")
    user_doc = _user_doc()
    mock_db.users.find_one = AsyncMock(return_value=user_doc)
    mock_db.users.delete_one = AsyncMock(return_value=MagicMock(deleted_count=1))

    class EmptyCursor:
        def __aiter__(self): return self
        async def __anext__(self): raise StopAsyncIteration

    mock_db.brew_sessions.find = MagicMock(return_value=EmptyCursor())
    response = await app_client.delete(f"/api/users/{str(oid)}", headers={"Authorization": f"Bearer {admin_token}"})
    assert response.status_code == 200
    assert response.json()["ok"] is True

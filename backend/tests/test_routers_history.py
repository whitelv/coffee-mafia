import pytest
from unittest.mock import AsyncMock, MagicMock
from bson import ObjectId
from datetime import datetime


def _history_doc(user_id="aaaaaaaaaaaaaaaaaaaaaaaa", session_id="s1"):
    return {
        "_id": ObjectId("eeeeeeeeeeeeeeeeeeeeeeee"),
        "session_id": session_id,
        "user_id": user_id,
        "recipe_id": "r1",
        "recipe_name": "Espresso",
        "worker_name": "Alice",
        "cooked_by_admin": False,
        "started_at": datetime(2024, 1, 1, 10, 0, 0),
        "completed_at": datetime(2024, 1, 1, 10, 5, 0),
    }


@pytest.mark.asyncio
async def test_list_history_requires_auth(app_client):
    response = await app_client.get("/api/history")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_my_history_empty(app_client, mock_db, client_token):
    class EmptyCursor:
        def sort(self, *a, **kw): return self
        def skip(self, *a): return self
        def limit(self, *a): return self
        def __aiter__(self): return self
        async def __anext__(self): raise StopAsyncIteration

    mock_db.history.find = MagicMock(return_value=EmptyCursor())
    mock_db.history.count_documents = AsyncMock(return_value=0)
    response = await app_client.get("/api/history/me", headers={"Authorization": f"Bearer {client_token}"})
    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert data["data"]["items"] == []
    assert data["data"]["total"] == 0


@pytest.mark.asyncio
async def test_my_history_with_entries(app_client, mock_db, client_token):
    doc = _history_doc()

    class OneItemCursor:
        def __init__(self): self._done = False
        def sort(self, *a, **kw): return self
        def skip(self, *a): return self
        def limit(self, *a): return self
        def __aiter__(self): return self
        async def __anext__(self):
            if not self._done:
                self._done = True
                return doc
            raise StopAsyncIteration

    mock_db.history.find = MagicMock(return_value=OneItemCursor())
    mock_db.history.count_documents = AsyncMock(return_value=1)
    response = await app_client.get("/api/history/me", headers={"Authorization": f"Bearer {client_token}"})
    assert response.status_code == 200
    data = response.json()
    assert data["data"]["total"] == 1
    assert data["data"]["items"][0]["recipe_name"] == "Espresso"


@pytest.mark.asyncio
async def test_all_history_requires_admin(app_client, client_token):
    response = await app_client.get("/api/history/all", headers={"Authorization": f"Bearer {client_token}"})
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_all_history_as_admin(app_client, mock_db, admin_token):
    class EmptyCursor:
        def sort(self, *a, **kw): return self
        def skip(self, *a): return self
        def limit(self, *a): return self
        def __aiter__(self): return self
        async def __anext__(self): raise StopAsyncIteration

    mock_db.history.find = MagicMock(return_value=EmptyCursor())
    mock_db.history.count_documents = AsyncMock(return_value=0)
    response = await app_client.get("/api/history/all", headers={"Authorization": f"Bearer {admin_token}"})
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_get_history_entry_not_found(app_client, mock_db, client_token):
    mock_db.history.find_one = AsyncMock(return_value=None)
    response = await app_client.get("/api/history/s1", headers={"Authorization": f"Bearer {client_token}"})
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_history_entry_access_denied(app_client, mock_db, client_token):
    doc = _history_doc(user_id="different_user_id_here_xx")
    mock_db.history.find_one = AsyncMock(return_value=doc)
    response = await app_client.get("/api/history/s1", headers={"Authorization": f"Bearer {client_token}"})
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_get_history_entry_own(app_client, mock_db, client_token):
    doc = _history_doc(user_id="aaaaaaaaaaaaaaaaaaaaaaaa")
    mock_db.history.find_one = AsyncMock(return_value=doc)
    response = await app_client.get("/api/history/s1", headers={"Authorization": f"Bearer {client_token}"})
    assert response.status_code == 200
    assert response.json()["data"]["recipe_name"] == "Espresso"


@pytest.mark.asyncio
async def test_get_history_entry_admin_any(app_client, mock_db, admin_token):
    doc = _history_doc(user_id="some_other_user_id_xxxxx")
    mock_db.history.find_one = AsyncMock(return_value=doc)
    response = await app_client.get("/api/history/s1", headers={"Authorization": f"Bearer {admin_token}"})
    assert response.status_code == 200

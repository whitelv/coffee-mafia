import pytest
from unittest.mock import AsyncMock, MagicMock
from bson import ObjectId

from backend.routers.recipes import _steps_with_order, RecipeStepBody


# --- Pure function tests ---

def test_steps_with_order_assigns_index():
    steps = [
        RecipeStepBody(type="instruction", label="Start", instruction_text="Begin"),
        RecipeStepBody(type="timer", label="Wait", target_value=30.0),
    ]
    result = _steps_with_order(steps)
    assert result[0]["order"] == 0
    assert result[1]["order"] == 1


def test_steps_with_order_excludes_none_fields():
    steps = [RecipeStepBody(type="instruction", label="Note", instruction_text="Do this")]
    result = _steps_with_order(steps)
    assert "target_value" not in result[0]
    assert "tolerance" not in result[0]


def test_steps_with_order_empty():
    assert _steps_with_order([]) == []


# --- Router endpoint tests ---

@pytest.mark.asyncio
async def test_list_recipes_requires_auth(app_client):
    response = await app_client.get("/api/recipes")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_list_recipes_returns_ok(app_client, mock_db, client_token):
    oid = ObjectId("aaaaaaaaaaaaaaaaaaaaaaaa")
    recipe_doc = {"_id": oid, "name": "Espresso", "active": True, "steps": []}

    class AsyncCursor:
        def __init__(self): self._done = False
        def sort(self, *a, **kw): return self
        def __aiter__(self): return self
        async def __anext__(self):
            if not self._done:
                self._done = True
                return recipe_doc
            raise StopAsyncIteration

    mock_db.recipes.find = MagicMock(return_value=AsyncCursor())
    response = await app_client.get("/api/recipes", headers={"Authorization": f"Bearer {client_token}"})
    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert len(data["data"]) == 1


@pytest.mark.asyncio
async def test_get_recipe_not_found(app_client, client_token):
    oid = "aaaaaaaaaaaaaaaaaaaaaaaa"
    response = await app_client.get(f"/api/recipes/{oid}", headers={"Authorization": f"Bearer {client_token}"})
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_recipe_found(app_client, mock_db, client_token):
    oid = ObjectId("aaaaaaaaaaaaaaaaaaaaaaaa")
    recipe_doc = {"_id": oid, "name": "Latte", "active": True, "steps": []}
    mock_db.recipes.find_one = AsyncMock(return_value=recipe_doc)
    response = await app_client.get(f"/api/recipes/{str(oid)}", headers={"Authorization": f"Bearer {client_token}"})
    assert response.status_code == 200
    assert response.json()["data"]["name"] == "Latte"


@pytest.mark.asyncio
async def test_create_recipe_requires_admin(app_client, client_token):
    payload = {
        "name": "New Recipe",
        "description": "Desc",
        "steps": [{"type": "instruction", "label": "Step", "instruction_text": "Do it"}]
    }
    response = await app_client.post("/api/recipes", json=payload, headers={"Authorization": f"Bearer {client_token}"})
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_create_recipe_as_admin(app_client, mock_db, admin_token):
    oid = ObjectId("aaaaaaaaaaaaaaaaaaaaaaaa")
    created_doc = {"_id": oid, "name": "New Recipe", "active": True, "steps": [{"order": 0, "type": "instruction", "label": "Step", "instruction_text": "Do it"}]}
    mock_db.recipes.insert_one = AsyncMock(return_value=MagicMock(inserted_id=oid))
    mock_db.recipes.find_one = AsyncMock(return_value=created_doc)
    payload = {
        "name": "New Recipe",
        "description": "Desc",
        "steps": [{"type": "instruction", "label": "Step", "instruction_text": "Do it"}]
    }
    response = await app_client.post("/api/recipes", json=payload, headers={"Authorization": f"Bearer {admin_token}"})
    assert response.status_code == 201
    assert response.json()["data"]["name"] == "New Recipe"


@pytest.mark.asyncio
async def test_delete_recipe_requires_admin(app_client, client_token):
    oid = "aaaaaaaaaaaaaaaaaaaaaaaa"
    response = await app_client.delete(f"/api/recipes/{oid}", headers={"Authorization": f"Bearer {client_token}"})
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_delete_recipe_not_found(app_client, mock_db, admin_token):
    from unittest.mock import MagicMock
    mock_db.recipes.update_one = AsyncMock(return_value=MagicMock(matched_count=0))
    oid = "aaaaaaaaaaaaaaaaaaaaaaaa"
    response = await app_client.delete(f"/api/recipes/{oid}", headers={"Authorization": f"Bearer {admin_token}"})
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_delete_recipe_success(app_client, mock_db, admin_token):
    from unittest.mock import MagicMock
    mock_db.recipes.update_one = AsyncMock(return_value=MagicMock(matched_count=1))
    oid = "aaaaaaaaaaaaaaaaaaaaaaaa"
    response = await app_client.delete(f"/api/recipes/{oid}", headers={"Authorization": f"Bearer {admin_token}"})
    assert response.status_code == 200
    assert response.json()["ok"] is True

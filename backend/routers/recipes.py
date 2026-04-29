from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, model_validator
from pymongo import ReturnDocument

from backend.database import get_db
from backend.models.recipe import RecipeModel
from backend.models.user import UserPublic
from backend.routers.api_utils import ok, serialize_recipe, to_object_id
from backend.routers.auth import get_current_user, require_admin

router = APIRouter()


class RecipeStepBody(BaseModel):
    type: Literal["weight", "timer", "instruction"]
    label: str
    target_value: float | None = None
    tolerance: float | None = None
    instruction_text: str | None = None

    @model_validator(mode="after")
    def validate_step_fields(self) -> "RecipeStepBody":
        if self.type == "weight":
            if self.target_value is None or self.tolerance is None:
                raise ValueError("Weight steps require target_value and tolerance")
        elif self.type == "timer":
            if self.target_value is None:
                raise ValueError("Timer steps require target_value")
        elif self.type == "instruction":
            if not self.instruction_text:
                raise ValueError("Instruction steps require instruction_text")
        return self


class RecipeCreateBody(BaseModel):
    name: str
    description: str
    steps: list[RecipeStepBody]


class RecipeUpdateBody(BaseModel):
    name: str
    description: str


class RecipeStepsBody(BaseModel):
    steps: list[RecipeStepBody]


def _steps_with_order(steps: list[RecipeStepBody]) -> list[dict]:
    return [
        {"order": index, **step.model_dump(exclude_none=True)}
        for index, step in enumerate(steps)
    ]


@router.get("")
async def list_recipes(_: UserPublic = Depends(get_current_user)):
    db = get_db()
    cursor = db.recipes.find({"active": True}).sort("name", 1)
    recipes = [serialize_recipe(doc) async for doc in cursor]
    return ok(recipes)


@router.get("/{recipe_id}")
async def get_recipe(recipe_id: str, _: UserPublic = Depends(get_current_user)):
    db = get_db()
    doc = await db.recipes.find_one({"_id": to_object_id(recipe_id), "active": True})
    if not doc:
        raise HTTPException(status_code=404, detail="Recipe not found")
    return ok(serialize_recipe(doc))


@router.post("", status_code=201)
async def create_recipe(body: RecipeCreateBody, _: UserPublic = Depends(require_admin)):
    db = get_db()
    recipe = RecipeModel(
        name=body.name,
        description=body.description,
        steps=_steps_with_order(body.steps),
    )
    doc = recipe.model_dump(by_alias=True, exclude_none=True)
    result = await db.recipes.insert_one(doc)
    created = await db.recipes.find_one({"_id": result.inserted_id})
    return ok(serialize_recipe(created))


@router.put("/{recipe_id}")
async def update_recipe(
    recipe_id: str,
    body: RecipeUpdateBody,
    _: UserPublic = Depends(require_admin),
):
    db = get_db()
    result = await db.recipes.find_one_and_update(
        {"_id": to_object_id(recipe_id), "active": True},
        {"$set": {"name": body.name, "description": body.description}},
        return_document=ReturnDocument.AFTER,
    )
    if not result:
        raise HTTPException(status_code=404, detail="Recipe not found")
    return ok(serialize_recipe(result))


@router.put("/{recipe_id}/steps")
async def replace_recipe_steps(
    recipe_id: str,
    body: RecipeStepsBody,
    _: UserPublic = Depends(require_admin),
):
    db = get_db()
    result = await db.recipes.find_one_and_update(
        {"_id": to_object_id(recipe_id), "active": True},
        {"$set": {"steps": _steps_with_order(body.steps)}},
        return_document=ReturnDocument.AFTER,
    )
    if not result:
        raise HTTPException(status_code=404, detail="Recipe not found")
    return ok(serialize_recipe(result))


@router.delete("/{recipe_id}")
async def delete_recipe(recipe_id: str, _: UserPublic = Depends(require_admin)):
    db = get_db()
    result = await db.recipes.update_one(
        {"_id": to_object_id(recipe_id), "active": True},
        {"$set": {"active": False}},
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Recipe not found")
    return ok(None)

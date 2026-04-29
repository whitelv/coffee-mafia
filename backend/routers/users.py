from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from pymongo import ReturnDocument

from backend.database import get_db
from backend.models.user import UserCreate, UserModel
from backend.routers.api_utils import ok, serialize_doc, to_object_id
from backend.routers.auth import require_admin

router = APIRouter()


class UserUpdateBody(BaseModel):
    name: str
    rfid_uid: str
    role: Literal["client", "admin"]


def _public_user(doc: dict) -> dict:
    return serialize_doc(doc)


@router.get("")
async def list_users(_ = Depends(require_admin)):
    db = get_db()
    cursor = db.users.find().sort("name", 1)
    users = [_public_user(doc) async for doc in cursor]
    return ok(users)


@router.post("", status_code=201)
async def create_user(body: UserCreate, _ = Depends(require_admin)):
    db = get_db()
    existing = await db.users.find_one({"rfid_uid": body.rfid_uid})
    if existing:
        raise HTTPException(status_code=409, detail="RFID UID already registered")
    user = UserModel(rfid_uid=body.rfid_uid, name=body.name, role=body.role)
    doc = user.model_dump(by_alias=True, exclude_none=True)
    result = await db.users.insert_one(doc)
    created = await db.users.find_one({"_id": result.inserted_id})
    return ok(_public_user(created))


@router.put("/{user_id}")
async def update_user(
    user_id: str,
    body: UserUpdateBody,
    _ = Depends(require_admin),
):
    db = get_db()
    user_oid = to_object_id(user_id)
    existing = await db.users.find_one({
        "rfid_uid": body.rfid_uid,
        "_id": {"$ne": user_oid},
    })
    if existing:
        raise HTTPException(status_code=409, detail="RFID UID already registered")
    result = await db.users.find_one_and_update(
        {"_id": user_oid},
        {"$set": {"name": body.name, "rfid_uid": body.rfid_uid, "role": body.role}},
        return_document=ReturnDocument.AFTER,
    )
    if not result:
        raise HTTPException(status_code=404, detail="User not found")
    return ok(_public_user(result))


@router.delete("/{user_id}")
async def delete_user(user_id: str, _ = Depends(require_admin)):
    db = get_db()
    user_oid = to_object_id(user_id)
    user_doc = await db.users.find_one({"_id": user_oid})
    if not user_doc:
        raise HTTPException(status_code=404, detail="User not found")

    cursor = db.brew_sessions.find({"user_id": user_id, "status": "active"})
    from backend.routers.ws import _abandon_session

    async for session_doc in cursor:
        await _abandon_session(str(session_doc["_id"]), "user_deleted")

    await db.users.delete_one({"_id": user_oid})
    return ok(None)

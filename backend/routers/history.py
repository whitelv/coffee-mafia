from fastapi import APIRouter, Depends, HTTPException, Query

from backend.database import get_db
from backend.models.user import UserPublic
from backend.routers.api_utils import ok, serialize_history
from backend.routers.auth import get_current_user, require_admin

router = APIRouter()


async def _history_page(query: dict, page: int, limit: int) -> dict:
    db = get_db()
    skip = (page - 1) * limit
    cursor = db.history.find(query).sort("started_at", -1).skip(skip).limit(limit)
    total = await db.history.count_documents(query)
    items = [serialize_history(doc) async for doc in cursor]
    return {"items": items, "page": page, "limit": limit, "total": total}


@router.get("/me")
async def my_history(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    user: UserPublic = Depends(get_current_user),
):
    return ok(await _history_page({"user_id": user.id}, page, limit))


@router.get("/all")
async def all_history(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    user_id: str | None = None,
    _: UserPublic = Depends(require_admin),
):
    query = {"user_id": user_id} if user_id else {}
    return ok(await _history_page(query, page, limit))


@router.get("")
async def list_history(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    user: UserPublic = Depends(get_current_user),
):
    query = {} if user.role == "admin" else {"user_id": user.id}
    return ok(await _history_page(query, page, limit))


@router.get("/{session_id}")
async def get_history_entry(
    session_id: str,
    user: UserPublic = Depends(get_current_user),
):
    db = get_db()
    doc = await db.history.find_one({"session_id": session_id})
    if not doc:
        raise HTTPException(status_code=404, detail="History entry not found")
    if user.role != "admin" and doc.get("user_id") != user.id:
        raise HTTPException(status_code=403, detail="Access denied")
    return ok(serialize_history(doc))

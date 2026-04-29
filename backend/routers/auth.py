from datetime import datetime, timedelta

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from pydantic import BaseModel

import state as st
from config import settings
from database import get_db
from models.user import UserPublic

router = APIRouter()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/token", auto_error=False)


def create_jwt(user_id: str, name: str, role: str) -> str:
    payload = {
        "sub": user_id,
        "name": name,
        "role": role,
        "exp": datetime.utcnow() + timedelta(hours=settings.jwt_expire_hours),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_jwt(token: str) -> dict:
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")


async def get_current_user(token: str = Depends(oauth2_scheme)) -> UserPublic:
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    claims = decode_jwt(token)
    return UserPublic(id=claims["sub"], name=claims["name"], role=claims["role"])


async def require_admin(user: UserPublic = Depends(get_current_user)) -> UserPublic:
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


class RfidScanBody(BaseModel):
    rfid_uid: str
    esp_id: str


@router.post("/rfid")
async def rfid_scan(body: RfidScanBody):
    """Simulate an RFID scan — used for testing without hardware."""
    db = get_db()
    user_doc = await db.users.find_one({"rfid_uid": body.rfid_uid})
    if not user_doc:
        raise HTTPException(status_code=404, detail="Unknown RFID card")

    user_id = str(user_doc["_id"])
    user = {"id": user_id, "name": user_doc["name"], "role": user_doc["role"]}

    cutoff = datetime.utcnow() - timedelta(minutes=10)
    abandoned = await db.brew_sessions.find_one({
        "user_id": user_id,
        "status": "abandoned",
        "completed_at": {"$gte": cutoff},
    })
    resume_available = abandoned is not None

    token = create_jwt(user_id, user_doc["name"], user_doc["role"])
    st.pending_auth[body.esp_id] = st.PendingAuth(
        token=token,
        user=user,
        session_id=str(abandoned["_id"]) if abandoned else None,
        resume_available=resume_available,
    )
    return {"status": "ok", "token": token, "user": user, "resume_available": resume_available}


@router.get("/status")
async def auth_status(esp_id: str = Query(...)):
    # Check pending auth first — valid whether ESP is connected or not (covers /rfid test endpoint)
    pending = st.pending_auth.get(esp_id)
    if pending is not None:
        if pending.expires_at <= datetime.utcnow():
            del st.pending_auth[esp_id]
            if esp_id not in st.esp_sockets:
                return {"status": "esp_offline"}
            return {"status": "waiting"}
        del st.pending_auth[esp_id]
        return {
            "status": "authenticated",
            "token": pending.token,
            "user": pending.user,
            "resume_available": pending.resume_available,
        }
    if esp_id not in st.esp_sockets:
        return {"status": "esp_offline"}
    return {"status": "waiting"}

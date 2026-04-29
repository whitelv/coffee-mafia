from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from backend.config import settings

_client: AsyncIOMotorClient | None = None
_db: AsyncIOMotorDatabase | None = None


async def connect_db() -> None:
    global _client, _db
    _client = AsyncIOMotorClient(settings.mongodb_uri)
    _db = _client[settings.db_name]
    await _create_indexes()


async def close_db() -> None:
    global _client
    if _client:
        _client.close()
        _client = None


def get_db() -> AsyncIOMotorDatabase:
    if _db is None:
        raise RuntimeError("Database not connected")
    return _db


async def _create_indexes() -> None:
    db = get_db()
    await db.users.create_index("rfid_uid", unique=True)
    await db.brew_sessions.create_index([("status", 1), ("last_seen", 1)])
    await db.brew_sessions.create_index("user_id")
    await db.history.create_index("user_id")
    await db.history.create_index([("started_at", -1)])

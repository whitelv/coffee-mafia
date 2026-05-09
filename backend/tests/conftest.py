import os
import sys
import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from httpx import AsyncClient, ASGITransport

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

os.environ.setdefault("MONGODB_URI", "mongodb://localhost:27017")
os.environ.setdefault("JWT_SECRET", "test-secret")
os.environ.setdefault("DB_NAME", "test_coffeedb")

from backend.config import settings
settings.jwt_secret = "test-secret"

from backend.routers.auth import create_jwt


def make_token(user_id: str = "aaaaaaaaaaaaaaaaaaaaaaaa", name: str = "Test User", role: str = "client") -> str:
    return create_jwt(user_id, name, role)


def make_admin_token(user_id: str = "bbbbbbbbbbbbbbbbbbbbbbbb") -> str:
    return create_jwt(user_id, "Admin User", "admin")


@pytest.fixture
def client_token() -> str:
    return make_token()


@pytest.fixture
def admin_token() -> str:
    return make_admin_token()


def _async_cursor(docs):
    class _Cursor:
        def __init__(self, items):
            self._items = iter(items)
        def sort(self, *a, **kw): return self
        def skip(self, *a): return self
        def limit(self, *a): return self
        def __aiter__(self): return self
        async def __anext__(self):
            try:
                return next(self._items)
            except StopIteration:
                raise StopAsyncIteration
    return _Cursor(docs)


@pytest.fixture
def mock_db():
    db = MagicMock()
    db.users = _mock_collection()
    db.recipes = _mock_collection()
    db.brew_sessions = _mock_collection()
    db.history = _mock_collection()
    db.command = AsyncMock(return_value={"ok": 1})
    return db


def _mock_collection():
    col = MagicMock()
    col.find_one = AsyncMock(return_value=None)
    col.find = MagicMock(return_value=_async_cursor([]))
    col.insert_one = AsyncMock(return_value=MagicMock(inserted_id="000000000000000000000001"))
    col.update_one = AsyncMock(return_value=MagicMock(matched_count=1, modified_count=1))
    col.find_one_and_update = AsyncMock(return_value=None)
    col.count_documents = AsyncMock(return_value=0)
    col.delete_one = AsyncMock(return_value=MagicMock(deleted_count=1))
    col.create_index = AsyncMock(return_value=None)
    return col


@pytest_asyncio.fixture
async def app_client(mock_db):
    from backend.main import app
    # Patch get_db in all router modules that call it directly
    patches = [
        patch("backend.database.get_db", return_value=mock_db),
        patch("backend.routers.auth.get_db", return_value=mock_db),
        patch("backend.routers.sessions.get_db", return_value=mock_db),
        patch("backend.routers.recipes.get_db", return_value=mock_db),
        patch("backend.routers.history.get_db", return_value=mock_db),
        patch("backend.routers.users.get_db", return_value=mock_db),
        patch("backend.routers.ws.get_db", return_value=mock_db),
    ]
    for p in patches:
        p.start()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    for p in patches:
        p.stop()

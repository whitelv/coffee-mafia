import asyncio
import logging
import os
import sys
import traceback
from contextlib import asynccontextmanager

sys.path.append(os.path.dirname(__file__))

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.encoders import jsonable_encoder
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from database import close_db, connect_db, get_db
from routers import auth, history, recipes, sessions, users, ws
import state as st

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        await connect_db()
        db = get_db()
        await db.command("ping")
        user_count = await db.users.count_documents({})
        recipe_count = await db.recipes.count_documents({})
    except Exception:
        logger.exception("Database startup validation failed")
        await close_db()
        sys.exit(1)

    logger.info("MongoDB connected")
    logger.info("Startup data loaded: users=%s recipes=%s", user_count, recipe_count)
    logger.info("WebSocket hub initialized")
    logger.info("Server started successfully")

    watchdog_task = asyncio.create_task(ws.stale_session_watchdog())
    yield
    watchdog_task.cancel()
    try:
        await watchdog_task
    except asyncio.CancelledError:
        pass
    await close_db()


app = FastAPI(title="Coffee Bar API", version="1.0.0", lifespan=lifespan)


def _is_api_request(request: Request) -> bool:
    return request.url.path.startswith("/api/")


def _error_text(status_code: int, detail=None) -> str:
    if status_code == 401:
        return "unauthorized"
    if status_code == 403:
        return "forbidden"
    if status_code == 404:
        return "not found"
    if status_code == 422:
        return "validation error"
    if isinstance(detail, str):
        return detail
    return "error"


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    if not _is_api_request(request):
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
    payload = {"ok": False, "error": _error_text(exc.status_code, exc.detail)}
    if exc.status_code == 422 and exc.detail:
        payload["detail"] = exc.detail
    return JSONResponse(status_code=exc.status_code, content=payload)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    detail = jsonable_encoder(exc.errors())
    if not _is_api_request(request):
        return JSONResponse(status_code=422, content={"detail": detail})
    return JSONResponse(
        status_code=422,
        content={"ok": False, "error": "validation error", "detail": detail},
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.error("Unhandled exception:\n%s", traceback.format_exc())
    if not _is_api_request(request):
        return JSONResponse(status_code=500, content={"detail": "Internal Server Error"})
    return JSONResponse(
        status_code=500,
        content={"ok": False, "error": "internal server error"},
    )

origins = os.getenv("ALLOWED_ORIGINS", "*").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/auth", tags=["auth"])
app.include_router(recipes.router, prefix="/api/recipes", tags=["recipes"])
app.include_router(sessions.router, prefix="/api/sessions", tags=["sessions"])
app.include_router(history.router, prefix="/api/history", tags=["history"])
app.include_router(users.router, prefix="/api/users", tags=["users"])
app.include_router(ws.router, tags=["websocket"])


@app.get("/health", tags=["health"])
async def health():
    try:
        await get_db().command("ping")
    except Exception:
        logger.exception("Health check database ping failed")
        return {
            "ok": False,
            "db": "disconnected",
            "sessions_active": 0,
            "esp_connected": 0,
        }

    return {
        "ok": True,
        "db": "connected",
        "sessions_active": len(st.sessions),
        "esp_connected": len(st.esp_sockets),
    }

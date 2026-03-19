import time
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from backend.config import get_settings
from backend.utils.logging import setup_logging, get_logger
from backend.db.app_db import init_db, close_db, db_status
from backend.utils.redis_client import connect_redis, disconnect_redis
from backend.connectors.registry import ConnectorRegistry

settings = get_settings()
setup_logging()
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("raxus_starting", env=settings.app_env)
    await init_db()
    await connect_redis()
    await ConnectorRegistry.load_from_app_db()
    from backend.monitoring.metrics import metrics_collector
    await metrics_collector.start()
    logger.info("raxus_ready")
    yield
    from backend.monitoring.metrics import metrics_collector
    await metrics_collector.stop()
    await ConnectorRegistry.close_all()
    await disconnect_redis()
    await close_db()


app = FastAPI(
    title="Raxus API", version="1.0.0",
    description="Unified Intelligent Data Platform",
    docs_url="/docs" if not settings.is_production else None,
    redoc_url=None, lifespan=lifespan,
)

app.add_middleware(CORSMiddleware,
    allow_origins=settings.app_cors_origins,
    allow_credentials=True, allow_methods=["*"], allow_headers=["*"],
)

from backend.middleware.security import SecurityMiddleware
app.add_middleware(SecurityMiddleware)


@app.middleware("http")
async def request_middleware(request: Request, call_next):
    import uuid
    request_id = str(uuid.uuid4())[:8]
    request.state.request_id = request_id
    start = time.perf_counter()
    response = await call_next(request)
    ms = round((time.perf_counter() - start) * 1000)
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Response-Time"] = f"{ms}ms"
    return response


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    rid = getattr(request.state, "request_id", "unknown")
    logger.error("unhandled_exception", error=str(exc), exc_info=True)
    return JSONResponse(status_code=500, content={
        "type": "https://raxus.io/errors/internal", "title": "Internal Server Error",
        "status": 500, "detail": str(exc) if settings.app_debug else "Unexpected error.",
        "request_id": rid,
    })


from backend.routers import connections, query, monitoring, audit, tasks, chat, auth, servers, users
app.include_router(auth.router,        prefix="/auth",        tags=["Auth"])
app.include_router(users.router,       prefix="/users",       tags=["Users"])
app.include_router(connections.router, prefix="/connections",  tags=["Connections"])
app.include_router(query.router,       prefix="/query",        tags=["Query"])
app.include_router(monitoring.router,  prefix="/monitoring",   tags=["Monitoring"])
app.include_router(audit.router,       prefix="/audit",        tags=["Audit"])
app.include_router(tasks.router,       prefix="/tasks",        tags=["Tasks"])
app.include_router(chat.router,        prefix="/chat",         tags=["Chat"])
app.include_router(servers.router,     prefix="/agents",       tags=["Agents"])


@app.get("/health", tags=["System"])
async def health():
    from backend.utils.redis_client import get_redis_status
    mysql_ok = await db_status()
    redis_ok = await get_redis_status()
    return {
        "status": "healthy" if mysql_ok and redis_ok else "degraded",
        "version": "1.0.0",
        "services": {"mysql_app": "up" if mysql_ok else "down", "redis": "up" if redis_ok else "down"},
        "db_connectors": ConnectorRegistry.get_health_summary(),
    }


@app.get("/", include_in_schema=False)
async def root():
    return {"name": "Raxus", "version": "1.0.0"}

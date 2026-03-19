import redis.asyncio as aioredis
from backend.config import get_settings
from backend.utils.logging import get_logger

logger = get_logger(__name__)
_redis: aioredis.Redis | None = None


async def connect_redis():
    global _redis
    settings = get_settings()
    _redis = aioredis.from_url(
        settings.redis_url,
        encoding="utf-8",
        decode_responses=True,
        socket_connect_timeout=5,
        socket_timeout=5,
        retry_on_timeout=True,
    )
    await _redis.ping()
    logger.info("redis_connected")


async def disconnect_redis():
    global _redis
    if _redis:
        await _redis.aclose()
        logger.info("redis_disconnected")


async def get_redis_status() -> bool:
    try:
        await _redis.ping()
        return True
    except Exception:
        return False


def get_redis() -> aioredis.Redis:
    if _redis is None:
        raise RuntimeError("Redis not connected")
    return _redis

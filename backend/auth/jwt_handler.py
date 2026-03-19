"""JWT Handler — access + refresh tokens, blacklist Redis"""
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict

import jwt
from backend.config import get_settings
from backend.utils.redis_client import get_redis
from backend.utils.logging import get_logger

logger = get_logger(__name__)
settings = get_settings()

ALGORITHM = "HS256"
ACCESS_EXPIRE_MIN = settings.jwt_access_token_expire_minutes
REFRESH_EXPIRE_DAYS = settings.jwt_refresh_token_expire_days


def create_access_token(user: Dict) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user["id"],
        "username": user.get("username", ""),
        "role": user.get("role", "viewer"),
        "jti": str(uuid.uuid4()),
        "type": "access",
        "iat": now,
        "exp": now + timedelta(minutes=ACCESS_EXPIRE_MIN),
    }
    return jwt.encode(payload, settings.app_secret_key, algorithm=ALGORITHM)


async def create_refresh_token(user: Dict, long_lived: bool = False) -> str:
    now = datetime.now(timezone.utc)
    days = REFRESH_EXPIRE_DAYS * 3 if long_lived else REFRESH_EXPIRE_DAYS
    jti = str(uuid.uuid4())
    payload = {
        "sub": user["id"],
        "username": user.get("username", ""),
        "role": user.get("role", "viewer"),
        "jti": jti,
        "type": "refresh",
        "iat": now,
        "exp": now + timedelta(days=days),
    }
    token = jwt.encode(payload, settings.app_secret_key, algorithm=ALGORITHM)
    # Store jti in Redis for validation
    redis = get_redis()
    await redis.setex(f"refresh:{jti}", days * 86400, user["id"])
    return token


async def verify_token(token: str, token_type: str = "access") -> Optional[Dict]:
    try:
        payload = jwt.decode(token, settings.app_secret_key, algorithms=[ALGORITHM])
        if payload.get("type") != token_type:
            return None
        jti = payload.get("jti", "")
        redis = get_redis()
        # Check blacklist
        if await redis.exists(f"blacklist:{jti}"):
            return None
        # For refresh tokens, verify jti exists
        if token_type == "refresh":
            if not await redis.exists(f"refresh:{jti}"):
                return None
        return payload
    except jwt.ExpiredSignatureError:
        logger.debug("token_expired")
        return None
    except jwt.InvalidTokenError as e:
        logger.debug("token_invalid", error=str(e))
        return None


async def revoke_token(token: str):
    try:
        payload = jwt.decode(token, settings.app_secret_key, algorithms=[ALGORITHM],
                             options={"verify_exp": False})
        jti = payload.get("jti", "")
        if jti:
            redis = get_redis()
            exp = payload.get("exp", 0)
            ttl = max(exp - int(datetime.now(timezone.utc).timestamp()), 1)
            await redis.setex(f"blacklist:{jti}", ttl, "1")
            await redis.delete(f"refresh:{jti}")
    except Exception as e:
        logger.error("revoke_token_error", error=str(e))

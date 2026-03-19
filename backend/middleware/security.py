"""
Middleware de sécurité Raxus
- Rate limiting par IP (Redis sliding window)
- Rate limiting par utilisateur authentifié
- Injection de l'audit log automatique
- Détection basique de patterns suspects
"""
import time
import json
from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from backend.utils.logging import get_logger

logger = get_logger(__name__)

# Routes exemptées du rate limiting
EXEMPT_PATHS = {"/health", "/docs", "/openapi.json", "/redoc"}

# Limites (requêtes / fenêtre)
RATE_IP_LIMIT = 200          # 200 req / min par IP anonyme
RATE_USER_LIMIT = 1000       # 1000 req / min par user authentifié
RATE_WINDOW = 60             # fenêtre glissante en secondes

# Patterns suspects dans les headers/params (heuristique simple, pas AST)
SUSPICIOUS_PATTERNS = [
    "' OR '1'='1", "'; DROP", "UNION SELECT", "EXEC(",
    "<script>", "javascript:", "eval(",
]


class SecurityMiddleware(BaseHTTPMiddleware):

    async def dispatch(self, request: Request, call_next):
        path = request.url.path

        # Exempt certaines routes
        if path in EXEMPT_PATHS or path.startswith("/docs"):
            return await call_next(request)

        client_ip = request.client.host if request.client else "unknown"
        start = time.perf_counter()

        # ── Rate limiting ─────────────────────────────────────
        rl_result = await self._check_rate_limit(request, client_ip)
        if rl_result:
            return rl_result

        # ── Heuristic security check ──────────────────────────
        sec_result = self._check_suspicious(request)
        if sec_result:
            logger.warning("suspicious_request", ip=client_ip, path=path)
            return sec_result

        # ── Process request ───────────────────────────────────
        response = await call_next(request)
        duration_ms = round((time.perf_counter() - start) * 1000)

        # ── Auto audit log for mutating operations ─────────────
        if request.method in ("POST", "PUT", "PATCH", "DELETE") and response.status_code < 500:
            await self._write_audit(request, response, duration_ms, client_ip)

        return response

    async def _check_rate_limit(self, request: Request, ip: str):
        """Redis sliding window rate limiting."""
        try:
            from backend.utils.redis_client import get_redis
            redis = get_redis()

            # Extract user_id from JWT if present
            user_id = None
            auth_header = request.headers.get("Authorization", "")
            if auth_header.startswith("Bearer "):
                try:
                    import jwt
                    from backend.config import get_settings
                    token = auth_header[7:]
                    payload = jwt.decode(
                        token, get_settings().app_secret_key,
                        algorithms=["HS256"], options={"verify_exp": False}
                    )
                    user_id = payload.get("sub")
                except Exception:
                    pass

            now = int(time.time())
            window_start = now - RATE_WINDOW

            if user_id:
                key = f"rl:user:{user_id}"
                limit = RATE_USER_LIMIT
            else:
                key = f"rl:ip:{ip}"
                limit = RATE_IP_LIMIT

            # Sliding window: remove old entries, add current, count
            pipe = redis.pipeline()
            pipe.zremrangebyscore(key, 0, window_start)
            pipe.zadd(key, {f"{now}:{time.time_ns()}": now})
            pipe.zcard(key)
            pipe.expire(key, RATE_WINDOW + 5)
            results = await pipe.execute()
            count = results[2]

            if count > limit:
                logger.warning("rate_limit_exceeded",
                               ip=ip, user_id=user_id, count=count, limit=limit)
                return JSONResponse(
                    status_code=429,
                    content={
                        "type": "https://raxus.io/errors/rate-limited",
                        "title": "Too Many Requests",
                        "status": 429,
                        "detail": f"Rate limit exceeded. Max {limit} requests per {RATE_WINDOW}s.",
                        "retry_after": RATE_WINDOW,
                    },
                    headers={"Retry-After": str(RATE_WINDOW), "X-RateLimit-Limit": str(limit)},
                )

            return None  # OK
        except Exception as e:
            # Redis unavailable — fail open (don't block requests)
            logger.error("rate_limit_check_failed", error=str(e))
            return None

    def _check_suspicious(self, request: Request) -> JSONResponse | None:
        """Heuristic check on headers and query params (not SQL AST — that's done in sql_engine)."""
        # Check query params
        qs = str(request.url.query).upper()
        # Check user-agent
        ua = request.headers.get("user-agent", "").lower()

        for pattern in SUSPICIOUS_PATTERNS:
            if pattern.upper() in qs:
                return JSONResponse(
                    status_code=400,
                    content={
                        "type": "https://raxus.io/errors/suspicious-request",
                        "title": "Suspicious Request Detected",
                        "status": 400,
                        "detail": "Request contains potentially malicious patterns.",
                    }
                )
        return None

    async def _write_audit(self, request: Request, response: Response,
                            duration_ms: int, ip: str):
        """Écriture audit log automatique pour toutes les mutations."""
        try:
            from backend.db.app_db import write_audit_log

            # Extract user from JWT
            user_id, username, role = "", "anonymous", "viewer"
            auth_header = request.headers.get("Authorization", "")
            if auth_header.startswith("Bearer "):
                try:
                    import jwt
                    from backend.config import get_settings
                    payload = jwt.decode(
                        auth_header[7:], get_settings().app_secret_key,
                        algorithms=["HS256"], options={"verify_exp": False}
                    )
                    user_id = payload.get("sub", "")
                    username = payload.get("username", "")
                    role = payload.get("role", "viewer")
                except Exception:
                    pass

            # Map path to action
            method = request.method
            path = request.url.path
            action = f"{method.lower()}.{path.strip('/').replace('/', '.')}"

            # Determine result
            status = response.status_code
            result = "success" if status < 400 else "failure" if status < 500 else "error"

            # Risk score heuristic
            risk = 0
            if method == "DELETE":
                risk = 40
            if "password" in path or "credentials" in path:
                risk += 20
            if status == 401 or status == 403:
                risk += 30

            await write_audit_log(
                user_id=user_id, username=username, user_role=role,
                action=action,
                resource_type=path.split("/")[1] if "/" in path else "",
                resource_id=path.split("/")[2] if path.count("/") >= 2 else "",
                request_ip=ip,
                user_agent=request.headers.get("user-agent", "")[:200],
                payload_summary=f"{method} {path}",
                result=result,
                risk_score=min(risk, 100),
                duration_ms=duration_ms,
            )
        except Exception as e:
            # Never fail the request because of audit log
            logger.error("audit_write_failed", error=str(e))

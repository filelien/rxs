"""
Dépendances FastAPI partagées — injection JWT réelle.
Utilisées dans tous les routers pour récupérer l'utilisateur courant.
"""
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from typing import Optional, Dict
from backend.auth.jwt_handler import verify_token
from backend.auth.rbac import PERMISSIONS
from backend.utils.logging import get_logger

logger = get_logger(__name__)
bearer = HTTPBearer(auto_error=False)


# ── Current user dependency ───────────────────────────────────
async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer),
) -> Dict:
    """Extrait et valide le JWT. Retourne le payload complet."""
    if not credentials:
        raise HTTPException(status_code=401, detail="Authentication required")
    payload = await verify_token(credentials.credentials, token_type="access")
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    return {
        "user_id": payload.get("sub", ""),
        "username": payload.get("username", ""),
        "role": payload.get("role", "viewer"),
        "jti": payload.get("jti", ""),
    }


async def get_optional_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer),
) -> Optional[Dict]:
    """Retourne None si pas de token — pour les routes semi-publiques."""
    if not credentials:
        return None
    payload = await verify_token(credentials.credentials, token_type="access")
    if not payload:
        return None
    return {
        "user_id": payload.get("sub", ""),
        "username": payload.get("username", ""),
        "role": payload.get("role", "viewer"),
    }


# ── Permission checker factory ────────────────────────────────
def require_permission(resource: str, action: str):
    """Dependency factory: vérifie que le rôle JWT a resource:action."""
    async def _check(user: Dict = Depends(get_current_user)) -> Dict:
        role = user.get("role", "viewer")
        allowed = action in PERMISSIONS.get(role, {}).get(resource, [])
        if not allowed:
            raise HTTPException(
                status_code=403,
                detail=f"Role '{role}' cannot perform '{action}' on '{resource}'",
            )
        return user
    return _check


def require_role(min_role: str):
    """Dependency: vérifie que le rôle est au moins min_role."""
    LEVELS = {"admin": 4, "dba": 3, "analyst": 2, "viewer": 1}
    async def _check(user: Dict = Depends(get_current_user)) -> Dict:
        user_level = LEVELS.get(user.get("role", "viewer"), 0)
        min_level = LEVELS.get(min_role, 99)
        if user_level < min_level:
            raise HTTPException(
                status_code=403,
                detail=f"Requires '{min_role}' role or higher",
            )
        return user
    return _check

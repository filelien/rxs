"""RBAC — 4 rôles, permissions granulaires par resource:action"""
from typing import Dict, List, Optional
from fastapi import HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from backend.auth.jwt_handler import verify_token
from backend.utils.logging import get_logger

logger = get_logger(__name__)
bearer = HTTPBearer(auto_error=False)

PERMISSIONS: Dict[str, Dict[str, List[str]]] = {
    "admin": {
        "connections": ["read","create","update","delete","test"],
        "query":       ["execute","history","saved","explain_plan","delete","update"],
        "monitoring":  ["read","configure_alerts","delete_alerts"],
        "audit":       ["read","export"],
        "tasks":       ["create","read","execute","delete","schedule"],
        "chat":        ["use","history"],
        "users":       ["create","read","update","delete","suspend"],
        "agents":      ["register","read","delete","execute"],
    },
    "dba": {
        "connections": ["read","create","update","delete","test"],
        "query":       ["execute","history","saved","explain_plan"],
        "monitoring":  ["read","configure_alerts"],
        "audit":       ["read"],
        "tasks":       ["create","read","execute","delete","schedule"],
        "chat":        ["use","history"],
        "agents":      ["read","execute"],
        "users":       ["read"],
    },
    "analyst": {
        "connections": ["read","test"],
        "query":       ["execute","history","saved"],
        "monitoring":  ["read"],
        "audit":       [],
        "tasks":       ["read"],
        "chat":        ["use"],
        "agents":      [],
        "users":       [],
    },
    "viewer": {
        "connections": ["read"],
        "query":       ["history"],
        "monitoring":  ["read"],
        "audit":       [],
        "tasks":       ["read"],
        "chat":        [],
        "agents":      [],
        "users":       [],
    },
}


def has_permission(role: str, resource: str, action: str) -> bool:
    return action in PERMISSIONS.get(role, {}).get(resource, [])


async def get_user_by_credentials(username: str, password: str) -> Optional[Dict]:
    """Authenticate against MySQL applicatif."""
    from backend.db.app_db import get_user_by_credentials as db_get
    return await db_get(username, password)

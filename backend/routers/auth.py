"""Router: /auth — Login, refresh, logout, me — sur MySQL applicatif"""
from fastapi import APIRouter, HTTPException, Depends, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from typing import Optional, Dict
from backend.auth.jwt_handler import create_access_token, create_refresh_token, verify_token, revoke_token
from backend.db import app_db
from backend.utils.logging import get_logger

router = APIRouter()
logger = get_logger(__name__)
bearer = HTTPBearer(auto_error=False)


class LoginRequest(BaseModel):
    username: str
    password: str
    remember_me: bool = False


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int = 900


class RefreshRequest(BaseModel):
    refresh_token: str


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest, request: Request):
    # Authenticate against MySQL applicatif
    user = await app_db.get_user_by_credentials(body.username, body.password)
    if not user:
        # Log failed attempt
        await app_db.write_audit_log(
            user_id="", username=body.username, user_role="",
            action="auth.login.failed",
            request_ip=request.client.host if request.client else "",
            result="failure", risk_score=30,
            payload_summary=f"username={body.username}",
        )
        logger.warning("login_failed", username=body.username, ip=request.client.host if request.client else "")
        raise HTTPException(status_code=401, detail="Identifiants incorrects")

    user_dict = {
        "id": user["id"],
        "username": user["username"],
        "role": user["role"],
    }

    access = create_access_token(user_dict)
    refresh = await create_refresh_token(user_dict, long_lived=body.remember_me)

    # Update last_login
    await app_db.update_user_login(user["id"])

    # Audit log
    await app_db.write_audit_log(
        user_id=user["id"], username=user["username"], user_role=user["role"],
        action="auth.login",
        request_ip=request.client.host if request.client else "",
        result="success", risk_score=0,
        payload_summary=f"username={user['username']} role={user['role']}",
    )

    logger.info("login_success", user_id=user["id"], username=user["username"])
    return TokenResponse(access_token=access, refresh_token=refresh)


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(body: RefreshRequest):
    payload = await verify_token(body.refresh_token, token_type="refresh")
    if not payload:
        raise HTTPException(status_code=401, detail="Refresh token invalide ou expiré")

    user_dict = {
        "id": payload["sub"],
        "username": payload.get("username", ""),
        "role": payload.get("role", "viewer"),
    }
    access = create_access_token(user_dict)
    new_refresh = await create_refresh_token(user_dict)
    return TokenResponse(access_token=access, refresh_token=new_refresh)


@router.post("/logout")
async def logout(credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer)):
    if credentials:
        await revoke_token(credentials.credentials)
    return {"message": "Déconnecté"}


@router.get("/me")
async def me(credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer)):
    if not credentials:
        raise HTTPException(status_code=401, detail="Non authentifié")
    payload = await verify_token(credentials.credentials, token_type="access")
    if not payload:
        raise HTTPException(status_code=401, detail="Token invalide")

    # Fetch fresh user data from MySQL
    user = await app_db.get_user_by_id(payload["sub"])
    if not user:
        raise HTTPException(status_code=404, detail="Utilisateur introuvable")

    return {
        "user_id": user["id"],
        "username": user["username"],
        "email": user.get("email", ""),
        "role": user["role"],
        "full_name": user.get("full_name", ""),
        "active": user.get("active", True),
    }


@router.post("/change-password")
async def change_password(
    body: dict,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer),
):
    if not credentials:
        raise HTTPException(status_code=401, detail="Non authentifié")
    payload = await verify_token(credentials.credentials, token_type="access")
    if not payload:
        raise HTTPException(status_code=401, detail="Token invalide")

    old_pwd = body.get("old_password", "")
    new_pwd = body.get("new_password", "")
    if not old_pwd or not new_pwd:
        raise HTTPException(status_code=422, detail="old_password et new_password requis")
    if len(new_pwd) < 8:
        raise HTTPException(status_code=422, detail="Le nouveau mot de passe doit faire au moins 8 caractères")

    # Verify old password
    user = await app_db.get_user_by_credentials(payload.get("username", ""), old_pwd)
    if not user:
        raise HTTPException(status_code=401, detail="Mot de passe actuel incorrect")

    new_hash = app_db.hash_password(new_pwd)
    await app_db.execute(
        "UPDATE users SET password_hash=%s WHERE id=%s",
        (new_hash, payload["sub"]),
    )
    await app_db.write_audit_log(
        user_id=payload["sub"], username=payload.get("username", ""), user_role=payload.get("role", ""),
        action="auth.change_password", result="success", risk_score=10,
    )
    return {"message": "Mot de passe mis à jour"}

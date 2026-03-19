"""Router: /users — Gestion utilisateurs MySQL avec JWT"""
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, EmailStr
from typing import Optional, Dict, List
from backend.db import app_db
from backend.dependencies import get_current_user, require_role, require_permission

router = APIRouter()


class UserCreate(BaseModel):
    username: str
    email: str
    password: str
    role: str = "viewer"
    full_name: str = ""


class UserUpdate(BaseModel):
    role: Optional[str] = None
    full_name: Optional[str] = None
    active: Optional[bool] = None


@router.get("/")
async def list_users(user: Dict = Depends(require_permission("users", "read"))):
    rows = await app_db.list_users()
    for r in rows:
        r.pop("password_hash", None)
        for k in ("last_login_at", "created_at", "updated_at"):
            if r.get(k) and hasattr(r[k], "isoformat"):
                r[k] = r[k].isoformat()
    return rows


@router.post("/", status_code=201)
async def create_user(body: UserCreate, user: Dict = Depends(require_permission("users", "create"))):
    # Check uniqueness
    existing = await app_db.fetch_one(
        "SELECT id FROM users WHERE username=%s OR email=%s", (body.username, body.email)
    )
    if existing:
        raise HTTPException(status_code=409, detail="Username ou email déjà utilisé")

    if len(body.password) < 8:
        raise HTTPException(status_code=422, detail="Mot de passe trop court (min 8 caractères)")

    valid_roles = ("admin", "dba", "analyst", "viewer")
    if body.role not in valid_roles:
        raise HTTPException(status_code=422, detail=f"Rôle invalide. Valeurs: {valid_roles}")

    uid = await app_db.create_user(body.username, body.email, body.password, body.role, body.full_name)
    await app_db.write_audit_log(
        user_id=user["user_id"], username=user["username"], user_role=user["role"],
        action="user.create", resource_type="user", resource_id=uid,
        payload_summary=f"username={body.username} role={body.role}", result="success",
    )
    return {"id": uid, "message": "Utilisateur créé"}


@router.get("/me")
async def get_me(user: Dict = Depends(get_current_user)):
    row = await app_db.get_user_by_id(user["user_id"])
    if not row:
        raise HTTPException(status_code=404, detail="Utilisateur introuvable")
    row.pop("password_hash", None)
    for k in ("last_login_at", "created_at"):
        if row.get(k) and hasattr(row[k], "isoformat"):
            row[k] = row[k].isoformat()
    return row


@router.get("/{user_id}")
async def get_user(user_id: str, user: Dict = Depends(require_permission("users", "read"))):
    row = await app_db.get_user_by_id(user_id)
    if not row:
        raise HTTPException(status_code=404, detail="Utilisateur introuvable")
    row.pop("password_hash", None)
    for k in ("last_login_at", "created_at"):
        if row.get(k) and hasattr(row[k], "isoformat"):
            row[k] = row[k].isoformat()
    return row


@router.patch("/{user_id}")
async def update_user(user_id: str, body: UserUpdate, user: Dict = Depends(require_permission("users", "update"))):
    # Prevent non-admins from promoting to admin
    if body.role == "admin" and user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Seul un admin peut créer un autre admin")

    if body.active is not None:
        await app_db.update_user_status(user_id, body.active)
    if body.role:
        await app_db.execute("UPDATE users SET role=%s WHERE id=%s", (body.role, user_id))
    if body.full_name is not None:
        await app_db.execute("UPDATE users SET full_name=%s WHERE id=%s", (body.full_name, user_id))

    await app_db.write_audit_log(
        user_id=user["user_id"], username=user["username"], user_role=user["role"],
        action="user.update", resource_type="user", resource_id=user_id,
        payload_summary=f"role={body.role} active={body.active}", result="success",
    )
    return {"message": "Utilisateur mis à jour"}


@router.delete("/{user_id}")
async def delete_user(user_id: str, user: Dict = Depends(require_permission("users", "delete"))):
    if user_id == user["user_id"]:
        raise HTTPException(status_code=400, detail="Impossible de supprimer son propre compte")

    row = await app_db.get_user_by_id(user_id)
    if not row:
        raise HTTPException(status_code=404, detail="Utilisateur introuvable")
    if row.get("role") == "admin":
        # Check that at least one other admin exists
        admins = await app_db.fetch_all("SELECT id FROM users WHERE role='admin' AND id != %s", (user_id,))
        if not admins:
            raise HTTPException(status_code=400, detail="Impossible de supprimer le dernier administrateur")

    await app_db.execute("DELETE FROM users WHERE id=%s AND role!='admin' OR id=%s AND role='admin'", (user_id, user_id))
    await app_db.write_audit_log(
        user_id=user["user_id"], username=user["username"], user_role=user["role"],
        action="user.delete", resource_type="user", resource_id=user_id,
        payload_summary=f"deleted={row['username']}", result="success", risk_score=40,
    )
    return {"message": "Utilisateur supprimé"}

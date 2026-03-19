"""Router: /agents — Serveurs et agents, métriques, commandes"""
import json
import hashlib
import hmac
import time
from fastapi import APIRouter, HTTPException, Request, Depends
from pydantic import BaseModel
from typing import Dict, Any, List, Optional
from backend.db import app_db
from backend.monitoring.metrics import metrics_collector, alert_engine
from backend.dependencies import get_current_user
from backend.utils.logging import get_logger

router = APIRouter()
logger = get_logger(__name__)
_pending_commands: Dict[str, List[Dict]] = {}


class HeartbeatPayload(BaseModel):
    status: str = "ok"
    version: str = "1.0"
    uptime: int = 0
    hostname: Optional[str] = None


class MetricsPayload(BaseModel):
    server_id: str
    hostname: str
    timestamp: str
    cpu: Dict[str, Any]
    memory: Dict[str, Any]
    disk: List[Dict]
    network: Dict[str, Any]
    load_average: List[float]
    processes: Dict[str, Any]
    uptime_seconds: int


class CommandResult(BaseModel):
    command_id: str
    command: str
    status: str
    result: Any


class RegisterServer(BaseModel):
    server_id: str
    hostname: str
    ip_address: str = ""
    description: str = ""


# ── UI endpoints (authentifiés) ───────────────────────────────

@router.get("/")
async def list_servers(user: Dict = Depends(get_current_user)):
    rows = await app_db.list_servers()
    for r in rows:
        for k in ("last_seen_at", "created_at", "updated_at"):
            if r.get(k) and hasattr(r[k], "isoformat"):
                r[k] = r[k].isoformat()
    return rows


@router.post("/register", status_code=201)
async def register_server(body: RegisterServer, user: Dict = Depends(get_current_user)):
    await app_db.upsert_server(body.server_id, body.hostname, body.ip_address)
    return {"message": "Server registered", "server_id": body.server_id}


@router.post("/{server_id}/send-command")
async def send_command(server_id: str, command: str, user: Dict = Depends(get_current_user)):
    ALLOWED = {"disk_usage", "top_processes", "read_log", "uptime"}
    if command not in ALLOWED:
        raise HTTPException(status_code=400, detail=f"Command not allowed. Allowed: {ALLOWED}")
    import uuid
    cmd = {"command_id": str(uuid.uuid4())[:8], "command": command}
    _pending_commands.setdefault(server_id, []).append(cmd)
    await app_db.write_audit_log(
        user_id=user["user_id"], username=user["username"], user_role=user["role"],
        action=f"agent.send_command.{command}", resource_type="server", resource_id=server_id,
        result="success",
    )
    return {"queued": True, "command_id": cmd["command_id"]}


@router.get("/{server_id}/metrics/history")
async def server_metric_history(
    server_id: str, metric: str = "cpu_percent", window: int = 60,
    user: Dict = Depends(get_current_user),
):
    rows = await app_db.get_metric_history(None, metric, window)
    for r in rows:
        if r.get("timestamp") and hasattr(r["timestamp"], "isoformat"):
            r["timestamp"] = r["timestamp"].isoformat()
    return rows


@router.delete("/{server_id}")
async def delete_server(server_id: str, user: Dict = Depends(get_current_user)):
    await app_db.execute("DELETE FROM servers WHERE id=%s", (server_id,))
    return {"message": "Server deleted"}


# ── Agent endpoints (HMAC-auth, pas de JWT) ───────────────────

def _verify_hmac(secret: str, signature: str, timestamp: str, body: str) -> bool:
    try:
        ts = int(timestamp)
        if abs(time.time() - ts) > 60:
            return False
        expected = hmac.new(secret.encode(), (timestamp + body).encode(), hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, signature)
    except Exception:
        return False


@router.post("/{server_id}/heartbeat")
async def heartbeat(server_id: str, body: HeartbeatPayload, request: Request):
    await app_db.upsert_server(
        server_id,
        body.hostname or server_id,
        request.client.host if request.client else "",
        agent_version=body.version,
    )
    return {"ok": True}


@router.post("/{server_id}/metrics")
async def receive_metrics(server_id: str, body: MetricsPayload, request: Request):
    # Update server record
    await app_db.upsert_server(server_id, body.hostname, request.client.host if request.client else "")

    # Persist metrics to MySQL
    cpu_pct = body.cpu.get("percent", 0)
    mem_pct = body.memory.get("percent", 0)
    await app_db.save_metric(None, server_id, "cpu_percent", cpu_pct)
    await app_db.save_metric(None, server_id, "memory_percent", mem_pct)
    await app_db.save_metric(None, server_id, "uptime_seconds", body.uptime_seconds)
    await app_db.save_metric(None, server_id, "load_1m", body.load_average[0] if body.load_average else 0)

    for disk in body.disk:
        mount = disk.get("mount", "/").replace("/", "_").strip("_") or "root"
        await app_db.save_metric(None, server_id, f"disk_pct_{mount}", disk.get("percent", 0))

    # Also update Prometheus gauges
    from backend.monitoring.metrics import SERVER_CPU, SERVER_MEMORY
    SERVER_CPU.labels(server_id=server_id, hostname=body.hostname).set(cpu_pct)
    SERVER_MEMORY.labels(server_id=server_id, type="used").set(body.memory.get("used_mb", 0))

    # Alert evaluation
    await alert_engine.evaluate(server_id, {
        "cpu": cpu_pct,
        "memory_percent": mem_pct,
    })

    logger.info("agent_metrics", server_id=server_id, cpu=cpu_pct, mem=mem_pct)
    return {"ok": True}


@router.get("/{server_id}/commands")
async def get_commands(server_id: str):
    """Agent polls for pending commands."""
    commands = _pending_commands.pop(server_id, [])
    return commands


@router.post("/{server_id}/results")
async def receive_result(server_id: str, body: CommandResult, request: Request):
    logger.info("agent_result", server_id=server_id, command=body.command, status=body.status)
    await app_db.write_audit_log(
        user_id="system", username="agent", user_role="system",
        action=f"agent.command_result.{body.command}",
        resource_type="server", resource_id=server_id,
        result=body.status,
        payload_summary=str(body.result)[:200],
    )
    return {"ok": True}

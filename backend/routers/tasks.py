"""Router: /tasks — Task Engine avec JWT réel"""
from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect, Depends
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone
from backend.db import app_db
from backend.models.base import new_id
from backend.dependencies import get_current_user, require_permission
from backend.utils.logging import get_logger
import asyncio, json, time

router = APIRouter()
logger = get_logger(__name__)
_task_streams: Dict[str, List[str]] = {}
_task_done: Dict[str, bool] = {}

class TaskCreate(BaseModel):
    name: str
    type: str
    connector_id: Optional[str] = None
    server_id: Optional[str] = None
    payload: Dict[str, Any] = {}
    max_retries: int = 2

class ScheduleCreate(BaseModel):
    name: str
    task_type: str
    connector_id: Optional[str] = None
    payload: Dict[str, Any] = {}
    cron: str
    timezone: str = "UTC"

@router.get("/")
async def list_tasks(status:Optional[str]=None,limit:int=50,user:Dict=Depends(require_permission("tasks","read"))):
    rows=await app_db.get_tasks(status or "",limit)
    for r in rows:
        for k in ("created_at","started_at","finished_at"):
            if r.get(k) and hasattr(r[k],"isoformat"): r[k]=r[k].isoformat()
    return rows

@router.post("/",status_code=201)
async def create_task(body:TaskCreate,user:Dict=Depends(require_permission("tasks","create"))):
    task_id=new_id()
    await app_db.create_task(task_id=task_id,name=body.name,task_type=body.type,
        connection_id=body.connector_id or "",server_id=body.server_id or "",
        payload=body.payload,created_by=user["user_id"],max_retries=body.max_retries)
    asyncio.create_task(_execute_task(task_id,body,user))
    return {"task_id":task_id,"status":"pending"}

@router.get("/{task_id}")
async def get_task(task_id:str,user:Dict=Depends(require_permission("tasks","read"))):
    row=await app_db.get_task(task_id)
    if not row: raise HTTPException(404,"Task not found")
    for k in ("created_at","started_at","finished_at"):
        if row.get(k) and hasattr(row[k],"isoformat"): row[k]=row[k].isoformat()
    return row

@router.delete("/{task_id}")
async def cancel_task(task_id:str,user:Dict=Depends(require_permission("tasks","delete"))):
    await app_db.update_task_status(task_id,"cancelled")
    return {"message":"Cancelled"}

@router.websocket("/{task_id}/logs")
async def task_logs_ws(websocket:WebSocket,task_id:str):
    await websocket.accept()
    sent=0
    try:
        while True:
            logs=_task_streams.get(task_id,[])
            while sent<len(logs):
                await websocket.send_text(json.dumps({"line":logs[sent]})); sent+=1
            if _task_done.get(task_id) and sent>=len(logs):
                await websocket.send_text(json.dumps({"done":True})); break
            await asyncio.sleep(0.3)
    except WebSocketDisconnect: pass

@router.get("/schedules/list")
async def list_schedules(user:Dict=Depends(require_permission("tasks","read"))):
    rows=await app_db.list_schedules()
    for r in rows:
        for k in ("created_at","next_run_at","last_run_at"):
            if r.get(k) and hasattr(r[k],"isoformat"): r[k]=r[k].isoformat()
    return rows

@router.post("/schedules/",status_code=201)
async def create_schedule(body:ScheduleCreate,user:Dict=Depends(require_permission("tasks","schedule"))):
    sid=new_id()
    await app_db.create_schedule(sched_id=sid,name=body.name,task_type=body.task_type,
        cron_expr=body.cron,connection_id=body.connector_id or "",
        payload=body.payload,timezone=body.timezone,created_by=user["user_id"])
    return {"schedule_id":sid}

@router.post("/schedules/{schedule_id}/pause")
async def pause_schedule(schedule_id:str,user:Dict=Depends(require_permission("tasks","schedule"))):
    await app_db.pause_schedule(schedule_id,True); return {"message":"Paused"}

@router.post("/schedules/{schedule_id}/resume")
async def resume_schedule(schedule_id:str,user:Dict=Depends(require_permission("tasks","schedule"))):
    await app_db.pause_schedule(schedule_id,False); return {"message":"Resumed"}

@router.post("/schedules/{schedule_id}/trigger")
async def trigger_schedule(schedule_id:str,user:Dict=Depends(require_permission("tasks","execute"))):
    rows=await app_db.list_schedules()
    sched=next((r for r in rows if str(r.get("id"))==schedule_id),None)
    if not sched: raise HTTPException(404,"Schedule not found")
    task_id=new_id()
    payload=json.loads(sched.get("payload") or "{}") if isinstance(sched.get("payload"),str) else (sched.get("payload") or {})
    await app_db.create_task(task_id=task_id,name=f"[Trigger] {sched['name']}",task_type=sched["task_type"],
        connection_id=sched.get("connection_id") or "",payload=payload,created_by=user["user_id"])
    body=TaskCreate(name=sched["name"],type=sched["task_type"],connector_id=sched.get("connection_id"),payload=payload)
    asyncio.create_task(_execute_task(task_id,body,user))
    return {"task_id":task_id}

async def _execute_task(task_id:str,body:TaskCreate,user:Dict):
    _task_streams[task_id]=[]; _task_done[task_id]=False
    def log(line:str): _task_streams[task_id].append(f"[{datetime.now(timezone.utc).strftime('%H:%M:%S')}] {line}")
    await app_db.update_task_status(task_id,"running")
    log(f"Tâche '{body.name}' démarrée (type={body.type}, user={user['username']})")
    t0=time.perf_counter()
    try:
        output=""
        if body.type=="SQL_SCRIPT":
            from backend.services.sql_engine import sql_engine
            sql=body.payload.get("sql","SELECT 1")
            log(f"Exécution SQL sur connecteur {body.connector_id}...")
            result=await sql_engine.execute(sql=sql,connector_id=body.connector_id or "",user_id=user["user_id"],user_role=user["role"])
            output=f"Lignes: {result.row_count} | Durée: {result.duration_ms}ms | Statut: {result.status.value}"
            log(output)
        elif body.type=="ANALYZE":
            from backend.connectors.registry import ConnectorRegistry
            try:
                conn=ConnectorRegistry.get(body.connector_id or ""); log("Analyse de santé...")
                m=await conn.get_metrics()
                output=f"Connexions: {m.active_connections} | Latence: {m.avg_query_ms}ms | Lentes: {m.slow_queries_count}"
                log(output)
            except Exception as e: output=f"Erreur: {e}"; log(output)
        elif body.type=="REPORT":
            log("Génération du rapport d'audit...")
            from backend.services.audit_report import audit_report_service
            report=await audit_report_service.generate_report(days=7)
            output=f"Rapport généré: {report['summary']['total_audit_events']} événements, {report['summary']['high_risk_events']} à risque élevé"
            log(output)
        else:
            log(f"Type '{body.type}' traité"); output=f"Tâche {body.type} exécutée"
        d=round((time.perf_counter()-t0)*1000); log(f"Terminé en {d}ms")
        await app_db.update_task_status(task_id,"success",output=output,duration_ms=d)
    except Exception as e:
        log(f"ERREUR: {e}")
        await app_db.update_task_status(task_id,"failed",error_msg=str(e),duration_ms=round((time.perf_counter()-t0)*1000))
    finally: _task_done[task_id]=True

"""Router: /audit — Logs immuables, sessions, privilèges, rapport, few-shot store"""
from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import HTMLResponse
from typing import Optional, Dict
from backend.db import app_db
from backend.dependencies import get_current_user, require_permission
router = APIRouter()

@router.get("/logs")
async def get_audit_logs(user_id:Optional[str]=None,action:Optional[str]=None,risk_score_min:int=0,days:int=7,page:int=1,limit:int=50,current:Dict=Depends(require_permission("audit","read"))):
    res=await app_db.get_audit_logs(user_id=user_id or "",action=action or "",risk_min=risk_score_min,days=days,page=page,limit=limit)
    for r in (res.get("data") or []):
        if r.get("created_at") and hasattr(r["created_at"],"isoformat"): r["created_at"]=r["created_at"].isoformat()
    return res

@router.get("/sessions/{connector_id}")
async def active_sessions(connector_id:str,current:Dict=Depends(get_current_user)):
    from backend.connectors.registry import ConnectorRegistry
    try:
        conn=ConnectorRegistry.get(connector_id)
        return await conn.get_active_sessions() if hasattr(conn,"get_active_sessions") else []
    except KeyError: return []

@router.get("/privileges/{connector_id}")
async def oracle_privileges(connector_id:str,current:Dict=Depends(require_permission("audit","read"))):
    from backend.connectors.registry import ConnectorRegistry
    try: conn=ConnectorRegistry.get(connector_id)
    except KeyError: raise HTTPException(404,"Connector not found")
    try:
        res=await conn.execute_query("SELECT grantee,privilege,admin_option FROM dba_sys_privs WHERE grantee NOT IN ('SYS','SYSTEM','DBSNMP','SYSMAN') ORDER BY grantee,privilege")
        dangerous=["DBA","SYSDBA","ALTER SYSTEM","CREATE ANY TABLE","DROP ANY TABLE","EXECUTE ANY PROCEDURE","SELECT ANY TABLE"]
        flagged=[r for r in res.rows if any(d in str(r.get("privilege","")).upper() for d in dangerous)]
        return {"all_privileges":res.rows,"flagged":flagged,"flagged_count":len(flagged)}
    except Exception as e: raise HTTPException(400,str(e))

@router.get("/locks/{connector_id}")
async def detect_locks(connector_id:str,current:Dict=Depends(get_current_user)):
    from backend.connectors.registry import ConnectorRegistry
    try:
        conn=ConnectorRegistry.get(connector_id)
        return await conn.get_locks() if hasattr(conn,"get_locks") else []
    except KeyError: return []

@router.get("/report")
async def get_audit_report(days:int=7,format:str="json",current:Dict=Depends(require_permission("audit","read"))):
    from backend.services.audit_report import audit_report_service
    report=await audit_report_service.generate_report(days=days)
    if format=="html":
        return HTMLResponse(content=audit_report_service.to_html(report),media_type="text/html")
    return report

@router.post("/log")
async def write_audit_log_manual(entry:dict,current:Dict=Depends(get_current_user)):
    if current["role"]!="admin": raise HTTPException(403,"Admin only")
    await app_db.write_audit_log(user_id=current["user_id"],username=current["username"],user_role=current["role"],
        action=entry.get("action","manual.log"),resource_type=entry.get("resource_type",""),
        resource_id=entry.get("resource_id",""),payload_summary=entry.get("payload_summary",""),
        result=entry.get("result","success"),risk_score=entry.get("risk_score",0))
    return {"logged":True}

@router.get("/few-shots")
async def list_few_shots(db_type:Optional[str]=None,current:Dict=Depends(get_current_user)):
    from backend.services.audit_report import few_shot_store
    return await few_shot_store.list_all(db_type)

@router.post("/few-shots")
async def add_few_shot(body:dict,current:Dict=Depends(get_current_user)):
    from backend.services.audit_report import few_shot_store
    eid=await few_shot_store.add_example(question=body.get("question",""),sql=body.get("sql",""),
        connector_id=body.get("connector_id",""),db_type=body.get("db_type",""),user_id=current["user_id"])
    return {"id":eid}

@router.delete("/few-shots/{example_id}")
async def delete_few_shot(example_id:str,current:Dict=Depends(get_current_user)):
    from backend.services.audit_report import few_shot_store
    await few_shot_store.delete(example_id)
    return {"deleted":True}

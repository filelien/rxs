"""Router: /connections — CRUD MySQL, JWT réel, schema browser"""
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from typing import Dict, Any, Optional, List
from backend.connectors.registry import ConnectorRegistry, encrypt_credentials, decrypt_credentials
from backend.db import app_db
from backend.dependencies import get_current_user, require_permission
from backend.utils.logging import get_logger
router = APIRouter()
logger = get_logger(__name__)

class ConnectionCreate(BaseModel):
    name: str = Field(...,min_length=1,max_length=200)
    db_type: str
    description: Optional[str] = None
    config: Dict[str, Any]
    ssh_tunnel: bool = False
    ssh_host: Optional[str] = None
    ssh_port: int = 22
    ssh_user: Optional[str] = None

@router.get("/")
async def list_connections(user:Dict=Depends(require_permission("connections","read"))):
    rows=await app_db.list_connections()
    for r in rows:
        for k in ("last_tested_at","created_at","updated_at"):
            if r.get(k) and hasattr(r[k],"isoformat"): r[k]=r[k].isoformat()
        r.pop("credentials_enc",None)
    return rows

@router.post("/",status_code=201)
async def create_connection(body:ConnectionCreate,user:Dict=Depends(require_permission("connections","create"))):
    if await app_db.fetch_one("SELECT id FROM db_connections WHERE name=%s",(body.name,)):
        raise HTTPException(409,f"Name '{body.name}' already exists")
    cfg=body.config
    host=cfg.get("host","")
    if not host: raise HTTPException(422,"host required in config")
    conn_id=await app_db.create_connection(
        name=body.name,db_type=body.db_type,host=host,port=cfg.get("port",0),
        database_name=cfg.get("database") or cfg.get("service_name") or cfg.get("sid") or "",
        username=cfg.get("user") or cfg.get("username") or "",
        credentials_enc=encrypt_credentials(cfg),description=body.description or "",
        created_by=user["user_id"],ssh_tunnel=body.ssh_tunnel,
        ssh_host=body.ssh_host or "",ssh_port=body.ssh_port,ssh_user=body.ssh_user or "",
    )
    try:
        await ConnectorRegistry.register(conn_id,body.db_type,cfg,meta={"name":body.name,"host":host})
    except Exception as e:
        await app_db.delete_connection(conn_id)
        raise HTTPException(400,f"Connection failed: {e}")
    await app_db.write_audit_log(user_id=user["user_id"],username=user["username"],user_role=user["role"],
        action="connection.create",resource_type="connection",resource_id=conn_id,
        payload_summary=f"name={body.name} type={body.db_type} host={host}",result="success")
    return {"id":conn_id,"message":"Connection created and active"}

@router.patch("/{conn_id}")
async def update_connection(conn_id:str,body:dict,user:Dict=Depends(require_permission("connections","update"))):
    row=await app_db.get_connection(conn_id)
    if not row: raise HTTPException(404,"Not found")
    enabled=body.get("enabled")
    if enabled is not None:
        await app_db.toggle_connection(conn_id,bool(enabled))
        if enabled:
            try:
                full=await app_db.fetch_one("SELECT credentials_enc,db_type FROM db_connections WHERE id=%s",(conn_id,))
                await ConnectorRegistry.register(conn_id,full["db_type"],decrypt_credentials(full["credentials_enc"]),meta={"name":row["name"]})
            except Exception as e: logger.warning("reregister_failed",id=conn_id,error=str(e))
        else: await ConnectorRegistry.remove(conn_id)
    if body.get("name"): await app_db.execute("UPDATE db_connections SET name=%s WHERE id=%s",(body["name"],conn_id))
    return {"message":"Updated"}

@router.delete("/{conn_id}")
async def delete_connection(conn_id:str,user:Dict=Depends(require_permission("connections","delete"))):
    row=await app_db.get_connection(conn_id)
    if not row: raise HTTPException(404,"Not found")
    await ConnectorRegistry.remove(conn_id)
    await app_db.delete_connection(conn_id)
    await app_db.write_audit_log(user_id=user["user_id"],username=user["username"],user_role=user["role"],
        action="connection.delete",resource_type="connection",resource_id=conn_id,
        payload_summary=f"name={row['name']}",result="success")
    return {"message":"Deleted"}

@router.post("/{conn_id}/test")
async def test_connection(conn_id:str,user:Dict=Depends(require_permission("connections","test"))):
    try: status=await ConnectorRegistry.test(conn_id)
    except KeyError: raise HTTPException(404,"Connector not registered")
    await app_db.update_connection_test(conn_id,ok=status.healthy,latency_ms=status.latency_ms or 0)
    return {"healthy":status.healthy,"latency_ms":status.latency_ms,"version":status.version,"error":status.error}

@router.get("/{conn_id}/schema")
async def get_schema(conn_id:str,database:Optional[str]=None,user:Dict=Depends(get_current_user)):
    try:
        conn=ConnectorRegistry.get(conn_id)
        tables=await conn.list_tables(database)
        result=[]
        for t in tables[:100]:
            try: cols=await conn.get_table_columns(t.name,t.schema or database); idx=await conn.list_indexes(t.name)
            except: cols,idx=[],[]
            result.append({"name":t.name,"schema":t.schema,"row_count":t.row_count,"size_bytes":t.size_bytes,
                "columns":[{"name":c.name,"data_type":c.data_type,"nullable":c.nullable,"default":c.default,"primary_key":c.primary_key} for c in cols],
                "indexes":[{"name":i.name,"columns":i.columns,"unique":i.unique} for i in idx]})
        return {"tables":result,"count":len(result)}
    except KeyError: raise HTTPException(404,"Connector not found")

@router.get("/{conn_id}/databases")
async def list_databases(conn_id:str,user:Dict=Depends(get_current_user)):
    try: conn=ConnectorRegistry.get(conn_id); return {"databases":await conn.list_databases()}
    except KeyError: raise HTTPException(404,"Connector not found")

@router.get("/{conn_id}/tables/{table_name}")
async def get_table_detail(conn_id:str,table_name:str,schema:Optional[str]=None,user:Dict=Depends(get_current_user)):
    try: conn=ConnectorRegistry.get(conn_id)
    except KeyError: raise HTTPException(404,"Connector not found")
    cols=await conn.get_table_columns(table_name,schema)
    idx=await conn.list_indexes(table_name)
    oracle_info={}
    if conn.db_type.value=="oracle" and hasattr(conn,"execute_query"):
        try:
            res=await conn.execute_query("SELECT tablespace_name,num_rows,blocks FROM dba_tables WHERE table_name=UPPER(:t)",{"t":table_name})
            if res.rows: oracle_info=res.rows[0]
        except: pass
    return {"table":table_name,"schema":schema,"oracle_stats":oracle_info,
        "columns":[{"name":c.name,"data_type":c.data_type,"nullable":c.nullable,"default":c.default,"primary_key":c.primary_key} for c in cols],
        "indexes":[{"name":i.name,"columns":i.columns,"unique":i.unique,"status":i.status} for i in idx]}

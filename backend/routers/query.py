"""Router: /query — Exécution SQL avec JWT réel, transactions, schema, historique MySQL"""
import uuid
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone

from backend.services.sql_engine import sql_engine, SQLValidator
from backend.connectors.registry import ConnectorRegistry
from backend.db import app_db
from backend.dependencies import get_current_user, require_permission
from backend.utils.logging import get_logger

router = APIRouter()
logger = get_logger(__name__)
_tx_sessions: Dict[str, Dict] = {}


class QueryRequest(BaseModel):
    sql: str = Field(..., min_length=1)
    connector_id: str
    params: Optional[Dict[str, Any]] = None
    timeout: int = Field(default=30, ge=1, le=300)


class SaveQueryRequest(BaseModel):
    name: str = Field(..., min_length=1)
    sql: str
    connector_id: str
    description: str = ""
    tags: List[str] = []
    is_public: bool = False


@router.post("/execute")
async def execute_query(body: QueryRequest, user: Dict = Depends(require_permission("query", "execute"))):
    result = await sql_engine.execute(
        sql=body.sql, connector_id=body.connector_id,
        user_id=user["user_id"], user_role=user["role"],
        params=body.params, timeout=body.timeout,
    )
    await app_db.save_query_history(
        query_uuid=result.query_id, user_id=user["user_id"],
        connection_id=body.connector_id, sql_text=body.sql[:5000],
        status=result.status.value, row_count=result.row_count,
        duration_ms=result.duration_ms, error_msg=result.error or "",
        risk_level=result.status.value if result.status.value == "blocked" else "safe",
    )
    if result.status.value == "blocked":
        raise HTTPException(status_code=403, detail=result.error)
    return result.model_dump()


@router.post("/validate")
async def validate_query(body: QueryRequest, user: Dict = Depends(get_current_user)):
    dialect = "oracle"
    try:
        conn = ConnectorRegistry.get(body.connector_id)
        dialect = conn.db_type.value
    except Exception:
        pass
    return SQLValidator.validate(body.sql, user_role=user["role"], dialect=dialect).model_dump()


@router.post("/explain")
async def explain_plan(body: QueryRequest, user: Dict = Depends(require_permission("query", "explain_plan"))):
    try:
        conn = ConnectorRegistry.get(body.connector_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Connector not found")
    if not hasattr(conn, "get_explain_plan"):
        raise HTTPException(status_code=400, detail="Not supported for this DB type")
    plan = await conn.get_explain_plan(body.sql)
    return {"plan": plan, "sql": body.sql}


@router.get("/history")
async def query_history(
    connector_id: Optional[str] = None, page: int = 1, limit: int = 50,
    user: Dict = Depends(require_permission("query", "history"))
):
    res = await app_db.get_query_history(user["user_id"], connector_id or "", limit, page)
    for r in (res.get("data") or []):
        if hasattr(r.get("executed_at"), "isoformat"):
            r["executed_at"] = r["executed_at"].isoformat()
    return res


@router.get("/slow")
async def slow_queries(
    threshold_ms: int = 1000, limit: int = 20,
    user: Dict = Depends(require_permission("query", "history"))
):
    rows = await app_db.get_slow_queries(threshold_ms, limit)
    for r in rows:
        if hasattr(r.get("executed_at"), "isoformat"):
            r["executed_at"] = r["executed_at"].isoformat()
    return rows


@router.post("/save", status_code=201)
async def save_query(body: SaveQueryRequest, user: Dict = Depends(require_permission("query", "saved"))):
    qid = await app_db.save_query(
        user["user_id"], body.connector_id, body.name,
        body.sql, body.description, body.tags, body.is_public
    )
    return {"id": qid}


@router.get("/saved")
async def list_saved_queries(
    connector_id: Optional[str] = None,
    user: Dict = Depends(require_permission("query", "saved"))
):
    rows = await app_db.list_saved_queries(user["user_id"], connector_id or "")
    for r in rows:
        for k in ("created_at", "updated_at"):
            if r.get(k) and hasattr(r[k], "isoformat"):
                r[k] = r[k].isoformat()
    return rows


@router.delete("/saved/{query_id}")
async def delete_saved_query(query_id: str, user: Dict = Depends(require_permission("query", "saved"))):
    await app_db.delete_saved_query(query_id, user["user_id"])
    return {"message": "Deleted"}


@router.get("/schema/{connector_id}")
async def get_schema(
    connector_id: str, database: Optional[str] = None,
    user: Dict = Depends(get_current_user)
):
    try:
        conn = ConnectorRegistry.get(connector_id)
        tables = await conn.list_tables(database)
        return {
            "tables": [{"name": t.name, "schema": t.schema,
                        "row_count": t.row_count, "size_bytes": t.size_bytes} for t in tables],
            "count": len(tables),
        }
    except KeyError:
        raise HTTPException(status_code=404, detail="Connector not found")


@router.get("/schema/{connector_id}/table/{table_name}")
async def get_table_detail(
    connector_id: str, table_name: str, schema: Optional[str] = None,
    user: Dict = Depends(get_current_user)
):
    try:
        conn = ConnectorRegistry.get(connector_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Connector not found")
    cols = await conn.get_table_columns(table_name, schema)
    idx = await conn.list_indexes(table_name)
    return {
        "table": table_name, "schema": schema,
        "columns": [{"name": c.name, "data_type": c.data_type, "nullable": c.nullable,
                     "default": c.default, "primary_key": c.primary_key} for c in cols],
        "indexes": [{"name": i.name, "columns": i.columns, "unique": i.unique} for i in idx],
    }


# ── Transaction management ────────────────────────────────────
@router.post("/transaction/begin")
async def begin_transaction(connector_id: str, user: Dict = Depends(require_permission("query", "execute"))):
    session_id = str(uuid.uuid4())[:8]
    _tx_sessions[session_id] = {
        "connector_id": connector_id,
        "user_id": user["user_id"],
        "started_at": datetime.now(timezone.utc).isoformat(),
        "statements": [],
    }
    logger.info("tx_begin", session_id=session_id, user=user["username"])
    return {"session_id": session_id, "message": "Transaction session opened"}


@router.post("/transaction/{session_id}/execute")
async def execute_in_transaction(
    session_id: str, body: QueryRequest,
    user: Dict = Depends(require_permission("query", "execute"))
):
    session = _tx_sessions.get(session_id)
    if not session or session["user_id"] != user["user_id"]:
        raise HTTPException(status_code=404, detail="Transaction session not found")
    result = await sql_engine.execute(
        sql=body.sql, connector_id=body.connector_id,
        user_id=user["user_id"], user_role=user["role"], params=body.params
    )
    session["statements"].append({"sql": body.sql, "status": result.status.value})
    return {**result.model_dump(), "session_id": session_id,
            "statements_count": len(session["statements"])}


@router.post("/transaction/{session_id}/commit")
async def commit_transaction(session_id: str, user: Dict = Depends(get_current_user)):
    session = _tx_sessions.pop(session_id, None)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    logger.info("tx_commit", session_id=session_id, user=user["username"],
                statements=len(session.get("statements", [])))
    return {"committed": True, "statements_executed": len(session.get("statements", []))}


@router.post("/transaction/{session_id}/rollback")
async def rollback_transaction(session_id: str, user: Dict = Depends(get_current_user)):
    session = _tx_sessions.pop(session_id, None)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    logger.info("tx_rollback", session_id=session_id, user=user["username"])
    return {"rolled_back": True}


@router.get("/transaction/{session_id}")
async def get_transaction(session_id: str, user: Dict = Depends(get_current_user)):
    session = _tx_sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


# ── Oracle Advanced ───────────────────────────────────────────
@router.get("/oracle/{connector_id}/performance")
async def oracle_performance(connector_id: str, user: Dict = Depends(require_permission("query", "explain_plan"))):
    try:
        conn = ConnectorRegistry.get(connector_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Connector not found")
    if conn.db_type.value != "oracle":
        raise HTTPException(status_code=400, detail="Oracle connector required")
    return {
        "top_sql": await conn.get_top_sql(10) if hasattr(conn, "get_top_sql") else [],
        "wait_events": await conn.get_wait_events(10) if hasattr(conn, "get_wait_events") else [],
        "locks": await conn.get_locks() if hasattr(conn, "get_locks") else [],
        "tablespaces": await conn.get_tablespace_usage() if hasattr(conn, "get_tablespace_usage") else [],
        "slow_queries": await conn.detect_slow_queries(1000) if hasattr(conn, "detect_slow_queries") else [],
        "active_sessions": await conn.get_active_sessions() if hasattr(conn, "get_active_sessions") else [],
    }

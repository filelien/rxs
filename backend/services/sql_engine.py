"""
SQL Engine — exécution sécurisée multi-SGBD pour Raxus.
Validation par AST (sqlglot), historique persisté, explain plan.
"""
import uuid
import time
import asyncio
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

import sqlglot
from pydantic import BaseModel

from backend.connectors.registry import ConnectorRegistry
from backend.utils.database import get_db
from backend.utils.logging import get_logger

logger = get_logger(__name__)

ROW_LIMIT = 10_000
QUERY_TIMEOUT = 30  # seconds

# ── Statements bloqués et admin-only ─────────────────────────
BLOCKED_STATEMENTS = {
    "drop", "truncate", "alter", "create user",
    "grant", "revoke", "rename",
}
ADMIN_ONLY_STATEMENTS = {
    "delete",   # sans WHERE → bloqué ; avec WHERE → admin only
    "update",   # idem
    "drop index",
    "insert",
}


class RiskLevel(str, Enum):
    SAFE = "safe"
    WARN = "warn"
    ADMIN_REQUIRED = "admin_required"
    BLOCKED = "blocked"


class QueryStatus(str, Enum):
    SUCCESS = "success"
    ERROR = "error"
    TIMEOUT = "timeout"
    BLOCKED = "blocked"


class ValidationResult(BaseModel):
    valid: bool
    risk_level: RiskLevel
    reason: str = ""
    normalized_sql: str = ""
    detected_operations: List[str] = []
    warnings: List[str] = []


class ExecutionResult(BaseModel):
    query_id: str
    sql_original: str
    sql_executed: str
    connector_id: str
    status: QueryStatus
    rows: List[Dict[str, Any]] = []
    row_count: int = 0
    columns: List[Dict[str, str]] = []
    duration_ms: int = 0
    truncated: bool = False
    error: Optional[str] = None
    executed_at: str = ""
    user_id: str = ""


# ── Validator ─────────────────────────────────────────────────
class SQLValidator:

    @staticmethod
    def validate(sql: str, user_role: str = "analyst", dialect: str = "oracle") -> ValidationResult:
        sql_lower = sql.strip().lower()
        detected_ops = []
        warnings = []

        # Parse AST
        try:
            statements = sqlglot.parse(sql, dialect=dialect)
        except Exception as e:
            return ValidationResult(
                valid=False,
                risk_level=RiskLevel.BLOCKED,
                reason=f"SQL parse error: {e}",
            )

        for stmt in statements:
            stmt_type = type(stmt).__name__.lower()
            detected_ops.append(stmt_type)

            # Hard block
            for blocked in BLOCKED_STATEMENTS:
                if blocked in sql_lower and stmt_type in blocked.replace(" ", ""):
                    return ValidationResult(
                        valid=False,
                        risk_level=RiskLevel.BLOCKED,
                        reason=f"Statement '{blocked.upper()}' is not allowed.",
                        detected_operations=detected_ops,
                    )

            # DELETE without WHERE
            if "delete" in stmt_type:
                has_where = "where" in sql_lower
                if not has_where:
                    return ValidationResult(
                        valid=False,
                        risk_level=RiskLevel.BLOCKED,
                        reason="DELETE without WHERE clause is not allowed.",
                        detected_operations=detected_ops,
                    )
                if user_role not in ("admin", "dba"):
                    return ValidationResult(
                        valid=False,
                        risk_level=RiskLevel.ADMIN_REQUIRED,
                        reason="DELETE requires admin or DBA role.",
                        detected_operations=detected_ops,
                    )

            # UPDATE without WHERE
            if "update" in stmt_type:
                if "where" not in sql_lower:
                    return ValidationResult(
                        valid=False,
                        risk_level=RiskLevel.BLOCKED,
                        reason="UPDATE without WHERE clause is not allowed.",
                        detected_operations=detected_ops,
                    )
                if user_role not in ("admin", "dba"):
                    return ValidationResult(
                        valid=False,
                        risk_level=RiskLevel.ADMIN_REQUIRED,
                        reason="UPDATE requires admin or DBA role.",
                        detected_operations=detected_ops,
                    )

            # SELECT warnings
            if "select" in stmt_type:
                if "limit" not in sql_lower and "rownum" not in sql_lower and "fetch" not in sql_lower:
                    warnings.append("No LIMIT clause detected — row limit will be enforced automatically.")
                if "from" in sql_lower and "," in sql_lower.split("from")[-1].split("where")[0]:
                    warnings.append("Possible cross-join detected.")

        # Normalize (format)
        try:
            normalized = sqlglot.transpile(sql, read=dialect, write=dialect, pretty=True)[0]
        except Exception:
            normalized = sql

        return ValidationResult(
            valid=True,
            risk_level=RiskLevel.WARN if warnings else RiskLevel.SAFE,
            normalized_sql=normalized,
            detected_operations=detected_ops,
            warnings=warnings,
        )


# ── SQL Engine ────────────────────────────────────────────────
class SQLEngine:

    def __init__(self):
        self.validator = SQLValidator()

    async def execute(
        self,
        sql: str,
        connector_id: str,
        user_id: str,
        user_role: str = "analyst",
        params: Optional[Dict] = None,
        timeout: int = QUERY_TIMEOUT,
    ) -> ExecutionResult:
        query_id = str(uuid.uuid4())[:8]
        executed_at = datetime.now(timezone.utc).isoformat()

        # 1. Validate
        connector = ConnectorRegistry.get(connector_id)
        dialect = connector.db_type.value if hasattr(connector, "db_type") else "oracle"
        validation = self.validator.validate(sql, user_role=user_role, dialect=dialect)

        if not validation.valid:
            result = ExecutionResult(
                query_id=query_id,
                sql_original=sql,
                sql_executed="",
                connector_id=connector_id,
                status=QueryStatus.BLOCKED,
                error=validation.reason,
                executed_at=executed_at,
                user_id=user_id,
            )
            await self._persist_history(result)
            logger.warning("query_blocked", query_id=query_id, reason=validation.reason, user_id=user_id)
            return result

        # 2. Auto-inject LIMIT if missing for SELECT
        sql_to_run = validation.normalized_sql or sql
        sql_lower = sql_to_run.lower()
        if "select" in sql_lower and "limit" not in sql_lower and "fetch" not in sql_lower and "rownum" not in sql_lower:
            if dialect == "oracle":
                sql_to_run = f"SELECT * FROM ({sql_to_run}) WHERE ROWNUM <= {ROW_LIMIT}"
            else:
                sql_to_run = f"{sql_to_run.rstrip(';')} LIMIT {ROW_LIMIT}"

        # 3. Execute with timeout
        start = time.perf_counter()
        try:
            qr = await asyncio.wait_for(
                connector.execute_query(sql_to_run, params=params, timeout=timeout, row_limit=ROW_LIMIT),
                timeout=timeout + 2,
            )
            duration_ms = round((time.perf_counter() - start) * 1000)
            result = ExecutionResult(
                query_id=query_id,
                sql_original=sql,
                sql_executed=sql_to_run,
                connector_id=connector_id,
                status=QueryStatus.SUCCESS,
                rows=qr.rows,
                row_count=qr.row_count,
                columns=qr.columns,
                duration_ms=duration_ms,
                truncated=qr.truncated,
                executed_at=executed_at,
                user_id=user_id,
            )
            logger.info("query_executed", query_id=query_id, duration_ms=duration_ms,
                        rows=qr.row_count, connector_id=connector_id)
        except asyncio.TimeoutError:
            result = ExecutionResult(
                query_id=query_id, sql_original=sql, sql_executed=sql_to_run,
                connector_id=connector_id, status=QueryStatus.TIMEOUT,
                error=f"Query exceeded {timeout}s timeout.",
                duration_ms=round((time.perf_counter()-start)*1000),
                executed_at=executed_at, user_id=user_id,
            )
        except Exception as e:
            result = ExecutionResult(
                query_id=query_id, sql_original=sql, sql_executed=sql_to_run,
                connector_id=connector_id, status=QueryStatus.ERROR,
                error=str(e),
                duration_ms=round((time.perf_counter()-start)*1000),
                executed_at=executed_at, user_id=user_id,
            )
            logger.error("query_error", query_id=query_id, error=str(e))

        await self._persist_history(result)
        return result

    async def _persist_history(self, result: ExecutionResult):
        try:
            db = get_db()
            await db.query_history.insert_one({
                **result.model_dump(),
                "timestamp": datetime.now(timezone.utc),
            })
        except Exception as e:
            logger.error("history_persist_failed", error=str(e))

    async def get_history(
        self,
        user_id: str,
        connector_id: Optional[str] = None,
        limit: int = 50,
        page: int = 1,
    ) -> Dict:
        db = get_db()
        filt: Dict = {"user_id": user_id}
        if connector_id:
            filt["connector_id"] = connector_id
        total = await db.query_history.count_documents(filt)
        skip = (page - 1) * limit
        cursor = db.query_history.find(filt, {"rows": 0}).sort("timestamp", -1).skip(skip).limit(limit)
        docs = [doc async for doc in cursor]
        for d in docs:
            d["_id"] = str(d["_id"])
        return {"data": docs, "total": total, "page": page, "limit": limit}

    async def get_slow_queries(self, threshold_ms: int = 1000, limit: int = 20) -> List[Dict]:
        db = get_db()
        cursor = db.query_history.find(
            {"status": "success", "duration_ms": {"$gt": threshold_ms}},
            {"rows": 0}
        ).sort("duration_ms", -1).limit(limit)
        docs = [d async for d in cursor]
        for d in docs:
            d["_id"] = str(d["_id"])
        return docs

    async def save_query(self, name: str, sql: str, connector_id: str, user_id: str, tags: List[str] = []) -> str:
        db = get_db()
        doc = {"name": name, "sql": sql, "connector_id": connector_id,
               "user_id": user_id, "tags": tags, "created_at": datetime.now(timezone.utc)}
        res = await db.saved_queries.insert_one(doc)
        return str(res.inserted_id)

    async def list_saved_queries(self, user_id: str, connector_id: Optional[str] = None) -> List[Dict]:
        db = get_db()
        filt: Dict = {"user_id": user_id}
        if connector_id:
            filt["connector_id"] = connector_id
        cursor = db.saved_queries.find(filt).sort("created_at", -1)
        docs = [d async for d in cursor]
        for d in docs:
            d["_id"] = str(d["_id"])
        return docs


# Singleton
sql_engine = SQLEngine()

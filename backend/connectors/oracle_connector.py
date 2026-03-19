"""
Oracle connector — python-oracledb (thin mode)
Covers: SQL, PL/SQL, AWR, V$ views, explain plan, locks, tablespaces
"""
import time
import asyncio
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional

import oracledb

from backend.connectors.base import (
    BaseConnector, ColumnInfo, ConnectorMetrics,
    DBType, HealthStatus, IndexInfo, QueryResult, TableInfo,
)
from backend.utils.logging import get_logger

logger = get_logger(__name__)

# ── JSON-safe type coercion ───────────────────────────────────
def _safe(v: Any) -> Any:
    if isinstance(v, Decimal):
        return float(v)
    if isinstance(v, (datetime,)):
        return v.isoformat()
    if isinstance(v, oracledb.LOB):
        return v.read()
    if isinstance(v, bytes):
        return v.decode("utf-8", errors="replace")
    return v


def _row_to_dict(cursor, row) -> Dict[str, Any]:
    return {col[0].lower(): _safe(val) for col, val in zip(cursor.description, row)}


class OracleConnector(BaseConnector):

    def __init__(self, connector_id: str, config: Dict[str, Any]):
        super().__init__(connector_id, config)
        self._pool: Optional[oracledb.AsyncConnectionPool] = None
        self.db_type = DBType.ORACLE

    # ── Lifecycle ────────────────────────────────────────────
    async def connect(self) -> None:
        for attempt in range(1, 4):
            try:
                self._pool = oracledb.create_pool_async(
                    user=self.config["user"],
                    password=self.config["password"],
                    dsn=self.config.get("dsn") or oracledb.makedsn(
                        self.config["host"],
                        self.config.get("port", 1521),
                        service_name=self.config.get("service_name"),
                        sid=self.config.get("sid"),
                    ),
                    min=2,
                    max=10,
                    increment=1,
                )
                self._connected = True
                self._connected_at = datetime.now(timezone.utc)
                logger.info("oracle_connected", connector_id=self.connector_id)
                return
            except Exception as e:
                self._record_error(str(e))
                if attempt == 3:
                    raise
                await asyncio.sleep(2 ** attempt)

    async def disconnect(self) -> None:
        if self._pool:
            await self._pool.close(force=False)
            self._connected = False
            logger.info("oracle_disconnected", connector_id=self.connector_id)

    async def test_connection(self) -> HealthStatus:
        start = time.perf_counter()
        try:
            async with self._pool.acquire() as conn:
                async with conn.cursor() as cur:
                    await cur.execute("SELECT 1 FROM dual")
                    version_row = await cur.fetchone()
                    await cur.execute("SELECT version FROM v$instance")
                    ver = (await cur.fetchone())[0]
            latency = round((time.perf_counter() - start) * 1000)
            return HealthStatus(healthy=True, latency_ms=latency, version=ver)
        except Exception as e:
            self._record_error(str(e))
            return HealthStatus(healthy=False, error=str(e))

    # ── Query execution ──────────────────────────────────────
    async def execute_query(
        self,
        sql: str,
        params: Optional[Dict] = None,
        timeout: int = 30,
        row_limit: int = 10_000,
    ) -> QueryResult:
        import uuid
        query_id = str(uuid.uuid4())[:8]
        start = time.perf_counter()
        try:
            async with self._pool.acquire() as conn:
                conn.callTimeout = timeout * 1000
                async with conn.cursor() as cur:
                    await cur.execute(sql, params or {})
                    cols = [{"name": d[0].lower(), "type": str(d[1])} for d in cur.description] if cur.description else []
                    rows_raw = await cur.fetchmany(row_limit + 1)
                    truncated = len(rows_raw) > row_limit
                    rows = [_row_to_dict(cur, r) for r in rows_raw[:row_limit]]
            duration_ms = round((time.perf_counter() - start) * 1000)
            self._record_query(duration_ms)
            return QueryResult(
                rows=rows,
                columns=cols,
                row_count=len(rows),
                duration_ms=duration_ms,
                query_id=query_id,
                truncated=truncated,
            )
        except Exception as e:
            self._record_error(str(e))
            raise

    async def execute_plsql(self, block: str, bind_vars: Optional[Dict] = None) -> Dict:
        async with self._pool.acquire() as conn:
            async with conn.cursor() as cur:
                out = bind_vars or {}
                await cur.execute(block, out)
                return {"success": True, "bind_vars": {k: v for k, v in out.items()}}

    # ── Schema browser ───────────────────────────────────────
    async def list_databases(self) -> List[str]:
        res = await self.execute_query("SELECT name FROM v$database")
        return [r["name"] for r in res.rows]

    async def list_tables(self, database: Optional[str] = None) -> List[TableInfo]:
        schema_filter = f"AND owner = UPPER('{database}')" if database else "AND owner = USER"
        sql = f"""
            SELECT t.owner, t.table_name, t.num_rows, s.bytes
            FROM dba_tables t
            LEFT JOIN dba_segments s ON s.segment_name = t.table_name AND s.owner = t.owner
            WHERE 1=1 {schema_filter}
            ORDER BY t.table_name
        """
        res = await self.execute_query(sql)
        return [
            TableInfo(
                name=r["table_name"],
                schema=r["owner"],
                row_count=r.get("num_rows"),
                size_bytes=r.get("bytes"),
            )
            for r in res.rows
        ]

    async def get_table_columns(self, table: str, schema: Optional[str] = None) -> List[ColumnInfo]:
        sql = """
            SELECT column_name, data_type, nullable,
                   data_default, column_id
            FROM dba_tab_columns
            WHERE table_name = UPPER(:table)
            AND owner = UPPER(:schema)
            ORDER BY column_id
        """
        res = await self.execute_query(sql, {"table": table, "schema": schema or self.config["user"]})
        return [
            ColumnInfo(
                name=r["column_name"].lower(),
                data_type=r["data_type"],
                nullable=r["nullable"] == "Y",
                default=r.get("data_default"),
            )
            for r in res.rows
        ]

    async def list_indexes(self, table: str) -> List[IndexInfo]:
        sql = """
            SELECT i.index_name, i.uniqueness, i.status,
                   LISTAGG(ic.column_name, ',') WITHIN GROUP (ORDER BY ic.column_position) AS cols
            FROM dba_indexes i
            JOIN dba_ind_columns ic ON ic.index_name = i.index_name AND ic.table_name = i.table_name
            WHERE i.table_name = UPPER(:table)
            GROUP BY i.index_name, i.uniqueness, i.status
        """
        res = await self.execute_query(sql, {"table": table})
        return [
            IndexInfo(
                name=r["index_name"],
                table=table,
                columns=r["cols"].split(","),
                unique=r["uniqueness"] == "UNIQUE",
                status=r["status"],
            )
            for r in res.rows
        ]

    # ── Performance analysis ─────────────────────────────────
    async def get_active_sessions(self) -> List[Dict]:
        sql = """
            SELECT s.sid, s.serial#, s.username, s.status,
                   s.wait_class, s.event, s.seconds_in_wait,
                   s.machine, s.program, q.sql_text
            FROM v$session s
            LEFT JOIN v$sql q ON q.sql_id = s.sql_id
            WHERE s.type = 'USER' AND s.status = 'ACTIVE'
            ORDER BY s.seconds_in_wait DESC
        """
        res = await self.execute_query(sql)
        return res.rows

    async def get_top_sql(self, top_n: int = 20) -> List[Dict]:
        sql = f"""
            SELECT sql_id, sql_text,
                   executions, elapsed_time/1000 AS elapsed_ms,
                   cpu_time/1000 AS cpu_ms,
                   buffer_gets, disk_reads,
                   ROUND(elapsed_time / NULLIF(executions,0)/1000, 2) AS avg_elapsed_ms
            FROM v$sql
            WHERE executions > 0 AND elapsed_time > 0
            ORDER BY elapsed_time DESC
            FETCH FIRST {top_n} ROWS ONLY
        """
        res = await self.execute_query(sql)
        return res.rows

    async def get_wait_events(self, top_n: int = 10) -> List[Dict]:
        sql = f"""
            SELECT event, wait_class, total_waits,
                   total_timeouts, time_waited,
                   ROUND(time_waited * 100 / NULLIF(SUM(time_waited) OVER (), 0), 2) AS pct
            FROM v$system_event
            WHERE wait_class != 'Idle'
            ORDER BY time_waited DESC
            FETCH FIRST {top_n} ROWS ONLY
        """
        res = await self.execute_query(sql)
        return res.rows

    async def get_locks(self) -> List[Dict]:
        sql = """
            SELECT l.sid, s.username, l.type, l.mode_held,
                   l.mode_requested, o.object_name
            FROM v$lock l
            JOIN v$session s ON s.sid = l.sid
            LEFT JOIN dba_objects o ON o.object_id = l.id1
            WHERE l.block = 1 OR l.request > 0
            ORDER BY l.sid
        """
        res = await self.execute_query(sql)
        return res.rows

    async def get_tablespace_usage(self) -> List[Dict]:
        sql = """
            SELECT df.tablespace_name,
                   ROUND(df.total_mb, 2) AS total_mb,
                   ROUND(df.total_mb - NVL(fs.free_mb, 0), 2) AS used_mb,
                   ROUND(NVL(fs.free_mb, 0), 2) AS free_mb,
                   ROUND((df.total_mb - NVL(fs.free_mb, 0)) * 100 / df.total_mb, 2) AS pct_used
            FROM (SELECT tablespace_name, SUM(bytes)/1048576 AS total_mb FROM dba_data_files GROUP BY tablespace_name) df
            LEFT JOIN (SELECT tablespace_name, SUM(bytes)/1048576 AS free_mb FROM dba_free_space GROUP BY tablespace_name) fs
            ON df.tablespace_name = fs.tablespace_name
            ORDER BY pct_used DESC
        """
        res = await self.execute_query(sql)
        return res.rows

    async def get_explain_plan(self, sql: str) -> List[Dict]:
        async with self._pool.acquire() as conn:
            async with conn.cursor() as cur:
                plan_id = f"RAXUS_{int(time.time())}"
                await cur.execute(f"EXPLAIN PLAN SET STATEMENT_ID = '{plan_id}' FOR {sql}")
                await cur.execute(f"""
                    SELECT id, parent_id, operation, options,
                           object_name, cost, cardinality, bytes,
                           cpu_cost, io_cost
                    FROM plan_table
                    WHERE statement_id = '{plan_id}'
                    ORDER BY id
                """)
                rows = await cur.fetchall()
                await cur.execute(f"DELETE FROM plan_table WHERE statement_id = '{plan_id}'")
                await conn.commit()
                return [_row_to_dict(cur, r) for r in rows]

    async def detect_slow_queries(self, threshold_ms: int = 1000) -> List[Dict]:
        sql = f"""
            SELECT sql_id, SUBSTR(sql_text, 1, 200) AS sql_text,
                   executions,
                   ROUND(elapsed_time / NULLIF(executions,0) / 1000, 2) AS avg_elapsed_ms,
                   ROUND(cpu_time / NULLIF(executions,0) / 1000, 2) AS avg_cpu_ms,
                   buffer_gets, disk_reads
            FROM v$sql
            WHERE executions > 0
              AND elapsed_time / NULLIF(executions,0) / 1000 > {threshold_ms}
            ORDER BY avg_elapsed_ms DESC
            FETCH FIRST 20 ROWS ONLY
        """
        res = await self.execute_query(sql)
        return res.rows

    # ── Metrics ──────────────────────────────────────────────
    async def get_metrics(self) -> ConnectorMetrics:
        try:
            sessions = await self.execute_query(
                "SELECT COUNT(*) AS cnt FROM v$session WHERE type='USER' AND status='ACTIVE'"
            )
            active = sessions.rows[0]["cnt"] if sessions.rows else 0
        except Exception:
            active = 0
        return ConnectorMetrics(
            connector_id=self.connector_id,
            db_type=DBType.ORACLE,
            active_connections=active,
            query_count_total=self._query_count,
            avg_query_ms=self._avg_query_ms(),
            slow_queries_count=self._slow_query_count,
            last_error=self._last_error,
            uptime_seconds=self._uptime_seconds(),
        )

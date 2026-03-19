"""
MySQL, PostgreSQL, MongoDB et Redis connectors pour Raxus.
Tous implémentent BaseConnector.
"""
import time
import asyncio
import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from backend.connectors.base import (
    BaseConnector, ColumnInfo, ConnectorMetrics, DBType,
    HealthStatus, IndexInfo, QueryResult, TableInfo,
)
from backend.utils.logging import get_logger

logger = get_logger(__name__)


# ═══════════════════════════════════════════════════════════
#  MySQL Connector
# ═══════════════════════════════════════════════════════════
class MySQLConnector(BaseConnector):

    def __init__(self, connector_id: str, config: Dict[str, Any]):
        super().__init__(connector_id, config)
        self._pool = None
        self.db_type = DBType.MYSQL

    async def connect(self) -> None:
        import aiomysql
        for attempt in range(1, 4):
            try:
                self._pool = await aiomysql.create_pool(
                    host=self.config["host"],
                    port=self.config.get("port", 3306),
                    user=self.config["user"],
                    password=self.config["password"],
                    db=self.config.get("database", ""),
                    minsize=2, maxsize=10,
                    autocommit=True,
                    connect_timeout=10,
                )
                self._connected = True
                self._connected_at = datetime.now(timezone.utc)
                logger.info("mysql_connected", connector_id=self.connector_id)
                return
            except Exception as e:
                self._record_error(str(e))
                if attempt == 3:
                    raise
                await asyncio.sleep(2 ** attempt)

    async def disconnect(self) -> None:
        if self._pool:
            self._pool.close()
            await self._pool.wait_closed()
            self._connected = False

    async def test_connection(self) -> HealthStatus:
        start = time.perf_counter()
        try:
            async with self._pool.acquire() as conn:
                async with conn.cursor() as cur:
                    await cur.execute("SELECT VERSION()")
                    ver = (await cur.fetchone())[0]
            return HealthStatus(
                healthy=True,
                latency_ms=round((time.perf_counter() - start) * 1000),
                version=ver,
            )
        except Exception as e:
            return HealthStatus(healthy=False, error=str(e))

    async def execute_query(self, sql: str, params=None, timeout=30, row_limit=10_000) -> QueryResult:
        import uuid
        qid = str(uuid.uuid4())[:8]
        start = time.perf_counter()
        try:
            async with self._pool.acquire() as conn:
                async with conn.cursor(aiomysql.DictCursor) as cur:
                    await asyncio.wait_for(cur.execute(sql, params), timeout=timeout)
                    cols = [{"name": d[0], "type": "text"} for d in (cur.description or [])]
                    rows_raw = await cur.fetchmany(row_limit + 1)
                    truncated = len(rows_raw) > row_limit
                    rows = list(rows_raw[:row_limit])
            duration_ms = round((time.perf_counter() - start) * 1000)
            self._record_query(duration_ms)
            return QueryResult(rows=rows, columns=cols, row_count=len(rows),
                               duration_ms=duration_ms, query_id=qid, truncated=truncated)
        except Exception as e:
            self._record_error(str(e))
            raise

    async def list_databases(self) -> List[str]:
        res = await self.execute_query("SHOW DATABASES")
        return [list(r.values())[0] for r in res.rows]

    async def list_tables(self, database: Optional[str] = None) -> List[TableInfo]:
        db = database or self.config.get("database", "")
        sql = f"""
            SELECT table_name, table_rows, data_length + index_length AS size_bytes
            FROM information_schema.tables
            WHERE table_schema = '{db}' AND table_type = 'BASE TABLE'
            ORDER BY table_name
        """
        res = await self.execute_query(sql)
        return [TableInfo(name=r["TABLE_NAME"] if "TABLE_NAME" in r else r.get("table_name",""),
                          schema=db, row_count=r.get("TABLE_ROWS") or r.get("table_rows"),
                          size_bytes=r.get("size_bytes")) for r in res.rows]

    async def get_table_columns(self, table: str, schema: Optional[str] = None) -> List[ColumnInfo]:
        db = schema or self.config.get("database", "")
        sql = f"""
            SELECT column_name, data_type, is_nullable, column_default, column_key
            FROM information_schema.columns
            WHERE table_schema = '{db}' AND table_name = '{table}'
            ORDER BY ordinal_position
        """
        res = await self.execute_query(sql)
        return [ColumnInfo(name=r.get("COLUMN_NAME", r.get("column_name","")),
                           data_type=r.get("DATA_TYPE", r.get("data_type","")),
                           nullable=r.get("IS_NULLABLE","YES")=="YES",
                           primary_key=r.get("COLUMN_KEY","")=="PRI") for r in res.rows]

    async def list_indexes(self, table: str) -> List[IndexInfo]:
        res = await self.execute_query(f"SHOW INDEX FROM {table}")
        grouped: Dict[str, IndexInfo] = {}
        for r in res.rows:
            name = r.get("Key_name", r.get("key_name",""))
            col = r.get("Column_name", r.get("column_name",""))
            unique = str(r.get("Non_unique", r.get("non_unique","1"))) == "0"
            if name not in grouped:
                grouped[name] = IndexInfo(name=name, table=table, columns=[], unique=unique)
            grouped[name].columns.append(col)
        return list(grouped.values())

    async def get_metrics(self) -> ConnectorMetrics:
        try:
            res = await self.execute_query("SHOW STATUS LIKE 'Threads_connected'")
            active = int(res.rows[0].get("Value", 0)) if res.rows else 0
        except Exception:
            active = 0
        return ConnectorMetrics(connector_id=self.connector_id, db_type=DBType.MYSQL,
                                active_connections=active, query_count_total=self._query_count,
                                avg_query_ms=self._avg_query_ms(),
                                slow_queries_count=self._slow_query_count,
                                last_error=self._last_error, uptime_seconds=self._uptime_seconds())


# ═══════════════════════════════════════════════════════════
#  PostgreSQL Connector
# ═══════════════════════════════════════════════════════════
class PostgreSQLConnector(BaseConnector):

    def __init__(self, connector_id: str, config: Dict[str, Any]):
        super().__init__(connector_id, config)
        self._pool = None
        self.db_type = DBType.POSTGRESQL

    async def connect(self) -> None:
        import asyncpg
        for attempt in range(1, 4):
            try:
                self._pool = await asyncpg.create_pool(
                    host=self.config["host"],
                    port=self.config.get("port", 5432),
                    user=self.config["user"],
                    password=self.config["password"],
                    database=self.config.get("database", "postgres"),
                    min_size=2, max_size=10,
                    command_timeout=30,
                )
                self._connected = True
                self._connected_at = datetime.now(timezone.utc)
                logger.info("postgresql_connected", connector_id=self.connector_id)
                return
            except Exception as e:
                self._record_error(str(e))
                if attempt == 3:
                    raise
                await asyncio.sleep(2 ** attempt)

    async def disconnect(self) -> None:
        if self._pool:
            await self._pool.close()
            self._connected = False

    async def test_connection(self) -> HealthStatus:
        start = time.perf_counter()
        try:
            async with self._pool.acquire() as conn:
                ver = await conn.fetchval("SELECT version()")
            return HealthStatus(healthy=True,
                                latency_ms=round((time.perf_counter()-start)*1000),
                                version=ver)
        except Exception as e:
            return HealthStatus(healthy=False, error=str(e))

    async def execute_query(self, sql: str, params=None, timeout=30, row_limit=10_000) -> QueryResult:
        import uuid
        qid = str(uuid.uuid4())[:8]
        start = time.perf_counter()
        try:
            async with self._pool.acquire() as conn:
                records = await asyncio.wait_for(
                    conn.fetch(sql, *(params or [])), timeout=timeout
                )
                truncated = len(records) > row_limit
                rows = [dict(r) for r in records[:row_limit]]
                cols = [{"name": k, "type": "text"} for k in (rows[0].keys() if rows else [])]
            duration_ms = round((time.perf_counter()-start)*1000)
            self._record_query(duration_ms)
            return QueryResult(rows=rows, columns=cols, row_count=len(rows),
                               duration_ms=duration_ms, query_id=qid, truncated=truncated)
        except Exception as e:
            self._record_error(str(e))
            raise

    async def list_databases(self) -> List[str]:
        res = await self.execute_query("SELECT datname FROM pg_database WHERE datistemplate = false")
        return [r["datname"] for r in res.rows]

    async def list_tables(self, database: Optional[str] = None) -> List[TableInfo]:
        sql = """
            SELECT schemaname, tablename,
                   pg_total_relation_size(schemaname||'.'||tablename) AS size_bytes
            FROM pg_tables WHERE schemaname NOT IN ('pg_catalog','information_schema')
            ORDER BY tablename
        """
        res = await self.execute_query(sql)
        return [TableInfo(name=r["tablename"], schema=r["schemaname"],
                          size_bytes=r.get("size_bytes")) for r in res.rows]

    async def get_table_columns(self, table: str, schema: Optional[str] = None) -> List[ColumnInfo]:
        sql = """
            SELECT column_name, data_type, is_nullable, column_default
            FROM information_schema.columns
            WHERE table_name = $1 AND table_schema = $2
            ORDER BY ordinal_position
        """
        res = await self.execute_query(sql, [table, schema or "public"])
        return [ColumnInfo(name=r["column_name"], data_type=r["data_type"],
                           nullable=r["is_nullable"]=="YES") for r in res.rows]

    async def list_indexes(self, table: str) -> List[IndexInfo]:
        sql = """
            SELECT indexname, indexdef,
                   ix.indisunique AS unique
            FROM pg_indexes pi
            JOIN pg_class c ON c.relname = pi.tablename
            JOIN pg_index ix ON ix.indrelid = c.oid
            JOIN pg_class ic ON ic.oid = ix.indexrelid AND ic.relname = pi.indexname
            WHERE pi.tablename = $1
        """
        res = await self.execute_query(sql, [table])
        return [IndexInfo(name=r["indexname"], table=table,
                          columns=[], unique=r.get("unique", False)) for r in res.rows]

    async def get_slow_queries(self, threshold_ms: int = 1000) -> List[Dict]:
        sql = f"""
            SELECT query, calls, total_exec_time, mean_exec_time, rows
            FROM pg_stat_statements
            WHERE mean_exec_time > {threshold_ms}
            ORDER BY mean_exec_time DESC
            LIMIT 20
        """
        res = await self.execute_query(sql)
        return res.rows

    async def get_metrics(self) -> ConnectorMetrics:
        try:
            res = await self.execute_query(
                "SELECT count(*) AS cnt FROM pg_stat_activity WHERE state = 'active'"
            )
            active = res.rows[0]["cnt"] if res.rows else 0
        except Exception:
            active = 0
        return ConnectorMetrics(connector_id=self.connector_id, db_type=DBType.POSTGRESQL,
                                active_connections=active, query_count_total=self._query_count,
                                avg_query_ms=self._avg_query_ms(),
                                slow_queries_count=self._slow_query_count,
                                last_error=self._last_error, uptime_seconds=self._uptime_seconds())


# ═══════════════════════════════════════════════════════════
#  MongoDB Connector
# ═══════════════════════════════════════════════════════════
class MongoDBConnector(BaseConnector):

    def __init__(self, connector_id: str, config: Dict[str, Any]):
        super().__init__(connector_id, config)
        self._client = None
        self.db_type = DBType.MONGODB

    async def connect(self) -> None:
        from motor.motor_asyncio import AsyncIOMotorClient
        uri = self.config.get("uri") or (
            f"mongodb://{self.config['user']}:{self.config['password']}"
            f"@{self.config['host']}:{self.config.get('port',27017)}"
        )
        self._client = AsyncIOMotorClient(uri, serverSelectionTimeoutMS=5000)
        await self._client.admin.command("ping")
        self._connected = True
        self._connected_at = datetime.now(timezone.utc)
        logger.info("mongodb_connector_connected", connector_id=self.connector_id)

    async def disconnect(self) -> None:
        if self._client:
            self._client.close()
            self._connected = False

    async def test_connection(self) -> HealthStatus:
        start = time.perf_counter()
        try:
            info = await self._client.admin.command("serverStatus")
            ver = info.get("version", "unknown")
            return HealthStatus(healthy=True,
                                latency_ms=round((time.perf_counter()-start)*1000),
                                version=ver)
        except Exception as e:
            return HealthStatus(healthy=False, error=str(e))

    async def execute_query(self, sql: str, params=None, timeout=30, row_limit=10_000) -> QueryResult:
        import uuid
        qid = str(uuid.uuid4())[:8]
        start = time.perf_counter()
        try:
            # sql is expected to be JSON: {"db":"mydb","collection":"col","pipeline":[...]}
            q = json.loads(sql)
            db = self._client[q["db"]]
            col = db[q["collection"]]
            pipeline = q.get("pipeline", [])
            cursor = col.aggregate(pipeline)
            rows = []
            async for doc in cursor:
                doc.pop("_id", None)
                rows.append(doc)
                if len(rows) >= row_limit:
                    break
            duration_ms = round((time.perf_counter()-start)*1000)
            self._record_query(duration_ms)
            cols = [{"name": k, "type": "mixed"} for k in (rows[0].keys() if rows else [])]
            return QueryResult(rows=rows, columns=cols, row_count=len(rows),
                               duration_ms=duration_ms, query_id=qid)
        except Exception as e:
            self._record_error(str(e))
            raise

    async def list_databases(self) -> List[str]:
        return await self._client.list_database_names()

    async def list_tables(self, database: Optional[str] = None) -> List[TableInfo]:
        db_name = database or self.config.get("database", "")
        db = self._client[db_name]
        names = await db.list_collection_names()
        return [TableInfo(name=n, schema=db_name) for n in names]

    async def get_table_columns(self, table: str, schema: Optional[str] = None) -> List[ColumnInfo]:
        db = self._client[schema or self.config.get("database","")]
        doc = await db[table].find_one()
        if not doc:
            return []
        doc.pop("_id", None)
        return [ColumnInfo(name=k, data_type=type(v).__name__) for k, v in doc.items()]

    async def list_indexes(self, table: str) -> List[IndexInfo]:
        db = self._client[self.config.get("database","")]
        indexes = await db[table].index_information()
        return [IndexInfo(name=name, table=table,
                          columns=[k for k, _ in info.get("key", [])],
                          unique=info.get("unique", False))
                for name, info in indexes.items()]

    async def get_metrics(self) -> ConnectorMetrics:
        try:
            status = await self._client.admin.command("serverStatus")
            active = status.get("connections", {}).get("current", 0)
        except Exception:
            active = 0
        return ConnectorMetrics(connector_id=self.connector_id, db_type=DBType.MONGODB,
                                active_connections=active, query_count_total=self._query_count,
                                avg_query_ms=self._avg_query_ms(),
                                slow_queries_count=self._slow_query_count,
                                last_error=self._last_error, uptime_seconds=self._uptime_seconds())


# ═══════════════════════════════════════════════════════════
#  Redis Connector
# ═══════════════════════════════════════════════════════════
class RedisConnector(BaseConnector):

    def __init__(self, connector_id: str, config: Dict[str, Any]):
        super().__init__(connector_id, config)
        self._client = None
        self.db_type = DBType.REDIS

    async def connect(self) -> None:
        import redis.asyncio as aioredis
        self._client = aioredis.from_url(
            self.config.get("uri") or
            f"redis://:{self.config.get('password','')}@{self.config['host']}:{self.config.get('port',6379)}/{self.config.get('db',0)}",
            decode_responses=True,
        )
        await self._client.ping()
        self._connected = True
        self._connected_at = datetime.now(timezone.utc)
        logger.info("redis_connector_connected", connector_id=self.connector_id)

    async def disconnect(self) -> None:
        if self._client:
            await self._client.aclose()
            self._connected = False

    async def test_connection(self) -> HealthStatus:
        start = time.perf_counter()
        try:
            info = await self._client.info("server")
            ver = info.get("redis_version", "unknown")
            return HealthStatus(healthy=True,
                                latency_ms=round((time.perf_counter()-start)*1000),
                                version=ver)
        except Exception as e:
            return HealthStatus(healthy=False, error=str(e))

    async def execute_query(self, sql: str, params=None, timeout=30, row_limit=10_000) -> QueryResult:
        """Redis: sql is a Redis command string e.g. 'KEYS user:*' or 'GET mykey'"""
        import uuid
        qid = str(uuid.uuid4())[:8]
        start = time.perf_counter()
        try:
            parts = sql.strip().split()
            cmd = parts[0].upper()
            args = parts[1:]
            result = await self._client.execute_command(cmd, *args)
            if isinstance(result, (list, tuple)):
                rows = [{"key": str(r)} for r in result[:row_limit]]
            elif isinstance(result, dict):
                rows = [{"field": k, "value": v} for k, v in list(result.items())[:row_limit]]
            else:
                rows = [{"result": str(result)}]
            duration_ms = round((time.perf_counter()-start)*1000)
            self._record_query(duration_ms)
            return QueryResult(rows=rows, columns=[{"name": k, "type": "text"} for k in (rows[0].keys() if rows else [])],
                               row_count=len(rows), duration_ms=duration_ms, query_id=qid)
        except Exception as e:
            self._record_error(str(e))
            raise

    async def list_databases(self) -> List[str]:
        info = await self._client.info("keyspace")
        return [k for k in info.keys()]

    async def list_tables(self, database: Optional[str] = None) -> List[TableInfo]:
        keys = await self._client.keys("*")
        types: Dict[str, int] = {}
        for k in keys:
            t = await self._client.type(k)
            types[t] = types.get(t, 0) + 1
        return [TableInfo(name=t, row_count=cnt) for t, cnt in types.items()]

    async def get_table_columns(self, table: str, schema: Optional[str] = None) -> List[ColumnInfo]:
        return [ColumnInfo(name="key", data_type="string"), ColumnInfo(name="value", data_type="mixed")]

    async def list_indexes(self, table: str) -> List[IndexInfo]:
        return []

    async def get_metrics(self) -> ConnectorMetrics:
        try:
            info = await self._client.info("clients")
            active = info.get("connected_clients", 0)
            memory = await self._client.info("memory")
        except Exception:
            active = 0
        return ConnectorMetrics(connector_id=self.connector_id, db_type=DBType.REDIS,
                                active_connections=active, query_count_total=self._query_count,
                                avg_query_ms=self._avg_query_ms(),
                                slow_queries_count=self._slow_query_count,
                                last_error=self._last_error, uptime_seconds=self._uptime_seconds())

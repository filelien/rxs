from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone
from enum import Enum


class DBType(str, Enum):
    ORACLE = "oracle"
    MYSQL = "mysql"
    POSTGRESQL = "postgresql"
    MONGODB = "mongodb"
    REDIS = "redis"
    SQLITE = "sqlite"


@dataclass
class ColumnInfo:
    name: str
    data_type: str
    nullable: bool = True
    default: Optional[str] = None
    primary_key: bool = False


@dataclass
class TableInfo:
    name: str
    schema: Optional[str] = None
    row_count: Optional[int] = None
    size_bytes: Optional[int] = None
    columns: List[ColumnInfo] = field(default_factory=list)


@dataclass
class IndexInfo:
    name: str
    table: str
    columns: List[str]
    unique: bool = False
    status: str = "VALID"


@dataclass
class QueryResult:
    rows: List[Dict[str, Any]]
    columns: List[Dict[str, str]]   # [{name, type}]
    row_count: int
    duration_ms: int
    query_id: str = ""
    truncated: bool = False         # True if row limit hit


@dataclass
class ConnectorMetrics:
    connector_id: str
    db_type: str
    active_connections: int = 0
    query_count_total: int = 0
    avg_query_ms: float = 0.0
    slow_queries_count: int = 0
    last_error: Optional[str] = None
    uptime_seconds: int = 0
    collected_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class HealthStatus:
    healthy: bool
    latency_ms: Optional[int] = None
    version: Optional[str] = None
    error: Optional[str] = None


class BaseConnector(ABC):
    """Abstract base — every DB connector must implement this interface."""

    def __init__(self, connector_id: str, config: Dict[str, Any]):
        self.connector_id = connector_id
        self.config = config
        self._connected = False
        self._query_count = 0
        self._total_duration_ms = 0
        self._slow_query_count = 0
        self._last_error: Optional[str] = None
        self._connected_at: Optional[datetime] = None

    # ── Lifecycle ────────────────────────────────────────────
    @abstractmethod
    async def connect(self) -> None: ...

    @abstractmethod
    async def disconnect(self) -> None: ...

    @abstractmethod
    async def test_connection(self) -> HealthStatus: ...

    # ── Query ────────────────────────────────────────────────
    @abstractmethod
    async def execute_query(
        self,
        sql: str,
        params: Optional[Dict] = None,
        timeout: int = 30,
        row_limit: int = 10_000,
    ) -> QueryResult: ...

    # ── Schema ───────────────────────────────────────────────
    @abstractmethod
    async def list_databases(self) -> List[str]: ...

    @abstractmethod
    async def list_tables(self, database: Optional[str] = None) -> List[TableInfo]: ...

    @abstractmethod
    async def get_table_columns(self, table: str, schema: Optional[str] = None) -> List[ColumnInfo]: ...

    @abstractmethod
    async def list_indexes(self, table: str) -> List[IndexInfo]: ...

    # ── Metrics ──────────────────────────────────────────────
    @abstractmethod
    async def get_metrics(self) -> ConnectorMetrics: ...

    # ── Health ───────────────────────────────────────────────
    async def health_check(self) -> HealthStatus:
        return await self.test_connection()

    # ── Internal helpers ─────────────────────────────────────
    def _record_query(self, duration_ms: int, slow_threshold_ms: int = 1000):
        self._query_count += 1
        self._total_duration_ms += duration_ms
        if duration_ms >= slow_threshold_ms:
            self._slow_query_count += 1

    def _record_error(self, error: str):
        self._last_error = error

    def _avg_query_ms(self) -> float:
        if self._query_count == 0:
            return 0.0
        return round(self._total_duration_ms / self._query_count, 2)

    def _uptime_seconds(self) -> int:
        if not self._connected_at:
            return 0
        return int((datetime.now(timezone.utc) - self._connected_at).total_seconds())

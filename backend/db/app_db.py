"""
Base MySQL applicative de Raxus.
Toutes les données de la plateforme (users, connexions, requêtes,
métriques, audit, tâches, chat) sont stockées ici.
"""
from __future__ import annotations

import json
import hashlib
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from contextlib import asynccontextmanager

import aiomysql
from backend.config import get_settings
from backend.utils.logging import get_logger

logger = get_logger(__name__)
_pool: aiomysql.Pool | None = None


# ── Pool lifecycle ────────────────────────────────────────────
async def init_db():
    global _pool
    s = get_settings()
    _pool = await aiomysql.create_pool(
        host=s.app_db_host,
        port=s.app_db_port,
        user=s.app_db_user,
        password=s.app_db_password,
        db=s.app_db_name,
        minsize=3,
        maxsize=20,
        autocommit=True,
        charset="utf8mb4",
        use_unicode=True,
        connect_timeout=10,
    )
    await _run_migrations()
    logger.info("app_db_connected", db=s.app_db_name)


async def close_db():
    global _pool
    if _pool:
        _pool.close()
        await _pool.wait_closed()
        logger.info("app_db_disconnected")


async def db_status() -> bool:
    try:
        async with get_conn() as conn:
            async with conn.cursor() as cur:
                await cur.execute("SELECT 1")
        return True
    except Exception:
        return False


@asynccontextmanager
async def get_conn():
    if _pool is None:
        raise RuntimeError("DB pool not initialized")
    async with _pool.acquire() as conn:
        yield conn


async def fetch_one(sql: str, params: tuple = ()) -> Optional[Dict]:
    async with get_conn() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute(sql, params)
            return await cur.fetchone()


async def fetch_all(sql: str, params: tuple = ()) -> List[Dict]:
    async with get_conn() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute(sql, params)
            return await cur.fetchall()


async def execute(sql: str, params: tuple = ()) -> int:
    """Returns lastrowid or rowcount."""
    async with get_conn() as conn:
        async with conn.cursor() as cur:
            await cur.execute(sql, params)
            return cur.lastrowid or cur.rowcount


async def execute_many(sql: str, params_list: List[tuple]):
    async with get_conn() as conn:
        async with conn.cursor() as cur:
            await cur.executemany(sql, params_list)


def _serialize(v: Any) -> Any:
    """Make value JSON-safe for storage."""
    if isinstance(v, dict) or isinstance(v, list):
        return json.dumps(v, default=str)
    if isinstance(v, datetime):
        return v.isoformat()
    return v


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def new_id() -> str:
    import uuid
    return str(uuid.uuid4())


def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()


# ── Migrations ────────────────────────────────────────────────
async def _run_migrations():
    """Run schema.sql if tables don't exist."""
    import os
    schema_path = os.path.join(os.path.dirname(__file__), "schema.sql")
    if not os.path.exists(schema_path):
        return
    with open(schema_path) as f:
        sql_content = f.read()

    # Split on ; and run each statement
    statements = [s.strip() for s in sql_content.split(";") if s.strip() and not s.strip().startswith("--")]
    async with get_conn() as conn:
        async with conn.cursor() as cur:
            for stmt in statements:
                try:
                    await cur.execute(stmt)
                except Exception as e:
                    if "already exists" not in str(e).lower() and "Duplicate" not in str(e):
                        logger.warning("migration_stmt_error", error=str(e)[:200])
    logger.info("migrations_applied")


# ════════════════════════════════════════════════════════════
#  REPOSITORIES — une fonction par domaine
# ════════════════════════════════════════════════════════════

# ── Users ─────────────────────────────────────────────────────
async def get_user_by_credentials(username: str, password: str) -> Optional[Dict]:
    return await fetch_one(
        "SELECT id, username, email, role, full_name, active FROM users WHERE username=%s AND password_hash=%s AND active=1",
        (username, hash_password(password))
    )


async def get_user_by_id(user_id: str) -> Optional[Dict]:
    return await fetch_one(
        "SELECT id, username, email, role, full_name, active, created_at FROM users WHERE id=%s",
        (user_id,)
    )


async def list_users() -> List[Dict]:
    return await fetch_all(
        "SELECT id, username, email, role, full_name, active, last_login_at, created_at FROM users ORDER BY created_at DESC"
    )


async def create_user(username: str, email: str, password: str, role: str, full_name: str = "") -> str:
    uid = new_id()
    await execute(
        "INSERT INTO users (id, username, email, password_hash, role, full_name) VALUES (%s,%s,%s,%s,%s,%s)",
        (uid, username, email, hash_password(password), role, full_name)
    )
    return uid


async def update_user_login(user_id: str):
    await execute("UPDATE users SET last_login_at=%s WHERE id=%s", (utcnow(), user_id))


async def update_user_status(user_id: str, active: bool):
    await execute("UPDATE users SET active=%s WHERE id=%s", (int(active), user_id))


# ── DB Connections ────────────────────────────────────────────
async def list_connections(only_enabled: bool = False) -> List[Dict]:
    sql = "SELECT id, name, db_type, host, port, database_name, username, description, enabled, ssh_tunnel, last_tested_at, last_test_ok, last_test_ms, created_at FROM db_connections"
    if only_enabled:
        sql += " WHERE enabled=1"
    sql += " ORDER BY name"
    return await fetch_all(sql)


async def get_connection(conn_id: str) -> Optional[Dict]:
    return await fetch_one(
        "SELECT * FROM db_connections WHERE id=%s",
        (conn_id,)
    )


async def create_connection(name: str, db_type: str, host: str, port: int,
                             database_name: str, username: str, credentials_enc: str,
                             description: str = "", created_by: str = "",
                             ssh_tunnel: bool = False, ssh_host: str = "",
                             ssh_port: int = 22, ssh_user: str = "", ssh_key_enc: str = "") -> str:
    cid = new_id()
    await execute(
        """INSERT INTO db_connections
           (id, name, db_type, host, port, database_name, username, credentials_enc,
            description, created_by, ssh_tunnel, ssh_host, ssh_port, ssh_user, ssh_key_enc)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
        (cid, name, db_type, host, port, database_name, username, credentials_enc,
         description, created_by, int(ssh_tunnel), ssh_host, ssh_port, ssh_user, ssh_key_enc)
    )
    return cid


async def update_connection_test(conn_id: str, ok: bool, latency_ms: int):
    await execute(
        "UPDATE db_connections SET last_tested_at=%s, last_test_ok=%s, last_test_ms=%s WHERE id=%s",
        (utcnow(), int(ok), latency_ms, conn_id)
    )


async def delete_connection(conn_id: str):
    await execute("DELETE FROM db_connections WHERE id=%s", (conn_id,))


async def toggle_connection(conn_id: str, enabled: bool):
    await execute("UPDATE db_connections SET enabled=%s WHERE id=%s", (int(enabled), conn_id))


# ── Query History ──────────────────────────────────────────────
async def save_query_history(query_uuid: str, user_id: str, connection_id: str,
                              sql_text: str, status: str, row_count: int = 0,
                              duration_ms: int = 0, error_msg: str = "",
                              risk_level: str = "safe"):
    sql_hash = hashlib.sha256(sql_text.encode()).hexdigest()
    await execute(
        """INSERT INTO query_history
           (query_uuid, user_id, connection_id, sql_text, sql_hash, status, row_count, duration_ms, error_msg, risk_level)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
        (query_uuid, user_id, connection_id, sql_text, sql_hash, status,
         row_count, duration_ms, error_msg, risk_level)
    )


async def get_query_history(user_id: str, connection_id: str = "", limit: int = 50, page: int = 1) -> Dict:
    conditions = ["user_id=%s"]
    params: list = [user_id]
    if connection_id:
        conditions.append("connection_id=%s")
        params.append(connection_id)
    where = " AND ".join(conditions)
    total = (await fetch_one(f"SELECT COUNT(*) as cnt FROM query_history WHERE {where}", tuple(params)))["cnt"]
    offset = (page - 1) * limit
    rows = await fetch_all(
        f"SELECT * FROM query_history WHERE {where} ORDER BY executed_at DESC LIMIT %s OFFSET %s",
        tuple(params) + (limit, offset)
    )
    return {"data": rows, "total": total, "page": page, "limit": limit}


async def get_slow_queries(threshold_ms: int = 1000, limit: int = 20) -> List[Dict]:
    return await fetch_all(
        "SELECT * FROM query_history WHERE duration_ms > %s AND status='success' ORDER BY duration_ms DESC LIMIT %s",
        (threshold_ms, limit)
    )


# ── Saved Queries ─────────────────────────────────────────────
async def save_query(user_id: str, connection_id: str, name: str, sql_text: str,
                     description: str = "", tags: list = [], is_public: bool = False) -> str:
    qid = new_id()
    await execute(
        "INSERT INTO saved_queries (id, user_id, connection_id, name, sql_text, description, tags, is_public) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
        (qid, user_id, connection_id, name, sql_text, description, json.dumps(tags), int(is_public))
    )
    return qid


async def list_saved_queries(user_id: str, connection_id: str = "") -> List[Dict]:
    if connection_id:
        return await fetch_all(
            "SELECT * FROM saved_queries WHERE (user_id=%s OR is_public=1) AND connection_id=%s ORDER BY created_at DESC",
            (user_id, connection_id)
        )
    return await fetch_all(
        "SELECT * FROM saved_queries WHERE user_id=%s OR is_public=1 ORDER BY created_at DESC",
        (user_id,)
    )


async def delete_saved_query(query_id: str, user_id: str):
    await execute("DELETE FROM saved_queries WHERE id=%s AND user_id=%s", (query_id, user_id))


# ── Metrics ────────────────────────────────────────────────────
async def save_metric(connection_id: str, server_id: str, metric_name: str,
                       metric_value: float, labels: dict = {}):
    await execute(
        "INSERT INTO metrics (connection_id, server_id, metric_name, metric_value, labels) VALUES (%s,%s,%s,%s,%s)",
        (connection_id, server_id, metric_name, metric_value, json.dumps(labels))
    )


async def get_metric_history(connection_id: str, metric_name: str, window_minutes: int = 60) -> List[Dict]:
    return await fetch_all(
        """SELECT metric_value as value, collected_at as timestamp
           FROM metrics
           WHERE connection_id=%s AND metric_name=%s
             AND collected_at >= NOW() - INTERVAL %s MINUTE
           ORDER BY collected_at ASC""",
        (connection_id, metric_name, window_minutes)
    )


async def cleanup_old_metrics(days: int = 30):
    await execute("DELETE FROM metrics WHERE collected_at < NOW() - INTERVAL %s DAY", (days,))


# ── Audit Logs ────────────────────────────────────────────────
async def write_audit_log(user_id: str, username: str, user_role: str,
                           action: str, resource_type: str = "", resource_id: str = "",
                           request_ip: str = "", user_agent: str = "",
                           payload_summary: str = "", result: str = "success",
                           risk_score: int = 0, duration_ms: int = 0):
    await execute(
        """INSERT INTO audit_logs
           (user_id, username, user_role, action, resource_type, resource_id,
            request_ip, user_agent, payload_summary, result, risk_score, duration_ms)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
        (user_id, username, user_role, action, resource_type, resource_id,
         request_ip, user_agent, payload_summary[:200], result, risk_score, duration_ms)
    )


async def get_audit_logs(user_id: str = "", action: str = "",
                          risk_min: int = 0, days: int = 7,
                          page: int = 1, limit: int = 50) -> Dict:
    conditions = ["created_at >= NOW() - INTERVAL %s DAY", "risk_score >= %s"]
    params: list = [days, risk_min]
    if user_id:
        conditions.append("user_id=%s")
        params.append(user_id)
    if action:
        conditions.append("action LIKE %s")
        params.append(f"%{action}%")
    where = " AND ".join(conditions)
    total = (await fetch_one(f"SELECT COUNT(*) as cnt FROM audit_logs WHERE {where}", tuple(params)))["cnt"]
    offset = (page - 1) * limit
    rows = await fetch_all(
        f"SELECT * FROM audit_logs WHERE {where} ORDER BY created_at DESC LIMIT %s OFFSET %s",
        tuple(params) + (limit, offset)
    )
    return {"data": rows, "total": total, "page": page, "limit": limit}


# ── Tasks ─────────────────────────────────────────────────────
async def create_task(task_id: str, name: str, task_type: str, connection_id: str = "",
                       server_id: str = "", payload: dict = {}, created_by: str = "",
                       max_retries: int = 2) -> str:
    await execute(
        """INSERT INTO tasks (id, name, type, connection_id, server_id, payload, created_by, max_retries)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
        (task_id, name, task_type, connection_id, server_id, json.dumps(payload), created_by, max_retries)
    )
    return task_id


async def update_task_status(task_id: str, status: str, output: str = "",
                              error_msg: str = "", duration_ms: int = 0):
    if status == "running":
        await execute("UPDATE tasks SET status=%s, started_at=%s WHERE id=%s", (status, utcnow(), task_id))
    else:
        await execute(
            "UPDATE tasks SET status=%s, finished_at=%s, output=%s, error_msg=%s, duration_ms=%s WHERE id=%s",
            (status, utcnow(), output[:5000] if output else "", error_msg[:2000] if error_msg else "", duration_ms, task_id)
        )


async def get_tasks(status: str = "", limit: int = 50) -> List[Dict]:
    if status:
        return await fetch_all("SELECT * FROM tasks WHERE status=%s ORDER BY created_at DESC LIMIT %s", (status, limit))
    return await fetch_all("SELECT * FROM tasks ORDER BY created_at DESC LIMIT %s", (limit,))


async def get_task(task_id: str) -> Optional[Dict]:
    return await fetch_one("SELECT * FROM tasks WHERE id=%s", (task_id,))


# ── Schedules ─────────────────────────────────────────────────
async def create_schedule(sched_id: str, name: str, task_type: str, cron_expr: str,
                           connection_id: str = "", payload: dict = {},
                           timezone: str = "UTC", created_by: str = "") -> str:
    from croniter import croniter
    next_run = croniter(cron_expr).get_next(datetime)
    await execute(
        """INSERT INTO schedules (id, name, task_type, connection_id, payload, cron_expr, timezone, next_run_at, created_by)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
        (sched_id, name, task_type, connection_id, json.dumps(payload), cron_expr, timezone, next_run, created_by)
    )
    return sched_id


async def list_schedules() -> List[Dict]:
    return await fetch_all("SELECT * FROM schedules ORDER BY next_run_at ASC")


async def pause_schedule(sched_id: str, paused: bool):
    await execute("UPDATE schedules SET paused=%s WHERE id=%s", (int(paused), sched_id))


# ── Servers (agents) ──────────────────────────────────────────
async def upsert_server(server_id: str, hostname: str, ip: str = "",
                         agent_version: str = "1.0", os_info: dict = {}):
    await execute(
        """INSERT INTO servers (id, hostname, ip_address, agent_version, os_info, status, last_seen_at)
           VALUES (%s,%s,%s,%s,%s,'online',%s)
           ON DUPLICATE KEY UPDATE
             hostname=%s, ip_address=%s, agent_version=%s, os_info=%s,
             status='online', last_seen_at=%s""",
        (server_id, hostname, ip, agent_version, json.dumps(os_info), utcnow(),
         hostname, ip, agent_version, json.dumps(os_info), utcnow())
    )


async def list_servers() -> List[Dict]:
    return await fetch_all("SELECT * FROM servers ORDER BY last_seen_at DESC")


async def mark_offline_servers():
    """Mark servers that haven't sent heartbeat in 90s."""
    await execute(
        "UPDATE servers SET status='offline' WHERE last_seen_at < NOW() - INTERVAL 90 SECOND AND status='online'"
    )


# ── Chat ──────────────────────────────────────────────────────
async def create_chat_session(session_id: str, user_id: str, connection_id: str = "") -> str:
    await execute(
        "INSERT INTO chat_sessions (id, user_id, connection_id) VALUES (%s,%s,%s)",
        (session_id, user_id, connection_id)
    )
    return session_id


async def save_chat_message(session_id: str, role: str, content: str,
                             sql_generated: str = "", intent: str = "", duration_ms: int = 0):
    await execute(
        """INSERT INTO chat_messages (session_id, role, content, sql_generated, intent, duration_ms)
           VALUES (%s,%s,%s,%s,%s,%s)""",
        (session_id, role, content, sql_generated, intent, duration_ms)
    )
    await execute("UPDATE chat_sessions SET last_msg_at=%s WHERE id=%s", (utcnow(), session_id))
    # Auto-title from first user message
    first = await fetch_one("SELECT content FROM chat_messages WHERE session_id=%s AND role='user' LIMIT 1", (session_id,))
    if first:
        title = first["content"][:100]
        await execute("UPDATE chat_sessions SET title=%s WHERE id=%s AND title IS NULL", (title, session_id))


async def get_chat_sessions(user_id: str) -> List[Dict]:
    return await fetch_all(
        "SELECT id, title, connection_id, created_at, last_msg_at FROM chat_sessions WHERE user_id=%s ORDER BY last_msg_at DESC LIMIT 30",
        (user_id,)
    )


async def get_chat_history(session_id: str) -> List[Dict]:
    return await fetch_all(
        "SELECT role, content, sql_generated, intent, duration_ms, created_at FROM chat_messages WHERE session_id=%s ORDER BY created_at ASC",
        (session_id,)
    )


# ── Alert Rules ───────────────────────────────────────────────
async def list_alert_rules() -> List[Dict]:
    return await fetch_all("SELECT * FROM alert_rules ORDER BY created_at DESC")


async def create_alert_rule(name: str, metric_name: str, condition_op: str,
                             threshold: float, severity: str = "warning",
                             duration_minutes: int = 1, cooldown_minutes: int = 30,
                             notify_channels: list = ["email"], created_by: str = "") -> str:
    rid = new_id()
    await execute(
        """INSERT INTO alert_rules (id, name, metric_name, condition_op, threshold, severity,
           duration_minutes, cooldown_minutes, notify_channels, created_by)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
        (rid, name, metric_name, condition_op, threshold, severity,
         duration_minutes, cooldown_minutes, json.dumps(notify_channels), created_by)
    )
    return rid


async def save_alert_event(rule_id: str, connection_id: str, server_id: str,
                            severity: str, metric_name: str, metric_value: float,
                            threshold: float, message: str):
    await execute(
        """INSERT INTO alert_events (rule_id, connection_id, server_id, severity,
           metric_name, metric_value, threshold, message)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
        (rule_id, connection_id, server_id, severity, metric_name, metric_value, threshold, message)
    )


async def get_active_alerts() -> List[Dict]:
    return await fetch_all(
        """SELECT ae.*, ar.name as rule_name FROM alert_events ae
           JOIN alert_rules ar ON ar.id=ae.rule_id
           WHERE ae.status='active' ORDER BY ae.fired_at DESC LIMIT 50"""
    )

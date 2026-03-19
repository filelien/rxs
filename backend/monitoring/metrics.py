"""
Monitoring Raxus — Phase 5
- MetricsCollector : scraping toutes les 30s
- PrometheusExporter : endpoint /metrics
- AlertEngine : règles configurables + notifications
"""
import asyncio
import smtplib
import time
from datetime import datetime, timezone, timedelta
from email.mime.text import MIMEText
from typing import Dict, List, Optional, Any

import httpx
from prometheus_client import (
    CollectorRegistry, Gauge, Counter, Histogram,
    generate_latest, CONTENT_TYPE_LATEST,
)
from pydantic import BaseModel

from backend.connectors.registry import ConnectorRegistry
from backend.utils.database import get_db
from backend.utils.logging import get_logger
from backend.config import get_settings

logger = get_logger(__name__)
settings = get_settings()

# ── Prometheus metrics registry ───────────────────────────────
prom_registry = CollectorRegistry()

DB_CONNECTIONS = Gauge("raxus_db_connections_active", "Active DB connections",
                       ["connector_id", "db_type"], registry=prom_registry)
DB_QUERY_DURATION = Histogram("raxus_db_query_duration_ms", "Query duration in ms",
                               ["connector_id"],
                               buckets=[50, 100, 250, 500, 1000, 2000, 5000, 10000],
                               registry=prom_registry)
DB_SLOW_QUERIES = Counter("raxus_db_slow_queries_total", "Slow query count",
                           ["connector_id"], registry=prom_registry)
DB_ERRORS = Counter("raxus_db_errors_total", "DB errors",
                     ["connector_id", "error_type"], registry=prom_registry)
DB_UPTIME = Gauge("raxus_db_uptime_seconds", "Connector uptime",
                   ["connector_id"], registry=prom_registry)

SERVER_CPU = Gauge("raxus_server_cpu_usage_percent", "Server CPU %",
                   ["server_id", "hostname"], registry=prom_registry)
SERVER_MEMORY = Gauge("raxus_server_memory_usage_bytes", "Server memory bytes",
                      ["server_id", "type"], registry=prom_registry)
SERVER_DISK = Gauge("raxus_server_disk_usage_bytes", "Server disk bytes",
                    ["server_id", "mount"], registry=prom_registry)


# ── MetricsCollector ──────────────────────────────────────────
class MetricsCollector:
    """Scrape all registered connectors every N seconds and store time-series."""

    def __init__(self, interval: int = 30):
        self.interval = interval
        self._running = False
        self._task: Optional[asyncio.Task] = None

    async def start(self):
        self._running = True
        self._task = asyncio.create_task(self._loop())
        logger.info("metrics_collector_started", interval=self.interval)

    async def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()

    async def _loop(self):
        while self._running:
            try:
                await self.collect_all()
            except Exception as e:
                logger.error("metrics_collect_error", error=str(e))
            await asyncio.sleep(self.interval)

    async def collect_all(self):
        for cid, connector in ConnectorRegistry._connectors.items():
            try:
                metrics = await asyncio.wait_for(connector.get_metrics(), timeout=10)
                # Update Prometheus gauges
                DB_CONNECTIONS.labels(connector_id=cid, db_type=metrics.db_type).set(metrics.active_connections)
                DB_QUERY_DURATION.labels(connector_id=cid).observe(metrics.avg_query_ms)
                DB_UPTIME.labels(connector_id=cid).set(metrics.uptime_seconds)
                if metrics.slow_queries_count > 0:
                    DB_SLOW_QUERIES.labels(connector_id=cid).inc(metrics.slow_queries_count)
                # Persist time-series to MongoDB
                await self._persist(cid, metrics.db_type, {
                    "active_connections": metrics.active_connections,
                    "avg_query_ms": metrics.avg_query_ms,
                    "slow_queries_count": metrics.slow_queries_count,
                    "uptime_seconds": metrics.uptime_seconds,
                })
                # Check alert rules
                await alert_engine.evaluate(cid, {
                    "cpu": None,
                    "active_connections": metrics.active_connections,
                    "avg_query_ms": metrics.avg_query_ms,
                    "slow_queries": metrics.slow_queries_count,
                })
            except Exception as e:
                DB_ERRORS.labels(connector_id=cid, error_type="collect").inc()
                logger.warning("metrics_collect_connector_error", connector_id=cid, error=str(e))

    async def _persist(self, connector_id: str, db_type: str, values: Dict):
        try:
            db = get_db()
            await db.metrics.insert_one({
                "connector_id": connector_id,
                "db_type": db_type,
                "values": values,
                "timestamp": datetime.now(timezone.utc),
            })
        except Exception as e:
            logger.error("metrics_persist_error", error=str(e))

    async def get_history(
        self,
        connector_id: str,
        metric_key: str,
        window_minutes: int = 60,
    ) -> List[Dict]:
        db = get_db()
        since = datetime.now(timezone.utc) - timedelta(minutes=window_minutes)
        cursor = db.metrics.find(
            {"connector_id": connector_id, "timestamp": {"$gte": since}},
            {"timestamp": 1, f"values.{metric_key}": 1, "_id": 0}
        ).sort("timestamp", 1)
        return [
            {"timestamp": d["timestamp"].isoformat(), "value": d["values"].get(metric_key)}
            async for d in cursor
        ]

    def prometheus_output(self) -> bytes:
        return generate_latest(prom_registry)

    def prometheus_content_type(self) -> str:
        return CONTENT_TYPE_LATEST


# ── Alert Engine ──────────────────────────────────────────────
class AlertRule(BaseModel):
    rule_id: str
    name: str
    metric: str                   # e.g. "avg_query_ms", "cpu", "active_connections"
    condition: str                # ">", "<", "==", "!="
    threshold: float
    duration_minutes: int = 1     # must be true for N minutes
    severity: str = "warning"     # info | warning | critical
    notify: List[str] = ["email"] # email | webhook | slack
    cooldown_minutes: int = 30
    enabled: bool = True


DEFAULT_RULES: List[Dict] = [
    {"rule_id":"r1","name":"High avg query time","metric":"avg_query_ms",
     "condition":">","threshold":1000,"duration_minutes":2,"severity":"warning","notify":["email","slack"],"cooldown_minutes":30,"enabled":True},
    {"rule_id":"r2","name":"Too many slow queries","metric":"slow_queries",
     "condition":">","threshold":10,"duration_minutes":1,"severity":"warning","notify":["slack"],"cooldown_minutes":15,"enabled":True},
    {"rule_id":"r3","name":"High CPU (server)","metric":"cpu",
     "condition":">","threshold":85,"duration_minutes":5,"severity":"critical","notify":["email","slack"],"cooldown_minutes":30,"enabled":True},
]


class AlertEngine:
    def __init__(self):
        self._rules: List[AlertRule] = [AlertRule(**r) for r in DEFAULT_RULES]
        self._last_fired: Dict[str, datetime] = {}  # rule_id → last fire time
        self._breach_start: Dict[str, datetime] = {}  # rule_id:connector → breach start

    def add_rule(self, rule: AlertRule):
        self._rules.append(rule)

    def get_rules(self) -> List[AlertRule]:
        return self._rules

    async def evaluate(self, connector_id: str, metrics: Dict[str, Any]):
        for rule in self._rules:
            if not rule.enabled:
                continue
            value = metrics.get(rule.metric)
            if value is None:
                continue
            breach_key = f"{rule.rule_id}:{connector_id}"
            is_breach = self._check_condition(value, rule.condition, rule.threshold)

            if is_breach:
                if breach_key not in self._breach_start:
                    self._breach_start[breach_key] = datetime.now(timezone.utc)
                breach_duration = (datetime.now(timezone.utc) - self._breach_start[breach_key]).total_seconds() / 60
                if breach_duration >= rule.duration_minutes:
                    await self._fire_alert(rule, connector_id, value)
            else:
                self._breach_start.pop(breach_key, None)

    def _check_condition(self, value: float, condition: str, threshold: float) -> bool:
        ops = {">": value > threshold, "<": value < threshold,
               "==": value == threshold, "!=": value != threshold}
        return ops.get(condition, False)

    async def _fire_alert(self, rule: AlertRule, connector_id: str, value: float):
        fire_key = f"{rule.rule_id}:{connector_id}"
        last = self._last_fired.get(fire_key)
        if last:
            elapsed = (datetime.now(timezone.utc) - last).total_seconds() / 60
            if elapsed < rule.cooldown_minutes:
                return
        self._last_fired[fire_key] = datetime.now(timezone.utc)
        msg = (f"[{rule.severity.upper()}] {rule.name} — "
               f"Connector: {connector_id} | {rule.metric}={value} (threshold {rule.condition} {rule.threshold})")
        logger.warning("alert_fired", rule=rule.name, connector_id=connector_id, value=value)
        await self._persist_alert(rule, connector_id, value, msg)
        for channel in rule.notify:
            try:
                if channel == "email":
                    await self._notify_email(rule.severity, rule.name, msg)
                elif channel == "webhook":
                    await self._notify_webhook(rule, connector_id, value, msg)
                elif channel == "slack":
                    await self._notify_slack(msg, rule.severity)
            except Exception as e:
                logger.error("alert_notify_error", channel=channel, error=str(e))

    async def _persist_alert(self, rule: AlertRule, connector_id: str, value: float, msg: str):
        try:
            db = get_db()
            await db.alerts.insert_one({
                "rule_id": rule.rule_id,
                "rule_name": rule.name,
                "connector_id": connector_id,
                "severity": rule.severity,
                "metric": rule.metric,
                "value": value,
                "threshold": rule.threshold,
                "message": msg,
                "status": "active",
                "fired_at": datetime.now(timezone.utc),
            })
        except Exception as e:
            logger.error("alert_persist_error", error=str(e))

    async def _notify_email(self, severity: str, subject: str, body: str):
        if not settings.smtp_host:
            return
        msg = MIMEText(body)
        msg["Subject"] = f"[Raxus Alert {severity.upper()}] {subject}"
        msg["From"] = settings.smtp_from
        msg["To"] = settings.smtp_user
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as server:
            server.starttls()
            server.login(settings.smtp_user, settings.smtp_password)
            server.send_message(msg)

    async def _notify_webhook(self, rule: AlertRule, connector_id: str, value: float, msg: str):
        webhook_url = getattr(settings, "alert_webhook_url", None)
        if not webhook_url:
            return
        async with httpx.AsyncClient() as client:
            await client.post(webhook_url, json={
                "rule_id": rule.rule_id,
                "rule_name": rule.name,
                "connector_id": connector_id,
                "severity": rule.severity,
                "value": value,
                "threshold": rule.threshold,
                "message": msg,
                "fired_at": datetime.now(timezone.utc).isoformat(),
            }, timeout=10)

    async def _notify_slack(self, msg: str, severity: str):
        slack_url = getattr(settings, "slack_webhook_url", None)
        if not slack_url:
            return
        emoji = {"critical": ":red_circle:", "warning": ":warning:", "info": ":information_source:"}.get(severity, "")
        async with httpx.AsyncClient() as client:
            await client.post(slack_url, json={"text": f"{emoji} {msg}"}, timeout=10)

    async def get_active_alerts(self) -> List[Dict]:
        db = get_db()
        cursor = db.alerts.find({"status": "active"}).sort("fired_at", -1).limit(50)
        docs = [d async for d in cursor]
        for d in docs:
            d["_id"] = str(d["_id"])
        return docs


# Singletons
metrics_collector = MetricsCollector(interval=settings.metrics_scrape_interval_seconds)
alert_engine = AlertEngine()

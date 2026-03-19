"""Router: /monitoring — Métriques, alertes, historique — tout sur MySQL"""
from fastapi import APIRouter, Response, Depends
from typing import Optional, Dict
from backend.monitoring.metrics import metrics_collector, alert_engine
from backend.db import app_db
from backend.dependencies import get_current_user, require_permission

router = APIRouter()


@router.get("/metrics/prometheus")
async def prometheus_metrics():
    """Endpoint Prometheus scraping — pas d'auth pour compatibilité."""
    content = metrics_collector.prometheus_output()
    return Response(content=content, media_type=metrics_collector.prometheus_content_type())


@router.get("/connectors")
async def connectors_summary(user: Dict = Depends(get_current_user)):
    from backend.connectors.registry import ConnectorRegistry
    return ConnectorRegistry.list_all()


@router.get("/metrics/{connector_id}/history")
async def metric_history(
    connector_id: str,
    metric: str = "avg_query_ms",
    window: int = 60,
    user: Dict = Depends(get_current_user),
):
    """Historique time-series depuis MySQL."""
    rows = await app_db.get_metric_history(connector_id, metric, window)
    for r in rows:
        if r.get("timestamp") and hasattr(r["timestamp"], "isoformat"):
            r["timestamp"] = r["timestamp"].isoformat()
    return rows


@router.get("/alerts")
async def active_alerts(user: Dict = Depends(get_current_user)):
    """Alertes actives depuis MySQL."""
    rows = await app_db.get_active_alerts()
    for r in rows:
        if r.get("fired_at") and hasattr(r["fired_at"], "isoformat"):
            r["fired_at"] = r["fired_at"].isoformat()
    return rows


@router.get("/rules")
async def list_alert_rules(user: Dict = Depends(require_permission("monitoring", "read"))):
    rows = await app_db.list_alert_rules()
    for r in rows:
        if r.get("created_at") and hasattr(r["created_at"], "isoformat"):
            r["created_at"] = r["created_at"].isoformat()
    return rows


@router.post("/rules", status_code=201)
async def create_alert_rule(body: dict, user: Dict = Depends(require_permission("monitoring", "configure_alerts"))):
    rid = await app_db.create_alert_rule(
        name=body["name"],
        metric_name=body["metric_name"],
        condition_op=body.get("condition_op", ">"),
        threshold=float(body["threshold"]),
        severity=body.get("severity", "warning"),
        duration_minutes=body.get("duration_minutes", 1),
        cooldown_minutes=body.get("cooldown_minutes", 30),
        notify_channels=body.get("notify_channels", ["email"]),
        created_by=user["user_id"],
    )
    # Register in in-memory alert engine too
    from backend.monitoring.metrics import AlertRule
    alert_engine.add_rule(AlertRule(
        rule_id=rid, name=body["name"],
        metric=body["metric_name"],
        condition=body.get("condition_op", ">"),
        threshold=float(body["threshold"]),
        severity=body.get("severity", "warning"),
    ))
    return {"id": rid}


@router.patch("/alerts/{alert_id}/acknowledge")
async def acknowledge_alert(alert_id: int, user: Dict = Depends(get_current_user)):
    await app_db.execute(
        "UPDATE alert_events SET status='acknowledged', ack_by=%s WHERE id=%s",
        (user["user_id"], alert_id),
    )
    return {"message": "Alert acknowledged"}


@router.patch("/alerts/{alert_id}/resolve")
async def resolve_alert(alert_id: int, user: Dict = Depends(get_current_user)):
    from datetime import datetime, timezone
    await app_db.execute(
        "UPDATE alert_events SET status='resolved', resolved_at=%s WHERE id=%s",
        (datetime.now(timezone.utc), alert_id),
    )
    return {"message": "Alert resolved"}


@router.get("/dashboard")
async def monitoring_dashboard(user: Dict = Depends(get_current_user)):
    """Snapshot complet pour le dashboard — un seul appel."""
    from backend.connectors.registry import ConnectorRegistry
    connectors = ConnectorRegistry.list_all()
    alerts = await app_db.get_active_alerts()
    slow_queries = await app_db.get_slow_queries(threshold_ms=1000, limit=10)
    servers = await app_db.list_servers()

    # Serialize datetimes
    for r in alerts:
        if r.get("fired_at") and hasattr(r["fired_at"], "isoformat"):
            r["fired_at"] = r["fired_at"].isoformat()
    for r in slow_queries:
        if r.get("executed_at") and hasattr(r["executed_at"], "isoformat"):
            r["executed_at"] = r["executed_at"].isoformat()
    for r in servers:
        for k in ("last_seen_at", "created_at", "updated_at"):
            if r.get(k) and hasattr(r[k], "isoformat"):
                r[k] = r[k].isoformat()

    return {
        "connectors": connectors,
        "alerts": alerts[:10],
        "slow_queries": slow_queries,
        "servers": servers,
        "summary": {
            "total_connectors": len(connectors),
            "active_connectors": sum(1 for c in connectors if c.get("connected")),
            "critical_alerts": sum(1 for a in alerts if a.get("severity") == "critical"),
            "warning_alerts": sum(1 for a in alerts if a.get("severity") == "warning"),
            "slow_queries_count": len(slow_queries),
            "online_servers": sum(1 for s in servers if s.get("status") == "online"),
        },
    }

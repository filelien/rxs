"""
Few-shot store : stocke les paires (question → SQL approuvées) pour améliorer NL2SQL.
Rapport d'audit : génère un rapport JSON/HTML hebdomadaire.
"""
import json
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Optional

from backend.db import app_db
from backend.utils.logging import get_logger

logger = get_logger(__name__)


# ════════════════════════════════════════════════════════════
#  FEW-SHOT STORE
# ════════════════════════════════════════════════════════════

class FewShotStore:
    """
    Stocke les paires (question NL, SQL validé) pour améliorer NL2SQL.
    Persisté dans MySQL : table few_shot_examples (créée à la demande).
    """

    async def _ensure_table(self):
        """Crée la table si elle n'existe pas."""
        await app_db.execute("""
            CREATE TABLE IF NOT EXISTS few_shot_examples (
                id          VARCHAR(36)  NOT NULL PRIMARY KEY,
                question    TEXT         NOT NULL,
                sql_text    TEXT         NOT NULL,
                connector_id VARCHAR(36),
                db_type     VARCHAR(50),
                user_id     VARCHAR(36),
                approved    BOOLEAN      NOT NULL DEFAULT TRUE,
                used_count  INT          NOT NULL DEFAULT 0,
                created_at  DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
                INDEX idx_db_type (db_type),
                INDEX idx_connector (connector_id)
            )
        """)

    async def add_example(
        self,
        question: str,
        sql: str,
        connector_id: str,
        db_type: str,
        user_id: str,
    ) -> str:
        await self._ensure_table()
        from backend.models.base import new_id
        eid = new_id()
        await app_db.execute(
            """INSERT INTO few_shot_examples
               (id, question, sql_text, connector_id, db_type, user_id)
               VALUES (%s,%s,%s,%s,%s,%s)""",
            (eid, question, sql, connector_id, db_type, user_id),
        )
        logger.info("few_shot_added", id=eid, db_type=db_type)
        return eid

    async def get_examples(
        self,
        db_type: str,
        connector_id: Optional[str] = None,
        top_n: int = 3,
    ) -> List[Dict]:
        """Récupère les N meilleurs exemples pour un type de DB."""
        try:
            await self._ensure_table()
            if connector_id:
                rows = await app_db.fetch_all(
                    """SELECT question, sql_text FROM few_shot_examples
                       WHERE db_type=%s AND connector_id=%s AND approved=1
                       ORDER BY used_count DESC, created_at DESC LIMIT %s""",
                    (db_type, connector_id, top_n),
                )
            else:
                rows = await app_db.fetch_all(
                    """SELECT question, sql_text FROM few_shot_examples
                       WHERE db_type=%s AND approved=1
                       ORDER BY used_count DESC, created_at DESC LIMIT %s""",
                    (db_type, top_n),
                )
            return rows
        except Exception as e:
            logger.error("few_shot_get_failed", error=str(e))
            return []

    def format_for_prompt(self, examples: List[Dict]) -> str:
        """Formate les exemples pour injection dans le prompt LLM."""
        if not examples:
            return ""
        lines = ["Exemples de requêtes similaires validées :"]
        for i, ex in enumerate(examples, 1):
            lines.append(f"\nExemple {i}:")
            lines.append(f"  Question: {ex['question']}")
            lines.append(f"  SQL: {ex['sql_text']}")
        return "\n".join(lines)

    async def increment_usage(self, example_id: str):
        try:
            await self._ensure_table()
            await app_db.execute(
                "UPDATE few_shot_examples SET used_count=used_count+1 WHERE id=%s",
                (example_id,),
            )
        except Exception:
            pass

    async def list_all(self, db_type: Optional[str] = None) -> List[Dict]:
        await self._ensure_table()
        if db_type:
            rows = await app_db.fetch_all(
                "SELECT * FROM few_shot_examples WHERE db_type=%s ORDER BY created_at DESC",
                (db_type,)
            )
        else:
            rows = await app_db.fetch_all("SELECT * FROM few_shot_examples ORDER BY created_at DESC")
        for r in rows:
            if r.get("created_at") and hasattr(r["created_at"], "isoformat"):
                r["created_at"] = r["created_at"].isoformat()
        return rows

    async def delete(self, example_id: str):
        await app_db.execute("DELETE FROM few_shot_examples WHERE id=%s", (example_id,))


few_shot_store = FewShotStore()


# ════════════════════════════════════════════════════════════
#  RAPPORT D'AUDIT AUTOMATISÉ
# ════════════════════════════════════════════════════════════

class AuditReportService:
    """Génère des rapports d'audit périodiques (JSON + HTML)."""

    async def generate_report(self, days: int = 7) -> Dict:
        """Génère un rapport complet sur les N derniers jours."""
        since = datetime.now(timezone.utc) - timedelta(days=days)

        # Stats globales
        total_logs = (await app_db.fetch_one(
            "SELECT COUNT(*) as cnt FROM audit_logs WHERE created_at >= %s", (since,)
        ) or {}).get("cnt", 0)

        # Top actions
        top_actions = await app_db.fetch_all(
            """SELECT action, COUNT(*) as count,
               SUM(CASE WHEN result='failure' THEN 1 ELSE 0 END) as failures
               FROM audit_logs WHERE created_at >= %s
               GROUP BY action ORDER BY count DESC LIMIT 10""",
            (since,)
        )

        # Top users
        top_users = await app_db.fetch_all(
            """SELECT username, COUNT(*) as count,
               MAX(created_at) as last_activity,
               SUM(risk_score) as total_risk
               FROM audit_logs WHERE created_at >= %s AND username != ''
               GROUP BY username ORDER BY count DESC LIMIT 10""",
            (since,)
        )
        for r in top_users:
            if r.get("last_activity") and hasattr(r["last_activity"], "isoformat"):
                r["last_activity"] = r["last_activity"].isoformat()

        # High risk events
        high_risk = await app_db.fetch_all(
            """SELECT username, action, request_ip, risk_score, result, created_at
               FROM audit_logs WHERE created_at >= %s AND risk_score >= 50
               ORDER BY risk_score DESC LIMIT 20""",
            (since,)
        )
        for r in high_risk:
            if r.get("created_at") and hasattr(r["created_at"], "isoformat"):
                r["created_at"] = r["created_at"].isoformat()

        # Failures
        failures = await app_db.fetch_all(
            """SELECT username, action, request_ip, created_at
               FROM audit_logs WHERE created_at >= %s AND result='failure'
               ORDER BY created_at DESC LIMIT 15""",
            (since,)
        )
        for r in failures:
            if r.get("created_at") and hasattr(r["created_at"], "isoformat"):
                r["created_at"] = r["created_at"].isoformat()

        # Slow queries
        slow_queries = await app_db.fetch_all(
            """SELECT sql_text, duration_ms, connection_id, executed_at
               FROM query_history WHERE duration_ms > 1000 AND executed_at >= %s
               ORDER BY duration_ms DESC LIMIT 10""",
            (since,)
        )
        for r in slow_queries:
            if r.get("executed_at") and hasattr(r["executed_at"], "isoformat"):
                r["executed_at"] = r["executed_at"].isoformat()

        # Query stats
        query_stats = (await app_db.fetch_one(
            """SELECT COUNT(*) as total,
               SUM(CASE WHEN status='success' THEN 1 ELSE 0 END) as success,
               SUM(CASE WHEN status='error' THEN 1 ELSE 0 END) as errors,
               SUM(CASE WHEN status='blocked' THEN 1 ELSE 0 END) as blocked,
               AVG(duration_ms) as avg_duration_ms,
               MAX(duration_ms) as max_duration_ms
               FROM query_history WHERE executed_at >= %s""",
            (since,)
        ) or {})

        report = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "period_days": days,
            "period_from": since.isoformat(),
            "summary": {
                "total_audit_events": total_logs,
                "high_risk_events": len(high_risk),
                "total_failures": len(failures),
                "total_queries": query_stats.get("total", 0),
                "query_success_rate": round(
                    (query_stats.get("success", 0) / max(query_stats.get("total", 1), 1)) * 100, 1
                ),
                "avg_query_ms": round(float(query_stats.get("avg_duration_ms") or 0), 1),
                "max_query_ms": query_stats.get("max_duration_ms", 0),
            },
            "top_actions": top_actions,
            "top_users": top_users,
            "high_risk_events": high_risk,
            "failures": failures,
            "slow_queries": slow_queries,
        }
        return report

    def to_html(self, report: Dict) -> str:
        """Génère un rapport HTML lisible."""
        s = report["summary"]
        dt = report["generated_at"][:10]
        return f"""<!DOCTYPE html>
<html lang="fr">
<head><meta charset="UTF-8">
<title>Rapport Audit Raxus — {dt}</title>
<style>
body{{font-family:'Segoe UI',sans-serif;background:#05080f;color:#e2e8f0;padding:32px;max-width:1000px;margin:0 auto}}
h1{{color:#3b8ef3;font-size:24px;margin-bottom:4px}}
.meta{{color:#3d5a7a;font-size:13px;margin-bottom:32px}}
.kpi-grid{{display:grid;grid-template-columns:repeat(4,1fr);gap:16px;margin-bottom:32px}}
.kpi{{background:#0d1425;border:1px solid #1a2640;border-radius:10px;padding:16px 20px}}
.kpi-label{{font-size:11px;color:#3d5a7a;text-transform:uppercase;letter-spacing:.06em;margin-bottom:6px}}
.kpi-value{{font-size:26px;font-weight:700;color:#f0f4ff}}
.kpi-value.green{{color:#22c55e}}.kpi-value.red{{color:#ef4444}}.kpi-value.amber{{color:#f59e0b}}
h2{{font-size:15px;color:#8ba3c7;margin:24px 0 12px;border-bottom:1px solid #1a2640;padding-bottom:8px}}
table{{width:100%;border-collapse:collapse;font-size:13px;margin-bottom:24px}}
th{{text-align:left;padding:8px 12px;font-size:11px;color:#3d5a7a;text-transform:uppercase;letter-spacing:.06em;border-bottom:1px solid #1a2640}}
td{{padding:8px 12px;border-bottom:1px solid #1a2640;color:#8ba3c7}}
td.primary{{color:#e2e8f0;font-weight:500}}
.badge{{font-size:10px;padding:2px 8px;border-radius:4px;font-weight:700}}
.badge-red{{background:rgba(239,68,68,.15);color:#ef4444}}
.badge-green{{background:rgba(34,197,94,.15);color:#22c55e}}
.badge-amber{{background:rgba(245,158,11,.15);color:#f59e0b}}
.footer{{margin-top:40px;padding-top:16px;border-top:1px solid #1a2640;font-size:12px;color:#3d5a7a;text-align:center}}
</style></head>
<body>
<h1>Rapport d'Audit Raxus</h1>
<div class="meta">Généré le {report['generated_at'][:19].replace('T',' ')} UTC · Période : {report['period_days']} jours</div>

<div class="kpi-grid">
  <div class="kpi"><div class="kpi-label">Événements audit</div><div class="kpi-value">{s['total_audit_events']}</div></div>
  <div class="kpi"><div class="kpi-label">Risque élevé</div><div class="kpi-value {'red' if s['high_risk_events']>0 else 'green'}">{s['high_risk_events']}</div></div>
  <div class="kpi"><div class="kpi-label">Taux succès requêtes</div><div class="kpi-value {'green' if s['query_success_rate']>90 else 'amber'}">{s['query_success_rate']}%</div></div>
  <div class="kpi"><div class="kpi-label">Latence moy. SQL</div><div class="kpi-value {'amber' if s['avg_query_ms']>500 else 'green'}">{s['avg_query_ms']}ms</div></div>
</div>

<h2>Top actions</h2>
<table><thead><tr><th>Action</th><th>Occurrences</th><th>Échecs</th></tr></thead><tbody>
{''.join(f"<tr><td class='primary'>{r['action']}</td><td>{r['count']}</td><td>{'<span class=\"badge badge-red\">' + str(r['failures']) + '</span>' if r['failures'] else '—'}</td></tr>" for r in report['top_actions'])}
</tbody></table>

<h2>Top utilisateurs</h2>
<table><thead><tr><th>Utilisateur</th><th>Actions</th><th>Risque total</th><th>Dernière activité</th></tr></thead><tbody>
{''.join(f"<tr><td class='primary'>{r['username']}</td><td>{r['count']}</td><td>{'<span class=\"badge badge-red\">' + str(r['total_risk']) + '</span>' if (r['total_risk'] or 0)>100 else str(r['total_risk'] or 0)}</td><td style='font-size:11px'>{str(r.get('last_activity',''))[:16]}</td></tr>" for r in report['top_users'])}
</tbody></table>

<h2>Événements à risque élevé (score ≥ 50)</h2>
<table><thead><tr><th>Utilisateur</th><th>Action</th><th>IP</th><th>Score</th><th>Résultat</th><th>Date</th></tr></thead><tbody>
{''.join(f"<tr><td class='primary'>{r['username']}</td><td>{r['action']}</td><td style='font-family:monospace;font-size:11px'>{r['request_ip']}</td><td><span class=\"badge badge-red\">{r['risk_score']}</span></td><td>{'<span class=\"badge badge-red\">failure</span>' if r['result']=='failure' else r['result']}</td><td style='font-size:11px'>{str(r.get('created_at',''))[:16]}</td></tr>" for r in report['high_risk_events']) or '<tr><td colspan="6" style="color:#3d5a7a">Aucun</td></tr>'}
</tbody></table>

<h2>Requêtes lentes (> 1s)</h2>
<table><thead><tr><th>SQL</th><th>Durée</th><th>Connexion</th></tr></thead><tbody>
{''.join(f"<tr><td style='font-family:monospace;font-size:11px;max-width:400px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap'>{str(r.get('sql_text',''))[:60]}</td><td style='color:#f59e0b;font-weight:600'>{r['duration_ms']}ms</td><td style='font-size:11px'>{str(r.get('connection_id',''))[:8]}</td></tr>" for r in report['slow_queries']) or '<tr><td colspan="3" style="color:#3d5a7a">Aucune</td></tr>'}
</tbody></table>

<div class="footer">Rapport généré automatiquement par Raxus v1.0 — Plateforme d'intelligence de données</div>
</body></html>"""


audit_report_service = AuditReportService()

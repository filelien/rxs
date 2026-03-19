"""ConnectorRegistry — charge depuis MySQL applicatif."""
import base64, json
from typing import Dict, List, Any
from cryptography.fernet import Fernet
from backend.connectors.base import BaseConnector, HealthStatus
from backend.utils.logging import get_logger
from backend.config import get_settings

logger = get_logger(__name__)


def _get_fernet() -> Fernet:
    key = get_settings().credentials_encryption_key
    raw = key.encode()[:32].ljust(32, b"0")
    return Fernet(base64.urlsafe_b64encode(raw))


def encrypt_credentials(data: Dict[str, Any]) -> str:
    return _get_fernet().encrypt(json.dumps(data).encode()).decode()


def decrypt_credentials(token: str) -> Dict[str, Any]:
    return json.loads(_get_fernet().decrypt(token.encode()).decode())


def create_connector(connector_id: str, db_type: str, config: Dict[str, Any]) -> BaseConnector:
    from backend.connectors.oracle_connector import OracleConnector
    from backend.connectors.other_connectors import (
        MySQLConnector, PostgreSQLConnector, MongoDBConnector, RedisConnector,
    )
    m = {"oracle": OracleConnector, "mysql": MySQLConnector,
         "postgresql": PostgreSQLConnector, "mongodb": MongoDBConnector, "redis": RedisConnector}
    cls = m.get(db_type.lower())
    if not cls:
        raise ValueError(f"Unsupported db_type: {db_type}")
    return cls(connector_id, config)


class ConnectorRegistry:
    _connectors: Dict[str, BaseConnector] = {}
    _meta: Dict[str, Dict] = {}

    @classmethod
    async def register(cls, connector_id: str, db_type: str,
                        config: Dict[str, Any], meta: Dict = {}) -> BaseConnector:
        conn = create_connector(connector_id, db_type, config)
        await conn.connect()
        cls._connectors[connector_id] = conn
        cls._meta[connector_id] = {"db_type": db_type, "name": meta.get("name", connector_id), **meta}
        logger.info("connector_registered", id=connector_id, type=db_type)
        return conn

    @classmethod
    def get(cls, connector_id: str) -> BaseConnector:
        conn = cls._connectors.get(connector_id)
        if not conn:
            raise KeyError(f"Connector '{connector_id}' not found")
        return conn

    @classmethod
    async def remove(cls, connector_id: str):
        conn = cls._connectors.pop(connector_id, None)
        cls._meta.pop(connector_id, None)
        if conn:
            try:
                await conn.disconnect()
            except Exception:
                pass

    @classmethod
    def list_all(cls) -> List[Dict]:
        return [{"connector_id": cid, "name": cls._meta.get(cid, {}).get("name", cid),
                 "db_type": cls._meta.get(cid, {}).get("db_type"), "connected": conn._connected}
                for cid, conn in cls._connectors.items()]

    @classmethod
    def get_health_summary(cls) -> Dict[str, str]:
        return {cid: "up" if c._connected else "down" for cid, c in cls._connectors.items()}

    @classmethod
    async def close_all(cls):
        for conn in list(cls._connectors.values()):
            try:
                await conn.disconnect()
            except Exception:
                pass
        cls._connectors.clear()
        cls._meta.clear()

    @classmethod
    async def load_from_app_db(cls):
        try:
            from backend.db.app_db import list_connections, fetch_one
            rows = await list_connections(only_enabled=True)
            for row in rows:
                try:
                    full = await fetch_one("SELECT credentials_enc FROM db_connections WHERE id=%s", (row["id"],))
                    config = decrypt_credentials(full["credentials_enc"])
                    await cls.register(row["id"], row["db_type"], config, meta={"name": row["name"]})
                except Exception as e:
                    logger.warning("connector_load_failed", id=row["id"], error=str(e))
        except Exception as e:
            logger.error("registry_load_failed", error=str(e))

    @classmethod
    async def test(cls, connector_id: str) -> HealthStatus:
        return await cls.get(connector_id).test_connection()

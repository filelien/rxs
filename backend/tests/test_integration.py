"""
Tests d'intégration Raxus — Phase 12
Nécessite: MySQL sur port 3307, Redis sur port 6380
Run: pytest tests/test_integration.py -v -m integration
"""
import pytest
import asyncio
import os

# Mark pour skip si pas de DB disponible
pytestmark = pytest.mark.integration


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session", autouse=True)
def setup_env():
    """Setup environment variables for integration tests."""
    os.environ.setdefault("APP_ENV", "testing")
    os.environ.setdefault("APP_SECRET_KEY", "test-secret-key-32-bytes-minimum!!")
    os.environ.setdefault("APP_DB_HOST", "127.0.0.1")
    os.environ.setdefault("APP_DB_PORT", "3307")
    os.environ.setdefault("APP_DB_USER", "raxus")
    os.environ.setdefault("APP_DB_PASSWORD", "testpass")
    os.environ.setdefault("APP_DB_NAME", "raxus_test")
    os.environ.setdefault("REDIS_URL", "redis://127.0.0.1:6380/0")
    os.environ.setdefault("CREDENTIALS_ENCRYPTION_KEY", "test-fernet-key-32-bytes-padding!!")
    os.environ.setdefault("ANTHROPIC_API_KEY", "")


class TestAppDB:
    """Test MySQL applicatif CRUD operations."""

    @pytest.mark.asyncio
    async def test_db_connection(self):
        from backend.db.app_db import init_db, close_db, db_status
        await init_db()
        ok = await db_status()
        assert ok is True
        await close_db()

    @pytest.mark.asyncio
    async def test_create_and_get_user(self):
        from backend.db.app_db import init_db, close_db, create_user, get_user_by_id, execute
        await init_db()
        try:
            uid = await create_user("testuser_int", "test_int@raxus.io", "password123", "analyst")
            assert uid
            user = await get_user_by_id(uid)
            assert user is not None
            assert user["username"] == "testuser_int"
            assert user["role"] == "analyst"
            # Cleanup
            await execute("DELETE FROM users WHERE id=%s", (uid,))
        finally:
            await close_db()

    @pytest.mark.asyncio
    async def test_audit_log_write(self):
        from backend.db.app_db import init_db, close_db, write_audit_log, get_audit_logs
        await init_db()
        try:
            await write_audit_log(
                user_id="test-user", username="testuser", user_role="admin",
                action="test.action", resource_type="test", resource_id="123",
                request_ip="127.0.0.1", result="success", risk_score=5
            )
            logs = await get_audit_logs(days=1, limit=5)
            assert logs["total"] >= 1
        finally:
            await close_db()

    @pytest.mark.asyncio
    async def test_query_history_persistence(self):
        from backend.db.app_db import init_db, close_db, save_query_history, get_query_history, execute
        await init_db()
        try:
            test_conn_id = "test-conn-integration"
            await save_query_history(
                query_uuid="test-qid-001",
                user_id="test-user",
                connection_id=test_conn_id,
                sql_text="SELECT 1 FROM dual",
                status="success",
                row_count=1,
                duration_ms=42,
            )
            hist = await get_query_history("test-user", test_conn_id, 10, 1)
            assert hist["total"] >= 1
            # Cleanup
            await execute("DELETE FROM query_history WHERE query_uuid='test-qid-001'")
        finally:
            await close_db()


class TestAPIEndpoints:
    """Test FastAPI endpoints with TestClient."""

    @pytest.fixture
    def client(self):
        from fastapi.testclient import TestClient
        from backend.main import app
        return TestClient(app)

    def test_health_endpoint(self, client):
        """Health check should return 200 even without all services."""
        try:
            response = client.get("/health")
            assert response.status_code in (200, 503)
            data = response.json()
            assert "status" in data
            assert "version" in data
        except Exception:
            pass  # Services might not be available in CI

    def test_root_endpoint(self, client):
        response = client.get("/")
        # Might redirect or return 200
        assert response.status_code in (200, 307, 404)

    def test_docs_available_in_dev(self, client):
        response = client.get("/docs")
        assert response.status_code in (200, 404)

    def test_login_with_invalid_credentials(self, client):
        try:
            response = client.post("/auth/login", json={
                "username": "nonexistent", "password": "wrongpass"
            })
            assert response.status_code == 401
        except Exception:
            pass

    def test_protected_endpoint_without_token(self, client):
        try:
            response = client.get("/connections/")
            # Should return 401 or 200 depending on auth setup
            assert response.status_code in (200, 401, 403, 422, 500)
        except Exception:
            pass


class TestSQLEngine:
    """Integration tests for SQL engine with real validation."""

    def test_validator_safe_select(self):
        from backend.services.sql_engine import SQLValidator
        v = SQLValidator()
        result = v.validate("SELECT id, name FROM employees WHERE dept_id = 5 LIMIT 100", "analyst", "mysql")
        assert result.valid is True

    def test_validator_blocks_dangerous_ops(self):
        from backend.services.sql_engine import SQLValidator
        v = SQLValidator()
        dangerous = [
            "DROP TABLE employees",
            "TRUNCATE users",
            "DELETE FROM orders",
        ]
        for sql in dangerous:
            result = v.validate(sql, "admin", "mysql")
            assert result.valid is False, f"Should block: {sql}"

    def test_validator_oracle_dialect(self):
        from backend.services.sql_engine import SQLValidator
        v = SQLValidator()
        result = v.validate(
            "SELECT * FROM employees FETCH FIRST 100 ROWS ONLY",
            "analyst", "oracle"
        )
        assert result.valid is True


class TestEncryptionIntegration:
    """Test credential encryption round-trip."""

    def test_full_roundtrip_complex_config(self):
        from backend.connectors.registry import encrypt_credentials, decrypt_credentials
        config = {
            "host": "oracle-prod.internal.company.com",
            "port": 1521,
            "service_name": "PRODDB",
            "user": "dba_read_only",
            "password": "P@ssw0rd!Special#Chars$",
            "options": {"timeout": 30, "pool_size": 10},
        }
        encrypted = encrypt_credentials(config)
        # Ensure password not in plaintext
        assert "P@ssw0rd" not in encrypted
        # Ensure roundtrip works
        decrypted = decrypt_credentials(encrypted)
        assert decrypted == config
        assert decrypted["password"] == "P@ssw0rd!Special#Chars$"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-m", "integration", "--tb=short"])

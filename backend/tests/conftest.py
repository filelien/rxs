"""Fixtures partagées pour tous les tests Raxus."""
import os
import pytest


def pytest_configure(config):
    """Set env vars before any import."""
    os.environ.setdefault("APP_ENV", "testing")
    os.environ.setdefault("APP_SECRET_KEY", "test-secret-min-32-chars-raxus-ci!!")
    os.environ.setdefault("APP_DB_HOST", "127.0.0.1")
    os.environ.setdefault("APP_DB_PORT", "3307")
    os.environ.setdefault("APP_DB_USER", "raxus")
    os.environ.setdefault("APP_DB_PASSWORD", "testpass")
    os.environ.setdefault("APP_DB_NAME", "raxus_test")
    os.environ.setdefault("REDIS_URL", "redis://127.0.0.1:6380/0")
    os.environ.setdefault("CREDENTIALS_ENCRYPTION_KEY", "raxus-test-fernet-key-32bytes!!!")
    os.environ.setdefault("ANTHROPIC_API_KEY", "")
    os.environ.setdefault("LLM_MODEL", "claude-sonnet-4-20250514")


@pytest.fixture
def sample_user():
    return {"id": "usr-test-001", "username": "testuser", "role": "analyst"}


@pytest.fixture
def admin_user():
    return {"id": "usr-admin-001", "username": "admin", "role": "admin"}


@pytest.fixture
def sample_connection_config():
    return {
        "host": "localhost", "port": 3306,
        "database": "testdb", "user": "testuser", "password": "testpass"
    }

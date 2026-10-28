"""PostgreSQL integration test fixtures. Set TEST_DATABASE_URL to a test database."""

import os
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, sessionmaker


@pytest.fixture(scope="session")
def test_engine():
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL is required for PostgreSQL integration tests")
    database_name = make_url(url).database or ""
    if "test" not in database_name.lower():
        pytest.fail("TEST_DATABASE_URL must name a dedicated test database")
    os.environ["DATABASE_URL"] = url
    os.environ.setdefault("ADMIN_USERNAME", "test-admin")
    os.environ.setdefault("ADMIN_PASSWORD", "test-password")
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    command.upgrade(config, "head")
    engine = create_engine(url, pool_pre_ping=True)
    yield engine
    engine.dispose()


@pytest.fixture
def db_session(test_engine):
    with test_engine.begin() as connection:
        connection.execute(text("TRUNCATE TABLE reviews, books RESTART IDENTITY CASCADE"))
    factory = sessionmaker(bind=test_engine, expire_on_commit=False, autoflush=False)
    with factory() as session:
        yield session
        session.rollback()


@pytest.fixture
def client(test_engine, db_session, tmp_path, monkeypatch):
    """An HTTP client bound to the migrated test DB and isolated file storage."""
    monkeypatch.setenv("STORAGE_DIR", str(tmp_path))
    from fastapi.testclient import TestClient

    from app.infrastructure.database import get_db
    from app.main import app

    def override_db():
        with Session(test_engine) as session:
            yield session

    app.dependency_overrides[get_db] = override_db
    with TestClient(app) as http_client:
        yield http_client
    app.dependency_overrides.clear()

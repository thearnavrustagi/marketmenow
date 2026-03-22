"""Tests for web project routes and project-scoped DB helpers.

Mocks ``web.db`` so routes run without PostgreSQL. Matches patterns in
``test_web_routes.py`` (TestClient, minimal FastAPI app, monkeypatched DB).
"""

from __future__ import annotations

import inspect
import uuid
from datetime import UTC, datetime
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_content_item(**overrides: object) -> dict:
    defaults: dict[str, object] = {
        "id": uuid.uuid4(),
        "platform": "instagram",
        "modality": "video",
        "title": "Test reel",
        "status": "pending_review",
        "generate_command": ["mmn", "reel", "create"],
        "publish_command": ["mmn", "reel", "create", "--publish"],
        "preview_data": {},
        "progress_data": {},
        "output_path": None,
        "error_message": None,
        "created_at": datetime.now(UTC),
        "updated_at": datetime.now(UTC),
    }
    defaults.update(overrides)
    return defaults


def _make_record(data: dict) -> dict:
    return data


@pytest.fixture
def mock_db(monkeypatch: pytest.MonkeyPatch):
    """Patch web.db functions so routes don't need a real database."""
    from unittest.mock import AsyncMock

    import web.db as db_module

    sample_item = _make_content_item()

    monkeypatch.setattr(db_module, "init_pool", AsyncMock(return_value=None))
    monkeypatch.setattr(db_module, "close_pool", AsyncMock(return_value=None))
    monkeypatch.setattr(
        db_module,
        "list_content_items",
        AsyncMock(return_value=[_make_record(sample_item)]),
    )
    monkeypatch.setattr(
        db_module,
        "get_platform_activity_stats",
        AsyncMock(return_value=[]),
    )
    monkeypatch.setattr(
        db_module,
        "get_content_item",
        AsyncMock(return_value=_make_record(sample_item)),
    )
    monkeypatch.setattr(
        db_module,
        "insert_content_item",
        AsyncMock(return_value=sample_item["id"]),
    )
    monkeypatch.setattr(db_module, "update_content_status", AsyncMock(return_value=None))
    monkeypatch.setattr(db_module, "update_progress_data", AsyncMock(return_value=None))
    monkeypatch.setattr(
        db_module,
        "enqueue_content",
        AsyncMock(return_value=uuid.uuid4()),
    )
    monkeypatch.setattr(
        db_module,
        "list_queue_items",
        AsyncMock(return_value=[]),
    )
    monkeypatch.setattr(
        db_module,
        "get_rate_limits",
        AsyncMock(return_value=[]),
    )
    monkeypatch.setattr(
        db_module,
        "get_post_log",
        AsyncMock(return_value=[]),
    )
    monkeypatch.setattr(
        db_module,
        "clear_all_content",
        AsyncMock(return_value=0),
    )
    monkeypatch.setattr(
        db_module,
        "list_history_items",
        AsyncMock(return_value=[]),
    )

    return sample_item


@pytest.fixture
def client(mock_db: dict) -> TestClient:
    """Minimal app with dashboard + project routes (same style as test_web_routes)."""
    from contextlib import asynccontextmanager

    from fastapi import FastAPI
    from fastapi.staticfiles import StaticFiles

    from web.deps import STATIC_DIR
    from web.routes.dashboard import router as dashboard_router
    from web.routes.project import router as project_router

    @asynccontextmanager
    async def noop_lifespan(_app: FastAPI):
        yield

    test_app = FastAPI(lifespan=noop_lifespan)
    test_app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
    test_app.include_router(dashboard_router)
    test_app.include_router(project_router)

    return TestClient(test_app, raise_server_exceptions=False)


@pytest.fixture
def fake_projects_context(monkeypatch: pytest.MonkeyPatch) -> None:
    """Override Jinja global ``get_projects`` (template holds a direct callable ref)."""
    from marketmenow.models.project import BrandConfig, ProjectConfig

    acme = ProjectConfig(
        slug="acme",
        brand=BrandConfig(name="Acme Co", url="https://acme.test", tagline="Test"),
    )

    def get_projects() -> tuple[list[ProjectConfig], str | None]:
        return ([acme], "acme")

    import web.deps as deps_mod

    monkeypatch.setitem(deps_mod.templates.env.globals, "get_projects", get_projects)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestProjectSelector:
    def test_dashboard_includes_project_dropdown(
        self,
        client: TestClient,
        fake_projects_context: None,
    ) -> None:
        resp = client.get("/")
        assert resp.status_code == 200
        assert 'name="slug"' in resp.text
        assert 'hx-post="/project/select"' in resp.text
        assert "Acme Co" in resp.text
        assert 'value="acme"' in resp.text


class TestProjectPage:
    def test_project_page_returns_200(self, client: TestClient) -> None:
        with patch("web.routes.project._get_pm") as mock_pm:
            mock_pm.return_value.list_projects.return_value = []
            mock_pm.return_value.get_active_project.return_value = None
            resp = client.get("/project")
            assert resp.status_code == 200


class TestProjectSelect:
    def test_select_sets_cookie(self, client: TestClient, tmp_path, monkeypatch) -> None:
        monkeypatch.chdir(tmp_path)
        from marketmenow.core.project_manager import ProjectManager
        from marketmenow.models.project import BrandConfig

        pm = ProjectManager()
        pm.create_project("test", BrandConfig(name="Test", url="https://t.io", tagline="t"))

        with patch("web.routes.project._get_pm", return_value=pm):
            resp = client.post(
                "/project/select",
                data={"slug": "test"},
            )
            assert resp.status_code == 200
            assert "mmn_project" in resp.headers.get("set-cookie", "")


class TestDbProjectSlug:
    def test_insert_content_item_accepts_project_slug(self) -> None:
        from web.db import insert_content_item

        sig = inspect.signature(insert_content_item)
        assert "project_slug" in sig.parameters

    def test_list_content_items_accepts_project_slug(self) -> None:
        from web.db import list_content_items

        sig = inspect.signature(list_content_items)
        assert "project_slug" in sig.parameters

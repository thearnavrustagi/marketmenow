from __future__ import annotations

import uuid
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

_mock_provider = MagicMock()


@pytest.fixture(autouse=True)
def _patch_llm_provider():
    with (
        patch(
            "marketmenow.steps.repurpose_content.create_llm_provider", return_value=_mock_provider
        ),
        patch("marketmenow.steps.prepare_youtube.create_llm_provider", return_value=_mock_provider),
    ):
        yield


def _make_content_item(**overrides: object) -> dict:
    defaults: dict[str, object] = {
        "id": uuid.uuid4(),
        "platform": "workflow",
        "modality": "workflow",
        "title": "Test flow",
        "status": "generating",
        "generate_command": ["mmn", "run", "twitter-thread"],
        "publish_command": ["mmn", "run", "twitter-thread"],
        "preview_data": {},
        "progress_data": {},
        "output_path": None,
        "error_message": None,
        "created_at": datetime.now(UTC),
        "updated_at": datetime.now(UTC),
    }
    defaults.update(overrides)
    return defaults


@pytest.fixture
def mock_db(monkeypatch: pytest.MonkeyPatch) -> dict:
    import web.db as db_module

    sample = _make_content_item()

    monkeypatch.setattr(db_module, "init_pool", AsyncMock(return_value=None))
    monkeypatch.setattr(db_module, "close_pool", AsyncMock(return_value=None))
    monkeypatch.setattr(db_module, "list_content_items", AsyncMock(return_value=[]))
    monkeypatch.setattr(db_module, "get_platform_activity_stats", AsyncMock(return_value=[]))
    monkeypatch.setattr(db_module, "get_content_item", AsyncMock(return_value=sample))
    monkeypatch.setattr(db_module, "insert_content_item", AsyncMock(return_value=sample["id"]))
    monkeypatch.setattr(db_module, "update_content_status", AsyncMock(return_value=None))
    monkeypatch.setattr(db_module, "update_progress_data", AsyncMock(return_value=None))
    monkeypatch.setattr(db_module, "enqueue_content", AsyncMock(return_value=uuid.uuid4()))
    monkeypatch.setattr(db_module, "list_queue_items", AsyncMock(return_value=[]))
    monkeypatch.setattr(db_module, "get_rate_limits", AsyncMock(return_value=[]))
    monkeypatch.setattr(db_module, "get_post_log", AsyncMock(return_value=[]))
    monkeypatch.setattr(db_module, "clear_all_content", AsyncMock(return_value=0))
    monkeypatch.setattr(db_module, "list_history_items", AsyncMock(return_value=[]))

    return sample


@pytest.fixture
def client(mock_db: dict, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    from contextlib import asynccontextmanager

    from fastapi import FastAPI
    from fastapi.staticfiles import StaticFiles

    from web.deps import STATIC_DIR
    from web.routes import flows as flows_mod
    from web.routes.credentials import router as creds_router
    from web.routes.flows import router as flows_router

    monkeypatch.setattr(flows_mod, "_CUSTOM_DIR", tmp_path / "custom")
    (tmp_path / "custom").mkdir()

    @asynccontextmanager
    async def noop_lifespan(_app: FastAPI):
        yield

    test_app = FastAPI(lifespan=noop_lifespan)
    test_app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
    test_app.include_router(flows_router)
    test_app.include_router(creds_router)

    return TestClient(test_app, raise_server_exceptions=False)


class TestFlowsPage:
    def test_returns_200(self, client: TestClient) -> None:
        resp = client.get("/flows")
        assert resp.status_code == 200
        assert "Flows" in resp.text

    def test_contains_workflow_names(self, client: TestClient) -> None:
        resp = client.get("/flows")
        assert "instagram-reel" in resp.text
        assert "reddit-launch" in resp.text

    def test_contains_run_forms(self, client: TestClient) -> None:
        resp = client.get("/flows")
        assert "Run this flow" in resp.text


class TestFlowEditor:
    def test_editor_page_returns_200(self, client: TestClient) -> None:
        resp = client.get("/flows/editor")
        assert resp.status_code == 200
        assert "New Flow" in resp.text

    def test_editor_has_step_picker(self, client: TestClient) -> None:
        resp = client.get("/flows/editor")
        assert "generate-reel" in resp.text
        assert "post-to-platform" in resp.text

    def test_editor_has_yaml_tab(self, client: TestClient) -> None:
        resp = client.get("/flows/editor")
        assert "YAML" in resp.text

    def test_save_valid_yaml(self, client: TestClient) -> None:
        yaml_content = "name: test-save\ndescription: test\nsteps:\n  - generate-thread\n"
        resp = client.post("/flows/save", data={"yaml_content": yaml_content})
        assert resp.status_code == 200
        assert "saved" in resp.text.lower()

    def test_save_empty_yaml_error(self, client: TestClient) -> None:
        resp = client.post("/flows/save", data={"yaml_content": ""})
        assert resp.status_code == 200
        assert "empty" in resp.text.lower()

    def test_save_invalid_yaml_error(self, client: TestClient) -> None:
        resp = client.post("/flows/save", data={"yaml_content": "{{not yaml"})
        assert resp.status_code == 200
        assert "Invalid YAML" in resp.text or "invalid" in resp.text.lower()


class TestCredentialsPage:
    def test_returns_200(self, client: TestClient) -> None:
        resp = client.get("/credentials")
        assert resp.status_code == 200
        assert "Credentials" in resp.text

    def test_shows_platform_list(self, client: TestClient) -> None:
        resp = client.get("/credentials")
        assert "reddit" in resp.text.lower()
        assert "twitter" in resp.text.lower()

    def test_platform_keys_endpoint(self, client: TestClient) -> None:
        resp = client.get("/credentials/keys/reddit")
        assert resp.status_code == 200
        assert "REDDIT_SESSION" in resp.text

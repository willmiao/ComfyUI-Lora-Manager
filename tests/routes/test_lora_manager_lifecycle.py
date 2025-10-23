from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from types import SimpleNamespace

import pytest
from aiohttp import web

from py import lora_manager


class _DummyScanner:
    def __init__(self, name: str) -> None:
        self.name = name
        self.initialized = False

    async def initialize_in_background(self) -> None:
        self.initialized = True


class _DummyWSManager:
    async def handle_connection(self, request):  # pragma: no cover - interface stub
        return None

    async def handle_download_connection(self, request):  # pragma: no cover - interface stub
        return None

    async def handle_init_connection(self, request):  # pragma: no cover - interface stub
        return None


async def test_lora_manager_lifecycle(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    app = web.Application()
    app._handler_args = {"max_field_size": 1024, "foo": "bar"}
    monkeypatch.setattr(lora_manager.PromptServer, "instance", SimpleNamespace(app=app))

    added_static_routes: list[tuple[str, Path]] = []
    def record_static_route(path: str, directory: str, *_, **__) -> SimpleNamespace:
        added_static_routes.append((path, Path(directory)))
        return SimpleNamespace()

    added_get_routes: list[tuple[str, object]] = []
    def record_get_route(path: str, handler, *_, **__) -> SimpleNamespace:
        added_get_routes.append((path, handler))
        return SimpleNamespace()

    monkeypatch.setattr(app.router, "add_static", record_static_route)
    monkeypatch.setattr(app.router, "add_get", record_get_route)

    register_calls: list[bool] = []
    monkeypatch.setattr(lora_manager, "register_default_model_types", lambda: register_calls.append(True))

    model_factory_calls: list[object] = []
    monkeypatch.setattr(lora_manager.ModelServiceFactory, "setup_all_routes", lambda app_: model_factory_calls.append(app_))
    monkeypatch.setattr(lora_manager.ModelServiceFactory, "get_registered_types", lambda: ["dummy"])

    stats_setup: list[object] = []
    class FakeStatsRoutes:
        def setup_routes(self, app_: web.Application) -> None:
            stats_setup.append(app_)
    monkeypatch.setattr(lora_manager, "StatsRoutes", FakeStatsRoutes)

    recipe_setup: list[object] = []
    class FakeRecipeRoutes:
        @staticmethod
        def setup_routes(app_: web.Application) -> None:
            recipe_setup.append(app_)
    monkeypatch.setattr(lora_manager, "RecipeRoutes", FakeRecipeRoutes)

    update_setup: list[object] = []
    class FakeUpdateRoutes:
        @staticmethod
        def setup_routes(app_: web.Application) -> None:
            update_setup.append(app_)
    monkeypatch.setattr(lora_manager, "UpdateRoutes", FakeUpdateRoutes)

    misc_setup: list[object] = []
    class FakeMiscRoutes:
        @staticmethod
        def setup_routes(app_: web.Application) -> None:
            misc_setup.append(app_)
    monkeypatch.setattr(lora_manager, "MiscRoutes", FakeMiscRoutes)

    example_setup: list[tuple[object, object]] = []
    class FakeExampleImagesRoutes:
        @staticmethod
        def setup_routes(app_: web.Application, *, ws_manager) -> None:
            example_setup.append((app_, ws_manager))
    monkeypatch.setattr(lora_manager, "ExampleImagesRoutes", FakeExampleImagesRoutes)

    preview_setup: list[object] = []
    class FakePreviewRoutes:
        @staticmethod
        def setup_routes(app_: web.Application) -> None:
            preview_setup.append(app_)
    monkeypatch.setattr(lora_manager, "PreviewRoutes", FakePreviewRoutes)

    fake_ws = _DummyWSManager()
    monkeypatch.setattr(lora_manager, "ws_manager", fake_ws)

    example_images_root = tmp_path / "example_images"
    example_images_root.mkdir()
    monkeypatch.setattr(
        lora_manager.settings,
        "get",
        lambda key, default=None: str(example_images_root) if key == "example_images_path" else default,
    )

    loras_root = tmp_path / "loras"
    loras_root.mkdir()
    (loras_root / "model.ckpt.bak").write_text("stale")
    nested = loras_root / "nested"
    nested.mkdir()
    (nested / "nested_model.ckpt.bak").write_text("stale")

    checkpoints_root = tmp_path / "checkpoints"
    checkpoints_root.mkdir()
    (checkpoints_root / "checkpoint.safetensors.bak").write_text("old")

    embeddings_root = tmp_path / "embeddings"
    embeddings_root.mkdir()
    (embeddings_root / "embedding.pt.bak").write_text("old")

    monkeypatch.setattr(lora_manager.config, "loras_roots", [str(loras_root)])
    monkeypatch.setattr(lora_manager.config, "base_models_roots", [str(checkpoints_root)])
    monkeypatch.setattr(lora_manager.config, "embeddings_roots", [str(embeddings_root)])

    scanners = {
        "lora": _DummyScanner("lora"),
        "checkpoint": _DummyScanner("checkpoint"),
        "embedding": _DummyScanner("embedding"),
        "recipe": _DummyScanner("recipe"),
    }

    registry_calls: list[str] = []

    async def _stub(name: str, value):
        registry_calls.append(name)
        return value

    monkeypatch.setattr(lora_manager.ServiceRegistry, "get_civitai_client", lambda: _stub("civitai_client", object()))
    monkeypatch.setattr(lora_manager.ServiceRegistry, "get_download_manager", lambda: _stub("download_manager", object()))
    monkeypatch.setattr(lora_manager.ServiceRegistry, "get_websocket_manager", lambda: _stub("websocket_manager", object()))
    monkeypatch.setattr(lora_manager.ServiceRegistry, "get_lora_scanner", lambda: _stub("lora_scanner", scanners["lora"]))
    monkeypatch.setattr(lora_manager.ServiceRegistry, "get_checkpoint_scanner", lambda: _stub("checkpoint_scanner", scanners["checkpoint"]))
    monkeypatch.setattr(lora_manager.ServiceRegistry, "get_embedding_scanner", lambda: _stub("embedding_scanner", scanners["embedding"]))
    monkeypatch.setattr(lora_manager.ServiceRegistry, "get_recipe_scanner", lambda: _stub("recipe_scanner", scanners["recipe"]))

    migration_calls: list[bool] = []

    async def fake_migration() -> None:
        migration_calls.append(True)

    monkeypatch.setattr(
        lora_manager.ExampleImagesMigration,
        "check_and_run_migrations",
        staticmethod(fake_migration),
    )

    original_create_task = asyncio.create_task
    scheduled_tasks: list[asyncio.Task] = []

    def track_create_task(coro, *, name=None):
        task = original_create_task(coro, name=name)
        scheduled_tasks.append(task)
        return task

    monkeypatch.setattr(asyncio, "create_task", track_create_task)

    asyncio_logger = logging.getLogger("asyncio")
    original_filters = list(asyncio_logger.filters)
    try:
        lora_manager.LoraManager.add_routes()
        assert lora_manager.LoraManager._cleanup in app.on_shutdown
        assert app.on_startup, "startup hooks should be registered"
        assert app._handler_args["max_field_size"] == lora_manager.HEADER_SIZE_LIMIT
        assert app._handler_args["max_line_size"] == lora_manager.HEADER_SIZE_LIMIT
        assert app._handler_args["foo"] == "bar"
        assert register_calls == [True]
        assert model_factory_calls == [app]
        assert stats_setup == [app]
        assert recipe_setup == [app]
        assert update_setup == [app]
        assert misc_setup == [app]
        assert example_setup == [(app, fake_ws)]
        assert preview_setup == [app]
        assert {path for path, _ in added_static_routes} == {
            "/example_images_static",
            "/locales",
            "/loras_static",
        }
        get_paths = {path for path, _ in added_get_routes}
        assert {"/ws/fetch-progress", "/ws/download-progress", "/ws/init-progress"}.issubset(get_paths)
        assert any(filter_obj.__class__.__name__ == "ConnectionResetFilter" for filter_obj in asyncio_logger.filters)
    finally:
        asyncio_logger.filters[:] = original_filters

    await lora_manager.LoraManager._initialize_services()

    pending = [task for task in scheduled_tasks if not task.done()]
    if pending:
        await asyncio.gather(*pending)

    task_names = {task.get_name() for task in scheduled_tasks}
    assert {"lora_cache_init", "checkpoint_cache_init", "embedding_cache_init", "recipe_cache_init", "post_init_tasks", "cleanup_bak_files"}.issubset(task_names)

    for scanner in scanners.values():
        assert scanner.initialized is True

    assert migration_calls == [True]

    for root in (loras_root, checkpoints_root, embeddings_root):
        assert not any(path.suffix == ".bak" for path in root.rglob("*")), f"Backup files remain in {root}"

    assert {"civitai_client", "download_manager", "websocket_manager", "lora_scanner", "checkpoint_scanner", "embedding_scanner", "recipe_scanner"}.issubset(registry_calls)

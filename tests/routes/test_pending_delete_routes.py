"""Tests for the pending-delete undo endpoint.

Covers ``POST /api/lm/undo-delete`` (``py/routes/handlers/
pending_delete_handler.py``) and its route registration
(``py/routes/pending_delete_routes.py``): model/recipe cache restoration,
per-type scanner resolution, restart-safe and rescan-stale undo, tag-count
restoration, broadcast, error responses, malformed input, and exactly-once
registration in both plugin and standalone modes.
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from collections.abc import Iterator
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, List, Optional, Sequence

import pytest
from aiohttp import web

from py.routes.pending_delete_routes import PendingDeleteRoutes
from py.services.pending_delete_service import (
    PENDING_DELETE_DIR_NAME,
    PendingDeleteService,
    _reset_pending_delete_service,
)
from py.utils import settings_paths

UNDO_DELETE_PATH = "/api/lm/undo-delete"


# ---------------------------------------------------------------------------
# Doubles
# ---------------------------------------------------------------------------
class FakeRequest:
    """Request double exposing the async ``json()`` the handler awaits."""

    def __init__(self, *, json_data: Any = None, raise_json_error: bool = False) -> None:
        self._json_data = json_data
        self._raise_json_error = raise_json_error

    async def json(self) -> Any:
        if self._raise_json_error:
            raise ValueError("invalid json body")
        return self._json_data


class FakeHashIndex:
    """Hash index double recording ``add_entry`` calls."""

    def __init__(self) -> None:
        self.entries: List[tuple[Any, ...]] = []

    def add_entry(self, sha256: str, file_path: str, autov3: Optional[str] = None) -> None:
        self.entries.append((sha256, file_path, autov3))


class FakeCache:
    """Cache double exposing the raw_data/version-index surface the undo uses."""

    def __init__(self, items: Optional[Sequence[Dict[str, Any]]] = None) -> None:
        self.raw_data: List[Dict[str, Any]] = list(items or [])
        self.version_index: Dict[Any, Any] = {}
        self.model_id_index: Dict[Any, Any] = {}
        self.rebuild_calls = 0
        self.resort_calls = 0

    def rebuild_version_index(self) -> None:
        self.rebuild_calls += 1
        self.version_index = {}
        self.model_id_index = {}

    async def resort(self) -> None:
        self.resort_calls += 1


class FakeScanner:
    """Scanner double exposing the attributes the undo cache-restore uses."""

    def __init__(
        self,
        root: Path,
        *,
        model_type: str = "lora",
        cache: Optional[FakeCache] = None,
    ) -> None:
        self._root = os.path.abspath(str(root))
        self.model_type = model_type
        self._cache = cache or FakeCache()
        self._hash_index = FakeHashIndex()
        self._tags_count: Dict[str, int] = {}
        self.cache_version = 0
        self.bump_calls = 0
        self.persist_calls = 0

    def get_model_roots(self) -> List[str]:
        return [self._root]

    def _find_root_for_file(self, file_path: Optional[str]) -> Optional[str]:
        if not file_path:
            return None
        normalized = os.path.abspath(os.path.normpath(file_path))
        if normalized == self._root or normalized.startswith(self._root + os.sep):
            return self._root
        return None

    async def get_cached_data(self, force_refresh: bool = False) -> FakeCache:
        return self._cache

    def bump_cache_version(self) -> None:
        self.cache_version += 1
        self.bump_calls += 1

    async def _persist_current_cache(self) -> None:
        self.persist_calls += 1


class FakeRecipeScanner:
    """Recipe scanner double mirroring add_recipe's tolerant path-map read."""

    def __init__(self) -> None:
        self.added: List[Dict[str, Any]] = []
        self._json_path_map: Dict[str, str] = {}

    async def add_recipe(self, recipe_data: Dict[str, Any]) -> None:
        # The real scanner only READS _json_path_map here (the row may carry an
        # empty json_path until the forced frontend refresh) - never crashes.
        recipe_id = str(recipe_data.get("id", ""))
        self._json_path_map.get(recipe_id, "")
        self.added.append(dict(recipe_data))

    def force_refresh(self) -> None:
        """Simulate ``window.recipeManager.loadRecipes(true)`` rebuilding the map."""
        for recipe in self.added:
            recipe_id = str(recipe.get("id", ""))
            file_path = recipe.get("file_path")
            if recipe_id and file_path:
                self._json_path_map[recipe_id] = str(file_path)


class _DummyRoutes:
    @staticmethod
    def setup_routes(app_: web.Application, **kwargs: Any) -> None:
        return None


class _DummyWSManager:
    async def handle_connection(self, request):  # pragma: no cover - interface stub
        return None

    async def handle_download_connection(self, request):  # pragma: no cover - interface stub
        return None

    async def handle_init_connection(self, request):  # pragma: no cover - interface stub
        return None


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------
@pytest.fixture(autouse=True)
def _reset_service_singleton() -> Iterator[None]:
    """Reset the pending-delete singleton before and after each test."""
    _reset_pending_delete_service()
    yield
    _reset_pending_delete_service()


@pytest.fixture(autouse=True)
def _stub_scanner_registry(monkeypatch: pytest.MonkeyPatch) -> None:
    """Prevent scanner resolution from instantiating real singletons."""
    from py.services.service_registry import ServiceRegistry

    async def _none(*_args: Any, **_kwargs: Any) -> None:
        return None

    monkeypatch.setattr(ServiceRegistry, "get_lora_scanner", _none)
    monkeypatch.setattr(ServiceRegistry, "get_checkpoint_scanner", _none)
    monkeypatch.setattr(ServiceRegistry, "get_embedding_scanner", _none)
    monkeypatch.setattr(ServiceRegistry, "get_recipe_scanner", _none)


async def _register_scanners(
    monkeypatch: pytest.MonkeyPatch,
    *,
    lora: Any = None,
    checkpoint: Any = None,
    embedding: Any = None,
    recipe: Any = None,
) -> None:
    """Point the ServiceRegistry getters at per-test scanner doubles."""
    from py.services.service_registry import ServiceRegistry

    def _make(scanner: Any):
        async def _getter(*_args: Any, **_kwargs: Any) -> Any:
            return scanner

        return _getter

    monkeypatch.setattr(ServiceRegistry, "get_lora_scanner", _make(lora))
    monkeypatch.setattr(ServiceRegistry, "get_checkpoint_scanner", _make(checkpoint))
    monkeypatch.setattr(ServiceRegistry, "get_embedding_scanner", _make(embedding))
    monkeypatch.setattr(ServiceRegistry, "get_recipe_scanner", _make(recipe))


def _make_undo_request(**json_data: Any) -> FakeRequest:
    return FakeRequest(json_data=json_data)


def _json_payload(response: web.Response) -> Dict[str, Any]:
    """Decode the JSON body of a web.Response, asserting it is not null."""
    text = response.text
    assert text is not None
    return json.loads(text)


def _write_batch_manifest(
    batch_dir: Path,
    *,
    batch_id: str,
    kind: str,
    expires_at: int,
    entries: Sequence[Dict[str, Any]],
    model_type: Optional[str] = None,
    state: str = "staged",
    model_snapshot: Any = None,
    recipe_snapshot: Any = None,
) -> None:
    """Write a manifest.json with the shape the service reads."""
    manifest: Dict[str, Any] = {
        "batch_id": batch_id,
        "kind": kind,
        "model_type": model_type if kind == "model" else None,
        "state": state,
        "expires_at": int(expires_at),
        "entries": list(entries),
        "model_snapshot": model_snapshot if kind == "model" else None,
        "recipe_snapshot": recipe_snapshot if kind == "recipe" else None,
    }
    (batch_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")


def _undo_delete_routes(app: web.Application) -> List[Any]:
    """The POST /api/lm/undo-delete routes currently registered on *app*."""
    return [
        route
        for route in app.router.routes()
        if route.method == "POST"
        and getattr(route.resource, "canonical", "") == UNDO_DELETE_PATH
    ]


async def _drain_broadcast() -> None:
    """Yield to the loop so the fire-and-forget broadcast task can run."""
    for _ in range(10):
        await asyncio.sleep(0)


# (a) undo of a staged model batch (loras) -> files + cache + hash + broadcast
# ---------------------------------------------------------------------------
async def test_a_undo_staged_model_batch_restores_files_cache_and_broadcasts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "loras"
    root.mkdir()
    model = root / "model.safetensors"
    model.write_bytes(b"model-data")
    snapshot = {
        "file_path": str(model),
        "sha256": "a" * 64,
        "tags": ["alpha"],
        "model_name": "model",
    }

    scanner = FakeScanner(root, model_type="lora")
    scanner._cache.raw_data = [dict(snapshot)]
    scanner._tags_count = {"alpha": 1}
    await _register_scanners(monkeypatch, lora=scanner)

    service = await PendingDeleteService.get_instance()
    batch_id = await service.stage_model_delete(
        scanner=scanner,
        target_dir=str(root),
        file_name="model",
        main_extension=".safetensors",
        original_file_path=str(model),
        cached_entry=dict(snapshot),
    )
    assert batch_id is not None

    # Simulate the delete-time cache mutation: entry removed, tags decremented.
    scanner._cache.raw_data = []
    scanner._tags_count = {}

    sent: List[Dict[str, Any]] = []

    async def fake_broadcast(data: Dict[str, Any]) -> None:
        sent.append(data)

    monkeypatch.setattr("py.services.websocket_manager.ws_manager.broadcast", fake_broadcast)

    from py.routes.handlers.pending_delete_handler import PendingDeleteHandler

    response = await PendingDeleteHandler().undo_delete(
        _make_undo_request(batch_id=batch_id)  # pyright: ignore[reportArgumentType]
    )

    assert response.status == 200
    payload = _json_payload(response)
    assert payload["success"] is True
    assert payload["kind"] == "model"
    assert payload["restored"] == [str(model)]

    # Files restored to the original path.
    assert model.read_bytes() == b"model-data"
    # Cache entry restored exactly once.
    assert len(scanner._cache.raw_data) == 1
    assert scanner._cache.raw_data[0]["file_path"] == str(model)
    # Version-index rebuild + resort + persist + cache bump all ran.
    assert scanner._cache.rebuild_calls >= 1
    assert scanner._cache.resort_calls >= 1
    assert scanner.persist_calls >= 1
    assert scanner.bump_calls >= 1
    # Hash index has the path.
    assert any(entry[1] == str(model) for entry in scanner._hash_index.entries)
    # Tag counts re-incremented.
    assert scanner._tags_count == {"alpha": 1}
    # Broadcast fired exactly once with models_changed.
    await _drain_broadcast()
    assert sent == [{"type": "models_changed"}]


# ---------------------------------------------------------------------------
# (b) undo of a staged CHECKPOINT batch -> resolves the checkpoint scanner
# ---------------------------------------------------------------------------
async def test_b_undo_checkpoint_batch_updates_checkpoint_cache_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ckpt_root = tmp_path / "checkpoints"
    ckpt_root.mkdir()
    model = ckpt_root / "model.safetensors"
    model.write_bytes(b"ckpt-data")
    snapshot = {
        "file_path": str(model),
        "sha256": "b" * 64,
        "tags": [],
        "model_name": "ckpt",
    }

    lora_scanner = FakeScanner(tmp_path / "loras", model_type="lora")
    ckpt_scanner = FakeScanner(ckpt_root, model_type="checkpoint")
    lora_scanner._cache.raw_data = [{"file_path": "/loras/other.safetensors", "sha256": "x"}]
    ckpt_scanner._cache.raw_data = [dict(snapshot)]
    await _register_scanners(monkeypatch, lora=lora_scanner, checkpoint=ckpt_scanner)

    service = await PendingDeleteService.get_instance()
    batch_id = await service.stage_model_delete(
        scanner=ckpt_scanner,
        target_dir=str(ckpt_root),
        file_name="model",
        main_extension=".safetensors",
        original_file_path=str(model),
        cached_entry=dict(snapshot),
    )
    assert batch_id is not None
    # Simulate the delete-time cache mutation on the checkpoint cache.
    ckpt_scanner._cache.raw_data = []

    from py.routes.handlers.pending_delete_handler import PendingDeleteHandler

    response = await PendingDeleteHandler().undo_delete(
        _make_undo_request(batch_id=batch_id)  # pyright: ignore[reportArgumentType]
    )
    assert response.status == 200

    # The CHECKPOINT cache was updated, not the lora cache.
    assert len(ckpt_scanner._cache.raw_data) == 1
    assert ckpt_scanner._cache.raw_data[0]["file_path"] == str(model)
    assert len(lora_scanner._cache.raw_data) == 1  # untouched


# ---------------------------------------------------------------------------
# (c) undo of a staged recipe batch -> files restored + add_recipe called
# ---------------------------------------------------------------------------
async def test_c_undo_recipe_batch_restores_files_and_calls_add_recipe(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    recipe_json = tmp_path / "my_recipe.recipe.json"
    recipe_data = {"id": "r1", "name": "Recipe One", "file_path": str(recipe_json)}
    recipe_json.write_text(json.dumps(recipe_data), encoding="utf-8")

    recipe_scanner = FakeRecipeScanner()
    await _register_scanners(monkeypatch, recipe=recipe_scanner)

    service = await PendingDeleteService.get_instance()
    batch_id = await service.stage_recipe_delete(
        recipe_json_path=str(recipe_json),
        image_path=None,
        recipe_data=dict(recipe_data),
    )
    assert batch_id is not None
    # The todo-4 caller removes the originals after staging.
    recipe_json.unlink()

    sent: List[Dict[str, Any]] = []

    async def fake_broadcast(data: Dict[str, Any]) -> None:
        sent.append(data)

    monkeypatch.setattr("py.services.websocket_manager.ws_manager.broadcast", fake_broadcast)

    from py.routes.handlers.pending_delete_handler import PendingDeleteHandler

    response = await PendingDeleteHandler().undo_delete(
        _make_undo_request(batch_id=batch_id)  # pyright: ignore[reportArgumentType]
    )

    assert response.status == 200
    payload = _json_payload(response)
    assert payload["success"] is True
    assert payload["kind"] == "recipe"
    assert payload["restored"] == [str(recipe_json)]

    # Files restored and the recipe re-added to the scanner.
    assert recipe_json.read_text(encoding="utf-8") == json.dumps(recipe_data)
    assert recipe_scanner.added == [recipe_data]
    # Recipe undo is client-refresh only - no models_changed broadcast.
    await _drain_broadcast()
    assert sent == []


# ---------------------------------------------------------------------------
# (d) unknown / expired / occupied batch -> 404 responses
# ---------------------------------------------------------------------------
async def test_d1_undo_unknown_batch_returns_404(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _register_scanners(
        monkeypatch, lora=FakeScanner(tmp_path / "loras", model_type="lora")
    )

    from py.routes.handlers.pending_delete_handler import PendingDeleteHandler

    response = await PendingDeleteHandler().undo_delete(
        _make_undo_request(batch_id="f" * 32)  # pyright: ignore[reportArgumentType]
    )

    assert response.status == 404
    payload = _json_payload(response)
    assert payload["success"] is False
    assert "batch" in payload["error"].lower()


async def test_d2_undo_expired_batch_returns_404(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "loras"
    root.mkdir()
    model = root / "model.safetensors"
    model.write_bytes(b"data")

    scanner = FakeScanner(root, model_type="lora")
    await _register_scanners(monkeypatch, lora=scanner)

    service = await PendingDeleteService.get_instance()

    # Isolate the expiry check from the opportunistic purge.
    async def _no_purge() -> int:
        return 0

    monkeypatch.setattr(service, "purge_expired", _no_purge)

    batch_id = await service.stage_model_delete(
        scanner=scanner,
        target_dir=str(root),
        file_name="model",
        main_extension=".safetensors",
        original_file_path=str(model),
        cached_entry={"file_path": str(model)},
    )
    assert batch_id is not None
    batch_dir = root / PENDING_DELETE_DIR_NAME / batch_id
    manifest_path = batch_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["expires_at"] = int(time.time()) - 10
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    from py.routes.handlers.pending_delete_handler import PendingDeleteHandler

    response = await PendingDeleteHandler().undo_delete(
        _make_undo_request(batch_id=batch_id)  # pyright: ignore[reportArgumentType]
    )
    assert response.status == 404
    assert "expired" in _json_payload(response)["error"].lower()


async def test_d3_undo_occupied_path_returns_404(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "loras"
    root.mkdir()
    model = root / "model.safetensors"
    model.write_bytes(b"data")

    scanner = FakeScanner(root, model_type="lora")
    await _register_scanners(monkeypatch, lora=scanner)

    service = await PendingDeleteService.get_instance()
    batch_id = await service.stage_model_delete(
        scanner=scanner,
        target_dir=str(root),
        file_name="model",
        main_extension=".safetensors",
        original_file_path=str(model),
        cached_entry={"file_path": str(model)},
    )
    assert batch_id is not None
    # A re-download now occupies the original path.
    model.write_bytes(b"new-file")

    from py.routes.handlers.pending_delete_handler import PendingDeleteHandler

    response = await PendingDeleteHandler().undo_delete(
        _make_undo_request(batch_id=batch_id)  # pyright: ignore[reportArgumentType]
    )
    assert response.status == 404
    assert "occupied" in _json_payload(response)["error"].lower()


# ---------------------------------------------------------------------------
# (d-adjacent) malformed input -> 400
# ---------------------------------------------------------------------------
async def test_d4_undo_malformed_body_returns_400(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from py.routes.handlers.pending_delete_handler import PendingDeleteHandler

    handler = PendingDeleteHandler()

    # Missing batch_id.
    response = await handler.undo_delete(_make_undo_request())  # pyright: ignore[reportArgumentType]
    assert response.status == 400
    assert "batch_id" in _json_payload(response)["error"].lower()

    # Non-dict JSON body.
    response = await handler.undo_delete(FakeRequest(json_data="not-a-dict"))  # pyright: ignore[reportArgumentType]
    assert response.status == 400

    # Invalid JSON body.
    response = await handler.undo_delete(FakeRequest(raise_json_error=True))  # pyright: ignore[reportArgumentType]
    assert response.status == 400

    # (VAL-1) path-traversal style batch_id -> 400.
    response = await handler.undo_delete(_make_undo_request(batch_id="../evil"))  # pyright: ignore[reportArgumentType]
    assert response.status == 400
    assert "Invalid batch_id" in _json_payload(response)["error"]

    # (VAL-2) non-hex batch_id -> 400.
    response = await handler.undo_delete(_make_undo_request(batch_id="not-a-hex-id"))  # pyright: ignore[reportArgumentType]
    assert response.status == 400
    assert "Invalid batch_id" in _json_payload(response)["error"]


# ---------------------------------------------------------------------------
# (e) route registered exactly ONCE in both modes
# ---------------------------------------------------------------------------
def test_e1_routes_class_registers_undo_route_exactly_once() -> None:
    app = web.Application()
    PendingDeleteRoutes.setup_routes(app)

    assert len(_undo_delete_routes(app)) == 1


def test_e2_plugin_mode_registers_undo_route_exactly_once(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from py import lora_manager

    app = web.Application()
    app._handler_args = {"max_field_size": 1024}
    monkeypatch.setattr(lora_manager.PromptServer, "instance", SimpleNamespace(app=app))

    monkeypatch.setattr(lora_manager, "register_default_model_types", lambda: None)
    monkeypatch.setattr(
        lora_manager.ModelServiceFactory, "setup_all_routes", lambda app_: None
    )
    monkeypatch.setattr(
        lora_manager.ModelServiceFactory, "get_registered_types", lambda: ["dummy"]
    )
    for name in (
        "StatsRoutes",
        "RecipeRoutes",
        "UpdateRoutes",
        "MiscRoutes",
        "ExampleImagesRoutes",
        "PreviewRoutes",
    ):
        monkeypatch.setattr(lora_manager, name, _DummyRoutes)
    monkeypatch.setattr(lora_manager, "ws_manager", _DummyWSManager())
    monkeypatch.setattr(
        lora_manager.settings,
        "get",
        lambda key, default=None: str(tmp_path) if key == "example_images_path" else default,
    )
    monkeypatch.setattr(app.router, "add_static", lambda *a, **k: SimpleNamespace())

    lora_manager.LoraManager.add_routes()

    assert len(_undo_delete_routes(app)) == 1


def test_e3_standalone_mode_registers_undo_route_exactly_once(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    import standalone as standalone_module

    app = web.Application()
    locales_dir = tmp_path / "locales"
    locales_dir.mkdir()
    static_dir = tmp_path / "static"
    static_dir.mkdir()
    monkeypatch.setattr(
        standalone_module,
        "config",
        SimpleNamespace(i18n_path=str(locales_dir), static_path=str(static_dir)),
    )

    import py.services.model_service_factory as factory_module

    monkeypatch.setattr(factory_module, "register_default_model_types", lambda: None)
    monkeypatch.setattr(
        factory_module.ModelServiceFactory,
        "setup_all_routes",
        classmethod(lambda cls, app_arg: None),
    )
    monkeypatch.setattr("py.routes.recipe_routes.RecipeRoutes", _DummyRoutes)
    monkeypatch.setattr("py.routes.update_routes.UpdateRoutes", _DummyRoutes)
    monkeypatch.setattr("py.routes.misc_routes.MiscRoutes", _DummyRoutes)
    monkeypatch.setattr("py.routes.stats_routes.StatsRoutes", _DummyRoutes)
    monkeypatch.setattr("py.routes.example_images_routes.ExampleImagesRoutes", _DummyRoutes)
    monkeypatch.setattr("py.routes.preview_routes.PreviewRoutes", _DummyRoutes)

    async def _noop_ws_handler(request: Any) -> web.Response:
        return web.Response(status=204)

    ws_stub = SimpleNamespace(
        handle_connection=_noop_ws_handler,
        handle_download_connection=_noop_ws_handler,
        handle_init_connection=_noop_ws_handler,
    )
    monkeypatch.setattr("py.services.websocket_manager.ws_manager", ws_stub)

    server = SimpleNamespace(app=app)
    standalone_module.StandaloneLoraManager.add_routes(server)

    assert len(_undo_delete_routes(app)) == 1


# ---------------------------------------------------------------------------
# (f) RESTART-SAFE UNDO (T8): staged batch on disk, no in-process timer
# ---------------------------------------------------------------------------
async def test_f_restart_safe_undo_restores_files_and_cache(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "loras"
    root.mkdir()
    model = root / "model.safetensors"
    # NOTE: the original file does NOT exist - it lives in the staging batch
    # (a delete moved it away before the restart).
    snapshot = {"file_path": str(model), "sha256": "c" * 64, "tags": ["beta"]}

    # Simulate a post-restart state: the batch + manifest exist on disk but
    # nothing was staged in-process (no timer task, no _known_roots entry).
    restart_batch_id = "b" * 32
    batch_dir = root / PENDING_DELETE_DIR_NAME / restart_batch_id
    batch_dir.mkdir(parents=True)
    (batch_dir / "model.safetensors").write_bytes(b"survived-restart")
    _write_batch_manifest(
        batch_dir,
        batch_id=restart_batch_id,
        kind="model",
        model_type="loras",
        expires_at=int(time.time()) + 3600,
        entries=[
            {
                "staged": str(batch_dir / "model.safetensors"),
                "original": str(model),
                "restored": False,
            }
        ],
        model_snapshot=dict(snapshot),
    )

    scanner = FakeScanner(root, model_type="lora")
    await _register_scanners(monkeypatch, lora=scanner)

    from py.routes.handlers.pending_delete_handler import PendingDeleteHandler

    response = await PendingDeleteHandler().undo_delete(
        _make_undo_request(batch_id=restart_batch_id)  # pyright: ignore[reportArgumentType]
    )

    assert response.status == 200
    assert model.read_bytes() == b"survived-restart"
    assert not batch_dir.exists()
    assert len(scanner._cache.raw_data) == 1
    assert scanner._cache.raw_data[0]["file_path"] == str(model)
    assert scanner._tags_count == {"beta": 1}


# ---------------------------------------------------------------------------
# (g) RESCAN STALENESS (T7): stale raw_data entry replaced by the snapshot
# ---------------------------------------------------------------------------
async def test_g_rescan_stale_cache_entry_replaced_by_snapshot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "loras"
    root.mkdir()
    model = root / "model.safetensors"
    model.write_bytes(b"model-data")
    snapshot = {
        "file_path": str(model),
        "sha256": "d" * 64,
        "tags": ["gamma"],
        "model_name": "model",
    }

    scanner = FakeScanner(root, model_type="lora")
    await _register_scanners(monkeypatch, lora=scanner)

    service = await PendingDeleteService.get_instance()
    batch_id = await service.stage_model_delete(
        scanner=scanner,
        target_dir=str(root),
        file_name="model",
        main_extension=".safetensors",
        original_file_path=str(model),
        cached_entry=dict(snapshot),
    )
    assert batch_id is not None

    # A rescan between delete and undo re-added a STALE entry for the same path.
    stale = {
        "file_path": str(model),
        "sha256": "z" * 64,
        "tags": ["stale-tag"],
        "model_name": "stale",
    }
    scanner._cache.raw_data = [stale]

    from py.routes.handlers.pending_delete_handler import PendingDeleteHandler

    response = await PendingDeleteHandler().undo_delete(
        _make_undo_request(batch_id=batch_id)  # pyright: ignore[reportArgumentType]
    )
    assert response.status == 200

    # Exactly one entry remains and it equals the snapshot.
    assert len(scanner._cache.raw_data) == 1
    assert scanner._cache.raw_data[0] == snapshot
    assert scanner._tags_count == {"gamma": 1}


# ---------------------------------------------------------------------------
# (h) RECIPE RE-DELETE AFTER UNDO (T9): path map rebuilt by forced refresh
# ---------------------------------------------------------------------------
async def test_h_recipe_redo_delete_after_undo_and_refresh_succeeds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    recipe_json = tmp_path / "my_recipe.recipe.json"
    recipe_data = {"id": "r1", "name": "Recipe One", "file_path": str(recipe_json)}
    recipe_json.write_text(json.dumps(recipe_data), encoding="utf-8")

    recipe_scanner = FakeRecipeScanner()
    await _register_scanners(monkeypatch, recipe=recipe_scanner)

    service = await PendingDeleteService.get_instance()
    batch_id = await service.stage_recipe_delete(
        recipe_json_path=str(recipe_json),
        image_path=None,
        recipe_data=dict(recipe_data),
    )
    assert batch_id is not None
    recipe_json.unlink()

    from py.routes.handlers.pending_delete_handler import PendingDeleteHandler

    handler = PendingDeleteHandler()
    response = await handler.undo_delete(_make_undo_request(batch_id=batch_id))  # pyright: ignore[reportArgumentType]
    assert response.status == 200
    assert recipe_json.exists()
    assert recipe_scanner.added == [recipe_data]

    # Forced frontend refresh rebuilds the scanner path map.
    recipe_scanner.force_refresh()
    assert recipe_scanner._json_path_map.get("r1") == str(recipe_json)

    # Immediately deleting the same recipe again succeeds.
    batch_id2 = await service.stage_recipe_delete(
        recipe_json_path=str(recipe_json),
        image_path=None,
        recipe_data=dict(recipe_data),
    )
    assert batch_id2 is not None
    recipe_json.unlink()
    response2 = await handler.undo_delete(_make_undo_request(batch_id=batch_id2))  # pyright: ignore[reportArgumentType]
    assert response2.status == 200
    assert recipe_json.exists()


# ---------------------------------------------------------------------------
# (i) recipe undo WITHOUT prior refresh still restores files (no crash)
# ---------------------------------------------------------------------------
async def test_i_recipe_undo_without_refresh_still_restores_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    recipe_json = tmp_path / "no_refresh.recipe.json"
    recipe_data = {"id": "r2", "name": "No Refresh"}
    recipe_json.write_text(json.dumps(recipe_data), encoding="utf-8")

    recipe_scanner = FakeRecipeScanner()
    await _register_scanners(monkeypatch, recipe=recipe_scanner)

    service = await PendingDeleteService.get_instance()
    batch_id = await service.stage_recipe_delete(
        recipe_json_path=str(recipe_json),
        image_path=None,
        recipe_data=dict(recipe_data),
    )
    assert batch_id is not None
    recipe_json.unlink()

    from py.routes.handlers.pending_delete_handler import PendingDeleteHandler

    response = await PendingDeleteHandler().undo_delete(
        _make_undo_request(batch_id=batch_id)  # pyright: ignore[reportArgumentType]
    )

    assert response.status == 200
    assert recipe_json.read_text(encoding="utf-8") == json.dumps(recipe_data)
    assert recipe_scanner.added == [recipe_data]


# ---------------------------------------------------------------------------
# (j) TAG COUNTS: bulk-delete 2 tagged models, undo restores pre-delete counts
# ---------------------------------------------------------------------------
async def test_j_undo_restores_tag_counts_after_bulk_delete(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "loras"
    root.mkdir()
    model_a = root / "alpha.safetensors"
    model_a.write_bytes(b"alpha")
    model_b = root / "beta.safetensors"
    model_b.write_bytes(b"beta")

    snapshot_a = {"file_path": str(model_a), "sha256": "e" * 64, "tags": ["alpha"]}
    snapshot_b = {"file_path": str(model_b), "sha256": "f" * 64, "tags": ["beta"]}

    scanner = FakeScanner(root, model_type="lora")
    await _register_scanners(monkeypatch, lora=scanner)

    service = await PendingDeleteService.get_instance()
    batch_a = await service.stage_model_delete(
        scanner=scanner,
        target_dir=str(root),
        file_name="alpha",
        main_extension=".safetensors",
        original_file_path=str(model_a),
        cached_entry=dict(snapshot_a),
    )
    batch_b = await service.stage_model_delete(
        scanner=scanner,
        target_dir=str(root),
        file_name="beta",
        main_extension=".safetensors",
        original_file_path=str(model_b),
        cached_entry=dict(snapshot_b),
    )
    assert batch_a is not None
    assert batch_b is not None

    # Simulate the bulk-delete cache mutation (mirror of
    # _batch_update_cache_for_deleted_models): entries removed, tags decremented.
    scanner._cache.raw_data = [dict(snapshot_a), dict(snapshot_b)]
    scanner._tags_count = {"alpha": 1, "beta": 1}
    for model in (dict(snapshot_a), dict(snapshot_b)):
        for tag in model.get("tags", []):
            if tag in scanner._tags_count:
                scanner._tags_count[tag] = max(0, scanner._tags_count[tag] - 1)
                if scanner._tags_count[tag] == 0:
                    del scanner._tags_count[tag]
    scanner._cache.raw_data = []
    pre_delete_counts = {"alpha": 1, "beta": 1}

    from py.routes.handlers.pending_delete_handler import PendingDeleteHandler

    handler = PendingDeleteHandler()
    # Sequential undo of the (unmerged) constituent batches - the batch_ids
    # fallback path used by the frontend for cross-volume bulks.
    assert (await handler.undo_delete(_make_undo_request(batch_id=batch_a))).status == 200  # pyright: ignore[reportArgumentType]
    assert (await handler.undo_delete(_make_undo_request(batch_id=batch_b))).status == 200  # pyright: ignore[reportArgumentType]

    assert scanner._tags_count == pre_delete_counts
    assert {item["file_path"] for item in scanner._cache.raw_data} == {
        str(model_a),
        str(model_b),
    }
    assert model_a.read_bytes() == b"alpha"
    assert model_b.read_bytes() == b"beta"


# ---------------------------------------------------------------------------
# (k) EMBEDDINGS UNDO: resolves the embedding scanner, not the lora scanner
# ---------------------------------------------------------------------------
async def test_k_undo_embeddings_batch_updates_embedding_cache_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    emb_root = tmp_path / "embeddings"
    emb_root.mkdir()
    model = emb_root / "my_embedding.safetensors"
    model.write_bytes(b"emb-data")
    snapshot = {
        "file_path": str(model),
        "sha256": "g" * 64,
        "tags": [],
        "model_name": "my_embedding",
    }

    lora_scanner = FakeScanner(tmp_path / "loras", model_type="lora")
    emb_scanner = FakeScanner(emb_root, model_type="embedding")
    lora_scanner._cache.raw_data = [{"file_path": "/loras/other.safetensors", "sha256": "x"}]
    emb_scanner._cache.raw_data = [dict(snapshot)]
    await _register_scanners(monkeypatch, lora=lora_scanner, embedding=emb_scanner)

    service = await PendingDeleteService.get_instance()
    batch_id = await service.stage_model_delete(
        scanner=emb_scanner,
        target_dir=str(emb_root),
        file_name="my_embedding",
        main_extension=".safetensors",
        original_file_path=str(model),
        cached_entry=dict(snapshot),
    )
    assert batch_id is not None
    emb_scanner._cache.raw_data = []

    from py.routes.handlers.pending_delete_handler import PendingDeleteHandler

    response = await PendingDeleteHandler().undo_delete(
        _make_undo_request(batch_id=batch_id)  # pyright: ignore[reportArgumentType]
    )
    assert response.status == 200

    # The EMBEDDINGS cache was updated, not the lora cache.
    assert len(emb_scanner._cache.raw_data) == 1
    assert emb_scanner._cache.raw_data[0]["file_path"] == str(model)
    assert len(lora_scanner._cache.raw_data) == 1  # untouched
    assert model.read_bytes() == b"emb-data"


# ---------------------------------------------------------------------------
# (BULK-UNDO) MERGED bulk undo restores ALL cache entries (not just the winner)
# ---------------------------------------------------------------------------
async def test_bulk_undo_after_merge_restores_all_cache_entries(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "loras"
    root.mkdir()
    model_a = root / "alpha.safetensors"
    model_a.write_bytes(b"alpha")
    model_b = root / "beta.safetensors"
    model_b.write_bytes(b"beta")

    snapshot_a = {
        "file_path": str(model_a),
        "sha256": "e" * 64,
        "tags": ["alpha"],
        "model_name": "alpha",
    }
    snapshot_b = {
        "file_path": str(model_b),
        "sha256": "f" * 64,
        "tags": ["beta"],
        "model_name": "beta",
    }

    scanner = FakeScanner(root, model_type="lora")
    await _register_scanners(monkeypatch, lora=scanner)

    service = await PendingDeleteService.get_instance()
    batch_a = await service.stage_model_delete(
        scanner=scanner,
        target_dir=str(root),
        file_name="alpha",
        main_extension=".safetensors",
        original_file_path=str(model_a),
        cached_entry=dict(snapshot_a),
    )
    batch_b = await service.stage_model_delete(
        scanner=scanner,
        target_dir=str(root),
        file_name="beta",
        main_extension=".safetensors",
        original_file_path=str(model_b),
        cached_entry=dict(snapshot_b),
    )
    assert batch_a is not None
    assert batch_b is not None
    merged = await service.merge_batches([batch_a, batch_b])
    assert merged == batch_a

    # Simulate the bulk-delete cache mutation (entries removed, tags cleared).
    scanner._cache.raw_data = []
    scanner._tags_count = {}
    scanner._hash_index = FakeHashIndex()

    from py.routes.handlers.pending_delete_handler import PendingDeleteHandler

    response = await PendingDeleteHandler().undo_delete(
        _make_undo_request(batch_id=merged)  # pyright: ignore[reportArgumentType]
    )
    assert response.status == 200

    # BOTH entries restored - the loser's file_path present in raw_data.
    assert {item["file_path"] for item in scanner._cache.raw_data} == {
        str(model_a),
        str(model_b),
    }
    # Hash index carries both paths.
    assert {entry[1] for entry in scanner._hash_index.entries} == {
        str(model_a),
        str(model_b),
    }
    # Tag counts match pre-delete counts for tagged models.
    assert scanner._tags_count == {"alpha": 1, "beta": 1}
    # Files restored byte-identical.
    assert model_a.read_bytes() == b"alpha"
    assert model_b.read_bytes() == b"beta"


# ---------------------------------------------------------------------------
# (BC-1) backward compat: entries WITHOUT snapshots + top-level model_snapshot
# ---------------------------------------------------------------------------
async def test_bc1_old_format_manifest_falls_back_to_top_level_snapshot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "loras"
    root.mkdir()
    model = root / "model.safetensors"
    snapshot = {
        "file_path": str(model),
        "sha256": "c" * 64,
        "tags": ["beta"],
        "model_name": "model",
    }

    # Old-format manifest: entries carry NO snapshot; only the top-level
    # model_snapshot exists (pre-F3 single-delete manifests).
    batch_id = "a" * 32
    batch_dir = root / PENDING_DELETE_DIR_NAME / batch_id
    batch_dir.mkdir(parents=True)
    (batch_dir / "model.safetensors").write_bytes(b"old-format-data")
    _write_batch_manifest(
        batch_dir,
        batch_id=batch_id,
        kind="model",
        model_type="loras",
        expires_at=int(time.time()) + 3600,
        entries=[
            {
                "staged": str(batch_dir / "model.safetensors"),
                "original": str(model),
                "restored": False,
            }
        ],
        model_snapshot=dict(snapshot),
    )

    scanner = FakeScanner(root, model_type="lora")
    await _register_scanners(monkeypatch, lora=scanner)

    from py.routes.handlers.pending_delete_handler import PendingDeleteHandler

    response = await PendingDeleteHandler().undo_delete(
        _make_undo_request(batch_id=batch_id)  # pyright: ignore[reportArgumentType]
    )
    assert response.status == 200

    # The top-level snapshot entry is still restored exactly.
    assert len(scanner._cache.raw_data) == 1
    assert scanner._cache.raw_data[0] == snapshot
    assert scanner._tags_count == {"beta": 1}
    assert model.read_bytes() == b"old-format-data"

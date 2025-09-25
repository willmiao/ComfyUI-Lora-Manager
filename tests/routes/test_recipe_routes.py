"""Integration smoke tests for the recipe route stack."""
from __future__ import annotations

import json
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any, AsyncIterator, Dict, List, Optional

from aiohttp import FormData, web
from aiohttp.test_utils import TestClient, TestServer

from py.config import config
from py.routes import base_recipe_routes
from py.routes.recipe_routes import RecipeRoutes
from py.services.recipes import RecipeValidationError
from py.services.service_registry import ServiceRegistry


@dataclass
class RecipeRouteHarness:
    """Container exposing the aiohttp client and stubbed collaborators."""

    client: TestClient
    scanner: "StubRecipeScanner"
    analysis: "StubAnalysisService"
    persistence: "StubPersistenceService"
    sharing: "StubSharingService"
    tmp_dir: Path


class StubRecipeScanner:
    """Minimal scanner double with the surface used by the handlers."""

    def __init__(self, base_dir: Path) -> None:
        self.recipes_dir = str(base_dir / "recipes")
        self.listing_items: List[Dict[str, Any]] = []
        self.cached_raw: List[Dict[str, Any]] = []
        self.recipes: Dict[str, Dict[str, Any]] = {}
        self.removed: List[str] = []

        async def _noop_get_cached_data(force_refresh: bool = False) -> None:  # noqa: ARG001 - signature mirrors real scanner
            return None

        self._lora_scanner = SimpleNamespace(  # mimic BaseRecipeRoutes expectations
            get_cached_data=_noop_get_cached_data,
            _hash_index=SimpleNamespace(_hash_to_path={}),
        )

    async def get_cached_data(self, force_refresh: bool = False) -> SimpleNamespace:  # noqa: ARG002 - flag unused by stub
        return SimpleNamespace(raw_data=list(self.cached_raw))

    async def get_paginated_data(self, **params: Any) -> Dict[str, Any]:
        items = [dict(item) for item in self.listing_items]
        page = int(params.get("page", 1))
        page_size = int(params.get("page_size", 20))
        return {
            "items": items,
            "total": len(items),
            "page": page,
            "page_size": page_size,
            "total_pages": max(1, (len(items) + page_size - 1) // max(page_size, 1)),
        }

    async def get_recipe_by_id(self, recipe_id: str) -> Optional[Dict[str, Any]]:
        return self.recipes.get(recipe_id)

    async def remove_recipe(self, recipe_id: str) -> None:
        self.removed.append(recipe_id)
        self.recipes.pop(recipe_id, None)


class StubAnalysisService:
    """Captures calls made by analysis routes while returning canned responses."""

    instances: List["StubAnalysisService"] = []

    def __init__(self, **_: Any) -> None:
        self.raise_for_uploaded: Optional[Exception] = None
        self.raise_for_remote: Optional[Exception] = None
        self.raise_for_local: Optional[Exception] = None
        self.upload_calls: List[bytes] = []
        self.remote_calls: List[Optional[str]] = []
        self.local_calls: List[Optional[str]] = []
        self.result = SimpleNamespace(payload={"loras": []}, status=200)
        StubAnalysisService.instances.append(self)

    async def analyze_uploaded_image(self, *, image_bytes: bytes | None, recipe_scanner) -> SimpleNamespace:  # noqa: D401 - mirrors real signature
        if self.raise_for_uploaded:
            raise self.raise_for_uploaded
        self.upload_calls.append(image_bytes or b"")
        return self.result

    async def analyze_remote_image(self, *, url: Optional[str], recipe_scanner, civitai_client) -> SimpleNamespace:  # noqa: D401
        if self.raise_for_remote:
            raise self.raise_for_remote
        self.remote_calls.append(url)
        return self.result

    async def analyze_local_image(self, *, file_path: Optional[str], recipe_scanner) -> SimpleNamespace:  # noqa: D401
        if self.raise_for_local:
            raise self.raise_for_local
        self.local_calls.append(file_path)
        return self.result

    async def analyze_widget_metadata(self, *, recipe_scanner) -> SimpleNamespace:
        return SimpleNamespace(payload={"metadata": {}, "image_bytes": b""}, status=200)


class StubPersistenceService:
    """Stub for persistence operations to avoid filesystem writes."""

    instances: List["StubPersistenceService"] = []

    def __init__(self, **_: Any) -> None:
        self.save_calls: List[Dict[str, Any]] = []
        self.delete_calls: List[str] = []
        self.save_result = SimpleNamespace(payload={"success": True, "recipe_id": "stub-id"}, status=200)
        self.delete_result = SimpleNamespace(payload={"success": True}, status=200)
        StubPersistenceService.instances.append(self)

    async def save_recipe(self, *, recipe_scanner, image_bytes, image_base64, name, tags, metadata) -> SimpleNamespace:  # noqa: D401
        self.save_calls.append(
            {
                "recipe_scanner": recipe_scanner,
                "image_bytes": image_bytes,
                "image_base64": image_base64,
                "name": name,
                "tags": list(tags),
                "metadata": metadata,
            }
        )
        return self.save_result

    async def delete_recipe(self, *, recipe_scanner, recipe_id: str) -> SimpleNamespace:
        self.delete_calls.append(recipe_id)
        await recipe_scanner.remove_recipe(recipe_id)
        return self.delete_result

    async def update_recipe(self, *, recipe_scanner, recipe_id: str, updates: Dict[str, Any]) -> SimpleNamespace:  # pragma: no cover - unused by smoke tests
        return SimpleNamespace(payload={"success": True, "recipe_id": recipe_id, "updates": updates}, status=200)

    async def reconnect_lora(self, *, recipe_scanner, recipe_id: str, lora_index: int, target_name: str) -> SimpleNamespace:  # pragma: no cover
        return SimpleNamespace(payload={"success": True}, status=200)

    async def bulk_delete(self, *, recipe_scanner, recipe_ids: List[str]) -> SimpleNamespace:  # pragma: no cover
        return SimpleNamespace(payload={"success": True, "deleted": recipe_ids}, status=200)

    async def save_recipe_from_widget(self, *, recipe_scanner, metadata: Dict[str, Any], image_bytes: bytes) -> SimpleNamespace:  # pragma: no cover
        return SimpleNamespace(payload={"success": True}, status=200)


class StubSharingService:
    """Share service stub recording requests and returning canned responses."""

    instances: List["StubSharingService"] = []

    def __init__(self, *, ttl_seconds: int = 300, logger) -> None:  # noqa: ARG002 - ttl unused in stub
        self.share_calls: List[str] = []
        self.download_calls: List[str] = []
        self.share_result = SimpleNamespace(
            payload={"success": True, "download_url": "/share/stub", "filename": "recipe.png"},
            status=200,
        )
        self.download_info = SimpleNamespace(file_path="", download_filename="")
        StubSharingService.instances.append(self)

    async def share_recipe(self, *, recipe_scanner, recipe_id: str) -> SimpleNamespace:
        self.share_calls.append(recipe_id)
        return self.share_result

    async def prepare_download(self, *, recipe_scanner, recipe_id: str) -> SimpleNamespace:
        self.download_calls.append(recipe_id)
        return self.download_info


@asynccontextmanager
async def recipe_harness(monkeypatch, tmp_path: Path) -> AsyncIterator[RecipeRouteHarness]:
    """Context manager that yields a fully wired recipe route harness."""

    StubAnalysisService.instances.clear()
    StubPersistenceService.instances.clear()
    StubSharingService.instances.clear()

    scanner = StubRecipeScanner(tmp_path)

    async def fake_get_recipe_scanner():
        return scanner

    async def fake_get_civitai_client():
        return object()

    monkeypatch.setattr(ServiceRegistry, "get_recipe_scanner", fake_get_recipe_scanner)
    monkeypatch.setattr(ServiceRegistry, "get_civitai_client", fake_get_civitai_client)
    monkeypatch.setattr(base_recipe_routes, "RecipeAnalysisService", StubAnalysisService)
    monkeypatch.setattr(base_recipe_routes, "RecipePersistenceService", StubPersistenceService)
    monkeypatch.setattr(base_recipe_routes, "RecipeSharingService", StubSharingService)
    monkeypatch.setattr(config, "loras_roots", [str(tmp_path)], raising=False)

    app = web.Application()
    RecipeRoutes.setup_routes(app)

    server = TestServer(app)
    client = TestClient(server)
    await client.start_server()

    harness = RecipeRouteHarness(
        client=client,
        scanner=scanner,
        analysis=StubAnalysisService.instances[-1],
        persistence=StubPersistenceService.instances[-1],
        sharing=StubSharingService.instances[-1],
        tmp_dir=tmp_path,
    )

    try:
        yield harness
    finally:
        await client.close()
        StubAnalysisService.instances.clear()
        StubPersistenceService.instances.clear()
        StubSharingService.instances.clear()


async def test_list_recipes_provides_file_urls(monkeypatch, tmp_path: Path) -> None:
    async with recipe_harness(monkeypatch, tmp_path) as harness:
        recipe_path = harness.tmp_dir / "recipes" / "demo.png"
        harness.scanner.listing_items = [
            {
                "id": "recipe-1",
                "file_path": str(recipe_path),
                "title": "Demo",
                "loras": [],
            }
        ]
        harness.scanner.cached_raw = list(harness.scanner.listing_items)

        response = await harness.client.get("/api/lm/recipes")
        payload = await response.json()

        assert response.status == 200
        assert payload["items"][0]["file_url"].endswith("demo.png")
        assert payload["items"][0]["loras"] == []


async def test_save_and_delete_recipe_round_trip(monkeypatch, tmp_path: Path) -> None:
    async with recipe_harness(monkeypatch, tmp_path) as harness:
        form = FormData()
        form.add_field("image", b"stub", filename="sample.png", content_type="image/png")
        form.add_field("name", "Test Recipe")
        form.add_field("tags", json.dumps(["tag-a"]))
        form.add_field("metadata", json.dumps({"loras": []}))
        form.add_field("image_base64", "aW1hZ2U=")

        harness.persistence.save_result = SimpleNamespace(
            payload={"success": True, "recipe_id": "saved-id"},
            status=201,
        )

        save_response = await harness.client.post("/api/lm/recipes/save", data=form)
        save_payload = await save_response.json()

        assert save_response.status == 201
        assert save_payload["recipe_id"] == "saved-id"
        assert harness.persistence.save_calls[-1]["name"] == "Test Recipe"

        harness.persistence.delete_result = SimpleNamespace(payload={"success": True}, status=200)

        delete_response = await harness.client.delete("/api/lm/recipe/saved-id")
        delete_payload = await delete_response.json()

        assert delete_response.status == 200
        assert delete_payload["success"] is True
        assert harness.persistence.delete_calls == ["saved-id"]


async def test_analyze_uploaded_image_error_path(monkeypatch, tmp_path: Path) -> None:
    async with recipe_harness(monkeypatch, tmp_path) as harness:
        harness.analysis.raise_for_uploaded = RecipeValidationError("No image data provided")

        form = FormData()
        form.add_field("image", b"", filename="empty.png", content_type="image/png")

        response = await harness.client.post("/api/lm/recipes/analyze-image", data=form)
        payload = await response.json()

        assert response.status == 400
        assert payload["error"] == "No image data provided"
        assert payload["loras"] == []


async def test_share_and_download_recipe(monkeypatch, tmp_path: Path) -> None:
    async with recipe_harness(monkeypatch, tmp_path) as harness:
        recipe_id = "share-me"
        download_path = harness.tmp_dir / "recipes" / "share.png"
        download_path.parent.mkdir(parents=True, exist_ok=True)
        download_path.write_bytes(b"stub")

        harness.scanner.recipes[recipe_id] = {
            "id": recipe_id,
            "title": "Shared",
            "file_path": str(download_path),
        }

        harness.sharing.share_result = SimpleNamespace(
            payload={"success": True, "download_url": "/api/share", "filename": "share.png"},
            status=200,
        )
        harness.sharing.download_info = SimpleNamespace(
            file_path=str(download_path),
            download_filename="share.png",
        )

        share_response = await harness.client.get(f"/api/lm/recipe/{recipe_id}/share")
        share_payload = await share_response.json()

        assert share_response.status == 200
        assert share_payload["filename"] == "share.png"
        assert harness.sharing.share_calls == [recipe_id]

        download_response = await harness.client.get(f"/api/lm/recipe/{recipe_id}/share/download")
        body = await download_response.read()

        assert download_response.status == 200
        assert download_response.headers["Content-Disposition"] == 'attachment; filename="share.png"'
        assert body == b"stub"

        download_path.unlink(missing_ok=True)


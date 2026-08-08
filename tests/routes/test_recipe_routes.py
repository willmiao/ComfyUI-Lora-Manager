"""Integration smoke tests for the recipe route stack."""

from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any, AsyncIterator, Dict, List, Optional

from aiohttp import FormData, web
from aiohttp.test_utils import TestClient, TestServer
from PIL import Image

from py.config import config
from py.routes import base_recipe_routes
from py.routes.handlers import recipe_handlers
from py.routes.recipe_routes import RecipeRoutes
from py.recipes.parsers.civitai_image import CivitaiApiMetadataParser
from py.services.recipes import RecipeValidationError, RecipeNotFoundError
from py.services.service_registry import ServiceRegistry


@dataclass
class RecipeRouteHarness:
    """Container exposing the aiohttp client and stubbed collaborators."""

    client: TestClient[Any, Any]
    scanner: "StubRecipeScanner"
    analysis: "StubAnalysisService"
    persistence: "StubPersistenceService"
    sharing: "StubSharingService"
    downloader: "StubDownloader"
    civitai: "StubCivitaiClient"
    tmp_dir: Path


class StubRecipeScanner:
    """Minimal scanner double with the surface used by the handlers."""

    def __init__(self, base_dir: Path) -> None:
        self.recipes_dir = str(base_dir / "recipes")
        self.listing_items: List[Dict[str, Any]] = []
        self.cached_raw: List[Dict[str, Any]] = []
        self.recipes: Dict[str, Dict[str, Any]] = {}
        self.removed: List[str] = []
        self.last_paginated_params: Dict[str, Any] | None = None
        self.lora_lookup: Dict[str, List[Dict[str, Any]]] = {}
        self.checkpoint_lookup: Dict[str, List[Dict[str, Any]]] = {}
        self.image_id_map_override: Dict[str, str] = {}
        self.local_hash_cache: Dict[str, Dict[str, Any]] | None = None

        async def _noop_get_cached_data(force_refresh: bool = False) -> None:  # noqa: ARG001 - signature mirrors real scanner
            return None

        self._lora_scanner: Any = SimpleNamespace(  # mimic BaseRecipeRoutes expectations
            get_cached_data=_noop_get_cached_data,
            _hash_index=SimpleNamespace(_hash_to_path={}),
        )

    async def get_cached_data(self, force_refresh: bool = False) -> SimpleNamespace:  # noqa: ARG002 - flag unused by stub
        return SimpleNamespace(
            raw_data=list(self.cached_raw),
            image_id_map=dict(getattr(self, "image_id_map_override", {})),
        )

    async def build_local_hash_cache(self) -> Dict[str, Dict[str, Any]]:
        """Return the stub's local hash map; empty unless a test overrides it."""
        cache = getattr(self, "local_hash_cache", None)
        return cache if cache is not None else {}

    async def get_paginated_data(self, **params: Any) -> Dict[str, Any]:
        self.last_paginated_params = params
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

    async def get_recipes_for_lora(self, lora_hash: str) -> List[Dict[str, Any]]:
        return list(self.lora_lookup.get(lora_hash.lower(), []))

    async def get_recipes_for_checkpoint(
        self, checkpoint_hash: str
    ) -> List[Dict[str, Any]]:
        return list(self.checkpoint_lookup.get(checkpoint_hash.lower(), []))

    async def get_recipe_json_path(self, recipe_id: str) -> Optional[str]:
        candidate = Path(self.recipes_dir) / f"{recipe_id}.recipe.json"
        return str(candidate) if candidate.exists() else None

    async def get_recipe_syntax_tokens(self, recipe_id: str) -> List[str]:
        return self.recipes.get(recipe_id, {}).get("syntax", [])  # pragma: no cover - overridden per test

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
        self._recipe_parser_factory: Any = None
        StubAnalysisService.instances.append(self)

    async def analyze_uploaded_image(
        self, *, image_bytes: bytes | None, recipe_scanner
    ) -> SimpleNamespace:  # noqa: D401 - mirrors real signature
        if self.raise_for_uploaded:
            raise self.raise_for_uploaded
        self.upload_calls.append(image_bytes or b"")
        return self.result

    async def analyze_remote_image(
        self, *, url: Optional[str], recipe_scanner, civitai_client
    ) -> SimpleNamespace:  # noqa: D401
        if self.raise_for_remote:
            raise self.raise_for_remote
        self.remote_calls.append(url)
        return self.result

    async def analyze_local_image(
        self, *, file_path: Optional[str], recipe_scanner
    ) -> SimpleNamespace:  # noqa: D401
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
        self.move_calls: List[Dict[str, str]] = []
        self.update_calls: List[Dict[str, Any]] = []
        self.save_result = SimpleNamespace(
            payload={"success": True, "recipe_id": "stub-id"}, status=200
        )
        self.delete_result = SimpleNamespace(payload={"success": True}, status=200)
        StubPersistenceService.instances.append(self)

    async def save_recipe(
        self,
        *,
        recipe_scanner,
        image_bytes,
        image_base64,
        name,
        tags,
        metadata,
        extension=None,
        recipe_id=None,
        target_dir=None,
    ) -> SimpleNamespace:  # noqa: D401
        self.save_calls.append(
            {
                "recipe_scanner": recipe_scanner,
                "image_bytes": image_bytes,
                "image_base64": image_base64,
                "name": name,
                "tags": list(tags),
                "metadata": metadata,
                "extension": extension,
                "recipe_id": recipe_id,
                "target_dir": target_dir,
            }
        )
        return self.save_result

    async def delete_recipe(self, *, recipe_scanner, recipe_id: str) -> SimpleNamespace:
        self.delete_calls.append(recipe_id)
        await recipe_scanner.remove_recipe(recipe_id)
        return self.delete_result

    async def move_recipe(
        self, *, recipe_scanner, recipe_id: str, target_path: str
    ) -> SimpleNamespace:  # noqa: D401
        self.move_calls.append({"recipe_id": recipe_id, "target_path": target_path})
        return SimpleNamespace(
            payload={
                "success": True,
                "recipe_id": recipe_id,
                "new_file_path": target_path,
            },
            status=200,
        )

    async def update_recipe(
        self, *, recipe_scanner, recipe_id: str, updates: Dict[str, Any]
    ) -> SimpleNamespace:
        self.update_calls.append(
            {
                "recipe_scanner": recipe_scanner,
                "recipe_id": recipe_id,
                "updates": updates,
            }
        )
        return SimpleNamespace(
            payload={"success": True, "recipe_id": recipe_id, "updates": updates},
            status=200,
        )

    async def reconnect_lora(
        self, *, recipe_scanner, recipe_id: str, lora_index: int, target_name: str
    ) -> SimpleNamespace:  # pragma: no cover
        return SimpleNamespace(payload={"success": True}, status=200)

    async def bulk_delete(
        self, *, recipe_scanner, recipe_ids: List[str]
    ) -> SimpleNamespace:  # pragma: no cover
        return SimpleNamespace(
            payload={"success": True, "deleted": recipe_ids}, status=200
        )

    async def save_recipe_from_widget(
        self, *, recipe_scanner, metadata: Dict[str, Any], image_bytes: bytes
    ) -> SimpleNamespace:  # pragma: no cover
        return SimpleNamespace(payload={"success": True}, status=200)


class StubSharingService:
    """Share service stub recording requests and returning canned responses."""

    instances: List["StubSharingService"] = []

    def __init__(self, *, ttl_seconds: int = 300, logger) -> None:  # noqa: ARG002 - ttl unused in stub
        self.share_calls: List[str] = []
        self.download_calls: List[str] = []
        self.share_result = SimpleNamespace(
            payload={
                "success": True,
                "download_url": "/share/stub",
                "filename": "recipe.png",
            },
            status=200,
        )
        self.download_info = SimpleNamespace(file_path="", download_filename="")
        StubSharingService.instances.append(self)

    async def share_recipe(self, *, recipe_scanner, recipe_id: str) -> SimpleNamespace:
        self.share_calls.append(recipe_id)
        return self.share_result

    async def prepare_download(
        self, *, recipe_scanner, recipe_id: str
    ) -> SimpleNamespace:
        self.download_calls.append(recipe_id)
        return self.download_info


class StubDownloader:
    """Downloader stub that writes deterministic bytes to requested locations."""

    def __init__(self) -> None:
        self.urls: List[str] = []

    async def download_file(self, url: str, destination: str, use_auth: bool = False):  # noqa: ARG002 - use_auth unused
        self.urls.append(url)
        Path(destination).write_bytes(b"imported-image")
        return True, destination


class StubCivitaiClient:
    """Stub for Civitai API client."""

    def __init__(self) -> None:
        self.image_info: Dict[str, Any] = {}

    async def get_image_info(
        self, image_id: str, source_url: str | None = None
    ) -> Optional[Dict[str, Any]]:
        return self.image_info.get(image_id)


@asynccontextmanager
async def recipe_harness(
    monkeypatch, tmp_path: Path
) -> AsyncIterator[RecipeRouteHarness]:
    """Context manager that yields a fully wired recipe route harness."""

    StubAnalysisService.instances.clear()
    StubPersistenceService.instances.clear()
    StubSharingService.instances.clear()

    scanner = StubRecipeScanner(tmp_path)
    civitai_client = StubCivitaiClient()

    async def fake_get_recipe_scanner():
        return scanner

    async def fake_get_civitai_client():
        return civitai_client

    downloader = StubDownloader()

    async def fake_get_downloader():
        return downloader

    monkeypatch.setattr(ServiceRegistry, "get_recipe_scanner", fake_get_recipe_scanner)
    monkeypatch.setattr(ServiceRegistry, "get_civitai_client", fake_get_civitai_client)
    monkeypatch.setattr(
        base_recipe_routes, "RecipeAnalysisService", StubAnalysisService
    )
    monkeypatch.setattr(
        base_recipe_routes, "RecipePersistenceService", StubPersistenceService
    )
    monkeypatch.setattr(base_recipe_routes, "RecipeSharingService", StubSharingService)
    monkeypatch.setattr(base_recipe_routes, "get_downloader", fake_get_downloader)
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
        downloader=downloader,
        civitai=civitai_client,
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


async def test_list_recipes_exposes_preview_dimensions(
    monkeypatch, tmp_path: Path
) -> None:
    """(a) Image recipe items carry integer width/height from the on-disk file."""
    async with recipe_harness(monkeypatch, tmp_path) as harness:
        recipe_path = harness.tmp_dir / "recipes" / "real.png"
        recipe_path.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (64, 32), color="red").save(recipe_path)

        harness.scanner.listing_items = [
            {
                "id": "recipe-1",
                "file_path": str(recipe_path),
                "title": "Image Recipe",
                "loras": [],
            }
        ]
        harness.scanner.cached_raw = list(harness.scanner.listing_items)

        response = await harness.client.get("/api/lm/recipes")
        payload = await response.json()

        assert response.status == 200
        item = payload["items"][0]
        assert item["width"] == 64
        assert item["height"] == 32
        assert isinstance(item["width"], int)
        assert isinstance(item["height"], int)


async def test_list_recipes_omits_dimensions_for_video_and_missing(
    monkeypatch, tmp_path: Path
) -> None:
    """(b) Video/missing-image recipes omit width/height yet still return 200."""
    async with recipe_harness(monkeypatch, tmp_path) as harness:
        harness.scanner.listing_items = [
            {
                "id": "recipe-video",
                "file_path": str(harness.tmp_dir / "recipes" / "preview.mp4"),
                "title": "Video Recipe",
                "loras": [],
            },
            {
                "id": "recipe-missing",
                "file_path": str(harness.tmp_dir / "recipes" / "gone.png"),
                "title": "Missing Recipe",
                "loras": [],
            },
        ]
        harness.scanner.cached_raw = list(harness.scanner.listing_items)

        response = await harness.client.get("/api/lm/recipes")
        payload = await response.json()

        assert response.status == 200
        for item in payload["items"]:
            assert "width" not in item
            assert "height" not in item


async def test_list_recipes_offloads_dimensions_to_thread(
    monkeypatch, tmp_path: Path
) -> None:
    """(c) Dimension reads run through asyncio.to_thread for every item."""
    async with recipe_harness(monkeypatch, tmp_path) as harness:
        recipe_path = harness.tmp_dir / "recipes" / "real.png"
        recipe_path.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (16, 48), color="blue").save(recipe_path)

        harness.scanner.listing_items = [
            {
                "id": "recipe-1",
                "file_path": str(recipe_path),
                "title": "Image Recipe",
                "loras": [],
            },
            {
                "id": "recipe-2",
                "file_path": str(harness.tmp_dir / "recipes" / "gone.png"),
                "title": "Missing Recipe",
                "loras": [],
            },
        ]
        harness.scanner.cached_raw = list(harness.scanner.listing_items)

        real_to_thread = asyncio.to_thread
        to_thread_calls: list[tuple[Any, ...]] = []

        async def counting_to_thread(fn, *args, **kwargs):
            to_thread_calls.append((fn, args, kwargs))
            return await real_to_thread(fn, *args, **kwargs)

        monkeypatch.setattr(asyncio, "to_thread", counting_to_thread)

        response = await harness.client.get("/api/lm/recipes")
        payload = await response.json()

        assert response.status == 200
        assert len(to_thread_calls) >= len(harness.scanner.listing_items)
        assert payload["items"][0]["width"] == 16
        assert payload["items"][0]["height"] == 48
        assert "width" not in payload["items"][1]
        assert "height" not in payload["items"][1]


async def test_list_recipes_batches_dimensions_for_mixed_items(
    monkeypatch, tmp_path: Path
) -> None:
    """(d) Mixed file_path presence: dims align per-item with their own files."""
    async with recipe_harness(monkeypatch, tmp_path) as harness:
        wide_path = harness.tmp_dir / "recipes" / "wide.png"
        tall_path = harness.tmp_dir / "recipes" / "tall.png"
        wide_path.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (120, 40), color="green").save(wide_path)
        Image.new("RGB", (30, 90), color="blue").save(tall_path)

        harness.scanner.listing_items = [
            {
                "id": "recipe-wide",
                "file_path": str(wide_path),
                "title": "Wide",
                "loras": [],
            },
            {"id": "recipe-none", "title": "No Preview", "loras": []},
            {
                "id": "recipe-tall",
                "file_path": str(tall_path),
                "title": "Tall",
                "loras": [],
            },
            {"id": "recipe-none-2", "title": "No Preview 2", "loras": []},
        ]
        harness.scanner.cached_raw = list(harness.scanner.listing_items)

        response = await harness.client.get("/api/lm/recipes")
        payload = await response.json()

        assert response.status == 200
        items = payload["items"]

        # Items with a file_path carry integer dims read from their own file;
        # the two images differ in both dimensions so a shifted pair would
        # fail these assertions.
        assert items[0]["width"] == 120
        assert items[0]["height"] == 40
        assert isinstance(items[0]["width"], int)
        assert isinstance(items[0]["height"], int)
        assert items[2]["width"] == 30
        assert items[2]["height"] == 90

        # Items without a file_path get the no-preview fallback and omit dims.
        for item in (items[1], items[3]):
            assert "width" not in item
            assert "height" not in item
            assert item["file_url"] == "/loras_static/images/no-preview.png"


async def test_list_recipes_passes_checkpoint_hash_filter(
    monkeypatch, tmp_path: Path
) -> None:
    async with recipe_harness(monkeypatch, tmp_path) as harness:
        response = await harness.client.get("/api/lm/recipes?checkpoint_hash=ckpt123")
        payload = await response.json()

        assert response.status == 200
        assert payload["items"] == []
        assert harness.scanner.last_paginated_params is not None
        assert harness.scanner.last_paginated_params["checkpoint_hash"] == "ckpt123"


async def test_get_recipes_for_checkpoint(monkeypatch, tmp_path: Path) -> None:
    async with recipe_harness(monkeypatch, tmp_path) as harness:
        harness.scanner.checkpoint_lookup["abc123"] = [
            {"id": "recipe-1", "title": "Linked recipe"}
        ]

        response = await harness.client.get(
            "/api/lm/recipes/for-checkpoint?hash=ABC123"
        )
        payload = await response.json()

        assert response.status == 200
        assert payload == {
            "success": True,
            "recipes": [{"id": "recipe-1", "title": "Linked recipe"}],
        }


async def test_get_recipes_for_checkpoint_requires_hash(
    monkeypatch, tmp_path: Path
) -> None:
    async with recipe_harness(monkeypatch, tmp_path) as harness:
        response = await harness.client.get("/api/lm/recipes/for-checkpoint")
        payload = await response.json()

        assert response.status == 400
        assert payload["success"] is False


async def test_save_and_delete_recipe_round_trip(monkeypatch, tmp_path: Path) -> None:
    async with recipe_harness(monkeypatch, tmp_path) as harness:
        form = FormData()
        form.add_field(
            "image", b"stub", filename="sample.png", content_type="image/png"
        )
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

        harness.persistence.delete_result = SimpleNamespace(
            payload={"success": True}, status=200
        )

        delete_response = await harness.client.delete("/api/lm/recipe/saved-id")
        delete_payload = await delete_response.json()

        assert delete_response.status == 200
        assert delete_payload["success"] is True
        assert harness.persistence.delete_calls == ["saved-id"]


async def test_move_recipe_invokes_persistence(monkeypatch, tmp_path: Path) -> None:
    async with recipe_harness(monkeypatch, tmp_path) as harness:
        response = await harness.client.post(
            "/api/lm/recipe/move",
            json={
                "recipe_id": "move-me",
                "target_path": str(tmp_path / "recipes" / "subdir"),
            },
        )

        payload = await response.json()
        assert response.status == 200
        assert payload["recipe_id"] == "move-me"
        assert harness.persistence.move_calls == [
            {
                "recipe_id": "move-me",
                "target_path": str(tmp_path / "recipes" / "subdir"),
            }
        ]


async def test_import_remote_recipe(monkeypatch, tmp_path: Path) -> None:
    provider_calls: list[str | int] = []

    class Provider:
        async def get_model_version_info(self, model_version_id):
            provider_calls.append(model_version_id)
            return {
                "baseModel": "Flux Provider",
                "model": {"type": "Checkpoint", "name": "Flux"},
            }, None

    async def fake_get_default_metadata_provider():
        return Provider()

    monkeypatch.setattr(
        "py.recipes.enrichment.get_default_metadata_provider",
        fake_get_default_metadata_provider,
    )

    async with recipe_harness(monkeypatch, tmp_path) as harness:
        resources = [
            {
                "type": "checkpoint",
                "modelId": 10,
                "modelVersionId": 33,
                "modelName": "Flux",
                "modelVersionName": "Dev",
            },
            {
                "type": "lora",
                "modelId": 20,
                "modelVersionId": 44,
                "modelName": "Painterly",
                "modelVersionName": "v2",
                "weight": 0.25,
            },
        ]
        response = await harness.client.get(
            "/api/lm/recipes/import-remote",
            params={
                "image_url": "https://example.com/images/1",
                "name": "Remote Recipe",
                "resources": json.dumps(resources),
                "tags": "foo,bar",
                "base_model": "Flux",
                "source_path": "https://example.com/images/1",
                "gen_params": json.dumps({"prompt": "hello world", "cfg_scale": 7}),
            },
        )

        payload = await response.json()
        assert response.status == 200
        assert payload["success"] is True

        call = harness.persistence.save_calls[-1]
        assert call["name"] == "Remote Recipe"
        assert call["tags"] == ["foo", "bar"]
        metadata = call["metadata"]
        assert metadata["base_model"] == "Flux Provider"
        assert provider_calls == ["33"]
        assert metadata["checkpoint"]["modelVersionId"] == 33
        assert metadata["loras"][0]["weight"] == 0.25
        assert metadata["gen_params"]["prompt"] == "hello world"
        assert harness.downloader.urls == ["https://example.com/images/1"]


async def test_import_remote_recipe_falls_back_to_request_base_model(
    monkeypatch, tmp_path: Path
) -> None:
    provider_calls: list[str | int] = []

    class Provider:
        async def get_model_version_info(self, model_version_id):
            provider_calls.append(model_version_id)
            return {}, None

    async def fake_get_default_metadata_provider():
        return Provider()

    monkeypatch.setattr(
        "py.recipes.enrichment.get_default_metadata_provider",
        fake_get_default_metadata_provider,
    )

    async with recipe_harness(monkeypatch, tmp_path) as harness:
        resources = [
            {
                "type": "checkpoint",
                "modelId": 11,
                "modelVersionId": 77,
                "modelName": "Flux",
                "modelVersionName": "Dev",
            },
        ]
        response = await harness.client.get(
            "/api/lm/recipes/import-remote",
            params={
                "image_url": "https://example.com/images/1",
                "name": "Remote Recipe",
                "resources": json.dumps(resources),
                "tags": "foo,bar",
                "base_model": "Flux",
            },
        )

        payload = await response.json()
        assert response.status == 200
        assert payload["success"] is True

        metadata = harness.persistence.save_calls[-1]["metadata"]
        assert metadata["base_model"] == "Flux"
        assert provider_calls == ["77"]


async def test_update_recipe_accepts_gen_params(monkeypatch, tmp_path: Path) -> None:
    async with recipe_harness(monkeypatch, tmp_path) as harness:
        payload = {
            "gen_params": {
                "prompt": "updated prompt",
                "negative_prompt": "updated negative",
                "steps": 30,
            }
        }

        response = await harness.client.put(
            "/api/lm/recipe/recipe-42/update",
            json=payload,
        )
        data = await response.json()

        assert response.status == 200
        assert data["success"] is True
        assert harness.persistence.update_calls == [
            {
                "recipe_scanner": harness.scanner,
                "recipe_id": "recipe-42",
                "updates": payload,
            }
        ]


async def test_import_remote_video_recipe(monkeypatch, tmp_path: Path) -> None:
    async def fake_get_default_metadata_provider():
        return SimpleNamespace(get_model_version_info=lambda id: ({}, None))

    monkeypatch.setattr(
        "py.recipes.enrichment.get_default_metadata_provider",
        fake_get_default_metadata_provider,
    )

    async with recipe_harness(monkeypatch, tmp_path) as harness:
        harness.civitai.image_info["12345"] = {
            "id": 12345,
            "url": "https://image.civitai.com/x/y/original=true/video.mp4",
            "type": "video",
        }

        response = await harness.client.get(
            "/api/lm/recipes/import-remote",
            params={
                "image_url": "https://civitai.com/images/12345",
                "name": "Video Recipe",
                "resources": json.dumps([]),
                "base_model": "Flux",
            },
        )

        payload = await response.json()
        assert response.status == 200
        assert payload["success"] is True

        # Verify downloader was called with rewritten URL
        assert "transcode=true" in harness.downloader.urls[0]

        # Verify persistence was called with correct extension
        call = harness.persistence.save_calls[-1]
        assert call["extension"] == ".mp4"


async def test_import_remote_recipe_supports_civitai_red(monkeypatch, tmp_path: Path) -> None:
    async def fake_get_default_metadata_provider():
        return SimpleNamespace(get_model_version_info=lambda id: ({}, None))

    monkeypatch.setattr(
        "py.recipes.enrichment.get_default_metadata_provider",
        fake_get_default_metadata_provider,
    )

    async with recipe_harness(monkeypatch, tmp_path) as harness:
        harness.civitai.image_info["126920345"] = {
            "id": 126920345,
            "url": "https://image.civitai.com/x/y/original=true/sample.jpeg",
            "type": "image",
        }

        response = await harness.client.get(
            "/api/lm/recipes/import-remote",
            params={
                "image_url": "https://civitai.red/images/126920345",
                "name": "Red Recipe",
                "resources": json.dumps([]),
                "base_model": "Flux",
            },
        )

        payload = await response.json()
        assert response.status == 200
        assert payload["success"] is True
        assert harness.downloader.urls
        assert "width=450,optimized=true" in harness.downloader.urls[0]


async def test_analyze_remote_image_supports_civitai_red(
    monkeypatch, tmp_path: Path
) -> None:
    async with recipe_harness(monkeypatch, tmp_path) as harness:
        harness.analysis.result = SimpleNamespace(payload={"loras": []}, status=200)

        response = await harness.client.post(
            "/api/lm/recipes/analyze-image",
            json={"url": "https://civitai.red/images/126920345"},
        )
        payload = await response.json()

        assert response.status == 200
        assert payload == {"loras": []}
        assert harness.analysis.remote_calls == [
            "https://civitai.red/images/126920345"
        ]


async def test_analyze_uploaded_image_error_path(monkeypatch, tmp_path: Path) -> None:
    async with recipe_harness(monkeypatch, tmp_path) as harness:
        harness.analysis.raise_for_uploaded = RecipeValidationError(
            "No image data provided"
        )

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
            payload={
                "success": True,
                "download_url": "/api/share",
                "filename": "share.png",
            },
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

        download_response = await harness.client.get(
            f"/api/lm/recipe/{recipe_id}/share/download"
        )
        body = await download_response.read()

        assert download_response.status == 200
        assert (
            download_response.headers["Content-Disposition"]
            == 'attachment; filename="share.png"'
        )
        assert body == b"stub"

        download_path.unlink(missing_ok=True)


async def test_import_remote_recipe_merges_metadata(
    monkeypatch, tmp_path: Path
) -> None:
    # 1. Mock Metadata Provider
    class Provider:
        async def get_model_version_info(self, model_version_id):
            return {"baseModel": "Flux Provider"}, None

    async def fake_get_default_metadata_provider():
        return Provider()

    monkeypatch.setattr(
        "py.recipes.enrichment.get_default_metadata_provider",
        fake_get_default_metadata_provider,
    )

    # 2. Mock ExifUtils to return some embedded metadata
    class MockExifUtils:
        @staticmethod
        def extract_image_metadata(path):
            return "Recipe metadata: " + json.dumps(
                {"gen_params": {"prompt": "from embedded", "seed": 123}}
            )

    monkeypatch.setattr(recipe_handlers, "ExifUtils", MockExifUtils)

    # 3. Mock Parser Factory for StubAnalysisService
    class MockParser:
        async def parse_metadata(self, raw, recipe_scanner=None):
            return json.loads(raw[len("Recipe metadata: ") :])

    class MockApiParser:
        async def parse_metadata(self, raw, recipe_scanner=None):
            return {"gen_params": raw, "loras": []}

    class MockFactory:
        def create_parser(self, raw):
            if isinstance(raw, str) and raw.startswith("Recipe metadata: "):
                return MockParser()
            if isinstance(raw, dict):
                return MockApiParser()
            return None

    # 4. Setup Harness and run test
    async with recipe_harness(monkeypatch, tmp_path) as harness:
        harness.analysis._recipe_parser_factory = MockFactory()

        # Civitai meta via image_info
        harness.civitai.image_info["1"] = {
            "id": 1,
            "url": "https://example.com/images/1.jpg",
            "meta": {"prompt": "from civitai", "cfg": 7.0},
        }

        resources = []
        response = await harness.client.get(
            "/api/lm/recipes/import-remote",
            params={
                "image_url": "https://civitai.com/images/1",
                "name": "Merged Recipe",
                "resources": json.dumps(resources),
                "gen_params": json.dumps({"prompt": "from request", "steps": 25}),
            },
        )

        payload = await response.json()
        assert response.status == 200

        call = harness.persistence.save_calls[-1]
        metadata = call["metadata"]
        gen_params = metadata["gen_params"]

        assert gen_params["seed"] == 123


async def test_get_recipe_syntax(monkeypatch, tmp_path: Path) -> None:
    async with recipe_harness(monkeypatch, tmp_path) as harness:
        recipe_id = "test-recipe-id"
        harness.scanner.recipes[recipe_id] = {
            "id": recipe_id,
            "title": "Syntax Test",
            "loras": [{"name": "lora1", "weight": 0.5}],
        }

        # Mock the method that handlers call
        async def fake_get_recipe_syntax_tokens(rid):
            if rid == recipe_id:
                return ["<lora:lora1:0.5>"]
            raise RecipeNotFoundError(f"Recipe {rid} not found")

        harness.scanner.get_recipe_syntax_tokens = (  # pyright: ignore[reportAttributeAccessIssue]
            fake_get_recipe_syntax_tokens
        )

        response = await harness.client.get(f"/api/lm/recipe/{recipe_id}/syntax")
        payload = await response.json()

        assert response.status == 200
        assert payload["success"] is True
        assert payload["syntax"] == "<lora:lora1:0.5>"

        # Test error path
        response_404 = await harness.client.get("/api/lm/recipe/non-existent/syntax")
        assert response_404.status == 404


async def test_batch_import_start_success(monkeypatch, tmp_path: Path) -> None:
    async with recipe_harness(monkeypatch, tmp_path) as harness:
        response = await harness.client.post(
            "/api/lm/recipes/batch-import/start",
            json={
                "items": [
                    {"source": "https://example.com/image1.png"},
                    {"source": "https://example.com/image2.png"},
                ],
                "tags": ["batch", "import"],
                "skip_no_metadata": True,
            },
        )
        payload = await response.json()
        assert response.status == 200
        assert payload["success"] is True
        assert "operation_id" in payload


async def test_batch_import_start_empty_items(monkeypatch, tmp_path: Path) -> None:
    async with recipe_harness(monkeypatch, tmp_path) as harness:
        response = await harness.client.post(
            "/api/lm/recipes/batch-import/start",
            json={"items": [], "tags": []},
        )
        payload = await response.json()
        assert response.status == 400
        assert payload["success"] is False
        assert "No items provided" in payload["error"]


async def test_batch_import_start_missing_source(monkeypatch, tmp_path: Path) -> None:
    async with recipe_harness(monkeypatch, tmp_path) as harness:
        response = await harness.client.post(
            "/api/lm/recipes/batch-import/start",
            json={"items": [{"source": ""}]},
        )
        payload = await response.json()
        assert response.status == 400
        assert payload["success"] is False
        assert "source" in payload["error"].lower()


async def test_batch_import_start_already_running(monkeypatch, tmp_path: Path) -> None:
    async with recipe_harness(monkeypatch, tmp_path) as harness:
        original_analyze = harness.analysis.analyze_remote_image

        async def slow_analyze(*, url, recipe_scanner, civitai_client):
            await asyncio.sleep(0.5)
            return await original_analyze(
                url=url, recipe_scanner=recipe_scanner, civitai_client=civitai_client
            )

        harness.analysis.analyze_remote_image = slow_analyze

        items = [{"source": f"https://example.com/image{i}.png"} for i in range(10)]

        response1 = await harness.client.post(
            "/api/lm/recipes/batch-import/start",
            json={"items": items},
        )
        assert response1.status == 200

        payload1 = await response1.json()
        assert payload1["success"] is True

        await asyncio.sleep(0.1)

        response2 = await harness.client.post(
            "/api/lm/recipes/batch-import/start",
            json={"items": [{"source": "https://example.com/other.png"}]},
        )
        payload2 = await response2.json()
        assert response2.status == 409
        assert "already in progress" in payload2["error"].lower()


async def test_batch_import_get_progress_not_found(monkeypatch, tmp_path: Path) -> None:
    async with recipe_harness(monkeypatch, tmp_path) as harness:
        response = await harness.client.get(
            "/api/lm/recipes/batch-import/progress",
            params={"operation_id": "nonexistent-id"},
        )
        payload = await response.json()
        assert response.status == 404
        assert payload["success"] is False


async def test_batch_import_get_progress_missing_id(
    monkeypatch, tmp_path: Path
) -> None:
    async with recipe_harness(monkeypatch, tmp_path) as harness:
        response = await harness.client.get("/api/lm/recipes/batch-import/progress")
        payload = await response.json()
        assert response.status == 400
        assert payload["success"] is False


async def test_batch_import_cancel_success(monkeypatch, tmp_path: Path) -> None:
    async with recipe_harness(monkeypatch, tmp_path) as harness:
        start_response = await harness.client.post(
            "/api/lm/recipes/batch-import/start",
            json={"items": [{"source": "https://example.com/image.png"}]},
        )
        start_payload = await start_response.json()
        operation_id = start_payload["operation_id"]

        cancel_response = await harness.client.post(
            "/api/lm/recipes/batch-import/cancel",
            json={"operation_id": operation_id},
        )
        cancel_payload = await cancel_response.json()
        assert cancel_response.status == 200
        assert cancel_payload["success"] is True


async def test_batch_import_cancel_not_found(monkeypatch, tmp_path: Path) -> None:
    async with recipe_harness(monkeypatch, tmp_path) as harness:
        response = await harness.client.post(
            "/api/lm/recipes/batch-import/cancel",
            json={"operation_id": "nonexistent-id"},
        )
        payload = await response.json()
        assert response.status == 404
        assert payload["success"] is False


async def test_batch_import_cancel_missing_id(monkeypatch, tmp_path: Path) -> None:
    async with recipe_harness(monkeypatch, tmp_path) as harness:
        response = await harness.client.post(
            "/api/lm/recipes/batch-import/cancel",
            json={},
        )
        payload = await response.json()
        assert response.status == 400
        assert payload["success"] is False


async def test_check_image_exists_uses_image_id_map(monkeypatch, tmp_path: Path) -> None:
    """check_image_exists must use precomputed image_id_map instead of scanning raw_data."""
    async with recipe_harness(monkeypatch, tmp_path) as harness:
        harness.scanner.image_id_map_override = {
            "123": "recipe-alpha",
            "789": "recipe-gamma",
        }

        response = await harness.client.get(
            "/api/lm/recipes/check-image-exists",
            params={"image_ids": "123,456,789"},
        )
        payload = await response.json()

        assert response.status == 200
        assert payload["success"] is True
        assert payload["results"]["123"] == {
            "in_library": True,
            "recipe_id": "recipe-alpha",
        }
        assert payload["results"]["456"] == {
            "in_library": False,
            "recipe_id": None,
        }
        assert payload["results"]["789"] == {
            "in_library": True,
            "recipe_id": "recipe-gamma",
        }


async def test_check_image_exists_handles_empty_input(monkeypatch, tmp_path: Path) -> None:
    """Empty or non-numeric image_ids must return an empty results dict."""
    async with recipe_harness(monkeypatch, tmp_path) as harness:
        response = await harness.client.get(
            "/api/lm/recipes/check-image-exists",
            params={"image_ids": ""},
        )
        payload = await response.json()
        assert response.status == 200
        assert payload["results"] == {}


async def test_import_from_url_detects_duplicate_via_image_id_map(
    monkeypatch, tmp_path: Path,
) -> None:
    """import_from_url must return already_exists when image_id is in image_id_map."""
    async with recipe_harness(monkeypatch, tmp_path) as harness:
        harness.scanner.cached_raw = [
            {"id": "existing-recipe", "title": "My Recipe"},
        ]
        harness.scanner.image_id_map_override = {
            "99999": "existing-recipe",
        }

        response = await harness.client.get(
            "/api/lm/recipes/import-from-url",
            params={"image_url": "https://civitai.com/images/99999"},
        )
        payload = await response.json()

        assert response.status == 200
        assert payload["already_exists"] is True
        assert payload["recipe_id"] == "existing-recipe"
        assert payload["name"] == "My Recipe"


async def test_import_from_url_proceeds_when_image_id_not_in_map(
    monkeypatch, tmp_path: Path,
) -> None:
    """When image_id is absent from image_id_map, import_from_url must proceed to import."""
    async with recipe_harness(monkeypatch, tmp_path) as harness:
        harness.scanner.image_id_map_override = {
            "111": "some-other-recipe",
        }
        harness.civitai.image_info["99999"] = {
            "id": 99999,
            "url": "https://image.civitai.com/x/y/original=true/sample.jpeg",
            "type": "image",
            "meta": {"prompt": "test"},
        }

        response = await harness.client.get(
            "/api/lm/recipes/import-from-url",
            params={"image_url": "https://civitai.com/images/99999"},
        )

        # The import may succeed or fail depending on downstream stubs,
        # but it must NOT return already_exists
        payload = await response.json()
        assert payload.get("already_exists") is not True


async def test_import_remote_recipe_passes_local_cache_to_civitai_parser(
    monkeypatch, tmp_path: Path
) -> None:
    """import_remote must hand the same local hash cache to both Civitai parse passes."""
    parse_calls: list[Dict[str, Any]] = []

    class SpyCivitaiParser(CivitaiApiMetadataParser):
        async def parse_metadata(
            self, user_comment, recipe_scanner=None, civitai_client=None,
            local_cache=None,
        ) -> Dict[str, Any]:
            parse_calls.append({"local_cache": local_cache})
            return {"gen_params": {"prompt": "spy"}}

    class SpyFactory:
        def create_parser(self, raw):
            return SpyCivitaiParser()

    class MockExifUtils:
        @staticmethod
        def extract_image_metadata(path):
            return "Recipe metadata: " + json.dumps({"gen_params": {"seed": 7}})

    async def fake_get_default_metadata_provider():
        return SimpleNamespace(get_model_version_info=lambda _id: ({}, None))

    monkeypatch.setattr(recipe_handlers, "ExifUtils", MockExifUtils)
    monkeypatch.setattr(
        "py.recipes.enrichment.get_default_metadata_provider",
        fake_get_default_metadata_provider,
    )

    async with recipe_harness(monkeypatch, tmp_path) as harness:
        harness.analysis._recipe_parser_factory = SpyFactory()
        cache_marker = {"abcdef123456": {"model_name": "local-lora"}}
        harness.scanner.local_hash_cache = cache_marker
        harness.civitai.image_info["1"] = {
            "id": 1,
            "url": "https://example.com/images/1.jpg",
            "meta": {"prompt": "from civitai", "seed": 99},
        }

        response = await harness.client.get(
            "/api/lm/recipes/import-remote",
            params={
                "image_url": "https://civitai.com/images/1",
                "name": "Civitai Cache",
                "resources": json.dumps([]),
                "gen_params": json.dumps({"prompt": "from request", "steps": 25}),
            },
        )
        payload = await response.json()

        assert response.status == 200
        assert payload["success"] is True
        # Both parse passes (EXIF + CivitAI API) ran and received the SAME
        # local_cache object, built once at handler level.
        assert len(parse_calls) == 2
        assert all(call["local_cache"] is cache_marker for call in parse_calls)
        assert parse_calls[0]["local_cache"] is parse_calls[1]["local_cache"]


async def test_import_remote_recipe_does_not_pass_local_cache_to_other_parsers(
    monkeypatch, tmp_path: Path
) -> None:
    """Non-Civitai parsers must never receive local_cache (their signature lacks it)."""
    parse_calls: list[Dict[str, Any]] = []

    class PlainParser:
        async def parse_metadata(self, raw, recipe_scanner=None, **kwargs):
            assert "local_cache" not in kwargs, (
                "local_cache leaked to a non-Civitai parser"
            )
            parse_calls.append({"raw": raw})
            return {"gen_params": {"prompt": "plain"}}

    class PlainFactory:
        def create_parser(self, raw):
            return PlainParser()

    class MockExifUtils:
        @staticmethod
        def extract_image_metadata(path):
            return "Recipe metadata: " + json.dumps({"gen_params": {"seed": 7}})

    async def fake_get_default_metadata_provider():
        return SimpleNamespace(get_model_version_info=lambda _id: ({}, None))

    monkeypatch.setattr(recipe_handlers, "ExifUtils", MockExifUtils)
    monkeypatch.setattr(
        "py.recipes.enrichment.get_default_metadata_provider",
        fake_get_default_metadata_provider,
    )

    async with recipe_harness(monkeypatch, tmp_path) as harness:
        harness.analysis._recipe_parser_factory = PlainFactory()
        harness.scanner.local_hash_cache = {"deadbeef": {"model_name": "local"}}
        harness.civitai.image_info["1"] = {
            "id": 1,
            "url": "https://example.com/images/1.jpg",
            "meta": {"prompt": "from civitai", "seed": 99},
        }

        response = await harness.client.get(
            "/api/lm/recipes/import-remote",
            params={
                "image_url": "https://civitai.com/images/1",
                "name": "Plain Cache",
                "resources": json.dumps([]),
                "gen_params": json.dumps({"prompt": "from request", "steps": 25}),
            },
        )
        payload = await response.json()

        assert response.status == 200
        assert payload["success"] is True
        assert len(parse_calls) == 2


async def test_import_from_url_passes_local_cache_on_all_three_parse_calls(
    monkeypatch, tmp_path: Path
) -> None:
    """import_from_url must pass local_cache to all three Civitai parse passes."""
    parse_calls: list[Dict[str, Any]] = []
    str_call_count = 0

    class SpyCivitaiParser(CivitaiApiMetadataParser):
        async def parse_metadata(
            self, user_comment, recipe_scanner=None, civitai_client=None,
            local_cache=None,
        ) -> Dict[str, Any]:
            nonlocal str_call_count
            parse_calls.append({"local_cache": local_cache})
            if isinstance(user_comment, str):
                str_call_count += 1
                if str_call_count == 1:
                    # First (optimized EXIF) pass yields an empty dict so the
                    # handler falls back to the original image, exercising
                    # pass #2 (an empty dict is falsy for `not parsed_embedded`).
                    return {}
                return {"gen_params": {"prompt": "fallback"}}
            return {"gen_params": {"prompt": "civitai"}}

    class SpyFactory:
        def create_parser(self, raw):
            return SpyCivitaiParser()

    class MockExifUtils:
        @staticmethod
        def extract_image_metadata(path):
            if path.endswith(".png"):
                return "original metadata: " + json.dumps({"gen_params": {"seed": 2}})
            return "optimized metadata: " + json.dumps({"gen_params": {"seed": 1}})

    async def fake_get_default_metadata_provider():
        return SimpleNamespace(get_model_version_info=lambda _id: ({}, None))

    monkeypatch.setattr(recipe_handlers, "ExifUtils", MockExifUtils)
    monkeypatch.setattr(
        "py.recipes.enrichment.get_default_metadata_provider",
        fake_get_default_metadata_provider,
    )

    async with recipe_harness(monkeypatch, tmp_path) as harness:
        harness.analysis._recipe_parser_factory = SpyFactory()
        cache_marker = {"deadbeef": {"model_name": "local-lora"}}
        harness.scanner.local_hash_cache = cache_marker
        harness.civitai.image_info["42"] = {
            "id": 42,
            "url": "https://image.civitai.com/x/y/original=true/sample.jpeg",
            "type": "image",
            "meta": {"prompt": "test", "seed": 3},
        }

        response = await harness.client.get(
            "/api/lm/recipes/import-from-url",
            params={"image_url": "https://civitai.com/images/42"},
        )
        payload = await response.json()

        assert response.status == 200
        assert payload["success"] is True
        assert len(parse_calls) == 3
        assert all(call["local_cache"] is cache_marker for call in parse_calls)
        assert parse_calls[0]["local_cache"] is parse_calls[2]["local_cache"]


class _RawDataLoraScanner:
    """Lora-scanner double whose get_cached_data returns a fixed raw_data list."""

    def __init__(self, raw_data: List[Dict[str, Any]]) -> None:
        self._raw_data = raw_data

    async def get_cached_data(self) -> SimpleNamespace:
        return SimpleNamespace(raw_data=self._raw_data)


class _SpyCivitaiParser(CivitaiApiMetadataParser):
    """Records the local_cache passed to parse_metadata and returns a canned result."""

    def __init__(self, parse_result: Dict[str, Any]) -> None:
        self.received_cache: Optional[Dict[str, Dict[str, Any]]] = None
        self._parse_result = parse_result

    async def parse_metadata(
        self, user_comment, recipe_scanner=None, civitai_client=None, local_cache=None,
    ) -> Dict[str, Any]:
        self.received_cache = local_cache
        return self._parse_result


class _SpyFactory:
    def __init__(self, parser: _SpyCivitaiParser) -> None:
        self._parser = parser

    def create_parser(self, raw):  # noqa: ARG001 - mirrors real factory signature
        return self._parser


async def _post_create_from_example(
    harness: RecipeRouteHarness, model_hash: str, *, model_name: str = "parent.safetensors"
) -> Any:
    return await harness.client.post(
        "/api/lm/recipes/create-from-example",
        json={
            "image_data": {
                "url": "https://image.civitai.com/x/y/original=true/sample.jpeg",
                "meta": {"prompt": "sample prompt"},
            },
            "model_hash": model_hash,
            "model_name": model_name,
            "model_type": "loras",
        },
    )


async def test_create_from_example_resolves_parent_item_by_sha256_key(
    monkeypatch, tmp_path: Path
) -> None:
    """A parent present in the shared cache under its sha256 key drives isDeleted reconciliation."""
    model_hash = "a1b2c3d4e5f60718293a4b5c6d7e8f90123456789abcdef0123456789abcdef"
    model_name = "parent.safetensors"
    parent_item: Dict[str, Any] = {
        "civitai": {"id": 77, "modelId": 88, "name": "v1.0"},
        "model_name": "Parent Model",
    }
    parser = _SpyCivitaiParser(
        {
            "loras": [{"isDeleted": True, "file_name": model_name, "name": "Stale"}],
            "gen_params": {"prompt": "test prompt"},
        }
    )

    async with recipe_harness(monkeypatch, tmp_path) as harness:
        harness.analysis._recipe_parser_factory = _SpyFactory(parser)
        harness.scanner.local_hash_cache = {model_hash.lower(): parent_item}

        response = await _post_create_from_example(harness, model_hash, model_name=model_name)
        payload = await response.json()

        assert response.status == 200, payload
        # The shared builder result is the exact object handed to the parser.
        assert parser.received_cache is harness.scanner.local_hash_cache
        lora = harness.persistence.save_calls[0]["metadata"]["loras"][0]
        assert lora["isDeleted"] is False
        assert lora["existsLocally"] is True
        assert lora["hash"] == model_hash
        assert lora["id"] == 77
        assert lora["modelId"] == 88
        assert lora["version"] == "v1.0"
        assert lora["name"] == "Parent Model"


async def test_create_from_example_computes_autov3_for_unbackfilled_parent(
    monkeypatch, tmp_path: Path
) -> None:
    """A parent with no stored autov3 gets a single-file compute registered in the cache."""
    model_hash = "b2c3d4e5f60718293a4b5c6d7e8f90123456789abcdef0123456789abcdef0"
    model_file = tmp_path / "parent.safetensors"
    model_file.write_bytes(b"\x00" * 16)
    parent_item: Dict[str, Any] = {
        "sha256": model_hash,
        "autov3": "",
        "file_path": str(model_file),
        "model_name": "Parent Model",
    }
    autov3_calls: list[str] = []

    def fake_calculate_autov3(file_path: str) -> str | None:
        autov3_calls.append(file_path)
        return "abc123def456"

    monkeypatch.setattr("py.utils.file_utils.calculate_autov3", fake_calculate_autov3)
    parser = _SpyCivitaiParser({"loras": [], "gen_params": {"prompt": "test prompt"}})

    async with recipe_harness(monkeypatch, tmp_path) as harness:
        harness.analysis._recipe_parser_factory = _SpyFactory(parser)
        # The sha256 key is already present (as the real builder registers it);
        # the supplement must still run because the stored autov3 is empty.
        harness.scanner.local_hash_cache = {model_hash.lower(): parent_item}
        harness.scanner._lora_scanner = _RawDataLoraScanner([parent_item])

        response = await _post_create_from_example(harness, model_hash)
        payload = await response.json()

        assert response.status == 200, payload
        # Bounded: exactly one header read for the single parent file.
        assert autov3_calls == [str(model_file)]
        assert parser.received_cache is harness.scanner.local_hash_cache
        assert parser.received_cache is not None
        # The computed autov3 key was registered, pointing at the parent item.
        assert parser.received_cache["abc123def456"] is parent_item


async def test_create_from_example_parent_not_in_library_has_no_arbitrary_item(
    monkeypatch, tmp_path: Path
) -> None:
    """A missing parent must NOT fall back to an arbitrary cache entry during auto-populate."""
    model_hash = "c3d4e5f60718293a4b5c6d7e8f90123456789abcdef0123456789abcdef01"
    model_name = "parent.safetensors"
    decoy: Dict[str, Any] = {
        "civitai": {"id": 999, "modelId": 998, "name": "v9"},
        "model_name": "Wrong Model",
    }
    parser = _SpyCivitaiParser({"loras": [], "gen_params": {"prompt": "test prompt"}})

    async with recipe_harness(monkeypatch, tmp_path) as harness:
        harness.analysis._recipe_parser_factory = _SpyFactory(parser)
        harness.scanner.local_hash_cache = {"someotherhash": decoy}

        response = await _post_create_from_example(harness, model_hash, model_name=model_name)
        payload = await response.json()

        assert response.status == 200, payload
        lora = harness.persistence.save_calls[0]["metadata"]["loras"][0]
        assert lora["hash"] == model_hash
        assert lora["file_name"] == model_name
        assert lora["existsLocally"] is True
        # parent_item is None: the entry keeps its default name, and no
        # enrichment fields may come from any cache entry.
        assert lora["name"] == model_name
        assert "id" not in lora
        assert "modelId" not in lora
        assert "version" not in lora


async def test_create_from_example_parent_not_in_library_isDeleted_reconciliation_has_no_arbitrary_item(
    monkeypatch, tmp_path: Path
) -> None:
    """isDeleted reconciliation must not enrich from an arbitrary entry when the parent is missing."""
    model_hash = "d4e5f60718293a4b5c6d7e8f90123456789abcdef0123456789abcdef012"
    model_name = "parent.safetensors"
    decoy: Dict[str, Any] = {
        "civitai": {"id": 777, "modelId": 776, "name": "v7"},
        "model_name": "Decoy Model",
    }
    parser = _SpyCivitaiParser(
        {
            "loras": [{"isDeleted": True, "file_name": model_name}],
            "gen_params": {"prompt": "test prompt"},
        }
    )

    async with recipe_harness(monkeypatch, tmp_path) as harness:
        harness.analysis._recipe_parser_factory = _SpyFactory(parser)
        harness.scanner.local_hash_cache = {"someotherhash": decoy}

        response = await _post_create_from_example(harness, model_hash, model_name=model_name)
        payload = await response.json()

        assert response.status == 200, payload
        lora = harness.persistence.save_calls[0]["metadata"]["loras"][0]
        # Reconciliation still runs (parent matched by file_name), but enriches
        # nothing because parent_item is None.
        assert lora["isDeleted"] is False
        assert lora["existsLocally"] is True
        assert lora["hash"] == model_hash
        assert "id" not in lora
        assert "name" not in lora


async def test_create_from_example_does_not_pass_local_cache_to_other_parsers(
    monkeypatch, tmp_path: Path
) -> None:
    """Non-Civitai parsers must never receive local_cache (their signature lacks it)."""
    parse_calls: list[Dict[str, Any]] = []

    class PlainParser:
        async def parse_metadata(self, raw, recipe_scanner=None, **kwargs):
            assert "local_cache" not in kwargs, (
                "local_cache leaked to a non-Civitai parser"
            )
            parse_calls.append({"raw": raw})
            return {"loras": [], "gen_params": {"prompt": "plain"}}

    class PlainFactory:
        def create_parser(self, raw):  # noqa: ARG001 - mirrors real factory signature
            return PlainParser()

    async with recipe_harness(monkeypatch, tmp_path) as harness:
        harness.analysis._recipe_parser_factory = PlainFactory()
        harness.scanner.local_hash_cache = {"deadbeef": {"model_name": "local"}}

        response = await _post_create_from_example(harness, "f1234", model_name="plain.safetensors")
        payload = await response.json()

        assert response.status == 200, payload
        assert len(parse_calls) == 1


async def test_create_from_example_does_not_recompute_stored_autov3(
    monkeypatch, tmp_path: Path
) -> None:
    """A parent whose autov3 is already stored must not trigger the supplement."""
    model_hash = "e5f60718293a4b5c6d7e8f90123456789abcdef0123456789abcdef0123"
    model_file = tmp_path / "parent.safetensors"
    model_file.write_bytes(b"\x00" * 16)
    parent_item: Dict[str, Any] = {
        "sha256": model_hash,
        "autov3": "existing123456",
        "file_path": str(model_file),
        "model_name": "Parent Model",
    }
    autov3_calls: list[str] = []

    def fake_calculate_autov3(file_path: str) -> str | None:  # noqa: ARG001 - must not run
        autov3_calls.append(file_path)
        return "should-not-run"

    monkeypatch.setattr("py.utils.file_utils.calculate_autov3", fake_calculate_autov3)
    parser = _SpyCivitaiParser({"loras": [], "gen_params": {"prompt": "test prompt"}})

    async with recipe_harness(monkeypatch, tmp_path) as harness:
        harness.analysis._recipe_parser_factory = _SpyFactory(parser)
        # The shared builder registers both the sha256 and the stored autov3 keys.
        harness.scanner.local_hash_cache = {
            model_hash.lower(): parent_item,
            "existing123456": parent_item,
        }
        harness.scanner._lora_scanner = _RawDataLoraScanner([parent_item])

        response = await _post_create_from_example(harness, model_hash)
        payload = await response.json()

        assert response.status == 200, payload
        # Stale-state guard: no recompute when autov3 is already stored.
        assert autov3_calls == []
        assert parser.received_cache is harness.scanner.local_hash_cache
        assert parser.received_cache is not None
        assert parser.received_cache["existing123456"] is parent_item

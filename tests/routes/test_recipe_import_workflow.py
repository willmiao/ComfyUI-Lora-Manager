"""Workflow preservation for remote recipe imports.

CivitAI serves a re-encoded, metadata-free ``optimized`` rendition as the
recipe preview, so an embedded ComfyUI workflow only exists in the
``original=true`` image. These tests pin the recovery and transport of that
workflow through the remote import paths.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from PIL import Image, PngImagePlugin

from py.routes.handlers.recipe_handlers import RecipeManagementHandler
from py.services.recipes.persistence_service import PersistenceResult
from py.utils.exif_utils import ExifUtils


async def _noop_ensure() -> None:
    return None


class CapturingPersistence:
    """Persistence service double recording the save payload."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def save_recipe(self, **kwargs: Any) -> PersistenceResult:
        self.calls.append(kwargs)
        return PersistenceResult({"success": True, "recipe_id": "recipe-1"})


class StubScanner:
    """Scanner double exposing only what the remote import paths touch."""

    def __init__(self) -> None:
        self.recipes_dir = "/tmp/recipes"

    async def build_local_hash_cache(self) -> dict[str, Any]:
        return {}

    async def get_local_lora(self, name, base_model=None):
        return None


def _make_handler(
    persistence: CapturingPersistence,
    *,
    downloader_factory=None,
) -> RecipeManagementHandler:
    async def default_downloader_factory():
        class Downloader:
            async def download_file(self, url, path, use_auth=False):
                Path(path).write_bytes(b"downloaded")
                return True, "ok"

        return Downloader()

    analysis_service = SimpleNamespace(
        _recipe_parser_factory=SimpleNamespace(create_parser=lambda metadata: None)
    )

    return RecipeManagementHandler(
        ensure_dependencies_ready=_noop_ensure,
        recipe_scanner_getter=lambda: StubScanner(),
        logger=logging.getLogger(__name__),
        persistence_service=persistence,  # pyright: ignore[reportArgumentType]
        analysis_service=analysis_service,  # pyright: ignore[reportArgumentType]
        downloader_factory=downloader_factory or default_downloader_factory,
        civitai_client_getter=lambda: None,
    )


def _meta_with_comfy() -> dict[str, Any]:
    return {
        "id": 143518055,
        "meta": {"prompt": "p", "comfy": '{"prompt": {"1": {"class_type": "KSampler"}}}'},
    }


def test_meta_indicates_comfy_workflow() -> None:
    assert RecipeManagementHandler._meta_indicates_comfy_workflow(
        {"meta": {"comfy": "{}"}}
    )
    assert RecipeManagementHandler._meta_indicates_comfy_workflow({"comfy": "{}"})
    assert not RecipeManagementHandler._meta_indicates_comfy_workflow({"meta": {}})
    assert not RecipeManagementHandler._meta_indicates_comfy_workflow(
        {"meta": {"comfy": None}}
    )
    assert not RecipeManagementHandler._meta_indicates_comfy_workflow(None)
    assert not RecipeManagementHandler._meta_indicates_comfy_workflow("comfy")


@pytest.mark.asyncio
async def test_fetch_original_media_reads_workflow_and_cleans_up(tmp_path, monkeypatch):
    workflow = json.dumps({"nodes": [{"id": 1}], "last_node_id": 1})
    source = tmp_path / "original.png"
    png_info = PngImagePlugin.PngInfo()
    png_info.add_text("workflow", workflow)
    png_info.add_text("prompt", '{"1": {"class_type": "KSampler"}}')
    Image.new("RGB", (32, 32), color="red").save(source, pnginfo=png_info)

    written: list[str] = []

    async def downloader_factory():
        class Downloader:
            async def download_file(self, url, path, use_auth=False):
                written.append(str(path))
                Path(path).write_bytes(source.read_bytes())
                return True, "ok"

        return Downloader()

    handler = _make_handler(CapturingPersistence(), downloader_factory=downloader_factory)

    raw_metadata, recovered = await handler._fetch_original_media(
        "https://image.civitai.com/x/original=true/x.png"
    )

    assert recovered == workflow
    # extract_image_metadata prefers the prompt chunk over the workflow.
    assert raw_metadata is not None and "class_type" in raw_metadata
    assert written and not os.path.exists(written[0])


@pytest.mark.asyncio
async def test_fetch_original_media_degrades_on_download_failure():
    async def downloader_factory():
        class Downloader:
            async def download_file(self, url, path, use_auth=False):
                return False, "boom"

        return Downloader()

    handler = _make_handler(CapturingPersistence(), downloader_factory=downloader_factory)

    assert await handler._fetch_original_media("https://image.civitai.com/x.png") == (
        None,
        None,
    )
    assert await handler._fetch_original_media(None) == (None, None)


@pytest.mark.asyncio
async def test_remote_import_transports_workflow_to_save(monkeypatch):
    workflow = json.dumps({"nodes": [{"id": 4}]})
    persistence = CapturingPersistence()
    handler = _make_handler(persistence)

    async def fake_download_remote_media(image_url):
        return (
            b"optimized-preview",
            ".jpg",
            _meta_with_comfy(),
            12345,
            "https://image.civitai.com/x/original=true/x.png",
        )

    fetched: list[str] = []

    async def fake_fetch_original_media(original_url):
        fetched.append(original_url)
        return None, workflow

    handler._download_remote_media = fake_download_remote_media  # type: ignore[method-assign]
    handler._fetch_original_media = fake_fetch_original_media  # type: ignore[method-assign]
    monkeypatch.setattr(
        ExifUtils, "extract_image_metadata", staticmethod(lambda path: None)
    )

    response = await handler._do_import_remote_recipe(
        image_url="https://civitai.red/images/143518055",
        name="Recipe",
        lora_entries=[],
        checkpoint_entry=None,
        gen_params_request={},
        tags=[],
        base_model="Krea 2",
        source_path="https://civitai.red/images/143518055",
    )

    assert response.status == 200
    assert fetched == ["https://image.civitai.com/x/original=true/x.png"]
    assert persistence.calls[0]["metadata"]["workflow"] == workflow


@pytest.mark.asyncio
async def test_remote_import_skips_original_without_comfy_meta(monkeypatch):
    persistence = CapturingPersistence()
    handler = _make_handler(persistence)

    async def fake_download_remote_media(image_url):
        return (
            b"optimized-preview",
            ".jpg",
            {"id": 1, "meta": {"prompt": "p"}},
            None,
            "https://image.civitai.com/x/original=true/x.png",
        )

    async def fail_fetch(original_url):  # pragma: no cover - must not be called
        raise AssertionError("original rendition should not be fetched")

    handler._download_remote_media = fake_download_remote_media  # type: ignore[method-assign]
    handler._fetch_original_media = fail_fetch  # type: ignore[method-assign]
    monkeypatch.setattr(
        ExifUtils, "extract_image_metadata", staticmethod(lambda path: None)
    )

    response = await handler._do_import_remote_recipe(
        image_url="https://civitai.red/images/1",
        name="Recipe",
        lora_entries=[],
        checkpoint_entry=None,
        gen_params_request={},
        tags=[],
        base_model="SDXL 1.0",
        source_path="https://civitai.red/images/1",
    )

    assert response.status == 200
    assert "workflow" not in persistence.calls[0]["metadata"]


@pytest.mark.asyncio
async def test_url_import_transports_workflow_to_save(monkeypatch):
    workflow = json.dumps({"nodes": [{"id": 5}]})
    persistence = CapturingPersistence()
    handler = _make_handler(persistence)

    async def fake_download_remote_media(image_url):
        return (
            b"optimized-preview",
            ".jpg",
            {"id": 9, "meta": {"prompt": "p"}},
            None,
            "https://image.civitai.com/x/original=true/x.png",
        )

    async def fake_fetch_original_media(original_url):
        return None, workflow

    handler._download_remote_media = fake_download_remote_media  # type: ignore[method-assign]
    handler._fetch_original_media = fake_fetch_original_media  # type: ignore[method-assign]
    monkeypatch.setattr(
        ExifUtils, "extract_image_metadata", staticmethod(lambda path: None)
    )

    response = await handler._do_import_from_url(
        "https://civitai.red/images/143518055", StubScanner()
    )

    assert response.status == 200
    assert persistence.calls[0]["metadata"]["workflow"] == workflow

from __future__ import annotations

import asyncio
import json
import os
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, Generator, Tuple

import pytest

from py.services.settings_manager import get_settings_manager
from py.utils import example_images_metadata as metadata_module
from py.utils import example_images_processor as processor_module
from py.utils.example_images_paths import get_model_folder


@pytest.fixture(autouse=True)
def restore_settings() -> Generator[None, None, None]:
    manager = get_settings_manager()
    original = manager.settings.copy()
    try:
        yield
    finally:
        manager.settings.clear()
        manager.settings.update(original)


@pytest.fixture(autouse=True)
def patch_metadata_loader(monkeypatch: pytest.MonkeyPatch) -> None:
    class SimpleMetadata:
        def __init__(self, payload: Dict[str, Any]) -> None:
            self._payload = payload
            self._unknown_fields: Dict[str, Any] = {}

        def to_dict(self) -> Dict[str, Any]:
            return self._payload.copy()

    async def fake_load(path: str, *_args: Any, **_kwargs: Any):
        metadata_path = path if path.endswith(".metadata.json") else f"{os.path.splitext(path)[0]}.metadata.json"
        if os.path.exists(metadata_path):
            data = json.loads(Path(metadata_path).read_text(encoding="utf-8"))
            return SimpleMetadata(data), False
        return None, False

    monkeypatch.setattr(processor_module.MetadataManager, "load_metadata", staticmethod(fake_load))
    monkeypatch.setattr(metadata_module.MetadataManager, "load_metadata", staticmethod(fake_load))


def test_get_file_extension_from_magic_bytes() -> None:
    jpg_bytes = b"\xff\xd8\xff" + b"rest"
    ext = processor_module.ExampleImagesProcessor._get_file_extension_from_content_or_headers(
        jpg_bytes, {}, None
    )
    assert ext == ".jpg"


def test_get_file_extension_from_headers() -> None:
    ext = processor_module.ExampleImagesProcessor._get_file_extension_from_content_or_headers(
        b"", {"content-type": "image/png"}, None
    )
    assert ext == ".png"


def test_get_file_extension_from_url_fallback() -> None:
    ext = processor_module.ExampleImagesProcessor._get_file_extension_from_content_or_headers(
        b"", {}, "https://example.com/file.webm?query=1"
    )
    assert ext == ".webm"


def test_get_file_extension_defaults_to_jpg() -> None:
    ext = processor_module.ExampleImagesProcessor._get_file_extension_from_content_or_headers(
        b"", {}, None
    )
    assert ext == ".jpg"


def test_get_file_extension_from_media_type_hint_video() -> None:
    """Test that media_type_hint='video' returns .mp4 when other methods fail"""
    ext = processor_module.ExampleImagesProcessor._get_file_extension_from_content_or_headers(
        b"", {}, "https://c.genur.art/536be3c9-e506-4365-b078-bfbc5df9ceec", "video"
    )
    assert ext == ".mp4"


def test_get_file_extension_from_media_type_hint_image() -> None:
    """Test that media_type_hint='image' falls back to .jpg"""
    ext = processor_module.ExampleImagesProcessor._get_file_extension_from_content_or_headers(
        b"", {}, "https://example.com/no-extension", "image"
    )
    assert ext == ".jpg"


def test_get_file_extension_media_type_hint_low_priority() -> None:
    """Test that media_type_hint is only used as last resort (after URL extension)"""
    # URL has extension, should use that instead of media_type_hint
    ext = processor_module.ExampleImagesProcessor._get_file_extension_from_content_or_headers(
        b"", {}, "https://example.com/video.mp4", "image"
    )
    assert ext == ".mp4"


def test_example_image_file_exists_checks_plausible_extensions(tmp_path) -> None:
    proc = processor_module.ExampleImagesProcessor
    assert proc._example_image_file_exists(str(tmp_path), 0) is False
    Path(tmp_path, "image_0.webp").write_bytes(b"x")
    assert proc._example_image_file_exists(str(tmp_path), 0) is True
    assert proc._example_image_file_exists(str(tmp_path), 1) is False


def test_example_image_file_exists_video_hint_only_checks_video_extensions(tmp_path) -> None:
    proc = processor_module.ExampleImagesProcessor
    Path(tmp_path, "image_2.jpg").write_bytes(b"x")
    # An existing image file must not satisfy a video-hinted lookup
    assert proc._example_image_file_exists(str(tmp_path), 2, "video") is False
    Path(tmp_path, "image_2.mp4").write_bytes(b"x")
    assert proc._example_image_file_exists(str(tmp_path), 2, "video") is True


async def test_download_model_images_with_tracking_skips_existing_files(tmp_path) -> None:
    proc = processor_module.ExampleImagesProcessor
    images = [
        {"url": "https://image.civitai.com/a/b", "type": "image"},
        {"url": "https://image.civitai.com/c/d", "type": "image"},
    ]
    Path(tmp_path, "image_0.jpg").write_bytes(b"existing")

    class RecordingDownloader:
        def __init__(self) -> None:
            self.calls: list[str] = []

        async def download_to_memory(self, url, use_auth=False, return_headers=False):
            self.calls.append(url)
            return True, b"\xff\xd8\xff" + b"data", {}

    downloader = RecordingDownloader()
    outcome = await proc.download_model_images_with_tracking(
        "hash", "model", images, str(tmp_path), False, downloader
    )

    assert outcome.success is True
    assert outcome.is_stale is False
    assert outcome.failed == []
    assert outcome.rate_limited == []
    # Only the missing image is requested; the existing one is skipped without a network call
    assert len(downloader.calls) == 1
    assert "c/d" in downloader.calls[0]
    assert Path(tmp_path, "image_1.jpg").exists()


class StubScanner:
    def __init__(self, models: list[Dict[str, Any]]) -> None:
        self._cache = SimpleNamespace(raw_data=models)
        self.updated: list[Tuple[str, str, Dict[str, Any]]] = []

    async def get_cached_data(self):
        return self._cache

    async def update_single_model_cache(self, old_path: str, new_path: str, metadata: Dict[str, Any]) -> bool:
        self.updated.append((old_path, new_path, metadata))
        return True

    def has_hash(self, _hash: str) -> bool:
        return True


@pytest.fixture
def stub_scanners(monkeypatch: pytest.MonkeyPatch, tmp_path) -> StubScanner:
    model_hash = "a" * 64
    model_path = tmp_path / "model.safetensors"
    model_path.write_text("content", encoding="utf-8")
    model_data = {
        "sha256": model_hash,
        "model_name": "Example",
        "file_path": str(model_path),
        "civitai": {},
    }
    scanner = StubScanner([model_data])

    async def _return_scanner(cls=None):
        return scanner

    monkeypatch.setattr(processor_module.ServiceRegistry, "get_lora_scanner", classmethod(_return_scanner))
    monkeypatch.setattr(processor_module.ServiceRegistry, "get_checkpoint_scanner", classmethod(_return_scanner))
    monkeypatch.setattr(processor_module.ServiceRegistry, "get_embedding_scanner", classmethod(_return_scanner))
    monkeypatch.setattr(processor_module.ServiceRegistry, "get_other_scanner", classmethod(_return_scanner))

    return scanner


async def test_import_images_creates_hash_directory(monkeypatch: pytest.MonkeyPatch, tmp_path, stub_scanners: StubScanner) -> None:
    settings_manager = get_settings_manager()
    settings_manager.settings["example_images_path"] = str(tmp_path / "examples")
    settings_manager.settings["libraries"] = {"default": {}}
    settings_manager.settings["active_library"] = "default"

    source_file = tmp_path / "upload.png"
    source_file.write_bytes(b"PNG data")

    monkeypatch.setattr(processor_module.ExampleImagesProcessor, "generate_short_id", staticmethod(lambda: "short"))

    recorded: Dict[str, Any] = {}

    async def fake_update_metadata(model_hash, model_data, scanner, paths):
        recorded["args"] = (model_hash, list(paths))
        return ["regular"], ["custom"]

    monkeypatch.setattr(processor_module.MetadataUpdater, "update_metadata_after_import", staticmethod(fake_update_metadata))

    result: Dict[str, Any] = await processor_module.ExampleImagesProcessor.import_images("a" * 64, [str(source_file)])

    assert result["success"] is True
    assert result["files"][0]["name"].startswith("custom_short")

    model_folder = Path(settings_manager.settings["example_images_path"]) / ("a" * 64)
    assert model_folder.exists()
    created_files = list(model_folder.glob("custom_short*.png"))
    assert len(created_files) == 1
    assert created_files[0].read_bytes() == source_file.read_bytes()

    model_hash, paths = recorded["args"]
    assert model_hash == "a" * 64
    assert paths[0][0].startswith(str(model_folder))


async def test_import_images_rejects_missing_parameters(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(processor_module.ExampleImagesValidationError):
        await processor_module.ExampleImagesProcessor.import_images("", [])

    with pytest.raises(processor_module.ExampleImagesValidationError):
        await processor_module.ExampleImagesProcessor.import_images("abc", [])


async def test_import_images_raises_when_model_not_found(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    settings_manager = get_settings_manager()
    settings_manager.settings["example_images_path"] = str(tmp_path)

    async def _empty_scanner(cls=None):
        return StubScanner([])

    monkeypatch.setattr(processor_module.ServiceRegistry, "get_lora_scanner", classmethod(_empty_scanner))
    monkeypatch.setattr(processor_module.ServiceRegistry, "get_checkpoint_scanner", classmethod(_empty_scanner))
    monkeypatch.setattr(processor_module.ServiceRegistry, "get_embedding_scanner", classmethod(_empty_scanner))
    monkeypatch.setattr(processor_module.ServiceRegistry, "get_other_scanner", classmethod(_empty_scanner))

    with pytest.raises(processor_module.ExampleImagesImportError):
        await processor_module.ExampleImagesProcessor.import_images("a" * 64, [str(tmp_path / "missing.png")])


@pytest.mark.asyncio
async def test_delete_custom_image_preserves_existing_metadata(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    settings_manager = get_settings_manager()
    settings_manager.settings["example_images_path"] = str(tmp_path / "examples")

    model_hash = "c" * 64
    model_file = tmp_path / "keep.safetensors"
    model_file.write_text("content", encoding="utf-8")
    metadata_path = tmp_path / "keep.metadata.json"

    existing_metadata: Dict[str, Any] = {
        "model_name": "Keep",
        "file_path": str(model_file),
        "civitai": {
            "images": [{"url": "https://example.com/default.png", "type": "image"}],
            "customImages": [{"id": "existing-id", "url": "", "type": "image"}],
            "trainedWords": ["foo"],
        },
    }
    metadata_path.write_text(json.dumps(existing_metadata), encoding="utf-8")

    model_data = {
        "sha256": model_hash,
        "model_name": "Keep",
        "file_path": str(model_file),
        "civitai": {
            "customImages": [{"id": "existing-id", "url": "", "type": "image"}],
            "trainedWords": ["foo"],
        },
    }

    class Scanner(StubScanner):
        def has_hash(self, hash_value: str) -> bool:
            return hash_value == model_hash

    scanner = Scanner([model_data])

    async def _return_scanner(cls=None):
        return scanner

    monkeypatch.setattr(processor_module.ServiceRegistry, "get_lora_scanner", classmethod(_return_scanner))
    monkeypatch.setattr(processor_module.ServiceRegistry, "get_checkpoint_scanner", classmethod(_return_scanner))
    monkeypatch.setattr(processor_module.ServiceRegistry, "get_embedding_scanner", classmethod(_return_scanner))
    monkeypatch.setattr(processor_module.ServiceRegistry, "get_other_scanner", classmethod(_return_scanner))

    model_folder = get_model_folder(model_hash)
    os.makedirs(model_folder, exist_ok=True)
    (Path(model_folder) / "custom_existing-id.png").write_bytes(b"data")

    saved: list[tuple[str, Dict[str, Any]]] = []

    async def fake_save(path: str, payload: Dict[str, Any]) -> bool:
        saved.append((path, payload.copy()))
        return True

    monkeypatch.setattr(processor_module.MetadataManager, "save_metadata", staticmethod(fake_save))

    class StubRequest:
        def __init__(self, payload: Dict[str, Any]) -> None:
            self._payload = payload

        async def json(self) -> Dict[str, Any]:
            return self._payload

    response = await processor_module.ExampleImagesProcessor.delete_custom_image(
        StubRequest({"model_hash": model_hash, "short_id": "existing-id"})
    )

    assert response.status == 200
    assert response.text is not None
    body = json.loads(response.text)
    assert body["success"] is True
    assert body["custom_images"] == []
    assert not (Path(model_folder) / "custom_existing-id.png").exists()

    saved_path, saved_payload = saved[-1]
    assert saved_path == str(model_file)
    assert saved_payload["civitai"]["images"] == existing_metadata["civitai"]["images"]
    assert saved_payload["civitai"]["trainedWords"] == ["foo"]
    assert saved_payload["civitai"]["customImages"] == []

    assert scanner.updated
    _, _, updated_metadata = scanner.updated[-1]
    assert updated_metadata["civitai"]["images"] == existing_metadata["civitai"]["images"]
    assert updated_metadata["civitai"]["customImages"] == []


def _patch_scanner_getters(monkeypatch: pytest.MonkeyPatch, **scanners) -> None:
    """Point every model-scanner getter at the given stub (empty by default)."""

    async def _empty(cls=None):
        return StubScanner([])

    for name in (
        "get_lora_scanner",
        "get_checkpoint_scanner",
        "get_embedding_scanner",
        "get_other_scanner",
    ):
        stub = scanners.get(name)
        if stub is None:
            getter = _empty
        else:
            async def getter(cls=None, _stub=stub):  # noqa: B023 - bound per iteration
                return _stub
        monkeypatch.setattr(
            processor_module.ServiceRegistry, name, classmethod(getter)
        )


@pytest.mark.asyncio
async def test_import_images_finds_model_in_other_scanner(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """Other-category models (VAEs, text encoders) live in the Other scanner;
    importing example images must search it too."""
    settings_manager = get_settings_manager()
    settings_manager.settings["example_images_path"] = str(tmp_path / "examples")
    settings_manager.settings["libraries"] = {"default": {}}
    settings_manager.settings["active_library"] = "default"

    model_hash = "b" * 64
    model_data = {
        "sha256": model_hash,
        "model_name": "VAE",
        "file_path": str(tmp_path / "vae.safetensors"),
        "civitai": {},
    }
    other_scanner = StubScanner([model_data])
    _patch_scanner_getters(monkeypatch, get_other_scanner=other_scanner)

    source_file = tmp_path / "upload.png"
    source_file.write_bytes(b"PNG data")
    monkeypatch.setattr(
        processor_module.ExampleImagesProcessor,
        "generate_short_id",
        staticmethod(lambda: "short"),
    )

    recorded: Dict[str, Any] = {}

    async def fake_update_metadata(model_hash, model_data, scanner, paths):
        recorded["scanner"] = scanner
        return [], []

    monkeypatch.setattr(
        processor_module.MetadataUpdater,
        "update_metadata_after_import",
        staticmethod(fake_update_metadata),
    )

    result = await processor_module.ExampleImagesProcessor.import_images(
        model_hash, [str(source_file)]
    )

    assert result["success"] is True
    assert result["model_hash"] == model_hash
    assert recorded["scanner"] is other_scanner


@pytest.mark.asyncio
async def test_resolve_hash_for_file_path_computes_pending_hash(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """A model whose hash is still pending gets it computed on demand."""
    model_path = str(tmp_path / "encoder.safetensors").replace(os.sep, "/")
    item = {"file_path": model_path, "sha256": "", "hash_status": "pending"}

    calculated: list[str] = []

    class PendingScanner(StubScanner):
        async def calculate_hash_for_model(self, file_path: str):
            calculated.append(file_path)
            return "f" * 64

    _patch_scanner_getters(monkeypatch, get_other_scanner=PendingScanner([item]))

    result = await processor_module.ExampleImagesProcessor.resolve_hash_for_file_path(
        model_path
    )

    assert result == "f" * 64
    assert calculated == [model_path]


@pytest.mark.asyncio
async def test_resolve_hash_for_file_path_returns_completed_hash_without_recompute(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    model_path = str(tmp_path / "model.safetensors").replace(os.sep, "/")
    item = {"file_path": model_path, "sha256": "c" * 64, "hash_status": "completed"}

    class EagerScanner(StubScanner):
        async def calculate_hash_for_model(self, file_path: str):  # pragma: no cover
            raise AssertionError("must not recompute a completed hash")

    _patch_scanner_getters(monkeypatch, get_lora_scanner=EagerScanner([item]))

    result = await processor_module.ExampleImagesProcessor.resolve_hash_for_file_path(
        model_path
    )

    assert result == "c" * 64


@pytest.mark.asyncio
async def test_resolve_hash_for_file_path_unknown_file_returns_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_scanner_getters(monkeypatch)

    assert (
        await processor_module.ExampleImagesProcessor.resolve_hash_for_file_path(
            "/models/nope.safetensors"
        )
        == ""
    )


@pytest.mark.asyncio
async def test_download_model_images_uses_bounded_renditions(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """Images use the configured width and videos are transcoded at their cap."""
    settings_manager = get_settings_manager()
    settings_manager.settings["example_images_max_width"] = 800
    settings_manager.settings["example_images_video_max_width"] = 450

    images = [
        {
            "url": "https://image.civitai.com/xG1nk/uuid/original=true/1.jpeg",
            "type": "image",
        },
        {
            "url": "https://image.civitai.com/xG1nk/uuid/original=true/2.mp4",
            "type": "video",
        },
    ]

    class RecordingDownloader:
        def __init__(self) -> None:
            self.calls: list[str] = []

        async def download_to_memory(self, url, use_auth=False, return_headers=False):
            self.calls.append(url)
            if url.endswith(".mp4"):
                return True, b"\x00\x00\x00\x18ftypmp42data", {"content-type": "video/mp4"}
            return True, b"\xff\xd8\xff" + b"data", {"content-type": "image/jpeg"}

    downloader = RecordingDownloader()
    limiter = processor_module.MediaDownloadLimiter(max_concurrency=2)
    outcome = await (
        processor_module.ExampleImagesProcessor.download_model_images_with_tracking(
            "hash", "model", images, str(tmp_path), True, downloader, limiter=limiter
        )
    )

    assert outcome.success is True
    assert outcome.is_stale is False
    assert outcome.failed == []
    assert outcome.rate_limited == []
    assert any("width=800,optimized=true/1.jpeg" in url for url in downloader.calls)
    assert any(
        "transcode=true,width=450,optimized=true/2.mp4" in url
        for url in downloader.calls
    )
    assert Path(tmp_path, "image_0.jpg").exists()
    assert Path(tmp_path, "image_1.mp4").exists()


@pytest.mark.asyncio
async def test_download_model_images_runs_requests_concurrently(tmp_path) -> None:
    """The limiter's pool overlaps network waits instead of serializing them."""
    images = [
        {
            "url": f"https://image.civitai.com/xG1nk/uuid/original=true/{i}.jpeg",
            "type": "image",
        }
        for i in range(6)
    ]

    class TrackingDownloader:
        def __init__(self) -> None:
            self.active = 0
            self.max_active = 0

        async def download_to_memory(self, url, use_auth=False, return_headers=False):
            self.active += 1
            self.max_active = max(self.max_active, self.active)
            try:
                await asyncio.sleep(0.02)
                return True, b"\xff\xd8\xff" + b"data", {"content-type": "image/jpeg"}
            finally:
                self.active -= 1

    downloader = TrackingDownloader()
    limiter = processor_module.MediaDownloadLimiter(max_concurrency=3)
    outcome = await (
        processor_module.ExampleImagesProcessor.download_model_images_with_tracking(
            "hash", "model", images, str(tmp_path), False, downloader, limiter=limiter
        )
    )

    assert outcome.success is True
    assert outcome.failed == []
    assert outcome.rate_limited == []
    assert 1 < downloader.max_active <= 3
    assert len(list(Path(tmp_path).glob("image_*.jpg"))) == 6


@pytest.mark.asyncio
async def test_download_model_images_shares_429_cooldown(tmp_path) -> None:
    """A 429 retries after the shared cooldown, not a per-task 60s sleep."""
    images = [
        {
            "url": f"https://image.civitai.com/xG1nk/uuid/original=true/{i}.jpeg",
            "type": "image",
        }
        for i in range(2)
    ]

    class RateLimitedThenOk:
        def __init__(self) -> None:
            self.attempts: dict[str, int] = {}

        async def download_to_memory(self, url, use_auth=False, return_headers=False):
            attempt = self.attempts.get(url, 0) + 1
            self.attempts[url] = attempt
            if attempt == 1:
                return False, "Rate limited (429), retry after 0.01s", None
            return True, b"\xff\xd8\xff" + b"data", {"content-type": "image/jpeg"}

    downloader = RateLimitedThenOk()
    limiter = processor_module.MediaDownloadLimiter(
        max_concurrency=2, min_cooldown=0.01, default_cooldown=0.01
    )
    started = time.monotonic()
    outcome = await (
        processor_module.ExampleImagesProcessor.download_model_images_with_tracking(
            "hash", "model", images, str(tmp_path), False, downloader, limiter=limiter
        )
    )
    elapsed = time.monotonic() - started

    assert outcome.success is True
    assert outcome.failed == []
    assert outcome.rate_limited == []
    assert all(attempts == 2 for attempts in downloader.attempts.values())
    assert elapsed < 1.0


@pytest.mark.asyncio
async def test_download_model_images_marks_404_stale_with_original_url(tmp_path) -> None:
    image = {
        "url": "https://image.civitai.com/xG1nk/uuid/original=true/1.jpeg",
        "type": "image",
    }

    class NotFoundDownloader:
        async def download_to_memory(self, url, use_auth=False, return_headers=False):
            return False, "File not found", None

    outcome = await (
        processor_module.ExampleImagesProcessor.download_model_images_with_tracking(
            "hash", "model", [image], str(tmp_path), True, NotFoundDownloader()
        )
    )

    assert outcome.success is False
    assert outcome.is_stale is True
    assert outcome.failed == [image["url"]]
    assert outcome.rate_limited == []


def test_resolve_genur_signed_url_uses_direct_small_rendition() -> None:
    signed = (
        "https://img.genur.art/sig/width:450/quality:85/"
        "aHR0cHM6Ly9jLmdlbnVyLmFydC83MjIwZGMwYy05N2YyLTQ0YzEtYWNkZi00ZDBhMzkxY2ZjNmQ="
    )
    assert (
        processor_module.resolve_genur_media_url(signed)
        == "https://c.genur.art/7220dc0c-97f2-44c1-acdf-4d0a391cfc6d_small.webp"
    )


def test_resolve_genur_direct_url_adds_small_suffix() -> None:
    assert (
        processor_module.resolve_genur_media_url(
            "https://c.genur.art/7220dc0c-97f2-44c1-acdf-4d0a391cfc6d"
        )
        == "https://c.genur.art/7220dc0c-97f2-44c1-acdf-4d0a391cfc6d_small.webp"
    )
    existing = "https://c.genur.art/7220dc0c-97f2-44c1-acdf-4d0a391cfc6d_large.webp"
    assert processor_module.resolve_genur_media_url(existing) == existing


def test_resolve_genur_leaves_other_urls_alone() -> None:
    url = "https://image.civitai.com/xG1nk/uuid/original=true/1.jpeg"
    assert processor_module.resolve_genur_media_url(url) == url


@pytest.mark.asyncio
async def test_download_model_images_classifies_network_errors_as_transient(tmp_path) -> None:
    image = {
        "url": "https://img.genur.art/sig/width:450/quality:85/"
        "aHR0cHM6Ly9jLmdlbnVyLmFydC83MjIwZGMwYy05N2YyLTQ0YzEtYWNkZi00ZDBhMzkxY2ZjNmQ=",
        "type": "image",
    }

    class OfflineDownloader:
        async def download_to_memory(self, url, use_auth=False, return_headers=False):
            return False, "Network offline, will retry automatically later", None

    outcome = await (
        processor_module.ExampleImagesProcessor.download_model_images_with_tracking(
            "hash", "model", [image], str(tmp_path), True, OfflineDownloader()
        )
    )

    assert outcome.success is False
    assert outcome.transient == [image["url"]]
    assert outcome.failed == []
    assert outcome.rate_limited == []


@pytest.mark.asyncio
async def test_download_model_images_empty_error_is_transient(tmp_path) -> None:
    """aiohttp connection errors can stringify to an empty message.

    They used to fall through the 404/transient checks as a permanent
    failure, which removed the image from the model's metadata.
    """

    image = {
        "url": "https://c.genur.art/7220dc0c-97f2-44c1-acdf-4d0a391cfc6d_small.webp",
        "type": "image",
    }

    class EmptyErrorDownloader:
        async def download_to_memory(self, url, use_auth=False, return_headers=False):
            return False, "", None

    outcome = await (
        processor_module.ExampleImagesProcessor.download_model_images_with_tracking(
            "hash", "model", [image], str(tmp_path), True, EmptyErrorDownloader()
        )
    )

    assert outcome.success is False
    assert outcome.transient == [image["url"]]
    assert outcome.failed == []


@pytest.mark.asyncio
async def test_download_model_images_exception_is_transient(tmp_path) -> None:
    image = {
        "url": "https://image.civitai.com/xG1nk/uuid/original=true/1.jpeg",
        "type": "image",
    }

    class RaisingDownloader:
        async def download_to_memory(self, url, use_auth=False, return_headers=False):
            raise RuntimeError("")

    outcome = await (
        processor_module.ExampleImagesProcessor.download_model_images_with_tracking(
            "hash", "model", [image], str(tmp_path), True, RaisingDownloader()
        )
    )

    assert outcome.success is False
    assert outcome.transient == [image["url"]]
    assert outcome.failed == []


@pytest.mark.asyncio
async def test_download_model_images_timeout_is_transient(tmp_path, monkeypatch) -> None:
    """A CDN that accepts and then stalls must not block the model.

    The shared session's 300s socket read is sized for multi-GB model files;
    gallery images get a shorter wall-clock bound.
    """

    monkeypatch.setattr(processor_module, "MEDIA_IMAGE_DOWNLOAD_TIMEOUT_SECONDS", 0.05)
    image = {
        "url": "https://c.genur.art/7220dc0c-97f2-44c1-acdf-4d0a391cfc6d_small.webp",
        "type": "image",
    }

    class StalledDownloader:
        async def download_to_memory(self, url, use_auth=False, return_headers=False):
            await asyncio.sleep(10)
            return True, b"", {}

    outcome = await (
        processor_module.ExampleImagesProcessor.download_model_images_with_tracking(
            "hash", "model", [image], str(tmp_path), True, StalledDownloader()
        )
    )

    assert outcome.success is False
    assert outcome.transient == [image["url"]]
    assert outcome.failed == []


def test_is_transient_treats_blank_message_as_transient() -> None:
    assert processor_module.ExampleImagesProcessor._is_transient_failure("") is True
    assert processor_module.ExampleImagesProcessor._is_transient_failure("   ") is True


@pytest.mark.asyncio
async def test_download_model_images_retries_flagged_genur_image(tmp_path) -> None:
    original = (
        "https://img.genur.art/sig/width:450/quality:85/"
        "aHR0cHM6Ly9jLmdlbnVyLmFydC83MjIwZGMwYy05N2YyLTQ0YzEtYWNkZi00ZDBhMzkxY2ZjNmQ="
    )
    image = {
        "url": original,
        "type": "image",
        "downloadFailed": True,
        "downloadError": "not_found",
    }

    class GenurDownloader:
        def __init__(self) -> None:
            self.calls: list[str] = []

        async def download_to_memory(self, url, use_auth=False, return_headers=False):
            self.calls.append(url)
            return True, b"RIFF\x00\x00\x00\x00WEBPdata", {"content-type": "image/webp"}

    downloader = GenurDownloader()
    outcome = await (
        processor_module.ExampleImagesProcessor.download_model_images_with_tracking(
            "hash",
            "model",
            [image],
            str(tmp_path),
            True,
            downloader,
            retry_failed=True,
        )
    )

    assert outcome.success is True
    assert outcome.recovered == [original]
    assert outcome.downloaded == [original]
    assert downloader.calls == [
        "https://c.genur.art/7220dc0c-97f2-44c1-acdf-4d0a391cfc6d_small.webp"
    ]
    assert Path(tmp_path, "image_0.webp").exists()


@pytest.mark.asyncio
async def test_download_model_images_does_not_retry_flag_without_retry_option(tmp_path) -> None:
    image = {
        "url": "https://image.civitai.com/xG1nk/uuid/original=true/1.jpeg",
        "type": "image",
        "downloadFailed": True,
        "downloadError": "not_found",
    }

    class ShouldNotRun:
        async def download_to_memory(self, url, use_auth=False, return_headers=False):
            raise AssertionError("flagged image must not be requested")

    outcome = await (
        processor_module.ExampleImagesProcessor.download_model_images_with_tracking(
            "hash", "model", [image], str(tmp_path), True, ShouldNotRun()
        )
    )

    assert outcome.success is False
    assert outcome.skipped_failed == 1
    assert outcome.downloaded == []

"""Tests for the OpenModelDB client, provider, and sync-service integration."""

from __future__ import annotations

import json
import time
from types import SimpleNamespace
from typing import Any, Dict, Optional
from unittest.mock import AsyncMock

import pytest

from py.services import openmodeldb_client as openmodeldb_module
from py.services.metadata_sync_service import MetadataSyncService
from py.services.model_metadata_provider import (
    FallbackMetadataProvider,
    ModelMetadataProvider,
    OpenModelDBModelMetadataProvider,
)
from py.services.openmodeldb_client import (
    CACHE_TTL_SECONDS,
    OPENMODELDB_API_BASE,
    OpenModelDBClient,
)


MODEL_SHA = "a" * 64
ALT_SHA = "b" * 64


def _fixture_dumps() -> Dict[str, Dict[str, Any]]:
    """Small OpenModelDB catalogue fixture covering the shape variants."""
    models = {
        "4x-UltraSharp": {
            "name": "4x UltraSharp",
            "author": "kim",
            "license": "MIT",
            "tags": ["general"],
            "description": "Sharp general-purpose upscaler",
            "date": "2023-01-02",
            "architecture": "esrgan",
            "size": ["64nf", "23nb"],
            "scale": 4,
            "inputChannels": 3,
            "outputChannels": 3,
            "thumbnail": {
                "type": "paired",
                "LR": "/thumbs/ultrasharp-lr.png",
                "SR": "/thumbs/ultrasharp-sr.jpg",
            },
            "resources": [
                {
                    "platform": "pytorch",
                    "type": "pth",
                    "size": 67_000_000,
                    "sha256": MODEL_SHA,
                    "urls": ["https://files.example.com/4x-UltraSharp.pth"],
                },
                {
                    "platform": "pytorch",
                    "type": "safetensors",
                    "size": 67_100_000,
                    "sha256": ALT_SHA,
                    "urls": ["https://files.example.com/4x-UltraSharp.safetensors"],
                },
            ],
            "images": [
                {
                    "type": "paired",
                    "caption": "comparison",
                    "LR": "https://img.example.com/lr.jpg",
                    "SR": "https://img.example.com/sr.jpg",
                    "thumbnail": "/thumbs/small/t.jpg",
                }
            ],
        },
        "2x-90s-Sonic-LG": {
            "name": "90s Sonic 2x (Large)",
            "author": "kim",
            "architecture": "esrgan",
            "scale": 2,
            "thumbnail": {
                "type": "paired",
                "LR": "/thumbs/sonic-lr.png",
                "SR": "/thumbs/sonic-sr.jpg",
            },
            "resources": [
                {
                    "platform": "pytorch",
                    "type": "pth",
                    "size": 9_443_322,
                    "sha256": "d" * 64,
                    # mediafire puts the real filename mid-path; the basename
                    # is just "file".
                    "urls": [
                        "https://www.mediafire.com/file/e57pd40qph8nak2/90s_Sonic_2x.pth/file"
                    ],
                }
            ],
            "images": [
                {
                    "type": "paired",
                    "caption": "Tails",
                    # Ephemeral imgdiff viewer sessions: 404 outside them.
                    "LR": "https://imgdiff.net/api/image.php?id=abc&image=2171",
                    "SR": "https://imgdiff.net/api/image.php?id=abc&image=2172",
                    "thumbnail": "/thumbs/small/sonic1.jpg",
                },
                {
                    "type": "paired",
                    "LR": "https://imgdiff.net/api/image.php?id=def&image=2173",
                    "SR": "https://imgdiff.net/api/image.php?id=def&image=2174",
                },
            ],
        },
        "mega-only": {
            "name": "Mega Only",
            "author": "kim",
            "architecture": "esrgan",
            "scale": 4,
            "resources": [
                {
                    "platform": "pytorch",
                    "type": "pth",
                    "size": 60_000_000,
                    "sha256": "e" * 64,
                    # A folder link carries no filename at all.
                    "urls": ["https://mega.nz/folder/qZRBmaIY#nIG8KyWFcGNTuMX_XNbJ_g"],
                }
            ],
            "images": [],
        },
        "1x-DeJPG": {
            "name": "1x DeJPG",
            "author": ["alice", "bob"],
            "license": None,
            "tags": ["restoration"],
            "description": "",
            "date": "2021-05-06",
            "architecture": "compact",
            "size": [],
            "scale": 1,
            "inputChannels": 3,
            "outputChannels": 3,
            "resources": [
                {
                    "platform": "pytorch",
                    "type": "pth",
                    "size": 3_000_000,
                    "sha256": "c" * 64,
                    "urls": ["https://files.example.com/1x-DeJPG.pth"],
                }
            ],
            "images": [
                {
                    "type": "standalone",
                    "url": "https://img.example.com/dejpg.png",
                }
            ],
        },
    }
    users = {
        "kim": {"name": "Kim"},
        "alice": {"name": "Alice"},
        "bob": {"name": "Bob"},
    }
    tags = {
        "general": {"name": "General Purpose"},
        "restoration": {"name": "Restoration"},
    }
    architectures = {
        "esrgan": {"name": "ESRGAN"},
        "compact": {"name": "Compact"},
    }
    return {
        "models": models,
        "users": users,
        "tags": tags,
        "architectures": architectures,
    }


class DummyDownloader:
    """Downloader stub exposing the two entry points the client uses."""

    def __init__(
        self,
        *,
        payloads: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, Dict[str, str]]] = None,
        fail: bool = False,
    ) -> None:
        self.payloads = payloads or {}
        self.headers = headers or {}
        self.fail = fail
        self.get_calls: list = []
        self.head_calls: list = []

    async def get_response_headers(self, url, use_auth=False, custom_headers=None):
        self.head_calls.append(url)
        if self.fail:
            return False, "network unreachable"
        return True, dict(self.headers.get(url, {}))

    async def make_request(self, method, url, use_auth=False, custom_headers=None, **kwargs):
        self.get_calls.append(url)
        if self.fail:
            return False, "network unreachable"
        return True, self.payloads.get(url)


def _dump_url(name: str) -> str:
    return f"{OPENMODELDB_API_BASE}/{name}.json"


@pytest.fixture
def dumps() -> Dict[str, Dict[str, Any]]:
    return _fixture_dumps()


@pytest.fixture
def make_client(monkeypatch, tmp_path):
    """Factory returning a client backed by a DummyDownloader and tmp cache."""

    def _make(downloader: DummyDownloader, **kwargs) -> OpenModelDBClient:
        monkeypatch.setattr(
            openmodeldb_module,
            "get_downloader",
            AsyncMock(return_value=downloader),
        )
        return OpenModelDBClient(cache_dir=str(tmp_path / "omdb"), **kwargs)

    return _make


def _payloads_by_url(dumps: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    return {f"{OPENMODELDB_API_BASE}/{name}.json": payload for name, payload in dumps.items()}


# ---------------------------------------------------------------------------
# Index building + CivitAI-shape mapping
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_lookup_maps_catalogue_entry_to_civitai_shape(make_client, dumps):
    downloader = DummyDownloader(payloads=_payloads_by_url(dumps))
    client = make_client(downloader)

    result, error = await client.get_model_by_hash(MODEL_SHA)

    assert error is None
    assert result is not None

    # Version-level fields
    assert result["name"] == "4x UltraSharp"
    assert result["source"] == "openmodeldb"
    assert result["baseModel"] == "Other"
    assert result["publishedAt"] == "2023-01-02"
    assert result["trainedWords"] == []
    assert result["description"] == "Sharp general-purpose upscaler"
    # OpenModelDB ids are strings; numeric CivitAI ids must stay absent so
    # consumers do not treat this as a CivitAI model.
    assert "id" not in result
    assert "modelId" not in result

    # Model block
    model = result["model"]
    assert model["name"] == "4x UltraSharp"
    assert model["type"] == "Upscaler"
    assert model["tags"] == ["General Purpose"]
    assert model["license"] == "MIT"
    assert model["description"] == "Sharp general-purpose upscaler"

    # Creator resolved via users.json
    assert result["creator"]["username"] == "Kim"

    # Files: every resource becomes a file; the hash-matched one is primary.
    files = result["files"]
    assert len(files) == 2
    primary = [f for f in files if f["primary"]]
    assert len(primary) == 1
    assert primary[0]["name"] == "4x-UltraSharp.pth"
    assert primary[0]["hashes"] == {"SHA256": MODEL_SHA.upper()}
    assert primary[0]["sizeKB"] == pytest.approx(67_000_000 / 1024.0)
    assert primary[0]["downloadUrl"] == "https://files.example.com/4x-UltraSharp.pth"
    assert primary[0]["metadata"]["format"] == "PickleTensor"
    st_file = next(f for f in files if f["name"].endswith(".safetensors"))
    assert st_file["metadata"]["format"] == "SafeTensor"

    # Images: the model-level thumbnail leads (the card preview derives from
    # images[0]); paired entries display their site-hosted thumbnail, never
    # the ephemeral imgdiff originals.
    images = result["images"]
    assert len(images) == 2
    assert images[0]["url"] == "https://openmodeldb.info/thumbs/ultrasharp-sr.jpg"
    assert images[0]["nsfwLevel"] == 1
    assert images[1]["url"] == "https://openmodeldb.info/thumbs/small/t.jpg"
    assert images[1]["meta"] == {"caption": "comparison"}
    # The thumbnail IS the display URL here, so no separate thumbnailUrl.
    assert "thumbnailUrl" not in images[1]

    # OpenModelDB-native provenance block
    omdb = result["openmodeldb"]
    assert omdb["id"] == "4x-UltraSharp"
    assert omdb["url"] == "https://openmodeldb.info/models/4x-UltraSharp"
    assert omdb["authors"] == ["kim"]
    assert omdb["architecture"] == "esrgan"
    assert omdb["architectureName"] == "ESRGAN"
    assert omdb["scale"] == 4


@pytest.mark.asyncio
async def test_lookup_supports_list_authors_and_standalone_images(make_client, dumps):
    downloader = DummyDownloader(payloads=_payloads_by_url(dumps))
    client = make_client(downloader)

    result, error = await client.get_model_by_hash("c" * 64)

    assert error is None
    assert result["creator"]["username"] == "Alice, Bob"
    assert result["openmodeldb"]["authors"] == ["alice", "bob"]
    assert result["images"][0]["url"] == "https://img.example.com/dejpg.png"
    assert result["model"]["tags"] == ["Restoration"]


@pytest.mark.asyncio
async def test_lookup_never_emits_ephemeral_imgdiff_urls(make_client, dumps):
    downloader = DummyDownloader(payloads=_payloads_by_url(dumps))
    client = make_client(downloader)

    result, error = await client.get_model_by_hash("d" * 64)

    assert error is None
    images = result["images"]
    # Model thumbnail first, then the one pair that has a thumbnail; the
    # thumbnail-less imgdiff pair has no displayable asset and is dropped.
    assert [img["url"] for img in images] == [
        "https://openmodeldb.info/thumbs/sonic-sr.jpg",
        "https://openmodeldb.info/thumbs/small/sonic1.jpg",
    ]
    assert all("imgdiff.net" not in img["url"] for img in images)
    # The original viewer URL survives as reference-only metadata.
    assert images[1]["meta"]["comparisonUrl"] == (
        "https://imgdiff.net/api/image.php?id=abc&image=2172"
    )
    assert images[1]["meta"]["caption"] == "Tails"


@pytest.mark.asyncio
async def test_lookup_derives_mediafire_mid_path_filename(make_client, dumps):
    downloader = DummyDownloader(payloads=_payloads_by_url(dumps))
    client = make_client(downloader)

    result, error = await client.get_model_by_hash("d" * 64)

    assert error is None
    # The basename of the mediafire URL is "file"; the real name sits mid-path.
    assert result["files"][0]["name"] == "90s_Sonic_2x.pth"
    # No direct-bytes mirror: the HTML-gateway URL stays as the reference.
    assert result["files"][0]["downloadUrl"].startswith("https://www.mediafire.com/")


@pytest.mark.asyncio
async def test_lookup_synthesizes_filename_for_folder_links(make_client, dumps):
    downloader = DummyDownloader(payloads=_payloads_by_url(dumps))
    client = make_client(downloader)

    result, error = await client.get_model_by_hash("e" * 64)

    assert error is None
    # A mega.nz folder link has no filename; the catalogue type is authoritative.
    assert result["files"][0]["name"] == "mega-only.pth"


@pytest.mark.asyncio
async def test_lookup_is_case_insensitive_and_reports_misses(make_client, dumps):
    downloader = DummyDownloader(payloads=_payloads_by_url(dumps))
    client = make_client(downloader)

    result, error = await client.get_model_by_hash(MODEL_SHA.upper())
    assert error is None and result is not None

    result, error = await client.get_model_by_hash("f" * 64)
    assert result is None
    assert error == "Model not found"


@pytest.mark.asyncio
async def test_lookup_unavailable_without_cache_or_network(make_client):
    downloader = DummyDownloader(fail=True)
    client = make_client(downloader)

    result, error = await client.get_model_by_hash(MODEL_SHA)

    assert result is None
    assert error == "OpenModelDB catalogue unavailable"


@pytest.mark.asyncio
async def test_lookup_survives_missing_optional_dumps(make_client, dumps):
    # users/tags/architectures failing must degrade to raw ids, not break.
    payloads = _payloads_by_url(dumps)
    payloads[_dump_url("users")] = None
    payloads[_dump_url("tags")] = None
    payloads[_dump_url("architectures")] = None
    downloader = DummyDownloader(payloads=payloads)
    client = make_client(downloader)

    result, error = await client.get_model_by_hash(MODEL_SHA)

    assert error is None
    assert result["creator"]["username"] == "kim"  # raw id fallback
    assert result["model"]["tags"] == ["general"]  # raw id fallback
    assert result["openmodeldb"]["architectureName"] == "esrgan"


# ---------------------------------------------------------------------------
# Disk cache, TTL, and conditional revalidation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_disk_cache_written_and_reused_without_network(make_client, dumps):
    payloads = _payloads_by_url(dumps)
    downloader = DummyDownloader(payloads=payloads)
    client = make_client(downloader)

    result, _ = await client.get_model_by_hash(MODEL_SHA)
    assert result is not None
    assert len(downloader.get_calls) == 4  # all four dumps fetched once

    # A second lookup hits the warm in-memory index: no additional HTTP.
    result, _ = await client.get_model_by_hash(MODEL_SHA)
    assert result is not None
    assert len(downloader.get_calls) == 4
    assert len(downloader.head_calls) == 4  # HEAD probes from the initial fetch only

    # A fresh client instance (simulating a restart) within the TTL reads the
    # disk cache without any network traffic.
    offline = DummyDownloader(fail=True)
    client2 = make_client(offline)
    result, error = await client2.get_model_by_hash(MODEL_SHA)
    assert error is None
    assert result["name"] == "4x UltraSharp"
    assert offline.get_calls == []
    assert offline.head_calls == []


@pytest.mark.asyncio
async def test_expired_cache_revalidates_with_etag(make_client, dumps, tmp_path):
    cache_dir = tmp_path / "omdb"
    payloads = _payloads_by_url(dumps)
    etags = {name: f'"etag-{name}"' for name in dumps}
    headers = {
        url: {"ETag": etags[name], "Last-Modified": "Wed, 01 Jan 2025 00:00:00 GMT"}
        for name, url in ((n, _dump_url(n)) for n in dumps)
    }
    downloader = DummyDownloader(payloads=payloads, headers=headers)
    client = make_client(downloader)

    await client.get_model_by_hash(MODEL_SHA)
    assert len(downloader.get_calls) == 4

    # Force the disk cache to look stale.
    meta_path = cache_dir / "_meta.json"
    meta = json.loads(meta_path.read_text())
    meta["fetched_at"] = time.time() - (CACHE_TTL_SECONDS + 60)
    meta_path.write_text(json.dumps(meta))

    # Unchanged etags -> cached bodies reused, no GET re-download.
    downloader2 = DummyDownloader(payloads=None, headers=headers)
    client2 = make_client(downloader2)
    result, error = await client2.get_model_by_hash(MODEL_SHA)
    assert error is None and result is not None
    assert len(downloader2.head_calls) == 4
    assert downloader2.get_calls == []

    # The TTL marker is refreshed even though bodies were reused.
    meta = json.loads(meta_path.read_text())
    assert meta["fetched_at"] > time.time() - 60
    assert meta["etags"]["models"] == '"etag-models"'


@pytest.mark.asyncio
async def test_expired_cache_refetches_changed_dump(make_client, dumps, tmp_path):
    cache_dir = tmp_path / "omdb"
    payloads = _payloads_by_url(dumps)
    old_etags = {
        _dump_url(name): {"ETag": f'"old-{name}"'} for name in dumps
    }
    downloader = DummyDownloader(payloads=payloads, headers=old_etags)
    client = make_client(downloader)
    await client.get_model_by_hash(MODEL_SHA)

    meta_path = cache_dir / "_meta.json"
    meta = json.loads(meta_path.read_text())
    meta["fetched_at"] = time.time() - (CACHE_TTL_SECONDS + 60)
    meta_path.write_text(json.dumps(meta))

    # Server reports a new etag for models.json only -> only it is re-downloaded.
    new_headers = dict(old_etags)
    new_headers[_dump_url("models")] = {"ETag": '"new-models"'}
    downloader2 = DummyDownloader(payloads=payloads, headers=new_headers)
    client2 = make_client(downloader2)
    result, error = await client2.get_model_by_hash(MODEL_SHA)
    assert error is None and result is not None
    assert downloader2.get_calls == [_dump_url("models")]

    meta = json.loads(meta_path.read_text())
    assert meta["etags"]["models"] == '"new-models"'
    assert meta["etags"]["users"] == '"old-users"'


@pytest.mark.asyncio
async def test_network_failure_falls_back_to_stale_cache(make_client, dumps, tmp_path):
    cache_dir = tmp_path / "omdb"
    payloads = _payloads_by_url(dumps)
    downloader = DummyDownloader(payloads=payloads)
    client = make_client(downloader)
    await client.get_model_by_hash(MODEL_SHA)

    meta_path = cache_dir / "_meta.json"
    meta = json.loads(meta_path.read_text())
    meta["fetched_at"] = time.time() - (CACHE_TTL_SECONDS + 60)
    meta_path.write_text(json.dumps(meta))

    offline = DummyDownloader(fail=True)
    client2 = make_client(offline)
    result, error = await client2.get_model_by_hash(MODEL_SHA)
    assert error is None
    assert result["name"] == "4x UltraSharp"


# ---------------------------------------------------------------------------
# Provider wrapper
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_provider_delegates_and_declares_unsupported_surface(make_client, dumps):
    downloader = DummyDownloader(payloads=_payloads_by_url(dumps))
    client = make_client(downloader)
    provider = OpenModelDBModelMetadataProvider(client)

    result, error = await provider.get_model_by_hash(MODEL_SHA)
    assert error is None and result is not None

    assert await provider.get_model_versions("4x-UltraSharp") is None
    assert await provider.get_model_version(model_id=1) is None
    version, version_error = await provider.get_model_version_info("123")
    assert version is None and version_error == "Model not found"
    assert await provider.get_user_models("kim") is None


@pytest.mark.asyncio
async def test_fallback_chain_continues_past_openmodeldb_miss(make_client, dumps):
    downloader = DummyDownloader(payloads=_payloads_by_url(dumps))
    client = make_client(downloader)
    openmodeldb = OpenModelDBModelMetadataProvider(client)

    class _HitProvider(ModelMetadataProvider):
        async def get_model_by_hash(self, model_hash):
            return {"source": "elsewhere", "model": {"name": "Hit"}}, None

        async def get_model_versions(self, model_id):
            return None

        async def get_model_version(self, model_id=None, version_id=None):
            return None

        async def get_model_version_info(self, version_id):
            return None, None

        async def get_user_models(self, username, cursor=None):
            return None

    fallback = FallbackMetadataProvider(
        [("openmodeldb_api", openmodeldb), ("other", _HitProvider())]
    )

    result, error = await fallback.get_model_by_hash("f" * 64)
    assert result is not None
    assert result["model"]["name"] == "Hit"


# ---------------------------------------------------------------------------
# FallbackMetadataProvider.excluding + sync-service sub_type gating
# ---------------------------------------------------------------------------


class _RecordingProvider(ModelMetadataProvider):
    def __init__(self, label: str, result: Optional[Dict[str, Any]] = None) -> None:
        self.label = label
        self.result = result
        self.calls: list = []

    async def get_model_by_hash(self, model_hash: str):
        self.calls.append(model_hash)
        return self.result, None if self.result else "Model not found"

    async def get_model_versions(self, model_id):
        return None

    async def get_model_version(self, model_id=None, version_id=None):
        return None

    async def get_model_version_info(self, version_id):
        return None, None

    async def get_user_models(self, username, cursor=None):
        return None


def test_fallback_excluding_drops_named_providers():
    civitai = _RecordingProvider("civitai_api")
    openmodeldb = _RecordingProvider("openmodeldb_api")
    fallback = FallbackMetadataProvider(
        [("civitai_api", civitai), ("openmodeldb_api", openmodeldb)]
    )

    filtered = fallback.excluding({"openmodeldb_api"})
    assert filtered is not fallback
    assert filtered._provider_labels == ["civitai_api"]
    # Original chain is untouched.
    assert fallback._provider_labels == ["civitai_api", "openmodeldb_api"]
    # Empty/no-op exclusions return the same instance.
    assert fallback.excluding(set()) is fallback


def _build_sync_service(default_provider, provider_selector):
    metadata_manager = SimpleNamespace(save_metadata=AsyncMock())
    preview_service = SimpleNamespace(ensure_preview_for_metadata=AsyncMock())
    settings = SimpleNamespace(get=lambda key, default=None: default)
    return MetadataSyncService(
        metadata_manager=metadata_manager,
        preview_service=preview_service,
        settings=settings,
        default_metadata_provider_factory=AsyncMock(return_value=default_provider),
        metadata_provider_selector=provider_selector,
    )


@pytest.mark.asyncio
async def test_sync_gates_openmodeldb_out_for_non_upscalers(tmp_path):
    civitai = _RecordingProvider("civitai_api")
    openmodeldb = _RecordingProvider(
        "openmodeldb_api", result={"source": "openmodeldb", "model": {"name": "OMDB"}}
    )
    fallback = FallbackMetadataProvider(
        [("civitai_api", civitai), ("openmodeldb_api", openmodeldb)]
    )
    service = _build_sync_service(fallback, AsyncMock())

    model_data: Dict[str, Any] = {
        "model_name": "lora",
        "file_path": str(tmp_path / "lora.safetensors"),
        # No sub_type (a LoRA): openmodeldb must not be consulted.
    }
    ok, _ = await service.fetch_and_update_model(
        sha256="abc",
        file_path=model_data["file_path"],
        model_data=model_data,
        update_cache_func=AsyncMock(return_value=True),
    )
    assert ok is False  # nothing found anywhere
    assert civitai.calls == ["abc"]
    assert openmodeldb.calls == []


@pytest.mark.asyncio
async def test_sync_consults_openmodeldb_for_upscalers(tmp_path):
    civitai = _RecordingProvider("civitai_api")
    openmodeldb = _RecordingProvider(
        "openmodeldb_api",
        result={
            "source": "openmodeldb",
            "name": "4x UltraSharp",
            "model": {"name": "4x UltraSharp", "type": "Upscaler", "tags": []},
            "files": [{"name": "x.pth", "hashes": {"SHA256": "ABC"}}],
            "images": [],
        },
    )
    fallback = FallbackMetadataProvider(
        [("civitai_api", civitai), ("openmodeldb_api", openmodeldb)]
    )
    service = _build_sync_service(fallback, AsyncMock())

    model_data: Dict[str, Any] = {
        "model_name": "upscaler",
        "file_path": str(tmp_path / "upscaler.pth"),
        "sub_type": "upscaler",
    }
    ok, error = await service.fetch_and_update_model(
        sha256="abc",
        file_path=model_data["file_path"],
        model_data=model_data,
        update_cache_func=AsyncMock(return_value=True),
    )
    assert ok is True, error
    assert civitai.calls == ["abc"]
    assert openmodeldb.calls == ["abc"]
    assert model_data["metadata_source"] == "openmodeldb"


@pytest.mark.asyncio
async def test_sync_deleted_upscaler_still_reaches_openmodeldb(tmp_path):
    openmodeldb = _RecordingProvider(
        "openmodeldb_api",
        result={
            "source": "openmodeldb",
            "name": "Recovered",
            "model": {"name": "Recovered", "type": "Upscaler", "tags": []},
            "files": [],
            "images": [],
        },
    )

    async def selector(name):
        if name == "openmodeldb_api":
            return openmodeldb
        raise ValueError(f"Provider '{name}' is not registered")

    service = _build_sync_service(
        SimpleNamespace(get_model_by_hash=AsyncMock(return_value=(None, "Model not found"))),
        AsyncMock(side_effect=selector),
    )

    model_data: Dict[str, Any] = {
        "model_name": "deleted upscaler",
        "file_path": str(tmp_path / "deleted.pth"),
        "sub_type": "upscaler",
        "civitai_deleted": True,
        "metadata_source": "openmodeldb",
    }
    ok, error = await service.fetch_and_update_model(
        sha256="abc",
        file_path=model_data["file_path"],
        model_data=model_data,
        update_cache_func=AsyncMock(return_value=True),
    )
    assert ok is True, error
    assert openmodeldb.calls == ["abc"]
    assert model_data["metadata_source"] == "openmodeldb"


@pytest.mark.asyncio
async def test_sync_openmodeldb_sourced_model_prefers_openmodeldb_provider(tmp_path):
    """A model downloaded from OpenModelDB refreshes against its catalogue."""
    civitai = _RecordingProvider("civitai_api")
    openmodeldb = _RecordingProvider(
        "openmodeldb_api",
        result={
            "source": "openmodeldb",
            "name": "4x UltraSharp",
            "model": {"name": "4x UltraSharp", "type": "Upscaler", "tags": []},
            "files": [{"name": "x.pth", "hashes": {"SHA256": "ABC"}}],
            "images": [],
        },
    )

    async def selector(name):
        return {"civitai_api": civitai, "openmodeldb_api": openmodeldb}[name]

    service = _build_sync_service(
        SimpleNamespace(get_model_by_hash=AsyncMock(return_value=(None, "Model not found"))),
        AsyncMock(side_effect=selector),
    )

    model_data: Dict[str, Any] = {
        "model_name": "upscaler",
        "file_path": str(tmp_path / "upscaler.pth"),
        "sub_type": "upscaler",
        "source_platform": "openmodeldb",
        "source_url": "https://openmodeldb.info/models/4x-UltraSharp",
    }
    ok, error = await service.fetch_and_update_model(
        sha256="abc",
        file_path=model_data["file_path"],
        model_data=model_data,
        update_cache_func=AsyncMock(return_value=True),
    )
    assert ok is True, error
    # The source's own catalogue answers first; CivitAI is not needed.
    assert openmodeldb.calls == ["abc"]
    assert civitai.calls == []
    assert model_data["metadata_source"] == "openmodeldb"
    # A "not found" from the source provider must not read as civitai-deleted.
    assert model_data.get("civitai_deleted") is not True


@pytest.mark.asyncio
async def test_sync_openmodeldb_sourced_model_falls_back_to_civitai(tmp_path):
    """When the OpenModelDB catalogue has no record, CivitAI is still tried."""
    civitai = _RecordingProvider(
        "civitai_api",
        result={
            "source": "civitai_api",
            "name": "Also on CivitAI",
            "model": {"name": "Also on CivitAI", "type": "Upscaler", "tags": []},
            "files": [{"name": "x.pth", "hashes": {"SHA256": "ABC"}}],
            "images": [],
        },
    )
    openmodeldb = _RecordingProvider("openmodeldb_api")

    async def selector(name):
        return {"civitai_api": civitai, "openmodeldb_api": openmodeldb}[name]

    service = _build_sync_service(
        SimpleNamespace(get_model_by_hash=AsyncMock(return_value=(None, "Model not found"))),
        AsyncMock(side_effect=selector),
    )

    model_data: Dict[str, Any] = {
        "model_name": "upscaler",
        "file_path": str(tmp_path / "upscaler.pth"),
        "sub_type": "upscaler",
        "source_platform": "openmodeldb",
        "source_url": "https://openmodeldb.info/models/4x-UltraSharp",
    }
    ok, error = await service.fetch_and_update_model(
        sha256="abc",
        file_path=model_data["file_path"],
        model_data=model_data,
        update_cache_func=AsyncMock(return_value=True),
    )
    assert ok is True, error
    assert openmodeldb.calls == ["abc"]
    assert civitai.calls == ["abc"]
    assert model_data["metadata_source"] == "civitai_api"


@pytest.mark.asyncio
async def test_sync_huggingface_sourced_model_stays_civitai_only(tmp_path):
    """Sources without their own provider keep the CivitAI-only behaviour."""
    civitai = _RecordingProvider("civitai_api")

    async def selector(name):
        return {"civitai_api": civitai}[name]

    service = _build_sync_service(
        SimpleNamespace(get_model_by_hash=AsyncMock(return_value=(None, "Model not found"))),
        AsyncMock(side_effect=selector),
    )

    model_data: Dict[str, Any] = {
        "model_name": "lora",
        "file_path": str(tmp_path / "lora.safetensors"),
        "source_platform": "huggingface",
        "source_url": "https://huggingface.co/user/repo",
    }
    ok, _ = await service.fetch_and_update_model(
        sha256="abc",
        file_path=model_data["file_path"],
        model_data=model_data,
        update_cache_func=AsyncMock(return_value=True),
    )
    assert ok is False
    assert civitai.calls == ["abc"]
    # A "Model not found" from the named provider does not mark deletion.
    assert model_data.get("civitai_deleted") is not True

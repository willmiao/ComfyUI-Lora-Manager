"""Tests for the external model-source handlers.

Covers linking (``set_hf_url``), file listing and downloads across the
registered platforms (Hugging Face / ModelScope).

Regression coverage for issue #1094: linking a model to HuggingFace must not
clear its CivitAI provenance or metadata, so both "View on CivitAI" and
"View on Hugging Face" can coexist.
"""

from __future__ import annotations

import json
import os
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest

from py.routes.handlers import model_source_handlers
from py.routes.handlers.model_source_handlers import ModelSourceHandler
from py.services.model_sources import ModelSourceError, SourceRef
from py.services.service_registry import ServiceRegistry
from py.utils.models import LoraMetadata
from py.utils.metadata_manager import MetadataManager


def _json_payload(response) -> dict[str, Any]:
    assert response.text is not None
    return json.loads(response.text)


class FakeRequest:
    def __init__(self, *, json_data=None, query=None):
        self._json_data = json_data or {}
        self.query = query or {}

    async def json(self):
        return self._json_data


def _sidecar_path(model_path) -> str:
    return f"{os.path.splitext(str(model_path))[0]}.metadata.json"


@pytest.fixture
def source_env(tmp_path, monkeypatch):
    """Point HF linking at *tmp_path* and stub the scanner cache write."""
    monkeypatch.setattr(model_source_handlers, "_find_matching_root", lambda _dir: str(tmp_path))
    cache_write = AsyncMock()
    monkeypatch.setattr(model_source_handlers, "_add_to_scanner_cache", cache_write)
    return {"root": tmp_path, "cache_write": cache_write}


async def _write_model(model_path, payload: dict[str, Any]) -> None:
    model_path.write_bytes(b"x" * 32)
    await MetadataManager.save_metadata(str(model_path), payload)


@pytest.mark.asyncio
async def test_set_hf_url_keeps_civitai_metadata_and_provenance(tmp_path, source_env):
    model_path = tmp_path / "civitai_model.safetensors"
    await _write_model(
        model_path,
        {
            "file_name": "civitai_model",
            "model_name": "CivitAI Model",
            "file_path": str(model_path),
            "size": 32,
            "modified": 1.0,
            "sha256": "a" * 64,
            "base_model": "SDXL 1.0",
            "preview_url": "",
            "from_civitai": True,
            "civitai": {"id": 111, "modelId": 222, "name": "v1", "trainedWords": []},
        },
    )

    response = await ModelSourceHandler().set_hf_url(
        FakeRequest(
            json_data={
                "file_path": str(model_path),
                "hf_url": "https://huggingface.co/user/repo",
            }
        )
    )

    assert response.status == 200
    assert _json_payload(response)["success"] is True

    saved = json.loads(open(_sidecar_path(model_path), encoding="utf-8").read())
    assert saved["hf_url"] == "https://huggingface.co/user/repo"
    # Linking HF must not erase the model's CivitAI provenance or data.
    assert saved["from_civitai"] is True
    assert saved["civitai"]["modelId"] == 222
    assert saved["civitai"]["id"] == 111

    source_env["cache_write"].assert_awaited_once()
    cached_metadata = source_env["cache_write"].await_args.args[1]
    assert cached_metadata["hf_url"] == "https://huggingface.co/user/repo"
    assert cached_metadata["from_civitai"] is True
    assert cached_metadata["civitai"]["modelId"] == 222


@pytest.mark.asyncio
async def test_set_hf_url_does_not_force_from_civitai_false(tmp_path, source_env):
    """A model without CivitAI data keeps its existing provenance flag."""
    model_path = tmp_path / "hf_only.safetensors"
    await _write_model(
        model_path,
        {
            "file_name": "hf_only",
            "model_name": "HF Only",
            "file_path": str(model_path),
            "size": 32,
            "modified": 1.0,
            "sha256": "b" * 64,
            "base_model": "Unknown",
            "preview_url": "",
            "from_civitai": True,
        },
    )

    response = await ModelSourceHandler().set_hf_url(
        FakeRequest(
            json_data={
                "file_path": str(model_path),
                "hf_url": "https://huggingface.co/user/repo",
            }
        )
    )

    assert response.status == 200
    saved = json.loads(open(_sidecar_path(model_path), encoding="utf-8").read())
    assert saved["hf_url"] == "https://huggingface.co/user/repo"
    assert saved["from_civitai"] is True


@pytest.mark.asyncio
async def test_set_hf_url_rejects_non_repo_url(tmp_path, source_env):
    model_path = tmp_path / "model.safetensors"
    await _write_model(
        model_path,
        {
            "file_name": "model",
            "model_name": "model",
            "file_path": str(model_path),
            "size": 32,
            "modified": 1.0,
            "sha256": "c" * 64,
            "base_model": "Unknown",
            "preview_url": "",
        },
    )

    response = await ModelSourceHandler().set_hf_url(
        FakeRequest(json_data={"file_path": str(model_path), "hf_url": "https://example.com/x"})
    )

    assert response.status == 400
    payload = _json_payload(response)
    assert payload["success"] is False
    source_env["cache_write"].assert_not_awaited()


# ---------------------------------------------------------------------------
# Multi-source linking (ModelScope / TensorArt)
# ---------------------------------------------------------------------------


async def _write_plain_model(model_path, sha: str = "d" * 64) -> None:
    await _write_model(
        model_path,
        {
            "file_name": "model",
            "model_name": "model",
            "file_path": str(model_path),
            "size": 32,
            "modified": 1.0,
            "sha256": sha,
            "base_model": "Unknown",
            "preview_url": "",
        },
    )


@pytest.mark.asyncio
async def test_set_hf_url_accepts_modelscope_and_stores_source_fields(tmp_path, source_env):
    model_path = tmp_path / "ms_model.safetensors"
    await _write_plain_model(model_path)

    response = await ModelSourceHandler().set_hf_url(
        FakeRequest(
            json_data={
                "file_path": str(model_path),
                "source_url": "https://modelscope.cn/models/jj3550945163/Krea-2-LORA",
            }
        )
    )

    assert response.status == 200
    payload = _json_payload(response)
    assert payload["source_platform"] == "modelscope"
    assert payload["source_url"] == "https://modelscope.cn/models/jj3550945163/Krea-2-LORA"

    saved = json.loads(open(_sidecar_path(model_path), encoding="utf-8").read())
    assert saved["source_platform"] == "modelscope"
    assert saved["source_url"] == "https://modelscope.cn/models/jj3550945163/Krea-2-LORA"
    # No stale Hugging Face alias for a ModelScope model.
    assert saved.get("hf_url", "") == ""

    cached_metadata = source_env["cache_write"].await_args.args[1]
    assert cached_metadata["source_platform"] == "modelscope"


@pytest.mark.asyncio
async def test_set_hf_url_accepts_tensorart_url(tmp_path, source_env):
    model_path = tmp_path / "ta_model.safetensors"
    await _write_plain_model(model_path, sha="e" * 64)

    response = await ModelSourceHandler().set_hf_url(
        FakeRequest(
            json_data={
                "file_path": str(model_path),
                "source_url": (
                    "https://tensor.art/models/827823520299086029/"
                    "Vivid-Impressions-Storybook-Sstyle-V1.0"
                ),
            }
        )
    )

    assert response.status == 200
    payload = _json_payload(response)
    assert payload["source_platform"] == "tensorart"
    # The canonical page URL is stored, without the slug.
    assert payload["source_url"] == "https://tensor.art/models/827823520299086029"


@pytest.mark.asyncio
async def test_set_hf_url_canonicalises_modelscope_subpage(tmp_path, source_env):
    model_path = tmp_path / "ms_sub.safetensors"
    await _write_plain_model(model_path, sha="f" * 64)

    response = await ModelSourceHandler().set_hf_url(
        FakeRequest(
            json_data={
                "file_path": str(model_path),
                "source_url": "https://modelscope.cn/models/user/repo/summary",
            }
        )
    )

    assert response.status == 200
    assert _json_payload(response)["source_url"] == "https://modelscope.cn/models/user/repo"


@pytest.mark.asyncio
async def test_set_hf_url_is_idempotent_for_modelscope(tmp_path, source_env):
    model_path = tmp_path / "ms_twice.safetensors"
    await _write_plain_model(model_path, sha="1" * 64)

    request = FakeRequest(
        json_data={
            "file_path": str(model_path),
            "source_url": "https://modelscope.cn/models/user/repo",
        }
    )
    await ModelSourceHandler().set_hf_url(request)
    await ModelSourceHandler().set_hf_url(request)

    # The second call short-circuits without rewriting the cache entry.
    assert source_env["cache_write"].await_count == 1


@pytest.mark.asyncio
async def test_set_hf_url_switching_source_clears_hf_alias(tmp_path, source_env):
    model_path = tmp_path / "switch.safetensors"
    await _write_plain_model(model_path, sha="2" * 64)

    await ModelSourceHandler().set_hf_url(
        FakeRequest(
            json_data={
                "file_path": str(model_path),
                "source_url": "https://huggingface.co/user/repo",
            }
        )
    )
    await ModelSourceHandler().set_hf_url(
        FakeRequest(
            json_data={
                "file_path": str(model_path),
                "source_url": "https://modelscope.cn/models/user/repo",
            }
        )
    )

    saved = json.loads(open(_sidecar_path(model_path), encoding="utf-8").read())
    assert saved["source_platform"] == "modelscope"
    assert saved.get("hf_url", "") == ""


@pytest.mark.asyncio
async def test_get_model_sources_lists_capabilities():
    response = await ModelSourceHandler().get_model_sources(FakeRequest())
    sources = _json_payload(response)

    by_platform = {s["platform"]: s for s in sources}
    assert set(by_platform) == {"huggingface", "modelscope", "tensorart"}
    assert by_platform["huggingface"]["supports_enrichment"] is True
    assert by_platform["modelscope"]["supports_enrichment"] is True
    # TensorArt is link-only: no accessible model card for the backend.
    assert by_platform["tensorart"]["supports_enrichment"] is False
    assert by_platform["modelscope"]["supports_download"] is True
    assert by_platform["modelscope"]["default_revision"] == "master"
    assert by_platform["tensorart"]["supports_download"] is False
    assert all(s["example_url"] for s in sources)


# ---------------------------------------------------------------------------
# File listing
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_model_source_files_returns_provider_result(monkeypatch):
    captured: dict = {}

    async def fake_list_files(self, source_id, revision=""):
        captured["source_id"] = source_id
        captured["revision"] = revision
        return [{"filename": "a.safetensors", "size": 10}]

    monkeypatch.setattr(
        "py.services.model_sources.modelscope.ModelScopeSource.list_files",
        fake_list_files,
    )

    response = await ModelSourceHandler().list_model_source_files(
        FakeRequest(
            query={
                "platform": "modelscope",
                "repo": "jj3550945163/Krea-2-LORA",
                "revision": "v1",
            }
        )
    )

    assert response.status == 200
    assert _json_payload(response) == [{"filename": "a.safetensors", "size": 10}]
    assert captured == {"source_id": "jj3550945163/Krea-2-LORA", "revision": "v1"}


@pytest.mark.asyncio
async def test_list_model_source_files_rejects_link_only_platform():
    response = await ModelSourceHandler().list_model_source_files(
        FakeRequest(query={"platform": "tensorart", "repo": "u/r"})
    )

    assert response.status == 400
    assert "does not support downloads" in _json_payload(response)["error"]


@pytest.mark.asyncio
async def test_list_model_source_files_rejects_unsafe_repo():
    for repo in ("noslash", "../etc/passwd", "u/.."):
        response = await ModelSourceHandler().list_model_source_files(
            FakeRequest(query={"platform": "modelscope", "repo": repo})
        )
        assert response.status == 400, repo
        assert "repo" in _json_payload(response)["error"]


@pytest.mark.asyncio
async def test_list_model_source_files_maps_missing_repo_to_404(monkeypatch):
    async def fake_list_files(self, source_id, revision=""):
        raise ModelSourceError(f"Repository '{source_id}' not found", status=404)

    monkeypatch.setattr(
        "py.services.model_sources.modelscope.ModelScopeSource.list_files",
        fake_list_files,
    )

    response = await ModelSourceHandler().list_model_source_files(
        FakeRequest(query={"platform": "modelscope", "repo": "u/r"})
    )

    assert response.status == 404
    assert "not found" in _json_payload(response)["error"]


@pytest.mark.asyncio
async def test_list_model_source_files_maps_transport_failure_to_502(monkeypatch):
    async def fake_list_files(self, source_id, revision=""):
        raise ModelSourceError("upstream exploded", status=502)

    monkeypatch.setattr(
        "py.services.model_sources.modelscope.ModelScopeSource.list_files",
        fake_list_files,
    )

    response = await ModelSourceHandler().list_model_source_files(
        FakeRequest(query={"platform": "modelscope", "repo": "u/r"})
    )

    assert response.status == 502


# ---------------------------------------------------------------------------
# Downloads
# ---------------------------------------------------------------------------


def _stub_download_backend(monkeypatch) -> dict:
    """Replace the downloader/settings plumbing with a recording stub."""
    captured: dict = {}

    async def fake_download_file(**kwargs):
        captured.update(kwargs)
        return True, kwargs["save_path"]

    class _Downloader:
        download_file = staticmethod(fake_download_file)

    async def fake_get_downloader():
        return _Downloader()

    class _Settings:
        def get(self, key, default=None):
            return default

    monkeypatch.setattr(model_source_handlers, "get_downloader", fake_get_downloader)
    monkeypatch.setattr(
        model_source_handlers, "get_settings_manager", lambda: _Settings()
    )
    return captured


@pytest.mark.asyncio
async def test_download_model_source_modelscope_uses_resolve_url(tmp_path, monkeypatch):
    captured = _stub_download_backend(monkeypatch)
    saved = AsyncMock()
    monkeypatch.setattr(model_source_handlers, "_save_source_metadata", saved)

    response = await ModelSourceHandler().download_model_source(
        FakeRequest(
            json_data={
                "platform": "modelscope",
                "repo": "jj3550945163/Krea-2-LORA",
                "filename": "Krea-2-LORA_c1-st1000.safetensors",
                "model_root": str(tmp_path),
            }
        )
    )

    assert response.status == 200
    assert captured["url"] == (
        "https://modelscope.cn/models/jj3550945163/Krea-2-LORA/resolve/master/"
        "Krea-2-LORA_c1-st1000.safetensors"
    )
    assert captured["save_path"] == str(tmp_path / "Krea-2-LORA_c1-st1000.safetensors")

    ref = saved.await_args.args[1]
    assert ref.platform == "modelscope"
    assert ref.source_id == "jj3550945163/Krea-2-LORA"
    assert ref.url == "https://modelscope.cn/models/jj3550945163/Krea-2-LORA"


@pytest.mark.asyncio
async def test_download_model_source_modelscope_default_paths(tmp_path, monkeypatch):
    captured = _stub_download_backend(monkeypatch)
    saved = AsyncMock()
    monkeypatch.setattr(model_source_handlers, "_save_source_metadata", saved)

    response = await ModelSourceHandler().download_model_source(
        FakeRequest(
            json_data={
                "platform": "modelscope",
                "repo": "owner/name",
                "filename": "nested/model.safetensors",
                "model_root": str(tmp_path),
                "use_default_paths": True,
            }
        )
    )

    assert response.status == 200
    # The site gets its own sub-directory, mirroring `huggingface/<owner>/<repo>`.
    assert captured["save_path"] == str(
        tmp_path / "modelscope" / "owner" / "name" / "model.safetensors"
    )


@pytest.mark.asyncio
async def test_download_model_source_defaults_to_huggingface(tmp_path, monkeypatch):
    """The legacy /api/lm/download-hf-model payload has no `platform` key."""
    captured = _stub_download_backend(monkeypatch)
    monkeypatch.setattr(model_source_handlers, "_save_source_metadata", AsyncMock())

    response = await ModelSourceHandler().download_model_source(
        FakeRequest(
            json_data={
                "repo": "user/repo",
                "filename": "f.safetensors",
                "revision": "main",
                "model_root": str(tmp_path),
            }
        )
    )

    assert response.status == 200
    assert captured["url"] == (
        "https://huggingface.co/user/repo/resolve/main/f.safetensors"
    )


@pytest.mark.asyncio
async def test_download_model_source_rejects_link_only_platform(tmp_path):
    response = await ModelSourceHandler().download_model_source(
        FakeRequest(
            json_data={
                "platform": "tensorart",
                "repo": "u/r",
                "filename": "f.safetensors",
                "model_root": str(tmp_path),
            }
        )
    )

    assert response.status == 400
    assert "does not support downloads" in _json_payload(response)["error"]


@pytest.mark.asyncio
async def test_download_model_source_rejects_unsafe_input(tmp_path, monkeypatch):
    _stub_download_backend(monkeypatch)

    cases = [
        ({"repo": "noslash", "filename": "f.safetensors"}, "repo format"),
        ({"repo": "u/r", "filename": "../../etc/passwd"}, "Invalid filename"),
        (
            {"repo": "u/r", "filename": "f.safetensors", "relative_path": "/abs"},
            "relative_path must not be absolute",
        ),
        (
            {"repo": "u/r", "filename": "f.safetensors", "relative_path": "../up"},
            "Invalid relative_path",
        ),
    ]
    for extra, expected in cases:
        response = await ModelSourceHandler().download_model_source(
            FakeRequest(
                json_data={
                    "platform": "modelscope",
                    "model_root": str(tmp_path),
                    **extra,
                }
            )
        )
        assert response.status == 400, extra
        assert expected in _json_payload(response)["error"], extra


@pytest.mark.asyncio
async def test_download_model_source_skips_existing_file(tmp_path, monkeypatch):
    captured = _stub_download_backend(monkeypatch)
    monkeypatch.setattr(model_source_handlers, "_save_source_metadata", AsyncMock())
    (tmp_path / "f.safetensors").write_bytes(b"already here")

    response = await ModelSourceHandler().download_model_source(
        FakeRequest(
            json_data={
                "platform": "modelscope",
                "repo": "u/r",
                "filename": "f.safetensors",
                "model_root": str(tmp_path),
            }
        )
    )

    assert response.status == 200
    assert "already exists" in _json_payload(response)["message"]
    assert captured == {}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("platform", "url", "expect_hf_alias"),
    [
        ("modelscope", "https://modelscope.cn/models/u/r", False),
        ("huggingface", "https://huggingface.co/u/r", True),
    ],
)
async def test_save_source_metadata_writes_platform_fields(
    tmp_path, monkeypatch, platform, url, expect_hf_alias
):
    """A download's sidecar must record its own platform (and no stale HF alias)."""
    model_path = tmp_path / "downloaded.safetensors"
    model_path.write_bytes(b"x" * 32)

    metadata = LoraMetadata(
        file_name="downloaded",
        model_name="Downloaded",
        file_path=str(model_path),
        size=32,
        modified=1.0,
        sha256="a" * 64,
        base_model="SDXL 1.0",
        preview_url="",
    )
    monkeypatch.setattr(
        model_source_handlers.MetadataManager,
        "create_default_metadata",
        AsyncMock(return_value=metadata),
    )
    scanner = SimpleNamespace(add_model_to_cache=AsyncMock())
    monkeypatch.setattr(
        ServiceRegistry, "get_lora_scanner", AsyncMock(return_value=scanner)
    )
    monkeypatch.setattr(
        model_source_handlers, "_infer_model_type", lambda _root: (LoraMetadata, "get_lora_scanner")
    )

    ref = SourceRef(platform=platform, source_id="u/r", url=url)
    await model_source_handlers._save_source_metadata(str(model_path), ref, str(tmp_path))

    saved = json.loads(open(_sidecar_path(model_path), encoding="utf-8").read())
    assert saved["source_platform"] == platform
    assert saved["source_url"] == url
    assert bool(saved.get("hf_url", "")) is expect_hf_alias

    cached = scanner.add_model_to_cache.await_args.args[0]
    assert cached["source_platform"] == platform
    assert cached["source_url"] == url

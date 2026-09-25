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
    assert set(by_platform) == {
        "huggingface",
        "modelscope",
        "modelscope-ai",
        "tensorart",
    }
    assert by_platform["huggingface"]["supports_enrichment"] is True
    assert by_platform["modelscope"]["supports_enrichment"] is True
    # TensorArt is link-only: no accessible model card for the backend.
    assert by_platform["tensorart"]["supports_enrichment"] is False
    assert by_platform["modelscope"]["supports_download"] is True
    assert by_platform["modelscope"]["default_revision"] == "master"
    assert by_platform["tensorart"]["supports_download"] is False
    # The international deployment is advertised with its own example URL, so
    # the Link dialog names the host a user actually has open.
    assert by_platform["modelscope-ai"]["supports_download"] is True
    assert by_platform["modelscope-ai"]["example_url"].startswith(
        "https://www.modelscope.ai/"
    )
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
async def test_download_model_source_modelscope_intl_uses_its_own_host(
    tmp_path, monkeypatch
):
    """`.ai` is a separate catalogue, so the download must not go to `.cn`."""
    captured = _stub_download_backend(monkeypatch)
    saved = AsyncMock()
    monkeypatch.setattr(model_source_handlers, "_save_source_metadata", saved)

    response = await ModelSourceHandler().download_model_source(
        FakeRequest(
            json_data={
                "platform": "modelscope-ai",
                "repo": "referall13/EM1",
                "filename": "EM1_c1-st1000.safetensors",
                "model_root": str(tmp_path),
                "use_default_paths": True,
            }
        )
    )

    assert response.status == 200
    assert captured["url"] == (
        "https://www.modelscope.ai/models/referall13/EM1/resolve/master/"
        "EM1_c1-st1000.safetensors"
    )
    # Its own default directory, so the same owner/name on both deployments
    # cannot overwrite each other.
    assert captured["save_path"] == str(
        tmp_path / "modelscope-ai" / "referall13" / "EM1" / "EM1_c1-st1000.safetensors"
    )

    ref = saved.await_args.args[1]
    assert ref.platform == "modelscope-ai"
    assert ref.source_id == "referall13/EM1"
    assert ref.url == "https://www.modelscope.ai/models/referall13/EM1"


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
    scanner = SimpleNamespace(
        # A real scanner owns metadata creation (see the lazy-hash test below).
        _create_default_metadata=AsyncMock(return_value=metadata),
        add_model_to_cache=AsyncMock(),
    )
    monkeypatch.setattr(
        ServiceRegistry, "get_lora_scanner", AsyncMock(return_value=scanner)
    )
    monkeypatch.setattr(
        model_source_handlers, "_infer_model_type", lambda _root: (LoraMetadata, "get_lora_scanner")
    )
    hydrate = AsyncMock()
    monkeypatch.setattr(model_source_handlers, "hydrate_from_source", hydrate)

    ref = SourceRef(platform=platform, source_id="u/r", url=url)
    await model_source_handlers._save_source_metadata(str(model_path), ref, str(tmp_path))

    saved = json.loads(open(_sidecar_path(model_path), encoding="utf-8").read())
    assert saved["source_platform"] == platform
    assert saved["source_url"] == url
    assert bool(saved.get("hf_url", "")) is expect_hf_alias

    assert scanner._create_default_metadata.await_args.args == (str(model_path),)

    cached = scanner.add_model_to_cache.await_args.args[0]
    assert cached["source_platform"] == platform
    assert cached["source_url"] == url

    # The site's own API is consulted last, so the scanner-cache refresh it
    # performs lands on the entry created above.
    assert hydrate.await_args.args == (str(model_path),)
    assert hydrate.await_args.kwargs["ref"] == ref


@pytest.mark.asyncio
async def test_checkpoint_download_defers_the_hash(tmp_path, monkeypatch):
    """A multi-GB checkpoint must not be hashed inside the download request.

    ``CheckpointScanner`` records ``hash_status="pending"`` and lets the hash be
    computed on demand; going through the generic
    ``MetadataManager.create_default_metadata`` would read the whole file before
    the download response could return, which is exactly the pause this code
    path is supposed to avoid.
    """
    from py.services.checkpoint_scanner import CheckpointScanner
    from py.utils.models import CheckpointMetadata

    model_path = tmp_path / "big_checkpoint.safetensors"
    model_path.write_bytes(b"stub")

    real_scanner = CheckpointScanner()
    scanner = SimpleNamespace(
        _create_default_metadata=real_scanner._create_default_metadata,
        add_model_to_cache=AsyncMock(),
    )
    monkeypatch.setattr(
        ServiceRegistry, "get_checkpoint_scanner", AsyncMock(return_value=scanner)
    )
    monkeypatch.setattr(
        model_source_handlers,
        "_infer_model_type",
        lambda _root: (CheckpointMetadata, "get_checkpoint_scanner"),
    )
    generic = AsyncMock(
        # Stands in for the eager helper: if the handler reaches for it, the
        # sidecar ends up hashed and the assertions below say so plainly.
        return_value=LoraMetadata(
            file_name="big_checkpoint",
            model_name="big_checkpoint",
            file_path=str(model_path),
            size=4,
            modified=1.0,
            sha256="d" * 64,
            base_model="Unknown",
            preview_url="",
        )
    )
    monkeypatch.setattr(
        model_source_handlers.MetadataManager, "create_default_metadata", generic
    )
    monkeypatch.setattr(model_source_handlers, "hydrate_from_source", AsyncMock())

    ref = SourceRef(
        platform="huggingface",
        source_id="u/r",
        url="https://huggingface.co/u/r",
    )
    await model_source_handlers._save_source_metadata(str(model_path), ref, str(tmp_path))

    saved = json.loads(open(_sidecar_path(model_path), encoding="utf-8").read())
    assert saved["sha256"] == ""
    assert saved["hash_status"] == "pending"
    assert saved["from_civitai"] is False
    # The download link is still recorded on top of the deferred hash.
    assert saved["source_platform"] == "huggingface"
    assert saved["source_url"] == "https://huggingface.co/u/r"

    # The scanner cache must carry the pending state too, or the cache fill
    # would compute the hash after all.
    cached = scanner.add_model_to_cache.await_args.args[0]
    assert cached["hash_status"] == "pending"
    assert cached["sha256"] == ""

    generic.assert_not_awaited()


# ---------------------------------------------------------------------------
# Post-transfer phase reporting
# ---------------------------------------------------------------------------


def _stub_hydration_pipeline(tmp_path, monkeypatch):
    """Wire `_save_source_metadata`'s collaborators and record call order."""
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
    monkeypatch.setattr(
        ServiceRegistry,
        "get_lora_scanner",
        AsyncMock(return_value=SimpleNamespace(add_model_to_cache=AsyncMock())),
    )
    monkeypatch.setattr(
        model_source_handlers,
        "_infer_model_type",
        lambda _root: (LoraMetadata, "get_lora_scanner"),
    )

    events: list = []

    async def fake_broadcast(download_id, data):
        events.append(("broadcast", data["stage"], data, download_id))

    async def fake_hydrate(*_args, **_kwargs):
        events.append(("hydrate", None, None, None))

    monkeypatch.setattr(
        model_source_handlers.ws_manager, "broadcast_download_progress", fake_broadcast
    )
    monkeypatch.setattr(model_source_handlers, "hydrate_from_source", fake_hydrate)
    return model_path, events


@pytest.mark.asyncio
async def test_save_source_metadata_reports_post_transfer_stages(tmp_path, monkeypatch):
    """The byte counter stops before indexing and the site fetch, so the UI has
    to be told what is still running — otherwise the bar looks stuck."""
    model_path, events = _stub_hydration_pipeline(tmp_path, monkeypatch)

    ref = SourceRef(
        platform="modelscope", source_id="u/r", url="https://modelscope.cn/models/u/r"
    )
    await model_source_handlers._save_source_metadata(
        str(model_path), ref, str(tmp_path), download_id="dl-1"
    )

    # Each stage is announced *before* its work starts, so the label is never
    # describing something that already finished.
    assert [event[:2] for event in events] == [
        ("broadcast", "indexing"),
        ("broadcast", "source"),
        ("hydrate", None),
    ]
    for kind, stage, data, download_id in events:
        if kind != "broadcast":
            continue
        assert download_id == "dl-1"
        assert data["status"] == "metadata"
        assert data["progress"] == 100
        assert data["platform"] == "modelscope"


@pytest.mark.asyncio
async def test_save_source_metadata_is_silent_without_a_watcher(tmp_path, monkeypatch):
    """No `download_id` means no UI is watching; nothing should be broadcast."""
    model_path, events = _stub_hydration_pipeline(tmp_path, monkeypatch)

    ref = SourceRef(
        platform="modelscope", source_id="u/r", url="https://modelscope.cn/models/u/r"
    )
    await model_source_handlers._save_source_metadata(str(model_path), ref, str(tmp_path))

    assert events == [("hydrate", None, None, None)]


@pytest.mark.asyncio
async def test_report_phase_never_breaks_a_download(monkeypatch):
    """Progress reporting is cosmetic; a dead socket must not fail the file."""
    monkeypatch.setattr(
        model_source_handlers.ws_manager,
        "broadcast_download_progress",
        AsyncMock(side_effect=RuntimeError("socket gone")),
    )

    await model_source_handlers._report_phase("dl-1", "source", "modelscope")


@pytest.mark.asyncio
async def test_download_passes_its_watch_id_into_metadata_work(tmp_path, monkeypatch):
    """The stages are only visible if the handler hands its id down."""
    _stub_download_backend(monkeypatch)
    saved = AsyncMock()
    monkeypatch.setattr(model_source_handlers, "_save_source_metadata", saved)

    await ModelSourceHandler().download_model_source(
        FakeRequest(
            json_data={
                "platform": "modelscope",
                "repo": "owner/name",
                "filename": "model.safetensors",
                "model_root": str(tmp_path),
                "download_id": "dl-42",
            }
        )
    )

    assert saved.await_args.kwargs["download_id"] == "dl-42"


@pytest.mark.asyncio
async def test_skipped_download_still_reports_the_site_stage(tmp_path, monkeypatch):
    """An already-present file is hydrated too, so it needs the same signal."""
    _stub_download_backend(monkeypatch)
    hydrate = AsyncMock()
    monkeypatch.setattr(model_source_handlers, "hydrate_from_source", hydrate)
    broadcast = AsyncMock()
    monkeypatch.setattr(
        model_source_handlers.ws_manager, "broadcast_download_progress", broadcast
    )

    existing = tmp_path / "model.safetensors"
    existing.write_bytes(b"x" * 32)

    await ModelSourceHandler().download_model_source(
        FakeRequest(
            json_data={
                "platform": "modelscope",
                "repo": "owner/name",
                "filename": "model.safetensors",
                "model_root": str(tmp_path),
                "download_id": "dl-7",
            }
        )
    )

    assert broadcast.await_args.args[1]["stage"] == "source"


@pytest.mark.asyncio
async def test_save_source_metadata_survives_a_hydration_failure(tmp_path, monkeypatch):
    """Metadata hydration must never be able to fail a completed download."""
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
    monkeypatch.setattr(
        ServiceRegistry,
        "get_lora_scanner",
        AsyncMock(return_value=SimpleNamespace(add_model_to_cache=AsyncMock())),
    )
    monkeypatch.setattr(
        model_source_handlers, "_infer_model_type", lambda _root: (LoraMetadata, "get_lora_scanner")
    )
    monkeypatch.setattr(
        model_source_handlers,
        "hydrate_from_source",
        AsyncMock(side_effect=RuntimeError("site down")),
    )

    ref = SourceRef(
        platform="modelscope", source_id="u/r", url="https://modelscope.cn/models/u/r"
    )
    await model_source_handlers._save_source_metadata(str(model_path), ref, str(tmp_path))

    saved = json.loads(open(_sidecar_path(model_path), encoding="utf-8").read())
    assert saved["source_platform"] == "modelscope"


@pytest.mark.asyncio
async def test_downloading_an_existing_file_still_hydrates(tmp_path, monkeypatch):
    """A pre-existing file may still be missing the site's metadata."""
    _stub_download_backend(monkeypatch)
    saved = AsyncMock()
    monkeypatch.setattr(model_source_handlers, "_save_source_metadata", saved)
    hydrate = AsyncMock()
    monkeypatch.setattr(model_source_handlers, "hydrate_from_source", hydrate)

    existing = tmp_path / "model.safetensors"
    existing.write_bytes(b"x" * 32)

    response = await ModelSourceHandler().download_model_source(
        FakeRequest(
            json_data={
                "platform": "modelscope",
                "repo": "owner/name",
                "filename": "model.safetensors",
                "model_root": str(tmp_path),
            }
        )
    )

    assert response.status == 200
    saved.assert_not_awaited()
    assert hydrate.await_args.args == (str(existing),)
    assert hydrate.await_args.kwargs["ref"].source_id == "owner/name"


# ---------------------------------------------------------------------------
# Download-time metadata hydration (end to end)
# ---------------------------------------------------------------------------


def _modelscope_card_payload() -> dict:
    """A trimmed ModelScope model-detail response for the hydration test."""

    return {
        "Code": 200,
        "Data": {
            "Name": "Krea-2-LORA",
            "ChineseName": "krea脸模",
            "AigcType": "LoRA",
            "Description": "权重0.5-1.2。配合《风格滤镜》lora一起使用。",
            "BaseModel": ["krea/Krea-2-Turbo"],
            "OfficialTags": [{"Tag": "photography"}, {"Tag": "woman"}],
            "ModelInfos": {
                "safetensor": {
                    "files": [
                        {
                            "name": "Krea-2-LORA_c1-st1000.safetensors",
                            "sha256": "a" * 64,
                        }
                    ]
                }
            },
            "MuseInfo": {
                "versions": [
                    {
                        "stats": {"fileList": ["Krea-2-LORA_c1-st1000.safetensors"]},
                        "modelVersion": {
                            "showName": "c1-st1000",
                            "triggerWords": '["kreaface","kreamodel"]',
                            "id": 1002,
                            "modelId": 555,
                        },
                        "coverImages": [
                            {"url": "https://resources.modelscope.cn/cover-images/b.png"},
                            {"url": "https://resources.modelscope.cn/cover-images/c.png"},
                        ],
                    }
                ]
            },
        },
    }


@pytest.mark.asyncio
async def test_download_hydrates_the_card_from_the_site(tmp_path, monkeypatch):
    """A ModelScope download must land with a populated model card.

    Only the network, the scanner and the file transfer are faked, so this
    exercises the real handler, the real `ModelScopeSource` and the real
    post-processor together. Breaking the wiring between them fails here even
    when each half still passes its own unit tests.
    """
    model_path = tmp_path / "Krea-2-LORA_c1-st1000.safetensors"

    async def fake_download_file(**kwargs):
        with open(kwargs["save_path"], "wb") as handle:
            handle.write(b"stub")
        return True, kwargs["save_path"]

    class _Downloader:
        download_file = staticmethod(fake_download_file)

    class _Settings:
        def get(self, key, default=None):
            return default

    async def fake_get_downloader():
        return _Downloader()

    monkeypatch.setattr(model_source_handlers, "get_downloader", fake_get_downloader)
    monkeypatch.setattr(
        model_source_handlers, "get_settings_manager", lambda: _Settings()
    )
    monkeypatch.setattr(
        model_source_handlers,
        "_infer_model_type",
        lambda _root: (LoraMetadata, "get_lora_scanner"),
    )

    scanner = SimpleNamespace(
        get_cached_data=AsyncMock(
            return_value=SimpleNamespace(raw_data=[{"file_path": str(model_path)}])
        ),
        add_model_to_cache=AsyncMock(),
        update_single_model_cache=AsyncMock(),
    )
    monkeypatch.setattr(
        ServiceRegistry, "get_lora_scanner", AsyncMock(return_value=scanner)
    )

    async def fake_fetch_text(url, **_kwargs):
        return "# Krea-2-LORA\n\n权重0.5-1.2。"

    async def fake_fetch_json(url, **_kwargs):
        return 200, _modelscope_card_payload()

    monkeypatch.setattr(
        "py.services.model_sources.modelscope.fetch_text", fake_fetch_text
    )
    monkeypatch.setattr(
        "py.services.model_sources.modelscope.fetch_json", fake_fetch_json
    )
    monkeypatch.setattr(
        "py.metadata_ops.list_base_models", AsyncMock(return_value=["Krea 2"])
    )
    monkeypatch.setattr(
        "py.metadata_ops.download_preview",
        AsyncMock(return_value=str(tmp_path / "preview.webp")),
    )

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
    saved = json.loads(open(_sidecar_path(model_path), encoding="utf-8").read())

    # The download's own provenance is unchanged.
    assert saved["source_platform"] == "modelscope"
    assert saved["source_url"] == "https://modelscope.cn/models/jj3550945163/Krea-2-LORA"
    assert saved["from_civitai"] is False

    # The site's published metadata, with no LLM involved.
    assert saved["model_name"] == "Krea-2-LORA"
    assert saved["base_model"] == "Krea 2"
    assert saved["tags"] == ["photography", "woman"]
    assert saved["civitai"]["name"] == "c1-st1000"
    assert saved["civitai"]["trainedWords"] == ["kreaface", "kreamodel"]
    assert saved["civitai"]["description"] == "权重0.5-1.2。配合《风格滤镜》lora一起使用。"
    assert [img["url"] for img in saved["civitai"]["images"]] == [
        "https://resources.modelscope.cn/cover-images/b.png",
        "https://resources.modelscope.cn/cover-images/c.png",
    ]
    assert saved["preview_url"] == str(tmp_path / "preview.webp")
    assert saved["usage_tips"] == (
        '{"strength_min": 0.5, "strength_max": 1.2, "strength_range": "0.5-1.2"}'
    )
    assert saved["metadata_source"] == "source:modelscope"
    # The site-native identity ids are persisted for version grouping.
    assert saved["source_model_id"] == "555"
    assert saved["source_version_id"] == "1002"
    # No provider answered, so claiming an AI enrichment would be a lie.
    assert "llm_enriched_at" not in saved

    # The enriched card reaches the scanner cache, not just the file.
    assert scanner.update_single_model_cache.await_count == 1
    cached = scanner.update_single_model_cache.await_args.args[2]
    assert cached["model_name"] == "Krea-2-LORA"
    assert cached["source_model_id"] == "555"


@pytest.mark.asyncio
async def test_download_model_source_sends_hf_token_as_custom_headers(
    tmp_path, monkeypatch
):
    """A gated/private HF repo needs the configured token on the download."""
    captured = _stub_download_backend(monkeypatch)
    monkeypatch.setattr(model_source_handlers, "_save_source_metadata", AsyncMock())
    monkeypatch.setattr(
        "py.services.model_sources.huggingface._hf_token", lambda: "hf_secret"
    )

    response = await ModelSourceHandler().download_model_source(
        FakeRequest(
            json_data={
                "platform": "huggingface",
                "repo": "user/repo",
                "filename": "f.safetensors",
                "model_root": str(tmp_path),
            }
        )
    )

    assert response.status == 200
    assert captured["custom_headers"] == {"Authorization": "Bearer hf_secret"}


@pytest.mark.asyncio
async def test_download_model_source_sends_no_headers_without_hf_token(
    tmp_path, monkeypatch
):
    captured = _stub_download_backend(monkeypatch)
    monkeypatch.setattr(model_source_handlers, "_save_source_metadata", AsyncMock())
    monkeypatch.setattr(
        "py.services.model_sources.huggingface._hf_token", lambda: ""
    )

    response = await ModelSourceHandler().download_model_source(
        FakeRequest(
            json_data={
                "platform": "huggingface",
                "repo": "user/repo",
                "filename": "f.safetensors",
                "model_root": str(tmp_path),
            }
        )
    )

    assert response.status == 200
    assert captured["custom_headers"] is None

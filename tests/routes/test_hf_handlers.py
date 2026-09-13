"""Tests for the HuggingFace link handler (``set_hf_url``).

Regression coverage for issue #1094: linking a model to HuggingFace must not
clear its CivitAI provenance or metadata, so both "View on CivitAI" and
"View on Hugging Face" can coexist.
"""

from __future__ import annotations

import json
import os
from typing import Any
from unittest.mock import AsyncMock

import pytest

from py.routes.handlers import hf_handlers
from py.routes.handlers.hf_handlers import HfHandler
from py.utils.metadata_manager import MetadataManager


def _json_payload(response) -> dict[str, Any]:
    assert response.text is not None
    return json.loads(response.text)


class FakeRequest:
    def __init__(self, *, json_data=None):
        self._json_data = json_data or {}

    async def json(self):
        return self._json_data


def _sidecar_path(model_path) -> str:
    return f"{os.path.splitext(str(model_path))[0]}.metadata.json"


@pytest.fixture
def hf_env(tmp_path, monkeypatch):
    """Point HF linking at *tmp_path* and stub the scanner cache write."""
    monkeypatch.setattr(hf_handlers, "_find_matching_root", lambda _dir: str(tmp_path))
    cache_write = AsyncMock()
    monkeypatch.setattr(hf_handlers, "_add_to_scanner_cache", cache_write)
    return {"root": tmp_path, "cache_write": cache_write}


async def _write_model(model_path, payload: dict[str, Any]) -> None:
    model_path.write_bytes(b"x" * 32)
    await MetadataManager.save_metadata(str(model_path), payload)


@pytest.mark.asyncio
async def test_set_hf_url_keeps_civitai_metadata_and_provenance(tmp_path, hf_env):
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

    response = await HfHandler().set_hf_url(
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

    hf_env["cache_write"].assert_awaited_once()
    cached_metadata = hf_env["cache_write"].await_args.args[1]
    assert cached_metadata["hf_url"] == "https://huggingface.co/user/repo"
    assert cached_metadata["from_civitai"] is True
    assert cached_metadata["civitai"]["modelId"] == 222


@pytest.mark.asyncio
async def test_set_hf_url_does_not_force_from_civitai_false(tmp_path, hf_env):
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

    response = await HfHandler().set_hf_url(
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
async def test_set_hf_url_rejects_non_repo_url(tmp_path, hf_env):
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

    response = await HfHandler().set_hf_url(
        FakeRequest(json_data={"file_path": str(model_path), "hf_url": "https://example.com/x"})
    )

    assert response.status == 400
    payload = _json_payload(response)
    assert payload["success"] is False
    hf_env["cache_write"].assert_not_awaited()


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
async def test_set_hf_url_accepts_modelscope_and_stores_source_fields(tmp_path, hf_env):
    model_path = tmp_path / "ms_model.safetensors"
    await _write_plain_model(model_path)

    response = await HfHandler().set_hf_url(
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

    cached_metadata = hf_env["cache_write"].await_args.args[1]
    assert cached_metadata["source_platform"] == "modelscope"


@pytest.mark.asyncio
async def test_set_hf_url_accepts_tensorart_url(tmp_path, hf_env):
    model_path = tmp_path / "ta_model.safetensors"
    await _write_plain_model(model_path, sha="e" * 64)

    response = await HfHandler().set_hf_url(
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
async def test_set_hf_url_canonicalises_modelscope_subpage(tmp_path, hf_env):
    model_path = tmp_path / "ms_sub.safetensors"
    await _write_plain_model(model_path, sha="f" * 64)

    response = await HfHandler().set_hf_url(
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
async def test_set_hf_url_is_idempotent_for_modelscope(tmp_path, hf_env):
    model_path = tmp_path / "ms_twice.safetensors"
    await _write_plain_model(model_path, sha="1" * 64)

    request = FakeRequest(
        json_data={
            "file_path": str(model_path),
            "source_url": "https://modelscope.cn/models/user/repo",
        }
    )
    await HfHandler().set_hf_url(request)
    await HfHandler().set_hf_url(request)

    # The second call short-circuits without rewriting the cache entry.
    assert hf_env["cache_write"].await_count == 1


@pytest.mark.asyncio
async def test_set_hf_url_switching_source_clears_hf_alias(tmp_path, hf_env):
    model_path = tmp_path / "switch.safetensors"
    await _write_plain_model(model_path, sha="2" * 64)

    await HfHandler().set_hf_url(
        FakeRequest(
            json_data={
                "file_path": str(model_path),
                "source_url": "https://huggingface.co/user/repo",
            }
        )
    )
    await HfHandler().set_hf_url(
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
    response = await HfHandler().get_model_sources(FakeRequest())
    sources = _json_payload(response)

    by_platform = {s["platform"]: s for s in sources}
    assert set(by_platform) == {"huggingface", "modelscope", "tensorart"}
    assert by_platform["huggingface"]["supports_enrichment"] is True
    assert by_platform["modelscope"]["supports_enrichment"] is True
    # TensorArt is link-only: no accessible model card for the backend.
    assert by_platform["tensorart"]["supports_enrichment"] is False
    assert by_platform["modelscope"]["supports_download"] is False
    assert all(s["example_url"] for s in sources)

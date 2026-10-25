import copy
import logging
from typing import Any, Dict
from unittest.mock import AsyncMock

import pytest

from py.services import civarchive_client as civarchive_client_module
from py.services.civarchive_client import CivArchiveClient
from py.services.errors import RateLimitError
from py.services.model_metadata_provider import ModelMetadataProviderManager


class DummyDownloader:
    def __init__(self):
        self.calls = []

    async def make_request(self, method, url, use_auth=False, **kwargs):
        self.calls.append({"method": method, "url": url, "params": kwargs.get("params")})
        return True, {}


@pytest.fixture(autouse=True)
def reset_singletons():
    CivArchiveClient._instance = None
    ModelMetadataProviderManager._instance = None
    yield
    CivArchiveClient._instance = None
    ModelMetadataProviderManager._instance = None


@pytest.fixture
def downloader(monkeypatch):
    instance = DummyDownloader()
    monkeypatch.setattr(civarchive_client_module, "get_downloader", AsyncMock(return_value=instance))
    return instance


def _base_civarchive_payload(version_id=1976567, *, trigger="mxpln", nsfw_level=31) -> Dict[str, Any]:
    version_name = "v2.0" if version_id != 1976567 else "v1.0"
    file_sha = "e2b7a280d6539556f23f380b3f71e4e22bc4524445c4c96526e117c6005c6ad3"
    return {
        "data": {
            "id": 1746460,
            "name": "Mixplin Style [Illustrious]",
            "type": "LORA",
            "description": "description",
            "is_nsfw": True,
            "nsfw_level": nsfw_level,
            "tags": ["art", "style"],
            "creator_username": "Ty_Lee",
            "creator_name": "Ty_Lee",
            "creator_url": "/users/Ty_Lee",
            "version": {
                "id": version_id,
                "modelId": 1746460,
                "name": version_name,
                "baseModel": "Illustrious",
                "description": "version description",
                "downloadCount": 437,
                "ratingCount": 0,
                "rating": 0,
                "nsfw_level": nsfw_level,
                "trigger": [trigger],
                "files": [
                    {
                        "id": 1874043,
                        "name": "mxpln-illustrious-ty_lee.safetensors",
                        "type": "Model",
                        "sizeKB": 223124.37109375,
                        "downloadUrl": "https://civitai.com/api/download/models/1976567",
                        "sha256": file_sha,
                        "is_primary": False,
                        "mirrors": [
                            {
                                "filename": "mxpln-illustrious-ty_lee.safetensors",
                                "url": "https://civitai.com/api/download/models/1976567",
                                "deletedAt": None,
                            }
                        ],
                    }
                ],
                "images": [
                    {
                        "id": 86403595,
                        "url": "https://img.genur.art/example.png",
                        "nsfwLevel": 1,
                    }
                ],
            },
            "versions": [
                {"id": 2042594, "name": "v2.0"},
                {"id": 1976567, "name": "v1.0"},
            ],
        }
    }


async def test_get_model_by_hash_transforms_payload(downloader):
    payload = _base_civarchive_payload()

    async def fake_make_request(method, url, use_auth=False, **kwargs):
        downloader.calls.append({"url": url, "params": kwargs.get("params")})
        if url.endswith("/sha256/abc"):
            return True, copy.deepcopy(payload)
        return False, "unexpected"

    downloader.make_request = fake_make_request

    client = await CivArchiveClient.get_instance()

    result, error = await client.get_model_by_hash("abc")

    assert error is None
    assert result is not None
    assert result["id"] == 1976567
    assert result["nsfwLevel"] == 31
    assert result["trainedWords"] == ["mxpln"]
    assert result["stats"] == {"downloadCount": 437, "ratingCount": 0, "rating": 0}
    assert result["model"]["name"] == "Mixplin Style [Illustrious]"
    assert result["model"]["nsfw"] is True
    assert result["creator"]["username"] == "Ty_Lee"
    assert result["creator"]["image"] == ""
    file_meta = result["files"][0]
    assert file_meta["hashes"]["SHA256"] == "E2B7A280D6539556F23F380B3F71E4E22BC4524445C4C96526E117C6005C6AD3"
    assert file_meta["mirrors"][0]["url"] == "https://civitai.com/api/download/models/1976567"
    assert file_meta["primary"] is True
    assert result["source"] == "civarchive"
    assert result["images"][0]["url"] == "https://img.genur.art/example.png"


async def test_get_model_versions_fetches_each_version(downloader):
    base_url = "https://civarchive.com/api/models/1746460"
    base_payload = _base_civarchive_payload(version_id=2042594, trigger="mxpln-new", nsfw_level=5)
    other_payload = _base_civarchive_payload()

    responses: Dict[Any, Dict[str, Any]] = {
        (base_url, None): base_payload,
        (base_url, (("modelVersionId", "2042594"),)): base_payload,
        (base_url, (("modelVersionId", "1976567"),)): other_payload,
    }

    async def fake_make_request(method, url, use_auth=False, **kwargs):
        params = kwargs.get("params")
        key = (url, tuple(sorted((params or {}).items())) if params else None)
        downloader.calls.append({"url": url, "params": params})
        if key in responses:
            return True, copy.deepcopy(responses[key])
        return False, "unexpected"

    downloader.make_request = fake_make_request

    client = await CivArchiveClient.get_instance()

    result = await client.get_model_versions("1746460")

    assert result is not None
    assert result["name"] == "Mixplin Style [Illustrious]"
    assert result["type"] == "LORA"
    versions = result["modelVersions"]
    assert [version["id"] for version in versions] == [2042594, 1976567]
    assert versions[0]["trainedWords"] == ["mxpln-new"]
    assert versions[1]["trainedWords"] == ["mxpln"]
    assert versions[0]["nsfwLevel"] == 5
    assert versions[1]["nsfwLevel"] == 31
    assert any(call["params"] == {"modelVersionId": "2042594"} for call in downloader.calls)
    assert any(call["params"] == {"modelVersionId": "1976567"} for call in downloader.calls)


async def test_get_model_version_redirects_to_actual_model_id(downloader):
    first_payload = _base_civarchive_payload()
    first_payload["data"]["version"]["modelId"] = 222

    base_url_request = "https://civarchive.com/api/models/111"
    redirected_url_request = "https://civarchive.com/api/models/222"

    async def fake_make_request(method, url, use_auth=False, **kwargs):
        downloader.calls.append({"url": url, "params": kwargs.get("params")})
        params = kwargs.get("params") or {}
        if url == base_url_request:
            return True, copy.deepcopy(first_payload)
        if url == redirected_url_request and params.get("modelVersionId") == "1976567":
            return True, copy.deepcopy(_base_civarchive_payload())
        return False, "unexpected"

    downloader.make_request = fake_make_request

    client = await CivArchiveClient.get_instance()

    result = await client.get_model_version(model_id=111, version_id=1976567)

    assert result is not None
    assert result["model"]["name"] == "Mixplin Style [Illustrious]"
    assert len(downloader.calls) == 2
    assert downloader.calls[1]["url"] == redirected_url_request


async def test_get_model_by_hash_uses_file_fallback(downloader, monkeypatch):
    file_only_payload = {
        "data": {
            "files": [
                {
                    "model_id": 1746460,
                    "model_version_id": 1976567,
                    "source": "civitai",
                }
            ]
        }
    }

    version_payload = _base_civarchive_payload()

    async def fake_make_request(method, url, use_auth=False, **kwargs):
        downloader.calls.append({"url": url, "params": kwargs.get("params")})
        if "/sha256/" in url:
            return True, copy.deepcopy(file_only_payload)
        if "/models/1746460" in url:
            return True, copy.deepcopy(version_payload)
        return False, "unexpected"

    downloader.make_request = fake_make_request

    client = await CivArchiveClient.get_instance()

    result, error = await client.get_model_by_hash(
        "e2b7a280d6539556f23f380b3f71e4e22bc4524445c4c96526e117c6005c6ad3"
    )

    assert error is None
    assert result is not None
    assert result["id"] == 1976567
    assert result["model"]["name"] == "Mixplin Style [Illustrious]"
    assert any("/models/1746460" in call["url"] for call in downloader.calls)


async def test_get_model_by_hash_skips_foreign_ecosystem_file_entries(downloader):
    """File entries from a foreign ecosystem (e.g. civision) carry IDs from a
    different ID space; resolving them would hit an unrelated CivitAI model."""
    file_only_payload = {
        "data": {
            "files": [
                {
                    "filename": "Kiara-Krea_c1-st4000.safetensors",
                    "url": "https://www.modelscope.ai/models/arbinshado/Kiara-Krea/files",
                    "source": "civision",
                    "model_id": "455108",
                    "model_version_id": "130022",
                }
            ]
        }
    }

    async def fake_make_request(method, url, use_auth=False, **kwargs):
        downloader.calls.append({"url": url, "params": kwargs.get("params")})
        if "/sha256/" in url:
            return True, copy.deepcopy(file_only_payload)
        return False, "unexpected"

    downloader.make_request = fake_make_request

    client = await CivArchiveClient.get_instance()

    result, error = await client.get_model_by_hash("f3a5370b")

    assert result is None
    assert error == "No version data found"
    assert not any("/models/" in call["url"] for call in downloader.calls)


async def test_get_model_by_hash_discards_resolved_version_on_hash_mismatch(downloader):
    """The version endpoint resolves modelVersionId globally, so a colliding
    foreign ID can resolve to a valid-looking but wrong version. The resolved
    files must contain the queried hash, otherwise the result is discarded."""
    file_only_payload = {
        "data": {
            "files": [
                {
                    "model_id": 1746460,
                    "model_version_id": 1976567,
                }
            ]
        }
    }

    version_payload = _base_civarchive_payload()

    async def fake_make_request(method, url, use_auth=False, **kwargs):
        downloader.calls.append({"url": url, "params": kwargs.get("params")})
        if "/sha256/" in url:
            return True, copy.deepcopy(file_only_payload)
        if "/models/1746460" in url:
            return True, copy.deepcopy(version_payload)
        return False, "unexpected"

    downloader.make_request = fake_make_request

    client = await CivArchiveClient.get_instance()

    result, error = await client.get_model_by_hash(
        "f3a5370b60e2a10ba8c35ddd95dc8a573b3843e032bd507a941b2cc467884955"
    )

    assert result is None
    assert error == "No version data found"


async def test_get_model_by_hash_records_foreign_source_ref(downloader):
    """The civision entry's ModelScope URL is surfaced so the sync service can
    link the model to its real source instead of leaving it 'not found'."""
    file_only_payload = {
        "data": {
            "files": [
                {
                    "filename": "Kiara-Krea_c1-st4000.safetensors",
                    "url": "https://www.modelscope.ai/models/arbinshado/Kiara-Krea/files?version=20260712182542",
                    "source": "civision",
                    "model_id": "455108",
                    "model_version_id": "130022",
                }
            ]
        }
    }

    async def fake_make_request(method, url, use_auth=False, **kwargs):
        downloader.calls.append({"url": url, "params": kwargs.get("params")})
        if "/sha256/" in url:
            return True, copy.deepcopy(file_only_payload)
        return False, "unexpected"

    downloader.make_request = fake_make_request

    client = await CivArchiveClient.get_instance()

    result, error = await client.get_model_by_hash("f3a5370b")

    assert result is None
    ref = client.pop_foreign_source_ref("f3a5370b")
    assert ref is not None
    assert ref.platform == "modelscope-ai"
    assert ref.source_id == "arbinshado/Kiara-Krea"
    # Consumed once; a second read returns nothing.
    assert client.pop_foreign_source_ref("f3a5370b") is None


async def test_get_model_by_hash_handles_not_found(downloader):
    async def fake_make_request(method, url, use_auth=False, **kwargs):
        return False, "Resource not found"

    downloader.make_request = fake_make_request

    client = await CivArchiveClient.get_instance()

    result, error = await client.get_model_by_hash("missing")

    assert result is None
    assert error == "Model not found"


async def test_get_model_by_hash_propagates_rate_limit(downloader):
    async def fake_make_request(method, url, use_auth=False, **kwargs):
        return False, RateLimitError("limited", retry_after=5)

    downloader.make_request = fake_make_request

    client = await CivArchiveClient.get_instance()

    with pytest.raises(RateLimitError) as exc_info:
        await client.get_model_by_hash("limited")

    assert exc_info.value.retry_after == 5
    assert exc_info.value.provider == "civarchive_api"


async def test_get_model_by_hash_empty_error_payload(downloader):
    """An empty-string failure payload must surface as a proper error.

    Regression test: (None, "") used to fall through the falsy-error check and
    crash in _resolve_version_from_files with "'NoneType' object has no
    attribute 'get'".
    """

    async def fake_make_request(method, url, use_auth=False, **kwargs):
        return False, ""

    downloader.make_request = fake_make_request

    client = await CivArchiveClient.get_instance()

    result, error = await client.get_model_by_hash("empty-error")

    assert result is None
    assert error == "Request failed"


async def test_get_model_version_offline_cooldown_logged_as_debug(downloader, caplog):
    """Cooldown short-circuits must not spam an ERROR per request."""

    async def fake_make_request(method, url, use_auth=False, **kwargs):
        return False, "offline_cooldown"

    downloader.make_request = fake_make_request

    client = await CivArchiveClient.get_instance()

    with caplog.at_level(logging.DEBUG, logger="py.services.civarchive_client"):
        result = await client.get_model_version(model_id=1, version_id=123)

    assert result is None
    module_records = [r for r in caplog.records if r.name == "py.services.civarchive_client"]
    assert not any(
        r.levelno >= logging.ERROR and "Error fetching CivArchive model version" in r.getMessage()
        for r in module_records
    )
    assert any(
        r.levelno == logging.DEBUG and "while offline" in r.getMessage()
        for r in module_records
    )


async def test_get_model_by_hash_ignores_the_empty_hash_placeholder(downloader):
    """The zero-byte digest resolves to a pile of unrelated files (#1162)."""
    from py.utils.constants import EMPTY_HASH_SHA256

    client = await CivArchiveClient.get_instance()

    result, error = await client.get_model_by_hash(EMPTY_HASH_SHA256)

    assert result is None
    assert error == "Model not found"
    assert downloader.calls == []
    # Nothing was remembered for a later foreign-source link either.
    assert client.pop_foreign_source_ref(EMPTY_HASH_SHA256) is None


async def test_resolve_version_from_files_refuses_the_placeholder(downloader):
    """A file-entry payload for the placeholder must not record a link target."""
    from py.utils.constants import EMPTY_HASH_SHA256

    client = await CivArchiveClient.get_instance()
    payload = {
        "files": [
            {
                "filename": "pam-krea2_c1-st4000.safetensors",
                "url": "https://www.modelscope.ai/models/ppxjmqq/pam-krea2/files?version=1",
                "source": "civision",
                "model_id": 474441,
                "model_version_id": 199065,
            }
        ]
    }

    assert (
        await client._resolve_version_from_files(
            payload, expected_hash=EMPTY_HASH_SHA256
        )
        is None
    )
    assert client.pop_foreign_source_ref(EMPTY_HASH_SHA256) is None
    assert downloader.calls == []

import copy
from unittest.mock import AsyncMock

import pytest

from py.services import civitai_client as civitai_client_module
from py.services.civitai_client import CivitaiClient
from py.services.errors import RateLimitError, ResourceNotFoundError
from py.services.model_metadata_provider import ModelMetadataProviderManager


class DummyDownloader:
    def __init__(self):
        self.download_calls = []
        self.memory_calls = []
        self.request_calls = []

    async def download_file(self, **kwargs):
        self.download_calls.append(kwargs)
        return True, kwargs["save_path"]

    async def download_to_memory(self, url, use_auth=False):
        self.memory_calls.append({"url": url, "use_auth": use_auth})
        return True, b"bytes", {"content-type": "image/jpeg"}

    async def make_request(self, method, url, use_auth=True, **kwargs):
        self.request_calls.append(
            {"method": method, "url": url, "use_auth": use_auth, "kwargs": kwargs}
        )
        return True, {}


@pytest.fixture(autouse=True)
def reset_singletons():
    CivitaiClient._instance = None
    ModelMetadataProviderManager._instance = None
    yield
    CivitaiClient._instance = None
    ModelMetadataProviderManager._instance = None


@pytest.fixture
def downloader(monkeypatch):
    instance = DummyDownloader()
    monkeypatch.setattr(civitai_client_module, "get_downloader", AsyncMock(return_value=instance))
    return instance


async def test_download_file_uses_downloader(tmp_path, downloader):
    client = await CivitaiClient.get_instance()
    save_dir = tmp_path / "files"
    save_dir.mkdir()

    success, path = await client.download_file(
        url="https://example.invalid/model",
        save_dir=str(save_dir),
        default_filename="model.safetensors",
    )

    assert success is True
    assert path == str(save_dir / "model.safetensors")
    assert downloader.download_calls[0]["use_auth"] is True


async def test_get_model_by_hash_enriches_metadata(monkeypatch, downloader):
    version_payload = {
        "modelId": 123,
        "model": {"description": "", "tags": []},
        "creator": {},
        "images": [
            {"meta": {"comfy": {"foo": "bar"}, "other": "keep"}},
            {"meta": "not-a-dict"},
        ],
    }
    model_payload = {"description": "desc", "tags": ["tag"], "creator": {"username": "user"}}

    async def fake_make_request(method, url, use_auth=True, **kwargs):
        if url.endswith("by-hash/hash"):
            return True, version_payload.copy()
        if url.endswith("/models/123"):
            return True, model_payload
        return False, "unexpected"

    downloader.make_request = fake_make_request

    client = await CivitaiClient.get_instance()

    result, error = await client.get_model_by_hash("hash")

    assert error is None
    assert result["model"]["description"] == "desc"
    assert result["model"]["tags"] == ["tag"]
    assert result["creator"] == {"username": "user"}
    assert "comfy" not in result["images"][0]["meta"]
    assert result["images"][0]["meta"]["other"] == "keep"


async def test_get_model_by_hash_handles_not_found(monkeypatch, downloader):
    async def fake_make_request(method, url, use_auth=True, **kwargs):
        return False, "not found"

    downloader.make_request = fake_make_request

    client = await CivitaiClient.get_instance()

    result, error = await client.get_model_by_hash("missing")

    assert result is None
    assert error == "Model not found"


async def test_get_model_by_hash_propagates_rate_limit(monkeypatch, downloader):
    async def fake_make_request(method, url, use_auth=True, **kwargs):
        return False, RateLimitError("limited", retry_after=4)

    downloader.make_request = fake_make_request

    client = await CivitaiClient.get_instance()

    with pytest.raises(RateLimitError) as exc_info:
        await client.get_model_by_hash("limited")

    assert exc_info.value.retry_after == 4
    assert exc_info.value.provider == "civitai_api"


async def test_download_preview_image_writes_file(tmp_path, downloader):
    client = await CivitaiClient.get_instance()
    target = tmp_path / "preview" / "image.jpg"

    success = await client.download_preview_image("https://example.invalid/preview", str(target))

    assert success is True
    assert target.exists()
    assert target.read_bytes() == b"bytes"


async def test_download_preview_image_failure(monkeypatch, downloader):
    async def failing_download(url, use_auth=False):
        return False, b"", {}

    downloader.download_to_memory = failing_download

    client = await CivitaiClient.get_instance()
    target = "/tmp/ignored.jpg"

    success = await client.download_preview_image("https://example.invalid/preview", target)

    assert success is False


async def test_get_model_versions_success(monkeypatch, downloader):
    async def fake_make_request(method, url, use_auth=True, **kwargs):
        return True, {"modelVersions": [{"id": 1}], "type": "LORA", "name": "Model"}

    downloader.make_request = fake_make_request

    client = await CivitaiClient.get_instance()

    result = await client.get_model_versions("123")

    assert result == {"modelVersions": [{"id": 1}], "type": "LORA", "name": "Model"}


async def test_get_model_versions_raises_on_not_found(monkeypatch, downloader):
    async def fake_make_request(method, url, use_auth=True, **kwargs):
        return False, {"message": "Resource not found"}

    downloader.make_request = fake_make_request

    client = await CivitaiClient.get_instance()

    with pytest.raises(ResourceNotFoundError):
        await client.get_model_versions("missing")


async def test_get_model_versions_raises_on_nested_not_found(monkeypatch, downloader):
    async def fake_make_request(method, url, use_auth=True, **kwargs):
        return False, {"error": {"message": "Resource not found"}}

    downloader.make_request = fake_make_request

    client = await CivitaiClient.get_instance()

    with pytest.raises(ResourceNotFoundError):
        await client.get_model_versions("missing")


async def test_get_model_versions_raises_on_other_errors(monkeypatch, downloader):
    async def fake_make_request(method, url, use_auth=True, **kwargs):
        return False, {"error": {"message": "Server error"}}

    downloader.make_request = fake_make_request

    client = await CivitaiClient.get_instance()

    with pytest.raises(RuntimeError):
        await client.get_model_versions("oops")


async def test_get_model_versions_bulk_success(monkeypatch, downloader):
    async def fake_make_request(method, url, use_auth=True, **kwargs):
        assert url.endswith("/models")
        assert kwargs.get("params") == {"ids": "1,2"}
        return True, {
            "items": [
                {"id": 1, "modelVersions": [{"id": 11}], "type": "LORA", "name": "One"},
                {"id": 2, "modelVersions": [], "type": "Checkpoint", "name": "Two"},
            ]
        }

    downloader.make_request = fake_make_request

    client = await CivitaiClient.get_instance()

    result = await client.get_model_versions_bulk([1, "2", 2])

    assert result == {
        1: {"modelVersions": [{"id": 11}], "type": "LORA", "name": "One"},
        2: {"modelVersions": [], "type": "Checkpoint", "name": "Two"},
    }


async def test_get_model_versions_bulk_handles_errors(monkeypatch, downloader):
    async def fake_make_request(method, url, use_auth=True, **kwargs):
        return False, "error"

    downloader.make_request = fake_make_request

    client = await CivitaiClient.get_instance()

    result = await client.get_model_versions_bulk([1, 2])

    assert result is None


async def test_get_model_version_by_version_id(monkeypatch, downloader):
    async def fake_make_request(method, url, use_auth=True, **kwargs):
        if url.endswith("/model-versions/7"):
            return True, {
                "modelId": 321,
                "model": {"description": ""},
                "files": [],
                "images": [{"meta": {"comfy": {"foo": "bar"}, "other": "keep"}}],
            }
        if url.endswith("/models/321"):
            return True, {"description": "desc", "tags": ["tag"], "creator": {"username": "user"}}
        return False, "unexpected"

    downloader.make_request = fake_make_request

    client = await CivitaiClient.get_instance()

    result = await client.get_model_version(version_id=7)

    assert result["model"]["description"] == "desc"
    assert result["model"]["tags"] == ["tag"]
    assert result["creator"] == {"username": "user"}
    assert "comfy" not in result["images"][0]["meta"]
    assert result["images"][0]["meta"]["other"] == "keep"


async def test_get_model_version_with_model_id_prefers_version_endpoint(monkeypatch, downloader):
    requests = []

    model_payload = {
        "modelVersions": [
            {
                "id": 7,
                "files": [
                    {
                        "type": "Model",
                        "primary": True,
                        "hashes": {"SHA256": "hash7"},
                    }
                ],
            }
        ],
        "description": "desc",
        "tags": ["tag"],
        "creator": {"username": "user"},
        "name": "Model",
        "type": "LORA",
        "nsfw": False,
        "poi": False,
    }

    version_payload = {
        "id": 7,
        "modelId": 99,
        "model": {},
        "files": [],
        "images": [],
    }

    async def fake_make_request(method, url, use_auth=True, **kwargs):
        requests.append(url)
        if url.endswith("/models/99"):
            return True, copy.deepcopy(model_payload)
        if url.endswith("/model-versions/7"):
            return True, copy.deepcopy(version_payload)
        return False, "unexpected"

    downloader.make_request = fake_make_request

    client = await CivitaiClient.get_instance()

    result = await client.get_model_version(model_id=99, version_id=7)

    assert result["id"] == 7
    assert result["model"]["description"] == "desc"
    assert result["model"]["tags"] == ["tag"]
    assert result["creator"] == {"username": "user"}
    assert requests[0].endswith("/models/99")
    assert requests[1].endswith("/model-versions/7")


async def test_get_model_version_with_model_id_fallbacks_to_hash(monkeypatch, downloader):
    requests = []

    model_payload = {
        "modelVersions": [
            {
                "id": 7,
                "files": [
                    {
                        "type": "Model",
                        "primary": True,
                        "hashes": {"SHA256": "hash7"},
                    }
                ],
            }
        ],
        "description": "desc",
        "tags": ["tag"],
        "creator": {"username": "user"},
        "name": "Model",
        "type": "LORA",
        "nsfw": False,
        "poi": False,
    }

    version_payload = {
        "id": 7,
        "modelId": 99,
        "files": [],
        "images": [],
    }

    async def fake_make_request(method, url, use_auth=True, **kwargs):
        requests.append(url)
        if url.endswith("/models/99"):
            return True, copy.deepcopy(model_payload)
        if url.endswith("/model-versions/7"):
            return False, "boom"
        if url.endswith("/model-versions/by-hash/hash7"):
            return True, copy.deepcopy(version_payload)
        return False, "unexpected"

    downloader.make_request = fake_make_request

    client = await CivitaiClient.get_instance()

    result = await client.get_model_version(model_id=99, version_id=7)

    assert result["id"] == 7
    assert result["model"]["description"] == "desc"
    assert result["model"]["tags"] == ["tag"]
    assert result["creator"] == {"username": "user"}
    assert requests[1].endswith("/model-versions/7")
    assert requests[2].endswith("/model-versions/by-hash/hash7")


async def test_get_model_version_with_model_id_builds_from_model_data(monkeypatch, downloader):
    model_payload = {
        "modelVersions": [
            {
                "id": 7,
                "files": [],
                "name": "v1",
            }
        ],
        "description": "desc",
        "tags": ["tag"],
        "creator": {"username": "user"},
        "name": "Model",
        "type": "LORA",
        "nsfw": False,
        "poi": False,
    }

    async def fake_make_request(method, url, use_auth=True, **kwargs):
        if url.endswith("/models/99"):
            return True, copy.deepcopy(model_payload)
        if url.endswith("/model-versions/7"):
            return False, "boom"
        if "/model-versions/by-hash/" in url:
            return False, "boom"
        return False, "unexpected"

    downloader.make_request = fake_make_request

    client = await CivitaiClient.get_instance()

    result = await client.get_model_version(model_id=99, version_id=7)

    assert result["modelId"] == 99
    assert result["model"]["name"] == "Model"
    assert result["model"]["type"] == "LORA"
    assert result["model"]["description"] == "desc"
    assert result["model"]["tags"] == ["tag"]
    assert result["creator"] == {"username": "user"}


async def test_get_model_version_requires_identifier(monkeypatch, downloader):
    client = await CivitaiClient.get_instance()
    result = await client.get_model_version()
    assert result is None


async def test_get_model_version_info_handles_not_found(monkeypatch, downloader):
    async def fake_make_request(method, url, use_auth=True, **kwargs):
        return False, "not found"

    downloader.make_request = fake_make_request

    client = await CivitaiClient.get_instance()

    result, error = await client.get_model_version_info("55")

    assert result is None
    assert error == "Model not found"


async def test_get_model_version_info_success(monkeypatch, downloader):
    expected = {"id": 55, "images": [{"meta": {"comfy": {"foo": "bar"}, "other": "keep"}}]}

    async def fake_make_request(method, url, use_auth=True, **kwargs):
        return True, expected

    downloader.make_request = fake_make_request

    client = await CivitaiClient.get_instance()

    result, error = await client.get_model_version_info("55")

    assert result == expected
    assert error is None
    assert "comfy" not in result["images"][0]["meta"]
    assert result["images"][0]["meta"]["other"] == "keep"


async def test_get_image_info_returns_first_item(monkeypatch, downloader):
    async def fake_make_request(method, url, use_auth=True, **kwargs):
        return True, {"items": [{"id": 1}, {"id": 2}]}

    downloader.make_request = fake_make_request

    client = await CivitaiClient.get_instance()

    result = await client.get_image_info("42")

    assert result == {"id": 1}


async def test_get_image_info_handles_missing(monkeypatch, downloader):
    async def fake_make_request(method, url, use_auth=True, **kwargs):
        return True, {"items": []}

    downloader.make_request = fake_make_request

    client = await CivitaiClient.get_instance()

    result = await client.get_image_info("42")

    assert result is None

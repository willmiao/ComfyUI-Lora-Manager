from types import SimpleNamespace
from typing import Any, Dict
from unittest.mock import AsyncMock

import pytest

from py.services.errors import RateLimitError
from py.services.metadata_sync_service import MetadataSyncService


class DummySettings:
    def __init__(self, values: dict | None = None) -> None:
        self._values = values or {}

    def get(self, key: str, default=None):
        return self._values.get(key, default)


def build_service(
    *,
    settings_values: dict | None = None,
    default_provider: SimpleNamespace | None = None,
    provider_selector: AsyncMock | None = None,
):
    metadata_manager = SimpleNamespace(
        save_metadata=AsyncMock(),
        hydrate_model_data=AsyncMock(side_effect=lambda payload: payload),
    )
    preview_service = SimpleNamespace(ensure_preview_for_metadata=AsyncMock())
    settings = DummySettings(settings_values)

    provider = default_provider or SimpleNamespace(
        get_model_by_hash=AsyncMock(),
        get_model_version=AsyncMock(),
    )
    if default_provider is None:
        provider.get_model_by_hash.return_value = (None, None)

    default_provider_factory = AsyncMock(return_value=provider)
    provider_selector = provider_selector or AsyncMock(return_value=provider)

    service = MetadataSyncService(
        metadata_manager=metadata_manager,
        preview_service=preview_service,
        settings=settings,
        default_metadata_provider_factory=default_provider_factory,
        metadata_provider_selector=provider_selector,
    )

    return SimpleNamespace(
        service=service,
        metadata_manager=metadata_manager,
        preview_service=preview_service,
        default_provider=provider,
        default_provider_factory=default_provider_factory,
        provider_selector=provider_selector,
    )


@pytest.mark.asyncio
async def test_update_model_metadata_merges_and_persists():
    helpers = build_service()

    local = {
        "civitai": {"trainedWords": ["alpha"], "creator": {"id": 1}},
        "modelDescription": "",
        "tags": [],
        "model_name": "Local",
    }
    remote = {
        "source": "api",
        "trainedWords": ["beta"],
        "model": {
            "name": "Remote Model",
            "description": "desc",
            "tags": ["style"],
            "creator": {"id": 2},
        },
        "baseModel": "sdxl",
        "images": ["img"],
    }

    result = await helpers.service.update_model_metadata(
        "path/to/model.metadata.json",
        local,
        remote,
        helpers.default_provider,
    )

    assert set(result["civitai"]["trainedWords"]) == {"alpha", "beta"}
    assert result["model_name"] == "Remote Model"
    assert result["modelDescription"] == "desc"
    assert result["tags"] == ["style"]
    assert result["base_model"] == "SDXL 1.0"

    helpers.preview_service.ensure_preview_for_metadata.assert_awaited_once()
    helpers.metadata_manager.save_metadata.assert_awaited_once_with(
        "path/to/model.metadata.json",
        result,
    )


@pytest.mark.asyncio
async def test_fetch_and_update_model_success_updates_cache(tmp_path):
    helpers = build_service()

    civitai_payload = {
        "source": "api",
        "model": {"name": "Remote", "description": "", "tags": ["tag"]},
        "images": [],
        "baseModel": "sdxl",
    }
    helpers.default_provider.get_model_by_hash.return_value = (civitai_payload, None)

    model_path = tmp_path / "model.safetensors"

    async def hydrate(payload: Dict[str, Any]) -> Dict[str, Any]:
        payload["hydrated"] = True
        return payload

    helpers.metadata_manager.hydrate_model_data.side_effect = hydrate

    model_data = {
        "model_name": "Local",
        "folder": "root",
        "file_path": str(model_path),
    }
    update_cache = AsyncMock(return_value=True)

    await hydrate(model_data)
    helpers.metadata_manager.hydrate_model_data.reset_mock()

    ok, error = await helpers.service.fetch_and_update_model(
        sha256="abc",
        file_path=str(model_path),
        model_data=model_data,
        update_cache_func=update_cache,
    )

    assert ok and error is None
    assert model_data["from_civitai"] is True
    assert model_data["civitai_deleted"] is False
    assert "civitai" in model_data
    assert model_data["metadata_source"] == "civitai_api"

    helpers.metadata_manager.hydrate_model_data.assert_not_awaited()
    assert model_data["hydrated"] is True

    metadata_path = str(model_path.with_suffix(".metadata.json"))
    await_args = helpers.metadata_manager.save_metadata.await_args_list
    assert await_args, "expected metadata to be persisted"
    last_call = await_args[-1]
    assert last_call.args[0] == metadata_path
    assert last_call.args[1]["hydrated"] is True
    update_cache.assert_awaited_once()


@pytest.mark.asyncio
async def test_fetch_and_update_model_handles_missing_remote_metadata(tmp_path):
    helpers = build_service()
    helpers.default_provider.get_model_by_hash.return_value = (None, "Model not found")

    model_path = tmp_path / "model.safetensors"

    async def hydrate(payload: Dict[str, Any]) -> Dict[str, Any]:
        payload["hydrated"] = True
        return payload

    helpers.metadata_manager.hydrate_model_data.side_effect = hydrate

    model_data = {
        "model_name": "Local",
        "folder": "sub",
        "file_path": str(model_path),
    }

    await hydrate(model_data)
    helpers.metadata_manager.hydrate_model_data.reset_mock()

    ok, error = await helpers.service.fetch_and_update_model(
        sha256="missing",
        file_path=str(model_path),
        model_data=model_data,
        update_cache_func=AsyncMock(),
    )

    assert not ok
    assert "Model not found" in error
    assert model_data["from_civitai"] is False
    assert model_data["civitai_deleted"] is True

    helpers.metadata_manager.hydrate_model_data.assert_not_awaited()
    assert model_data["hydrated"] is True

    helpers.metadata_manager.save_metadata.assert_awaited_once()
    call_args = helpers.metadata_manager.save_metadata.await_args
    assert call_args.args[0].endswith("model.safetensors")
    assert "folder" not in call_args.args[1]
    assert call_args.args[1]["hydrated"] is True


@pytest.mark.asyncio
async def test_fetch_and_update_model_respects_deleted_without_archive():
    helpers = build_service(settings_values={"enable_metadata_archive_db": False})

    model_data = {
        "civitai_deleted": True,
        "file_path": "/tmp/model.safetensors",
    }
    update_cache = AsyncMock()

    ok, error = await helpers.service.fetch_and_update_model(
        sha256="abc",
        file_path="/tmp/model.safetensors",
        model_data=model_data,
        update_cache_func=update_cache,
    )

    assert not ok
    assert "metadata archive DB is not enabled" in error
    helpers.default_provider_factory.assert_not_awaited()
    helpers.metadata_manager.hydrate_model_data.assert_not_awaited()
    update_cache.assert_not_awaited()


@pytest.mark.asyncio
async def test_fetch_and_update_model_prefers_civarchive_for_deleted_models(tmp_path):
    default_provider = SimpleNamespace(
        get_model_by_hash=AsyncMock(),
        get_model_version=AsyncMock(),
    )
    civarchive_provider = SimpleNamespace(
        get_model_by_hash=AsyncMock(
            return_value=(
                {
                    "source": "civarchive",
                    "model": {"name": "Recovered", "description": "", "tags": []},
                    "images": [],
                    "baseModel": "sdxl",
                },
                None,
            )
        ),
        get_model_version=AsyncMock(),
    )

    async def select_provider(name: str):
        return civarchive_provider if name == "civarchive_api" else default_provider

    provider_selector = AsyncMock(side_effect=select_provider)
    helpers = build_service(
        settings_values={"enable_metadata_archive_db": False},
        default_provider=default_provider,
        provider_selector=provider_selector,
    )

    model_path = tmp_path / "model.safetensors"
    model_data = {
        "civitai_deleted": True,
        "metadata_source": "civarchive",
        "civitai": {"source": "civarchive"},
        "file_path": str(model_path),
    }
    update_cache = AsyncMock()

    ok, error = await helpers.service.fetch_and_update_model(
        sha256="deadbeef",
        file_path=str(model_path),
        model_data=model_data,
        update_cache_func=update_cache,
    )

    assert ok
    assert error is None
    provider_selector.assert_awaited_with("civarchive_api")
    helpers.default_provider_factory.assert_not_awaited()
    civarchive_provider.get_model_by_hash.assert_awaited_once_with("deadbeef")
    update_cache.assert_awaited()
    assert model_data["metadata_source"] == "civarchive"
    helpers.metadata_manager.save_metadata.assert_awaited()


@pytest.mark.asyncio
async def test_fetch_and_update_model_falls_back_to_sqlite_after_civarchive_failure(tmp_path):
    default_provider = SimpleNamespace(
        get_model_by_hash=AsyncMock(),
        get_model_version=AsyncMock(),
    )
    civarchive_provider = SimpleNamespace(
        get_model_by_hash=AsyncMock(return_value=(None, "Model not found")),
        get_model_version=AsyncMock(),
    )
    sqlite_payload = {
        "source": "archive_db",
        "model": {"name": "Recovered", "description": "", "tags": []},
        "images": [],
        "baseModel": "sdxl",
    }
    sqlite_provider = SimpleNamespace(
        get_model_by_hash=AsyncMock(return_value=(sqlite_payload, None)),
        get_model_version=AsyncMock(),
    )

    async def select_provider(name: str):
        if name == "civarchive_api":
            return civarchive_provider
        if name == "sqlite":
            return sqlite_provider
        return default_provider

    provider_selector = AsyncMock(side_effect=select_provider)
    helpers = build_service(
        settings_values={"enable_metadata_archive_db": True},
        default_provider=default_provider,
        provider_selector=provider_selector,
    )

    model_path = tmp_path / "model.safetensors"
    model_data = {
        "civitai_deleted": True,
        "db_checked": False,
        "file_path": str(model_path),
    }
    update_cache = AsyncMock()

    ok, error = await helpers.service.fetch_and_update_model(
        sha256="cafe",
        file_path=str(model_path),
        model_data=model_data,
        update_cache_func=update_cache,
    )

    assert ok and error is None
    assert civarchive_provider.get_model_by_hash.await_count == 1
    assert sqlite_provider.get_model_by_hash.await_count == 1
    assert model_data["metadata_source"] == "archive_db"
    assert model_data["db_checked"] is True
    assert provider_selector.await_args_list[0].args == ("civarchive_api",)
    assert provider_selector.await_args_list[1].args == ("sqlite",)
    update_cache.assert_awaited()
    helpers.metadata_manager.save_metadata.assert_awaited()


@pytest.mark.asyncio
async def test_fetch_and_update_model_returns_rate_limit_error(tmp_path):
    rate_error = RateLimitError("limited", retry_after=7)
    default_provider = SimpleNamespace(
        get_model_by_hash=AsyncMock(side_effect=rate_error),
        get_model_version=AsyncMock(),
    )
    helpers = build_service(default_provider=default_provider)

    model_path = tmp_path / "model.safetensors"
    model_data = {
        "file_path": str(model_path),
        "model_name": "Local",
    }
    update_cache = AsyncMock()

    ok, error = await helpers.service.fetch_and_update_model(
        sha256="deadbeef",
        file_path=str(model_path),
        model_data=model_data,
        update_cache_func=update_cache,
    )

    assert ok is False
    assert error is not None and "Rate limited" in error
    assert "7" in error
    helpers.metadata_manager.save_metadata.assert_not_awaited()
    update_cache.assert_not_awaited()
    helpers.provider_selector.assert_not_awaited()


@pytest.mark.asyncio
async def test_relink_metadata_fetches_version_without_overwriting_sha(tmp_path):
    provider = SimpleNamespace(
        get_model_by_hash=AsyncMock(),
        get_model_version=AsyncMock(
            return_value={
                "files": [
                    {
                        "primary": True,
                        "type": "Model",
                        "hashes": {"SHA256": "ABCDEF"},
                    }
                ],
                "model": {"name": "Remote"},
                "images": [],
            }
        ),
    )

    helpers = build_service(default_provider=provider)

    metadata = {"model_name": "Local", "sha256": "original"}
    result = await helpers.service.relink_metadata(
        file_path=str(tmp_path / "model.safetensors"),
        metadata=metadata,
        model_id=1,
        model_version_id=2,
    )

    assert result["model_name"] == "Remote"
    assert result["sha256"] == "original"
    helpers.metadata_manager.save_metadata.assert_awaited_once()


@pytest.mark.asyncio
async def test_relink_metadata_raises_when_version_missing():
    provider = SimpleNamespace(
        get_model_by_hash=AsyncMock(),
        get_model_version=AsyncMock(return_value=None),
    )

    helpers = build_service(default_provider=provider)

    with pytest.raises(ValueError):
        await helpers.service.relink_metadata(
            file_path="/tmp/model.safetensors",
            metadata={},
            model_id=9,
            model_version_id=None,
        )


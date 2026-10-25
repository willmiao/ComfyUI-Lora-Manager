from types import SimpleNamespace
from typing import Any, Dict
from unittest.mock import AsyncMock

import pytest

from py.services.connectivity_guard import OFFLINE_COOLDOWN_ERROR, OFFLINE_FRIENDLY_MESSAGE
from py.services.errors import MetadataPersistError, RateLimitError
from py.utils.constants import EMPTY_HASH_SHA256
from py.services.metadata_sync_service import MetadataSyncService, _merge_ordered_unique


class DummySettings:
    def __init__(self, values: dict[str, Any] | None = None) -> None:
        self._values = values or {}

    def get(self, key: str, default=None):
        return self._values.get(key, default)


def build_service(
    *,
    settings_values: dict[str, Any] | None = None,
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
        settings=settings,  # pyright: ignore[reportArgumentType]
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
            "allowNoCredit": False,
            "allowCommercialUse": ["Image"],
            "allowDerivatives": False,
            "allowDifferentLicense": True,
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
    civitai_model = result["civitai"]["model"]
    assert civitai_model["allowNoCredit"] is False
    assert civitai_model["allowCommercialUse"] == ["Image"]
    assert civitai_model["allowDerivatives"] is False
    assert civitai_model["allowDifferentLicense"] is True
    for key in ("allowNoCredit", "allowCommercialUse", "allowDerivatives", "allowDifferentLicense"):
        assert key not in result

    helpers.preview_service.ensure_preview_for_metadata.assert_awaited_once()
    helpers.metadata_manager.save_metadata.assert_awaited_once_with(
        "path/to/model.metadata.json",
        result,
    )


def test_merge_ordered_unique_keeps_first_seen_order():
    assert _merge_ordered_unique(["b", "a"], ["a", "c", "b", "d"]) == [
        "b",
        "a",
        "c",
        "d",
    ]
    assert _merge_ordered_unique([], ["x"]) == ["x"]
    assert _merge_ordered_unique(["x"], []) == ["x"]


@pytest.mark.asyncio
async def test_update_model_metadata_preserves_trained_word_order():
    """Trigger word order (prompt order) must survive a metadata refresh."""

    helpers = build_service()

    local = {
        "civitai": {"trainedWords": ["zeta style", "alpha", "beta"]},
        "model_name": "Local",
    }
    remote = {
        "source": "api",
        "trainedWords": ["beta", "gamma", "alpha"],
        "model": {"name": "Remote Model"},
    }

    result = await helpers.service.update_model_metadata(
        "path/to/model.metadata.json",
        local,
        remote,
        helpers.default_provider,
    )

    # Saved order first, newly discovered words appended, duplicates dropped
    assert result["civitai"]["trainedWords"] == [
        "zeta style",
        "alpha",
        "beta",
        "gamma",
    ]


@pytest.mark.asyncio
async def test_update_model_metadata_propagates_civitai_autov3():
    helpers = build_service()

    local = {
        "sha256": "111aabbf94dd9e59c05d842fccf57bec915b2a3c237f6b54f8d614e40858d717",
        "autov3": "",
        "model_name": "Local",
    }
    remote = {
        "source": "api",
        "model": {"name": "Remote Model", "description": "", "tags": []},
        "images": [],
        "files": [
            {
                "name": "other.safetensors",
                "hashes": {"SHA256": "ZZZ999"},
            },
            {
                "name": "model.safetensors",
                "hashes": {
                    "SHA256": "111aabbf94dd9e59c05d842fccf57bec915b2a3c237f6b54f8d614e40858d717",
                    "AutoV3": "8A582E901D7F",
                },
            },
        ],
    }

    result = await helpers.service.update_model_metadata(
        "path/to/model.metadata.json",
        local,
        remote,
        helpers.default_provider,
    )

    # Civitai-first: the '' (checked-unavailable) state is upgraded in-session
    # by the freshly fetched metadata, without any header re-read.
    assert result["autov3"] == "8a582e901d7f"


@pytest.mark.asyncio
async def test_update_model_metadata_keeps_autov3_without_matching_file():
    helpers = build_service()

    local = {"sha256": "abc123", "autov3": "", "model_name": "Local"}
    remote = {
        "source": "api",
        "model": {"name": "Remote Model", "description": "", "tags": []},
        "images": [],
        "files": [{"name": "other.safetensors", "hashes": {"SHA256": "ZZZ999", "AutoV3": "ABCDEF123456"}}],
    }

    result = await helpers.service.update_model_metadata(
        "path/to/model.metadata.json",
        local,
        remote,
        helpers.default_provider,
    )

    assert result["autov3"] == ""


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

    model_data: Dict[str, Any] = {
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
    civitai_model = model_data["civitai"]["model"]
    assert civitai_model["allowNoCredit"] is True
    assert civitai_model["allowDerivatives"] is True
    assert civitai_model["allowDifferentLicense"] is True
    assert civitai_model["allowCommercialUse"] == ["Sell"]
    for key in ("allowNoCredit", "allowCommercialUse", "allowDerivatives", "allowDifferentLicense"):
        assert key not in model_data

    helpers.metadata_manager.hydrate_model_data.assert_not_awaited()
    assert model_data["hydrated"] is True

    metadata_path = str(model_path.with_suffix(".metadata.json"))
    await_args = helpers.metadata_manager.save_metadata.await_args_list
    assert await_args, "expected metadata to be persisted"
    last_call = await_args[-1]
    assert last_call.args[0] == metadata_path
    persisted_payload = last_call.args[1]
    assert persisted_payload["hydrated"] is True
    civitai_model = persisted_payload["civitai"]["model"]
    assert civitai_model["allowNoCredit"] is True
    assert civitai_model["allowCommercialUse"] == ["Sell"]
    for key in ("allowNoCredit", "allowCommercialUse", "allowDerivatives", "allowDifferentLicense"):
        assert key not in persisted_payload
    update_cache.assert_awaited_once()


@pytest.mark.asyncio
async def test_update_model_metadata_raises_when_sidecar_write_fails():
    """A failed sidecar write must surface instead of being swallowed."""
    helpers = build_service()
    helpers.metadata_manager.save_metadata.return_value = False

    with pytest.raises(MetadataPersistError):
        await helpers.service.update_model_metadata(
            "path/to/model.metadata.json",
            {"civitai": {}, "model_name": "Local"},
            {"source": "api", "model": {"name": "Remote"}, "images": []},
            helpers.default_provider,
        )


@pytest.mark.asyncio
async def test_update_model_metadata_unblocks_example_image_failures(monkeypatch):
    """Persisting fresh provider metadata re-enables example image downloads."""
    helpers = build_service()

    from py.utils import example_images_download_manager as download_module

    calls: list[list[str]] = []

    def fake_unblock(hashes, library_name=None):
        calls.append(list(hashes))
        return len(hashes)

    monkeypatch.setattr(
        download_module, "unblock_failed_example_image_models", fake_unblock
    )

    result = await helpers.service.update_model_metadata(
        "path/to/model.metadata.json",
        {"sha256": "A" * 64, "model_name": "Local"},
        {"source": "api", "model": {"name": "Remote"}, "images": []},
        helpers.default_provider,
    )

    assert result["model_name"] == "Remote"
    assert calls == [["a" * 64]]


@pytest.mark.asyncio
async def test_update_model_metadata_without_hash_skips_unblock(monkeypatch):
    helpers = build_service()

    from py.utils import example_images_download_manager as download_module

    def fail_unblock(hashes, library_name=None):  # pragma: no cover - must not run
        raise AssertionError("unblock must not run without a sha256")

    monkeypatch.setattr(
        download_module, "unblock_failed_example_image_models", fail_unblock
    )

    result = await helpers.service.update_model_metadata(
        "path/to/model.metadata.json",
        {"model_name": "Local"},
        {"source": "api", "model": {"name": "Remote"}, "images": []},
        helpers.default_provider,
    )

    assert result["model_name"] == "Remote"


@pytest.mark.asyncio
async def test_fetch_and_update_model_reports_sidecar_write_failure(tmp_path):
    """Fetch fails the item (and leaves the cache untouched) when the sidecar
    cannot be written, so the model stays eligible for the next run."""
    helpers = build_service()
    helpers.metadata_manager.save_metadata.return_value = False

    civitai_payload = {
        "source": "api",
        "model": {"name": "Remote", "description": "", "tags": ["tag"]},
        "images": [],
        "baseModel": "sdxl",
    }
    helpers.default_provider.get_model_by_hash.return_value = (civitai_payload, None)

    model_path = tmp_path / "model.safetensors"
    model_data: Dict[str, Any] = {
        "model_name": "Local",
        "folder": "root",
        "file_path": str(model_path),
    }
    update_cache = AsyncMock(return_value=True)

    ok, error = await helpers.service.fetch_and_update_model(
        sha256="abc",
        file_path=str(model_path),
        model_data=model_data,
        update_cache_func=update_cache,
    )

    assert ok is False
    assert "sidecar" in (error or "")
    update_cache.assert_not_awaited()


@pytest.mark.asyncio
async def test_fetch_and_update_model_keeps_deleted_flag_false_for_archive_source(tmp_path):
    helpers = build_service()

    civitai_payload = {
        "source": "archive_db",
        "model": {"name": "Recovered", "description": "", "tags": ["tag"]},
        "images": [],
        "baseModel": "sd15",
    }
    helpers.default_provider.get_model_by_hash.return_value = (civitai_payload, None)

    model_path = tmp_path / "model.safetensors"
    model_data = {
        "model_name": "Local",
        "folder": "root",
        "file_path": str(model_path),
    }
    update_cache = AsyncMock(return_value=True)

    ok, error = await helpers.service.fetch_and_update_model(
        sha256="abc",
        file_path=str(model_path),
        model_data=model_data,
        update_cache_func=update_cache,
    )

    assert ok and error is None
    assert model_data["metadata_source"] == "archive_db"
    assert model_data["civitai_deleted"] is False
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

    model_data: Dict[str, Any] = {
        "model_name": "Local",
        "folder": "root",
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


@pytest.mark.asyncio
async def test_fetch_and_update_model_returns_friendly_offline_message(tmp_path):
    helpers = build_service()
    helpers.default_provider.get_model_by_hash.return_value = (None, OFFLINE_COOLDOWN_ERROR)

    model_path = tmp_path / "model.safetensors"
    model_data = {
        "model_name": "Local",
        "folder": "root",
        "file_path": str(model_path),
    }
    update_cache = AsyncMock(return_value=True)

    ok, error = await helpers.service.fetch_and_update_model(
        sha256="abc",
        file_path=str(model_path),
        model_data=model_data,
        update_cache_func=update_cache,
    )

    assert ok is False
    assert error is not None
    assert OFFLINE_FRIENDLY_MESSAGE in error
    update_cache.assert_not_awaited()


def _foreign_ref():
    from py.services.model_sources import SourceRef

    return SourceRef(
        platform="modelscope-ai",
        source_id="arbinshado/Kiara-Krea",
        url="https://www.modelscope.ai/models/arbinshado/Kiara-Krea",
    )


def _wire_foreign_source(monkeypatch, *, context, hydrate_result=None):
    """Patch the source-registry pieces _try_link_foreign_source consumes."""
    from unittest.mock import Mock

    fake_source = SimpleNamespace(
        fetch_card_context_by_hash=AsyncMock(return_value=context),
    )
    hydrate = AsyncMock(return_value=hydrate_result or [])
    monkeypatch.setattr(
        "py.services.metadata_sync_service.get_source", lambda _platform: fake_source
    )
    monkeypatch.setattr(
        "py.services.metadata_sync_service.hydrate_from_source", hydrate
    )
    monkeypatch.setattr(
        "py.services.metadata_sync_service.shared_source_cache", lambda *_args: None
    )
    return SimpleNamespace(source=fake_source, hydrate=hydrate, Mock=Mock)


@pytest.mark.asyncio
async def test_fetch_and_update_model_links_foreign_source_when_not_found(tmp_path, monkeypatch):
    """CivArchive knows the file only as a foreign-ecosystem entry: the model
    gets linked to its real source and hydrated instead of flagged deleted."""
    ref = _foreign_ref()
    provider = SimpleNamespace(
        get_model_by_hash=AsyncMock(return_value=(None, "Model not found")),
        get_model_version=AsyncMock(),
        pop_foreign_source_ref=lambda _hash: ref,
    )
    helpers = build_service(
        default_provider=provider,
        provider_selector=AsyncMock(return_value=provider),
    )
    wired = _wire_foreign_source(monkeypatch, context=SimpleNamespace(model_name="Kiara-Krea"), hydrate_result=["model_name"])

    model_path = tmp_path / "Kiara-Krea_c1-st4000.safetensors"
    model_data: Dict[str, Any] = {
        "model_name": "Kiara-Krea_c1-st4000",
        "folder": "root",
        "file_path": str(model_path),
    }
    update_cache = AsyncMock(return_value=True)

    ok, error = await helpers.service.fetch_and_update_model(
        sha256="f3a5370b",
        file_path=str(model_path),
        model_data=model_data,
        update_cache_func=update_cache,
    )

    assert ok is True and error is None
    assert model_data["source_url"] == ref.url
    assert model_data["source_platform"] == "modelscope-ai"
    assert model_data["from_civitai"] is False
    assert "civitai_deleted" not in model_data
    helpers.metadata_manager.save_metadata.assert_awaited()
    update_cache.assert_awaited()
    wired.hydrate.assert_awaited_once()
    assert wired.hydrate.await_args.kwargs["ref"] is ref


@pytest.mark.asyncio
async def test_fetch_and_update_model_skips_foreign_link_when_hash_not_published(tmp_path, monkeypatch):
    """The strict hash gate rejects the link: the repository does not publish
    this exact file, so normal not-found handling takes over."""
    provider = SimpleNamespace(
        get_model_by_hash=AsyncMock(return_value=(None, "Model not found")),
        get_model_version=AsyncMock(),
        pop_foreign_source_ref=lambda _hash: _foreign_ref(),
    )
    helpers = build_service(
        default_provider=provider,
        provider_selector=AsyncMock(return_value=provider),
    )
    wired = _wire_foreign_source(monkeypatch, context=None)

    model_path = tmp_path / "model.safetensors"
    model_data: Dict[str, Any] = {
        "model_name": "Local",
        "folder": "root",
        "file_path": str(model_path),
    }

    ok, error = await helpers.service.fetch_and_update_model(
        sha256="deadbeef",
        file_path=str(model_path),
        model_data=model_data,
        update_cache_func=AsyncMock(return_value=True),
    )

    assert ok is False
    assert "source_url" not in model_data
    assert model_data["from_civitai"] is False
    assert model_data["civitai_deleted"] is True
    wired.hydrate.assert_not_awaited()


@pytest.mark.asyncio
async def test_fetch_and_update_model_never_relinks_a_model_with_external_source(tmp_path, monkeypatch):
    """A model already linked to an external source keeps that link."""
    from unittest.mock import Mock

    pop_ref = Mock(return_value=_foreign_ref())
    provider = SimpleNamespace(
        get_model_by_hash=AsyncMock(return_value=(None, "Model not found")),
        get_model_version=AsyncMock(),
        pop_foreign_source_ref=pop_ref,
    )
    helpers = build_service(
        default_provider=provider,
        provider_selector=AsyncMock(return_value=provider),
    )

    model_path = tmp_path / "model.safetensors"
    model_data: Dict[str, Any] = {
        "model_name": "Local",
        "folder": "root",
        "file_path": str(model_path),
        "source_url": "https://huggingface.co/some/user",
        "source_platform": "huggingface",
    }

    ok, error = await helpers.service.fetch_and_update_model(
        sha256="deadbeef",
        file_path=str(model_path),
        model_data=model_data,
        update_cache_func=AsyncMock(return_value=True),
    )

    assert ok is False
    assert model_data["source_url"] == "https://huggingface.co/some/user"
    pop_ref.assert_not_called()


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
    # Now update_cache_func IS called to persist the not-found flags to SQLite
    update_cache.assert_awaited_once()


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
    assert model_data["civitai_deleted"] is True
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
    assert model_data["civitai_deleted"] is True
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


@pytest.mark.asyncio
async def test_relink_metadata_uses_named_civarchive_provider(tmp_path):
    default_provider = SimpleNamespace(
        get_model_by_hash=AsyncMock(),
        get_model_version=AsyncMock(),
    )
    civarchive_provider = SimpleNamespace(
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
                "model": {"name": "Archived"},
                "images": [],
            }
        ),
    )

    async def select_provider(name: str):
        return civarchive_provider if name == "civarchive_api" else default_provider

    provider_selector = AsyncMock(side_effect=select_provider)
    helpers = build_service(
        default_provider=default_provider,
        provider_selector=provider_selector,
    )

    metadata = {"model_name": "Local", "sha256": "original"}
    result = await helpers.service.relink_metadata(
        file_path=str(tmp_path / "model.safetensors"),
        metadata=metadata,
        model_id=1,
        model_version_id=2,
        provider_name="civarchive_api",
    )

    assert result["model_name"] == "Archived"
    assert result["sha256"] == "original"
    provider_selector.assert_awaited_with("civarchive_api")
    civarchive_provider.get_model_version.assert_awaited_once_with(1, 2)
    helpers.default_provider_factory.assert_not_awaited()
    helpers.metadata_manager.save_metadata.assert_awaited_once()


@pytest.mark.asyncio
async def test_relink_metadata_raises_when_version_missing_with_civarchive():
    default_provider = SimpleNamespace(
        get_model_by_hash=AsyncMock(),
        get_model_version=AsyncMock(),
    )
    civarchive_provider = SimpleNamespace(
        get_model_by_hash=AsyncMock(),
        get_model_version=AsyncMock(return_value=None),
    )

    async def select_provider(name: str):
        return civarchive_provider if name == "civarchive_api" else default_provider

    provider_selector = AsyncMock(side_effect=select_provider)
    helpers = build_service(
        default_provider=default_provider,
        provider_selector=provider_selector,
    )

    with pytest.raises(ValueError, match="CivitArchive"):
        await helpers.service.relink_metadata(
            file_path="/tmp/model.safetensors",
            metadata={},
            model_id=9,
            model_version_id=None,
            provider_name="civarchive_api",
        )


@pytest.mark.asyncio
async def test_relink_metadata_raises_friendly_error_when_provider_unavailable():
    provider_selector = AsyncMock(
        side_effect=ValueError("Provider 'civarchive_api' is not registered")
    )
    helpers = build_service(provider_selector=provider_selector)

    with pytest.raises(ValueError, match="CivitArchive is not available or not enabled"):
        await helpers.service.relink_metadata(
            file_path="/tmp/model.safetensors",
            metadata={},
            model_id=9,
            model_version_id=None,
            provider_name="civarchive_api",
        )


@pytest.mark.asyncio
async def test_relink_metadata_default_call_uses_default_provider_factory(tmp_path):
    helpers = build_service()
    helpers.default_provider.get_model_version.return_value = {
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

    result = await helpers.service.relink_metadata(
        file_path=str(tmp_path / "model.safetensors"),
        metadata={"model_name": "Local", "sha256": "original"},
        model_id=1,
        model_version_id=None,
    )

    assert result["model_name"] == "Remote"
    assert result["sha256"] == "original"
    helpers.default_provider_factory.assert_awaited_once()
    helpers.provider_selector.assert_not_awaited()
    helpers.metadata_manager.save_metadata.assert_awaited_once()

@pytest.mark.asyncio
async def test_fetch_and_update_model_persists_db_checked_when_sqlite_fails(tmp_path):
    """
    Regression test: When a deleted model is checked against sqlite and not found,
    db_checked=True must be persisted to disk so the model is skipped in future refreshes.

    Previously, db_checked was set in memory but never saved because the save_metadata
    call was inside the `if civitai_api_not_found:` block, which is False for deleted
    models (since the default CivitAI API is never tried).
    """
    default_provider = SimpleNamespace(
        get_model_by_hash=AsyncMock(),
        get_model_version=AsyncMock(),
    )
    civarchive_provider = SimpleNamespace(
        get_model_by_hash=AsyncMock(return_value=(None, "Model not found")),
        get_model_version=AsyncMock(),
    )
    sqlite_provider = SimpleNamespace(
        get_model_by_hash=AsyncMock(return_value=(None, "Model not found")),
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
        "from_civitai": False,
        "file_path": str(model_path),
        "model_name": "Deleted Model",
    }
    update_cache = AsyncMock()

    ok, error = await helpers.service.fetch_and_update_model(
        sha256="deadbeef",
        file_path=str(model_path),
        model_data=model_data,
        update_cache_func=update_cache,
    )

    # The call should fail because neither provider found metadata
    assert not ok
    assert error is not None
    assert "Model not found" in error or "not found in metadata archive DB" in error

    # Both providers should have been tried
    assert civarchive_provider.get_model_by_hash.await_count == 1
    assert sqlite_provider.get_model_by_hash.await_count == 1

    # db_checked should be True in memory
    assert model_data["db_checked"] is True

    # CRITICAL: metadata should have been saved to disk with db_checked=True
    helpers.metadata_manager.save_metadata.assert_awaited_once()
    saved_call = helpers.metadata_manager.save_metadata.await_args
    saved_data = saved_call.args[1]
    assert saved_data["db_checked"] is True
    assert "folder" not in saved_data  # folder should be stripped
    assert "last_checked_at" in saved_data  # timestamp should be set


@pytest.mark.asyncio
async def test_fetch_and_update_model_does_not_overwrite_api_metadata_with_archive(tmp_path):
    helpers = build_service()

    # Existing high-quality metadata
    existing_civitai = {
        "source": "api", # will be normalized to civitai_api in some paths, but let's use what is_civitai_api_metadata expects
        "files": [{"id": 1}],
        "images": [{"url": "img1"}],
        "name": "High Quality",
        "trainedWords": ["keyword1"]
    }

    # Incoming lower-quality metadata from CivArchive (simulating fallback)
    civarchive_payload = {
        "source": "civarchive",
        "model": {"name": "Low Quality", "description": "low quality", "tags": []},
        "images": [], # Missing images
        "baseModel": "sdxl",
        "trainedWords": ["keyword2"]
    }
    helpers.default_provider.get_model_by_hash.return_value = (civarchive_payload, None)

    model_path = tmp_path / "model.safetensors"
    model_data: Dict[str, Any] = {
        "model_name": "High Quality",
        "metadata_source": "civitai_api",
        "civitai": existing_civitai,
        "file_path": str(model_path),
    }
    update_cache = AsyncMock(return_value=True)

    ok, error = await helpers.service.fetch_and_update_model(
        sha256="abc",
        file_path=str(model_path),
        model_data=model_data,
        update_cache_func=update_cache,
    )

    assert ok and error is None
    # Ensure the civitai block still contains the high-quality data
    assert model_data["civitai"]["name"] == "High Quality"
    assert "keyword1" in model_data["civitai"]["trainedWords"]
    # Source might be updated in model_data root, but the block should be protected if logic works
    assert model_data["metadata_source"] == "civarchive" 
    
    # Check that trained words were merged if any (though in this case we might skip the whole update)
    # Actually, according to the new logic, the update is SKIPPED entirely for the civitai block
    assert model_data["civitai"]["trainedWords"] == ["keyword1"]
    
    helpers.metadata_manager.save_metadata.assert_awaited()
    update_cache.assert_awaited()


@pytest.mark.asyncio
async def test_fetch_and_update_model_keeps_sqlite_last_resort_after_civarchive_rate_limit(tmp_path):
    """A CivArchive 429 must not block the local sqlite last resort (#1085)."""
    civarchive_provider = SimpleNamespace(
        get_model_by_hash=AsyncMock(
            side_effect=RateLimitError("limited", retry_after=30)
        ),
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
        raise AssertionError(f"unexpected provider request: {name}")

    helpers = build_service(
        settings_values={"enable_metadata_archive_db": True},
        provider_selector=AsyncMock(side_effect=select_provider),
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
    civarchive_provider.get_model_by_hash.assert_awaited_once()
    sqlite_provider.get_model_by_hash.assert_awaited_once()
    assert model_data["metadata_source"] == "archive_db"


# ---------------------------------------------------------------------------
# Empty-file SHA256 placeholder (issue #1162)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fetch_rehashes_the_empty_file_placeholder_before_lookup(tmp_path):
    """A stored hash of zero bytes must be replaced before any provider runs."""
    import hashlib

    helpers = build_service()
    helpers.default_provider.get_model_by_hash.return_value = (None, "Model not found")

    model_path = tmp_path / "Emilia(RE0).safetensors"
    model_path.write_bytes(b"real model bytes")
    expected = hashlib.sha256(b"real model bytes").hexdigest()
    model_data: Dict[str, Any] = {
        "model_name": "Emilia",
        "folder": "root",
        "file_path": str(model_path),
        "sha256": EMPTY_HASH_SHA256,
    }
    update_cache = AsyncMock(return_value=True)

    ok, error = await helpers.service.fetch_and_update_model(
        sha256=EMPTY_HASH_SHA256,
        file_path=str(model_path),
        model_data=model_data,
        update_cache_func=update_cache,
    )

    assert ok is False and error is not None  # not found, but the hash was repaired
    assert model_data["sha256"] == expected
    assert model_data["hash_status"] == "completed"
    helpers.default_provider.get_model_by_hash.assert_awaited_once_with(expected)
    saved_payload = helpers.metadata_manager.save_metadata.await_args.args[1]
    assert saved_payload["sha256"] == expected
    assert "folder" not in saved_payload
    # Once for the repaired hash, once for the not-found bookkeeping.
    assert update_cache.await_count == 2
    assert update_cache.await_args_list[0].args[2]["sha256"] == expected


@pytest.mark.asyncio
async def test_fetch_refuses_to_look_up_an_empty_file(tmp_path):
    """Zero-byte models cannot be identified: no provider request is made."""
    helpers = build_service()
    model_path = tmp_path / "broken.safetensors"
    model_path.write_bytes(b"")
    model_data: Dict[str, Any] = {"file_path": str(model_path), "sha256": EMPTY_HASH_SHA256}
    update_cache = AsyncMock(return_value=True)

    ok, error = await helpers.service.fetch_and_update_model(
        sha256=EMPTY_HASH_SHA256,
        file_path=str(model_path),
        model_data=model_data,
        update_cache_func=update_cache,
    )

    assert ok is False
    assert "empty" in (error or "").lower()
    helpers.default_provider.get_model_by_hash.assert_not_awaited()
    update_cache.assert_not_awaited()
    assert "civitai_deleted" not in model_data


@pytest.mark.asyncio
async def test_fetch_reports_a_missing_model_file_for_the_placeholder(tmp_path):
    helpers = build_service()
    model_data: Dict[str, Any] = {"file_path": str(tmp_path / "gone.safetensors")}

    ok, error = await helpers.service.fetch_and_update_model(
        sha256=EMPTY_HASH_SHA256,
        file_path=str(tmp_path / "gone.safetensors"),
        model_data=model_data,
        update_cache_func=AsyncMock(return_value=True),
    )

    assert ok is False
    assert "not found" in (error or "").lower()
    helpers.default_provider.get_model_by_hash.assert_not_awaited()


@pytest.mark.asyncio
async def test_foreign_source_link_skipped_for_the_empty_hash_placeholder():
    """No repository gets linked for a hash that identifies no file (#1162)."""
    helpers = build_service()

    linked = await helpers.service._try_link_foreign_source(
        sha256=EMPTY_HASH_SHA256,
        file_path="/tmp/Emilia(RE0).safetensors",
        model_data={"file_path": "/tmp/Emilia(RE0).safetensors"},
        update_cache_func=AsyncMock(return_value=True),
    )

    assert linked is False
    helpers.provider_selector.assert_not_awaited()


@pytest.mark.asyncio
async def test_relink_without_a_sidecar_rebuilds_the_required_local_fields(tmp_path):
    """Relinking after a manual sidecar deletion must write a parseable sidecar.

    Regression test for issue #1162: relinking from ``{}`` used to persist only
    the remote fields, so the next startup logged
    ``LoraMetadata.__init__() missing N required positional arguments`` and the
    scanner skipped the model forever.
    """
    import hashlib

    from py.utils.models import LoraMetadata

    provider = SimpleNamespace(
        get_model_by_hash=AsyncMock(),
        get_model_version=AsyncMock(
            return_value={
                "files": [
                    {"primary": True, "type": "Model", "hashes": {"SHA256": "ABCDEF"}}
                ],
                "model": {"name": "Remote"},
                "images": [],
            }
        ),
    )
    helpers = build_service(default_provider=provider)
    model_path = tmp_path / "Emilia(RE0).safetensors"
    content = b"real model bytes"
    model_path.write_bytes(content)

    result = await helpers.service.relink_metadata(
        file_path=str(model_path),
        metadata={},
        model_id=1,
        model_version_id=2,
    )

    parsed = LoraMetadata.from_dict(result)  # raises when a field is missing
    assert parsed.file_name == "Emilia(RE0)"
    assert parsed.file_path.endswith("Emilia(RE0).safetensors")
    assert parsed.size == len(content)
    assert parsed.sha256 == hashlib.sha256(content).hexdigest()
    assert parsed.model_name == "Remote"
    assert parsed.preview_url == ""


@pytest.mark.asyncio
async def test_relink_keeps_the_existing_payload_values(tmp_path):
    """A healthy sidecar is not rewritten from disk facts alone."""
    provider = SimpleNamespace(
        get_model_by_hash=AsyncMock(),
        get_model_version=AsyncMock(
            return_value={
                "files": [
                    {"primary": True, "type": "Model", "hashes": {"SHA256": "ABCDEF"}}
                ],
                "model": {"name": "Remote"},
                "images": [],
            }
        ),
    )
    helpers = build_service(default_provider=provider)
    model_path = tmp_path / "model.safetensors"
    model_path.write_bytes(b"real model bytes")

    result = await helpers.service.relink_metadata(
        file_path=str(model_path),
        metadata={"file_path": str(model_path), "model_name": "Local", "sha256": "original"},
        model_id=1,
        model_version_id=2,
    )

    assert result["sha256"] == "original"
    assert result["model_name"] == "Remote"

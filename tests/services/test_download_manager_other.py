"""DownloadManager support for the "other" model type (VAE, upscaler, ...).

Covers the Phase-2 scatter points from docs/plans/other-models-page.md §9.1:
type map acceptance, existence gates consulting the other scanner (never
falling through to the lora scanner), per-sub_type default roots, resume
metadata and the archive extension set.
"""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from py.services import aria2_transfer_state
from py.services import download_manager
from py.services.download_manager import DownloadManager
from py.services.service_registry import ServiceRegistry
from py.services.settings_manager import SettingsManager, get_settings_manager


@pytest.fixture(autouse=True)
def reset_download_manager():
    """Ensure each test operates on a fresh singleton."""
    DownloadManager._instance = None
    yield
    DownloadManager._instance = None


@pytest.fixture(autouse=True)
def isolate_settings(monkeypatch, tmp_path):
    """Point settings writes at a temporary directory to avoid touching real files."""
    manager = get_settings_manager()
    default_settings = manager._get_default_settings()
    default_settings.update(
        {
            "default_lora_root": str(tmp_path / "loras"),
            "default_checkpoint_root": str(tmp_path / "checkpoints"),
            "default_embedding_root": str(tmp_path / "embeddings"),
            "default_other_roots": {
                "vae": str(tmp_path / "vae"),
                "upscaler": str(tmp_path / "upscale_models"),
                "text_encoder": str(tmp_path / "text_encoders"),
                "clip_vision": str(tmp_path / "clip_vision"),
            },
            "enable_other_models": True,
            "enabled_other_sub_types": [
                "vae",
                "upscaler",
                "text_encoder",
                "clip_vision",
                "controlnet",
            ],
            "download_path_templates": {
                "lora": "{base_model}/{first_tag}",
                "checkpoint": "{base_model}/{first_tag}",
                "embedding": "{base_model}/{first_tag}",
                "other": "",
            },
            "skip_previously_downloaded_model_versions": False,
            "download_skip_base_models": [],
        }
    )
    monkeypatch.setattr(manager, "settings", default_settings)
    monkeypatch.setattr(SettingsManager, "_save_settings", lambda self: None)


@pytest.fixture(autouse=True)
def isolate_aria2_state(monkeypatch, tmp_path):
    state_path = tmp_path / "cache" / "aria2" / "downloads.json"
    monkeypatch.setattr(
        aria2_transfer_state,
        "get_aria2_state_path",
        lambda: str(state_path),
    )


@pytest.fixture(autouse=True)
def stub_metadata(monkeypatch):
    class _StubMetadata:
        def __init__(self, save_path: str):
            self.file_path = save_path
            self.sha256 = "sha256"
            self.file_name = Path(save_path).stem

    def _make_class(name):
        @staticmethod
        def from_civitai_info(_version_info, _file_info, save_path):
            metadata = _StubMetadata(save_path)
            metadata.metadata_class = name
            return metadata

        return type(name, (), {"from_civitai_info": from_civitai_info})

    monkeypatch.setattr(download_manager, "LoraMetadata", _make_class("LoraMetadata"))
    monkeypatch.setattr(
        download_manager, "CheckpointMetadata", _make_class("CheckpointMetadata")
    )
    monkeypatch.setattr(
        download_manager, "EmbeddingMetadata", _make_class("EmbeddingMetadata")
    )
    monkeypatch.setattr(
        download_manager, "OtherModelMetadata", _make_class("OtherModelMetadata")
    )


class DummyScanner:
    def __init__(self, exists: bool = False, raw_data=None):
        self.exists = exists
        self.calls = []
        self._cache = SimpleNamespace(raw_data=list(raw_data or []))

    async def check_model_version_exists(self, version_id):
        self.calls.append(version_id)
        return self.exists

    async def get_cached_data(self):
        return self._cache


@pytest.fixture
def scanners(monkeypatch):
    lora_scanner = DummyScanner()
    checkpoint_scanner = DummyScanner()
    embedding_scanner = DummyScanner()
    other_scanner = DummyScanner()

    monkeypatch.setattr(
        ServiceRegistry, "get_lora_scanner", AsyncMock(return_value=lora_scanner)
    )
    monkeypatch.setattr(
        ServiceRegistry,
        "get_checkpoint_scanner",
        AsyncMock(return_value=checkpoint_scanner),
    )
    monkeypatch.setattr(
        ServiceRegistry,
        "get_embedding_scanner",
        AsyncMock(return_value=embedding_scanner),
    )
    monkeypatch.setattr(
        ServiceRegistry,
        "get_other_scanner",
        AsyncMock(return_value=other_scanner),
    )

    return SimpleNamespace(
        lora=lora_scanner,
        checkpoint=checkpoint_scanner,
        embedding=embedding_scanner,
        other=other_scanner,
    )


def _other_payload(civitai_type: str, *, files=None) -> dict:
    return {
        "id": 42,
        "model": {"type": civitai_type, "tags": ["utility"]},
        "baseModel": "SDXL 1.0",
        "creator": {"username": "Author"},
        "files": files
        or [
            {
                "type": "Model",
                "primary": True,
                "downloadUrl": "https://example.invalid/file.safetensors",
                "name": "file.safetensors",
            }
        ],
    }


@pytest.fixture
def metadata_provider(monkeypatch):
    class DummyProvider:
        def __init__(self):
            self.calls = []
            self.payload = _other_payload("VAE")

        async def get_model_version(self, model_id, model_version_id):
            self.calls.append((model_id, model_version_id))
            return self.payload

    provider = DummyProvider()
    monkeypatch.setattr(
        download_manager,
        "get_default_metadata_provider",
        AsyncMock(return_value=provider),
    )
    return provider


def _capture_execute(monkeypatch, captured):
    async def fake_execute_download(self, **kwargs):
        captured.update(kwargs)
        return {"success": True}

    monkeypatch.setattr(
        DownloadManager, "_execute_download", fake_execute_download, raising=False
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "civitai_type",
    ["VAE", "Upscaler", "TextEncoder", "CLIP", "CLIPVision", "Controlnet", "Other"],
)
async def test_download_accepts_other_model_types(
    monkeypatch, scanners, metadata_provider, tmp_path, civitai_type
):
    """All VALID_OTHER_CIVITAI_TYPES route to model_type 'other'."""
    metadata_provider.payload = _other_payload(civitai_type)

    captured = {}
    _capture_execute(monkeypatch, captured)

    manager = DownloadManager()
    result = await manager.download_from_civitai(
        model_version_id=99, save_dir=str(tmp_path)
    )

    assert result["success"] is True
    assert captured["model_type"] == "other"
    assert captured["metadata"].metadata_class == "OtherModelMetadata"


@pytest.mark.asyncio
async def test_download_rejects_unknown_model_type(
    monkeypatch, scanners, metadata_provider, tmp_path
):
    metadata_provider.payload = _other_payload("Workflow")

    manager = DownloadManager()
    result = await manager.download_from_civitai(
        model_version_id=99, save_dir=str(tmp_path)
    )

    assert result["success"] is False
    assert result["error"].startswith("Model type")


@pytest.mark.asyncio
async def test_download_rejects_other_when_feature_disabled(
    monkeypatch, scanners, metadata_provider, tmp_path
):
    """The opt-in feature is off: no other-type download is accepted."""
    metadata_provider.payload = _other_payload("VAE")
    get_settings_manager().settings["enable_other_models"] = False

    manager = DownloadManager()
    result = await manager.download_from_civitai(
        model_version_id=99, save_dir=str(tmp_path)
    )

    assert result["success"] is False
    assert "disabled" in result["error"].lower()
    assert result["reason"] == "other_models_disabled"


@pytest.mark.asyncio
async def test_default_paths_reject_switched_off_sub_type(
    monkeypatch, scanners, metadata_provider, tmp_path
):
    """A disabled sub_type refuses default-path routing (manual pick still works)."""
    metadata_provider.payload = _other_payload("VAE")
    get_settings_manager().settings["enabled_other_sub_types"] = ["upscaler"]

    manager = DownloadManager()
    result = await manager.download_from_civitai(
        model_version_id=99, use_default_paths=True
    )

    assert result["success"] is False
    assert "disabled" in result["error"].lower()
    assert result["reason"] == "other_sub_type_disabled"


@pytest.mark.asyncio
async def test_early_gate_checks_other_scanner(
    monkeypatch, scanners, metadata_provider, tmp_path
):
    scanners.other.exists = True

    manager = DownloadManager()
    result = await manager.download_from_civitai(
        model_version_id=101, save_dir=str(tmp_path)
    )

    assert result["success"] is False
    assert result["error"] == "Model version already exists in other library"
    assert scanners.other.calls == [101]


@pytest.mark.asyncio
async def test_scanner_dispatch_has_no_lora_fall_through(scanners):
    """The Phase-2 trap: 'other' must reach the other scanner explicitly, and
    unknown types must raise instead of silently deduping against loras."""
    manager = DownloadManager()

    scanner = await manager._get_scanner_for_model_type("other")
    assert scanner is scanners.other

    scanner = await manager._get_scanner_for_model_type("lora")
    assert scanner is scanners.lora

    with pytest.raises(ValueError):
        await manager._get_scanner_for_model_type("bogus")


@pytest.mark.asyncio
async def test_explicit_file_gate_uses_other_scanner_not_lora(
    monkeypatch, scanners, metadata_provider, tmp_path
):
    """A matching local entry in the LORA library must not block an 'other'
    download; only the other scanner's library is consulted."""
    local_entry = {
        "file_name": "file",
        "sha256": "deadbeef",
        "civitai": {"id": 42},
    }
    scanners.lora._cache = SimpleNamespace(raw_data=[dict(local_entry)])
    scanners.other._cache = SimpleNamespace(raw_data=[])

    metadata_provider.payload = _other_payload(
        "VAE",
        files=[
            {
                "id": 7,
                "type": "Model",
                "primary": True,
                "name": "file.safetensors",
                "hashes": {"SHA256": "deadbeef"},
                "downloadUrl": "https://example.invalid/file.safetensors",
            }
        ],
    )

    captured = {}
    _capture_execute(monkeypatch, captured)

    manager = DownloadManager()
    result = await manager.download_from_civitai(
        model_version_id=42,
        save_dir=str(tmp_path),
        file_params={"id": 7, "type": "Model"},
    )

    assert result["success"] is True
    assert captured["model_type"] == "other"


@pytest.mark.asyncio
async def test_explicit_file_gate_blocks_when_other_scanner_has_file(
    monkeypatch, scanners, metadata_provider, tmp_path
):
    local_entry = {
        "file_name": "file",
        "sha256": "deadbeef",
        "civitai": {"id": 42},
    }
    scanners.other._cache = SimpleNamespace(raw_data=[dict(local_entry)])

    metadata_provider.payload = _other_payload(
        "VAE",
        files=[
            {
                "id": 7,
                "type": "Model",
                "primary": True,
                "name": "file.safetensors",
                "hashes": {"SHA256": "deadbeef"},
                "downloadUrl": "https://example.invalid/file.safetensors",
            }
        ],
    )

    execute_mock = AsyncMock(return_value={"success": True})
    monkeypatch.setattr(DownloadManager, "_execute_download", execute_mock)

    manager = DownloadManager()
    result = await manager.download_from_civitai(
        model_version_id=42,
        save_dir=str(tmp_path),
        file_params={"id": 7, "type": "Model"},
    )

    assert result["success"] is False
    assert "already exists in other library" in result["error"]
    assert execute_mock.await_count == 0


@pytest.mark.asyncio
async def test_version_level_fallback_gate_checks_other_scanner(
    monkeypatch, scanners, metadata_provider, tmp_path
):
    """file_params that resolve to nothing fall back to the version-level
    gate, which must consult the other scanner."""
    scanners.other.exists = True

    execute_mock = AsyncMock(return_value={"success": True})
    monkeypatch.setattr(DownloadManager, "_execute_download", execute_mock)

    manager = DownloadManager()
    result = await manager.download_from_civitai(
        model_version_id=101,
        save_dir=str(tmp_path),
        file_params={"id": 999999, "type": "Model"},
    )

    assert result["success"] is False
    assert result["error"] == "Model version already exists in other library"
    assert scanners.other.calls == [101]
    assert execute_mock.await_count == 0


@pytest.mark.asyncio
async def test_default_paths_use_per_sub_type_root(
    monkeypatch, scanners, metadata_provider, tmp_path
):
    """model.type VAE -> default_other_roots['vae']."""
    captured = {}
    _capture_execute(monkeypatch, captured)

    manager = DownloadManager()
    result = await manager.download_from_civitai(
        model_version_id=99, use_default_paths=True
    )

    assert result["success"] is True
    assert str(tmp_path / "vae") in str(captured["save_dir"])
    assert captured["relative_path"] == ""


@pytest.mark.asyncio
async def test_default_paths_other_is_flat_without_configured_template(
    monkeypatch, scanners, metadata_provider, tmp_path
):
    """Regression: an unconfigured 'other' template must resolve to a flat
    layout at the sub_type root instead of the {base_model}/{first_tag}
    fallback (which scattered files into arbitrary CivitAI-tag folders)."""
    get_settings_manager().settings["download_path_templates"].pop("other", None)

    captured = {}
    _capture_execute(monkeypatch, captured)

    manager = DownloadManager()
    result = await manager.download_from_civitai(
        model_version_id=99, use_default_paths=True
    )

    assert result["success"] is True
    assert captured["relative_path"] == ""
    assert str(tmp_path / "vae") in str(captured["save_dir"])


@pytest.mark.asyncio
async def test_default_paths_file_type_fallback_for_unmapped_model_type(
    monkeypatch, scanners, metadata_provider, tmp_path
):
    """model.type 'Other' maps to nothing; a 'Upscaler' file type decides."""
    metadata_provider.payload = _other_payload(
        "Other",
        files=[
            {
                "type": "Upscaler",
                "primary": True,
                "downloadUrl": "https://example.invalid/upscaler.safetensors",
                "name": "upscaler.safetensors",
            }
        ],
    )

    captured = {}
    _capture_execute(monkeypatch, captured)

    manager = DownloadManager()
    result = await manager.download_from_civitai(
        model_version_id=99, use_default_paths=True
    )

    assert result["success"] is True
    assert str(tmp_path / "upscale_models") in str(captured["save_dir"])


@pytest.mark.asyncio
async def test_default_paths_explicit_file_pick_wins(
    monkeypatch, scanners, metadata_provider, tmp_path
):
    """An explicit pick of a bundled VAE component file routes to the vae
    root even though model.type maps to upscaler."""
    metadata_provider.payload = _other_payload(
        "Upscaler",
        files=[
            {
                "id": 1,
                "type": "Model",
                "primary": True,
                "downloadUrl": "https://example.invalid/model.safetensors",
                "name": "model.safetensors",
            },
            {
                "id": 2,
                "type": "VAE",
                "downloadUrl": "https://example.invalid/bundled-vae.safetensors",
                "name": "bundled-vae.safetensors",
            },
        ],
    )

    captured = {}
    _capture_execute(monkeypatch, captured)

    manager = DownloadManager()
    result = await manager.download_from_civitai(
        model_version_id=99,
        use_default_paths=True,
        file_params={"id": 2, "type": "VAE"},
    )

    assert result["success"] is True
    assert str(tmp_path / "vae") in str(captured["save_dir"])
    assert captured["download_urls"] == [
        "https://example.invalid/bundled-vae.safetensors"
    ]


@pytest.mark.asyncio
async def test_default_paths_errors_when_sub_type_root_unconfigured(
    monkeypatch, scanners, metadata_provider, tmp_path
):
    """controlnet has no configured default root in the fixture settings."""
    metadata_provider.payload = _other_payload("Controlnet")

    execute_mock = AsyncMock(return_value={"success": True})
    monkeypatch.setattr(DownloadManager, "_execute_download", execute_mock)

    manager = DownloadManager()
    result = await manager.download_from_civitai(
        model_version_id=99, use_default_paths=True
    )

    assert result["success"] is False
    assert "controlnet" in result["error"]
    assert result["reason"] == "other_no_default_root"
    assert execute_mock.await_count == 0


@pytest.mark.asyncio
async def test_default_paths_errors_when_sub_type_undecidable(
    monkeypatch, scanners, metadata_provider, tmp_path
):
    """model.type 'Other' with only plain 'Model' files: never silently
    default to the vae folder — error and ask for an explicit folder."""
    metadata_provider.payload = _other_payload("Other")

    execute_mock = AsyncMock(return_value={"success": True})
    monkeypatch.setattr(DownloadManager, "_execute_download", execute_mock)

    manager = DownloadManager()
    result = await manager.download_from_civitai(
        model_version_id=99, use_default_paths=True
    )

    assert result["success"] is False
    assert "sub-type" in result["error"]
    assert result["reason"] == "other_sub_type_undecidable"
    assert execute_mock.await_count == 0


@pytest.mark.asyncio
async def test_civarchive_source_same_payload_shape(
    monkeypatch, scanners, metadata_provider, tmp_path
):
    """CivArchive downloads walk the same path with the same payload shape."""
    metadata_provider.payload = _other_payload("TextEncoder")

    captured = {}
    _capture_execute(monkeypatch, captured)

    manager = DownloadManager()
    result = await manager.download_from_civitai(
        model_version_id=99, save_dir=str(tmp_path), source="civarchive"
    )

    assert result["success"] is True
    assert captured["model_type"] == "other"


@pytest.mark.asyncio
async def test_other_failure_reasons_are_machine_readable(
    monkeypatch, scanners, metadata_provider, tmp_path
):
    """Contract C4: every other-type default-path failure carries a ``reason``.

    The companion browser extension binds to ``reason`` and only falls back to
    substring matching for backends that predate the field, so the exact values
    below must not drift.
    """
    expected_reasons = {
        "disabled": "other_models_disabled",
        "sub_type_disabled": "other_sub_type_disabled",
        "no_default_root": "other_no_default_root",
        "undecidable": "other_sub_type_undecidable",
    }
    reasons: dict[str, str] = {}

    manager = DownloadManager()

    # 1. Master switch off.
    metadata_provider.payload = _other_payload("VAE")
    get_settings_manager().settings["enable_other_models"] = False
    disabled = await manager.download_from_civitai(
        model_version_id=99, save_dir=str(tmp_path)
    )
    reasons["disabled"] = disabled["reason"]
    assert disabled["error"].strip()

    get_settings_manager().settings["enable_other_models"] = True

    # 2. Resolved sub_type not enabled.
    get_settings_manager().settings["enabled_other_sub_types"] = ["upscaler"]
    sub_type_disabled = await manager.download_from_civitai(
        model_version_id=99, use_default_paths=True
    )
    reasons["sub_type_disabled"] = sub_type_disabled["reason"]
    assert sub_type_disabled["error"].strip()

    get_settings_manager().settings["enabled_other_sub_types"] = [
        "vae",
        "upscaler",
        "text_encoder",
        "clip_vision",
        "controlnet",
    ]

    # 3. Sub_type resolved but no default root configured.
    metadata_provider.payload = _other_payload("Controlnet")
    no_default_root = await manager.download_from_civitai(
        model_version_id=99, use_default_paths=True
    )
    reasons["no_default_root"] = no_default_root["reason"]
    assert no_default_root["error"].strip()

    # 4. Neither model.type nor file types map to a sub_type.
    metadata_provider.payload = _other_payload("Other")
    undecidable = await manager.download_from_civitai(
        model_version_id=99, use_default_paths=True
    )
    reasons["undecidable"] = undecidable["reason"]
    assert undecidable["error"].strip()

    assert reasons == expected_reasons


def test_build_metadata_for_resume_uses_other_metadata():
    manager = DownloadManager()
    metadata = manager._build_metadata_for_resume(
        model_type="other",
        version_info={"model": {"type": "VAE"}},
        file_info={"name": "file.safetensors"},
        save_path="/tmp/file.safetensors",
    )
    assert metadata.metadata_class == "OtherModelMetadata"


def test_other_extension_set_matches_checkpoint():
    manager = DownloadManager()
    extensions = manager._get_supported_extensions_for_type("other")
    assert extensions == manager._get_supported_extensions_for_type("checkpoint")
    assert ".gguf" in extensions
    assert ".safetensors" in extensions


@pytest.mark.asyncio
async def test_sync_downloaded_version_uses_other_scanner(monkeypatch, scanners):
    """Update tracking for a downloaded other-model version consults the
    other scanner for local versions."""

    class FakeUpdateService:
        def __init__(self):
            self.calls = []

        async def update_in_library_versions(
            self, model_type, model_id, version_ids, version_info=None
        ):
            self.calls.append((model_type, model_id, version_ids))

    update_service = FakeUpdateService()
    monkeypatch.setattr(
        ServiceRegistry,
        "get_model_update_service",
        AsyncMock(return_value=update_service),
    )

    manager = DownloadManager()
    await manager._sync_downloaded_version(
        "other", 7, {"id": 42, "model": {"id": 7}}
    )

    assert update_service.calls == [("other", 7, [42])]

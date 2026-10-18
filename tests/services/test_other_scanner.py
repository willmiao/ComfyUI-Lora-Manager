"""Tests for OtherScanner: root aggregation, sub_type derivation, lazy hash."""

import asyncio
import json
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from py import config as config_module
from py.services import model_scanner
from py.services.model_scanner import ModelScanner
from py.services.other_scanner import OtherScanner
from py.utils.models import OtherModelMetadata


def _normalize(path) -> str:
    return str(path).replace(os.sep, "/")


@pytest.fixture(autouse=True)
def reset_model_scanner_singletons():
    ModelScanner._instances.clear()
    ModelScanner._locks.clear()
    yield
    ModelScanner._instances.clear()
    ModelScanner._locks.clear()


@pytest.fixture
def other_config(monkeypatch, tmp_path):
    """Point the global config at a synthetic set of other-model roots."""
    vae_root = tmp_path / "vae"
    upscaler_root = tmp_path / "upscale_models"
    te_root = tmp_path / "text_encoders"
    clip_root = tmp_path / "clip"
    clip_vision_root = tmp_path / "clip_vision"
    for root in (vae_root, upscaler_root, te_root, clip_root, clip_vision_root):
        root.mkdir()

    roots = [
        _normalize(vae_root),
        _normalize(upscaler_root),
        _normalize(te_root),
        _normalize(clip_root),
        _normalize(clip_vision_root),
    ]
    subtypes = {
        _normalize(vae_root): "vae",
        _normalize(upscaler_root): "upscaler",
        _normalize(te_root): "text_encoder",
        _normalize(clip_root): "text_encoder",
        _normalize(clip_vision_root): "clip_vision",
    }
    monkeypatch.setattr(config_module.config, "other_roots", roots)
    monkeypatch.setattr(config_module.config, "other_root_subtypes", subtypes)
    return {
        "roots": roots,
        "subtypes": subtypes,
        "vae": _normalize(vae_root),
        "upscaler": _normalize(upscaler_root),
        "text_encoders": _normalize(te_root),
        "clip": _normalize(clip_root),
        "clip_vision": _normalize(clip_vision_root),
    }


def _make_scanner() -> OtherScanner:
    """Create a scanner without __init__ to avoid async initialization."""
    scanner = object.__new__(OtherScanner)
    scanner.model_type = "other"
    scanner.model_class = OtherModelMetadata
    scanner.file_extensions = {".safetensors", ".pt", ".bin"}
    scanner._hash_index = MagicMock()
    return scanner


class TestOtherScannerRoots:
    """Root aggregation and sub_type resolution."""

    def test_get_model_roots_aggregates_and_dedupes(self, other_config, monkeypatch):
        scanner = _make_scanner()
        monkeypatch.setattr(
            config_module.config,
            "other_roots",
            other_config["roots"] + [other_config["vae"]],
        )
        roots = scanner.get_model_roots()
        assert roots == other_config["roots"]

    def test_get_model_roots_empty_when_unconfigured(self, monkeypatch):
        scanner = _make_scanner()
        monkeypatch.setattr(config_module.config, "other_roots", None)
        assert scanner.get_model_roots() == []

    def test_resolve_sub_type_for_each_default_category(self, other_config):
        scanner = _make_scanner()
        cases = [
            (other_config["vae"], "vae"),
            (other_config["upscaler"], "upscaler"),
            (other_config["text_encoders"], "text_encoder"),
            # Legacy ComfyUI 'clip' key maps to text_encoder as well
            (other_config["clip"], "text_encoder"),
            (other_config["clip_vision"], "clip_vision"),
        ]
        for root, expected in cases:
            file_path = f"{root}/model.safetensors"
            assert scanner.resolve_sub_type_for_path(file_path) == expected

    def test_resolve_sub_type_longest_prefix_wins(self, monkeypatch, tmp_path):
        """A nested root (controlnet inside vae) resolves to the inner category."""
        outer = tmp_path / "vae"
        inner = outer / "controlnet"
        inner.mkdir(parents=True)
        monkeypatch.setattr(
            config_module.config,
            "other_root_subtypes",
            {_normalize(outer): "vae", _normalize(inner): "controlnet"},
        )
        scanner = _make_scanner()
        assert (
            scanner.resolve_sub_type_for_path(f"{_normalize(inner)}/cn.safetensors")
            == "controlnet"
        )
        assert (
            scanner.resolve_sub_type_for_path(f"{_normalize(outer)}/vae.safetensors")
            == "vae"
        )

    def test_resolve_sub_type_none_for_unknown_or_empty(self, other_config):
        scanner = _make_scanner()
        assert scanner.resolve_sub_type_for_path(None) is None
        assert scanner.resolve_sub_type_for_path("") is None
        assert scanner.resolve_sub_type_for_path("/unrelated/model.safetensors") is None

    def test_adjust_metadata_sets_sub_type(self, other_config):
        scanner = _make_scanner()
        metadata = OtherModelMetadata(
            file_name="te",
            model_name="te",
            file_path=f"{other_config['text_encoders']}/te.safetensors",
            size=1,
            modified=0.0,
            sha256="",
            base_model="Unknown",
            preview_url="",
        )
        result = scanner.adjust_metadata(
            metadata,
            metadata.file_path,
            other_config["text_encoders"],
        )
        assert result.sub_type == "text_encoder"

    def test_adjust_cached_entry_rederives_sub_type(self, other_config):
        """Persisted sub_type is never trusted: it is re-derived from location."""
        scanner = _make_scanner()
        entry = {
            "file_path": f"{other_config['clip']}/legacy.safetensors",
            "sub_type": "vae",  # stale value from an old snapshot
        }
        result = scanner.adjust_cached_entry(entry)
        assert result["sub_type"] == "text_encoder"

    def test_adjust_cached_entry_keeps_value_when_root_unknown(self, other_config):
        scanner = _make_scanner()
        entry = {
            "file_path": "/gone/model.safetensors",
            "sub_type": "upscaler",
        }
        result = scanner.adjust_cached_entry(entry)
        assert result["sub_type"] == "upscaler"


class TestOtherScannerHydrationFilter:
    """Persisted entries for roots that are no longer managed are dropped."""

    def test_keeps_entries_under_enabled_roots(self, other_config):
        scanner = _make_scanner()
        assert (
            scanner._should_keep_cached_entry(
                {"file_path": f"{other_config['vae']}/model.safetensors"}
            )
            is True
        )

    def test_drops_entries_under_disabled_root(self, other_config, monkeypatch):
        scanner = _make_scanner()
        # Only vae stays managed; the upscaler root disappeared from the map.
        monkeypatch.setattr(
            config_module.config,
            "other_root_subtypes",
            {other_config["vae"]: "vae"},
        )

        assert (
            scanner._should_keep_cached_entry(
                {"file_path": f"{other_config['upscaler']}/model.safetensors"}
            )
            is False
        )
        assert (
            scanner._should_keep_cached_entry(
                {"file_path": f"{other_config['vae']}/model.safetensors"}
            )
            is True
        )

    def test_drops_everything_when_feature_off(self, monkeypatch):
        monkeypatch.setattr(config_module.config, "other_root_subtypes", {})
        scanner = _make_scanner()
        assert (
            scanner._should_keep_cached_entry(
                {"file_path": "/models/vae/model.safetensors"}
            )
            is False
        )


class TestOtherScannerLazyHash:
    """Lazy hashing: pending by default, singleflight on-demand calculation."""

    @pytest.mark.asyncio
    async def test_default_metadata_has_pending_hash(self, other_config):
        vae_file = Path(other_config["vae"]) / "vae_model.safetensors"
        vae_file.write_text("fake vae content", encoding="utf-8")

        scanner = OtherScanner()
        metadata = await scanner._create_default_metadata(_normalize(vae_file))

        assert metadata is not None
        assert metadata.sha256 == ""
        assert metadata.hash_status == "pending"
        assert metadata.from_civitai is False
        assert metadata.sub_type == "vae"

    @pytest.mark.asyncio
    async def test_default_metadata_sub_type_from_location(self, other_config):
        te_file = Path(other_config["text_encoders"]) / "t5.safetensors"
        te_file.write_text("fake text encoder", encoding="utf-8")

        scanner = OtherScanner()
        metadata = await scanner._create_default_metadata(_normalize(te_file))

        assert metadata is not None
        assert metadata.sub_type == "text_encoder"

    @pytest.mark.asyncio
    async def test_calculate_hash_for_model_completes_pending(self, other_config):
        model_file = Path(other_config["upscaler"]) / "upscaler.safetensors"
        model_file.write_text("fake upscaler content", encoding="utf-8")
        normalized_file = _normalize(model_file)

        scanner = OtherScanner()
        metadata = await scanner._create_default_metadata(normalized_file)
        assert metadata is not None and metadata.hash_status == "pending"

        hash_result = await scanner.calculate_hash_for_model(normalized_file)

        assert hash_result is not None
        assert len(hash_result) == 64

        metadata_file = model_file.with_suffix(".metadata.json")
        saved_data = json.loads(metadata_file.read_text(encoding="utf-8"))
        assert saved_data["sha256"] == hash_result
        assert saved_data["hash_status"] == "completed"

    @pytest.mark.asyncio
    async def test_calculate_hash_singleflight_same_file(self, other_config):
        """Concurrent calls for the same file share one SHA256 task."""
        model_file = Path(other_config["vae"]) / "shared.safetensors"
        model_file.write_text("fake content", encoding="utf-8")
        normalized_file = _normalize(model_file)
        real_file = os.path.realpath(normalized_file)

        scanner = OtherScanner()
        metadata = await scanner._create_default_metadata(normalized_file)
        assert metadata is not None

        calls = []

        async def fake_calculate_sha256(file_path: str) -> str:
            calls.append(file_path)
            await asyncio.sleep(0.01)
            return "a" * 64

        with patch(
            "py.utils.file_utils.calculate_sha256", side_effect=fake_calculate_sha256
        ):
            results = await asyncio.gather(
                *[scanner.calculate_hash_for_model(normalized_file) for _ in range(8)]
            )

        assert calls == [real_file]
        assert results == ["a" * 64] * 8
        assert scanner._hash_calculation_tasks == {}

    @pytest.mark.asyncio
    async def test_calculate_hash_skips_completed(self, other_config):
        model_file = Path(other_config["clip_vision"]) / "cv.safetensors"
        model_file.write_text("fake content", encoding="utf-8")
        normalized_file = _normalize(model_file)

        scanner = OtherScanner()
        metadata = await scanner._create_default_metadata(normalized_file)
        assert metadata is not None
        # Simulate an already-completed hash
        metadata.sha256 = "existing_hash"
        metadata.hash_status = "completed"
        from py.utils.metadata_manager import MetadataManager

        await MetadataManager.save_metadata(normalized_file, metadata)

        with patch("py.utils.file_utils.calculate_sha256") as mock_calc:
            hash_result = await scanner.calculate_hash_for_model(normalized_file)

        assert hash_result == "existing_hash"
        mock_calc.assert_not_called()

    @pytest.mark.asyncio
    async def test_calculate_all_pending_hashes(self, other_config):
        for index in range(3):
            model_file = Path(other_config["vae"]) / f"model_{index}.safetensors"
            model_file.write_text(f"content {index}", encoding="utf-8")

        scanner = OtherScanner()
        for index in range(3):
            model_file = Path(other_config["vae"]) / f"model_{index}.safetensors"
            await scanner._create_default_metadata(_normalize(model_file))

        progress_calls = []

        async def progress_callback(current, total, file_path):
            progress_calls.append((current, total, file_path))

        result = await scanner.calculate_all_pending_hashes(progress_callback)

        assert result["total"] == 3
        assert result["completed"] == 3
        assert result["failed"] == 0
        assert len(progress_calls) == 3


class TestOtherModelMetadataFromCivitai:
    """CivitAI type mapping in OtherModelMetadata.from_civitai_info."""

    def _build(self, civitai_type: str) -> OtherModelMetadata:
        return OtherModelMetadata.from_civitai_info(
            {
                "baseModel": "SDXL",
                "model": {
                    "name": "Model",
                    "tags": ["tag"],
                    "description": "desc",
                    "type": civitai_type,
                },
            },
            {"name": "model.safetensors", "sizeKB": 1, "hashes": {"SHA256": "AB"}},
            "/tmp/model.safetensors",
        )

    @pytest.mark.parametrize(
        "civitai_type,expected",
        [
            ("VAE", "vae"),
            ("Upscaler", "upscaler"),
            ("TextEncoder", "text_encoder"),
            ("CLIP", "text_encoder"),
            ("CLIPVision", "clip_vision"),
            ("Controlnet", "controlnet"),
            ("Other", "vae"),  # unknown types fall back to the placeholder
        ],
    )
    def test_civitai_type_mapping(self, civitai_type, expected):
        metadata = self._build(civitai_type)
        assert metadata.sub_type == expected
        assert metadata.sha256 == "ab"
        assert metadata.tags == ["tag"]

    def test_top_level_type_key_is_ignored(self):
        """Regression: the CivitAI type lives at version["model"]["type"]; a
        top-level version["type"] key must not drive the mapping (#Phase-1 bug)."""
        metadata = OtherModelMetadata.from_civitai_info(
            {
                "type": "Upscaler",
                "baseModel": "SDXL",
                "model": {"name": "Model", "type": "VAE"},
            },
            {"name": "model.safetensors", "sizeKB": 1, "hashes": {"SHA256": "AB"}},
            "/tmp/model.safetensors",
        )
        assert metadata.sub_type == "vae"


def test_page_type_maps_to_other():
    """The WS progress page type for the other scanner is 'other'."""
    assert model_scanner.PAGE_TYPE_MAP["other"] == "other"
    scanner = _make_scanner()
    assert scanner.page_type == "other"

"""Tests for the AgentCLI module (py/agent_cli/).

All tests mock the underlying services (scanner, MetadataManager, downloader)
since the AgentCLI is a thin delegation layer.

Mock targets must match where imports are resolved inside each function
(lazy imports via ``from X import Y`` inside function body).
"""

from __future__ import annotations

from unittest import mock

import pytest

from py.agent_cli import (
    list_base_models,
    read_metadata,
    apply_metadata_updates,
    download_preview,
    refresh_cache,
)


# ======================================================================
# Helpers
# ======================================================================


class MockCache:
    def __init__(self, raw_data: list[dict] | None = None):
        self.raw_data = raw_data or []


class MockScanner:
    """Simulates a ModelScanner for testing."""

    def __init__(self, raw_data: list[dict] | None = None):
        self._raw_data = raw_data or []
        self.update_single_model_cache = mock.AsyncMock(return_value=True)

    async def get_cached_data(self):
        return MockCache(self._raw_data)


# ======================================================================
# list_base_models  --  imports ServiceRegistry internally
# ======================================================================


class TestListBaseModels:

    @pytest.mark.asyncio
    async def test_empty_cache(self):
        scanner = MockScanner([])
        with mock.patch(
            "py.services.service_registry.ServiceRegistry",
            get_lora_scanner=mock.AsyncMock(return_value=scanner),
            get_checkpoint_scanner=mock.AsyncMock(return_value=None),
            get_embedding_scanner=mock.AsyncMock(return_value=None),
        ):
            result = await list_base_models()
        assert result == []

    @pytest.mark.asyncio
    async def test_merges_all_scanners(self):
        lora_scanner = MockScanner([
            {"base_model": "SDXL 1.0"},
            {"base_model": "Flux.1 D"},
            {"base_model": "SDXL 1.0"},
        ])
        ckpt_scanner = MockScanner([
            {"base_model": "SDXL 1.0"},
            {"base_model": "SD 1.5"},
        ])
        with mock.patch(
            "py.services.service_registry.ServiceRegistry",
            get_lora_scanner=mock.AsyncMock(return_value=lora_scanner),
            get_checkpoint_scanner=mock.AsyncMock(return_value=ckpt_scanner),
            get_embedding_scanner=mock.AsyncMock(return_value=None),
        ):
            result = await list_base_models()
        assert result == ["SDXL 1.0", "Flux.1 D", "SD 1.5"]

    @pytest.mark.asyncio
    async def test_limit(self):
        scanner = MockScanner([
            {"base_model": "A"}, {"base_model": "B"}, {"base_model": "C"},
        ])
        with mock.patch(
            "py.services.service_registry.ServiceRegistry",
            get_lora_scanner=mock.AsyncMock(return_value=scanner),
            get_checkpoint_scanner=mock.AsyncMock(return_value=None),
            get_embedding_scanner=mock.AsyncMock(return_value=None),
        ):
            result = await list_base_models(limit=2)
        assert result == ["A", "B"]

    @pytest.mark.asyncio
    async def test_all_scanners_return_none(self):
        with mock.patch(
            "py.services.service_registry.ServiceRegistry",
            get_lora_scanner=mock.AsyncMock(return_value=None),
            get_checkpoint_scanner=mock.AsyncMock(return_value=None),
            get_embedding_scanner=mock.AsyncMock(return_value=None),
        ):
            result = await list_base_models()
        assert result == []

    @pytest.mark.asyncio
    async def test_skips_empty_or_missing_base_model(self):
        scanner = MockScanner([
            {"base_model": "SDXL 1.0"},
            {"file_name": "foo.safetensors"},  # no base_model key
            {"base_model": ""},                 # empty
        ])
        with mock.patch(
            "py.services.service_registry.ServiceRegistry",
            get_lora_scanner=mock.AsyncMock(return_value=scanner),
            get_checkpoint_scanner=mock.AsyncMock(return_value=None),
            get_embedding_scanner=mock.AsyncMock(return_value=None),
        ):
            result = await list_base_models()
        assert result == ["SDXL 1.0"]


# ======================================================================
# read_metadata  --  imports MetadataManager from py.utils.metadata_manager
# ======================================================================


class TestReadMetadata:

    @pytest.mark.asyncio
    async def test_delegates_to_metadata_manager(self):
        fake = {"file_name": "test", "base_model": "SDXL 1.0"}
        with mock.patch("py.utils.metadata_manager.MetadataManager") as mm:
            mm.load_metadata_payload = mock.AsyncMock(return_value=fake)
            result = await read_metadata("/p.safetensors")
        assert result == fake

    @pytest.mark.asyncio
    async def test_exception_returns_empty_dict(self):
        with mock.patch("py.utils.metadata_manager.MetadataManager") as mm:
            mm.load_metadata_payload = mock.AsyncMock(side_effect=ValueError("x"))
            result = await read_metadata("/p.safetensors")
        assert result == {}

    @pytest.mark.asyncio
    async def test_none_coerces_to_empty_dict(self):
        with mock.patch("py.utils.metadata_manager.MetadataManager") as mm:
            mm.load_metadata_payload = mock.AsyncMock(return_value=None)
            result = await read_metadata("/p.safetensors")
        assert result == {}


# ======================================================================
# apply_metadata_updates  --  uses read_metadata + MetadataManager.save_metadata
# ======================================================================


class TestApplyMetadataUpdates:

    @pytest.mark.asyncio
    async def test_updates_field(self):
        with (
            mock.patch("py.agent_cli.read_metadata") as mock_read,
            mock.patch("py.utils.metadata_manager.MetadataManager") as mm,
        ):
            mock_read.return_value = {"base_model": "", "tags": []}
            mm.save_metadata = mock.AsyncMock(return_value=True)
            updated = await apply_metadata_updates(
                "/p.safetensors", {"base_model": "Flux.1 D"}
            )
        assert updated == ["base_model"]
        mm.save_metadata.assert_awaited_once_with(
            "/p.safetensors", {"base_model": "Flux.1 D", "tags": []},
        )

    @pytest.mark.asyncio
    async def test_noop_when_value_unchanged(self):
        with (
            mock.patch("py.agent_cli.read_metadata") as mock_read,
            mock.patch("py.utils.metadata_manager.MetadataManager") as mm,
        ):
            mock_read.return_value = {"base_model": "Flux.1 D"}
            updated = await apply_metadata_updates(
                "/p.safetensors", {"base_model": "Flux.1 D"}
            )
        assert updated == []
        mm.save_metadata.assert_not_called()

    @pytest.mark.asyncio
    async def test_multiple_fields(self):
        with (
            mock.patch("py.agent_cli.read_metadata") as mock_read,
            mock.patch("py.utils.metadata_manager.MetadataManager") as mm,
        ):
            mm.save_metadata = mock.AsyncMock(return_value=True)
            mock_read.return_value = {
                "base_model": "", "modelDescription": "", "tags": [],
            }
            updated = await apply_metadata_updates(
                "/p.safetensors",
                {"base_model": "SDXL 1.0", "modelDescription": "A", "tags": ["flux"]},
            )
        assert sorted(updated) == sorted(["base_model", "modelDescription", "tags"])
        saved = mm.save_metadata.call_args[0][1]
        assert saved["base_model"] == "SDXL 1.0"

    @pytest.mark.asyncio
    async def test_empty_updates_noop(self):
        with (
            mock.patch("py.agent_cli.read_metadata"),
            mock.patch("py.utils.metadata_manager.MetadataManager") as mm,
        ):
            updated = await apply_metadata_updates("/p.safetensors", {})
        assert updated == []
        mm.save_metadata.assert_not_called()


# ======================================================================
# download_preview  --  imports get_downloader + ExifUtils
# ======================================================================


class TestDownloadPreview:

    @pytest.mark.asyncio
    async def test_empty_url_returns_false(self, tmp_path):
        mp = tmp_path / "m.safetensors"
        mp.write_bytes(b"fake")
        assert await download_preview(str(mp), "") is False
        assert await download_preview(str(mp), "   ") is False

    @pytest.mark.asyncio
    async def test_successful_download_and_optimise(self, tmp_path):
        mp = tmp_path / "t.safetensors"
        mp.write_bytes(b"fake")
        with (
            mock.patch("py.services.downloader.get_downloader") as get_dl,
            mock.patch("py.utils.exif_utils.ExifUtils") as exif,
        ):
            dl = mock.AsyncMock()
            dl.download_to_memory = mock.AsyncMock(return_value=(True, b"raw", {}))
            get_dl.return_value = dl
            exif.optimize_image.return_value = (b"optimized_webp", {})
            result = await download_preview(str(mp), "https://ex.com/i.png")
        assert result is True
        assert (tmp_path / "t.webp").exists()
        assert (tmp_path / "t.webp").read_bytes() == b"optimized_webp"

    @pytest.mark.asyncio
    async def test_download_failure_returns_false(self, tmp_path):
        mp = tmp_path / "t.safetensors"
        mp.write_bytes(b"fake")
        with mock.patch("py.services.downloader.get_downloader") as get_dl:
            dl = mock.AsyncMock()
            dl.download_to_memory = mock.AsyncMock(return_value=(False, None, {}))
            dl.download_file = mock.AsyncMock(return_value=(False, None))
            get_dl.return_value = dl
            result = await download_preview(str(mp), "https://ex.com/i.png")
        assert result is False
        assert not (tmp_path / "t.webp").exists()


# ======================================================================
# refresh_cache  --  uses _find_scanner_for_model (ServiceRegistry)
# ======================================================================


class TestRefreshCache:

    @pytest.mark.asyncio
    async def test_found_and_refreshed(self):
        scanner = MockScanner([{"file_path": "/some/path.safetensors"}])
        with (
            mock.patch(
                "py.services.service_registry.ServiceRegistry",
                get_lora_scanner=mock.AsyncMock(return_value=scanner),
                get_checkpoint_scanner=mock.AsyncMock(return_value=None),
                get_embedding_scanner=mock.AsyncMock(return_value=None),
            ),
            mock.patch("py.agent_cli.read_metadata") as mock_read,
        ):
            mock_read.return_value = {"base_model": "SDXL 1.0"}
            result = await refresh_cache("/some/path.safetensors")
        assert result is True
        scanner.update_single_model_cache.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_not_found_in_any_scanner(self):
        scanner = MockScanner([])
        with mock.patch(
            "py.services.service_registry.ServiceRegistry",
            get_lora_scanner=mock.AsyncMock(return_value=scanner),
            get_checkpoint_scanner=mock.AsyncMock(return_value=None),
            get_embedding_scanner=mock.AsyncMock(return_value=None),
        ):
            result = await refresh_cache("/nonexistent/path.safetensors")
        assert result is False

    @pytest.mark.asyncio
    async def test_no_metadata_returns_false(self):
        scanner = MockScanner([{"file_path": "/some/path.safetensors"}])
        with (
            mock.patch(
                "py.services.service_registry.ServiceRegistry",
                get_lora_scanner=mock.AsyncMock(return_value=scanner),
                get_checkpoint_scanner=mock.AsyncMock(return_value=None),
                get_embedding_scanner=mock.AsyncMock(return_value=None),
            ),
            mock.patch("py.agent_cli.read_metadata") as mock_read,
        ):
            mock_read.return_value = {}
            result = await refresh_cache("/some/path.safetensors")
        assert result is False

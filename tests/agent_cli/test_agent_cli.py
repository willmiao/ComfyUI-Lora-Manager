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
    async def test_empty_url_returns_none(self, tmp_path):
        mp = tmp_path / "m.safetensors"
        mp.write_bytes(b"fake")
        assert await download_preview(str(mp), "") is None
        assert await download_preview(str(mp), "   ") is None

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
        assert result == str(tmp_path / "t.webp")
        assert (tmp_path / "t.webp").exists()
        assert (tmp_path / "t.webp").read_bytes() == b"optimized_webp"

    @pytest.mark.asyncio
    async def test_download_failure_returns_none(self, tmp_path):
        mp = tmp_path / "t.safetensors"
        mp.write_bytes(b"fake")
        with mock.patch("py.services.downloader.get_downloader") as get_dl:
            dl = mock.AsyncMock()
            dl.download_to_memory = mock.AsyncMock(return_value=(False, None, {}))
            dl.download_file = mock.AsyncMock(return_value=(False, None))
            get_dl.return_value = dl
            result = await download_preview(str(mp), "https://ex.com/i.png")
        assert result is None
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


# ======================================================================
# convert_readme_to_html  —  pure function, no mocks needed
# ======================================================================


class TestConvertReadmeToHtml:
    """Tests for the inline markdown→HTML converter."""

    def test_empty_input(self):
        from py.services.agent.skills.enrich_hf_metadata.md_to_html import \
            convert_readme_to_html

        assert convert_readme_to_html("") == ""
        assert convert_readme_to_html(None) == ""  # type: ignore[arg-type]

    def test_heading(self):
        from py.services.agent.skills.enrich_hf_metadata.md_to_html import \
            convert_readme_to_html

        result = convert_readme_to_html("# Title")
        assert "<h1>" in result and "Title" in result

    def test_subheadings(self):
        from py.services.agent.skills.enrich_hf_metadata.md_to_html import \
            convert_readme_to_html

        md = "## Overview\n\n### Details"
        result = convert_readme_to_html(md)
        assert "<h2>Overview</h2>" in result
        assert "<h3>Details</h3>" in result

    def test_bold_and_italic(self):
        from py.services.agent.skills.enrich_hf_metadata.md_to_html import \
            convert_readme_to_html

        md = "**bold** and *italic*"
        result = convert_readme_to_html(md)
        assert "<strong>bold</strong>" in result
        assert "<em>italic</em>" in result

    def test_inline_code(self):
        from py.services.agent.skills.enrich_hf_metadata.md_to_html import \
            convert_readme_to_html

        md = "Use `model.train()`"
        result = convert_readme_to_html(md)
        assert "<code>" in result and "model.train()" in result

    def test_fenced_code_block(self):
        from py.services.agent.skills.enrich_hf_metadata.md_to_html import \
            convert_readme_to_html

        md = "```python\nprint('hello')\n```"
        result = convert_readme_to_html(md)
        assert "<pre>" in result
        assert "print" in result and "hello" in result

    def test_unordered_list(self):
        from py.services.agent.skills.enrich_hf_metadata.md_to_html import \
            convert_readme_to_html

        md = "- item one\n- item two"
        result = convert_readme_to_html(md)
        assert "<ul>" in result
        assert "<li>item one</li>" in result
        assert "<li>item two</li>" in result

    def test_ordered_list(self):
        from py.services.agent.skills.enrich_hf_metadata.md_to_html import \
            convert_readme_to_html

        md = "1. first\n2. second"
        result = convert_readme_to_html(md)
        assert "<ol>" in result
        assert "<li>first</li>" in result
        assert "<li>second</li>" in result

    def test_link(self):
        from py.services.agent.skills.enrich_hf_metadata.md_to_html import \
            convert_readme_to_html

        md = "[click here](https://example.com)"
        result = convert_readme_to_html(md)
        assert '<a href="https://example.com">click here</a>' in result

    def test_badge_image_stripped(self):
        from py.services.agent.skills.enrich_hf_metadata.md_to_html import \
            convert_readme_to_html

        md = "![badge](https://img.shields.io/badge/status-active)"
        result = convert_readme_to_html(md)
        assert "img.shields.io" not in result

    def test_gallery_stripped(self):
        from py.services.agent.skills.enrich_hf_metadata.md_to_html import \
            convert_readme_to_html

        md = "Some text\n<Gallery />\nmore text"
        result = convert_readme_to_html(md)
        assert "<Gallery" not in result

    def test_yaml_frontmatter_stripped(self):
        from py.services.agent.skills.enrich_hf_metadata.md_to_html import \
            convert_readme_to_html

        md = "---\ntags:\n  - lora\nbase_model: flux\n---\n\n# Real content"
        result = convert_readme_to_html(md)
        assert "base_model" not in result
        assert "<h1>Real content</h1>" in result

    def test_table(self):
        from py.services.agent.skills.enrich_hf_metadata.md_to_html import \
            convert_readme_to_html

        md = "| A | B |\n|---|---|\n| 1 | 2 |"
        result = convert_readme_to_html(md)
        assert "<table>" in result
        assert "<th>A</th>" in result
        assert "<td>1</td>" in result

    def test_horizontal_rule(self):
        from py.services.agent.skills.enrich_hf_metadata.md_to_html import \
            convert_readme_to_html

        md = "before\n\n---\n\nafter"
        result = convert_readme_to_html(md)
        assert "<hr>" in result

    def test_inline_code_preserves_angle_bracket(self):
        from py.services.agent.skills.enrich_hf_metadata.md_to_html import \
            convert_readme_to_html

        result = convert_readme_to_html("Use `a < b` in code")
        assert "<code>a &lt; b</code>" in result

    def test_blockquote(self):
        from py.services.agent.skills.enrich_hf_metadata.md_to_html import \
            convert_readme_to_html

        md = "> quoted text"
        result = convert_readme_to_html(md)
        assert "<blockquote>" in result
        assert "quoted text" in result

    def test_indented_whitespace_not_treated_as_code(self):
        from py.services.agent.skills.enrich_hf_metadata.md_to_html import \
            convert_readme_to_html

        md = "- item\n    \n## heading after spacing"
        result = convert_readme_to_html(md)
        assert "<pre>" not in result
        assert "<h2>heading after spacing</h2>" in result


# ======================================================================
# extract_gallery_images  —  YAML widget → civitai.images
# ======================================================================


class TestExtractGalleryImages:

    _REPO = "prithivMLmods/Flux-Long-Toon-LoRA"
    _README = """---
tags:
- lora
widget:
- text: "a cat"
  output:
    url: images/cat.png
- text: >-
    multi line
    prompt here
  output:
    url: images/dog.png
base_model: flux
---
# Content after frontmatter
"""

    def test_extracts_widget_images(self):
        from py.services.agent.skills.enrich_hf_metadata.md_to_html import \
            extract_gallery_images

        images = extract_gallery_images(self._README, self._REPO)
        assert len(images) == 2

        assert images[0]["url"] == (
            "https://huggingface.co/prithivMLmods/Flux-Long-Toon-LoRA"
            "/resolve/main/images/cat.png"
        )
        assert images[0]["meta"]["prompt"] == "a cat"
        assert images[0]["type"] == "image"
        assert images[0]["hasMeta"] is True
        assert images[0]["hasPositivePrompt"] is True

        assert images[1]["url"] == (
            "https://huggingface.co/prithivMLmods/Flux-Long-Toon-LoRA"
            "/resolve/main/images/dog.png"
        )
        assert images[1]["meta"]["prompt"] == "multi line prompt here"

    def test_default_dimensions_used(self):
        from py.services.agent.skills.enrich_hf_metadata.md_to_html import \
            extract_gallery_images

        images = extract_gallery_images(self._README, self._REPO)
        assert images[0]["width"] == 512
        assert images[0]["height"] == 512

    def test_custom_dimensions_applied(self):
        from py.services.agent.skills.enrich_hf_metadata.md_to_html import \
            extract_gallery_images

        images = extract_gallery_images(
            self._README, self._REPO,
            default_width=768, default_height=1024,
        )
        assert images[0]["width"] == 768
        assert images[0]["height"] == 1024

    def test_empty_readme_returns_empty(self):
        from py.services.agent.skills.enrich_hf_metadata.md_to_html import \
            extract_gallery_images

        assert extract_gallery_images("", self._REPO) == []
        assert extract_gallery_images("no frontmatter here", self._REPO) == []

    def test_empty_repo_returns_empty(self):
        from py.services.agent.skills.enrich_hf_metadata.md_to_html import \
            extract_gallery_images

        assert extract_gallery_images(self._README, "") == []

    def test_no_widget_returns_empty(self):
        from py.services.agent.skills.enrich_hf_metadata.md_to_html import \
            extract_gallery_images

        md = "---\ntags:\n  - lora\n---\n\nContent"
        assert extract_gallery_images(md, self._REPO) == []

    def test_extract_repo_from_hf_url(self):
        from py.services.agent.skills.enrich_hf_metadata.md_to_html import \
            extract_repo_from_hf_url

        assert extract_repo_from_hf_url(
            "https://huggingface.co/prithivMLmods/Flux-Long-Toon-LoRA"
        ) == "prithivMLmods/Flux-Long-Toon-LoRA"
        assert extract_repo_from_hf_url("") == ""
        assert extract_repo_from_hf_url("not a url") == ""

    def test_plain_yaml_scalar_text(self):
        """Unquoted multi-line YAML scalar (plain format) should extract prompt."""
        from py.services.agent.skills.enrich_hf_metadata.md_to_html import \
            extract_gallery_images

        md = """---
widget:
- text: two samurais doing a muay thai fight
    while the other leans back. Textured abstract style
  output:
    url: images/00.png
---"""
        images = extract_gallery_images(md, "user/repo")
        assert len(images) == 1
        assert "two samurais doing a muay thai fight" in images[0]["meta"]["prompt"]
        assert "Textured abstract style" in images[0]["meta"]["prompt"]

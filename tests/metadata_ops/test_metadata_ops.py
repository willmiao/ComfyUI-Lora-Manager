"""Tests for the metadata_ops module (py/metadata_ops/).

All tests mock the underlying services (scanner, MetadataManager, downloader)
since it is a thin delegation layer.

Mock targets must match where imports are resolved inside each function
(lazy imports via ``from X import Y`` inside function body).
"""

from __future__ import annotations

from unittest import mock

import pytest

from py.metadata_ops import (
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

    _MOCK_MODELS = ["SDXL 1.0", "Flux.1 D", "SD 1.5"]

    @pytest.mark.asyncio
    async def test_returns_all_models(self):
        """Verifies the function delegates to CivitaiBaseModelService.

        Uses a monkey-patch on ``get_instance`` to return a controlled mock
        so we don't need to work around ``mock.patch``'s dotted-path
        limitations with lazy imports inside function bodies."""
        import py.services.civitai_base_model_service as _svc
        orig = _svc.CivitaiBaseModelService.get_instance
        mock_svc = mock.AsyncMock()
        mock_svc.get_base_models.return_value = {
            "models": self._MOCK_MODELS,
        }
        _svc.CivitaiBaseModelService.get_instance = mock.AsyncMock(
            return_value=mock_svc,
        )
        try:
            result = await list_base_models()
            assert result == self._MOCK_MODELS
        finally:
            _svc.CivitaiBaseModelService.get_instance = orig

    @pytest.mark.asyncio
    async def test_limit(self):
        import py.services.civitai_base_model_service as _svc
        orig = _svc.CivitaiBaseModelService.get_instance
        mock_svc = mock.AsyncMock()
        mock_svc.get_base_models.return_value = {"models": ["A", "B", "C"]}
        _svc.CivitaiBaseModelService.get_instance = mock.AsyncMock(
            return_value=mock_svc,
        )
        try:
            result = await list_base_models(limit=2)
            assert result == ["A", "B"]
        finally:
            _svc.CivitaiBaseModelService.get_instance = orig

    @pytest.mark.asyncio
    async def test_empty_list_when_service_returns_empty(self):
        import py.services.civitai_base_model_service as _svc
        orig = _svc.CivitaiBaseModelService.get_instance
        mock_svc = mock.AsyncMock()
        mock_svc.get_base_models.return_value = {"models": []}
        _svc.CivitaiBaseModelService.get_instance = mock.AsyncMock(
            return_value=mock_svc,
        )
        try:
            result = await list_base_models()
            assert result == []
        finally:
            _svc.CivitaiBaseModelService.get_instance = orig

    @pytest.mark.asyncio
    async def test_handles_exception(self):
        import py.services.civitai_base_model_service as _svc
        orig = _svc.CivitaiBaseModelService.get_instance
        mock_svc = mock.AsyncMock()
        mock_svc.get_base_models.side_effect = RuntimeError("API error")
        _svc.CivitaiBaseModelService.get_instance = mock.AsyncMock(
            return_value=mock_svc,
        )
        try:
            result = await list_base_models()
            assert result == []
        finally:
            _svc.CivitaiBaseModelService.get_instance = orig


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
            mock.patch("py.metadata_ops.read_metadata") as mock_read,
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
            mock.patch("py.metadata_ops.read_metadata") as mock_read,
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
            mock.patch("py.metadata_ops.read_metadata") as mock_read,
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
            mock.patch("py.metadata_ops.read_metadata"),
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
            mock.patch("py.metadata_ops.read_metadata") as mock_read,
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
            mock.patch("py.metadata_ops.read_metadata") as mock_read,
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
        from py.services.agent.skills.enrich_hf_metadata.readme_processor import \
            convert_readme_to_html

        assert convert_readme_to_html("") == ""
        assert convert_readme_to_html(None) == ""  # type: ignore[arg-type]

    def test_heading(self):
        from py.services.agent.skills.enrich_hf_metadata.readme_processor import \
            convert_readme_to_html

        result = convert_readme_to_html("# Title")
        assert "<h1>" in result and "Title" in result

    def test_subheadings(self):
        from py.services.agent.skills.enrich_hf_metadata.readme_processor import \
            convert_readme_to_html

        md = "## Overview\n\n### Details"
        result = convert_readme_to_html(md)
        assert "<h2>Overview</h2>" in result
        assert "<h3>Details</h3>" in result

    def test_bold_and_italic(self):
        from py.services.agent.skills.enrich_hf_metadata.readme_processor import \
            convert_readme_to_html

        md = "**bold** and *italic*"
        result = convert_readme_to_html(md)
        assert "<strong>bold</strong>" in result
        assert "<em>italic</em>" in result

    def test_inline_code(self):
        from py.services.agent.skills.enrich_hf_metadata.readme_processor import \
            convert_readme_to_html

        md = "Use `model.train()`"
        result = convert_readme_to_html(md)
        assert "<code>" in result and "model.train()" in result

    def test_fenced_code_block(self):
        from py.services.agent.skills.enrich_hf_metadata.readme_processor import \
            convert_readme_to_html

        md = "```python\nprint('hello')\n```"
        result = convert_readme_to_html(md)
        assert "<pre>" in result
        assert "print" in result and "hello" in result

    def test_unordered_list(self):
        from py.services.agent.skills.enrich_hf_metadata.readme_processor import \
            convert_readme_to_html

        md = "- item one\n- item two"
        result = convert_readme_to_html(md)
        assert "<ul>" in result
        assert "<li>item one</li>" in result
        assert "<li>item two</li>" in result

    def test_ordered_list(self):
        from py.services.agent.skills.enrich_hf_metadata.readme_processor import \
            convert_readme_to_html

        md = "1. first\n2. second"
        result = convert_readme_to_html(md)
        assert "<ol>" in result
        assert "<li>first</li>" in result
        assert "<li>second</li>" in result

    def test_link(self):
        from py.services.agent.skills.enrich_hf_metadata.readme_processor import \
            convert_readme_to_html

        md = "[click here](https://example.com)"
        result = convert_readme_to_html(md)
        assert '<a href="https://example.com">click here</a>' in result

    def test_badge_image_stripped(self):
        from py.services.agent.skills.enrich_hf_metadata.readme_processor import \
            convert_readme_to_html

        md = "![badge](https://img.shields.io/badge/status-active)"
        result = convert_readme_to_html(md)
        assert "img.shields.io" not in result

    def test_gallery_stripped(self):
        from py.services.agent.skills.enrich_hf_metadata.readme_processor import \
            convert_readme_to_html

        md = "Some text\n<Gallery />\nmore text"
        result = convert_readme_to_html(md)
        assert "<Gallery" not in result

    def test_yaml_frontmatter_stripped(self):
        from py.services.agent.skills.enrich_hf_metadata.readme_processor import \
            convert_readme_to_html

        md = "---\ntags:\n  - lora\nbase_model: flux\n---\n\n# Real content"
        result = convert_readme_to_html(md)
        assert "base_model" not in result
        assert "<h1>Real content</h1>" in result

    def test_table(self):
        from py.services.agent.skills.enrich_hf_metadata.readme_processor import \
            convert_readme_to_html

        md = "| A | B |\n|---|---|\n| 1 | 2 |"
        result = convert_readme_to_html(md)
        assert "<table>" in result
        assert "<th>A</th>" in result
        assert "<td>1</td>" in result

    def test_horizontal_rule(self):
        from py.services.agent.skills.enrich_hf_metadata.readme_processor import \
            convert_readme_to_html

        md = "before\n\n---\n\nafter"
        result = convert_readme_to_html(md)
        assert "<hr>" in result

    def test_inline_code_preserves_angle_bracket(self):
        from py.services.agent.skills.enrich_hf_metadata.readme_processor import \
            convert_readme_to_html

        result = convert_readme_to_html("Use `a < b` in code")
        assert "<code>a &lt; b</code>" in result

    def test_blockquote(self):
        from py.services.agent.skills.enrich_hf_metadata.readme_processor import \
            convert_readme_to_html

        md = "> quoted text"
        result = convert_readme_to_html(md)
        assert "<blockquote>" in result
        assert "quoted text" in result

    def test_indented_whitespace_not_treated_as_code(self):
        from py.services.agent.skills.enrich_hf_metadata.readme_processor import \
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
        from py.services.agent.skills.enrich_hf_metadata.readme_processor import \
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
        from py.services.agent.skills.enrich_hf_metadata.readme_processor import \
            extract_gallery_images

        images = extract_gallery_images(self._README, self._REPO)
        assert images[0]["width"] == 512
        assert images[0]["height"] == 512

    def test_custom_dimensions_applied(self):
        from py.services.agent.skills.enrich_hf_metadata.readme_processor import \
            extract_gallery_images

        images = extract_gallery_images(
            self._README, self._REPO,
            default_width=768, default_height=1024,
        )
        assert images[0]["width"] == 768
        assert images[0]["height"] == 1024

    def test_empty_readme_returns_empty(self):
        from py.services.agent.skills.enrich_hf_metadata.readme_processor import \
            extract_gallery_images

        assert extract_gallery_images("", self._REPO) == []
        assert extract_gallery_images("no frontmatter here", self._REPO) == []

    def test_empty_repo_returns_empty(self):
        from py.services.agent.skills.enrich_hf_metadata.readme_processor import \
            extract_gallery_images

        assert extract_gallery_images(self._README, "") == []

    def test_no_widget_returns_empty(self):
        from py.services.agent.skills.enrich_hf_metadata.readme_processor import \
            extract_gallery_images

        md = "---\ntags:\n  - lora\n---\n\nContent"
        assert extract_gallery_images(md, self._REPO) == []

    def test_extract_repo_from_hf_url(self):
        from py.services.agent.skills.enrich_hf_metadata.readme_processor import \
            extract_repo_from_hf_url

        assert extract_repo_from_hf_url(
            "https://huggingface.co/prithivMLmods/Flux-Long-Toon-LoRA"
        ) == "prithivMLmods/Flux-Long-Toon-LoRA"
        assert extract_repo_from_hf_url("") == ""
        assert extract_repo_from_hf_url("not a url") == ""

    def test_plain_yaml_scalar_text(self):
        """Unquoted multi-line YAML scalar (plain format) extracts first line only.
        The YAML parser only reports the value on the ``text:`` line; continuation
        lines are handled by the post-processor from the raw README."""
        from py.services.agent.skills.enrich_hf_metadata.readme_processor import \
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
        assert images[0]["meta"]["prompt"] == "two samurais doing a muay thai fight"


# ======================================================================
# extract_gallery_table_images  —  Sample Gallery markdown tables
# ======================================================================


class TestExtractGalleryTableImages:

    _REPO = "Limbicnation/pixel-art-lora"
    _README = """## Sample Gallery

| Preview | Prompt |
|---------|--------|
| ![Knight](./samples/knight.png) | pixel art sprite, a brave knight |
| ![Dragon](./samples/dragon.png) | pixel art sprite, a fire dragon |
"""

    @staticmethod
    def _extract(md: str, repo: str = _REPO, existing: set | None = None):
        from py.services.agent.skills.enrich_hf_metadata.readme_processor import \
            extract_gallery_table_images
        return extract_gallery_table_images(md, repo, existing_urls=existing)

    def test_extracts_table_images(self):
        images = self._extract(self._README)
        assert len(images) == 2
        assert "knight.png" in images[0]["url"]
        assert images[0]["meta"]["prompt"] == "pixel art sprite, a brave knight"
        assert "dragon.png" in images[1]["url"]

    def test_skips_existing_urls(self):
        existing = {"https://huggingface.co/Limbicnation/pixel-art-lora/resolve/main/samples/knight.png"}
        images = self._extract(self._README, existing=existing)
        assert len(images) == 1
        assert "knight.png" not in images[0]["url"]

    def test_empty_readme_returns_empty(self):
        assert self._extract("") == []

    def test_no_gallery_table_returns_empty(self):
        md = "## Description\nSome text."
        assert self._extract(md) == []

    def test_non_gallery_table_skipped(self):
        md = "| Param | Value |\n|---|---|\n| Steps | 4 |"
        assert self._extract(md) == []

    def test_absolute_url_preserved(self):
        md = "| Preview | Prompt |\n|---|---|\n| ![img](https://cdn.example.com/img.png) | text |"
        images = self._extract(md, repo="user/repo")
        assert len(images) == 1
        assert images[0]["url"] == "https://cdn.example.com/img.png"


# ======================================================================
# clean_readme_for_llm  —  pre-process README before LLM injection
# ======================================================================


class TestCleanReadmeForLlm:

    @staticmethod
    def _clean(md: str, max_length: int = 6000) -> str:
        from py.services.agent.skills.enrich_hf_metadata.readme_processor import \
            clean_readme_for_llm
        return clean_readme_for_llm(md, max_length=max_length)

    # -- basic guards --------------------------------------------------------

    def test_none_returns_empty(self):
        assert self._clean(None) == ""  # type: ignore[arg-type]

    def test_empty_returns_empty(self):
        assert self._clean("") == ""

    def test_plain_text_passes_through(self):
        result = self._clean("Just some description text.")
        assert "Just some description text." in result

    # -- widget section stripping -------------------------------------------

    def test_widget_stripped_frontmatter_metadata_preserved(self):
        """Widget section is stripped, but ``base_model``, ``tags``,
        ``instance_prompt`` survive."""
        md = """---
tags:
- lora
- anime
widget:
- text: "a test prompt"
  output:
    url: images/test.png
- text: >-
    another long
    prompt here
  output:
    url: images/test2.png
base_model: black-forest-labs/FLUX.1-dev
instance_prompt: trigger word
---
# Model Description
This is the actual content.
"""
        result = self._clean(md)
        # Widget text stripped (it's handled by the post-processor gallery
        # extraction instead)
        assert "a test prompt" not in result
        assert "another long" not in result
        # Non-widget frontmatter preserved
        assert "base_model: black-forest-labs/FLUX.1-dev" in result
        assert "instance_prompt: trigger word" in result
        assert "tags:" in result
        assert "- lora" in result
        assert "- anime" in result
        assert "Model Description" in result

    def test_widget_last_key_in_frontmatter(self):
        """Widget stripped, non-widget keys preserved."""
        md = """---
tags:
- lora
widget:
- output:
    url: img.png
  text: prompt
---
# Content
"""
        result = self._clean(md)
        assert "prompt" not in result
        assert "tags:" in result

    def test_no_widget_untouched(self):
        md = """---
tags:
- lora
base_model: flux
---
# Content
"""
        result = self._clean(md)
        assert "tags:" in result
        assert "base_model: flux" in result

    # -- gallery stripping ---------------------------------------------------

    def test_gallery_tag_stripped(self):
        md = "Some text\n<Gallery />\nmore text"
        result = self._clean(md)
        assert "<Gallery" not in result

    # -- code block stripping ------------------------------------------------

    def test_fenced_code_block_stripped(self):
        md = """## Usage
```python
import torch
pipe = DiffusionPipeline.from_pretrained('base')
```
## Description
Some text.
"""
        result = self._clean(md)
        assert "import torch" not in result
        assert "DiffusionPipeline" not in result
        assert "## Usage" in result
        assert "## Description" in result

    def test_bash_code_block_stripped(self):
        md = """## Setup
```bash
pip install diffusers
huggingface-cli download repo
```
"""
        result = self._clean(md)
        assert "pip install" not in result
        assert "## Setup" in result

    def test_code_block_sections_remain_separated(self):
        md = "## Install\n```bash\npip install x\n```\n\n## Usage\nSome text."
        result = self._clean(md)
        assert "pip install" not in result
        assert "## Install" in result
        assert "## Usage" in result
        assert "Some text." in result

    def test_unmarked_code_block_preserved(self):
        """Unmarked fenced code blocks (just ```) are kept since they
        often contain trigger words rather than code."""
        md = """### Trigger Words

Always include:

```
pixel art sprite, game asset, transparent background
```
"""
        result = self._clean(md)
        assert "pixel art sprite" in result
        assert "game asset" in result
        assert "transparent background" in result

    def test_unmarked_code_block_with_python_preserved(self):
        """Even unmarked blocks with Python code are kept (false positive
        accepted because trigger-word blocks are unmarked)."""
        md = "## Setup\n```\nimport torch\nprint('hello')\n```\n## Desc\nText."
        result = self._clean(md)
        assert "import torch" in result

    # -- standalone image stripping ------------------------------------------

    def test_standalone_image_urls_preserved_for_llm(self):
        """Markdown image URLs are kept so the LLM can extract a ``preview_url``."""
        md = "## Gallery\n![sample](https://cdn.hf.co/img.png)\n![another](https://cdn.hf.co/img2.png)\n\nSome text."
        result = self._clean(md)
        # URLs preserved for LLM preview extraction
        assert "cdn.hf.co/img.png" in result
        assert "cdn.hf.co/img2.png" in result
        assert "## Gallery" in result
        assert "Some text." in result

    def test_html_img_tag_converted_to_markdown_image(self):
        """``<img>`` converted to ``![](src)``, preserving URL for LLM."""
        md = '## Preview\n<img src="https://cdn.hf.co/img.webp"></img>\n\nDescription.'
        result = self._clean(md)
        assert "![](https://cdn.hf.co/img.webp)" in result
        assert "cdn.hf.co" in result  # URL preserved for LLM extraction
        assert "Description." in result

    def test_inline_image_within_paragraph_preserved(self):
        """Inline images inside paragraphs are rare but shouldn't be stripped."""
        md = "Click here ![icon](https://example.com/icon.png) for more info."
        result = self._clean(md)
        assert "Click here" in result
        assert "for more info" in result

    # -- training table stripping --------------------------------------------

    def test_training_table_stripped(self):
        md = """## Training
| Parameter     | Value    |
|---------------|----------|
| LR Scheduler  | constant |
| Optimizer     | AdamW    |
| Network Dim   | 64       |
## Best Dimensions
| Resolution | Status  |
|-----------|---------|
| 768x1024  | Best    |
"""
        result = self._clean(md)
        assert "LR Scheduler" not in result
        assert "Optimizer" not in result
        assert "Network Dim" not in result
        # Normal table preserved
        assert "Best Dimensions" in result
        assert "768x1024" in result

    def test_normal_table_preserved(self):
        md = """## Recommended
| Resolution | Status  |
|-----------|---------|
| 1024x1024 | Default |
"""
        result = self._clean(md)
        assert "1024x1024" in result

    # -- boilerplate section stripping ---------------------------------------

    def test_boilerplate_license_stripped(self):
        md = """## Description
Some text.
## License
apache-2.0
Some license details here.
## More Content
After license.
"""
        result = self._clean(md)
        assert "apache-2.0" not in result
        assert "## License" not in result
        assert "## Description" in result
        assert "## More Content" in result
        assert "After license." in result

    def test_boilerplate_disclaimer_stripped(self):
        md = """## Description
Some text.
## DISCLAIMER
Legal text here.
## Citation
Bibtex here.
"""
        result = self._clean(md)
        assert "Legal text" not in result
        assert "Bibtex" not in result
        assert "Some text." in result

    def test_boilerplate_subsection_not_stripped(self):
        """Only top-level (##) boilerplate is stripped; ### subsections inside
        non-boilerplate headings are left alone."""
        md = """## Usage
Some text.
### Important Note
This is a note within the usage section.
"""
        result = self._clean(md)
        assert "Important Note" in result

    # -- massive list stripping ----------------------------------------------

    def test_massive_name_list_stripped(self):
        lines = ["## 2026 Updates:"]
        for i in range(12):
            lines.append(f"Name{i}A, Name{i}B, Name{i}C, Name{i}D, Name{i}E,")
        lines.append("## License")
        lines.append("apache")
        md = "\n".join(lines)
        result = self._clean(md)
        assert "Name0A" not in result
        assert "Name11E" not in result
        assert "## 2026 Updates:" in result
        # License stripped by boilerplate
        assert "apache" not in result

    def test_short_list_preserved(self):
        """Short lists (< 8 consecutive lines) should not be stripped."""
        lines = ["## Tags:"]
        for i in range(4):
            lines.append(f"tag{i}A, tag{i}B,")
        lines.append("## Description")
        lines.append("Some text.")
        md = "\n".join(lines)
        result = self._clean(md)
        assert "tag0A" in result
        assert "tag3B" in result

    # -- max_length truncation -----------------------------------------------

    def test_truncation(self):
        md = "A" * 100 + "\n" + "B" * 100
        result = self._clean(md, max_length=150)
        assert len(result) <= 150
        assert result.startswith("A" * 100)

    # -- integration: end-to-end realistic README ----------------------------

    def test_realistic_flux_lora_readme(self):
        md = """---
tags:
- text-to-image
- lora
- diffusers
- 3D
- Toon
widget:
- text: >-
    Long toons, a close-up of a cartoon character face...
  output:
    url: images/LT4.png
- text: >-
    Long toons, Super Detail, a close-up shot...
  output:
    url: images/LT5.png
base_model: black-forest-labs/FLUX.1-dev
instance_prompt: Long toons
license: creativeml-openrail-m
---
# Flux-Long-Toon-LoRA

<Gallery />

**The model is still in the training phase.**

## Model description

**prithivMLmods/Flux-Long-Toon-LoRA**

Image Processing Parameters

| Parameter                 | Value  | Parameter                 | Value  |
|---------------------------|--------|---------------------------|--------|
| LR Scheduler              | constant | Noise Offset              | 0.03   |
| Optimizer                 | AdamW  | Multires Noise Discount   | 0.1    |
| Network Dim               | 64     | Multires Noise Iterations | 10     |
| Network Alpha             | 32     | Repeat & Steps           | 25 & 3270 |
| Epoch                     | 18    | Save Every N Epochs       | 1     |

## Best Dimensions

- 768 x 1024 (Best)
- 1024 x 1024 (Default)

## Setting Up
```python
import torch
from pipelines import DiffusionPipeline

base_model = "black-forest-labs/FLUX.1-dev"
pipe = DiffusionPipeline.from_pretrained(base_model, torch_dtype=torch.bfloat16)

lora_repo = "prithivMLmods/Flux-Long-Toon-LoRA"
trigger_word = "Long toons"
pipe.load_lora_weights(lora_repo)
```

## Trigger words

You should use `Long toons` to trigger the image generation.

## Download model

Weights for this model are available in Safetensors format.
"""
        original_len = len(md)
        result = self._clean(md)

        # Significantly smaller: widget + training tables + code blocks
        # + boilerplate all stripped
        assert len(result) < original_len * 0.35, (
            f"Expected <35% of original, got {len(result)}/{original_len}"
        )

        # Signal preserved
        assert "Long toons" in result
        assert "black-forest-labs/FLUX.1-dev" in result
        assert "3D" in result
        assert "Toon" in result

        # Widget content stripped (post-processor handles image extraction)
        assert "close-up of a cartoon character face" not in result

        # Noise stripped
        assert "import torch" not in result
        assert "DiffusionPipeline" not in result
        assert "LR Scheduler" not in result
        assert "<Gallery" not in result
        assert "Download model" not in result

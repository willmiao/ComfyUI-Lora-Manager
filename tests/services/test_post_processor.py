"""Tests for the PostProcessor (py/services/agent/post_processor.py).

PostProcessor delegates all I/O to AgentCLI — these tests mock AgentCLI
functions and verify the business logic (conditions, merges, dispatch).
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from unittest import mock

import pytest

from py.services.agent.post_processor import PostProcessor
from py.services.model_sources import ModelCardContext


@pytest.fixture
def processor():
    return PostProcessor()


# ======================================================================
# process() — routing
# ======================================================================


class TestProcessDispatch:
    @pytest.mark.asyncio
    async def test_unknown_skill_returns_error(self, processor):
        result = await processor.process(
            skill_name="nonexistent",
            model_path="/p.safetensors",
            llm_output={},
            metadata={},
        )
        assert result["success"] is False
        assert "nonexistent" in result["errors"][0]

    @pytest.mark.asyncio
    async def test_enrich_hf_metadata_routes_correctly(self, processor):
        with (
            mock.patch("py.metadata_ops.apply_metadata_updates") as mock_apply,
            mock.patch("py.metadata_ops.download_preview") as mock_dl,
            mock.patch("py.metadata_ops.refresh_cache") as mock_ref,
        ):
            mock_apply.return_value = ["metadata_source"]
            mock_dl.return_value = None

            result = await processor.process(
                skill_name="enrich_hf_metadata",
                model_path="/p.safetensors",
                llm_output={},
                metadata={"from_civitai": True},
            )

        assert result["success"] is True


# ======================================================================
# enrich_hf_metadata — field-level logic
# ======================================================================


class TestEnrichHfMetadata:
    """Business logic tests for the enrich_hf_metadata post-processor."""

    MIN_LLM_OUTPUT = {
        "base_model": "",
        "trigger_words": [],
        "short_description": "",
        "tags": [],
        "recommended_width": 0,
        "recommended_height": 0,
        "preview_url": "",
        "confidence": "low",
    }

    # -- base_model ------------------------------------------------------

    @pytest.mark.asyncio
    async def test_base_model_overwrites_empty(self, processor):
        """Empty current base_model → new value is applied."""
        llm = {**self.MIN_LLM_OUTPUT, "base_model": "Flux.1 D"}
        with (
            mock.patch("py.metadata_ops.apply_metadata_updates") as mock_apply,
            mock.patch("py.metadata_ops.download_preview", return_value=False),
            mock.patch("py.metadata_ops.refresh_cache"),
        ):
            await processor.process(
                skill_name="enrich_hf_metadata",
                model_path="/p.safetensors",
                llm_output=llm,
                metadata={"base_model": ""},
            )
        applied = mock_apply.call_args[0][1]
        assert applied["base_model"] == "Flux.1 D"

    @pytest.mark.asyncio
    async def test_base_model_does_not_overwrite_existing_civitai(self, processor):
        """Existing base_model from CivitAI → not overwritten."""
        llm = {**self.MIN_LLM_OUTPUT, "base_model": "Flux.1 D"}
        with (
            mock.patch("py.metadata_ops.apply_metadata_updates") as mock_apply,
            mock.patch("py.metadata_ops.download_preview", return_value=False),
            mock.patch("py.metadata_ops.refresh_cache"),
        ):
            await processor.process(
                skill_name="enrich_hf_metadata",
                model_path="/p.safetensors",
                llm_output=llm,
                metadata={"base_model": "SDXL 1.0", "from_civitai": True},
            )
        # apply IS called (metadata_source, llm_enriched_at) but base_model not in it
        applied = mock_apply.call_args[0][1]
        assert "base_model" not in applied

    @pytest.mark.asyncio
    async def test_base_model_overwrites_existing_hf_model(self, processor):
        """Existing base_model from HF → overwritten (LLM is more reliable)."""
        llm = {**self.MIN_LLM_OUTPUT, "base_model": "Flux.1 D"}
        with (
            mock.patch("py.metadata_ops.apply_metadata_updates") as mock_apply,
            mock.patch("py.metadata_ops.download_preview", return_value=False),
            mock.patch("py.metadata_ops.refresh_cache"),
        ):
            await processor.process(
                skill_name="enrich_hf_metadata",
                model_path="/p.safetensors",
                llm_output=llm,
                metadata={
                    "base_model": "SD 1.5",
                    "from_civitai": False,
                    "hf_url": "https://huggingface.co/user/repo",
                },
            )
        applied = mock_apply.call_args[0][1]
        assert applied["base_model"] == "Flux.1 D"

    @pytest.mark.asyncio
    async def test_base_model_skipped_when_llm_empty(self, processor):
        """LLM returns empty base_model → nothing written."""
        with (
            mock.patch("py.metadata_ops.apply_metadata_updates") as mock_apply,
            mock.patch("py.metadata_ops.download_preview", return_value=False),
            mock.patch("py.metadata_ops.refresh_cache"),
        ):
            await processor.process(
                skill_name="enrich_hf_metadata",
                model_path="/p.safetensors",
                llm_output=self.MIN_LLM_OUTPUT,
                metadata={"base_model": ""},
            )
        applied = mock_apply.call_args[0][1]
        assert "base_model" not in applied

    # -- trigger_words ---------------------------------------------------

    @pytest.mark.asyncio
    async def test_trigger_words_merged(self, processor):
        """New trigger words written when current list is empty."""
        llm = {**self.MIN_LLM_OUTPUT, "trigger_words": ["trigger1", "trigger2"]}
        with (
            mock.patch("py.metadata_ops.apply_metadata_updates") as mock_apply,
            mock.patch("py.metadata_ops.download_preview", return_value=None),
            mock.patch("py.metadata_ops.refresh_cache"),
        ):
            await processor.process(
                skill_name="enrich_hf_metadata",
                model_path="/p.safetensors",
                llm_output=llm,
                metadata={},
            )
        applied = mock_apply.call_args[0][1]
        assert applied["civitai"]["trainedWords"] == ["trigger1", "trigger2"]

    # -- short_description → civitai.description -------------------------

    @pytest.mark.asyncio
    async def test_short_description_written_to_civitai(self, processor):
        """short_description written to civitai.description for HF models."""
        llm = {**self.MIN_LLM_OUTPUT, "short_description": "A short summary"}
        with (
            mock.patch("py.metadata_ops.apply_metadata_updates") as mock_apply,
            mock.patch("py.metadata_ops.download_preview", return_value=None),
            mock.patch("py.metadata_ops.refresh_cache"),
        ):
            await processor.process(
                skill_name="enrich_hf_metadata",
                model_path="/p.safetensors",
                llm_output=llm,
                metadata={
                    "from_civitai": False,
                    "hf_url": "https://huggingface.co/user/repo",
                },
            )
        applied = mock_apply.call_args[0][1]
        assert applied["civitai"]["description"] == "A short summary"

    @pytest.mark.asyncio
    async def test_short_description_skipped_without_hf_url(self, processor):
        """short_description NOT written when the model has no HF source."""
        llm = {**self.MIN_LLM_OUTPUT, "short_description": "A short summary"}
        with (
            mock.patch("py.metadata_ops.apply_metadata_updates") as mock_apply,
            mock.patch("py.metadata_ops.download_preview", return_value=None),
            mock.patch("py.metadata_ops.refresh_cache"),
        ):
            await processor.process(
                skill_name="enrich_hf_metadata",
                model_path="/p.safetensors",
                llm_output=llm,
                metadata={"from_civitai": True},
            )
        applied = mock_apply.call_args[0][1]
        assert "civitai" not in applied or "description" not in applied.get("civitai", {})

    # -- readme_content → modelDescription -------------------------------

    @pytest.mark.asyncio
    async def test_readme_content_converted_to_model_description(self, processor):
        """Raw README converted to HTML and stored as modelDescription."""
        with (
            mock.patch("py.metadata_ops.apply_metadata_updates") as mock_apply,
            mock.patch("py.metadata_ops.download_preview", return_value=None),
            mock.patch("py.metadata_ops.refresh_cache"),
        ):
            await processor.process(
                skill_name="enrich_hf_metadata",
                model_path="/p.safetensors",
                llm_output=self.MIN_LLM_OUTPUT,
                metadata={
                    "from_civitai": False,
                    "hf_url": "https://huggingface.co/user/repo",
                },
                readme_content="# Hello\n\nThis is **bold**.",
            )
        applied = mock_apply.call_args[0][1]
        assert "<h1>Hello</h1>" in applied.get("modelDescription", "")
        assert "<strong>bold</strong>" in applied.get("modelDescription", "")

    @pytest.mark.asyncio
    async def test_readme_content_skipped_without_hf_url(self, processor):
        """README content NOT converted when the model has no HF source."""
        with (
            mock.patch("py.metadata_ops.apply_metadata_updates") as mock_apply,
            mock.patch("py.metadata_ops.download_preview", return_value=None),
            mock.patch("py.metadata_ops.refresh_cache"),
        ):
            await processor.process(
                skill_name="enrich_hf_metadata",
                model_path="/p.safetensors",
                llm_output=self.MIN_LLM_OUTPUT,
                metadata={"from_civitai": True},
                readme_content="# Hello",
            )
        applied = mock_apply.call_args[0][1]
        assert "modelDescription" not in applied

    # -- gallery images → civitai.images ---------------------------------

    @pytest.mark.asyncio
    async def test_gallery_images_extracted_from_readme(self, processor):
        """Widget entries in README → civitai.images."""
        readme = """---
widget:
- text: "a cat"
  output:
    url: images/cat.png
---
Content
"""
        with (
            mock.patch("py.metadata_ops.apply_metadata_updates") as mock_apply,
            mock.patch("py.metadata_ops.download_preview", return_value=None),
            mock.patch("py.metadata_ops.refresh_cache"),
        ):
            await processor.process(
                skill_name="enrich_hf_metadata",
                model_path="/p.safetensors",
                llm_output=self.MIN_LLM_OUTPUT,
                metadata={
                    "from_civitai": False,
                    "hf_url": "https://huggingface.co/user/repo",
                },
                readme_content=readme,
            )
        applied = mock_apply.call_args[0][1]
        images = applied.get("civitai", {}).get("images", [])
        assert len(images) == 1
        assert images[0]["url"] == (
            "https://huggingface.co/user/repo/resolve/main/images/cat.png"
        )
        assert images[0]["meta"]["prompt"] == "a cat"

    @pytest.mark.asyncio
    async def test_gallery_images_use_modelscope_asset_base_url(self, processor):
        """A ModelScope-linked model resolves relative images against ModelScope."""
        readme = """---
widget:
- text: "a cat"
  output:
    url: images/cat.png
---
Content
"""
        with (
            mock.patch("py.metadata_ops.apply_metadata_updates") as mock_apply,
            mock.patch("py.metadata_ops.download_preview", return_value=None),
            mock.patch("py.metadata_ops.refresh_cache"),
        ):
            await processor.process(
                skill_name="enrich_hf_metadata",
                model_path="/p.safetensors",
                llm_output=self.MIN_LLM_OUTPUT,
                metadata={
                    "from_civitai": False,
                    "source_platform": "modelscope",
                    "source_url": "https://modelscope.cn/models/user/repo",
                },
                readme_content=readme,
            )
        applied = mock_apply.call_args[0][1]
        images = applied.get("civitai", {}).get("images", [])
        assert len(images) == 1
        assert images[0]["url"] == (
            "https://modelscope.cn/models/user/repo/resolve/master/images/cat.png"
        )

    @pytest.mark.asyncio
    async def test_base_model_overwrites_existing_modelscope_model(self, processor):
        """ModelScope is an external source, so the LLM may overwrite base_model."""
        llm = {**self.MIN_LLM_OUTPUT, "base_model": "Flux.1 D"}
        with (
            mock.patch("py.metadata_ops.apply_metadata_updates") as mock_apply,
            mock.patch("py.metadata_ops.download_preview", return_value=False),
            mock.patch("py.metadata_ops.refresh_cache"),
        ):
            await processor.process(
                skill_name="enrich_hf_metadata",
                model_path="/p.safetensors",
                llm_output=llm,
                metadata={
                    "base_model": "SD 1.5",
                    "source_platform": "modelscope",
                    "source_url": "https://modelscope.cn/models/user/repo",
                },
            )
        assert mock_apply.call_args[0][1]["base_model"] == "Flux.1 D"

    @pytest.mark.asyncio
    async def test_gallery_images_skipped_without_hf_url(self, processor):
        """Gallery images NOT extracted when the model has no HF source."""
        with (
            mock.patch("py.metadata_ops.apply_metadata_updates") as mock_apply,
            mock.patch("py.metadata_ops.download_preview", return_value=None),
            mock.patch("py.metadata_ops.refresh_cache"),
        ):
            await processor.process(
                skill_name="enrich_hf_metadata",
                model_path="/p.safetensors",
                llm_output=self.MIN_LLM_OUTPUT,
                metadata={"from_civitai": True},
                readme_content="---\nwidget:\n- text: a\n  output:\n    url: x.png\n---\n",
            )
        applied = mock_apply.call_args[0][1]
        civitai = applied.get("civitai", {})
        assert "images" not in civitai

    @pytest.mark.asyncio
    async def test_gallery_images_extracted_for_civitai_linked_model(self, processor):
        """A model may be on CivitAI and HuggingFace at once (#1094).

        HF enrichment is gated on ``hf_url``, not on ``from_civitai``, so the
        README gallery is still applied when both sources are present.
        """
        with (
            mock.patch("py.metadata_ops.apply_metadata_updates") as mock_apply,
            mock.patch("py.metadata_ops.download_preview", return_value=None),
            mock.patch("py.metadata_ops.refresh_cache"),
        ):
            await processor.process(
                skill_name="enrich_hf_metadata",
                model_path="/p.safetensors",
                llm_output=self.MIN_LLM_OUTPUT,
                metadata={
                    "from_civitai": True,
                    "hf_url": "https://huggingface.co/user/repo",
                },
                readme_content="---\nwidget:\n- text: a\n  output:\n    url: x.png\n---\n",
            )
        applied = mock_apply.call_args[0][1]
        images = applied.get("civitai", {}).get("images", [])
        assert len(images) == 1
        assert images[0]["url"] == (
            "https://huggingface.co/user/repo/resolve/main/x.png"
        )

    # -- tags ------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_tags_merged_and_deduplicated(self, processor):
        llm = {**self.MIN_LLM_OUTPUT, "tags": ["flux", "lora", "STYLE"]}
        with (
            mock.patch("py.metadata_ops.apply_metadata_updates") as mock_apply,
            mock.patch("py.metadata_ops.download_preview", return_value=False),
            mock.patch("py.metadata_ops.refresh_cache"),
        ):
            await processor.process(
                skill_name="enrich_hf_metadata",
                model_path="/p.safetensors",
                llm_output=llm,
                metadata={"tags": ["anime"], "from_civitai": False},
            )
        merged = mock_apply.call_args[0][1]["tags"]
        assert "anime" in merged
        assert "flux" in merged
        assert "style" in merged  # lowercased
        # "lora" and "STYLE" → "lora" and "style"
        assert len(merged) == 4  # anime, flux, lora, style

    # -- metadata_source & llm_enriched_at --------------------------------

    @pytest.mark.asyncio
    async def test_audit_fields_always_set(self, processor):
        with (
            mock.patch("py.metadata_ops.apply_metadata_updates") as mock_apply,
            mock.patch("py.metadata_ops.download_preview", return_value=False),
            mock.patch("py.metadata_ops.refresh_cache"),
        ):
            await processor.process(
                skill_name="enrich_hf_metadata",
                model_path="/p.safetensors",
                llm_output=self.MIN_LLM_OUTPUT,
                metadata={},
            )
        applied = mock_apply.call_args[0][1]
        assert applied["metadata_source"] == "agent:enrich_hf_metadata"
        assert "llm_enriched_at" in applied

    @pytest.mark.asyncio
    async def test_confidence_is_stored_under_a_persisted_key(self, processor):
        """`llm_confidence` must not be underscore-prefixed.

        Underscore-prefixed keys are dropped by `BaseModelMetadata`, which made
        `_llm_confidence` vanish on the next metadata write.
        """
        llm = {**self.MIN_LLM_OUTPUT, "confidence": "medium"}
        with (
            mock.patch("py.metadata_ops.apply_metadata_updates") as mock_apply,
            mock.patch("py.metadata_ops.download_preview", return_value=False),
            mock.patch("py.metadata_ops.refresh_cache"),
        ):
            await processor.process(
                skill_name="enrich_hf_metadata",
                model_path="/p.safetensors",
                llm_output=llm,
                metadata={},
            )
        applied = mock_apply.call_args[0][1]
        assert applied["llm_confidence"] == "medium"
        assert "_llm_confidence" not in applied

    @pytest.mark.asyncio
    async def test_confidence_absent_when_the_llm_reported_none(self, processor):
        llm = {**self.MIN_LLM_OUTPUT, "confidence": ""}
        with (
            mock.patch("py.metadata_ops.apply_metadata_updates") as mock_apply,
            mock.patch("py.metadata_ops.download_preview", return_value=False),
            mock.patch("py.metadata_ops.refresh_cache"),
        ):
            await processor.process(
                skill_name="enrich_hf_metadata",
                model_path="/p.safetensors",
                llm_output=llm,
                metadata={},
            )
        assert "llm_confidence" not in mock_apply.call_args[0][1]

    # -- preview download ------------------------------------------------

    @pytest.mark.asyncio
    async def test_preview_downloaded_when_url_provided(self, processor):
        llm = {**self.MIN_LLM_OUTPUT, "preview_url": "https://ex.com/img.png"}
        with (
            mock.patch("py.metadata_ops.apply_metadata_updates") as mock_apply,
            mock.patch("py.metadata_ops.download_preview") as mock_dl,
            mock.patch("py.metadata_ops.refresh_cache"),
        ):
            mock_dl.return_value = "/p.webp"
            result = await processor.process(
                skill_name="enrich_hf_metadata",
                model_path="/p.safetensors",
                llm_output=llm,
                metadata={},
            )
        assert result["preview_downloaded"] is True
        mock_dl.assert_awaited_once_with("/p.safetensors", "https://ex.com/img.png")
        applied = mock_apply.call_args[0][1]
        assert applied["preview_url"] == "/p.webp"

    @pytest.mark.asyncio
    async def test_preview_skipped_when_exists(self, processor):
        """If current_preview file exists on disk, skip download."""
        llm = {**self.MIN_LLM_OUTPUT, "preview_url": "https://ex.com/img.png"}
        with (
            mock.patch("py.metadata_ops.apply_metadata_updates"),
            mock.patch("py.metadata_ops.download_preview") as mock_dl,
            mock.patch("py.metadata_ops.refresh_cache"),
            mock.patch("os.path.exists", return_value=True),
        ):
            await processor.process(
                skill_name="enrich_hf_metadata",
                model_path="/p.safetensors",
                llm_output=llm,
                metadata={"preview_url": "/existing/preview.webp"},
            )
        mock_dl.assert_not_called()

    # -- cache refresh ---------------------------------------------------

    @pytest.mark.asyncio
    async def test_cache_refreshed_when_updates_applied(self, processor):
        llm = {**self.MIN_LLM_OUTPUT, "base_model": "Flux.1 D"}
        with (
            mock.patch("py.metadata_ops.apply_metadata_updates", return_value=["base_model"]),
            mock.patch("py.metadata_ops.download_preview", return_value=False),
            mock.patch("py.metadata_ops.refresh_cache") as mock_ref,
        ):
            await processor.process(
                skill_name="enrich_hf_metadata",
                model_path="/p.safetensors",
                llm_output=llm,
                metadata={"base_model": ""},
            )
        mock_ref.assert_awaited_once_with("/p.safetensors")

    @pytest.mark.asyncio
    async def test_cache_not_refreshed_when_nothing_changed(self, processor):
        with (
            mock.patch("py.metadata_ops.apply_metadata_updates", return_value=[]),
            mock.patch("py.metadata_ops.download_preview", return_value=False),
            mock.patch("py.metadata_ops.refresh_cache") as mock_ref,
        ):
            await processor.process(
                skill_name="enrich_hf_metadata",
                model_path="/p.safetensors",
                llm_output=self.MIN_LLM_OUTPUT,
                metadata={"base_model": ""},
            )
        mock_ref.assert_not_called()


# ======================================================================
# Unit: _merge_tags
# ======================================================================


class TestMergeTags:
    def test_deduplicates_case_insensitive(self):
        existing = ["anime", "Flux"]
        new = ["flux", "LORA", "anime"]
        result = PostProcessor._merge_tags(existing, new)
        # All tags are lowercased (matching TagUpdateService behaviour)
        assert result == ["anime", "flux", "lora"]


# ======================================================================
# enrich_hf_metadata — site-provided card extras (ModelCardContext)
# ======================================================================


class TestSiteProvidedContext:
    """ModelScope keeps the author summary, the curated tags and the per-file
    example images outside the README; these tests pin how they are applied.
    """

    MODELSCOPE_METADATA = {
        "from_civitai": False,
        "source_platform": "modelscope",
        "source_url": "https://modelscope.cn/models/user/repo",
    }

    LLM_OUTPUT = {
        "base_model": "",
        "trigger_words": [],
        "short_description": "",
        "tags": [],
        "recommended_width": 0,
        "recommended_height": 0,
        "preview_url": "",
        "confidence": "medium",
    }

    @pytest.mark.asyncio
    async def test_example_images_become_gallery_and_preview(self, processor):
        """A boilerplate README still yields images and a downloaded preview."""
        context = ModelCardContext(
            example_images=[
                "https://resources.modelscope.cn/cover-images/a.png",
                "https://resources.modelscope.cn/cover-images/b.png",
            ]
        )
        boilerplate = "### 当前模型的贡献者未提供更加详细的模型介绍。\n"

        with (
            mock.patch("py.metadata_ops.apply_metadata_updates") as mock_apply,
            mock.patch("py.metadata_ops.download_preview") as mock_dl,
            mock.patch("py.metadata_ops.refresh_cache"),
        ):
            mock_dl.return_value = "/p.webp"
            result = await processor.process(
                skill_name="enrich_hf_metadata",
                model_path="/p.safetensors",
                llm_output=self.LLM_OUTPUT,
                metadata=dict(self.MODELSCOPE_METADATA),
                readme_content=boilerplate,
                source_context=context,
            )

        applied = mock_apply.call_args[0][1]
        images = applied["civitai"]["images"]
        assert [img["url"] for img in images] == context.example_images
        assert images[0]["type"] == "image"
        # The first (per-file) site image is used as the preview.
        mock_dl.assert_awaited_once_with(
            "/p.safetensors", "https://resources.modelscope.cn/cover-images/a.png"
        )
        assert applied["preview_url"] == "/p.webp"
        assert result["preview_downloaded"] is True

    @pytest.mark.asyncio
    async def test_example_images_work_without_any_readme(self, processor):
        """The site images alone are enough — the README may be unreachable."""
        context = ModelCardContext(
            example_images=["https://resources.modelscope.cn/cover-images/a.png"]
        )

        with (
            mock.patch("py.metadata_ops.apply_metadata_updates") as mock_apply,
            mock.patch("py.metadata_ops.download_preview", return_value=None),
            mock.patch("py.metadata_ops.refresh_cache"),
        ):
            await processor.process(
                skill_name="enrich_hf_metadata",
                model_path="/p.safetensors",
                llm_output=self.LLM_OUTPUT,
                metadata=dict(self.MODELSCOPE_METADATA),
                readme_content="",
                source_context=context,
            )

        images = mock_apply.call_args[0][1]["civitai"]["images"]
        assert [img["url"] for img in images] == context.example_images

    @pytest.mark.asyncio
    async def test_site_description_precedes_readme_in_model_description(self, processor):
        context = ModelCardContext(description="权重0.5-1.2。配合滤镜lora一起使用。")
        readme = "# 模型介绍\n\n本模型依托魔搭社区完成训练。\n"

        with (
            mock.patch("py.metadata_ops.apply_metadata_updates") as mock_apply,
            mock.patch("py.metadata_ops.download_preview", return_value=None),
            mock.patch("py.metadata_ops.refresh_cache"),
        ):
            await processor.process(
                skill_name="enrich_hf_metadata",
                model_path="/p.safetensors",
                llm_output=self.LLM_OUTPUT,
                metadata=dict(self.MODELSCOPE_METADATA),
                readme_content=readme,
                source_context=context,
            )

        description = mock_apply.call_args[0][1]["modelDescription"]
        assert description.startswith(f"<p>{context.description}</p>")
        assert "<h1>模型介绍</h1>" in description

    @pytest.mark.asyncio
    async def test_site_description_is_html_escaped(self, processor):
        context = ModelCardContext(description="a < b & c")

        with (
            mock.patch("py.metadata_ops.apply_metadata_updates") as mock_apply,
            mock.patch("py.metadata_ops.download_preview", return_value=None),
            mock.patch("py.metadata_ops.refresh_cache"),
        ):
            await processor.process(
                skill_name="enrich_hf_metadata",
                model_path="/p.safetensors",
                llm_output=self.LLM_OUTPUT,
                metadata=dict(self.MODELSCOPE_METADATA),
                readme_content="",
                source_context=context,
            )

        assert mock_apply.call_args[0][1]["modelDescription"] == "<p>a &lt; b &amp; c</p>"

    @pytest.mark.asyncio
    async def test_site_trigger_words_fill_in_when_llm_finds_none(self, processor):
        context = ModelCardContext(trigger_words=["kreaface", "kreamodel"])
        readme = "---\ninstance_prompt: yamlword\n---\nbody\n"

        with (
            mock.patch("py.metadata_ops.apply_metadata_updates") as mock_apply,
            mock.patch("py.metadata_ops.download_preview", return_value=None),
            mock.patch("py.metadata_ops.refresh_cache"),
        ):
            await processor.process(
                skill_name="enrich_hf_metadata",
                model_path="/p.safetensors",
                llm_output=self.LLM_OUTPUT,
                metadata=dict(self.MODELSCOPE_METADATA),
                readme_content=readme,
                source_context=context,
            )

        # The per-file site value wins over the repo-wide YAML instance_prompt.
        assert mock_apply.call_args[0][1]["civitai"]["trainedWords"] == [
            "kreaface",
            "kreamodel",
        ]

    @pytest.mark.asyncio
    async def test_yaml_instance_prompt_still_used_when_site_has_none(self, processor):
        context = ModelCardContext(description="summary only")
        readme = "---\ninstance_prompt: yamlword\n---\nbody\n"

        with (
            mock.patch("py.metadata_ops.apply_metadata_updates") as mock_apply,
            mock.patch("py.metadata_ops.download_preview", return_value=None),
            mock.patch("py.metadata_ops.refresh_cache"),
        ):
            await processor.process(
                skill_name="enrich_hf_metadata",
                model_path="/p.safetensors",
                llm_output=self.LLM_OUTPUT,
                metadata=dict(self.MODELSCOPE_METADATA),
                readme_content=readme,
                source_context=context,
            )

        assert mock_apply.call_args[0][1]["civitai"]["trainedWords"] == ["yamlword"]

    @pytest.mark.asyncio
    async def test_site_images_are_skipped_for_a_model_with_no_external_source(
        self, processor
    ):
        """A CivitAI-only model must not pick up ModelScope images."""
        context = ModelCardContext(
            example_images=["https://resources.modelscope.cn/cover-images/a.png"]
        )

        with (
            mock.patch("py.metadata_ops.apply_metadata_updates") as mock_apply,
            mock.patch("py.metadata_ops.download_preview", return_value=None),
            mock.patch("py.metadata_ops.refresh_cache"),
        ):
            await processor.process(
                skill_name="enrich_hf_metadata",
                model_path="/p.safetensors",
                llm_output=self.LLM_OUTPUT,
                metadata={"from_civitai": True},
                readme_content="",
                source_context=context,
            )

        assert "images" not in mock_apply.call_args[0][1].get("civitai", {})

    @pytest.mark.asyncio
    async def test_site_images_deduplicate_against_readme_images(self, processor):
        """A URL present in both the site data and the README appears once."""
        shared = "https://modelscope.cn/models/user/repo/resolve/master/sample.png"
        context = ModelCardContext(example_images=[shared])
        readme = f"![alt]({shared})\n"

        with (
            mock.patch("py.metadata_ops.apply_metadata_updates") as mock_apply,
            mock.patch("py.metadata_ops.download_preview", return_value=None),
            mock.patch("py.metadata_ops.refresh_cache"),
        ):
            await processor.process(
                skill_name="enrich_hf_metadata",
                model_path="/p.safetensors",
                llm_output=self.LLM_OUTPUT,
                metadata=dict(self.MODELSCOPE_METADATA),
                readme_content=readme,
                source_context=context,
            )

        images = mock_apply.call_args[0][1]["civitai"]["images"]
        assert [img["url"] for img in images] == [shared]

    @pytest.mark.asyncio
    async def test_empty_context_keeps_readme_only_behaviour(self, processor):
        """An empty site context must not change existing HF behaviour."""
        readme = "---\nwidget:\n- text: a cat\n  output:\n    url: images/cat.png\n---\n"
        with (
            mock.patch("py.metadata_ops.apply_metadata_updates") as mock_apply,
            mock.patch("py.metadata_ops.download_preview", return_value=None),
            mock.patch("py.metadata_ops.refresh_cache"),
        ):
            await processor.process(
                skill_name="enrich_hf_metadata",
                model_path="/p.safetensors",
                llm_output=self.LLM_OUTPUT,
                metadata={
                    "from_civitai": False,
                    "hf_url": "https://huggingface.co/user/repo",
                },
                readme_content=readme,
                source_context=ModelCardContext(),
            )
        images = mock_apply.call_args[0][1]["civitai"]["images"]
        assert [img["url"] for img in images] == [
            "https://huggingface.co/user/repo/resolve/main/images/cat.png"
        ]



# ======================================================================
# enrich_hf_metadata — deterministic fallbacks used when the LLM is skipped
# ======================================================================


class TestDeterministicFallbacks:
    """With the LLM skipped, these fields must still be produced from the API."""

    MODELSCOPE_METADATA = {
        "from_civitai": False,
        "source_platform": "modelscope",
        "source_url": "https://modelscope.cn/models/user/repo",
    }

    EMPTY_LLM = {
        "base_model": "",
        "trigger_words": [],
        "short_description": "",
        "tags": [],
        "recommended_width": 0,
        "recommended_height": 0,
        "preview_url": "",
        "notes": "",
        "usage_tips": "{}",
        "confidence": "",
    }

    @pytest.mark.asyncio
    async def test_resolved_base_model_used_when_llm_gave_none(self, processor):
        with (
            mock.patch("py.metadata_ops.apply_metadata_updates") as mock_apply,
            mock.patch("py.metadata_ops.download_preview", return_value=None),
            mock.patch("py.metadata_ops.refresh_cache"),
        ):
            await processor.process(
                skill_name="enrich_hf_metadata",
                model_path="/p.safetensors",
                llm_output=self.EMPTY_LLM,
                metadata=dict(self.MODELSCOPE_METADATA),
                source_context=ModelCardContext(base_model="krea/Krea-2-Turbo"),
                resolved_base_model="Krea 2",
            )
        assert mock_apply.call_args[0][1]["base_model"] == "Krea 2"

    @pytest.mark.asyncio
    async def test_llm_base_model_still_wins_over_the_resolver(self, processor):
        llm = {**self.EMPTY_LLM, "base_model": "Flux.1 D"}
        with (
            mock.patch("py.metadata_ops.apply_metadata_updates") as mock_apply,
            mock.patch("py.metadata_ops.download_preview", return_value=None),
            mock.patch("py.metadata_ops.refresh_cache"),
        ):
            await processor.process(
                skill_name="enrich_hf_metadata",
                model_path="/p.safetensors",
                llm_output=llm,
                metadata=dict(self.MODELSCOPE_METADATA),
                resolved_base_model="Krea 2",
            )
        assert mock_apply.call_args[0][1]["base_model"] == "Flux.1 D"

    @pytest.mark.asyncio
    async def test_site_description_fills_civitai_description(self, processor):
        context = ModelCardContext(description="一个 Krea 2 人像 LoRA。")
        with (
            mock.patch("py.metadata_ops.apply_metadata_updates") as mock_apply,
            mock.patch("py.metadata_ops.download_preview", return_value=None),
            mock.patch("py.metadata_ops.refresh_cache"),
        ):
            await processor.process(
                skill_name="enrich_hf_metadata",
                model_path="/p.safetensors",
                llm_output=self.EMPTY_LLM,
                metadata=dict(self.MODELSCOPE_METADATA),
                source_context=context,
            )
        assert (
            mock_apply.call_args[0][1]["civitai"]["description"]
            == "一个 Krea 2 人像 LoRA。"
        )

    @pytest.mark.asyncio
    async def test_llm_short_description_wins_over_site_description(self, processor):
        llm = {**self.EMPTY_LLM, "short_description": "from the LLM"}
        with (
            mock.patch("py.metadata_ops.apply_metadata_updates") as mock_apply,
            mock.patch("py.metadata_ops.download_preview", return_value=None),
            mock.patch("py.metadata_ops.refresh_cache"),
        ):
            await processor.process(
                skill_name="enrich_hf_metadata",
                model_path="/p.safetensors",
                llm_output=llm,
                metadata=dict(self.MODELSCOPE_METADATA),
                source_context=ModelCardContext(description="from the site"),
            )
        assert mock_apply.call_args[0][1]["civitai"]["description"] == "from the LLM"

    @pytest.mark.asyncio
    async def test_official_tags_are_applied_without_the_llm(self, processor):
        context = ModelCardContext(
            official_tags=["photography", "character-enhancement", "woman"]
        )
        with (
            mock.patch("py.metadata_ops.apply_metadata_updates") as mock_apply,
            mock.patch("py.metadata_ops.download_preview", return_value=None),
            mock.patch("py.metadata_ops.refresh_cache"),
        ):
            await processor.process(
                skill_name="enrich_hf_metadata",
                model_path="/p.safetensors",
                llm_output=self.EMPTY_LLM,
                metadata=dict(self.MODELSCOPE_METADATA),
                source_context=context,
            )
        assert mock_apply.call_args[0][1]["tags"] == [
            "photography",
            "character-enhancement",
            "woman",
        ]

    @pytest.mark.asyncio
    async def test_official_tags_are_kept_alongside_llm_tags(self, processor):
        context = ModelCardContext(official_tags=["photography", "woman"])
        llm = {**self.EMPTY_LLM, "tags": ["portrait", "photography"]}
        with (
            mock.patch("py.metadata_ops.apply_metadata_updates") as mock_apply,
            mock.patch("py.metadata_ops.download_preview", return_value=None),
            mock.patch("py.metadata_ops.refresh_cache"),
        ):
            await processor.process(
                skill_name="enrich_hf_metadata",
                model_path="/p.safetensors",
                llm_output=llm,
                metadata=dict(self.MODELSCOPE_METADATA),
                source_context=context,
            )
        # Site tags first, then the LLM's extra ones, no duplicates.
        assert mock_apply.call_args[0][1]["tags"] == [
            "photography",
            "woman",
            "portrait",
        ]

    @pytest.mark.asyncio
    async def test_usage_tips_recovered_from_the_author_summary(self, processor):
        context = ModelCardContext(
            description="权重0.5-1.2。2个一起时，权重建议都用1.0-1.1。"
        )
        with (
            mock.patch("py.metadata_ops.apply_metadata_updates") as mock_apply,
            mock.patch("py.metadata_ops.download_preview", return_value=None),
            mock.patch("py.metadata_ops.refresh_cache"),
        ):
            await processor.process(
                skill_name="enrich_hf_metadata",
                model_path="/p.safetensors",
                llm_output=self.EMPTY_LLM,
                metadata=dict(self.MODELSCOPE_METADATA),
                source_context=context,
            )
        tips = json.loads(mock_apply.call_args[0][1]["usage_tips"])
        assert tips == {
            "strength_min": 0.5,
            "strength_max": 1.2,
            "strength_range": "0.5-1.2",
        }

    @pytest.mark.asyncio
    async def test_llm_usage_tips_win_over_the_regex(self, processor):
        llm = {**self.EMPTY_LLM, "usage_tips": '{"strength": 0.9}'}
        with (
            mock.patch("py.metadata_ops.apply_metadata_updates") as mock_apply,
            mock.patch("py.metadata_ops.download_preview", return_value=None),
            mock.patch("py.metadata_ops.refresh_cache"),
        ):
            await processor.process(
                skill_name="enrich_hf_metadata",
                model_path="/p.safetensors",
                llm_output=llm,
                metadata=dict(self.MODELSCOPE_METADATA),
                source_context=ModelCardContext(description="权重0.5-1.2"),
            )
        assert mock_apply.call_args[0][1]["usage_tips"] == '{"strength": 0.9}'

    @pytest.mark.asyncio
    async def test_notes_are_not_rewritten_when_the_llm_is_skipped(self, processor):
        """Notes are LLM-only; skipping must not clobber or duplicate them."""
        with (
            mock.patch("py.metadata_ops.apply_metadata_updates") as mock_apply,
            mock.patch("py.metadata_ops.download_preview", return_value=None),
            mock.patch("py.metadata_ops.refresh_cache"),
        ):
            await processor.process(
                skill_name="enrich_hf_metadata",
                model_path="/p.safetensors",
                llm_output=self.EMPTY_LLM,
                metadata={**self.MODELSCOPE_METADATA, "notes": "existing notes"},
                source_context=ModelCardContext(description="权重0.5-1.2"),
            )
        assert "notes" not in mock_apply.call_args[0][1]

    @pytest.mark.asyncio
    async def test_no_site_data_leaves_llm_only_fields_untouched(self, processor):
        """An empty context must behave exactly like the pre-existing pipeline."""
        with (
            mock.patch("py.metadata_ops.apply_metadata_updates") as mock_apply,
            mock.patch("py.metadata_ops.download_preview", return_value=None),
            mock.patch("py.metadata_ops.refresh_cache"),
        ):
            await processor.process(
                skill_name="enrich_hf_metadata",
                model_path="/p.safetensors",
                llm_output=self.EMPTY_LLM,
                metadata=dict(self.MODELSCOPE_METADATA),
                source_context=ModelCardContext(),
                resolved_base_model="",
            )
        applied = mock_apply.call_args[0][1]
        assert "base_model" not in applied
        assert "tags" not in applied
        assert "notes" not in applied
        assert "usage_tips" not in applied


class TestPlaceholderCardDescription:
    """A site-generated placeholder card must not become the description."""

    MODELSCOPE_METADATA = {
        "from_civitai": False,
        "source_platform": "modelscope",
        "source_url": "https://modelscope.cn/models/user/repo",
    }

    PLACEHOLDER_README = """---
base_model: krea/Krea-2-Turbo
---
### 当前模型的贡献者未提供更加详细的模型介绍。模型文件和权重，可浏览“模型文件”页面获取。
#### 您可以通过如下git clone命令，或者ModelScope SDK来下载模型

SDK下载
```bash
pip install modelscope
```

<p style="color: lightgrey;">如果您是本模型的贡献者，我们邀请您根据文档及时完善模型卡片内容。</p>
"""

    LLM_OUTPUT = {
        "base_model": "Krea 2",
        "trigger_words": [],
        "short_description": "一个 Krea 2 人像 LoRA。",
        "tags": [],
        "recommended_width": 0,
        "recommended_height": 0,
        "preview_url": "",
        "notes": "",
        "usage_tips": "{}",
        "confidence": "medium",
    }

    @pytest.mark.asyncio
    async def test_description_holds_only_the_author_summary(self, processor):
        context = ModelCardContext(description="权重0.5-1.2。")
        with (
            mock.patch("py.metadata_ops.apply_metadata_updates") as mock_apply,
            mock.patch("py.metadata_ops.download_preview", return_value=None),
            mock.patch("py.metadata_ops.refresh_cache"),
        ):
            await processor.process(
                skill_name="enrich_hf_metadata",
                model_path="/p.safetensors",
                llm_output=self.LLM_OUTPUT,
                metadata=dict(self.MODELSCOPE_METADATA),
                readme_content=self.PLACEHOLDER_README,
                source_context=context,
            )

        description = mock_apply.call_args[0][1]["modelDescription"]
        assert description == "<p>权重0.5-1.2。</p>"
        assert "pip install modelscope" not in description
        assert "git clone" not in description
        assert "贡献者" not in description

    @pytest.mark.asyncio
    async def test_placeholder_card_alone_writes_no_description(self, processor):
        """Without an author summary there is nothing worth storing."""
        with (
            mock.patch("py.metadata_ops.apply_metadata_updates") as mock_apply,
            mock.patch("py.metadata_ops.download_preview", return_value=None),
            mock.patch("py.metadata_ops.refresh_cache"),
        ):
            await processor.process(
                skill_name="enrich_hf_metadata",
                model_path="/p.safetensors",
                llm_output=self.LLM_OUTPUT,
                metadata=dict(self.MODELSCOPE_METADATA),
                readme_content=self.PLACEHOLDER_README,
                source_context=ModelCardContext(),
            )

        assert "modelDescription" not in mock_apply.call_args[0][1]

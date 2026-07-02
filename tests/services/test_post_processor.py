"""Tests for the PostProcessor (py/services/agent/post_processor.py).

PostProcessor delegates all I/O to AgentCLI — these tests mock AgentCLI
functions and verify the business logic (conditions, merges, dispatch).
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest import mock

import pytest

from py.services.agent.post_processor import PostProcessor


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
            mock.patch("py.agent_cli.apply_metadata_updates") as mock_apply,
            mock.patch("py.agent_cli.download_preview") as mock_dl,
            mock.patch("py.agent_cli.refresh_cache") as mock_ref,
        ):
            mock_apply.return_value = ["metadata_source"]
            mock_dl.return_value = False

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
        "description": "",
        "tags": [],
        "preview_url": "",
        "confidence": "low",
    }

    # -- base_model ------------------------------------------------------

    @pytest.mark.asyncio
    async def test_base_model_overwrites_empty(self, processor):
        """Empty current base_model → new value is applied."""
        llm = {**self.MIN_LLM_OUTPUT, "base_model": "Flux.1 D"}
        with (
            mock.patch("py.agent_cli.apply_metadata_updates") as mock_apply,
            mock.patch("py.agent_cli.download_preview", return_value=False),
            mock.patch("py.agent_cli.refresh_cache"),
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
            mock.patch("py.agent_cli.apply_metadata_updates") as mock_apply,
            mock.patch("py.agent_cli.download_preview", return_value=False),
            mock.patch("py.agent_cli.refresh_cache"),
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
            mock.patch("py.agent_cli.apply_metadata_updates") as mock_apply,
            mock.patch("py.agent_cli.download_preview", return_value=False),
            mock.patch("py.agent_cli.refresh_cache"),
        ):
            await processor.process(
                skill_name="enrich_hf_metadata",
                model_path="/p.safetensors",
                llm_output=llm,
                metadata={"base_model": "SD 1.5", "from_civitai": False},
            )
        applied = mock_apply.call_args[0][1]
        assert applied["base_model"] == "Flux.1 D"

    @pytest.mark.asyncio
    async def test_base_model_skipped_when_llm_empty(self, processor):
        """LLM returns empty base_model → nothing written."""
        with (
            mock.patch("py.agent_cli.apply_metadata_updates") as mock_apply,
            mock.patch("py.agent_cli.download_preview", return_value=False),
            mock.patch("py.agent_cli.refresh_cache"),
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
            mock.patch("py.agent_cli.apply_metadata_updates") as mock_apply,
            mock.patch("py.agent_cli.download_preview", return_value=False),
            mock.patch("py.agent_cli.refresh_cache"),
        ):
            await processor.process(
                skill_name="enrich_hf_metadata",
                model_path="/p.safetensors",
                llm_output=llm,
                metadata={"trainedWords": []},
            )
        applied = mock_apply.call_args[0][1]
        assert applied["trainedWords"] == ["trigger1", "trigger2"]

    # -- description -----------------------------------------------------

    @pytest.mark.asyncio
    async def test_description_set_when_empty(self, processor):
        llm = {**self.MIN_LLM_OUTPUT, "description": "A model description"}
        with (
            mock.patch("py.agent_cli.apply_metadata_updates") as mock_apply,
            mock.patch("py.agent_cli.download_preview", return_value=False),
            mock.patch("py.agent_cli.refresh_cache"),
        ):
            await processor.process(
                skill_name="enrich_hf_metadata",
                model_path="/p.safetensors",
                llm_output=llm,
                metadata={"modelDescription": ""},
            )
        assert "modelDescription" in mock_apply.call_args[0][1]

    # -- tags ------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_tags_merged_and_deduplicated(self, processor):
        llm = {**self.MIN_LLM_OUTPUT, "tags": ["flux", "lora", "STYLE"]}
        with (
            mock.patch("py.agent_cli.apply_metadata_updates") as mock_apply,
            mock.patch("py.agent_cli.download_preview", return_value=False),
            mock.patch("py.agent_cli.refresh_cache"),
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
            mock.patch("py.agent_cli.apply_metadata_updates") as mock_apply,
            mock.patch("py.agent_cli.download_preview", return_value=False),
            mock.patch("py.agent_cli.refresh_cache"),
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

    # -- preview download ------------------------------------------------

    @pytest.mark.asyncio
    async def test_preview_downloaded_when_url_provided(self, processor):
        llm = {**self.MIN_LLM_OUTPUT, "preview_url": "https://ex.com/img.png"}
        with (
            mock.patch("py.agent_cli.apply_metadata_updates") as mock_apply,
            mock.patch("py.agent_cli.download_preview") as mock_dl,
            mock.patch("py.agent_cli.refresh_cache"),
        ):
            mock_dl.return_value = True
            result = await processor.process(
                skill_name="enrich_hf_metadata",
                model_path="/p.safetensors",
                llm_output=llm,
                metadata={},
            )
        assert result["preview_downloaded"] is True
        mock_dl.assert_awaited_once_with("/p.safetensors", "https://ex.com/img.png")

    @pytest.mark.asyncio
    async def test_preview_skipped_when_exists(self, processor):
        """If current_preview file exists on disk, skip download."""
        llm = {**self.MIN_LLM_OUTPUT, "preview_url": "https://ex.com/img.png"}
        with (
            mock.patch("py.agent_cli.apply_metadata_updates"),
            mock.patch("py.agent_cli.download_preview") as mock_dl,
            mock.patch("py.agent_cli.refresh_cache"),
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
            mock.patch("py.agent_cli.apply_metadata_updates", return_value=["base_model"]),
            mock.patch("py.agent_cli.download_preview", return_value=False),
            mock.patch("py.agent_cli.refresh_cache") as mock_ref,
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
            mock.patch("py.agent_cli.apply_metadata_updates", return_value=[]),
            mock.patch("py.agent_cli.download_preview", return_value=False),
            mock.patch("py.agent_cli.refresh_cache") as mock_ref,
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

"""Tests for source-aware AI enrichment orchestration.

Covers the fast-fail gate (:meth:`AgentService._enrichment_skip_reason`) and
the prompt-context builder for non-Hugging Face model sources.
"""

from __future__ import annotations

from unittest import mock

import pytest

from py.services.agent.agent_service import AgentService


class TestEnrichmentSkipReason:
    def test_skips_when_no_source_linked(self):
        reason = AgentService._enrichment_skip_reason({})
        assert "source_url" in reason

    def test_allows_huggingface(self):
        assert (
            AgentService._enrichment_skip_reason(
                {"hf_url": "https://huggingface.co/user/repo"}
            )
            == ""
        )

    def test_allows_modelscope(self):
        assert (
            AgentService._enrichment_skip_reason(
                {
                    "source_platform": "modelscope",
                    "source_url": "https://modelscope.cn/models/user/repo",
                }
            )
            == ""
        )

    def test_skips_tensorart_with_reason(self):
        reason = AgentService._enrichment_skip_reason(
            {
                "source_platform": "tensorart",
                "source_url": "https://tensor.art/models/827823520299086029",
            }
        )
        assert "TensorArt" in reason
        assert "not available" in reason

    def test_skips_unknown_platform(self):
        reason = AgentService._enrichment_skip_reason(
            {"source_platform": "somewhere", "source_url": "https://somewhere.example/m/1"}
        )
        assert "somewhere" in reason


class TestBuildPromptContext:
    @pytest.mark.asyncio
    async def test_modelscope_card_populates_source_variables(self):
        service = AgentService()
        readme = "---\nbase_model: krea/Krea-2-Turbo\n---\n# krea\n"

        with (
            mock.patch(
                "py.services.model_sources.modelscope.ModelScopeSource.fetch_model_card",
                new=mock.AsyncMock(return_value=readme),
            ) as mock_fetch,
            mock.patch(
                "py.metadata_ops.list_base_models",
                new=mock.AsyncMock(return_value=["Krea 2 Turbo"]),
            ),
            mock.patch(
                "py.metadata_ops.identify_model_type",
                new=mock.AsyncMock(return_value="lora"),
            ),
            mock.patch(
                "py.services.settings_manager.SettingsManager.get_priority_tag_config",
                return_value={"lora": "style, subject"},
            ),
        ):
            context = await service._build_prompt_context(
                skill_name="enrich_hf_metadata",
                model_path="/models/loras/krea.safetensors",
                metadata={
                    "source_platform": "modelscope",
                    "source_url": "https://modelscope.cn/models/jj3550945163/Krea-2-LORA",
                    "file_name": "krea",
                },
                registry=mock.Mock(),
                llm=mock.Mock(),
            )

        mock_fetch.assert_awaited_once_with("jj3550945163/Krea-2-LORA")
        assert context["source_platform"] == "modelscope"
        assert context["source_id"] == "jj3550945163/Krea-2-LORA"
        assert context["source_label"] == "ModelScope"
        assert (
            context["asset_base_url"]
            == "https://modelscope.cn/models/jj3550945163/Krea-2-LORA/resolve/master"
        )
        assert readme in context["readme_content_full"]
        # Hugging Face aliases stay empty for a non-HF source.
        assert context["hf_url"] == ""
        assert context["repo"] == "jj3550945163/Krea-2-LORA"

    @pytest.mark.asyncio
    async def test_huggingface_keeps_legacy_aliases(self):
        service = AgentService()
        readme = "# card\n"

        with (
            mock.patch(
                "py.services.model_sources.huggingface.HuggingFaceSource.fetch_model_card",
                new=mock.AsyncMock(return_value=readme),
            ) as mock_fetch,
            mock.patch(
                "py.metadata_ops.list_base_models",
                new=mock.AsyncMock(return_value=[]),
            ),
            mock.patch(
                "py.metadata_ops.identify_model_type",
                new=mock.AsyncMock(return_value="lora"),
            ),
            mock.patch(
                "py.services.settings_manager.SettingsManager.get_priority_tag_config",
                return_value={},
            ),
        ):
            context = await service._build_prompt_context(
                skill_name="enrich_hf_metadata",
                model_path="/models/loras/thing.safetensors",
                metadata={"hf_url": "https://huggingface.co/user/repo"},
                registry=mock.Mock(),
                llm=mock.Mock(),
            )

        mock_fetch.assert_awaited_once_with("user/repo")
        assert context["source_platform"] == "huggingface"
        assert context["hf_url"] == "https://huggingface.co/user/repo"
        assert context["repo"] == "user/repo"

    @pytest.mark.asyncio
    async def test_tensorart_never_fetches_a_card(self):
        service = AgentService()

        with (
            mock.patch(
                "py.services.model_sources.huggingface.HuggingFaceSource.fetch_model_card",
                new=mock.AsyncMock(),
            ) as hf_fetch,
            mock.patch(
                "py.services.model_sources.modelscope.ModelScopeSource.fetch_model_card",
                new=mock.AsyncMock(),
            ) as ms_fetch,
            mock.patch(
                "py.metadata_ops.list_base_models",
                new=mock.AsyncMock(return_value=[]),
            ),
            mock.patch(
                "py.metadata_ops.identify_model_type",
                new=mock.AsyncMock(return_value="lora"),
            ),
            mock.patch(
                "py.services.settings_manager.SettingsManager.get_priority_tag_config",
                return_value={},
            ),
        ):
            context = await service._build_prompt_context(
                skill_name="enrich_hf_metadata",
                model_path="/models/loras/thing.safetensors",
                metadata={
                    "source_platform": "tensorart",
                    "source_url": "https://tensor.art/models/827823520299086029",
                },
                registry=mock.Mock(),
                llm=mock.Mock(),
            )

        hf_fetch.assert_not_awaited()
        ms_fetch.assert_not_awaited()
        assert context["readme_content"] == ""
        assert context["source_platform"] == "tensorart"
"""Tests for source-aware AI enrichment orchestration.

Covers the fast-fail gate (:meth:`AgentService._enrichment_skip_reason`) and
the prompt-context builder for non-Hugging Face model sources.
"""

from __future__ import annotations

from unittest import mock

import pytest

from py.services.agent.agent_service import AgentService
from py.services.model_sources import ModelCardContext


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
        card_context = ModelCardContext(
            description="权重0.5-1.2。配合《krea2-Cc-MJ-风格滤镜》lora一起使用。",
            base_model="krea/Krea-2-Turbo",
            official_tags=["photography", "woman"],
            example_images=["https://resources.modelscope.cn/cover-images/a.png"],
            trigger_words=["kreamodel"],
        )

        with (
            mock.patch(
                "py.services.model_sources.modelscope.ModelScopeSource.fetch_model_card",
                new=mock.AsyncMock(return_value=readme),
            ) as mock_fetch,
            mock.patch(
                "py.services.model_sources.modelscope.ModelScopeSource.fetch_model_card_context",
                new=mock.AsyncMock(return_value=card_context),
            ) as mock_context,
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
        # The per-file lookup must receive the basename, not the full path.
        mock_context.assert_awaited_once()
        assert mock_context.call_args.args == (
            "jj3550945163/Krea-2-LORA",
            "krea.safetensors",
        )
        assert context["source_platform"] == "modelscope"
        assert context["source_id"] == "jj3550945163/Krea-2-LORA"
        assert context["source_label"] == "ModelScope"
        assert (
            context["asset_base_url"]
            == "https://modelscope.cn/models/jj3550945163/Krea-2-LORA/resolve/master"
        )
        assert readme in context["readme_content_full"]
        # Site-provided extras are rendered into their own prompt variables.
        assert context["source_description"] == card_context.description
        assert context["source_base_model"] == "krea/Krea-2-Turbo"
        assert context["source_official_tags"] == "- photography\n- woman"
        assert (
            context["source_example_images"]
            == "- https://resources.modelscope.cn/cover-images/a.png"
        )
        assert context["source_trigger_words"] == "kreamodel"
        # The structured context is carried through for the post-processor.
        assert context["source_context"] is card_context
        # Hugging Face aliases stay empty for a non-HF source.
        assert context["hf_url"] == ""
        assert context["repo"] == "jj3550945163/Krea-2-LORA"

    @pytest.mark.asyncio
    async def test_huggingface_card_context_is_empty(self):
        """Sources without card extras contribute empty prompt variables."""
        service = AgentService()

        with (
            mock.patch(
                "py.services.model_sources.huggingface.HuggingFaceSource.fetch_model_card",
                new=mock.AsyncMock(return_value="# card\n"),
            ),
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

        assert context["source_description"] == ""
        assert context["source_official_tags"] == ""
        assert context["source_example_images"] == ""
        assert context["source_context"].is_empty()

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

class TestExecuteSkillThreadsSourceContext:
    """The structured site context must reach the post-processor intact."""

    @pytest.mark.asyncio
    async def test_source_context_reaches_the_post_processor(self):
        service = AgentService()
        card_context = ModelCardContext(
            example_images=["https://resources.modelscope.cn/cover-images/a.png"]
        )
        skill = mock.Mock(llm_required=True, input_schema={})
        registry = mock.Mock()
        registry.get_skill.return_value = skill
        registry.load_prompt.return_value = "{{model_path}}"

        llm = mock.Mock()
        llm.is_configured.return_value = True
        llm.chat_completion_json = mock.AsyncMock(return_value={"base_model": "Krea 2"})

        source_vars = {
            "readme_content_full": "# card",
            "source_description": "",
            "source_base_model": "",
            "source_official_tags": "",
            "source_example_images": "",
            "source_trigger_words": "",
            "asset_base_url": "",
            "readme_content": "# card",
        }

        with (
            mock.patch.object(
                service, "_ensure_registry", new=mock.AsyncMock(return_value=registry)
            ),
            mock.patch.object(
                service, "_ensure_llm", new=mock.AsyncMock(return_value=llm)
            ),
            mock.patch.object(
                service,
                "_load_source_card",
                new=mock.AsyncMock(return_value=(source_vars, card_context)),
            ),
            mock.patch.object(
                service,
                "_build_prompt_context",
                new=mock.AsyncMock(
                    return_value={
                        "model_path": "/p.safetensors",
                        "readme_content_full": "# card",
                        "source_context": card_context,
                    }
                ),
            ),
            mock.patch(
                "py.metadata_ops.read_metadata",
                new=mock.AsyncMock(
                    return_value={
                        "source_platform": "modelscope",
                        "source_url": "https://modelscope.cn/models/u/r",
                    }
                ),
            ),
            mock.patch(
                "py.services.agent.agent_service.PostProcessor.process",
                new=mock.AsyncMock(
                    return_value={"success": True, "updated_fields": []}
                ),
            ) as mock_process,
        ):
            result = await service.execute_skill(
                skill_name="enrich_hf_metadata",
                input_data={"model_paths": ["/p.safetensors"]},
            )

        assert result.success is True
        assert mock_process.call_args.kwargs["source_context"] is card_context
        assert mock_process.call_args.kwargs["readme_content"] == "# card"


class TestSiteDataAppliedWithoutLlm:
    """A: the site's deterministic data must land even with no LLM available."""

    @staticmethod
    def _run(service, *, llm_configured: bool, card_context: ModelCardContext):
        skill = mock.Mock(llm_required=True, input_schema={})
        registry = mock.Mock()
        registry.get_skill.return_value = skill
        registry.load_prompt.return_value = "{{model_path}}"

        llm = mock.Mock()
        llm.is_configured.return_value = llm_configured
        llm.chat_completion_json = mock.AsyncMock(return_value={"base_model": "Krea 2"})

        source_vars = {
            "readme_content_full": "# card",
            "source_description": card_context.description,
            "source_base_model": card_context.base_model,
            "source_official_tags": "",
            "source_example_images": "",
            "source_trigger_words": "",
            "asset_base_url": "",
            "readme_content": "# card",
        }
        return skill, registry, llm, source_vars

    @pytest.mark.asyncio
    async def test_unconfigured_llm_still_applies_site_data(self):
        service = AgentService()
        card_context = ModelCardContext(
            description="作者说明",
            base_model="krea/Krea-2-Turbo",
            official_tags=["photography"],
            example_images=["https://cdn.example/a.png"],
        )
        skill, registry, llm, source_vars = self._run(
            service, llm_configured=False, card_context=card_context
        )

        with (
            mock.patch.object(
                service, "_ensure_registry", new=mock.AsyncMock(return_value=registry)
            ),
            mock.patch.object(
                service, "_ensure_llm", new=mock.AsyncMock(return_value=llm)
            ),
            mock.patch.object(
                service,
                "_load_source_card",
                new=mock.AsyncMock(return_value=(source_vars, card_context)),
            ),
            mock.patch.object(
                service, "_resolve_site_base_model", new=mock.AsyncMock(return_value="Krea 2")
            ),
            mock.patch(
                "py.metadata_ops.read_metadata",
                new=mock.AsyncMock(
                    return_value={
                        "source_platform": "modelscope",
                        "source_url": "https://modelscope.cn/models/u/r",
                    }
                ),
            ),
            mock.patch(
                "py.services.agent.agent_service.PostProcessor.process",
                new=mock.AsyncMock(
                    return_value={"success": True, "updated_fields": []}
                ),
            ) as mock_process,
        ):
            result = await service.execute_skill(
                skill_name="enrich_hf_metadata",
                input_data={"model_paths": ["/p.safetensors"]},
            )

        assert result.success is True
        # No LLM call, but the deterministic payload reached the post-processor.
        llm.chat_completion_json.assert_not_awaited()
        kwargs = mock_process.call_args.kwargs
        assert kwargs["source_context"] is card_context
        assert kwargs["readme_content"] == "# card"
        assert kwargs["resolved_base_model"] == "Krea 2"
        assert kwargs["llm_output"] == {}


class TestLoadSourceCard:
    @pytest.mark.asyncio
    async def test_returns_empty_variables_without_a_source(self):
        service = AgentService()
        variables, context = await service._load_source_card("/p.safetensors", {})
        assert context.is_empty() is True
        assert variables["readme_content_full"] == ""
        assert variables["readme_content"] == "(README not available)"

    @pytest.mark.asyncio
    async def test_collects_readme_and_site_extras(self):
        service = AgentService()
        card = ModelCardContext(
            description="作者说明",
            base_model="krea/Krea-2-Turbo",
            official_tags=["photography", "woman"],
            example_images=["https://cdn.example/a.png"],
            trigger_words=["kreaface"],
        )
        with (
            mock.patch(
                "py.services.model_sources.modelscope.ModelScopeSource.fetch_model_card",
                new=mock.AsyncMock(return_value="# card"),
            ),
            mock.patch(
                "py.services.model_sources.modelscope.ModelScopeSource.fetch_model_card_context",
                new=mock.AsyncMock(return_value=card),
            ) as mock_ctx,
        ):
            variables, context = await service._load_source_card(
                "/models/loras/krea.safetensors",
                {
                    "source_platform": "modelscope",
                    "source_url": "https://modelscope.cn/models/u/r",
                },
            )

        mock_ctx.assert_awaited_once()
        assert mock_ctx.call_args.args == ("u/r", "krea.safetensors")
        assert context is card
        assert variables["readme_content_full"] == "# card"
        assert variables["source_description"] == "作者说明"
        assert variables["source_official_tags"] == "- photography\n- woman"
        assert variables["source_example_images"] == "- https://cdn.example/a.png"
        assert variables["source_trigger_words"] == "kreaface"
        assert variables["asset_base_url"].endswith("/resolve/master")

    @pytest.mark.asyncio
    async def test_resolve_site_base_model_uses_the_canonical_vocabulary(self):
        service = AgentService()
        with mock.patch(
            "py.metadata_ops.list_base_models",
            new=mock.AsyncMock(return_value=["Krea 2", "Flux.1 D"]),
        ):
            resolved = await service._resolve_site_base_model(
                ModelCardContext(
                    base_model="krea/Krea-2-Turbo",
                    base_model_aliases=["KREA_2", "KREA_2_TURBO"],
                )
            )
        assert resolved == "Krea 2"

    @pytest.mark.asyncio
    async def test_resolve_site_base_model_is_empty_without_hints(self):
        service = AgentService()
        assert await service._resolve_site_base_model(ModelCardContext()) == ""


class TestLlmAlwaysRunsWhenConfigured:
    """Clicking "Enrich Metadata with AI" must always consult the LLM.

    The site-provided data is applied deterministically either way, but it is
    never treated as a reason to skip the call — the LLM's summary and notes
    are richer than the raw site fields, and silently not calling out to the
    provider would make the menu action unpredictable.
    """

    @pytest.mark.asyncio
    async def test_llm_runs_even_when_the_site_supplies_everything(self):
        service = AgentService()
        card_context = ModelCardContext(
            description="作者说明",
            base_model="krea/Krea-2-Turbo",
            base_model_aliases=["KREA_2"],
            official_tags=["photography", "woman"],
            example_images=["https://cdn.example/a.png"],
            trigger_words=["kreaface"],
        )
        skill = mock.Mock(llm_required=True, input_schema={})
        registry = mock.Mock()
        registry.get_skill.return_value = skill
        registry.load_prompt.return_value = "{{model_path}}"

        llm = mock.Mock()
        llm.is_configured.return_value = True
        llm.chat_completion_json = mock.AsyncMock(
            return_value={"base_model": "Krea 2", "short_description": "llm summary"}
        )

        source_vars = {
            "readme_content_full": "# card",
            "source_description": card_context.description,
            "source_base_model": card_context.base_model,
            "source_official_tags": "- photography\n- woman",
            "source_example_images": "- https://cdn.example/a.png",
            "source_trigger_words": "kreaface",
            "asset_base_url": "",
            "readme_content": "# card",
        }

        with (
            mock.patch.object(
                service, "_ensure_registry", new=mock.AsyncMock(return_value=registry)
            ),
            mock.patch.object(
                service, "_ensure_llm", new=mock.AsyncMock(return_value=llm)
            ),
            mock.patch.object(
                service,
                "_load_source_card",
                new=mock.AsyncMock(return_value=(source_vars, card_context)),
            ),
            mock.patch.object(
                service,
                "_build_prompt_context",
                new=mock.AsyncMock(
                    return_value={"model_path": "/p.safetensors", "system_prompt": "sys"}
                ),
            ) as mock_prompt,
            mock.patch(
                "py.metadata_ops.read_metadata",
                new=mock.AsyncMock(
                    return_value={
                        "source_platform": "modelscope",
                        "source_url": "https://modelscope.cn/models/u/r",
                        "base_model": "Krea 2",
                    }
                ),
            ),
            mock.patch(
                "py.services.agent.agent_service.PostProcessor.process",
                new=mock.AsyncMock(
                    return_value={"success": True, "updated_fields": []}
                ),
            ),
        ):
            result = await service.execute_skill(
                skill_name="enrich_hf_metadata",
                input_data={"model_paths": ["/p.safetensors"]},
            )

        assert result.success is True
        llm.chat_completion_json.assert_awaited_once()
        # The prompt is built from the already-fetched card, not re-fetched.
        assert mock_prompt.call_args.kwargs["source_context"] is card_context
        assert mock_prompt.call_args.kwargs["source_vars"] is source_vars


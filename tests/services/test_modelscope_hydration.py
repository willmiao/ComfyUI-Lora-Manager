"""Tests for download-time metadata hydration.

`py/services/model_sources/hydration.py` is the deterministic counterpart of
the `enrich_hf_metadata` skill: it turns a freshly downloaded ModelScope /
Hugging Face file into the populated model card a CivitAI download produces,
without an LLM and without the user running anything.

These tests cover the orchestration — which source data is fetched, what is
handed to the post-processor, and that nothing here can fail a download. The
field-by-field mapping lives in `tests/services/test_post_processor.py`.
"""

from __future__ import annotations

import pytest

from py.services.model_sources import ModelCardContext, ModelSourceCache, SourceRef
from py.services.model_sources import hydration
from py.services.model_sources.base import ModelSource
from py.services.model_sources.hydration import (
    SHARED_CACHE_MAX_ENTRIES,
    hydrate_from_source,
    load_model_card,
    reset_shared_caches,
    resolve_site_base_model,
    shared_source_cache,
)

REF = SourceRef(
    platform="modelscope",
    source_id="user/repo",
    url="https://modelscope.cn/models/user/repo",
)

SIDECAR = {
    "sha256": "a" * 64,
    "base_model": "Unknown",
    # Written by the download handler just before hydration runs.
    "source_platform": "modelscope",
    "source_url": "https://modelscope.cn/models/user/repo",
}


class _FakeSource(ModelSource):
    """Minimal provider that records what hydration asked of it."""

    platform = "modelscope"
    label = "ModelScope"
    supports_enrichment = True

    def __init__(self, *, context=None, readme="", fail=False):
        self.context = context if context is not None else ModelCardContext()
        self.readme = readme
        self.fail = fail
        self.readme_calls = 0
        self.context_calls = 0
        self.context_kwargs: dict = {}

    async def fetch_model_card(self, source_id):
        self.readme_calls += 1
        if self.fail:
            raise RuntimeError("network down")
        return self.readme

    async def fetch_model_card_context(
        self, source_id, filename="", *, sha256="", cache=None
    ):
        self.context_calls += 1
        self.context_kwargs = {"filename": filename, "sha256": sha256}
        if self.fail:
            raise RuntimeError("network down")
        return self.context


@pytest.fixture(autouse=True)
def _isolated_shared_caches():
    reset_shared_caches()
    yield
    reset_shared_caches()


def _async(value):
    async def _call(*_args, **_kwargs):
        return value

    return _call


def _wire(monkeypatch, source, *, metadata=SIDECAR, result=None):
    """Patch hydration's collaborators; return the recorded process() calls."""

    monkeypatch.setattr(hydration, "get_source", lambda _platform: source)
    monkeypatch.setattr("py.metadata_ops.read_metadata", _async(metadata))

    calls: list = []

    class _Processor:
        async def process(self, **kwargs):
            calls.append(kwargs)
            if result is not None:
                return result
            return {"success": True, "updated_fields": ["model_name"]}

    monkeypatch.setattr("py.services.agent.post_processor.PostProcessor", _Processor)
    return calls


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


class TestHydrateFromSource:
    @pytest.mark.asyncio
    async def test_applies_the_site_card_without_an_llm(self, monkeypatch):
        source = _FakeSource(
            context=ModelCardContext(
                model_name="Krea-2-LORA",
                version_name="c1-st1000",
                description="权重0.5-1.2。",
                official_tags=["photography"],
            ),
            readme="# Krea-2-LORA",
        )
        calls = _wire(monkeypatch, source)

        updated = await hydrate_from_source("/models/lora.safetensors", ref=REF)

        assert updated == ["model_name"]
        assert len(calls) == 1
        call = calls[0]
        # No provider is consulted: everything applied is what the site published.
        assert call["llm_output"] == {}
        assert call["skill_name"] == "enrich_hf_metadata"
        assert call["readme_content"] == "# Krea-2-LORA"
        assert call["source_context"].model_name == "Krea-2-LORA"
        assert call["metadata_source"] == "source:modelscope"

    @pytest.mark.asyncio
    async def test_matches_the_file_by_hash_and_basename(self, monkeypatch):
        source = _FakeSource(context=ModelCardContext(model_name="X"))
        _wire(monkeypatch, source)

        await hydrate_from_source("/models/sub/Krea-2-LORA_c1-st1000.safetensors", ref=REF)

        assert source.context_kwargs == {
            "filename": "Krea-2-LORA_c1-st1000.safetensors",
            "sha256": "a" * 64,
        }

    @pytest.mark.asyncio
    async def test_returns_early_for_an_unknown_platform(self, monkeypatch):
        source = _FakeSource(context=ModelCardContext(model_name="X"))
        calls = _wire(monkeypatch, source)
        monkeypatch.setattr(hydration, "get_source", lambda _platform: None)

        assert await hydrate_from_source("/models/lora.safetensors", ref=REF) == []
        assert calls == []

    @pytest.mark.asyncio
    async def test_returns_early_for_a_link_only_source(self, monkeypatch):
        source = _FakeSource(context=ModelCardContext(model_name="X"))
        source.supports_enrichment = False
        calls = _wire(monkeypatch, source)

        assert await hydrate_from_source("/models/lora.safetensors", ref=REF) == []
        assert calls == []

    @pytest.mark.asyncio
    async def test_returns_early_without_a_sidecar(self, monkeypatch):
        source = _FakeSource(context=ModelCardContext(model_name="X"))
        calls = _wire(monkeypatch, source, metadata={})

        assert await hydrate_from_source("/models/lora.safetensors", ref=REF) == []
        assert calls == []

    @pytest.mark.asyncio
    async def test_returns_early_when_the_site_published_nothing(self, monkeypatch):
        source = _FakeSource(context=ModelCardContext(), readme="")
        calls = _wire(monkeypatch, source)

        assert await hydrate_from_source("/models/lora.safetensors", ref=REF) == []
        assert calls == []

    @pytest.mark.asyncio
    async def test_a_deferred_hash_still_matches_by_filename(self, monkeypatch):
        """Checkpoints and other large files are stored with
        ``hash_status="pending"`` and an empty ``sha256`` (see
        ``CheckpointScanner._create_default_metadata``), so hydration has to
        work from the filename alone."""
        source = _FakeSource(context=ModelCardContext(model_name="X"))
        calls = _wire(
            monkeypatch,
            source,
            metadata={**SIDECAR, "sha256": "", "hash_status": "pending"},
        )

        await hydrate_from_source("/models/big_checkpoint.safetensors", ref=REF)

        assert calls[0]["source_context"].model_name == "X"
        assert source.context_kwargs == {
            "filename": "big_checkpoint.safetensors",
            "sha256": "",
        }

    @pytest.mark.asyncio
    async def test_returns_early_when_the_model_is_not_linked(self, monkeypatch):
        """A file that merely shares a name must not get another model's card."""
        source = _FakeSource(context=ModelCardContext(model_name="X"))
        calls = _wire(
            monkeypatch, source, metadata={"sha256": "a" * 64, "base_model": "Unknown"}
        )

        assert await hydrate_from_source("/models/lora.safetensors", ref=REF) == []
        assert calls == []

    @pytest.mark.asyncio
    async def test_returns_early_when_linked_to_another_repository(self, monkeypatch):
        source = _FakeSource(context=ModelCardContext(model_name="X"))
        calls = _wire(
            monkeypatch,
            source,
            metadata={
                **SIDECAR,
                "source_url": "https://modelscope.cn/models/user/other",
            },
        )

        assert await hydrate_from_source("/models/lora.safetensors", ref=REF) == []
        assert calls == []

    @pytest.mark.asyncio
    async def test_returns_early_when_linked_to_another_platform(self, monkeypatch):
        source = _FakeSource(context=ModelCardContext(model_name="X"))
        calls = _wire(
            monkeypatch,
            source,
            metadata={
                "sha256": "a" * 64,
                "source_platform": "huggingface",
                "source_url": "https://huggingface.co/user/repo",
            },
        )

        assert await hydrate_from_source("/models/lora.safetensors", ref=REF) == []
        assert calls == []

    @pytest.mark.asyncio
    async def test_readme_alone_is_enough_to_run(self, monkeypatch):
        source = _FakeSource(context=ModelCardContext(), readme="# hi")
        calls = _wire(monkeypatch, source)

        await hydrate_from_source("/models/lora.safetensors", ref=REF)

        assert len(calls) == 1
        assert calls[0]["readme_content"] == "# hi"

    @pytest.mark.asyncio
    async def test_a_failing_site_never_breaks_the_download(self, monkeypatch):
        source = _FakeSource(fail=True)
        calls = _wire(monkeypatch, source)

        assert await hydrate_from_source("/models/lora.safetensors", ref=REF) == []
        assert calls == []

    @pytest.mark.asyncio
    async def test_a_failing_post_processor_never_breaks_the_download(
        self, monkeypatch
    ):
        source = _FakeSource(context=ModelCardContext(model_name="X"))
        _wire(monkeypatch, source, result={"success": False, "errors": ["boom"]})

        assert await hydrate_from_source("/models/lora.safetensors", ref=REF) == []

    @pytest.mark.asyncio
    async def test_updates_are_reported_for_logging(self, monkeypatch):
        source = _FakeSource(context=ModelCardContext(model_name="X"))
        _wire(
            monkeypatch,
            source,
            result={"success": True, "updated_fields": ["tags", "civitai"]},
        )

        assert await hydrate_from_source("/models/lora.safetensors", ref=REF) == [
            "tags",
            "civitai",
        ]


# ---------------------------------------------------------------------------
# Per-repository memo
# ---------------------------------------------------------------------------


class TestSharedSourceCache:
    def test_same_repository_reuses_one_memo(self):
        assert shared_source_cache("modelscope", "u/r") is shared_source_cache(
            "modelscope", "u/r"
        )

    def test_different_repositories_get_different_memos(self):
        assert shared_source_cache("modelscope", "u/r") is not shared_source_cache(
            "modelscope", "u/other"
        )

    def test_entry_expires(self, monkeypatch):
        clock = {"now": 1000.0}
        monkeypatch.setattr(hydration.time, "monotonic", lambda: clock["now"])

        first = shared_source_cache("modelscope", "u/r")
        clock["now"] += hydration.SHARED_CACHE_TTL + 1

        assert shared_source_cache("modelscope", "u/r") is not first

    def test_cache_is_bounded(self):
        for index in range(SHARED_CACHE_MAX_ENTRIES + 5):
            shared_source_cache("modelscope", f"u/r{index}")

        assert len(hydration._shared_caches) == SHARED_CACHE_MAX_ENTRIES


class TestLoadModelCard:
    @pytest.mark.asyncio
    async def test_successful_read_is_memoised(self):
        source = _FakeSource(readme="# hi")
        cache = ModelSourceCache()

        assert await load_model_card(source, "u/r", cache) == "# hi"
        assert await load_model_card(source, "u/r", cache) == "# hi"
        assert source.readme_calls == 1

    @pytest.mark.asyncio
    async def test_empty_read_is_retried(self):
        """A transient failure must not be cached as "this repo has no card"."""
        source = _FakeSource(readme="")
        cache = ModelSourceCache()

        await load_model_card(source, "u/r", cache)
        await load_model_card(source, "u/r", cache)

        assert source.readme_calls == 2

    @pytest.mark.asyncio
    async def test_works_without_a_cache(self):
        source = _FakeSource(readme="# hi")

        assert await load_model_card(source, "u/r") == "# hi"
        assert source.readme_calls == 1


# ---------------------------------------------------------------------------
# Base-model resolution
# ---------------------------------------------------------------------------


class TestResolveSiteBaseModel:
    @pytest.mark.asyncio
    async def test_maps_the_sites_own_vocabulary(self, monkeypatch):
        monkeypatch.setattr(
            "py.metadata_ops.list_base_models",
            _async(["Krea 2", "Flux.1 D"]),
        )

        context = ModelCardContext(
            base_model="krea/Krea-2-Turbo",
            base_model_aliases=["KREA_2_TURBO", "krea/Krea-2-Turbo"],
        )

        assert await resolve_site_base_model(context) == "Krea 2"

    @pytest.mark.asyncio
    async def test_unknown_hint_defers_instead_of_guessing(self, monkeypatch):
        monkeypatch.setattr(
            "py.metadata_ops.list_base_models", _async(["Flux.1 D"])
        )

        context = ModelCardContext(base_model="something/else")

        assert await resolve_site_base_model(context) == ""

    @pytest.mark.asyncio
    async def test_no_hints_needs_no_vocabulary_lookup(self, monkeypatch):
        async def _boom(*_args, **_kwargs):  # pragma: no cover - must not run
            raise AssertionError("list_base_models should not be called")

        monkeypatch.setattr("py.metadata_ops.list_base_models", _boom)

        assert await resolve_site_base_model(ModelCardContext()) == ""

    @pytest.mark.asyncio
    async def test_a_vocabulary_failure_is_not_fatal(self, monkeypatch):
        async def _boom(*_args, **_kwargs):
            raise RuntimeError("civitai down")

        monkeypatch.setattr("py.metadata_ops.list_base_models", _boom)

        assert await resolve_site_base_model(ModelCardContext(base_model="x")) == ""

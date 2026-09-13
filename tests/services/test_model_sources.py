"""Tests for the external model-source provider registry.

Covers URL recognition for Hugging Face / ModelScope / TensorArt, the
legacy ``hf_url`` → ``source_url`` normalisation, version-group keys, and
each provider's model-card fetching and capability flags.
"""

from __future__ import annotations

import pytest

from py.services.model_sources import (
    HuggingFaceSource,
    ModelScopeSource,
    TensorArtSource,
    detect_source,
    get_source,
    get_source_platform,
    has_external_source,
    list_sources,
    normalize_metadata_source,
    resolve_source_ref,
    source_group_key,
    source_label,
)


# ---------------------------------------------------------------------------
# URL recognition
# ---------------------------------------------------------------------------


class TestDetectSource:
    @pytest.mark.parametrize(
        ("url", "platform", "source_id"),
        [
            ("https://huggingface.co/user/repo", "huggingface", "user/repo"),
            ("https://www.huggingface.co/user/repo", "huggingface", "user/repo"),
            (
                "https://huggingface.co/user/repo/resolve/main/model.safetensors",
                "huggingface",
                "user/repo",
            ),
            (
                "https://modelscope.cn/models/jj3550945163/Krea-2-LORA",
                "modelscope",
                "jj3550945163/Krea-2-LORA",
            ),
            (
                "https://www.modelscope.cn/models/jj3550945163/Krea-2-LORA/summary",
                "modelscope",
                "jj3550945163/Krea-2-LORA",
            ),
            (
                "https://tensor.art/models/827823520299086029/Vivid-Impressions-Storybook-Sstyle-V1.0",
                "tensorart",
                "827823520299086029",
            ),
            ("https://tusi.cn/models/827823520299086029", "tensorart", "827823520299086029"),
        ],
    )
    def test_recognises_supported_urls(self, url, platform, source_id):
        ref = detect_source(url)
        assert ref is not None
        assert ref.platform == platform
        assert ref.source_id == source_id

    @pytest.mark.parametrize(
        "url",
        [
            "",
            None,
            "not-a-url",
            "https://example.com/x",
            "https://civitai.com/models/123",
        ],
    )
    def test_ignores_unsupported_urls(self, url):
        assert detect_source(url) is None

    def test_canonical_url_is_stable(self):
        assert detect_source("https://huggingface.co/u/r").url == "https://huggingface.co/u/r"
        assert (
            detect_source("https://modelscope.cn/models/u/r/summary").url
            == "https://modelscope.cn/models/u/r"
        )
        assert (
            detect_source("https://tensor.art/models/123/some-slug").url
            == "https://tensor.art/models/123"
        )


class TestStrictParsing:
    @pytest.mark.parametrize(
        "url",
        [
            "https://huggingface.co/user/repo",
            "https://huggingface.co/user/repo/",
            "https://modelscope.cn/models/user/repo",
            "https://modelscope.cn/models/user/repo/summary",
            "https://tensor.art/models/827823520299086029",
            "https://tensor.art/models/827823520299086029/Vivid-Impressions",
        ],
    )
    def test_accepts_user_facing_urls(self, url):
        assert detect_source(url, strict=True) is not None

    @pytest.mark.parametrize(
        "url",
        [
            "https://huggingface.co/user/repo/resolve/main/model.safetensors",
            "https://example.com/x",
            "https://tensor.art/models/not-a-number",
        ],
    )
    def test_rejects_non_page_urls(self, url):
        assert detect_source(url, strict=True) is None


# ---------------------------------------------------------------------------
# Capabilities
# ---------------------------------------------------------------------------


class TestCapabilities:
    def test_huggingface_supports_everything(self):
        source = get_source("huggingface")
        assert source.supports_enrichment is True
        assert source.supports_download is True

    def test_modelscope_supports_enrichment_but_not_download(self):
        source = get_source("modelscope")
        assert source.supports_enrichment is True
        assert source.supports_download is False

    def test_tensorart_is_link_only(self):
        source = get_source("tensorart")
        assert source.supports_enrichment is False
        assert source.supports_download is False

    def test_registry_lists_every_source(self):
        platforms = {s.platform for s in list_sources()}
        assert platforms == {"huggingface", "modelscope", "tensorart"}

    def test_labels_are_brand_names(self):
        assert source_label("huggingface") == "Hugging Face"
        assert source_label("modelscope") == "ModelScope"
        assert source_label("tensorart") == "TensorArt"
        assert source_label("unknown", "fallback") == "fallback"


# ---------------------------------------------------------------------------
# Metadata normalisation
# ---------------------------------------------------------------------------


class TestNormalizeMetadataSource:
    def test_derives_source_fields_from_legacy_hf_url(self):
        metadata = {"hf_url": "https://huggingface.co/user/repo"}
        normalize_metadata_source(metadata)
        assert metadata["source_platform"] == "huggingface"
        assert metadata["source_url"] == "https://huggingface.co/user/repo"
        assert metadata["hf_url"] == "https://huggingface.co/user/repo"

    def test_canonicalises_modelscope_url_and_clears_hf_alias(self):
        metadata = {
            "source_platform": "modelscope",
            "source_url": "https://modelscope.cn/models/user/repo/summary",
            "hf_url": "https://huggingface.co/old/repo",
        }
        normalize_metadata_source(metadata)
        assert metadata["source_platform"] == "modelscope"
        assert metadata["source_url"] == "https://modelscope.cn/models/user/repo"
        # A stale HF alias must not make a ModelScope model look like HF.
        assert metadata["hf_url"] == ""

    def test_preserves_unknown_url_for_unknown_platform(self):
        metadata = {"source_url": "https://example.com/model/1", "source_platform": "other"}
        normalize_metadata_source(metadata)
        assert metadata["source_url"] == "https://example.com/model/1"
        assert metadata["source_platform"] == "other"

    def test_empty_metadata_gets_default_fields(self):
        metadata: dict = {}
        normalize_metadata_source(metadata)
        assert metadata["source_platform"] == ""
        assert metadata["source_url"] == ""

    def test_infers_platform_from_url_when_missing(self):
        metadata = {"source_url": "https://modelscope.cn/models/user/repo"}
        normalize_metadata_source(metadata)
        assert metadata["source_platform"] == "modelscope"


class TestResolveSourceRef:
    def test_resolves_from_canonical_fields(self):
        ref = resolve_source_ref(
            {"source_platform": "modelscope", "source_url": "https://modelscope.cn/models/u/r"}
        )
        assert ref is not None
        assert ref.platform == "modelscope"
        assert ref.source_id == "u/r"

    def test_resolves_from_legacy_hf_url(self):
        ref = resolve_source_ref({"hf_url": "https://huggingface.co/u/r"})
        assert ref is not None
        assert ref.platform == "huggingface"

    def test_returns_none_without_any_source(self):
        assert resolve_source_ref({}) is None
        assert resolve_source_ref({"hf_url": ""}) is None


class TestHelpers:
    def test_has_external_source_accepts_both_field_shapes(self):
        assert has_external_source({"hf_url": "https://huggingface.co/u/r"}) is True
        assert has_external_source({"source_url": "https://modelscope.cn/models/u/r"}) is True
        assert has_external_source({"source_url": ""}) is False
        assert has_external_source({}) is False

    def test_get_source_platform_infers_from_url(self):
        assert get_source_platform({"hf_url": "https://huggingface.co/u/r"}) == "huggingface"
        assert get_source_platform({"source_platform": "tensorart"}) == "tensorart"
        assert get_source_platform({}) == ""

    def test_group_keys_match_legacy_hf_shape(self):
        assert source_group_key({"hf_url": "https://huggingface.co/u/r"}) == "hf:u/r"
        assert (
            source_group_key({"source_url": "https://modelscope.cn/models/u/r"}) == "ms:u/r"
        )
        assert (
            source_group_key({"source_url": "https://tensor.art/models/123"}) == "ta:123"
        )

    def test_group_key_is_none_without_source(self):
        assert source_group_key({}) is None
        assert source_group_key({"hf_url": "https://example.com/x"}) is None


# ---------------------------------------------------------------------------
# Model card fetching
# ---------------------------------------------------------------------------


class TestFetchModelCard:
    @pytest.mark.asyncio
    async def test_huggingface_tries_main_then_master(self, monkeypatch):
        calls: list[str] = []

        async def fake_fetch_text(url: str, **_kwargs) -> str:
            calls.append(url)
            if url.endswith("/master/README.md"):
                return "# card"
            return ""

        monkeypatch.setattr("py.services.model_sources.huggingface.fetch_text", fake_fetch_text)

        card = await HuggingFaceSource().fetch_model_card("user/repo")

        assert card == "# card"
        assert calls == [
            "https://huggingface.co/user/repo/raw/main/README.md",
            "https://huggingface.co/user/repo/raw/master/README.md",
        ]

    @pytest.mark.asyncio
    async def test_modelscope_prefers_resolve_url(self, monkeypatch):
        calls: list[str] = []

        async def fake_fetch_text(url: str, **_kwargs) -> str:
            calls.append(url)
            return "---\nbase_model: krea/Krea-2-Turbo\n---\n# krea"

        monkeypatch.setattr("py.services.model_sources.modelscope.fetch_text", fake_fetch_text)

        card = await ModelScopeSource().fetch_model_card("u/r")

        assert card.startswith("---")
        assert calls == ["https://modelscope.cn/models/u/r/resolve/master/README.md"]

    @pytest.mark.asyncio
    async def test_modelscope_falls_back_to_repo_api(self, monkeypatch):
        calls: list[str] = []

        async def fake_fetch_text(url: str, **_kwargs) -> str:
            calls.append(url)
            if "/api/v1/models/" in url:
                return "# from api"
            return ""

        monkeypatch.setattr("py.services.model_sources.modelscope.fetch_text", fake_fetch_text)

        card = await ModelScopeSource().fetch_model_card("u/r")

        assert card == "# from api"
        assert "resolve/master/README.md" in calls[0]
        assert (
            "https://modelscope.cn/api/v1/models/u/r/repo?Revision=master&FilePath=README.md"
            in calls
        )

    @pytest.mark.asyncio
    async def test_tensorart_never_fetches(self):
        # TensorArt enrichment is disabled: the provider must not issue any
        # HTTP request, so it deliberately does not import `fetch_text`.
        import importlib

        module = importlib.import_module("py.services.model_sources.tensorart")
        assert not hasattr(module, "fetch_text")
        assert await TensorArtSource().fetch_model_card("123") == ""


class TestAssetBaseUrl:
    def test_huggingface_uses_main_revision(self):
        assert (
            HuggingFaceSource().asset_base_url("u/r")
            == "https://huggingface.co/u/r/resolve/main"
        )

    def test_modelscope_uses_master_revision(self):
        assert (
            ModelScopeSource().asset_base_url("u/r")
            == "https://modelscope.cn/models/u/r/resolve/master"
        )

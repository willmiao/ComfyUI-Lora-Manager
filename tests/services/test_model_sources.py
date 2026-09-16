"""Tests for the external model-source provider registry.

Covers URL recognition for Hugging Face / ModelScope / TensorArt, the
legacy ``hf_url`` → ``source_url`` normalisation, version-group keys, and
each provider's model-card fetching and capability flags.
"""

from __future__ import annotations

from unittest import mock
import pytest

from py.services.agent.agent_service import AgentService
from py.services.model_sources import (
    ModelCardContext,
    ModelSourceCache,
    HuggingFaceSource,
    ModelScopeSource,
    TensorArtSource,
    detect_source,
    downloadable_sources,
    get_download_source,
    get_source,
    get_source_platform,
    has_external_source,
    is_valid_source_id,
    list_sources,
    ModelSourceError,
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
            # modelscope.ai is a separate catalogue with its own platform id.
            (
                "https://www.modelscope.ai/models/referall13/EM1",
                "modelscope-ai",
                "referall13/EM1",
            ),
            (
                "https://modelscope.ai/models/ErLubu/krea2_style_260911_02/summary",
                "modelscope-ai",
                "ErLubu/krea2_style_260911_02",
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

    def test_modelscope_com_is_an_alias_of_the_mainland_site(self):
        """``.com`` 301-redirects to ``.cn``, so it is not a third catalogue."""
        ref = detect_source("https://www.modelscope.com/models/u/r")
        assert ref.platform == "modelscope"
        assert ref.url == "https://modelscope.cn/models/u/r"

    def test_the_two_modelscope_catalogues_do_not_cross_match(self):
        """A host must never be accepted by the other deployment's patterns."""
        mainland = get_source("modelscope")
        international = get_source("modelscope-ai")

        assert mainland.parse("https://www.modelscope.ai/models/u/r") is None
        assert international.parse("https://modelscope.cn/models/u/r") is None
        assert international.parse("https://www.modelscope.com/models/u/r") is None


class TestStrictParsing:
    @pytest.mark.parametrize(
        "url",
        [
            "https://huggingface.co/user/repo",
            "https://huggingface.co/user/repo/",
            "https://modelscope.cn/models/user/repo",
            "https://modelscope.cn/models/user/repo/summary",
            "https://www.modelscope.ai/models/user/repo",
            "https://www.modelscope.ai/models/user/repo/files",
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
        assert source.default_revision == "main"
        assert source.default_subdir == "huggingface"

    def test_modelscope_supports_enrichment_and_download(self):
        source = get_source("modelscope")
        assert source.supports_enrichment is True
        assert source.supports_download is True
        assert source.default_revision == "master"
        assert source.default_subdir == "modelscope"

    def test_modelscope_intl_is_the_same_site_on_another_catalogue(self):
        source = get_source("modelscope-ai")
        assert source.supports_enrichment is True
        assert source.supports_download is True
        assert source.default_revision == "master"
        # A distinct directory: the same owner/name can exist on both
        # deployments with different content.
        assert source.default_subdir == "modelscope-ai"
        assert source.base_url == "https://www.modelscope.ai"

    def test_tensorart_is_link_only(self):
        source = get_source("tensorart")
        assert source.supports_enrichment is False
        assert source.supports_download is False

    def test_registry_lists_every_source(self):
        platforms = {s.platform for s in list_sources()}
        assert platforms == {
            "huggingface",
            "modelscope",
            "modelscope-ai",
            "tensorart",
        }

    def test_labels_are_brand_names(self):
        assert source_label("huggingface") == "Hugging Face"
        assert source_label("modelscope") == "ModelScope"
        assert source_label("modelscope-ai") == "ModelScope (International)"
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
    async def test_modelscope_intl_fetches_from_its_own_catalogue(self, monkeypatch):
        """The mainland site 404s for a `.ai`-only repository, so every fetch
        has to stay on the host the URL came from."""
        calls: list[str] = []

        async def fake_fetch_text(url: str, **_kwargs) -> str:
            calls.append(url)
            return "# card"

        json_calls: list[str] = []

        async def fake_fetch_json(url: str, **_kwargs):
            json_calls.append(url)
            return 200, {"Data": {"Name": "EM1", "MuseInfo": {"versions": []}}}

        monkeypatch.setattr(
            "py.services.model_sources.modelscope.fetch_text", fake_fetch_text
        )
        monkeypatch.setattr(
            "py.services.model_sources.modelscope.fetch_json", fake_fetch_json
        )

        source = get_source("modelscope-ai")
        await source.fetch_model_card("referall13/EM1")
        await source.fetch_model_card_context("referall13/EM1")
        await source.list_files("referall13/EM1")

        assert calls == [
            "https://www.modelscope.ai/models/referall13/EM1/resolve/master/README.md"
        ]
        assert json_calls == [
            "https://www.modelscope.ai/api/v1/models/referall13/EM1",
            "https://www.modelscope.ai/api/v1/models/referall13/EM1/repo/files"
            "?Revision=master",
        ]
        assert not any("modelscope.cn" in url for url in calls + json_calls)

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

    def test_modelscope_intl_uses_master_revision(self):
        assert (
            get_source("modelscope-ai").asset_base_url("u/r")
            == "https://www.modelscope.ai/models/u/r/resolve/master"
        )


# ---------------------------------------------------------------------------
# Model card context (site extras kept outside the README)
# ---------------------------------------------------------------------------


def _modelscope_detail_payload() -> dict:
    """A trimmed-but-faithful ModelScope model-detail response.

    Mirrors the shape of ``/api/v1/models/{id}`` for an AIGC LoRA repo whose
    README is auto-generated boilerplate, so the author summary and the
    per-file example images are only reachable through this API.
    """

    return {
        "Code": 200,
        "Data": {
            "Name": "Krea-2-LORA",
            "ChineseName": "krea脸模",
            "AigcType": "LoRA",
            "License": "Apache License 2.0",
            "Tags": ["LoRA", "text-to-image", "portrait"],
            "Description": "权重0.5-1.2。配合《风格滤镜》lora一起使用。",
            "BaseModel": ["krea/Krea-2-Turbo"],
            "License": "Apache License 2.0",
            "OfficialTags": [
                {"Tag": "photography", "ChineseName": "写实摄影"},
                {"Tag": "woman", "ChineseName": "女生"},
                {"Tag": "photography", "ChineseName": "重复项"},
            ],
            "MuseInfo": {
                "versions": [
                    {
                        "stats": {"fileList": ["Krea-2-LORA_c1-st8000.safetensors"]},
                        "modelVersion": {"showName": "c1-st8000", "triggerWords": '[""]'},
                        "coverImages": [
                            {"url": "https://resources.modelscope.cn/cover-images/a.png"}
                        ],
                    },
                    {
                        "stats": {"fileList": ["Krea-2-LORA_c1-st1000.safetensors"]},
                        "modelVersion": {
                            "showName": "c1-st1000",
                            "triggerWords": '["kreaface","kreamodel"]',
                        },
                        "coverImages": [
                            {"url": "https://resources.modelscope.cn/cover-images/b.png"},
                            {"url": "https://resources.modelscope.cn/cover-images/c.png"},
                        ],
                    },
                ]
            },
            "ModelInfos": {
                "safetensor": {
                    "files": [
                        {
                            "name": "Krea-2-LORA_c1-st8000.safetensors",
                            "sha256": "a" * 64,
                            "size": 234680568,
                        },
                        {
                            "name": "Krea-2-LORA_c1-st1000.safetensors",
                            "sha256": "b" * 64,
                            "size": 234680568,
                        },
                    ]
                }
            },
        },
    }


class TestFetchModelCardContext:
    @pytest.mark.asyncio
    async def test_modelscope_reads_description_tags_and_base_model(self, monkeypatch):
        async def fake_fetch_json(url, **_kwargs):
            assert url == "https://modelscope.cn/api/v1/models/u/r"
            return 200, _modelscope_detail_payload()

        monkeypatch.setattr(
            "py.services.model_sources.modelscope.fetch_json", fake_fetch_json
        )

        context = await ModelScopeSource().fetch_model_card_context("u/r")

        assert context.description == "权重0.5-1.2。配合《风格滤镜》lora一起使用。"
        assert context.base_model == "krea/Krea-2-Turbo"
        # OfficialTag values only, de-duplicated, order preserved.
        assert context.official_tags == ["photography", "woman"]

    @pytest.mark.asyncio
    async def test_modelscope_reads_site_identity_fields(self, monkeypatch):
        async def fake_fetch_json(url, **_kwargs):
            return 200, _modelscope_detail_payload()

        monkeypatch.setattr(
            "py.services.model_sources.modelscope.fetch_json", fake_fetch_json
        )

        context = await ModelScopeSource().fetch_model_card_context(
            "u/r", "Krea-2-LORA_c1-st1000.safetensors"
        )

        assert context.model_name == "Krea-2-LORA"
        assert context.model_name_localized == "krea脸模"
        assert context.license == "Apache License 2.0"
        assert context.model_type == "LoRA"
        # The version label is taken from the file that was matched, not from
        # whichever version happens to come first in the payload.
        assert context.version_name == "c1-st1000"

    @pytest.mark.asyncio
    async def test_modelscope_version_label_is_empty_for_an_unknown_file(
        self, monkeypatch
    ):
        async def fake_fetch_json(url, **_kwargs):
            return 200, _modelscope_detail_payload()

        monkeypatch.setattr(
            "py.services.model_sources.modelscope.fetch_json", fake_fetch_json
        )

        context = await ModelScopeSource().fetch_model_card_context(
            "u/r", "other.safetensors"
        )

        assert context.version_name == ""
        # The repository-wide fields are still published.
        assert context.model_name == "Krea-2-LORA"

    @pytest.mark.asyncio
    async def test_modelscope_falls_back_to_plain_tags(self, monkeypatch):
        """An empty ``OfficialTags`` must not mean "no tags at all".

        The plain ``Tags`` list mixes genuine content tags with library and
        task categories; the latter are dropped so the card is not tagged
        "lora" / "text-to-image".
        """
        payload = _modelscope_detail_payload()
        payload["Data"]["OfficialTags"] = None

        async def fake_fetch_json(url, **_kwargs):
            return 200, payload

        monkeypatch.setattr(
            "py.services.model_sources.modelscope.fetch_json", fake_fetch_json
        )

        context = await ModelScopeSource().fetch_model_card_context("u/r")

        assert context.official_tags == ["portrait"]

    @pytest.mark.asyncio
    async def test_modelscope_curated_tags_win_over_plain_tags(self, monkeypatch):
        async def fake_fetch_json(url, **_kwargs):
            return 200, _modelscope_detail_payload()

        monkeypatch.setattr(
            "py.services.model_sources.modelscope.fetch_json", fake_fetch_json
        )

        context = await ModelScopeSource().fetch_model_card_context("u/r")

        assert "portrait" not in context.official_tags

    @pytest.mark.asyncio
    async def test_modelscope_matches_example_images_by_filename(self, monkeypatch):
        async def fake_fetch_json(url, **_kwargs):
            return 200, _modelscope_detail_payload()

        monkeypatch.setattr(
            "py.services.model_sources.modelscope.fetch_json", fake_fetch_json
        )

        context = await ModelScopeSource().fetch_model_card_context(
            "u/r", "Krea-2-LORA_c1-st1000.safetensors"
        )

        # Only the requested file's images, never a sibling checkpoint's.
        assert context.example_images == [
            "https://resources.modelscope.cn/cover-images/b.png",
            "https://resources.modelscope.cn/cover-images/c.png",
        ]
        assert context.trigger_words == ["kreaface", "kreamodel"]

    @pytest.mark.asyncio
    async def test_modelscope_never_borrows_images_for_an_unknown_file(
        self, monkeypatch
    ):
        async def fake_fetch_json(url, **_kwargs):
            return 200, _modelscope_detail_payload()

        monkeypatch.setattr(
            "py.services.model_sources.modelscope.fetch_json", fake_fetch_json
        )

        context = await ModelScopeSource().fetch_model_card_context(
            "u/r", "other.safetensors"
        )

        assert context.example_images == []
        assert context.trigger_words == []
        # The repo-wide fields are still returned.
        assert context.base_model == "krea/Krea-2-Turbo"

    @pytest.mark.asyncio
    async def test_modelscope_single_version_repo_without_filename(self, monkeypatch):
        payload = _modelscope_detail_payload()
        versions = payload["Data"]["MuseInfo"]["versions"]
        payload["Data"]["MuseInfo"]["versions"] = versions[:1]

        async def fake_fetch_json(url, **_kwargs):
            return 200, payload

        monkeypatch.setattr(
            "py.services.model_sources.modelscope.fetch_json", fake_fetch_json
        )

        context = await ModelScopeSource().fetch_model_card_context("u/r")

        assert context.example_images == [
            "https://resources.modelscope.cn/cover-images/a.png"
        ]

    @pytest.mark.asyncio
    async def test_modelscope_tolerates_failures_and_odd_payloads(self, monkeypatch):
        payloads = (None, {"Code": 500}, {"Data": "nope"}, {"Data": {}})
        for payload in payloads:

            async def fake_fetch_json(url, _payload=payload, **_kwargs):
                return (0 if _payload is None else 200), _payload

            monkeypatch.setattr(
                "py.services.model_sources.modelscope.fetch_json", fake_fetch_json
            )
            context = await ModelScopeSource().fetch_model_card_context(
                "u/r", "a.safetensors"
            )
            assert context.is_empty(), payload

    @pytest.mark.asyncio
    async def test_modelscope_reads_stats_from_json_encoded_fallback(self, monkeypatch):
        payload = {
            "Data": {
                "MuseInfo": {
                    "versions": [
                        {
                            "modelVersion": {
                                "showName": "v1",
                                "stats": '{"fileList": ["model.safetensors"]}',
                                "triggerWords": '["hi"]',
                            },
                            "coverImages": [{"url": "https://cdn.example/x.png"}],
                        }
                    ]
                }
            }
        }

        async def fake_fetch_json(url, **_kwargs):
            return 200, payload

        monkeypatch.setattr(
            "py.services.model_sources.modelscope.fetch_json", fake_fetch_json
        )

        context = await ModelScopeSource().fetch_model_card_context(
            "u/r", "model.safetensors"
        )

        assert context.example_images == ["https://cdn.example/x.png"]
        assert context.trigger_words == ["hi"]

    @pytest.mark.asyncio
    async def test_default_context_is_empty_for_other_sources(self):
        assert (await HuggingFaceSource().fetch_model_card_context("u/r")).is_empty()
        assert (await TensorArtSource().fetch_model_card_context("123")).is_empty()


# ---------------------------------------------------------------------------
# Download support
# ---------------------------------------------------------------------------


class TestListFiles:
    @pytest.mark.asyncio
    async def test_huggingface_reads_tree_api_with_lfs_sizes(self, monkeypatch):
        captured: dict = {}

        async def fake_fetch_json(url, **_kwargs):
            captured["url"] = url
            return 200, [
                {"path": "README.md", "size": 120},
                {"path": "a/model.safetensors", "size": 300},
                {"path": "b.safetensors", "size": 0, "lfs": {"size": 200}},
            ]

        monkeypatch.setattr(
            "py.services.model_sources.huggingface.fetch_json", fake_fetch_json
        )

        files = await HuggingFaceSource().list_files("u/r")

        assert captured["url"] == "https://huggingface.co/api/models/u/r/tree/main"
        assert files == [
            {"filename": "a/model.safetensors", "size": 300},
            {"filename": "b.safetensors", "size": 200},
        ]

    @pytest.mark.asyncio
    async def test_huggingface_honours_explicit_revision(self, monkeypatch):
        captured: dict = {}

        async def fake_fetch_json(url, **_kwargs):
            captured["url"] = url
            return 200, []

        monkeypatch.setattr(
            "py.services.model_sources.huggingface.fetch_json", fake_fetch_json
        )

        await HuggingFaceSource().list_files("u/r", "v2.0")

        assert captured["url"].endswith("/tree/v2.0")

    @pytest.mark.asyncio
    async def test_modelscope_reads_repo_files_api(self, monkeypatch):
        captured: dict = {}

        async def fake_fetch_json(url, **_kwargs):
            captured["url"] = url
            return 200, {
                "Data": {
                    "Files": [
                        # directories are listed too and must be dropped
                        {"Type": "tree", "Path": "vae", "Size": 0},
                        {"Type": "blob", "Path": "README.md", "Size": 100},
                        {"Type": "blob", "Path": "sub/model.safetensors", "Size": 500},
                        {"Type": "blob", "Path": "model.ckpt", "Size": 200},
                    ]
                }
            }

        monkeypatch.setattr(
            "py.services.model_sources.modelscope.fetch_json", fake_fetch_json
        )

        files = await ModelScopeSource().list_files("u/r")

        assert captured["url"] == (
            "https://modelscope.cn/api/v1/models/u/r/repo/files?Revision=master"
        )
        assert files == [
            {"filename": "sub/model.safetensors", "size": 500},
            {"filename": "model.ckpt", "size": 200},
        ]

    @pytest.mark.asyncio
    async def test_missing_repo_is_reported_as_not_found(self, monkeypatch):
        async def fake_fetch_json(url, **_kwargs):
            return 404, None

        monkeypatch.setattr(
            "py.services.model_sources.modelscope.fetch_json", fake_fetch_json
        )

        with pytest.raises(ModelSourceError) as excinfo:
            await ModelScopeSource().list_files("u/r")

        assert excinfo.value.status == 404
        assert "not found" in str(excinfo.value)

    @pytest.mark.asyncio
    async def test_transport_failure_is_reported_as_bad_gateway(self, monkeypatch):
        async def fake_fetch_json(url, **_kwargs):
            return 0, None

        monkeypatch.setattr(
            "py.services.model_sources.huggingface.fetch_json", fake_fetch_json
        )

        with pytest.raises(ModelSourceError) as excinfo:
            await HuggingFaceSource().list_files("u/r")

        assert excinfo.value.status == 502


class TestDownloadUrls:
    def test_huggingface_resolve_url(self):
        assert HuggingFaceSource().file_download_url("u/r", "sub/f.safetensors") == (
            "https://huggingface.co/u/r/resolve/main/sub/f.safetensors"
        )

    def test_modelscope_resolve_url_defaults_to_master(self):
        assert ModelScopeSource().file_download_url("u/r", "sub/f.safetensors") == (
            "https://modelscope.cn/models/u/r/resolve/master/sub/f.safetensors"
        )

    def test_modelscope_intl_builds_every_url_on_its_own_host(self):
        """The two deployments serve different catalogues, so a URL built for
        one must never point at the other."""
        source = get_source("modelscope-ai")

        assert source.canonical_url("u/r") == "https://www.modelscope.ai/models/u/r"
        assert source.file_download_url("u/r", "sub/f.safetensors") == (
            "https://www.modelscope.ai/models/u/r/resolve/master/sub/f.safetensors"
        )
        assert source.asset_base_url("u/r") == (
            "https://www.modelscope.ai/models/u/r/resolve/master"
        )
        assert source.page_url_for_file("u/r", "sub/f.safetensors") == (
            "https://www.modelscope.ai/models/u/r/file/view/master/sub/f.safetensors"
        )

    def test_explicit_revision_wins(self):
        assert ModelScopeSource().file_download_url("u/r", "f.bin", "v1") == (
            "https://modelscope.cn/models/u/r/resolve/v1/f.bin"
        )

    def test_tensorart_refuses_to_build_a_download_url(self):
        source = TensorArtSource()
        assert source.supports_download is False
        with pytest.raises(ModelSourceError):
            source.file_download_url("123", "f.safetensors")

    @pytest.mark.asyncio
    async def test_tensorart_lists_nothing(self):
        assert await TensorArtSource().list_files("123") == []


class TestSourceIdValidation:
    @pytest.mark.parametrize(
        "source_id",
        ["u/r", "black-forest-labs/FLUX.1-dev", "AI-ModelScope/stable-diffusion-v1-5"],
    )
    def test_accepts_repo_ids(self, source_id):
        assert is_valid_source_id(source_id) is True

    @pytest.mark.parametrize(
        "source_id",
        [
            "",
            "noslash",
            "a/b/c",
            "../etc/passwd",
            "u/..",
            "u/.",
            ".hidden/r",
            "u/r with space",
            "/r",
            "u/",
        ],
    )
    def test_rejects_unsafe_ids(self, source_id):
        assert is_valid_source_id(source_id) is False


class TestDownloadSourceRegistry:
    def test_downloadable_sources_excludes_link_only_sites(self):
        platforms = {source.platform for source in downloadable_sources()}
        assert platforms == {"huggingface", "modelscope", "modelscope-ai"}

    def test_get_download_source_rejects_link_only_platform(self):
        assert get_download_source("tensorart") is None
        assert get_download_source("nope") is None
        assert get_download_source("modelscope").platform == "modelscope"
        assert get_download_source("modelscope-ai").platform == "modelscope-ai"
        assert get_download_source("huggingface").platform == "huggingface"


# ---------------------------------------------------------------------------
# Per-run model-card cache
# ---------------------------------------------------------------------------


class TestModelSourceCache:
    def test_starts_empty(self):
        cache = ModelSourceCache()
        assert cache.readmes == {}
        assert cache.provider == {}


class TestCachedModelCardFetch:
    @pytest.mark.asyncio
    async def test_detail_payload_is_fetched_once_per_source_id(self, monkeypatch):
        """A collection repo's files share one detail request, not one each."""
        calls: list[str] = []

        async def fake_fetch_json(url, **_kwargs):
            calls.append(url)
            return 200, _modelscope_detail_payload()

        monkeypatch.setattr(
            "py.services.model_sources.modelscope.fetch_json", fake_fetch_json
        )

        source = ModelScopeSource()
        cache = ModelSourceCache()
        filenames = [
            "Krea-2-LORA_c1-st1000.safetensors",
            "Krea-2-LORA_c1-st8000.safetensors",
            "Krea-2-LORA_c1-st1000.safetensors",
        ]
        for name in filenames:
            await source.fetch_model_card_context("u/r", name, cache=cache)

        assert calls == ["https://modelscope.cn/api/v1/models/u/r"]
        assert ("modelscope", "detail", "u/r") in cache.provider

    @pytest.mark.asyncio
    async def test_per_file_selection_still_runs_for_each_file(self, monkeypatch):
        """The cached payload must not leak one file's images to another."""

        async def fake_fetch_json(url, **_kwargs):
            return 200, _modelscope_detail_payload()

        monkeypatch.setattr(
            "py.services.model_sources.modelscope.fetch_json", fake_fetch_json
        )

        source = ModelScopeSource()
        cache = ModelSourceCache()

        st1000 = await source.fetch_model_card_context(
            "u/r", "Krea-2-LORA_c1-st1000.safetensors", cache=cache
        )
        st8000 = await source.fetch_model_card_context(
            "u/r", "Krea-2-LORA_c1-st8000.safetensors", cache=cache
        )

        assert st1000.example_images == [
            "https://resources.modelscope.cn/cover-images/b.png",
            "https://resources.modelscope.cn/cover-images/c.png",
        ]
        assert st8000.example_images == [
            "https://resources.modelscope.cn/cover-images/a.png"
        ]
        assert st8000.trigger_words == []

    @pytest.mark.asyncio
    async def test_failures_are_not_cached(self, monkeypatch):
        """A transient error must be retried for the next file."""
        calls: list[str] = []

        async def fake_fetch_json(url, **_kwargs):
            calls.append(url)
            return 500, None

        monkeypatch.setattr(
            "py.services.model_sources.modelscope.fetch_json", fake_fetch_json
        )

        source = ModelScopeSource()
        cache = ModelSourceCache()
        for _ in range(2):
            context = await source.fetch_model_card_context("u/r", "a.safetensors", cache=cache)
            assert context.is_empty()

        assert len(calls) == 2
        assert cache.provider == {}

    @pytest.mark.asyncio
    async def test_no_cache_keeps_the_uncached_behaviour(self, monkeypatch):
        calls: list[str] = []

        async def fake_fetch_json(url, **_kwargs):
            calls.append(url)
            return 200, _modelscope_detail_payload()

        monkeypatch.setattr(
            "py.services.model_sources.modelscope.fetch_json", fake_fetch_json
        )

        source = ModelScopeSource()
        for _ in range(2):
            await source.fetch_model_card_context("u/r", "a.safetensors")

        assert len(calls) == 2


class TestHashBasedVersionMatching:
    """A renamed file must still find its own example images."""

    ST1000_HASH = "b" * 64
    ST8000_HASH = "a" * 64

    @staticmethod
    def _patch(monkeypatch):
        async def fake_fetch_json(url, **_kwargs):
            return 200, _modelscope_detail_payload()

        monkeypatch.setattr(
            "py.services.model_sources.modelscope.fetch_json", fake_fetch_json
        )

    @pytest.mark.asyncio
    async def test_renamed_file_is_matched_by_sha256(self, monkeypatch):
        self._patch(monkeypatch)

        context = await ModelScopeSource().fetch_model_card_context(
            "u/r", "krea脸模-st1000-我改的名字.safetensors", sha256=self.ST1000_HASH
        )

        assert context.example_images == [
            "https://resources.modelscope.cn/cover-images/b.png",
            "https://resources.modelscope.cn/cover-images/c.png",
        ]
        assert context.trigger_words == ["kreaface", "kreamodel"]

    @pytest.mark.asyncio
    async def test_renamed_file_without_a_hash_finds_nothing(self, monkeypatch):
        """Pins the behaviour the hash match exists to fix."""
        self._patch(monkeypatch)

        context = await ModelScopeSource().fetch_model_card_context(
            "u/r", "krea脸模-st1000-我改的名字.safetensors"
        )

        assert context.example_images == []
        # Repo-wide fields are unaffected by the miss.
        assert context.base_model == "krea/Krea-2-Turbo"

    @pytest.mark.asyncio
    async def test_hash_wins_over_a_filename_that_matches_another_version(
        self, monkeypatch
    ):
        """An inconsistent name/hash pair trusts the content hash."""
        self._patch(monkeypatch)

        context = await ModelScopeSource().fetch_model_card_context(
            "u/r", "Krea-2-LORA_c1-st8000.safetensors", sha256=self.ST1000_HASH
        )

        assert context.example_images == [
            "https://resources.modelscope.cn/cover-images/b.png",
            "https://resources.modelscope.cn/cover-images/c.png",
        ]

    @pytest.mark.asyncio
    async def test_unknown_hash_falls_back_to_the_filename(self, monkeypatch):
        """A re-encoded file still matches by name rather than losing its images."""
        self._patch(monkeypatch)

        context = await ModelScopeSource().fetch_model_card_context(
            "u/r", "Krea-2-LORA_c1-st1000.safetensors", sha256="f" * 64
        )

        assert context.example_images == [
            "https://resources.modelscope.cn/cover-images/b.png",
            "https://resources.modelscope.cn/cover-images/c.png",
        ]

    @pytest.mark.asyncio
    async def test_hash_is_case_insensitive(self, monkeypatch):
        self._patch(monkeypatch)

        context = await ModelScopeSource().fetch_model_card_context(
            "u/r", "renamed.safetensors", sha256=self.ST1000_HASH.upper()
        )

        assert len(context.example_images) == 2

    @pytest.mark.asyncio
    async def test_blank_hash_is_ignored(self, monkeypatch):
        self._patch(monkeypatch)

        context = await ModelScopeSource().fetch_model_card_context(
            "u/r", "Krea-2-LORA_c1-st8000.safetensors", sha256="   "
        )

        assert context.example_images == [
            "https://resources.modelscope.cn/cover-images/a.png"
        ]

    @pytest.mark.asyncio
    async def test_missing_model_infos_degrades_to_filename_matching(self, monkeypatch):
        payload = _modelscope_detail_payload()
        del payload["Data"]["ModelInfos"]

        async def fake_fetch_json(url, **_kwargs):
            return 200, payload

        monkeypatch.setattr(
            "py.services.model_sources.modelscope.fetch_json", fake_fetch_json
        )

        context = await ModelScopeSource().fetch_model_card_context(
            "u/r", "Krea-2-LORA_c1-st1000.safetensors", sha256=self.ST1000_HASH
        )

        assert len(context.example_images) == 2

    @pytest.mark.asyncio
    async def test_real_published_hashes_are_used_by_the_agent(self):
        """The agent must pass the recorded hash, not just the filename."""
        service = AgentService()
        with (
            mock.patch(
                "py.services.model_sources.modelscope.ModelScopeSource.fetch_model_card",
                new=mock.AsyncMock(return_value="# card"),
            ),
            mock.patch(
                "py.services.model_sources.modelscope.ModelScopeSource.fetch_model_card_context",
                new=mock.AsyncMock(return_value=ModelCardContext()),
            ) as mock_ctx,
        ):
            await service._load_source_card(
                "/models/loras/renamed.safetensors",
                {
                    "source_platform": "modelscope",
                    "source_url": "https://modelscope.cn/models/u/r",
                    "sha256": "c" * 64,
                },
            )

        assert mock_ctx.call_args.kwargs["sha256"] == "c" * 64

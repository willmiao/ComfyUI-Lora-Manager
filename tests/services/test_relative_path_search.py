import os
import pytest

from py.services.base_model_service import BaseModelService
from py.utils.models import BaseModelMetadata


class DummyService(BaseModelService):
    async def format_response(self, model_data):
        return model_data


class FakeCache:
    def __init__(self, raw_data):
        self.raw_data = list(raw_data)


class FakeScanner:
    def __init__(self, raw_data, roots):
        self._cache = FakeCache(raw_data)
        self._roots = list(roots)

    async def get_cached_data(self, *_args, **_kwargs):
        return self._cache

    def get_model_roots(self):
        return list(self._roots)


class StubSettings:
    """Settings stub that returns defaults, avoiding the real settings singleton."""

    def get(self, key, default=None):
        return default


@pytest.mark.asyncio
async def test_search_relative_paths_supports_multiple_tokens():
    scanner = FakeScanner(
        [
            {"file_path": "/models/flux/detail-model.safetensors"},
            {"file_path": "/models/flux/only-flux.safetensors"},
            {"file_path": "/models/detail/flux-trained.safetensors"},
            {"file_path": "/models/detail/standalone.safetensors"},
        ],
        ["/models"],
    )
    service = DummyService("stub", scanner, BaseModelMetadata)

    matching = await service.search_relative_paths("flux detail")

    assert matching == [
        f"flux{os.sep}detail-model.safetensors",
        f"detail{os.sep}flux-trained.safetensors",
    ]


@pytest.mark.asyncio
async def test_search_relative_paths_excludes_tokens():
    scanner = FakeScanner(
        [
            {"file_path": "/models/flux/detail-model.safetensors"},
            {"file_path": "/models/flux/keep-me.safetensors"},
        ],
        ["/models"],
    )
    service = DummyService("stub", scanner, BaseModelMetadata)

    matching = await service.search_relative_paths("flux -detail")

    assert matching == [f"flux{os.sep}keep-me.safetensors"]


@pytest.mark.asyncio
async def test_search_does_not_match_extension():
    """Searching for 's' or 'safe' should not match .safetensors extension."""
    scanner = FakeScanner(
        [
            {"file_path": "/models/lora1.safetensors"},
            {"file_path": "/models/lora2.safetensors"},
            {"file_path": "/models/special-model.safetensors"},  # 's' in filename
        ],
        ["/models"],
    )
    service = DummyService("stub", scanner, BaseModelMetadata)

    # Searching for 's' should only match 'special-model', not all .safetensors
    matching = await service.search_relative_paths("s")

    # Should only match 'special-model' because 's' is in the filename
    assert len(matching) == 1
    assert "special-model" in matching[0]


@pytest.mark.asyncio
async def test_search_safe_does_not_match_all_files():
    """Searching for 'safe' should not match .safetensors extension."""
    scanner = FakeScanner(
        [
            {"file_path": "/models/flux.safetensors"},
            {"file_path": "/models/detail.safetensors"},
        ],
        ["/models"],
    )
    service = DummyService("stub", scanner, BaseModelMetadata)

    # Searching for 'safe' should return nothing (no file has 'safe' in its name)
    matching = await service.search_relative_paths("safe")

    assert len(matching) == 0


class SfwStubSettings(StubSettings):
    """Settings stub with the global SFW filter enabled."""

    def get(self, key, default=None):
        if key == "show_only_sfw":
            return True
        return default


@pytest.mark.asyncio
async def test_search_relative_paths_respects_global_sfw_setting():
    """Filtered search applies show_only_sfw like the list endpoint (parity)."""
    scanner = FakeScanner(
        [
            {"file_path": "/models/sfw-model.safetensors", "preview_nsfw_level": 0},
            {"file_path": "/models/nsfw-model.safetensors", "preview_nsfw_level": 4},
        ],
        ["/models"],
    )
    service = DummyService(
        "stub", scanner, BaseModelMetadata, settings_provider=SfwStubSettings()
    )

    matching = await service.search_relative_paths("model", apply_filters=True)

    assert matching == ["sfw-model.safetensors"]


@pytest.mark.asyncio
async def test_search_relative_paths_sfw_only_applied_when_filter_mode_is_on():
    """Global settings (show_only_sfw) apply only when the filter pipeline runs."""
    scanner = FakeScanner(
        [
            {"file_path": "/models/sfw-model.safetensors", "preview_nsfw_level": 0},
            {"file_path": "/models/nsfw-model.safetensors", "preview_nsfw_level": 4},
        ],
        ["/models"],
    )
    service = DummyService(
        "stub", scanner, BaseModelMetadata, settings_provider=SfwStubSettings()
    )

    default_matching = await service.search_relative_paths("model")

    assert default_matching == [
        "sfw-model.safetensors",
        "nsfw-model.safetensors",
    ]


@pytest.mark.asyncio
async def test_search_relative_paths_folder_filter_recursive():
    """folder filter with recursive=True (default) matches subfolders."""
    scanner = FakeScanner(
        [
            {"file_path": "/models/anime/model-a.safetensors", "folder": "anime"},
            {
                "file_path": "/models/anime/nsfw/model-b.safetensors",
                "folder": "anime/nsfw",
            },
            {"file_path": "/models/realistic/model-c.safetensors", "folder": "realistic"},
        ],
        ["/models"],
    )
    service = DummyService(
        "stub", scanner, BaseModelMetadata, settings_provider=StubSettings()
    )

    matching = await service.search_relative_paths("model", folder="anime")

    assert matching == [
        f"anime{os.sep}model-a.safetensors",
        f"anime{os.sep}nsfw{os.sep}model-b.safetensors",
    ]


@pytest.mark.asyncio
async def test_search_relative_paths_folder_filter_exact():
    """folder filter with recursive=False matches only the exact folder."""
    scanner = FakeScanner(
        [
            {"file_path": "/models/anime/model-a.safetensors", "folder": "anime"},
            {
                "file_path": "/models/anime/nsfw/model-b.safetensors",
                "folder": "anime/nsfw",
            },
            {"file_path": "/models/realistic/model-c.safetensors", "folder": "realistic"},
        ],
        ["/models"],
    )
    service = DummyService(
        "stub", scanner, BaseModelMetadata, settings_provider=StubSettings()
    )

    matching = await service.search_relative_paths(
        "model", folder="anime", recursive=False
    )

    assert matching == [f"anime{os.sep}model-a.safetensors"]


@pytest.mark.asyncio
async def test_search_relative_paths_base_model_filter():
    scanner = FakeScanner(
        [
            {"file_path": "/models/model-a.safetensors", "base_model": "SD 1.5"},
            {"file_path": "/models/model-b.safetensors", "base_model": "SDXL"},
        ],
        ["/models"],
    )
    service = DummyService(
        "stub", scanner, BaseModelMetadata, settings_provider=StubSettings()
    )

    matching = await service.search_relative_paths("model", base_models=["SD 1.5"])

    assert matching == ["model-a.safetensors"]


@pytest.mark.asyncio
async def test_search_relative_paths_tag_include():
    scanner = FakeScanner(
        [
            {"file_path": "/models/model-a.safetensors", "tags": ["anime"]},
            {"file_path": "/models/model-b.safetensors", "tags": ["realistic"]},
            {"file_path": "/models/model-c.safetensors", "tags": ["anime", "realistic"]},
        ],
        ["/models"],
    )
    service = DummyService(
        "stub", scanner, BaseModelMetadata, settings_provider=StubSettings()
    )

    matching = await service.search_relative_paths("model", tags={"anime": "include"})

    assert set(matching) == {"model-a.safetensors", "model-c.safetensors"}


@pytest.mark.asyncio
async def test_search_relative_paths_tag_exclude():
    scanner = FakeScanner(
        [
            {"file_path": "/models/model-a.safetensors", "tags": ["anime"]},
            {"file_path": "/models/model-b.safetensors", "tags": ["realistic"]},
        ],
        ["/models"],
    )
    service = DummyService(
        "stub", scanner, BaseModelMetadata, settings_provider=StubSettings()
    )

    matching = await service.search_relative_paths("model", tags={"anime": "exclude"})

    assert matching == ["model-b.safetensors"]


@pytest.mark.asyncio
async def test_search_relative_paths_auto_tag_include():
    scanner = FakeScanner(
        [
            {
                "file_path": "/models/model-i2v.safetensors",
                "file_name": "model-i2v.safetensors",
            },
            {
                "file_path": "/models/model-t2v.safetensors",
                "file_name": "model-t2v.safetensors",
            },
        ],
        ["/models"],
    )
    service = DummyService(
        "stub", scanner, BaseModelMetadata, settings_provider=StubSettings()
    )

    matching = await service.search_relative_paths(
        "model", auto_tags={"I2V": "include"}
    )

    assert matching == ["model-i2v.safetensors"]


@pytest.mark.asyncio
async def test_search_relative_paths_tag_logic_all():
    scanner = FakeScanner(
        [
            {"file_path": "/models/model-a.safetensors", "tags": ["anime", "style"]},
            {"file_path": "/models/model-b.safetensors", "tags": ["anime"]},
        ],
        ["/models"],
    )
    service = DummyService(
        "stub", scanner, BaseModelMetadata, settings_provider=StubSettings()
    )

    matching = await service.search_relative_paths(
        "model", tags={"anime": "include", "style": "include"}, tag_logic="all"
    )

    assert matching == ["model-a.safetensors"]


@pytest.mark.asyncio
async def test_search_relative_paths_credit_required_filter():
    # license_flags bit0: 1 = no credit required, 0 = credit required
    scanner = FakeScanner(
        [
            {"file_path": "/models/model-a.safetensors", "license_flags": 127},
            {"file_path": "/models/model-b.safetensors", "license_flags": 0},
        ],
        ["/models"],
    )
    service = DummyService(
        "stub", scanner, BaseModelMetadata, settings_provider=StubSettings()
    )

    matching = await service.search_relative_paths("model", credit_required=True)
    assert matching == ["model-b.safetensors"]

    matching = await service.search_relative_paths("model", credit_required=False)
    assert matching == ["model-a.safetensors"]


@pytest.mark.asyncio
async def test_search_relative_paths_allow_selling_filter():
    # license_flags bit1: 1 = commercial image use allowed, 0 = not allowed
    scanner = FakeScanner(
        [
            {"file_path": "/models/model-a.safetensors", "license_flags": 2},
            {"file_path": "/models/model-b.safetensors", "license_flags": 1},
        ],
        ["/models"],
    )
    service = DummyService(
        "stub", scanner, BaseModelMetadata, settings_provider=StubSettings()
    )

    matching = await service.search_relative_paths(
        "model", allow_selling_generated_content=True
    )
    assert matching == ["model-a.safetensors"]

    matching = await service.search_relative_paths(
        "model", allow_selling_generated_content=False
    )
    assert matching == ["model-b.safetensors"]


@pytest.mark.asyncio
async def test_search_relative_paths_no_filters_regression():
    """No filter kwargs -> behavior is byte-identical to plain token matching."""
    scanner = FakeScanner(
        [
            {"file_path": "/models/flux/detail-model.safetensors"},
            {"file_path": "/models/flux/only-flux.safetensors"},
        ],
        ["/models"],
    )
    service = DummyService(
        "stub", scanner, BaseModelMetadata, settings_provider=StubSettings()
    )

    matching = await service.search_relative_paths("flux")

    assert matching == [
        f"flux{os.sep}only-flux.safetensors",
        f"flux{os.sep}detail-model.safetensors",
    ]


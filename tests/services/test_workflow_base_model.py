"""Tests for py.services.workflow_base_model: base model resolution."""

from py.services.model_scanner import ModelScanner
from py.services.workflow_base_model import resolve_workflow_base_model


class _FakeModelScanner:
    """Stand-in for the lora/checkpoint scanners backed by fixed items."""

    def __init__(self, items):
        self._items = items

    async def find_models_by_name(self, name, *, base_model=None):
        return ModelScanner.find_matching_models(
            self._items, name, base_model=base_model
        )


class _FakeProvider:
    def __init__(self, infos):
        self._infos = infos
        self.calls = []

    async def get_model_version_info(self, version_id):
        self.calls.append(version_id)
        return self._infos.get(version_id), None


def _checkpoint(file_name, base_model, folder=""):
    return {"file_name": file_name, "folder": folder, "base_model": base_model}


async def test_resolves_from_checkpoint_loader_refs():
    checkpoint_scanner = _FakeModelScanner(
        [_checkpoint("sd_xl_base_1.0.safetensors", "SDXL 1.0")]
    )
    result = await resolve_workflow_base_model(
        primary_model_refs=["sd_xl_base_1.0.safetensors"],
        model_refs=["sd_xl_base_1.0.safetensors"],
        checkpoint_scanner=checkpoint_scanner,
        lora_scanner=_FakeModelScanner([]),
    )
    assert result == "SDXL 1.0"


async def test_checkpoint_refs_accept_spaced_and_foldered_names():
    checkpoint_scanner = _FakeModelScanner(
        [_checkpoint("My Model v2.safetensors", "SDXL 1.0", folder="SDXL")]
    )
    result = await resolve_workflow_base_model(
        primary_model_refs=["SDXL/My Model v2.safetensors"],
        model_refs=[],
        checkpoint_scanner=checkpoint_scanner,
        lora_scanner=_FakeModelScanner([]),
    )
    assert result == "SDXL 1.0"


async def test_checkpoint_majority_vote_wins():
    checkpoint_scanner = _FakeModelScanner(
        [
            _checkpoint("base.safetensors", "SDXL 1.0"),
            _checkpoint("refiner.safetensors", "SDXL 1.0"),
            _checkpoint("other.safetensors", "SD 1.5"),
        ]
    )
    result = await resolve_workflow_base_model(
        primary_model_refs=[
            "base.safetensors",
            "refiner.safetensors",
            "other.safetensors",
        ],
        model_refs=[],
        checkpoint_scanner=checkpoint_scanner,
        lora_scanner=_FakeModelScanner([]),
    )
    assert result == "SDXL 1.0"


async def test_unknown_checkpoint_base_model_never_votes():
    checkpoint_scanner = _FakeModelScanner(
        [_checkpoint("base.safetensors", "Unknown")]
    )
    lora_scanner = _FakeModelScanner(
        [_checkpoint("style.safetensors", "Pony")]
    )
    result = await resolve_workflow_base_model(
        primary_model_refs=["base.safetensors"],
        model_refs=["style.safetensors"],
        checkpoint_scanner=checkpoint_scanner,
        lora_scanner=lora_scanner,
    )
    assert result == "Pony"


async def test_lora_majority_vote_is_the_fallback():
    checkpoint_scanner = _FakeModelScanner([])
    lora_scanner = _FakeModelScanner(
        [
            _checkpoint("a.safetensors", "Illustrious"),
            _checkpoint("b.safetensors", "Illustrious"),
            _checkpoint("c.safetensors", "SDXL 1.0"),
        ]
    )
    result = await resolve_workflow_base_model(
        primary_model_refs=["not-in-library.safetensors"],
        model_refs=["a.safetensors", "b.safetensors", "c.safetensors"],
        checkpoint_scanner=checkpoint_scanner,
        lora_scanner=lora_scanner,
    )
    assert result == "Illustrious"


async def test_civitai_urn_fallback_requires_opt_in():
    provider = _FakeProvider({"67890": {"baseModel": "SDXL 1.0"}})
    kwargs = dict(
        primary_model_refs=[],
        model_refs=[],
        civitai_refs=["civitai:12345@67890"],
        checkpoint_scanner=_FakeModelScanner([]),
        lora_scanner=_FakeModelScanner([]),
        metadata_provider=provider,
    )

    assert await resolve_workflow_base_model(**kwargs) is None
    assert provider.calls == []

    assert await resolve_workflow_base_model(**kwargs, include_remote=True) == "SDXL 1.0"
    assert provider.calls == ["67890"]


async def test_civitai_urn_fallback_ignores_unknown_answers():
    provider = _FakeProvider(
        {"111": {"baseModel": ""}, "222": {"baseModel": "Flux.1 D"}}
    )
    result = await resolve_workflow_base_model(
        primary_model_refs=[],
        model_refs=[],
        civitai_refs=["civitai:1@111", "civitai:2@222"],
        checkpoint_scanner=_FakeModelScanner([]),
        lora_scanner=_FakeModelScanner([]),
        include_remote=True,
        metadata_provider=provider,
    )
    assert result == "Flux.1 D"


async def test_checkpoint_name_hint_outranks_static_votes():
    checkpoint_scanner = _FakeModelScanner(
        [
            _checkpoint("real_primary.safetensors", "Illustrious"),
            _checkpoint("voted.safetensors", "SDXL 1.0"),
        ]
    )
    result = await resolve_workflow_base_model(
        primary_model_refs=["voted.safetensors"],
        model_refs=["voted.safetensors"],
        checkpoint_scanner=checkpoint_scanner,
        lora_scanner=_FakeModelScanner([]),
        checkpoint_name_hint="real_primary.safetensors",
    )
    assert result == "Illustrious"


async def test_checkpoint_name_hint_falls_back_to_votes_when_unresolved():
    checkpoint_scanner = _FakeModelScanner(
        [_checkpoint("voted.safetensors", "SDXL 1.0")]
    )
    result = await resolve_workflow_base_model(
        primary_model_refs=["voted.safetensors"],
        model_refs=["voted.safetensors"],
        checkpoint_scanner=checkpoint_scanner,
        lora_scanner=_FakeModelScanner([]),
        checkpoint_name_hint="deleted-model.safetensors",
    )
    assert result == "SDXL 1.0"


async def test_returns_none_when_nothing_resolves():
    result = await resolve_workflow_base_model(
        primary_model_refs=["missing.safetensors"],
        model_refs=["missing.safetensors"],
        checkpoint_scanner=_FakeModelScanner([]),
        lora_scanner=_FakeModelScanner([]),
    )
    assert result is None

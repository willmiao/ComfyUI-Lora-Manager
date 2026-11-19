from __future__ import annotations

import pytest

from py.services import wildcard_service as runtime_module
from py.services.wildcard_activation_service import (
    WildcardActivationService,
    WildcardConflictError,
)
from py.services.wildcard_parser import parse_wildcard_artifact
from py.services.wildcard_service import WildcardService


@pytest.fixture
def activation_state(tmp_path, monkeypatch):
    manual_dir = tmp_path / "manual"
    monkeypatch.setattr(runtime_module, "get_wildcards_dir", lambda create=False: str(manual_dir))
    runtime = WildcardService()
    runtime._cached_signature = None
    runtime._manual_cached_signature = None
    service = WildcardActivationService(str(tmp_path / "wildcard-activations.json"))
    monkeypatch.setattr(
        "py.services.wildcard_activation_service.get_wildcard_activation_service",
        lambda: service,
    )
    return service, runtime, manual_dir, tmp_path


def resource_for(file_path):
    parsed = parse_wildcard_artifact(str(file_path))
    return {
        "file_path": str(file_path),
        "file_name": file_path.stem,
        "model_name": file_path.stem,
        "sha256": "test-hash",
        "entries": [entry.summary() for entry in parsed.entries],
    }


def test_runtime_loads_only_activated_resources(activation_state):
    service, runtime, _manual, root = activation_state
    artifact = root / "colors.txt"
    artifact.write_text("red\nblue\n", encoding="utf-8")
    resource = resource_for(artifact)

    assert runtime.get_wildcard_dict() == {}
    service.activate(resource)
    assert runtime.expand_text("__colors__", seed=0) in ("red", "blue")
    assert service.decorate(resource)["active"] is True

    service.deactivate(str(artifact))
    assert runtime.get_wildcard_dict() == {}


def test_alias_and_namespace_apply_to_yaml(activation_state):
    service, runtime, _manual, root = activation_state
    artifact = root / "palette.yaml"
    artifact.write_text("warm:\n  - red\n  - orange\n", encoding="utf-8")
    resource = resource_for(artifact)

    result = service.activate(resource, "Design", {"warm": "Warm Colors"})

    assert result["keys"] == ["design/warm colors"]
    assert runtime.get_wildcard_dict() == {"design/warm colors": ["red", "orange"]}
    assert service.get_entry_values(str(artifact), "design/warm colors")["values"] == ["red", "orange"]


def test_conflicts_include_manual_and_other_active_resources(activation_state):
    service, _runtime, manual, root = activation_state
    manual.mkdir()
    (manual / "color.txt").write_text("manual\n", encoding="utf-8")
    artifact = root / "nested.txt"
    artifact.write_text("blue\n", encoding="utf-8")
    resource = resource_for(artifact)
    resource["entries"][0]["key"] = "nested/color"
    artifact.unlink()
    (root / "pack.txt").write_text("blue\n", encoding="utf-8")
    resource["file_path"] = str(root / "pack.txt")

    with pytest.raises(WildcardConflictError) as caught:
        service.activate(resource, aliases={"nested/color": "color"})
    assert caught.value.conflicts[0]["key"] == "color"


def test_activation_state_persists(activation_state):
    service, _runtime, _manual, root = activation_state
    artifact = root / "animals.txt"
    artifact.write_text("cat\ndog\n", encoding="utf-8")
    service.activate(resource_for(artifact))

    reloaded = WildcardActivationService(service.activations_path)
    assert reloaded.get_active_runtime()[0] == {"animals": ["cat", "dog"]}

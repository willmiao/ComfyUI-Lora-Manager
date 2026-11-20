from __future__ import annotations

import json

import pytest

from py.services import wildcard_service as runtime_module
from py.services.wildcard_activation_service import (
    WildcardActivationService,
    WildcardConflictError,
    WildcardLibraryError,
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


def _nested_anime_resource(root):
    artifact = root / "anime.json"
    artifact.write_text(
        json.dumps({"anime": {"bang_dream": ["ichigaya arisa"]}}), encoding="utf-8"
    )
    return resource_for(artifact)


def test_alias_may_contain_punctuation(activation_state):
    service, runtime, _manual, root = activation_state
    resource = _nested_anime_resource(root)

    result = service.activate(resource, aliases={"anime/bang_dream": "bang_dream!"})

    assert result["keys"] == ["bang_dream!"]
    assert runtime.expand_text("__bang_dream!__", seed=0) == "ichigaya arisa"


def test_alias_rejects_names_that_break_the_token_syntax(activation_state):
    service, _runtime, _manual, root = activation_state
    resource = _nested_anime_resource(root)

    for alias in ("a__b", "{a|b}", "line\nbreak"):
        with pytest.raises(WildcardLibraryError):
            service.preview_activation(resource, aliases={"anime/bang_dream": alias})


def test_unreferenceable_keys_are_reported_and_alias_rescues_them(activation_state):
    service, _runtime, _manual, root = activation_state
    artifact = root / "edge.txt"
    artifact.write_text("value\n", encoding="utf-8")
    resource = resource_for(artifact)
    resource["entries"][0]["key"] = "a__b"

    preview = service.preview_activation(resource)
    assert preview["unreferenceable_keys"] == [
        {"key": "a__b", "reason": "contains '__', which closes the token early"}
    ]
    assert service.decorate(resource)["entries"][0]["reference_problem"]

    preview = service.preview_activation(resource, aliases={"a__b": "a_b"})
    assert preview["unreferenceable_keys"] == []

    service.activate(resource, aliases={"a__b": "a_b"})
    decorated = service.decorate(resource)["entries"][0]
    assert decorated["effective_key"] == "a_b"
    assert decorated["reference_problem"] is None


def test_activation_state_persists(activation_state):
    service, _runtime, _manual, root = activation_state
    artifact = root / "animals.txt"
    artifact.write_text("cat\ndog\n", encoding="utf-8")
    service.activate(resource_for(artifact))

    reloaded = WildcardActivationService(service.activations_path)
    assert reloaded.get_active_runtime()[0] == {"animals": ["cat", "dog"]}


def test_deactivation_keeps_settings_for_reactivation(activation_state):
    service, runtime, _manual, root = activation_state
    artifact = root / "palette.yaml"
    artifact.write_text("warm:\n  - red\n  - orange\n", encoding="utf-8")
    resource = resource_for(artifact)

    service.activate(resource, "Design", {"warm": "Warm Colors"})
    service.deactivate(str(artifact))

    saved = service.activation_for(str(artifact), include_inactive=True)
    assert saved["active"] is False
    assert saved["namespace"] == "design"
    assert saved["aliases"] == {"warm": "warm colors"}
    assert service.activation_for(str(artifact)) is None
    assert runtime.get_wildcard_dict() == {}

    decorated = service.decorate(resource)
    assert decorated["active"] is False
    assert decorated["activation_namespace"] == "design"
    assert decorated["activation_aliases"] == {"warm": "warm colors"}
    assert decorated["entries"][0]["effective_key"] == "warm"

    result = service.activate(resource)
    assert result["namespace"] == "design"
    assert result["keys"] == ["design/warm colors"]
    assert runtime.get_wildcard_dict() == {"design/warm colors": ["red", "orange"]}


def test_inactive_resource_is_skipped_in_conflict_check(activation_state):
    service, _runtime, _manual, root = activation_state
    first = root / "first.txt"
    first.write_text("red\n", encoding="utf-8")
    second = root / "second.txt"
    second.write_text("blue\n", encoding="utf-8")

    first_resource = resource_for(first)
    first_resource["entries"][0]["key"] = "color"
    second_resource = resource_for(second)
    second_resource["entries"][0]["key"] = "color"

    service.activate(first_resource)
    service.deactivate(str(first))
    service.activate(second_resource)

    assert service.activation_for(str(second))["active"] is True


def test_legacy_activation_record_without_active_flag_is_active(activation_state):
    service, _runtime, _manual, root = activation_state
    artifact = root / "animals.txt"
    artifact.write_text("cat\ndog\n", encoding="utf-8")
    resource = resource_for(artifact)

    # A file written before deactivation kept records carried no explicit
    # state: presence meant active. Derive it from the service's own output so
    # the stored path keys keep the platform-correct form.
    service.activate(resource)
    with open(service.activations_path, "r", encoding="utf-8") as handle:
        payload = json.load(handle)
    for record in payload["resources"].values():
        record.pop("active", None)
    with open(service.activations_path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle)

    loaded = WildcardActivationService(service.activations_path)
    assert loaded.activation_for(str(artifact))["active"] is True
    assert loaded.get_active_runtime()[0] == {"animals": ["cat", "dog"]}

    loaded.deactivate(str(artifact))
    assert loaded.get_active_runtime()[0] == {}
    assert loaded.activation_for(str(artifact), include_inactive=True)["active"] is False


def test_rebind_path_preserves_activation_configuration_and_runtime(activation_state):
    service, runtime, _manual, root = activation_state
    artifact = root / "palette.yaml"
    artifact.write_text("warm:\n  - red\n  - orange\n", encoding="utf-8")
    resource = resource_for(artifact)
    service.activate(resource, "Design", {"warm": "Warm Colors"})
    target = root / "nested" / "renamed.yaml"
    target.parent.mkdir()
    artifact.rename(target)

    rebound = service.rebind_path(str(artifact), str(target))

    assert rebound["active"] is True
    assert rebound["namespace"] == "design"
    assert rebound["aliases"] == {"warm": "warm colors"}
    assert service.activation_for(str(artifact), include_inactive=True) is None
    restored = service.activation_for(str(target))
    assert restored["file_path"] == str(target)
    assert restored["activated_at"] == rebound["activated_at"]
    assert runtime.get_wildcard_dict() == {"design/warm colors": ["red", "orange"]}


def test_rebind_paths_handles_active_and_inactive_records(activation_state):
    service, _runtime, _manual, root = activation_state
    active = root / "active.txt"
    inactive = root / "inactive.txt"
    active.write_text("red\n", encoding="utf-8")
    inactive.write_text("blue\n", encoding="utf-8")
    service.activate(resource_for(active), "active", {"active": "active"})
    service.activate(resource_for(inactive), "inactive", {"inactive": "Inactive Colors"})
    service.deactivate(str(inactive))
    active_target = root / "moved" / "active.txt"
    inactive_target = root / "moved" / "inactive.txt"
    active_target.parent.mkdir()
    active.rename(active_target)
    inactive.rename(inactive_target)

    rebound = service.rebind_paths({
        str(active): str(active_target),
        str(inactive): str(inactive_target),
        str(root / "untracked.txt"): str(root / "moved" / "untracked.txt"),
    })

    assert set(rebound) == {str(active), str(inactive)}
    assert service.activation_for(str(active_target))["active"] is True
    restored_inactive = service.activation_for(str(inactive_target), include_inactive=True)
    assert restored_inactive["active"] is False
    assert restored_inactive["namespace"] == "inactive"
    assert restored_inactive["aliases"] == {"inactive": "inactive colors"}


def test_rebind_paths_does_not_overwrite_destination_settings(activation_state):
    service, _runtime, _manual, root = activation_state
    source = root / "source.txt"
    destination = root / "destination.txt"
    source.write_text("red\n", encoding="utf-8")
    destination.write_text("blue\n", encoding="utf-8")
    service.activate(resource_for(source), "source", {"source": "source"})
    service.activate(resource_for(destination), "destination", {"destination": "destination"})
    source.rename(root / "source-moved.txt")

    with pytest.raises(WildcardLibraryError):
        service.rebind_path(str(source), str(destination))

    assert service.activation_for(str(source), include_inactive=True) is not None
    assert service.activation_for(str(destination))["namespace"] == "destination"


def test_reconcile_resources_recovers_unique_external_move(activation_state):
    service, runtime, _manual, root = activation_state
    artifact = root / "colors.txt"
    artifact.write_text("red\nblue\n", encoding="utf-8")
    resource = resource_for(artifact)
    service.activate(resource, "palette", {"colors": "colors"})
    target = root / "external" / "colors.txt"
    target.parent.mkdir()
    artifact.rename(target)
    moved_resource = resource_for(target)

    rebound = service.reconcile_resources([moved_resource])

    assert list(rebound) == [str(artifact)]
    assert service.activation_for(str(target))["namespace"] == "palette"
    assert runtime.get_wildcard_dict() == {"palette/colors": ["red", "blue"]}


def test_reconcile_resources_skips_duplicate_hash_matches(activation_state):
    service, runtime, _manual, root = activation_state
    artifact = root / "colors.txt"
    artifact.write_text("red\nblue\n", encoding="utf-8")
    resource = resource_for(artifact)
    service.activate(resource)
    first = root / "first.txt"
    second = root / "second.txt"
    artifact.rename(first)
    second.write_text("red\nblue\n", encoding="utf-8")

    rebound = service.reconcile_resources([resource_for(first), resource_for(second)])

    assert rebound == {}
    assert service.activation_for(str(artifact), include_inactive=True) is not None
    assert runtime.get_wildcard_dict() == {}


def test_reconcile_resources_skips_hash_shared_by_missing_records(activation_state):
    service, runtime, _manual, root = activation_state
    first = root / "first.txt"
    second = root / "second.txt"
    first.write_text("red\n", encoding="utf-8")
    second.write_text("blue\n", encoding="utf-8")
    service.activate(resource_for(first), "first", {"first": "first"})
    service.activate(resource_for(second), "second", {"second": "second"})
    target = root / "target.txt"
    first.rename(root / "first-moved.txt")
    second.rename(root / "second-moved.txt")
    target.write_text("red\n", encoding="utf-8")

    rebound = service.reconcile_resources([resource_for(target)])

    assert rebound == {}
    assert service.activation_for(str(first), include_inactive=True) is not None
    assert service.activation_for(str(second), include_inactive=True) is not None
    assert runtime.get_wildcard_dict() == {}


def test_reconcile_resources_ignores_candidates_missing_from_disk(activation_state):
    service, _runtime, _manual, root = activation_state
    artifact = root / "colors.txt"
    artifact.write_text("red\nblue\n", encoding="utf-8")
    service.activate(resource_for(artifact))
    target = root / "target.txt"
    artifact.rename(target)
    stale_resource = resource_for(target)
    target.unlink()

    rebound = service.reconcile_resources([stale_resource])

    assert rebound == {}
    assert service.activation_for(str(artifact), include_inactive=True) is not None

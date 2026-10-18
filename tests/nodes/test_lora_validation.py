"""Tests for queue-time LoRA validation helpers (validate_lora_entries)."""

import pytest

from py.nodes.utils import _find_missing_loras, validate_lora_entries


class _FakeCache:
    def __init__(self, raw_data):
        self.raw_data = raw_data


class _FakeScanner:
    def __init__(self, raw_data):
        self._raw_data = raw_data
        # Non-None cache marks the scanner as initialized; None means the
        # real scanner has not hydrated yet (validation must stay lenient).
        self._cache = object()
        self._is_initializing = False

    async def get_cached_data(self, force_refresh=False):
        return _FakeCache(self._raw_data)


@pytest.fixture
def lora_library(tmp_path):
    """Create a fake on-disk LoRA library plus a matching scanner cache."""
    existing_a = tmp_path / "a.safetensors"
    existing_b = tmp_path / "sub" / "b.safetensors"
    existing_a.write_bytes(b"a")
    existing_b.parent.mkdir()
    existing_b.write_bytes(b"b")

    # "gone" is referenced by the cache but the file was deleted afterwards,
    # simulating a stale scanner cache.
    gone = tmp_path / "gone.safetensors"

    raw_data = [
        {"file_name": "a.safetensors", "folder": "", "file_path": str(existing_a)},
        {
            "file_name": "b.safetensors",
            "folder": "sub",
            "file_path": str(existing_b),
        },
        {"file_name": "gone.safetensors", "folder": "", "file_path": str(gone)},
    ]
    return raw_data


@pytest.fixture
def mock_lora_scanner(lora_library, monkeypatch):
    from py.services.service_registry import ServiceRegistry

    async def _fake_scanner():
        return _FakeScanner(lora_library)

    monkeypatch.setattr(
        ServiceRegistry, "get_lora_scanner", _fake_scanner
    )


def _entries(*names):
    return [
        {"active": True, "name": name, "strength": 1.0, "clipStrength": 1.0}
        for name in names
    ]


def test_validate_flat_name_with_extension(mock_lora_scanner):
    assert validate_lora_entries({"loras": _entries("a.safetensors")}) is None


def test_validate_flat_name_without_extension(mock_lora_scanner):
    assert validate_lora_entries({"loras": _entries("a")}) is None


def test_validate_subfolder_name(mock_lora_scanner):
    assert validate_lora_entries({"loras": _entries("sub/b.safetensors")}) is None
    assert validate_lora_entries({"loras": _entries("sub/b")}) is None


def test_validate_stale_cache_entry_reported(mock_lora_scanner):
    result = validate_lora_entries({"loras": _entries("gone.safetensors")})
    assert result is not None
    assert "gone.safetensors" in result


def test_validate_unknown_name_reported(mock_lora_scanner):
    result = validate_lora_entries({"loras": _entries("nope.safetensors")})
    assert result is not None
    assert "nope.safetensors" in result


def test_validate_multiple_missing_all_listed(mock_lora_scanner):
    result = validate_lora_entries(
        {"loras": _entries("gone.safetensors", "nope.safetensors")}
    )
    assert result is not None
    assert "gone.safetensors" in result
    assert "nope.safetensors" in result


def test_validate_inactive_entries_ignored(mock_lora_scanner):
    kwargs = {"loras": [{"active": False, "name": "gone.safetensors", "strength": 1.0}]}
    assert validate_lora_entries(kwargs) is None


def test_validate_value_wrapper_format(mock_lora_scanner):
    kwargs = {"loras": {"__value__": _entries("a.safetensors")}}
    assert validate_lora_entries(kwargs) is None
    kwargs_missing = {"loras": {"__value__": _entries("gone.safetensors")}}
    assert validate_lora_entries(kwargs_missing) is not None


def test_validate_legacy_basename_fallback(mock_lora_scanner):
    # A name with a folder that only matches by basename resolves at runtime
    # via get_lora_info_absolute's fallback, so it must not be flagged.
    assert validate_lora_entries({"loras": _entries("other/b.safetensors")}) is None


def test_validate_existing_absolute_path_ok(mock_lora_scanner, lora_library):
    existing_a = lora_library[0]["file_path"]
    assert validate_lora_entries({"loras": _entries(existing_a)}) is None


def test_validate_missing_absolute_path_reported(mock_lora_scanner):
    result = validate_lora_entries(
        {"loras": _entries("/nonexistent/path/x.safetensors")}
    )
    # Legacy syntax format normalizes to the basename, matching execution.
    assert result is not None
    assert "x.safetensors" in result


def test_validate_empty_or_missing_loras_is_valid(mock_lora_scanner):
    assert validate_lora_entries({}) is None
    assert validate_lora_entries({"loras": []}) is None


def test_validate_scanner_failure_is_lenient(monkeypatch):
    from py.services.service_registry import ServiceRegistry

    def _boom():
        raise RuntimeError("scanner not initialized")

    monkeypatch.setattr(ServiceRegistry, "get_lora_scanner", _boom)
    assert validate_lora_entries({"loras": _entries("a.safetensors")}) is None


def test_find_missing_loras_empty(mock_lora_scanner):
    assert _find_missing_loras([]) == []


def test_validate_inputs_only_reports_loras_input(mock_lora_scanner):
    """VALIDATE_INPUTS must fail for the single 'loras' input only — ComfyUI
    creates one custom_validation_failed error per declared input, so an
    explicit loras parameter keeps the report to a single input error."""
    from py.nodes.lora_loader import LoraLoaderLM
    from py.nodes.lora_stacker import LoraStackerLM
    from py.nodes.create_hook_lora import CreateHookLoraLM
    from py.nodes.wanvideo_lora_select import WanVideoLoraSelectLM
    from py.nodes.lora_randomizer import LoraRandomizerLM

    import inspect

    for cls in (
        LoraLoaderLM,
        LoraStackerLM,
        CreateHookLoraLM,
        WanVideoLoraSelectLM,
        LoraRandomizerLM,
    ):
        spec = inspect.getfullargspec(getattr(cls, "VALIDATE_INPUTS"))
        assert spec.varkw is None, f"{cls.__name__} VALIDATE_INPUTS must not accept **kwargs"
        assert "loras" in spec.args, f"{cls.__name__} VALIDATE_INPUTS must declare loras"

    result = LoraLoaderLM.VALIDATE_INPUTS(
        loras=[
            {"active": True, "name": "gone.safetensors", "strength": 1.0},
        ]
    )
    assert result is not None
    assert "gone.safetensors" in result

    assert LoraLoaderLM.VALIDATE_INPUTS(loras=None) is True
    assert LoraLoaderLM.VALIDATE_INPUTS() is True
    assert LoraLoaderLM.VALIDATE_INPUTS(loras=[]) is True


def test_validate_lenient_when_scanner_not_initialized(monkeypatch):
    """An unhydrated scanner (empty cache) must not reject every LoRA."""
    from py.services.service_registry import ServiceRegistry

    class _UninitializedScanner(_FakeScanner):
        def __init__(self, raw_data):
            super().__init__(raw_data)
            self._cache = None

    async def _fake_scanner():
        return _UninitializedScanner([])

    monkeypatch.setattr(ServiceRegistry, "get_lora_scanner", _fake_scanner)
    assert validate_lora_entries({"loras": _entries("a.safetensors")}) is None


def test_validate_lenient_while_scanner_initializing(monkeypatch):
    from py.services.service_registry import ServiceRegistry

    class _InitializingScanner(_FakeScanner):
        def __init__(self, raw_data):
            super().__init__(raw_data)
            self._is_initializing = True

    async def _fake_scanner():
        return _InitializingScanner([])

    monkeypatch.setattr(ServiceRegistry, "get_lora_scanner", _fake_scanner)
    assert validate_lora_entries({"loras": _entries("a.safetensors")}) is None


def test_find_missing_basename_fallback_prefers_folder_prefix(
    tmp_path, monkeypatch
):
    """Folder-prefix candidates win over the first basename match, mirroring
    get_lora_info_absolute's fallback ordering."""
    from py.services.service_registry import ServiceRegistry

    root_a = tmp_path / "root_a"
    root_b = tmp_path / "root_b"
    root_a.mkdir()
    root_b.mkdir()
    live_a = root_a / "x.safetensors"
    live_a.write_bytes(b"x")
    stale_b = root_b / "x.safetensors"  # same basename, file deleted

    raw_data = [
        {"file_name": "x.safetensors", "folder": "root_a", "file_path": str(live_a)},
        {"file_name": "x.safetensors", "folder": "root_b", "file_path": str(stale_b)},
    ]

    async def _fake_scanner():
        return _FakeScanner(raw_data)

    monkeypatch.setattr(ServiceRegistry, "get_lora_scanner", _fake_scanner)
    # Exact path matches are authoritative.
    assert _find_missing_loras(["root_b/x"]) == ["root_b/x"]
    # Folder-prefix fallback beats the first basename match: root_a is live.
    assert _find_missing_loras(["root_a/deep/x"]) == []
    # Prefix match wins over the first candidate: root_b is stale.
    assert _find_missing_loras(["root_b/deep/x"]) == ["root_b/deep/x"]
    # No prefix match: falls back to the first basename candidate (root_a).
    assert _find_missing_loras(["other/x"]) == []

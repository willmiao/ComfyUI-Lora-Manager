"""Performance-regression tests for the bulk filename-template rename path.

The bulk "Apply to Library" rename must be O(1)-per-file: the heavyweight
cache persist/resort chain and the recipe maintenance run exactly once per
bulk operation (even on cancellation or mid-loop errors), while single-shot
renames keep their immediate per-call behavior.
"""

from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncIterator, Dict, List, Optional

import pytest

from py.services import model_scanner as model_scanner_module
from py.services.model_cache import ModelCache
from py.services.model_lifecycle_service import ModelLifecycleService
from py.services.model_scanner import ModelScanner
from py.services.settings_manager import get_settings_manager
from py.services.use_cases.filename_template_use_case import FilenameTemplateUseCase
from py.utils.models import BaseModelMetadata


class BulkDummyScanner(ModelScanner):
    """Minimal concrete scanner for cache-behavior tests."""

    def __init__(self, root: Path):
        self._root = str(root)
        super().__init__(
            model_type="dummy",
            model_class=BaseModelMetadata,
            file_extensions={".txt"},
        )

    def get_model_roots(self) -> List[str]:
        return [self._root]


@pytest.fixture(autouse=True)
def _reset_model_scanner_singletons():
    ModelScanner._instances.clear()
    ModelScanner._locks.clear()
    yield
    ModelScanner._instances.clear()
    ModelScanner._locks.clear()


@pytest.fixture(autouse=True)
def _disable_persistent_cache_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("LORA_MANAGER_DISABLE_PERSISTENT_CACHE", "1")


@pytest.fixture(autouse=True)
def _stub_register_service(monkeypatch: pytest.MonkeyPatch):
    async def noop(*_args: Any, **_kwargs: Any) -> None:
        return None

    monkeypatch.setattr(
        model_scanner_module.ServiceRegistry, "register_service", noop
    )


def _metadata(stem: str, path: str, sha256: str, civitai_id: int = 1) -> Dict[str, Any]:
    return {
        "file_name": stem,
        "file_path": path,
        "model_name": stem,
        "sha256": sha256,
        "folder": "",
        "tags": [],
        "size": 1,
        "modified": 1.0,
        "civitai": {"id": civitai_id, "modelId": 2},
    }


class _SpiedCache:
    """Scanner cache with call counters for resort/persist/sync."""

    def __init__(self, scanner: BulkDummyScanner, entries: List[Dict[str, Any]]):
        self.cache = ModelCache(raw_data=[dict(e) for e in entries], folders=[])
        scanner._cache = self.cache
        self.resort_calls = 0
        self.save_calls: List[bool] = []
        self.sync_calls = 0
        self._original_resort = self.cache.resort

    async def resort(self) -> None:
        self.resort_calls += 1
        await self._original_resort()

    async def fake_save(self, scan_result: Any, *, force: bool = False) -> None:
        self.save_calls.append(force)

    async def fake_sync(self, raw_data: Any, *, source: str) -> None:
        self.sync_calls += 1


async def _make_spied_scanner(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, entries: List[Dict[str, Any]]
) -> tuple[BulkDummyScanner, _SpiedCache]:
    scanner = BulkDummyScanner(tmp_path)
    spied = _SpiedCache(scanner, entries)
    # Truthy stand-in so _persist_current_cache() does not early-return.
    scanner._persistent_cache = object()
    monkeypatch.setattr(scanner, "_save_persistent_cache", spied.fake_save)
    monkeypatch.setattr(scanner, "_sync_download_history", spied.fake_sync)
    # Flush the resort task scheduled by ModelCache.__post_init__ before
    # installing the counting wrapper.
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    monkeypatch.setattr(spied.cache, "resort", spied.resort)
    return scanner, spied


# ---------------------------------------------------------------------------
# ModelScanner deferred persist
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_update_single_model_cache_persists_immediately_by_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    path_a = (tmp_path / "a.txt").as_posix()
    scanner, spied = await _make_spied_scanner(
        tmp_path, monkeypatch, [_metadata("a", path_a, "hash-a")]
    )

    await scanner.update_single_model_cache(
        path_a, path_a, _metadata("a", path_a, "hash-a")
    )

    assert spied.save_calls == [False]
    assert spied.sync_calls == 1
    assert spied.resort_calls == 1


@pytest.mark.asyncio
async def test_deferred_cache_persist_persists_once_for_many_updates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    entries = []
    for index, stem in enumerate(("a", "b", "c")):
        path = (tmp_path / f"{stem}.txt").as_posix()
        entries.append(_metadata(stem, path, f"hash-{stem}", civitai_id=index + 1))
    scanner, spied = await _make_spied_scanner(tmp_path, monkeypatch, entries)

    async with scanner.defer_cache_persist():
        for index, stem in enumerate(("a", "b", "c")):
            old_path = (tmp_path / f"{stem}.txt").as_posix()
            new_path = (tmp_path / f"{stem}-renamed.txt").as_posix()
            await scanner.update_single_model_cache(
                old_path,
                new_path,
                _metadata(
                    f"{stem}-renamed", new_path, f"hash-{stem}", civitai_id=index + 1
                ),
            )
        # Nothing heavy may run mid-loop.
        assert spied.save_calls == []
        assert spied.sync_calls == 0
        assert spied.resort_calls == 0

    # Exactly one heavyweight finalize for the whole bulk operation.
    assert spied.save_calls == [True]
    assert spied.sync_calls == 1
    assert spied.resort_calls == 1

    # In-memory state is correct, including the incremental version index.
    cache = await scanner.get_cached_data()
    cached_paths = {item["file_path"] for item in cache.raw_data}
    for stem in ("a", "b", "c"):
        assert (tmp_path / f"{stem}.txt").as_posix() not in cached_paths
        assert (tmp_path / f"{stem}-renamed.txt").as_posix() in cached_paths
    assert cache.version_index[1]["file_path"].endswith("a-renamed.txt")
    assert scanner._hash_index.get_path("hash-a").endswith("a-renamed.txt")


@pytest.mark.asyncio
async def test_deferred_cache_persist_finalizes_despite_cancellation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    path_a = (tmp_path / "a.txt").as_posix()
    scanner, spied = await _make_spied_scanner(
        tmp_path, monkeypatch, [_metadata("a", path_a, "hash-a")]
    )

    scanner.cancel_task()
    async with scanner.defer_cache_persist():
        new_path = (tmp_path / "a-renamed.txt").as_posix()
        await scanner.update_single_model_cache(
            path_a, new_path, _metadata("a-renamed", new_path, "hash-a")
        )

    # Files are already renamed on disk, so the persist must be forced even
    # though the cancellation flag is set.
    assert spied.save_calls == [True]
    assert spied.sync_calls == 1
    assert spied.resort_calls == 1


@pytest.mark.asyncio
async def test_deferred_cache_persist_finalizes_despite_mid_loop_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    path_a = (tmp_path / "a.txt").as_posix()
    scanner, spied = await _make_spied_scanner(
        tmp_path, monkeypatch, [_metadata("a", path_a, "hash-a")]
    )

    with pytest.raises(RuntimeError, match="boom"):
        async with scanner.defer_cache_persist():
            new_path = (tmp_path / "a-renamed.txt").as_posix()
            await scanner.update_single_model_cache(
                path_a, new_path, _metadata("a-renamed", new_path, "hash-a")
            )
            raise RuntimeError("boom")

    assert spied.save_calls == [True]
    assert spied.sync_calls == 1


@pytest.mark.asyncio
async def test_deferred_cache_persist_nested_contexts_finalize_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    path_a = (tmp_path / "a.txt").as_posix()
    scanner, spied = await _make_spied_scanner(
        tmp_path, monkeypatch, [_metadata("a", path_a, "hash-a")]
    )

    async with scanner.defer_cache_persist():
        async with scanner.defer_cache_persist():
            new_path = (tmp_path / "a-renamed.txt").as_posix()
            await scanner.update_single_model_cache(
                path_a, new_path, _metadata("a-renamed", new_path, "hash-a")
            )

    assert spied.save_calls == [True]
    assert spied.resort_calls == 1


@pytest.mark.asyncio
async def test_deferred_cache_persist_without_updates_persists_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    scanner, spied = await _make_spied_scanner(tmp_path, monkeypatch, [])

    async with scanner.defer_cache_persist():
        pass

    assert spied.save_calls == []
    assert spied.resort_calls == 0


# ---------------------------------------------------------------------------
# ModelLifecycleService bulk rename session
# ---------------------------------------------------------------------------


class _SessionScanner:
    model_type = "lora"

    def __init__(self, root: Path):
        self._root = str(root)
        self.cache_updates: List[tuple[str, str]] = []
        self.defer_enters = 0
        self.defer_exits = 0

    def get_model_roots(self) -> List[str]:
        return [self._root]

    @asynccontextmanager
    async def defer_cache_persist(self) -> AsyncIterator[None]:
        self.defer_enters += 1
        try:
            yield
        finally:
            self.defer_exits += 1

    async def update_single_model_cache(
        self, old_path: str, new_path: str, metadata: Dict[str, Any]
    ) -> bool:
        self.cache_updates.append((old_path, new_path))
        return True


class _PassthroughMetadataManager:
    def __init__(self) -> None:
        self.saved: List[str] = []

    async def save_metadata(self, path: str, metadata: Dict[str, Any]) -> bool:
        self.saved.append(path)
        return True


class RecordingRecipeScanner:
    """Records bulk-mode recipe calls and applies filename changes."""

    def __init__(self) -> None:
        self.index_builds = 0
        self.updates: List[Dict[str, Any]] = []
        self.finalizes = 0
        self._recipes: Dict[str, Dict[str, Any]] = {}

    def add_recipe(self, recipe_id: str, lora_hash: str, file_name: str) -> None:
        self._recipes[recipe_id] = {
            "id": recipe_id,
            "loras": [{"hash": lora_hash, "file_name": file_name}],
        }

    async def build_lora_hash_index(self) -> Dict[str, List[Dict[str, Any]]]:
        self.index_builds += 1
        index: Dict[str, List[Dict[str, Any]]] = {}
        for recipe in self._recipes.values():
            for lora in recipe["loras"]:
                index.setdefault(lora["hash"].lower(), []).append(recipe)
        return index

    async def update_lora_filename_by_hash(
        self,
        hash_value: str,
        new_file_name: str,
        *,
        hash_index: Optional[Dict[str, List[Dict[str, Any]]]] = None,
        defer_maintenance: bool = False,
    ) -> tuple[int, int]:
        self.updates.append(
            {
                "hash_value": hash_value,
                "new_file_name": new_file_name,
                "hash_index": hash_index,
                "defer_maintenance": defer_maintenance,
            }
        )
        matched = 0
        for recipe in (self._recipes.values() if hash_index is None else hash_index.get(hash_value.lower(), [])):
            for lora in recipe["loras"]:
                if lora["hash"].lower() == hash_value.lower():
                    lora["file_name"] = new_file_name
                    matched += 1
        return (matched, matched)

    async def finalize_bulk_filename_updates(self) -> None:
        self.finalizes += 1


def _write_model_with_sidecar(
    root: Path, stem: str, sha256: str, model_name: Optional[str] = None
) -> str:
    model_path = root / f"{stem}.safetensors"
    model_path.write_bytes(b"model")
    (root / f"{stem}.metadata.json").write_text(
        json.dumps(
            {
                "file_name": stem,
                "file_path": model_path.as_posix(),
                "model_name": model_name or stem,
                "sha256": sha256,
            }
        )
    )
    return model_path.as_posix()


def _make_lifecycle_service(
    scanner: _SessionScanner, recipe_scanner: RecordingRecipeScanner
) -> ModelLifecycleService:
    async def metadata_loader(path: str) -> Dict[str, Any]:
        with open(path, "r", encoding="utf-8") as handle:
            return json.load(handle)

    async def recipe_scanner_factory() -> RecordingRecipeScanner:
        return recipe_scanner

    return ModelLifecycleService(
        scanner=scanner,  # pyright: ignore[reportArgumentType]
        metadata_manager=_PassthroughMetadataManager(),  # pyright: ignore[reportArgumentType]
        metadata_loader=metadata_loader,
        recipe_scanner_factory=recipe_scanner_factory,
    )


@pytest.mark.asyncio
async def test_bulk_rename_session_defers_and_finalizes_once(tmp_path: Path):
    scanner = _SessionScanner(tmp_path)
    recipe_scanner = RecordingRecipeScanner()
    recipe_scanner.add_recipe("r1", "aa" * 32, "old_a")
    recipe_scanner.add_recipe("r2", "bb" * 32, "old_b")
    service = _make_lifecycle_service(scanner, recipe_scanner)

    path_a = _write_model_with_sidecar(tmp_path, "model-a", "aa" * 32)
    path_b = _write_model_with_sidecar(tmp_path, "model-b", "bb" * 32)

    async with service.bulk_rename_session() as bulk_context:
        await service.rename_model(
            file_path=path_a, new_file_name="renamed-a", bulk_context=bulk_context
        )
        await service.rename_model(
            file_path=path_b, new_file_name="renamed-b", bulk_context=bulk_context
        )
        # No finalize may run before the session ends.
        assert recipe_scanner.finalizes == 0
        assert scanner.defer_enters == 1
        assert scanner.defer_exits == 0

    assert scanner.defer_exits == 1
    # Hash index built at most once for the whole session.
    assert recipe_scanner.index_builds == 1
    assert recipe_scanner.finalizes == 1
    assert len(recipe_scanner.updates) == 2
    for update in recipe_scanner.updates:
        assert update["hash_index"] is not None
        assert update["defer_maintenance"] is True

    # Recipes were re-pointed.
    assert recipe_scanner._recipes["r1"]["loras"][0]["file_name"] == "renamed-a"
    assert recipe_scanner._recipes["r2"]["loras"][0]["file_name"] == "renamed-b"


@pytest.mark.asyncio
async def test_bulk_rename_session_finalizes_recipes_despite_error(tmp_path: Path):
    scanner = _SessionScanner(tmp_path)
    recipe_scanner = RecordingRecipeScanner()
    recipe_scanner.add_recipe("r1", "aa" * 32, "old_a")
    service = _make_lifecycle_service(scanner, recipe_scanner)

    path_a = _write_model_with_sidecar(tmp_path, "model-a", "aa" * 32)

    with pytest.raises(RuntimeError, match="mid-loop"):
        async with service.bulk_rename_session() as bulk_context:
            await service.rename_model(
                file_path=path_a, new_file_name="renamed-a", bulk_context=bulk_context
            )
            raise RuntimeError("mid-loop")

    assert recipe_scanner.finalizes == 1
    assert scanner.defer_exits == 1


@pytest.mark.asyncio
async def test_bulk_rename_session_skips_recipe_finalize_when_untouched(tmp_path: Path):
    scanner = _SessionScanner(tmp_path)
    recipe_scanner = RecordingRecipeScanner()
    recipe_scanner.add_recipe("r1", "cc" * 32, "old_c")
    service = _make_lifecycle_service(scanner, recipe_scanner)

    # Model whose hash matches no recipe: the lookup runs but no recipe is
    # touched, so no recipe maintenance is needed at finalize.
    path_a = _write_model_with_sidecar(tmp_path, "model-a", "aa" * 32)

    async with service.bulk_rename_session() as bulk_context:
        await service.rename_model(
            file_path=path_a, new_file_name="renamed-a", bulk_context=bulk_context
        )

    assert len(recipe_scanner.updates) == 1
    assert recipe_scanner.updates[0]["defer_maintenance"] is True
    assert recipe_scanner.finalizes == 0
    assert recipe_scanner._recipes["r1"]["loras"][0]["file_name"] == "old_c"


@pytest.mark.asyncio
async def test_single_rename_keeps_immediate_recipe_behavior(tmp_path: Path):
    scanner = _SessionScanner(tmp_path)
    recipe_scanner = RecordingRecipeScanner()
    recipe_scanner.add_recipe("r1", "aa" * 32, "old_a")
    service = _make_lifecycle_service(scanner, recipe_scanner)

    path_a = _write_model_with_sidecar(tmp_path, "model-a", "aa" * 32)

    await service.rename_model(file_path=path_a, new_file_name="renamed-a")

    assert len(recipe_scanner.updates) == 1
    update = recipe_scanner.updates[0]
    assert update["hash_index"] is None
    assert update["defer_maintenance"] is False
    assert recipe_scanner.finalizes == 0
    assert recipe_scanner._recipes["r1"]["loras"][0]["file_name"] == "renamed-a"


# ---------------------------------------------------------------------------
# Use case end-to-end: exactly one heavyweight persist for the whole loop
# ---------------------------------------------------------------------------


class _UseCaseScanner(ModelScanner):
    def __init__(self, root: Path):
        self._root = str(root)
        super().__init__(
            model_type="lora",
            model_class=BaseModelMetadata,
            file_extensions={".safetensors"},
        )

    def get_model_roots(self) -> List[str]:
        return [self._root]


class _UseCaseLockProvider:
    def __init__(self) -> None:
        self._lock = asyncio.Lock()

    def is_auto_organize_running(self) -> bool:
        return False

    async def get_auto_organize_lock(self) -> asyncio.Lock:
        return self._lock


def _set_filename_template(template: str, model_type: str = "lora") -> None:
    manager = get_settings_manager()
    templates = dict(manager.settings.get("download_filename_templates") or {})
    templates[model_type] = template
    manager.settings["download_filename_templates"] = templates


@pytest.mark.asyncio
async def test_filename_template_bulk_apply_persists_and_repoints_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    _set_filename_template("{model_name}")

    entries = []
    for index, (stem, model_name, sha) in enumerate(
        (("model-a", "alpha", "aa" * 32), ("model-b", "beta", "bb" * 32))
    ):
        path = _write_model_with_sidecar(tmp_path, stem, sha, model_name=model_name)
        entries.append(_metadata(model_name, path, sha, civitai_id=index + 1))

    scanner = _UseCaseScanner(tmp_path)
    spied = _SpiedCache(scanner, entries)
    scanner._persistent_cache = object()
    monkeypatch.setattr(scanner, "_save_persistent_cache", spied.fake_save)
    monkeypatch.setattr(scanner, "_sync_download_history", spied.fake_sync)
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    monkeypatch.setattr(spied.cache, "resort", spied.resort)

    recipe_scanner = RecordingRecipeScanner()
    recipe_scanner.add_recipe("r1", "aa" * 32, "alpha")
    recipe_scanner.add_recipe("r2", "bb" * 32, "beta")

    service = _make_lifecycle_service(  # type: ignore[arg-type]
        scanner, recipe_scanner  # pyright: ignore[reportArgumentType]
    )
    use_case = FilenameTemplateUseCase(
        scanner=scanner,
        lifecycle_service=service,
        lock_provider=_UseCaseLockProvider(),
        model_type="lora",
    )

    result = await use_case.execute(progress_callback=None)

    assert result.status == "success"
    assert result.success_count == 2

    # One heavyweight persist/resort for the entire bulk operation, not two.
    assert spied.save_calls == [True]
    assert spied.sync_calls == 1
    assert spied.resort_calls == 1

    # Recipes re-pointed via a single lazily built hash index, maintenance
    # finalized once.
    assert recipe_scanner.index_builds == 1
    assert recipe_scanner.finalizes == 1
    assert recipe_scanner._recipes["r1"]["loras"][0]["file_name"] == "alpha"
    assert recipe_scanner._recipes["r2"]["loras"][0]["file_name"] == "beta"

    # Cache reflects the new paths.
    cache = await scanner.get_cached_data()
    cached_paths = {item["file_path"] for item in cache.raw_data}
    assert (tmp_path / "alpha.safetensors").as_posix() in cached_paths
    assert (tmp_path / "beta.safetensors").as_posix() in cached_paths

    # Sidecars moved alongside the model files.
    assert (tmp_path / "alpha.metadata.json").exists()
    assert (tmp_path / "beta.metadata.json").exists()


@pytest.mark.asyncio
async def test_filename_template_bulk_apply_finalizes_persist_on_cancellation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    _set_filename_template("{model_name}")

    entries = []
    paths = []
    for index, (stem, model_name, sha) in enumerate(
        (("model-a", "alpha", "aa" * 32), ("model-b", "beta", "bb" * 32))
    ):
        path = _write_model_with_sidecar(tmp_path, stem, sha, model_name=model_name)
        paths.append(path)
        entries.append(_metadata(model_name, path, sha, civitai_id=index + 1))

    scanner = _UseCaseScanner(tmp_path)
    spied = _SpiedCache(scanner, entries)
    scanner._persistent_cache = object()
    monkeypatch.setattr(scanner, "_save_persistent_cache", spied.fake_save)
    monkeypatch.setattr(scanner, "_sync_download_history", spied.fake_sync)
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    monkeypatch.setattr(spied.cache, "resort", spied.resort)

    service = _make_lifecycle_service(
        scanner,  # pyright: ignore[reportArgumentType]
        RecordingRecipeScanner(),
    )

    original_rename = service.rename_model

    async def cancelling_rename(**kwargs: Any) -> Dict[str, object]:
        result = await original_rename(**kwargs)
        scanner.cancel_task()
        return result

    monkeypatch.setattr(service, "rename_model", cancelling_rename)

    use_case = FilenameTemplateUseCase(
        scanner=scanner,
        lifecycle_service=service,
        lock_provider=_UseCaseLockProvider(),
        model_type="lora",
    )

    result = await use_case.execute(progress_callback=None)

    assert result.status == "cancelled"
    # The one file renamed before cancellation is on disk; the cache must
    # still be persisted exactly once.
    assert spied.save_calls == [True]
    assert spied.sync_calls == 1
    assert spied.resort_calls == 1

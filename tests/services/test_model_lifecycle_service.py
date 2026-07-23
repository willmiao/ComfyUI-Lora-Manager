import asyncio
import json
import os
from pathlib import Path

import pytest

from py.services.model_lifecycle_service import ModelLifecycleService, _require_path_in_library_roots
from py.utils.metadata_manager import MetadataManager
from py.utils.models import LoraMetadata


class ScannerWithRoots:
    def __init__(self, roots):
        self._roots = list(roots)

    def get_model_roots(self):
        return self._roots


class TestRequirePathInLibraryRoots:
    def test_accepts_path_within_root(self, tmp_path):
        root = tmp_path / "loras"
        root.mkdir()
        model = root / "model.safetensors"
        model.write_text("")

        scanner = ScannerWithRoots([str(root)])
        _require_path_in_library_roots(str(model), scanner)

    def test_rejects_path_outside_roots(self, tmp_path):
        root = tmp_path / "loras"
        root.mkdir()
        outside = tmp_path / "outside" / "model.safetensors"
        outside.parent.mkdir(parents=True)
        outside.write_text("")

        scanner = ScannerWithRoots([str(root)])
        with pytest.raises(ValueError, match="outside configured library"):
            _require_path_in_library_roots(str(outside), scanner)

    def test_passes_when_no_roots_configured(self, tmp_path):
        f = tmp_path / "model.safetensors"
        f.write_text("")

        scanner = ScannerWithRoots([])
        _require_path_in_library_roots(str(f), scanner)

    def test_accepts_path_matching_root_exactly(self, tmp_path):
        root = tmp_path / "loras"
        root.mkdir()

        scanner = ScannerWithRoots([str(root)])
        _require_path_in_library_roots(str(root), scanner)

    def test_accepts_symlink_within_root(self, tmp_path):
        """Symlinks under a configured root are legitimate business paths
        and should be accepted — containment works on business-path space,
        not resolved physical paths."""
        root = tmp_path / "loras"
        root.mkdir()

        outside_dir = tmp_path / "outside"
        outside_dir.mkdir()
        outside_file = outside_dir / "escaped.safetensors"
        outside_file.write_text("")

        symlink = root / "link.safetensors"
        symlink.symlink_to(outside_file)

        scanner = ScannerWithRoots([str(root)])
        # Symlink path is under root in business-path space → accepted
        _require_path_in_library_roots(str(symlink), scanner)

    def test_rejects_dot_dot_traversal(self, tmp_path):
        """Verify that ``..`` components are still resolved and blocked —
        ``abspath`` normalises dot-dot but does not resolve symlinks."""
        root = tmp_path / "loras"
        root.mkdir()

        # A path that traverses up out of the root via ..
        escaped = os.path.join(str(root), "..", "..", "etc", "passwd")

        scanner = ScannerWithRoots([str(root)])
        with pytest.raises(ValueError, match="outside configured library"):
            _require_path_in_library_roots(escaped, scanner)


class ScannerForDelete:
    def __init__(self, raw_data, roots, model_type="lora"):
        self.model_type = model_type
        self.cache = DummyCache(raw_data)
        self._hash_index = DummyHashIndex()
        self._roots = list(roots)
        self._persist_calls = []

    def get_model_roots(self):
        return self._roots

    async def get_cached_data(self):
        return self.cache

    async def _persist_current_cache(self):
        self._persist_calls.append(True)


@pytest.mark.asyncio
async def test_delete_model_rejects_path_outside_roots(tmp_path: Path):
    root = tmp_path / "loras"
    root.mkdir()
    model = root / "model.safetensors"
    model.write_bytes(b"data")

    scanner = ScannerForDelete(
        raw_data=[{"file_path": str(model)}],
        roots=[str(root)],
    )
    service = ModelLifecycleService(
        scanner=scanner,
        metadata_manager=DummyMetadataManager({"civitai": {"modelId": 1}}),
        metadata_loader=lambda x: {},
    )
    # Path within root should work (model file exists)
    result = await service.delete_model(str(model))
    assert result["success"] is True

    # Path outside root should be rejected
    outside = tmp_path / "outside.safetensors"
    outside.write_bytes(b"data")
    scanner2 = ScannerForDelete(
        raw_data=[],
        roots=[str(root)],
    )
    service2 = ModelLifecycleService(
        scanner=scanner2,
        metadata_manager=DummyMetadataManager({}),
        metadata_loader=lambda x: {},
    )
    with pytest.raises(ValueError, match="outside configured library"):
        await service2.delete_model(str(outside))


@pytest.mark.asyncio
async def test_rename_model_rejects_path_outside_roots(tmp_path: Path):
    root = tmp_path / "loras"
    root.mkdir()

    scanner = ScannerWithRoots([str(root)])
    service = ModelLifecycleService(
        scanner=scanner,
        metadata_manager=DummyMetadataManager({}),
        metadata_loader=lambda x: {},
    )
    outside = tmp_path / "outside.safetensors"
    outside.write_bytes(b"data")

    with pytest.raises(ValueError, match="outside configured library"):
        await service.rename_model(file_path=str(outside), new_file_name="new_name")


@pytest.mark.asyncio
async def test_bulk_delete_rejects_any_path_outside_roots(tmp_path: Path):
    root = tmp_path / "loras"
    root.mkdir()
    model_ok = root / "model.safetensors"
    model_ok.write_bytes(b"data")
    outside = tmp_path / "outside.safetensors"
    outside.write_bytes(b"data")

    scanner = ScannerWithRoots([str(root)])
    service = ModelLifecycleService(
        scanner=scanner,
        metadata_manager=DummyMetadataManager({}),
        metadata_loader=lambda x: {},
    )
    with pytest.raises(ValueError, match="outside configured library"):
        await service.bulk_delete_models([str(model_ok), str(outside)])


class DummyCache:
    def __init__(self, raw_data):
        self.raw_data = raw_data

    async def resort(self):
        return


class DummyHashIndex:
    def __init__(self):
        self.removed = []

    def remove_by_path(self, path, *args):
        self.removed.append(path)


class VersionAwareScanner:
    def __init__(self, raw_data, model_type="lora"):
        self.model_type = model_type
        self.cache = DummyCache(raw_data)
        self._hash_index = DummyHashIndex()

    async def get_cached_data(self):
        return self.cache

    async def get_model_versions_by_id(self, model_id):
        collected = []
        for item in self.cache.raw_data:
            civitai = item.get("civitai")
            if not isinstance(civitai, dict):
                continue
            candidate = civitai.get("modelId")
            try:
                normalized = int(candidate)
            except (TypeError, ValueError):
                continue
            if normalized != model_id:
                continue
            version_id = civitai.get("id")
            if version_id is None:
                continue
            collected.append({"versionId": version_id})
        return collected


class DummyMetadataManager:
    def __init__(self, payload):
        self._payload = dict(payload)

    async def load_metadata_payload(self, file_path: str):
        return dict(self._payload)


def test_smart_name_uses_sha_matched_uploaded_filename():
    payload = {
        "file_path": "/models/local-name.safetensors",
        "sha256": "a" * 64,
        "civitai": {
            "files": [{
                "name": "RedCraft_FP8_rank128.safetensors",
                "hashes": {"SHA256": "A" * 64},
            }],
        },
    }

    result = ModelLifecycleService._build_smart_name(payload)

    assert result == "RedCraft_FP8_rank128"


def test_smart_name_requires_exact_sha_match():
    payload = {
        "file_path": "/models/current-name.safetensors",
        "sha256": "a" * 64,
        "civitai": {
            "files": [{
                "name": "wrong-file.safetensors",
                "hashes": {"SHA256": "b" * 64},
            }],
        },
    }

    assert ModelLifecycleService._build_smart_name(payload) == "current-name"


def test_smart_name_does_not_append_local_quantization_to_civitai_filename():
    payload = {
        "file_path": "/models/Wan2.2-I2V-A14B-HighNoise-Q8_0.gguf",
        "sha256": "a" * 64,
        "civitai": {
            "files": [{
                "name": "Wan2.2-I2V-A14B-HighNoise.gguf",
                "hashes": {"SHA256": "a" * 64},
            }],
        },
    }

    result = ModelLifecycleService._build_smart_name(payload)

    assert result == "Wan2.2-I2V-A14B-HighNoise"


def test_smart_name_keeps_author_uploaded_characters_but_removes_extension():
    payload = {
        "file_path": "/models/animate-Q8_0.gguf",
        "sha256": "a" * 64,
        "civitai": {
            "files": [{
                "name": "💀 Wan Animate Q8_0.gguf",
                "hashes": {"SHA256": "a" * 64},
            }],
        },
    }

    result = ModelLifecycleService._build_smart_name(payload)

    assert result == "💀 Wan Animate Q8_0"


def test_smart_name_keeps_descriptive_local_name_over_long_marketing_name():
    current = "wan21-lightx2v-i2v-14b-480p-cfg-step-distill-rank128-bf16"
    payload = {
        "file_path": f"/models/{current}.safetensors",
        "sha256": "a" * 64,
        "civitai": {
            "files": [{
                "name": f"{current}.safetensors",
                "hashes": {"SHA256": "a" * 64},
            }],
        },
    }

    assert ModelLifecycleService._build_smart_name(payload) == current


def test_smart_name_keeps_descriptive_name_for_generic_civitai_filename():
    payload = {
        "file_path": "/models/useful-local-name.safetensors",
        "sha256": "a" * 64,
        "civitai": {
            "files": [{
                "name": "lora.safetensors",
                "hashes": {"SHA256": "a" * 64},
            }],
        },
    }

    assert ModelLifecycleService._build_smart_name(payload) == "useful-local-name"


def test_smart_name_keeps_current_when_same_sha_has_multiple_uploaded_names():
    payload = {
        "file_path": "/models/current-name.safetensors",
        "sha256": "a" * 64,
        "civitai": {
            "files": [
                {"name": "first.safetensors", "hashes": {"SHA256": "a" * 64}},
                {"name": "second.safetensors", "hashes": {"SHA256": "a" * 64}},
            ],
        },
    }

    assert ModelLifecycleService._build_smart_name(payload) == "current-name"


def test_smart_name_selects_clear_technical_match_from_same_sha_aliases():
    payload = {
        "file_path": "/models/Wan2.1-I2V-jiggle-tits.safetensors",
        "sha256": "a" * 64,
        "civitai": {
            "files": [
                {
                    "name": "I2V-jiggle_tits.safetensors",
                    "hashes": {"SHA256": "a" * 64},
                },
                {
                    "name": "T2V-jiggle_tits-14b.safetensors",
                    "hashes": {"SHA256": "a" * 64},
                },
            ],
        },
    }

    assert ModelLifecycleService._build_smart_name(payload) == "I2V-jiggle_tits"


def test_ambiguous_match_rejects_conflicting_precision_even_if_name_is_similar():
    selected = ModelLifecycleService._select_ambiguous_uploaded_name(
        "portrait_rank128_fp16",
        ["portrait_rank128_fp8.safetensors", "unrelated_fp16.safetensors"],
    )

    assert selected is None


def test_parse_current_civitai_files_uses_page_name_and_sha():
    sha256 = "89821C3D2094ECA90CDD543FA88CFE33B74855512E14B1D55402CBE3B20DA31A"
    page = (
        '<script>{"id":2352229,"url":"https://example/model.safetensors",'
        '"sizeKB":12021392,"name":"REDZ-v1.5-bf16.safetensors",'
        '"overrideName":null,"type":"Model","modelVersionId":2462789,'
        '"hashes":[{"type":"SHA256","hash":"' + sha256 + '"}]}</script>'
    )

    files = ModelLifecycleService._parse_current_civitai_files(page, 2462789)

    assert files == [{
        "name": "REDZ-v1.5-bf16.safetensors",
        "hashes": {"SHA256": sha256.casefold()},
    }]


def test_parse_current_civitai_files_rejects_other_version():
    page = (
        '{"id":1,"name":"wrong.safetensors","modelVersionId":22,'
        '"hashes":[{"type":"SHA256","hash":"' + "a" * 64 + '"}]}'
    )
    assert ModelLifecycleService._parse_current_civitai_files(page, 11) == []


@pytest.mark.asyncio
async def test_metadata_payload_preserves_raw_civitai_fields(tmp_path: Path):
    model = tmp_path / "example.safetensors"
    model.write_bytes(b"model")
    sidecar = model.with_suffix(".metadata.json")
    sidecar.write_text(json.dumps({
        "file_name": "example",
        "model_name": "Example",
        "file_path": model.as_posix(),
        "size": 5,
        "modified": 1.0,
        "sha256": "a" * 64,
        "base_model": "Unknown",
        "preview_url": "",
        "civitai": {
            "id": 2462789,
            "modelId": 958009,
            "files": [{"name": "official.safetensors"}],
        },
    }), encoding="utf-8")

    payload = await MetadataManager.load_metadata_payload(model.as_posix())

    assert payload["civitai"]["id"] == 2462789
    assert payload["civitai"]["files"][0]["name"] == "official.safetensors"


@pytest.mark.asyncio
async def test_preview_smart_renames_keeps_names_when_upload_names_collide(tmp_path: Path):
    first = tmp_path / "first.safetensors"
    second = tmp_path / "second.safetensors"
    first.write_bytes(b"first")
    second.write_bytes(b"second")
    entries = [
        {
            "file_path": first.as_posix(),
            "file_name": "first",
            "model_name": "Shared Model",
            "sha256": "a" * 64,
            "civitai": {"files": [{
                "name": "shared.safetensors",
                "hashes": {"SHA256": "a" * 64},
            }]},
        },
        {
            "file_path": second.as_posix(),
            "file_name": "second",
            "model_name": "Shared Model",
            "sha256": "b" * 64,
            "civitai": {"files": [{
                "name": "shared.safetensors",
                "hashes": {"SHA256": "b" * 64},
            }]},
        },
    ]
    scanner = VersionAwareScanner(entries)
    manager = DummyMetadataManager({})
    service = ModelLifecycleService(
        scanner=scanner,
        metadata_manager=manager,
        metadata_loader=manager.load_metadata_payload,
    )

    plan = await service.preview_smart_renames()

    assert not [item for item in plan["items"] if item["status"] == "ready"]
    assert all(item["status"] == "unchanged" for item in plan["items"])
    assert all(
        item["reason"] == "duplicate_uploaded_filename" for item in plan["items"]
    )


@pytest.mark.asyncio
async def test_preview_smart_renames_warms_three_at_a_time_and_reports_progress(
    tmp_path: Path,
):
    entries = []
    sha_by_version = {}
    for index in range(5):
        model = tmp_path / f"local-{index}.safetensors"
        model.write_bytes(f"model-{index}".encode())
        sha256 = str(index + 1) * 64
        version_id = 200 + index
        sha_by_version[version_id] = sha256
        entries.append(
            {
                "file_path": model.as_posix(),
                "file_name": f"local-{index}",
                "sha256": sha256,
                "civitai": {"modelId": 100 + index, "id": version_id},
            }
        )

    scanner = VersionAwareScanner(entries)
    manager = DummyMetadataManager({})
    service = ModelLifecycleService(
        scanner=scanner,
        metadata_manager=manager,
        metadata_loader=manager.load_metadata_payload,
    )
    active = 0
    max_active = 0

    async def fetch_files(_model_id, version_id):
        nonlocal active, max_active
        active += 1
        max_active = max(max_active, active)
        await asyncio.sleep(0.02)
        active -= 1
        return [
            {
                "name": f"official-{version_id}.safetensors",
                "hashes": {"SHA256": sha_by_version[version_id]},
            }
        ]

    service._fetch_current_civitai_files = fetch_files
    progress = []

    async def report(payload):
        progress.append(dict(payload))

    plan = await service.preview_smart_renames(progress_callback=report)

    assert max_active == 3
    assert len(plan["items"]) == 5
    assert progress[0] == {"status": "started", "completed": 0, "total": 5}
    assert progress[-1] == {"status": "completed", "completed": 5, "total": 5}
    assert [
        item["completed"] for item in progress if item["status"] == "processing"
    ] == [1, 2, 3, 4, 5]


class DummyUpdateService:
    def __init__(self):
        self.calls = []

    async def update_in_library_versions(self, model_type, model_id, version_ids):
        self.calls.append((model_type, model_id, version_ids))


class DummyScanner:
    def __init__(self):
        self.calls = []
        self.model_type = "checkpoint"

    async def update_single_model_cache(self, old_path, new_path, metadata):
        self.calls.append((old_path, new_path, metadata))


class PassthroughMetadataManager:
    def __init__(self):
        self.saved_payloads = []

    async def save_metadata(self, path: str, metadata):
        self.saved_payloads.append((path, metadata.copy()))
        await MetadataManager.save_metadata(path, metadata)


@pytest.mark.asyncio
async def test_rename_model_preserves_compound_extensions(tmp_path: Path):
    old_name = "Qwen-Image-Edit-2509-Lightning-8steps-V1.0-bf16.0-bf16"
    new_name = f"{old_name}-testing"

    model_path = tmp_path / f"{old_name}.safetensors"
    model_path.write_bytes(b"lora")

    preview_path = tmp_path / f"{old_name}.preview.webp"
    preview_path.write_bytes(b"preview")

    metadata_path = tmp_path / f"{old_name}.metadata.json"
    metadata_payload = {
        "file_name": old_name,
        "file_path": model_path.as_posix(),
        "preview_url": preview_path.as_posix(),
    }
    metadata_path.write_text(json.dumps(metadata_payload))

    async def metadata_loader(path: str):
        with open(path, "r", encoding="utf-8") as handle:
            return json.load(handle)

    scanner = DummyScanner()
    metadata_manager = PassthroughMetadataManager()
    service = ModelLifecycleService(
        scanner=scanner,
        metadata_manager=metadata_manager,
        metadata_loader=metadata_loader,
    )

    result = await service.rename_model(
        file_path=model_path.as_posix(),
        new_file_name=new_name,
    )

    expected_main = tmp_path / f"{new_name}.safetensors"
    expected_metadata = tmp_path / f"{new_name}.metadata.json"
    expected_preview = tmp_path / f"{new_name}.preview.webp"

    assert expected_main.exists()
    assert not model_path.exists()
    assert result["new_file_path"].endswith(f"{new_name}.safetensors")
    assert expected_preview.exists()
    assert not preview_path.exists()

    saved_metadata = json.loads(expected_metadata.read_text())
    assert saved_metadata["file_name"] == new_name
    assert saved_metadata["file_path"].endswith(f"{new_name}.safetensors")
    assert saved_metadata["preview_url"].endswith(f"{new_name}.preview.webp")

    assert scanner.calls
    old_call_path, new_call_path, payload = scanner.calls[0]
    assert old_call_path.endswith(f"{old_name}.safetensors")
    assert new_call_path.endswith(f"{new_name}.safetensors")
    assert payload["file_name"] == new_name


@pytest.mark.asyncio
async def test_rename_model_merges_same_sha_orphan_target_metadata(tmp_path: Path):
    old_name = "friendly-name"
    new_name = "author-upload-name"
    model_path = tmp_path / f"{old_name}.safetensors"
    model_path.write_bytes(b"model")
    source_metadata_path = tmp_path / f"{old_name}.metadata.json"
    source_payload = {
        "file_name": old_name,
        "file_path": model_path.as_posix(),
        "sha256": "a" * 64,
        "size": 5,
        "notes": "",
    }
    source_metadata_path.write_text(json.dumps(source_payload))
    target_metadata_path = tmp_path / f"{new_name}.metadata.json"
    target_metadata_path.write_text(
        json.dumps(
            {
                "file_name": new_name,
                "file_path": (tmp_path / f"{new_name}.safetensors").as_posix(),
                "sha256": "a" * 64,
                "size": 5,
                "notes": "keep this note",
            }
        )
    )

    async def metadata_loader(path: str):
        with open(path, "r", encoding="utf-8") as handle:
            return json.load(handle)

    service = ModelLifecycleService(
        scanner=DummyScanner(),
        metadata_manager=PassthroughMetadataManager(),
        metadata_loader=metadata_loader,
    )

    await service.rename_model(
        file_path=model_path.as_posix(), new_file_name=new_name
    )

    assert not model_path.exists()
    assert not source_metadata_path.exists()
    assert (tmp_path / f"{new_name}.safetensors").exists()
    merged = json.loads(target_metadata_path.read_text())
    assert merged["sha256"] == "a" * 64
    assert merged["notes"] == "keep this note"


@pytest.mark.asyncio
async def test_rename_model_rejects_different_sha_orphan_target_metadata(tmp_path: Path):
    model_path = tmp_path / "old.safetensors"
    model_path.write_bytes(b"model")
    (tmp_path / "old.metadata.json").write_text(
        json.dumps({"sha256": "a" * 64, "file_path": model_path.as_posix()})
    )
    (tmp_path / "new.metadata.json").write_text(
        json.dumps({"sha256": "b" * 64, "file_path": "new.safetensors"})
    )

    async def metadata_loader(path: str):
        with open(path, "r", encoding="utf-8") as handle:
            return json.load(handle)

    service = ModelLifecycleService(
        scanner=DummyScanner(),
        metadata_manager=PassthroughMetadataManager(),
        metadata_loader=metadata_loader,
    )

    with pytest.raises(ValueError, match="Associated target already exists"):
        await service.rename_model(file_path=model_path.as_posix(), new_file_name="new")


@pytest.mark.asyncio
async def test_delete_model_updates_update_service(tmp_path: Path):
    model_path = tmp_path / "sample.safetensors"
    model_path.write_bytes(b"content")

    other_path = tmp_path / "another.safetensors"
    other_path.write_bytes(b"other")

    raw_data = [
        {
            "file_path": model_path.as_posix(),
            "civitai": {"modelId": 42, "id": 1001},
        },
        {
            "file_path": other_path.as_posix(),
            "civitai": {"modelId": 42, "id": 1002},
        },
    ]

    scanner = VersionAwareScanner(raw_data)
    metadata_manager = DummyMetadataManager({"civitai": {"modelId": 42, "id": 1001}})

    async def metadata_loader(path: str):
        return {}

    update_service = DummyUpdateService()
    service = ModelLifecycleService(
        scanner=scanner,
        metadata_manager=metadata_manager,
        metadata_loader=metadata_loader,
        update_service=update_service,
    )

    result = await service.delete_model(model_path.as_posix())

    assert result["success"] is True
    assert not model_path.exists()
    assert update_service.calls == [("lora", 42, [1002])]


@pytest.mark.asyncio
async def test_rename_model_preserves_extension(tmp_path: Path):
    old_name = "model"
    old_extension = ".gguf"
    new_name = "model-renamed"

    model_path = tmp_path / f"{old_name}{old_extension}"
    model_path.write_bytes(b"model")

    preview_path = tmp_path / f"{old_name}.preview.png"
    preview_path.write_bytes(b"preview")

    metadata_path = tmp_path / f"{old_name}.metadata.json"
    metadata_payload = {
        "file_name": old_name,
        "file_path": model_path.as_posix(),
        "preview_url": preview_path.as_posix(),
    }
    metadata_path.write_text(json.dumps(metadata_payload))

    async def metadata_loader(path: str):
        with open(path, "r", encoding="utf-8") as handle:
            return json.load(handle)

    scanner = DummyScanner()
    metadata_manager = PassthroughMetadataManager()
    service = ModelLifecycleService(
        scanner=scanner,
        metadata_manager=metadata_manager,
        metadata_loader=metadata_loader,
    )

    result = await service.rename_model(
        file_path=model_path.as_posix(),
        new_file_name=new_name,
    )

    expected_main = tmp_path / f"{new_name}{old_extension}"
    expected_metadata = tmp_path / f"{new_name}.metadata.json"
    expected_preview = tmp_path / f"{new_name}.preview.png"

    assert expected_main.exists()
    assert not model_path.exists()
    assert result["new_file_path"].endswith(f"{new_name}{old_extension}")
    assert expected_preview.exists()
    assert not preview_path.exists()

    saved_metadata = json.loads(expected_metadata.read_text())
    assert saved_metadata["file_name"] == new_name
    assert saved_metadata["file_path"].endswith(f"{new_name}{old_extension}")
    assert saved_metadata["preview_url"].endswith(f"{new_name}.preview.png")

    assert scanner.calls
    old_call_path, new_call_path, payload = scanner.calls[0]
    assert old_call_path.endswith(f"{old_name}{old_extension}")
    assert new_call_path.endswith(f"{new_name}{old_extension}")
    assert payload["file_name"] == new_name


@pytest.mark.asyncio
async def test_rename_model_with_dotted_basename(tmp_path: Path):
    old_name = "model.v1"
    old_extension = ".gguf"
    new_name = "renamed-model"

    model_path = tmp_path / f"{old_name}{old_extension}"
    model_path.write_bytes(b"content")

    metadata_path = tmp_path / f"{old_name}.metadata.json"
    metadata_payload = {
        "file_name": old_name,
        "file_path": model_path.as_posix(),
    }
    metadata_path.write_text(json.dumps(metadata_payload))

    async def metadata_loader(path: str):
        with open(path, "r", encoding="utf-8") as handle:
            return json.load(handle)

    scanner = DummyScanner()
    metadata_manager = PassthroughMetadataManager()
    service = ModelLifecycleService(
        scanner=scanner,
        metadata_manager=metadata_manager,
        metadata_loader=metadata_loader,
    )

    result = await service.rename_model(
        file_path=model_path.as_posix(),
        new_file_name=new_name,
    )

    expected_main = tmp_path / f"{new_name}{old_extension}"
    assert expected_main.exists()
    assert result["new_file_path"] == expected_main.as_posix()
    assert any(p.endswith(f"{new_name}{old_extension}") for p in result["renamed_files"])

    saved_metadata = json.loads((tmp_path / f"{new_name}.metadata.json").read_text())
    assert saved_metadata["file_name"] == new_name
    assert saved_metadata["file_path"].endswith(f"{new_name}{old_extension}")

@pytest.mark.asyncio
async def test_delete_model_removes_gguf_file(tmp_path: Path):
    model_path = tmp_path / "model.gguf"
    model_path.write_bytes(b"content")

    metadata_path = tmp_path / "model.metadata.json"
    metadata_path.write_text(json.dumps({}))

    preview_path = tmp_path / "model.preview.png"
    preview_path.write_bytes(b"preview")

    raw_data = [
        {
            "file_path": model_path.as_posix(),
            "civitai": {"modelId": 1, "id": 10},
        }
    ]

    scanner = VersionAwareScanner(raw_data)
    metadata_manager = DummyMetadataManager({"civitai": {"modelId": 1, "id": 10}})

    async def metadata_loader(path: str):
        return {}

    service = ModelLifecycleService(
        scanner=scanner,
        metadata_manager=metadata_manager,
        metadata_loader=metadata_loader,
    )

    result = await service.delete_model(model_path.as_posix())

    assert result["success"] is True
    assert not model_path.exists()
    assert not metadata_path.exists()
    assert not preview_path.exists()
    assert any(item.endswith("model.gguf") for item in result["deleted_files"])


# =============================================================================
# Tests for exclude_model functionality
# =============================================================================


@pytest.mark.asyncio
async def test_exclude_model_marks_as_excluded(tmp_path: Path):
    """Verify exclude_model marks model as excluded and updates metadata."""
    model_path = tmp_path / "test_model.safetensors"
    model_path.write_bytes(b"content")

    metadata_path = tmp_path / "test_model.metadata.json"
    metadata_payload = {"file_name": "test_model", "file_path": str(model_path)}
    metadata_path.write_text(json.dumps(metadata_payload))

    raw_data = [
        {
            "file_path": str(model_path),
            "tags": ["tag1", "tag2"],
        }
    ]

    class ExcludeTestScanner:
        def __init__(self, raw_data):
            self.cache = DummyCache(raw_data)
            self.model_type = "lora"
            self._tags_count = {"tag1": 1, "tag2": 1}
            self._hash_index = DummyHashIndex()
            self._excluded_models = []

        async def get_cached_data(self):
            return self.cache

    scanner = ExcludeTestScanner(raw_data)

    saved_metadata = []

    class SavingMetadataManager:
        async def save_metadata(self, path: str, metadata: dict):
            saved_metadata.append((path, metadata.copy()))

    async def metadata_loader(path: str):
        return metadata_payload.copy()

    service = ModelLifecycleService(
        scanner=scanner,
        metadata_manager=SavingMetadataManager(),
        metadata_loader=metadata_loader,
    )

    result = await service.exclude_model(str(model_path))

    assert result["success"] is True
    assert "excluded" in result["message"].lower()
    assert saved_metadata[0][1]["exclude"] is True
    assert str(model_path) in scanner._excluded_models


@pytest.mark.asyncio
async def test_exclude_model_updates_tag_counts(tmp_path: Path):
    """Verify exclude_model decrements tag counts correctly."""
    model_path = tmp_path / "test_model.safetensors"
    model_path.write_bytes(b"content")

    metadata_path = tmp_path / "test_model.metadata.json"
    metadata_path.write_text(json.dumps({}))

    raw_data = [
        {
            "file_path": str(model_path),
            "tags": ["tag1", "tag2"],
        }
    ]

    class TagCountScanner:
        def __init__(self, raw_data):
            self.cache = DummyCache(raw_data)
            self.model_type = "lora"
            self._tags_count = {"tag1": 2, "tag2": 1}
            self._hash_index = DummyHashIndex()
            self._excluded_models = []

        async def get_cached_data(self):
            return self.cache

    scanner = TagCountScanner(raw_data)

    class DummyMetadataManagerLocal:
        async def save_metadata(self, path: str, metadata: dict):
            pass

    async def metadata_loader(path: str):
        return {}

    service = ModelLifecycleService(
        scanner=scanner,
        metadata_manager=DummyMetadataManagerLocal(),
        metadata_loader=metadata_loader,
    )

    await service.exclude_model(str(model_path))

    # tag2 count should become 0 and be removed
    assert "tag2" not in scanner._tags_count
    # tag1 count should decrement to 1
    assert scanner._tags_count["tag1"] == 1


@pytest.mark.asyncio
async def test_exclude_model_empty_path_raises_error():
    """Verify exclude_model raises ValueError for empty path."""
    service = ModelLifecycleService(
        scanner=VersionAwareScanner([]),
        metadata_manager=DummyMetadataManager({}),
        metadata_loader=lambda x: {},
    )

    with pytest.raises(ValueError, match="Model path is required"):
        await service.exclude_model("")


@pytest.mark.asyncio
async def test_unexclude_model_restores_cache_entry(tmp_path: Path):
    """Verify unexclude_model clears exclude metadata and restores cache entry."""
    model_path = tmp_path / "restored_model.safetensors"
    model_path.write_bytes(b"content")

    metadata_payload = {
        "file_name": "restored_model",
        "model_name": "restored_model",
        "file_path": str(model_path),
        "sha256": "abc123",
        "exclude": True,
        "tags": ["tag1"],
    }
    metadata_path = tmp_path / "restored_model.metadata.json"
    metadata_path.write_text(json.dumps(metadata_payload))

    class RestoreScanner:
        def __init__(self):
            self.model_type = "lora"
            self.model_class = LoraMetadata
            self._excluded_models = [str(model_path)]
            self.updated = []

        async def update_single_model_cache(self, old_path, new_path, metadata, recalculate_type=False):
            exclude_value = metadata.get("exclude") if isinstance(metadata, dict) else metadata.exclude
            self.updated.append((old_path, new_path, exclude_value, recalculate_type))

    saved_metadata = []

    class SavingMetadataManager:
        async def save_metadata(self, path: str, metadata: dict):
            saved_metadata.append((path, metadata.copy()))
            await MetadataManager.save_metadata(path, metadata)

    async def metadata_loader(path: str):
        with open(path, "r", encoding="utf-8") as handle:
            return json.load(handle)

    scanner = RestoreScanner()
    service = ModelLifecycleService(
        scanner=scanner,
        metadata_manager=SavingMetadataManager(),
        metadata_loader=metadata_loader,
    )

    result = await service.unexclude_model(str(model_path))

    assert result["success"] is True
    assert "restored" in result["message"].lower()
    assert scanner._excluded_models == []
    assert saved_metadata[0][1]["exclude"] is False
    assert scanner.updated == [
        (str(model_path), str(model_path), False, True)
    ]


# =============================================================================
# Tests for bulk_delete_models functionality
# =============================================================================


@pytest.mark.asyncio
async def test_bulk_delete_models_deletes_multiple_files(tmp_path: Path):
    """Verify bulk_delete_models deletes multiple models via scanner."""
    model1_path = tmp_path / "model1.safetensors"
    model1_path.write_bytes(b"content1")
    model2_path = tmp_path / "model2.safetensors"
    model2_path.write_bytes(b"content2")

    file_paths = [str(model1_path), str(model2_path)]

    class BulkDeleteScanner:
        def __init__(self):
            self.model_type = "lora"
            self.bulk_delete_calls = []

        async def bulk_delete_models(self, paths):
            self.bulk_delete_calls.append(paths)
            return {"success": True, "deleted": paths}

    scanner = BulkDeleteScanner()

    service = ModelLifecycleService(
        scanner=scanner,
        metadata_manager=DummyMetadataManager({}),
        metadata_loader=lambda x: {},
    )

    result = await service.bulk_delete_models(file_paths)

    assert result["success"] is True
    assert len(scanner.bulk_delete_calls) == 1
    assert scanner.bulk_delete_calls[0] == file_paths


@pytest.mark.asyncio
async def test_bulk_delete_models_empty_list_raises_error():
    """Verify bulk_delete_models raises ValueError for empty list."""
    service = ModelLifecycleService(
        scanner=VersionAwareScanner([]),
        metadata_manager=DummyMetadataManager({}),
        metadata_loader=lambda x: {},
    )

    with pytest.raises(ValueError, match="No file paths provided"):
        await service.bulk_delete_models([])


# =============================================================================
# Tests for error paths and edge cases
# =============================================================================


@pytest.mark.asyncio
async def test_delete_model_empty_path_raises_error():
    """Verify delete_model raises ValueError for empty path."""
    service = ModelLifecycleService(
        scanner=VersionAwareScanner([]),
        metadata_manager=DummyMetadataManager({}),
        metadata_loader=lambda x: {},
    )

    with pytest.raises(ValueError, match="Model path is required"):
        await service.delete_model("")


@pytest.mark.asyncio
async def test_rename_model_empty_path_raises_error():
    """Verify rename_model raises ValueError for empty path."""
    service = ModelLifecycleService(
        scanner=DummyScanner(),
        metadata_manager=DummyMetadataManager({}),
        metadata_loader=lambda x: {},
    )

    with pytest.raises(ValueError, match="required"):
        await service.rename_model(file_path="", new_file_name="new_name")


@pytest.mark.asyncio
async def test_rename_model_empty_name_raises_error(tmp_path: Path):
    """Verify rename_model raises ValueError for empty new name."""
    model_path = tmp_path / "model.safetensors"
    model_path.write_bytes(b"content")

    service = ModelLifecycleService(
        scanner=DummyScanner(),
        metadata_manager=DummyMetadataManager({}),
        metadata_loader=lambda x: {},
    )

    with pytest.raises(ValueError, match="required"):
        await service.rename_model(file_path=str(model_path), new_file_name="")


@pytest.mark.asyncio
async def test_rename_model_invalid_characters_raises_error(tmp_path: Path):
    """Verify rename_model raises ValueError for invalid characters."""
    model_path = tmp_path / "model.safetensors"
    model_path.write_bytes(b"content")

    service = ModelLifecycleService(
        scanner=DummyScanner(),
        metadata_manager=DummyMetadataManager({}),
        metadata_loader=lambda x: {},
    )

    invalid_names = [
        "model/name",
        "model\\\\name",
        "model:name",
        "model*name",
        "model?name",
        'model"name',
        "model<name>",
        "model|name",
    ]

    for invalid_name in invalid_names:
        with pytest.raises(ValueError, match="Invalid characters"):
            await service.rename_model(
                file_path=str(model_path), new_file_name=invalid_name
            )


@pytest.mark.asyncio
async def test_rename_model_existing_file_raises_error(tmp_path: Path):
    """Verify rename_model raises ValueError if target exists."""
    old_name = "model"
    new_name = "existing"
    extension = ".safetensors"

    old_path = tmp_path / f"{old_name}{extension}"
    old_path.write_bytes(b"content")

    # Create existing file with target name
    existing_path = tmp_path / f"{new_name}{extension}"
    existing_path.write_bytes(b"existing content")

    service = ModelLifecycleService(
        scanner=DummyScanner(),
        metadata_manager=DummyMetadataManager({}),
        metadata_loader=lambda x: {},
    )

    with pytest.raises(ValueError, match="already exists"):
        await service.rename_model(
            file_path=str(old_path), new_file_name=new_name
        )


# =============================================================================
# Tests for _extract_model_id_from_payload utility
# =============================================================================


@pytest.mark.asyncio
async def test_extract_model_id_from_civitai_payload():
    """Verify model ID extraction from civitai-formatted payload."""
    service = ModelLifecycleService(
        scanner=DummyScanner(),
        metadata_manager=DummyMetadataManager({}),
        metadata_loader=lambda x: {},
    )

    # Test civitai.modelId
    payload1 = {"civitai": {"modelId": 12345}}
    assert service._extract_model_id_from_payload(payload1) == 12345

    # Test civitai.model.id nested
    payload2 = {"civitai": {"model": {"id": 67890}}}
    assert service._extract_model_id_from_payload(payload2) == 67890

    # Test model_id fallback
    payload3 = {"model_id": 11111}
    assert service._extract_model_id_from_payload(payload3) == 11111

    # Test civitai_model_id fallback
    payload4 = {"civitai_model_id": 22222}
    assert service._extract_model_id_from_payload(payload4) == 22222


@pytest.mark.asyncio
async def test_extract_model_id_returns_none_for_invalid_payload():
    """Verify model ID extraction returns None for invalid payloads."""
    service = ModelLifecycleService(
        scanner=DummyScanner(),
        metadata_manager=DummyMetadataManager({}),
        metadata_loader=lambda x: {},
    )

    assert service._extract_model_id_from_payload({}) is None
    assert service._extract_model_id_from_payload(None) is None
    assert service._extract_model_id_from_payload("string") is None
    assert service._extract_model_id_from_payload({"civitai": None}) is None
    assert service._extract_model_id_from_payload({"civitai": {}}) is None


@pytest.mark.asyncio
async def test_extract_model_id_handles_string_values():
    """Verify model ID extraction handles string values."""
    service = ModelLifecycleService(
        scanner=DummyScanner(),
        metadata_manager=DummyMetadataManager({}),
        metadata_loader=lambda x: {},
    )

    payload = {"civitai": {"modelId": "54321"}}
    assert service._extract_model_id_from_payload(payload) == 54321

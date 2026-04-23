import json
import os

import numpy as np
import piexif
from PIL import Image

from py.services.service_registry import ServiceRegistry
from py.nodes.save_image import SaveImageLM


class _DummyTensor:
    def __init__(self, array):
        self._array = array
        self.shape = array.shape

    def cpu(self):
        return self

    def numpy(self):
        return self._array


def _make_image():
    return _DummyTensor(
        np.array(
            [
                [[0.0, 0.1, 0.2], [0.3, 0.4, 0.5]],
                [[0.6, 0.7, 0.8], [0.9, 1.0, 0.0]],
            ],
            dtype="float32",
        )
    )


def _configure_save_paths(monkeypatch, tmp_path):
    monkeypatch.setattr("folder_paths.get_output_directory", lambda: str(tmp_path), raising=False)
    monkeypatch.setattr(
        "folder_paths.get_save_image_path",
        lambda *_args, **_kwargs: (str(tmp_path), "sample", 1, "", "sample"),
        raising=False,
    )


def _configure_metadata(monkeypatch, metadata_dict):
    monkeypatch.setattr("py.nodes.save_image.get_metadata", lambda: {"raw": "metadata"})
    monkeypatch.setattr(
        "py.nodes.save_image.MetadataProcessor.to_dict",
        lambda raw_metadata, node_id: metadata_dict,
    )


def test_save_image_defaults_to_writing_png_metadata(monkeypatch, tmp_path):
    _configure_save_paths(monkeypatch, tmp_path)
    _configure_metadata(monkeypatch, {"prompt": "prompt text", "seed": 123})

    node = SaveImageLM()
    node.save_images([_make_image()], "ComfyUI", "png", id="node-1")

    image_path = tmp_path / "sample_00001_.png"
    with Image.open(image_path) as img:
        assert img.info["parameters"] == "prompt text\nSeed: 123"


def test_save_image_skips_png_parameters_when_metadata_disabled_and_keeps_workflow(
    monkeypatch, tmp_path
):
    _configure_save_paths(monkeypatch, tmp_path)
    _configure_metadata(monkeypatch, {"prompt": "prompt text", "seed": 123})

    node = SaveImageLM()
    workflow = {"nodes": [{"id": 1}]}
    node.save_images(
        [_make_image()],
        "ComfyUI",
        "png",
        id="node-1",
        embed_workflow=True,
        extra_pnginfo={"workflow": workflow},
        save_with_metadata=False,
    )

    image_path = tmp_path / "sample_00001_.png"
    with Image.open(image_path) as img:
        assert "parameters" not in img.info
        assert img.info["workflow"] == json.dumps(workflow)


def test_save_image_skips_jpeg_metadata_when_disabled(monkeypatch, tmp_path):
    _configure_save_paths(monkeypatch, tmp_path)
    _configure_metadata(monkeypatch, {"prompt": "prompt text", "seed": 123})

    node = SaveImageLM()
    node.save_images(
        [_make_image()],
        "ComfyUI",
        "jpeg",
        id="node-1",
        save_with_metadata=False,
    )

    image_path = tmp_path / "sample_00001_.jpg"
    exif_dict = piexif.load(str(image_path))
    assert piexif.ExifIFD.UserComment not in exif_dict.get("Exif", {})


def test_save_image_skips_webp_metadata_when_disabled(monkeypatch, tmp_path):
    _configure_save_paths(monkeypatch, tmp_path)
    _configure_metadata(monkeypatch, {"prompt": "prompt text", "seed": 123})

    node = SaveImageLM()
    node.save_images(
        [_make_image()],
        "ComfyUI",
        "webp",
        id="node-1",
        save_with_metadata=False,
    )

    image_path = tmp_path / "sample_00001_.webp"
    exif_dict = piexif.load(str(image_path))
    assert piexif.ExifIFD.UserComment not in exif_dict.get("Exif", {})


def test_process_image_returns_passthrough_result_and_ui_images(monkeypatch, tmp_path):
    _configure_save_paths(monkeypatch, tmp_path)
    _configure_metadata(monkeypatch, {"prompt": "prompt text", "seed": 123})

    images = [_make_image()]
    node = SaveImageLM()

    result = node.process_image(images, id="node-1")

    assert result["result"] == (images,)
    assert result["ui"] == {
        "images": [{"filename": "sample_00001_.png", "subfolder": "", "type": "output"}]
    }


def test_process_image_returns_empty_ui_images_when_save_fails(monkeypatch, tmp_path):
    _configure_save_paths(monkeypatch, tmp_path)
    _configure_metadata(monkeypatch, {"prompt": "prompt text", "seed": 123})

    def _raise_save_error(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(Image.Image, "save", _raise_save_error)

    images = [_make_image()]
    node = SaveImageLM()

    result = node.process_image(images, id="node-1")

    assert result["result"] == (images,)
    assert result["ui"] == {"images": []}


def test_save_image_does_not_save_recipe_by_default(monkeypatch, tmp_path):
    _configure_save_paths(monkeypatch, tmp_path)
    _configure_metadata(monkeypatch, {"prompt": "prompt text", "seed": 123})

    calls = []
    monkeypatch.setattr(
        SaveImageLM,
        "_save_image_as_recipe",
        lambda self, file_path, metadata_dict: calls.append((file_path, metadata_dict)),
    )

    node = SaveImageLM()
    node.save_images([_make_image()], "ComfyUI", "png", id="node-1")

    assert calls == []


def test_save_image_saves_recipe_when_enabled(monkeypatch, tmp_path):
    _configure_save_paths(monkeypatch, tmp_path)
    metadata_dict = {"prompt": "prompt text", "seed": 123}
    _configure_metadata(monkeypatch, metadata_dict)

    calls = []
    monkeypatch.setattr(
        SaveImageLM,
        "_save_image_as_recipe",
        lambda self, file_path, metadata_dict: calls.append((file_path, metadata_dict)),
    )

    node = SaveImageLM()
    node.save_images(
        [_make_image()],
        "ComfyUI",
        "png",
        id="node-1",
        save_as_recipe=True,
    )

    assert calls == [(str(tmp_path / "sample_00001_.png"), metadata_dict)]


def test_save_image_saves_recipe_for_each_successful_batch_image(monkeypatch, tmp_path):
    monkeypatch.setattr("folder_paths.get_output_directory", lambda: str(tmp_path), raising=False)
    monkeypatch.setattr(
        "folder_paths.get_save_image_path",
        lambda *_args, **_kwargs: (str(tmp_path), "sample", 7, "", "sample"),
        raising=False,
    )
    metadata_dict = {"prompt": "prompt text", "seed": 123}
    _configure_metadata(monkeypatch, metadata_dict)

    calls = []
    monkeypatch.setattr(
        SaveImageLM,
        "_save_image_as_recipe",
        lambda self, file_path, metadata_dict: calls.append((file_path, metadata_dict)),
    )

    node = SaveImageLM()
    node.save_images(
        [_make_image(), _make_image()],
        "ComfyUI",
        "png",
        id="node-1",
        save_as_recipe=True,
    )

    assert calls == [
        (str(tmp_path / "sample_00007_.png"), metadata_dict),
        (str(tmp_path / "sample_00008_.png"), metadata_dict),
    ]


def test_save_image_does_not_save_recipe_when_image_save_fails(monkeypatch, tmp_path):
    _configure_save_paths(monkeypatch, tmp_path)
    _configure_metadata(monkeypatch, {"prompt": "prompt text", "seed": 123})

    def _raise_save_error(*args, **kwargs):
        raise OSError("disk full")

    calls = []
    monkeypatch.setattr(Image.Image, "save", _raise_save_error)
    monkeypatch.setattr(
        SaveImageLM,
        "_save_image_as_recipe",
        lambda self, file_path, metadata_dict: calls.append((file_path, metadata_dict)),
    )

    node = SaveImageLM()
    node.save_images(
        [_make_image()],
        "ComfyUI",
        "png",
        id="node-1",
        save_as_recipe=True,
    )

    assert calls == []


def test_process_image_keeps_image_result_when_recipe_save_fails(monkeypatch, tmp_path):
    _configure_save_paths(monkeypatch, tmp_path)
    _configure_metadata(monkeypatch, {"prompt": "prompt text", "seed": 123})

    def _raise_recipe_error(*args, **kwargs):
        raise RuntimeError("recipe unavailable")

    monkeypatch.setattr(SaveImageLM, "_save_image_as_recipe", _raise_recipe_error)

    images = [_make_image()]
    node = SaveImageLM()

    result = node.process_image(images, id="node-1", save_as_recipe=True)

    assert result["result"] == (images,)
    assert result["ui"] == {
        "images": [{"filename": "sample_00001_.png", "subfolder": "", "type": "output"}]
    }


def test_save_image_as_recipe_writes_recipe_without_async_scanner_calls(
    monkeypatch, tmp_path
):
    _configure_save_paths(monkeypatch, tmp_path)
    source_image = tmp_path / "source.png"
    Image.new("RGB", (16, 16), color=(10, 20, 30)).save(source_image)
    recipes_dir = tmp_path / "recipes"

    class _Cache:
        def __init__(self, raw_data=None):
            self.raw_data = raw_data or []
            self.sorted_by_name = []
            self.sorted_by_date = []
            self.folders = []
            self.folder_tree = {}

    class _ModelScanner:
        def __init__(self, raw_data):
            self._cache = _Cache(raw_data)

    class _PersistentCache:
        def __init__(self):
            self.updates = []

        def update_recipe(self, recipe_data, json_path):
            self.updates.append((recipe_data, json_path))

    class _RecipeScanner:
        def __init__(self):
            self.recipes_dir = str(recipes_dir)
            self._cache = _Cache([])
            self._json_path_map = {}
            self._persistent_cache = _PersistentCache()
            self._lora_scanner = _ModelScanner(
                [
                    {
                        "file_name": "foo",
                        "sha256": "ABC123",
                        "base_model": "SDXL",
                        "civitai": {
                            "id": 456,
                            "name": "Foo v1",
                            "model": {"name": "Foo"},
                        },
                    }
                ]
            )
            self._checkpoint_scanner = _ModelScanner([])
            self.fts_updates = []

        def _update_folder_metadata(self, cache):
            cache.folders = [""]
            cache.folder_tree = {}

        def _update_fts_index_for_recipe(self, recipe_data, operation):
            self.fts_updates.append((recipe_data["id"], operation))

    scanner = _RecipeScanner()
    monkeypatch.setitem(ServiceRegistry._services, "recipe_scanner", scanner)

    node = SaveImageLM()
    node._save_image_as_recipe(
        str(source_image),
        {
            "prompt": "prompt text",
            "seed": 123,
            "checkpoint": "model.safetensors",
            "loras": "<lora:foo:0.7>",
        },
    )

    recipe_files = list(recipes_dir.glob("*.recipe.json"))
    preview_files = list(recipes_dir.glob("*.webp"))

    assert len(recipe_files) == 1
    assert len(preview_files) == 1
    assert len(scanner._cache.raw_data) == 1
    assert len(scanner._persistent_cache.updates) == 1

    recipe = json.loads(recipe_files[0].read_text(encoding="utf-8"))
    assert recipe["file_path"] == os.path.normpath(str(preview_files[0]))
    assert recipe["title"] == "foo-0.70"
    assert recipe["base_model"] == "SDXL"
    assert recipe["loras"][0]["hash"] == "abc123"
    assert recipe["loras"][0]["modelVersionId"] == 456
    assert recipe["gen_params"] == {"prompt": "prompt text", "seed": 123}
    assert scanner._json_path_map[recipe["id"]] == os.path.normpath(str(recipe_files[0]))
    assert scanner.fts_updates == [(recipe["id"], "add")]

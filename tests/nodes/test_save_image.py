import json
import os
from typing import Any, cast

import numpy as np
import piexif  # pyright: ignore[reportMissingTypeStubs]
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
        assert img.info["parameters"] == "prompt text\nSeed: 123, Version: ComfyUI"


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


def test_save_image_does_not_append_loras_to_prompt_by_default(monkeypatch, tmp_path):
    _configure_save_paths(monkeypatch, tmp_path)
    _configure_metadata(
        monkeypatch,
        {"prompt": "prompt text", "seed": 123, "loras": "<lora:foo:0.7>"},
    )

    node = SaveImageLM()
    node.save_images([_make_image()], "ComfyUI", "png", id="node-1")

    image_path = tmp_path / "sample_00001_.png"
    with Image.open(image_path) as img:
        assert "<lora:" not in img.info["parameters"]
        assert img.info["parameters"] == "prompt text\nSeed: 123, Version: ComfyUI"


def test_save_image_appends_loras_to_prompt_when_enabled(monkeypatch, tmp_path):
    _configure_save_paths(monkeypatch, tmp_path)
    _configure_metadata(
        monkeypatch,
        {"prompt": "prompt text", "seed": 123, "loras": "<lora:foo:0.7>"},
    )

    node = SaveImageLM()
    node.save_images(
        [_make_image()], "ComfyUI", "png", id="node-1", add_loras_to_prompt=True
    )

    image_path = tmp_path / "sample_00001_.png"
    with Image.open(image_path) as img:
        assert img.info["parameters"] == (
            "prompt text\n<lora:foo:0.7>\nSeed: 123, Version: ComfyUI"
        )


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
    exif_ifd = exif_dict.get("Exif", {}) or {}
    assert piexif.ExifIFD.UserComment not in exif_ifd


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
    exif_ifd = exif_dict.get("Exif", {}) or {}
    assert piexif.ExifIFD.UserComment not in exif_ifd


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


# ---------------------------------------------------------------------------
# Tests for webp_method and jpeg_subsampling parameters
# ---------------------------------------------------------------------------

def _capture_save_kwargs(monkeypatch):
    """Monkeypatch Image.Image.save to capture kwargs while still saving to disk."""
    real_save = Image.Image.save
    captured_kwargs = {}

    def _fake_save(self, fp, *args, **kwargs):
        captured_kwargs.update(kwargs)
        return real_save(self, fp, *args, **kwargs)

    monkeypatch.setattr(Image.Image, "save", _fake_save)
    return captured_kwargs


def test_webp_method_default_passed_to_pillow_save(monkeypatch, tmp_path):
    _configure_save_paths(monkeypatch, tmp_path)
    _configure_metadata(monkeypatch, {"prompt": "test", "seed": 1})
    captured = _capture_save_kwargs(monkeypatch)

    node = SaveImageLM()
    node.save_images([_make_image()], "ComfyUI", "webp", id="node-1")

    assert "method" in captured
    assert captured["method"] == 6


def test_webp_method_custom_value_passed_to_pillow_save(monkeypatch, tmp_path):
    _configure_save_paths(monkeypatch, tmp_path)
    _configure_metadata(monkeypatch, {"prompt": "test", "seed": 1})
    captured = _capture_save_kwargs(monkeypatch)

    node = SaveImageLM()
    node.save_images(
        [_make_image()], "ComfyUI", "webp", id="node-1", webp_method=3
    )

    assert captured["method"] == 3


def test_jpeg_subsampling_default_passed_to_pillow_save(monkeypatch, tmp_path):
    _configure_save_paths(monkeypatch, tmp_path)
    _configure_metadata(monkeypatch, {"prompt": "test", "seed": 1})
    captured = _capture_save_kwargs(monkeypatch)

    node = SaveImageLM()
    node.save_images([_make_image()], "ComfyUI", "jpeg", id="node-1")

    assert "subsampling" in captured
    assert captured["subsampling"] == 0


def test_jpeg_subsampling_custom_value_passed_to_pillow_save(monkeypatch, tmp_path):
    _configure_save_paths(monkeypatch, tmp_path)
    _configure_metadata(monkeypatch, {"prompt": "test", "seed": 1})
    captured = _capture_save_kwargs(monkeypatch)

    node = SaveImageLM()
    node.save_images(
        [_make_image()], "ComfyUI", "jpeg", id="node-1", jpeg_subsampling=1
    )

    assert captured["subsampling"] == 1


class TestParameterDefaultConsistency:
    """Verify defaults match across INPUT_TYPES, save_images(), and process_image()."""

    def test_webp_method_defaults_are_consistent(self):
        input_types = SaveImageLM.INPUT_TYPES()
        optional = input_types["optional"]

        widget_spec = cast(Any, optional["webp_method"])
        assert widget_spec[1]["default"] == 6
        save_defaults = cast(tuple[Any, ...], SaveImageLM.save_images.__defaults__ or ())
        process_defaults = cast(tuple[Any, ...], SaveImageLM.process_image.__defaults__ or ())
        assert save_defaults[4] == 6  # positional: webp_method=6 is at index 4
        assert process_defaults[6] == 6

    def test_jpeg_subsampling_defaults_are_consistent(self):
        input_types = SaveImageLM.INPUT_TYPES()
        optional = input_types["optional"]

        widget_spec = cast(Any, optional["jpeg_subsampling"])
        assert widget_spec[1]["default"] == 0
        save_defaults = cast(tuple[Any, ...], SaveImageLM.save_images.__defaults__ or ())
        process_defaults = cast(tuple[Any, ...], SaveImageLM.process_image.__defaults__ or ())
        assert save_defaults[5] == 0
        assert process_defaults[7] == 0

    def test_add_loras_to_prompt_defaults_are_consistent(self):
        input_types = SaveImageLM.INPUT_TYPES()
        optional = input_types["optional"]

        widget_spec = cast(Any, optional["add_loras_to_prompt"])
        assert widget_spec[1]["default"] is False
        save_defaults = cast(tuple[Any, ...], SaveImageLM.save_images.__defaults__ or ())
        process_defaults = cast(tuple[Any, ...], SaveImageLM.process_image.__defaults__ or ())
        assert save_defaults[-1] is False
        assert process_defaults[-1] is False


def test_png_does_not_pass_webp_method_or_jpeg_subsampling(monkeypatch, tmp_path):
    _configure_save_paths(monkeypatch, tmp_path)
    _configure_metadata(monkeypatch, {"prompt": "test", "seed": 1})
    captured = _capture_save_kwargs(monkeypatch)

    node = SaveImageLM()
    node.save_images([_make_image()], "ComfyUI", "png", id="node-1")

    assert "method" not in captured
    assert "subsampling" not in captured


def _sample_prompt():
    return {
        "1": {
            "class_type": "CheckpointLoaderSimple",
            "inputs": {"ckpt_name": "DasiwaIl.safetensors"},
            "_meta": {"title": "CheckpointLoaderSimple"},
        },
        "2": {
            "class_type": "LoraLoader",
            "inputs": {"lora_name": "anime_style_v2.safetensors"},
            "_meta": {"title": "Lora"},
        },
    }


def test_resolve_cross_node_placeholders_by_title(monkeypatch, tmp_path):
    _configure_save_paths(monkeypatch, tmp_path)
    _configure_metadata(monkeypatch, {"prompt": "prompt text", "seed": 123})

    captured_prefix = []
    monkeypatch.setattr(
        "folder_paths.get_save_image_path",
        lambda prefix, *_: captured_prefix.append(prefix) or (str(tmp_path), "sample", 1, "", "sample"),
        raising=False,
    )

    node = SaveImageLM()
    node.save_images(
        [_make_image()],
        "samples/%Lora.lora_name%",
        "png",
        id="node-1",
        prompt=_sample_prompt(),
    )

    assert captured_prefix == ["samples/anime_style_v2.safetensors"]


def test_resolve_cross_node_placeholders_falls_back_to_class_type():
    node = SaveImageLM.__new__(SaveImageLM)

    result = node._resolve_cross_node_placeholders(
        "%LoraLoader.lora_name%",
        _sample_prompt(),
    )
    assert result == "anime_style_v2.safetensors"

    result = node._resolve_cross_node_placeholders(
        "%Missing.node%_%Lora.unknown_field%",
        _sample_prompt(),
    )
    assert result == "%Missing.node%_%Lora.unknown_field%"


def test_resolve_cross_node_placeholders_sanitizes_and_skips_linked_inputs():
    node = SaveImageLM.__new__(SaveImageLM)
    prompt = {
        "3": {
            "class_type": "Text",
            "inputs": {
                "text": "a/b\\c:d",
                # Linked inputs carry [origin_node, origin_slot] and must be skipped
                "linked_text": [1, 2],
            },
            "_meta": {"title": "My Text"},
        }
    }

    assert node._resolve_cross_node_placeholders("%My Text.text%", prompt) == "a_b_c_d"
    assert node._resolve_cross_node_placeholders("%My Text.linked_text%", prompt) == (
        "%My Text.linked_text%"
    )


def test_resolve_cross_node_placeholders_strips_percent_from_value():
    """A resolved value must not introduce segments for the later format pass."""
    node = SaveImageLM.__new__(SaveImageLM)
    prompt = {
        "3": {
            "class_type": "Text",
            "inputs": {"text": "100%seed%done"},
            "_meta": {"title": "My Text"},
        }
    }

    resolved = node._resolve_cross_node_placeholders("%My Text.text%", prompt)
    assert resolved == "100_seed_done"
    assert node.format_filename(resolved, {"seed": 123}) == "100_seed_done"


def test_resolve_cross_node_placeholders_prefers_title_over_class_type():
    node = SaveImageLM.__new__(SaveImageLM)
    prompt = {
        # Class-type match comes first in graph order but must lose to the title match.
        "1": {
            "class_type": "LoraLoader",
            "inputs": {"lora_name": "by_class.safetensors"},
            "_meta": {"title": "Style"},
        },
        "2": {
            "class_type": "LoraLoaderModelOnly",
            "inputs": {"lora_name": "by_title.safetensors"},
            "_meta": {"title": "LoraLoader"},
        },
    }

    assert node._resolve_cross_node_placeholders("%LoraLoader.lora_name%", prompt) == (
        "by_title.safetensors"
    )


def test_resolve_cross_node_placeholders_survives_malformed_prompt():
    node = SaveImageLM.__new__(SaveImageLM)

    for prompt in (None, [], "not-a-graph", {"1": "not-a-node"}, {"1": {"inputs": None}}):
        assert node._resolve_cross_node_placeholders("%Lora.lora_name%", prompt) == (
            "%Lora.lora_name%"
        )


def test_save_images_tolerates_placeholder_resolution_failure(monkeypatch, tmp_path):
    """Placeholder resolution must never block the actual save."""
    _configure_save_paths(monkeypatch, tmp_path)
    _configure_metadata(monkeypatch, {"prompt": "prompt text", "seed": 123})

    def _boom(*_args, **_kwargs):
        raise RuntimeError("prompt graph exploded")

    monkeypatch.setattr(SaveImageLM, "_lookup_node_widget_value", _boom)

    captured_prefix = []
    monkeypatch.setattr(
        "folder_paths.get_save_image_path",
        lambda prefix, *_: captured_prefix.append(prefix) or (str(tmp_path), "sample", 1, "", "sample"),
        raising=False,
    )

    node = SaveImageLM()
    result = node.save_images(
        [_make_image()],
        "samples/%Lora.lora_name%",
        "png",
        id="node-1",
        prompt=_sample_prompt(),
    )

    assert captured_prefix == ["samples/%Lora.lora_name%"]
    assert len(result) == 1

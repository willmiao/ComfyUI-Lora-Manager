import json

import numpy as np
import piexif
from PIL import Image

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

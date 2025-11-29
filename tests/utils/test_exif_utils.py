import json

from py.utils.exif_utils import ExifUtils


def test_append_recipe_metadata_includes_checkpoint(monkeypatch, tmp_path):
    captured = {}

    monkeypatch.setattr(
        ExifUtils, "extract_image_metadata", staticmethod(lambda _path: None)
    )

    def fake_update_image_metadata(image_path, metadata):
        captured["path"] = image_path
        captured["metadata"] = metadata
        return image_path

    monkeypatch.setattr(
        ExifUtils, "update_image_metadata", staticmethod(fake_update_image_metadata)
    )

    checkpoint = {
        "type": "checkpoint",
        "modelId": 827184,
        "modelVersionId": 2167369,
        "modelName": "WAI-illustrious-SDXL",
        "modelVersionName": "v15.0",
        "hash": "ABC123",
        "file_name": "WAI-illustrious-SDXL",
        "baseModel": "Illustrious",
    }

    recipe_data = {
        "title": "Semi-realism",
        "base_model": "Illustrious",
        "loras": [],
        "tags": [],
        "checkpoint": checkpoint,
    }

    image_path = tmp_path / "image.webp"
    image_path.write_bytes(b"")

    ExifUtils.append_recipe_metadata(str(image_path), recipe_data)

    assert captured["path"] == str(image_path)
    assert captured["metadata"].startswith("Recipe metadata: ")

    payload = json.loads(captured["metadata"].split("Recipe metadata: ", 1)[1])

    assert payload["checkpoint"] == {
        "type": "checkpoint",
        "modelId": 827184,
        "modelVersionId": 2167369,
        "modelName": "WAI-illustrious-SDXL",
        "modelVersionName": "v15.0",
        "hash": "abc123",
        "file_name": "WAI-illustrious-SDXL",
        "baseModel": "Illustrious",
    }
    assert payload["base_model"] == "Illustrious"

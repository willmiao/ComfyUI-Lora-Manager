import json

import piexif
from PIL import Image, PngImagePlugin

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


def test_optimize_image_preserves_workflow_when_converting_png_to_webp(tmp_path):
    image_path = tmp_path / "source.png"
    png_info = PngImagePlugin.PngInfo()
    png_info.add_text("parameters", "prompt text\nSteps: 20")
    png_info.add_text("workflow", json.dumps({"nodes": [{"id": 1}]}))

    Image.new("RGB", (64, 32), color="red").save(image_path, pnginfo=png_info)

    optimized_data, extension = ExifUtils.optimize_image(
        str(image_path),
        target_width=32,
        format="webp",
        quality=85,
        preserve_metadata=True,
    )

    optimized_path = tmp_path / f"optimized{extension}"
    optimized_path.write_bytes(optimized_data)

    exif_dict = piexif.load(str(optimized_path))
    assert (
        exif_dict["0th"][piexif.ImageIFD.ImageDescription].decode("utf-8")
        == 'Workflow:{"nodes": [{"id": 1}]}'
    )
    user_comment = exif_dict["Exif"][piexif.ExifIFD.UserComment]
    assert user_comment.startswith(b"UNICODE\0")
    assert user_comment[8:].decode("utf-16be") == "prompt text\nSteps: 20"


def test_update_image_metadata_preserves_webp_workflow(tmp_path):
    image_path = tmp_path / "recipe.webp"
    exif_dict = {
        "0th": {
            piexif.ImageIFD.ImageDescription: 'Workflow:{"nodes":[{"id":1}]}',
        },
        "Exif": {
            piexif.ExifIFD.UserComment: b"UNICODE\0"
            + "prompt text".encode("utf-16be")
        },
    }
    Image.new("RGB", (32, 32), color="blue").save(
        image_path, format="WEBP", exif=piexif.dump(exif_dict), quality=85
    )

    ExifUtils.update_image_metadata(
        str(image_path), 'prompt text\nRecipe metadata: {"title":"recipe"}'
    )

    updated_exif = piexif.load(str(image_path))
    assert (
        updated_exif["0th"][piexif.ImageIFD.ImageDescription].decode("utf-8")
        == 'Workflow:{"nodes":[{"id":1}]}'
    )
    updated_comment = updated_exif["Exif"][piexif.ExifIFD.UserComment]
    assert (
        updated_comment[8:].decode("utf-16be")
        == 'prompt text\nRecipe metadata: {"title":"recipe"}'
    )


def test_update_image_metadata_preserves_png_workflow(tmp_path):
    image_path = tmp_path / "recipe.png"
    png_info = PngImagePlugin.PngInfo()
    png_info.add_text("parameters", "prompt text")
    png_info.add_text("workflow", '{"nodes":[{"id":1}]}')
    Image.new("RGB", (32, 32), color="green").save(image_path, pnginfo=png_info)

    ExifUtils.update_image_metadata(
        str(image_path), 'prompt text\nRecipe metadata: {"title":"recipe"}'
    )

    with Image.open(image_path) as img:
        assert img.info["workflow"] == '{"nodes":[{"id":1}]}'
        assert (
            img.info["parameters"]
            == 'prompt text\nRecipe metadata: {"title":"recipe"}'
        )

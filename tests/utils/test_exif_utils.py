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


# --- ISOBMFF / brotli extraction tests ---

import struct

import brotli


def _build_jxl_with_brob(payload_json: dict) -> bytes:
    """Build a minimal JXL container with a brob box containing brotli-compressed JSON."""
    # ISOBMFF box 1: JXL signature box (size=12, type='JXL ', signature)
    box1 = struct.pack(">I", 12) + b"JXL " + bytes([0x0d, 0x0a, 0x87, 0x0a])
    # ISOBMFF box 2: ftyp (size=16, type='ftyp', major='jxl ', minor=0)
    box2 = struct.pack(">I", 16) + b"ftyp" + b"jxl " + struct.pack(">I", 0)
    # ISOBMFF box 3: brob — payload is b'comf' + brotli(json)
    compressed = brotli.compress(json.dumps(payload_json).encode("utf-8"))
    brob_payload = b"comf" + compressed
    box3 = struct.pack(">I", 8 + len(brob_payload)) + b"brob" + brob_payload
    return box1 + box2 + box3


def _build_avif_with_brob(payload_json: dict) -> bytes:
    """Build a minimal AVIF container with a brob box containing brotli-compressed JSON."""
    compressed = brotli.compress(json.dumps(payload_json).encode("utf-8"))
    brob_payload = b"comf" + compressed
    ftyp_box = struct.pack(">I", 20) + b"ftyp" + b"avif" + struct.pack(">I", 0) + b"avif"
    brob_box = struct.pack(">I", 8 + len(brob_payload)) + b"brob" + brob_payload
    return ftyp_box + brob_box


class TestIsobmffBrotliExtraction:
    """Tests for ISOBMFF brotli metadata extraction in ExifUtils."""

    def test_extract_jxl_brotli_happy_path(self, tmp_path):
        """JXL container with valid brob box extracts prompt and workflow."""
        payload = {"prompt": "a cute cat", "workflow": {"nodes": [{"id": 1}]}}
        data = _build_jxl_with_brob(payload)
        path = tmp_path / "test.jxl"
        path.write_bytes(data)

        result = ExifUtils._load_structured_metadata(str(path))

        assert result["prompt"] == "a cute cat"
        assert result["workflow"] == '{"nodes": [{"id": 1}]}'
        assert result["parameters"] is None
        assert result["comment"] is None

    def test_extract_avif_brotli_happy_path(self, tmp_path):
        """AVIF container with valid brob box extracts prompt and workflow."""
        payload = {"prompt": "landscape", "workflow": {"nodes": []}}
        data = _build_avif_with_brob(payload)
        path = tmp_path / "test.avif"
        path.write_bytes(data)

        result = ExifUtils._load_structured_metadata(str(path))

        assert result["prompt"] == "landscape"
        assert result["workflow"] == '{"nodes": []}'

    def test_extract_no_brob_box_returns_none(self, tmp_path):
        """JXL container without a brob box returns None from _extract_isobmff_brotli."""
        # Only JXL signature + ftyp, no brob
        box1 = struct.pack(">I", 12) + b"JXL " + bytes([0x0d, 0x0a, 0x87, 0x0a])
        box2 = struct.pack(">I", 16) + b"ftyp" + b"jxl " + struct.pack(">I", 0)
        path = tmp_path / "test.jxl"
        path.write_bytes(box1 + box2)

        # The low-level extraction should return None (no brob box)
        result = ExifUtils._extract_isobmff_brotli(str(path))
        assert result is None

    def test_extract_corrupt_brob_returns_none(self, tmp_path):
        """Broken brob box payload gracefully returns None."""
        box1 = struct.pack(">I", 12) + b"JXL " + bytes([0x0d, 0x0a, 0x87, 0x0a])
        box2 = struct.pack(">I", 16) + b"ftyp" + b"jxl " + struct.pack(">I", 0)
        # brob with garbage payload that doesn't start with b'comf'
        garbage = b"\xff\xff\xff\xff" * 32
        box3 = struct.pack(">I", 8 + len(garbage)) + b"brob" + garbage
        path = tmp_path / "test.jxl"
        path.write_bytes(box1 + box2 + box3)

        result = ExifUtils._extract_isobmff_brotli(str(path))
        assert result is None

    def test_extract_non_isobmff_file_falls_through(self, tmp_path):
        """A regular PNG file is not processed as ISOBMFF and returns PIL metadata."""
        png_info = PngImagePlugin.PngInfo()
        png_info.add_text("prompt", "from png")
        path = tmp_path / "test.png"
        Image.new("RGB", (4, 4), color="red").save(path, pnginfo=png_info)

        result = ExifUtils._load_structured_metadata(str(path))
        assert result["prompt"] == "from png"

    def test_extract_skip_on_update_and_optimize(self, tmp_path):
        """AVIF/JXL files are skipped for write operations (update/append/optimize)."""
        path = tmp_path / "test.avif"
        path.write_bytes(b"fake avif data")

        # update_image_metadata should return the path unchanged
        result = ExifUtils.update_image_metadata(str(path), "some metadata")
        assert result == str(path)

        # append_recipe_metadata should also skip
        result = ExifUtils.append_recipe_metadata(str(path), {"title": "test"})
        assert result == str(path)

        # optimize_image should passthrough for AVIF/JXL paths
        result_data, ext = ExifUtils.optimize_image(str(path))
        assert ext == ".avif"
        assert result_data == b"fake avif data"

    def test_extract_prompt_as_dict(self, tmp_path):
        """prompt field as dict is JSON-serialized."""
        payload = {"prompt": {"text": "hello", "negative": "bad"}}
        data = _build_jxl_with_brob(payload)
        path = tmp_path / "test.jxl"
        path.write_bytes(data)

        result = ExifUtils._load_structured_metadata(str(path))
        assert json.loads(result["prompt"]) == {"text": "hello", "negative": "bad"}

    def test_extract_workflow_as_list(self, tmp_path):
        """workflow field as list is JSON-serialized."""
        payload = {"workflow": [{"id": 1}, {"id": 2}]}
        data = _build_avif_with_brob(payload)
        path = tmp_path / "test.avif"
        path.write_bytes(data)

        result = ExifUtils._load_structured_metadata(str(path))
        assert json.loads(result["workflow"]) == [{"id": 1}, {"id": 2}]

    def test_over_decompressed_size_limit(self, tmp_path, monkeypatch):
        """Decompressed data exceeding _BROTLI_MAX_DECOMPRESSED is rejected."""
        # Monkey-patch the limit to a small value to avoid large test data
        monkeypatch.setattr(ExifUtils, "_BROTLI_MAX_DECOMPRESSED", 100)

        large_content = "x" * 200
        payload = {"prompt": large_content}
        data = _build_jxl_with_brob(payload)
        path = tmp_path / "test.jxl"
        path.write_bytes(data)

        # Direct extraction should return None because decompressed size exceeds limit
        result = ExifUtils._extract_isobmff_brotli(str(path))
        assert result is None

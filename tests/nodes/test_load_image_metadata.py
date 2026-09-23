import json
import sys
import types
from pathlib import Path

import piexif
import piexif.helper
import pytest
from PIL import Image, PngImagePlugin

from py.nodes.load_image_metadata import LoadImageMetadataLM, MetadataError, resolve_resource
from py.utils.exif_utils import ExifUtils


PARAMETERS = 'cat <lora:style:0.7:0.2>\nNegative prompt: blur\nSteps: 25, Sampler: Euler, Schedule type: Normal, CFG scale: 6.5, Seed: 18446744073709551615, Size: 768x1024, Model: base'


@pytest.fixture
def runtime(tmp_path, monkeypatch):
    import comfy
    import folder_paths
    import nodes

    image_path = tmp_path / "input.png"
    info = PngImagePlugin.PngInfo()
    info.add_text("parameters", PARAMETERS)
    Image.new("RGB", (16, 24)).save(image_path, pnginfo=info)
    model = tmp_path / "base.safetensors"
    lora = tmp_path / "style.safetensors"
    model.touch()
    lora.touch()
    library = ([{"file_path": str(model), "sub_type": "checkpoint"}], [str(tmp_path)], [{"file_path": str(lora)}], [str(tmp_path)])
    monkeypatch.setattr(LoadImageMetadataLM, "_library", staticmethod(lambda: library))
    monkeypatch.setattr(folder_paths, "get_annotated_filepath", lambda name: str(image_path), raising=False)
    monkeypatch.setattr(folder_paths, "exists_annotated_filepath", lambda name: image_path.exists(), raising=False)
    pixels = types.SimpleNamespace(shape=(1, 24, 16, 3))
    mask = object()
    class LoadImage:
        @classmethod
        def INPUT_TYPES(cls):
            return {"required": {"image": (["input.png"], {"image_upload": True})}}

        def load_image(self, name):
            return pixels, mask
    monkeypatch.setattr(nodes, "LoadImage", LoadImage, raising=False)
    samplers = types.ModuleType("comfy.samplers")
    samplers.KSampler = types.SimpleNamespace(SAMPLERS=["euler", "dpmpp_2m"], SCHEDULERS=["normal", "karras"])
    monkeypatch.setitem(sys.modules, "comfy.samplers", samplers)
    monkeypatch.setattr(comfy, "samplers", samplers, raising=False)
    return image_path, library, pixels, mask


def test_full_node_contract_with_real_png_metadata(runtime):
    _, library, pixels, mask = runtime
    result = LoadImageMetadataLM().load_metadata("input.png")
    assert len(result) == len(LoadImageMetadataLM.RETURN_TYPES)
    assert result[:4] == (pixels, mask, "cat", "blur")
    assert result[5] == [(library[2][0]["file_path"], .7, .2)]
    assert result[7:15] == (2**64 - 1, 25, 6.5, "euler", "normal", 768, 1024, 1.0)
    assert "Resolved 1 LoRA" in result[15]
    assert LoadImageMetadataLM.INPUT_TYPES()["required"]["image"][1]["image_upload"]


@pytest.mark.parametrize("extension", ["webp", "jpg"])
def test_exif_parameters_from_real_image(runtime, extension):
    image_path, *_ = runtime
    exif = piexif.dump({"Exif": {piexif.ExifIFD.UserComment: piexif.helper.UserComment.dump(PARAMETERS, encoding="unicode")}})
    alternate = image_path.with_suffix("." + extension)
    Image.new("RGB", (16, 24)).save(alternate, exif=exif)
    fields = ExifUtils._load_structured_metadata(str(alternate))
    assert "Steps: 25" in fields["parameters"]


def test_missing_lora_strict_or_explicit_skip(runtime):
    runtime[1][2].clear()
    strict_result = LoadImageMetadataLM().load_metadata("input.png")
    assert strict_result[5] == []
    assert "LoRA: style | model weight: 0.7 | CLIP weight: 0.2" in strict_result[17]
    result = LoadImageMetadataLM().load_metadata("input.png", missing_settings="use_defaults")
    assert result[5] == []
    assert "Skipped LoRA" in result[15]


def test_overrides_replace_loras_and_preserve_large_seed(runtime):
    result = LoadImageMetadataLM().load_metadata("input.png", overrides_json=json.dumps({"seed": 2**64 - 2, "loras": [], "positive": "changed"}))
    assert result[2] == "changed"
    assert result[5] == []
    assert result[7] == 2**64 - 2


def test_no_metadata_can_be_inspected_with_defaults(runtime):
    Image.new("RGB", (16, 24)).save(runtime[0])
    assert LoadImageMetadataLM().load_metadata("input.png")[12:14] == (1024, 1024)
    result = LoadImageMetadataLM().load_metadata("input.png", missing_settings="use_defaults")
    assert result[12:14] == (1024, 1024)
    assert "No model resolved" in result[15]


def test_graph_without_recognized_latent_falls_back_to_image_size(runtime):
    info = PngImagePlugin.PngInfo()
    graph = {
        "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "base.safetensors"}},
        "2": {"class_type": "CLIPTextEncode", "inputs": {"text": "pos", "clip": ["1", 1]}},
        "3": {"class_type": "CLIPTextEncode", "inputs": {"text": "neg", "clip": ["1", 1]}},
        "5": {"class_type": "KSampler", "inputs": {
            "model": ["1", 0], "positive": ["2", 0], "negative": ["3", 0],
            "latent_image": ["9", 0], "seed": 1, "steps": 20, "cfg": 7,
            "sampler_name": "euler", "scheduler": "normal", "denoise": 1,
        }},
        "9": {"class_type": "VAEEncode", "inputs": {"pixels": ["10", 0], "vae": ["1", 2]}},
    }
    info.add_text("prompt", json.dumps(graph))
    Image.new("RGB", (16, 24)).save(runtime[0], pnginfo=info)
    # The mocked loader returns pixels with shape (1, 24, 16, 3): H=24, W=16.
    result = LoadImageMetadataLM().load_metadata("input.png")
    assert result[12:14] == (16, 24)
    assert "using source image dimension" in result[15]
    assert "❌ ERROR" not in result[16]


def test_parameters_without_size_fall_back_to_image_size(runtime):
    info = PngImagePlugin.PngInfo()
    info.add_text("parameters", PARAMETERS.replace(", Size: 768x1024", ""))
    Image.new("RGB", (16, 24)).save(runtime[0], pnginfo=info)
    result = LoadImageMetadataLM().load_metadata("input.png")
    assert result[12:14] == (16, 24)


def test_size_override_wins_over_image_size_fallback(runtime):
    info = PngImagePlugin.PngInfo()
    info.add_text("parameters", PARAMETERS.replace(", Size: 768x1024", ""))
    Image.new("RGB", (16, 24)).save(runtime[0], pnginfo=info)
    result = LoadImageMetadataLM().load_metadata("input.png", overrides_json='{"width": 512, "height": 640}')
    assert result[12:14] == (512, 640)


@pytest.mark.parametrize("override", [{"seed": -1}, {"steps": 2.5}, {"cfg": float("nan")}, {"sampler_name": "made_up"}, {"positive": ["1", 0]}, {"unknown": 1}])
def test_invalid_override_rejected(runtime, override):
    with pytest.raises((MetadataError, ValueError)):
        LoadImageMetadataLM().load_metadata("input.png", overrides_json=json.dumps(override))


def test_duplicate_basenames_require_path(tmp_path):
    items = []
    for folder in ("a", "b"):
        directory = tmp_path / folder
        directory.mkdir()
        path = directory / "same.safetensors"
        path.touch()
        items.append({"file_path": str(path)})
    with pytest.raises(MetadataError, match="Ambiguous"):
        resolve_resource("same", items, [str(tmp_path)])
    assert resolve_resource("b/same.safetensors", items, [str(tmp_path)]) == items[1]
    assert resolve_resource("b/same", items, [str(tmp_path)]) == items[1]


def test_file_hash_detects_replacement_and_accepts_all_inputs(runtime):
    before = LoadImageMetadataLM.IS_CHANGED("input.png", sampler_node_id="", missing_settings="strict", overrides_json="{}")
    Image.new("RGB", (32, 32)).save(runtime[0])
    assert before != LoadImageMetadataLM.IS_CHANGED("input.png")


def test_comfy_webp_exif_prompt_fields(runtime):
    image_path, *_ = runtime
    graph = {"1": {"class_type": "KSampler", "inputs": {"seed": 42}}}
    exif = piexif.dump({"0th": {
        piexif.ImageIFD.Make: "prompt:" + json.dumps(graph),
        piexif.ImageIFD.Model: 'workflow:{"nodes": []}',
    }})
    alternate = image_path.with_suffix(".webp")
    Image.new("RGB", (16, 24)).save(alternate, exif=exif)
    fields = ExifUtils._load_structured_metadata(str(alternate))
    assert json.loads(fields["prompt"]) == graph
    assert json.loads(fields["workflow"]) == {"nodes": []}



def test_report_preserves_extracted_names_without_catalog(runtime):
    runtime[1][0].clear()
    runtime[1][2].clear()
    result = LoadImageMetadataLM().load_metadata("input.png", missing_settings="use_defaults")
    payload = json.loads(result[15].split("\n\n", 1)[1])
    assert result[4:7] == ("", [], "")
    assert payload["source_resources"]["checkpoint_name"] == "base"
    assert payload["source_resources"]["loras"] == [["style", .7, .2]]


# These user-provided images are optional local integration fixtures, not assets
# required by the public test suite.
_SAMPLE_PNGS = sorted((Path(__file__).resolve().parents[2] / "_tmp").glob("*.png"))
_SAMPLE_PNGS = [path for path in _SAMPLE_PNGS if path.stem.endswith("_")]


@pytest.mark.parametrize("sample", _SAMPLE_PNGS or [pytest.param(None, marks=pytest.mark.skip(reason="No local PNG samples"))], ids=lambda path: path.name if path else "no-samples")
def test_local_png_node_without_catalog(runtime, monkeypatch, sample):
    import comfy.samplers
    import folder_paths

    runtime[1][0].clear()
    runtime[1][2].clear()
    monkeypatch.setattr(folder_paths, "get_annotated_filepath", lambda name: str(sample))
    monkeypatch.setattr(comfy.samplers.KSampler, "SAMPLERS", ["euler", "euler_ancestral", "er_sde"])
    monkeypatch.setattr(comfy.samplers.KSampler, "SCHEDULERS", ["normal", "simple", "sgm_uniform"])
    result = LoadImageMetadataLM().load_metadata(sample.name, missing_settings="use_defaults")
    payload = json.loads(result[15].split("\n\n", 1)[1])
    assert result[2] and result[3]
    assert "<lora:" not in result[2]
    assert result[7] == int(sample.stem.split("_")[-3])
    assert result[4:7] == ("", [], "")
    assert "Default " not in result[15]
    assert "Replaced unsupported" not in result[15]
    assert payload["source_resources"]["checkpoint_name"] in sample.name
    expected_count = 0 if any(name in sample.name for name in ("hyphoria", "pieModelsAnima")) else 1
    assert len(payload["source_resources"]["loras"]) == expected_count


@pytest.mark.parametrize("chunk_type", [b"tEXt", b"zTXt", b"iTXt"])
def test_png_metadata_after_pixel_data_is_read(runtime, chunk_type):
    import struct
    import zlib

    image_path = runtime[0]
    Image.new("RGB", (16, 24)).save(image_path)
    original = image_path.read_bytes()
    encoded = PARAMETERS.encode("utf-8")
    if chunk_type == b"zTXt":
        payload = b"parameters\0\0" + zlib.compress(encoded)
    elif chunk_type == b"iTXt":
        payload = b"parameters\0\0\0\0\0" + encoded
    else:
        payload = b"parameters\0" + encoded
    chunk = (struct.pack(">I", len(payload)) + chunk_type + payload
             + struct.pack(">I", zlib.crc32(chunk_type + payload) & 0xFFFFFFFF))
    # Place metadata immediately before IEND, after all pixel data.
    image_path.write_bytes(original[:-12] + chunk + original[-12:])
    result = LoadImageMetadataLM().load_metadata("input.png")
    assert result[2:4] == ("cat", "blur")
    assert result[4] == "base.safetensors"
    assert result[7] == 2**64 - 1


def test_missing_metadata_report_identifies_actual_file(runtime):
    Image.new("RGB", (16, 24)).save(runtime[0])
    message = LoadImageMetadataLM().load_metadata("input.png")[15]
    assert str(runtime[0]) in message
    assert "Format: PNG" in message
    assert "metadata keys: (none)" in message
    assert "settings were not extracted" in message



def test_readable_report_contains_settings_prompts_and_missing_resources(runtime):
    runtime[1][0].clear()
    runtime[1][2].clear()
    result = LoadImageMetadataLM().load_metadata("input.png", missing_settings="use_defaults")
    readable = result[16]
    assert LoadImageMetadataLM.RETURN_NAMES[16] == "readable_report"
    assert "Checkpoint recorded in image: base" in readable
    assert "No local model resolved." in readable
    assert "Seed: 18446744073709551615" in readable
    assert "Sampler: euler" in readable
    assert "Size: 768 × 1024" in readable
    assert "style (model: 0.7, CLIP: 0.2)" in readable
    assert "Resolved locally: 0 of 1 requested entries." in readable
    assert "POSITIVE PROMPT\ncat" in readable
    assert "NEGATIVE PROMPT\nblur" in readable
    assert "WARNING" in readable
    assert json.loads(result[15].split("\n\n", 1)[1])["seed"] == 2**64 - 1



def test_empty_metadata_starter_respects_overrides_and_indexed_model(runtime):
    Image.new("RGB", (16, 24)).save(runtime[0])
    base = runtime[0].parent / "sd_xl_base_1.0.safetensors"
    base.touch()
    runtime[1][0].append({"file_path": str(base), "sub_type": "checkpoint"})
    result = LoadImageMetadataLM().load_metadata("input.png", overrides_json='{"seed": 123, "positive": "custom prompt", "width": 768}')
    assert result[2] == "custom prompt"
    assert result[4] == base.name
    assert result[7] == 123
    assert result[12:14] == (768, 1024)
    assert result[5] == []


def test_user_example_png_runs_with_saved_strict_setting(runtime, monkeypatch):
    import folder_paths

    path = Path(__file__).resolve().parents[2] / "_tmp" / "example.png"
    if not path.exists():
        pytest.skip("No local example.png fixture")
    monkeypatch.setattr(folder_paths, "get_annotated_filepath", lambda name: str(path))
    assert not any(ExifUtils._load_structured_metadata(str(path)).values())
    runtime[1][0].clear()
    runtime[1][2].clear()
    result = LoadImageMetadataLM().load_metadata("example.png", missing_settings="strict")
    assert "glass bottle" in result[2]
    assert result[3] == "text, watermark"
    assert result[4:7] == ("", [], "")
    assert result[7:15] == (0, 20, 7.0, "euler", "normal", 1024, 1024, 1.0)
    assert "starter preset" in result[16]



def test_missing_files_includes_model_and_lora_in_strict_mode(runtime):
    runtime[1][0].clear()
    runtime[1][2].clear()
    result = LoadImageMetadataLM().load_metadata("input.png", missing_settings="strict")
    assert result[4:7] == ("", [], "")
    assert "Model: base" in result[17]
    assert "LoRA: style | model weight: 0.7 | CLIP weight: 0.2" in result[17]
    assert LoadImageMetadataLM.RETURN_NAMES[17] == "missing_files"


def test_missing_files_keeps_valid_stack_entries(runtime):
    result = LoadImageMetadataLM().load_metadata("input.png", overrides_json=json.dumps({"loras": [["style", .7, .2], ["missing", -.5, 0]]}))
    assert result[5] == [(runtime[1][2][0]["file_path"], .7, .2)]
    assert "LoRA: missing | model weight: -0.5 | CLIP weight: 0" in result[17]
    assert "LoRA: style" not in result[17]
    assert LoadImageMetadataLM().load_metadata("input.png")[17] == ""


@pytest.mark.parametrize("subtype", ["checkpoint", "diffusion_model"])
def test_generic_model_name_resolves_both_model_categories(runtime, subtype):
    runtime[1][0][0]["sub_type"] = subtype
    result = LoadImageMetadataLM().load_metadata("input.png")
    assert result[4] == "base.safetensors"
    assert result[17] == ""
    assert subtype in result[16]
    assert LoadImageMetadataLM.RETURN_NAMES[4:7] == ("model_name", "lora_stack", "lora_stack_text")
    assert result[6] == f"{runtime[1][2][0]['file_path']} | model weight: 0.7 | CLIP weight: 0.2"


def test_duplicate_model_names_across_categories_require_path(runtime):
    directory = runtime[0].parent / "unet"
    directory.mkdir()
    model = directory / "base.safetensors"
    model.touch()
    runtime[1][0].append({"file_path": str(model), "sub_type": "diffusion_model"})
    # The exact root-relative name wins when present.
    result = LoadImageMetadataLM().load_metadata("input.png", overrides_json='{"model_name":"unet/base.safetensors"}')
    assert result[4] == "unet/base.safetensors"
    result = LoadImageMetadataLM().load_metadata("input.png", overrides_json='{"model_name":"old/base.safetensors"}')
    assert result[4] == ""
    assert "Ambiguous" in result[17]


@pytest.mark.parametrize("key", ["model_name", "checkpoint_name", "unet_name"])
def test_model_override_aliases(runtime, key):
    runtime[1][0][0]["sub_type"] = "diffusion_model"
    result = LoadImageMetadataLM().load_metadata("input.png", overrides_json=json.dumps({key: "base.safetensors"}))
    assert result[4] == "base.safetensors"


@pytest.mark.parametrize("policy", ["strict", "use_defaults"])
def test_unsupported_sampler_returns_defaults_and_error(runtime, policy):
    info = PngImagePlugin.PngInfo()
    info.add_text("prompt", json.dumps({"1": {"class_type": "CustomSampler", "inputs": {}}}))
    Image.new("RGB", (16, 24)).save(runtime[0], pnginfo=info)
    result = LoadImageMetadataLM().load_metadata("input.png", missing_settings=policy)
    assert result[7:15] == (0, 20, 7.0, "euler", "normal", 1024, 1024, 1.0)
    assert "glass bottle" in result[2]
    assert result[5] == []
    assert "❌ ERROR" in result[16]
    assert "supported sampler IDs: none" in result[16]
    assert "⚙️ SAMPLING" in result[16]


def test_unsupported_graph_uses_valid_parameters_before_defaults(runtime):
    info = PngImagePlugin.PngInfo()
    info.add_text("prompt", json.dumps({"1": {"class_type": "CustomSampler", "inputs": {}}}))
    info.add_text("parameters", PARAMETERS)
    Image.new("RGB", (16, 24)).save(runtime[0], pnginfo=info)
    result = LoadImageMetadataLM().load_metadata("input.png", missing_settings="strict", prefer_saved_image_metadata=False)
    assert result[2] == "cat"
    assert result[7] == 2**64 - 1
    assert result[8] == 25
    assert "recovered saved generation parameters" in result[16]
    assert "❌ ERROR" in result[16]


def test_invalid_extracted_number_preserves_other_settings(runtime):
    info = PngImagePlugin.PngInfo()
    info.add_text("parameters", PARAMETERS.replace("CFG scale: 6.5", "CFG scale: nan"))
    Image.new("RGB", (16, 24)).save(runtime[0], pnginfo=info)
    result = LoadImageMetadataLM().load_metadata("input.png")
    assert result[9] == 7.0
    assert result[8] == 25
    assert "ERROR: Invalid cfg" in result[16]



def test_actual_custom_sampler_png_uses_saved_parameters(runtime, monkeypatch):
    import comfy.samplers
    import folder_paths

    path = Path(__file__).resolve().parents[2] / "_tmp" / "20260613-122517_S4_unnamedaANIMA_v10_617459040116303.png"
    if not path.exists():
        pytest.skip("No local custom sampler PNG")
    monkeypatch.setattr(folder_paths, "get_annotated_filepath", lambda name: str(path))
    monkeypatch.setattr(comfy.samplers.KSampler, "SAMPLERS", ["euler", "er_sde"])
    monkeypatch.setattr(comfy.samplers.KSampler, "SCHEDULERS", ["normal", "simple"])
    result = LoadImageMetadataLM().load_metadata(path.name, missing_settings="strict", prefer_saved_image_metadata=False)
    assert result[7:15] == (617459040116303, 30, 4.0, "er_sde", "simple", 1664, 1088, 1.0)
    assert result[2]
    assert "❌ ERROR" in result[16]
    assert "recovered saved generation parameters" in result[16]


@pytest.mark.parametrize("selector", ["1481:1783", "1481/1783", "1481", "1783"])
def test_actual_png_subgraph_sampler_selection(runtime, monkeypatch, selector):
    import comfy.samplers
    import folder_paths

    path = Path(__file__).resolve().parents[2] / "_tmp" / "20260613-122517_S4_unnamedaANIMA_v10_617459040116303.png"
    if not path.exists():
        pytest.skip("No local custom sampler PNG")
    monkeypatch.setattr(folder_paths, "get_annotated_filepath", lambda name: str(path))
    monkeypatch.setattr(comfy.samplers.KSampler, "SAMPLERS", ["euler", "er_sde"])
    monkeypatch.setattr(comfy.samplers.KSampler, "SCHEDULERS", ["normal", "simple"])
    result = LoadImageMetadataLM().load_metadata(path.name, sampler_node_id=selector, prefer_saved_image_metadata=False)
    assert result[7:12] == (617459040116303, 30, 4.0, "er_sde", "simple")
    assert "sampler 1481:1783" in result[16]
    assert "Detail Daemon" in result[16]
    assert "recovered saved generation parameters" not in result[16]


def test_source_preference_flag_defaults_true(runtime):
    assert LoadImageMetadataLM.INPUT_TYPES()["required"]["prefer_saved_image_metadata"][1]["default"] is True
    info = PngImagePlugin.PngInfo()
    info.add_text("parameters", PARAMETERS)
    info.add_text("prompt", json.dumps({"1": {"class_type": "CustomSampler", "inputs": {}}}))
    Image.new("RGB", (16, 24)).save(runtime[0], pnginfo=info)
    result = LoadImageMetadataLM().load_metadata("input.png")
    assert result[7] == 2**64 - 1
    assert "saved image generation parameters (preferred)" in result[16]
    assert "❌ ERROR" not in result[16]



@pytest.mark.parametrize("name", ["Kroma.v2.1", "Kroma.v2.1.safetensors", " Kroma.v2.1 "])
def test_model_resolution_preserves_dotted_extensionless_names(tmp_path, name):
    directory = tmp_path / "Krea 2"
    directory.mkdir()
    path = directory / "Kroma.v2.1.safetensors"
    path.touch()
    item = {"file_path": str(path)}
    assert resolve_resource(name, [item], [str(tmp_path)]) == item


def test_model_resolution_accepts_unique_catalog_model_name(tmp_path):
    path = tmp_path / "local-renamed.safetensors"
    path.touch()
    item = {"file_path": str(path), "model_name": "Kroma catalog name"}
    assert resolve_resource("Kroma catalog name", [item], [str(tmp_path)]) == item


def test_catalog_alias_ambiguity_and_stale_entries(tmp_path):
    items = []
    for name in ("a", "b"):
        path = tmp_path / (name + ".safetensors")
        path.touch()
        items.append({"file_path": str(path), "model_name": "Kroma"})
    with pytest.raises(MetadataError, match="Ambiguous"):
        resolve_resource("Kroma", items, [str(tmp_path)])
    items.append({"file_path": str(tmp_path / "absent.safetensors"), "model_name": "missing"})
    with pytest.raises(MetadataError, match="could not be matched"):
        resolve_resource("missing", items, [str(tmp_path)])
    assert resolve_resource("a.safetensors", items, [str(tmp_path)]) == items[0]

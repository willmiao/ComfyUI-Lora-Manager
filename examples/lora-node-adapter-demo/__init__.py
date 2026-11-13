from __future__ import annotations

import re

import comfy.sd  # pyright: ignore[reportMissingImports]
import comfy.utils  # pyright: ignore[reportMissingImports]
import folder_paths  # pyright: ignore[reportMissingImports]


NUMBER_PATTERN = r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)"
LORA_PATTERN = re.compile(
    rf"<lora:([^>]+?):({NUMBER_PATTERN})(?::({NUMBER_PATTERN}))?>",
    re.IGNORECASE,
)


class LoraNodeAdapterDemoLoader:
    NAME = "LoRA Adapter Demo Loader"
    CATEGORY = "Third Party Examples"
    DESCRIPTION = "Minimal third-party LoRA loader demonstrating the LoRA Manager adapter API."

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "model": ("MODEL",),
                "text": (
                    "STRING",
                    {
                        "default": "",
                        "multiline": True,
                        "tooltip": "Format: <lora:name:model_strength[:clip_strength]>",
                    },
                ),
            },
            "optional": {"clip": ("CLIP",)},
        }

    RETURN_TYPES = ("MODEL", "CLIP", "STRING")
    RETURN_NAMES = ("MODEL", "CLIP", "loaded_loras")
    FUNCTION = "load_loras"

    def load_loras(self, model, text: str, clip=None):
        loaded_loras = []
        for match in LORA_PATTERN.finditer(text):
            name = match.group(1)
            model_strength = float(match.group(2))
            clip_strength = (
                float(match.group(3)) if match.group(3) else model_strength
            )
            lora_path = folder_paths.get_full_path("loras", name)
            if lora_path is None:
                raise FileNotFoundError(f"LoRA not found: {name}")

            lora = comfy.utils.load_torch_file(lora_path, safe_load=True)
            model, clip = comfy.sd.load_lora_for_models(
                model,
                clip,
                lora,
                model_strength,
                clip_strength,
            )
            loaded_loras.append(match.group(0))

        return model, clip, " ".join(loaded_loras)


NODE_CLASS_MAPPINGS = {LoraNodeAdapterDemoLoader.NAME: LoraNodeAdapterDemoLoader}
WEB_DIRECTORY = "./web"

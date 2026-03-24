import os
import json
import folder_paths
import torch
import numpy as np
from PIL import Image


class RecipeBrowserLM:
    NAME = "Recipe Browser (LoraManager)"
    CATEGORY = "Lora Manager/recipes"
    DESCRIPTION = "Browse recipes and output prompt, image, and LoRA stack."

    RETURN_TYPES = (
        "IMAGE",
        "STRING",
        "STRING",
        "INT",
        "STRING",
        "FLOAT",
        "INT",
        "LORA_STACK",
    )

    RETURN_NAMES = (
        "image",
        "prompt",
        "negative_prompt",
        "steps",
        "sampler",
        "cfg_scale",
        "seed",
        "lora_stack",
    )

    FUNCTION = "run"

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "recipe_id": ("STRING", {"default": ""}),
            }
        }

    def run(self, recipe_id):
        recipe_id = (recipe_id or "").strip()

        if not recipe_id:
            return self.empty_result()

        recipe_path = self.get_recipe_path(recipe_id)

        if not os.path.exists(recipe_path):
            print(f"[RecipeBrowserLM] Missing recipe: {recipe_path}")
            return self.empty_result()

        try:
            with open(recipe_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            print(f"[RecipeBrowserLM] Failed to read recipe '{recipe_path}': {e}")
            return self.empty_result()

        gen = data.get("gen_params", {}) or {}

        image = self.load_image(data.get("file_path"))
        prompt = self.safe_str(gen.get("prompt", ""))
        negative = self.safe_str(gen.get("negative_prompt", ""))
        steps = self.safe_int(gen.get("steps", 20), 20)
        sampler = self.safe_str(gen.get("sampler", "euler"))
        cfg = self.safe_float(gen.get("cfg_scale", 7.0), 7.0)
        seed = self.safe_int(gen.get("seed", 0), 0)
        lora_stack = self.build_lora_stack(data.get("loras", []))

        return (
            image,
            prompt,
            negative,
            steps,
            sampler,
            cfg,
            seed,
            lora_stack,
        )

    def empty_result(self):
        return (
            self.create_placeholder_image(),
            "",
            "",
            0,
            "",
            0.0,
            0,
            [],
        )

    def get_recipe_path(self, recipe_id):
        base = os.path.join(folder_paths.models_dir, "loras", "recipes")
        return os.path.join(base, f"{recipe_id}.recipe.json")

    def load_image(self, path):
        if not path or not os.path.exists(path):
            return self.create_placeholder_image()

        try:
            img = Image.open(path).convert("RGB")
            arr = np.array(img).astype(np.float32) / 255.0
            return torch.from_numpy(arr)[None,]
        except Exception as e:
            print(f"[RecipeBrowserLM] Failed to load image '{path}': {e}")
            return self.create_placeholder_image()

    def create_placeholder_image(self, width=64, height=64):
        arr = np.zeros((height, width, 3), dtype=np.float32)
        return torch.from_numpy(arr)[None,]

    def build_lora_stack(self, loras):
        """
        Convert recipe loras -> ComfyUI LORA_STACK format:
        [(path, model_strength, clip_strength)]
        """
        stack = []

        if not isinstance(loras, list):
            return stack

        for lora in loras:
            if not isinstance(lora, dict):
                continue

            if lora.get("exclude"):
                continue

            file_name = self.safe_str(lora.get("file_name", "")).strip()
            if not file_name:
                continue

            strength = self.safe_float(lora.get("strength", 1.0), 1.0)
            lora_path = self.resolve_lora_path(file_name)

            if not lora_path:
                print(f"[RecipeBrowserLM] Could not resolve LoRA: {file_name}")
                continue

            stack.append((lora_path, strength, strength))

        return stack

    def resolve_lora_path(self, file_name):
        """
        Resolve actual LoRA file path using ComfyUI folder_paths.
        Tries exact stem match first, then substring fallback.
        """
        try:
            all_loras = folder_paths.get_filename_list("loras")
        except Exception as e:
            print(f"[RecipeBrowserLM] Error reading LoRA list: {e}")
            return None

        normalized_target = self.normalize_name(file_name)

        # Pass 1: exact normalized basename/stem match
        for lora_path in all_loras:
            base_name = os.path.basename(lora_path)
            stem, _ext = os.path.splitext(base_name)

            if self.normalize_name(base_name) == normalized_target:
                return lora_path
            if self.normalize_name(stem) == normalized_target:
                return lora_path

        # Pass 2: normalized substring fallback
        for lora_path in all_loras:
            base_name = os.path.basename(lora_path)
            stem, _ext = os.path.splitext(base_name)

            norm_base = self.normalize_name(base_name)
            norm_stem = self.normalize_name(stem)

            if normalized_target in norm_base or normalized_target in norm_stem:
                return lora_path

        return None

    def normalize_name(self, value):
        value = self.safe_str(value).strip().lower()
        return value.replace("\\", "/")

    def safe_str(self, value, default=""):
        if value is None:
            return default
        return str(value)

    def safe_int(self, value, default=0):
        try:
            return int(value)
        except Exception:
            try:
                return int(float(value))
            except Exception:
                return default

    def safe_float(self, value, default=0.0):
        try:
            return float(value)
        except Exception:
            return default
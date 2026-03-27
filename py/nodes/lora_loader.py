import logging
import re

import comfy.sd  # type: ignore
import comfy.utils  # type: ignore

from ..utils.utils import get_lora_info_absolute
from .nunchaku_qwen import nunchaku_load_qwen_loras
from .utils import (
    FlexibleOptionalInputType,
    any_type,
    detect_nunchaku_model_kind,
    extract_lora_name,
    get_loras_list,
    nunchaku_load_lora,
)

logger = logging.getLogger(__name__)


def _collect_stack_entries(lora_stack):
    entries = []
    if not lora_stack:
        return entries

    for lora_path, model_strength, clip_strength in lora_stack:
        lora_name = extract_lora_name(lora_path)
        absolute_lora_path, trigger_words = get_lora_info_absolute(lora_name)
        entries.append({
            "name": lora_name,
            "absolute_path": absolute_lora_path,
            "input_path": lora_path,
            "model_strength": float(model_strength),
            "clip_strength": float(clip_strength),
            "trigger_words": trigger_words,
        })
    return entries


def _collect_widget_entries(kwargs):
    entries = []
    for lora in get_loras_list(kwargs):
        if not lora.get("active", False):
            continue
        lora_name = lora["name"]
        model_strength = float(lora["strength"])
        clip_strength = float(lora.get("clipStrength", model_strength))
        lora_path, trigger_words = get_lora_info_absolute(lora_name)
        entries.append({
            "name": lora_name,
            "absolute_path": lora_path,
            "input_path": lora_path,
            "model_strength": model_strength,
            "clip_strength": clip_strength,
            "trigger_words": trigger_words,
        })
    return entries


def _format_loaded_loras(loaded_loras):
    formatted_loras = []
    for item in loaded_loras:
        if item["include_clip_strength"]:
            formatted_loras.append(
                f"<lora:{item['name']}:{item['model_strength']}:{item['clip_strength']}>"
            )
        else:
            formatted_loras.append(f"<lora:{item['name']}:{item['model_strength']}>")
    return " ".join(formatted_loras)


def _apply_entries(model, clip, lora_entries, nunchaku_model_kind):
    loaded_loras = []
    all_trigger_words = []

    if nunchaku_model_kind == "qwen_image":
        qwen_lora_configs = []
        for entry in lora_entries:
            qwen_lora_configs.append((entry["absolute_path"], entry["model_strength"]))
            loaded_loras.append({
                "name": entry["name"],
                "model_strength": entry["model_strength"],
                "clip_strength": entry["model_strength"],
                "include_clip_strength": False,
            })
            all_trigger_words.extend(entry["trigger_words"])
        if qwen_lora_configs:
            model = nunchaku_load_qwen_loras(model, qwen_lora_configs)
        return model, clip, loaded_loras, all_trigger_words

    for entry in lora_entries:
        if nunchaku_model_kind == "flux":
            model = nunchaku_load_lora(model, entry["input_path"], entry["model_strength"])
        else:
            lora = comfy.utils.load_torch_file(entry["absolute_path"], safe_load=True)
            model, clip = comfy.sd.load_lora_for_models(
                model,
                clip,
                lora,
                entry["model_strength"],
                entry["clip_strength"],
            )

        include_clip_strength = nunchaku_model_kind is None and abs(entry["model_strength"] - entry["clip_strength"]) > 0.001
        loaded_loras.append({
            "name": entry["name"],
            "model_strength": entry["model_strength"],
            "clip_strength": entry["clip_strength"],
            "include_clip_strength": include_clip_strength,
        })
        all_trigger_words.extend(entry["trigger_words"])

    return model, clip, loaded_loras, all_trigger_words


class LoraLoaderLM:
    NAME = "Lora Loader (LoraManager)"
    CATEGORY = "Lora Manager/loaders"

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "model": ("MODEL",),
                "text": ("AUTOCOMPLETE_TEXT_LORAS", {
                    "placeholder": "Search LoRAs to add...",
                    "tooltip": "Format: <lora:lora_name:strength> separated by spaces or punctuation",
                }),
            },
            "optional": FlexibleOptionalInputType(any_type),
        }

    RETURN_TYPES = ("MODEL", "CLIP", "STRING", "STRING")
    RETURN_NAMES = ("MODEL", "CLIP", "trigger_words", "loaded_loras")
    FUNCTION = "load_loras"

    def load_loras(self, model, text, **kwargs):
        """Loads multiple LoRAs based on the kwargs input and lora_stack."""
        del text
        clip = kwargs.get("clip", None)
        lora_entries = _collect_stack_entries(kwargs.get("lora_stack", None))
        lora_entries.extend(_collect_widget_entries(kwargs))

        nunchaku_model_kind = detect_nunchaku_model_kind(model)
        if nunchaku_model_kind == "flux":
            logger.info("Detected Nunchaku Flux model")
        elif nunchaku_model_kind == "qwen_image":
            logger.info("Detected Nunchaku Qwen-Image model")

        model, clip, loaded_loras, all_trigger_words = _apply_entries(model, clip, lora_entries, nunchaku_model_kind)
        trigger_words_text = ",, ".join(all_trigger_words) if all_trigger_words else ""
        formatted_loras_text = _format_loaded_loras(loaded_loras)
        return (model, clip, trigger_words_text, formatted_loras_text)


class LoraTextLoaderLM:
    NAME = "LoRA Text Loader (LoraManager)"
    CATEGORY = "Lora Manager/loaders"

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "model": ("MODEL",),
                "lora_syntax": ("STRING", {
                    "forceInput": True,
                    "tooltip": "Format: <lora:lora_name:strength> separated by spaces or punctuation",
                }),
            },
            "optional": {
                "clip": ("CLIP",),
                "lora_stack": ("LORA_STACK",),
            },
        }

    RETURN_TYPES = ("MODEL", "CLIP", "STRING", "STRING")
    RETURN_NAMES = ("MODEL", "CLIP", "trigger_words", "loaded_loras")
    FUNCTION = "load_loras_from_text"

    def parse_lora_syntax(self, text):
        """Parse LoRA syntax from text input."""
        pattern = r"<lora:([^:>]+):([^:>]+)(?::([^:>]+))?>"
        matches = re.findall(pattern, text, re.IGNORECASE)

        loras = []
        for match in matches:
            model_strength = float(match[1])
            loras.append({
                "name": match[0],
                "model_strength": model_strength,
                "clip_strength": float(match[2]) if match[2] else model_strength,
            })
        return loras

    def load_loras_from_text(self, model, lora_syntax, clip=None, lora_stack=None):
        """Load LoRAs based on text syntax input."""
        lora_entries = _collect_stack_entries(lora_stack)
        for lora in self.parse_lora_syntax(lora_syntax):
            lora_path, trigger_words = get_lora_info_absolute(lora["name"])
            lora_entries.append({
                "name": lora["name"],
                "absolute_path": lora_path,
                "input_path": lora_path,
                "model_strength": lora["model_strength"],
                "clip_strength": lora["clip_strength"],
                "trigger_words": trigger_words,
            })

        nunchaku_model_kind = detect_nunchaku_model_kind(model)
        if nunchaku_model_kind == "flux":
            logger.info("Detected Nunchaku Flux model")
        elif nunchaku_model_kind == "qwen_image":
            logger.info("Detected Nunchaku Qwen-Image model")

        model, clip, loaded_loras, all_trigger_words = _apply_entries(model, clip, lora_entries, nunchaku_model_kind)
        trigger_words_text = ",, ".join(all_trigger_words) if all_trigger_words else ""
        formatted_loras_text = _format_loaded_loras(loaded_loras)
        return (model, clip, trigger_words_text, formatted_loras_text)

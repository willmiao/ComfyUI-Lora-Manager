"""Metadata Overwrite node — allows users to manually specify generation parameters
that override the automatically collected/inferred metadata.

Most inputs have falsy defaults (empty string / 0) which are skipped.
clip_skip uses a sentinel default (-25) so that a wired value of 0 is
preserved — both ComfyUI and A1111 conventions have no meaningful 0 value,
but users may wire 0 to express "no clip skip / default".
"""

from typing import Any

from ..metadata_collector.constants import CLIP_SKIP_SENTINEL as _CLIP_SKIP_SENTINEL
from ..metadata_collector.overwrite_utils import collect_overwrite_params


class MetadataOverwriteLM:
    NAME = "Metadata Overwrite (LoraManager)"
    CATEGORY = "Lora Manager/utils"
    DESCRIPTION = (
        "Manually specify generation parameters to override automatically collected "
        "metadata. Only filled/connected inputs will take effect — empty defaults "
        "are ignored."
    )

    @classmethod
    def INPUT_TYPES(cls) -> dict[str, Any]:
        return {
            "optional": {
                "prompt": (
                    "STRING",
                    {
                        "default": "",
                        "multiline": True,
                        "tooltip": "Positive prompt. Only overwrites when non-empty.",
                    },
                ),
                "negative_prompt": (
                    "STRING",
                    {
                        "default": "",
                        "multiline": True,
                        "tooltip": "Negative prompt. Only overwrites when non-empty.",
                    },
                ),
                "seed": (
                    "INT",
                    {
                        "default": 0,
                        "min": 0,
                        "max": 0xFFFFFFFFFFFFFFFF,
                        "control_after_generate": False,
                        "tooltip": "Seed value. Only overwrites when > 0.",
                    },
                ),
                "steps": (
                    "INT",
                    {
                        "default": 0,
                        "min": 0,
                        "max": 10000,
                        "tooltip": "Number of steps. Only overwrites when > 0.",
                    },
                ),
                "cfg_scale": (
                    "FLOAT",
                    {
                        "default": 0.0,
                        "min": 0.0,
                        "max": 100.0,
                        "tooltip": "CFG scale. Only overwrites when > 0.",
                    },
                ),
                "sampler": (
                    "STRING,SAMPLER",
                    {
                        "default": "",
                        "widgetType": "STRING",
                        "tooltip": (
                            "Sampler name. Fill in the name manually or "
                            "connect a SAMPLER output (e.g. KSamplerSelect) "
                            "— the sampler name is then extracted "
                            "automatically. Note: ddim is recorded as "
                            "euler (ComfyUI internal representation). "
                            "Only overwrites when non-empty."
                        ),
                    },
                ),
                "scheduler": (
                    "STRING",
                    {
                        "default": "",
                        "tooltip": "Scheduler name. Only overwrites when non-empty.",
                    },
                ),
                "model": (
                    "STRING,MODEL",
                    {
                        "default": "",
                        "widgetType": "STRING",
                        "tooltip": (
                            "The checkpoint or diffusion model (UNet) used "
                            "for generation. Fill in the name manually or "
                            "connect a MODEL output — the model name is then "
                            "extracted automatically. Only overwrites when "
                            "non-empty."
                        ),
                    },
                ),
                "loras": (
                    "STRING",
                    {
                        "default": "",
                        "multiline": True,
                        "tooltip": (
                            "LoRA syntax, e.g. <lora:name:strength> "
                            "or <lora:name:model_strength:clip_strength>, "
                            "separated by spaces. Only overwrites when non-empty."
                        ),
                    },
                ),
                "size": (
                    "STRING",
                    {
                        "default": "",
                        "tooltip": (
                            "Image size in WIDTHxHEIGHT format (e.g. 512x768). "
                            "Only overwrites when non-empty."
                        ),
                    },
                ),
                "clip_skip": (
                    "INT",
                    {
                        "default": _CLIP_SKIP_SENTINEL,
                        "min": -25,
                        "max": 24,
                        "tooltip": (
                            "Clip skip (ComfyUI: -24..-1, A1111: 1+). "
                            "Default -25 means not set — any other value "
                            "overwrites."
                        ),
                    },
                ),
                "additional_data": (
                    "STRING",
                    {
                        "default": "",
                        "multiline": True,
                        "tooltip": (
                            "Additional data to embed in the image metadata. "
                            "Inserted between Clip skip and Model hash in the "
                            "A1111-compatible parameters string. "
                            'Example: "Copyright": "Some license info"'
                        ),
                    },
                ),
            },
        }

    RETURN_TYPES = ("METADATA",)
    RETURN_NAMES = ("metadata",)
    FUNCTION = "collect_metadata"
    OUTPUT_NODE = True

    def collect_metadata(self, **kwargs: Any) -> tuple[dict[str, Any]]:
        """Collect non-default input values into a metadata dict.

        For most fields, a falsy value (empty string, 0) means "not set"
        and is skipped.  clip_skip uses a dedicated sentinel (-25) so that
        a wired value of 0 is preserved and reaches the metadata pipeline.

        The ``model`` field accepts either a manual string or a wired MODEL
        (ModelPatcher) connection; in the latter case the underlying model
        name is extracted from the patcher's ``cached_patcher_init`` and
        stored as a ComfyUI-style relative path.  The ``sampler`` field
        likewise accepts a manual string or a wired SAMPLER (KSAMPLER)
        connection, from which the sampler name is extracted automatically.
        """
        return (collect_overwrite_params(kwargs),)

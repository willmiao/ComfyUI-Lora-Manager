"""Metadata Overwrite node — allows users to manually specify generation parameters
that override the automatically collected/inferred metadata.

All inputs have falsy defaults: only truthy (non-empty / non-zero) values
will overwrite the corresponding field in the final metadata.
"""

from typing import Any

from ..metadata_collector.constants import METADATA_OVERWRITE_FIELDS


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
                    "STRING",
                    {
                        "default": "",
                        "tooltip": "Sampler name. Only overwrites when non-empty.",
                    },
                ),
                "scheduler": (
                    "STRING",
                    {
                        "default": "",
                        "tooltip": "Scheduler name. Only overwrites when non-empty.",
                    },
                ),
                "checkpoint": (
                    "STRING",
                    {
                        "default": "",
                        "tooltip": "Checkpoint / model name. Only overwrites when non-empty.",
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
                        "default": 0,
                        "min": -24,
                        "max": 24,
                        "tooltip": "Clip skip. Only overwrites when non-zero.",
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
        """Collect non-falsy input values into a metadata dict.

        Only values that are truthy (non-empty string, non-zero number)
        are included — matching the overwrite logic in the metadata pipeline.
        """
        result: dict[str, Any] = {}
        for key in METADATA_OVERWRITE_FIELDS:
            value = kwargs.get(key)
            if value:
                result[key] = value
        return (result,)

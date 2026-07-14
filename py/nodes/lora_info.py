"""Lora Info display node — pure frontend node for showing selected LoRA info.

This node does NOT participate in workflow execution. Its single optional
"lora_source" input exists solely as a wire-connection anchor so that the
frontend can traverse the graph and push selection data to connected info nodes.
"""

from __future__ import annotations


class LoraInfoLM:
    """Display node that shows filename and notes for the selected LoRA."""

    NAME = "Lora Info (LoraManager)"
    CATEGORY = "Lora Manager/utils"
    DESCRIPTION = (
        "Displays information (filename, notes) about the currently selected "
        "LoRA. Connect any output from a LoRA Loader or Stacker to the "
        "lora_source input, then select a LoRA in the source widget — the "
        "info updates automatically. Does not affect workflow execution."
    )

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {},
        }

    RETURN_TYPES = ()
    RETURN_NAMES = ()
    OUTPUT_NODE = False
    FUNCTION = "noop"

    def noop(self, **kwargs):
        # This node is display-only — no workflow execution needed.
        return ()


NODE_CLASS_MAPPINGS = {
    LoraInfoLM.NAME: LoraInfoLM,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    LoraInfoLM.NAME: "Lora Info (LoraManager)",
}

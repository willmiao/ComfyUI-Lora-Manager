from __future__ import annotations

import re
from typing import Any

_STACK_INPUT_PATTERN = re.compile(r"^lora_stack(?:_([ab])|(\d+))$")


def _is_stack_input(name: str) -> bool:
    return bool(_STACK_INPUT_PATTERN.match(name))


def _stack_slot_number(name: str) -> int:
    """Numeric slot used to order stack inputs; legacy a/b map to 1/2."""
    match = _STACK_INPUT_PATTERN.match(name)
    if not match:
        return -1
    letter, digits = match.group(1), match.group(2)
    if digits is not None:
        return int(digits)
    return 1 if letter == "a" else 2


class _LoraStackOptionalInputs(dict):
    """Optional-input mapping that also resolves dynamically added stack slots.

    Inheriting ``dict`` keeps ``INPUT_TYPES()`` JSON-serializable for ComfyUI's
    ``/object_info`` route: it serializes the stored entries, exactly as the plain
    dict did before. The overridden ``__contains__``/``__getitem__`` let the
    execution side resolve ``lora_stack3``-style inputs the frontend adds on
    demand. This replaces the previous ``inspect.stack()`` check for the
    ``get_input_info`` caller, which the registry security scan reports as
    anti-debugging.
    """

    def __init__(self, explicit_inputs: dict[str, tuple[str, dict[str, Any]]]) -> None:
        super().__init__(explicit_inputs)

    def __contains__(self, item: object) -> bool:
        if not isinstance(item, str):
            return False
        return super().__contains__(item) or _is_stack_input(item)

    def __getitem__(self, key: str) -> tuple[str, dict[str, Any]]:
        if super().__contains__(key):
            return super().__getitem__(key)
        if _is_stack_input(key):
            return (
                "LORA_STACK",
                {
                    "tooltip": "A LoRA stack to combine. Connect to add more inputs.",
                },
            )
        raise KeyError(key)


class LoraStackCombinerLM:
    NAME = "Lora Stack Combiner (LoraManager)"
    CATEGORY = "Lora Manager/stackers"
    DESCRIPTION = (
        "Combines multiple LoRA stacks into a single stack. "
        "Supports dynamic inputs: connect a stack to add more inputs."
    )

    @classmethod
    def INPUT_TYPES(cls):
        optional_inputs: dict[str, tuple[str, dict[str, Any]]] = {
            "lora_stack1": (
                "LORA_STACK",
                {
                    "tooltip": "A LoRA stack to combine. Connect to add more inputs.",
                },
            ),
            "lora_stack2": (
                "LORA_STACK",
                {
                    "tooltip": "A LoRA stack to combine. Connect to add more inputs.",
                },
            ),
        }

        return {
            "required": {},
            "optional": _LoraStackOptionalInputs(optional_inputs),
        }

    RETURN_TYPES = ("LORA_STACK",)
    RETURN_NAMES = ("LORA_STACK",)
    FUNCTION = "combine_stacks"

    def combine_stacks(self, lora_stack1=None, lora_stack2=None, **kwargs):
        stacks = {
            "lora_stack1": lora_stack1,
            "lora_stack2": lora_stack2,
        }
        for key, value in kwargs.items():
            if _is_stack_input(key) and value is not None:
                stacks[key] = value

        combined_stack = []
        for key in sorted(stacks, key=_stack_slot_number):
            stack = stacks[key]
            if stack:
                combined_stack.extend(stack)

        return (combined_stack,)

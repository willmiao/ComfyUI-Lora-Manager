from __future__ import annotations

import inspect
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


class _LoraStackOptionalInputs:
    """Lookup that preserves explicit optional inputs and dynamic lora_stack slots."""

    def __init__(self, explicit_inputs: dict[str, tuple[str, dict[str, Any]]]) -> None:
        self._explicit_inputs = explicit_inputs

    def __contains__(self, item: object) -> bool:
        if not isinstance(item, str):
            return False
        return item in self._explicit_inputs or _is_stack_input(item)

    def __getitem__(self, key: str) -> tuple[str, dict[str, Any]]:
        if key in self._explicit_inputs:
            return self._explicit_inputs[key]
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

        stack = inspect.stack()
        if len(stack) > 2 and stack[2].function == "get_input_info":
            optional_inputs = _LoraStackOptionalInputs(optional_inputs)  # type: ignore[assignment]

        return {
            "required": {},
            "optional": optional_inputs,
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

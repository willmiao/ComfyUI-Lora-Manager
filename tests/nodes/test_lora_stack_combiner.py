import types

import pytest

from py.nodes.lora_stack_combiner import (
    LoraStackCombinerLM,
    _LoraStackOptionalInputs,
)


def test_combine_stacks_preserves_order():
    node = LoraStackCombinerLM()
    stack_a = [
        ("folder/a.safetensors", 0.7, 0.6),
        ("folder/b.safetensors", 0.8, 0.8),
    ]
    stack_b = [
        ("folder/c.safetensors", 1.0, 0.9),
    ]

    (combined_stack,) = node.combine_stacks(stack_a, stack_b)

    assert combined_stack == stack_a + stack_b


def test_combine_stacks_returns_second_when_first_empty():
    node = LoraStackCombinerLM()
    stack_b = [("folder/c.safetensors", 1.0, 0.9)]

    (combined_stack,) = node.combine_stacks([], stack_b)

    assert combined_stack == stack_b


def test_combine_stacks_returns_first_when_second_empty():
    node = LoraStackCombinerLM()
    stack_a = [("folder/a.safetensors", 0.7, 0.6)]

    (combined_stack,) = node.combine_stacks(stack_a, [])

    assert combined_stack == stack_a


def test_combine_stacks_returns_empty_when_both_empty():
    node = LoraStackCombinerLM()

    (combined_stack,) = node.combine_stacks([], [])

    assert combined_stack == []


def test_combine_stacks_allows_duplicate_entries():
    node = LoraStackCombinerLM()
    duplicate_entry = ("folder/shared.safetensors", 0.9, 0.5)

    (combined_stack,) = node.combine_stacks([duplicate_entry], [duplicate_entry])

    assert combined_stack == [duplicate_entry, duplicate_entry]


def test_combine_stacks_returns_empty_when_both_unconnected():
    node = LoraStackCombinerLM()

    (combined_stack,) = node.combine_stacks()

    assert combined_stack == []


def test_combine_stacks_returns_other_when_one_unconnected():
    node = LoraStackCombinerLM()
    stack_a = [("folder/a.safetensors", 0.7, 0.6)]

    (combined_stack_a,) = node.combine_stacks(lora_stack1=stack_a)
    (combined_stack_b,) = node.combine_stacks(lora_stack2=stack_a)

    assert combined_stack_a == stack_a
    assert combined_stack_b == stack_a


def test_combine_stacks_with_dynamic_third_slot():
    node = LoraStackCombinerLM()
    stack_a = [("folder/a.safetensors", 0.7, 0.6)]
    stack_b = [("folder/b.safetensors", 0.8, 0.8)]
    stack_c = [("folder/c.safetensors", 1.0, 0.9)]

    (combined_stack,) = node.combine_stacks(
        lora_stack1=stack_a, lora_stack2=stack_b, lora_stack3=stack_c
    )

    assert combined_stack == stack_a + stack_b + stack_c


def test_combine_stacks_orders_by_slot_number_not_call_order():
    node = LoraStackCombinerLM()
    stack_a = [("folder/a.safetensors", 0.7, 0.6)]
    stack_b = [("folder/b.safetensors", 0.8, 0.8)]
    stack_c = [("folder/c.safetensors", 1.0, 0.9)]

    (combined_stack,) = node.combine_stacks(
        lora_stack3=stack_c, lora_stack2=stack_b, lora_stack1=stack_a
    )

    assert combined_stack == stack_a + stack_b + stack_c


def test_combine_stacks_accepts_only_dynamic_slot():
    node = LoraStackCombinerLM()
    stack_c = [("folder/c.safetensors", 1.0, 0.9)]

    (combined_stack,) = node.combine_stacks(lora_stack3=stack_c)

    assert combined_stack == stack_c


def test_combine_stacks_handles_legacy_input_names():
    node = LoraStackCombinerLM()
    stack_a = [("folder/a.safetensors", 0.7, 0.6)]
    stack_b = [("folder/b.safetensors", 0.8, 0.8)]

    (combined_stack,) = node.combine_stacks(lora_stack_a=stack_a, lora_stack_b=stack_b)

    assert combined_stack == stack_a + stack_b


def test_input_types_exposes_two_default_slots():
    input_types = LoraStackCombinerLM.INPUT_TYPES()

    assert set(input_types["optional"]) == {"lora_stack1", "lora_stack2"}
    assert input_types["optional"]["lora_stack1"][0] == "LORA_STACK"
    assert input_types["optional"]["lora_stack2"][0] == "LORA_STACK"


def test_input_types_recognizes_dynamic_slots_from_get_input_info(monkeypatch):
    frames = [None, None, types.SimpleNamespace(function="get_input_info")]
    monkeypatch.setattr(
        "py.nodes.lora_stack_combiner.inspect.stack", lambda: frames
    )

    input_types = LoraStackCombinerLM.INPUT_TYPES()
    optional = input_types["optional"]

    assert "lora_stack3" in optional
    assert optional["lora_stack3"][0] == "LORA_STACK"
    assert "lora_stack25" in optional
    assert optional["lora_stack25"][0] == "LORA_STACK"


def test_lora_stack_optional_inputs_proxy():
    proxy = _LoraStackOptionalInputs({"lora_stack1": ("LORA_STACK", {})})

    assert "lora_stack1" in proxy
    assert "lora_stack2" in proxy
    assert "lora_stack10" in proxy
    assert "lora_stack_a" in proxy
    assert "lora_stack" not in proxy
    assert "lora_stacka" not in proxy
    assert "lora_stack_1" not in proxy
    assert "text" not in proxy

    assert proxy["lora_stack1"][0] == "LORA_STACK"
    assert proxy["lora_stack5"][0] == "LORA_STACK"

    with pytest.raises(KeyError):
        proxy["not_a_stack"]

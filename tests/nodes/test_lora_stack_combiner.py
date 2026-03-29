from py.nodes.lora_stack_combiner import LoraStackCombinerLM


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

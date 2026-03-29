class LoraStackCombinerLM:
    NAME = "Lora Stack Combiner (LoraManager)"
    CATEGORY = "Lora Manager/stackers"

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "lora_stack_a": ("LORA_STACK",),
                "lora_stack_b": ("LORA_STACK",),
            },
        }

    RETURN_TYPES = ("LORA_STACK",)
    RETURN_NAMES = ("LORA_STACK",)
    FUNCTION = "combine_stacks"

    def combine_stacks(self, lora_stack_a, lora_stack_b):
        combined_stack = []

        if lora_stack_a:
            combined_stack.extend(lora_stack_a)
        if lora_stack_b:
            combined_stack.extend(lora_stack_b)

        return (combined_stack,)

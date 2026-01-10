"""
Demo node to showcase Vue + PrimeVue widget integration in ComfyUI LoRA Manager.

This node demonstrates:
- Vue 3 + PrimeVue custom widget
- Widget state serialization
- Integration with ComfyUI workflow
"""


class LoraManagerDemoNode:
    """
    A demo node that uses a Vue + PrimeVue widget to configure LoRA parameters.
    """

    def __init__(self):
        pass

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "lora_demo_widget": ("LORA_DEMO_WIDGET", {}),
            },
            "optional": {
                "text": ("STRING", {
                    "default": "",
                    "multiline": True,
                    "placeholder": "Additional prompt text..."
                }),
            }
        }

    RETURN_TYPES = ("STRING", "FLOAT", "STRING")
    RETURN_NAMES = ("model_name", "strength", "info")

    FUNCTION = "process"

    CATEGORY = "loramanager/demo"

    def process(self, lora_demo_widget, text=""):
        """
        Process the widget data and return the configuration.

        Args:
            lora_demo_widget: Widget data containing model_name and strength
            text: Optional text input

        Returns:
            Tuple of (model_name, strength, info_string)
        """
        model_name = lora_demo_widget.get("modelName", "")
        strength = lora_demo_widget.get("strength", 1.0)

        info = f"Vue Widget Demo - Model: {model_name}, Strength: {strength}"
        if text:
            info += f"\nAdditional text: {text}"

        print(f"[LoraManagerDemoNode] {info}")

        return (model_name, strength, info)


# Node class mappings for ComfyUI
NODE_CLASS_MAPPINGS = {
    "LoraManagerDemoNode": LoraManagerDemoNode
}

# Display name mappings
NODE_DISPLAY_NAME_MAPPINGS = {
    "LoraManagerDemoNode": "LoRA Manager Demo (Vue)"
}

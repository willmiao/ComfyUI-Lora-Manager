# Vue Widgets for ComfyUI LoRA Manager

This directory contains the source code for Vue 3 + PrimeVue custom widgets for ComfyUI LoRA Manager.

## Structure

```
vue-widgets/
├── src/                    # TypeScript/Vue source code
│   ├── main.ts            # Main entry point that registers extensions
│   └── components/        # Vue components
│       └── DemoWidget.vue # Example demo widget
├── package.json           # Dependencies and build scripts
├── vite.config.mts        # Vite build configuration
├── tsconfig.json          # TypeScript configuration
└── README.md             # This file
```

## Development

### Install Dependencies

```bash
cd vue-widgets
npm install
```

### Build for Production

```bash
npm run build
```

This compiles the TypeScript/Vue code and outputs to `../web/comfyui/vue-widgets/`.

### Development Mode (Watch)

```bash
npm run dev
```

This builds the widgets in watch mode, automatically rebuilding when files change.

### Type Checking

```bash
npm run typecheck
```

## Creating a New Widget

### 1. Create the Python Node

Create a new node file in `/py/nodes/your_node.py`:

```python
class YourCustomNode:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "your_widget_name": ("YOUR_WIDGET_TYPE", {}),
            }
        }

    RETURN_TYPES = ("STRING",)
    FUNCTION = "process"
    CATEGORY = "loramanager"

    def process(self, your_widget_name):
        # Process widget data
        return (str(your_widget_name),)

NODE_CLASS_MAPPINGS = {
    "YourCustomNode": YourCustomNode
}
```

### 2. Create the Vue Component

Create a new component in `src/components/YourWidget.vue`:

```vue
<template>
  <div class="your-widget-container">
    <!-- Your UI here using PrimeVue components -->
    <Button label="Click me" @click="handleClick" />
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import Button from 'primevue/button'

const props = defineProps<{
  widget: { serializeValue?: (node: unknown, index: number) => Promise<unknown> }
  node: { id: number }
}>()

onMounted(() => {
  // Serialize widget data when workflow is saved
  props.widget.serializeValue = async () => {
    return { /* your data */ }
  }
})
</script>

<style scoped>
/* Your styles */
</style>
```

### 3. Register the Widget

In `src/main.ts`, add your widget registration:

```typescript
import YourWidget from '@/components/YourWidget.vue'

// In getCustomWidgets()
YOUR_WIDGET_TYPE(node) {
  return createVueWidget(node, YourWidget, 'your-widget-name')
}

// In nodeCreated()
if (node.constructor?.comfyClass !== 'YourCustomNode') return
```

### 4. Register the Node

Add your node to `__init__.py`:

```python
from .py.nodes.your_node import YourCustomNode

NODE_CLASS_MAPPINGS = {
    # ...
    "YourCustomNode": YourCustomNode
}
```

### 5. Build and Test

```bash
npm run build
```

Then restart ComfyUI and test your new widget!

## Available PrimeVue Components

This project uses PrimeVue 4.x. Popular components include:

- `Button` - Buttons with icons and variants
- `InputText` - Text input fields
- `InputNumber` - Number input with increment/decrement
- `Dropdown` - Select dropdowns
- `Card` - Card containers
- `DataTable` - Data tables with sorting/filtering
- `Dialog` - Modal dialogs
- `Tree` - Tree view components
- And many more! See [PrimeVue Docs](https://primevue.org/)

## Notes

- Build output goes to `../web/comfyui/vue-widgets/` (gitignored)
- The widget type name in Python (e.g., "YOUR_WIDGET_TYPE") must match the key in `getCustomWidgets()`
- Widget data is serialized when the workflow is saved/executed via `serializeValue()`
- ComfyUI's app.js is marked as external and not bundled

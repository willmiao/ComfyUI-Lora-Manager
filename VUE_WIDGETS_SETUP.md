# Vue + PrimeVue Widget Development Setup

This guide explains the Vue + PrimeVue widget development scaffold for ComfyUI LoRA Manager.

## Overview

The project now supports developing custom ComfyUI widgets using Vue 3 + PrimeVue, providing a modern reactive framework for building rich UI components.

## Architecture

```
ComfyUI-Lora-Manager/
├── vue-widgets/              # Vue widget source code (TypeScript)
│   ├── src/
│   │   ├── main.ts          # Extension registration
│   │   └── components/      # Vue components
│   ├── package.json
│   ├── vite.config.mts      # Build to web/comfyui/vue-widgets/
│   └── tsconfig.json
│
├── web/comfyui/             # ComfyUI web directory
│   ├── vue-widgets/         # Compiled Vue widgets (gitignored)
│   │   ├── demo-widget.js   # Built JavaScript
│   │   └── assets/          # CSS and other assets
│   └── *.js                 # Existing vanilla JS widgets
│
├── py/nodes/                # Python node definitions
│   ├── demo_vue_widget_node.py  # Demo node
│   └── ...
│
└── __init__.py              # Node registration
```

## Quick Start

### 1. Install Dependencies

```bash
cd vue-widgets
npm install
```

### 2. Build the Demo Widget

```bash
npm run build
```

This compiles the TypeScript/Vue code and outputs to `web/comfyui/vue-widgets/`.

### 3. Test in ComfyUI

1. Start/restart ComfyUI
2. Open the ComfyUI interface
3. Add the "LoRA Manager Demo (Vue)" node from the node menu
4. You should see a Vue-powered widget with PrimeVue components:
   - Text input for model name
   - Number input for strength (with +/- buttons)
   - Apply and Reset buttons
   - Result card showing current configuration

## Development Workflow

### Watch Mode for Development

```bash
cd vue-widgets
npm run dev
```

This watches for file changes and automatically rebuilds. You'll need to refresh ComfyUI's browser page to see changes.

### Project Structure

**Python Side (`py/nodes/demo_vue_widget_node.py`):**
- Defines the ComfyUI node class
- Specifies input types (including the custom widget type)
- Implements the processing logic
- The widget type name must match the key in the frontend's `getCustomWidgets()`

**Frontend Side (`vue-widgets/src/`):**
- `main.ts` - Registers the extension with ComfyUI and creates Vue apps
- `components/DemoWidget.vue` - The actual Vue component with PrimeVue UI

### Data Flow

1. **Widget Creation:**
   - ComfyUI calls `getCustomWidgets()` when creating a node
   - Creates a container DOM element
   - Mounts a Vue app with the component inside the container

2. **Widget State:**
   - Component props receive `widget` and `node` objects from ComfyUI
   - Use Vue's reactive state management within the component

3. **Serialization:**
   - Implement `widget.serializeValue()` in `onMounted()`
   - This function is called when the workflow is saved or executed
   - Return the data that should be passed to the Python node

4. **Processing:**
   - Python node receives the serialized data in its `process()` method
   - Process the data and return results to the workflow

## Creating Your Own Widget

See the detailed guide in `vue-widgets/README.md`.

Quick checklist:
- [ ] Create Python node in `py/nodes/`
- [ ] Create Vue component in `vue-widgets/src/components/`
- [ ] Register widget in `vue-widgets/src/main.ts`
- [ ] Register node in `__init__.py`
- [ ] Build with `npm run build`
- [ ] Test in ComfyUI

## Key Technologies

- **Vue 3**: Modern reactive framework with Composition API
- **PrimeVue 4**: Rich UI component library with 90+ components
- **TypeScript**: Type-safe development
- **Vite**: Fast build tool with HMR support

## Build Configuration

The build is configured to:
- Output ES modules to `../web/comfyui/vue-widgets/`
- Mark ComfyUI's `app.js` as external (not bundled)
- Generate source maps for debugging
- Keep code unminified for easier debugging
- Split vendor code into separate chunks

## PrimeVue Components

The demo widget showcases several PrimeVue components:
- `Button` - Styled buttons with icons
- `InputText` - Text input fields
- `InputNumber` - Number inputs with spinners
- `Card` - Container component

For the full component library, see [PrimeVue Documentation](https://primevue.org/).

## Troubleshooting

### Build fails with module errors
- Make sure you're in the `vue-widgets` directory
- Run `npm install` to ensure all dependencies are installed
- Check that Node.js version is 18+ (`node --version`)

### Widget doesn't appear in ComfyUI
- Verify the build completed successfully (`web/comfyui/vue-widgets/demo-widget.js` exists)
- Check that the Python node is registered in `__init__.py`
- Restart ComfyUI completely (not just refresh browser)
- Check browser console for JavaScript errors

### Widget type mismatch error
- Ensure the widget type in Python (e.g., `"LORA_DEMO_WIDGET"`) matches the key in `getCustomWidgets()`
- Type names are case-sensitive

### Changes not reflected after rebuild
- Hard refresh the browser (Ctrl+Shift+R / Cmd+Shift+R)
- Clear browser cache
- Restart ComfyUI server

## Next Steps

Now that the scaffold is set up, you can:

1. **Extend the demo widget** - Add more PrimeVue components and functionality
2. **Create production widgets** - Build widgets for actual LoRA management features
3. **Add styling** - Customize the look with CSS/Tailwind
4. **Add i18n** - Implement vue-i18n for internationalization
5. **Add state management** - Use Pinia if you need shared state across widgets

## References

- [ComfyUI Custom Nodes Documentation](https://docs.comfy.org/essentials/custom_node_server)
- [PrimeVue Documentation](https://primevue.org/)
- [Vue 3 Documentation](https://vuejs.org/)
- [Vite Documentation](https://vitejs.dev/)
- Reference implementation: `/refs/ComfyUI_frontend_vue_basic`

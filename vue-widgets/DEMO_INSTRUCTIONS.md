# Demo Widget Testing Instructions

## What Was Created

A complete Vue + PrimeVue development scaffold for creating custom ComfyUI widgets, including a working demo to validate the entire workflow.

## Components

### 1. Python Node (`py/nodes/demo_vue_widget_node.py`)
- **Node Name**: LoRA Manager Demo (Vue)
- **Category**: loramanager/demo
- **Inputs**:
  - `lora_demo_widget` (custom widget)
  - `text` (optional string)
- **Outputs**:
  - `model_name` (STRING)
  - `strength` (FLOAT)
  - `info` (STRING)

### 2. Vue Widget (`vue-widgets/src/components/DemoWidget.vue`)
Uses PrimeVue components:
- **InputText** - For model name input
- **InputNumber** - For strength value (0-2, step 0.1) with +/- buttons
- **Button** - Apply and Reset actions
- **Card** - Display current configuration

### 3. Build System
- **Vite** - Fast build tool
- **TypeScript** - Type-safe development
- **Output**: `web/comfyui/vue-widgets/demo-widget.js`

## How to Test

### 1. Build the Widget (if not already built)

```bash
cd vue-widgets
npm install  # Only needed once
npm run build
```

### 2. Start/Restart ComfyUI

```bash
# In your ComfyUI root directory
python main.py
```

### 3. Add the Demo Node

1. Open ComfyUI in your browser (usually http://localhost:8188)
2. Right-click on the canvas → **Add Node**
3. Navigate to: **loramanager** → **demo** → **LoRA Manager Demo (Vue)**
4. The node should appear with a Vue-powered widget inside

### 4. Test the Widget

The widget provides an interactive demo:

1. **Enter a model name** in the text field (e.g., "test-lora-model")
2. **Adjust the strength** using the number input or +/- buttons (0.0 - 2.0)
3. **Click "Apply"** to set the configuration
4. A card will appear showing the current configuration
5. **Click "Reset"** to clear everything

### 5. Test Workflow Integration

1. Add some input/output nodes to create a minimal workflow
2. Connect the demo node outputs to other nodes:
   - `model_name` → Can connect to any STRING input
   - `strength` → Can connect to any FLOAT input
   - `info` → Informational STRING output
3. Click **Queue Prompt** to execute the workflow
4. Check the console/terminal - you should see:
   ```
   [LoraManagerDemoNode] Vue Widget Demo - Model: test-lora-model, Strength: 1.5
   ```

### 6. Test State Persistence

1. Configure the widget (set model name and strength, click Apply)
2. Save the workflow (Ctrl+S / Cmd+S)
3. Reload the page
4. Load the saved workflow
5. The widget should restore its state

## Expected Behavior

✅ **Success Indicators:**
- Widget appears inside the node with proper styling
- PrimeVue components are rendered correctly
- Buttons respond to clicks
- Input values update reactively
- Configuration card appears after clicking Apply
- Node outputs the correct data when workflow executes
- State persists when saving/loading workflows

❌ **Common Issues:**

**Widget doesn't appear:**
- Check browser console for JavaScript errors
- Verify `web/comfyui/vue-widgets/demo-widget.js` exists
- Restart ComfyUI completely

**Build errors:**
- Make sure you're in the `vue-widgets` directory when running npm commands
- Check Node.js version: `node --version` (should be 18+)
- Try deleting `node_modules` and running `npm install` again

**Widget shows but crashes:**
- Check browser console for errors
- Verify PrimeVue components are imported correctly
- Check that the widget type matches between Python and JavaScript

## Development Workflow

For active development:

```bash
# Terminal 1: Watch mode for auto-rebuild
cd vue-widgets
npm run dev

# Terminal 2: ComfyUI server
cd ../../..  # Back to ComfyUI root
python main.py
```

When you make changes to Vue files:
1. Vite automatically rebuilds
2. Hard refresh the browser (Ctrl+Shift+R / Cmd+Shift+R)
3. Changes should appear

## Next Steps

Now that the demo works, you can:

1. **Modify the demo widget** to add more features
2. **Create new widgets** for actual LoRA Manager functionality
3. **Add more PrimeVue components** (see [PrimeVue Docs](https://primevue.org/))
4. **Integrate with the LoRA Manager API** to fetch real data
5. **Add styling** to match ComfyUI's theme better

## File Structure Reference

```
ComfyUI-Lora-Manager/
├── vue-widgets/                          # Vue source code
│   ├── src/
│   │   ├── main.ts                      # Extension registration
│   │   └── components/
│   │       └── DemoWidget.vue           # Demo widget component
│   ├── package.json                     # Dependencies
│   ├── vite.config.mts                  # Build config
│   ├── tsconfig.json                    # TypeScript config
│   ├── README.md                        # Development guide
│   └── DEMO_INSTRUCTIONS.md             # This file
│
├── web/comfyui/
│   └── vue-widgets/                     # Build output (gitignored)
│       ├── demo-widget.js               # Compiled JavaScript
│       └── assets/
│           └── demo-widget-*.css        # Compiled CSS
│
├── py/nodes/
│   └── demo_vue_widget_node.py          # Python node definition
│
├── __init__.py                          # Updated with demo node
├── VUE_WIDGETS_SETUP.md                 # Complete setup guide
└── .gitignore                           # Updated to ignore build output
```

## Support

For issues or questions:
1. Check the browser console for errors
2. Check the ComfyUI terminal for Python errors
3. Review `VUE_WIDGETS_SETUP.md` for detailed documentation
4. Review `vue-widgets/README.md` for development guide

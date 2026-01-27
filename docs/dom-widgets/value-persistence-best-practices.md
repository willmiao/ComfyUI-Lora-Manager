# DOM Widget Value Persistence - Best Practices

## Overview

DOM widgets require different persistence patterns depending on their complexity. This document covers two patterns:

1. **Simple Text Widgets**: DOM element as source of truth (e.g., textarea, input)
2. **Complex Widgets**: Internal value with `widget.callback` (e.g., LoraPoolWidget, RandomizerWidget)

## Understanding ComfyUI's Built-in Callback Mechanism

When `widget.value` is set (e.g., during workflow load), ComfyUI's `domWidget.ts` triggers this flow:

```typescript
// From ComfyUI_frontend/src/scripts/domWidget.ts:146-149
set value(v: V) {
  this.options.setValue?.(v)      // 1. Update internal state
  this.callback?.(this.value)     // 2. Notify listeners for UI updates
}
```

This means:
- `setValue()` handles storing the value
- `widget.callback()` is automatically called to notify the UI
- You don't need custom callback mechanisms like `onSetValue`

---

## Pattern 1: Simple Text Input Widgets

For widgets where the value IS the DOM element's text content (textarea, input fields).

### When to Use

- Single text input/textarea widgets
- Value is a simple string
- No complex state management needed

### Implementation

**main.ts:**
```typescript
const widget = node.addDOMWidget(name, type, container, {
  getValue() {
    return widget.inputEl?.value ?? ''
  },
  setValue(v: string) {
    if (widget.inputEl) {
      widget.inputEl.value = v ?? ''
    }
  }
})
```

**Vue Component:**
```typescript
onMounted(() => {
  if (textareaRef.value) {
    props.widget.inputEl = textareaRef.value
  }
})

onUnmounted(() => {
  if (props.widget.inputEl === textareaRef.value) {
    props.widget.inputEl = undefined
  }
})
```

### Why This Works

- Single source of truth: the DOM element
- `getValue()` reads directly from DOM
- `setValue()` writes directly to DOM
- No sync issues between multiple state variables

---

## Pattern 2: Complex Widgets

For widgets with structured data (JSON configs, arrays, objects) where the value cannot be stored in a DOM element.

### When to Use

- Value is a complex object/array (e.g., `{ loras: [...], settings: {...} }`)
- Multiple UI elements contribute to the value
- Vue reactive state manages the UI

### Implementation

**main.ts:**
```typescript
let internalValue: MyConfig | undefined

const widget = node.addDOMWidget(name, type, container, {
  getValue() {
    return internalValue
  },
  setValue(v: MyConfig) {
    internalValue = v
    // NO custom onSetValue needed - widget.callback is called automatically
  },
  serialize: true  // Ensure value is saved with workflow
})
```

**Vue Component:**
```typescript
const config = ref<MyConfig>(getDefaultConfig())

onMounted(() => {
  // Set up callback for UI updates when widget.value changes externally
  // (e.g., workflow load, undo/redo)
  props.widget.callback = (newValue: MyConfig) => {
    if (newValue) {
      config.value = newValue
    }
  }

  // Restore initial value if workflow was already loaded
  if (props.widget.value) {
    config.value = props.widget.value
  }
})

// When UI changes, update widget value
function onConfigChange(newConfig: MyConfig) {
  config.value = newConfig
  props.widget.value = newConfig  // This also triggers callback
}
```

### Why This Works

1. **Clear separation**: `internalValue` stores the data, Vue ref manages the UI
2. **Built-in callback**: ComfyUI calls `widget.callback()` automatically after `setValue()`
3. **Bidirectional sync**:
   - External → UI: `setValue()` updates `internalValue`, `callback()` updates Vue ref
   - UI → External: User interaction updates Vue ref, which updates `widget.value`

---

## Common Mistakes

### ❌ Creating custom callback mechanisms

```typescript
// Wrong - unnecessary complexity
setValue(v: MyConfig) {
  internalValue = v
  widget.onSetValue?.(v)  // Don't add this - use widget.callback instead
}
```

Use the built-in `widget.callback` instead.

### ❌ Using v-model for simple text inputs in DOM widgets

```html
<!-- Wrong - creates sync issues -->
<textarea v-model="textValue" />

<!-- Right for simple text widgets -->
<textarea ref="textareaRef" @input="onInput" />
```

### ❌ Watching props.widget.value

```typescript
// Wrong - creates race conditions
watch(() => props.widget.value, (newValue) => {
  config.value = newValue
})
```

Use `widget.callback` instead - it's called at the right time in the lifecycle.

### ❌ Multiple sources of truth

```typescript
// Wrong - who is the source of truth?
let internalValue = ''        // State 1
const textValue = ref('')     // State 2
const domElement = textarea   // State 3
props.widget.value            // State 4
```

Choose ONE source of truth:
- **Simple widgets**: DOM element
- **Complex widgets**: `internalValue` (with Vue ref as derived UI state)

### ❌ Adding serializeValue for simple widgets

```typescript
// Wrong - getValue/setValue handle serialization
props.widget.serializeValue = async () => textValue.value
```

---

## Decision Guide

| Widget Type | Source of Truth | Use `widget.callback` | Example |
|-------------|-----------------|----------------------|---------|
| Simple text input | DOM element (`inputEl`) | Optional | AutocompleteTextWidget |
| Complex config | `internalValue` | Yes, for UI sync | LoraPoolWidget |
| Vue component widget | Vue ref + `internalValue` | Yes | RandomizerWidget |

---

## Testing Checklist

- [ ] Load workflow - value restores correctly
- [ ] Switch workflow - value persists
- [ ] Reload page - value persists
- [ ] UI interaction - value updates
- [ ] Undo/redo - value syncs with UI
- [ ] No console errors

---

## References

- ComfyUI DOMWidget implementation: `ComfyUI_frontend/src/scripts/domWidget.ts`
- Simple text widget example: `ComfyUI_frontend/src/renderer/extensions/vueNodes/widgets/composables/useStringWidget.ts`

# DOM Widget Value Persistence - Best Practices

## Problem

DOM widgets with text inputs failed to persist values after:
- Loading workflows
- Switching workflows  
- Reloading pages

## Root Cause

**Multiple sources of truth** causing sync issues:
- Internal state variable (`internalValue` in main.ts)
- Vue reactive ref (`textValue` in component)
- DOM element value (actual textarea)
- ComfyUI widget value (`props.widget.value`)

**Broken sync chains:**
```
getValue() → internalValue (not actual DOM value)
setValue(v) → internalValue → onSetValue() → textValue.value (async chain)
serializeValue() → textValue.value (different from getValue)
watch() → another sync layer
```

## Solution

Follow ComfyUI built-in `addMultilineWidget` pattern:

### ✅ Do

1. **Single source of truth**: Use the DOM element directly
   ```typescript
   // main.ts
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

2. **Register DOM reference** when component mounts
   ```typescript
   // Vue component
   onMounted(() => {
     if (textareaRef.value) {
       props.widget.inputEl = textareaRef.value
     }
   })
   ```

3. **Clean up reference** on unmount
   ```typescript
   onUnmounted(() => {
     if (props.widget.inputEl === textareaRef.value) {
       props.widget.inputEl = undefined
     }
   })
   ```

4. **Simplify interface** - only expose what's needed
   ```typescript
   export interface MyWidgetInterface {
     inputEl?: HTMLTextAreaElement
     callback?: (v: string) => void
   }
   ```

### ❌ Don't

1. **Don't create internal state variables**
   ```typescript
   // Wrong
   let internalValue = ''
   getValue() { return internalValue }
   ```

2. **Don't use v-model** for text inputs in DOM widgets
   ```html
   <!-- Wrong -->
   <textarea v-model="textValue" />

   <!-- Right -->
   <textarea ref="textareaRef" @input="onInput" />
   ```

3. **Don't add serializeValue** - getValue/setValue handle it
   ```typescript
   // Wrong
   props.widget.serializeValue = async () => textValue.value
   ```

4. **Don't add onSetValue** callback
   ```typescript
   // Wrong
   setValue(v: string) {
     internalValue = v
     widget.onSetValue?.(v) // Unnecessary layer
   }
   ```

5. **Don't watch props.widget.value** - creates race conditions
   ```typescript
   // Wrong
   watch(() => props.widget.value, (newValue) => {
     textValue.value = newValue
   })
   ```

6. **Don't restore from props.widget.value** in onMounted
   ```typescript
   // Wrong
   onMounted(() => {
     if (props.widget.value) {
       textValue.value = props.widget.value
     }
   })
   ```

## Key Principles

1. **One source of truth**: DOM element value only
2. **Direct sync**: getValue/setValue read/write DOM directly
3. **No async chains**: Eliminate intermediate variables
4. **Match built-in patterns**: Study ComfyUI's `addMultilineWidget` implementation
5. **Minimal interface**: Only expose `inputEl` and `callback`

## Testing Checklist

- [ ] Load workflow - value restores correctly
- [ ] Switch workflow - value persists
- [ ] Reload page - value persists
- [ ] Type in widget - callback fires
- [ ] No console errors

## References

- ComfyUI built-in: `/home/miao/code/ComfyUI_frontend/src/renderer/extensions/vueNodes/widgets/composables/useStringWidget.ts`
- Example fix: `vue-widgets/src/components/AutocompleteTextWidget.vue` (after fix)

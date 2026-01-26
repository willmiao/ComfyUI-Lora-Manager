# DOM Widgets Documentation

Documentation for custom DOM widget development in ComfyUI LoRA Manager.

## Files

- **[Value Persistence Best Practices](value-persistence-best-practices.md)** - Essential guide for implementing text input DOM widgets that persist values correctly

## Key Lessons

### Common Anti-Patterns

❌ **Don't**: Create internal state variables  
❌ **Don't**: Use v-model for text inputs  
❌ **Don't**: Add serializeValue, onSetValue callbacks  
❌ **Don't**: Watch props.widget.value  

### Best Practices

✅ **Do**: Use DOM element as single source of truth  
✅ **Do**: Store DOM reference on widget.inputEl  
✅ **Do**: Direct getValue/setValue to DOM  
✅ **Do**: Clean up reference on unmount

## Related Documentation

- [DOM Widget Development Guide](../dom_widget_dev_guide.md) - Comprehensive guide for building DOM widgets
- [ComfyUI Built-in Example](../../../../code/ComfyUI_frontend/src/renderer/extensions/vueNodes/widgets/composables/useStringWidget.ts) - Reference implementation

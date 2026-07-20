# ComfyUI Dual-Mode Widget Rendering

ComfyUI custom node widgets render in one of two modes. Patterns that work in one often fail silently in the other. Test both.

## Mode Detection

```js
typeof LiteGraph !== 'undefined' && LiteGraph.vueNodesMode
```

In Vue SFCs, `window.LiteGraph` is unavailable — pass as a prop from `main.ts`.

## Canvas Mode Layout

Uses `computeLayoutSize()` + `distributeSpace()` to allocate widget height within the node. Widgets with `computeLayoutSize` participate in space distribution; those with `computeSize` have fixed height.

- `getMinHeight()` in `addDOMWidget` options → minimum widget height
- `widget.computeLayoutSize()` → `{ minHeight, minWidth, maxHeight? }`
- Avoid `getMaxHeight()` unless the widget genuinely needs a fixed cap (prevents user resize)

## Vue Mode Layout

Uses CSS Grid (`grid-template-rows`) + `ResizeObserver`. The ResizeObserver watches the widget's DOM and feeds back into grid row sizing. This creates a feedback loop: content grows → row resizes → more space for content → content reflows/grows → row resizes again.

### Height Containment

The fix: `contain: layout size` on the widget root. This tells the browser the element's intrinsic size is CSS-determined, not driven by descendant content. The ResizeObserver sees a stable size and the loop is broken.

```css
.widget-root.lm-vue-node {
  height: 100%;
  min-height: var(--comfy-widget-min-height, 200px);
  contain: layout size;
}
```

Existing examples: `.lm-loras-container.lm-vue-node` and `.comfy-tags-container.lm-vue-node` in `web/comfyui/lm_styles.css`.

**Do NOT** fix height issues with `maxHeight`, `getMaxHeight()`, or inline `max-height` — these prevent the user from resizing the node.

## Scroll Wheel Isolation

Both modes need to distinguish "user wants to scroll widget content" from "user wants to zoom canvas".

**Canvas mode:** Add `@wheel` on widget root. Check `event.target.closest(selector)` for scrollable sub-areas. If scrollable → `event.stopPropagation()`. Otherwise → `app.canvas.processMouseWheel(event)`.

**Vue mode:** Add CSS class `lm-wheel-scrollable` to scrollable elements. The global capture-phase hook in `web/comfyui/utils.js` (`enableListWheelScroll`) detects wheel events on marked elements and manually scrolls them via `element.scrollTop`, consuming the event before canvas zoom sees it.

## DOM Structure

`main.ts` creates an outer `<div>` container, then `vueApp.mount(container)`. The Vue app renders its own root element inside.

- `container.id` / `container.style.*` → outer element
- Vue scoped `<style>` → `[data-v-hash]` applies only to Vue root

Classes needed by scoped Vue CSS must go on the Vue root element. Pass data as props and bind with `:class` rather than manipulating the DOM from `main.ts`.

## Serialization

For stateful widgets that need workflow persistence:

- `serialize: true` in `addDOMWidget` options
- `serializeValue()` → state snapshot (called on workflow save)
- `onSetValue(v)` → restore state (called on workflow load)
- Always handle missing keys in restored value for backward compatibility with old workflows

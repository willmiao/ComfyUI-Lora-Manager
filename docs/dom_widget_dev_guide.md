# DOMWidget Development Guide

This document provides a comprehensive guide for developing custom DOMWidgets in ComfyUI using Vanilla JavaScript. DOMWidgets allow you to embed standard HTML elements (div, video, canvas, input, etc.) into ComfyUI nodes while benefitting from the frontend's automatic layout and zoom management.

## 1. Core Concepts

In ComfyUI, a `DOMWidget` extends the default LiteGraph Canvas rendering logic. It maintains an HTML layer on top of the Canvas, making complex interactions and media displays significantly easier to implement than pure Canvas drawing.

### Key APIs
*   **`app.registerExtension`**: The entry point for registering extensions.
*   **`getCustomWidgets`**: A hook for defining new widget types associated with specific input types.
*   **`node.addDOMWidget`**: The core method to add HTML elements to a node.

---

## 2. Basic Structure

A standard custom DOMWidget extension typically follows this structure:

```javascript
import { app } from "../../scripts/app.js";

app.registerExtension({
    name: "My.Custom.Extension",
    async getCustomWidgets() {
        return {
            // Define a new widget type named "MY_WIDGET_TYPE"
            MY_WIDGET_TYPE(node, inputName, inputData, app) {
                // 1. Create the HTML element
                const container = document.createElement("div");
                container.innerHTML = "Hello <b>DOMWidget</b>!";
                
                // 2. Setup styles (Optional but recommended)
                container.style.color = "white";
                container.style.backgroundColor = "#222";
                container.style.padding = "5px";

                // 3. Add the DOMWidget and return the result
                const widget = node.addDOMWidget(inputName, "MY_WIDGET_TYPE", container, {
                    // Configuration options
                    getValue() {
                        return container.innerText;
                    },
                    setValue(v) {
                        container.innerText = v;
                    }
                });

                // 4. Return in the standard format
                return { widget };
            }
        };
    }
});
```

---

## 3. The `addDOMWidget` API

```javascript
node.addDOMWidget(name, type, element, options)
```

### Parameters
1.  **`name`**: The internal name of the widget (usually matches the input name).
2.  **`type`**: The type identifier for the widget.
3.  **`element`**: The actual HTMLElement to embed.
4.  **`options`**: (Object) Configuration for lifecycle, sizing, and persistence.

### Common `options` Fields
| Field | Type | Description |
| :--- | :--- | :--- |
| `getValue` | `Function` | Defines how to retrieve the widget's value for serialization. |
| `setValue` | `Function` | Defines how to restore the widget's state from workflow data. |
| `getMinHeight` | `Function` | Returns the minimum height in pixels. |
| `getHeight` | `Function` | Returns the preferred height (supports numbers or percentage strings like `"50%"`). |
| `onResize` | `Function` | Callback triggered when the widget is resized. |
| `hideOnZoom`| `Boolean` | Whether to hide the DOM element when zoomed out to improve performance (default: `true`). |
| `selectOn` | `string[]` | Events on the element that should trigger node selection (default: `['focus', 'click']`). |

---

## 4. Size Control

Custom DOMWidgets must actively inform the parent Node of their size requirements to ensure the Node layout is calculated correctly and connection wires remain aligned.

### 4.1 Core Mechanism

Whether in Canvas Mode or Vue Mode, the underlying logic model (`LGraphNode`) calls the widget's `computeLayoutSize` method to determine dimensions. This logic is used to calculate the Node's total size and the position of input/output slots.

### 4.2 Controlling Height

It is recommended to use the `options` parameter to define height behavior.

**Performance Note:** providing `getMinHeight` and `getHeight` via `options` allows the system to skip expensive DOM measurements (`getComputedStyle`) during rendering loop. This significantly improves performance and prevents FPS drops during node resizing.

**Method 1: Using `options` (Recommended)**

```javascript
const widget = node.addDOMWidget("MyWidget", "custom", element, {
    // Specify minimum height in pixels
    getMinHeight: () => 150,
    
    // Or specify preferred height (pixels or percentage string)
    // getHeight: () => "50%", 
});
```

**Method 2: Using CSS Variables**

You can also set specific CSS variables on the root element:

```javascript
element.style.setProperty("--comfy-widget-min-height", "150px");
// or --comfy-widget-height
```

### 4.3 Controlling Width

By default, a DOMWidget's width automatically stretches to fit the Node's width (which is determined by the Title or other Input Slots).

If you must **force the Node to be wider** to accommodate your widget, you need to override the widget instance's `computeLayoutSize` method:

```javascript
const widget = node.addDOMWidget("WideWidget", "custom", element);

// Override the default layout calculation
widget.computeLayoutSize = (targetNode) => {
    return {
        minHeight: 150, // Must return height
        minWidth: 300   // Force the Node to be at least 300px wide
    };
};
```

### 4.4 Dynamic Resizing

If your widget's content changes dynamically (e.g., expanding sections, loading images, or CSS changes), the DOM element will resize, but the Canvas-rendered Node background and Slots will not automatically follow. You must manually trigger a synchronization.

**The Update Sequence:**
Whenever the **actual rendering height** of your DOM element changes, execute the following "three-step combo":

```javascript
// 1. Calculate the new optimal size for the node based on current widget requirements
const newSize = node.computeSize();

// 2. Apply the new size to the node model (updates bounding box and slot positions)
node.setSize(newSize);

// 3. Mark the canvas as dirty to trigger a redraw in the next animation frame
node.setDirtyCanvas(true, true);
```

**Common Scenarios:**

| Scenario | Actual Height Change? | Update Required? |
| :--- | :--- | :--- |
| **Expand/Collapse content** | **Yes** | ✅ **Yes**. Prevents widget from overflowing node boundaries. |
| **Image/Video finished loading** | **Yes** | ✅ **Yes**. Initial height might be 0 until the media loads. |
| **Changing `minHeight`** | **Maybe** | ❓ **Only if** the change causes the element's actual height to shift. |
| **Changing font size/styles** | **Yes** | ✅ **Yes**. Text reflow often changes the total height. |
| **User dragging node corner** | **Yes** | ❌ **No**. LiteGraph handles this internally. |

---

## 5. State Persistence (Serialization)

### 5.1 Default Behavior

DOMWidgets have **serialization enabled** by default (`serialize` property is `true`).
*   **Saving**: ComfyUI attempts to read the widget's value to save into the Workflow file.
*   **Loading**: ComfyUI reads the value from the Workflow file and assigns it to the widget.

### 5.2 Custom Serialization

To make persistence work effectively (saving internal DOM state and restoring it), you must implement `getValue` and `setValue` in the `options`:

*   **`getValue`**: Returns the state to be saved (Number, String, or Object).
*   **`setValue`**: Receives the restored value and updates the DOM element.

**Example:**

```javascript
const inputEl = document.createElement("input");
const widget = node.addDOMWidget("MyInput", "custom", inputEl, {
    // 1. Called during Save
    getValue: () => {
        return inputEl.value;
    },
    // 2. Called during Load or Copy/Paste
    setValue: (value) => {
        inputEl.value = value || "";
    }
});

// Optional: Listen for changes to update widget.value immediately
inputEl.addEventListener("change", () => {
    widget.value = inputEl.value; // Triggers callbacks
});
```

### 5.3 The Restoration Mechanism (`configure`)

*   **`configure(data)`**: When a Workflow is loaded, `LGraphNode` calls its `configure(data)` method.
*   **`setValue` Chain**: During `configure`, the Node iterates over the saved `widgets_values` array and assigns each value (`widget.value = savedValue`). For DOMWidgets, this assignment triggers the `setValue` callback defined in your options.

Therefore, `options.setValue` is the critical hook for restoring widget state.

### 5.4 Disabling Serialization

If your widget is purely for display (e.g., a real-time monitor or generated chart) and doesn't need to save state, disable serialization to reduce workflow file size.

**Note**: You cannot set this via `options`. You must modify the widget instance directly.

```javascript
const widget = node.addDOMWidget("DisplayOnly", "custom", element);
widget.serialize = false; // Explicitly disable
```

---

## 6. Lifecycle & Events

### 6.1 `onResize`

When the Node size changes (e.g., user drags the corner), the widget can receive a notification via `options`:

```javascript
const widget = node.addDOMWidget("ResizingWidget", "custom", element, {
    onResize: (w) => {
        // 'w' is the widget instance
        // Adjust internal DOM layout here if necessary
        console.log("Widget resized");
    }
});
```

### 6.2 Construction & Mounting

*   **Construction**: Occurs immediately when `addDOMWidget` is called.
*   **Mounting**:
    *   **Canvas Mode**: Appended to `.dom-widget-container` via `DomWidget.vue`.
    *   **Vue Mode**: Appended inside the Node component via `WidgetDOM.vue`.
    *   **Caution**: When `addDOMWidget` returns, the element may not be in the `document.body` yet. If you need to access layout properties like `getBoundingClientRect`, use `setTimeout` or wait for the first `onResize`.

### 6.3 Cleanup

If you create external references (like `setInterval` or global event listeners), ensure you clean them up using `node.onRemoved`:

```javascript
node.onRemoved = function() {
    clearInterval(myInterval);
    // Call original onRemoved if it existed
};
```

---

## 7. Styling & Best Practices

### 7.1 Styling
Since DOMWidgets are placed in absolute positioned containers or managed by Vue, ensure your container handles sizing gracefully:

```javascript
container.style.width = "100%";
container.style.boxSizing = "border-box";
```

### 7.2 Path References
When importing `app`, adjust the path based on your extension's folder depth. Typically:
`import { app } from "../../scripts/app.js";`

### 7.3 Security
If setting `innerHTML` dynamically, ensure the content is sanitized or trusted to prevent XSS attacks.

---

## 8. Complete Example: Text Counter

This example implements a simple widget that displays the character count of another text widget in the same node.

```javascript
import { app } from "../../scripts/app.js";

app.registerExtension({
    name: "Comfy.TextCounter",
    getCustomWidgets() {
        return {
            TEXT_COUNTER(node, inputName) {
                const el = document.createElement("div");
                Object.assign(el.style, {
                    background: "#222",
                    border: "1px solid #444",
                    padding: "8px",
                    borderRadius: "4px",
                    fontSize: "12px",
                    color: "#eee"
                });
                
                const label = document.createElement("span");
                label.innerText = "Characters: 0";
                el.appendChild(label);

                const widget = node.addDOMWidget(inputName, "TEXT_COUNTER", el, {
                    getValue() { return ""; }, // Nothing to save
                    setValue(v) { },           // Nothing to restore
                    getMinHeight() { return 40; }
                });
                
                // Disable serialization for this display-only widget
                widget.serialize = false;

                // Custom method to update UI
                widget.updateCount = (text) => {
                    label.innerText = `Characters: ${text.length}`;
                };

                return { widget };
            }
        };
    },
    nodeCreated(node) {
        // Logic to link widgets after the node is initialized
        if (node.comfyClass === "MyTextNode") {
            const counterWidget = node.widgets.find(w => w.type === "TEXT_COUNTER");
            const textWidget = node.widgets.find(w => w.name === "text");
            
            if (counterWidget && textWidget) {
                // Hook into the text widget's callback
                const oldCallback = textWidget.callback;
                textWidget.callback = function(v) {
                    if (oldCallback) oldCallback.apply(this, arguments);
                    counterWidget.updateCount(v);
                };
            }
        }
    }
});
```

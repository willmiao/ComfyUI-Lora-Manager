# ComfyUI Custom DOMWidget 开发说明文档 (Vanilla JavaScript)

本文档旨在说明如何使用 Vanilla JavaScript (纯 JS) 在 ComfyUI 前端中实现自定义 `DOMWidget`。`DOMWidget` 允许你将标准的 HTML 元素（如 `div`, `video`, `canvas`, `input` 等）嵌入到 ComfyUI 的节点中，并享受前端自动布局和缩放管理。

---

## 1. 核心概念

在 ComfyUI 中，`DOMWidget` 是对 LiteGraph 默认 Canvas 渲染逻辑的扩展。它在 Canvas 之上维护一个 HTML 层，使得复杂的交互和媒体显示变得非常容易。

### 核心 API
*   `app.registerExtension`: 注册扩展的入口。
*   `getCustomWidgets`: 定义新部件类型的钩子。
*   `node.addDOMWidget(name, type, element, options)`: 将 HTML 元素添加到节点的关键方法。

---

## 2. 基础结构

一个标准的自定义 `DOMWidget` 扩展通常遵循以下结构：

```javascript
import { app } from "../../scripts/app.js";

app.registerExtension({
    name: "My.Custom.Extension",
    async getCustomWidgets() {
        return {
            // 定义一个名为 "MY_WIDGET_TYPE" 的新部件类型
            MY_WIDGET_TYPE(node, inputName, inputData, app) {
                // 1. 创建 HTML 元素
                const container = document.createElement("div");
                container.innerHTML = "Hello <b>DOMWidget</b>!";
                
                // 2. 样式设置 (可选)
                container.style.color = "white";
                container.style.padding = "5px";

                // 3. 调用 addDOMWidget 并返回结果
                const widget = node.addDOMWidget(inputName, "MY_WIDGET_TYPE", container, {
                    // 配置选项
                    getValue() {
                        return container.innerText;
                    },
                    setValue(v) {
                        container.innerText = v;
                    }
                });

                // 4. 固定返回格式
                return { widget };
            }
        };
    }
});
```

---

## 3. `addDOMWidget` 详细参数

```javascript
node.addDOMWidget(name, type, element, options)
```

### 参数说明:
1.  **`name`**: 部件的内部名称（通常匹配输入名称）。
2.  **`type`**: 部件的类型标识符。
3.  **`element`**: 实际的 HTML 元素。
4.  **`options`**: (Object) 包含生命周期和行为的配置项。

### `options` 常用字段:
| 字段 | 类型 | 说明 |
| :--- | :--- | :--- |
| `getValue` | `Function` | 定义部件序列化时的值来源。 |
| `setValue` | `Function` | 定义如何从工作流数据中恢复部件状态。 |
| `getMinHeight` | `Function` | 返回部件的最小像素高度。 |
| `getHeight` | `Function` | 返回部件的期望高度（可返回百分比字符串，如 `"50%"`）。 |
| `hideOnZoom`| `Boolean` | 当 Canvas 缩小到一定程度时是否隐藏 DOM 元素（提高性能，默认 `true`）。 |
| `onDraw` | `Function` | 每一帧绘制时触发，可用于在 Canvas 上做额外标注。 |
| `afterResize` | `Function` | 节点缩放后的回调。 |

---

## 4. 样式与布局管理

ComfyUI 前端使用 CSS 变量来协调 Canvas 节点与 DOM 部件的尺寸。你可以在元素的 `style` 或 CSS 中设置这些变量：

```javascript
container.style.setProperty('--comfy-widget-min-height', '100px');
container.style.setProperty('--comfy-widget-max-height', '500px');
```

由于 `DOMWidget` 被放置在绝对定位的容器中，建议容器元素的样式设为：
```javascript
container.style.width = "100%";
container.style.boxSizing = "border-box";
```

---

## 5. 生命周期与交互

如果你需要访问其他部件或在特定时刻触发逻辑，可以结合 `nodeCreated` 钩子：

```javascript
app.registerExtension({
    name: "My.Lifecycle.Extension",
    nodeCreated(node) {
        if (node.comfyClass === "MyCustomNode") {
            // 查找刚才创建好的 DOMWidget
            const myWidget = node.widgets.find(w => w.name === "my_input");
            
            // 可以在这里绑定事件
            myWidget.element.addEventListener("click", () => {
                console.log("Widget clicked!", myWidget.value);
            });
        }
    }
});
```

---

## 6. 完整实战示例: 简易文本预览器

这个示例实现了一个动态显示文本字数统计的预览器部件。

```javascript
import { app } from "../../scripts/app.js";

app.registerExtension({
    name: "Comfy.TextCounter",
    getCustomWidgets() {
        return {
            TEXT_COUNTER(node, inputName) {
                const el = document.createElement("div");
                el.style.background = "#222";
                el.style.border = "1px solid #444";
                el.style.padding = "8px";
                el.style.borderRadius = "4px";
                el.style.fontSize = "12px";
                
                const label = document.createElement("span");
                label.innerText = "Characters: 0";
                el.appendChild(label);

                const widget = node.addDOMWidget(inputName, "TEXT_COUNTER", el, {
                    getValue() { return node.widgets[0]?.value || ""; },
                    setValue(v) { /* 逻辑通常由上游触发 */ },
                    getMinHeight() { return 40; }
                });

                // 设置一个自定义更新逻辑
                widget.updateCount = (text) => {
                    label.innerText = `Characters: ${text.length}`;
                };

                return { widget };
            }
        };
    },
    nodeCreated(node) {
        if (node.comfyClass === "MyTextNode") {
            const counterWidget = node.widgets.find(w => w.type === "TEXT_COUNTER");
            const textWidget = node.widgets.find(w => w.name === "text");
            
            if (counterWidget && textWidget) {
                // 监听文本部件的回调
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

---

## 7. 注意事项

1.  **路径引用**: 引用 `app` 时请根据你的插件目录深度调整路径，通常是 `../../scripts/app.js`。
2.  **清理**: 如果你创建了外部引用（如 `setInterval` 或全局监听），请确在 `node.onRemoved` 中进行清理。
3.  **安全性**: 如果动态设置 `innerHTML`，请确保内容来源可靠，防止 XSS 攻击。
4.  **性能**: 对于高频更新的 DOM 元素，注意不要触发过多的重排（Reflow）。

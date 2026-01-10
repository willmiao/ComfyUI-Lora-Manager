# Vue Widget 开发快速参考

## 🚀 快速开始

### 用户安装
```bash
# Clone仓库后直接启动ComfyUI，无需其他步骤
git clone <repo>
# 构建产物已包含，直接可用
```

### 开发者设置
```bash
cd vue-widgets
npm install           # 首次安装依赖
npm run build        # 构建widget
```

---

## 📝 常用命令

### 构建命令
```bash
cd vue-widgets

npm run build           # 单次构建
npm run dev             # 监听模式（自动重建）
npm run rebuild         # 清理并重建
npm run typecheck       # TypeScript类型检查
npm run clean           # 清理构建产物
```

### 开发工作流
```bash
# 方式1: 监听模式（推荐）
cd vue-widgets && npm run dev
# 修改代码后，刷新ComfyUI浏览器页面

# 方式2: 手动构建
# 修改代码 → npm run build → 刷新浏览器

# 方式3: 自动检测
# 修改代码 → 重启ComfyUI（会自动重建）
```

---

## 📂 项目结构

```
vue-widgets/                          # Vue源代码目录
├── src/
│   ├── main.ts                      # 扩展注册入口
│   └── components/
│       └── DemoWidget.vue           # Widget组件
├── package.json                     # 依赖和脚本
└── vite.config.mts                  # 构建配置

web/comfyui/vue-widgets/             # 构建产物（提交到Git）
├── demo-widget.js                   # 编译后的JS
├── demo-widget.js.map               # Source map
└── assets/                          # CSS等资源

py/nodes/
└── demo_vue_widget_node.py          # Python节点定义

py/
└── vue_widget_builder.py            # 构建检测模块
```

---

## 🔧 创建新Widget

### 1. 创建Python节点
`py/nodes/my_widget_node.py`:
```python
class MyWidgetNode:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "my_widget": ("MY_WIDGET", {}),
            }
        }

    RETURN_TYPES = ("STRING",)
    FUNCTION = "process"
    CATEGORY = "loramanager"

    def process(self, my_widget):
        return (str(my_widget),)

NODE_CLASS_MAPPINGS = {"MyWidgetNode": MyWidgetNode}
```

### 2. 创建Vue组件
`vue-widgets/src/components/MyWidget.vue`:
```vue
<template>
  <div>
    <Button label="Click" @click="handleClick" />
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import Button from 'primevue/button'

const props = defineProps<{
  widget: { serializeValue?: Function }
  node: { id: number }
}>()

onMounted(() => {
  props.widget.serializeValue = async () => {
    return { /* 数据 */ }
  }
})
</script>
```

### 3. 注册Widget
`vue-widgets/src/main.ts`:
```typescript
import MyWidget from '@/components/MyWidget.vue'

// 在 getCustomWidgets() 中:
MY_WIDGET(node) {
  return createVueWidget(node, MyWidget, 'my-widget')
}
```

### 4. 注册节点
`__init__.py`:
```python
from .py.nodes.my_widget_node import MyWidgetNode

NODE_CLASS_MAPPINGS = {
    # ...
    "MyWidgetNode": MyWidgetNode
}
```

### 5. 构建并测试
```bash
cd vue-widgets && npm run build
# 重启ComfyUI并测试
```

---

## 🎯 构建流程保证

### 如何确保用户安装后有最新的构建产物？

**实施的方案**: 提交构建产物 + 智能检测

#### ✅ 对用户
1. 构建产物已包含在Git仓库中
2. Clone后即可使用，无需Node.js
3. ComfyUI启动时自动检查（如果有Node.js会自动重建）

#### ✅ 对开发者
1. 修改Vue代码后，ComfyUI重启时自动检测并重建
2. 可使用 `npm run dev` 监听模式自动重建
3. 提交前运行 `npm run build`（或使用pre-commit hook）

#### ✅ Git配置
```bash
# .gitignore
✅ 提交: web/comfyui/vue-widgets/         # 构建产物
❌ 忽略: vue-widgets/node_modules/        # 开发依赖
❌ 忽略: vue-widgets/.vite/               # 构建缓存
```

---

## 🛠️ 故障排除

### 问题: Widget不显示最新修改
```bash
# 解决方案1: 强制重建
cd vue-widgets && npm run rebuild

# 解决方案2: 清理缓存
rm -rf web/comfyui/vue-widgets
npm run build

# 解决方案3: 硬刷新浏览器
Ctrl+Shift+R (Windows/Linux)
Cmd+Shift+R (Mac)
```

### 问题: 自动构建失败
```bash
# 检查Node.js
node --version    # 需要 >= 18
npm --version

# 重新安装依赖
cd vue-widgets
rm -rf node_modules package-lock.json
npm install
npm run build
```

### 问题: TypeScript错误
```bash
cd vue-widgets
npm run typecheck          # 检查类型错误
npm run build              # 构建（忽略类型错误）
```

---

## 📚 常用PrimeVue组件

```typescript
import Button from 'primevue/button'
import InputText from 'primevue/inputtext'
import InputNumber from 'primevue/inputnumber'
import Dropdown from 'primevue/dropdown'
import Card from 'primevue/card'
import DataTable from 'primevue/datatable'
import Column from 'primevue/column'
import Dialog from 'primevue/dialog'
import Tree from 'primevue/tree'
import Checkbox from 'primevue/checkbox'
import Slider from 'primevue/slider'
```

文档: https://primevue.org/

---

## 🔄 Git工作流

### 提交代码
```bash
# 方式1: 手动构建
cd vue-widgets && npm run build && cd ..
git add .
git commit -m "feat: update widget"

# 方式2: 使用pre-commit hook
cp vue-widgets/pre-commit.example .git/hooks/pre-commit
chmod +x .git/hooks/pre-commit
git commit -m "feat: update widget"
# Hook自动构建并添加产物
```

### 提交前检查清单
- [ ] Vue源代码已修改
- [ ] 运行 `npm run build`
- [ ] 测试widget功能正常
- [ ] 构建产物已生成在 `web/comfyui/vue-widgets/`
- [ ] `git add` 包含构建产物
- [ ] Commit

---

## 📖 更多文档

- **VUE_WIDGETS_SETUP.md** - 完整架构和设置指南
- **vue-widgets/README.md** - Widget开发详细指南
- **vue-widgets/DEMO_INSTRUCTIONS.md** - Demo widget测试说明
- **BUILD_WORKFLOW_SOLUTIONS.md** - 构建流程方案对比
- **BUILD_WORKFLOW_IMPLEMENTATION.md** - 已实施方案详解

---

## 💡 提示

- 开发时优先使用 `npm run dev` 监听模式
- 提交前确保运行 `npm run build`
- 构建产物约1.4MB，会提交到Git（正常）
- ComfyUI会在启动时自动检测并重建（如果需要）
- Source maps已启用，便于调试

---

## 🎓 学习资源

- [Vue 3 文档](https://vuejs.org/)
- [PrimeVue 文档](https://primevue.org/)
- [TypeScript 文档](https://www.typescriptlang.org/)
- [Vite 文档](https://vitejs.dev/)
- [ComfyUI 自定义节点开发](https://docs.comfy.org/)

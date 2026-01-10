# Vue Widget 构建流程解决方案

## 问题分析

当前配置问题：
- ✅ Vue源代码在 `vue-widgets/src/` 中
- ✅ 构建产物输出到 `web/comfyui/vue-widgets/`
- ❌ **构建产物被 `.gitignore` 忽略，不会提交到仓库**
- ❌ **用户安装后没有构建产物，widget无法工作**

## 解决方案对比

### 方案1：提交构建产物到Git（推荐 ⭐）

**优点：**
- ✅ 用户安装即可用，无需额外步骤
- ✅ 最简单可靠
- ✅ 适合大多数ComfyUI用户（不一定有Node.js环境）
- ✅ 与现有ComfyUI插件生态一致

**缺点：**
- ⚠️ Git仓库略大（每次构建产物变化都会commit）
- ⚠️ 需要确保开发者提交前构建

**实现方式：**
1. 从 `.gitignore` 移除 `web/comfyui/vue-widgets/`
2. 添加 pre-commit hook 自动构建
3. 提交构建产物到仓库

**适用场景：**
- 生产环境发布
- 用户通过ComfyUI Manager或git clone安装

---

### 方案2：用户安装时自动构建

**优点：**
- ✅ Git仓库小，只包含源代码
- ✅ 始终使用最新代码构建
- ✅ 开发者友好

**缺点：**
- ❌ 要求用户有Node.js环境
- ❌ 安装时间长（需要npm install + build）
- ❌ 可能构建失败影响安装体验
- ❌ ComfyUI Manager可能不支持

**实现方式：**
1. 保持 `.gitignore` 设置
2. 添加安装脚本自动检测并构建
3. 在Python `__init__.py` 启动时检查构建产物

**适用场景：**
- 开发环境
- 技术用户

---

### 方案3：混合方案（开发 + 生产分离）

**优点：**
- ✅ 开发时只提交源代码
- ✅ Release时提供完整构建
- ✅ Git仓库保持干净
- ✅ 用户安装release版本即可用

**缺点：**
- ⚠️ 需要CI/CD配置
- ⚠️ 工作流稍复杂

**实现方式：**
1. 开发分支：gitignore构建产物
2. GitHub Actions：自动构建
3. Release分支/Tag：包含构建产物
4. 用户安装release版本

**适用场景：**
- 成熟项目
- 多人协作开发

---

### 方案4：Python启动时自动构建（智能方案）

**优点：**
- ✅ 自动检测是否需要构建
- ✅ 开发模式自动构建
- ✅ 生产模式使用已有构建
- ✅ 最灵活

**缺点：**
- ⚠️ 需要编写构建检测逻辑
- ⚠️ 首次启动可能较慢

**实现方式：**
1. 在 `__init__.py` 中检查构建产物
2. 如果不存在或过期，尝试自动构建
3. 如果无Node.js环境，给出明确提示

**适用场景：**
- 开发+生产通用
- 技术用户为主

---

## 推荐实现：方案1 + 方案4 组合

### 为什么？

1. **对普通用户**：提交构建产物，安装即用
2. **对开发者**：pre-commit hook确保提交前构建
3. **智能检测**：Python启动时检查，开发模式可自动重建

### 实现步骤

#### Step 1: 修改 .gitignore（提交构建产物）

```bash
# 移除这行：
# web/comfyui/vue-widgets/

# 但保留源码构建缓存：
vue-widgets/node_modules/
vue-widgets/dist/
```

#### Step 2: 添加 pre-commit hook

创建 `.husky/pre-commit` 或使用简单的git hook：
```bash
#!/bin/sh
# 在commit前自动构建Vue widgets
cd vue-widgets && npm run build && cd .. && git add web/comfyui/vue-widgets/
```

#### Step 3: 在Python中添加智能检测

在 `__init__.py` 或专门的构建检查模块中：
```python
import os
import subprocess
from pathlib import Path

def check_vue_widgets_build():
    """检查Vue widgets是否已构建，如果需要则自动构建"""
    project_root = Path(__file__).parent
    build_file = project_root / "web/comfyui/vue-widgets/demo-widget.js"
    src_dir = project_root / "vue-widgets/src"

    # 如果构建产物不存在
    if not build_file.exists():
        print("[LoRA Manager] Vue widget build not found, attempting to build...")
        try:
            result = subprocess.run(
                ["npm", "run", "build"],
                cwd=project_root / "vue-widgets",
                capture_output=True,
                timeout=120
            )
            if result.returncode == 0:
                print("[LoRA Manager] ✓ Vue widgets built successfully")
            else:
                print(f"[LoRA Manager] ⚠️  Build failed: {result.stderr.decode()}")
                print("[LoRA Manager] Please run: cd vue-widgets && npm install && npm run build")
        except FileNotFoundError:
            print("[LoRA Manager] ⚠️  Node.js not found. Please install Node.js and run:")
            print("[LoRA Manager]   cd vue-widgets && npm install && npm run build")
        except Exception as e:
            print(f"[LoRA Manager] ⚠️  Build error: {e}")

    # 检查源代码是否比构建产物新（开发模式）
    elif src_dir.exists():
        src_mtime = max(f.stat().st_mtime for f in src_dir.rglob("*") if f.is_file())
        build_mtime = build_file.stat().st_mtime

        if src_mtime > build_mtime:
            print("[LoRA Manager] Source code newer than build, rebuilding...")
            # 同样的构建逻辑
```

#### Step 4: package.json 添加便捷脚本

```json
{
  "scripts": {
    "dev": "vite build --watch",
    "build": "vite build",
    "build:check": "node scripts/check-build.js",
    "typecheck": "vue-tsc --noEmit",
    "prepare": "npm run build"
  }
}
```

---

## 对于不同场景的建议

### 场景A：当前开发阶段（快速验证）
**使用：方案1（提交构建产物）**
```bash
# 1. 移除gitignore
# 2. 构建并提交
cd vue-widgets && npm run build && cd ..
git add -f web/comfyui/vue-widgets/
git commit -m "Add Vue widget build output"
```

### 场景B：多人协作开发
**使用：方案1 + pre-commit hook**
- 提交构建产物保证可用性
- Hook确保开发者不会忘记构建

### 场景C：成熟生产项目
**使用：方案3（GitHub Actions）**
- main分支不含构建产物
- CI自动构建并发布到release
- 用户安装release tag

---

## 立即可用的解决方案

### 最简单方案（推荐现在使用）：

```bash
# 1. 修改 .gitignore，移除构建产物忽略
sed -i '/web\/comfyui\/vue-widgets/d' .gitignore

# 2. 添加源码缓存到gitignore
echo "vue-widgets/node_modules/" >> .gitignore
echo "vue-widgets/.vite/" >> .gitignore

# 3. 确保已构建
cd vue-widgets && npm run build && cd ..

# 4. 提交所有文件
git add .
git commit -m "feat: Add Vue + PrimeVue widget scaffold with demo"
```

这样用户clone后即可直接使用，同时开发者在修改Vue代码后需要手动运行 `npm run build`。

---

## 未来改进

可以考虑：
1. 添加 Husky + lint-staged 自动化pre-commit
2. 添加 GitHub Actions 自动构建和发布
3. 编写安装后检查脚本
4. 在ComfyUI Manager元数据中说明Node.js依赖（如果选择方案2）

---

## 总结

| 方案 | 用户体验 | 开发体验 | Git仓库大小 | 实现难度 |
|------|---------|---------|------------|---------|
| 方案1 | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐ | ⭐⭐⭐⭐⭐ |
| 方案2 | ⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ |
| 方案3 | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐ |
| 方案4 | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐ |

**当前阶段推荐：方案1（提交构建产物）**
**长期推荐：方案1 + 方案4 组合（提交产物 + 智能检测）**

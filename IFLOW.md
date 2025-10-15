# ComfyUI LoRA Manager - iFlow 上下文

## 项目概述

ComfyUI LoRA Manager 是一个全面的工具集，用于简化 ComfyUI 中 LoRA 模型的组织、下载和应用。它提供了强大的功能，如配方管理、检查点组织和一键工作流集成，使模型操作更快、更流畅、更简单。

该项目是一个 Python 后端与 JavaScript 前端结合的 Web 应用程序，既可以作为 ComfyUI 的自定义节点运行，也可以作为独立应用程序运行。

## 项目结构

```
D:\Workspace\ComfyUI\custom_nodes\ComfyUI-Lora-Manager\
├── py/                 # Python 后端代码
│   ├── config.py       # 全局配置
│   ├── lora_manager.py # 主入口点
│   ├── controllers/    # 控制器
│   ├── metadata_collector/ # 元数据收集器
│   ├── middleware/     # 中间件
│   ├── nodes/          # ComfyUI 节点
│   ├── recipes/        # 配方相关
│   ├── routes/         # API 路由
│   ├── services/       # 业务逻辑服务
│   ├── utils/          # 工具函数
│   └── validators/     # 验证器
├── static/             # 静态资源 (CSS, JS, 图片)
├── templates/          # HTML 模板
├── locales/            # 国际化文件
├── tests/              # 测试代码
├── standalone.py       # 独立模式入口
├── requirements.txt    # Python 依赖
├── package.json        # Node.js 依赖和脚本
└── README.md           # 项目说明
```

## 核心组件

### 后端 (Python)

- **主入口**: `py/lora_manager.py` 和 `standalone.py`
- **配置**: `py/config.py` 管理全局配置和路径
- **路由**: `py/routes/` 目录下包含各种 API 路由
- **服务**: `py/services/` 目录下包含业务逻辑，如模型扫描、下载管理等
- **模型管理**: 使用 `ModelServiceFactory` 来管理不同类型的模型 (LoRA, Checkpoint, Embedding)

### 前端 (JavaScript)

- **构建工具**: 使用 Node.js 和 npm 进行依赖管理和测试
- **测试**: 使用 Vitest 进行前端测试

## 构建和运行

### 安装依赖

```bash
# Python 依赖
pip install -r requirements.txt

# Node.js 依赖 (用于测试)
npm install
```

### 运行 (ComfyUI 模式)

作为 ComfyUI 的自定义节点安装后，在 ComfyUI 中启动即可。

### 运行 (独立模式)

```bash
# 使用默认配置运行
python standalone.py

# 指定主机和端口
python standalone.py --host 127.0.0.1 --port 9000
```

### 测试

#### 后端测试

```bash
# 安装开发依赖
pip install -r requirements-dev.txt

# 运行测试
pytest
```

#### 前端测试

```bash
# 运行测试
npm run test

# 运行测试并生成覆盖率报告
npm run test:coverage
```

## 开发约定

- **代码风格**: Python 代码应遵循 PEP 8 规范
- **测试**: 新功能应包含相应的单元测试
- **配置**: 使用 `settings.json` 文件进行用户配置
- **日志**: 使用 Python 标准库 `logging` 模块进行日志记录
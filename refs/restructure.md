# 代码结构优化建议

## 现状分析

当前代码存在以下问题：

1. **责任边界模糊**：
   - base_model_routes.py 包含过多业务逻辑
   - routes_common.py 的 `ModelRouteUtils` 类职责过于宽泛
   - 静态方法的过度使用导致代码难以测试和扩展

2. **代码组织问题**：
   - 文件过大难以维护
   - 业务逻辑和请求处理混合
   - 功能重复和散落在不同文件

## 业界最佳实践

### 1. 清晰的分层架构

```
请求 → Router → Controller → Service → Repository → 数据源
            ↑         ↑          ↑           ↑
            └ 路由和参数验证   业务逻辑   数据访问抽象
```

### 2. 职责分离

- **Router**: 仅负责URL映射到控制器方法
- **Controller**: 处理HTTP请求/响应，参数验证
- **Service**: 实现业务逻辑
- **Repository**: 数据访问和持久化

## 具体重构建议

### 1. 拆分 routes_common.py 为多个领域服务

```python
# 拆分为多个服务类，例如:
class ModelMetadataService:
    """处理模型元数据相关操作"""
    
    async def load_local_metadata(self, metadata_path):
        # 实现...

class ModelFileService:
    """处理模型文件操作"""
    
    async def delete_model_files(self, target_dir, file_name):
        # 实现...

class ModelPreviewService:
    """处理模型预览图相关操作"""
    
    async def replace_preview(self, model_path, preview_data, nsfw_level):
        # 实现...
```

### 2. 改造 base_model_routes.py 为纯控制器

```python
class BaseModelController:
    """基础模型控制器，仅处理HTTP请求/响应"""
    
    def __init__(self, model_service, metadata_service, file_service):
        self.model_service = model_service
        self.metadata_service = metadata_service
        self.file_service = file_service
    
    async def handle_delete_model(self, request):
        """处理模型删除请求"""
        data = await request.json()
        file_path = data.get('file_path')
        
        if not file_path:
            return web.Response(text='Model path is required', status=400)
            
        result = await self.file_service.delete_model(file_path)
        return web.json_response(result)
```

### 3. 创建专门的验证层

```python
class RequestValidator:
    """请求验证类"""
    
    def validate_delete_request(self, data):
        if not data.get('file_path'):
            raise ValidationError('Model path is required')
        return data
```

### 4. 改进路由注册方式

```python
def setup_routes(app, services_container):
    """更模块化的路由注册"""
    # 注入依赖的服务
    model_controller = BaseModelController(
        services_container.model_service,
        services_container.metadata_service,
        services_container.file_service
    )
    
    # 路由注册
    app.router.add_post('/api/models/delete', model_controller.handle_delete_model)
    # 更多路由...
```

### 5. 领域驱动的目录结构

```
py/
├── controllers/              # HTTP请求处理
│   ├── base_controller.py
│   ├── model_controller.py
│   └── ...
├── services/                 # 业务逻辑
│   ├── metadata_service.py
│   ├── file_service.py 
│   └── ...
├── repositories/             # 数据访问
│   ├── model_repository.py
│   └── ...
├── utils/                    # 通用工具
├── validators/               # 请求验证
└── routes/                   # 路由定义
```

### 6. 减少对静态方法的依赖

将 `ModelRouteUtils` 改为可实例化的服务类，使用依赖注入模式：

```python
# 改造前
result = await ModelRouteUtils.handle_delete_model(request, scanner)

# 改造后
model_file_service = ModelFileService(scanner)
result = await model_file_service.handle_delete_model(request.json())
```
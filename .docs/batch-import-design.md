# Recipe Batch Import Feature Design

## Overview
Enable users to import multiple images as recipes in a single operation, rather than processing them individually. This feature addresses the need for efficient bulk recipe creation from existing image collections.

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        Frontend                                  │
├─────────────────────────────────────────────────────────────────┤
│  BatchImportManager.js                                          │
│  ├── InputCollector (收集URL列表/目录路径)                        │
│  ├── ConcurrencyController (自适应并发控制)                       │
│  ├── ProgressTracker (进度追踪)                                   │
│  └── ResultAggregator (结果汇总)                                  │
├─────────────────────────────────────────────────────────────────┤
│  batch_import_modal.html                                        │
│  └── 批量导入UI组件                                              │
├─────────────────────────────────────────────────────────────────┤
│  batch_import_progress.css                                      │
│  └── 进度显示样式                                                │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                        Backend                                   │
├─────────────────────────────────────────────────────────────────┤
│  py/routes/handlers/recipe_handlers.py                          │
│  ├── start_batch_import() - 启动批量导入                         │
│  ├── get_batch_import_progress() - 查询进度                      │
│  └── cancel_batch_import() - 取消导入                            │
├─────────────────────────────────────────────────────────────────┤
│  py/services/batch_import_service.py                            │
│  ├── 自适应并发执行                                              │
│  ├── 结果汇总                                                    │
│  └── WebSocket进度广播                                           │
└─────────────────────────────────────────────────────────────────┘
```

## API Endpoints

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/lm/recipes/batch-import/start` | POST | 启动批量导入，返回 operation_id |
| `/api/lm/recipes/batch-import/progress` | GET | 查询进度状态 |
| `/api/lm/recipes/batch-import/cancel` | POST | 取消导入 |

## Backend Implementation Details

### BatchImportService

Location: `py/services/batch_import_service.py`

Key classes:
- `BatchImportItem`: Dataclass for individual import item
- `BatchImportProgress`: Dataclass for tracking progress
- `BatchImportService`: Main service class

Features:
- Adaptive concurrency control (adjusts based on success/failure rate)
- WebSocket progress broadcasting
- Graceful error handling (individual failures don't stop the batch)
- Result aggregation

### WebSocket Message Format

```json
{
    "type": "batch_import_progress",
    "operation_id": "xxx",
    "total": 50,
    "completed": 23,
    "success": 21,
    "failed": 2,
    "skipped": 0,
    "current_item": "image_024.png",
    "status": "running"
}
```

### Input Types

1. **URL List**: Array of URLs (http/https)
2. **Local Paths**: Array of local file paths
3. **Directory**: Path to directory with optional recursive flag

### Error Handling

- Invalid URLs/paths: Skip and record error
- Download failures: Record error, continue
- Metadata extraction failures: Mark as "no metadata"
- Duplicate detection: Option to skip duplicates

## Frontend Implementation Details (TODO)

### UI Components

1. **BatchImportModal**: Main modal with tabs for URLs/Directory input
2. **ProgressDisplay**: Real-time progress bar and status
3. **ResultsSummary**: Final results with success/failure breakdown

### Adaptive Concurrency Controller

```javascript
class AdaptiveConcurrencyController {
    constructor(options = {}) {
        this.minConcurrency = options.minConcurrency || 1;
        this.maxConcurrency = options.maxConcurrency || 5;
        this.currentConcurrency = options.initialConcurrency || 3;
    }

    adjustConcurrency(taskDuration, success) {
        if (success && taskDuration < 1000 && this.currentConcurrency < this.maxConcurrency) {
            this.currentConcurrency = Math.min(this.currentConcurrency + 1, this.maxConcurrency);
        }
        if (!success || taskDuration > 10000) {
            this.currentConcurrency = Math.max(this.currentConcurrency - 1, this.minConcurrency);
        }
        return this.currentConcurrency;
    }
}
```

## File Structure

```
Backend (implemented):
├── py/services/batch_import_service.py            # 后端服务
├── py/routes/handlers/batch_import_handler.py     # API处理器 (added to recipe_handlers.py)
├── tests/services/test_batch_import_service.py    # 单元测试
└── tests/routes/test_batch_import_routes.py       # API集成测试

Frontend (TODO):
├── static/js/managers/BatchImportManager.js       # 主管理器
├── static/js/managers/batch/                       # 子模块
│   ├── ConcurrencyController.js                    # 并发控制
│   ├── ProgressTracker.js                          # 进度追踪
│   └── ResultAggregator.js                         # 结果汇总
├── static/css/components/batch-import-modal.css   # 样式
└── templates/components/batch_import_modal.html    # Modal模板
```

## Implementation Status

- [x] Backend BatchImportService
- [x] Backend API handlers
- [x] WebSocket progress broadcasting
- [x] Unit tests
- [x] Integration tests
- [ ] Frontend BatchImportManager
- [ ] Frontend UI components
- [ ] E2E tests
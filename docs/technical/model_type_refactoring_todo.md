# Model Type 字段重构 - 遗留工作清单

> **状态**: Phase 1-4 已完成 | **创建日期**: 2026-01-30  
> **相关文件**: `py/utils/models.py`, `py/services/model_query.py`, `py/services/checkpoint_scanner.py`, etc.

---

## 概述

本次重构旨在解决 `model_type` 字段语义不统一的问题。系统中有两个层面的"类型"概念：

1. **Scanner Type** (`scanner_type`): 架构层面的大类 - `lora`, `checkpoint`, `embedding`
2. **Sub Type** (`sub_type`): 业务层面的细分类型 - `lora`/`locon`/`dora`, `checkpoint`/`diffusion_model`, `embedding`

重构目标是统一使用 `sub_type` 表示细分类型，保留 `model_type` 作为向后兼容的别名。

---

## 已完成工作 ✅

### Phase 1: 后端字段重命名
- [x] `CheckpointMetadata.model_type` → `sub_type`
- [x] `EmbeddingMetadata.model_type` → `sub_type`
- [x] `model_scanner.py` `_build_cache_entry()` 同时处理 `sub_type` 和 `model_type`

### Phase 2: 查询逻辑更新
- [x] `model_query.py` 新增 `resolve_sub_type()` 和 `normalize_sub_type()`
- [x] ~~保持向后兼容的别名 `resolve_civitai_model_type`, `normalize_civitai_model_type`~~ (已在 Phase 5 移除)
- [x] `ModelFilterSet.apply()` 更新为使用新的解析函数

### Phase 3: API 响应更新
- [x] `LoraService.format_response()` 返回 `sub_type` ~~+ `model_type`~~ (已移除 `model_type`)
- [x] `CheckpointService.format_response()` 返回 `sub_type` ~~+ `model_type`~~ (已移除 `model_type`)
- [x] `EmbeddingService.format_response()` 返回 `sub_type` ~~+ `model_type`~~ (已移除 `model_type`)

### Phase 4: 前端更新
- [x] `constants.js` 新增 `MODEL_SUBTYPE_DISPLAY_NAMES`
- [x] `MODEL_TYPE_DISPLAY_NAMES` 作为别名保留

### Phase 5: 清理废弃代码 ✅
- [x] 从 `ModelScanner._build_cache_entry()` 中移除 `model_type` 向后兼容代码
- [x] 从 `CheckpointScanner` 中移除 `model_type` 兼容处理
- [x] 从 `model_query.py` 中移除 `resolve_civitai_model_type` 和 `normalize_civitai_model_type` 别名
- [x] 更新前端 `FilterManager.js` 使用 `sub_type` (已在使用 `MODEL_SUBTYPE_DISPLAY_NAMES`)
- [x] 更新所有相关测试

---

## 遗留工作 ⏳

### Phase 5: 清理废弃代码 ✅ **已完成**

所有 Phase 5 的清理工作已完成：

#### 5.1 移除 `model_type` 字段的向后兼容代码 ✅
- 从 `ModelScanner._build_cache_entry()` 中移除了 `model_type` 的设置
- 现在只设置 `sub_type` 字段

#### 5.2 移除 CheckpointScanner 的 model_type 兼容处理 ✅
- `adjust_metadata()` 现在只处理 `sub_type`
- `adjust_cached_entry()` 现在只设置 `sub_type`

#### 5.3 移除 model_query 中的向后兼容别名 ✅
- 移除了 `resolve_civitai_model_type = resolve_sub_type`
- 移除了 `normalize_civitai_model_type = normalize_sub_type`

#### 5.4 前端清理 ✅
- `FilterManager.js` 已经在使用 `MODEL_SUBTYPE_DISPLAY_NAMES` (通过别名 `MODEL_TYPE_DISPLAY_NAMES`)
- API list endpoint 现在只返回 `sub_type`，不再返回 `model_type`
- `ModelCard.js` 现在设置 `card.dataset.sub_type` (所有模型类型通用)
- `CheckpointContextMenu.js` 现在读取 `card.dataset.sub_type`
- `MoveManager.js` 现在处理 `cache_entry.sub_type`
- `RecipeModal.js` 现在读取 `checkpoint.sub_type`

---

## 数据库迁移评估

### 当前状态
- `persistent_model_cache.py` 使用 `civitai_model_type` 列存储 CivitAI 原始类型
- 缓存 entry 中的 `sub_type` 在运行期动态计算
- 数据库 schema **无需立即修改**

### 未来可选优化
```sql
-- 可选：在 models 表中添加 sub_type 列（与 civitai_model_type 保持一致但语义更清晰）
ALTER TABLE models ADD COLUMN sub_type TEXT;

-- 数据迁移
UPDATE models SET sub_type = civitai_model_type WHERE sub_type IS NULL;
```

**建议**: 如果决定添加 `sub_type` 列，应与 Phase 5 一起进行。

---

## 测试覆盖率

### 新增/更新测试文件（已全部通过 ✅）

| 测试文件 | 数量 | 覆盖内容 |
|---------|------|---------|
| `tests/utils/test_models_sub_type.py` | 7 | Metadata sub_type 字段 |
| `tests/services/test_model_query_sub_type.py` | 19 | sub_type 解析和过滤 |
| `tests/services/test_checkpoint_scanner_sub_type.py` | 6 | CheckpointScanner sub_type |
| `tests/services/test_service_format_response_sub_type.py` | 6 | API 响应 sub_type 包含 |
| `tests/services/test_checkpoint_scanner.py` | 1 | Checkpoint 缓存 sub_type |
| `tests/services/test_model_scanner.py` | 1 | adjust_cached_entry hook |
| `tests/services/test_download_manager.py` | 1 | Checkpoint 下载 sub_type |

### 需要补充的测试（可选）

- [ ] 集成测试：验证前端过滤使用 sub_type 字段
- [ ] 数据库迁移测试（如果执行可选优化）
- [ ] 性能测试：确认 resolve_sub_type 的优先级查找没有显著性能影响

---

## 兼容性检查清单

### 已完成 ✅

- [x] 前端代码已全部改用 `sub_type` 字段
- [x] API list endpoint 已移除 `model_type`，只返回 `sub_type`
- [x] 后端 cache entry 已移除 `model_type`，只保留 `sub_type`
- [x] 所有测试已更新通过
- [x] 文档已更新

---

## 相关文件清单

### 核心文件
```
py/utils/models.py
py/utils/constants.py
py/services/model_scanner.py
py/services/model_query.py
py/services/checkpoint_scanner.py
py/services/base_model_service.py
py/services/lora_service.py
py/services/checkpoint_service.py
py/services/embedding_service.py
```

### 前端文件
```
static/js/utils/constants.js
static/js/managers/FilterManager.js
static/js/managers/MoveManager.js
static/js/components/shared/ModelCard.js
static/js/components/ContextMenu/CheckpointContextMenu.js
static/js/components/RecipeModal.js
```

### 测试文件
```
tests/utils/test_models_sub_type.py
tests/services/test_model_query_sub_type.py
tests/services/test_checkpoint_scanner_sub_type.py
tests/services/test_service_format_response_sub_type.py
```

---

## 风险评估

| 风险项 | 影响 | 缓解措施 |
|-------|------|---------|
| ~~第三方代码依赖 `model_type`~~ | ~~高~~ | ~~保持别名至少 1 个 major 版本~~ ✅ 已完成移除 |
| ~~数据库 schema 变更~~ | ~~中~~ | ~~暂缓 schema 变更，仅运行时计算~~ ✅ 无需变更 |
| ~~前端过滤失效~~ | ~~中~~ | ~~全面的集成测试覆盖~~ ✅ 测试通过 |
| CivitAI API 变化 | 低 | 保持多源解析策略 |

---

## 时间线

- **v1.x**: Phase 1-4 已完成，保持向后兼容
- **v2.0 (当前)**: ✅ Phase 5 已完成 - `model_type` 兼容代码已移除
  - API list endpoint 只返回 `sub_type`
  - Cache entry 只保留 `sub_type`
  - 移除了 `resolve_civitai_model_type` 和 `normalize_civitai_model_type` 别名

---

## 备注

- 重构期间发现 `civitai_model_type` 数据库列命名尚可，但语义上应理解为存储 CivitAI API 返回的原始类型值
- Checkpoint 的 `diffusion_model` sub_type 不能通过 CivitAI API 获取，必须通过文件路径（model root）判断
- LoRA 的 sub_type（lora/locon/dora）直接来自 CivitAI API 的 `version_info.model.type`

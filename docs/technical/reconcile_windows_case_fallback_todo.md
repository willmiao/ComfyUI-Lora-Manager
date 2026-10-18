# Reconcile 的 Windows 大小写回退分支

> **状态**: 已改为 O(1) 索引（2026-10-06），不再需要 Windows 机器验证 | **创建日期**: 2026-09-11
> **相关文件**: `py/services/model_scanner.py`（`_walk_root_for_reconcile` / `_CachedPathLookups`）
> **相关历史**: #871 (`76ee59cd`, 路径重叠去重)、#1108 (按文件夹扫描的需求)

---

## 背景

Refresh 按钮走的是 `_reconcile_cache()`（快速增量对账）。2026-09-11 做了一轮性能优化，把两处"预防性"的
realpath 全量遍历改成按需触发。清理时留下的唯一可疑点，是 Windows 专属的大小写不敏感回退分支：它排在
精确匹配和 realpath 别名匹配之后，只有**未命中**的文件才会走到，但一旦走到就是 O(文件数 × 缓存条目数)。

---

## 现状（已改造）

分支语义保持不变，查找改为 O(1)：

```python
if _CASE_INSENSITIVE_PATHS:                       # 模块级常量，默认 os.name == "nt"
    cached_case_match = lookups.match_casefold_path(file_path)
```

`lookups` 是 `_CachedPathLookups`：小写索引 `{lower(cached_path): cached_path}` 在第一次未命中时构建一次
（与 realpath 别名索引同样懒构建，并用 `threading.Lock` 护住——walk 现在跑在工作线程里），之后每次未命中
只做一次字典查询。

`_CASE_INSENSITIVE_PATHS` 提成模块级常量的原因：这条分支在 Linux 上原本被 `os.name == 'nt'` 短路、没有任何
测试覆盖；现在测试可以 monkeypatch 该常量，在 Linux 上真实执行这条分支。

---

## 待办

- [x] **消除 O(N×M)**：改成懒构建的小写索引，查询降为 O(1)。
- [x] **补回归测试**：`tests/services/test_model_scanner.py::test_reconcile_case_fold_fallback_is_indexed_not_linear`
      （缓存路径与磁盘仅大小写不同、realpath 别名不命中 → 断言条目保留、不重新处理、索引只构建一次）。
- [x] 回填本文件。
- [ ] （可选，纯代码瘦身）在 Windows 上确认 realpath 别名匹配是否已覆盖全部情形；若确认该分支不可达，
      可以整体删掉这一层。它现在的成本已经可以忽略，删除不再是性能问题。

---

## 验证方法（可选，Windows）

1. 构造"缓存路径与磁盘真实大小写不一致"的场景（改过盘符大小写、迁移过 `settings.json` 与持久化缓存），点 Refresh。
2. 日志判据：`Cache reconciliation completed in X seconds. Added 0, removed 0 models.`，且**没有**
   `Found N new files to process` / `Processing <path>`。
3. 跑测试：`python -m pytest tests/services/test_model_scanner.py -k reconcile`。

---

## 已完成（历史，供对照）

2026-09-11 那轮清理里在 Linux（5 万文件库）验证过的部分：

- `cached_real_paths` 别名映射改为**首次未命中时**懒构建（原来每次 Refresh 都对全部缓存条目算一次 realpath）。
- 每个文件的 `realpath` 移到精确命中检查**之后**（原来对每个文件都算，命中即丢弃）。
- `get_model_roots()` 在新增文件处理阶段只快照一次（原来每个新文件重读一次）。
- 全量去重 pass 加了 O(1) 前置判断（`cached_size_before != len(cached_paths) or total_added > 0`）。

结果：零变更 Refresh 5 万文件 **~1400 ms → ~120 ms**；根目录顺序/符号链接别名翻转场景仍是
`re-processed=0`。

---

## 2026-10-06 追加：walk 阶段的并发与进度

同一次改动还做了两件事（与大小写分支无关，但都动到了同一段 walk 循环，故一并记录）：

- walk 循环抽成同步函数 `_walk_root_for_reconcile()`，并按设备分组
  （`_root_device_key()` / `_group_roots_by_device()`）在工作线程里并行执行：同一设备内的 root 仍按配置顺序
  串行（保证目录认领与去重的确定性），不同设备之间才并行。结果回到事件循环后按**配置的 root 顺序**合并，
  因此"同一个文件可达多条业务路径时谁胜出"与并发完成顺序无关。
- walk 阶段按 root 广播进度：`_ReconcileWalkTracker` 以「该 root 的缓存条目数」为权重估算进度（真实文件数
  只有走完才知道），进度条把 walk 记为 0-50%，新增文件处理阶段顺延为 50-99%，两段之间不会回退。

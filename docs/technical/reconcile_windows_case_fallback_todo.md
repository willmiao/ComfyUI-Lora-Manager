# Reconcile 的 Windows 大小写回退分支 - 待验证清单

> **状态**: 待 Windows 环境验证 | **创建日期**: 2026-09-11
> **相关文件**: `py/services/model_scanner.py` (`ModelScanner._reconcile_cache`)
> **相关历史**: #871 (`76ee59cd`, 路径重叠去重)、#1108 (按文件夹扫描的需求)

---

## 背景

Refresh 按钮走的是 `_reconcile_cache()`（快速增量对账）。2026-09-11 做了一轮性能优化，把两处"预防性"的
realpath 全量遍历改成按需触发（详见下方"已完成"）。优化后，一次零变更 Refresh 在 5 万文件库上从
~1400 ms 降到 ~120 ms。

清理过程中发现**唯一一处遗留的可疑点**：Windows 专属的大小写不敏感回退分支。它无法在 Linux 上验证，
因此单独记录，留待 Windows 机器上确认。

---

## 待验证分支（现状）

`py/services/model_scanner.py` 中 `_reconcile_cache()` 的 walk 循环内：

```python
# Try case-insensitive match on Windows
if os.name == 'nt':
    lower_path = file_path.lower()
    matched = False
    for cached_path in cached_paths:          # 每个未命中文件都全量扫一遍缓存
        if cached_path.lower() == lower_path:
            found_paths.add(cached_path)
            matched = True
            break
    if matched:
        continue
```

它排在精确匹配（`file_path in cached_paths`）和 realpath 别名匹配之后，只有**未命中**的文件才会走到。

### 为什么可疑

1. **可能不可达**：Windows 上 `os.path.realpath()` 会返回磁盘上的真实大小写，因此"缓存路径大小写与磁盘
   不一致"的情形，理论上已经被上一步的 realpath 别名匹配覆盖。若如此，这段就是纯冗余代码。
2. **一旦可达就是 O(N×M)**：每个未命中文件都要遍历全部 `cached_paths` 做小写比较。若某种路径写法让
   整个库都变成"未命中"（例如缓存里的盘符/大小写形式与 walk 结果系统性不一致），一次 Refresh 会退化
   成 文件数 × 缓存条目数 次字符串比较，比真实 IO 还贵。
3. **没有测试覆盖**：`tests/services/test_model_scanner.py` 没有任何针对该分支的用例（它在 Linux 上
   被 `os.name == 'nt'` 短路，无法覆盖）。

---

## 待办

- [ ] **验证可达性**：在 Windows 上构造"缓存路径与磁盘真实大小写不一致"的场景，确认 realpath 别名匹配
      是否已经命中，即上面的 `if os.name == 'nt'` 分支是否还有进入的必要。
- [ ] **若不可达 / 冗余**：删除该分支，并在删除处留注释说明 realpath 已覆盖大小写归一（附验证记录）。
- [ ] **若可达**：保留语义但改成 O(1)——预先构建一次 `lower_path -> cached_path` 映射（与
      `cached_real_paths` 同样按需、懒构建），把内层全量扫描换成一次字典查询。
- [ ] **补一个 Windows-only 的回归测试**（`pytest.mark.skipif(os.name != "nt", ...)`），锁定最终结论。
- [ ] 把验证结论回填到本文件，并同步更新状态行。

---

## 验证方法（Windows）

1. **构造不一致的大小写**：让缓存里的 `file_path` 与磁盘实际路径大小写不同（例如改过盘符/目录大小写，
   或从另一台机器迁移了 `settings.json` 与持久化缓存），然后在 UI 点 Refresh。
2. **看后端日志判据**：
   - 若 realpath 已覆盖 → 日志应显示 `Cache reconciliation completed in X seconds. Added 0, removed 0 models.`，
     且**没有** `Found N new files to process` / `Processing <path>`。
   - 若回退分支在起作用 → 同样应该是 `Added 0, removed 0`（因为 `found_paths` 被补上），这是"分支可达"
     的证据；反之若出现大量 `Processing ...` 并重新 hash，说明连回退分支也没命中，问题更严重
     （缓存路径被当成了新文件 + 旧条目被删）。
3. **跑测试**：`python -m pytest tests/services/test_model_scanner.py -k reconcile`（该文件在 Windows 上会
   真实执行 `os.name == 'nt'` 分支）。
4. **量化**：如果需要，可在 `_reconcile_cache` 里临时插桩统计该分支的进入次数与内层迭代次数，确认是否为 0。

---

## 已完成（本轮优化，供对照）

同一次清理里已经落地并验证的部分（Linux，5 万文件库）：

- `cached_real_paths` 别名映射改为**首次未命中时**懒构建（原来每次 Refresh 都对全部缓存条目算一次 realpath）。
- 每个文件的 `realpath` 移到精确命中检查**之后**（原来对每个文件都算，命中即丢弃）。
- `get_model_roots()` 在新增文件处理阶段只快照一次（原来每个新文件重读一次）。
- 全量去重 pass 加了 O(1) 前置判断（`cached_size_before != len(cached_paths) or total_added > 0`），
  零变更且缓存干净时跳过；快照本身含重复路径时仍会自愈。

结果：零变更 Refresh 5 万文件 **~1400 ms → ~120 ms**；根目录顺序/符号链接别名翻转场景仍是
`re-processed=0`（不重新读 metadata、不重新 hash）。测试：`tests/services/test_model_scanner.py`
47 项、全量后端 2567 项全部通过。

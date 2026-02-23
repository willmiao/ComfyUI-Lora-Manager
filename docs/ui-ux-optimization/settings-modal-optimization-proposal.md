# Settings Modal UI/UX Optimization

## Overview
随着Settings功能的不断增加，当前的单列表长页面设计已难以高效浏览和定位设置项。本方案旨在通过专业的UI/UX优化，在保持原有设计语言的前提下，大幅提升用户体验。

## Goals
1. **提升浏览效率**：用户能够快速定位和修改设置
2. **保持设计一致性**：延续现有的颜色、间距、动画系统
3. **渐进式增强**：分阶段实施，降低风险
4. **向后兼容**：不影响现有功能逻辑

## Design Principles
- **贴近原有设计语言**：使用现有CSS变量和样式模式
- **最小化风格改动**：在提升UX的同时保持视觉风格稳定
- **渐进增强**：优先核心功能，次要功能逐步添加

---

## Optimization Phases

### Phase 0: 左侧导航栏 + 两栏布局 (P0)
**Status**: In Progress

#### Goals
- 解决核心痛点：设置项过多导致的浏览困难
- 建立清晰的视觉层次和信息架构

#### Implementation Details

##### Layout Changes
```
┌─────────────────────────────────────────────────────────────┐
│  Settings                                    [×]            │
├──────────────┬──────────────────────────────────────────────┤
│  NAVIGATION  │  CONTENT                                     │
│              │                                              │
│  ▶ General   │  ┌─────────────────────────────────────────┐ │
│    Interface │  │ Section: General                        │ │
│    Download  │  │ ┌─────────────────────────────────────┐ │ │
│    Advanced  │  │ │ Setting Item 1                      │ │ │
│              │  │ └─────────────────────────────────────┘ │ │
│              │  │ ┌─────────────────────────────────────┐ │ │
│              │  │ │ Setting Item 2                      │ │ │
│              │  │ └─────────────────────────────────────┘ │ │
│              │  └─────────────────────────────────────────┘ │
│              │                                              │
│              │  ┌─────────────────────────────────────────┐ │
│              │  │ Section: Interface                      │ │
│              │  │ ...                                     │ │
│              │  └─────────────────────────────────────────┘ │
└──────────────┴──────────────────────────────────────────────┘
```

##### Technical Specifications
- **Modal Width**: 从700px扩展至950px
- **Left Sidebar**: 200px固定宽度，独立滚动
- **Right Content**: flex: 1，独立滚动
- **Height**: 固定80vh，确保内容可见
- **Responsive**: 移动端自动切换为单栏布局

##### Navigation Items
基于当前Settings结构，导航项分为4组：

1. **通用** (General)
   - Language
   - Storage Location

2. **界面** (Interface)
   - Layout Settings
   - Video Settings
   - Content Filtering

3. **下载** (Download)
   - Download Path Templates
   - Example Images
   - Update Flags

4. **高级** (Advanced)
   - Priority Tags
   - Auto-organize
   - Metadata Archive
   - Proxy Settings
   - Misc

##### Interactive Features
- **点击导航**：平滑滚动到对应Section
- **当前高亮**：根据滚动位置高亮当前Section
- **平滑滚动**：使用scroll-behavior: smooth

##### CSS Variables Usage
延续使用现有变量系统：
- `--lora-accent`: 高亮色
- `--lora-border`: 边框色
- `--card-bg`: 卡片背景
- `--text-color`: 文字颜色
- `--space-1` to `--space-4`: 间距系统
- `--border-radius-xs/sm`: 圆角系统

---

### Phase 1: Section折叠/展开 (P1)
**Status**: Planned

#### Goals
- 进一步减少视觉负担
- 允许用户自定义信息密度

#### Implementation Details
- 点击Section标题折叠/展开
- 添加chevron图标旋转动画
- 记忆用户折叠状态(localStorage)

---

### Phase 2: 顶部搜索栏 (P1)
**Status**: Planned

#### Goals
- 快速定位特定设置项
- 支持关键词搜索设置标签和描述

#### Implementation Details
- 实时过滤显示匹配项
- 高亮匹配的关键词
- 使用现有的text-input-wrapper样式

---

### Phase 3: 视觉层次优化 (P2)
**Status**: Planned

#### Goals
- 提升可读性
- 强化Section的视觉区分

#### Implementation Details
- Section标题左侧添加accent色边框
- 设置项标签加粗处理
- 增大Section间距

---

### Phase 4: 快速操作按钮 (P3)
**Status**: Planned

#### Goals
- 增强功能完整性
- 提供批量操作能力

#### Implementation Details
- 重置为默认按钮
- 导出配置按钮
- 导入配置按钮

---

## Files to Modify

### Phase 0 Files
1. `static/css/components/modal/settings-modal.css`
   - 新增两栏布局样式
   - 新增导航栏样式
   - 调整Modal尺寸

2. `templates/components/modals/settings_modal.html`
   - 重构HTML结构为两栏布局
   - 添加导航列表
   - 为Section添加ID锚点

3. `static/js/managers/SettingsManager.js`
   - 添加导航点击处理
   - 添加滚动监听高亮
   - 添加平滑滚动行为

---

## Success Criteria

### Phase 0
- [ ] Modal显示为两栏布局
- [ ] 左侧导航可点击跳转
- [ ] 当前Section在导航中高亮
- [ ] 滚动时高亮状态同步更新
- [ ] 移动端响应式正常
- [ ] 所有现有功能正常工作
- [ ] 设计风格与原有UI一致

---

## Timeline

| Phase | Estimated Time | Status |
|-------|---------------|--------|
| P0    | 2-3 hours     | In Progress |
| P1    | 1-2 hours     | Planned |
| P2    | 1-2 hours     | Planned |
| P3    | 1 hour        | Planned |

---

## Notes
- 所有修改优先使用现有CSS变量
- 保持向后兼容，不破坏现有功能
- 每次Phase完成后进行功能测试
- 遵循现有代码风格和命名约定

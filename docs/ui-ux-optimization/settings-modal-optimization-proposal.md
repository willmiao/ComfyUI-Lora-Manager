# Settings Modal UI/UX Optimization

## Overview
当前Settings Modal采用单列表长页面设计，随着设置项不断增加，已难以高效浏览和定位。本方案采用 **macOS Settings 模式**（左侧导航 + 右侧单Section独占显示），在保持原有设计语言的前提下，重构信息架构，大幅提升用户体验。

## Goals
1. **提升浏览效率**：用户能够快速定位和修改设置
2. **保持设计一致性**：延续现有的颜色、间距、动画系统
3. **简化交互模型**：移除冗余元素（SETTINGS label、折叠功能）
4. **清晰的视觉层次**：Section级导航，右侧独占显示
5. **向后兼容**：不影响现有功能逻辑

## Design Principles
- **macOS Settings模式**：点击左侧导航，右侧仅显示该Section内容
- **贴近原有设计语言**：使用现有CSS变量和样式模式
- **最小化风格改动**：在提升UX的同时保持视觉风格稳定
- **简化优于复杂**：移除不必要的折叠/展开交互

---

## New Design Architecture

### Layout Structure
```
┌─────────────────────────────────────────────────────────────┐
│  Settings                                    [×]            │
├──────────────┬──────────────────────────────────────────────┤
│  NAVIGATION  │  CONTENT                                     │
│              │                                              │
│  General   → │  ┌─────────────────────────────────────────┐ │
│  Interface   │  │ General                                 │ │
│  Download    │  │ ═══════════════════════════════════════ │ │
│  Advanced    │  │                                           │ │
│              │  │ ┌─────────────────────────────────────┐   │ │
│              │  │ │ Civitai API Key                     │   │ │
│              │  │ │ [                         ] [?]     │   │ │
│              │  │ └─────────────────────────────────────┘   │ │
│              │  │                                           │ │
│              │  │ ┌─────────────────────────────────────┐   │ │
│              │  │ │ Settings Location                   │   │ │
│              │  │ │ [/path/to/settings]     [Browse]    │   │ │
│              │  │ └─────────────────────────────────────┘   │ │
│              │  └─────────────────────────────────────────┘ │
│              │                                              │
│              │  [Cancel]                    [Save Changes]  │
└──────────────┴──────────────────────────────────────────────┘
```

### Key Design Decisions

#### 1. 移除冗余元素
- ❌ 删除 sidebar 中的 "SETTINGS" label
- ❌ **取消折叠/展开功能**（增加交互成本，无实际收益）
- ❌ 不再在左侧导航显示具体设置项（减少认知负荷）

#### 2. 导航简化
- 左侧仅显示 **4个Section**（General / Interface / Download / Advanced）
- 当前选中项用 accent 色 background highlight
- 无需滚动监听，点击即切换

#### 3. 右侧单Section独占
- 点击左侧导航，右侧仅显示该Section的所有设置项
- Section标题作为页面标题（大号字体 + accent色下划线）
- 所有设置项平铺展示，无需折叠

#### 4. 视觉层次
```
Section Header (20px, bold, accent underline)
├── Setting Group (card container, subtle border)
│   ├── Setting Label (14px, semibold)
│   ├── Setting Description (12px, muted color)
│   └── Setting Control (input/select/toggle)
```

---

## Optimization Phases

### Phase 0: macOS Settings模式重构 (P0)
**Status**: Ready for Development
**Priority**: High

#### Goals
- 重构为两栏布局（左侧导航 + 右侧内容）
- 实现Section级导航切换
- 优化视觉层次和间距
- 移除冗余元素

#### Implementation Details

##### Layout Specifications
| Element | Specification |
|---------|--------------|
| Modal Width | 800px (比原700px稍宽) |
| Modal Height | 600px (固定高度) |
| Left Sidebar | 200px 固定宽度 |
| Right Content | flex: 1，自动填充 |
| Content Padding | --space-3 (24px) |

##### Navigation Structure
```
General (通用)
├── Language
├── Civitai API Key
└── Settings Location

Interface (界面)
├── Layout Settings
├── Video Settings
└── Content Filtering

Download (下载)
├── Folder Settings
├── Download Path Templates
├── Example Images
└── Update Flags

Advanced (高级)
├── Priority Tags
├── Auto-organize exclusions
├── Metadata refresh skip paths
├── Metadata Archive Database
├── Proxy Settings
└── Misc
```

##### CSS Style Guide

**Section Header**
```css
.settings-section-header {
  font-size: 20px;
  font-weight: 600;
  padding-bottom: var(--space-2);
  border-bottom: 2px solid var(--lora-accent);
  margin-bottom: var(--space-3);
}
```

**Setting Group (Card)**
```css
.settings-group {
  background: var(--card-bg);
  border: 1px solid var(--lora-border);
  border-radius: var(--border-radius-sm);
  padding: var(--space-3);
  margin-bottom: var(--space-3);
}
```

**Setting Item**
```css
.setting-item {
  margin-bottom: var(--space-3);
}

.setting-item:last-child {
  margin-bottom: 0;
}

.setting-label {
  font-size: 14px;
  font-weight: 500;
  margin-bottom: var(--space-1);
}

.setting-description {
  font-size: 12px;
  color: var(--text-muted);
  margin-bottom: var(--space-2);
}
```

**Sidebar Navigation**
```css
.settings-nav-item {
  padding: var(--space-2) var(--space-3);
  border-radius: var(--border-radius-xs);
  cursor: pointer;
  transition: background 0.2s ease;
}

.settings-nav-item:hover {
  background: rgba(255, 255, 255, 0.05);
}

.settings-nav-item.active {
  background: var(--lora-accent);
  color: white;
}
```

#### Files to Modify

1. **static/css/components/modal/settings-modal.css**
   - [ ] 新增两栏布局样式
   - [ ] 新增侧边栏导航样式
   - [ ] 新增Section标题样式
   - [ ] 调整设置项卡片样式
   - [ ] 移除折叠相关的CSS

2. **templates/components/modals/settings_modal.html**
   - [ ] 重构为两栏HTML结构
   - [ ] 添加4个导航项
   - [ ] 将Section改为独立内容区域
   - [ ] 移除折叠按钮HTML

3. **static/js/managers/SettingsManager.js**
   - [ ] 添加导航点击切换逻辑
   - [ ] 添加Section显示/隐藏控制
   - [ ] 移除折叠/展开相关代码
   - [ ] 默认显示第一个Section

---

### Phase 1: 搜索功能 (P1)
**Status**: Planned
**Priority**: Medium

#### Goals
- 快速定位特定设置项
- 支持关键词搜索设置标签和描述

#### Implementation
- 搜索框保持在顶部右侧
- 实时过滤：显示匹配的Section和设置项
- 高亮匹配的关键词
- 无结果时显示友好提示

---

### Phase 2: 操作按钮优化 (P2)
**Status**: Planned
**Priority**: Low

#### Goals
- 增强功能完整性
- 提供批量操作能力

#### Implementation
- 底部固定操作栏（position: sticky）
- [Cancel] 和 [Save Changes] 按钮
- 可选：重置为默认、导出配置、导入配置

---

## Migration Notes

### Removed Features
| Feature | Reason |
|---------|--------|
| Section折叠/展开 | 单Section独占显示后不再需要 |
| 滚动监听高亮 | 改为点击切换，无需监听滚动 |
| 长页面平滑滚动 | 内容不再超长，无需滚动 |
| "SETTINGS" label | 冗余信息，移除以简化UI |

### Preserved Features
- 所有设置项功能和逻辑
- 表单验证
- 设置项描述和提示
- 原有的CSS变量系统

---

## Success Criteria

### Phase 0
- [ ] Modal显示为两栏布局
- [ ] 左侧显示4个Section导航
- [ ] 点击导航切换右侧显示的Section
- [ ] 当前选中导航项高亮显示
- [ ] Section标题有accent色下划线
- [ ] 设置项以卡片形式分组展示
- [ ] 移除所有折叠/展开功能
- [ ] 移动端响应式正常（单栏堆叠）
- [ ] 所有现有设置功能正常工作
- [ ] 设计风格与原有UI一致

### Phase 1
- [ ] 搜索框可输入关键词
- [ ] 实时过滤显示匹配项
- [ ] 高亮匹配的关键词

### Phase 2
- [ ] 底部有固定操作按钮栏
- [ ] Cancel和Save Changes按钮工作正常

---

## Timeline

| Phase | Estimated Time | Status |
|-------|---------------|--------|
| P0    | 3-4 hours     | Ready for Development |
| P1    | 2-3 hours     | Planned |
| P2    | 1-2 hours     | Planned |

---

## Reference

### Design Inspiration
- **macOS System Settings**: 左侧导航 + 右侧单Section独占
- **VS Code Settings**: 清晰的视觉层次和搜索体验
- **Linear**: 简洁的两栏布局设计

### CSS Variables Reference
```css
/* Colors */
--lora-accent: #007AFF;
--lora-border: rgba(255, 255, 255, 0.1);
--card-bg: rgba(255, 255, 255, 0.05);
--text-color: #ffffff;
--text-muted: rgba(255, 255, 255, 0.6);

/* Spacing */
--space-1: 8px;
--space-2: 12px;
--space-3: 16px;
--space-4: 24px;

/* Border Radius */
--border-radius-xs: 4px;
--border-radius-sm: 8px;
```

---

**Last Updated**: 2025-02-24
**Author**: AI Assistant
**Status**: Ready for Implementation

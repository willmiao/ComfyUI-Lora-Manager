# Lora-Manager UI Token Migration Guide

## Overview

The design token system has been created in `static/css/tokens/`. `base.css` now imports the tokens and provides backward-compatible aliases for existing component CSS.

## Token Files

| File | Purpose |
|------|---------|
| `tokens/colors.css` | OKLch color primitives + semantic light/dark tokens |
| `tokens/typography.css` | Font stacks, type scale, weights, line heights |
| `tokens/spacing.css` | 4px-base grid with legacy aliases |
| `tokens/effects.css` | Border radius, shadows, transitions |
| `tokens/breakpoints.css` | Named breakpoint variables |
| `tokens/z-index.css` | Stacking context scale |
| `tokens/index.css` | Aggregator that imports all token files |

## Backward Compatibility

Old variable names in component CSS still work via aliases in `base.css`:

| Old Name | Maps To |
|----------|---------|
| `--bg-color` | `--bg-base` |
| `--text-color` | `--text-primary` |
| `--text-muted` | `--text-secondary` |
| `--card-bg` | `--surface-base` |
| `--border-color` | `--border-base` |
| `--lora-accent` | `--color-accent` |
| `--lora-surface` | `--bg-elevated` |
| `--lora-border` | `--border-subtle` |
| `--space-1` (8px) | `--space-1-legacy` |
| `--border-radius-base` | `--radius-lg` |

## Phase 2: Component Audit Checklist

Below are the hardcoded values found across component CSS that should be replaced with tokens.

### Critical Fixes (P0)

- [ ] **card.css line 441**: `.base-model { background: #f0f0f0; }` → use `--bg-hover` or new `--surface-variant`
- [ ] **card.css line 369**: `.favorite-active { color: #ffc107 !important; }` → use `--favorite-color` (already defined in tokens)
- [ ] **layout.css line 134**: `.control-group button.favorite-filter i { color: #ffc107; }` → use `--favorite-color`
- [ ] **header.css lines 233-250**: Hardcoded dark theme colors (`#3a3a3a`, `#888888`, `#555555`) → use `--bg-disabled`, `--text-secondary`, `--border-base`

### Spacing Normalization (P1)

Replace hard pixel values with token equivalents:

- [ ] `padding: 4px 10px` → `padding: var(--space-1) var(--space-3)`
- [ ] `gap: 6px` → `gap: var(--space-1-legacy)` or `gap: var(--space-2)`
- [ ] `gap: 8px` → `gap: var(--space-2)`
- [ ] `gap: 12px` → `gap: var(--space-3)`
- [ ] `padding: 15px` → `padding: var(--space-4)`
- [ ] `padding: 16px` → `padding: var(--space-4)`
- [ ] `margin-top: 2px` → `margin-top: var(--space-0-5)`
- [ ] `padding: 2px 6px` → `padding: var(--space-0-5) var(--space-2)`
- [ ] `border-radius: 50%` → `border-radius: var(--radius-full)`

### Shadow Standardization (P1)

Replace hardcoded shadows with token equivalents:

- [ ] `box-shadow: 0 1px 2px rgba(0, 0, 0, 0.05)` → `box-shadow: var(--shadow-xs)`
- [ ] `box-shadow: 0 1px 3px rgba(0, 0, 0, 0.05)` → `box-shadow: var(--shadow-sm)`
- [ ] `box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1)` → `box-shadow: var(--shadow-md)`
- [ ] `box-shadow: 0 3px 5px rgba(0, 0, 0, 0.08)` → `box-shadow: var(--shadow-lg)`
- [ ] `box-shadow: 0 4px 16px rgba(0, 0, 0, 0.15)` → `box-shadow: var(--shadow-xl)`
- [ ] `box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08)` → combine or add new token

### Typography Normalization (P1)

Replace scattered font sizes with type scale:

- [ ] `font-size: 0.8em` → `font-size: var(--text-xs)`
- [ ] `font-size: 0.85em` → `font-size: var(--text-sm)`
- [ ] `font-size: 0.9em` → `font-size: var(--text-sm)`
- [ ] `font-size: 0.95em` → `font-size: var(--text-md)`
- [ ] `font-size: 1.1em` → `font-size: var(--text-lg)`
- [ ] `font-size: 11px` → `font-size: var(--text-xs)`

### Breakpoint Normalization (P2)

Replace magic numbers with named breakpoints:

- [ ] `@media (min-width: 2150px)` → `@media (min-width: var(--bp-ultrawide))`
- [ ] `@media (min-width: 3000px)` → `@media (min-width: var(--bp-4k))`
- [ ] `@media (max-width: 768px)` → `@media (max-width: var(--bp-mobile))`
- [ ] `@media (max-width: 1200px)` → `@media (max-width: var(--bp-desktop))`

### Z-Index Cleanup (P2)

Replace magic z-index values with tokens:

- [ ] `z-index: 2` / `z-index: 3` / `z-index: 4` in card.css → use `--z-base` + calc
- [ ] `z-index: 200` in header.css (hamburger dropdown) → use `--z-dropdown`

### Remaining Hardcoded Colors (P2)

- [ ] `rgba(0, 184, 122, 0.05)` and `#00B87A` in import-modal.css → use `--color-success`
- [ ] `rgba(255, 255, 255, 0.12)` in card.css (base-model-label background) → use token
- [ ] `rgba(255, 255, 255, 0.25)` in card.css (separator) → use `--border-inverse`
- [ ] `rgba(0, 0, 0, 0.5)` and `rgba(0, 0, 0, 0.7)` in card.css (toggle blur btn) → use `--bg-overlay` variants
- [ ] `rgba(46, 204, 113, 0.3)` and `rgba(231, 76, 60, 0.3)` in card.css → use success/error tokens

## New Tokens Added

The following tokens were added beyond the existing system:

| Token | Value | Use Case |
|-------|-------|----------|
| `--color-accent-hover` | oklch(58% 0.28 256) | Hover states for accent buttons |
| `--color-accent-subtle` | accent @ 12% opacity | Subtle accent backgrounds |
| `--color-accent-border` | accent @ 25% opacity | Accent borders |
| `--color-accent-transparent` | accent @ 60% opacity | Glow effects, pulse animations |
| `--bg-hover` | oklch(95% 0.02 256) / dark: oklch(35% 0.02 256) | Hover backgrounds |
| `--bg-disabled` | #f5f5f5 / dark: #3a3a3a | Disabled input backgrounds |
| `--bg-overlay` | oklch(0% 0 0 / 0.75) | Modal overlays, gradients |
| `--surface-hover` | oklch(95% 0.02 256) / dark: oklch(35% 0.02 256) | Card/panel hover |
| `--favorite-color` | #d4a017 | Accessible gold for favorites |
| `--shadow-focus` | 0 0 0 1px accent | Focus ring shadow |
| `--shadow-glow` | 0 2px 6px info-glow | Badge glow effects |
| `--transition-bounce` | 200ms cubic-bezier | Playful hover transitions |

## Migration Order Recommendation

1. **Start with colors**: Replace `#ffc107` and `#f0f0f0` (highest visual impact)
2. **Then spacing**: Unify padding/gap values (biggest consistency win)
3. **Then shadows**: Replace rgba shadows with tokens
4. **Then typography**: Standardize font sizes
5. **Finally breakpoints + z-index**: Lower priority but good for maintainability

## Testing Checklist

After each component file is migrated:

- [ ] Light theme renders correctly
- [ ] Dark theme renders correctly
- [ ] No visual regressions in card grid, header, modals
- [ ] Focus states still visible
- [ ] Hover transitions still work (unless prefers-reduced-motion)

# Plan: Quick Picker — Recipe View

**Status:** Implemented (2026-11-15). The design and task breakdown are kept as
the record; see "Implementation notes" for deviations.
**Related:** [canvas-quick-pickers.md](../features/canvas-quick-pickers.md)

## TL;DR (for humans)

**What you'll get:** the canvas quick picker gains a `Recipes` view. Search a
saved recipe, inspect its preview and LoRA set, then append or replace those
LoRAs on the current LoRA node without opening the manager.

**Why recipes before workflows:** recipes are available by default (the recipes
directory falls back to `<first LoRA root>/recipes`), while workflow management
is opt-in (`enable_workflows` defaults to `false`). Applying a recipe is the
same "write LoRAs to the target node" action as the LoRA view; opening a
workflow is a heavier action that must guard the current graph.

**Why a view, not a second panel:** `web/comfyui/lora_quick_panel.js` is ~757
lines of search, keyboard, target-select, status and async-guard logic. A second
floating panel would fork it, and a third (workflows) would fork it again. A
`LoRAs | Recipes` switch in the existing panel is the incremental version of
the documented unified launcher.

**Effort:** ~5–6 dev days estimated.
**Risk:** low–medium. No new backend surface was needed; the risk was the recipe
apply semantics (missing LoRAs, append vs replace) and preserving the existing
LoRA view behavior.

## Implementation notes (2026-11-15)

Shipped in the working tree (not yet committed):

- Shared behavior lives in `LoraQuickPanel` as an `assetView` state plus a
  `recipe_quick_view.js` renderer, rather than a new `quick_panel.js` base class.
  This preserved the existing 24 LoRA-panel tests and avoided rewriting the
  working picker; search, keyboard, target select, status, and async guards are
  still shared, not forked. The deviation from §5.1 is intentional.
- `applyLoraSet` in `web/comfyui/lora_selection.js`; `applyQuickLoraSet` in
  `lora_quick_panel.js` writes the widget/callback/canvas-dirty state.
- New `web/comfyui/recipe_canvas_api.js`, `recipe_quick_view.js`, and
  `recipe_quick_panel.js` (the command/keybinding extension).
- `Alt+R` default in `web/comfyui/shortcuts.js`; `Quick Recipe Picker` in the
  chevron menu; `LoRAs | Recipes` tabs; last view stored in
  `lm:quick-panel:asset-view`.
- The recipe picker is **not** added to the LoRA-node context menu. The node
  menu already carries the LoRA picker; adding one item per asset type would
  bloat it. The recipe view is reachable from the chevron, `Alt+R`, and the
  panel tabs, and its target comes from the panel's target select.
- `#recipe=<id>` deep link in `static/js/recipes.js`; a reused manager tab
  follows `hashchange`, and opening from `/loras` navigates the named tab to
  `/loras/recipes` (a reload, as noted in the plan).
- Payload verification: `get_paginated_data` enriches every list LoRA via
  `_enrich_lora_entry`, so missing/deleted counts need no per-row detail fetch.
- Verification: 82 targeted quick-picker tests across 9 files pass; full JS
  suite 2147 tests (211 files) and Vue 107 tests pass. `git diff --check` is
  clean.
- Still out of scope, as planned: checkpoint/prompt apply, missing-LoRA
  downloads, recipe folders/favorites filters, i18n, and the Workflow view.

## 1. Context

The canvas Quick LoRA Picker is the first asset picker
(`docs/features/canvas-quick-pickers.md`). It already has the ingredients a
recipe view needs:

- A floating panel shell with persisted geometry
  (`web/comfyui/floating_panel.js`).
- Search debounce plus stale-response guards
  (`web/comfyui/lora_quick_panel.js`).
- A target-node select and the "write LoRAs back to the node" primitive
  (`web/comfyui/lora_selection.js`).
- A list + detail layout and panel-level keyboard navigation.

Recipes expose the missing data through existing endpoints:

- `GET /api/lm/recipes` — paginated search over title, tags, LoRA file/model
  name, and prompt (same parameters as `static/js/api/recipeApi.js`).
- `GET /api/lm/recipe/{recipe_id}` — formatted recipe with enriched LoRA
  entries (availability, preview, strengths).

Applying a recipe only needs the LoRA set; no checkpoint or prompt write-back
is required for v1.

## 2. Scope

### In (v1)

- A `Recipes` view in the existing quick panel, switchable with `LoRAs`.
- Search over recipe title, tags, LoRA file name, LoRA model name, and prompt.
- Result rows: preview, title, LoRA count, base model, missing/deleted count.
- Detail: preview, title, base model, recipe LoRA list with strengths and
  missing/deleted markers.
- **Append** and **Replace** actions that write the recipe's available LoRAs
  and strengths to the current target node.
- Missing/deleted LoRAs are skipped and counted in the status bar; an
  `Open in manager` action lets the user reconnect or download them.
- Entry points: Quick Actions chevron item, registered command + default
  keybinding, and the `LoRAs | Recipes` tabs.
- View persistence: the last selected view is remembered, but an explicit
  entry point wins (LoRA `+` / `Alt+L` opens `LoRAs`; `Alt+R` opens `Recipes`).

### Out (v1)

- A LoRA-node context-menu entry. The node menu already carries the LoRA picker;
  adding one item per asset type would bloat it, so recipes are reached from the
  chevron, `Alt+R`, and the panel tabs.
- Applying the recipe's checkpoint.
- Applying the recipe's prompt, negative prompt, or generation parameters.
- Downloading missing LoRAs from inside the picker.
- Recipe folders/filters/favorites/recent toggles (flat search list only).
- Applying a recipe's embedded workflow.
- Workflow view (next step after recipes).
- i18n of the new strings (the existing picker is English-literal; a separate
  pass should cover LoRAs + Recipes together).
- Folders, multi-select, drag/drop, or recipe editing.

## 3. Interaction design

### 3.1 Entry points

- **Quick Actions chevron:** `Quick Recipe Picker` (proposed `Alt+R`, remappable)
  next to `Quick LoRA Picker` (`Alt+L`) and `Open LoRA Manager`.
- **Existing LoRA `+` button:** keeps opening the `LoRAs` view.
- **No node context-menu item:** the LoRA node menu keeps only the LoRA picker;
  the recipe target comes from the panel's target select.
- **Panel tabs:** `LoRAs | Recipes` switch in place; the target node and the
  query are preserved? **No** — switching clears the query and reloads the new
  asset type, because a query tuned for LoRA names rarely makes sense for
  recipes. The target node is kept.

### 3.2 Layout

The current list + detail split is reused; only the row and detail content
change for recipes.

```text
┌ Quick Pick · Recipe ──────────────────────────────────────────── ✕ ┐
│ [LoRAs] [Recipes]                                                  │
│ Search recipes, tags, LoRA names…                                  │
│ Add to Character Loader #12 ▾                                      │
├──────────────────────────────────────┬─────────────────────────────┤
│ [img] Cyberpunk portrait             │ [preview]                   │
│       5 LoRAs · Flux · 1 missing     │ Cyberpunk portrait          │
│ [img] Soft light portrait            │ Flux · 5 LoRAs · 1 missing  │
│       3 LoRAs · SDXL                 │                             │
│                                      │ LoRAs                       │
│                                      │  detail-tweaker      0.80   │
│                                      │  film-grain          0.60 ⚠ │
│                                      │                             │
│                                      │ [Append] [Replace]          │
│                                      │ [Open in manager]           │
├──────────────────────────────────────┴─────────────────────────────┤
│ 5 results · 1 missing                                              │
│ ↑↓ Navigate · Enter Append · Shift+Enter Keep open · Esc Close     │
└────────────────────────────────────────────────────────────────────┘
```

The panel keeps its persisted geometry (`lm:quick-panel:rect`); the recipe
detail is wide enough at the existing 880×570 default. At narrow widths the
detail column collapses to the list, like the LoRA view.

### 3.3 Rows and states

- **Normal row:** thumbnail (`file_url`, lazy-loaded), title, meta line
  (`N LoRAs · Base model`), and a warning chip when `missing > 0` or
  `deleted > 0`.
- **Empty query:** newest recipes first (`sort_by=date`), page size 30.
- **Searching:** debounced 180 ms, same as the LoRA view; status
  `Searching “…”…`, then `N results` or `No recipes match “…”`.
- **No recipes:** `No recipes yet. Save one from the LoRA widget or the
  manager.` with `Open LoRA Manager`.
- **No target node:** rows and detail still render; `Append`/`Replace` are
  disabled and the status says `No compatible LoRA node in this workflow`.
  `Open in manager` remains available.
- **Missing/deleted entries:** rows show a chip; the detail lists each LoRA with
  its status and skips it on apply. No download flow in the panel.
- **Loading/error:** reuse the existing `lm-quick__loading` and
  `lm-quick__empty` classes; a detail fetch failure leaves the row and shows
  the error in the detail column.

### 3.4 Keyboard

- `↑` / `↓`: move the selected row.
- `Enter`: apply the default action (**Append**) and close.
- `Shift+Enter`: apply and keep the panel open.
- `Esc`: clear the search when it has text, otherwise close the panel.
- `←` / `→`: do **not** bind in the Recipes view. The LoRA view uses them for
  folder navigation; binding them for tab switching in a view with a text
  field invites the same caret conflict the LoRA view has. Tabs are reachable
  with `Tab`/`Shift+Tab` and activated with `Enter`/`Space`.
- `Replace` is button-only, so the destructive action has no accidental
  keyboard default.
- The search input keeps normal text-editing behavior; panel-level handlers
  must not swallow text-editing keys.

### 3.5 Apply semantics

Entries come from the recipe detail response: `file_name` (normalized with
`normalizeLoraNameKey`), `strength`, and availability flags (`inLibrary`,
`isDeleted`, or the enriched status).

**Append (default)**
- For each available recipe LoRA, apply it with the existing
  `applyLoraSelection` semantics: if the target list already has the entry,
  enable it in place and keep its current strengths; otherwise append it
  active with the recipe's strength.
- Missing/deleted entries are skipped and counted.
- If every available entry is already active, do not write the widget; report
  `Recipe is already applied`.

**Replace**
- The target list becomes exactly the available recipe LoRAs, all active, using
  the recipe's strengths (clip strength = recipe clip strength when present,
  otherwise the same value).
- Missing/deleted entries are omitted; the status reports the skipped count.
- Replace is disabled when no recipe LoRA is available.

**After apply**
- Close unless `Shift+Enter`.
- Status: `Applied 4 LoRAs · 1 missing skipped` (or `Replaced with 3 LoRAs ·
  2 missing skipped`).
- Reuse the LoRA write-back path: set `widget.value`, call `widget.callback`,
  and mark the canvas dirty, exactly as `applyQuickLoraSelection` does today.
- If the target node disappeared while the panel was open, disable the actions
  and show the same "target node is no longer on this workflow" message.

## 4. Data and API reuse

| Purpose | Endpoint | Notes |
|---|---|---|
| Recipe search | `GET /api/lm/recipes` | Mirror the parameters in `static/js/api/recipeApi.js`: `page`, `page_size`, `sort_by`, `search`, `search_title`, `search_tags`, `search_lora_name`, `search_lora_model`, `search_prompt`, `recursive`. |
| Recipe detail | `GET /api/lm/recipe/{recipe_id}` | Formatted response with enriched `loras` (strengths + availability). |
| Preview | `file_url` from the list/detail | Same-origin static path; verify base-path handling on a subpath deployment. |
| Manager link | `/loras/recipes#recipe=<id>` | New deep link; see §5.3. |

- Add `web/comfyui/recipe_canvas_api.js` with the canvas-side client; use
  `lmUrl` for API calls and follow `lora_canvas_api.js` conventions.
- No backend change is planned. The list response already carries `loras`,
  `base_model`, and `file_url`; **task 0 verifies** whether each entry carries
  availability flags. If it does not, compute counts from the enriched detail
  on selection (row badges only when available) or add a lightweight summary
  field server-side — do not fetch details for every row.
- The existing server-side SFW filter applies to the list; detail is fetched
  only for a selected (already visible) recipe.

## 5. Architecture

### 5.1 Shared picker shell

> **As built:** this became a shared `assetView` state in `LoraQuickPanel` plus
> `recipe_quick_view.js`, not a separate `quick_panel.js` base class. The
> behavior below is shared either way; the class extraction remains a possible
> follow-up if a Workflow view needs more separation.

Extract the non-asset-specific parts of `LoraQuickPanel` into a shell/controller
(`web/comfyui/quick_panel.js`):

- Floating panel creation, title/context, persisted geometry, close/focus.
- Toolbar frame, asset tabs, search input + debounce, status bar + footer hints.
- Panel-level keyboard dispatch (`Esc`, `↑`/`↓`, `Enter`, `Shift+Enter`).
- Target-node select and node validation.
- Search/detail sequence guards and "is the panel still open?" checks.
- View persistence (`lm:quick-panel:asset-view`) and tab switching.

The view interface:

```text
id, label, searchPlaceholder, needsTargetNode
mount(container)                  // build the view's DOM
load(query)                       // fetch and render results
navigationItems()                 // rows/folders for keyboard navigation
activate(item, { keepOpen })      // Enter behavior
renderDetail(item)                // optional; the shell calls it on selection
onTargetChanged(node)             // update availability/actions
handleKey(event)                  // optional extra keys (LoRA folder ←/→)
```

`LoraQuickPanel` becomes the `LoRA` view, keeping its exports
(`openLoraQuickPanel`, `toggleLoraQuickPanel`, `closeLoraQuickPanel`) as thin
wrappers that open the controller with the LoRA view. This keeps call sites and
existing tests stable.

Do this as a behavior-preserving refactor first (task 1), then add the recipe
view (task 4). If the shell refactor proves too large in one step, ship the
shell + LoRA view, then the recipe view in the next change; do not fork the
search/keyboard logic.

### 5.2 Recipe view

New `web/comfyui/recipe_quick_panel.js`:

- Search/list rendering with thumbnails and summary chips.
- Detail rendering with preview, metadata, recipe LoRA rows, and actions.
- `Append`/`Replace` implemented through a new batch helper in
  `web/comfyui/lora_selection.js`:

```text
applyLoraSet(currentLoras, recipeLoras, { mode: "append" | "replace" })
  -> { loras, changed, applied, skipped }
```

- Register a ComfyUI extension for the command and keybinding only. Do **not**
  add a node context-menu item: the LoRA node menu keeps the LoRA picker as its
  single quick-picker entry, and recipes stay reachable from the chevron,
  `Alt+R`, and the panel tabs.

New `web/comfyui/recipe_canvas_api.js`:

- `searchRecipes(query, pageSize)`, `fetchRecipeDetails(recipeId)`,
  `openRecipeManager(recipeId)`.
- Use `lmUrl`; keep response-shape normalization in one place.

`web/comfyui/shortcuts.js`:
- Add `quickRecipePicker: "LoraManager.ToggleRecipeQuickPanel"` to `COMMAND_IDS`.
- Add the default combo to `DEFAULT_KEYBINDINGS` (proposed `Alt+R`; verify no
  conflict with ComfyUI defaults).
- Keep command ids stable for user remaps.

`web/comfyui/quick_actions_menu.js`:
- Add the `Quick Recipe Picker` item and its shortcut badge.

### 5.3 Manager deep link

The recipes page currently opens a specific recipe only through
`sessionStorage.viewRecipeId` (`static/js/recipes.js`), which cannot be set from
another tab. Add a hash deep link mirroring the model modal's `#model=` pattern:

- `static/js/recipes.js`: parse `#recipe=<id>` on load and on `hashchange`,
  reuse the existing `viewRecipeId` / custom-filter path, and open the recipe
  modal.
- `openRecipeManager(recipeId)` opens
  `${origin}${lmUrl("/loras/recipes")}#recipe=<id>` in the named
  `lm-lora-manager` tab; if the tab is on `/loras`, the navigation reloads the
  page (acceptable for v1; a cross-page hash handoff is a separate change).
- If this expands the change too much, v1 can open the recipes page without a
  deep link, but the review should call that out as a known limitation.

## 6. Task breakdown

| # | Task | Output | Est. | Depends on |
|---|---|---|---|---|
| 0 | Verify recipe payloads | Confirm list rows carry `loras` availability, preview, base model; decide counts fallback | 0.25d | — |
| 1 | Extract shared panel shell | `quick_panel.js`; `LoraQuickPanel` as a view; existing tests green with no behavior change | 1.5d | 0 |
| 2 | Batch apply primitive | `applyLoraSet` in `lora_selection.js` + unit tests (append/replace/missing/already-active) | 0.5d | — |
| 3 | Recipe canvas API | `recipe_canvas_api.js` + tests (query params, detail, base path, manager link) | 0.5d | 0 |
| 4 | Recipe view | `recipe_quick_panel.js` list/detail/apply/states/styles + tests | 1.5d | 1, 2, 3 |
| 5 | Entry points and view persistence | Chevron item, command/keybinding, tabs, `lm:quick-panel:asset-view`; tests | 0.5d | 4 |
| 6 | Manager deep link | `#recipe=<id>` handling in `static/js/recipes.js` + page tests | 0.5d | 3 |
| 7 | Docs and i18n note | Update `canvas-quick-pickers.md` after implementation; note the English-literal/i18n follow-up | 0.25d | 4–6 |
| 8 | Regression pass | Full `npm test`; LoRA view behavior unchanged; manual checks | 0.5d | all |

Total: ~5.5–6 dev days estimated. All tasks above are implemented as of
2026-11-15, with two as-built changes: task 1 is the shared `assetView` state in
`LoraQuickPanel` instead of a separate base class, and the recipe rendering lives
in `recipe_quick_view.js` with the panel methods in `lora_quick_panel.js`;
`recipe_quick_panel.js` is the command/keybinding extension. The i18n remainder
from task 7 is still open.

## 7. Verification

**Automated**

- `npx vitest run tests/frontend/components/loraQuickPanel.test.js`
- `npx vitest run tests/frontend/components/quickPanel.test.js` (new shell tests)
- `npx vitest run tests/frontend/components/recipeQuickPanel.test.js` (new)
- `npx vitest run tests/frontend/components/loraSelectionSendToComfy.test.js`
  plus the new `applyLoraSet` tests
- `npx vitest run tests/frontend/components/quickActionsMenu.test.js`
- `npx vitest run tests/frontend/pages/recipesPage.test.js` (deep link)
- Full `npm test` before the commit.

**Manual (look and feel, user's call)**

- Open from the chevron and `Alt+R`; confirm the LoRA node context menu still
  shows only **Quick LoRA Picker**.
- Search a recipe, switch to the LoRA tab and back; confirm the target node and
  view persistence behave as specified.
- Append to a node that already lists some of the recipe's LoRAs: no
  duplicates, existing strengths kept, inactive entries enabled.
- Replace: the node contains exactly the recipe's available LoRAs, recipe
  strengths applied.
- A recipe with a missing/deleted LoRA: row chip, detail marker, skip count.
- No target node: actions disabled, `Open in manager` works.
- `Esc` clears a non-empty search first, then closes.
- LoRA view regression: folder/flat, filters, recent, Added/Off markers, video
  previews, `+` button, `Alt+L`.

## 8. Open questions / assumptions

1. **Default action:** Append (least destructive). Replace is button-only.
2. **Append strengths:** keep existing strengths for LoRAs already on the node
   (matches `applyLoraSelection`); Replace applies recipe strengths. If the
   product prefers recipe strengths to win on append, change it explicitly.
3. **Missing/deleted LoRAs:** skip and count; no download flow in the panel.
4. **List availability:** verify payload in task 0; otherwise use detail-only
   counts or a small summary field.
5. **Node menu:** no recipe node-menu item (product decision to avoid menu
   bloat); the LoRA picker remains the only quick-picker entry there.
6. **Deep link:** `#recipe=<id>` is preferred; if the manager tab is on
   `/loras`, the navigation reloads that tab.
7. **i18n:** new strings stay English for now, consistent with the LoRA view;
   a separate pass should cover both views.
8. **Checkpoint/prompt:** out of scope; the button says `Apply LoRAs` and the
   detail can note that the checkpoint/prompt are not applied.
9. **Favorites/recent/folders:** not in v1; search + date order is enough.

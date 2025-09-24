# LoRA & Checkpoints Filtering/Sorting Test Matrix

This matrix captures the scenarios that Phase 3 frontend tests should cover for the LoRA and Checkpoint managers. It focuses on how search, filter, sort, and duplicate badge toggles interact so future specs can share fixtures and expectations.

## Scope

- **Components**: `PageControls`, `FilterManager`, `SearchManager`, and `ModelDuplicatesManager` wiring invoked through `CheckpointsPageManager` and `LorasPageManager`.
- **Templates**: `templates/loras.html` and `templates/checkpoints.html` along with shared filter panel and toolbar partials.
- **APIs**: Requests issued through `baseModelApi.fetchModels` (via `resetAndReload`/`refreshModels`) and duplicates badge updates.

## Shared Setup Considerations

1. Render full page templates using `renderLorasPage` / `renderCheckpointsPage` helpers before importing modules so DOM queries resolve.
2. Stub storage helpers (`getStorageItem`, `setStorageItem`, `getSessionItem`, `setSessionItem`) to observe persistence behavior without mutating real storage.
3. Mock `sidebarManager` to capture refresh calls triggered after sort/filter actions.
4. Provide fake API implementations exposing `resetAndReload`, `refreshModels`, `fetchFromCivitai`, `toggleBulkMode`, and `clearCustomFilter` so control events remain asynchronous but deterministic.
5. Supply a minimal `ModelDuplicatesManager` mock exposing `toggleDuplicateMode`, `checkDuplicatesCount`, and `updateDuplicatesBadgeAfterRefresh` to validate duplicate badge wiring.

## Scenario Matrix

| ID | Feature | Scenario | LoRAs Expectations | Checkpoints Expectations | Notes |
| --- | --- | --- | --- | --- | --- |
| F-01 | Search filter | Typing a query updates `pageState.filters.search`, persists to session, and triggers `resetAndReload` on submit | Validate `SearchManager` writes query and reloads via API stub; confirm LoRA cards pass query downstream | Same as LoRAs | Cover `enter` press and clicking search icon |
| F-02 | Tag filter | Selecting a tag chip adds it to filters, applies active styling, and reloads results | Tag stored under `filters.tags`; `FilterManager.applyFilters` persists and triggers `resetAndReload(true)` | Same; ensure base model tag set is scoped to checkpoints dataset | Include removal path |
| F-03 | Base model filter | Toggling base model checkboxes updates `filters.baseModel`, persists, and reloads | Ensure only LoRA-supported models show; toggle multi-select | Ensure SDXL/Flux base models appear as expected | Capture UI state restored from storage on next init |
| F-04 | Favorites-only | Clicking favorites toggle updates session flag and calls `resetAndReload(true)` | Button gains `.active` class and API called | Same | Verify duplicates badge refresh when active |
| F-05 | Sort selection | Changing sort select saves preference (legacy + new format) and reloads | Confirm `PageControls.saveSortPreference` invoked with option and API called | Same with checkpoints-specific defaults | Cover `convertLegacySortFormat` branch |
| F-06 | Filter persistence | Re-initializing manager loads stored filters/sort and updates DOM | Filters pre-populate chips/checkboxes; favorites state restored | Same | Requires simulating repeated construction |
| F-07 | Combined filters | Applying search + tag + base model yields aggregated query params for fetch | Assert API receives merged filter payload | Same | Validate toast messaging for active filters |
| F-08 | Clearing filters | Using "Clear filters" resets state, storage, and reloads list | `FilterManager.clearFilters` empties `filters`, removes active class, shows toast | Same | Ensure favorites-only toggle unaffected |
| F-09 | Duplicate badge toggle | Pressing "Find duplicates" toggles duplicate mode and updates badge counts post-refresh | `ModelDuplicatesManager.toggleDuplicateMode` invoked and badge refresh called after API rebuild | Same plus checkpoint-specific duplicate badge dataset | Connects to future duplicate-specific specs |
| F-10 | Bulk actions menu | Opening bulk dropdown keeps filters intact and closes on outside click | Validate dropdown class toggling and no unintended reload | Same | Guard against regression when dropdown interacts with filters |

## Automation Coverage Status

- ✅ F-01 Search filter, F-02 Tag filter, F-03 Base model filter, F-04 Favorites-only toggle, F-05 Sort selection, and F-09 Duplicate badge toggle are covered by `tests/frontend/components/pageControls.filtering.test.js` for both LoRA and checkpoint pages.
- ⏳ F-06 Filter persistence, F-07 Combined filters, F-08 Clearing filters, and F-10 Bulk actions remain to be automated alongside upcoming bulk mode refinements.

## Coverage Gaps & Follow-Ups

- Write Vitest suites that exercise the matrix for both managers, sharing fixtures through page helpers to avoid duplication.
- Capture API parameter assertions by inspecting `baseModelApi.fetchModels` mocks rather than relying solely on state mutations.
- Add regression cases for legacy storage migrations (old filter keys) once fixtures exist for older payloads.
- Extend duplicate badge coverage with scenarios where `checkDuplicatesCount` signals zero duplicates versus pending calculations.

# Plan: "Other Models" Page — Unified Management for VAE / Upscaler / Text Encoder / etc.

**Status:** v2 — **Phase 1 implemented** (2026-09-12, commits `27da7b3c` backend + `fa7ce725` frontend; verified live against a running ComfyUI instance: scan/hash/sub_type-derivation/fetch/previews all green). **Phase 2 implemented** (2026-09-12, per §9 design; full pytest + vitest green). **Phase 3 implemented** (§11: opt-in management toggles; default off). **i18n done** (2026-09-13): all 36 new keys translated in the 9 non-English locales — the `[TODO: Translate]` placeholders left by the sync script during development are gone (see `docs/i18n-translation-guidelines.md` §2, "Other Models feature"). **Default set revised (pre-release):** only `vae` / `upscaler` / `text_encoder` are managed by default — `clip_vision` and `controlnet` are both opt-in (§2, §11.1.1).
**Scope (Phase 1):** scan + manage (list, search, filter, tags, folders, preview, rename, move, delete/exclude, CivitAI metadata fetch) for a new model type `other`, exposed as a new web page. **Phase 2 (§9):** one-click download from CivitAI for these types.

## 1. Goal

Today the manager supports three model types:

| page | model_type | sub_types |
|---|---|---|
| `/loras` | `lora` | `lora`, `locon`, `dora` |
| `/checkpoints` | `checkpoint` | `checkpoint`, `diffusion_model` |
| `/embeddings` | `embedding` | `embedding` |

Add a fourth page that manages "everything else" — VAE, upscalers, text encoders / CLIP, CLIP vision, optionally ControlNet — with a folder→sub_type mapping table so new ComfyUI folder categories can be added later by configuration, not code.

## 2. Locked Decisions

1. **Architecture: one scanner + one service + one page, sub_type derived by location.**
   Replicates the checkpoint pattern (`CheckpointScanner` aggregates `checkpoints` + `unet` roots and derives `checkpoint` vs `diffusion_model` from the root containing the file, `py/services/checkpoint_scanner.py:384-415`). One `OtherScanner` aggregates all enabled folder roots; `resolve_sub_type_for_path()` maps each root to a sub_type. No per-category scanners.

2. **Naming: internal `model_type = "other"`, route prefix `/other`, page id `other`.**
   - `misc` is rejected: `py/routes/misc_routes.py` already owns that name for system/settings routes (`/api/lm/settings`, `/api/lm/doctor/*`).
   - `components` is rejected: `templates/components/` and `static/js/components/` directories would make `components.html` / `components.js` confusing neighbors.
   - `other` matches CivitAI's `Other` fallback type semantics. The **display name** is an i18n string (`other.title`, e.g. "Other Models") and can be renamed later without touching code.

3. **sub_type values:** snake_case, aligned with CivitAI `ModelType` semantics:

   | sub_type | ComfyUI `folder_paths` key(s) | CivitAI ModelType | enabled by default |
   |---|---|---|---|
   | `vae` | `vae` | `VAE` | yes |
   | `upscaler` | `upscale_models` | `Upscaler` | yes |
   | `text_encoder` | `text_encoders`, `clip` (legacy) | `TextEncoder` (CLIP is retired upstream) | yes |
   | `clip_vision` | `clip_vision` | `CLIPVision` | no (mapping present, opt-in) |
   | `controlnet` | `controlnet` | `Controlnet` | no (mapping present, opt-in) |

   New folder categories = one line in the mapping table (see §4.1).

   **Why only three are on by default** (revised in Phase 3, before release):
   VAE, upscalers and text encoders are dependency-style assets every pipeline
   needs, and "which one am I actually using" is the recurring problem they
   solve. `clip_vision` and `controlnet` are workflow-driven instead
   (IPAdapter/SVD image conditioning; per-workflow ControlNet variants), and
   ControlNet libraries routinely run to dozens of files, so both are treated
   symmetrically as opt-in. Enumerating all five as "the default set" was not
   defensible on demand breadth alone.

4. **Phase 1 = scan/manage only.** Downloads from CivitAI (`download_manager.py` type mapping, default-root settings keys, download routing) are Phase 2 (§9). CivitAI **metadata fetch** for existing files IS in Phase 1 (hash-based lookup is type-agnostic; only the type-validation hook needs new values).

5. **Out of scope (default off, revisit later):** usage statistics buckets, recipe matching (`recipe_scanner.py` only merges lora+checkpoint scanners), statistics page, embeddings re-classification (stays its own page — merging would be a breaking change).

## 3. Why This Works With Minimal Churn

- `ModelScanner` (`py/services/model_scanner.py:93`) is specialized entirely via constructor params (`model_type`, `model_class`, `file_extensions`) + optional hooks (`adjust_metadata`, `adjust_cached_entry`, `resolve_sub_type_for_path`, `model_scanner.py:1429-1443`).
- `BaseModelService` subclasses can be one method (`EmbeddingService` implements only `format_response`, `py/services/embedding_service.py:12`).
- Routes: `ModelServiceFactory.register_model_type()` (`py/services/model_service_factory.py:120-136`) + `COMMON_ROUTE_DEFINITIONS` (`py/routes/model_route_registrar.py:23-149`) generate the full `/api/lm/{prefix}/*` surface (~50 endpoints) plus the `GET /{prefix}` page route.
- `PersistentModelCache` (`py/services/persistent_model_cache.py:526-606`) is a single `models` table keyed `(model_type, file_path)` with `model_type` as free text — **zero schema change**.
- Frontend `apiConfig.js` (`static/js/api/apiConfig.js:51`) generates all endpoints from the model-type string; `ModelCard.js:670-675` renders the sub_type badge from data; the checkpoints page already demonstrates the "one page, multiple sub_types" filter (`header.html:298`).

## 4. Backend Changes

### 4.1 New constants — `py/utils/constants.py`

```python
# folder_paths key -> sub_type; single source of truth for extensibility
OTHER_MODEL_FOLDER_SUBTYPES = {
    "vae": "vae",
    "upscale_models": "upscaler",
    "text_encoders": "text_encoder",
    "clip": "text_encoder",        # legacy ComfyUI key
    "clip_vision": "clip_vision",
    "controlnet": "controlnet",
}
DEFAULT_OTHER_MODEL_FOLDERS = ("vae", "upscale_models", "text_encoders", "clip", "clip_vision")
VALID_OTHER_SUB_TYPES = ["vae", "upscaler", "text_encoder", "clip_vision", "controlnet"]
# CivitAI model.type values accepted for this page (fetch-metadata validation)
VALID_OTHER_CIVITAI_TYPES = {"vae", "upscaler", "textencoder", "clipvision", "controlnet", "other"}
```

Also extend `CIVITAI_USER_MODEL_TYPES` (`constants.py:90`) if user-model queries should include these types.

### 4.2 New files (mirror the embedding/checkpoint implementations)

1. **`py/utils/models.py`** — add `OtherModelMetadata(BaseModelMetadata)`: default `sub_type="vae"` placeholder overridden by scanner hook; `from_civitai_info` mapping CivitAI types → our sub_types (`TextEncoder`→`text_encoder`, `CLIPVision`→`clip_vision`, `Upscaler`→`upscaler`, `VAE`→`vae`, `Controlnet`→`controlnet`, else `other`-ish fallback to folder-derived sub_type).
2. **`py/services/other_scanner.py`** — `OtherScanner(ModelScanner)`:
   - `model_type="other"`, extensions: reuse the checkpoint set (`safetensors/pt/pt2/bin/pth/pkl/sft/gguf`).
   - `get_model_roots()`: iterate `OTHER_MODEL_FOLDER_SUBTYPES` ∩ enabled keys, pull each from `config` (§4.3); dedupe; build `root → sub_type` map (normalized abspaths; multiple keys may share a sub_type).
   - Implement all three hooks like `CheckpointScanner` (`checkpoint_scanner.py:384-415`): `resolve_sub_type_for_path` by longest-prefix root match, `adjust_metadata`, `adjust_cached_entry` (sub_type is re-derived on cache load, never persisted).
   - **Lazy hashing, checkpoint-style**: text encoders (T5-XXL ≈ 10 GB) make eager sha256 painful. Copy the `hash_status="pending"` + singleflight `calculate_hash_for_model` pattern from `CheckpointScanner`.
3. **`py/services/other_model_service.py`** — `OtherModelService(BaseModelService)`, `format_response` only (no usage_count, like `EmbeddingService`).
4. **`py/routes/other_routes.py`** — `OtherRoutes(BaseModelRoutes)`, `template_name="other.html"`, hooks:
   - `_validate_civitai_model_type` → `VALID_OTHER_CIVITAI_TYPES`
   - `_get_expected_model_types`, `_parse_specific_params` (no type-specific download params in Phase 1)
   - `initialize_services()` on `app.on_startup` pulling `ServiceRegistry.get_other_scanner()`.

### 4.3 `py/config.py`

- New `other_roots` property: for each enabled key in `OTHER_MODEL_FOLDER_SUBTYPES`, `folder_paths.get_folder_paths(key)` (plugin mode) — standalone mode needs nothing new: `MockFolderPaths` (`standalone.py:66-105`) already serves arbitrary keys from `settings.json.folder_paths`.
- Follow the existing per-type recipe: an `_prepare_other_paths()` (dedupe + symlink registration; also **cross-scanner overlap detection** — warn if an `other` root is already covered by checkpoints/unet/embedding roots, mirroring the checkpoint/unet overlap check).
- Wire into: `_apply_library_paths`, `_symlink_roots()`, `_rebuild_preview_roots()` (hard requirement — preview images are served per registered root), `save_folder_paths_to_settings()`.

### 4.4 Existing-file edits (the "type string scatter" — each is a small branch/entry)

| file | change |
|---|---|
| `py/services/model_service_factory.py:120` | register `("other", OtherModelService, OtherRoutes)` in `register_default_model_types()` |
| `py/services/service_registry.py` | add `get_other_scanner()` (mirror `:297` `get_embedding_scanner`) |
| `py/services/model_scanner.py:67` | `PAGE_TYPE_MAP['other'] = 'other'` (WebSocket progress) |
| `py/services/base_model_service.py:896-906` | `get_model_types()` branch → `VALID_OTHER_SUB_TYPES` |
| `py/lora_manager.py` | `_initialize_services` scanner task list (`:219-242`), `_cleanup` cancel list (`:463`), `_cleanup_backup_files` roots (`:327-330`) |
| `py/routes/handlers/misc_handlers.py` | `scanner_getters` (`:657-661`) + `scanner_factories` (`:757-759`) so Doctor / init-status / refresh-all see the new scanner |
| `py/services/pending_delete_service.py` | `_PAGE_TYPE` map (`:57-61`) + scanner getter list (`:983-985`) |
| `py/metadata_ops/__init__.py:36-38` | `SCANNER_TYPE_MAP['other']` |
| `settings.json.example` | document optional `folder_paths` keys: `vae`, `upscale_models`, `text_encoders`, `clip_vision` |

**Explicitly NOT touched in Phase 1:** `py/services/download_manager.py`, `py/services/download_routing.py`, `py/services/settings_manager.py` default-root keys, `py/routes/stats_routes.py`, `py/utils/usage_stats.py`, `py/services/recipe_scanner.py`, `py/metadata_collector/`, `py/nodes/`.

**Zero-change confirmations (verified):** `PersistentModelCache`, `ModelUpdateService`, `DownloadedVersionHistoryService`, `MetadataSyncService` + provider chain (type-agnostic hash lookups), `ModelFileService` / `ModelMoveService` / `ModelLifecycleService` (scanner + model_type injected), `ModelCache` / `ModelHashIndex`, `AutoV3BackfillService`.

## 5. Frontend Changes

1. **`static/js/api/apiConfig.js`** — `MODEL_TYPES.OTHER = 'other'`; `MODEL_CONFIG.other` entry (displayName, singularName, `supportsMove`, `supportsBulkOperations`; no letter filter); endpoints come free from `getApiEndpoints()` (`:51`).
2. **`static/js/api/otherApi.js`** — thin `OtherApiClient extends BaseModelApiClient` (mirror `embeddingApi.js`); register in `modelApiFactory.js`.
3. **`static/js/other.js`** — page entry (mirror `embeddings.js`): `appCore.initialize()` + `createPageControls('other')` + `initializePageFeatures()` + `ModelDuplicatesManager` + `initActiveFiltersSync('other')`.
4. **Controls & context menu** — `OtherControls extends PageControls` and `OtherContextMenu` (start from the embedding variants — the smallest); add branches in the two factories (`components/controls/index.js:15`, `components/ContextMenu/index.js:15`). Context-menu template block lives in `templates/other.html` (`{% block additional_components %}`, the checkpoints/embeddings pattern — do NOT touch the shared `context_menu.html`).
5. **`templates/other.html`** — copy `embeddings.html`: same content blocks (controls + breadcrumb + duplicates banner + folder sidebar + `#modelGrid`), `data-page="other"`, main script `/loras_static/js/other.js`.
6. **`templates/components/header.html`** — nav entry (`:23-43`, active when `request.path.startswith('/other')`); enable the `modelTypes` sub_type filter panel for `other` (`:298-305` pattern from checkpoints); check search-options panel conditions (`:199-224`).
7. **`static/js/utils/constants.js`** — `MODEL_SUBTYPE_ABBREVIATIONS` (`:115`): `vae→VAE`, `upscaler→UPS`, `text_encoder→TE`, `clip_vision→CV`, `controlnet→CN`; matching `MODEL_SUBTYPE_DISPLAY_NAMES` (`:99`). (Unknown fallback already uppercases 4 chars, but explicit mappings read better.)
8. **`static/js/core.js:110` `getPageType()`** — verify `data-page="other"` flows through `state.pages` generically; add only if the page list is enumerated anywhere.
9. No change to `web/comfyui/top_menu_extension.js` (it opens `/loras`; page-to-page nav is the header bar).

## 6. i18n

- `locales/en.json`: add `other.title` (e.g. "Other Models") + minimal `other.contextMenu.*` / `other.modelTypes.*` keys; reuse `modelCard.*`, `loras.contextMenu.*`, `common.*` wherever possible (the established pattern — checkpoints/embeddings already reuse lora keys).
- Run `python scripts/sync_translation_keys.py`; leave `[TODO: Translate]` placeholders in other locales (per `docs/i18n-translation-guidelines.md` §7 — do not translate proactively).

## 7. Testing

Follow existing conventions (`pytest.ini`, `tests/frontend/` vitest):

1. **Backend (pytest, async where needed):**
   - `OtherScanner` root aggregation + `resolve_sub_type_for_path` (file under `vae/` root → `vae`; `text_encoders` and legacy `clip` both → `text_encoder`; disabled `controlnet` root not scanned).
   - Cache round-trip: sub_type re-derived via `adjust_cached_entry` (not persisted).
   - Lazy hash: `hash_status="pending"` default; `calculate_hash_for_model` singleflight.
   - `OtherRoutes` registration smoke test: `/api/lm/other/...` endpoints exist; `_validate_civitai_model_type` accepts `vae`/`upscaler`/`textencoder`, rejects `lora`.
   - Config: `other_roots` in both modes (mock `folder_paths`, and standalone `settings.json.folder_paths`).
2. **Frontend (vitest + jsdom, `tests/frontend/`):**
   - `apiConfig`: `getApiEndpoints('other')` URL shapes; `modelApiFactory` returns the Other client.
   - `ModelCard` badge rendering for new sub_types.
   - `createPageControls('other')` / `createPageContextMenu('other')` factories.
3. **Manual UI verification by the user** (per AGENTS.md — no sandbox/browser automation): page loads, scans a real library, sub_type filter + badges, context menu actions.

## 8. Execution Order

1. `constants.py` + `OtherModelMetadata` + `config.py` roots
2. `OtherScanner` (+ registry, factory, `PAGE_TYPE_MAP`) → scanner unit tests green
3. `OtherModelService` + `OtherRoutes` + handler/registrar wiring + `lora_manager.py` lifecycle → route tests green
4. Doctor/pending-delete/metadata-ops scatter entries
5. Template + header nav + frontend API/controls/context-menu/card badges → vitest green
6. i18n keys + sync script
7. `pytest` + `npm test` full runs; hand to user for manual UI check

## 9. Phase 2 Detailed Design — CivitAI Downloads for `other`

Designed 2026-09-12 against the Phase-1 code on this branch; decisions marked **[locked]** follow the same recommendations the feature owner approved for Phase 1.

### 9.1 Download pipeline touch points

Flow: `POST /api/lm/download-model` (`py/routes/model_route_registrar.py:104`; GET variant `:105` for the browser extension) → `ModelDownloadHandler.download_model` (`model_handlers.py:1740`) → `DownloadModelUseCase.execute` → `DownloadCoordinator.schedule_download` → `DownloadManager.download_from_civitai` (`download_manager.py:386`) → `_execute_original_download` (`:1415`). Inside, seven scatter points need an `other` branch:

1. **Type map** (`:1496-1507`): accept `model.type.lower() in VALID_OTHER_CIVITAI_TYPES` → `model_type = "other"` (reuses the Phase-1 set, incl. `"other"` itself).
2. **Early version-exists gate** (`:1436-1463`): add `other_scanner.check_model_version_exists`.
3. **File-level exists gate** (`:1640-1655` → `_find_local_file_entry` `:320-346` → `_get_scanner_for_model_type` `:230-236`): add explicit `other` branch. **Trap**: the function currently falls through to the lora scanner for unknown types — `"other"` would silently dedupe against loras. Also narrow the fall-through to `"lora"` only / raise on unknown.
4. **Version-level fallback gate** (`:1656-1688`): add `elif model_type == "other"`.
5. **Default-root selection** (`:1690-1727`): for `other`, first resolve sub_type (§9.2), then read `default_other_roots[sub_type]` (§9.3); if sub_type is undecidable or no default root configured → error guiding the user to pick a folder explicitly.
6. **Metadata class selection** (`:1909-1928`) + `_build_metadata_for_resume` (`:969-981`): add `OtherModelMetadata.from_civitai_info` branches.
7. **Post-download cache write** (`_execute_download_pipeline` `:2622-2679`): add `other` scanner branch; `adjust_metadata` re-derives sub_type from the on-disk root automatically. `_get_supported_extensions_for_type` (`:2720-2744`): `other` reuses the checkpoint extension set.

Hooks: `_record_downloaded_version_history` (model_type is free text — zero change); `_sync_downloaded_version` (`:1984` → scanner dispatch `:2130-2135`) add `other`; `py/utils/example_images_download_manager.py` scanner dispatch at `:411-421`, `:591-601`, `:1089+` — add `other` at all three (silent no-scanner otherwise).

Path templates: `get_download_path_template("other")` is unset, so `other` resolves to a **flat** layout (empty template) — downloads land directly under the resolved sub_type root. This is deliberate: other-model roots are already split per sub_type (`default_other_roots`), and `priority_tags` has no `other` entry, so `{first_tag}` would fall back to an arbitrary CivitAI tag and scatter files into unstable folders. Users who want nesting can still set `download_path_templates["other"]` in `settings.json`. See `DEFAULT_DOWNLOAD_PATH_TEMPLATES` (`py/utils/constants.py`) and `DEFAULT_PATH_TEMPLATES` (`static/js/utils/constants.js`).

### 9.2 File-level routing (model.type / file.type → sub_type) **[locked]**

Table-driven, mirroring Phase 1. New in `py/utils/constants.py`:

```python
CIVITAI_FILE_TYPE_TO_OTHER_SUB_TYPE = {
    "VAE": "vae", "Upscaler": "upscaler", "Text Encoder": "text_encoder",
    "Vision Encoder": "clip_vision", "CLIPVision": "clip_vision",
    "ControlNet": "controlnet",
}
```

`download_routing.py` gains `resolve_other_download_sub_type(civitai_model_type, file_types, selected_file_type=None)` with fixed priority:

1. **Explicit user file pick** (`file_params` from #1058's `_resolve_target_file`) — if the picked file's type maps, it wins even when model.type is `Checkpoint`.
2. **model.type** via the existing `CIVITAI_TYPE_TO_OTHER_SUB_TYPE` (`constants.py:120-127`).
3. **file.type fallback** — only when model.type maps to nothing (e.g. model.type `Other` or retired `CLIP`). MUST NOT override a mapped model.type: checkpoint models routinely bundle VAE/Text Encoder component files, and unconditional file-type routing would misroute them.
4. Still undecidable → `None`; `use_default_paths` errors and the UI offers all other roots for manual selection.

HTTP: extend `DownloadRoutingHandler.get_download_routing` (`download_routing_handlers.py:23`) with an `other` branch returning `{root_kind: "other", sub_type: ...}`; add `GET /api/lm/other/roots_by_subtype` in `OtherRoutes.setup_specific_routes` (data from `config._prepare_other_paths`'s per-key roots, aggregating `text_encoders` + legacy `clip` under `text_encoder`).

### 9.3 Settings: single dict key `default_other_roots` **[locked]**

Rejected: four flat keys (`default_vae_root`…) — each flat key costs ~13 touch points in `settings_manager.py` (defaults `:82-85`, `_check_and_auto_set` `:890-895`, `set()` `:1621-1628`, `_update_active_library_entry` `:738-805`, upsert/create signatures `:1953-2132`, `_build_library_payload` `:552-612`, `_sync_active_library_to_root` `:519-547`, three library constructors, frontend `DEFAULT_SETTINGS_BASE`), repeated per future sub_type.

Chosen: one mapping key `default_other_roots: {sub_type: path}`, copying the `extra_folder_paths` precedent (generic Mapping handling at `:533-535`, `:573-578`, `:763-767`). `_check_and_auto_set` generalizes to per-sub_type candidates (union over that sub_type's folder keys — `text_encoder` → `text_encoders` + `clip`). `set()` validates keys against `VALID_OTHER_SUB_TYPES`.

Also fix the Phase-1 omission: add `"other_scanner"` to `_notify_library_change` (`:2150-2156`) and `_notify_model_name_display_change` (`:1795-1800`) — otherwise switching libraries leaves the other page stale.

### 9.4 Settings UI

- `templates/components/modals/settings/library.html:34-40`: sub_type selectors after the existing four `setting_select`s (Jinja loop; controlnet selector only when `enabled_other_folders` includes it). Dict-subkey save helper `saveOtherRootSetting(subType, value)` alongside the flat `saveSelectSetting`.
- `static/js/managers/SettingsManager.js:1547-1697`: `loadOtherRoots()` mirroring `loadUnetRoots()`, fed by `/api/lm/other/roots_by_subtype`; current values from `state.global.settings.default_other_roots`. `state/index.js:24` `DEFAULT_SETTINGS_BASE` += `default_other_roots: {}`.
- Optional: one `other` row in the download-path-template block (`library.html:153-211`).
- i18n: `settings.folderSettings.*` keys into `locales/en.json` + sync script; other locales keep `[TODO: Translate]`.
- Settings GET (`misc_handlers.py:1528-1536`) already returns all non-sensitive keys — new key reaches the frontend for free.

### 9.5 Frontend download entry

- `templates/components/controls.html:83`: drop the `page_id != 'other'` exclusion on the download button (keyboard shortcut D self-enables via `PageControls.js:196-198`).
- `OtherControls.js:22-55`: add `showDownloadModal: () => downloadManager.showDownloadModal()` (mirror `EmbeddingsControls.js:43-45`).
- `DownloadManager.js` `proceedToLocationContent` (`:955-1017`): add `_resolveOtherSubType()` (mirror `_resolveIsDiffusionModel` `:1026`): selected file type → `/api/lm/download/routing` → `otherApiClient.fetchModelRoots(subType)` (new); default-root preselect reads `default_other_roots[subType]` instead of `` `default_${singularType}_root` `` (`:974`). Undecidable → list all other roots (`/api/lm/other/roots`) for manual pick; an explicit save_dir skips backend default-root logic, so the two paths cannot disagree.
- `ModelVersionsTab` download buttons are modelType-generic and already work via `getModelApiClient('other')`; context menu has no CivitAI download entry — no change.
- Version-list type validation (`get_civitai_versions` → `_validate_civitai_model_type`) already accepts `VALID_OTHER_CIVITAI_TYPES` from Phase 1.

### 9.6 CivitAI type mapping decisions **[locked]**

- Download accepts exactly `VALID_OTHER_CIVITAI_TYPES` (`VAE, Upscaler, TextEncoder, CLIP, CLIPVision, Controlnet, Other`) — reuse the Phase-1 tables; do NOT create new ones.
- Extend `CIVITAI_USER_MODEL_TYPES` (`constants.py:133-137`) with the 7 aliases, and point them at the other scanner / `"other"` history bucket in `misc_handlers.py` (`type_scanner_map` `:2793-2797`, `downloaded_version_map` `:2821-2827`) — otherwise creator pages silently filter these models while downloads claim support.
- Fix (small Phase-1 bug): `OtherModelMetadata.from_civitai_info` (`py/utils/models.py:343`) reads `version_info.get("type")`, but the type lives at `version["model"]["type"]` — the mapping never fires and always degrades to the placeholder. Read `version_info.get("model", {}).get("type")` instead. (`CheckpointMetadata:290` has the same shape; leave it alone here.)

### 9.7 Tests

Existing base: `tests/services/test_download_manager_basic.py` (incl. `test_download_rejects_unsupported_model_type` `:1336`), `test_download_manager_error.py`, `test_download_manager_concurrent.py`, `tests/integration/test_download_flow.py`, `tests/services/test_settings_manager.py`; frontend `tests/frontend/managers/downloadManager.routing.test.js`, `settingsManager.library.test.js`.

Add: (1) `resolve_other_download_sub_type` unit tests — every priority tier, bundled-component anti-misrouting, undecidable → None, civarchive-shaped payload; (2) download_manager — six model.types accepted → other scanner (mock), unknown still rejected, no lora-scanner fall-through, per-sub_type default roots + unconfigured error, resume metadata, extension set; (3) settings_manager — `default_other_roots` defaults/auto-set (incl. text_encoder dual-key union)/library sync/upsert passthrough/illegal sub_type rejection; (4) routes — `/api/lm/download/routing` other branch, `roots_by_subtype` shape; (5) example-images dispatch accepts `other` (3 sites); (6) vitest — `_resolveOtherSubType` + root select + default preselect, `loadOtherRoots`; (7) user-models existsLocally for VAE.

### 9.8 Phase 2 file list

Backend: `py/utils/constants.py`, `py/services/download_routing.py`, `py/routes/handlers/download_routing_handlers.py`, `py/services/download_manager.py`, `py/utils/example_images_download_manager.py`, `py/services/settings_manager.py`, `py/utils/models.py`, `py/routes/other_routes.py`, `py/routes/handlers/misc_handlers.py`, `settings.json.example`.
Frontend/templates: `templates/components/controls.html`, `static/js/components/controls/OtherControls.js`, `static/js/managers/DownloadManager.js`, `static/js/api/otherApi.js`, `templates/components/modals/settings/library.html`, `static/js/managers/SettingsManager.js`, `static/js/state/index.js`, `locales/en.json` + sync.

## 10. Risks / Open Questions

- **Root overlap**: a user may point `text_encoders` at a directory already scanned as checkpoints/unet. Realpath dedup inside one scanner won't catch cross-scanner overlap → the `_prepare_other_paths` overlap warning (§4.3) is the mitigation; duplicate cards across pages are cosmetic, not corrupting (cache keyed by `(model_type, file_path)`).
- **Huge text encoders + lazy hash**: CivitAI fetch for a pending-hash model must trigger on-demand hash like checkpoints do — verify that flow (`calculate_hash_for_model`) is reachable from the `other` routes' fetch-metadata handler.
- **Retired CivitAI types**: `CLIP`/`CLIPVision` are retired upstream (grandfathered for existing models); metadata fetch must tolerate both retired and current types — `VALID_OTHER_CIVITAI_TYPES` includes them deliberately.
- **Standalone users** must add the new `folder_paths` keys to `settings.json` themselves; document in `settings.json.example` and the feature doc.
- **Page display name** is i18n-only; if "Other Models" tests poorly, rename `other.title` without code changes.

### Phase 2 risks

- **Bundled component files**: checkpoint models routinely ship VAE/Text Encoder component files — file.type routing must stay a fallback (or explicit user pick), never an override (§9.2 priority is load-bearing; test it).
- **`_get_scanner_for_model_type` lora fall-through** (`download_manager.py:236`): without an explicit `other` branch, dedupe checks run against the lora scanner — the most insidious trap in Phase 2.
- **text_encoder dual folder keys** (`text_encoders` + legacy `clip`): default-root candidates, `roots_by_subtype`, and auto-set must all merge both keys; miss one and the default-root dropdown comes up empty.
- **Undecidable sub_type** (model.type `Other` + unknown file types): must error and ask, never silently default to the vae folder.
- **Lazy hash after download**: downloads carry CivitAI SHA256 (no recompute needed) — ensure the post-download cache write doesn't leave `hash_status="pending"`, or the next metadata fetch re-hashes a 10 GB file.
- **CivArchive source**: same `_execute_original_download` path, same payload shape — cover it once in tests.

## 11. Phase 3 — Opt-in Management Toggles (implemented)

Designed 2026-09-13 against the Phase-1/2 code. Other Models is **opt-in**: after
Phase 3 the feature ships disabled, so no other-model folder is scanned and the
page shows an "enable" empty state until the user turns it on.

### 11.1 Settings (global, not per-library)

| key | type | default | meaning |
|---|---|---|---|
| `enable_other_models` | bool | `false` | master switch |
| `enabled_other_sub_types` | list[str] | `["vae","upscaler","text_encoder"]` | allow-list; `clip_vision` and `controlnet` are opt-in (see §2) |

`enabled_other_folders` (the unreleased, additive, no-UI backend key) was removed
and replaced by the sub_type-level allow-list; there is no migration because the
feature never shipped. `text_encoder` expands to `text_encoders` + legacy `clip`
via `OTHER_SUB_TYPE_FOLDER_KEYS`.

The default allow-list lives on five surfaces that must stay in sync:
`DEFAULT_ENABLED_OTHER_SUB_TYPES` (`py/utils/constants.py`), `DEFAULT_SETTINGS`
(`py/services/settings_manager.py`), the two `DEFAULT_SETTINGS_BASE` /
`createDefaultSettings` lists (`static/js/state/index.js`), the
`updateOtherModelsControls()` fallback (`static/js/managers/SettingsManager.js`)
and the server-rendered Jinja fallback
(`templates/components/modals/settings/library.html`).

### 11.1.1 Legacy key handling in `Config._init_other_paths`

ComfyUI's `folder_paths` rewrites legacy names before every access (`clip` →
`text_encoders`, `unet` → `diffusion_models`) and registers both legacy
directories under the canonical key, so `get_folder_paths("clip")` returns
exactly the same list as `get_folder_paths("text_encoders")`. Querying both keys
made the overlap guard fire twice with `please fix your path configuration` for a
configuration the user cannot fix. `Config._collapse_legacy_folder_keys()` now
drops a key when the host exposes `map_legacy` and resolves it to another queried
key, and `_prepare_other_paths()` downgrades a same-`sub_type` duplicate to
`debug` (a cross-`sub_type` collision still warns). In standalone mode
`MockFolderPaths` has no `map_legacy` and its keys are independent
`settings.json` entries, so every key is still queried there.

`settings.json.example` intentionally stays minimal (only `use_portable_settings`,
`civitai_api_key`, and the four core `folder_paths` keys: `loras`, `checkpoints`,
`unet`, `embeddings`). Optional keys — including the other-model folder paths and
`enable_other_models` — are NOT documented there; they live in `DEFAULT_SETTINGS`
and reach the user's `settings.json` on demand. This supersedes the Phase-1/Phase-2
notes that proposed adding the other-model folder keys to the example.

### 11.2 Behaviour matrix

| state | scan | nav / `/other` | other downloads | `default_other_roots` | Doctor / refresh-all |
|---|---|---|---|---|---|
| master off | nothing (`other_roots == []`) | nav entry hidden (`nav-item--hidden`); `/other` still renders the disabled empty state + Enable button; one-time dismissible announcement banner on first visit | rejected | preserved, never auto-set | scanner skipped |
| sub_type off | that sub_type's folder keys excluded | page keeps working, type disappears from data | auto-routing refused (manual folder still allowed) | preserved, not preselected | normal |
| all on (after enabling) | Phase-1/2 behaviour | normal | normal | normal | normal |

### 11.3 Backend touch points

- `py/utils/constants.py` — `DEFAULT_ENABLED_OTHER_SUB_TYPES`, `OTHER_SUB_TYPE_FOLDER_KEYS`, `normalize_other_sub_types`.
- `py/config.py` — `_get_enabled_other_folder_keys()` is the single scan gate (master switch + allow-list); new `refresh_other_roots()` rebuilds roots + preview roots on toggle.
- `py/services/settings_manager.py` — new defaults, `set()` normalization, `is_other_models_enabled()` / `get_enabled_other_sub_types()` / `is_other_sub_type_enabled()`, and `_apply_other_model_settings_change()` which reapplies config and calls `other_scanner.on_library_changed(reconcile=True)`.
- `py/services/model_scanner.py` — `_should_keep_cached_entry()` hydration hook (default keep) plus `on_library_changed(reconcile=...)` / `initialize_in_background(reconcile=...)`; the hook filters `raw_data` and the hash/autov3 index rows.
- `py/services/other_scanner.py` — drops persisted entries whose folder is no longer a managed root (sub_type is location-derived, so config is the source of truth).
- `py/routes/other_routes.py` — `_validate_civitai_model_type` rejects everything while off / mapped-but-disabled sub_types; `_get_page_context_provider()` injects `other_disabled` into the template.
- `py/routes/handlers/model_handlers.py` + `base_model_routes.py` — optional `page_context_provider` hook on `ModelPageView`.
- `py/routes/handlers/download_routing_handlers.py` — returns `{sub_type: None, disabled: true, reason}` instead of guessing.
- `py/services/download_manager.py` — rejects other-type downloads while off; disabled sub_type refuses default-path routing with a "pick a folder" error.
- `py/routes/handlers/misc_handlers.py` — Doctor / init-status / refresh-all skip the other scanner while off (`_active_scanner_factories` / `_active_scanner_getters`).
- `py/services/pending_delete_service.py` — deliberately untouched: the scanner stays registered so staged deletes still merge.

### 11.4 Frontend

Discoverability: the nav entry is hidden while the feature is off, and three
lightweight surfaces replace it — a one-time announcement banner, the download
toast, and the settings toggle itself.

- `templates/components/header.html` + `static/css/components/header.css` — `nav-item--hidden` class (server-rendered when off, client-toggled after enabling) and the `fa-shapes` icon.
- `templates/other.html` — `other_disabled` branch in `content` + `main_script`; page-scoped CSS for the empty state.
- `static/js/other_disabled.js` — boots `appCore` (shared header) and delegates to the shared enable helper.
- `static/js/utils/otherModels.js` — shared `enableOtherModels()` (POST settings + reload) and `openOtherModelsSettings()` (settings modal on the Library section); used by the disabled page, the banner and the download modal.
- `static/js/managers/BannerService.js` — `other-models-announcement` banner (only when off and not dismissed; `priority: 0`, dismissal persisted via `dismissed_banners`) with Enable / Open Settings actions; `removeOtherModelsAnnouncement()` drops it without persisting a dismissal.
- `templates/components/modals/settings/library.html` + `SettingsManager.updateOtherModelsControls()` / `saveEnabledOtherSubTypes()` / `updateOtherModelsNavVisibility()` — master toggle + five sub_type checkboxes; unchecked/disabled sub_types have their default-root select disabled.
- `static/js/managers/DownloadManager.js` — a disabled routing answer surfaces a `showActionToast` with an "Enable Other Models" action (opening settings) and falls back to manual selection.
- i18n: `settings.folderSettings.*`, `other.disabled.*` and `banners.otherModels.*` keys in `locales/en.json` + `scripts/sync_translation_keys.py` (other locales keep `[TODO: Translate]`).

### 11.5 Cache consistency

- Disabling purges rows from the in-memory view at hydration time (the
  `_should_keep_cached_entry` hook) and from SQLite on the reconcile triggered by
  the toggle; the `.metadata.json` sidecars survive, so re-enabling rescans
  without recomputing hashes (critical for multi-GB text encoders).
- Enabling triggers a reconcile so newly managed roots are scanned immediately.
- Editing `settings.json` while the server is stopped is still covered by the
  hydration hook, so disabled types never appear after a restart.

### 11.6 Tests

Backend: opt-in fixtures added to the other-related suites; new coverage for
"default off scans nothing", per-sub_type gating, routing/download rejection,
`_should_keep_cached_entry`, settings normalization and `other_disabled` page
context. Frontend: `updateOtherModelsControls` / `saveEnabledOtherSubTypes` and
the disabled-page enable flow.

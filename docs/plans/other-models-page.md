# Plan: "Other Models" Page — Unified Management for VAE / Upscaler / Text Encoder / etc.

**Status:** v1 — decisions locked with feature owner (2026-09-12); ready for implementation.
**Scope (Phase 1):** scan + manage (list, search, filter, tags, folders, preview, rename, move, delete/exclude, CivitAI metadata fetch) for a new model type `other`, exposed as a new web page. **Phase 2 (out of scope here, outlined in §9):** one-click download from CivitAI for these types.

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
   | `clip_vision` | `clip_vision` | `CLIPVision` | yes |
   | `controlnet` | `controlnet` | `Controlnet` | no (mapping present, opt-in) |

   New folder categories = one line in the mapping table (see §4.1).

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

## 9. Phase 2 Outline (NOT in this implementation)

CivitAI downloads for `other` types:

- `py/services/download_manager.py`: extend the type map (`:1496-1507` — currently rejects unknown types), `_get_scanner_for_model_type` (`:230-236`), `_build_metadata_for_resume` (`:977-981`).
- **Default-root selection** (`:1699-1727`): needs per-sub_type settings keys (`default_vae_root`, `default_upscaler_root`, …) — this is what pulls in `settings_manager.py` (library default keys `:82-85`, `_check_and_auto_set` ~`:890`, `set()` dispatch `:1621-1628`, `upsert_library` params, library-switch scanner notifications `:1795-1799`/`:2150-2155`).
- File-type routing: consult CivitAI's `primaryFileTypesByModelType` (e.g. CLIP-type models ship `Text Encoder`/`Vision Encoder` primary files, not `Model`); a `file.type → target folder` map analogous to `download_routing.py:is_diffusion_model_download`.
- Settings UI for the new default roots.

## 10. Risks / Open Questions

- **Root overlap**: a user may point `text_encoders` at a directory already scanned as checkpoints/unet. Realpath dedup inside one scanner won't catch cross-scanner overlap → the `_prepare_other_paths` overlap warning (§4.3) is the mitigation; duplicate cards across pages are cosmetic, not corrupting (cache keyed by `(model_type, file_path)`).
- **Huge text encoders + lazy hash**: CivitAI fetch for a pending-hash model must trigger on-demand hash like checkpoints do — verify that flow (`calculate_hash_for_model`) is reachable from the `other` routes' fetch-metadata handler.
- **Retired CivitAI types**: `CLIP`/`CLIPVision` are retired upstream (grandfathered for existing models); metadata fetch must tolerate both retired and current types — `VALID_OTHER_CIVITAI_TYPES` includes them deliberately.
- **Standalone users** must add the new `folder_paths` keys to `settings.json` themselves; document in `settings.json.example` and the feature doc.
- **Page display name** is i18n-only; if "Other Models" tests poorly, rename `other.title` without code changes.

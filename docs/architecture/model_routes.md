# Base model route architecture

The `BaseModelRoutes` controller centralizes HTTP endpoints that every model type
(LoRAs, checkpoints, embeddings, etc.) share.  Each handler either forwards the
request to the injected service, delegates to a utility in
`ModelRouteUtils`, or orchestrates long‑running operations via helper services
such as the download or WebSocket managers.  The table below lists every handler
exposed in `py/routes/base_model_routes.py`, the collaborators it leans on, and
any cache or WebSocket side effects implemented in
`py/utils/routes_common.py`.

## Contents

- [Handler catalogue](#handler-catalogue)
- [Dependency map and contracts](#dependency-map-and-contracts)
  - [Cache and metadata mutations](#cache-and-metadata-mutations)
  - [Download and WebSocket flows](#download-and-websocket-flows)
  - [Read-only queries](#read-only-queries)
  - [Template rendering and initialization](#template-rendering-and-initialization)

## Handler catalogue

The routes exposed by `BaseModelRoutes` combine HTTP wiring with a handful of
shared helper classes.  Services surface filesystem and metadata operations,
`ModelRouteUtils` bundles cache-sensitive mutations, and `ws_manager`
coordinates fan-out to browser clients.  The tables below expand the existing
catalogue into explicit dependency maps and invariants so refactors can reason
about the expectations each collaborator must uphold.

## Dependency map and contracts

### Cache and metadata mutations

| Endpoint(s) | Delegate(s) | State touched | Invariants / contracts |
| --- | --- | --- | --- |
| `/api/lm/{prefix}/delete` | `ModelRouteUtils.handle_delete_model()` | Removes files from disk, prunes `scanner._cache.raw_data`, awaits `scanner._cache.resort()`, calls `scanner._hash_index.remove_by_path()`. | Cache and hash index must no longer reference the deleted path; resort must complete before responding to keep pagination deterministic. |
| `/api/lm/{prefix}/exclude` | `ModelRouteUtils.handle_exclude_model()` | Mutates metadata records, `scanner._cache.raw_data`, `scanner._hash_index`, `scanner._tags_count`, and `scanner._excluded_models`. | Excluded models remain discoverable via exclusion list while being hidden from listings; tag counts stay balanced after removal. |
| `/api/lm/{prefix}/fetch-civitai` | `ModelRouteUtils.fetch_and_update_model()` | Reads `scanner._cache.raw_data`, writes metadata JSON through `MetadataManager`, syncs cache via `scanner.update_single_model_cache`. | Requires a cached SHA256 hash; cache entries must reflect merged metadata before formatted response is returned. |
| `/api/lm/{prefix}/fetch-all-civitai` | `ModelRouteUtils.fetch_and_update_model()`, `ws_manager.broadcast()` | Iterates over cache, updates metadata files and cache records, optionally awaits `scanner._cache.resort()`. | Progress broadcasts follow started → processing → completed; if any model name changes, cache resort must run once before completion broadcast. |
| `/api/lm/{prefix}/relink-civitai` | `ModelRouteUtils.handle_relink_civitai()` | Updates metadata on disk and resynchronizes the cache entry. | The new association must propagate to `scanner.update_single_model_cache` so duplicate resolution and listings reflect the change immediately. |
| `/api/lm/{prefix}/replace-preview` | `ModelRouteUtils.handle_replace_preview()` | Writes optimized preview file, persists metadata via `MetadataManager`, updates cache with `scanner.update_preview_in_cache()`. | Preview path stored in metadata and cache must match the normalized file system path; NSFW level integer is synchronized across metadata and cache. |
| `/api/lm/{prefix}/save-metadata` | `ModelRouteUtils.handle_save_metadata()` | Writes metadata JSON and ensures cache entry mirrors the latest content. | Metadata persistence must be atomic—cache data should match on-disk metadata before response emits success. |
| `/api/lm/{prefix}/add-tags` | `ModelRouteUtils.handle_add_tags()` | Updates metadata tags, increments `scanner._tags_count`, and patches cached item. | Tag frequency map remains in sync with cache and metadata after increments. |
| `/api/lm/{prefix}/rename` | `ModelRouteUtils.handle_rename_model()` | Renames files, metadata, previews; updates cache indices and hash mappings. | File moves succeed or rollback as a unit so cache state never points to a missing file; hash index entries track the new path. |
| `/api/lm/{prefix}/bulk-delete` | `ModelRouteUtils.handle_bulk_delete_models()` | Delegates to `scanner.bulk_delete_models()` to delete files, trim cache, resort, and drop hash index entries. | Every requested path is removed from cache and index; resort happens once after bulk deletion. |
| `/api/lm/{prefix}/verify-duplicates` | `ModelRouteUtils.handle_verify_duplicates()` | Recomputes hashes, updates metadata and cached entries if discrepancies found. | Hash metadata stored in cache must mirror recomputed values to guarantee future duplicate checks operate on current data. |
| `/api/lm/{prefix}/scan` | `service.scan_models()` | Rescans filesystem, rebuilding scanner cache. | Scanner replaces its cache atomically so subsequent requests observe a consistent snapshot. |
| `/api/lm/{prefix}/move_model` | `ModelMoveService.move_model()` | Moves files/directories and notifies scanner via service layer conventions. | Move operations respect filesystem invariants (target path exists, metadata follows file) and emit success/failure without leaving partial moves. |
| `/api/lm/{prefix}/move_models_bulk` | `ModelMoveService.move_models_bulk()` | Batch move behavior as above. | Aggregated result enumerates successes/failures while preserving per-model atomicity. |
| `/api/lm/{prefix}/auto-organize` (GET/POST) | `ModelFileService.auto_organize_models()`, `ws_manager.get_auto_organize_lock()`, `WebSocketProgressCallback` | Writes organized files, updates metadata, and streams progress snapshots. | Only one auto-organize job may run; lock must guard reentrancy and WebSocket updates must include latest progress payload consumed by polling route. |

### Download and WebSocket flows

| Endpoint(s) | Delegate(s) | State touched | Invariants / contracts |
| --- | --- | --- | --- |
| `/api/lm/download-model` (POST) & `/api/lm/download-model-get` (GET) | `ModelRouteUtils.handle_download_model()`, `ServiceRegistry.get_download_manager()` | Schedules downloads, registers `ws_manager.broadcast_download_progress()` callback that stores progress in `ws_manager._download_progress`. | Download IDs remain stable across POST/GET helpers; every progress callback persists a timestamped entry so `/download-progress` and WebSocket clients share consistent snapshots. |
| `/api/lm/cancel-download-get` | `ModelRouteUtils.handle_cancel_download()` | Signals download manager, prunes `ws_manager._download_progress`, and emits cancellation broadcast. | Cancel requests must tolerate missing IDs gracefully while ensuring cached progress is removed once cancellation succeeds. |
| `/api/lm/download-progress/{download_id}` | `ws_manager.get_download_progress()` | Reads cached progress dictionary. | Returns `404` when progress is absent; successful payload surfaces the numeric `progress` stored during broadcasts. |
| `/api/lm/{prefix}/fetch-all-civitai` | `ws_manager.broadcast()` | Broadcast loop described above. | Broadcast cadence cannot skip completion/error messages so clients know when to clear UI spinners. |
| `/api/lm/{prefix}/auto-organize-progress` | `ws_manager.get_auto_organize_progress()` | Reads cached progress snapshot. | Route returns cached payload verbatim; absence yields `404` to signal idle state. |

### Read-only queries

| Endpoint(s) | Delegate(s) | State touched | Invariants / contracts |
| --- | --- | --- | --- |
| `/api/lm/{prefix}/list` | `service.get_paginated_data()`, `service.format_response()` | Reads service-managed pagination data. | Formatting must be applied to every item before response; pagination metadata echoes service result. |
| `/api/lm/{prefix}/top-tags` | `service.get_top_tags()` | Reads aggregated tag counts. | Limit parameter bounded to `[1, 100]`; response always wraps tags in `{success: True}` envelope. |
| `/api/lm/{prefix}/base-models` | `service.get_base_models()` | Reads service data. | Same limit handling as tags. |
| `/api/lm/{prefix}/roots` | `service.get_model_roots()` | Reads configured roots. | Always returns `{success: True, roots: [...]}`. |
| `/api/lm/{prefix}/folders` | `service.scanner.get_cached_data()` | Reads folder summaries from cache. | Cache access must tolerate initialization phases by surfacing errors via HTTP 500. |
| `/api/lm/{prefix}/folder-tree` | `service.get_folder_tree()` | Reads derived tree for requested root. | Rejects missing `model_root` with HTTP 400. |
| `/api/lm/{prefix}/unified-folder-tree` | `service.get_unified_folder_tree()` | Aggregated folder tree. | Returns `{success: True, tree: ...}` or 500 on error. |
| `/api/lm/{prefix}/find-duplicates` | `service.find_duplicate_hashes()`, `service.scanner.get_cached_data()`, `service.get_path_by_hash()` | Reads cache and hash index to format duplicates. | Only returns groups with more than one resolved model. |
| `/api/lm/{prefix}/find-filename-conflicts` | `service.find_duplicate_filenames()`, `service.scanner.get_cached_data()`, `service.scanner.get_hash_by_filename()` | Similar read-only assembly. | Includes resolved main index entry when available; empty `models` groups are omitted. |
| `/api/lm/{prefix}/get-notes` | `service.get_model_notes()` | Reads persisted notes. | Missing notes produce HTTP 404 with explicit error message. |
| `/api/lm/{prefix}/preview-url` | `service.get_model_preview_url()` | Resolves static URL. | Successful responses wrap URL in `{success: True}`; missing preview yields 404 error payload. |
| `/api/lm/{prefix}/civitai-url` | `service.get_model_civitai_url()` | Returns remote permalink info. | Response envelope matches preview pattern. |
| `/api/lm/{prefix}/metadata` | `service.get_model_metadata()` | Reads metadata JSON. | Responds with raw metadata dict or 500 on failure. |
| `/api/lm/{prefix}/model-description` | `service.get_model_description()` | Returns formatted description string. | Always JSON with success boolean. |
| `/api/lm/{prefix}/relative-paths` | `service.get_relative_paths()` | Resolves filesystem suggestions. | Maintains read-only contract. |
| `/api/lm/{prefix}/civitai/versions/{model_id}` | `get_default_metadata_provider()`, `service.has_hash()`, `service.get_path_by_hash()` | Reads remote API, cross-references cache. | Versions payload includes `existsLocally`/`localPath` only when hashes match local indices. |
| `/api/lm/{prefix}/civitai/model/version/{modelVersionId}` | `get_default_metadata_provider()` | Remote metadata lookup. | Errors propagate as JSON with `{success: False}` payload. |
| `/api/lm/{prefix}/civitai/model/hash/{hash}` | `get_default_metadata_provider()` | Remote metadata lookup. | Missing hashes return 404 with `{success: False}`. |

### Template rendering and initialization

| Endpoint(s) | Delegate(s) | State touched | Invariants / contracts |
| --- | --- | --- | --- |
| `/{prefix}` | `handle_models_page` | Reads configuration via `settings`, sets locale with `server_i18n`, pulls cached folders through `service.scanner.get_cached_data()`, renders Jinja template. | Template rendering must tolerate scanner initialization by flagging `is_initializing`; i18n filter is attached exactly once per environment to avoid duplicate registration errors. |

### Contract sequences

The following high-level sequences show how the collaborating services work
together for the most stateful operations:

```
delete_model request
    → BaseModelRoutes.delete_model
    → ModelRouteUtils.handle_delete_model
        → filesystem delete + metadata cleanup
        → scanner._cache.raw_data prune
        → await scanner._cache.resort()
        → scanner._hash_index.remove_by_path()
```

```
replace_preview request
    → BaseModelRoutes.replace_preview
    → ModelRouteUtils.handle_replace_preview
        → ExifUtils.optimize_image / config.get_preview_static_url
        → MetadataManager.save_metadata
        → scanner.update_preview_in_cache(model_path, preview_path, nsfw_level)
```

```
download_model request
    → BaseModelRoutes.download_model
    → ModelRouteUtils.handle_download_model
        → ServiceRegistry.get_download_manager().download_from_civitai(..., progress_callback)
        → ws_manager.broadcast_download_progress(download_id, data)
        → ws_manager._download_progress[download_id] updated with timestamp
        → /api/lm/download-progress/{id} polls ws_manager.get_download_progress
```

These contracts complement the tables above: if any collaborator changes its
behavior, the invariants called out here must continue to hold for the routes
to remain predictable.

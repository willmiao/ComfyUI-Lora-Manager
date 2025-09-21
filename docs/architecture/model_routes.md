# Base model route architecture

The `BaseModelRoutes` controller centralizes HTTP endpoints that every model type
(LoRAs, checkpoints, embeddings, etc.) share.  Each handler either forwards the
request to the injected service, delegates to a utility in
`ModelRouteUtils`, or orchestrates long‑running operations via helper services
such as the download or WebSocket managers.  The table below lists every handler
exposed in `py/routes/base_model_routes.py`, the collaborators it leans on, and
any cache or WebSocket side effects implemented in
`py/utils/routes_common.py`.

## Handler catalogue

| Endpoint(s) | Handler | Purpose | Collaborators | Cache / WebSocket side effects |
| --- | --- | --- | --- | --- |
| `/{prefix}` | `handle_models_page` | Renders the HTML page for a model type, populating the template from cached scanner data when available. | `settings`, `server_i18n`, `service.scanner.get_cached_data()` | Reads scanner cache to build folder list; flags initialization state without mutating cache. |
| `/api/lm/{prefix}/list` | `get_models` | Returns paginated model metadata. | `service.get_paginated_data()`, `service.format_response()` | None (read-only). |
| `/api/lm/{prefix}/delete` | `delete_model` | Removes a single model from disk and cache. | `ModelRouteUtils.handle_delete_model()` | Deletes files, prunes `scanner.get_cached_data().raw_data`, calls `cache.resort()`, and updates `scanner._hash_index`. |
| `/api/lm/{prefix}/exclude` | `exclude_model` | Marks a model as excluded so it no longer appears in listings. | `ModelRouteUtils.handle_exclude_model()` | Updates metadata, decrements `scanner._tags_count`, removes cache entry and hash index entry, and appends to `scanner._excluded_models`. |
| `/api/lm/{prefix}/fetch-civitai` | `fetch_civitai` | Fetches metadata for a specific model from CivitAI. | `ModelRouteUtils.fetch_and_update_model()` | Uses scanner cache to find the target record and updates it via `scanner.update_single_model_cache`. |
| `/api/lm/{prefix}/fetch-all-civitai` | `fetch_all_civitai` | Bulk refreshes metadata for models missing CivitAI info. | `ModelRouteUtils.fetch_and_update_model()`, `ws_manager.broadcast()` | Streams progress to all clients, updates cache entries, optionally resorts cached data. |
| `/api/lm/{prefix}/relink-civitai` | `relink_civitai` | Re-associates a local file with a CivitAI entry. | `ModelRouteUtils.handle_relink_civitai()` | Updates metadata, refreshes cache via `scanner.update_single_model_cache`. |
| `/api/lm/{prefix}/replace-preview` | `replace_preview` | Replaces the preview asset attached to a model. | `ModelRouteUtils.handle_replace_preview()` | Writes new preview file, updates metadata, and calls `scanner.update_preview_in_cache()`. |
| `/api/lm/{prefix}/save-metadata` | `save_metadata` | Persists edits to model metadata. | `ModelRouteUtils.handle_save_metadata()` | Saves metadata file and syncs the cache entry. |
| `/api/lm/{prefix}/add-tags` | `add_tags` | Adds or increments tags for a model. | `ModelRouteUtils.handle_add_tags()` | Mutates metadata, increments `scanner._tags_count`, and updates the cached model. |
| `/api/lm/{prefix}/rename` | `rename_model` | Renames a model and its related assets. | `ModelRouteUtils.handle_rename_model()` | Renames files on disk, updates cache indices, refreshes metadata. |
| `/api/lm/{prefix}/bulk-delete` | `bulk_delete_models` | Deletes multiple models in one request. | `ModelRouteUtils.handle_bulk_delete_models()` | Delegates to `scanner.bulk_delete_models()` which removes disk assets and cache records in bulk. |
| `/api/lm/{prefix}/verify-duplicates` | `verify_duplicates` | Confirms that a list of files share the same hash. | `ModelRouteUtils.handle_verify_duplicates()` | Recalculates hashes, updates metadata, and patches cache entries when stored hashes change. |
| `/api/lm/{prefix}/top-tags` | `get_top_tags` | Returns the most frequently used tags. | `service.get_top_tags()` | None (read-only). |
| `/api/lm/{prefix}/base-models` | `get_base_models` | Lists base models referenced by this model type. | `service.get_base_models()` | None (read-only). |
| `/api/lm/{prefix}/scan` | `scan_models` | Triggers a rescan of the filesystem. | `service.scan_models()` | Scanner rebuilds its cache as part of the service workflow. |
| `/api/lm/{prefix}/roots` | `get_model_roots` | Enumerates root directories searched for this model type. | `service.get_model_roots()` | None (read-only). |
| `/api/lm/{prefix}/folders` | `get_folders` | Returns cached folder summaries. | `service.scanner.get_cached_data()` | Reads cached structure without mutation. |
| `/api/lm/{prefix}/folder-tree` | `get_folder_tree` | Builds a nested folder tree of cached items. | `service.scanner.get_cached_data()` | Reads cache; does not mutate. |
| `/api/lm/{prefix}/unified-folder-tree` | `get_unified_folder_tree` | Returns a tree aggregating all roots. | `service.scanner.get_cached_data()` | Reads cache; does not mutate. |
| `/api/lm/{prefix}/find-duplicates` | `find_duplicate_models` | Finds duplicate hashes within the cache. | `service.scanner.get_duplicates()`, `service.scanner.get_hash_by_filename()` | Uses cache data to assemble duplicate groups; no mutation. |
| `/api/lm/{prefix}/find-filename-conflicts` | `find_filename_conflicts` | Groups models that share a filename across directories. | `service.scanner.get_filename_conflicts()`, `service.get_path_by_hash()` | Reads cache while formatting results. |
| `/api/lm/{prefix}/get-notes` | `get_model_notes` | Retrieves saved notes for a model. | `service.get_model_notes()` | None (read-only). |
| `/api/lm/{prefix}/preview-url` | `get_model_preview_url` | Resolves the static preview URL for a model. | `service.get_model_preview_url()` | None (read-only). |
| `/api/lm/{prefix}/civitai-url` | `get_model_civitai_url` | Returns the CivitAI permalink for a model. | `service.get_model_civitai_url()` | None (read-only). |
| `/api/lm/{prefix}/metadata` | `get_model_metadata` | Loads the raw metadata payload for a model. | `service.get_model_metadata()` | None (read-only). |
| `/api/lm/{prefix}/model-description` | `get_model_description` | Returns a formatted description for the UI. | `service.get_model_description()` | None (read-only). |
| `/api/lm/{prefix}/relative-paths` | `get_relative_paths` | Provides filesystem auto-complete suggestions. | `service.get_relative_paths()` | None (read-only). |
| `/api/lm/{prefix}/civitai/versions/{model_id}` | `get_civitai_versions` | Lists remote versions and indicates which exist locally. | `get_default_metadata_provider()`, `self.service.has_hash()`, `self.service.get_path_by_hash()` | Read-only; consults cache/service indices to mark local availability. |
| `/api/lm/{prefix}/civitai/model/version/{modelVersionId}` | `get_civitai_model_by_version` | Fetches detailed metadata for a specific CivitAI version. | `get_default_metadata_provider()` | None (read-only). |
| `/api/lm/{prefix}/civitai/model/hash/{hash}` | `get_civitai_model_by_hash` | Fetches CivitAI details using a hash. | `get_default_metadata_provider()` | None (read-only). |
| `/api/lm/download-model` (POST) & `/api/lm/download-model-get` (GET) | `download_model`, `download_model_get` | Starts a download through the shared download manager. | `ModelRouteUtils.handle_download_model()`, `ServiceRegistry.get_download_manager()` | The helper broadcasts download progress via `ws_manager.broadcast_download_progress()` and stores state in `ws_manager._download_progress`. |
| `/api/lm/cancel-download-get` | `cancel_download_get` | Cancels an active download. | `ModelRouteUtils.handle_cancel_download()` | Broadcasts a cancellation message via `ws_manager.broadcast_download_progress()` and prunes download progress entries. |
| `/api/lm/download-progress/{download_id}` | `get_download_progress` | Reports cached download progress for a download ID. | `ws_manager.get_download_progress()` | Read-only view of cached progress. |
| `/api/lm/{prefix}/move_model` | `move_model` | Moves a model to a new folder. | `ModelMoveService.move_model()` | File operations performed by the injected service may update scanner caches downstream. |
| `/api/lm/{prefix}/move_models_bulk` | `move_models_bulk` | Bulk move models to a new location. | `ModelMoveService.move_models_bulk()` | File operations delegated to the service. |
| `/api/lm/{prefix}/auto-organize` (GET/POST) | `auto_organize_models` | Launches auto-organization for models, optionally limited to selected files. | `ModelFileService.auto_organize_models()`, `ws_manager.get_auto_organize_lock()`, `WebSocketProgressCallback` | Uses a shared asyncio lock, streams progress through `ws_manager.broadcast_auto_organize_progress()`, and relies on `ws_manager.is_auto_organize_running()` state. |
| `/api/lm/{prefix}/auto-organize-progress` | `get_auto_organize_progress` | Polls the latest auto-organize progress snapshot. | `ws_manager.get_auto_organize_progress()` | Read-only view of the WebSocket manager’s cached progress. |

## Shared utility side effects

The delegated helpers in `ModelRouteUtils` encapsulate most cache and
WebSocket mutations.  The smoke tests in this repository exercise the
following contracts from `py/utils/routes_common.py`:

* `handle_delete_model` removes matching records from
  `scanner.get_cached_data().raw_data`, awaits `cache.resort()`, and calls
  `scanner._hash_index.remove_by_path()` when an index is present before
  returning a success payload.
* `handle_replace_preview` writes a new preview file, persists metadata via
  `MetadataManager.save_metadata()`, and then invokes
  `scanner.update_preview_in_cache()` with the normalized preview path and
  NSFW level so downstream requests surface the updated asset.
* `handle_download_model` acquires the shared download manager from
  `ServiceRegistry`, injects a WebSocket progress callback, and relies on
  `ws_manager.broadcast_download_progress()` to update the cached progress map
  that `get_download_progress` later reads.
* `handle_bulk_delete_models`, `handle_add_tags`, `handle_exclude_model`, and
  `handle_verify_duplicates` all mutate scanner-maintained collections (hash
  indices, tag counts, exclusion lists, or cached metadata) so route handlers
  can stay thin while cache consistency remains centralized in the utility
  module.
* `ws_manager.broadcast_auto_organize_progress()` stores the latest progress
  snapshot consumed by `get_auto_organize_progress`, while
  `ws_manager.broadcast()` is used to notify clients during CivitAI bulk
  refreshes and other background operations.

Keeping these side effects in mind is essential when refactoring route logic:
any replacement must continue to honor the implicit contracts the utilities
expect from scanners, caches, and the WebSocket manager.

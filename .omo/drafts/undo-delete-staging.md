---
slug: undo-delete-staging
status: drafting
intent: clear
review_required: false
pending-action: write .omo/plans/undo-delete-staging.md
approach: "Option B: delayed physical deletion with Undo. Backend: same-volume rename to per-root staging dir (.lm-pending-delete/) [updated 2026-08: model staging moved to a SIBLING dir inside each deleted model's own folder — see 'Symlink fix (2026-08)' under Decisions] + manifest JSON (batch_id, expires_at, staged->original map) + purge (30s TTL timer + startup sweep + opportunistic) + undo-delete endpoint + settings toggle 'skip undo'. Small files (recipes: JSON+preview) copy to global staging under settings dir instead of rename. Frontend: extend toast system with action button + 30s countdown; delete flows (single model / recipe / bulk / duplicates) consume batch_id from delete response and show Undo toast; expired undo -> 'undo expired' toast. Plus confirm-modal friction (C-friction, NO type-to-confirm): delete button delay-activation 1.5s + modal shows file size 'will free X GB' + Cancel gets initial focus. i18n keys + sync_translation_keys.py."
---

# Draft: undo-delete-staging

## Components (topology ledger)
<!-- Lock the SHAPE before depth. One row per top-level component that can succeed or fail independently. -->
<!-- id | outcome (one line) | status: active|deferred | evidence path -->
- backend staging module (stage/purge/undo + manifest + per-volume dir resolution) | new module, active | pending exploration: model_lifecycle_service.py delete_model / delete_model_artifacts
- delete endpoints return batch_id (model/recipe/bulk/duplicates) | active | pending exploration: handlers + response shapes
- undo-delete HTTP endpoint + route registration | active | pending exploration: route registrar pattern
- purge scheduling (30s timer + startup sweep + opportunistic) | active | pending exploration: app on_startup hooks
- settings toggle "skip undo window" | active | pending exploration: settings service read pattern
- frontend toast extension (action button + countdown) | active | pending exploration: showToast impl
- frontend delete flows consume batch_id + Undo toast | active | pending exploration: call sites
- confirm-modal friction (delay-activate + size display + cancel focus) | active | pending exploration: modal focus behavior
- i18n keys + sync_translation_keys.py | active | known

## Open assumptions (announced defaults)
<!-- Record any default you adopt instead of asking, so the user can veto it at the gate. -->
<!-- assumption | adopted default | rationale | reversible? -->
- Undo window TTL = 30s | 30s balances space-freeing intent vs accident recovery | yes (constant)
- Staging dir name: `.lm-pending-delete/` under each model root; recipes: `{settings_dir}/.lm-pending-delete/` | hidden, same-volume [updated 2026-08: same-volume is now guaranteed by sibling staging inside the model's own folder, not by the root location], consistent | yes
- Staging failure falls back to existing hard delete | user intent is delete; staging is best-effort; hard delete likely fails identically under same conditions | yes
- Purge on startup uses expires_at (not purge-all) so a <30s restart with live tab can still undo | robust, matches client-side timer | yes
- Settings toggle label: "Delete permanently immediately (skip undo window)" | power users freeing space | yes
- C-friction: delete button enabled after 1.5s + modal shows freed size; NO type-to-confirm (user vetoed) | user explicitly rejected type-to-confirm | n/a
- Bulk/duplicates delete: one batch id for whole action, one undo restores all | simplest consistent semantics | yes

## Findings (cited - path:lines)

### Backend
- `delete_model_artifacts` (py/services/model_lifecycle_service.py:19-48) = physical delete via os.remove; patterns: main file + `{name}.metadata.json` + PREVIEW_EXTENSIONS (py/utils/constants.py:22-37). ALSO called by ModelScanner.bulk_delete_models (py/services/model_scanner.py:2221) - single swap point covers bulk models.
- `ModelLifecycleService.delete_model` (model_lifecycle_service.py:101-154): fetches `cached_entry` (111-116) - SNAPSHOT available for cache restore; after delete: cache.raw_data removal + resort + bump_cache_version (136-143), `_hash_index.remove_by_path` (145-146), `_sync_update_for_model` (148; update-service only, no recipe JSON rewrites - recipe refs are hash-based, re-resolve on restore), `_persist_current_cache` (150-152), returns `{"success": True, "deleted_files": [...]}` (154).
- Handler `delete_model` (py/routes/handlers/model_handlers.py:478-492): POST /api/lm/{prefix}/delete; response passthrough; `_broadcast_models_changed()` (57-74) after success; 400 `{"success":false,"error"}`; 500 plain text.
- Recipe delete: handler (recipe_handlers.py:1422-1438) DELETE /api/lm/recipe/{recipe_id} -> persistence_service.delete_recipe (py/services/recipes/persistence_service.py:193-209): os.remove(recipe_json_path) + os.remove(image_path) (204-206), recipe_scanner.remove_recipe (208), returns `{"success": true, "message": ...}`. PersistenceResult dataclass (20-25).
- Bulk models: POST /api/lm/{prefix}/bulk-delete (model_route_registrar.py:39) -> handler (model_handlers.py:974-994) -> lifecycle_service.bulk_delete_models (model_lifecycle_service.py:308-318) -> scanner.bulk_delete_models (model_scanner.py:2181-2269) which calls delete_model_artifacts per file (2221) + `_batch_update_cache_for_deleted_models` (2271-2335); response `{"success","status","total_deleted","total_attempted","cache_updated","results"}` (2254-2269).
- Bulk recipes: POST /api/lm/recipes/bulk-delete (recipe_route_registrar.py:50) -> handler (recipe_handlers.py:1554-1573) -> persistence_service.bulk_delete (persistence_service.py:439-482): per-id os.remove x2 (464-466), recipe_scanner.bulk_remove (472); response `{"success","deleted","failed","total_deleted","total_failed"}` (474-482).
- Duplicates: NO dedicated delete endpoints (find-only: GET /api/lm/{prefix}/find-duplicates model_route_registrar.py:59, GET /api/lm/recipes/find-duplicates recipe_route_registrar.py:49). Duplicate deletion reuses bulk-delete endpoints.
- Startup hooks: lora_manager.py:183-187 `app.on_startup.append(lambda app: cls._initialize_services())` (ComfyUI mode, app = PromptServer.instance.app at :78); standalone.py:370-374 same (StandaloneLoraManager.add_routes). Background tasks: `asyncio.create_task(name=...)` (lora_manager.py:224-239; recipe_handlers.py:793). Singleton+asyncio.Lock pattern: model_scanner.py:40-63.
- Settings: DEFAULT_SETTINGS (py/services/settings_manager.py:57-119), `get(key, default)` (1390-1392), get_settings_manager() (2215-2228), reset_settings_manager() (2231). Typed-bool getter example: get_skip_previously_downloaded_model_versions (1253-1262). Handlers: base_model_routes.py:70, base_recipe_routes.py:54.
- Model roots: ModelScanner.get_model_roots base NotImplementedError (model_scanner.py:1073-1075); impls lora_scanner.py:31-45, checkpoint_scanner.py:428-441, embedding_scanner.py:24-36. `_find_root_for_file(file_path)` (model_scanner.py:1108-1124) returns containing root - for per-root staging dir computation [updated 2026-08: staging no longer uses the containing root; batches are siblings inside the model's own folder]. Business-path rule (AGENTS.md): use os.path.abspath, never realpath, for staging/undo routing.
- Cache restore methods: ModelCache has raw_data + resort (conftest mocks: tests/conftest.py:144-154); ModelHashIndex.add_entry(sha256, file_path, autov3) (py/services/model_hash_index.py:16); RecipeScanner.add_recipe(recipe_data) (recipe_scanner.py:2136) -> recipe_cache.add_recipe (recipe_cache.py:64). No single-file incremental model rescan - use snapshot restore instead of rescan.
- Route registrar: model_route_registrar.py:177 add_route(method, path, handler), :180 add_prefixed_route - undo endpoint can be a non-prefixed route via add_route.
- Tests: tests/services/test_model_lifecycle_service.py (inline tmp_path files, per-test stub scanners ScannerForDelete/VersionAwareScanner etc); conftest MockScanner/MockCache/MockHashIndex (tests/conftest.py:134-212); integration fixtures tests/integration/conftest.py; lifecycle hook tests tests/routes/test_lora_manager_lifecycle.py:177-178, tests/standalone/test_standalone_server.py:83-84.

### Frontend
- 5 delete call sites:
  a) Single model: static/js/utils/modalUtils.js confirmDelete (27-42) -> getModelApiClient().deleteModel(path); ignores return.
  b) Recipe single: static/js/components/RecipeCard.js confirmDeleteRecipe (405-449) - RAW fetch DELETE /api/lm/recipe/{id}, checks only response.ok, showToast toast.recipes.deletedSuccessfully, state.virtualScroller.removeItemByFilePath.
  c) Bulk: static/js/managers/BulkManager.js confirmBulkDelete (633-672) -> getActiveApiClient() (134-142) -> bulkDeleteModels(filePaths); reads result.cancelled/success/deleted_count/error.
  d) Recipe duplicates: static/js/components/DuplicatesManager.js confirmDeleteDuplicates (457-494) - RAW fetch POST /api/lm/recipes/bulk-delete, reads data.success/data.total_deleted, exitDuplicateMode().
  e) Model duplicates: static/js/components/ModelDuplicatesManager.js confirmDeleteDuplicates (710-776) - RAW fetch POST /api/lm/{type}/bulk-delete, reads data.total_deleted, then resetAndReload(true) + find-duplicates re-check.
  Bonus: static/js/components/shared/ModelVersionsTab.js:1136-1144 client.deleteModel (ignores return).
- API clients: BaseModelApiClient.deleteModel (static/js/api/baseModelApi.js:184-216) returns true/false, shows its own toasts, does removeItemByFilePath inside; bulkDeleteModels (1591-1642) returns {success, deleted_count, failed_count, errors} or {success:false, cancelled:true}; RecipeSidebarApiClient.bulkDeleteModels (recipeApi.js:623-664) returns {success, deleted_count: total_deleted, ...}. Endpoint map apiConfig.js:56,64.
- Toast: showToast(key, params={}, type='info', fallback=null) (static/js/utils/uiHelpers.js:136-193) - textContent only, NO action/button support; durations 2000/5000ms; CSS static/css/components/toast.css (.toast flex gap:12px - button can be added). Closest action pattern: bannerService.registerBanner actions array + onRegister (static/js/managers/BannerService.js; used uiHelpers.js:18-57).
- i18n: locales/en.json delete keys (1303-1314 bulkDelete, 1945-1948 recipes, 1987-1991 models, 2124-2130 duplicates, 2166-2170 toast.api); t()/interpolate (static/js/i18n/index.js:193-248); translate wrapper (utils/i18nHelpers.js:13-23); sync script scripts/sync_translation_keys.py (en reference, [TODO: Translate] placeholders).
- Refresh after undo: recipes -> window.recipeManager.loadRecipes(true) (recipes.js:359; used by FilterManager.js:752 etc) or refreshRecipes (recipeApi.js:308); models -> resetAndReload(true) from modelApiFactory (used by ModelDuplicatesManager.js:740).
- Size for modal: card.dataset.file_size (ModelCard.js:467), formatFileSize (ModelModal.js:615).
- Tests: tests/frontend/utils/uiHelpers.dom.test.js (toast), api/recipeApi.bulk.test.js, components/duplicatesManager.test.js, components/modelDuplicatesManager.test.js, pages/*Page.test.js, i18n tests tests/i18n/test_i18n.py.

## Decisions (with rationale)

1. Same-volume rename staging for model files (atomic, no copy cost for multi-GB files); cross-volume rename forbidden. [CORRECTED 2026-08: "same-volume because under the containing root" was only true for plain directories — nested symlinked subdirs could cross volumes. Superseded by sibling staging: `.lm-pending-delete/<batch_id>/` inside the deleted model's own folder makes stage/undo same-device by construction; see "Symlink fix (2026-08)" below.]
2. Copy-to-global-staging for recipes (small files; avoids recipe JSON vs preview image cross-volume problem).
3. Manifest JSON files are the only state - no DB changes. Manifest includes model cached_entry snapshot for exact cache restore (no rescan needed).
4. Undo endpoint returns restored paths; expired batch -> 404-style error -> frontend 'undo expired' toast.
5. Skip-undo setting honored server-side (no batch_id in response -> no undo toast client-side).
6. Staging failure falls back to existing hard delete (best-effort undo, never blocks delete).
7. Undo window TTL = 30s constant (PENDING_DELETE_TTL_SECONDS); startup sweep uses expires_at (survives restart; browser-tab timer survives).
8. Purge triple-trigger: per-batch asyncio timer task + on_startup sweep + opportunistic purge at each stage/undo.
9. Frontend: new showActionToast (keep showToast signature untouched; extract shared createToastElement/appendToast internals); undo click -> shared handleUndoDelete(batchId, refreshFn); full list refresh after undo (recipes: window.recipeManager.loadRecipes(true); models: resetAndReload(true)).
10. C-friction wave (NO type-to-confirm - user vetoed): delete buttons delay-activate 1.5s after modal open, initial focus on Cancel, model delete modal gains "permanently deleted from disk" warning + file size display (card.dataset.file_size + formatFileSize).
11. Model cache restore on undo: append snapshot to cache.raw_data (dedupe by file_path) + resort + bump_cache_version + _persist_current_cache + _hash_index.add_entry + _broadcast_models_changed. Recipe restore: copy back files + recipe_scanner.add_recipe(recipe_data loaded from restored JSON).

### Symlink fix (2026-08)

Post-execution addendum (plan `.omo/plans/undo-delete-symlink-fix.md`, commits 5fd4946b / 0c00ee22):

12. Model staging moved from `<model_root>/.lm-pending-delete/<batch_id>/` to `<model_dir>/.lm-pending-delete/<batch_id>/` (sibling of the model artifacts, inside the deleted model's own folder). Stage/undo renames are same-device BY CONSTRUCTION — EXDEV is impossible even when the business path traverses nested symlinks to other volumes (the decision-1 "containing root" guarantee covered only plain directories). EXDEV remains possible only for cross-volume merges, which keep the batch_ids-array fallback. Accepted edge: deleting the model's whole FOLDER during the 30s window destroys that batch (undo returns 404). Batch discovery uses an in-memory registry (`_known_batch_dirs`) with a startup reconciliation scan (`purge_expired(scan_roots=True)`) covering restarts and crash leftovers. Recipe batches unchanged (copy-based settings-dir staging with the `_restore_file` EXDEV fallback).

## Scope IN

- Model single delete (model_handlers delete_model / model_lifecycle_service)
- Recipe delete (recipe_handlers delete_recipe / persistence_service)
- Bulk delete (models scanner + recipes persistence) + duplicates (reuse bulk endpoints)
- Undo endpoint POST /api/lm/undo-delete (models + recipes, one batch space)
- Purge: timer + startup sweep + opportunistic
- Settings toggle delete_undo_enabled + settings page checkbox
- Frontend: showActionToast + all 5 delete flows + shared undo handler
- C-friction modal changes (delay-activate + cancel focus + warning copy + size display)
- i18n keys + sync_translation_keys.py
- Backend + frontend tests

## Scope OUT (Must NOT have)

- NO type-to-confirm / hold-to-confirm friction (user vetoed)
- NO OS trash integration (send2trash) in this iteration
- NO persistent recycle-bin UI (no trash browsing page)
- NO changes to exclude/unexclude flow
- NO DB migrations
- NO new dependencies (no send2trash)
- NO changes to download flows
- NO recipe-JSON rewriting on model undo (hash-based refs re-resolve themselves)

## Open questions

None - all implementation details resolved by exploration. Design decisions settled in conversation (B+C, no type-to-confirm).

## Approval gate
status: approved
<!-- Approach approved -> rerun scaffold without --draft-only, run Metis gap analysis, APPEND todo batches, fill TL;DR last, run structural self-check, then Phase 4 handoff. -->

## Review round state (ulw-plan-review-round-state-contract)
```json
{
  "transition": "replace",
  "phase": "review_round_initialized",
  "applies_when": ["retry_after_plan_change"],
  "atomic": true,
  "review_required": true,
  "plan_path": ".omo/plans/undo-delete-staging.md",
  "plan_sha256": "8cf7c9be38a76d8ef1fb832aba043d6d7e82b60465b1bf28c6eafa7045117adc",
  "review_round_id": "rr-undo-del-20260811-006",
  "round_status": "active",
  "pending-action": "review .omo/plans/undo-delete-staging.md",
  "review": {
    "momus": { "status": "pending", "workspace_root": "/mnt/data/reinstall-backup-2026-04-12/data/workspace/ComfyUI/custom_nodes/ComfyUI-Lora-Manager", "runtime_home": null, "target": ".omo/plans/undo-delete-staging.md", "round_id": "rr-undo-del-20260811-006", "plan_sha256": "8cf7c9be38a76d8ef1fb832aba043d6d7e82b60465b1bf28c6eafa7045117adc", "launch_id": null, "session": null, "result": null },
    "independent": { "status": "pending", "workspace_root": "/mnt/data/reinstall-backup-2026-04-12/data/workspace/ComfyUI/custom_nodes/ComfyUI-Lora-Manager", "runtime_home": null, "target": ".omo/plans/undo-delete-staging.md", "round_id": "rr-undo-del-20260811-006", "plan_sha256": "8cf7c9be38a76d8ef1fb832aba043d6d7e82b60465b1bf28c6eafa7045117adc", "launch_id": null, "session": null, "result": null }
  }
}
```

## Review results + fix/retry ledger

### Round 1 (rr-undo-del-20260811-001, plan sha256 6c52bf99...)
- momus: APPROVE (non-blocking notes: todo1+7 duplicate DEFAULT_SETTINGS key -> fixed todo 7 to verify-only; "batch_ids" plural in todos 8/9 acceptance -> fixed; purge OSError note -> folded into todo 1 purge semantics)
- independent (oracle): CHANGES_REQUESTED
  - BLOCKING S1: scanner walks would index .lm-pending-delete staged files as ghost entries -> fixed: todo 1 now mandates scanner walk exclusion at model_scanner.py:706/:867/:1404/_process_model_file + acceptance (o) scanner-visibility test
  - BLOCKING S2: manifest lacks model_type, undo could restore into wrong cache/hash index -> fixed: manifest now carries model_type + todo 5 resolves per-type scanner via registrar pattern + acceptance (b) checkpoint-batch test
  - S3 merged-batch expires_at re-anchor -> fixed: merge_batches re-anchors now+TTL in todo 1 + todo 3/4 assertions
  - S4 manifest-less dir policy -> fixed: quarantine to <batch_id>.orphaned, never delete (todo 1 + acceptance g)
  - S5 partial-undo retry semantics -> fixed: per-entry restored flag write-through + retry test (acceptance e)
  - S6 purge locked-file failure semantics -> fixed: skip file, keep batch, never rmtree past errors (todo 1 + acceptance i)
  - T8 undo-after-restart test -> fixed: todo 5 acceptance (f)
  - T9 recipe undo -> re-delete test -> fixed: todo 5 acceptance (h)
  - T7 rescan-stale-entry test -> fixed: todo 5 acceptance (g)
  - Route registration pinned to shared routes class per mode (NOT per-model-type registrar which registers 3x) -> fixed: todo 5 now creates py/routes/pending_delete_routes.py registered once in lora_manager.py:170-172 + standalone.py:356-358 + duplicate-route test (e)
  - Version-index staleness on single-delete undo -> fixed: todo 5 follows bulk cache-update pattern incl. rebuild_version_index (model_scanner.py:2324)
  - Cancelled-bulk batch_id frontend handling -> fixed: todo 9 shows action toast on cancelled+staged-subset
  - Single-instance assumption -> added to Scope OUT
  - Occupied-refusal loss UX -> accepted-intent documented in success criteria + modal copy

### Round 2 (rr-undo-del-20260811-002, plan sha256 f3d52235...)
- momus: APPROVE (all 12 round-1 fixes verified present; zero dead references; non-blocking nits only)
- independent (oracle): CHANGES_REQUESTED
  - BLOCK-1: merge_batches file-movement semantics unspecified (silent data-loss vector) -> fixed: todo 1 now specifies move-into-winner-dir + entry re-point + loser-dirs-removed-only-when-empty + abort-on-move-failure (all batches intact) + merge inside service lock + acceptance (k) file-survival assertions + acceptance (l) merge-failure abort test
  - BLOCK-2: same-file parallel edits within waves (todo 5 vs 6 on lora_manager.py; todo 8 vs 9 on baseModelApi.js) -> fixed: waves/matrix now serialize 5->6 and 8->9 with explicit reasons; matrix updated
  - Recommended: checkpoint_scanner.py:331 exclusion -> fixed (todo 1 + acceptance p); S5 pre-check skips restored:true entries -> fixed (todo 1); _tags_count restore on undo -> fixed (todo 5 + acceptance j); undo-blind flows documented (ModelVersionsTab + misc_handlers:2456) -> fixed (todo 8 note + Scope OUT); merge-failure no-merge fallback contract (batch_ids array) -> fixed (todos 3/4/9)

### Round 3 (rr-undo-del-20260811-003, plan sha256 8f2dfd46...)
- momus: APPROVE (all round-2 fixes verified present + spot-checked refs; no new contradictions)
- independent (oracle): CHANGES_REQUESTED
  - BLOCKING A: merged batches never timer-purged after re-anchor (winner's original timer no-ops at old expiry; no fresh timer for re-anchored expiry; idle server -> merged batch lingers, violating "30s purge" success criterion; affects EVERY bulk delete) -> fixed: todo 1 merge_batches now ARMS A FRESH PURGE TIMER for the winner with re-anchored expiry + acceptance (q) fresh-timer test + purge_expired must enumerate ALL scanner types' roots (explicit in todo 1)
  - BLOCKING B: dependency matrix contradicted same-file policy for todos 8/9<->11 (5 shared files) and 12<->11 -> fixed: todo 11 now "Blocked by: 8, 9 (same files...)"; todo 12 blocked by 11 (sync after 11); wave text updated (11, then 12 AFTER 11); "Can parallelize with" columns corrected
  - BLOCKING C: frontend batch_ids sequential-undo fallback has NO test + merge->undo loser-restore + merge->purge assertions missing -> fixed: todo 9 acceptance now tests the batch_ids fallback path; todo 1 acceptance now has (k2)/(k3)
  - Notes folded: sub-second toast-tail expiry race accepted; EXDEV fallback = NORMAL path for cross-volume bulks [annotated 2026-08: after the sibling-staging fix, EXDEV can only arise during cross-volume MERGES, never during single stage/undo renames]

### Round 4 (rr-undo-del-20260811-004, plan sha256 179e7ff7...)
- momus: APPROVE (round-3 fixes verified; one non-blocking nit: todo 11 inline "Blocked by: —" stale -> fixed to "8, 9")
- independent (oracle): CHANGES_REQUESTED
  - BLOCKING GAP-1 (NEW, introduced by round-3 fix): todo 8 handleUndoDelete always-refresh/always-toast contract contradicted todo 9's sequential loop "exactly ONE final refresh" -> fixed: handleUndoDelete(batchId, refreshFn, {showToast, refresh}) suppression options; todo 9 loop uses suppressed calls + one final refresh/toast; acceptance extended (loop failure mid-way -> stop + error toast + no final refresh; 404 body discrimination expired vs occupied)
  - BLOCKING GAP-2: no cross-type purge enumeration test -> fixed: todo 1 acceptance (r) purges expired batches across lora root + checkpoint root + recipe staging dir in one call
  - Non-blocking folded: GAP-3 404-copy discrimination -> fixed in todo 8 (d); GAP-4 merge partial-failure rollback direction (move back + restore manifests, extended (l) asserts sequential constituent undo still restores everything) -> fixed in todo 1; GAP-5 post-restart timer-loss residual gap documented -> fixed in todo 6; GAP-6 usage_stats.py:424 walk added to exclusion mandate + todo 5 acceptance (k) embeddings undo test

### Round 5 (rr-undo-del-20260811-005, plan sha256 dfaa39ea...)
- momus: APPROVE (all round-4 fixes verified; no new contradictions)
- independent (oracle): CHANGES_REQUESTED
  - BLOCK-1: lock-ordering deadlock ambiguity (asyncio.Lock not re-entrant: opportunistic purge_expired called while stage/undo hold the lock would deadlock on first use) -> fixed: todo 1 now has explicit LOCK HIERARCHY (lock acquired ONLY by stage/merge/undo/purge_batch; purge_expired is lock-free and must be called BEFORE lock acquisition); todo 6 (c) updated with the same rule + acceptance (u) lock-no-deadlock test
  - BLOCK-2: purge edge semantics unspecified -> fixed: purge_batch treats missing staged files (partially-restored batches) as already-purged (FileNotFoundError silent no-op); sweep skips `.orphaned`-suffixed dirs (quarantine is terminal); acceptance (s) partially-restored purge + (t) quarantine-terminal tests
  - Non-blocking folded: todo 2/3 test-file collision -> todo 3's bulk tests moved to tests/services/test_model_scanner.py; todo 9 (d) DuplicatesManager refreshFn stated explicitly (recipes loadRecipes / models resetAndReload); modal-copy + bulk-count trade-offs acknowledged in success criteria; acceptance (r) extended with embeddings root

### Round 6 (rr-undo-del-20260811-006, plan sha256 8cf7c9be...)
- momus: APPROVE (all round-5 fixes verified; no new contradictions; references verified)
- independent (oracle): APPROVE — no blocking issues; all round-5 items fixed with working, tested solutions; no new race/data-loss/consistency defects
- Deferred optional improvements (non-blocking, recorded for executor awareness; plan file left untouched to preserve the approved digest):
  1. Tag-count asymmetry: single delete_model never decrements _tags_count (lifecycle 101-154), bulk does (scanner 2297-2303); undo re-increment is exact for bulk, over-counts for single until rescan (cosmetic, self-healing). Optional fix riding in todo 2: decrement tags in the single-delete path to mirror bulk.
  2. Todo 5 factual nit: ModelCache.resort() already rebuilds the version index — explicit rebuild in undo is belt-and-braces, no action needed.
  3. Todo 8 premise nit: ModelVersionsTab call ignores deleteModel's return entirely — nothing breaks, no adaptation needed.
  4. Todo 3's pytest command includes test_model_lifecycle_service.py which todo 2 edits in the same wave — run that file's tests after todo 2 lands.
  5. merge_batches with a missing/quarantined constituent id: any sane fallback (abort -> batch_ids, or skip missing) acceptable — files stay staged either way.

## Review lifecycle
- rounds: 6 (rr-undo-del-20260811-001..006); final round both lanes APPROVE
- final live-plan validation: sha256 = 8cf7c9be38a76d8ef1fb832aba043d6d7e82b60465b1bf28c6eafa7045117adc — MATCHES approved round-6 digest
- status: APPROVED — ready for execution handoff ($start-work undo-delete-staging)

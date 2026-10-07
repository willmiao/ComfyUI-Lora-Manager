# Plan: Scoped Scan (one root / one folder at a time)

**Issue:** [#1108](https://github.com/willmiao/ComfyUI-Lora-Manager/issues/1108) — scan a single
folder/root instead of the whole library.
**Status:** **P1, P2 and Wave 6 implemented** (2026-10-07). P1 shipped in `470d85cc` (translations
in `bd184559`), P2 in `12930ce7` (translations in `0941f992`). Supersedes the earlier draft's
per-root *status panel* and persisted *unreachable-subtree* state (both dropped, see
"Must NOT have").

Implementation notes / deviations from the draft below:

* The scope dataclass is public (`ReconcileScope`) because it crosses the scanner → service →
  route boundary; the draft called it `_ReconcileScope`.
* `_reconcile_cache()` now returns a summary dict, exposed as
  `ModelScanner.last_reconcile_summary` and returned by `BaseModelService.scan_models()`, so the
  scan HTTP response carries the counts (the WS `completed` payload carries the same fields).
* Root labels are computed over the **whole configured set** and passed into the walk tracker, so
  the progress line and the menu never disagree.
* Discovery: `Config._dedupe_existing_paths()` drops roots that do not exist **at config load**, so
  a drive that is already off when LM starts is not in `get_model_roots()` at all. Two consequences:
  it cannot appear in the refresh menu (nothing to select), and its cached entries are kept because
  they are outside every configured root prefix. The `root_unreachable` path therefore covers the
  *mid-session* case (drive switched off while LM runs), which is the workflow that motivated the
  issue; both paths keep the entries, which is what matters.
* Known limitation to keep in mind: after a scoped scan (or one with unreadable paths) the recorded
  empty-folder list is unioned instead of replaced, so an empty folder deleted on disk can linger in
  the sidebar until the next full refresh. Models are unaffected.

## TL;DR (For humans)

**What you'll get:** the Refresh ▾ menu can scan **one model root** (one drive) and leave every
other root untouched. Refreshing while a drive is switched off no longer deletes that drive's
models from the cache/DB — they are kept and reported. Browsing the grid while a drive is off no
longer silently strips `preview_url` from that drive's models.

**Why this approach:** a scan scope is a **path scope**, not a device scope, so it also works for
layouts where one root contains symlinks to other drives. The safety net collapses into one rule —
*anything this walk could not read is left untouched* — and that rule is nearly free: the root
existence check already exists, `os.walk(onerror=...)` only fires on failure, and the cached-entry
prefix attribution is already computed for the walk-progress weights.

**What it will NOT do:** no active probing of nested symlinks; no persisted "unreachable subtree"
table; no per-card offline badges (separate change); no root enable/disable switch; the main
Refresh button keeps meaning "scan everything"; no configuration-convention/documentation push to
re-layout libraries that use cross-drive symlinks (dropped by request).

**Effort:** Medium (~1.5–2 days for P1 including tests)
**Risk:** Medium-low — the risk sits in the folder-tree (`all_folders`) merge under a scoped scan
and in the exact pruning predicate; both get explicit tests.

**Decisions to sanity-check:**
1. A full Refresh now treats a *configured but unreachable* root as "keep + report" instead of
   "everything under it was deleted". This is a behaviour change (release-note it).
2. Keep the near-zero-cost **first-level symlink** reachability check (reuses
   `config._path_mappings`); nested symlinks stay uncovered.
3. Root labels become set-aware (`G: loras` / `usb/loras`, auto-deduped by parent segments).
   This also changes the walk-progress line.

## Scope

### Must have (P1)

- **Scope-aware reconcile**: `_reconcile_cache(scope=...)` where scope is
  `{roots: [path] | None, folder: rel | None}`. Files inside the scope reconcile normally
  (add / repair / remove); everything outside is neither re-read nor removed.
- **Path-level pruning guard**: cached entries under a path this walk could not read are excluded
  from `missing` and reported. Three sources:
  - configured root that fails the reachability check (already filtered at
    `model_scanner.py:1468`),
  - directories `os.walk` failed to enter (`onerror` collector; covers Windows junctions to an
    offline drive, permission errors, I/O errors),
  - first-level symlink mappings whose target is not a directory (`config._path_mappings`).
- **Folder tree correctness under scope**: `all_folders` becomes
  `(old outside scope) ∪ (old under unreachable paths) ∪ (discovered)`, so a scoped scan cannot
  collapse the sidebar tree and an offline root keeps its folders.
- **Result payload** for the toast: `added`, `removed`, `repaired`, `scanned_roots` (labels),
  `skipped_roots` (`{path, label, kept}`), `unavailable_paths` (`{path, kept}`, capped),
  `kept_unreachable`.
- **API**: `GET /api/lm/{prefix}/scan?full_rebuild=false&roots=<path>` (repeatable);
  `GET /api/lm/{prefix}/roots` gains `root_details: [{path, label, reachable, models}]` while
  keeping `roots: [str]` unchanged (other callers depend on it).
- **Frontend**: Refresh ▾ menu lists the current page's roots (label + model count, offline rows
  greyed out and non-clickable), main button unchanged, root items disabled while a scan runs;
  scoped completion toast reports counts and any kept/skipped paths.
- **Preview fix**: a preview 404 must not clear `preview_url` when the file's parent directory is
  itself unreachable (`preview_handlers.py:57` + `_cleanup_stale_preview_url`).
- **Set-aware root labels** (`_root_display_labels(roots)`), shared by the progress broadcasts and
  `/roots`: last path segment, Windows drive prefix (`G: loras`), deduped by prepending real parent
  segments (`usb/loras`, `a/models/loras`), `(2)` fallback by sorted path, 40-char cap, full path in
  the tooltip.
- i18n keys in `locales/en.json` + `python scripts/sync_translation_keys.py`.
- pytest + vitest coverage for every item above.

### Must have (P2, implemented)

- `folder=<rel>` parameter: walk `<root>/<rel>` for every reachable root that contains it (the
  sidebar's unified tree has no root identity, so "this folder" means "this relative path in all
  roots"), prune only inside that prefix. Validation reuses `normalize_relative_folder()` (extracted
  from `ModelMoveService` so the folder operations and the scan endpoint reject the same input:
  absolute paths, drive letters, `..` climbing). The summary carries `scope_label` = the folder, so
  the toast names the folder the user clicked rather than the roots it happens to live under.
- Sidebar folder context menu entry "Scan this folder" (`templates/components/context_menu.html`
  `#sidebarFolderContextMenu`, above `check-folder-updates`; update
  `tests/frontend/regression/sidebarFolderContextMenu.test.js` expectations). The entry is gated
  like the other folder operations and resolves the folder through the existing
  `_resolveFolderCandidates()` before scanning, so a folder no root holds any more explains itself
  instead of scanning nothing. It shares `check-folder-updates`'s divider (both are refresh-ish).

### Must NOT have (guardrails)

- NO per-entry symlink probing during the walk — `DirEntry.is_symlink()` costs a syscall per entry
  on Windows, the exact cost the reconcile optimisation removed. Nested symlinks stay uncovered.
- NO persisted `unavailable_paths` table, no DB schema change, no new cache state.
- NO configuration-convention guidance for cross-drive symlinks (dropped by request).
- NO per-card/modal offline badges in this plan (separate change; needs the L1 prefix list which
  P1 produces, so it can build on this later).
- NO root enable/disable setting, NO status panel in Settings.
- NO change to `full_rebuild=true` (it still walks everything and replaces the cache);
  `roots` + `full_rebuild=true` is rejected with 400.
- NO new dependency, NO change to the extension-facing endpoints.
- NO `os.path.realpath` for scope/prune routing — business paths only (AGENTS.md rule).

## Todos

### Wave 1 — backend semantics and safety net

1. **Scope plumbing in the scanner.**
   What to do: add `_ReconcileScope` (dataclass: `roots: Optional[List[str]]`, `folder: Optional[str]`)
   and `_reconcile_cache(scope=None)`. Resolve the effective root list once: configured roots ∩
   scope.roots, filtered by reachability; missing ones become `skipped_roots` (never pruned).
   `_walk_roots_for_reconcile` / `_walk_root_group_sync` / `_walk_root_for_reconcile` take the scope
   so the walk can start at `<root>/<folder>` while still computing `folder`/`file_path` relative to
   the **root** (`_process_model_file(path, root_path)` must keep receiving the root).
   References: `py/services/model_scanner.py:1453` (`_reconcile_cache`), `:1468` (root filter),
   `:1832` (`_walk_root_group_sync`), `:365` (`_walk_root_for_reconcile`), `:134`
   (`_count_cached_entries_per_root`), `:126` (`_normalized_root_prefix`).
   Done when: a scoped reconcile over 2 roots leaves the other root's `raw_data`, hash index and
   folder list byte-identical.

2. **Pruning predicate + unreachable collection.**
   What to do: `missing = {p for p in cached_paths - found_paths if in_scope(p) and not
   under_unreachable(p)}`; collect unreachable prefixes from (a) skipped roots, (b) an `onerror`
   callback on `os.walk` (record `oserror.filename` as a business path), (c) `config._path_mappings`
   entries whose target fails `os.path.isdir` (mapping is keyed target→link; protect the **link**
   prefix). Count the kept entries per prefix for reporting.
   References: `py/services/model_scanner.py:1679` (`missing_files = cached_paths - found_paths`),
   `:398` (`os.walk(..., followlinks=True)`), `py/config.py:167` (`_path_mappings`),
   `:801` (`add_path_mapping`, target→link), `:750-775` (first-level-only symlink scan).
   Done when: with a root removed from disk (or a directory replaced by an unreadable junction),
   `raw_data` keeps those entries, `removed` is 0, and the counts land in the result payload.

3. **Folder-tree merge under scope.**
   What to do: replace the unconditional `sorted_discovered` assignment with the union rule from
   "Must have"; keep the `folders_changed` comparison and the persist path unchanged. Unscoped
   scans with nothing unreachable must produce exactly today's list.
   References: `py/services/model_scanner.py` (walk loop records `discovered_folders`; `model_scanner.py:1738`
   (`sorted_discovered`) and `:1739` (`folders_changed`) after the dedup pass).
   Done when: a scoped scan keeps folders outside the scope, an offline root keeps its subtree, and
   a full scan still drops folders deleted on disk.

4. **Result payload + progress/cancel/complete messages.**
   What to do: extend the `completed` broadcast with `scanned_roots`, `skipped_roots`,
   `unavailable_paths`, `kept_unreachable`, `repaired`; the walk tracker already receives only the
   scoped roots, so the progress line shows that root's label with `roots_total=1`.
   References: `py/services/model_scanner.py` `_broadcast_scan_progress` (`:576`),
   `_ReconcileWalkTracker` (`:266`), the completed broadcast at the end of `_reconcile_cache`.
   Done when: a scoped scan emits `stage=reconcile_scan` with the single scoped label and a
   `completed` payload carrying the new fields.

5. **API surface.**
   What to do: `scan_models` accepts repeated `roots` query params (400 on unknown root, 400 when
   combined with `full_rebuild=true`); `get_model_roots` adds `root_details` (label, reachable,
   model count via the shared prefix attribution) without touching `roots`.
   References: `py/routes/handlers/model_handlers.py:1139` (`scan_models`), `:1165`
   (`get_model_roots`), `py/routes/model_route_registrar.py:61-62`, `static/js/api/apiConfig.js:114`.
   Done when: `tests/routes/test_lora_routes.py`-style coverage passes for the new params and the
   backward-compatible `/roots` payload.

6. **Preview 404 must not prune when the parent is unreachable.**
   What to do: in `serve_preview`, before `_cleanup_stale_preview_url`, check
   `os.path.isdir(os.path.dirname(resolved))`; if the directory itself is missing/unreachable,
   return 404 **without** clearing caches. (Centralized sidecar mode puts the preview in the mirror
   tree, so the check must use the preview file's own parent.)
   References: `py/routes/handlers/preview_handlers.py:57` (404 branch), `:74-110`
   (`_cleanup_stale_preview_url` → `clear_preview_by_path` + `_persist_current_cache`),
   `tests/routes/test_preview_routes.py`.
   Done when: a test asserts the cache keeps `preview_url` when the parent dir is absent and still
   clears it when the file was really deleted from a reachable directory.

### Wave 2 — labels

7. **`_root_display_labels(roots)` (set-aware, order-independent).**
   What to do: replace the single-root `_root_display_label`; compute over the sorted root list;
   prepend real parent segments until unique; `(2)`/`(3)` fallback; 40-char middle-ellipsis; return
   `{path: label}`. Use it in `_ReconcileWalkTracker.__init__` (progress) and in the `/roots`
   handler so both always agree.
   References: `py/services/model_scanner.py:117` (`_root_display_label`, current single-root
   version), `:266` (`_ReconcileWalkTracker`).
   Done when: unit tests cover `usb/loras` + `ssd/loras`, `a/models/loras` + `b/models/loras`,
   Windows `G:\x\loras` + `H:\y\loras` → `G: loras` / `H: loras`, and the identical-path fallback.

### Wave 3 — frontend

8. **Refresh ▾ scope section.**
   What to do: add an empty container to `templates/components/controls.html` inside
   `.dropdown-menu` (`#refreshScopeMenu`) + a section title; on dropdown open, fetch
   `endpoints.roots`, render one row per root (`data-action="scan-root"`, `data-root="<path>"`,
   label + model count, `disabled` + "Offline" for unreachable), hide the section on the recipes
   page (recipes have no roots); wire clicks by **event delegation** on the menu (the existing
   `full-rebuild` item is bound with a direct `querySelector`, dynamic rows cannot be);
   invalidate the cached list after a scan finishes; add CSS for the section + `max-height`/
   `overflow-y` so 4+ roots stay usable.
   References: `templates/components/controls.html:67-76`, `static/js/components/controls/PageControls.js:131`
   (`data-action="refresh"`), `:220-260` (`initDropdowns` + `full-rebuild` wiring),
   `static/js/api/apiConfig.js:118` (`roots` endpoint), `static/js/api/baseModelApi.js:1318`
   (`fetchModelRoots`).
   Done when: the menu lists roots with counts, an offline root is visibly disabled, and clicking a
   row starts a scoped refresh.

9. **Scoped request + toast.**
   What to do: `refreshModels(fullRebuild, {roots})` appends repeated `roots` params; the
   `completed` payload drives the toast (`added`/`removed`/`kept_unreachable`/`skipped_roots`);
   offline rows toast `… is not reachable right now. Nothing was changed.` without a request.
   References: `static/js/api/baseModelApi.js:514-602` (refreshModels, URL build at `:601`, toast
   at `:618`), `static/js/components/controls/PageControls.js:485`.
   Done when: the frontend test asserts the scoped URL and both toast variants.

10. **i18n.**
    What to do: add `loras.controls.refresh.scopeSection`, `.rootOffline`, `.rootModels`,
    `toast.api.refreshCompleteScoped`, `toast.api.refreshKeptUnreachable`,
    `toast.api.scanRootUnreachable` to `locales/en.json`, run
    `python scripts/sync_translation_keys.py`, then stop (placeholders are the expected state until
    translations are requested).
    Done when: `pytest tests/i18n` passes and every locale has the keys.

### Wave 4 — tests and verification

11. **Backend tests** (`tests/services/test_model_scanner.py`, `tests/routes/test_lora_routes.py`,
    `tests/routes/test_preview_routes.py`):
    `test_reconcile_scoped_scan_leaves_other_roots_untouched`,
    `test_reconcile_scoped_scan_removes_deleted_files_in_scope`,
    `test_reconcile_scoped_scan_preserves_folder_tree_outside_scope`,
    `test_reconcile_keeps_entries_of_unreachable_root`,
    `test_reconcile_keeps_entries_under_unreadable_dir`,
    `test_reconcile_keeps_entries_under_offline_first_level_symlink`,
    `test_root_display_labels_dedupe_by_parent_segments`,
    `test_scan_models_accepts_roots_param`, `test_scan_rejects_unknown_root`,
    `test_scan_rejects_roots_with_full_rebuild`, `test_roots_endpoint_reports_details`,
    `test_preview_404_keeps_cache_when_parent_dir_missing`.

12. **Frontend tests**: extend `tests/frontend/api/baseModelApi.refresh.test.js` (scoped URL, both
    toasts) and add `tests/frontend/components/controls/pageControls.scanRoots.test.js`
    (rows rendered from `/roots`, offline row disabled, delegation wiring).

13. **Full suites + sandbox eyeball**: `pytest -q`, `npx vitest run`, `npm run test:vue`; then a
    sandboxed standalone instance with two roots and a slowed walk
    (`LM_WALK_DELAY_S`-style `sitecustomize` hook) to eyeball the scoped progress line, the offline
    row and the toast — the user verifies by eye.

### Wave 5 — P2 (folder scope) — done

14. `folder=<rel>` in the scan endpoint + `ReconcileScope.folder`, the sidebar menu entry, the
    context-menu regression test update, and the "folder in several roots" semantics (scan every
    reachable root that has the relative path; report per root).
    * `normalize_relative_folder()` extracted to module scope in `model_file_service.py` (the
      private static method now delegates) and reused by the scan handler.
    * `scanFolder()` in `SidebarManager` reuses `_resolveFolderCandidatesSafe()` and delegates to the
      host page controls, which pass `{ folder }` through `registerAPI`'s argument-forwarding
      `refreshModels`.
    * Verified live: `folder=pack000` on the three-root sandbox walks drive-G and drive-Y, reports
      `scope_label=pack000`, keeps drive-Z's 6 entries under that folder (`kept_unreachable=6`) and
      leaves all 420 models cached.

## Wave 6 — configured vs currently available roots (approved follow-up)

The P1/P2 work exposed an asymmetry: `Config._dedupe_existing_paths()` drops roots whose directory
does not exist **at the moment the root list is built** (startup, or applying a library snapshot),
so a drive that is switched off while LM starts is not "an offline root" — it is not a root at all.
Consequences, all verified on the sandbox:

* `/roots` does not list it, so the Refresh ▾ menu shows no row for it in either state;
* a full refresh reports nothing (`kept_unreachable: 0`, no toast) even though its cached entries
  are kept — they survive only because they fall outside every configured root prefix;
* plugging the drive back in does not bring the row back: the in-memory list is not re-validated;
* **plugin mode only:** `Config.save_folder_paths_to_settings()` (called from `Config.__init__`)
  persists `target_folder_paths["loras"] = list(self.loras_roots)` through
  `upsert_library(folder_paths=...)`, which **replaces** the library's paths. Starting ComfyUI with
  a drive switched off therefore *erases that path from `settings.json`* — a configuration loss,
  not just a display gap. Extra paths are unaffected (that call reuses the stored
  `extra_folder_paths`), and the same pattern applies to checkpoints/unet/embeddings/other-model
  primary paths.

### Must have

1. **Never erase an unavailable root from the library config.** `Config` records the *configured*
   (existence-unfiltered) primary paths per model type while building the live lists, and
   `save_folder_paths_to_settings()` persists those instead of the filtered ones.
   `_resolve_valid_default_root()` receives the configured paths in `allowed_paths` too, so a
   `default_*_root` that sits on a switched-off drive is not "repaired" away.
2. **Report configured-but-unavailable roots.** `Config.configured_roots_for(model_type)` feeds
   `ModelScanner.describe_model_roots()`, which appends them with `available: false`, a live
   `reachable` and their cached entry count — so the Refresh ▾ menu has a row in **both** states
   (greyed while the directory is missing, normal and clickable once it is back). The reconcile
   summary reports them as `skipped_roots` / `unavailable_paths` with reason `root_unavailable` and
   counts their cached entries in `kept_unreachable`, which is what makes the "N models kept" toast
   appear in the startup-offline case.
3. **Admit them again, append-only.** `Config.admit_configured_roots()` re-runs the per-type
   prepare helpers against the configured paths and **appends** what exists now
   (plus the checkpoint/unet/other side maps) to the live lists, then refreshes the preview
   allowlist. Called from `/roots` and `/scan`, so a drive plugged in mid-session can be scanned
   without restarting. Appending (never re-sorting) keeps `loras_roots[0]` — which derives the
   recipes directory and the usage-stats file location — stable for the whole session.

### Must NOT have

* NO removal of a root from the live lists mid-session (that is what would let a later settings
  save persist a reduced configuration, and it would move `*_roots[0]`).
* NO change to the scan/prune scope: a root that is still unavailable stays out of scope, so its
  entries remain "kept because out of scope" exactly as today.
* NO persisted unavailable-state, no DB schema change, no per-entry filesystem probe.

### Where "configured" comes from

`Config` records the existence-unfiltered paths while building the live lists, but the *source*
differs per mode and that matters:

* **Plugin mode:** `folder_paths.get_folder_paths()` is ComfyUI's own list, unfiltered — a path the
  user removed there must be forgotten, one that is merely missing must be kept. The host list wins.
* **Standalone mode:** `standalone.MockFolderPaths.get_folder_paths()` already filters
  `os.path.exists` out of `settings.json`, so the host list cannot answer "what did the user
  configure". The active **library snapshot** (`libraries[<active>].folder_paths`, falling back to
  the top-level `folder_paths`) is the record, and it wins there.
  (`_remember_library_configured_paths()` implements the split.)

### Verification

* Config: a configured path that does not exist is still written back by
  `save_folder_paths_to_settings()`; a path the host no longer configures is still dropped.
* Promotion: create the directory after the lists were built → `admit_configured_roots()` adds it
  **at the end**, keeps every existing root in place, and adds nothing twice.
* Scanner: `describe_model_roots()` reports the missing root (`available: false`, cached count);
  a full refresh lists it in `skipped_roots`/`unavailable_paths` and keeps its entries; `/scan`
  with that root works once the directory is back.
* Sandbox, drive-Z gone **before** startup: `/roots` reports `drive-Z` with
  `reachable=false available=false models=60`; a full refresh returns
  `skipped_roots=[drive-Z root_unavailable]`, `unavailable_paths=[{... kept: 60}]`,
  `kept_unreachable=60` and leaves all 432 models cached. *(Both measured; before this wave the
  menu had no row and the refresh reported nothing.)*
* Sandbox, drive renamed back **while the server runs**: `/roots` admits it
  (`available=true reachable=true`) and `GET /scan?roots=<drive-Z>` walks it
  (`scanned_roots=['drive-Z']`, 0 added / 0 removed) — no restart required. *(Measured.)*

## Known limitations (accepted)

- **Nested symlinks** (a symlink *below* a root pointing at another drive) are only covered when
  `os.walk` fails to enter the target (Windows junctions, permission errors). A broken symlink that
  `os.walk` classifies as a non-directory (typical on POSIX) is not detected: its entries are pruned
  as today and come back on the next scan once the target is reachable (sidecars carry the sha256,
  so no re-hash). Verify the Windows junction behaviour before writing release notes.
- Only **first-level** symlinks are known to `config` (by design, `config.py:750-775`), so the
  symlink reachability check inherits that limit.
- A scoped scan of a folder does not re-read metadata for unchanged files (unchanged behaviour).
- Empty folders removed on disk can linger in the sidebar after a scoped scan (the folder list is
  unioned rather than replaced whenever the scan did not verify every root); the next full refresh
  drops them.
- `root_details[].reachable` is a live `os.path.exists()` per root, so a root that disappears
  mid-session shows as offline; a root that was already gone at startup is still listed thanks
  to Wave 6 (`available: false`, cached count), and `/roots` re-admits it once the directory
  is back.

## Verification checklist

- [x] `pytest -q` green (3704 passed, 7 skipped), `npx vitest run` green (1495 passed),
      `npm run test:vue` green (96 passed).
- [x] `python scripts/sync_translation_keys.py --dry-run` reports no pending changes.
- [x] Sandbox: 3 roots, one offline → scoped scan of one root walks only it; a full refresh keeps
      the offline root's models (`kept_unreachable=60`) and the grid still shows all 420.
- [x] Sandbox: folder scope (`folder=pack000`) walks the two reachable roots, labels the scan by the
      folder and keeps the offline root's 6 entries under it.
- [ ] Sandbox: preview of an offline root's model returns 404 and the DB keeps `preview_url`
      (test-locked; not eyeballed in the sandbox because the demo models have no previews).
- [ ] Release note wording agreed for the behaviour change (decision 1).
- [ ] The 2 new sidebar keys (`sidebar.scanFolder`, `sidebar.scanFolderResult.missing`) are
      `[TODO: Translate]` placeholders pending the feature owner's go-ahead.

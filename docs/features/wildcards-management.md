# Wildcard Resource Management and Global Activation

Wildcards are managed as first-class Civitai resources, like model files and
Workflows. The feature has three deliberately separate layers:

1. **Resource management** in the LoRA Manager web UI, in both standalone and
   ComfyUI plugin mode.
2. **Global activation management** shared by the manager and a ComfyUI canvas
   panel.
3. **Wildcard use** through autocomplete and runtime expansion in `PromptLM` and
   `TextLM` (plugin mode only).

Downloading a resource never activates it implicitly. Activation is logical: the
original artifact stays in the library; no copy, hard link, or symlink is placed
in the runtime wildcard directory.

## Design background

A Civitai API sample covered 197 distinct Wildcards resources (100 most
downloaded plus 100 newest, with overlap removed). The latest versions were
predominantly ZIP archives: 158 ZIP, 37 TXT, and 2 YAML. Many resources had
multiple versions, and multi-file packs were common in the inspected archives.
A public-download subset contained 2,006 supported files, 2,131 wildcard keys,
and approximately 148,400 candidate values.

The main consequences for the design are:

- A resource is not equivalent to one trigger word. One version can contain many
  files and keys.
- Civitai `trainedWords` can be a useful hint but is not authoritative: only a
  minority of sampled latest versions supplied it, and parsed file contents are
  the source of truth.
- Filename-only activation aliases are insufficient for YAML/JSON because their
  keys come from nested content rather than the filename.
- Activation needs a resource namespace and, for a single-entry resource, a key
  alias. Full archive paths should remain intact by default.
- Exact key conflicts are real, but blindly flattening paths creates additional
  short-key collisions. Autocomplete should insert the complete effective key.

The first implementation used a custom resource page. It was replaced by the
standard model-resource pipeline so Wildcards retains the same download,
version, card, bulk, sorting, folder, and metadata behavior as other resources.

## Resource library

Enable the feature under **Settings → Library → Wildcard Resource Management**.
`enable_wildcards` defaults to `false`; `wildcard_path` selects the single
LM-owned library root in both operating modes. The setting is intentionally not
part of ComfyUI's `folder_paths`.

While management is disabled, the manager does not scan or download the library.
Existing manual wildcards and resources that were already activated continue to
work at runtime.

Supported artifact formats are ZIP, TXT, YAML, YML, and JSON. The scanner stores
the original artifact and a normal `.metadata.json` sidecar. Civitai downloads
use the shared `DownloadManager`; archives are never extracted by the generic
post-download extractor. Each downloaded Civitai version is independent in the
standard model cache and can coexist with other versions. A newly downloaded
version does not replace the currently activated version implicitly.

Local multipart import is available at `POST /api/lm/wildcards/import` and uses
the configured library root.

### Parsed index

`py/services/wildcard_parser.py` reads artifacts without extracting ZIP files.
It records source files, normalized keys, candidate counts, unsupported files,
and parse errors in `WildcardMetadata`. The index is projected into the scanner
cache entry and persisted with it, so key/value counts survive scans, imports,
and restarts (old cache snapshots are backfilled from the sidecar).

Default key rules are:

- TXT: the relative path without its extension.
- ZIP member TXT: the archive-relative path without its extension, including any
  top-level folder.
- YAML/JSON: nested object keys joined with `/`; the artifact filename is not
  included.

Parsing uses safe YAML loading, UTF-8 text handling, archive member validation,
duplicate-key reporting, and limits for artifact size, archive members, member
size, and expanded text size. Source content and values are read on demand;
inactive resources do not contribute values to the runtime dictionary.

## Activation model

Activation state is stored in `<settings_dir>/wildcard-activations.json`, not in
Civitai metadata or workflow documents. Each record contains the artifact path,
hash, source-entry index, namespace, aliases, an `active` flag, and activation
timestamps. Deactivating marks the record inactive instead of deleting it: the
runtime skips inactive records, and a later reactivation restores the stored
namespace and aliases. This keeps the canvas panel's one-click toggle from
silently discarding a configured namespace or alias.

For every source key, the effective runtime key is:

```text
[namespace/]alias-or-original-key
```

The namespace is optional and applies to the whole resource. A single-entry
resource can also override its key directly. This works uniformly for TXT, YAML,
JSON, and ZIP members because the mapping is applied after parsing rather than
by renaming files.

### Conflicts

Activation performs a preflight against other activated resources and the
manual wildcard directory:

- An exact normalized-key conflict is rejected with HTTP 409. The response
  identifies the key and its owners. Resolve it by changing the namespace/alias
  or deactivating the other resource.
- A collision only between leaf names is allowed but reported as a short-key
  warning. Existing `*/key` fallback behavior can aggregate values from multiple
  full paths, so this remains visible instead of silent.
- If a manual file later introduces a conflict, the manual key wins at runtime
  and the conflict is exposed to the UI. Other managed duplicates are skipped
  deterministically and logged rather than silently overwritten.

Activation is **global to the ComfyUI instance**, not scoped to a workflow or
node. Changing it affects subsequent autocomplete searches and executions.

## LoRA Manager UI

The `/wildcards` page uses `WildcardScanner`, `WildcardModelService`, and
`WildcardRoutes` on the same infrastructure as Workflows. It therefore retains:

- standard download and download-queue behavior;
- one standard model card per downloaded artifact/version;
- sorting, searching, pagination, and infinite scrolling;
- bulk mode, move, delete, favorite, and exclude operations;
- folder sidebar, previews, versions, and update management;
- the standard model modal and Civitai metadata.

Wildcard-specific additions are intentionally small:

- an Active badge on the standard card;
- Activate/Deactivate in the card context menu;
- a **Wildcards** tab in the standard model modal for activation state,
  namespace/single-key alias editing, effective-key browsing, source content,
  and candidate-value previews. It stays last so the normal card click keeps
  the conventional first tab; explicit wildcard entry points (`Open in
  manager`, Details/Activate) switch to it;
- Active state included in the normal formatted model response.

The manager is also where complex conflict resolution belongs. The canvas panel
can report a conflict, but namespace and alias editing stays in the manager.

## ComfyUI Global Wildcards panel

Plugin mode adds a **Global Wildcards** floating panel. Open it from **Quick
Actions → Global Wildcards** or the default `Alt+W` binding. The command id is
`LoraManager.ToggleWildcardQuickPanel`; the binding can be changed or removed in
ComfyUI's keybinding settings.

The panel provides:

- a sectioned list: **Active** resources, **Library** (inactive) resources, and
  **Manual** keys; the panel opens with `All`, and the `Active` scope hides only
  the managed Library section;
- resource-name and wildcard-key search, plus an in-detail key filter;
- an `Active` badge on activated resources and a `Manual` badge on manual keys;
- a right-hand overview with preview, format/base model, namespace/alias,
  key/value counts, effective-key inspection, and one-click `__key__` copying;
- activation/deactivation for managed resources, with conflict details and a
  direct route to the full Wildcards Manager;
- a three-value preview and source path for manual keys, without activation
  controls;
- delayed image preview when hovering a resource row;
- runtime-conflict status and keyboard navigation (`↑`/`↓`, `Enter`, `Esc`).

Activating from the panel means activating an existing local resource, never
downloading from Civitai. The panel's **Open in manager** action reuses the
named `lm-lora-manager` tab (the same tab the recipe picker uses) and
deep-links to `#model=<file_path>`; the wildcards page opens the same shared
model modal a card click uses, with the Wildcards tab selected. Manual files
are listed individually but remain read-only and non-toggleable. The panel and
manager call the same activation endpoints. A
`lm_wildcards_changed` websocket event refreshes an open panel after a change.

The canvas panel is not a second full resource manager. Downloads, updates,
bulk operations, alias editing, and conflict repair stay in the standard
manager. See
[wildcards-quick-panel-redesign](wildcards-quick-panel-redesign.md) for the
interaction contract and design reference.

## Runtime loading

`py/services/wildcard_service.py` combines two sources:

1. Files under the existing `<settings_dir>/wildcards` manual directory, with
   backward-compatible TXT/YAML/JSON behavior.
2. Parsed values from activated managed resources only.

Manual directory signatures and activated artifact signatures invalidate the
cache. Inactive resources are not parsed or loaded. Existing `PromptLM` and
`TextLM` nodes call this service without a new node-level activation input.

Standalone mode has no ComfyUI autocomplete, canvas panel, or node expansion;
its library and activation management remain available for inspection and
preparing the activation state.

## API surface

Wildcard resources use the common `/api/lm/wildcards/*` model routes, including
list, download, metadata, versions, move, and delete. Feature-specific routes
use `file_path` as the resource identifier:

- `GET /api/lm/wildcards/active?search=...` — lightweight library/active state
  for the canvas panel, including format/base-model/alias fields, manual keys
  with source paths and a three-value preview, and runtime conflicts.
- `POST /api/lm/wildcards/activate` — body: `file_path`, optional `namespace`,
  optional `aliases`.
- `POST /api/lm/wildcards/deactivate` — body: `file_path`.
- `GET /api/lm/wildcards/content?file_path=...&source_path=...` — bounded raw
  source preview.
- `GET /api/lm/wildcards/entries?file_path=...&key=...&offset=0&limit=200` —
  paginated values for one effective or source key.
- `POST /api/lm/wildcards/import` — multipart local artifact import.

`GET /api/lm/wildcards/search` remains the separate autocomplete endpoint.

## Sidecar storage compatibility

Centralized sidecar support requires two independent registrations, both now
covered by regression tests:

1. `wildcards_roots` is included in `py/utils/sidecar_paths.py`'s model-root
   enumeration, so metadata and previews resolve into the centralized mirror.
2. `wildcard_scanner` is included in the default `SidecarMigrationUseCase`
   factories, so alongside and centralized migrations actually process wildcard
   artifacts. The migration skips it only when the feature is disabled.

These fixes address two different failure modes. Registering the root changes
future path resolution but does not move existing files. Registering the
migration scanner moves existing metadata and previews.

`MetadataManager`'s legacy lookup handles the old sidecar **naming rule**, not an
unconditional physical-alongside fallback. In centralized mode both current and
legacy paths can point into the mirror. Therefore a file written alongside
before the root registration fix still needs migration before the modal can read
it from the centralized layout.

Repeated “outside configured model roots” warnings were produced by independent
metadata/preview path queries during one download. The logger did not deduplicate
per artifact, and read/check operations triggered the warning as well as writes.

## Implementation status

Implemented and verified:

- first-class scanner, metadata, service, routes, settings, and download support;
- standard manager page and Wildcards tab in the shared model modal;
- global activation registry and runtime merging;
- Global Wildcards quick panel with websocket refresh;
- safe parsing and activation conflict handling;
- centralized sidecar resolution and bidirectional migration;
- manual-directory backward compatibility.

Known boundaries and follow-up candidates:

- Activation records are path-based. Moving or renaming an activated artifact
  can leave a stale record; the runtime skips the missing path and the resource
  should be reactivated at its new path. Stable identity rebinding is a future
  improvement.
- Standard bulk operations are available, but there is no dedicated bulk
  Activate/Deactivate action yet.
- The quick panel does not edit namespaces/aliases and does not download from
  Civitai; use the manager for those operations.
- Activation is global only. Per-workflow or per-node profiles are not currently
  supported.
- Manual-directory entries are visible as a count but are not independently
  toggleable in the quick panel.

## Verification

The final automated regression results were:

- Backend: **4683 passed, 8 skipped**.
- Frontend JavaScript: **227 test files, 2268 tests passed**.
- Wildcard parser, scanner, activation, route, node, and i18n tests included.
- Sidecar tests cover centralized path resolution, bidirectional wildcard
  migration, and full metadata loading after migration.

A sandboxed standalone instance also verified the real Civitai flow through the
production endpoints: download a ZIP, list its standard model card and metadata,
activate it with a namespace, inspect the active list, and deactivate it. The
centralized sidecar issues were covered separately by the dedicated migration
and path-resolution tests above.

Useful focused checks:

```bash
pytest -q \
  tests/services/test_wildcard_parser.py \
  tests/services/test_wildcard_scanner.py \
  tests/services/test_wildcard_activation_service.py \
  tests/routes/test_wildcard_activation_routes.py \
  tests/utils/test_sidecar_paths.py \
  tests/services/use_cases/test_sidecar_migration_use_case.py

npm run test:js -- \
  tests/frontend/components/wildcardQuickPanel.test.js \
  tests/frontend/components/quickActionsMenu.test.js
```

## Primary code locations

- `py/services/wildcard_parser.py` — safe artifact parsing and source previews.
- `py/services/wildcard_scanner.py` — library discovery and metadata indexing.
- `py/services/wildcard_model_service.py` — standard model formatting plus
  activation fields.
- `py/services/wildcard_activation_service.py` — activation records, conflict
  checks, aliases, and active-value loading.
- `py/services/wildcard_service.py` — manual + active runtime dictionary and
  expansion.
- `py/routes/wildcard_routes.py` — shared model routes and activation endpoints.
- `templates/wildcards.html` and `static/js/wildcards.js` — standard manager
  page.
- `static/js/components/ContextMenu/WildcardContextMenu.js` and
  `static/js/utils/wildcardActions.js` — card/context-menu modal and activation
  interactions.
- `static/js/components/shared/WildcardTab.js` and the `wildcards` tab in
  `static/js/components/shared/ModelModal.js` — activation, keys and source
  preview inside the shared model modal.
- `web/comfyui/wildcard_quick_panel.js` — global canvas panel.
- `web/comfyui/wildcard_quick_panel_extension.js` — ComfyUI command and event
  registration.

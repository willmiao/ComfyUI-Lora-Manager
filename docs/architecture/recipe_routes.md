# Recipe route architecture

The recipe routing stack now mirrors the modular model route design. HTTP
bindings, controller wiring, handler orchestration, and business rules live in
separate layers so new behaviours can be added without re-threading the entire
feature. The diagram below outlines the flow for a typical request:

```mermaid
graph TD
    subgraph HTTP
        A[RecipeRouteRegistrar] -->|binds| B[RecipeRoutes controller]
    end
    subgraph Application
        B --> C[RecipeHandlerSet]
        C --> D1[Handlers]
        D1 --> E1[Use cases]
        E1 --> F1[Services / scanners]
    end
    subgraph Side Effects
        F1 --> G1[Cache & fingerprint index]
        F1 --> G2[Metadata files]
        F1 --> G3[Temporary shares]
    end
```

## Layer responsibilities

| Layer | Module(s) | Responsibility |
| --- | --- | --- |
| Registrar | `py/routes/recipe_route_registrar.py` | Declarative list of every recipe endpoint and helper methods that bind them to an `aiohttp` application. |
| Controller | `py/routes/base_recipe_routes.py`, `py/routes/recipe_routes.py` | Lazily resolves scanners/clients from the service registry, wires shared templates/i18n, instantiates `RecipeHandlerSet`, and exposes a `{handler_name: coroutine}` mapping for the registrar. |
| Handler set | `py/routes/handlers/recipe_handlers.py` | Thin HTTP adapters grouped by concern (page view, listings, queries, mutations, sharing). They normalise responses and translate service exceptions into HTTP status codes. |
| Services & scanners | `py/services/recipes/*.py`, `py/services/recipe_scanner.py`, `py/services/service_registry.py` | Concrete business logic: metadata parsing, persistence, sharing, fingerprint/index maintenance, and cache refresh. |

## Handler responsibilities & invariants

`RecipeHandlerSet` flattens purpose-built handler objects into the callables the
registrar binds. Each handler is responsible for a narrow concern and enforces a
set of invariants before returning:

| Handler | Key endpoints | Collaborators | Contracts |
| --- | --- | --- | --- |
| `RecipePageView` | `/loras/recipes` | `SettingsManager`, `server_i18n`, Jinja environment, recipe scanner getter | Template rendered with `is_initializing` flag when caches are still warming; i18n filter registered exactly once per environment instance. |
| `RecipeListingHandler` | `/api/lm/recipes`, `/api/lm/recipe/{id}` | `recipe_scanner.get_paginated_data`, `recipe_scanner.get_recipe_by_id` | Listings respect pagination and search filters; every item receives a `file_url` fallback even when metadata is incomplete; missing recipes become HTTP 404. |
| `RecipeQueryHandler` | Tag/base-model stats, syntax, LoRA lookups, `find_duplicates`, `find_similar` | Recipe scanner cache, `format_recipe_file_url` helper | Cache snapshots are reused without forcing refresh; duplicate lookups collapse groups by exact fingerprint; similar lookups collapse groups by a fuzzy signature (see below); syntax lookups return helpful errors when LoRAs are absent. |
| `RecipeManagementHandler` | Save, update, reconnect, bulk delete, widget ingest | `RecipePersistenceService`, `RecipeAnalysisService`, recipe scanner | Persistence results propagate HTTP status codes; fingerprint/index updates flow through the scanner before returning; validation errors surface as HTTP 400 without touching disk. |
| `RecipeAnalysisHandler` | Uploaded/local/remote analysis | `RecipeAnalysisService`, `civitai_client`, recipe scanner | Unsupported content types map to HTTP 400; download errors (`RecipeDownloadError`) are not retried; every response includes a `loras` array for client compatibility. |
| `RecipeSharingHandler` | Share + download | `RecipeSharingService`, recipe scanner | Share responses provide a stable download URL and filename; expired shares surface as HTTP 404; downloads stream via `web.FileResponse` with attachment headers. |

## Use case boundaries

The dedicated services encapsulate long-running work so handlers stay thin.

| Use case | Entry point | Dependencies | Guarantees |
| --- | --- | --- | --- |
| `RecipeAnalysisService` | `analyze_uploaded_image`, `analyze_remote_image`, `analyze_local_image`, `analyze_widget_metadata` | `ExifUtils`, `RecipeParserFactory`, downloader factory, optional metadata collector/processor | Normalises missing/invalid payloads into `RecipeValidationError`; generates consistent fingerprint data to keep duplicate detection stable; temporary files are cleaned up after every analysis path. |
| `RecipePersistenceService` | `save_recipe`, `delete_recipe`, `update_recipe`, `reconnect_lora`, `bulk_delete`, `save_recipe_from_widget` | `ExifUtils`, recipe scanner, card preview sizing constants | Writes images/JSON metadata atomically; updates scanner caches and hash indices before returning; recalculates fingerprints whenever LoRA assignments change. |
| `RecipeSharingService` | `share_recipe`, `prepare_download` | `tempfile`, recipe scanner | Copies originals to TTL-managed temp files; metadata lookups re-use the scanner; expired shares trigger cleanup and `RecipeNotFoundError`. |

## Maintaining critical invariants

* **Cache updates** – Mutations (`save`, `delete`, `bulk_delete`, `update`) call
  back into the recipe scanner to mutate the in-memory cache and fingerprint
  index before returning a response. Tests assert that these methods are invoked
  even when stubbing persistence.
* **Fingerprint management** – `RecipePersistenceService` recomputes
  fingerprints whenever LoRA metadata changes and duplicate lookups use those
  fingerprints to group recipes. Handlers bubble the resulting IDs so clients
  can merge duplicates without an extra fetch.
* **Similarity grouping (two stages)** – `GET /api/lm/recipes/find-similar`
  groups recipes deterministically in two passes (all in `py/utils/utils.py`):
  1. **Base signature** (`calculate_recipe_similarity_signature`) — a
     *weight-free* key capturing which LoRAs a recipe uses (checkpoint/model
     always ignored), plus the normalized prompt (`match_prompt`) and/or config
     (`match_config`, = steps/sampler/cfg/size/clip_skip/denoising_strength;
     seed always excluded). `drop_low_weight` + `low_weight_threshold` ignore
     LoRAs by weight *magnitude* (`-0.1` drops, `-0.6` stays).
  2. **Weight clustering** (`cluster_recipes_by_weight`) — each base group is
     split into single-linkage connected components where two recipes link only
     if every shared LoRA's weight differs by at most `weight_tolerance` (`0`
     disables splitting). Keeps groups transitive while catching "same LoRAs,
     very different weights".
  The handler enriches each recipe with `diff_loras` (name/weight/low_weight)
  and `diff_params` so the frontend can render an expandable per-group **diff
  table** (LoRAs × recipes, differing weights highlighted, plus prompt/config
  match rows). The UI lives in a popover on the recipes-tab "Find Similar"
  button and reuses the duplicate-group banner/grid for review + bulk delete.
* **Metadata synchronisation** – Saving or reconnecting a recipe updates the
  JSON sidecar, refreshes embedded metadata via `ExifUtils`, and instructs the
  scanner to resort its cache. Sharing relies on this metadata to generate
  filenames and ensure downloads stay in sync with on-disk state.

## Extending the stack

1. Declare the new endpoint in `ROUTE_DEFINITIONS` with a unique handler name.
2. Implement the coroutine on an existing handler or introduce a new handler
   class inside `py/routes/handlers/recipe_handlers.py` when the concern does
   not fit existing ones.
3. Wire additional collaborators inside
   `BaseRecipeRoutes._create_handler_set` (inject new services or factories) and
   expose helper getters on the handler owner if the handler needs to share
   utilities.

Integration tests in `tests/routes/test_recipe_routes.py` exercise the listing,
mutation, analysis-error, and sharing paths end-to-end, ensuring the controller
and handler wiring remains valid as new capabilities are added.


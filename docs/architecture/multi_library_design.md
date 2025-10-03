# Multi-Library Management for Standalone Mode

## Requirements Summary
- **Independent libraries**: In standalone mode, users can maintain multiple libraries, where each library represents a distinct set of model folders (LoRAs, checkpoints, embeddings, etc.). Only one library is active at any given time, but users need a fast way to switch between them.
- **Library-specific settings**: The fields that vary per library are `folder_paths`, `default_lora_root`, `default_checkpoint_root`, and `default_embedding_root` inside `settings.json`.
- **Persistent caches**: Every library must have its own SQLite persistent model cache so that metadata generated for one library does not leak into another.
- **Backward compatibility**: Existing single-library setups should continue to work. When no multi-library configuration is provided, the application should behave exactly as before.

## Proposed Design
1. **Library registry**
   - Extend the standalone configuration to hold a list of libraries, each identified by a unique name.
   - Each entry stores the folder path configuration plus any library-scoped metadata (e.g. creation time, display name).
   - The active library key is stored separately to allow quick switching without rewriting the full config.
2. **Settings management**
   - Update `settings_manager` to load and persist the library registry. When a library is activated, hydrate the in-memory settings object with that library's folder configuration.
   - Provide helper methods for creating, renaming, and deleting libraries, ensuring validation for duplicate names and path collisions.
   - Continue writing the active library settings to `settings.json` for compatibility, while storing the registry in a new section such as `libraries`.
3. **Persistent model cache**
   - Derive the SQLite file path from the active library, e.g. `model_cache_<library>.sqlite` or a nested directory structure like `model_cache/<library>/models.sqlite`.
   - Update `PersistentModelCache` so it resolves the database path dynamically whenever the active library changes. Ensure connections are closed before switching to avoid locking issues.
   - Migrate existing single cache files by treating them as the default library's cache.
4. **Model scanning workflow**
   - Modify `ModelScanner` and related services to react to library switches by clearing in-memory caches, re-reading folder paths, and rehydrating metadata from the library-specific SQLite cache.
   - Provide API endpoints in standalone mode to list libraries, activate one, and trigger a rescan.
5. **UI/UX considerations**
   - In the standalone UI, introduce a library selector component that surfaces available libraries and offers quick switching.
   - Offer feedback when switching libraries (e.g. spinner while rescanning) and guard destructive actions with confirmation prompts.

## Implementation Notes
- **Data migration**: On startup, detect if the old `settings.json` structure is present. If so, create a default library entry using the current folder paths and point the active library to it.
- **Thread safety**: Ensure that any long-running scans are cancelled or awaited before switching libraries to prevent race conditions in cache writes.
- **Testing**: Add unit tests for the settings manager to cover library CRUD operations and cache path resolution. Include integration tests that simulate switching libraries and verifying that the correct models are loaded.
- **Documentation**: Update user guides to explain how to define libraries, switch between them, and where the new cache files are stored.
- **Extensibility**: Keep the design open to future per-library settings (e.g. auto-refresh intervals, metadata overrides) by storing library data as objects instead of flat maps.

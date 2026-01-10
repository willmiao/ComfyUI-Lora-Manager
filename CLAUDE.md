# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

ComfyUI LoRA Manager is a comprehensive LoRA management system for ComfyUI that combines a Python backend with browser-based widgets. It provides model organization, downloading from CivitAI/CivArchive, recipe management, and one-click workflow integration.

## Development Commands

### Backend Development
```bash
# Install dependencies
pip install -r requirements.txt

# Install development dependencies (for testing)
pip install -r requirements-dev.txt

# Run standalone server (port 8188 by default)
python standalone.py --port 8188

# Run backend tests with coverage
COVERAGE_FILE=coverage/backend/.coverage pytest \
  --cov=py \
  --cov=standalone \
  --cov-report=term-missing \
  --cov-report=html:coverage/backend/html \
  --cov-report=xml:coverage/backend/coverage.xml \
  --cov-report=json:coverage/backend/coverage.json

# Run specific test file
pytest tests/test_recipes.py
```

### Frontend Development
```bash
# Install frontend dependencies
npm install

# Run frontend tests
npm test

# Run frontend tests in watch mode
npm run test:watch

# Run frontend tests with coverage
npm run test:coverage
```

### Localization
```bash
# Sync translation keys after UI string updates
python scripts/sync_translation_keys.py
```

## Architecture

### Backend Structure (Python)

**Core Entry Points:**
- `__init__.py` - ComfyUI plugin entry point, registers nodes and routes
- `standalone.py` - Standalone server that mocks ComfyUI dependencies
- `py/lora_manager.py` - Main LoraManager class that registers HTTP routes

**Service Layer** (`py/services/`):
- `ServiceRegistry` - Singleton service registry for dependency management
- `ModelServiceFactory` - Factory for creating model services (LoRA, Checkpoint, Embedding)
- Scanner services (`lora_scanner.py`, `checkpoint_scanner.py`, `embedding_scanner.py`) - Model file discovery and indexing
- `model_scanner.py` - Base scanner with hash-based deduplication and metadata extraction
- `persistent_model_cache.py` - SQLite-based cache for model metadata
- `metadata_sync_service.py` - Syncs metadata from CivitAI/CivArchive APIs
- `civitai_client.py` / `civarchive_client.py` - API clients for external services
- `downloader.py` / `download_manager.py` - Model download orchestration
- `recipe_scanner.py` - Recipe file management and image association
- `settings_manager.py` - Application settings with migration support
- `websocket_manager.py` - WebSocket broadcasting for real-time updates
- `use_cases/` - Business logic orchestration (auto-organize, bulk refresh, downloads)

**Routes Layer** (`py/routes/`):
- Route registrars organize endpoints by domain (models, recipes, previews, example images, updates)
- `handlers/` - Request handlers implementing business logic
- Routes use aiohttp and integrate with ComfyUI's PromptServer

**Recipe System** (`py/recipes/`):
- `base.py` - Base recipe metadata structure
- `enrichment.py` - Enriches recipes with model metadata
- `merger.py` - Merges recipe data from multiple sources
- `parsers/` - Parsers for different recipe formats (PNG, JSON, workflow)

**Custom Nodes** (`py/nodes/`):
- `lora_loader.py` - LoRA loader nodes with preset support
- `save_image.py` - Enhanced save image with pattern-based filenames
- `trigger_word_toggle.py` - Toggle trigger words in prompts
- `lora_stacker.py` - Stack multiple LoRAs
- `prompt.py` - Prompt node with autocomplete
- `wanvideo_lora_select.py` - WanVideo-specific LoRA selection

**Configuration** (`py/config.py`):
- Manages folder paths for models, checkpoints, embeddings
- Handles symlink mappings for complex directory structures
- Auto-saves paths to settings.json in ComfyUI mode

### Frontend Structure (JavaScript)

**ComfyUI Widgets** (`web/comfyui/`):
- Vanilla JavaScript ES modules extending ComfyUI's LiteGraph-based UI
- `loras_widget.js` - Main LoRA selection widget with preview
- `loras_widget_events.js` - Event handling for widget interactions
- `autocomplete.js` - Autocomplete for trigger words and embeddings
- `preview_tooltip.js` - Preview tooltip for model cards
- `top_menu_extension.js` - Adds "Launch LoRA Manager" menu item
- `trigger_word_highlight.js` - Syntax highlighting for trigger words
- `utils.js` - Shared utilities and API helpers

**Widget Development:**
- Widgets use `app.registerExtension` and `getCustomWidgets` hooks
- `node.addDOMWidget(name, type, element, options)` embeds HTML in nodes
- See `docs/dom_widget_dev_guide.md` for complete DOMWidget development guide

**Web Source** (`web-src/`):
- Modern frontend components (if migrating from static)
- `components/` - Reusable UI components
- `styles/` - CSS styling

### Key Patterns

**Dual Mode Operation:**
- ComfyUI plugin mode: Integrates with ComfyUI's PromptServer, uses folder_paths
- Standalone mode: Mocks ComfyUI dependencies via `standalone.py`, reads paths from settings.json
- Detection: `os.environ.get("LORA_MANAGER_STANDALONE", "0") == "1"`

**Settings Management:**
- Settings stored in user directory (via `platformdirs`) or portable mode (in repo)
- Migration system tracks settings schema version
- Template in `settings.json.example` defines defaults

**Model Scanning Flow:**
1. Scanner walks folder paths, computes file hashes
2. Hash-based deduplication prevents duplicate processing
3. Metadata extracted from safetensors headers
4. Persistent cache stores results in SQLite
5. Background sync fetches CivitAI/CivArchive metadata
6. WebSocket broadcasts updates to connected clients

**Recipe System:**
- Recipes store LoRA combinations with parameters
- Supports import from workflow JSON, PNG metadata
- Images associated with recipes via sibling file detection
- Enrichment adds model metadata for display

**Frontend-Backend Communication:**
- REST API for CRUD operations
- WebSocket for real-time progress updates (downloads, scans)
- API endpoints follow `/loras/*` pattern

## Code Style

**Python:**
- PEP 8 with 4-space indentation
- snake_case for files, functions, variables
- PascalCase for classes
- Type hints preferred
- English comments only (per copilot-instructions.md)
- Loggers via `logging.getLogger(__name__)`

**JavaScript:**
- ES modules with camelCase
- Files use `*_widget.js` suffix for ComfyUI widgets
- Prefer vanilla JS, avoid framework dependencies

## Testing

**Backend Tests:**
- pytest with `--import-mode=importlib`
- Test files: `tests/test_*.py`
- Fixtures in `tests/conftest.py`
- Mock ComfyUI dependencies using standalone.py patterns
- Markers: `@pytest.mark.asyncio` for async tests, `@pytest.mark.no_settings_dir_isolation` for real paths

**Frontend Tests:**
- Vitest with jsdom environment
- Test files: `tests/frontend/**/*.test.js`
- Setup in `tests/frontend/setup.js`
- Coverage via `npm run test:coverage`

## Important Notes

**Settings Location:**
- ComfyUI mode: Auto-saves folder paths to user settings directory
- Standalone mode: Use `settings.json` (copy from `settings.json.example`)
- Portable mode: Set `"use_portable_settings": true` in settings.json

**API Integration:**
- CivitAI API key required for downloads (add to settings)
- CivArchive API used as fallback for deleted models
- Metadata archive database available for offline metadata

**Symlink Handling:**
- Config scans symlinks to map virtual paths to physical locations
- Preview validation uses normalized preview root paths
- Fingerprinting prevents redundant symlink rescans

**ComfyUI Node Development:**
- Nodes defined in `py/nodes/`, registered in `__init__.py`
- Frontend widgets in `web/comfyui/`, matched by node type
- Use `WEB_DIRECTORY = "./web/comfyui"` convention

**Recipe Image Association:**
- Recipes scan for sibling images in same directory
- Supports repair/migration of recipe image paths
- See `py/services/recipe_scanner.py` for implementation details

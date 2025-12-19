# ComfyUI LoRA Manager

## Project Overview

ComfyUI LoRA Manager is a comprehensive extension for ComfyUI that streamlines the organization, downloading, and application of LoRA models. It functions as both a custom node within ComfyUI and a standalone application.

**Key Features:**
*   **Model Management:** Browse, organize, and download LoRA models (and Checkpoints/Embeddings) from Civitai and CivArchive.
*   **Visualization:** Preview images, videos, and trigger words.
*   **Workflow Integration:** "One-click" integration into ComfyUI workflows, preserving generation parameters.
*   **Recipe System:** Save and share LoRA combinations as "recipes".
*   **Architecture:** Hybrid Python backend (API, file management) and JavaScript/HTML frontend (Web UI).

## Directory Structure

*   `py/`: Core Python backend source code.
    *   `lora_manager.py`: Main entry point for the ComfyUI node.
    *   `routes/`: API route definitions (using `aiohttp` in standalone, or ComfyUI's server).
    *   `services/`: Business logic (downloading, metadata, scanning).
    *   `nodes/`: ComfyUI custom node implementations.
*   `static/`: Frontend static assets (CSS, JS, Images).
*   `templates/`: HTML templates (Jinja2).
*   `locales/`: Internationalization JSON files.
*   `web/comfyui/`: JavaScript extensions specifically for the ComfyUI interface.
*   `standalone.py`: Entry point for running the manager as a standalone web app.
*   `tests/`: Backend tests.
*   `requirements.txt`: Python runtime dependencies.
*   `package.json`: Frontend development dependencies and test scripts.

## Building and Running

### Prerequisites
*   Python 3.8+
*   Node.js (only for running frontend tests)

### Backend Setup
1.  Install Python dependencies:
    ```bash
    pip install -r requirements.txt
    ```

### Running in Standalone Mode
You can run the manager independently of ComfyUI for development or management purposes.
```bash
python standalone.py --port 8188
```

### Running in ComfyUI
Ensure the folder is located in `ComfyUI/custom_nodes/`. ComfyUI will automatically load it upon startup.

## Testing

### Backend Tests (Pytest)
1.  Install development dependencies:
    ```bash
    pip install -r requirements-dev.txt
    ```
2.  Run tests:
    ```bash
    pytest
    ```
    *   Coverage reports are generated in `coverage/backend/`.

### Frontend Tests (Vitest)
1.  Install Node dependencies:
    ```bash
    npm install
    ```
2.  Run tests:
    ```bash
    npm run test
    ```
3.  Run coverage:
    ```bash
    npm run test:coverage
    ```

## Development Conventions

*   **Python Style:** Follow PEP 8. Use snake_case for files/functions and PascalCase for classes.
*   **Frontend:** Standard ES modules. UI components often end in `_widget.js`.
*   **Configuration:** User settings are stored in `settings.json`. Developers should reference `settings.json.example`.
*   **Localization:** Update `locales/<lang>.json` and run `scripts/sync_translation_keys.py` when changing UI text.
*   **Documentation:** Architecture details are in `docs/architecture/` and `IFLOW.md`.

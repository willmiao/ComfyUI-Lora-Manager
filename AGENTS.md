# Repository Guidelines

## Project Structure & Module Organization
ComfyUI LoRA Manager pairs a Python backend with browser-side widgets. Backend modules live in <code>py/</code> with HTTP entry points in <code>py/routes/</code>, feature logic in <code>py/services/</code>, shared helpers in <code>py/utils/</code>, and custom nodes in <code>py/nodes/</code>. UI scripts extend ComfyUI from <code>web/comfyui/</code>, while deploy-ready assets remain in <code>static/</code> and <code>templates/</code>. Localization files live in <code>locales/</code>, example workflows in <code>example_workflows/</code>, and interim tests such as <code>test_i18n.py</code> sit beside their source until a dedicated <code>tests/</code> tree lands.

## Build, Test, and Development Commands
- <code>pip install -r requirements.txt</code> installs backend dependencies.
- <code>python standalone.py --port 8188</code> launches the standalone server for iterative development.
- <code>python -m pytest test_i18n.py</code> runs the current regression suite; target new files explicitly, e.g. <code>python -m pytest tests/test_recipes.py</code>.
- <code>python scripts/sync_translation_keys.py</code> synchronizes locale keys after UI string updates.

## Coding Style & Naming Conventions
Follow PEP 8 with four-space indentation and descriptive snake_case file and function names such as <code>settings_manager.py</code>. Classes stay PascalCase, constants in UPPER_SNAKE_CASE, and loggers retrieved via <code>logging.getLogger(__name__)</code>. Prefer explicit type hints and docstrings on public APIs. JavaScript under <code>web/comfyui/</code> uses ES modules with camelCase helpers and the <code>_widget.js</code> suffix for UI components.

## Testing Guidelines
Pytest powers backend tests. Name modules <code>test_<feature>.py</code> and keep them near the code or in a future <code>tests/</code> package. Mock ComfyUI dependencies through helpers in <code>standalone.py</code>, keep filesystem fixtures deterministic, and ensure translations are covered. Run <code>python -m pytest</code> before submitting changes.

## Commit & Pull Request Guidelines
Commits follow the conventional format, e.g. <code>feat(settings): add default model path</code>, and should stay focused on a single concern. Pull requests must outline the problem, summarize the solution, list manual verification steps (server run, targeted pytest), and link related issues. Include screenshots or GIFs for UI or locale updates and call out migration steps such as <code>settings.json</code> adjustments.

## Configuration & Localization Tips
Copy <code>settings.json.example</code> to <code>settings.json</code> and adapt model directories before running the standalone server. Store reference assets in <code>civitai/</code> or <code>docs/</code> to keep runtime directories deploy-ready. Whenever UI text changes, update every <code>locales/&lt;lang&gt;.json</code> file and rerun the translation sync script so ComfyUI surfaces localized strings.

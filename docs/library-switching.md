# Preview Routes

Multi-library support and library switching have been removed. On upgrade, all
configured library folder paths are merged into the active library, and the
`libraries` / `active_library` keys are removed from `settings.json`. Legacy
library-named caches are migrated to the default cache namespace. Multiple
folder roots within that single library remain fully supported.

The preview thumbnails shown in the UI are served through a dynamic endpoint
that resolves files against the currently configured folders at request time.
This keeps previews available when model roots change without touching the
aiohttp router.

## How the dynamic preview endpoint works

* `config.get_preview_static_url()` now returns
  `/api/lm/previews?path=<encoded>&v=<mtime_ns>` for any preview path. The raw
  filesystem location is URL encoded so that it can be passed through the query
  string without leaking directory structure in the route itself. The `v`
  parameter carries the preview file's modification time so a rewritten preview
  (e.g. delete + recreate an LM-managed workflow) produces a fresh URL that
  bypasses the browser's day-long cache; the handler ignores it.【F:py/config.py†L398-L404】
  Because the URL no longer ends with the media extension, clients must not
  pick between `<img>` and `<video>` with a suffix check: derive the extension
  from the decoded `path` value (`static/js/utils/mediaTypes.js` for the web
  UI, `web/comfyui/mediaTypes.js` for the ComfyUI widgets).
* `PreviewRoutes` exposes the `/api/lm/previews` handler which validates the
  decoded path against the directories registered for the current library. The
  request is rejected if it falls outside those roots or if the file does not
  exist.【F:py/routes/preview_routes.py†L5-L21】【F:py/routes/handlers/preview_handlers.py†L9-L48】
* `Config` keeps an up-to-date cache of allowed preview roots. Every time a
  library is applied the cache is rebuilt using the declared LoRA, checkpoint
  and embedding directories (including symlink targets). The validation logic
  checks preview requests against this cache.【F:py/config.py†L51-L68】【F:py/config.py†L180-L248】【F:py/config.py†L332-L346】

Both the ComfyUI runtime (`LoraManager.add_routes`) and the standalone launcher
(`StandaloneLoraManager.add_routes`) register the preview routes instead of
mounting a static directory per root. Preview URLs therefore continue to resolve
correctly when the configured roots change.【F:py/lora_manager.py†L21-L82】【F:standalone.py†L302-L315】

# Library Switching and Preview Routes

Library switching no longer requires restarting the backend. The preview
thumbnails shown in the UI are now served through a dynamic endpoint that
resolves files against the folders registered for the active library at request
time. This allows the multi-library flow to update model roots without touching
the aiohttp router, so previews remain available immediately after a switch.

## How the dynamic preview endpoint works

* `config.get_preview_static_url()` now returns `/api/lm/previews?path=<encoded>`
  for any preview path. The raw filesystem location is URL encoded so that it
  can be passed through the query string without leaking directory structure in
  the route itself.【F:py/config.py†L398-L404】
* `PreviewRoutes` exposes the `/api/lm/previews` handler which validates the
  decoded path against the directories registered for the current library. The
  request is rejected if it falls outside those roots or if the file does not
  exist.【F:py/routes/preview_routes.py†L5-L21】【F:py/routes/handlers/preview_handlers.py†L9-L48】
* `Config` keeps an up-to-date cache of allowed preview roots. Every time a
  library is applied the cache is rebuilt using the declared LoRA, checkpoint
  and embedding directories (including symlink targets). The validation logic
  checks preview requests against this cache.【F:py/config.py†L51-L68】【F:py/config.py†L180-L248】【F:py/config.py†L332-L346】

Both the ComfyUI runtime (`LoraManager.add_routes`) and the standalone launcher
(`StandaloneLoraManager.add_routes`) register the new preview routes instead of
mounting a static directory per root. Switching libraries therefore works
without restarting the application, and preview URLs generated before or after a
switch continue to resolve correctly.【F:py/lora_manager.py†L21-L82】【F:standalone.py†L302-L315】

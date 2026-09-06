# CivitAI image imports can end up with 0 LoRAs

## Symptom

Importing a CivitAI image URL can produce a recipe with **zero LoRA
entries**, even though the image page lists LoRAs in its resource panel.

Reported example: `https://civitai.red/images/140818889` was imported as a
local recipe with 0 LoRAs, while the page shows 3 LoRAs. Some images (e.g.
NSFW / higher browsing level) additionally require a login to view, so their
data is not publicly reachable at all.

## Root cause

URL imports use only two data sources:

1. **CivitAI REST image API** — `GET /api/v1/images?imageId=<id>&nsfw=X&withMeta=true` → `meta`
2. **Embedded image metadata** — EXIF/XMP read from the downloaded bytes

For the same image both sources can be empty, and the one source that does
contain the data is never queried. Verified for image 140818889:

| Source | What it returned |
|---|---|
| REST image API | `meta` holds only a prompt; `modelVersionIds: []`; no `resources`/`hashes`; `baseModel: null` |
| Downloaded image | PNG with **no EXIF/XMP** (the CDN URL ends in `.jpeg`, the body is PNG) |
| Image page HTML | `__NEXT_DATA__` embeds the trpc `image.getGenerationData` result → full `resources` list: 3 LoRAs, each with `modelId`, `modelVersionId`, `modelName`, `modelType`, `versionName`, `baseModel` |

Key points:

- The page's resource panel is fed by an **internal, non-public trpc
  endpoint**, not by the public REST image API.
- That internal endpoint is **login-gated** for some content — the
  "requires login" symptom.
- Even with the version IDs in hand, `/model-versions/{id}` for these
  (Krea) versions returns **no `sha256`**, so an exact local-file hash match
  is impossible; only model/version identity is recoverable.

## Conclusion / status

0-LoRA imports are a data-source gap: public REST meta and image EXIF are
both empty, while the only complete source (page generation data) is
internal, sometimes login-gated, and not used by the importer.

Such imports **cannot be reliably auto-repaired/completed** by the backend
alone. The old "Repair Metadata" feature only re-fetched the same incomplete
REST meta and could not fix them; it was deprecated and has been removed.

**Fixed via the companion browser extension.** When the extension is
installed with a valid license, it scrapes the image page's internal trpc
generation data with the user's session and calls the payload-capable
re-import endpoint (`POST /api/lm/recipe/{recipe_id}/reimport` with
`image_url`/`name`/`resources`/`gen_params`/`base_model`/`tags` query
params), which rebuilds the recipe from the caller-supplied metadata. The
web UI delegates re-import of CivitAI-image-sourced recipes to the extension
automatically (probe + `lm:reimport*` DOM events); without the extension,
re-import silently falls back to the native path, which remains limited by
the data-source gap documented above.

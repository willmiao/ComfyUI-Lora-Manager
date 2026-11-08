# Example-image download throughput

## Problem

Downloading example media for a large library was effectively serial: one
Civitai CDN request per image/video, one model after another, plus an
empirical `delay` (0.2 s) between models. A model with 10–20 gallery items
therefore paid 10–20 network round-trips before the next model started.

The inter-model delay is not the cost. In a 10-image probe it accounted for
about 2 s of a 7 s run; the remaining time was the per-image round-trips.

## Is there a batch endpoint?

No. Civitai's public API exposes:

- `GET /api/v1/images?ids=...` — **metadata** for up to 100 images in one
  request (`IMAGE_IDS_BATCH_MAX = 100`), not the binaries.
- One model-version response that already contains the image URLs the
  downloader uses.
- One binary per `image.civitai.com` URL. Each URL 301-redirects to a
  `blobs-b2.civitai.com` object.

The image cacher also has no multi-URL delivery endpoint. The practical
"batch" is therefore client-side pipelining: bounded concurrent requests, a
rendition that is cheaper to transfer, and a shared cooldown when the CDN
returns 429.

## Measurements (single sample, 2026-11)

Ten images from one model, cold process, Civitai CDN over the local link:

| Strategy | Wall time | Bytes |
| --- | ---: | ---: |
| Old: serial, `/optimized=true` | 7.07 s | 1669 KiB |
| New: 4 concurrent, `width=800` | 3.08 s | 834 KiB |
| New: 8 concurrent, `width=800` | 1.62 s | 834 KiB |
| New: 6 concurrent (default), `width=800` | 3.23 s | 834 KiB |

A 720×924 sample video:

| Rendition | Size |
| --- | ---: |
| Old: `/optimized=true` (original MP4) | 73.4 MB |
| New: `transcode=true,width=450,optimized=true` | 27.0 MB |

The video case was the largest single regression in the old path: the URL
helper only appended `optimized=true`, which the cacher serves as the original
video.

## Design

- `MediaDownloadLimiter` (`py/utils/example_images_processor.py`):
  - bounds concurrent requests (default 6),
  - shares a 429 cooldown across every worker instead of letting each task
    sleep and retry independently,
  - halves the limit on a 429 and adds one slot back after a run of successes
    (AIMD), so a sustained limit settles below the threshold.
- `download_model_images_with_tracking` builds one task per pending item and
  runs them through the limiter. The task result still drives the existing
  per-model bookkeeping (`failed_models`, `rate_limited_models`, metadata
  refresh on 404).
- URLs are built with `build_civitai_media_url`:
  - images: `width=800,optimized=true` (the filename is preserved),
  - videos: `transcode=true,width=450,optimized=true`,
  - non-Civitai URLs: unchanged,
  - `optimize=False`: the original URL.
- The legacy inter-model `delay` defaults to 0. API callers that still send it
  keep the old behavior.
- Failure lists now store the *original* metadata URL, which is what
  `_remove_failed_images_from_metadata` matches against.

## Settings (`DEFAULT_SETTINGS`)

| Key | Default | Meaning |
| --- | ---: | --- |
| `example_images_download_concurrency` | 6 | Simultaneous CDN requests per run |
| `example_images_max_width` | 800 | Image rendition width |
| `example_images_video_max_width` | 450 | Video transcode width |
| `example_images_rate_limit_cooldown` | 30 | Fallback cooldown when `Retry-After` is absent |

Widths are chosen from the image cacher's common-size ladder
(96/320/450/512/800/1200/1600/2200); off-ladder widths are snapped up by the
cacher, so they do not buy a smaller transfer.

## Follow-up: transient failures and Genur recovery

The first implementation still treated *any* non-404 failure as permanent. A
network outage (or the ConnectivityGuard's shared cooldown message) was
written to the sidecar as `downloadFailed: true, downloadError: "not_found"`,
which made a transient failure permanent and produced empty example folders
that were reprocessed every run. Genur was the visible victim: its signed
proxy host (`img.genur.art`) can be unreachable (fake-IP DNS / TLS reset)
while the direct host serves the same asset.

The follow-up changes:

- `download_model_images_with_tracking` returns an `ImageDownloadOutcome`
  (`downloaded`, `failed`, `rate_limited`, `transient`, `recovered`,
  `skipped_failed`) instead of a tuple. Offline/connect/timeout/5xx errors go
  to `transient` and are **not** written to the sidecar; the model is left
  pending (tracked in `retryable_models`) so the next run retries it.
- `retry_failed=True` (force / explicit targets) re-attempts Genur entries
  that carry `downloadFailed`; the flag is cleared only after a file is
  actually written, through `_clear_failed_images_from_metadata` and the
  normal `save_metadata` + cache-update path. No bulk sidecar rewrite is
  needed.
- Genur signed URLs are resolved at download time:
  `img.genur.art/sig/.../<base64>` → `c.genur.art/<uuid>_small.webp`
  (`_large.webp` when optimization is disabled). Direct
  `c.genur.art/<uuid>` URLs get the same `_small.webp` suffix. The direct
  renditions return 200 for the sampled Organic Sauce / Better Lego assets.
- Force now bypasses the model-level "populated folder" guard, so flagged
  images in partially populated folders can be retried; per-image existence
  checks still skip files that are already there.

Existing affected libraries recover by restarting the instance and running a
force download (global or per-model). The 398 Genur entries counted in the
user's sidecars are eligible; Civitai 404 entries stay flagged because those
assets are genuinely gone.

## Future work

- Pipeline models, not just images within a model: start model N+1's image
  jobs while model N's metadata/failure bookkeeping finishes. This helps
  models with only a few gallery items.
- Stream media to a temp file instead of `download_to_memory`; the current
  pool bounds memory at `concurrency × item size`, which is fine for
  transcoded videos but large if `optimize_example_images` is disabled.
- Cache the `image.civitai.com` → `blobs-b2.civitai.com` redirect when a
  rendition is retried, to save one hop per retry.
- Expose the four settings in the settings UI if users need to tune them
  without editing `settings.json`.

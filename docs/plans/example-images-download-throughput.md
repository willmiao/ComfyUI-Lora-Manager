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

## Full-library run (2026-11-08)

The local library (932 LoRA, 51 checkpoint, 6 embedding entries with a
SHA-256; 161 GB of model files) was downloaded into a temporary empty
`example_images_path` with `optimize=true`, concurrency 6 and no inter-model
delay. The clean run finished all 987 models in 1,164 s (19.4 min).

| Metric | Value |
| --- | ---: |
| Models | 987 / 987 |
| Media files | 7,990 |
| Bytes | 1.045 GB |
| Model folders | 985 |
| Media per model | 8.1 |
| Average media size | 131 KB |
| Models/s | 0.85 |
| Media/s | 6.9 |
| Rate-limited responses | 0 |
| New 404 responses | 0 |
| Transient image failures | 9 |
| Timeouts (25 s image bound) | 1 |
| `failed_models` at the end | 46 |

The 46 failed models are mostly permanent absences rather than errors: 25
models have no Civitai media, 10 only carry already-flagged 404 assets and 6
have no sidecar. Two models were left pending in `retryable_models` for the
next run after transient network failures.

### ETA findings

The old formula was `(total - completed) / (completed / elapsed)`. Two
concrete failures showed up:

- **Resumed runs.** Marking 282 already-populated folders as processed took
  about 3 s. The lifetime rate then showed an ETA of 1–5 minutes for a run
  that still needed about 20 minutes (89% median error in the first two
  minutes).
- **Pauses.** `start_time` kept running while the download slept, so a pause
  inflated the displayed elapsed time and the post-resume ETA.

Throughput is also non-stationary: a separate run moved from 1.2 s/model in
its first 100 models to 2.75 s/model in the next 100, then accelerated again
near the end. A lifetime average cannot follow that; a short window follows
it but turns one 25–45 s CDN stall into a wildly pessimistic estimate.

`ThroughputEtaTracker` therefore blends a phase baseline (70%) with a 120 s
window (30%). The baseline restarts after a pause or a large fast counter
jump (the resumed-run skip burst). The tracker needs at least 20 s and four
completed models before it shows an estimate. On the clean run the tracker
had a 2.1% median / 6.0% mean absolute error (the old formula: 3.1% / 5.9%);
in the first two minutes of the resumed run it was 19% versus 89%.

### Reliability fixes from the run

- `.download_progress.json` was only written from a branch that the normal
  download path returned before. Periodic saves now run in both download
  loops, so a crash loses at most ten models.
- aiohttp connection errors often stringify to an empty message. They were
  classified as permanent failures, which wrote `downloadFailed` and dropped
  the image from future attempts. Empty/raised transport errors and local
  write errors are now transient; images get a 25 s wall-clock bound (videos
  180 s) instead of the shared 300 s socket read.
- The status endpoint gained `?compact=1`, replacing six hash lists with
  counts. At 334 models the poll payload dropped from 23.4 KB to 0.4 KB; the
  progress panel polls it every two seconds.
- The progress panel now ignores a poll response that overlaps a newer one,
  so a slow response cannot feed the tracker a stale `completed` count.

### Completion markers and partial-folder repair

A model left partially downloaded by a stop/crash used to be treated as
complete on the next non-force run because its folder already contained files.
Four such folders (28 missing media files) were observed after two interrupted
runs, and they were not in `failed_models`, so the UI did not surface them.

Each model folder now gets `.lm-examples-complete`, written atomically only
after a pass has accounted for every media entry (downloaded now, already on
disk, or permanently flagged). The marker is cleared before a pass starts, so
an interrupted or transient-failure pass leaves the folder unverified. The
non-force skip guard requires **both** media and the marker; a populated folder
without it is re-checked by the per-image existence path, which downloads only
the gaps. The marker is also cleared when a provider metadata refresh succeeds,
because new images may have appeared.

`check_pending_models` uses the same rule, including for models already in
`processed_models` or `failed_models`, so the auto-download pre-check sees an
unmarked legacy/partial folder as pending. The first run after upgrading
therefore re-checks every pre-existing populated folder once (metadata read +
per-image stat, no downloads) and writes markers for them.

User-imported custom images also write the marker, preserving the old behavior
for a folder the user populated by hand; an explicit force download still
re-checks it.

### Bounded metadata refresh and failure summary

- 404-triggered metadata refreshes are wrapped in a 90 s timeout. A hung
  provider no longer parks the serial pipeline; the current metadata is used
  and the model is retried on a later run.
- `failed_models` now carries a reason (`no_media`, `unavailable`,
  `unknown`); models whose provider metadata has not been fetched stay in the
  retryable bucket. The status payload exposes `failure_summary` counts. The
  progress panel renders
  `Not downloaded: 25 without Civitai media · 10 unavailable at source · 2 will retry`
  for ten seconds after completion instead of leaving the user with an opaque
  failed count. The reasons are persisted in `.download_progress.json` so a
  restarted run keeps its breakdown.

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

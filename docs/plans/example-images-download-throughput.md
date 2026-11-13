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
| `example_images_download_concurrency` | 6 | Base simultaneous CDN requests per run |
| `example_images_download_max_concurrency` | 8 | AIMD probe ceiling above the base |
| `example_images_model_concurrency` | 2 | Models whose media may overlap (1 = serial) |
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

### Model pipeline, concurrency probing and redirect reuse

- A bounded model pipeline (`example_images_model_concurrency`, default 2,
  clamped to 1–4) overlaps model preparation/bookkeeping with the previous
  model's last media jobs. Every image still goes through the one shared
  `MediaDownloadLimiter`, so this does not raise the request concurrency; it
  only stops the slots from draining at model boundaries. Setting it to 1
  restores the old serial behavior.
- The limiter keeps its configured base (`example_images_download_concurrency`,
  default 6) and may probe one slot above it after a long success streak, up
  to `example_images_download_max_concurrency` (default 8). A 429 halves the
  limit below the base and the existing AIMD recovery takes over, so 8 is a
  ceiling rather than a new default.
- `Downloader.download_to_memory` caches the final `blobs-*.civitai.com` URL
  for Civitai image renditions for one hour. This only helps retries or
  repeated views of the same rendition (the redirect target is a random blob
  id, not derivable from the rendition path); a 404 invalidates the cache.
  A manual curl on one real rendition measured about 1.9–2.5 s for the
  followed 301 versus 1.2–1.4 s for the cached blob URL (roughly 0.6–0.8 s
  saved per repeat). The 185-image A/B has no repeated rendition URLs, so this
  is not part of its wall-time delta.

### A/B benchmark

`scripts/benchmark_example_images.py` builds a reproducible subset from the
user's cache/sidecars and runs four modes against the same temporary examples
path and fresh per-run cache/sidecar copies:

| Mode | Tree | Model concurrency | Probe ceiling |
| --- | --- | ---: | ---: |
| `serial` | old `9ed75e8f` | 1 | 6 |
| `new-serial` | current | 1 | 6 |
| `pipeline` | current | 2 | 6 |
| `aimd` | current | 2 | 8 |

`serial` vs `new-serial` includes the earlier per-model media pool and
optimized-rendition changes; `new-serial` vs `pipeline` isolates the model
pipeline; `pipeline` vs `aimd` isolates upward probing. Each run starts from an
empty examples directory and its own cache/sidecar copy, so progress/markers
from a previous mode cannot leak in.

Measured on 19 models / 185 selected images, three alternating repeats:

| Mode | Median wall | Speedup vs new-serial | Files | Bytes | 429 | Probe steps |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `serial` (old) | 100.7 s | 0.234× | 177 | 52.3 MB | 0 | 0 |
| `new-serial` | 23.6 s | 1.000× | 177 | 18.0 MB | 0 | 0 |
| `pipeline` | 18.0 s | 1.305× | 177 | 18.0 MB | 0 | 0 |
| `aimd` | 14.0 s | 1.678× | 177 | 18.0 MB | 0 | 6 |

- Model pipeline: **23.4% less wall time** than `new-serial` (1.305×).
- AIMD probing: **22.2% less wall time** than `pipeline`, **40.4% less** than
  `new-serial` (1.678×); each AIMD run probed from 6 to 8 with no 429.
- `serial` → `new-serial` is the earlier per-model media pool plus the
  optimized 800 px rendition change, not the pipeline. The old serial tree
  fetched 52.3 MB versus 18.0 MB for the new tree, so its wall-time delta is
  dominated by those earlier changes.
- New runs classified one model as permanently failed while the old tree
  cleared explicit-target failures; both produced the same 177 files. This is
  the post-P1 failure-classification behavior, not a throughput regression.

### Medium-subset check

A second, larger subset (80 models / 729 selected images) was run twice on the
new tree only, because the old serial tree was aborted after 13/80 models in
about 11 minutes: it stalled on stale metadata, which is exactly the failure the
90 s refresh timeout in the current tree bounds. The new tree finished all 80
models in every run.

| Mode | Runs | Median wall | Speedup vs new-serial | Files | 429 | Probe steps |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `new-serial` | 2 | 110.1 s | 1.000× | 721–730 | 0 | 0 |
| `pipeline` | 2 | 78.7 s | 1.398× | 730 | 0 | 0 |
| `aimd` | 2 | 55.7 s | 1.977× | 730 | 0 | 4 |

- Pipeline: **28.5% less wall time** than new-serial.
- AIMD: **29.3% less** than pipeline and **49.4% less** than new-serial; both
  AIMD runs probed 6 → 8 (two steps each).
- One new-serial run produced 721 files instead of 730; the others produced
  730. A single model was classified failed in every run; no 429s occurred.

The 19-model and 80-model subsets agree on the direction and roughly on the
magnitude of the pipeline/AIMD gains. Neither reproduces the old serial tree's
stall, which is why the full old-vs-new A/B is not recommended.

> **Superseded methodology.** These two tables reused one URL set across modes
> and repeats, so later runs measured a warm Civitai edge cache and the
> 2-repeat baseline mixed the only cold run. See
> [Benchmark correction](#benchmark-correction-cdn-cache-and-per-model-cost-2026-11-13);
> re-measure with the cache-neutral harness before quoting the pipeline gain.

### Full-library validation (new code only)

One full run of the current tree (`9a52ed0b`, `aimd`, model concurrency 2,
probe ceiling 8) processed the UI's default 987 models (lora + checkpoint +
embedding) into a fresh temporary examples directory:

| Metric | Previous clean run (base 6, serial models) | Current full run |
| --- | ---: | ---: |
| Wall time | 1,164 s | 894.7 s |
| Files | 7,990 | 7,404 |
| Bytes | 1.045 GB | 995.3 MB |
| Failed models | 46 | 46 |
| 429 responses | 0 | 0 |
| Probe steps | 0 | 2 (6 → 8) |

- Wall time fell **23.1%**; file throughput rose from 6.86/s to 8.27/s
  (+20.6%) and byte throughput from 0.898 MB/s to 1.112 MB/s (+23.8%).
- The current run produced fewer files (7,404 vs 7,990), so the raw wall-time
  delta is not entirely like-for-like. A sidecar scan of the same selection
  finds 7,714 image entries, so 7,404 downloaded files is plausible after the
  46 failed models; the earlier count likely included extra legacy/local files.
- There were no 429s and exactly two probe steps, so the full run exercised
  8-way concurrency without triggering a cooldown.
- Four per-image download errors were logged; the failed-model count still
  matches the previous run (46).

This validates that the pipeline/AIMD settings survive a full-library run; it
is not an old-vs-new full A/B (the old serial tree would take roughly
70–90 minutes per run and downloads larger renditions).

The subset runs are directional, and the full run validates stability rather
than an old-vs-new full A/B. Re-run the harness after material changes:

```bash
python scripts/benchmark_example_images.py prepare --count 20 --images 180
python scripts/benchmark_example_images.py compare --repeats 3

# Re-verify cost of a library whose images are already on disk (per model):
python scripts/benchmark_example_images.py --workdir .tmp/example-images-bench-reverify \
  prepare --count 200 --images 2000
python scripts/benchmark_example_images.py --workdir .tmp/example-images-bench-reverify \
  reverify --force
python scripts/benchmark_example_images.py --workdir .tmp/example-images-bench-reverify \
  reverify --no-force

# Full 987-model validation of the current tree only:
python scripts/benchmark_example_images.py --workdir .tmp/example-images-bench-full prepare --full
python scripts/benchmark_example_images.py --workdir .tmp/example-images-bench-full run --tree . --mode aimd --port 18300
```

The harness creates its old worktree, cache/sidecar copies and run logs under
`.tmp/example-images-bench/`; none of it is written to the real settings
directory or model library.

The A/B numbers above predate the cache-neutral methodology described in the
next section; treat the incremental pipeline probe gain as provisional until it
is re-measured with `--warm-cache` (the default) and three repeats.

## Benchmark correction: CDN cache and per-model cost (2026-11-13)

A user report ([#1203](https://github.com/willmiao/ComfyUI-Lora-Manager/issues/1203),
81,051 models, most images already on disk) showed no improvement from the
pipeline/AIMD work, so the measurement setup was re-examined.

### Civitai's edge cache invalidated the old A/B

`image.civitai.com` is a Cloudflare edge cache:

| Response | Cache-Control | Observed |
| --- | --- | --- |
| 301 rendition → blob | `public, max-age=172800` (48 h) | `cf-cache-status: MISS → HIT`, `age` up to 32 h on `/original=true` |
| `blobs-b2.civitai.com` object | `max-age=3600` (1 h) | `MISS → HIT` |

Measured on 60 rendition URLs at concurrency 6 from one machine: cold pass
21.3 s (2.82 req/s, 59 MISS) versus warm passes 8.9 s and 9.2 s (6.6–6.8 req/s,
60 HIT), i.e. **2.3×**. The old harness reused one fixed URL set for every mode
and repeat (only the sandbox examples directory was reset), so the first pass
was cold and every later pass was warm; the *old tree also uses a different
URL form* (`.../<imageId>/optimized=true`, usually already warm from Civitai's
own traffic) than the new tree (`width=800,optimized=true`).

Impact on the tables above:

- The 19-model / 185-image medians come from three repeats, so the median run
  is warm; the direction of the pipeline gain may still hold, but it was not
  measured against a warm baseline for every run.
- The 80-model / 729-image runs used two repeats per mode; the `new-serial`
  median is the mean of one cold and one warm run while `pipeline`/`aimd` ran
  warm. The reported `pipeline −28.5%` is therefore not trustworthy and may be
  entirely cache warm-up.
- The full-library `1,164 s → 894.7 s` comparison is not like-for-like (7,990
  vs 7,404 files, different renditions, warm URLs on the second run).

### Harness changes

- `--warm-cache` (default for `compare`) resolves the exact URLs each tree will
  request with that tree's own URL builder (run in a subprocess so the old and
  new modules cannot alias), fetches them once, then probes a sample and
  records the edge hit ratio per run. Cold runs are reported, not silently
  mixed into medians. A single `run` skips warming unless the flag is passed.
- The per-run table is always printed, and the summary reports
  `cache_clean_runs`. `--no-warm-cache` only skips warming; it cannot force
  cold URLs, so its medians are documented as not comparable.
- `--image-width` is pinned in the sandbox settings (default 800) so the
  warm-up and the server agree even if the user's settings differ.
- The A/B subset now skips models outside `folder_paths` roots: their sidecars
  resolve alongside the model file, so the sandbox sidecar copy is not used and
  the old tree cannot read their media. `--any-root` opts back in, `--full`
  keeps every model.

### `reverify`: the workload the report actually hit

`compare` measures 100% missing media, i.e. one CDN request per image. The
report's library has the opposite shape: 81,051 models at ~6.5 models/s
(21,722 at 52 min, 35,029 at 90 min in the screenshots), so almost no requests
are made and the run is bound by per-model bookkeeping. The new `reverify`
command populates the sandbox examples tree from the sidecars and times a
library-wide pass:

| Mode | Request | Shape | Local result (987 models, populated) |
| --- | --- | --- | --- |
| `--force` | `force=true` + explicit hashes | per-model / bulk Re-process | ~5.5–6.3 ms/model |
| `--force --global` | `force=true`, no hashes | global Re-process All | see fix below |
| `--no-force` | `force=false`, no hashes | Download Missing, verified tree | ~0.06–0.08 ms/model |
| `--no-force --no-markers` | `force=false`, no hashes | Download Missing, legacy unmarked tree | ~0.3 ms/model |

`--force` passes the selected hashes, which models a per-model/bulk
*Re-process*: explicit targets always bypass the verified-folder guard.
`--force --global` omits the hashes and mirrors the UI's global entry (use it
with `--full` so every cached model is in scope). A `model_concurrency`
comparison on the populated tree (6.22 s / 5.48 s at 1 versus 6.97 s / 9.09 s
at 2) shows the pipeline does not help a re-verify pass: that work is blocking
synchronous code (sidecar load, `scandir`, marker write), so extra asyncio
workers only interleave at `await` points.

### Fix: force keeps the verified-folder skip

v1.2.9 made `force` bypass the populated-folder guard (commit `04b26b2e9`,
kept by `f9cb3988`) so the global Re-process All could retry stale Genur
flags. That cost a sidecar read, per-image stat and marker rewrite for every
model, even when nothing could change. The guard now skips a verified folder
(media + `.lm-examples-complete`) under `force` unless the model is on the
failed list: a completed pass marks a model failed as soon as any media stays
flagged, and clears it on a successful retry, so the failed list is exactly the
set that can still change. If no progress file was loaded, the failed list
cannot be trusted and force keeps the historical full re-check.

Measured with `reverify --force --global --repeat 2` over 989 models:

| Run | State | Wall | Per model |
| --- | --- | ---: | ---: |
| 1 | no `.download_progress.json` (safety fallback) | 7.9 s | 8.0 ms |
| 2 | progress loaded, all folders verified | 0.1 s | 0.12 ms |

A steady-state Re-process All is therefore ~65× cheaper per model, while
failed models are still re-checked and Genur retries still run. Tests:
`test_force_skips_verified_folder_without_pending_retries`,
`test_force_retries_failed_model_with_verified_folder`,
`test_force_rechecks_verified_folder_without_loaded_progress`,
`test_download_missing_skips_verified_folder`.

Two smaller fixes shipped with it:

- `MetadataUpdater.get_updated_model` accepts the cache entry the caller
  already holds, so the per-model O(N) scan (O(N²) per run; ~1.6 ms/lookup at
  81k) only remains on the rare failure paths.
- `_save_progress` is throttled to one write per `PROGRESS_SAVE_INTERVAL_SECONDS`
  (10 s) at a ten-model boundary and writes atomically (`os.replace`), so a
  81k-model run no longer rewrites a ~6 MB file thousands of times or risks a
  truncated file on a crash.

### Legacy libraries: one-time marker backfill

The first run over a library populated before the marker scheme used to verify
every folder (sidecar read + per-image stat + marker write) just to learn that
nothing was missing. `start_download` now runs
`backfill_legacy_completion_markers` once per examples root: it scans the hash
folders and writes a marker for any folder that already contains media, with no
metadata reads. A `.lm-examples-backfill` flag in the root makes it a one-time
operation.

Trade-off, deliberately accepted for large libraries: a folder left partial by
an interrupted run from **before** the upgrade is trusted instead of repaired
retroactively. The showcase falls back to the remote image at runtime
(`tryLocalImageOrFallbackToRemote`), and a per-model force download (explicit
targets) still repairs it. Interruptions after the upgrade are still repaired,
because every model pass clears its marker before it starts; folders that
appear later go through normal verification.

Measured on 987 populated folders (no progress file, migration gate pre-set):

| Scenario | Rechecked folders | Wall | Note |
| --- | ---: | ---: | --- |
| No backfill (pre-fix behavior) | 985 | 9.7 s | 9.8 ms/model of verification |
| Backfill at start | 0 | 5.4 s | backfill POST 0.11 s; the remaining 5.4 s is two models without an examples folder downloading their media |

Tests: `test_backfill_marks_legacy_folders`, `test_backfill_runs_once`,
`test_legacy_folder_is_trusted_on_upgrade`, plus the existing
`test_unmarked_partial_folder_is_repaired_then_skipped` (which pre-writes the
flag so the post-upgrade repair path stays covered).

Still open (deliberately not changed):

- Folders that appear **after** the backfill (new models, interrupted runs) are
  still verified with blocking I/O; moving that to a thread pool is the next
  lever if it remains too slow on slow storage.

## Future work

- Stream media to a temp file instead of `download_to_memory`; the current
  pool bounds memory at `concurrency × item size`, which is fine for
  transcoded videos but large if `optimize_example_images` is disabled.
- Expose the example-image performance settings in the settings UI if users
  need to tune them without editing `settings.json`.

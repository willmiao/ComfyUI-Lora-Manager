# Plan: Global Rate-Limit Abidance for Recipe Ingest & Metadata Fetching

**Issue:** [#1085 — Large Recipe Ingest Appears to not abide by vendor rate limits, possibly a few other errors?](https://github.com/willmiao/ComfyUI-Lora-Manager/issues/1085)
**Status:** v1 — awaiting review
**Scope:** HTTP API traffic to CivitAI (`civitai.red`) and CivArchive (`civarchive.com`) from metadata fetching (bulk refresh, metadata sync, recipe analysis/enrichment, usage-control lookups). Large binary downloads (model files / preview images via `download_file`) are out of scope for *pacing* (they are already single-connection transfers) but their 429 responses should still be *registered*.

> Context: a first batch of fixes for this issue was already committed as
> `ee233548` ("fix(recipes): enforce batch-import concurrency bound and harden
> ingest errors (#1085)"): the batch-import concurrency controller now shares a
> real semaphore (bounds 1–5 actually apply), the Comfy parser tolerates
> list/`None` `ckpt_name`, CivArchive treats empty error payloads as failures,
> and offline-cooldown short-circuits log at DEBUG. This plan covers the two
> remaining orchestration-level fixes:
> **Fix 2** — slow down globally when a vendor rate limit is hit (respect
> `Retry-After`, queue instead of hammering); **Fix 3** — stop immediately
> failing over to CivArchive when CivitAI is rate-limited.

---

## 1. Problem Statement

During a large recipe ingest (e.g. importing the example-images directory,
which can be thousands of images), the manager fires one metadata request per
checkpoint + per LoRA per image through the fallback provider chain
(`civitai_api → civarchive_api → sqlite`). Consequences observed in #1085:

1. **CivitAI gets hammered** → 429s. The consumer then *immediately* tries
   CivArchive for the same lookup, so **CivArchive gets hammered too** before
   it was ever naturally needed (its only real job is recovering metadata for
   models deleted from CivitAI).
2. Requests are retried per-call after `Retry-After`, but **each concurrent
   call sleeps independently** → thundering herd: thousands of coroutines wake
   at the same moment and re-flood the vendor.
3. While CivArchive is in the `ConnectivityGuard` cooldown, every batch item
   short-circuits and is marked `FAILED` — the batch import's success/failure
   accounting is polluted by a transient vendor state (log spam was fixed in
   `ee233548`; the item-failure accounting is not).
4. `ConnectivityGuard` (`py/services/connectivity_guard.py`) only treats
   transport-level unreachability as offline; **HTTP 429 is invisible to it**,
   so nothing ever intentionally paces request rate.

User expectation from the issue: *"once a vendor rate limit time out is hit,
you should trigger a slow down with intentional reduction in request rate"*.

## 2. Current State (verified against code)

### 2.1 Where 429s are surfaced

- `Downloader.make_request` (`py/services/downloader.py:1120-1132`): HTTP 429 →
  returns `RateLimitError(message, retry_after=…)` parsed from `Retry-After`
  (missing header defaults to `None`).
- `CivitaiClient._make_request` (`py/services/civitai_client.py:97-100`):
  converts `RateLimitError` to a raise immediately; no waiting. Transient
  5xx/connection errors are retried 3× with 1s/2s/4s backoff.
- `CivArchiveClient._make_request` (`py/services/civarchive_client.py`):
  raises `RateLimitError` with `provider="civarchive_api"` when not set.
- `_RateLimitRetryHelper` (`py/services/model_metadata_provider.py:45-102`):
  per-call retry loop — sleeps `retry_after` (capped at 1800 s; `≥120 s` ⇒ no
  retry), then re-raises. Because every concurrent call runs its own helper,
  they sleep in parallel and re-fire in parallel.
- `FallbackMetadataProvider` (`py/services/model_metadata_provider.py:488-508,
  564-584` etc.): on a final `RateLimitError` from one provider it logs
  "skipping to next provider" and **continues to the next network provider** —
  this is the direct cause of the CivArchive flood.
- `MetadataSyncService.fetch_and_update_model`
  (`py/services/metadata_sync_service.py:248-333`): manually iterates
  `provider_attempts`; on `RateLimitError` it `continue`s to the next provider
  (same failover problem), then reports `"Rate limited"` when nothing
  succeeded.
- `Downloader.make_request` has a per-destination scope already available:
  `_guard_destination(url)` returns the hostname (`downloader.py:1194-1199`),
  used by `ConnectivityGuard`.

### 2.2 What pacing exists today

- `ConnectivityGuard`: per-destination cooldown (30 s base, ×2 per extra
  failure batch, 300 s cap) triggered only by transport errors
  (`connectivity_guard.py:168-197`).
- `AdaptiveConcurrencyController` (batch import, fixed in `ee233548`): shared
  semaphore enforces 1–5 concurrent items; *duration*-based adjustment only —
  it never sees HTTP statuses, so it cannot distinguish "slow because rate
  limited" from "slow because big image".
- No token bucket, no minimum inter-request interval, no shared
  `Retry-After` gate anywhere (`grep` for throttle/token-bucket/rate-limiter:
  0 hits).

## 3. Requirements & Constraints

R1. **Respect `Retry-After`.** After a 429, no further request to that
    destination may be sent before the vendor's retry window elapses.
R2. **No thundering herd.** Concurrent waiters must share one wake-up (gate),
    not sleep independently.
R3. **No double load.** A CivitAI 429 must not trigger a CivArchive request
    for the same lookup. CivArchive should only be consulted when CivitAI
    legitimately has no answer (404 / "not found"), or when CivitAI is
    unreachable long-term.
R4. **No spurious item failures.** A rate-limited request must not turn a
    batch-import item into `FAILED`; it should wait (bounded) and retry, or at
    worst be `SKIPPED` with a clear "rate limited" reason (re-runnable import).
R5. **Never hang forever.** All waiting is bounded by a configurable cap; on
    expiry the caller receives the `RateLimitError` and can decide.
R6. **Keep legitimate failover.** Deleted-model recovery via CivArchive/sqlite
    must keep working (404 paths unchanged).
R7. **Single choke point.** The pacing gate should live where every API call
    passes (the `Downloader`), so bulk refresh, metadata sync, recipe
    analysis, and usage-control lookups all benefit without per-feature work.

## 4. Approach Comparison

### A. Reactive gate — shared `Retry-After` deadman clock (recommended core)

A process-wide, per-destination coordinator records the *next-allowed-send*
timestamp from each 429 (`now + max(retry_after, backoff)`). Every request
through `Downloader.make_request` consults the gate *before sending* and *when
a 429 arrives*; waiters block on a shared `asyncio.Event` that fires when the
cooldown expires.

- Pros: single choke point (R7); herd-free (R2); honors server guidance (R1);
  no guessing at vendor limits; covers all providers automatically; reuses
  existing per-destination scoping.
- Cons: still experiences 429s before slowing down (reactive); long
  `Retry-After` windows (CivArchive has been observed at ~1500 s) need a sane
  wait cap + skip/retry UX.

### B. Preemptive pacing — minimum inter-request interval (recommended companion)

Per-destination token bucket (simplest form: capacity 1 — at least `N` seconds
between consecutive API requests; `N` configurable, default ~0.75 s ≈ 80
r/min ceiling).

- Pros: prevents most 429s before they happen — exactly the "intentional
  reduction in request rate" the issue asks for; trivial to implement on top
  of A's coordinator.
- Cons: adds latency to bulk operations (thousands of models × `N`); the *exact*
  vendor limits are unknown (CivitAI anonymous vs keyed vs `civitai.red`
  mirror differ), so the default must be conservative-but-not-crippling and
  settings-tunable.

### C. Fallback semantics change — stop network→network failover on 429 (must-do, low risk)

`FallbackMetadataProvider` (and `MetadataSyncService.fetch_and_update_model`'s
manual loop) must treat a final `RateLimitError` as a **terminal, non-failover
result** for network providers. Local-only providers (sqlite archive DB) may
stay as a last resort (no vendor cost).

- Pros: directly removes the CivArchive flood; small, surgical change.
- Cons: none significant; requires care to keep 404-failover intact (R6).

### Rejected / deferred

- **Per-feature retry queues** (batch import pauses & resumes whole batches):
  richer UX but much larger change (batch state machine, WebSocket states);
  unnecessary once A+B make requests wait at the choke point. Defer unless
  review finds the bounded-wait UX insufficient.
- **Full token bucket with burst credit**: overkill; capacity-1 interval is
  enough given the shared semaphore already caps concurrency at 5.
- **Retrying in `connectivity_guard`**: wrong layer — the guard is about
  transport reachability, not vendor quota.

## 5. Recommended Architecture

New singleton **`RateLimitCoordinator`** (`py/services/rate_limit_coordinator.py`,
mirroring `ConnectivityGuard`'s singleton + per-destination patterns):

```
state per destination (hostname):
  next_allowed_send: float (monotonic)   # from 429 Retry-After + backoff
  consecutive_429: int                   # for backoff growth
  last_send_at: float                    # for min-interval pacing
  waiters: list[Future] | asyncio.Event  # shared wake-up per cooldown cycle
```

API:

- `async wait_for_slot(destination, request_started_within_window: bool)`
  — called by `Downloader.make_request` *before* sending (blocks until
  `min(now >= next_allowed_send)` and inter-request interval elapses) and
  re-armable after a 429.
- `register_rate_limit(destination, retry_after: float | None)`
  — called on 429: `next_allowed_send = max(now + retry_after_or_backoff, current)`;
  `consecutive_429 += 1`; backoff = `retry_after` honored, else exponential
  `30 · 2^(n-1)` capped at 1800 s; creates/re-arms the shared wake-up event.
- `register_success(destination)` — resets `consecutive_429` (called from the
  existing 200 path in `make_request`).
- `remaining_seconds(destination)`, `in_cooldown(destination)` — for tests and
  diagnostics.

Enforcement points:

1. **`Downloader.make_request`** (`downloader.py:1102-1132`): before
   `session.request`, `await coordinator.wait_for_slot(destination)`. On 429:
   `coordinator.register_rate_limit(...)`, then *wait for the gate and
   re-send* (loop, bounded by `rate_limit_max_wait_seconds`, default 300;
   `retry_after ≥ cap` ⇒ fail immediately). After the loop, return the
   `RateLimitError` to the caller (unchanged contract). 200 path calls
   `register_success`.
2. **`Downloader.download_to_memory` / `get_response_headers`** (phase 2):
   register 429s (so API calls queue); waiting only in `make_request`
   initially.
3. **`FallbackMetadataProvider`** (`model_metadata_provider.py`): remove
   network→network failover on `RateLimitError` — re-raise; only sqlite stays
   as a local last resort (implementation: per-method `except RateLimitError`
   handler that marks the chain rate-limited and stops iterating).
4. **`MetadataSyncService.fetch_and_update_model`**
   (`metadata_sync_service.py:248-333`): on `RateLimitError` from the default
   provider, stop appending further network providers (sqlite may remain);
   the existing `any_rate_limited` merge already produces `"Rate limited"`.
5. **Batch import** (`batch_import_service.py`): no structural change needed —
   items now wait inside `make_request`; optionally (phase 2) map residual
   rate-limit failures (after the wait cap) to `SKIPPED` with
   `"rate limited (retry_after=…s); re-run the import later"` instead of
   `FAILED`, and surface a `rate_limited` flag in the WebSocket progress
   broadcast.
6. **`_RateLimitRetryHelper` retries** (`model_metadata_provider.py`): with the
   gate at the downloader, the helper's `retry_after` sleeps become mostly
   redundant; demote/simplify in phase 2 (keep the wiring so a
   `RateLimitError` still propagates cleanly).

Settings (`settings.json`, schema extension in `SettingsManager`):

| key | default | meaning |
|---|---|---|
| `rate_limit_gate_enabled` | `true` | master switch for the coordinator |
| `rate_limit_max_wait_seconds` | `300` | how long `make_request` waits on a 429 gate before returning the error |
| `rate_limit_min_interval_seconds` | `0.75` | minimum seconds between API requests per destination (pacing, R6-friendly conservative default) |

## 6. Changes by File

| File | Change |
|---|---|
| `py/services/rate_limit_coordinator.py` (new) | coordinator singleton + per-destination state + tests seam |
| `py/services/downloader.py` | gate pre-check + 429 register/wait/retry loop + `register_success`; log the 429 notice at INFO once per cooldown, then DEBUG |
| `py/services/model_metadata_provider.py` | `FallbackMetadataProvider`: stop network failover on `RateLimitError`; helper simplification |
| `py/services/metadata_sync_service.py` | `fetch_and_update_model`: same failover semantics; keep sqlite last resort |
| `py/services/batch_import_service.py` | (phase 2) rate-limit failures → `SKIPPED` + `rate_limited` progress flag |
| `py/services/settings_manager.py` | new settings keys + defaults |
| `tests/services/test_rate_limit_coordinator.py` (new) | gate unit tests |
| `tests/services/test_civitai_client.py` / `test_civarchive_client.py` | provider-level 429 behavior |
| `tests/services/test_metadata_service.py` | failover-chain tests |
| `tests/services/test_batch_import_service.py` | SKIPPED-on-rate-limit |

## 7. Impact, Risks, Open Questions

- **Behavior change**: with the gate in `make_request`, any request can block
  up to the wait cap — UI actions that call the API (e.g. a model-details
  fetch) may take longer during cooldowns. Mitigation: bounded cap + INFO log
  + the existing async request handling already tolerates slow responses.
  Open question: should interactive (non-batch) requests skip the wait and
  fail fast instead? (recommend: same wait — simpler, and cooldowns are short)
- **Rate limit reality check**: CivitAI anonymous vs keyed limits, and whether
  `civitai.red` differs, is unverified. Default pacing `0.75 s/req` is a
  conservative guess (R6). Open question for maintainer: preferred default
  and whether an API-keyed ceiling should be higher.
- **Long CivArchive windows**: `Retry-After ~1500 s` observed in code
  comments. A 300 s default cap means such lookups fail rather than wait.
  Open question: raise the default cap, or accept failure+skip semantics?
- **Double waiting**: `_RateLimitRetryHelper` + gate could stack waits; the
  phase-2 simplification removes the helper's own sleeps for requests that go
  through the downloader.
- **Downloads**: `download_file` 429s return an error to download managers
  unchanged (already handled); only *registration* is proposed, so future
  API calls queue behind a large `Retry-After` from a download burst.

## 8. Test Plan

1. **Coordinator unit tests** (new file):
   - 429 with `retry_after` → `wait_for_slot` blocks ~that long, then passes.
   - N concurrent waiters all wake together (herd test, wall-clock ≈ one
     window, not N windows).
   - Consecutive 429s grow backoff; `register_success` resets.
   - Missing `Retry-After` → default backoff path.
   - Wait cap: request fails after `rate_limit_max_wait_seconds` with
     `RateLimitError`.
2. **Downloader tests** (mock aiohttp session): 429 then 200 → `make_request`
   returns success after gate delay; two back-to-back calls to the same
   destination are spaced ≥ `min_interval`; different destinations are not
   spaced.
3. **Provider tests**: `FallbackMetadataProvider.get_model_version_info` —
   Civitai raises `RateLimitError` → CivArchive mock **not called**; 404 still
   falls through to CivArchive; sqlite still tried after network 429.
4. **Sync-service test**: `fetch_and_update_model` with a rate-limited default
   provider → result error contains `"Rate limited"` and sqlite attempt state
   unchanged.
5. **Batch-import test**: analysis provider 429s first, then succeeds →
   item ends `SUCCESS` (wait path), and post-cap 429 → `SKIPPED` with
   rate-limit reason (phase 2).
6. Full regression: `pytest tests/services tests/routes tests/standalone`
   (currently 1582 passing).

## 9. Implementation Phases

- **Phase 1 (this plan, after review):** `RateLimitCoordinator` +
  `Downloader.make_request` integration (pre-check pacing + 429
  register/wait/retry loop + cap) + settings + coordinator/downloader tests.
- **Phase 2:** failover semantics (`FallbackMetadataProvider`,
  `fetch_and_update_model`), helper simplification, batch-import
  `SKIPPED`-on-rate-limit + progress flag, `download_to_memory`/HEAD 429
  registration, provider/sync/batch tests.
- **Phase 3:** full regression + docs + commit referencing `(#1085)`.

## 10. Review Checklist

- [ ] Default pacing interval acceptable (`0.75 s`)? Prefer higher/lower?
- [ ] Wait cap `300 s` acceptable, or should long-window CivArchive lookups
      wait longer?
- [ ] OK that interactive API calls also wait (bounded) instead of failing
      fast?
- [ ] Keep sqlite as last resort behind a network rate limit?
- [ ] Add a UI hint ("rate limited — slowing down") surfaced via WebSocket,
      or is INFO logging enough?
# Plan: Buzz Price Tracking and Threshold Alerts for Paid / Early Access Versions

**Origin:** FR "Price tracker for models/loras" (Geekier, Discord) — track the buzz price of paid
model versions and flag when it drops below a threshold or becomes free.
**Related:** [#1060 — Some "Early Access" models are not identified correctly](https://github.com/willmiao/ComfyUI-Lora-Manager/issues/1060)
(closed) established `is_paid`, the Paid badge and `hide_paid_updates`; this FR is the next step
after gate *state* — gate *price*.
**Status:** v2 — **P0–P3 implemented** (see §10 for what shipped and the deviations from this plan).
Feasibility was verified against this repo and upstream CivitAI `main` (`6d29ed1368`), including live
probes against `civitai.com` / `civitai.red`.
**Scope:** every model type that goes through `ModelUpdateService` (lora / checkpoint / embedding /
other). Out of scope: purchasing, downloading gated content, and any change that depends on a future
CivitAI API addition.

---

## 1. Problem statement

Creators increasingly gate model versions behind buzz. LoRA Manager already knows **whether** a
version is gated (`is_paid`, `is_early_access`, `paid_access`) but not **how much it costs**, so it
cannot answer the two questions the FR asks:

1. "Tell me when this model's price drops below X buzz."
2. "Tell me when it becomes free."

Additionally, the current code only compares version ids when deciding `has_update`, so a version
that a user already tracks can go from paid to free (or gain a gate) without producing any signal at
all.

## 2. Verified current state

### 2.1 LoRA Manager (all references confirmed in this checkout)

| Fact | Reference |
| --- | --- |
| Gate fields persisted per version: `is_paid`, `is_early_access`, `paid_access` (raw DTO JSON), `early_access_ends_at` | `py/services/model_update_service.py:65-84` |
| Gate data comes from the bulk `GET /api/v1/models?ids=…` response (`availability`, `paidAccess`, `earlyAccessEndsAt`) | `py/services/civitai_client.py:329-380`, parsed at `py/services/model_update_service.py:1756-1793` |
| **No numeric price anywhere in `py/`** | `grep -rn "price" py/` → only license/`allowCommercialUse` hits |
| Update refresh is user-triggered, not scheduled; TTL 24 h | route `py/routes/handlers/model_handlers.py:2899`; `ModelUpdateService.__init__` default `ttl_seconds=24*60*60` at `py/services/model_update_service.py:338` |
| `has_update` compares version ids + gate filters only; no state-transition detection | `py/services/model_update_service.py:117-160` |
| `{permanent:false, endsAt:null}` is deliberately treated as **not** a gate on the download path | `py/services/download_manager.py:2000-2003` |
| Version payload sent to the frontend already carries `isPaid` / `paidAccess` | `py/routes/handlers/model_handlers.py:3444-3455` |
| UI: Paid / Early Access badges, `hide_paid_updates` filter | `static/js/components/shared/ModelVersionsTab.js:169-196, 474-545`; `static/js/state/index.js:58-59`; `templates/components/modals/settings/library.html:191-192` |

### 2.2 Upstream CivitAI — what is and is not public

| Fact | Evidence |
| --- | --- |
| Public v1 API intentionally strips pricing: `paidAccess` is reduced to `{permanent, endsAt}`. Source comment: *"Omits terms (pricing belongs to the purchase flow)"* | `~/code/civitai/src/server/services/paid-access.service.ts:640-652`; verified live: `/api/v1/models` and `/api/v1/model-versions/{id}` return exactly that shape |
| The internal tRPC route is **not** usable anonymously. `isAcceptableOrigin` rejects non-site origins with `401 "Please use the public API instead"` | `~/code/civitai/src/server/trpc.ts:120-128`; `acceptableOrigin` = `!isProd \|\| isBearerAuth \|\| isAllowedOriginRequest(req)` (`createContext.ts:43`), and the origin check is header-based (`src/server/utils/origin-helpers.ts:27-32`). **Live probe warning:** an anonymous tRPC GET can return `200` when Cloudflare serves a cached copy (`cf-cache-status: HIT`); uncached it is `401`. Do not build on this path. |
| **The price *is* publicly reachable inside the public model page.** The SSR payload embeds the site's own `model.getById` result, including full `terms` | `https://civitai.com/models/<id>` and `https://civitai.red/models/<id>` → `<script id="__NEXT_DATA__" type="application/json">` → `props.pageProps.trpcState.json.queries[*]` where `queryKey[0] == ["model","getById"]` → `state.data.modelVersions[*].paidAccess` |
| Observed payloads (anonymous, no cookies) | version 3379626 → `{terms:{download:{price:5000},generation:{price:100,trialLimit:5}}, endsAt:null, sale:null}`; version 3380114 → `download.price 125` `acceptsBlueBuzz:true` `endsAt:2026-10-10`; another → `200` |
| Per-generation licensing fees are already public and official | `GET /api/v1/model-versions/mini/{id}` (`MixedAuthEndpoint`, anonymous 200) exposes `fees` / `freeTrialLimit` — `~/code/civitai/src/pages/api/v1/model-versions/mini/[id].ts:455` |
| Webhooks cannot carry price changes | `updated-model` is driven by `Model.lastVersionAt` (fires only on new versions) and its select has no `paidAccess`: `~/code/civitai/src/server/webhooks/model.webooks.ts:88-96`, `~/code/civitai/src/server/selectors/model.selector.ts:15-36` |
| Prevalence (sampled newest 600 models / 4634 versions via public API cursor): **90 gated (1.9%), 87 permanent vs 3 timed** | live scan, 2026-xx; dominated by permanent gates, so "EA expiry" alone covers ~3% of gated versions |

### 2.3 Consequences for the design

* Threshold alerts on download price require **one new data source**: the model page payload. It is
  public, but it is page data — so it must be isolated, opt-in, cheap, and fail-open.
* Request budget is small because only gated models need it: ~2% of models, one extra ~200 KB
  request per gated model per price TTL.
* "Becomes free" and "gained a gate" need no new data source at all and should ship first.
* One page fetch returns **all** versions of a model, so prices cost one request per model, not per
  version.

## 3. Data source decision

**Chosen: `__NEXT_DATA__` of the public model page**, fetched with the existing HTTP stack.

Rejected alternatives:

* *Internal tRPC* — origin-gated; passing it means forging `Origin` or relying on bearer auth against
  an undocumented endpoint whose own error message says to use the public API. Not worth the
  stability/compliance risk for a convenience feature.
* *Official v1 API as-is* — no price field, by design. Track it as an upstream request (§8), not as a
  dependency.
* *`mini/{id}` `fees`* — useful extra signal for per-generation fees, but it is not the download
  price and does not cover the gate.

## 4. Design

### 4.1 Schema (all additive, in the existing update DB)

`model_update_versions` gains:

```sql
ALTER TABLE model_update_versions ADD COLUMN price_buzz INTEGER;            -- effective (sale-adjusted) download price
ALTER TABLE model_update_versions ADD COLUMN list_price_buzz INTEGER;       -- undiscounted download price
ALTER TABLE model_update_versions ADD COLUMN generation_price_buzz INTEGER;
ALTER TABLE model_update_versions ADD COLUMN accepts_blue_buzz INTEGER NOT NULL DEFAULT 0;
ALTER TABLE model_update_versions ADD COLUMN price_sale_ends_at TEXT;
ALTER TABLE model_update_versions ADD COLUMN price_checked_at REAL;         -- last *successful* price fetch
ALTER TABLE model_update_versions ADD COLUMN price_alert_state INTEGER NOT NULL DEFAULT 0; -- last computed alert hit, for edge detection
```

Adding a column to this table requires touching **all eight** enumerations (missing one silently
drops data or breaks reads):

1. dataclass `ModelVersionRecord` — `py/services/model_update_service.py:65-84`
2. `_SCHEMA` `CREATE TABLE` — `:300-330`
3. `_apply_migrations` column dict — `:554-580`
4. `_migrate_model_update_versions_primary_key` `target_columns` + `defaults` — `:680-745` (**easy to
   miss; omitting it loses the new columns whenever the PK migration runs**)
5. `_build_record_from_remote` — `:1630-1665`
6. `_extract_single_version` — `:1740-1795`
7. `_get_records_bulk` SELECT + row→record mapping — `:1945-1990`
8. `_upsert_record` INSERT — `:2028-2066`

`price_checked_at` lives on the version row (not the model status row) so a stale price on one
version does not force a re-fetch for its siblings; the fetch itself is per model.

### 4.2 Parser contract

New pure function, unit-testable without network:

```
parse_model_page_prices(html: str) -> dict[int, dict] | None
```

* Locate `<script id="__NEXT_DATA__" type="application/json">…</script>`; `json.loads` it.
* Walk `props.pageProps.trpcState.json.queries[*]`; pick the entry whose `queryKey[0] == ["model","getById"]`
  (the query order is not stable — 7 queries were observed, `getById` first only incidentally).
* From `state.data.modelVersions[*]`, per version emit:
  * `price_buzz` = `paidAccess.sale.buyerTerms.download.price` if `sale` present, else
    `paidAccess.terms.download.price`
  * `list_price_buzz` = `paidAccess.terms.download.price`
  * `generation_price_buzz` = `terms.generation.price` (undefined for `{free:true}` / bundled)
  * `accepts_blue_buzz`, `price_sale_ends_at`
  * no `paidAccess` → the version is ungated: emit an explicit "no price" marker so the caller can
    clear stale prices and raise a *became free* event.
* Return `None` (never raise) for: missing script tag, JSON error, shape mismatch, empty
  `modelVersions`, or a Cloudflare/challenge page.

### 4.3 Refresh flow and request budget

Hook: `_refresh_single_model` (`py/services/model_update_service.py:1099-1215`), inside the existing
"lock released during network I/O" window, after `fetched_versions` is built:

```
prices_needed = feature_enabled and (any gated version or any version with a stored price)
if prices_needed:
    prices = await provider.get_model_prices(model_id)      # never raises; None on failure
    if prices is not None:
        fetched_versions = [apply_price(v, prices.get(v.version_id)) for v in fetched_versions]
        # price_checked_at advances only for versions actually present in the payload
```

* Candidate selection uses the gate data already in hand from the bulk API, so no extra call is made
  for the ~98% of models with no gate (except models that previously had a price and must confirm
  "now free").
* TTL: `price_check_ttl_hours` (default 24 h), independent of the update TTL — a price refresh can be
  skipped while the version list is fresh, and vice versa. Force refresh (`force_refresh=True`) also
  forces prices.
* Failure behaviour: keep the previous price, do **not** advance `price_checked_at` (so the next
  refresh retries), log at debug/info. A `RateLimitError` from the shared gate must remain a skip,
  not a hard failure of the update check. After N consecutive parse failures within one refresh,
  stop attempting price fetches for the remainder of that run.
* Offline/cooldown: reuse the existing `ConnectivityGuard` path in `downloader.make_request` — no new
  connectivity handling.

Client/provider seam:

* `ModelMetadataProvider.get_model_prices(model_id)` — default returns `None` (not abstract, so
  CivArchive / SQLite providers are untouched).
* `CivitaiModelMetadataProvider` → `CivitaiClient.get_model_prices(model_id)`.
* Add the pass-through to the composite provider wrapper
  (`py/services/model_metadata_provider.py:855-955`) so the rate-limit helper applies.
* `CivitaiClient.get_model_prices`: build the URL with the existing helper
  `build_civitai_model_page_url(model_id, host=self._settings.get("civitai_host"))`
  (`py/utils/civitai_utils.py:44-66`; `civitai.red` is already a supported page host,
  `:10`), fetch with `downloader.make_request("GET", url, use_auth=False, custom_headers={"Accept": "text/html"})`
  (returns `str` because the body is not JSON), then call the parser. Cap the body size before
  parsing.

### 4.4 Alert semantics

* **Threshold hit**: `price_buzz is not None and price_buzz <= threshold_buzz`. `threshold_buzz = 0`
  means "free only, plus any gate removal".
* **Became free**: a version with a stored gate/price now has no `paidAccess` (from the bulk API
  and/or the page payload).
* **Newly gated**: a version that had none now has `paidAccess`.
* Edge detection uses `price_alert_state` plus the previous `paid_access` JSON, compared in
  `_build_record_from_remote` where `existing_map` is already built
  (`py/services/model_update_service.py:1636-1665`). Do not put this in `has_update`: it is a
  different question, and `has_update` is filtered by the hide-* settings.
* `ModelUpdateRecord` gains a **non-persisted** field (e.g. `events: list | None = None`) carrying
  `{version_id, kind: "price_drop"|"became_free"|"new_gate", price_buzz, previous_price_buzz}`.
  `_upsert_record` ignores it; `_get_record` leaves it `None`.

### 4.5 Settings and routes

New settings (defaults in `DEFAULT_SETTINGS`, `py/services/settings_manager.py:68`;
`settings.json.example` stays minimal per repo policy; frontend defaults in
`static/js/state/index.js:58`):

| Key | Default | Meaning |
| --- | --- | --- |
| `price_tracking_enabled` | `False` | master switch; off means no model-page fetches at all |
| `price_alert_threshold_buzz` | `0` | alert when effective price ≤ this; 0 = free only |
| `price_check_ttl_hours` | `24` | price freshness window |

Routes (all under the existing model route registrars, `POST` + `GET` because the companion
extension is GET-only per `AGENTS.md`):

* `GET /api/lm/models/price-alerts` — aggregate over the update DB:
  `{modelId, modelType, versionId, versionName, priceBuzz, listPriceBuzz, thresholdBuzz, isFree}`.
* Prices themselves need no new read route: they ride along in the existing version payload
  (`py/routes/handlers/model_handlers.py:3438-3455` gains `priceBuzz`, `listPriceBuzz`,
  `generationPriceBuzz`, `acceptsBlueBuzz`, `priceCheckedAt`, `priceAlert`).
* The existing update-refresh response gains `events` (from §4.4) so the frontend can toast.

### 4.6 UI

* `static/js/components/shared/ModelVersionsTab.js`
  * Extend the existing Paid / Early Access badge tooltips with the price when known
    ("Paid · 5,000 Buzz") — helpers at `:169-196`, badges at `:474-545`.
  * New badges: price chip (`paid`/`info` styling) and "Free now" for a became-free transition.
  * Filter toggle reusing the `hide_paid_updates` pattern (`:349-400`, plus the settings modal and
    `SettingsManager.js:1157-1163`) — e.g. "Show price drops only".
* Optional, cheap win: include the price in the paid-download error text
  (`py/services/download_manager.py:1987-2031`, `py/services/use_cases/download_model_use_case.py:35`).
* Strings: add to `locales/en.json`, then `python scripts/sync_translation_keys.py`, then **stop** —
  do not translate the other locales (see `docs/i18n-translation-guidelines.md` §7).

## 5. Phased tasks

### P0 — settle gate semantics (prerequisite, small)

- [ ] Decide the meaning of `{permanent:false, endsAt:null}`. The repo currently treats it as *no
      gate* (`py/services/download_manager.py:2000-2003`), while upstream `isPaidAccessActive`
      (`endsAt == null || endsAt > now`) treats it as *active*. Live sample: version 3372655
      currently returns exactly this DTO from `/api/v1/models`.
- [ ] Introduce one shared helper (e.g. `_has_active_gate(paid_access, early_access_ends_at)` in
      `py/services/model_update_service.py`) and use it from both the update service and the download
      gate, so alerts and download blocking cannot disagree.
- [ ] Unit test for the chosen rule.
- **Why first:** every alert kind inherits the gate-state decision; getting it wrong produces false
  "free" alerts.

### P1 — gate-state change detection (no new data source)

- [ ] Emit `new_gate` / `became_free` events from `_build_record_from_remote`; add the non-persisted
      `events` field; surface in the refresh response.
- [ ] Keep `has_update` semantics unchanged (regression risk to `hide_paid_updates`,
      `hide_early_access_updates`).
- [ ] UI: "Free now" badge + one batched toast per refresh; extend paid/EA tooltips.
- [ ] Tests in `tests/services/test_model_update_service.py` for each transition and for the
      no-change case.
- **Acceptance:** a version whose gate lapses is visibly marked free after a refresh, with no new
  network calls; existing hide-* filters behave identically.

### P2 — price capture (opt-in)

- [ ] Schema + all eight column touchpoints from §4.1, with a migration test.
- [ ] `parse_model_page_prices` + fixture-based tests (`tests/services/fixtures/…`, one trimmed page
      with a timed gate, one with a permanent gate, one malformed/missing payload).
- [ ] `CivitaiClient.get_model_prices` + provider methods + composite pass-through; assert redirect
      following and that a non-JSON body is returned as text.
- [ ] Wire into `_refresh_single_model` behind `price_tracking_enabled`, with the failure matrix from
      §4.3.
- [ ] Tests: feature off ⇒ zero extra calls; fetch failure ⇒ previous price retained and
      `price_checked_at` unchanged; gated-only candidate selection.
- **Acceptance:** with tracking enabled, a refresh on a gated model stores `price_buzz` for all of
  its versions from one request; with tracking disabled or offline, refresh behaves exactly as today.

### P3 — threshold alerts and surface

- [ ] Settings + defaults (§4.5) and the settings-modal toggles/inputs.
- [ ] Threshold evaluation + `price_alert_state` edges → `price_drop` events.
- [ ] `GET /api/lm/models/price-alerts` aggregate endpoint.
- [ ] Version payload gains the price fields; UI price chip, "Free now" badge, "price drops only"
      filter; optional price in the paid-download error.
- [ ] Locale keys + `scripts/sync_translation_keys.py`.
- [ ] Tests: threshold boundary (`<=` vs `<`), Blue Buzz labelling, sale-adjusted vs list price,
      alerts for a version already in the library.
- **Acceptance:** a user can set "alert me under 500 buzz", refresh, and see the models that
  qualify; nothing alerts when the price rises above the threshold again (state resets).

### P4 — docs and upstream

- [ ] Short feature note in the repo docs; keep this plan's data-source rationale in a code comment
      (public page read, no auth or origin spoofing, no internal API).
- [ ] Draft the upstream request: add a price field to the public `paidAccess` DTO. Point out the
      asymmetry — writes already go through the official v1 endpoint
      (`~/code/civitai/src/pages/api/v1/model-versions/early-access.ts`, sharing
      `updateModelVersionPaidAccessSchema`) while reads withhold it deliberately. If it lands, the
      page scraper becomes an optional fallback rather than the only path.

## 6. Test plan summary

* `pytest tests/services/test_model_update_service.py` — migrations, extraction, transitions,
  threshold logic, fetch-failure matrix, feature-off path.
* New parser tests with HTML fixtures (no network in tests).
* `npm run test:js` for badge/helper changes in `ModelVersionsTab`.
* Manual UI verification by the user (per repo policy — no browser automation for layout).
* No live CivitAI calls in the test suite.

## 7. Risks and mitigations

| Risk | Mitigation |
| --- | --- |
| Page payload format changes (Next.js is migrating away from `__NEXT_DATA__` to the flight payload) | Parser is a single pure function behind a provider method; fixture test fails loudly at build time; parse failure is non-fatal and keeps the last known price |
| Cloudflare / UA sensitivity (verified: `civitai.com`, `civitai.red` and even no-UA all returned the payload for the sampled pages) | Reuse `downloader` (proxy, rate-limit coordinator, connectivity guard); detect challenge/absence and back off; never retry in a tight loop |
| Traffic/size (~200-270 KB per model) | Gated models only (~2%), one request per model, `price_check_ttl_hours`, force-refresh only on user action |
| False "free" alerts from gate-semantics ambiguity | P0 helper + explicit tests before any alert ships |
| Misleading price (list vs sale-adjusted; Blue Buzz is the same number but non-withdrawable) | Store both list and effective price; tooltip states the unit and Blue Buzz acceptance |
| Alerts are pull-only (no scheduler, no push channel today) | State it in the UI copy; treat background push as a separate follow-up, not a silent gap |

## 8. Out of scope / follow-ups

* Purchasing or downloading gated content.
* Generation-fee tracking beyond displaying `generation_price_buzz` (the public `mini/{id}` `fees`
  field could feed a richer view later).
* A background/notification channel; today alerts appear when the user refreshes or opens the panel.
* Waiting on CivitAI to expose prices; P1–P3 stand alone.

## 9. Open questions

1. `{permanent:false, endsAt:null}` — gate or not? (P0; affects download blocking too.)
2. Should the threshold apply to versions already in the library (watching for a future re-buy) or
   only to versions the user does not own?
3. Is a per-model threshold override needed in v1, or is one global threshold enough?

---

## 10. What shipped (P0–P3)

### 10.1 Answers to the open questions

1. **`{permanent:false, endsAt:null}` is a gate.** Decided by evidence, not preference: the public v1
   API returns `null` for lapsed gates (`toPublicPaidAccessDto` filters on `isPaidAccessActive`), so a
   non-null DTO is always an *active* gate; on the live model 1802980 that version reports
   `canDownload: false` while its lapsed-tombstone siblings report `true`. The previous rule dropped
   it, which is exactly the #1060 class of bug.
2. The global threshold applies to **every** gated version the update service tracks, in library or
   not — the user may be watching a version they intend to buy later.
3. One global threshold in v1; a per-model override is still open.

### 10.2 Files and seams

| Area | Where |
| --- | --- |
| Shared gate semantics (`normalize_paid_access`, `is_gate_active`, `is_early_access_deadline_active`) | `py/utils/paid_access.py` (new) |
| Model page price parser (`parse_model_page_prices`) | `py/utils/civitai_page_prices.py` (new) |
| Price fetch | `CivitaiClient.get_model_prices` (`py/services/civitai_client.py`) |
| Provider seam | `ModelMetadataProvider.get_model_prices` default None; CivitAI impl; fallback + rate-limit wrappers (`py/services/model_metadata_provider.py`) |
| Columns, migration, transition + threshold logic, alerts query | `py/services/model_update_service.py` |
| Version payload, refresh `events`, `GET /api/lm/{type}/updates/price-alerts` | `py/routes/handlers/model_handlers.py`, `py/routes/model_route_registrar.py` |
| Badges, price chip, gate/price toast | `static/js/components/shared/ModelVersionsTab.js`, `static/js/utils/updateCheckHelpers.js`, `static/css/components/lora-modal/versions.css` |
| Settings | defaults in `py/services/settings_manager.py`; UI in `templates/components/modals/settings/library.html` + `static/js/managers/SettingsManager.js`; client defaults in `static/js/state/index.js` |
| API client | `getPriceAlerts` in `static/js/api/baseModelApi.js` + `priceAlerts` endpoint in `static/js/api/apiConfig.js` |

### 10.3 Deviations from the plan

* **`gate_lapsed_at` column added** (8th column): a transient event would leave a "became free"
  marker invisible minutes later, so the lapse timestamp is persisted and the UI shows a `Free Now`
  badge with it.
* **Alerts are edge-triggered, and first sight is silent.** When a price first appears under the
  threshold, `price_alert_state` is stored and the version shows up in `price-alerts` immediately,
  but no toast fires — otherwise switching the feature on would announce every cheap version in the
  library at once. The toast fires when a price *crosses* down through the threshold.
* **No dedicated alerts panel.** The surfaces are: price chip + `Free Now` badge in the versions tab,
  one combined toast per update check, and the `price-alerts` endpoint (GET, so the companion
  extension can use it). A browse surface over the endpoint is a follow-up.
* **Prices are only fetched for models with a gate** (~2% of a typical library), one page request per
  model, on `price_check_ttl_hours`, and immediately when the gate DTO changes.
* **The paid-download warning message does not include the price**: that path reads the model's
  CivitAI metadata, which has no price, and looking one up would add a request to a failure path.
  Left as a follow-up.

### 10.4 Test coverage added

* `tests/utils/test_paid_access.py` — gate shapes, activity, timestamps.
* `tests/utils/test_civitai_page_prices.py` + `tests/utils/fixtures/civitai_model_page_paid.html` —
  parser, including sale-adjusted vs list price and lapsed tombstones.
* `tests/services/test_model_update_service.py` — migration from a pre-feature DB, column round-trip,
  transitions, price capture on/off, failure retention, TTL, threshold edges, alerts query.
* `tests/services/test_civitai_client.py` — page fetch happy path, unusable payloads, rate limits.
* `tests/routes/test_model_update_handler.py` — alerts endpoint, gate events for non-updating records.


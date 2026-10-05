# Plan: Buzz Price Tracking and Threshold Alerts for Paid / Early Access Versions

**Origin:** FR "Price tracker for models/loras" (Geekier, Discord) — track the buzz price of paid
model versions and flag when it drops below a threshold or becomes free.
**Related:** [#1060 — Some "Early Access" models are not identified correctly](https://github.com/willmiao/ComfyUI-Lora-Manager/issues/1060)
(closed) established `is_paid`, the Paid badge and `hide_paid_updates`; this FR is the next step
after gate *state* — gate *price*.
**Status:** v3 — **P0–P3 implemented** (§10 records what shipped and the deviations); **P5 (alerts
panel) planned** in §11, not implemented. The grid-level "price alert only" filter was dropped by
owner decision, so §11 defines the panel as the only new browsing surface.
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
- [x] Draft the upstream request: add a price field to the public `paidAccess` DTO (§13). Point out the
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

---

## 11. P5 — Price alerts panel

**Goal:** a single surface that answers "what got cheaper / became free, and can I act on it".

**Status:** **P5a implemented** (see §11.9); P5b (inline threshold editing, *Refresh prices*, type
chips, ignore action) and P5c (polish) are not.

**Naming:** called P4a–c in earlier discussion; renumbered to **P5** because §5 already uses P4 for
"docs and upstream".

**Owner decision:** the grid-level "price alert only" filter is **out of scope**. The panel is the
only new browsing surface; the existing per-version badges and the update-check toast stay as they
are. Consequence: the panel carries the "act on it" affordances itself (§11.2), and discoverability
rests on the bell badge plus the controls-dropdown entry (§11.1 D8).

### 11.1 Locked decisions

| # | Decision | Why / evidence |
| --- | --- | --- |
| D1 | Host it as a **third tab in the existing notification bell modal**, driven by `UpdateService` | `templates/components/modals.html` is included by `templates/base.html:75`, so the bell exists on every page; `UpdateService` already has `toggleUpdateModal()`, `switchNotificationTab()`, tab badges, arrow-key tab navigation and a list/empty-state pattern (`renderRecentBanners`) |
| D2 | One **global** endpoint `GET /api/lm/price-alerts`, registered **once** in `MiscRoutes` | The update DB is one file per library shared by all model types (`cache/model_update/<library>.sqlite`), and `ServiceRegistry.get_model_update_service()` returns one shared instance (`py/services/service_registry.py:153`). `get_price_alerts` only filters on `s.model_type`, so `model_type=None` is all types in one query. Adding it to `COMMON_ROUTE_DEFINITIONS` would bind the same path once per model type (4×) |
| D3 | **Compare the threshold at read time** (`WHERE v.price_buzz <= ?`); keep `price_alert_state` for the toast edge only | As shipped, panel membership only changes after a refresh, so editing the threshold in the panel would look broken |
| D4 | New column `price_alert_since REAL` | `price_alert_state` is a boolean; "dropped 3 days ago" and an unread count both need the moment the state flipped, which the existing edge detection already knows |
| D5 | Unread state is **client-side** (`localStorage` watermark compared against `price_alert_since`) | No per-user read-state table and no sync logic; the worst case is a conservative badge on a second browser |
| D6 | Row actions: **CivitAI** always; **Open** only when the payload resolved a local file path | `showModelModal(model, modelType)` needs a local metadata object and re-fetches by `file_path` (`static/js/components/shared/ModelModal.js:343-361`); a gated version the user does not own has no local file |
| D7 | **Refresh prices** must bypass the price TTL | Prices stay fresh for `price_check_ttl_hours` (24 h by default), so without a force flag the button would appear to do nothing |
| D8 | **Two non-permanent entry points**, both opening the bell on the Price alerts tab: the **updates dropdown** in the controls bar, and the **global context menu** (right-click on empty space) | The controls dropdown already hosts `checkUpdatesMenuItem` (`templates/components/controls.html:114-126`) and costs no layout space. The global menu is the established home for library-wide occasional actions and already holds the sibling `check-model-updates` (`templates/components/context_menu.html:185`); it has only 7 items and existing hide/separator machinery (`GlobalContextMenu.showMenu` / `_updateSeparatorVisibility`). The **model-card menu is deliberately left alone** — it already has 20 items, and P5b's *Refresh prices* covers the per-model case |
| D9 | Bell badge shows the **unread alert count**; when there are none it keeps today's behaviour (dot for app updates). The same cached count is appended to the global context menu item (`Price alerts (3)`) | Otherwise a price drop is invisible until the user opens the bell. The count is fetched once on init **only when `price_tracking_enabled`**, so users who never enable the feature pay nothing |
| D10 | The global context menu item is **always visible** on model pages (hidden on recipes, like its siblings) | The panel's disabled state is the explanation plus a deep link into Settings; hiding the entry would make the feature undiscoverable for exactly the users who have not enabled it yet |

### 11.2 Information architecture

```
┌ Price alerts                                        [Refresh prices] ┐
│ Threshold: 500 Buzz  (click to edit)                                 │
│ [ Under threshold ] [ Became free ]        Type: All · LoRA · …      │
├──────────────────────────────────────────────────────────────────────┤
│ ▸ Glorious Art · Checkpoint · 2 versions                             │
│     Alpha · 250 Buzz  (was 500) · Blue Buzz OK                       │
│     EA until Oct 10 · Not in library · dropped 3 days ago            │
│     [CivitAI]  [Open]  [Ignore]                                      │
│ ▸ Eira Kishida · LoRA · 1 version                                    │
│     125 Buzz · In library · dropped today        [CivitAI] [Open]    │
└──────────────────────────────────────────────────────────────────────┘
```

* Segments cover both halves of the FR: `Under threshold` (price at or below the threshold) and
  `Became free` (versions with `gate_lapsed_at`, no price).
* Grouped by model (a model often has several versions at the same price), sorted cheapest first
  then most recently crossed; the type chips filter client-side over the loaded list.
* Row: effective price with the list price struck through when on sale, Blue Buzz note, EA end date,
  in-library marker, and "dropped X ago" from `price_alert_since`.
* Actions: open on CivitAI, open the local model modal (only when a file path was resolved), ignore
  this version (reuses `setVersionUpdateIgnore`).

### 11.3 Data contract

```
GET /api/lm/price-alerts?limit=200
{
  "success": true,
  "enabled": true,                  // price_tracking_enabled
  "thresholdBuzz": 500,
  "newestCheckedAt": 1791039694.5,  // staleness copy ("prices last checked X ago")
  "alerts": [
    {
      "modelId": 2981320, "modelType": "checkpoint",
      "modelName": "Glorious Art",          // best-effort, from the scanner cache
      "versionId": 3379626, "versionName": "Alpha",
      "kind": "below_threshold",            // or "became_free"
      "priceBuzz": 250, "listPriceBuzz": 500,
      "acceptsBlueBuzz": true, "priceSaleEndsAt": null,
      "priceAlertSince": 1791000000.0,
      "gateLapsedAt": null,
      "earlyAccessEndsAt": null, "isPaid": true, "isEarlyAccess": false,
      "isInLibrary": false,
      "filePath": null,                     // set only when resolvable
      "civitaiUrl": "https://civitai.com/models/2981320?modelVersionId=3379626"
    }
  ]
}
```

One list with a `kind` discriminator (not two lists) so "All" needs no second request. `civitaiUrl`
is built server-side with the existing `build_civitai_model_page_url` so `civitai_host` stays the
single source of truth.

### 11.4 States (all three must be designed, not just the happy path)

1. **Tracking off** — explain that CivitAI publishes no price in its public API and that the feature
   reads the model page, plus a button that opens Settings → Library.
2. **On, nothing matching** — "nothing under N Buzz right now", with the threshold editable inline.
3. **Stale / offline / rate-limited** — keep the last known list, add a "prices last checked X ago"
   line and a retry; never blank the panel.

### 11.5 Tasks

**P5a — panel usable end to end**

1. `py/services/model_update_service.py`
   * `get_price_alerts(model_type=None, *, threshold_buzz, limit=200)` — optional type filter, live
     threshold comparison, `kind`, `price_alert_since`; keep the shipped per-type call site working.
   * `price_alert_since` column through all eight enumerations (§4.1), set on the `0 → 1` edge and
     cleared on `1 → 0` inside `_build_record_from_remote`.
2. `py/routes/misc_route_registrar.py` + `py/routes/handlers/misc_handlers.py` — register
   `GET /api/lm/price-alerts` **once**, using `ServiceRegistry.get_model_update_service()` and the
   settings service; resolve `modelName` / `filePath` best-effort per model type from the scanner
   caches (`version_index[version_id]` → `file_path`, `file_name`; item `model_name` with a
   `file_name` fallback), and omit them when resolution fails.
3. `templates/components/modals/update_modal.html` — third tab + panel skeleton (segments, threshold
   row, list container, empty/disabled blocks), reusing `data-notification-tab` /
   `data-notification-panel`.
4. `static/js/managers/UpdateService.js` — `renderPriceAlerts()`, panel fetch on open, tab badge
   count, threshold display, row rendering and actions, `localStorage` watermark; extend
   `updateTabBadges()` and `switchNotificationTab()`.
5. `static/js/api/apiConfig.js` + a small fetch helper — the endpoint is global, so it does not
   belong in the per-model-type `endpoints` map.
6. `templates/components/controls.html` + `static/js/components/controls/PageControls.js` — the
   controls-dropdown item (D8).
7. `templates/components/context_menu.html` + `static/js/components/ContextMenu/GlobalContextMenu.js`
   — the global-context-menu item (D8): one template entry, the recipes-page hide list in
   `showMenu()`, one `case` in `handleMenuAction`, and the optional `(N)` count from the cached
   alert count. Both entries call one shared `openPriceAlertsPanel()` helper.
8. `locales/en.json` + `python scripts/sync_translation_keys.py`.

*Acceptance:* with tracking on and one refresh done, the bell shows a count, the tab lists the
versions with prices, CivitAI opens the right page, Open appears only for in-library models and opens
the modal, all three states render, and it works from every page type.

**P5b — actions and polish**

* Inline threshold editing (read-time comparison makes it instant) and **Refresh prices** with a
  `force_price_refresh` flag on the existing refresh endpoint (or a dedicated
  `POST /api/lm/price-alerts/refresh`).
* Type chips and a "only versions I do not own" toggle (this is open question 2 from §9).
* Ignore-this-version action.

**P5c — optional**

* Thumbnails from the scanner cache, "unread only", focus-management pass on the new tab, and a
  deep link from the panel into the settings section.

### 11.6 Tests

* `tests/services/test_model_update_service.py` — `model_type=None` spans types; live threshold
  parameter; `price_alert_since` set/cleared on the edge.
* `tests/routes/` — the global route is registered exactly once and returns the documented shape;
  `filePath` resolution is best-effort (mock scanner; omit on failure).
* `tests/frontend/` — vitest for `renderPriceAlerts` covering rows, both segments, the three states
  and the badge count with a mocked fetch.
* Manual eyeball for layout, per the repo's UI verification policy.

### 11.7 Risks

| Risk | Mitigation |
| --- | --- |
| The bell modal is nominally about app updates; a third tab changes its character | Clear labelling, and only count/badge when the feature is on; the app-update dot behaviour is unchanged when there are no alerts |
| Resolving local file paths pulls scanner caches into an app-wide route | Best-effort with `try/except`, one `get_cached_data()` per type (in-memory), omit the field and hide the Open button when it fails |
| `price_alert_since` is another migration | Same eight-touchpoint discipline as §4.1, covered by the existing migration test |
| A global route in `COMMON_ROUTE_DEFINITIONS` would bind 4× | Register it in `MiscRoutes` instead (D2) |
| Menu bloat / entry sprawl | Two entries maximum (D8), both calling one helper; the 20-item model-card menu is explicitly untouched |
| Panel data goes stale between refreshes | Show `newestCheckedAt`; the refresh action (P5b) makes it explicit rather than silent |

### 11.8 Open questions for the owner

1. **Badge policy** — count unread alerts on the bell (recommended, D9), or leave the bell alone and
   put the number only on the tab?
2. **Unread at all** — the `localStorage` watermark (recommended, D5), or simply "current matches"
   with no read state?
3. **Threshold editing inside the panel** — convenient, but it silently changes a global setting from
   a surface the user opened just to look.
4. **"Open in library"** — worth the scanner-cache coupling (D6), or should the row offer only
   "CivitAI" plus a copy-link action?
5. **Thumbnails** — skip for weight (recommended) or show them?
6. **Entry visibility when tracking is off** — always show the global-context-menu item
   (recommended, D10: the panel's disabled state educates and deep-links to Settings), or hide it
   until the feature is enabled for a cleaner menu?
7. **Count in the menu label** — `Price alerts (3)` using the cached count (recommended, D9), or a
   plain label with the number only on the bell/tab?

### 11.9 What shipped (P5a)

Answers to §11.8: badge counts unread alerts (D9), unread uses the `localStorage` watermark (D5),
threshold editing is **display-only in P5a** (editing is P5b), "Open in library" ships with the
best-effort path resolution (D6), no thumbnails, the context-menu item is always visible (D10), and
the menu label carries the count (D9).

| Area | Where |
| --- | --- |
| `price_alert_since` column through all eight enumerations, set on the `0 → 1` edge, preserved while the alert stands, cleared when the price rises | `py/services/model_update_service.py` |
| `get_price_alerts(model_type=None, *, threshold_buzz, limit)` — read-time threshold, `kind`, one list across types; `newest_price_checked_at()` | `py/services/model_update_service.py` |
| Global endpoint `GET /api/lm/price-alerts`, registered once | `py/routes/misc_route_registrar.py`, `py/routes/misc_routes.py`, `PriceAlertsHandler` in `py/routes/handlers/misc_handlers.py` |
| Third bell tab, panel skeleton, segments, three states | `templates/components/modals/update_modal.html`, `static/css/components/modal/update-modal.css` |
| Loader, renderer, unread watermark, badge, `openPriceAlertsPanel()` | `static/js/managers/UpdateService.js` |
| Entry points (controls dropdown + global context menu, count in the label) | `templates/components/controls.html`, `static/js/components/controls/PageControls.js`, `templates/components/context_menu.html`, `static/js/components/ContextMenu/GlobalContextMenu.js` |

Deviations and decisions made while implementing:

* **`became_free` is reported even while price tracking is off.** It needs no price data, so the
  panel shows the "tracking is off" explanation *and* whatever became free instead of hiding the
  half of the feature that already works.
* **`price_alert_since` is also set on first sight** of an already-cheap version. The toast stays
  silent (edge-triggered, §10.3), but the count is non-zero, which is what invites the user into the
  panel after enabling the feature.
* **The per-type frontend client method was removed** (`baseModelApi.getPriceAlerts` and the
  `priceAlerts` entry in `apiConfig.js`): with the global endpoint it was dead code. The per-type
  **backend** route stays for the companion extension and a possible future grid filter.
* **`openPriceAlertsTab()` exists because `toggleUpdateModal()` closes an open bell** — an entry
  point calling it unconditionally would dismiss the modal instead of switching tabs.
* **Local context uses the existing indexes** (`cache.model_id_index` for `model_name`,
  `cache.version_index` for `file_path`/`file_name`), so it is O(1) per row; every failure just
  omits the fields and the row loses its "Open" button.

Verification: `pytest` 3652 passed / 7 skipped, `npm run test:js` 1444 passed, plus a sandboxed
standalone server run that seeded the update DB and confirmed the payload shape, the `kind`
split, the `civitaiUrl`, and that changing `price_alert_threshold_buzz` through `POST /api/lm/settings`
changes panel membership immediately with no refresh.

### 11.10 Known limitation: mature (NSFW) model prices, and the host fallback

End-to-end verification against the live site found that the page fetch was broken for a whole class
of users: **the hosts are not interchangeable**, and the user's `civitai_host` preference was
silently fatal.

Measured with the app's own HTTP stack (aiohttp) and with httpx, browser User-Agent in both cases:

| Target | civitai.com | civitai.green | civitai.red |
| --- | --- | --- | --- |
| Anonymously visible model page | 200, prices parse | 200, prices parse (same bytes as .com) | **403 Cloudflare challenge** |
| Mature (NSFW) model page | 404 | 404 | **403 Cloudflare challenge** |

* `civitai.red` refuses non-browser clients outright — User-Agent, `Accept-Language`, `Sec-Fetch-*`
  and switching HTTP library all make no difference. (An earlier manual check with `curl` passed by
  luck of TLS fingerprint, which is why this was missed: it was a false positive.)
* A real user on `civitai_host=civitai.red` therefore captured **zero** prices
  (`price_checked_at = 0` in their update DB) even with tracking enabled.
* Mature models are hidden from anonymous visitors on `.com`/`.green` and only served by `.red`, so
  **no host can currently read their price.** The public API cannot help: it trims `paidAccess` to
  `{permanent, endsAt}` by design, and the public `mini/{id}` endpoint exposes only per-generation
  `fees`.

What P5a now does about it:

* **Host fallback** (`CivitaiClient.get_model_prices`): the configured host is tried first, then the
  others (`civitai_page_host_candidates`), first parseable payload wins. The host that worked is
  remembered, and a host that refuses outright (403) is parked for 15 minutes — a host-wide failure
  must not cost three requests per mature model in the library. A 404 is model-specific and does
  **not** park the host.
* **Honest "unavailable" state**: `price_check_attempted_at` separates "we tried and could not read
  a price" from "we never looked". Gated versions in that state show a muted `Price unavailable`
  badge in the versions tab, and the panel reports `unavailableCount`.
* **Diagnostics**: a host refusal is warned once per host per TTL, and a model with no price source
  logs the per-host reasons (404 vs challenge) instead of failing silently at debug level.

Recorded options for mature models, deliberately **not** implemented:

1. **Internal tRPC with the user's API key** (`modelVersion.getById` on `.red`): the route is a
   `publicProcedure` with `requiredScope: ModelsRead`, and `isBearerAuth` satisfies
   `acceptableOrigin`, so the user's own key would work and `.red`'s `/api` paths are not challenged.
   Rejected as the default because the endpoint is undocumented and its own 401 message says to use
   the public API. If ever wanted, it belongs behind an off-by-default setting.
2. **Extension-assisted fetch**: `lm-civitai-extension` runs inside the user's browser, so it has
   both the Cloudflare clearance and the login session needed to read mature pages. This is the only
   route that would work without an undocumented API, but it is a cross-component design of its own.

**Strengthened upstream ask:** the public API should expose the price. The argument is no longer
"convenience" — the page route is demonstrably unreliable (one host challenges non-browser clients,
the other two hide mature models from anonymous visitors), so a supported field is the only way for
any third-party tool to show prices for the models where creators monetize most.

### 11.11 Price capture is independent of the metadata TTL

Found in a real instance: after enabling price tracking, a normal "Check updates" captured exactly
**one** price out of 718 models. The price capture only ran when the *version list* was re-fetched
(`refresh_succeeded`), so it inherited the metadata TTL: with 24 h metadata and 24 h price TTLs, only
the 6 models whose metadata happened to be stale were ever priced.

The cached record already carries the gate, so the price pass now runs off whichever version list is
available — freshly fetched or stored — and applies the result without touching `last_checked_at`, so
a price-only pass cannot silently extend the metadata TTL. Two related semantics:

* A **failed** attempt (`price_check_attempted_at`) satisfies the price TTL, so a mature model whose
  page no host will serve is not retried on every single update check.
* An explicitly **forced** check re-prices within the TTL (`_should_fetch_prices(..., force=True)`).

Verified by copying a real instance's update DB into a sandbox and running a non-forced check:
`bulk metadata fetches: 0` (version lists came entirely from cache) while priced versions went
**1 → 20** and the panel listed 19 alerts.

### 11.12 The empty state has to explain a 0 Buzz threshold

The default threshold is 0 ("only tell me when a version becomes free"), and the settings copy says
so. The panel did not: a real instance with **52 priced paid versions** and an untouched threshold
showed "Nothing is under your price threshold right now" plus a small "Alert threshold: 0 Buzz" in
the corner, which reads as "the feature is broken".

The empty state is now threshold-aware, using a new `pricedCount` in the payload: when the threshold
is 0 and prices are known, it says how many paid versions have a price and where to set a threshold.
The read-time threshold comparison means changing it takes effect immediately — no re-check needed
(measured on a copy of that instance's DB: 0 Buzz -> 0 alerts, 100 -> 44, 500 -> 48, 5000 -> 51).

## 12. Redesign (locked): obtainability of versions you do not own

### 12.1 Why the P5a model was wrong

The owner could not tell, from the UI alone, what "Buzz Price Tracking" enables, what the
"Price alert threshold" number means, or what "Price Alerts" is alerting about. That is not a copy
problem: the implementation exposed **our mechanism** (a page scrape) and **our SQL predicates**
(`price_buzz <= ?`, `gate_lapsed_at IS NOT NULL`) as the user's concepts. Two concrete defects came
out of the same root:

* **The alert population included versions the user already owns.** Neither the event generator nor
  the panel query filtered on `is_in_library` (the payload even carried `isInLibrary`). In the
  owner's library **28 of 52 gated versions were already downloaded** — more than half of the
  "alerts" were about things already on disk. A version you own cannot become cheaper *for you*.
* **A filtered list in a notification surface.** "Price Alerts" was a state list whose contents were
  entirely decided by a number stored in Settings, so an empty panel had three indistinguishable
  causes (tracking off / threshold 0 / genuinely nothing), and it read as a broken feature.

Two measurements shaped the correction:

* **Permanent prices dominate** (87 permanent vs 3 timed gates in a 600-model sample), so "wait for a
  price drop" is a low-frequency proposition, while "wait for early access to end" is high-frequency
  and deterministic.
* **Prices cluster at the floor** (44 of the owner's 52 priced versions are 100 Buzz), so
  "price <= N" carries little information; the real distinction is *free / soon free / paid*.

Also corrected during the discussion: the **generation fee** is the cost of generating *on the
CivitAI site*. A locally downloaded model generated in ComfyUI has no such fee, so for this tool it
is not a price axis at all (42 of the owner's 52 gated versions carry one — displaying it would
mislead on 80% of paid rows). It is not displayed today and must stay that way.

### 12.2 The corrected information model

The unit is the **version**, and the boundary is **ownership**: information exists only where a
decision exists.

| State of a version **not in the library** | The user's decision | What is shown |
| --- | --- | --- |
| Downloadable for free | download or not | nothing special (the download action already says it) |
| Early access, free on D, buyable for N | **wait until D / pay N now** | `N Buzz - free on D` |
| Early access, free on D, not buyable | wait | `free on D` |
| Permanently paid, price known (N) | buy or skip | `N Buzz` |
| Permanently paid, price unknown | buy or skip, price unknown | `Paid` (no number) |
| **In the library** | none | **nothing** |

The numeric threshold has no place in this table: every decision is categorical (wait / pay / skip),
not numeric.

### 12.3 Locked decisions

* **D1 - No independent surface.** Obtainability is an attribute of the existing update surfaces:
  the model card's update badge, the grid's "models with updates" filter, the post-check toast, and
  the model modal's version list. No new bell tab.
* **D2 - No numeric threshold anywhere.** The setting, the comparison, and the tests around it go.
* **D3 - Only versions that are not in the library** produce events or badges (`is_in_library = 0`),
  enforced in both the event generator and any query.
* **D4 - Owned versions show no download price** (and carry no alert state).
* **D5 - The generation fee is never displayed.**
* **D6 - Models outside the library are out of scope.** Their decision moment is the download/browse
  flow; that is a recorded follow-up, not a background feed (the update service only knows local
  models, and there is no follow mechanism to build on).
* **D7 - The plumbing stays**: page fetch, host fallback, attempt markers, both TTLs, storage,
  parser, `gate_lapsed_at`, and the price columns.

### 12.4 What happens to what shipped in P5a

| Piece | Fate |
| --- | --- |
| `GET /api/lm/price-alerts`, `GET /api/lm/{prefix}/updates/price-alerts`, `PriceAlertsHandler` | **removed** - no surface consumes them; events reach the UI through the refresh response |
| `get_price_alerts`, `newest_price_checked_at`, `count_priced_versions`, `count_unavailable_prices` | **removed** (threshold comparison and the panel's counters) |
| `price_alert_threshold_buzz` (settings, `_price_alert_threshold_buzz`) | **removed** |
| `price_alert_since` | **stop writing**; the column stays (SQLite drops need a table rebuild) and is marked deprecated |
| `price_alert_state` | **kept** - it is the one-shot edge for the "became free" toast |
| Bell tab, panel markup, `.price-alerts*` CSS, `UpdateService` panel code, watermark, the two entry points (controls dropdown, global context menu), their locales | **removed** |
| Version badges | **reworked** to the 12.2 table, ownership-scoped |
| "Price unavailable" badge | **replaced** by `Paid` (the gate is known from the public API; only the number is best-effort, and that is our plumbing, not the user's problem) |
| `priceAttemptedAt` in the version payload | **removed** from the payload (kept internally for the price-TTL retry policy) |
| The "became free" toast | **kept**, reworded, ownership-scoped |

### 12.5 Tasks

**P6a - the core correction (no new surface).**
Backend: ownership-scope the event generator; remove the threshold, the alert query, the counters,
the two routes and the handler; stop writing `price_alert_since`. Frontend: rework the version
badges to the 12.2 table; delete the panel, tab, entry points, watermark and their locales; reword
the toast. Tests: replace the panel/alert suites with a badge-state matrix and ownership-scoping
tests; assert the removed routes are gone.

**P6b - obtainability in the update surfaces.**
Per-model obtainability summary in the model list payload (next to `hasUpdate`) so the card badge can
say `Update - 500 Buzz` / `Update - free on Oct 15`; toast copy that counts the free ones
("3 models have updates, 1 is now free").

**P6c - deferred (recorded, not planned).** A price-drop event (rare by measurement); obtainability
in the download/browse flow for models outside the library (D6).

### 12.6 Verification

Unit tests for the state matrix and the ownership filter; a sandbox run against a **copy** of the
owner's real update DB, where the population must shrink from 52 gated versions to the **24 that are
not in the library**, with the owned ones showing nothing.

### 12.7 What shipped (P6a)

* The two alert-state columns are **gone from the schema** (not merely unused): the dataclass,
  `_SCHEMA`, the additive migration table, the primary-key rebuild's column list and defaults, the
  bulk `SELECT`, the row mapping and the `INSERT`. A database created by an unreleased build still
  has them, so `_apply_migrations` drops them with a native `ALTER TABLE ... DROP COLUMN` (SQLite
  3.35+, guarded) and logs it; for everyone else it is a no-op.
* `price_alert_threshold_buzz`, `_price_alert_threshold_buzz`, `_evaluate_price_alert`, the
  threshold-crossing event, `get_price_alerts`, `newest_price_checked_at`,
  `count_priced_versions`, `count_unavailable_prices`, both alert routes, `PriceAlertsHandler`, its
  handler-set slot, its route mapping entry and the service-registry adapter field it needed: all
  removed.
* Gate events (and only gate events) are emitted, and only for versions the user does not have -
  `isInLibrary` is now the filter rather than a field in the payload.
* Version badges follow the 12.2 table: cost information only for versions not in the library, the
  price replaces the redundant `Paid` badge when it is known, `Paid` appears without a number when
  it is not, and `Price unavailable` is gone (the gate is certain; only the number is best-effort).
* The bell tab, panel markup, panel CSS, the controls-dropdown and global-context-menu entries, the
  unread watermark and their locales are removed; the toast keeps its gate transitions and drops the
  price-drop line. The setting is now framed as plumbing ("Show download prices for paid versions")
  and keeps only the enable flag and the refresh interval.

Verified: `pytest` 3653 passed / 7 skipped, `npm run test:js` 1444 passed. Against a copy of the
owner's real database the population is 52 gated versions -> **28 owned (now silent) + 24 that the
feature is actually about**; the drop migration logged twice and left no `price_alert_*` column, and
both removed endpoints return 404.

### 12.8 Correction to P6b: the model card cannot carry a price

P6b proposed annotating the model card's update badge with `Update - 500 Buzz` /
`Update - free on Oct 15`. The owner objected that the badge represents a **model** already in the
library while the update is a set of versions, each with its own price and its own early access end
date. The objection is correct, and the data is blunt about it:

* Live model `958009` has **37 gated versions across 6 price points** (1111, 2220, 4440, 8880,
  88800, 888888); model `153568` has two gated versions at 600 and 4000.
* In the owner's own library, model `647926` has two early access versions with **two different end
  dates**.

So a single price or date on the card would be fabricated, not summarised. It looked plausible only
because that library is uniform (44 of its 52 priced versions sit at the 100 Buzz floor) - an
artefact of floor pricing, not a guarantee.

What is well defined at model level, by construction: counts ("3 updates"), the earliest upcoming
free date (a minimum over the set), a minimum price ("from 100 Buzz", well defined but misleading
when the cheap version is an old one), and uniformity statements only when they are true. "The price
is X" is not among them.

Revised scope: the card badge stays a plain update indicator, and **prices stay in the version list**,
where every row has exactly one subject. The only model-level fact worth considering is the deadline
- "1 of 3 updates becomes free on Oct 15" - because a deadline can change what the user does *before*
opening the model; it is rare in practice (4 unexpired early access versions across 3 models in that
library), so it is optional polish rather than part of the correction.

## 13. Upstream API request

### 13.1 The request as filed (send this)

**Filed:** [civitai/civitai#5384](https://github.com/civitai/civitai/issues/5384) (2026-10-05, as
`willmiao`).

**Title:** `[API Feature Request] Expose Buzz prices for paid / early-access model versions`

**Body:**

> **Ask:** include the Buzz price in the public `paidAccess` DTO - the download price, whether a
> sale is currently discounting it, and whether Blue Buzz is accepted.
>
> **Why:** the API already tells a client *that* a version is gated and *when* early access ends
> (`paidAccess: { permanent, endsAt }`), but not what it costs. In the Buzz economy that is the
> other half of the question users are asking: wait for it to become free, or pay now? A live sale
> or Blue Buzz support is often what decides it.
>
> With the price exposed, an integration like ComfyUI LoRA Manager can show "100 Buzz - free on
> Oct 11" on a version and tell users when a paid version becomes free, instead of sending them to
> the website to check.
>
> Public or authenticated-only - whichever you prefer.

Filing notes: a new issue on `civitai/civitai`, using that repo's `[API Feature Request]` title
convention. No existing issue asks for this (searched `paidAccess`, "download price",
"buzz price API", and every open `[API Feature Request]`).

### 13.2 Internal notes (do NOT paste into the issue)

Kept here because it is what makes the request cheap to grant - but telling a maintainer how to
implement their own service reads as presumptuous, and volunteering how we read prices today is
our business, not theirs. Both were in the first draft and were cut.

* `toPublicPaidAccessDto` (`src/server/services/paid-access.service.ts:649`) already receives a
  `PaidAccessRow` carrying `terms: PaidAccessTerms` and `sales?: ModelVersionSaleWindow[]`
  (`packages/civitai-buzz/src/paid-access.ts:132`) and returns only `{ permanent, endsAt }`.
* `discountedTerms(terms, sales, now)` (line 426) already resolves what a buyer pays during a sale.
* The write path already accepts the same terms: `/api/v1/model-versions/early-access` validates
  `updateModelVersionPaidAccessSchema`, whose `paidAccess.terms` is `modelVersionTermsSchema`.
* So the reads withhold exactly what the writes accept, from a row that already holds it.

Evidence gathered for our own records (also not for the issue):

| Check | Result |
| --- | --- |
| `GET /api/v1/models?ids=646411` | version `1249246` -> `paidAccess: {permanent: true, endsAt: null}`, no price |
| `GET /api/v1/model-versions/1249246` | same, plus `usageControl: "Download"`, `licensingFee: null` |
| Same version on the model page | `downloadPrice 100`, `generationPrice 50`, `acceptsBlueBuzz false` |
| `civitai.red` model pages | Cloudflare challenge (403 for any User-Agent; aiohttp and httpx alike) |
| `civitai.com` / `civitai.green`, mature models | 404 to anonymous visitors, so no readable price source |

### 13.3 Why the request is written that way

* **Lead with the ask and the need; stop.** A maintainer triages on the first lines; the rest is
  only read if the ask survives.
* **No implementation guidance.** They know their service. A "here is your one-line change"
  section invites either irritation or a correction, and it can be wrong: withholding prices may be
  a deliberate product decision (the code comment says pricing belongs to the purchase flow), so the
  request has to argue for the *need*, not the diff.
* **No mention of how we read prices today.** It is an internal approach, it shifts the thread from
  the feature to our behaviour, and it invites a "please don't do that" that has nothing to do with
  the ask.
* **One scope concession, one clause** ("public or authenticated-only"): it removes the most likely
  objection without prescribing anything.
* **One precedent clause** ("you already expose whether a version is gated and when early access
  ends"): it makes the price look like the natural companion of what is already public.
* **One credibility clause** (naming ComfyUI LoRA Manager as a real integration): it separates the
  request from a one-off user wish.
* Target length: ~130 words. Longer drafts read as a specification, which is the failure mode this
  section exists to prevent.

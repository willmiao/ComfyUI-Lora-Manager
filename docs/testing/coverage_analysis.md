# Backend Test Coverage Notes

## Pytest Execution
- Command: `python -m pytest`
- Result: All 283 collected tests passed in the current environment.
- Coverage tooling (``pytest-cov``/``coverage``) is unavailable in the offline sandbox, so line-level metrics could not be generated. The earlier attempt to install ``pytest-cov`` failed because the package index cannot be reached from the container.

## High-Priority Gaps to Address

### 1. Standalone server bootstrapping
* **Source:** [`standalone.py`](../../standalone.py)
* **Why it matters:** The standalone entry point wires together the aiohttp application, static asset routes, model-route registration, and configuration validation. None of these behaviours are covered by automated tests, leaving regressions in bootstrapping logic undetected.
* **Suggested coverage:** Add integration-style tests that instantiate `StandaloneServer`/`StandaloneLoraManager` with temporary settings and assert that routes (HTTP + websocket) are registered, configuration warnings fire for missing paths, and the mock ComfyUI shims behave as expected.

### 2. Model service registration factory
* **Source:** [`py/services/model_service_factory.py`](../../py/services/model_service_factory.py)
* **Why it matters:** The factory coordinates which model services and routes the API exposes, including error handling when unknown model types are requested. No current tests verify registration, memoization of route instances, or the logging path on failures.
* **Suggested coverage:** Unit tests that exercise `register_model_type`, `get_route_instance`, error branches in `get_service_class`/`get_route_class`, and `setup_all_routes` when a route setup raises. Use lightweight fakes to confirm the logger is called and state is cleared via `clear_registrations`.

### 3. Server-side i18n helper
* **Source:** [`py/services/server_i18n.py`](../../py/services/server_i18n.py)
* **Why it matters:** Template rendering relies on the `ServerI18nManager` to load locale JSON, perform key lookups, and format parameters. The fallback logic (dot-notation lookup, English fallbacks, placeholder substitution) is untested, so malformed locale files or regressions in placeholder handling would slip through.
* **Suggested coverage:** Tests that load fixture locale dictionaries, assert `set_locale` fallbacks, verify nested key resolution and placeholder substitution, and ensure missing keys return the original identifier.

## Next Steps
Prioritize creating focused unit tests around these modules, then re-run pytest once coverage tooling is available to confirm the new tests close the identified gaps.

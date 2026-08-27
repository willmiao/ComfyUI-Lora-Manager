---
name: lora-manager-e2e
description: "End-to-end testing and validation for LoRa Manager features. Use ONLY for sandboxed E2E validation of LoRa Manager standalone mode: start the standalone server on a free port with --settings-path, drive the web UI (http://127.0.0.1:{PORT}/loras) via Chrome DevTools MCP, and verify frontend-to-backend integration. NOT for UI behavior checks that unit tests (Vitest/jsdom) can cover. Trigger keywords: E2E, standalone, Chrome DevTools MCP, lora-manager-e2e, sandbox."
---

# LoRa Manager E2E Testing

End-to-end testing of LoRa Manager standalone mode using Chrome DevTools MCP.

## When to Use — and When NOT To

E2E runs are slow and token-heavy. Reach for them only when the question genuinely
spans server + browser (routing, scan persistence, websocket updates, EXIF writes).

- **Default to unit/component tests first**: `npm run test:js` (Vitest/jsdom) covers
  DOM rendering, modal behavior, event handling and API-client calls deterministically
  in seconds. Backend logic goes through `pytest`. A UI-behavior question answered by
  jsdom MUST NOT be escalated to E2E.
- **Use E2E only when** the behavior cannot be observed without a live server and a
  real browser, e.g. template rendering through the aiohttp server, scanner → SQLite
  persistence → API → DOM round-trips, or real EXIF/image writes.
- If you start an E2E and realize a unit test would answer the question, stop and
  switch.

**Browser driver is fixed: Chrome DevTools MCP.** Do not substitute kimi-webbridge —
it operates on the user's real browser (real tabs, real sessions, synthetic
`isTrusted=false` events), which breaks the isolation this skill requires and lacks
the console/network inspection E2E debugging relies on. kimi-webbridge is for
interactive browsing with the user's real login sessions, not for sandboxed E2E.

## Conventions

- **`{PORT}`**: default candidate `8188`, but it is **commonly occupied by a live
  ComfyUI** — always check first (`ss -tlnp | grep ':{PORT}'`) and use a free port
  (e.g. `8199`). Substitute the chosen port everywhere below. Never kill a process
  you did not start for this E2E.
- **`<repo-root>`**: the repository/worktree root; run all commands from there.
- **`<sandbox>`**: a throwaway dir, e.g. `/tmp/opencode/<plan>-e2e`.

## SANDBOX (MANDATORY)

> Every E2E run MUST target a throwaway sandbox, never real user data.

1. **Explicit settings directory**: always launch with `--settings-path <sandbox>/settings`.
   This pins ALL runtime data (`settings.json`, `cache/`, `backups/`, `logs/`, `stats/`,
   `wildcards/`) under the sandbox. **Never** create `<repo-root>/settings.json` — the repo
   folder is usually the real ComfyUI plugin folder and a portable settings file there is
   read by the real instance.
2. **Sandboxed library paths**: point `folder_paths` / `recipes_path` /
   `example_images_path` at disposable dirs under `<sandbox>` — never the real library,
   real recipe dir, or real settings:

   ```json
   {
     "folder_paths": {
       "loras": ["<sandbox>/models/loras"],
       "checkpoints": ["<sandbox>/models/checkpoints"],
       "unet": ["<sandbox>/models/checkpoints"],
       "diffusers": []
     },
     "recipes_path": "<sandbox>/recipes",
     "example_images_path": "<sandbox>/example_images"
   }
   ```

3. **Real-data protection proof**: before starting and after finishing, snapshot the real
   config and recipe library and confirm they are byte-identical; also confirm
   `<repo-root>` gained no `settings.json` or `cache/`:

   ```bash
   sha256sum ~/.config/ComfyUI-LoRA-Manager/settings.json > <sandbox>/settings.before.sha256
   ls ~/models/recipes/*.recipe.json 2>/dev/null | wc -l > <sandbox>/recipes-count.before.txt
   # AFTER the run: record again and diff. Any change = the run leaked into real data.
   ```

## Quick Start

```bash
cd <repo-root>
# 1. Sandbox
mkdir -p <sandbox>/settings <sandbox>/models/{loras,checkpoints} <sandbox>/{recipes,example_images}
#    write <sandbox>/settings/settings.json per the SANDBOX example
# 2. Port
ss -tlnp | grep ':{PORT}' || echo "port {PORT} is free"
# 3. Server — MUST be fully detached (a plain background & dies with the shell);
#    the helper enforces this and manages its own pidfile
python .agents/skills/lora-manager-e2e/scripts/start_server.py \
  --port {PORT} --settings-path <sandbox>/settings --wait --timeout 30 --detach
ss -tlnp | grep ':{PORT}'   # verify listening BEFORE proceeding
# 4. Chrome with remote debugging, then connect Chrome DevTools MCP (verify via list_pages)
google-chrome --remote-debugging-port=9222 --user-data-dir=/tmp/chrome-lora-manager http://127.0.0.1:{PORT}/loras
```

Then drive the UI with the MCP tools (`take_snapshot`, `click`, `fill`, `fill_form`,
`evaluate_script`, `wait_for`, `list_network_requests`, `list_console_messages`) —
see [references/mcp-cheatsheet.md](references/mcp-cheatsheet.md) for patterns.

Server restart after config/fixture changes:

```bash
python .agents/skills/lora-manager-e2e/scripts/start_server.py \
  --port {PORT} --settings-path <sandbox>/settings --restart --wait --detach
# then reload the browser page (ignoreCache=True)
```

`--restart` only kills the E2E server the script itself started (via its pidfile) and
aborts instead of killing unrelated processes on the port.

## Abort Rule

A sandboxed E2E should finish in well under 30 minutes. If any phase exceeds ~2x its
expected duration (server readiness > 60 s, MCP connect > 2 min, a single scenario >
10 min), or any single tool call fails 3+ times in a row, **STOP** — do not retry
blindly. Report `BLOCKED` with the phase, last observed state (server PID,
`ss -tlnp` output, page snapshot, last API response) and suspected cause. A clean
BLOCKED report beats an hour of retries.

## Troubleshooting

- **"browser is already running" / `list_pages` fails**: a stale Chrome holds the
  profile dir. Find it (`ps -ef | grep -i '[c]hrome.*user-data-dir'`), confirm it is a
  leftover QA Chrome (not the live ComfyUI, not your current MCP browser), kill only
  that PID, then retry `list_pages`.
- **MCP refuses to write screenshots into the worktree**: save to `/tmp` via
  `take_screenshot(filePath="/tmp/...")` and copy into the evidence dir from the shell.

## Cleanup

1. Stop the standalone server: `kill <recorded-pid>` (only the PID you started), then
   confirm `ss -tlnp | grep ':{PORT}'` is empty.
2. Close browser pages (keep at least one open).
3. `rm -rf <sandbox>`; verify `<repo-root>` gained no `settings.json` or `cache/`.
4. Re-run the real-data protection check from the SANDBOX section and record the result.

## References & Scripts

- [references/mcp-cheatsheet.md](references/mcp-cheatsheet.md) — Chrome DevTools MCP
  command patterns (navigation, waiting, snapshots, forms, network, console, performance).
- [references/test-scenarios.md](references/test-scenarios.md) — detailed test scenarios
  (list display, metadata editing, recipes, settings, import/export).
- [references/recipe-rematch-fixtures.md](references/recipe-rematch-fixtures.md) —
  fixture format, fresh-state reset and known gaps for recipe rematch/repair E2E runs.
- `scripts/start_server.py` — start/restart the standalone server
  (`--port --settings-path --restart --wait --timeout --detach`); refuses to touch
  unrelated processes on the port.
- `scripts/wait_for_server.py` — poll readiness (`--port --timeout`).

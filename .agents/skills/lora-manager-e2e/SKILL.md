---
name: lora-manager-e2e
description: "End-to-end testing and validation for LoRa Manager features. Use when performing automated E2E validation of LoRa Manager standalone mode in a SANDBOXED, disposable configuration: check the port, start/restart the standalone server on a free port, use Chrome DevTools MCP to interact with the web UI (http://127.0.0.1:{PORT}/loras), and verify frontend-to-backend functionality. Covers workflow validation, UI interaction testing, and integration testing between the standalone Python backend and the browser frontend. Trigger keywords: E2E, standalone, Chrome DevTools MCP, lora-manager-e2e, sandbox."
---

# LoRa Manager E2E Testing

This skill provides workflows and utilities for end-to-end testing of LoRa Manager using Chrome DevTools MCP.

## Conventions Used in This Document

- **`{PORT}`**: The server port. The default candidate is `8188`, but **`8188` is commonly occupied by a live ComfyUI process** and MUST NOT be assumed to be free. Always check availability first (see [Port Selection](#port-selection)) and use a free port (e.g. `8199`) for the E2E run. Substitute the actual port for every `{PORT}` in the commands below.
- **`<repo-root>`**: The repository/worktree root. Always run commands from the repo or worktree root; never assume a specific absolute path (paths such as `/home/<user>/...` differ per machine). The E2E scripts resolve the project root themselves, but fixture/settings paths are relative to `<repo-root>`.

## SANDBOX (MANDATORY)

> **Read this section before running anything.** Every E2E run MUST target a throwaway sandbox, never the real user data. A fresh subagent that skips this section WILL permanently mutate real user recipes.

1. **Portable settings**: create `<repo-root>/settings.json` (gitignored) with `"use_portable_settings": true` plus sandboxed `folder_paths` (lora/checkpoint roots) and `recipes_path`. This keeps the configuration inside the repo instead of the real user config dir (`~/.config/ComfyUI-LoRA-Manager/settings.json`).
2. **Sandboxed paths**: point `folder_paths` / `recipes_path` / `example_images_path` at disposable dirs — e.g. under `/tmp/opencode/<plan-name>-e2e/` (or worktree-local dirs). NEVER point the E2E at the real library (`~/models/...`), real recipe dir, or real settings.
3. **Never touch the real config**: the real user config at `~/.config/ComfyUI-LoRA-Manager/settings.json` and the real recipe dir must remain byte-identical before and after the run.
4. **Record real-data protection proof** before starting and after finishing:
   ```bash
   # BEFORE: snapshot real config + recipe library state
   sha256sum ~/.config/ComfyUI-LoRA-Manager/settings.json > /tmp/opencode/<plan>-e2e/settings.before.sha256
   ls ~/models/recipes/*.recipe.json 2>/dev/null | wc -l > /tmp/opencode/<plan>-e2e/recipes-count.before.txt
   find ~/models/recipes -name '*.recipe.json' -newermt "$(date -Iseconds)" | head   # expect empty after run
   # AFTER: record again, then diff the two snapshots. Any change = the run leaked into real data.
   ```
   Also confirm `<repo-root>/git status` stays clean for `settings.json`/`cache/` (both are gitignored).

### Portable Settings Example

```json
{
  "use_portable_settings": true,
  "folder_paths": {
    "loras": ["/tmp/opencode/<plan>-e2e/models/loras"],
    "checkpoints": ["/tmp/opencode/<plan>-e2e/models/checkpoints"],
    "unet": ["/tmp/opencode/<plan>-e2e/models/checkpoints"],
    "diffusers": []
  },
  "recipes_path": "/tmp/opencode/<plan>-e2e/recipes",
  "example_images_path": "/tmp/opencode/<plan>-e2e/example_images"
}
```

The scanner computes and persists model hashes during the library scan, so the sandbox model dirs just need the model files + `.metadata.json` sidecars (see [Fixture + Fresh-State Guidance](#fixture--fresh-state-guidance)).

## Time Budgets & Abort Guidance

A fresh subagent should complete a sandboxed standalone E2E **in well under 30 minutes**. Budget each phase:

| Phase | Expected duration | Abort if |
| --- | --- | --- |
| Port check + sandbox setup | < 2 min | — |
| Server start (detached) + readiness | < 30 s | > 60 s (2x) → stop |
| Chrome DevTools MCP connect | < 1 min | > 2 min → stop |
| Per entry-point run (after fixtures ready) | < 5 min | > 10 min (2x) → stop |
| Fixture reset + cache clear between runs | < 1 min | > 2 min → stop |

**Abort rule**: if a phase exceeds ~2x its budget, OR any single tool call fails/retries 3+ times in a row, **STOP**. Do not loop or retry blindly. Report `BLOCKED` with: the phase, the last observed state (server PID + `ss -tlnp` output, page snapshot, last API response), and the suspected cause. Record the partial state as evidence; a clean BLOCKED report is more valuable than an hour of retries.

## Prerequisites

- LoRa Manager project cloned and dependencies installed (`pip install -r requirements.txt`) — run everything from `<repo-root>`
- Chrome browser available for debugging
- Chrome DevTools MCP connected
- `ss` (or `lsof`/`netstat`) available for port checks: `ss -tlnp`

## Port Selection

`8188` is only the *default candidate*. Verify it is actually free before every run:

```bash
# Is anything listening on 8188?
ss -tlnp | grep ':8188' || echo "8188 is free"
```

- If a process holds `8188` (e.g. a live ComfyUI — pid 6575 on this machine), pick a different free port, e.g. `8199`:
  ```bash
  ss -tlnp | grep ':8199' || echo "8199 is free"
  ```
- **Never** kill a process you did not start for this E2E. The live ComfyUI is off-limits. Pick a free port instead.
- Use your chosen port for **all** subsequent commands (server, Chrome launch, browser URLs).

## Quick Start Workflow (sandboxed)

### 1. Prepare the sandbox

```bash
cd <repo-root>                       # ALWAYS run from the repo/worktree root
mkdir -p /tmp/opencode/<plan>-e2e/models/{loras,checkpoints}
mkdir -p /tmp/opencode/<plan>-e2e/{recipes,example_images,recipes-before}
# write <repo-root>/settings.json per the portable-settings example above
# record real-data protection proof (see SANDBOX section)
```

### 2. Check port availability

```bash
ss -tlnp | grep ':{PORT}' || echo "port {PORT} is free"
```

If `{PORT}` is occupied by an unrelated process, pick a free one and use it everywhere below. When in doubt use `8199`.

### 3. Start LoRa Manager Standalone (detached)

The standalone server **dies with the shell unless launched fully detached** — a plain background `&` from the bash tool is killed when the tool call returns. Launch via the helper script:

```bash
python .agents/skills/lora-manager-e2e/scripts/start_server.py --port {PORT} --wait --timeout 30 --detach
```

Or manually (equivalent detached form):

```bash
setsid nohup python standalone.py --port {PORT} --host 127.0.0.1 < /dev/null \
  >> /tmp/opencode/<plan>-e2e/server.log 2>&1 &
echo "started"   # record the printed/pidfile PID for cleanup
```

Verify it is listening **before** proceeding (readiness poll is not a substitute for this):

```bash
ss -tlnp | grep ':{PORT}'
```

Record the server PID for cleanup: the helper script writes it to `/tmp/lora-manager-e2e-server-{PORT}.pid`; a manual `setsid` launch has no pidfile, so capture it explicitly (e.g. from `ss -tlnp`).

### 4. Open Chrome Debug Mode

```bash
# Chrome with remote debugging on port 9222 (note the {PORT} URL)
google-chrome --remote-debugging-port=9222 --user-data-dir=/tmp/chrome-lora-manager http://127.0.0.1:{PORT}/loras
```

### 5. Connect Chrome DevTools MCP

Ensure the MCP server is connected to Chrome at `http://localhost:9222`. Verify with `list_pages` — if it fails with "browser is already running", see [Chrome DevTools MCP Troubleshooting](#chrome-devtools-mcp-troubleshooting).

### 6. Navigate and Interact

Use Chrome DevTools MCP tools to:
- Take snapshots: `take_snapshot`
- Click elements: `click`
- Fill forms: `fill` or `fill_form`
- Evaluate scripts: `evaluate_script`
- Wait for elements: `wait_for`

## Common E2E Test Patterns

### Pattern: Full Page Load Verification

```python
# Navigate to LoRA list page
navigate_page(type="url", url="http://127.0.0.1:{PORT}/loras")

# Wait for page to load
wait_for(text="LoRAs", timeout=10000)

# Take snapshot to verify UI state
snapshot = take_snapshot()
```

### Pattern: Restart Server for Configuration Changes

```python
# Stop current server (if running), start with new configuration.
# --restart only kills the E2E server this script started before (via its pidfile);
# it refuses to blindly kill unrelated processes on the port.
python .agents/skills/lora-manager-e2e/scripts/start_server.py --port {PORT} --restart --wait --detach

# Wait and refresh browser
navigate_page(type="reload", ignoreCache=True)
wait_for(text="LoRAs", timeout=15000)
```

### Pattern: Verify Backend API via Frontend

```python
# Execute script in browser to call backend API
result = evaluate_script(function="""
async () => {
  const response = await fetch('/loras/api/list');
  const data = await response.json();
  return { count: data.length, firstItem: data[0]?.name };
}
""")
```

### Pattern: Form Submission Flow

```python
# Fill a form (e.g., search or filter)
fill_form(elements=[
    {"uid": "search-input", "value": "character"},
])

# Click submit button
click(uid="search-button")

# Wait for results
wait_for(text="Results", timeout=5000)

# Verify results via snapshot
snapshot = take_snapshot()
```

### Pattern: Modal Dialog Interaction

```python
# Open modal (e.g., add LoRA)
click(uid="add-lora-button")

# Wait for modal to appear
wait_for(text="Add LoRA", timeout=3000)

# Fill modal form
fill_form(elements=[
    {"uid": "lora-name", "value": "Test LoRA"},
    {"uid": "lora-path", "value": "/path/to/lora.safetensors"},
])

# Submit
click(uid="modal-submit-button")

# Wait for success message or close
wait_for(text="Success", timeout=5000)
```

## Fixture + Fresh-State Guidance

For rematch/repair E2E runs, seed the **sandboxed** `recipes_path` with hand-written fixture recipes. Rules (validated by the task-8 E2E):

1. **Filename constraint**: each file MUST be named `f"{id}.recipe.json"` **and** the in-JSON `id` field MUST equal the filename. Discovery accepts any `*.recipe.json`, but persistence resolves the path via `get_recipe_json_path` and `_save_recipe_persistently` returns `False` on a mismatch → the fixture would be counted as an error.
   - `recipe-a.recipe.json` → in-JSON `"id": "recipe-a"`
2. **File format**: mirror an existing recipe JSON — top-level `id`, `file_path`, `title`, `loras`, `fingerprint`, `gen_params`; lora entries per the persistence conventions (`hash`, `file_name`, `modelVersionId`, `isDeleted`, ...).
3. **Companion image**: each recipe needs an image (e.g. a `.webp` generated with PIL) referenced by `file_path`, used for EXIF verification (`ExifUtils.append_recipe_metadata` writes a `"Recipe metadata: ..."` marker; a freshly generated `.webp` with no marker is the clean "untouched" control).
4. **autov3 three-state contract**: for L3 (autov3-only, renamed-file) fixtures the local model's `.metadata.json` sidecar MUST have the `autov3` key **ABSENT** (the "unchecked" state), NOT `""` — `""` is the TERMINAL "checked but unavailable" state that L3 deliberately skips. The scanner computes + persists `autov3` from the file header during the normal library scan (`model_scanner.py` `_process_model_file`), so the live L3 match resolves through the local autov3/hash cache; the computed-autov3 branch for unchecked items is covered by the unit suite.
5. **Fixture design for a rematch run** (mirrors the task-8 E2E):
   - `recipe-a`: lora entry `isDeleted=True`, `hash` = 12-char autov3 computed from the local model (`calculate_autov3`, `py/utils/file_utils.py`), whose local model file was RENAMED after the recipe was written so `file_name` differs (proves L3 match without filename).
   - `recipe-b`: parser-convention checkpoint entry (uses `id`, no `modelVersionId`) matching a local checkpoint via L2 — the local checkpoint's `.metadata.json` MUST carry civitai version data with that `id` so `version_index` contains it (L2 cannot match otherwise).
   - `recipe-c`: healthy recipe (no deleted entries) → must remain untouched.

### Fresh state between entry-point runs

Each entry point (global / per-recipe / selection-bulk) must start from the same deleted state. Between runs:

```bash
# 1. Reset fixtures to the before-state snapshot (copy back from recipes-before/)
cp /tmp/opencode/<plan>-e2e/recipes-before/*.recipe.json /tmp/opencode/<plan>-e2e/recipes/
# 2. Clear the recipe/FTS caches so the stale in-memory/library state is gone
rm -f <repo-root>/cache/recipe/*.sqlite
rm -rf <repo-root>/cache/fts/*
# 3. Restart the server (fresh process, fresh scan)
python .agents/skills/lora-manager-e2e/scripts/start_server.py --port {PORT} --restart --wait --timeout 30 --detach
# 4. Re-verify server listening + reload the browser page
```

## Server Lifecycle

- **Detached launch is mandatory**: the standalone server dies with the shell unless launched via `setsid` (or the helper script's `--detach`). Use `setsid nohup python standalone.py --port {PORT} --host 127.0.0.1 ... < /dev/null &`.
- **Verify with `ss -tlnp`** after every (re)start; do not proceed on a blind "server starting" message.
- **Never kill pre-existing processes** — only kill the E2E server PID you started (`start_server.py --restart` kills only PIDs it manages via its pidfile). The live ComfyUI or a stale QA Chrome must never be killed as part of cleanup unless explicitly identified as such (see Chrome troubleshooting).
- **Record your PID for cleanup**: note the PID printed/pidfile, and stop exactly that PID at the end (`kill <PID>`, then confirm with `ss -tlnp` that `{PORT}` is released).

## Chrome DevTools MCP Troubleshooting

### Stale profile lock ("browser is already running" / `list_pages` fails)

A Chrome profile can be held by a stale Chrome from a prior MCP session, which makes `list_pages` fail with "browser is already running":

1. Identify the stale Chrome — it owns the profile dir in `--user-data-dir` (e.g. `~/.config/chrome-dev-profile`). Find its process:
   ```bash
   ps -ef | grep -i '[c]hrome.*user-data-dir'
   ```
2. Confirm it is a QA Chrome from a completed task (its parent is an old MCP/browser process, it is NOT the live ComfyUI server, and it is NOT your current MCP instance).
3. Kill ONLY that stale Chrome:
   ```bash
   kill <stale-chrome-pid>
   ```
   Never kill the live server or unrelated processes.
4. Retry `list_pages`. The current MCP will spawn a fresh browser.

### Screenshot-write restrictions

The chrome-devtools MCP may refuse to write into paths outside its configured workspace roots (e.g. the worktree `.omo/evidence/...` canonicalizing to an unmapped path). Workaround:

```bash
# 1. Save the screenshot to /tmp via the MCP
#    take_screenshot(filePath="/tmp/<plan>-e2e/recipe-b-after.png", format="png")
# 2. Copy it into the evidence dir from the shell
mkdir -p <repo-root>/.omo/evidence/screenshots
cp /tmp/<plan>-e2e/recipe-b-after.png <repo-root>/.omo/evidence/screenshots/
```

## Cancellation Testing (KNOWN GAP)

Testing the rematch-cancel path E2E requires a run long enough to cancel mid-flight. A tiny 3-recipe fixture set completes in **seconds** — too fast to reliably cancel. The cancel path is currently **unit-covered only** (`rematch_all_recipes` cancellation tests); do not block an E2E run on cancel-path verification. If you must attempt it, you would need an artificially large/deferred fixture set to create a cancellable window — treat this as a research task, not part of the standard E2E.

## Available Scripts

### scripts/start_server.py

Starts or restarts the LoRa Manager standalone server for E2E testing.

```bash
python scripts/start_server.py [--port PORT] [--restart] [--wait] [--timeout SECONDS] [--detach]
```

Options:
- `--port`: Server port (default: 8188). The script exits early with a clear message if the port is already in use by an unrelated process.
- `--restart`: Kill the E2E server this script previously managed (tracked via `/tmp/lora-manager-e2e-server-{PORT}.pid`) before starting. If unrelated processes still hold the port after that, the script reports them and aborts instead of killing them.
- `--wait`: Wait for the server to be ready before exiting.
- `--timeout`: Readiness wait timeout in seconds (default: 30).
- `--detach`: Launch the server fully detached (`setsid`-style, survives shell death — REQUIRED for E2E). Default off: a normal background process that dies with the shell.

### scripts/wait_for_server.py

Polls the server until ready or timeout.

```bash
python scripts/wait_for_server.py [--port PORT] [--timeout SECONDS]
```

## Test Scenarios Reference

See [references/test-scenarios.md](references/test-scenarios.md) for detailed test scenarios including:
- LoRA list display and filtering
- Model metadata editing
- Recipe creation and management
- Settings configuration
- Import/export functionality

## Network Request Verification

Use `list_network_requests` and `get_network_request` to verify API calls:

```python
# List recent XHR/fetch requests
requests = list_network_requests(resourceTypes=["xhr", "fetch"])

# Get details of specific request
details = get_network_request(reqid=123)
```

## Console Message Monitoring

```python
# Check for errors or warnings
messages = list_console_messages(types=["error", "warn"])
```

## Performance Testing

```python
# Start performance trace
performance_start_trace(reload=True, autoStop=False)

# Perform actions...

# Stop and analyze
results = performance_stop_trace()
```

## Cleanup

Always ensure proper cleanup after tests:
1. Stop the standalone server: `kill <recorded-pid>` (only the PID you started), then confirm `ss -tlnp | grep ':{PORT}'` is empty.
2. Close browser pages (keep at least one open).
3. Remove the sandbox: `rm -rf /tmp/opencode/<plan>-e2e` and `<repo-root>/settings.json` + `<repo-root>/cache` (both gitignored).
4. Re-run the real-data protection check from the SANDBOX section and record the result in your evidence.

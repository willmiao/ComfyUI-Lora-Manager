---
name: lora-manager-e2e
description: End-to-end testing and validation for LoRa Manager features. Use when performing automated E2E validation of LoRa Manager standalone mode, including starting/restarting the server, using Chrome DevTools MCP to interact with the web UI at http://127.0.0.1:8188/loras, and verifying frontend-to-backend functionality. Covers workflow validation, UI interaction testing, and integration testing between the standalone Python backend and the browser frontend.
---

# LoRa Manager E2E Testing

This skill provides workflows and utilities for end-to-end testing of LoRa Manager using Chrome DevTools MCP.

## Prerequisites

- LoRa Manager project cloned and dependencies installed (`pip install -r requirements.txt`)
- Chrome browser available for debugging
- Chrome DevTools MCP connected

## Quick Start Workflow

### 1. Start LoRa Manager Standalone

```python
# Use the provided script to start the server
python .agents/skills/lora-manager-e2e/scripts/start_server.py --port 8188
```

Or manually:
```bash
cd /home/miao/workspace/ComfyUI/custom_nodes/ComfyUI-Lora-Manager
python standalone.py --port 8188
```

Wait for server ready message before proceeding.

### 2. Open Chrome Debug Mode

```bash
# Chrome with remote debugging on port 9222
google-chrome --remote-debugging-port=9222 --user-data-dir=/tmp/chrome-lora-manager http://127.0.0.1:8188/loras
```

### 3. Connect Chrome DevTools MCP

Ensure the MCP server is connected to Chrome at `http://localhost:9222`.

### 4. Navigate and Interact

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
navigate_page(type="url", url="http://127.0.0.1:8188/loras")

# Wait for page to load
wait_for(text="LoRAs", timeout=10000)

# Take snapshot to verify UI state
snapshot = take_snapshot()
```

### Pattern: Restart Server for Configuration Changes

```python
# Stop current server (if running)
# Start with new configuration
python .agents/skills/lora-manager-e2e/scripts/start_server.py --port 8188 --restart

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

## Available Scripts

### scripts/start_server.py

Starts or restarts the LoRa Manager standalone server.

```bash
python scripts/start_server.py [--port PORT] [--restart] [--wait]
```

Options:
- `--port`: Server port (default: 8188)
- `--restart`: Kill existing server before starting
- `--wait`: Wait for server to be ready before exiting

### scripts/wait_for_server.py

Polls server until ready or timeout.

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
1. Stop the standalone server
2. Close browser pages (keep at least one open)
3. Clear temporary data if needed

# Chrome DevTools MCP Cheatsheet for LoRa Manager

Quick reference for common MCP commands used in LoRa Manager E2E testing.

## Navigation

```python
# Navigate to LoRA list page
navigate_page(type="url", url="http://127.0.0.1:8188/loras")

# Reload page with cache clear
navigate_page(type="reload", ignoreCache=True)

# Go back/forward
navigate_page(type="back")
navigate_page(type="forward")
```

## Waiting

```python
# Wait for text to appear
wait_for(text="LoRAs", timeout=10000)

# Wait for specific element (via evaluate_script)
evaluate_script(function="""
() => {
    return new Promise((resolve) => {
        const check = () => {
            if (document.querySelector('.lora-card')) {
                resolve(true);
            } else {
                setTimeout(check, 100);
            }
        };
        check();
    });
}
""")
```

## Taking Snapshots

```python
# Full page snapshot
snapshot = take_snapshot()

# Verbose snapshot (more details)
snapshot = take_snapshot(verbose=True)

# Save to file
take_snapshot(filePath="test-snapshots/page-load.json")
```

## Element Interaction

```python
# Click element
click(uid="element-uid-from-snapshot")

# Double click
click(uid="element-uid", dblClick=True)

# Fill input
fill(uid="search-input", value="test query")

# Fill multiple inputs
fill_form(elements=[
    {"uid": "input-1", "value": "value 1"},
    {"uid": "input-2", "value": "value 2"},
])

# Hover
hover(uid="lora-card-1")

# Upload file
upload_file(uid="file-input", filePath="/path/to/file.safetensors")
```

## Keyboard Input

```python
# Press key
press_key(key="Enter")
press_key(key="Escape")
press_key(key="Tab")

# Keyboard shortcuts
press_key(key="Control+A")  # Select all
press_key(key="Control+F")  # Find
```

## JavaScript Evaluation

```python
# Simple evaluation
result = evaluate_script(function="() => document.title")

# Async evaluation
result = evaluate_script(function="""
async () => {
    const response = await fetch('/loras/api/list');
    return await response.json();
}
""")

# Check element existence
exists = evaluate_script(function="""
() => document.querySelector('.lora-card') !== null
""")

# Get element count
count = evaluate_script(function="""
() => document.querySelectorAll('.lora-card').length
""")
```

## Network Monitoring

```python
# List all network requests
requests = list_network_requests()

# Filter by resource type
xhr_requests = list_network_requests(resourceTypes=["xhr", "fetch"])

# Get specific request details
details = get_network_request(reqid=123)

# Include preserved requests from previous navigations
all_requests = list_network_requests(includePreservedRequests=True)
```

## Console Monitoring

```python
# List all console messages
messages = list_console_messages()

# Filter by type
errors = list_console_messages(types=["error", "warn"])

# Include preserved messages
all_messages = list_console_messages(includePreservedMessages=True)

# Get specific message
details = get_console_message(msgid=1)
```

## Performance Testing

```python
# Start trace with page reload
performance_start_trace(reload=True, autoStop=False)

# Start trace without reload
performance_start_trace(reload=False, autoStop=True, filePath="trace.json.gz")

# Stop trace
results = performance_stop_trace()

# Stop and save
performance_stop_trace(filePath="trace-results.json.gz")

# Analyze specific insight
insight = performance_analyze_insight(
    insightSetId="results.insightSets[0].id",
    insightName="LCPBreakdown"
)
```

## Page Management

```python
# List open pages
pages = list_pages()

# Select a page
select_page(pageId=0, bringToFront=True)

# Create new page
new_page(url="http://127.0.0.1:8188/loras")

# Close page (keep at least one open!)
close_page(pageId=1)

# Resize page
resize_page(width=1920, height=1080)
```

## Screenshots

```python
# Full page screenshot
take_screenshot(fullPage=True)

# Viewport screenshot
take_screenshot()

# Element screenshot
take_screenshot(uid="lora-card-1")

# Save to file
take_screenshot(filePath="screenshots/page.png", format="png")

# JPEG with quality
take_screenshot(filePath="screenshots/page.jpg", format="jpeg", quality=90)
```

## Dialog Handling

```python
# Accept dialog
handle_dialog(action="accept")

# Accept with text input
handle_dialog(action="accept", promptText="user input")

# Dismiss dialog
handle_dialog(action="dismiss")
```

## Device Emulation

```python
# Mobile viewport
emulate(viewport={"width": 375, "height": 667, "isMobile": True, "hasTouch": True})

# Tablet viewport
emulate(viewport={"width": 768, "height": 1024, "isMobile": True, "hasTouch": True})

# Desktop viewport
emulate(viewport={"width": 1920, "height": 1080})

# Network throttling
emulate(networkConditions="Slow 3G")
emulate(networkConditions="Fast 4G")

# CPU throttling
emulate(cpuThrottlingRate=4)  # 4x slowdown

# Geolocation
emulate(geolocation={"latitude": 37.7749, "longitude": -122.4194})

# User agent
emulate(userAgent="Mozilla/5.0 (Custom)")

# Reset emulation
emulate(viewport=None, networkConditions="No emulation", userAgent=None)
```

## Drag and Drop

```python
# Drag element to another
drag(from_uid="draggable-item", to_uid="drop-zone")
```

## Common LoRa Manager Test Patterns

### Verify LoRA Cards Loaded

```python
navigate_page(type="url", url="http://127.0.0.1:8188/loras")
wait_for(text="LoRAs", timeout=10000)

# Check if cards loaded
result = evaluate_script(function="""
() => {
    const cards = document.querySelectorAll('.lora-card');
    return {
        count: cards.length,
        hasData: cards.length > 0
    };
}
""")
```

### Search and Verify Results

```python
fill(uid="search-input", value="character")
press_key(key="Enter")
wait_for(timeout=2000)  # Wait for debounce

# Check results
result = evaluate_script(function="""
() => {
    const cards = document.querySelectorAll('.lora-card');
    const names = Array.from(cards).map(c => c.dataset.name || c.textContent);
    return { count: cards.length, names };
}
""")
```

### Check API Response

```python
# Trigger API call
evaluate_script(function="""
() => window.loraApiCallPromise = fetch('/loras/api/list').then(r => r.json())
""")

# Wait and get result
import time
time.sleep(1)

result = evaluate_script(function="""
async () => await window.loraApiCallPromise
""")
```

### Monitor Console for Errors

```python
# Before test: clear console (navigate reloads)
navigate_page(type="reload")

# ... perform actions ...

# Check for errors
errors = list_console_messages(types=["error"])
assert len(errors) == 0, f"Console errors: {errors}"
```

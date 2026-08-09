#!/usr/bin/env python3
"""
Example E2E test demonstrating LoRa Manager testing workflow.

This script shows how to:
1. Start the standalone server
2. Use Chrome DevTools MCP to interact with the UI
3. Verify functionality end-to-end

Note: This is a template. Actual execution requires Chrome DevTools MCP.

Port: pick a FREE port for the run — 8188 is commonly occupied by a live
ComfyUI (see the skill's Port Selection section). Set PORT below to e.g. 8199
when 8188 is taken. Always run against a SANDBOXED standalone server.
"""

import subprocess
import sys

# Choose the E2E port. 8188 is only the default candidate; use 8199 (or any
# free port checked with `ss -tlnp`) when 8188 is occupied by a live ComfyUI.
PORT = "8188"


def run_test():
    """Run example E2E test flow."""

    print("=" * 60)
    print("LoRa Manager E2E Test Example")
    print("=" * 60)

    # Step 1: Start server (detached so it survives the shell)
    print("\n[1/5] Starting LoRa Manager standalone server...")
    result = subprocess.run(
        [sys.executable, "start_server.py", "--port", PORT, "--wait", "--timeout", "30", "--detach"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(f"Failed to start server: {result.stderr}")
        return 1
    print("Server ready!")

    # Step 2: Open Chrome (manual step - show command)
    print("\n[2/5] Open Chrome with debug mode:")
    print(
        f"google-chrome --remote-debugging-port=9222 "
        f"--user-data-dir=/tmp/chrome-lora-manager http://127.0.0.1:{PORT}/loras"
    )
    print("(In actual test, this would be automated via MCP)")

    # Step 3: Navigate and verify page load
    print("\n[3/5] Page Load Verification:")
    print(
        f"""
    MCP Commands to execute:
    1. navigate_page(type="url", url="http://127.0.0.1:{PORT}/loras")
    2. wait_for(text="LoRAs", timeout=10000)
    3. snapshot = take_snapshot()
    """
    )

    # Step 4: Test search functionality
    print("\n[4/5] Search Functionality Test:")
    print(
        """
    MCP Commands to execute:
    1. fill(uid="search-input", value="test")
    2. press_key(key="Enter")
    3. wait_for(text="Results", timeout=5000)
    4. result = evaluate_script(function=`
        () => {
            const cards = document.querySelectorAll('.lora-card');
            return { count: cards.length };
        }
        `)
    """
    )

    # Step 5: Verify API
    print("\n[5/5] API Verification:")
    print(
        """
    MCP Commands to execute:
    1. api_result = evaluate_script(function=`
        async () => {
            const response = await fetch('/loras/api/list');
            const data = await response.json();
            return { count: data.length, status: response.status };
        }
        `)
    2. Verify api_result['status'] == 200
    """
    )

    print("\n" + "=" * 60)
    print("Test flow completed!")
    print("=" * 60)

    return 0


def example_restart_flow():
    """Example: Testing configuration change that requires restart."""

    print("\n" + "=" * 60)
    print("Example: Server Restart Flow")
    print("=" * 60)

    print(
        f"""
    Scenario: Change setting and verify after restart

    Steps:
    1. Navigate to settings page
       - navigate_page(type="url", url="http://127.0.0.1:{PORT}/settings")

    2. Change a setting (e.g., theme)
       - fill(uid="theme-select", value="dark")
       - click(uid="save-settings-button")

    3. Restart server
       - subprocess.run([python, "start_server.py", "--port", "{PORT}", "--restart", "--wait", "--detach"])

    4. Refresh browser
       - navigate_page(type="reload", ignoreCache=True)
       - wait_for(text="LoRAs", timeout=15000)

    5. Verify setting persisted
       - navigate_page(type="url", url="http://127.0.0.1:{PORT}/settings")
       - theme = evaluate_script(function="() => document.querySelector('#theme-select').value")
       - assert theme == "dark"
    """
    )


def example_modal_interaction():
    """Example: Testing modal dialog interaction."""

    print("\n" + "=" * 60)
    print("Example: Modal Dialog Interaction")
    print("=" * 60)

    print(
        """
    Scenario: Add new LoRA via modal

    Steps:
    1. Open modal
       - click(uid="add-lora-button")
       - wait_for(text="Add LoRA", timeout=3000)

    2. Fill form
       - fill_form(elements=[
           {"uid": "lora-name", "value": "Test Character"},
           {"uid": "lora-path", "value": "/models/test.safetensors"},
       ])

    3. Submit
       - click(uid="modal-submit-button")

    4. Verify success
       - wait_for(text="Successfully added", timeout=5000)
       - snapshot = take_snapshot()
    """
    )


def example_network_monitoring():
    """Example: Network request monitoring."""

    print("\n" + "=" * 60)
    print("Example: Network Request Monitoring")
    print("=" * 60)

    print(
        f"""
    Scenario: Verify API calls during user interaction

    Steps:
    1. Clear network log (implicit on navigation)
       - navigate_page(type="url", url="http://127.0.0.1:{PORT}/loras")

    2. Perform action that triggers API call
       - fill(uid="search-input", value="character")
       - press_key(key="Enter")

    3. List network requests
       - requests = list_network_requests(resourceTypes=["xhr", "fetch"])

    4. Find search API call
       - search_requests = [r for r in requests if "/api/search" in r.get("url", "")]
       - assert len(search_requests) > 0, "Search API was not called"

    5. Get request details
       - if search_requests:
           details = get_network_request(reqid=search_requests[0]["reqid"])
           - Verify request method, response status, etc.
    """
    )


if __name__ == "__main__":
    print("LoRa Manager E2E Test Examples\n")
    print("This script demonstrates E2E testing patterns.\n")
    print("Note: Actual execution requires Chrome DevTools MCP connection.\n")

    run_test()
    example_restart_flow()
    example_modal_interaction()
    example_network_monitoring()

    print("\n" + "=" * 60)
    print("All examples shown!")
    print("=" * 60)

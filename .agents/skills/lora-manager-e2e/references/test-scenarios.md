# LoRa Manager E2E Test Scenarios

This document provides detailed test scenarios for end-to-end validation of LoRa Manager features.

## Table of Contents

1. [LoRA List Page](#lora-list-page)
2. [Model Details](#model-details)
3. [Recipes](#recipes)
4. [Settings](#settings)
5. [Import/Export](#importexport)

---

## LoRA List Page

### Scenario: Page Load and Display

**Objective**: Verify the LoRA list page loads correctly and displays models.

**Steps**:
1. Navigate to `http://127.0.0.1:8188/loras`
2. Wait for page title "LoRAs" to appear
3. Take snapshot to verify:
   - Header with "LoRAs" title is visible
   - Search/filter controls are present
   - Grid/list view toggle exists
   - LoRA cards are displayed (if models exist)
   - Pagination controls (if applicable)

**Expected Result**: Page loads without errors, UI elements are present.

### Scenario: Search Functionality

**Objective**: Verify search filters LoRA models correctly.

**Steps**:
1. Ensure at least one LoRA exists with known name (e.g., "test-character")
2. Navigate to LoRA list page
3. Enter search term in search box: "test"
4. Press Enter or click search button
5. Wait for results to update

**Expected Result**: Only LoRAs matching search term are displayed.

**Verification Script**:
```python
# After search, verify filtered results
evaluate_script(function="""
() => {
  const cards = document.querySelectorAll('.lora-card');
  const names = Array.from(cards).map(c => c.dataset.name);
  return { count: cards.length, names };
}
""")
```

### Scenario: Filter by Tags

**Objective**: Verify tag filtering works correctly.

**Steps**:
1. Navigate to LoRA list page
2. Click on a tag (e.g., "character", "style")
3. Wait for filtered results

**Expected Result**: Only LoRAs with selected tag are displayed.

### Scenario: View Mode Toggle

**Objective**: Verify grid/list view toggle works.

**Steps**:
1. Navigate to LoRA list page
2. Click list view button
3. Verify list layout
4. Click grid view button
5. Verify grid layout

**Expected Result**: View mode changes correctly, layout updates.

---

## Model Details

### Scenario: Open Model Details

**Objective**: Verify clicking a LoRA opens its details.

**Steps**:
1. Navigate to LoRA list page
2. Click on a LoRA card
3. Wait for details panel/modal to open

**Expected Result**: Details panel shows:
- Model name
- Preview image
- Metadata (trigger words, tags, etc.)
- Action buttons (edit, delete, etc.)

### Scenario: Edit Model Metadata

**Objective**: Verify metadata editing works end-to-end.

**Steps**:
1. Open a LoRA's details
2. Click "Edit" button
3. Modify trigger words field
4. Add/remove tags
5. Save changes
6. Refresh page
7. Reopen the same LoRA

**Expected Result**: Changes persist after refresh.

### Scenario: Delete Model

**Objective**: Verify model deletion works.

**Steps**:
1. Open a LoRA's details
2. Click "Delete" button
3. Confirm deletion in dialog
4. Wait for removal

**Expected Result**: Model removed from list, success message shown.

---

## Recipes

### Scenario: Recipe List Display

**Objective**: Verify recipes page loads and displays recipes.

**Steps**:
1. Navigate to `http://127.0.0.1:8188/recipes`
2. Wait for "Recipes" title
3. Take snapshot

**Expected Result**: Recipe list displayed with cards/items.

### Scenario: Create New Recipe

**Objective**: Verify recipe creation workflow.

**Steps**:
1. Navigate to recipes page
2. Click "New Recipe" button
3. Fill recipe form:
   - Name: "Test Recipe"
   - Description: "E2E test recipe"
   - Add LoRA models
4. Save recipe
5. Verify recipe appears in list

**Expected Result**: New recipe created and displayed.

### Scenario: Apply Recipe

**Objective**: Verify applying a recipe to ComfyUI.

**Steps**:
1. Open a recipe
2. Click "Apply" or "Load in ComfyUI"
3. Verify action completes

**Expected Result**: Recipe applied successfully.

---

## Settings

### Scenario: Settings Page Load

**Objective**: Verify settings page displays correctly.

**Steps**:
1. Navigate to `http://127.0.0.1:8188/settings`
2. Wait for "Settings" title
3. Take snapshot

**Expected Result**: Settings form with various options displayed.

### Scenario: Change Setting and Restart

**Objective**: Verify settings persist after restart.

**Steps**:
1. Navigate to settings page
2. Change a setting (e.g., default view mode)
3. Save settings
4. Restart server: `python scripts/start_server.py --restart --wait`
5. Refresh browser page
6. Navigate to settings

**Expected Result**: Changed setting value persists.

---

## Import/Export

### Scenario: Export Models List

**Objective**: Verify export functionality.

**Steps**:
1. Navigate to LoRA list
2. Click "Export" button
3. Select format (JSON/CSV)
4. Download file

**Expected Result**: File downloaded with correct data.

### Scenario: Import Models

**Objective**: Verify import functionality.

**Steps**:
1. Prepare import file
2. Navigate to import page
3. Upload file
4. Verify import results

**Expected Result**: Models imported successfully, confirmation shown.

---

## API Integration Tests

### Scenario: Verify API Endpoints

**Objective**: Verify backend API responds correctly.

**Test via browser console**:
```javascript
// List LoRAs
fetch('/loras/api/list').then(r => r.json()).then(console.log)

// Get LoRA details
fetch('/loras/api/detail/<id>').then(r => r.json()).then(console.log)

// Search LoRAs
fetch('/loras/api/search?q=test').then(r => r.json()).then(console.log)
```

**Expected Result**: APIs return valid JSON with expected structure.

---

## Console Error Monitoring

During all tests, monitor browser console for errors:

```python
# Check for JavaScript errors
messages = list_console_messages(types=["error"])
assert len(messages) == 0, f"Console errors found: {messages}"
```

## Network Request Verification

Verify key API calls are made:

```python
# List XHR requests
requests = list_network_requests(resourceTypes=["xhr", "fetch"])

# Look for specific endpoints
lora_list_requests = [r for r in requests if "/api/list" in r.get("url", "")]
assert len(lora_list_requests) > 0, "LoRA list API not called"
```

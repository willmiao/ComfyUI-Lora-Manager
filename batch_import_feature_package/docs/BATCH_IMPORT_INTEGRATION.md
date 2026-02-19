# Batch Import Feature - Integration Guide

## Overview

I've created a complete batch import system for your LoRA Manager. Here's what was added and how to integrate it.

## Files Created

### Backend Components

1. **`py/services/recipes/batch_import_service.py`**
   - Core batch processing logic
   - Handles directory and URL imports
   - Concurrent image analysis with configurable limits

2. **`py/routes/handlers/batch_import_handler.py`**
   - HTTP request handlers for batch operations
   - Endpoints: import_from_directory, import_from_urls, get_batch_status

3. **`py/routes/batch_import_route_registrar.py`**
   - Route registration configuration
   - Maps HTTP endpoints to handlers

### Frontend Components

1. **`static/js/managers/BatchImportManager.js`**
   - Client-side batch import operations
   - Tab navigation between directory and URL imports
   - Results display and export functionality

2. **`templates/components/batch_import_modal.html`**
   - Full UI component with modal dialog
   - Directory path and URL input fields
   - Results visualization with stats

### Documentation

1. **`docs/BATCH_IMPORT_GUIDE.md`**
   - Complete user guide for batch import feature
   - API documentation
   - Troubleshooting and examples

## Integration Steps

### Step 1: Register Backend Routes

Find the main route registration file (likely `py/routes/` or in `standalone.py`) and add:

```python
# Import the batch import components
from py.routes.batch_import_route_registrar import (
    register_batch_import_routes,
    BatchImportHandlerSet,
)
from py.routes.handlers.batch_import_handler import BatchImportHandler
from py.services.recipes.batch_import_service import BatchImportService

# Create batch import service
batch_import_service = BatchImportService(
    analysis_service=recipe_analysis_service,  # Your existing analysis service
    persistence_service=recipe_persistence_service,  # Your existing persistence service
)

# Create handler
batch_import_handler = BatchImportHandler(
    batch_import_service=batch_import_service,
    ensure_dependencies_ready=ensure_dependencies_ready,
    recipe_scanner_getter=lambda: recipe_scanner,
    civitai_client_getter=lambda: civitai_client,
    logger=logger,
)

# Register routes
batch_handler_set = BatchImportHandlerSet(handler=batch_import_handler)
register_batch_import_routes(app, batch_handler_set)
```

### Step 2: Add Frontend Manager Initialization

In your main JavaScript initialization file (e.g., `static/js/app.js` or where ImportManager is initialized):

```javascript
// Import the batch import manager
import BatchImportManager from './managers/BatchImportManager.js';

// Initialize batch import manager
const batchImportManager = new BatchImportManager(importManager);

// Make it globally available
window.batchImportManager = batchImportManager;
```

### Step 3: Include HTML Component

In your main recipes page template (likely `templates/recipes.html`):

1. Add the import at the top:
```html
{% include 'components/batch_import_modal.html' %}
```

2. Or copy the batch import modal HTML into your page directly

3. Add the batch import button to your toolbar:
```html
<div class="recipes-toolbar">
    <!-- Existing buttons -->
    {% include 'components/batch_import_modal.html' %}
</div>
```

### Step 4: Verify Dependencies

Make sure these services exist in your app:
- `recipe_analysis_service` - Analyzes images
- `recipe_persistence_service` - Saves recipes
- `recipe_scanner` - Scans for recipes
- `civitai_client` - Civitai API client

## API Endpoints Available

After integration, these endpoints will be available:

```
POST /api/lm/recipes/batch/import-directory
POST /api/lm/recipes/batch/import-urls
GET /api/lm/recipes/batch/status
```

## Testing the Integration

### Backend Test
```bash
# Test directory import via curl
curl -X POST http://localhost:9001/api/lm/recipes/batch/import-directory \
  -H "Content-Type: application/json" \
  -d '{"directory_path": "D:\\models\\models\\loras", "max_concurrent": 3}'
```

### Frontend Test
1. Open browser console (F12)
2. Type: `batchImportManager.openBatchImportModal()`
3. Modal should appear visible

## Configuration Options

### Concurrency Control

Adjust `max_concurrent` in requests to control parallel processing:
- Low: 1-2 (low spec machines, minimal resource usage)
- Medium: 3-5 (standard setup)
- High: 5-10 (powerful machines, faster processing)

### Auto-Organization

Configure these in batch import modal:
- Auto-generate tags from metadata
- Auto-organize by base model

## Troubleshooting Integration

### "Module not found" errors
- Ensure all paths are correct relative to your project structure
- Check that service classes are properly imported

### Routes not registered
- Verify `register_batch_import_routes()` is called during app setup
- Check app initialization order

### Frontend components not showing
- Verify JavaScript is loaded before batch import modal HTML
- Check browser console for JavaScript errors
- Ensure template files are included in correct location

### Services unavailable
- Ensure service instances are created and passed to BatchImportHandler
- Check that all dependencies exist and are initialized

## Performance Considerations

- Batch processing is I/O bound (disk/network operations)
- Increase concurrency on systems with good disk speed
- Monitor memory usage with large batch operations
- Consider limiting to 50-100 images per batch on low-spec systems

## Security Notes

- Directory path input should be validated on backend
- URL downloads should have timeout limits
- Consider rate limiting batch import endpoints
- Validate file types before processing

## Future Enhancements

Possible improvements you could add:
1. Progress bar during batch processing
2. Pause/resume functionality
3. Schedule batch imports for later
4. Batch import from cloud storage services
5. Advanced filtering options
6. Batch tagging from CSV file
7. Recipe template application

## Support

For issues with integration:
1. Check that all service dependencies are initialized
2. Verify routes are properly registered during app startup
3. Check browser and server logs for errors
4. Test individual components in isolation

---

**Ready to use batch import with your LoRA Manager!**

Once integrated, users will be able to:
- ✅ Import entire directories of images at once
- ✅ Batch process multiple image URLs
- ✅ Generate recipes automatically for all
- ✅ See detailed results and statistics
- ✅ Export batch results for records

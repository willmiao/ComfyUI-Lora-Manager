# Batch Recipe Import Guide

## Overview

The Batch Import feature allows you to import and generate recipes for multiple images at once, rather than processing them one image at a time. This is perfect for:

- Importing a folder of reference images
- Batch processing screenshots from workflows
- Mass-importing recipes from online collections
- Organizing large image libraries

## Features

✅ **Directory Import** - Process all images in a folder at once  
✅ **Concurrent Processing** - Multiple images analyzed in parallel (default: 3 concurrent)  
✅ **Automatic Recipe Generation** - Extracts metadata and creates recipes automatically  
✅ **Batch Results** - See summary of processed, failed, and skipped images  
✅ **Error Reporting** - Detailed feedback on what succeeded and what failed  
✅ **URL Batch Import** - Import recipes from multiple image URLs  

## Installation

The batch import feature is now integrated into your LoRA Manager. No additional installation needed!

### Files Added:

**Backend:**
- `py/services/recipes/batch_import_service.py` - Core batch processing logic
- `py/routes/handlers/batch_import_handler.py` - HTTP request handlers
- `py/routes/batch_import_route_registrar.py` - API endpoint registration

**Frontend:**
- `static/js/managers/BatchImportManager.js` - Client-side batch operations
- `templates/components/batch_import_modal.html` - UI components

## Usage

### 1. Directory Import

**Steps:**

1. Click the **"Batch Import"** button (purple gradient button with layer icons)
2. Click the **"From Directory"** tab
3. Enter the full path to your image folder:
   - Windows: `D:\path\to\images` or `D:\models\example_images`
   - Linux/Mac: `/path/to/images`
4. Optional: Configure auto-tagging and auto-organization settings
5. Click **"Start Import"**

**Example paths:**
```
D:\Pictures\AI_Reference_Images
D:\models\example_images
C:\Users\YourName\ImageCollections
```

**Supported image formats:**
- JPG, JPEG
- PNG
- WebP
- GIF
- BMP

### 2. URL Batch Import

**Steps:**

1. Click the **"Batch Import"** button
2. Click the **"From URLs"** tab
3. Paste image URLs, one per line:
   ```
   https://civitai.com/images/12345
   https://example.com/image1.jpg
   https://another-site.com/photo.png
   ```
4. Click **"Start Import"**

**URL types supported:**
- Civitai image URLs (automatically fetches metadata)
- Direct image URLs (JPG, PNG, WebP, etc.)
- Any web-accessible image URL

### 3. Understanding Results

After batch import completes, you'll see:

- **Total Files** - Number of images processed
- **✓ Processed** - Successfully imported recipes (green)
- **✗ Failed** - Images that couldn't be processed (red)
- **⊘ Skipped** - Images with no metadata found (yellow)

**Detailed Results** shows each imported recipe with its filename.  
**Errors** lists specific issues encountered.

## API Endpoints

If integrating with other tools, use these endpoints:

### Directory Import
```
POST /api/lm/recipes/batch/import-directory

Request body:
{
  "directory_path": "/path/to/images",
  "max_concurrent": 3
}

Response:
{
  "success": true,
  "total_files": 50,
  "processed": 48,
  "failed": 2,
  "skipped": 0,
  "results": [...],
  "errors": [...]
}
```

### URL Batch Import
```
POST /api/lm/recipes/batch/import-urls

Request body:
{
  "urls": [
    "https://civitai.com/images/12345",
    "https://example.com/image.jpg"
  ],
  "max_concurrent": 3
}

Response: (same as directory import)
```

### Status Check
```
GET /api/lm/recipes/batch/status

Response:
{
  "active": false,
  "message": "No batch operations in progress"
}
```

## Configuration

### Max Concurrent Operations

By default, 3 images are analyzed simultaneously. Adjust this via the API:

```json
{
  "directory_path": "/path/to/images",
  "max_concurrent": 5
}
```

**Recommendations:**
- **Low-end PC** (4GB RAM): 1-2 concurrent
- **Mid-range PC** (8-16GB RAM): 3-5 concurrent  
- **High-end PC** (32GB+ RAM): 5-10 concurrent

### Auto-Organization Options

When enabled during import:
- **Auto-generate tags** - Tags are extracted from image metadata
- **Auto-organize** - Recipes organized by base model if detected

## Troubleshooting

### "No image files found in directory"
- Check the path is correct
- Verify directory contains supported image formats
- Ensure you have read permissions for the folder

### "Analysis failed: No metadata found in this image"
- The image doesn't contain embedded metadata
- This will be **skipped** in batch import
- Export workflows as PNG to include metadata

### Some images fail while others succeed
- This is normal! Individual images may fail for various reasons
- Check the errors list for specific issues
- Skipped images can often be processed individually later

### Batch operation seems slow
- Reduce `max_concurrent` if your system is struggling
- Close other applications to free up RAM
- Process in smaller batches

### Results aren't visible
- Wait for all tasks to complete (watch the status message)
- Check browser console (F12) for any errors
- Try with a smaller batch first

## Example Workflows

### Scenario 1: Import entire example images collection
```
1. Right-click folder → copy path → paste in "From Directory"
2. Enter: D:\models\models\ExampImage
3. Let it process all images
4. Review results
```

### Scenario 2: Import Civitai reference images
```
1. Collect image URLs from Civitai
2. Paste each URL in "From URLs" tab, one per line
3. Click Start Import
4. Recipes created with Civitai metadata
```

### Scenario 3: Batch process exported workflows
```
1. Export multiple workflows from ComfyUI as PNG
2. Place all in one folder
3. Use "From Directory" to import all at once
4. All gen_params automatically extracted
```

## Performance Tips

- **Split large libraries** - Import 50-100 images at a time
- **Use appropriate concurrency** - Match your PC specs
- **Close background apps** - Free up RAM for processing
- **Use local paths** - Faster than network drives
- **Check file permissions** - Ensure read access to directory

## Limitations & Notes

- Recipes are created based on image metadata only
- If an image has no metadata, it will be skipped
- URL imports depend on internet connectivity
- Civitai URLs will fetch enriched metadata automatically
- Batch operations cannot be paused (only stop browser)

## Advanced Usage

### Connect PowerShell script for automated imports
```powershell
$urls = @(
    "https://civitai.com/images/123",
    "https://civitai.com/images/456"
)

$payload = @{
    urls = $urls
    max_concurrent = 3
} | ConvertTo-Json

Invoke-WebRequest -Uri "http://localhost:9001/api/lm/recipes/batch/import-urls" `
    -Method POST `
    -ContentType "application/json" `
    -Body $payload
```

### Python integration example
```python
import requests
import json

urls = [
    "https://civitai.com/images/123",
    "https://civitai.com/images/456"
]

response = requests.post(
    "http://localhost:9001/api/lm/recipes/batch/import-urls",
    json={"urls": urls, "max_concurrent": 3}
)

results = response.json()
print(f"Processed: {results['processed']}")
print(f"Failed: {results['failed']}")
```

## Support & Issues

If you encounter issues:

1. Check the error messages shown in the batch results
2. Verify file paths and permissions
3. Test with a single image first
4. Try reducing `max_concurrent` value
5. Check server logs for detailed error information

---

**Enjoy batch importing your recipes! 🚀**

# Recipe Batch Import Feature Requirements

## Overview
Enable users to import multiple images as recipes in a single operation, rather than processing them individually. This feature addresses the need for efficient bulk recipe creation from existing image collections.

## User Stories

### US-1: Directory Batch Import
As a user with a folder of reference images or workflow screenshots, I want to import all images from a directory at once so that I don't have to import them one by one.

**Acceptance Criteria:**
- User can specify a local directory path containing images
- System discovers all supported image files in the directory
- Each image is analyzed for metadata and converted to a recipe
- Results show which images succeeded, failed, or were skipped

### US-2: URL Batch Import
As a user with a list of image URLs (e.g., from Civitai or other sources), I want to import multiple images by URL in one operation.

**Acceptance Criteria:**
- User can provide multiple image URLs (one per line or as a list)
- System downloads and processes each image
- URL-specific metadata (like Civitai info) is preserved when available
- Failed URLs are reported with clear error messages

### US-3: Concurrent Processing Control
As a user with varying system resources, I want to control how many images are processed simultaneously to balance speed and system load.

**Acceptance Criteria:**
- User can configure the number of concurrent operations (1-10)
- System provides sensible defaults based on common hardware configurations
- Processing respects the concurrency limit to prevent resource exhaustion

### US-4: Import Results Summary
As a user performing a batch import, I want to see a clear summary of the operation results so I understand what succeeded and what needs attention.

**Acceptance Criteria:**
- Total count of images processed is displayed
- Number of successfully imported recipes is shown
- Number of failed imports with error details is provided
- Number of skipped images (no metadata) is indicated
- Results can be exported or saved for reference

### US-5: Progress Visibility
As a user importing a large batch, I want to see the progress of the operation so I know it's working and can estimate completion time.

**Acceptance Criteria:**
- Progress indicator shows current status (e.g., "Processing image 5 of 50")
- Real-time updates as each image completes
- Ability to view partial results before completion
- Clear indication when the operation is finished

## Functional Requirements

### FR-1: Image Discovery
The system shall discover image files in a specified directory recursively or non-recursively based on user preference.

**Supported formats:** JPG, JPEG, PNG, WebP, GIF, BMP

### FR-2: Metadata Extraction
For each image, the system shall:
- Extract EXIF metadata if present
- Parse embedded workflow data (ComfyUI PNG metadata)
- Fetch external metadata for known URL patterns (e.g., Civitai)
- Generate recipes from extracted information

### FR-3: Concurrent Processing
The system shall support concurrent processing of multiple images with:
- Configurable concurrency limit (default: 3)
- Resource-aware execution
- Graceful handling of individual failures without stopping the batch

### FR-4: Error Handling
The system shall handle various error conditions:
- Invalid directory paths
- Inaccessible files
- Network errors for URL imports
- Images without extractable metadata
- Malformed or corrupted image files

### FR-5: Recipe Persistence
Successfully analyzed images shall be persisted as recipes with:
- Extracted generation parameters
- Preview image association
- Tags and metadata
- Source information (file path or URL)

## Non-Functional Requirements

### NFR-1: Performance
- Batch operations should complete in reasonable time (< 5 seconds per image on average)
- UI should remain responsive during batch operations
- Memory usage should scale gracefully with batch size

### NFR-2: Scalability
- Support batches of 1-1000 images
- Handle mixed success/failure scenarios gracefully
- No hard limits on concurrent operations (configurable)

### NFR-3: Usability
- Clear error messages for common failure cases
- Intuitive UI for configuring import options
- Accessible from the main Recipes interface

### NFR-4: Reliability
- Failed individual imports should not crash the entire batch
- Partial results should be preserved on unexpected termination
- All operations should be idempotent (re-importing same image doesn't create duplicates)

## API Requirements

### Batch Import Endpoints
The system should expose endpoints for:

1. **Directory Import**
   - Accept directory path and configuration options
   - Return operation ID for status tracking
   - Async or sync operation support

2. **URL Import**
   - Accept list of URLs and configuration options
   - Support URL validation before processing
   - Return operation ID for status tracking

3. **Status/Progress**
   - Query operation status by ID
   - Get current progress and partial results
   - Retrieve final results after completion

## UI/UX Requirements

### UIR-1: Entry Point
Batch import should be accessible from the Recipes page via a clearly labeled button in the toolbar.

### UIR-2: Import Modal
A modal dialog should provide:
- Tab or section for Directory import
- Tab or section for URL import
- Configuration options (concurrency, options)
- Start/Stop controls
- Results display area

### UIR-3: Results Display
Results should be presented with:
- Summary statistics (total, success, failed, skipped)
- Expandable details for each category
- Export or copy functionality for results
- Clear visual distinction between success/failure/skip

## Future Considerations

- **Scheduled Imports**: Ability to schedule batch imports for later execution
- **Import Templates**: Save import configurations for reuse
- **Cloud Storage**: Import from cloud storage services (Google Drive, Dropbox)
- **Duplicate Detection**: Advanced duplicate detection based on image hash
- **Tag Suggestions**: AI-powered tag suggestions for imported recipes
- **Batch Editing**: Apply tags or organization to multiple imported recipes at once

## Dependencies

- Recipe analysis service (metadata extraction)
- Recipe persistence service (storage)
- Image download capability (for URL imports)
- Recipe scanner (for refresh after import)
- Civitai client (for enhanced URL metadata)

---

*Document Version: 1.0*
*Status: Requirements Definition*

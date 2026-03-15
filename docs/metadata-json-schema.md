# metadata.json Schema Documentation

This document defines the complete schema for `.metadata.json` files used by Lora Manager. These sidecar files store model metadata alongside model files (LoRA, Checkpoint, Embedding).

## Overview

- **File naming**: `<model_name>.metadata.json` (e.g., `my_lora.safetensors` → `my_lora.metadata.json`)
- **Format**: JSON with UTF-8 encoding
- **Purpose**: Store model metadata, tags, descriptions, preview images, and Civitai/CivArchive integration data
- **Extensibility**: Unknown fields are preserved via `_unknown_fields` mechanism for forward compatibility

---

## Base Fields (All Model Types)

These fields are present in all model metadata files.

| Field | Type | Required | Auto-Updated | Description |
|-------|------|----------|--------------|-------------|
| `file_name` | string | ✅ Yes | ✅ Yes | Filename without extension (e.g., `"my_lora"`) |
| `model_name` | string | ✅ Yes | ❌ No | Display name of the model. **Default**: `file_name` if no other source |
| `file_path` | string | ✅ Yes | ✅ Yes | Full absolute path to the model file (normalized with `/` separators) |
| `size` | integer | ✅ Yes | ❌ No | File size in bytes. **Set at**: Initial scan or download completion. Does not change thereafter. |
| `modified` | float | ✅ Yes | ❌ No | **Import timestamp** — Unix timestamp when the model was first imported/added to the system. Used for "Date Added" sorting. Does not change after initial creation. |
| `sha256` | string | ⚠️ Conditional | ✅ Yes | SHA256 hash of the model file (lowercase). **LoRA**: Required. **Checkpoint**: May be empty when `hash_status="pending"` (lazy hash calculation) |
| `base_model` | string | ❌ No | ❌ No | Base model type. **Examples**: `"SD 1.5"`, `"SDXL 1.0"`, `"SDXL Lightning"`, `"Flux.1 D"`, `"Flux.1 S"`, `"Flux.1 Krea"`, `"Illustrious"`, `"Pony"`, `"AuraFlow"`, `"Kolors"`, `"ZImageTurbo"`, `"Wan Video"`, etc. **Default**: `"Unknown"` or `""` |
| `preview_url` | string | ❌ No | ✅ Yes | Path to preview image file |
| `preview_nsfw_level` | integer | ❌ No | ❌ No | NSFW level using **bitmask values** from Civitai: `1` (PG), `2` (PG13), `4` (R), `8` (X), `16` (XXX), `32` (Blocked). **Default**: `0` (none) |
| `notes` | string | ❌ No | ❌ No | User-defined notes |
| `from_civitai` | boolean | ❌ No (default: `true`) | ❌ No | Whether the model originated from Civitai |
| `civitai` | object | ❌ No | ⚠️ Partial | Civitai/CivArchive API data and user-defined fields |
| `tags` | array[string] | ❌ No | ⚠️ Partial | Model tags (merged from API and user input) |
| `modelDescription` | string | ❌ No | ⚠️ Partial | Full model description (from API or user) |
| `civitai_deleted` | boolean | ❌ No (default: `false`) | ❌ No | Whether the model was deleted from Civitai |
| `favorite` | boolean | ❌ No (default: `false`) | ❌ No | Whether the model is marked as favorite |
| `exclude` | boolean | ❌ No (default: `false`) | ❌ No | Whether to exclude from cache/scanning. User can set from `false` to `true` (currently no UI to revert) |
| `db_checked` | boolean | ❌ No (default: `false`) | ❌ No | Whether checked against archive database |
| `skip_metadata_refresh` | boolean | ❌ No (default: `false`) | ❌ No | Skip this model during bulk metadata refresh |
| `metadata_source` | string\|null | ❌ No | ✅ Yes | Last provider that supplied metadata (see below) |
| `last_checked_at` | float | ❌ No (default: `0`) | ✅ Yes | Unix timestamp of last metadata check |
| `hash_status` | string | ❌ No (default: `"completed"`) | ✅ Yes | Hash calculation status: `"pending"`, `"calculating"`, `"completed"`, `"failed"` |

---

## Model-Specific Fields

### LoRA Models

LoRA models do not have a `model_type` field in metadata.json. The type is inferred from context or `civitai.type` (e.g., `"LoRA"`, `"LoCon"`, `"DoRA"`).

| Field | Type | Required | Auto-Updated | Description |
|-------|------|----------|--------------|-------------|
| `usage_tips` | string (JSON) | ❌ No (default: `"{}"`) | ❌ No | JSON string containing recommended usage parameters |

**`usage_tips` JSON structure:**

```json
{
  "strength_min": 0.3,
  "strength_max": 0.8,
  "strength_range": "0.3-0.8",
  "strength": 0.6,
  "clip_strength": 0.5,
  "clip_skip": 2
}
```

| Key | Type | Description |
|-----|------|-------------|
| `strength_min` | number | Minimum recommended model strength |
| `strength_max` | number | Maximum recommended model strength |
| `strength_range` | string | Human-readable strength range |
| `strength` | number | Single recommended strength value |
| `clip_strength` | number | Recommended CLIP/embedding strength |
| `clip_skip` | integer | Recommended CLIP skip value |

---

### Checkpoint Models

| Field | Type | Required | Auto-Updated | Description |
|-------|------|----------|--------------|-------------|
| `model_type` | string | ❌ No (default: `"checkpoint"`) | ❌ No | Model type: `"checkpoint"`, `"diffusion_model"` |

---

### Embedding Models

| Field | Type | Required | Auto-Updated | Description |
|-------|------|----------|--------------|-------------|
| `model_type` | string | ❌ No (default: `"embedding"`) | ❌ No | Model type: `"embedding"` |

---

## The `civitai` Field Structure

The `civitai` object stores the complete Civitai/CivArchive API response. Lora Manager preserves all fields from the API for future compatibility and extracts specific fields for use in the application.

### Version-Level Fields (Civitai API)

**Fields Used by Lora Manager:**

| Field | Type | Description |
|-------|------|-------------|
| `id` | integer | Version ID |
| `modelId` | integer | Parent model ID |
| `name` | string | Version name (e.g., `"v1.0"`, `"v2.0-pruned"`) |
| `nsfwLevel` | integer | NSFW level (bitmask: 1=PG, 2=PG13, 4=R, 8=X, 16=XXX, 32=Blocked) |
| `baseModel` | string | Base model (e.g., `"SDXL 1.0"`, `"Flux.1 D"`, `"Illustrious"`, `"Pony"`) |
| `trainedWords` | array[string] | **Trigger words** for the model |
| `type` | string | Model type (`"LoRA"`, `"Checkpoint"`, `"TextualInversion"`) |
| `earlyAccessEndsAt` | string\|null | Early access end date (used for update notifications) |
| `description` | string | Version description (HTML) |
| `model` | object | Parent model object (see Model-Level Fields below) |
| `creator` | object | Creator information (see Creator Fields below) |
| `files` | array[object] | File list with hashes, sizes, download URLs (used for metadata extraction) |
| `images` | array[object] | Image list with metadata, prompts, NSFW levels (used for preview/examples) |

**Fields Stored but Not Currently Used:**

| Field | Type | Description |
|-------|------|-------------|
| `createdAt` | string (ISO 8601) | Creation timestamp |
| `updatedAt` | string (ISO 8601) | Last update timestamp |
| `status` | string | Version status (e.g., `"Published"`, `"Draft"`) |
| `publishedAt` | string (ISO 8601) | Publication timestamp |
| `baseModelType` | string | Base model type (e.g., `"Standard"`, `"Inpaint"`, `"Refiner"`) |
| `earlyAccessConfig` | object | Early access configuration |
| `uploadType` | string | Upload type (`"Created"`, `"FineTuned"`, etc.) |
| `usageControl` | string | Usage control setting |
| `air` | string | Artifact ID (URN format: `urn:air:sdxl:lora:civitai:122359@135867`) |
| `stats` | object | Download count, ratings, thumbs up count |
| `videos` | array[object] | Video list |
| `downloadUrl` | string | Direct download URL |
| `trainingStatus` | string\|null | Training status (for on-site training) |
| `trainingDetails` | object\|null | Training configuration |

### Model-Level Fields (`civitai.model.*`)

**Fields Used by Lora Manager:**

| Field | Type | Description |
|-------|------|-------------|
| `name` | string | Model name |
| `type` | string | Model type (`"LoRA"`, `"Checkpoint"`, `"TextualInversion"`) |
| `description` | string | Model description (HTML, used for `modelDescription`) |
| `tags` | array[string] | Model tags (used for `tags` field) |
| `allowNoCredit` | boolean | License: allow use without credit |
| `allowCommercialUse` | array[string] | License: allowed commercial uses. **Values**: `"Image"` (sell generated images), `"Video"` (sell generated videos), `"RentCivit"` (rent on Civitai), `"Rent"` (rent elsewhere) |
| `allowDerivatives` | boolean | License: allow derivatives |
| `allowDifferentLicense` | boolean | License: allow different license |

**Fields Stored but Not Currently Used:**

| Field | Type | Description |
|-------|------|-------------|
| `nsfw` | boolean | Model NSFW flag |
| `poi` | boolean | Person of Interest flag |

### Creator Fields (`civitai.creator.*`)

Both fields are used by Lora Manager:

| Field | Type | Description |
|-------|------|-------------|
| `username` | string | Creator username (used for author display and search) |
| `image` | string | Creator avatar URL (used for display) |

### Model Type Field (Top-Level, Outside `civitai`)

| Field | Type | Values | Description |
|-------|------|--------|-------------|
| `model_type` | string | `"checkpoint"`, `"diffusion_model"`, `"embedding"` | Stored in metadata.json for Checkpoint and Embedding models. **Note**: LoRA models do not have this field; type is inferred from `civitai.type` or context. |

### User-Defined Fields (Within `civitai`)

For models not from Civitai or user-added data:

| Field | Type | Description |
|-------|------|-------------|
| `trainedWords` | array[string] | **Trigger words** — manually added by user |
| `customImages` | array[object] | Custom example images added by user |

### customImages Structure

Each custom image entry has the following structure:

```json
{
  "url": "",
  "id": "short_id",
  "nsfwLevel": 0,
  "width": 832,
  "height": 1216,
  "type": "image",
  "meta": {
    "prompt": "...",
    "negativePrompt": "...",
    "steps": 20,
    "cfgScale": 7,
    "seed": 123456
  },
  "hasMeta": true,
  "hasPositivePrompt": true
}
```

| Field | Type | Description |
|-------|------|-------------|
| `url` | string | Empty for local custom images |
| `id` | string | Short ID or filename |
| `nsfwLevel` | integer | NSFW level (bitmask) |
| `width` | integer | Image width in pixels |
| `height` | integer | Image height in pixels |
| `type` | string | `"image"` or `"video"` |
| `meta` | object\|null | Generation metadata (prompt, seed, etc.) extracted from image |
| `hasMeta` | boolean | Whether metadata is available |
| `hasPositivePrompt` | boolean | Whether a positive prompt is available |

### Minimal Non-Civitai Example

```json
{
  "civitai": {
    "trainedWords": ["my_trigger_word"]
  }
}
```

### Non-Civitai Example Without Trigger Words

```json
{
  "civitai": {}
}
```

### Example: User-Added Custom Images

```json
{
  "civitai": {
    "trainedWords": ["custom_style"],
    "customImages": [
      {
        "url": "",
        "id": "example_1",
        "nsfwLevel": 0,
        "width": 832,
        "height": 1216,
        "type": "image",
        "meta": {
          "prompt": "example prompt",
          "seed": 12345
        },
        "hasMeta": true,
        "hasPositivePrompt": true
      }
    ]
  }
}
```

---

## Metadata Source Values

The `metadata_source` field indicates which provider last updated the metadata:

| Value | Source |
|-------|--------|
| `"civitai_api"` | Civitai API |
| `"civarchive"` | CivArchive API |
| `"archive_db"` | Metadata Archive Database |
| `null` | No external source (user-defined only) |

---

## Auto-Update Behavior

### Fields Updated During Scanning

These fields are automatically synchronized with the filesystem:

- `file_name` — Updated if actual filename differs
- `file_path` — Normalized and updated if path changes
- `preview_url` — Updated if preview file is moved/removed
- `sha256` — Updated during hash calculation (when `hash_status="pending"`)
- `hash_status` — Updated during hash calculation
- `last_checked_at` — Timestamp of scan
- `metadata_source` — Set based on metadata provider

### Fields Set Once (Immutable After Import)

These fields are set when the model is first imported/scanned and **never change** thereafter:

- `modified` — Import timestamp (used for "Date Added" sorting)
- `size` — File size at time of import/download

### User-Editable Fields

These fields can be edited by users at any time through the Lora Manager UI or by manually editing the metadata.json file:

- `model_name` — Display name
- `tags` — Model tags
- `modelDescription` — Model description
- `notes` — User notes
- `favorite` — Favorite flag
- `exclude` — Exclude from scanning (user can set `false`→`true`, currently no UI to revert)
- `skip_metadata_refresh` — Skip during bulk refresh
- `civitai.trainedWords` — Trigger words
- `civitai.customImages` — Custom example images
- `usage_tips` — Usage recommendations (LoRA only)

---


## Field Reference by Behavior

### Required Fields (Must Always Exist)

- `file_name`
- `model_name` (defaults to `file_name` if not provided)
- `file_path`
- `size`
- `modified`
- `sha256` (LoRA: always required; Checkpoint: may be empty when `hash_status="pending"`)

### Optional Fields with Defaults

| Field | Default |
|-------|---------|
| `base_model` | `"Unknown"` or `""` |
| `preview_nsfw_level` | `0` |
| `from_civitai` | `true` |
| `civitai` | `{}` |
| `tags` | `[]` |
| `modelDescription` | `""` |
| `notes` | `""` |
| `civitai_deleted` | `false` |
| `favorite` | `false` |
| `exclude` | `false` |
| `db_checked` | `false` |
| `skip_metadata_refresh` | `false` |
| `metadata_source` | `null` |
| `last_checked_at` | `0` |
| `hash_status` | `"completed"` |
| `usage_tips` | `"{}"` (LoRA only) |
| `model_type` | `"checkpoint"` or `"embedding"` (not present in LoRA models) |

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | 2026-03 | Initial schema documentation |

---

## See Also

- [JSON Schema Definition](../.specs/metadata.schema.json) — Formal JSON Schema for validation

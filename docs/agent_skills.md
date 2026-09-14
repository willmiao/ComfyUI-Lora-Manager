# Agent Skills System

The LoRA Manager agent skills system enables LLM-powered metadata enrichment and other AI-driven tasks. Users configure their own LLM provider (BYOK), and skills are executed through right-click context menu actions.

## Architecture

```
┌──────────────────────────────────────────────┐
│              LoRA Manager Backend             │
│                                               │
│  ┌──────────────┐    ┌────────────────┐       │
│  │ LLMService    │───▶│ LLM Provider   │       │
│  │ (BYOK config, │◀───│ (OpenAI/Ollama │       │
│  │  API calls)   │    │ /custom)       │       │
│  └───────┬───────┘    └────────────────┘       │
│          │                                     │
│  ┌───────▼───────────────────────┐             │
│  │     AgentService              │             │
│  │  (orchestration: validate     │             │
│  │   → LLM call → post-process   │             │
│  │   → WebSocket broadcast)      │             │
│  └───────┬───────────────────────┘             │
│          │                                     │
│  ┌───────▼───────────────────────┐             │
│  │     SkillRegistry             │             │
│  │  ┌─────────────────────────┐  │             │
│  │  │ enrich_hf_metadata:     │  │             │
│  │  │  - skill.yaml           │  │             │
│  │  │  - prompt.md            │  │             │
│  │  │  - handler.py           │  │             │
│  │  └─────────────────────────┘  │             │
│  └───────────────────────────────┘             │
└──────────────────────────────────────────────┘
```

### Key Design Principle

**Skills define *what* to do (prompt + post-processing). The AgentService handles *how* (LLM calls, validation, progress).**

Skills never call the LLM directly. This keeps BYOK configuration centralized and provider-agnostic.

## BYOK Configuration

Users configure their LLM provider in **Settings → AI Provider**:

| Setting | Description | Example |
|---|---|---|
| `llm_provider` | Provider type | `openai`, `ollama`, or `custom` |
| `llm_api_key` | API key (not needed for local Ollama) | `sk-...` |
| `llm_api_base` | Custom API base URL (empty = provider default) | `https://api.openai.com/v1` |
| `llm_model` | Model name | `gpt-4o-mini` |

Environment variable overrides: `LLM_API_KEY`, `LLM_MODEL`, `LLM_API_BASE`, `LLM_PROVIDER`.

### Supported Providers

- **OpenAI**: Uses `https://api.openai.com/v1` by default
- **Ollama** (local): Uses `http://localhost:11434/v1`, no API key required
- **Custom**: Any OpenAI-compatible endpoint (vLLM, LM Studio, etc.) — set `llm_api_base` explicitly

## Available Skills

### enrich_hf_metadata

Enriches models linked to an external model site with metadata extracted by an LLM from the site's model card (README).

**Entry point**: Right-click context menu → "Enrich Metadata with AI"

**Supported model sources**:

| Platform | Link | AI enrichment | Direct download |
| --- | --- | --- | --- |
| Hugging Face | yes | yes | yes |
| ModelScope | yes | yes | yes |
| TensorArt | yes | no (see below) | no |

TensorArt is link-only: `tensor.art` sits behind a Cloudflare managed challenge and its internal API requires session authorization, so the backend cannot read its model pages. Linking still stores the canonical page URL and the "View on TensorArt" link works.

**What it does**:
1. Reads the model's `.metadata.json` to get the source (`source_platform` + `source_url`, or the legacy `hf_url`)
2. Fetches the model card through the provider in `py/services/model_sources/` — the README via `fetch_model_card()`, plus any extras the site keeps outside it via `fetch_model_card_context()`
3. Sends the README + site-provided extras + local metadata to the LLM for structured extraction
4. Writes extracted fields to `.metadata.json`:
   - `base_model` — only if current value is empty
   - `trainedWords` — trigger words (LoRA only, if none exist)
   - `modelDescription` — the site's author description (if any) followed by the README rendered as HTML
   - `tags` — merged with existing tags, deduplicated
   - `civitai.images` — example images
   - `metadata_source` — audit trail: `agent:enrich_hf_metadata`
   - `llm_enriched_at` — ISO timestamp
5. Downloads and optimizes a preview image, using the per-file example image the
   site publishes when the README has none
6. Updates the scanner cache
7. Broadcasts WebSocket progress events

#### Site-provided card extras (`fetch_model_card_context`)

A model card is not always just `README.md`. ModelScope keeps the author's
summary (`Description`), the site-curated tags (`OfficialTags`), and — per
published version — the model filenames together with that file's example
images (`MuseInfo.versions[].coverImages`) and trigger words in its
model-detail API. AIGC repositories there often ship an auto-generated
boilerplate README and put everything useful in `Description`, so reading only
the README yields almost nothing.

Providers opt in by overriding `ModelSource.fetch_model_card_context()`, which
returns a `ModelCardContext`. The wanted file is identified by its sha256 when
the caller knows it (the scanner already records one) and by **basename**
otherwise, so each checkpoint in a collection repo gets its own images — and
keeps getting them after the user renames the weights, which is the only
identifier a rename cannot invalidate. Sites with no such extras inherit an
empty context, and the pipeline behaves exactly as before.

The README and the repository metadata describe the whole repository, not one
file, so `execute_skill()` creates a `ModelSourceCache` for the duration of a
run and passes it down. Enriching the eight checkpoints of one ModelScope
repository costs two HTTP requests instead of sixteen; only the per-file
selection is redone for each file. Nothing is cached across runs, and download
URLs never go through it.

#### Deterministic data is applied whether or not an LLM is configured

`AgentService._load_source_card()` runs for every source-backed enrichment, and
the post-processor applies what it returns before the LLM output is merged. A
user with **no** provider configured therefore still gets the author summary,
the example images, the preview, the site-curated tags, the trigger words and
the README rendered as the model description.

The LLM is always consulted when one is configured — invoking **Enrich Metadata
with AI** must call the provider every time, and the site data is never treated
as a reason to skip it. The deterministic values act as fallbacks that fill
gaps the LLM leaves behind:

| Field | Deterministic source | LLM role |
| --- | --- | --- |
| `modelDescription` | author summary + README as HTML | — |
| `civitai.images` | site example images, then README images | — |
| `preview_url` | first available example image | may propose one from the README |
| `tags` | site-curated tags, always merged in | proposes additional content tags |
| `civitai.description` | author summary | richer 1-2 sentence summary wins |
| `base_model` | site hints resolved against the canonical vocabulary (`py/services/agent/base_model_resolver.py`) | mapping it is the LLM's job; the resolver only fills in when the LLM returns nothing |
| `trainedWords` | per-file site trigger words, then YAML `instance_prompt` | primary extraction |
| `usage_tips` | regex over an explicitly stated strength range | primary extraction |
| `notes` | — | LLM-only |

Models with no source, an unknown source, or a source without model-card access (TensorArt) are skipped with an explicit reason and counted in the run summary.

**Model types**: LoRA, Checkpoint, Embedding

## Adding a New Skill

### 1. Create the skill directory

```
py/services/agent/skills/<skill_name>/
├── skill.yaml      # Skill metadata and schemas
├── prompt.md       # LLM prompt template
└── handler.py      # Pre-processing and post-processing
```

### 2. Write skill.yaml

```yaml
name: my_skill
title: "My Skill"
description: "What this skill does"
llm_required: true
model_type_filter: ["lora"]  # or null for all types
input_schema:
  type: object
  properties:
    model_paths:
      type: array
      items:
        type: string
  required:
    - model_paths
output_schema:
  type: object
  properties:
    # ... JSON schema for LLM output
permissions:
  write_metadata: true
  write_previews: false
  network_domains:
    - "example.com"
```

### 3. Write prompt.md

Use `{{variable}}` placeholders that will be replaced with data from the `prepare` function:

```markdown
You are an expert assistant...

Model URL: {{source_url}}
README content:
{{readme_content}}

Current metadata:
{{current_metadata}}
```

### 4. Write handler.py

```python
async def prepare(model_path: str, input_data: dict) -> dict:
    """Gather context for the LLM prompt. Returns variables for template rendering."""
    return {
        "model_path": model_path,
        # ... other variables used in prompt.md
    }

async def post_process(context) -> dict:
    """Apply the LLM-extracted data to the model."""
    llm_response = context.llm_response
    # ... write metadata, download previews, update cache
    return {
        "success": True,
        "updated_fields": ["base_model", "tags"],
        "errors": [],
    }
```

**Important**: Use absolute imports (`from py.utils.metadata_manager import MetadataManager`) because skills are loaded via `importlib.util.spec_from_file_location`, which doesn't support relative imports.

### 5. Test

The skill is automatically discovered by `SkillRegistry` on startup. Test with:

```python
pytest tests/services/test_agent_service.py
```

## API Endpoints

| Method | Path | Description |
|---|---|---|
| GET | `/api/lm/agent/skills` | List available skills |
| POST | `/api/lm/agent/execute/{skill_name}` | Execute a skill (body: `{"model_paths": [...]}`) |
| POST | `/api/lm/agent/cancel` | Cancel running skill (stub) |

## WebSocket Events

| Type | When | Key fields |
|---|---|---|
| `agent_progress` | Skill started/processing | `skill`, `status`, `total`, `processed`, `success`, `current_path` |
| `agent_progress` | Skill completed | `skill`, `status`, `updated_models`, `errors`, `summary` |
| `agent_progress` | Skill error | `skill`, `status`, `error` |

## Security Model

Skills declare permissions in `skill.yaml`:
- `write_metadata` — can write `.metadata.json` files
- `write_previews` — can download/replace preview images
- `network_domains` — allowed domains for HTTP requests

These are declarative constraints checked by `AgentService`. They are defense-in-depth, not a sandbox — the Python process can technically do anything, but the contract is clear and auditable.

## File Locations

| Component | Path |
|---|---|
| LLMService | `py/services/llm_service.py` |
| AgentService | `py/services/agent/agent_service.py` |
| SkillRegistry | `py/services/agent/skill_registry.py` |
| SkillDefinition | `py/services/agent/skill_definition.py` |
| Skills directory | `py/services/agent/skills/` |
| Route handlers | `py/routes/handlers/agent_handlers.py` |
| Frontend manager | `static/js/managers/AgentManager.js` |
| Settings UI | `templates/components/modals/settings_modal.html` |
| Context menu | `templates/components/context_menu.html` |

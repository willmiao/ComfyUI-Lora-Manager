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

Enriches HuggingFace-downloaded models with metadata extracted by an LLM from the HF model card.

**Entry point**: Right-click context menu → "Enrich Metadata (Agent)"

**What it does**:
1. Reads the model's `.metadata.json` to get the `hf_url`
2. Fetches the README.md from the HuggingFace repository
3. Sends the README + local metadata to the LLM for structured extraction
4. Writes extracted fields to `.metadata.json`:
   - `base_model` — only if current value is empty
   - `trainedWords` — trigger words (LoRA only, if none exist)
   - `modelDescription` — concise summary (if none exists)
   - `tags` — merged with existing tags, deduplicated
   - `metadata_source` — audit trail: `agent:enrich_hf_metadata`
   - `llm_enriched_at` — ISO timestamp
5. Downloads and optimizes preview image (if LLM found one in the README)
6. Updates the scanner cache
7. Broadcasts WebSocket progress events

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

Model URL: {{hf_url}}
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

# Embeddings Usage Tracking — Hybrid Approach (Plan C)

> **Status**: Reference document for future implementation
> **Current implementation**: Plan A (prompt text parsing only, see `usage_stats.py:_process_embeddings`)
> **Next step**: Add Plan B as a supplement when edge-case coverage is needed

## Problem

Embeddings in ComfyUI are not loaded through dedicated ComfyUI nodes like LoRAs or
Checkpoints. They are resolved during CLIP tokenization when the prompt text contains
`embedding:<name>` syntax (see `comfy/sd1_clip.py:SDTokenizer.tokenize_with_weights`).

This means the existing metadata_collector hook (which intercepts node execution via
`_map_node_over_list`) cannot capture embeddings the same way it captures LoRAs and
checkpoints — there is no "EmbeddingLoader" node to intercept.

## Solution Architecture

The hybrid approach combines **two complementary mechanisms** to capture embedding
usage from all possible paths.

```
┌─────────────────────────────────────────────────────────┐
│                 Plan A (已实现)                          │
│                                                         │
│  MetadataRegistry.prompt_metadata["prompts"]            │
│       │                                                  │
│       ▼                                                  │
│  _process_embeddings()                                   │
│       │                                                  │
│       ├─ Iterate all prompt node texts                   │
│       ├─ regex extract "embedding:<name>"                │
│       ├─ resolve name → sha256 via EmbeddingScanner      │
│       └─ UsageStats.stats["embeddings"][sha256]++        │
│                                                         │
│  Coverage: ~95% — all CLIPTextEncode/Flux/etc nodes     │
│                                                         │
│  Gap: Custom nodes that load embeddings programmatically │
│       without putting embedding:name in prompt text      │
└─────────────────────────────────────────────────────────┘

                         +
                         ↓  (future: enable Plan B when needed)

┌─────────────────────────────────────────────────────────┐
│                 Plan B (未来 — monkey-patch)              │
│                                                         │
│  comfy/sd1_clip.py:load_embed()                         │
│       │                                                  │
│       ▼                                                  │
│  Monkey-patch intercepts EVERY embedding file load       │
│       │                                                  │
│       ├─ Records embedding_name + success/failure        │
│       ├─ Associates with current prompt_id (via registry)│
│       └─ Feeds into UsageStats same as Plan A            │
│                                                         │
│  Coverage: 100% — catches ALL embedding loads            │
│                                                         │
│  Cost: Requires patching into ComfyUI internals          │
│        (sd1_clip.py, sdxl_clip.py, some text_encoders)   │
└─────────────────────────────────────────────────────────┘
```

## Plan B Detail — Monkey-patch `load_embed`

### Target Function

**`comfy.sd1_clip.load_embed(embedding_name, embedding_directory, embedding_size, embed_key=None)`**
at line 415 of `sd1_clip.py`.

This is the **single choke point** for all embedding file loads in ComfyUI. Every
CLIP variant (SD1, SDXL, SD3, Flux) calls this same function.

### Implementation Sketch

```python
# In metadata_collector/metadata_hook.py (or a new module)
import comfy.sd1_clip as sd1_clip

_original_load_embed = sd1_clip.load_embed

def _patched_load_embed(embedding_name, embedding_directory, embedding_size, embed_key=None):
    result = _original_load_embed(
        embedding_name, embedding_directory, embedding_size, embed_key
    )
    if result is not None:
        _record_embedding_usage(embedding_name)
    return result

sd1_clip.load_embed = _patched_load_embed
```

### Prompt ID Association

The challenge is associating the `load_embed` call with the current `prompt_id`.
Options:

1. **Thread-local / contextvar**: Store current `prompt_id` in a `contextvars.ContextVar`
   that the metadata_collector sets at the start of each prompt execution.

2. **MetadataRegistry singleton**: The MetadataRegistry already has `current_prompt_id`.
   The patch can read it directly since both run in the same thread.

3. **Lazy aggregation**: Instead of associating with prompt_id at load time, collect
   all loaded embedding names in a global set during execution, then flush to
   UsageStats after the prompt completes.

### Files to Patch

| File | Function | Coverage |
|------|----------|----------|
| `comfy/sd1_clip.py:415` | `load_embed()` | Primary — SD1.x, SDXL, SD3, Flux |
| `comfy/sdxl_clip.py` | Not needed (calls `sd1_clip.SDTokenizer`) | — |
| `comfy/text_encoders/sd3_clip.py` | Not needed (calls `sd1_clip.SDTokenizer`) | — |
| `comfy/text_encoders/flux.py` | Not needed (calls `sd1_clip.SDTokenizer`) | — |

The SD1 tokenizer is the base class for all CLIP variants' tokenizers, so patching
`load_embed` covers them all.

### Edge Cases

| Edge Case | Plan A | Plan B |
|-----------|--------|--------|
| `embedding:name` in CLIPTextEncode | ✅ | ✅ |
| `embedding:name` in CLIPTextEncodeFlux | ✅ | ✅ |
| `embedding:name` in PromptLM (LoRA Manager) | ✅ | ✅ |
| `embedding:name` in WAS_Text_to_Conditioning | ✅ | ✅ |
| Custom node that loads embedding programmatically | ❌ | ✅ |
| Embedding loaded multiple times in same prompt | ✅ (dedup via set) | ✅ (dedup via set) |
| Embedding file not found | N/A | ✅ (can log) |
| Embedding dimension mismatch | N/A | ✅ (can log) |
| Text encoder with non-standard tokenizer (LLaMA, T5...) | Partial | ✅ (if it calls load_embed) |

## Migration Path: Standalone → Hybrid

### Phase 1 — Plan A (当前状态)
- Prompt text parsing only
- No monkey-patching required
- Covers all standard workflows

### Phase 2 — Enable Plan B (未来工作)
1. Add monkey-patch of `load_embed` in `metadata_collector/metadata_hook.py` (alongside
   the existing `_map_node_over_list` hook)
2. Collect loaded embedding names in a `set()` on the registry
3. In `UsageStats._process_embeddings()`, merge the Plan A results (from prompt text)
   with the Plan B results (from the patch)
4. Add `prompt_data` field on MetadataRegistry to store loaded embeddings per prompt

### Deduplication

```python
# Merge Plan A + Plan B results in _process_embeddings
plan_a_names = extract_from_prompt_texts(prompts_data)
plan_b_names = registry.get_loaded_embeddings(prompt_id)

all_names = plan_a_names | plan_b_names
```

## Testing the Hybrid

| Scenario | What to verify |
|----------|---------------|
| Standard `embedding:name` in prompt | Plan A captures it |
| Embedding loaded by custom node script | Plan B captures it |
| Both paths fire for same embedding | No double-counting (dedup) |
| Embedding name resolves to hash | EmbeddingScanner.get_hash_by_filename works |
| No embedding scanner available | Graceful skip, no crash |
| Missing embedding file | Plan B logs warning, Plan A skips gracefully |
| Empty prompt | No crash, no entries |
| Standalone mode | Both plans disabled gracefully |

## Key Files Reference

| File | Role |
|------|------|
| `py/utils/usage_stats.py` | Core — `_process_embeddings()` for Plan A |
| `py/metadata_collector/constants.py` | `EMBEDDINGS` category constant |
| `py/metadata_collector/metadata_hook.py` | Future — monkey-patch for Plan B |
| `py/services/embedding_scanner.py` | Hash resolution service |
| `py/routes/stats_routes.py` | Already handles `usage_data.get('embeddings', {})` |
| `comfy/sd1_clip.py` (ComfyUI) | `load_embed()` — Plan B target |

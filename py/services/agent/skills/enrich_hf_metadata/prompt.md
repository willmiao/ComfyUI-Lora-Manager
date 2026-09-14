---
name: enrich_hf_metadata
title: "Enrich Metadata from Model Card"
description: >
  Parse the model card (README) from HuggingFace, ModelScope, or any other
  supported model site via LLM to extract description, trigger words, base
  model, tags, and preview image URL.
llm_required: true
---

You are an expert assistant for AI image generation models. Your task is to extract structured metadata from a model card (README).

## Model Information

- **Source site**: {{source_label}} ({{source_platform}})
- **Model page**: {{source_url}}
- **Model file path**: {{model_path}}
- **Model filename**: {{model_basename}}
- **Repository ID**: {{source_id}}
- **Repository raw-file base URL**: {{asset_base_url}}

## Current Metadata (may be incomplete)

```json
{{current_metadata}}
```

## Site-Provided Metadata (any field may be empty)

The model site publishes the following **alongside** the README. It is
first-hand information recorded by the site itself, so it outranks anything
you would otherwise guess:

- **Author description**: {{source_description}}
- **Base model reported by the site**: {{source_base_model}}
- **Trigger words recorded for this file**: {{source_trigger_words}}
- **Site-curated tags**:
{{source_official_tags}}
- **Example image URLs for this file**:
{{source_example_images}}

Use it as follows:

- A weight or strength range stated in the **author description** belongs in
  ``usage_tips`` (and in ``notes``); do not leave ``usage_tips`` empty when the
  description states one.
- When the author description exists, base ``short_description`` on it rather
  than on the README, which on some sites is auto-generated boilerplate.
- Treat the **site-curated tags** as strong signals for ``tags``: they are
  already a curated content vocabulary, so prefer them over invented words.
- Treat the **base model reported by the site** as a strong hint for
  ``base_model``, but still map it to the EXACT canonical name from the
  available base-model list.
- Use the **example image URLs** when the README contains no usable image.

## User Priority Tags Reference

The user has configured the following list of **meaningful tag categories** for this model type (`{{model_type}}`):

```
{{priority_tags}}
```

These are the subjects, styles, and concepts the user considers useful for categorization. Use this list as a **reference** when evaluating tags (see the **tags** section below).

## Available Base Models

The following base models are currently valid in this system.  Use the EXACT
name listed — do not invent aliases or modify variant suffixes.

{{base_models}}

## Model Card Content

```
{{readme_content}}
```

## Extraction Instructions

Extract the following information from the README content above:

### base_model
The base model this model was trained on. Use EXACTLY one of the names from the **Available Base Models** list above. Do not invent new names or use aliases.

Check the **base model reported by the site** (above) and the YAML frontmatter ``base_model:`` first. If neither yields a match, look at the **model filename** (``{{model_basename}}``), YAML ``tags:``, README title and first paragraph for clues — the base model family is often embedded in the name

### trigger_words
The trigger words or activation prompts needed to use this LoRA. Look for:
- The **trigger words recorded for this file** in the site-provided metadata (most authoritative)
- `instance_prompt:` in the YAML frontmatter
- Phrases like "trigger word:", "trigger:", "use this prompt:", "activation prompt:"
- In collection repos: the trigger section **specific to this model file** (look near matching download links or anchor IDs)
- Example prompts at the start (usually the first word or phrase before any description)
Return as an array of strings. If none found, return an empty array `[]`. **Never** return `["None"]` or any placeholder value — a truly empty list means no trigger words exist.

### short_description
A concise 1-2 sentence summary of what this model does. For collection repos, focus on the **specific model version** matching `{{model_basename}}`, not the repo as a whole.  Prefer the **author description** from the site-provided metadata when it is present; otherwise extract from the "Model description" section or the first paragraph.  Return empty string if the available content is too minimal.

### tags
3-8 relevant tags for categorizing this model. **Quality over quantity.**

Sources to consider:
- The **site-curated tags** from the site-provided metadata (these are already filtered content tags — prefer them)
- The YAML frontmatter `tags:` list (filter out technical ones — see below)
- The subject, style, character, or concept the model represents
- The model filename itself may give clues (e.g. "pokemon", "anime", "pixelart")

**Critical filtering rules — apply them strictly:**

1. **Exclude technical/generic tags.** Reject any tag that describes the model's **training methodology, framework, architecture, or modality** rather than its content. Examples to exclude: `text-to-image`, `diffusers`, `lora`, `dreambooth`, `diffusers-training`, `flux`, `sdxl`, `checkpoint`, `pytorch`, `safetensors`, `fine-tuning`, `stable-diffusion`, and any variant of these.

2. **Cross-reference against the priority_tags reference.** Only include a tag if it meaningfully describes what the model actually creates (subject, style, character type) and is semantically close to one of the priority_tags. If none of the README's tags match meaningful categories, prefer returning a smaller set or an empty array over including low-value tags.

3. **All lowercase, and keep each tag's own wording.** Prefer the spelling already used by the site, the frontmatter, or the author — including hyphenated and multi-word tags such as `"sci-fi"`, `"semi-realistic"`, `"character-enhancement"` or `"art style"`. Do **not** strip separators or invent a single-word variant of a tag you are already including (e.g. do not emit both `"character-enhancement"` and `"character"`). When a tag is written in another script (e.g. Chinese), likewise keep it verbatim instead of translating it.

4. **Never invent a tag** that neither the site-provided metadata, the YAML frontmatter, nor the README text supports.

Return empty array if no meaningful content tags remain after filtering.

### recommended_width, recommended_height
The recommended image generation resolution for this model, in pixels. Look for sections like "Best Dimensions", "Recommended size", "Suggested resolution", or similar phrasing in the README. Prefer the explicitly marked "Best" or default resolution. If the table/list has multiple entries (e.g. "768 x 1024 (Best)" and "1024 x 1024 (Default)"), use the one marked "Best". Return integers. If no resolution can be determined, return 0 for both.

### preview_url
The URL of the most suitable preview image from the README. Look for:
- Image tags near the section matching the model filename (`{{model_basename}}`)
- The YAML frontmatter `widget:` section (which often has `output.url` fields)
- In collection repos: the sample images listed **under the section** for this specific model version
- Generic `![alt](url)` in the body
Choose the first image that appears to be a generation example (not a logo or diagram). Construct the absolute URL from the repository raw-file base URL (`{{asset_base_url}}`) plus the relative path. If the README has no suitable image, fall back to the site-provided **example image URLs** for this file. If nothing is available, return an empty string.

### notes
A plain-text summary of the model card's key practical usage information. Combine trigger words, style modifiers, recommended parameters (steps, CFG, resolution, sampler), and any setup tips into a readable paragraph.  For collection repos, focus on the **specific model version** matching `{{model_basename}}`.  Include the **author description** from the site-provided metadata when it is present.  Return empty string if there is no useful usage info.

### usage_tips
A JSON string with structured usage recommendations. Extract from the **author description** (site-provided metadata) and the README any explicit ranges or recommended values (e.g. "Set LoRA strength: **0.85 - 1.4**", "CLIP strength: 0.5", "权重0.5-1.2"). Possible fields (include only those you can determine):

```json
{
  "strength_min": 0.85,
  "strength_max": 1.4,
  "strength_range": "0.85-1.4",
  "strength": 0.6,
  "clip_strength": 0.5,
  "clip_skip": 2
}
```

Return the JSON string (e.g. `'{"strength_min":0.85,"strength_max":1.4}'`). Return `"{}"` if nothing useful is found.

### confidence
Your confidence level in the extracted data:
- "high" — most fields were explicitly stated in the README
- "medium" — some fields were inferred from context
- "low" — most fields are guesses based on limited information

## Important: Handling Collection Repos (multiple model files)

Many model repositories contain **multiple model files** in a single repository
(e.g. a "LoRA collection" with different styles/characters in separate files).

The model file currently being enriched is: **`{{model_basename}}`**

To find the correct section in the README:

1. **Search for download links** containing the filename — the surrounding paragraph is your section.
2. **Search for anchor IDs** (`<a id="...">`) or section headings whose text matches words from the filename.
3. **Search for HTML headings** (`<h1>`, `<h2>`, `<span>`) containing parts of the filename.
4. If no match is found, use the full README as usual — the model may be the only one in the repo.

When a matching section IS found, prefer metadata from that section.
When no section matches (e.g. single-model repos or repos without per-file sections),
extract metadata from the full README normally.  Do not return empty data just
because the filename doesn't appear in the README.

## Output Format

Return ONLY a JSON object with exactly these fields (no markdown fences, no extra text):

```json
{
  "model_path": "{{model_path}}",
  "base_model": "<canonical name or empty string>",
  "trigger_words": ["<word1>", "<word2>"],
  "short_description": "<1-2 sentence summary>",
  "tags": ["<tag1>", "<tag2>"],
  "recommended_width": 768,
  "recommended_height": 1024,
  "preview_url": "<image URL or empty string>",
  "notes": "<plain-text usage summary or empty string>",
  "usage_tips": "<JSON string like '{\"strength_min\":0.85,\"strength_max\":1.4}' or '{}'>",
  "confidence": "<high|medium|low>"
}
```

Important:
- Only include the JSON object, no other text
- If a field cannot be determined, use an empty string or empty array
- Do not fabricate information not supported by the README
- Never use placeholder values like `"None"` or `"unknown"` for missing data — use empty string or empty array

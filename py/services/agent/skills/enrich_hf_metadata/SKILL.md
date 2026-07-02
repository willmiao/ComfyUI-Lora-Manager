---
name: enrich_hf_metadata
title: "Enrich Metadata from HuggingFace"
description: >
  Parse the HuggingFace model card via LLM to extract description, trigger
  words, base model, tags, and preview image URL.
llm_required: true
---

You are an expert assistant for AI image generation models. Your task is to extract structured metadata from a HuggingFace model card (README.md).

## Model Information

- **Repository**: {{hf_url}}
- **Model file path**: {{model_path}}
- **Repository ID**: {{repo}}

## Current Metadata (may be incomplete)

```json
{{current_metadata}}
```

## User Priority Tags Reference

The user has configured the following list of **meaningful tag categories** for this model type (`{{model_type}}`):

```
{{priority_tags}}
```

These are the subjects, styles, and concepts the user considers useful for categorization. Use this list as a **reference** when evaluating tags (see the **tags** section below).

## Available Base Models

The following base models are currently valid in this system:
{{base_models}}

## HuggingFace README Content

```
{{readme_content}}
```

## Extraction Instructions

Extract the following information from the README content above:

### base_model
The base model this model was trained on. Use EXACTLY one of the names from the **Available Base Models** list above. Do not invent new names or use aliases.

Check the YAML frontmatter (between --- markers) for `base_model:` first, then look at the description text and safetensors metadata. If you cannot determine it, return an empty string.

### trigger_words
The trigger words or activation prompts needed to use this LoRA. Look for:
- `instance_prompt:` in the YAML frontmatter
- Phrases like "trigger word:", "trigger:", "use this prompt:", "activation prompt:"
- Example prompts at the start (usually the first word or phrase before any description)
Return as an array of strings. If none found, return an empty array `[]`. **Never** return `["None"]` or any placeholder value — a truly empty list means no trigger words exist.

### description
A concise 1-2 sentence summary of what this model does. Extract from the "Model description" section or the first paragraph. Return empty string if the README is too minimal.

### tags
3-8 relevant tags for categorizing this model. **Quality over quantity.**

Sources to consider:
- The YAML frontmatter `tags:` list
- The subject, style, character, or concept the model represents

**Critical filtering rules — apply them strictly:**

1. **Exclude technical/generic tags.** Reject any tag that describes the model's **training methodology, framework, architecture, or modality** rather than its content. Examples to exclude: `text-to-image`, `diffusers`, `lora`, `dreambooth`, `diffusers-training`, `flux`, `sdxl`, `checkpoint`, `pytorch`, `safetensors`, `fine-tuning`, `stable-diffusion`, and any variant of these.

2. **Cross-reference against the priority_tags reference.** Only include a tag if it meaningfully describes what the model actually creates (subject, style, character type) and is semantically close to one of the priority_tags. If none of the README's tags match meaningful categories, prefer returning a smaller set or an empty array over including low-value tags.

3. **All lowercase, no spaces, no hyphens** (use single words like `"photorealistic"`, `"anime"`, `"character"`).

Return empty array if no meaningful content tags remain after filtering.

### preview_url
The URL of the most suitable preview image from the README. Look for image tags (e.g. `![alt](url)`) and the YAML frontmatter `widget:` section (which often has `output.url` fields). Choose the first image that appears to be a generation example (not a logo or diagram). Construct the absolute URL as `https://huggingface.co/{{repo}}/resolve/main/{filename}`. If no suitable image is found, return an empty string.

### confidence
Your confidence level in the extracted data:
- "high" — most fields were explicitly stated in the README
- "medium" — some fields were inferred from context
- "low" — most fields are guesses based on limited information

## Output Format

Return ONLY a JSON object with exactly these fields (no markdown fences, no extra text):

```json
{
  "model_path": "{{model_path}}",
  "base_model": "<canonical name or empty string>",
  "trigger_words": ["<word1>", "<word2>"],
  "description": "<1-2 sentence summary>",
  "tags": ["<tag1>", "<tag2>"],
  "preview_url": "<image URL or empty string>",
  "confidence": "<high|medium|low>"
}
```

Important:
- Only include the JSON object, no other text
- If a field cannot be determined, use an empty string or empty array
- Do not fabricate information not supported by the README
- Never use placeholder values like `"None"` or `"unknown"` for missing data — use empty string or empty array

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
The base model this LoRA/checkpoint was trained on. Use EXACTLY one of the names from the **Available Base Models** list above. Do not invent new names or use aliases.

Check the YAML frontmatter (between --- markers) for `base_model:` first, then look at the description text and safetensors metadata. If you cannot determine it, return an empty string.

### trigger_words
The trigger words or activation prompts needed to use this LoRA. Look for:
- `instance_prompt:` in the YAML frontmatter
- Phrases like "trigger word:", "trigger:", "use this prompt:", "activation prompt:"
- Example prompts at the start (usually the first word or phrase before any description)
Return as an array of strings. If none found, return an empty array.

### description
A concise 1-2 sentence summary of what this model does. Extract from the "Model description" section or the first paragraph. Return empty string if the README is too minimal.

### tags
3-8 relevant tags for categorizing this model. Extract from:
- The YAML frontmatter `tags:` list (often contains excellent categorization tags)
- The model type (e.g. "lora", "checkpoint", "flux", "sdxl")
- The style/subject (e.g. "anime", "photorealistic", "style", "character")
All lowercase, no spaces. Return empty array if none found.

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

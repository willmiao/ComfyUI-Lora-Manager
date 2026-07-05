# HF Metadata Enrichment Validation Report

Generated: 2026-07-06 00:01:38
Models evaluated: **46**
Successful enrichments: **46**
Failures: **0**

## Preprocessing Audit

| Metric | Value |
|--------|-------|
| Models audited | 46 |
| README fetch failed | 0 |
| Section extraction activated | 19.6% |
| Basename found in section | 43.5% |
| Has YAML frontmatter | 100.0% |
| Has YAML widget section | 25.0% |
| Avg README compression | 41.1% |
| Avg cleaned length | 1812 chars |

### Audit Flags (most frequent)

- **SECTION_EXTRACTION_NOT_ACTIVATED**: 37x
- **BASENAME_NOT_IN_EXTRACTED_SECTION**: 1x

**Interpretation:**

- ⚠️ Section extraction activated for fewer than 50% of repos. This may indicate the basename doesn't match README content, or the repos are mostly single-model (where full README is expected).
- ⚠️ The safetensors basename was NOT found in the extracted section for many repos. This could mean the section extraction matched the wrong section, or the README doesn't explicitly reference the filename.

## ⚠️ Configuration Warnings

- ✅ LLM config matches between pipeline --settings and LLMService.

## Timing

- Total wall time: **544 s** 
  (9.1 min)
- Mean per model: **11.8 s**
- Median per model: **10.1 s**
- Fastest: **6.3 s**
- Slowest: **74.7 s**

## Overall Score Distribution  (0–100)

| Metric | Value |
|--------|-------|
| Mean   | 69.0 |
| Median | 70.0 |
| Min    | 30 |
| Max    | 90 |

- **Excellent (≥80)**: 16 models (34.8%)
- **Good (60–79)**: 18 models (39.1%)
- **Fair (40–59)**: 10 models (21.7%)
- **Poor (20–39)**: 2 models (4.3%)
- **Bad (<20)**: 0 models (0.0%)

## Per-Field Completeness

| Field | Mean Score | Fill Rate | Empty Rate |
|-------|-----------:|----------:|-----------:|
| base_model | 11.7 | 78.3% | 21.7% |
| trigger_words | 8.8 | 58.7% | 41.3% |
| short_description | 8.7 | 87.0% | 13.0% |
| tags | 14.3 | 95.7% | 4.3% |
| tags_priority_coverage | 3.9 | 71.7% | 13.0% |
| notes | 3.8 | 76.1% | 23.9% |
| usage_tips | 0.8 | 15.2% | 84.8% |
| modelDescription_html | 9.6 | 95.7% | 4.3% |
| preview_downloaded | 7.4 | 73.9% | 26.1% |

## LLM Confidence Distribution

- **high**: 14  ██████░░░░░░░░░░░░░░  30.4%
- **medium**: 21  █████████░░░░░░░░░░░  45.7%
- **low**: 11  █████░░░░░░░░░░░░░░░  23.9%
- **(not reported)**: 0  ░░░░░░░░░░░░░░░░░░░░  0.0%

## Most Frequent Issues

- **usage_tips is empty or invalid JSON** — 39/46 (84.8%)
- **trigger_words are missing or contain only placeholders** — 19/46 (41.3%)
- **preview image not downloaded (URL missing or download failed)** — 12/46 (26.1%)
- **notes are too short or empty** — 11/46 (23.9%)
- **base_model is empty or 'Unknown'** — 7/46 (15.2%)
- **short_description is too short or empty** — 6/46 (13.0%)
- **tags have low overlap with priority_tags (< 50%)** — 4/46 (8.7%)
- **tags are missing, too few, or purely technical** — 2/46 (4.3%)
- **modelDescription is too short (README may not have been converted)** — 2/46 (4.3%)
- **base_model 'Tongyi-MAI/Z-Image-Turbo' not in SUPPORTED_BASE_MODELS** — 1/46 (2.2%)
- **base_model 'Illustrious-xl-early-release-v0' not in SUPPORTED_BASE_MODELS** — 1/46 (2.2%)
- **base_model 'Pony SDXL' not in SUPPORTED_BASE_MODELS** — 1/46 (2.2%)

## Optimisation Suggestions

- **trigger_words 空置率高 (41%)**: 大量 HF 模型卡没有明确的 `instance_prompt:` 或 trigger word 说明。当前 prompt 已覆盖常见模式。若确认这些模型确实没有 trigger words（例如 style lora），空数组是正确结果，不需优化。
- **usage_tips 空置率极高 (85%)**: 这是预期行为。HF 模型卡通常不包含 LoRA 强度/CLIP skip 等结构化参数。当前提取策略已合理。若需要可用数据，可以考虑使用模型类型的通用默认值。

## Per-Model Detail

<details>
<summary>Click to expand</summary>

| # | Repo ID | Score | Issues | Confidence |
|---|---------|------:|--------|------------|
| 1 | k2styles/krea-2-cobalt-sky-anime-lora | 90 | ✓ ok | high |
| 2 | k2styles/krea-2-azure-gouache-daylight-lora | 87 | ✓ ok | high |
| 3 | TheDivergentAI/krea2-turbo-distill-lora | 70 | 2 issue(s) | medium |
| 4 | DeverStyle/Krea2-Loras | 65 | 2 issue(s) | medium |
| 5 | Komorebi1995/krea2-raw-jpaf-celpaint-lora | 90 | ✓ ok | medium |
| 6 | artificialguybr/pixelartredmond-1-5v-pixel-art-loras-for-sd-1-5 | 72 | 2 issue(s) | medium |
| 7 | Shakker-Labs/FLUX.1-dev-LoRA-Logo-Design | 90 | ✓ ok | high |
| 8 | glif-loradex-trainer/bingbangboom_flux_surf | 65 | 2 issue(s) | medium |
| 9 | prithivMLmods/Ton618-Epic-Realism-Flux-LoRA | 85 | 1 issue(s) | high |
| 10 | prithivMLmods/Fashion-Hut-Modeling-LoRA | 85 | 1 issue(s) | high |
| 11 | prithivMLmods/Retro-Pixel-Flux-LoRA | 80 | 2 issue(s) | medium |
| 12 | D1-3105/HiDream-E1-Full_lora | 55 | 4 issue(s) | low |
| 13 | renderartist/Classic-Painting-Z-Image-Turbo-LoRA | 70 | 2 issue(s) | medium |
| 14 | DeverStyle/Z-Image-loras | 55 | 3 issue(s) | medium |
| 15 | deadman44/Z-Image_LoRA | 55 | 4 issue(s) | low |
| 16 | zyuzuguldu/vton-lora-linen | 75 | 2 issue(s) | medium |
| 17 | svntax-dev/pixel_spritesheet_4walk_small_lora_v1 | 67 | 2 issue(s) | high |
| 18 | Haruka041/z-image-anime-lora | 55 | 4 issue(s) | low |
| 19 | systms/SYSTMS-INFL8-LoRA-Wan22 | 85 | 1 issue(s) | medium |
| 20 | crafiq/flux-2-klein-9b-360-panorama-lora | 85 | 1 issue(s) | medium |
| 21 | Leon1000/pixel_spritesheet_4walk_small_lora_v1 | 67 | 2 issue(s) | high |
| 22 | Muapi/pov-missionary-legs-together-lora | 70 | 2 issue(s) | medium |
| 23 | ostris/ideogram_4_unconditional_lora | 60 | 3 issue(s) | medium |
| 24 | ilkerzgi/krea-2-bleached-surreal-uncanny-lora | 85 | 1 issue(s) | high |
| 25 | ilkerzgi/krea-2-azure-surreal-collage-lora | 88 | ✓ ok | high |
| 26 | ilkerzgi/krea-2-airy-gouache-minimalist-lora | 82 | 1 issue(s) | high |
| 27 | k2styles/krea-2-airy-watercolor-chibi-lora | 90 | ✓ ok | high |
| 28 | TakeAswing/sdxl-lora-lofi | 50 | 5 issue(s) | medium |
| 29 | heville/anna-lora-krea2 | 85 | 1 issue(s) | high |
| 30 | Brioch/krea2_loras | 35 | 6 issue(s) | low |
| 31 | hr16/Miwano-Rag-LoRA | 75 | 2 issue(s) | medium |
| 32 | ikuseiso/Personal_Lora_collections | 30 | 6 issue(s) | low |
| 33 | Tanger/LoraByTanger | 55 | 3 issue(s) | medium |
| 34 | DS-Archive/ds-LoRA | 60 | 3 issue(s) | medium |
| 35 | soknife/loras | 70 | 2 issue(s) | low |
| 36 | prompthero/openjourney-lora | 75 | 2 issue(s) | medium |
| 37 | Banano/banchan-lora | 40 | 5 issue(s) | low |
| 38 | Maisman/No-Game-NoLife-LoRAs | 70 | 2 issue(s) | medium |
| 39 | EarthnDusk/Gambit_Xmen_Anime_Lora_V1.1 | 50 | 4 issue(s) | low |
| 40 | EarthnDusk/DuskfallArt_LoRa | 40 | 6 issue(s) | low |
| 41 | gaoxiao/pokemon-lora | 65 | 3 issue(s) | medium |
| 42 | wtcherr/sd-unsplash_10k_canny-model-control-lora | 65 | 3 issue(s) | low |
| 43 | wtcherr/sd-unsplash_10k_blur_rand_KS-model-control-lora | 65 | 3 issue(s) | medium |
| 44 | samurai-architects/lora-starbucks | 50 | 4 issue(s) | low |
| 45 | prithivMLmods/Flux-Long-Toon-LoRA | 85 | 1 issue(s) | high |
| 46 | Limbicnation/pixel-art-lora | 87 | ✓ ok | high |

</details>

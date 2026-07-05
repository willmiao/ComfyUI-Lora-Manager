---
tags:
  - text-to-image
  - lora
  - diffusers
  - krea2
  - distillation
  - template:diffusion-lora
license: other
license_name: krea-2-community-license
license_link: https://huggingface.co/krea/Krea-2-Turbo/blob/main/LICENSE.pdf
base_model: krea/Krea-2-Raw
---

# Krea-2 Turbo Distillation LoRA (SVD Extract)

Post-hoc LoRA adapters extracted from the weight delta between [krea/Krea-2-Turbo](https://huggingface.co/krea/Krea-2-Turbo) and [krea/Krea-2-Raw](https://huggingface.co/krea/Krea-2-Raw).

For each 2D weight matrix in the Krea-2 transformer, we compute `ΔW = W_turbo − W_raw` and factor it with truncated SVD (`torch.svd_lowrank`, q=256) into low-rank `lora_A` / `lora_B` pairs. The goal is to approximate turbo behavior on the **Raw** base model without swapping the full 24 GB checkpoint.

**Experimental.** This is not an official Krea release. Distillation is not purely low-rank, and turbo inference also depends on scheduler settings (8 steps, CFG=0, mu≈1.15).

## Files in this repo

| File | Rank | Size | Notes |
|------|------|------|-------|
| `krea2_turbo_distill_r64.safetensors` | 64 | ~0.47 GB | Smallest; rougher fit |
| `krea2_turbo_distill_r128.safetensors` | 128 | ~0.94 GB | **Recommended starting point** |
| `krea2_turbo_distill_r256.safetensors` | 256 | ~1.87 GB | Closest fit; largest file |
| `extraction_report.json` | — | ~15 KB | Per-layer reconstruction metrics |

Each LoRA file contains **530 tensors** (265 layers × `lora_A` + `lora_B`).

## Reconstruction quality

Approximation error for the 2D weight delta (lower is better):

| Rank | Global recon error | Mean singular energy captured |
|------|-------------------|-------------------------------|
| 64 | 46.1% | 86.8% |
| 128 | 41.5% | 93.6% |
| 256 | 36.6% | 100%* |

\*Energy is computed from the top-256 singular components returned by `svd_lowrank(q=256)`.

Worst-fit layers tend to be text/timestep MLP projections (`txtmlp.*`, `tmlp.*`, `tproj.*`). See `extraction_report.json` for per-layer details.

## Visual comparison gallery

Side-by-side rank comparisons on **Krea-2 Raw** with turbo distill LoRA at **8 steps, CFG 0, mu 1.15**. Each grid shows the prompt and metadata (top-left), then **Rank 256**, **Rank 128**, and **Rank 64** outputs for the same seed and settings.

| Panel | Content |
|-------|---------|
| Top-left | Prompt + generation settings |
| Top-right | Rank 256 output |
| Bottom-left | Rank 128 output |
| Bottom-right | Rank 64 output |

### Chroma Aperture

**Rocket Launch Exhaust** · 9:16

![01. Rocket Launch Exhaust (9:16)](gallery/01_rocket_launch_exhaust.webp)

**Designer Toy Figure** · 1:1

![02. Designer Toy Figure (1:1)](gallery/02_designer_toy_figure.webp)

**Vintage Analog Collage** · 5:4

![03. Vintage Analog Collage (5:4)](gallery/03_vintage_analog_collage.webp)

**Anime Portrait Smile** · 3:4

![04. Anime Portrait Smile (3:4)](gallery/04_anime_portrait_smile.webp)

**Ocean Wading Illustration** · 9:21

![05. Ocean Wading Illustration (9:21)](gallery/05_ocean_wading_illustration.webp)

### Light Spill

**Tree and Dog Landscape** · 16:9

![06. Tree and Dog Landscape (16:9)](gallery/06_tree_and_dog_landscape.webp)

**Portrait with Lilies** · 4:5

![07. Portrait with Lilies (4:5)](gallery/07_portrait_with_lilies.webp)

**Harvest Mouse Macro** · 3:2

![08. Harvest Mouse Macro (3:2)](gallery/08_harvest_mouse_macro.webp)

**Sailor Girl Motion** · 2:3

![09. Sailor Girl Motion (2:3)](gallery/09_sailor_girl_motion.webp)

**Coastal Convertible Sunset** · 4:3

![10. Coastal Convertible Sunset (4:3)](gallery/10_coastal_convertible_sunset.webp)

### Split Spectrum

**Stone Guardian Ruin** · 9:16

![11. Stone Guardian Ruin (9:16)](gallery/11_stone_guardian_ruin.webp)

**Jungle Fox Tapestry** · 21:9

![12. Jungle Fox Tapestry (21:9)](gallery/12_jungle_fox_tapestry.webp)

**Retro Chrome Spaceface** · 16:9

![13. Retro Chrome Spaceface (16:9)](gallery/13_retro_chrome_spaceface.webp)

**Gold Ribbon Portrait** · 2:3

![14. Gold Ribbon Portrait (2:3)](gallery/14_gold_ribbon_portrait.webp)

**Menacing Jester Fantasy** · 1:1

![15. Menacing Jester Fantasy (1:1)](gallery/15_menacing_jester_fantasy.webp)

### Analog Echo

**Fashion Editorial Crimson** · 4:5

![16. Fashion Editorial Crimson (4:5)](gallery/16_fashion_editorial_crimson.webp)

**Ink Faces Landscape** · 3:4

![17. Ink Faces Landscape (3:4)](gallery/17_ink_faces_landscape.webp)

**Vintage Anime Crowd** · 3:2

![18. Vintage Anime Crowd (3:2)](gallery/18_vintage_anime_crowd.webp)

**Windy Anime Portrait** · 4:3

![19. Windy Anime Portrait (4:3)](gallery/19_windy_anime_portrait.webp)

**Moody Close-Up Portrait** · 1:1

![20. Moody Close-Up Portrait (1:1)](gallery/20_moody_close_up_portrait.webp)

### Signal Grid

**Turbo Distill Keynote Hero** · 3:4

![21. Turbo Distill Keynote Hero (3:4)](gallery/21_turbo_distill_keynote_hero.webp)

**Rank Ladder Laboratory** · 3:4

![22. Rank Ladder Laboratory (3:4)](gallery/22_rank_ladder_laboratory.webp)

**Eight-Step Horizon** · 3:4

![23. Eight-Step Horizon (3:4)](gallery/23_eight_step_horizon.webp)

**Neural Condenser Array** · 3:4

![24. Neural Condenser Array (3:4)](gallery/24_neural_condenser_array.webp)

**Raw Versus Turbo Split** · 3:4

![25. Raw Versus Turbo Split (3:4)](gallery/25_raw_versus_turbo_split.webp)

## How to use

1. Load the **Krea-2-Raw** transformer (not Turbo) with [ComfyUI](https://github.com/comfy-org/comfyui) or HuggingFace diffusers.
2. Apply one of the LoRA files above on the diffusion transformer.
3. Generate with turbo-style settings:
   - **Steps:** 8
   - **CFG / guidance scale:** 0
   - **Timestep shift mu:** 1.15 (recommended for turbo)

Start with **`krea2_turbo_distill_r128.safetensors`**. Use r256 if you need a tighter weight approximation; use r64 only if VRAM or file size is constrained.

### Key format

Keys follow the ComfyUI Krea2 LoRA convention:

```
diffusion_model.blocks.0.attn.wq.lora_A.weight
diffusion_model.blocks.0.attn.wq.lora_B.weight
```

LoRA alpha equals rank (64, 128, or 256 respectively).

## Caveats

- **Approximation, not identity.** These adapters recover part of the Raw→Turbo weight shift; they do not guarantee pixel-level parity with native Turbo.
- **Scheduler matters.** Turbo expects few-step, CFG-free sampling. Match turbo settings when evaluating.
- **Official Krea workflow.** Krea recommends training LoRAs on Raw and running them on Turbo. These adapters explore making Raw behave more like Turbo via an extracted weight delta.

## Method

- SVD low-rank extraction on `(W_turbo − W_raw)` per 2D layer
- Source checkpoints: [krea/Krea-2-Raw](https://huggingface.co/krea/Krea-2-Raw), [krea/Krea-2-Turbo](https://huggingface.co/krea/Krea-2-Turbo)

## License

These adapters are derived from Krea-2 weights and inherit the [Krea-2 community license](https://huggingface.co/krea/Krea-2-Turbo/blob/main/LICENSE.pdf). See Krea licensing for commercial use terms.

## Citation

If you use Krea-2, please cite the Krea team:

```bibtex
@misc{krea-2-2026,
  author = {Sangwu Lee and Erwann Millon and Le Zhuo and others},
  title = {{Krea 2}},
  year = {2026},
  howpublished = {\url{https://www.krea.ai/blog/krea-2-technical-report}}
}
```

Base models:

- [krea/Krea-2-Raw](https://huggingface.co/krea/Krea-2-Raw)
- [krea/Krea-2-Turbo](https://huggingface.co/krea/Krea-2-Turbo)

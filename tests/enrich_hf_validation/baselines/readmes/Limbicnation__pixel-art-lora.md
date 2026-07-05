---
language:
- en
license: apache-2.0
library_name: diffusers
tags:
- lora
- flux
- pixel-art
- game-asset
- sprite
- character-design
- text-to-image
- FLUX.2-klein-4B
base_model: black-forest-labs/FLUX.2-klein-4B
datasets:
- Limbicnation/pixel-art-character
pipeline_tag: text-to-image
widget:
- text: "pixel art sprite, a brave knight in shining armor holding a sword, game asset, transparent background"
  output:
    url: samples/01_a_brave_knight_in_shining_armor_holding_.png
- text: "pixel art sprite, a fire-breathing dragon with red scales, game asset, transparent background"
  output:
    url: samples/06_a_fire-breathing_dragon_with_red_scales_.png
- text: "pixel art sprite, a cute slime monster, blue and bouncy, game asset, transparent background"
  output:
    url: samples/07_a_cute_slime_monster_blue_and_bouncy.png
---

# Pixel Art Sprite LoRA for FLUX.2-klein-4B

A LoRA adapter trained on FLUX.2-klein-4B for generating pixel art character sprites. Optimized for game-ready assets with transparent backgrounds.

## Highlights

- **4-step inference** — FLUX.2-klein is distilled, so generation is fast
- **512x512 RGBA** output with transparent backgrounds
- **CC0 training data** — 100% public domain, no copyright concerns
- **Game-ready** — designed for Godot, Unity, and other engines

## Quick Start

### Trigger Words

Always include in your prompt:

```
pixel art sprite, [your character description], game asset, transparent background
```

**Style modifiers:** `16-bit pixel art`, `32-bit pixel art`, `chibi`

### Inference Parameters

| Parameter | Value |
|-----------|-------|
| Steps | 4 |
| CFG Scale | 1.0 |
| Resolution | 512x512 |
| Sampler | Euler |

### Python (Diffusers)

> Requires `diffusers >= 0.37.0.dev0` (install from git main)

```python
import torch
from diffusers import Flux2KleinPipeline

# Load base model + LoRA
pipe = Flux2KleinPipeline.from_pretrained(
    "black-forest-labs/FLUX.2-klein-4B",
    torch_dtype=torch.bfloat16,
    low_cpu_mem_usage=False,
)
pipe.load_lora_weights("Limbicnation/pixel-art-lora")
pipe.to("cuda")

image = pipe(
    "pixel art sprite, a brave knight in shining armor, game asset, transparent background",
    num_inference_steps=4,
    guidance_scale=1.0,
    height=512,
    width=512,
).images[0]

image.save("knight.png")
```

### ComfyUI

1. Download the LoRA weights:
   ```bash
   huggingface-cli download Limbicnation/pixel-art-lora \
       pytorch_lora_weights.safetensors \
       --local-dir ./models/loras/
   ```
2. Load FLUX.2-klein-4B as the base checkpoint
3. Add a **Load LoRA** node, point to `pytorch_lora_weights.safetensors`
4. Set LoRA strength: **0.85 - 1.4** (tested range)
5. Use trigger words in your positive prompt

A sample workflow is included: [`comfyui_workflow.json`](./comfyui_workflow.json)

## Training Details

| Parameter | Value |
|-----------|-------|
| Base model | `black-forest-labs/FLUX.2-klein-4B` |
| LoRA rank | 64 |
| LoRA alpha | 128 |
| rsLoRA | Yes |
| Dtype | bfloat16 |
| Steps | 1000 |
| Batch size | 1 |
| Gradient accumulation | 4 |
| Learning rate | 1e-4 |
| LR scheduler | Cosine with restarts |
| Optimizer | AdamW 8-bit |
| Resolution | 512x512 |
| Dataset | 500 images (CC0 curated + synthetic) |

## Architecture Notes

FLUX.2-klein-4B uses a different architecture from FLUX.1:

- **Text encoder:** Qwen3 (not CLIP+T5)
- **Pipeline class:** `Flux2KleinPipeline` (not `FluxPipeline`)
- **VAE:** `AutoencoderKLFlux2`
- **Distilled:** 4-step inference with guidance scale 1.0

## License

This LoRA adapter is released under [Apache 2.0](./LICENSE).

The base model (FLUX.2-klein-4B) is also Apache 2.0 licensed.

## Citation

```bibtex
@misc{pixel-art-lora-2026,
  title={Pixel Art Sprite LoRA for FLUX.2-klein-4B},
  author={Limbicnation},
  year={2026},
  url={https://huggingface.co/Limbicnation/pixel-art-lora}
}
```

## Links

- **Model:** [Limbicnation/pixel-art-lora](https://huggingface.co/Limbicnation/pixel-art-lora)
- **Dataset:** [Limbicnation/pixel-art-character](https://huggingface.co/datasets/Limbicnation/pixel-art-character)
- **Base model:** [black-forest-labs/FLUX.2-klein-4B](https://huggingface.co/black-forest-labs/FLUX.2-klein-4B)
- **Training code:** [Limbicnation/SpriteForge](https://github.com/Limbicnation/SpriteForge)

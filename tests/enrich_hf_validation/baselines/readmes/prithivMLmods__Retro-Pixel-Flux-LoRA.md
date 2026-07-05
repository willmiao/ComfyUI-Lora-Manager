---
tags:
- text-to-image
- lora
- diffusers
- template:diffusion-lora
- Retro
- Pixel
widget:
- text: >-
    Retro Pixel, A pixelated image of a german shepherd dog. The dogs fur is a
    vibrant shade of brown, with a black stripe running down its back. The
    background is a light green, and the dogs shadow is cast on the ground.
  output:
    url: images/RP1.png
- text: >-
    Retro Pixel, A pixelated image of a man surfing on a surfboard. The mans
    body is covered in a red shirt and blue shorts. His arms are out to the
    sides of his body. The surfboard is a vibrant blue color. The water is a
    light blue color with white splashes. The sun is shining on the right side
    of the image.
  output:
    url: images/RP2.png
- text: >-
    Retro Pixel, pixel art of a Hamburger in the style of an old video game,
    hero, pixelated 8bit, final boss 
  output:
    url: images/RP3.png
base_model: black-forest-labs/FLUX.1-dev
instance_prompt: Retro Pixel
license: creativeml-openrail-m
---
# Retro-Pixel-Flux-LoRA

<Gallery />

- Hosted Here🧨: https://huggingface.co/spaces/prithivMLmods/FLUX-LoRA-DLC

**The model is still in the training phase. This is not the final version and may contain artifacts and perform poorly in some cases.**

## Model description 

**prithivMLmods/Retro-Pixel-Flux-LoRA**

Image Processing Parameters 

| Parameter                 | Value  | Parameter                 | Value  |
|---------------------------|--------|---------------------------|--------|
| LR Scheduler              | constant | Noise Offset              | 0.03   |
| Optimizer                 | AdamW  | Multires Noise Discount   | 0.1    |
| Network Dim               | 64     | Multires Noise Iterations | 10     |
| Network Alpha             | 32     | Repeat & Steps           | 24 & 2340|
| Epoch                     | 15  | Save Every N Epochs       | 1      |

    Labeling: florence2-en(natural language & English)
    
    Total Images Used for Training : 16 [ Hi-RES ]

![prithivMLmods/Retro-Pixel-Flux-LoRA](images/RP4.webp)
    
## Best Dimensions

- 1024 x 1024 (Default)
  
## Setting Up
```
import torch
from pipelines import DiffusionPipeline

base_model = "black-forest-labs/FLUX.1-dev"
pipe = DiffusionPipeline.from_pretrained(base_model, torch_dtype=torch.bfloat16)

lora_repo = "prithivMLmods/Retro-Pixel-Flux-LoRA"
trigger_word = "Retro Pixel"  
pipe.load_lora_weights(lora_repo)

device = torch.device("cuda")
pipe.to(device)
```
## Trigger words

You should use `Retro Pixel` to trigger the image generation.

## Download model

Weights for this model are available in Safetensors format.

[Download](/prithivMLmods/Retro-Pixel-Flux-LoRA/tree/main) them in the Files & versions tab.
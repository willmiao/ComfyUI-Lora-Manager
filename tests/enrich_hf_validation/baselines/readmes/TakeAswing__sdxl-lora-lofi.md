---
license: apache-2.0
base_model: stabilityai/stable-diffusion-xl-base-1.0
pipeline_tag: text-to-image
library_name: diffusers
tags:
- sdxl
- lora
- diffusers
- text-to-image
datasets:
- TakeAswing/LoFi-image-pixabay
---

# SDXL LoRA - Lofi

This repository contains a LoRA adapter trained on Stable Diffusion XL.

## Base Model

- stabilityai/stable-diffusion-xl-base-1.0

## Usage

```python
import torch
from diffusers import StableDiffusionXLPipeline

pipe = StableDiffusionXLPipeline.from_pretrained(
    "stabilityai/stable-diffusion-xl-base-1.0",
    torch_dtype=torch.float16
).to("cuda")

pipe.load_lora_weights("YOUR_USERNAME/sdxl-lora-lofi")

image = pipe(
    "LofiAnimeStyle, A cozy studyroom at night with rain outside",
    num_inference_steps=30,
).images[0]

image.save("output.png")
```

## Files

- `pytorch_lora_weights.safetensors`
- `adapter_config.json`
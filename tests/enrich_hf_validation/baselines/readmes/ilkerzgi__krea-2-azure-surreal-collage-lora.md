---
language:
- en
base_model:
- krea/Krea-2-Turbo
pipeline_tag: text-to-image
library_name: diffusers
license: other
license_name: krea-2-community-license
license_link: https://huggingface.co/krea/Krea-2-LoRA-impressionist/blob/main/LICENSE.pdf
instance_prompt: azure surreal collage style
tags:
- lora
- text-to-image
- krea
- krea-2
- fal-ai
- template:diffusion-lora
- cinematic
widget:
- text: "a lighthouse on a rocky cliff. azure surreal collage style"
  output:
    url: images/ex_1.png
- text: "a lighthouse on a rocky cliff. azure surreal collage style"
  output:
    url: images/ex_2.png
- text: "a lighthouse on a rocky cliff. azure surreal collage style"
  output:
    url: images/ex_3.png
- text: "a lighthouse on a rocky cliff. azure surreal collage style"
  output:
    url: images/ex_4.png
- text: "a lighthouse on a rocky cliff. azure surreal collage style"
  output:
    url: images/ex_5.png
---
<picture>
  <source media="(prefers-color-scheme: dark)" srcset="https://huggingface.co/ilkerzgi/krea-2-azure-surreal-collage-lora/resolve/main/fal-dark.png">
  <img src="https://huggingface.co/ilkerzgi/krea-2-azure-surreal-collage-lora/resolve/main/fal-light.png" alt="fal" height="18">
</picture>

# Azure Surreal Collage

**fal · Krea 2 Style LoRA series.** One of 1600+ style LoRAs trained on [fal](https://fal.ai).

A **Krea 2** style LoRA. Add the trigger **`azure surreal collage style`** to the end of your prompt.

[![Run on fal.ai](https://img.shields.io/badge/Run_on-fal.ai-FF6B35?style=for-the-badge)](https://fal.ai/models/fal-ai/krea-2/turbo/lora) [![Train on fal.ai](https://img.shields.io/badge/Train_on-fal.ai-FF6B35?style=for-the-badge)](https://fal.ai/models/fal-ai/krea-2-trainer) [![Krea 2](https://img.shields.io/badge/base-Krea_2_Turbo-7C5CFF?style=for-the-badge)](https://huggingface.co/krea/Krea-2-Turbo)

<Gallery />

## Quick start

| Parameter | Value |
|-----------|-------|
| Trigger | `azure surreal collage style` |
| Recommended LoRA scale | `1.0` to `1.25` |
| Base model | `krea/Krea-2-Turbo` |
| Trained on | [fal-ai/krea-2-trainer](https://fal.ai/models/fal-ai/krea-2-trainer) |

## Inference on fal

### Python
```python
import fal_client

result = fal_client.subscribe(
    "fal-ai/krea-2/turbo/lora",
    arguments={
        "prompt": "a lighthouse on a rocky cliff. azure surreal collage style",
        "loras": [{"path": "https://huggingface.co/ilkerzgi/krea-2-azure-surreal-collage-lora/resolve/main/azure-surreal-collage.safetensors", "scale": 1.0}],
        "image_size": {"width": 1024, "height": 1280},
    },
)
print(result["images"][0]["url"])
```

### JavaScript
```js
import { fal } from "@fal-ai/client";

const { data } = await fal.subscribe("fal-ai/krea-2/turbo/lora", {
  input: {
    prompt: "a lighthouse on a rocky cliff. azure surreal collage style",
    loras: [{ path: "https://huggingface.co/ilkerzgi/krea-2-azure-surreal-collage-lora/resolve/main/azure-surreal-collage.safetensors", scale: 1.0 }],
    image_size: { width: 1024, height: 1280 },
  },
});
console.log(data.images[0].url);
```

## Train your own on fal

Every LoRA in this series is trained on [`fal-ai/krea-2-trainer`](https://fal.ai/models/fal-ai/krea-2-trainer) (100 steps, learning rate 3.5e-4). Train your own style from 4 to 10 reference images:

```python
import fal_client

result = fal_client.subscribe(
    "fal-ai/krea-2-trainer",
    arguments={
        "images_data_url": "https://.../your-dataset.zip",
        "trigger_phrase": "azure surreal collage style",
        "steps": 100,
        "learning_rate": 0.00035,
    },
)
print(result)
```

## License

Krea 2 Community License. See the [license](https://huggingface.co/krea/Krea-2-LoRA-impressionist/blob/main/LICENSE.pdf).

## ComfyUI

A ComfyUI-compatible copy of the weights is included in this repo: **`azure-surreal-collage-comfy.safetensors`**. It is the
exact same LoRA with the key prefix remapped (`base_model.model.` to `diffusion_model.`) so
ComfyUI loads it directly. Download that file into `ComfyUI/models/loras/` and use it like
any other LoRA. The original `azure-surreal-collage.safetensors` is for [fal](https://fal.ai) / diffusers.


---
tags:
- text-to-image
- lora
- diffusers
- template:diffusion-lora
widget:
- text: 'Epic Realism, A medium-angle shot of a woman with long, wavy brown hair, a black long-sleeved t-shirt, and a black necklace around her neck. Her eyes are a piercing blue, and her lips are a lighter pink. She is standing in front of a white wall with a window on the left side of the wall. The window is slightly open, and the wall is a light gray color. The womans hair is a darker shade of brown, and she has a slight smile on her face.'
  output:
    url: images/ep1.png
- text: 'Epic Realism, Captured in a close-up, eye-level perspective, a medium-sized young mans face is adorned with a gold necklace, adding a touch of sparkle to his outfit. His eyes are a piercing blue, and his hair is a mix of brown and black. His eyebrows are a darker shade of brown, while his lips are a lighter shade of pink. The backdrop is blurred, creating a stark contrast to the foreground.'
  output:
    url: images/ep2.png
- text: 'Epic Realism, A close-up shot of a young woman with long brown hair and blue eyes. She is wearing a red and white cheerleading uniform. The uniform has a white stripe down the center of the uniform. Her hair is pulled back and cascades over her shoulders. Her eyes are a piercing blue. Her lips are painted a light pink color. Her eyebrows are a darker shade of brown. Her nose is a lighter shade of blue. The background is blurred, but it is out of focus.'
  output:
    url: images/ep3.png
base_model: black-forest-labs/FLUX.1-dev
instance_prompt: Epic Realism
license: creativeml-openrail-m
---
# Ton618-Epic-Realism-Flux-LoRA

<Gallery />

**The model is still in the training phase. This is not the final version and may contain artifacts and perform poorly in some cases.**

## Model description 

**prithivMLmods/Ton618-Epic-Realism-Flux-LoRA**

Image Processing Parameters 

| Parameter                 | Value  | Parameter                 | Value  |
|---------------------------|--------|---------------------------|--------|
| LR Scheduler              | constant | Noise Offset              | 0.03   |
| Optimizer                 | AdamW  | Multires Noise Discount   | 0.1    |
| Network Dim               | 64     | Multires Noise Iterations | 10     |
| Network Alpha             | 32     | Repeat & Steps           | 25 & 3000|
| Epoch                     | 15    | Save Every N Epochs       | 1      |

    Labeling: florence2-en(natural language & English)
    
    Total Images Used for Training : 22 [ Hi-RES ]

## Best Dimensions

- 1024 x 1024 (Default)
    
## Setting Up
```
import torch
from pipelines import DiffusionPipeline

base_model = "black-forest-labs/FLUX.1-dev"
pipe = DiffusionPipeline.from_pretrained(base_model, torch_dtype=torch.bfloat16)

lora_repo = "prithivMLmods/Ton618-Epic-Realism-Flux-LoRA"
trigger_word = "Epic Realism"  
pipe.load_lora_weights(lora_repo)

device = torch.device("cuda")
pipe.to(device)
```

## Data source
    
    - https://playground.com/
    
## Trigger words

You should use `Epic Realism` to trigger the image generation.

## Download model

Weights for this model are available in Safetensors format.

[Download](/prithivMLmods/Ton618-Epic-Realism-Flux-LoRA/tree/main) them in the Files & versions tab.

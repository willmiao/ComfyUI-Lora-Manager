---
tags:
- text-to-image
- lora
- diffusers
- template:diffusion-lora
- Long-Toons
- 3D
- Toon
widget:
- text: >-
    Long toons, a close-up of a cartoon characters face is featured in a vibrant
    red backdrop. The characters head is adorned with a gray hoodie, a red
    t-shirt, and a pair of pink earbuds. His eyes, a nose, and mustache are
    adorned with tiny white dots, adding a pop of color to the scene. His hair
    is a mix of black and gray, while his ears are a darker shade of pink.
  output:
    url: images/LT4.png
- text: >-
    Long toons, Super Detail, a close-up shot of a womans head and shoulders is
    seen against a vibrant red backdrop. The womans face is adorned with a white
    face, adorned with blue eyes, and her brown hair cascades over her
    shoulders. She is wearing a red turtleneck, with a ribbed collar. Her lips
    are painted a vibrant shade of red, adding a pop of color to her face. Her
    eyebrows are a darker shade of blue, addinga depth to the composition.
  output:
    url: images/LT5.png
- text: >-
    Long Toons, Cat 4K
    ........................................................................................................................................................................................
  output:
    url: images/LT6.png
- text: >-
    Long toons, a close-up portrait of a soccer player is depicted. The players
    uniform is a light blue and white striped jersey with the Adidas logo on the
    left side of the chest. The jersey also has three stars and the letters
    "AFA" on the right side. His hair is styled in a mohawk, adding a pop of
    color to his face. The background is blurred, suggesting a sports field.
  output:
    url: images/LT1.png
- text: >-
    Long toons, Captured at eye-level, a close-up shot of a black-haired doll
    with dreadlocks stands in front of a blurred backdrop of a cityscape. The
    dolls head is facing the viewer, and its eyes are squinted with black
    eyebrows and black eyes, and the dolls mouth is slightly open, as if it is
    frowning. His eyes are a piercing blue, and he is wearing a black hoodie
    with a white design on the front, adding a pop of color to the scene. The
    background is a mix of red and black, creating a vibrant contrast to the
    doll.
  output:
    url: images/LT2.png
- text: >-
    Long toons, Captured at eye-level on a sunny day, a mario figurine rests on
    a sandy beach. The figurine, dressed in a red cap, a red shirt, and blue
    overalls, is adorned with a yellow button. His hands are covered in white
    gloves, adding a touch of warmth to the scene. In the distance, a body of
    water can be seen, dotted with white clouds. The sky is a deep blue, with a
    few wispy white clouds streaming across it.
  output:
    url: images/LT3.png
base_model: black-forest-labs/FLUX.1-dev
instance_prompt: Long toons
license: creativeml-openrail-m
---
# Flux-Long-Toon-LoRA

<Gallery />

**The model is still in the training phase. This is not the final version and may contain artifacts and perform poorly in some cases.**

## Model description 

**prithivMLmods/Flux-Long-Toon-LoRA**

Image Processing Parameters 

| Parameter                 | Value  | Parameter                 | Value  |
|---------------------------|--------|---------------------------|--------|
| LR Scheduler              | constant | Noise Offset              | 0.03   |
| Optimizer                 | AdamW  | Multires Noise Discount   | 0.1    |
| Network Dim               | 64     | Multires Noise Iterations | 10     |
| Network Alpha             | 32     | Repeat & Steps           | 25 & 3270 |
| Epoch                     | 18    | Save Every N Epochs       | 1     |

    Labeling: florence2-en(natural language & English)
    
    Total Images Used for Training : 15

## Best Dimensions

- 768 x 1024 (Best)
- 1024 x 1024 (Default)
    
## Setting Up
```python
import torch
from pipelines import DiffusionPipeline

base_model = "black-forest-labs/FLUX.1-dev"
pipe = DiffusionPipeline.from_pretrained(base_model, torch_dtype=torch.bfloat16)

lora_repo = "prithivMLmods/Flux-Long-Toon-LoRA"
trigger_word = "Long toons"  
pipe.load_lora_weights(lora_repo)

device = torch.device("cuda")
pipe.to(device)
```
## Trigger words

You should use `Long toons` to trigger the image generation.

## Download model

Weights for this model are available in Safetensors format.

[Download](/prithivMLmods/Flux-Long-Toon-LoRA/tree/main) them in the Files & versions tab.

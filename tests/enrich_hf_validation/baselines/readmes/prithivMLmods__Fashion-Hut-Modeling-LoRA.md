---
tags:
- text-to-image
- lora
- diffusers
- template:diffusion-lora
- PG-13
- Fashion
- Modeling
- Realism
- Photography
widget:
- text: >-
    Modeling of Photo of a woman with long brown hair, wearing a pink sports
    bra, standing against a plain white background, looking over her shoulder
    with a serious expression, medium close-up, fair skin, slender physique,
    small breasts, soft lighting, high quality, jpeg artifacts, no watermark, no
    text, no tattoos, no piercings, no makeup, no jewelry, no accessories, no
    background, no shadows, no highlights, no reflections, no lens flare, no
    bokeh, no depth of field, no blur, no grain, no noise, no compression, no
    artifacts, no compression artifacts, no noise artifacts, no grain artifacts,
    no blur artifacts, no depth of field artifacts, no highlights artifacts, no
    shadows artifacts, no lens flare artifacts, no reflections artifacts
  output:
    url: images/MO1.png
- text: >-
    Modeling fashion photograph of a model posing minimalist set, model is
    styled in a streetwear yet chic outfit consisting of a over-fit grey
    sweat-shirt tucked into dark olive cargo jogger, background is a smooth,
    crimson, providing a contrast that highlights the outfit, lighting is strong
    yet directional, accentuating the texture of the fabric and the sleek fit of
    the pants, emphasize the confidence pose of the model, with hands up behind
    head, capturing a relaxed yet fashionable streetwear vibe, UHD --ar 9:16
    --stylize 500
  output:
    url: images/MO2.png
- text: "Modeling of a bold Japanese hyperrealistic advertising poster features a stunning Asian model with sleek, blonde hair cut in an extraordinary style that frames her angular face. She exudes confidence while wearing modern, oversized coloured baggy jeans paired with a matching loose-fitting top in another colour. The outfit is accentuated with chunky white sneakers and layered gold necklaces, blending street style with effortless chic. She stands in front of a futuristic urban background with neon signs and soft glowing lanterns, set against a sleek cityscape at night. Behind her, cherry blossoms softly fall, contrasting with the modern environment. Bold kanji characters in dynamic, graffiti-like style read â\x80\x9Cè\x87ªç\x94±ã\x81ªç¾\x8E - The Freedom of Beautyâ\x80\x9D across the top. The posterâ\x80\x99s aesthetic merges contemporary fashion with traditional Japanese elements, creating an energetic, youthful vibe."
  output:
    url: images/MO4.png
base_model: black-forest-labs/FLUX.1-dev
instance_prompt: Modeling of
license: creativeml-openrail-m
---
# Fashion-Hut-Modeling-LoRA : [👗]

<Gallery />

- Hosted Here🧨: https://huggingface.co/spaces/prithivMLmods/FLUX-LoRA-DLC

**The model is still in the training phase. This is not the final version and may contain artifacts and perform poorly in some cases.**

## Model description 

**prithivMLmods/Fashion-Hut-Modeling-LoRA**

Image Processing Parameters 

| Parameter                 | Value  | Parameter                 | Value  |
|---------------------------|--------|---------------------------|--------|
| LR Scheduler              | constant | Noise Offset              | 0.03   |
| Optimizer                 | AdamW  | Multires Noise Discount   | 0.1    |
| Network Dim               | 64     | Multires Noise Iterations | 10     |
| Network Alpha             | 32     | Repeat & Steps           | 26 & 2900|
| Epoch                     | 16  | Save Every N Epochs       | 1      |

    Labeling: florence2-en(natural language & English)
    
    Total Images Used for Training : 14 [ Hi-RES ]
--------------------------------------------------------------------

![prithivMLmods/Fashion-Hut-Modeling-LoRA](images/MOS.png)

| Description |
|--------------------|
| Modeling Photo of a woman with long brown hair, wearing a orange sports bra, standing against a plain white background, looking over her shoulder with a serious expression, medium close-up, fair skin, slender physique, small breasts, soft lighting, high quality, jpeg artifacts, no watermark, no text, no tattoos, no piercings, no makeup, no jewelry, no accessories, no background, no shadows, no highlights, no reflections, no lens flare, no bokeh, no depth of field, no blur, no grain, no noise, no compression, no artifacts, no compression artifacts, no noise artifacts, no grain artifacts, no blur artifacts, no depth of field artifacts, no highlights artifacts, no shadows artifacts, no lens flare artifacts, no reflections artifacts,  sweaty body glistens in the light |
## Best Dimensions

- 1024 x 1024 (Default)
  
## Setting Up
```
import torch
from pipelines import DiffusionPipeline

base_model = "black-forest-labs/FLUX.1-dev"
pipe = DiffusionPipeline.from_pretrained(base_model, torch_dtype=torch.bfloat16)

lora_repo = "prithivMLmods/Fashion-Hut-Modeling-LoRA"
trigger_word = "Modeling of"  
pipe.load_lora_weights(lora_repo)

device = torch.device("cuda")
pipe.to(device)
```
## Trigger words

You should use `Modeling of` to trigger the image generation.

## Download model

Weights for this model are available in Safetensors format.

[Download](/prithivMLmods/Fashion-Hut-Modeling-LoRA/tree/main) them in the Files & versions tab.
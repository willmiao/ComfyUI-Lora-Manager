---
tags:
- text-to-image
- stable-diffusion
- lora
- diffusers
- image-generation
- flux
- safetensors
widget:
- text: logo,Minimalist,A man stands in front of a door,his shadow forming the word "A",
  output:
    url: images/01.png
- text: logo,Minimalist,A pair of chopsticks and a bowl of rice with the word "Lee",
  output:
    url: images/02.png
- text: wablogo,Minimalist,Leaf and cat,logo,
  output:
    url: images/03.png
base_model: black-forest-labs/FLUX.1-dev
instance_prompt: wablogo, logo, Minimalist
license: other
license_name: flux-1-dev-non-commercial-license
license_link: https://huggingface.co/black-forest-labs/FLUX.1-dev/blob/main/LICENSE.md
---
# FLUX.1-dev-LoRA-Logo-Design

This is a LoRA (Logo-Design) trained on FLUX.1-dev by [CJim](https://www.shakker.ai/userpage/b43e5cc7fcd64d2bbde42c6e889267cc/publish) on [Shakker AI](https://www.shakker.ai/modelinfo/0355942f9bd140a99e371ba5731894e8?from=personal_page).
<div class="container">
  <img src="./poster.jpg" width="1024"/>
</div>

## Showcases
<Gallery />


## Trigger words

You should use `wablogo, logo, Minimalist` as trigger words. The recommended scale is `0.8` in diffusers.

## Usage suggestion
- Dual Combination: something and something, e.g., cat and coffee,

- Font Combination: a shape plus a letter, e.g., a book with the word "M," or The fingerprint pattern consists of the letters "hp,"

- Text Below Graphic: Below the graphic is the word "coffee," directly using with the word "XX" is also feasible

## Inference

```python
import torch
from diffusers import FluxPipeline

pipe = FluxPipeline.from_pretrained("black-forest-labs/FLUX.1-dev", torch_dtype=torch.bfloat16)
pipe.load_lora_weights("Shakker-Labs/FLUX.1-dev-LoRA-Logo-Design", weight_name="FLUX-dev-lora-Logo-Design.safetensors")
pipe.fuse_lora(lora_scale=0.8)
pipe.to("cuda")

prompt = "logo,Minimalist,A bunch of grapes and a wine glass"
image = pipe(prompt, 
             num_inference_steps=24, 
             guidance_scale=3.5,
            ).images[0]
image.save(f"example.png")
```

## Online Inference

You can also download this model at [Shakker AI](https://www.shakker.ai/modelinfo/0355942f9bd140a99e371ba5731894e8?from=personal_page), where we provide an online interface to generate images.


## Acknowledgements
This model is trained by our copyrighted users [CJim](https://www.shakker.ai/userpage/b43e5cc7fcd64d2bbde42c6e889267cc/publish). We release this model under permissions. The model follows [flux-1-dev-non-commercial-license](https://huggingface.co/black-forest-labs/FLUX.1-dev/blob/main/LICENSE.md).

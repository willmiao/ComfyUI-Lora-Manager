---
base_model: krea/Krea-2-Raw
tags:
- text-to-image
- diffusers
- lora
- krea2
- template:sd-lora
license: apache-2.0
instance_prompt: "ANNA_LORA"
widget:
- text: "A hyper-realistic portrait of ANNA_LORA wearing an ornate gold masquerade mask, standing in a candlelit Venetian ballroom with shimmering reflections on the marble floor."
  output:
    url: sample_0.png
- text: "ANNA_LORA as a futuristic cyberpunk pilot, wearing a neon-lined flight suit inside a cockpit filled with holographic displays and raining city lights outside."
  output:
    url: sample_1.png
- text: "A cinematic shot of ANNA_LORA in a flowing white linen dress, walking through a sun-drenched lavender field in Provence under a soft pastel sky."
  output:
    url: sample_2.png
---

# Krea 2 LoRA — heville/anna-lora-krea2

<Gallery />

A DreamBooth-LoRA for **Krea 2**, trained on **Krea 2 RAW** and shown on **Krea 2 Turbo**. The samples below were generated with this LoRA on Turbo (8 steps).

## Trigger

Use the token `ANNA_LORA` to invoke the concept.

## Samples

![sample](./sample_0.png)

> *"A hyper-realistic portrait of ANNA_LORA wearing an ornate gold masquerade mask, standing in a candlelit Venetian ballroom with shimmering reflections on the marble floor."*

![sample](./sample_1.png)

> *"ANNA_LORA as a futuristic cyberpunk pilot, wearing a neon-lined flight suit inside a cockpit filled with holographic displays and raining city lights outside."*

![sample](./sample_2.png)

> *"A cinematic shot of ANNA_LORA in a flowing white linen dress, walking through a sun-drenched lavender field in Provence under a soft pastel sky."*

## Use it with diffusers

```py
import torch
from diffusers import Krea2Pipeline

pipe = Krea2Pipeline.from_pretrained("krea/Krea-2-Turbo", torch_dtype=torch.bfloat16).to("cuda")
pipe.load_lora_weights("heville/anna-lora-krea2")
image = pipe("A hyper-realistic portrait of ANNA_LORA wearing an ornate gold masquerade mask, standing in a candlelit Venetian ballroom with shimmering reflections on the marble floor.", num_inference_steps=8, guidance_scale=0.0).images[0]
image.save("output.png")
```

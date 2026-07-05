---
license: openrail++
library_name: diffusers
base_model: OnomaAIResearch/Illustrious-xl-early-release-v0
tags:
  - lora
  - text-to-image
  - stable-diffusion-xl
  - illustrious
  - illustrious
pipeline_tag: text-to-image
---

# POV Missionary-Legs Together | LoRA

![preview](./preview.jpg)

**Base model**: Illustrious
**Trained words**: sex, missionary, pov

## 🧠 Usage (Python)

🔑 **Get your MUAPI key** from [muapi.ai/access-keys](https://muapi.ai/access-keys)

```python
import requests, os
url = "https://api.muapi.ai/api/v1/sdxl-lora-image"
headers = {"Content-Type": "application/json", "x-api-key": os.getenv("MUAPIAPP_API_KEY")}
payload = {
    "prompt": "masterpiece, best quality",
    "lora_model": "pov-missionary-legs-together-lora",
    "lora_strength": 1.0,
    "width": 1024,
    "height": 1024,
    "num_images": 1
}
print(requests.post(url, headers=headers, json=payload).json())
```

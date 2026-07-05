---
license: other
license_name: ideogram-4-non-commercial
license_link: https://huggingface.co/ideogram-ai/ideogram-4-fp8/blob/main/LICENSE.md
tags:
  - text-to-image
  - lora
  - diffusers
base_model: ideogram-ai/ideogram-4-fp8

---
# Ideogram 4 Unconditional LoRA

This is a LoRA that was initialized by extracting the difference of the Ideogram 4 conditional and unconditional model weights. 
It was further tuned using student teacher training on real data and a loss was performed on a per layer basis to more closely
match the unconditional model. This can be used on the conditional Ideogram 4 model during the unconditional pass 
as a replacement to the full 9B paramiter unconditional model. 

Using the full unconditional model will likely yield better results, but this will work as a light weight alternative. It was 
originally trained to be used in [Ostris AI Toolkit](https://github.com/ostris/ai-toolkit) so samples would be more in line 
with what the full pipeline would produce without needing to load the entire unconditional model. 
---
license: apache-2.0
library_name: diffusers
tags:
- lora
- text-to-image
- diffusers
- virtual-try-on
- fashion
- fabric-texture
- linen
base_model: stabilityai/stable-diffusion-xl-base-1.0
instance_prompt: a garment with linen fabric texture
widget:
- text: "a garment with linen fabric texture"
  output:
    url: "placeholder.png"
---

# Virtual Try-On LoRA: Linen

<div align="center">
  <img src="https://img.shields.io/badge/Type-LoRA-blue" alt="Type">
  <img src="https://img.shields.io/badge/Fabric-Linen-purple" alt="Fabric">
  <img src="https://img.shields.io/badge/Base-SDXL-green" alt="Base Model">
  <img src="https://img.shields.io/badge/License-Apache%202.0-yellow" alt="License">
</div>

## 📋 Model Description

This is a **LoRA (Low-Rank Adaptation)** model fine-tuned for generating realistic **Linen** fabric textures in virtual try-on applications. The model has been trained on high-quality linen texture images to capture the unique characteristics of this fabric type.

### Key Features

- 🎨 **Specialized for Linen**: Captures authentic fabric texture and appearance
- 🚀 **Lightweight**: Only 3.1 MB - efficient for deployment
- 🎯 **SDXL-based**: Built on Stable Diffusion XL for high-quality generation
- 👔 **Virtual Try-On Ready**: Designed for fashion and garment visualization
- ⚡ **Fast Inference**: LoRA architecture enables quick generation

## 🎯 Intended Use

### Primary Use Cases

1. **Virtual Try-On Systems**: Apply linen textures to garment designs
2. **Fashion Design**: Visualize how garments look with linen fabric
3. **E-commerce**: Generate product images with different fabric textures
4. **Style Transfer**: Transfer linen texture to existing garment images

### Out of Scope

- General-purpose image generation
- Non-fabric texture generation
- Photo-realistic face generation

## 🚀 Quick Start

### Installation

```bash
pip install diffusers transformers accelerate safetensors
```

### Basic Usage

```python
from diffusers import DiffusionPipeline
import torch

# Load base model
pipe = DiffusionPipeline.from_pretrained(
    "stabilityai/stable-diffusion-xl-base-1.0",
    torch_dtype=torch.float16,
    variant="fp16"
)
pipe.to("cuda")

# Load LoRA weights
pipe.load_lora_weights(
    "zyuzuguldu/vton-lora-linen",
    weight_name="pytorch_lora_weights.safetensors"
)

# Generate image
prompt = "a garment with linen fabric texture, high quality, detailed"
image = pipe(
    prompt,
    num_inference_steps=30,
    guidance_scale=7.5
).images[0]

image.save("output.png")
```

### Advanced Usage with Multiple LoRAs

```python
from diffusers import DiffusionPipeline
import torch

pipe = DiffusionPipeline.from_pretrained(
    "stabilityai/stable-diffusion-xl-base-1.0",
    torch_dtype=torch.float16
).to("cuda")

# Load with custom weight
pipe.load_lora_weights(
    "zyuzuguldu/vton-lora-linen",
    weight_name="pytorch_lora_weights.safetensors",
    adapter_name="linen"
)

# Set LoRA scale (0.0 to 1.0)
pipe.set_adapters(["linen"], adapter_weights=[0.8])

# Generate
prompt = "a stylish jacket with linen texture, fashion photography"
negative_prompt = "blurry, low quality, distorted"

image = pipe(
    prompt,
    negative_prompt=negative_prompt,
    num_inference_steps=40,
    guidance_scale=8.0
).images[0]

image.save("styled_garment.png")
```

### Using with Virtual Try-On Pipeline

```python
from diffusers import StableDiffusionXLInpaintPipeline
import torch

# Load inpainting pipeline for try-on
pipe = StableDiffusionXLInpaintPipeline.from_pretrained(
    "stabilityai/stable-diffusion-xl-base-1.0",
    torch_dtype=torch.float16
).to("cuda")

# Load LoRA
pipe.load_lora_weights("zyuzuguldu/vton-lora-linen")

# Apply texture to masked garment area
result = pipe(
    prompt="garment with linen fabric",
    image=original_image,
    mask_image=garment_mask,
    num_inference_steps=30
).images[0]
```

## 📊 Training Details

### Training Data

- **Dataset**: [lora-garment-textures](https://huggingface.co/datasets/zyuzuguldu/lora-garment-textures)
- **Category**: Linen
- **Images**: High-resolution linen fabric texture samples
- **Resolution**: Variable (resized to 1024x1024 for training)

### Training Configuration

- **Base Model**: Stable Diffusion XL 1.0
- **LoRA Rank**: 15
- **Training Framework**: Diffusers + PEFT
- **Optimizer**: AdamW
- **Training Steps**: ~2000-8000 (varied by category)
- **Hardware**: GPU-accelerated training

### Hyperparameters

```yaml
learning_rate: 1e-4
lora_rank: 15
lora_alpha: 15
batch_size: 4
resolution: 1024x1024
mixed_precision: fp16
gradient_accumulation_steps: 4
```

## 📁 Model Files

- **pytorch_lora_weights.safetensors** (3.1 MB): Main LoRA weights in SafeTensors format

## 🎨 Prompt Engineering Tips

### Recommended Prompts

```
"a garment with linen fabric texture, high quality, detailed"
"stylish clothing made of linen material, professional photography"
"fashion design with linen texture, studio lighting"
"linen fabric garment, detailed texture, 4k quality"
```

### Negative Prompts

```
"blurry, low quality, distorted, unrealistic, artificial"
"pixelated, noisy, artifacts, bad texture"
```

### Tips

1. **Texture Keywords**: Include words like "fabric", "texture", "material" for best results
2. **Quality Modifiers**: Add "high quality", "detailed", "4k" for better outputs
3. **LoRA Weight**: Adjust between 0.6-1.0 for strength control
4. **Inference Steps**: Use 30-50 steps for balanced quality/speed
5. **Guidance Scale**: 7.0-8.5 works well for most prompts

## ⚖️ Limitations and Bias

### Limitations

- Optimized specifically for linen textures
- May not generalize well to other fabric types
- Requires SDXL base model for best results
- Performance depends on prompt quality

### Potential Biases

- Training data may reflect specific regional or cultural fabric styles
- May perform better on certain garment types seen during training

## 📝 License

This model is released under the **Apache 2.0 License**.

- Free for commercial and non-commercial use
- Requires attribution to the original authors
- No warranty provided

## 🔗 Related Resources

### Models
- **Base Model**: [stabilityai/stable-diffusion-xl-base-1.0](https://huggingface.co/stabilityai/stable-diffusion-xl-base-1.0)
- **Other Textures**: [vton-lora-denim](https://huggingface.co/zyuzuguldu/vton-lora-denim), [vton-lora-linen](https://huggingface.co/zyuzuguldu/vton-lora-linen)
- **Segmentation Model**: [garment-segmentation-unet-resnet50](https://huggingface.co/zyuzuguldu/garment-segmentation-unet-resnet50)

### Datasets
- **Training Data**: [lora-garment-textures](https://huggingface.co/datasets/zyuzuguldu/lora-garment-textures)
- **Masks Dataset**: [deepfashion2-upper-body-masks](https://huggingface.co/datasets/zyuzuguldu/deepfashion2-upper-body-masks)

### Demos
- **Try It Out**: [garment-segmentation](https://huggingface.co/spaces/zyuzuguldu/garment-segmentation)

## 📚 Citation

If you use this model in your research or project, please cite:

```bibtex
@misc{vton_lora_linen,
  author = {zyuzuguldu},
  title = {Virtual Try-On LoRA: Linen},
  year = {2026},
  publisher = {Hugging Face},
  howpublished = {\url{https://huggingface.co/zyuzuguldu/vton-lora-linen}}
}
```

## 🤝 Contributing

Found an issue or want to improve the model? Feel free to reach out or open a discussion!

## 👨‍💻 Maintainer

Created and maintained by [@zyuzuguldu](https://huggingface.co/zyuzuguldu)

---

**Part of the Virtual Try-On Project**

Repository: [Virtual-Try-On](https://github.com/zyuzuguldu/Virtual-Try-On)

**Made with ❤️ for the fashion-tech and AI community**

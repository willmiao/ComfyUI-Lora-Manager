---
license: other
library_name: comfyui
pipeline_tag: text-to-image
tags:
- krea2
- lora
- safetensors
- style-lora
- comfyui
- jpaf-celpaint
---

# Krea2 Raw JPAF_CELPAINT LoRA

这是一个基于 Krea2 Raw 训练的 `JPAF_CELPAINT` 风格 LoRA，用于生成干净的 celpaint 画面：克制色彩、清晰线条、生活化背景，以及纸张、牌面、屏幕上的低密度不可读装饰痕迹。

- Hugging Face 模型仓库：https://huggingface.co/Komorebi1995/krea2-raw-jpaf-celpaint-lora
- GitHub 展示仓库：https://github.com/Hana19951208/krea2-raw-jpaf-celpaint-lora
- 英文说明：[README.en.md](README.en.md)
- 触发词：把 `JPAF_CELPAINT.` 放在 prompt 开头。

## 推荐用法

| 用途 | 文件 | 建议 strength | 说明 |
|---|---|---:|---|
| 默认推荐 | `krea2_raw_jpaf_celpaint_full_v1_000000750.safetensors` | `0.8` | 风格、线条、泛化和亮度最均衡。 |
| 备用 | `krea2_raw_jpaf_celpaint_full_v1_000001000.safetensors` | `0.6` | 更稳、更软一点，适合不想过强风格时用。 |
| 可用但偏暗 | `krea2_raw_jpaf_celpaint_full_v1_000001250.safetensors` | `0.6` | 画面更暗，默认不优先。 |
| final | `krea2_raw_jpaf_celpaint_full_v1.safetensors` | `0.6` | 1500 step final，可加载，但不作为默认推荐。 |

## 验证链路

验证图使用 Win11 本地 Krea2 Turbo ComfyUI 链生成：

```text
UNETLoader: krea2_turbo_fp8_scaled.safetensors
CLIPLoader: qwen3vl_4b_fp8_scaled.safetensors, type=krea2, device=default
VAELoader: qwen_image_vae.safetensors
LoraLoaderModelOnly: strength_model
ConditioningZeroOut negative
EmptyLatentImage: 1280x720
KSampler: euler/simple, steps=8, cfg=1, denoise=1
```

完整验证矩阵为 8 个 prompt x base + 750/1000/1250/1500_final 的 0.6/0.8/1.0，共 104 张。结论：`CONDITIONAL_PASS`。

## strength=0.8 step 对比

下面同一组 prompt 横向对比，纵向是 base / step 750 / step 1000 / step 1250 / step 1500 final。可以看到 step 越深，画面整体更暗，姿态和构图吸附也更强；因此默认推荐 step 750。

<img src="images/strength_0_8_step_comparison_grid.jpg" width="1100">

### base

<img src="images/base_strength_0_0_row.jpg" width="1100">

### step 750, strength 0.8

<img src="images/step_750_strength_0_8_row.jpg" width="1100">

### step 1000, strength 0.8

<img src="images/step_1000_strength_0_8_row.jpg" width="1100">

### step 1250, strength 0.8

<img src="images/step_1250_strength_0_8_row.jpg" width="1100">

### step 1500 final, strength 0.8

<img src="images/step_1500_final_strength_0_8_row.jpg" width="1100">

## 展示 prompt

### 城市黄昏

```text
JPAF_CELPAINT. A 16:9 single-frame celpaint scene of a quiet city shopping street at dusk, warm shop windows, damp pavement reflections, a small storefront sign with faint decorative marks, pedestrians in everyday clothing, clean linework, restrained colors, natural evening light.
```

### 公共中庭

```text
JPAF_CELPAINT. A 16:9 single-frame celpaint scene in a public library atrium with high windows, visitors moving calmly, wayfinding boards and notice panels carrying soft unreadable lettering, layered background details, balanced perspective, gentle daylight.
```

### 双人互动

```text
JPAF_CELPAINT. A 16:9 single-frame celpaint scene of two coworkers sharing lunch in a small back room, lunch boxes, tools, a receipt pad with subtle decorative lines, relaxed body language, layered props, soft overhead light, restrained celpaint shading.
```

### 空街泛化

```text
JPAF_CELPAINT. A 16:9 single-frame celpaint scene of an empty residential street in early morning, parked scooters, closed shutters, a notice board with subtle glyph-like marks, quiet air, clean edges, layered urban details, no central character.
```

### 新职业泛化

```text
JPAF_CELPAINT. A 16:9 single-frame celpaint scene of an airport security assistant helping a traveler arrange belongings at a checkpoint, trays, a small screen with an unreadable dark interface, soft fluorescent light, natural poses, detailed props, restrained color palette.
```

## 注意事项

- 不建议直接使用更深 checkpoint + 高 strength 作为默认组合，容易变暗。
- 不要在 prompt 中要求真实可读文字、logo、水印、品牌名。
- 牌面、纸张、屏幕建议写 `faint decorative marks`、`loose unreadable strokes`、`subtle glyph-like marks` 这类低密度不可读描述。

## License

`other`。请同时遵守 Krea2 Raw / Krea2 Turbo 及上游资产的许可约束。

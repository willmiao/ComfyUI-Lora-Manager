---
license: creativeml-openrail-m
tags:
- stable-diffusion
- text-to-image
---
## Lora for No Game No Life
---
<p align="center"><img src="https://media.vgm.io/products/29/2592/2592-1593945190.png">

# Table of Contents

- [Shiro](#shiro)
- [Izuna](#izuna)

---

# Shiro

Civitai: [Click here!](https://civitai.com/models/11520/shiro-lora-or-no-game-no-life)

How to use: 

# UPDATE
Shiro but now with her original Anime look! Just use
"ngnl style" in prompt to trigger her Anime style! I also added "ngnl background". This will try to add the feeling of the ngnl world and add its style too. 

Improvements: 

Better Anime look

She can now hold a chess piece (Okey sometimes but its better!)

Better enviroment

Better Shiro look. More detail

Better Backgrounds

Trigger Words same as before (version 1.0) + the new ones I mentioned on Civitai. I will add them here later. 


Trigger Words

hatsuse izuna, izuna, no game no life, kimono, hairband, fox ears, fox tail, 5 fingers, hands up, sitting, hands on face, open mouth, hand between legs, close face, blush, cards, 
```
hatsuse izuna, izuna, no game no life, kimono, hairband, fox ears, fox tail, 5 fingers, hands up, sitting, hands on face, open mouth, hand between legs, close face, blush, cards, 
```

Good weight ~0.5-0.6

High = Anime like (0.7-0.9))

Lower = Artwork like (0.5-0.6)

Download v1.0: [Shiro Lora](https://huggingface.co/Maisman/No-Game-NoLife-LoRAs/blob/main/MaismansShiroLora.safetensors)

Download v2.0: [Better Shiro Lora](https://huggingface.co/Maisman/No-Game-NoLife-LoRAs/blob/main/ShiroNGNL2_Lora.safetensors)

▼ Example Images ▼


<p align="center"><img src="https://huggingface.co/Maisman/No-Game-NoLife-LoRAs/resolve/main/images/01722-2106806252-((masterpiece%2C%20best%20quality_1.2))%2C%20(ultra-detailed_1.2)%2C%20%2C%20Shiro%2C%20shiro_(no_game_no_life)%2C%20No%20Game%20No%20Life%2C%20purple%20clothes%2C%20long.png">

Prompt: 
```
((masterpiece, best quality:1.2)), (ultra-detailed:1.2), <lora:MaismansShiroLora:0.6>, Shiro, shiro_(no_game_no_life), No Game No Life, purple clothes, long hair, purple thighhighs, long hair, 1girl,  blurry background, (crown), very_long_hair, blue background, (lying), Chess piece in background
```
Negative prompt: 
```
(nsfw, nude), (bad anatomy), extra limbs, lowres, destorced, (worst quality:1.4), (mouth open), (low quality:1.4), (trembling:1.4), (cropped head:1.4), (blurry), destorced hands,(disfigured), (bad hands, bad fingers, 1 finger, 2 fingers, 3 fingers, 6 fingers), watermark, wide hips, extra legs, bad legs,  (By bad artist -neg),
```
Steps: 30, Sampler: DPM++ 2M Karras, CFG scale: 5, Seed: 2106806252, Size: 512x768, Model: abyssorangemix2_Hardcore, Denoising strength: 0.6, Hires upscale: 2, Hires upscaler: Latent (antialiased)

---
<p align="center"><img src="https://huggingface.co/Maisman/No-Game-NoLife-LoRAs/resolve/main/images/00147-1572915960-(hand)%2C%20(5%20figers_1.6).png">

Prompt: 
```
((masterpiece, best quality)), (ultra-detailed), 5 fingers, illustration, <<lora:MaismansShiroLora:0.5>>, Shiro, shiro_(no_game_no_life), No Game No Life, long hair, purple thighhighs, long hair, 1girl,  blurry background, (crown), very_long_hair,  loli, blue background, (lying)
```
Negative prompt: 
```
bad anatomy, extra limbs, lowres, destorced, (worst quality:1.4), (mouth open), (low quality:1.4), (trembling:1.4), (cropped head:1.4), (blurry), destorced hands,(disfigured), ugly, bad hands, bad fingers, watermark, wide hips, extra legs, bad legs,  By bad artist -neg,  easynegative
```
Steps: 25, Sampler: DPM++ 2M Karras, CFG scale: 5, Seed: 2397796989, Size: 512x768, Model: abyssorangemix2_Hardcore, Denoising strength: 0.5, Hires upscale: 1.8, Hires upscaler: Latent


---
<p align="center"><img src="https://huggingface.co/Maisman/No-Game-NoLife-LoRAs/resolve/main/images/01593-111538347-masterpiece_best_quality_ultra-detailed_5_fingers_illustration__Shiro_shiro_no_game_no_life_No_Game_No_Life_lon.png">

Prompt: 
```
((masterpiece, best quality)), (ultra-detailed), 5 fingers, illustration, <lora:MaismansShiroLora:0.7>, Shiro, shiro_(no_game_no_life), No Game No Life, long hair, purple thighhighs, long hair, 1girl, blurry background, (crown), very_long_hair, loli, blue background, (lying),
```
Negative prompt: 
```
bad anatomy, extra limbs, lowres, destorced, (worst quality:1.4), (mouth open), (low quality:1.4), (trembling:1.4), (cropped head:1.4), (blurry), destorced hands,(disfigured), ugly, bad hands, bad fingers, watermark, wide hips, extra legs, bad legs, By bad artist -neg, easynegative
```
Steps: 20, Sampler: DPM++ 2M Karras, CFG scale: 5, Seed: 111538347, Size: 512x768, Model: abyssorangemix2_Hardcore, Denoising strength: 0.5, Hires upscale: 1.5, Hires upscaler: Latent


---
<p align="center"><img src="https://huggingface.co/Maisman/No-Game-NoLife-LoRAs/resolve/main/images/01604-1254898106-((masterpiece%2C%20best%20quality))%2C%20(ultra-detailed)%2C%205%20fingers%2C%20illustration%2C%20%2C%20Shiro%2C%20shiro_(no_game_no_life)%2C%20No%20Game%20No%20Life%2C%20lon.png">

Prompt: 
```
((masterpiece, best quality)), (ultra-detailed), 5 fingers, illustration, <lora:MaismansShiroLora:0.5>, Shiro, shiro_(no_game_no_life), No Game No Life, long hair, purple thighhighs, long hair, 1girl, blurry background, (crown), very_long_hair, loli, blue background, (lying),
```
Negative prompt: 
```
bad anatomy, extra limbs, lowres, destorced, (worst quality:1.4), (mouth open), (low quality:1.4), (trembling:1.4), (cropped head:1.4), (blurry), destorced hands,(disfigured), ugly, bad hands, bad fingers, watermark, wide hips, extra legs, bad legs, By bad artist -neg, easynegative
```
Steps: 25, Sampler: DPM++ 2M Karras, CFG scale: 5, Seed: 1254898106, Size: 512x768, Model: abyssorangemix2_Hardcore


---
<p align="center"><img src="https://huggingface.co/Maisman/No-Game-NoLife-LoRAs/resolve/main/images/01650-4277505990-((masterpiece%2C%20best%20quality))%2C%20(ultra-detailed)%2C%205%20fingers%2C%20illustration%2C%20%2C%20Shiro%2C%20shiro_(no_game_no_life)%2C%20No%20Game%20No%20Life%2C%20lon.png">

Prompt: 
```
((masterpiece, best quality)), (ultra-detailed), 5 fingers, illustration, <lora:MaismansShiroLora:0.6>, Shiro, shiro_(no_game_no_life), No Game No Life, long hair, purple thighhighs, long hair, 1girl, blurry background, (crown), very_long_hair, loli, blue background, (lying), cat ears, tail, (feet)
```
Negative prompt: 
```
NSFW, nude, bad anatomy, extra limbs, lowres, destorced, (worst quality:1.4), (mouth open), (low quality:1.4), (trembling:1.4), (cropped head:1.4), (blurry), destorced hands,(disfigured), ugly, bad hands, bad fingers, watermark, wide hips, extra legs, bad legs, (By bad artist -neg, (easynegative))
```
Steps: 25, Sampler: DPM++ 2M Karras, CFG scale: 5, Seed: 4277505990, Size: 512x768, Model: abyssorangemix2_Hardcore


---
<p align="center"><img src="https://huggingface.co/Maisman/No-Game-NoLife-LoRAs/resolve/main/images/ShiroCatGirl.png">

Prompt: 
```
((masterpiece, best quality)), (ultra-detailed), 5 fingers, illustration, <lora:MaismansShiroLora:0.5>, Shiro, shiro_(no_game_no_life), No Game No Life, long hair, purple thighhighs, long hair, 1girl, blurry background, (crown), very_long_hair, loli, blue background, (lying), cat ears, tail, (feet)
```
Negative prompt: 
```
NSFW, nude, bad anatomy, extra limbs, lowres, destorced, (worst quality:1.4), (mouth open), (low quality:1.4), (trembling:1.4), (cropped head:1.4), (blurry), destorced hands,(disfigured), ugly, bad hands, bad fingers, watermark, wide hips, extra legs, bad legs, (By bad artist -neg, (easynegative))
```
Steps: 25, Sampler: DPM++ 2M Karras, CFG scale: 5, Seed: 4277505989, Size: 512x768, Model: abyssorangemix2_Hardcore


---
<p align="center"><img src="https://huggingface.co/Maisman/No-Game-NoLife-LoRAs/resolve/main/images/01740-2997027614-((masterpiece%2C%20best%20quality_1.2))%2C%20(ultra-detailed_1.2)%2C%20%2C%20Shiro%2C%20shiro_(no_game_no_life)%2C%20No%20Game%20No%20Life%2C%20purple%20clothes%2C%20long.png">
<p align="center"><img src="https://huggingface.co/Maisman/No-Game-NoLife-LoRAs/resolve/main/images/01756-218090946-((masterpiece%2C%20best%20quality_1.2))%2C%20(ultra-detailed_1.2)%2C%20%2C%20Shiro%2C%20shiro_(no_game_no_life)%2C%20No%20Game%20No%20Life%2C%20purple%20clothes%2C%20long.png">
<p align="center"><img src="https://huggingface.co/Maisman/No-Game-NoLife-LoRAs/resolve/main/images/01718-2106806251-((masterpiece%2C%20best%20quality_1.2))%2C%20(ultra-detailed_1.2)%2C%20%2C%20Shiro%2C%20shiro_(no_game_no_life)%2C%20No%20Game%20No%20Life%2C%20purple%20clothes%2C%20long.png">
---

- [Lora for No Game No Life](#lora-for-no-game-no-life)
- [Shiro](#shiro)
- [Izuna](#izuna)

---

# Izuna


Civitai: [Click here!](https://civitai.com/models/12264/hatsuse-izuna-lora-or-no-game-no-life)

Download: [Izuna Lora](https://huggingface.co/Maisman/No-Game-NoLife-LoRAs/blob/main/IzunaLora.safetensors)

```
<lora:IzunaLora:1>
```

Weight 1 is actually really good. Try it!

Use "5 fingers" in prompt. I tried to train the AI to make better hands. I think it does a better job then without. 

<p align="center"><img src="https://huggingface.co/Maisman/No-Game-NoLife-LoRAs/resolve/main/01809-3128147556-((masterpiece%2C%20best%20quality_1.2))%2C%20(ultra-detailed_1.2)%2C%20%2C%20kimono%2C%20hairband%2C%20fox%20ears%2C%20fox%20tail%2C%20sitting%2C%20hand%20between%20legs%2C%20han.png">

Prompt: 
```
((masterpiece, best quality:1.2)), (ultra-detailed:1.2), <lora:IzunaLora:1>, kimono, hairband, fox ears, fox tail, sitting, hand between legs, hand on face, open mouth, white background, 5 fingers, volumetric lighting, realistic, realistic lighting, 8k, cinematic lighting, depth of field, perfect, hyper-detailed,
```
Negative: 
```
(nsfw, nude), (bad anatomy), extra limbs, lowres, destorced, (worst quality:1.4), (mouth open), (low quality:1.4), (trembling:1.4), (cropped head:1.4), (blurry), destorced hands,(disfigured), (bad hands, bad fingers, 1 finger, 2 fingers, 3 fingers, 6 fingers), watermark, wide hips, extra legs, bad legs, (By bad artist -neg), easynegative,
```


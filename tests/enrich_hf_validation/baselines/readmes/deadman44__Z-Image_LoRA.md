---
license: apache-2.0
pipeline_tag: text-to-image
language:
- en
tags:
  - text-to-image
  - z-image
  - safetensors
---
<style>
  .title{
    font-size: 2.5em;
    letter-spacing: 0.01em;
    padding: 0.5em 0;
  }
	.thumbwidth{
	max-width: 180px;
	}
	.font_red{
		color:red;
	}
	.font_blue{
		color:blue;
	}
	.font_grey{
		color: #aaaaaa;
	}
</style>

# models
- Add [lora_zimage_turbo_myjc_beta03](#myjc) :2026-06-21<br />
- Add [lora_zimage_turbo_myjk_beta01](#myjk) :2026-05-23<br />
- Add [lora_zimage_turbo_myjs_beta01](#myjs) :2026-04-17<br />
- Add [lora_zimage_turbo_myjy_alpha01](#myjy) :2026-01-13<br />

---

<br>

# Sample Workflow
### - [z_image_turbo](https://huggingface.co/deadman44/Z-Image_LoRA/raw/main/workflow/z_image_turbo.json)<br>
 - <span class="font_blue">reccomended</span><br/>
### - [z_image_turbo_redraw](https://huggingface.co/deadman44/Z-Image_LoRA/raw/main/workflow/z_image_turbo_redraw.json) 
 - <span class="font_blue">Redraw / Upscale </span><br/>
<br>
- If you get an error in distorch2, please refer to [this issue](https://github.com/pollockjj/ComfyUI-MultiGPU/issues/147).
- I use [RES4LYF](https://github.com/ClownsharkBatwing/RES4LYF) for bongtangent. Please install it from comfyui manager.<br>
<br>
## - reccomended models
- Model (\ComfyUI\models\diffusion_models)
  - [z_image_turbo_bf16.safetensors](https://huggingface.co/Comfy-Org/z_image_turbo/tree/main/split_files/diffusion_models)
- Text Encoder (\ComfyUI\models\text_encoders\)
  -  [qwen_3_4b.safetensors](https://huggingface.co/Comfy-Org/z_image_turbo/tree/main/split_files/text_encoders)
- VAE (\ComfyUI\models\vae)
  - [ae.safetensors](https://huggingface.co/Comfy-Org/z_image_turbo/tree/main/split_files/vae)
<br>
### - redraw
- Model Patch (\ComfyUI\models\model_patches) *If not, create the folder
  - [Z-Image-Turbo-Fun-Controlnet-Union-2.1-8steps.safetensors](https://huggingface.co/alibaba-pai/Z-Image-Turbo-Fun-Controlnet-Union-2.1/tree/main)
---
<br />

### Photorealistic Prompt Gnerator:: 
<br />

<details><summary>System Prompt for Gemma4</summary> 
  
```bash
<|think|>
Think step by step.
The "Organic Living-Snapshot" System Prompt

Role:
You are a documentary photographer specializing in capturing raw, unposed, and mundane moments of everyday life. Your mission is to reject the "AI digital perfection" (over-sharpening, plastic skin, cinematic lighting) and instead deliver an organic, lived-in atmosphere that feels like a real memory.

🛠️ Core Logic: The Four Pillars of Realism
1. [Subject & Action: The Mundane Story]
Goal: Capture "life happening" rather than a "staged pose."
Directives: Describe the person, their clothing (natural fabrics), and a quiet, domestic activity.
Key Terms: Candid, unposed, quietly engaged, mundane, everyday moment, mid-action, looking down/away.
2. [Lighting & Color: The Anti-Cinematic Rule]
Goal: Eliminate dramatic, artificial studio lighting.
Directives:
For Outdoor/Window scenes: Use only soft, indirect natural daylight. No harsh highlights or deep shadows.
For Indoor scenes: Use standard indoor ambient lighting (Neutral color temperature: 4000K-5000K).
Profile: Flat and even lighting profile. Avoid high contrast, dramatic rim lighting, or cinematic "god rays."
Key Terms: Even/flat lighting, neutral white balance, natural muted colors, realistic saturation, no heavy color grading.
3. [Texture & Materiality: The Imperfection Rule]
Goal: Prioritize biological and material reality over digital smoothness.
Directives:
Skin: Focus on authentic textures (pores, tiny imperfections, natural unevenness). Strictly prohibit "plastic-like" or "oily" skin.
Surfaces: All surfaces (skin, fabric, wood, metal) must be MATTE. Avoid excessive gloss or digital sheen.
Fabrics: Show realistic fiber weaves without over-sharpening.
Key Terms: Non-digital feel, authentic skin texture, matte finish, realistic fabric fibers, micro-details.
4. [Camera & Optics: The Snapshot Rule]
Goal: Emulate a real camera (Film or High-quality Consumer Digital) rather than an AI engine.
Directives:
For Nostalgic feel: Shot on 35mm film, featuring subtle, organic film grain.
For Modern snapshot feel: Captured with a high-quality consumer camera; unedited and raw.
Depth of Field: Use a natural depth of field (f/2.8). Crucially: Avoid excessive bokeh. Keep the immediate surroundings clearly visible to maintain a sense of place.
Key Terms: Unedited snapshot, subtle film grain, natural depth of field, no airbrushing, no heavy retouching, 8k photorealistic.
🚫 The "AI-Avoidance" Checklist (Strict Prohibitions)
❌ NO "Cinematic lighting" or "Dramatic shadows."
❌ NO "Plastic/Oily skin" or "Airbrushed faces."
❌ NO "Hyper-saturated colors" or "Heavy color grading."
❌ NO "Extreme bokeh/Blurry backgrounds" (Keep the room recognizable).
❌ NO "Digital glow" or "Over-sharpened edges." 
```
</details>

<br />

- <span class="font_blue">I created an image using the generator (gemma4_26b_a4b) and then had AI_detection perform the analysis. (delete metadata)</span>

  [AI-Generated Content Detection](https://thehive.ai/demos/ai-generated-content-detection)

<br />

 - myjs_beta01
 <div style="display: flex; flex-direction: row; gap: 12px; margin-bottom: 32px;">
  <div style="text-align: center;">
    <a href="https://huggingface.co/deadman44/Z-Image_LoRA/resolve/main/img/20260422104259_z_image_00001_.png" target="_blank">
      <img src="https://huggingface.co/deadman44/Z-Image_LoRA/resolve/main/img/20260422104259_z_image_00001_.jpg" alt="T2I" style="width: 320px; height: auto; object-fit: contain; border: 1px solid #ccc;">
    </a>
  </div>
  <div style="text-align: center;">
    <a href="https://huggingface.co/deadman44/Z-Image_LoRA/resolve/main/img/20260422104259_z_image_ai_detection.jpg" target="_blank">
<img src="https://huggingface.co/deadman44/Z-Image_LoRA/resolve/main/img/20260422104259_z_image_ai_detection.jpg"  alt="T2I"   style="width: 320px; height: auto; object-fit: contain; border: 1px solid #ccc;">
    </a>
  </div>
</div>

 <div style="display: flex; flex-direction: row; gap: 12px; margin-bottom: 32px;">
  <div style="text-align: center;">
    <a href="https://huggingface.co/deadman44/Z-Image_LoRA/resolve/main/img/20260422110240_z_image_00001_.png" target="_blank">
      <img src="https://huggingface.co/deadman44/Z-Image_LoRA/resolve/main/img/20260422110240_z_image_00001_.jpg" alt="T2I" style="width: 320px; height: auto; object-fit: contain; border: 1px solid #ccc;">
    </a>
  </div>
  <div style="text-align: center;">
    <a href="https://huggingface.co/deadman44/Z-Image_LoRA/resolve/main/img/20260422110240_z_image_ai_detection.jpg" target="_blank">
<img src="https://huggingface.co/deadman44/Z-Image_LoRA/resolve/main/img/20260422110240_z_image_ai_detection.jpg"  alt="T2I"   style="width: 320px; height: auto; object-fit: contain; border: 1px solid #ccc;">
    </a>
  </div>
</div>

<br>

---

<a id="myjc"></a> 
<h1 class="title">
<span>lora_zimage_turbo_myjc</span>
</h1>
  -<span class="font_red">Extremely blurry, The details are not accurate</span><br/>
  -<span class="font_blue">natural Japanese JC face</span><br/>
  -I recommend applying my WF's Refine Light (0.3-0.5).<br/>
<br/>
<br/>

# Download
 [Download: turbo_myjc_beta03](https://huggingface.co/deadman44/Z-Image_LoRA/resolve/main/lora_zimage_turbo_myjc_beta03.safetensors?download=true) <br />
 [Download: turbo_myjc_beta02](https://huggingface.co/deadman44/Z-Image_LoRA/resolve/main/lora_zimage_turbo_myjc_beta02.safetensors?download=true) <br />
 [Download: turbo_myjc_beta01](https://huggingface.co/deadman44/Z-Image_LoRA/resolve/main/lora_zimage_turbo_myjc_beta01.safetensors?download=true) <br />
<br />

# Trigger
```bash
myjc, japanese/european, 
and 13-15yo
```
 <br />

 
# Sample prompt
 <br />
 beta03
  <div style="display: flex; flex-direction: column; align-items: flex-start; gap: 12px; margin-bottom: 32px;">
<a href="https://huggingface.co/deadman44/Z-Image_LoRA/resolve/main/img/20260621072912_z_image_00001_.png" target="_blank">
      <img src="https://huggingface.co/deadman44/Z-Image_LoRA/resolve/main/img/20260621072912_z_image_00001_.jpg"
           alt="T2I"
           style="width: 360px; height: auto; object-fit: contain; border: 1px solid #ccc;">
    </a>
</div>
		
```bash
15yo, myjc, japanese, 
lo-fi photography, 2000s digicam style, snapshot, a Japanese girl posing with her hands near her head in an outdoor setting, looking towards the camera, wearing a sailor uniform with a necktie, long twintails with side bangs, indoor school corridor context replaced by outdoor environment with green trees and foliage on the left, water body or pond in the background, bright daylight conditions, strong backlighting, fine ISO grain, subtle film grain, high ISO sensor noise, washed out colors
```

 <br />
 <br />beta02
<div style="display: flex; flex-direction: row; gap: 12px; margin-bottom: 32px;">
  <div style="text-align: center;">
    <a href="https://huggingface.co/deadman44/Z-Image_LoRA/resolve/main/img/20260316180608_z_image_00001_.png" target="_blank">
      <img src="https://huggingface.co/deadman44/Z-Image_LoRA/resolve/main/img/20260316180608_z_image_00001_.jpg"
           alt="T2I"
           style="width: 320px; height: auto; object-fit: contain; border: 1px solid #ccc;">
    </a>
  </div>
  <div style="text-align: center;">
    <a href="https://huggingface.co/deadman44/Z-Image_LoRA/resolve/main/img/20260316181748_z_image_00001_.png" target="_blank">
      <img src="https://huggingface.co/deadman44/Z-Image_LoRA/resolve/main/img/20260316181748_z_image_00001_.jpg"
           alt="T2I"
           style="width: 320px; height: auto; object-fit: contain; border: 1px solid #ccc;">
    </a>
  </div>
  <div style="text-align: center;">
    <a href="https://huggingface.co/deadman44/Z-Image_LoRA/resolve/main/img/20260316183208_z_image_00001_.png" target="_blank">
      <img src="https://huggingface.co/deadman44/Z-Image_LoRA/resolve/main/img/20260316183208_z_image_00001_.jpg"
           alt="T2I"
           style="width: 320px; height: auto; object-fit: contain; border: 1px solid #ccc;">
    </a>
  </div>
</div>
		
```bash
15yo, myjc, japanese, 
This is an outdoor photograph taken during the day in a wooded area with trees and green foliage as the background.
The central figure is a girl standing facing slightly to her right but looking directly at the camera. She has fair skin and long, straight black hair styled with side bangs. She is smiling slightly.
She is wearing a black short-sleeved t-shirt and denim shorts. 
In terms of body features, she has a slender build with slim legs. 
The setting appears to be a park or forested area. Behind the girl, there is a large tree trunk with dark bark. On the right side of the frame, part of a red bench seat can be seen. The lighting suggests it might be overcast or shaded by trees, giving the scene a somewhat muted color palette.
```
		
```bash
15yo, myjc, japanese, 
Portrait of a girl, black ponytail, side bangs, school uniform, short sleeves, smiling, teeth, night time, room, sitting on couch, holding cellphone, looking at phone, a white cat sleeping on her thighs.
```
		
```bash
15yo, myjc, japanese, 
This photograph captures a nostalgic scene, likely from the mid-20th century.
A girl in a pink kimono is posing with a shrine in the background. Her bangs are blowing in the wind through her updo. She smiles happily with her hand on her cheek.
```

 <br />
 <br />
 beta01
 <div style="display: flex; flex-direction: row; align-items: flex-start; gap: 12px; margin-bottom: 32px;">
	   <div style="text-align: center;">
<a href="https://huggingface.co/deadman44/Z-Image_LoRA/resolve/main/img/20260224134917_z_image_00001_.png" target="_blank">
      <img src="https://huggingface.co/deadman44/Z-Image_LoRA/resolve/main/img/20260224134917_z_image_00001_.jpg"
           alt="T2I"
           style="width: 360px; height: auto; object-fit: contain; border: 1px solid #ccc;">
    </a>
<a href="https://huggingface.co/deadman44/Z-Image_LoRA/resolve/main/img/20260224142935_z_image_00001_.png" target="_blank">
      <img src="https://huggingface.co/deadman44/Z-Image_LoRA/resolve/main/img/20260224142935_z_image_00001_.jpg"
           alt="T2I"
           style="width: 360px; height: auto; object-fit: contain; border: 1px solid #ccc;">
    </a>
		</div>
</div>
		
```bash
15yo, myjc, japanese, 
Portrait of a girl, long straight black hair, bangs, school uniform, short sleeves, smiling, teeth, night time, room, sitting on couch, holding cellphone
```
		
```bash
15yo, myjc, japanese, smile, open mouth,  
A close-up woman in pink idol costume with frilled skirt, holding a microphone tightly, captured singing detailed live concert stage background, decisive moment full of energy.
```

 <br />
 <br />beta01
<div style="display: flex; flex-direction: row; gap: 12px; margin-bottom: 32px;">
  <div style="text-align: center;">
    <a href="https://huggingface.co/deadman44/Z-Image_LoRA/resolve/main/img/20260224140432_z_image_00001_.png" target="_blank">
      <img src="https://huggingface.co/deadman44/Z-Image_LoRA/resolve/main/img/20260224140432_z_image_00001_.jpg"
           alt="T2I"
           style="width: 320px; height: auto; object-fit: contain; border: 1px solid #ccc;">
    </a>
  </div>
  <div style="text-align: center;">
    <a href="https://huggingface.co/deadman44/Z-Image_LoRA/resolve/main/img/20260224142145_z_image_00001_.png" target="_blank">
      <img src="https://huggingface.co/deadman44/Z-Image_LoRA/resolve/main/img/20260224142145_z_image_00001_.jpg"
           alt="T2I"
           style="width: 320px; height: auto; object-fit: contain; border: 1px solid #ccc;">
    </a>
  </div>
  <div style="text-align: center;">
    <a href="https://huggingface.co/deadman44/Z-Image_LoRA/resolve/main/img/20260224135943_z_image_00001_.png" target="_blank">
      <img src="https://huggingface.co/deadman44/Z-Image_LoRA/resolve/main/img/20260224135949_z_image_00001_.jpg"
           alt="T2I"
           style="width: 320px; height: auto; object-fit: contain; border: 1px solid #ccc;">
    </a>
  </div>
</div>
		
```bash
15yo, myjc, japanese, 
A young girl with dark hair styled in pigtails is lying on her stomach on a wooden floor next to a window. She is wearing a dress over a white blouse and has her legs raised straight up in the air. Her face is turned towards the camera, giving a direct gaze with smiling. The background shows an outdoor scene through the window, with greenery visible outside.
```
		
```bash
15yo, myjc, japanese, smile, open mouth, rofer, 
A young girl with black hair styled in low twin braids is captured mid-dance jump at crowded street of Tokyo. She is wearing a white short-sleeved blouse under a dark blue-gray dress that flares out as she moves. The image captures a dynamic, energetic moment with a slight motion blur effect, emphasizing her movement. She appears to be smiling and enjoying herself.
```
		
```bash
15yo, myjc, japanese, 
This is an outdoor group photo featuring approximately fifteen young girls, posing together.

The girls are arranged in three rows:
1.  The front row consists of few individuals who are kneeling.
2.  The middle row has few individuals standing behind them.
3.  The back row features two individuals standing further back, above the middle row.

All the girls appear to be dressed in various styles of school uniforms that resembles them, including white shirts, blouses, and skirts. Some wear cardigans over their tops. Their hair is predominantly long and dark, styled in straight cuts with some variations like bangs and ponytails.

The girls are all smiling and posing for the camera with various hand gestures, such as peace signs (V-shapes) made with both hands, open palms facing forward, and other playful poses. Their expressions are cheerful and friendly.

The focus of the photo is on the group's camaraderie and youthful energy.
```

 <br />
 
---

  
 <a id="myjcnt"></a> 
 
 [Download: lora_zimage_myjc_alpha01_no_turbo](https://huggingface.co/deadman44/Z-Image_LoRA/resolve/main/lora_zimage_myjc_alpha01_no_turbo.safetensors?download=true)
 - z-image (base)
 
 <div style="display: flex; flex-direction: column; align-items: flex-start; gap: 12px; margin-bottom: 32px;">
<a href="https://huggingface.co/deadman44/Z-Image_LoRA/resolve/main/img/20260206085527_z_image_00001_.png" target="_blank">
      <img src="https://huggingface.co/deadman44/Z-Image_LoRA/resolve/main/img/20260206085527_z_image_00001_.jpg"
           alt="T2I"
           style="width: 360px; height: auto; object-fit: contain; border: 1px solid #ccc;">
    </a>
</div>
		
```bash
15yo, myjc, japanese, school uniform, 
The image is a close-up, slightly high-angle selfie of a girl with long, dark brown hair. She is smiling warmly at the camera, her head tilted to her right.
```

 <br />
 
 ---

<a id="myjs"></a> 
<h1 class="title">
<span>lora_zimage_turbo_myjs</span>
</h1>
  -<span class="font_blue">natural Japanese JS face</span><br/>
  -Using Refine light at 0.5 is better for my workflow<br/>
<br/>
<br/>

# Download
 [Download: myjs_beta01](https://huggingface.co/deadman44/Z-Image_LoRA/resolve/main/lora_zimage_myjs_turbo_beta01.safetensors?download=true) <br />
 [Download: myjs_alpha01](https://huggingface.co/deadman44/Z-Image_LoRA/resolve/main/lora_zimage_myjs_turbo_alpha01.safetensors?download=true) <br />
<br />

# Trigger
```bash
myjsh/myjsm/myjsl, japanese/european, 
and 6-12yo
```
 <br />

 
# Sample prompt
 <br />
 beta01
 <div style="display: flex; flex-direction: column; align-items: flex-start; gap: 12px; margin-bottom: 32px;">
<a href="https://huggingface.co/deadman44/Z-Image_LoRA/resolve/main/img/20260417165148_z_image_00001_.png" target="_blank">
      <img src="https://huggingface.co/deadman44/Z-Image_LoRA/resolve/main/img/20260417165148_z_image_00001_.jpg"
           alt="T2I"
           style="width: 360px; height: auto; object-fit: contain; border: 1px solid #ccc;">
    </a>
</div>
		
```bash
12yo, myjsh, japanese, 
A realistic medium shot of a cheerful 12-year-old Japanese girl with natural medium-length black hair and soft bangs, sitting on the floor of a cozy, sunlit girly bedroom. She is wearing a crisp white collared shirt and a suspender black pleated skirt, posing with an innocent and bright smile directly towards the camera. The composition is centered, ensuring her full head and upper body are clearly visible within the frame without any cut-offs. Natural daylight enters from a window, providing soft, neutral illumination at 5500K color temperature, maintaining authentic skin tones with visible micro-textures and natural sheen. Third-person perspective, captured as an authentic candid snapshot by a family member, sharp focus on her sparkling eyes, high-definition texture of the cotton shirt and fabric pleats, subtle film grain, incredibly lifelike and cinematic.
```

 <br />

  <br />
 <div style="display: flex; flex-direction: row; gap: 12px; margin-bottom: 32px;">
  <div style="text-align: center;">
    <a href="https://huggingface.co/deadman44/Z-Image_LoRA/resolve/main/img/20260417170238_z_image_00001_.png" target="_blank">
      <img src="https://huggingface.co/deadman44/Z-Image_LoRA/resolve/main/img/20260417170238_z_image_00001_.jpg" alt="T2I" style="width: 320px; height: auto; object-fit: contain; border: 1px solid #ccc;">
    </a>
  </div>
  <div style="text-align: center;">
    <a href="https://huggingface.co/deadman44/Z-Image_LoRA/resolve/main/img/20260417171031_z_image_00001_.png" target="_blank">
<img src="https://huggingface.co/deadman44/Z-Image_LoRA/resolve/main/img/20260417171031_z_image_00001_.jpg"  alt="T2I"   style="width: 320px; height: auto; object-fit: contain; border: 1px solid #ccc;">
    </a>
  </div>
  <div style="text-align: center;">
    <a href="https://huggingface.co/deadman44/Z-Image_LoRA/resolve/main/img/20260417171958_z_image_00001_.png" target="_blank">
      <img src="https://huggingface.co/deadman44/Z-Image_LoRA/resolve/main/img/20260417171958_z_image_00001_.jpg" alt="T2I" style="width: 320px; height: auto; object-fit: contain; border: 1px solid #ccc;">
    </a>
  </div>
</div>
		
```bash
12yo, myjsh, japanese, 
A candid group snapshot of three diverse 12-year-old Japanese girls laughing joyfully with heart hands on a dimly lit urban street at night, captured with a direct frontal hard flash. The first girl has a high ponytail and wears a vibrant pink sundress; the second girl has a neat bob cut with straight bangs and wears a casual white T-shirt; the third girl has cute twin tails tied with ribbons and wears a patterned floral blouse. The lighting is characterized by high contrast, with bright, sharp highlights on their skin and deep, harsh shadows cast directly behind them against the background. Realistic skin textures with natural sheen from the flash, visible pores, and authentic joyful expressions. 6000K neutral color temperature, crisp details, medium shot showing upper bodies and faces fully centered and clearly visible within the frame, third-person perspective, captured on a compact digital camera.
```
		
```bash
9yo, myjsm, japanese, few students, 
A candid, high-fidelity snapshot of a 9-year-old Japanese girl in a bright elementary school classroom. She has shoulder-length hair tied into a loose, slightly messy ponytail and is wearing a light blue short-sleeved school polo shirt. She is sitting at her wooden desk, leaning forward with a wide, genuine laugh, looking towards something just out of frame, capturing a moment of pure childhood joy. The background shows a soft-focus classroom setting with sunlight streaming through large windows, creating a natural and airy atmosphere. Lighting is bright and neutral, utilizing 6500K daylight-balanced tones to ensure realistic skin colors and avoid warm bias. Sharp focus on her joyful facial expression and sparkling eyes, with visible skin micro-textures and fine hair strands. Medium shot, centered composition with her head and upper body fully visible within the frame, third-person perspective, captured on a high-definition digital camera for an authentic daily life aesthetic.
```
		
```bash
6yo, myjsl, japanese, 
A candid, high-fidelity snapshot of a cheerful 6-year-old Japanese girl walking energetically along a lush, tree-lined avenue. She has short, bobbed hair with large white hair ribbon on top and blunt bangs and is wearing a bright, light-colored cotton short sundress, her face lit up with a wide, innocent smile as she looks ahead. The scene is filled with dappled sunlight filtering through the canopy of green trees, creating beautiful patches of light and shadow on the path and her clothing. In the soft-focus background, several pedestrians are walking by, adding a sense of real-world movement and life to the urban park setting. The lighting is natural and bright, using a 5500K daylight-balanced color temperature for authentic, neutral skin tones. Sharp focus on the girl's joyful expression and the fine textures of her hair and dress, with a shallow depth of field creating a soft bokeh effect for the background. Medium full shot, centered composition with her entire head and upper body clearly visible within the frame, third-person perspective, captured as a high-quality street photograph.
```

<br>
---

 <br />
 alpha01
 <div style="display: flex; flex-direction: column; align-items: flex-start; gap: 12px; margin-bottom: 32px;">
<a href="https://huggingface.co/deadman44/Z-Image_LoRA/resolve/main/img/20260112164934_z_image_00001_.png" target="_blank">
      <img src="https://huggingface.co/deadman44/Z-Image_LoRA/resolve/main/img/20260112164934_z_image_00001_.jpg"
           alt="T2I"
           style="width: 360px; height: auto; object-fit: contain; border: 1px solid #ccc;">
    </a>
</div>
		
```bash
11yo, myjsh, japanese, 
1girl, solo, holding microphone, singing, grin, black hair, long hair, braids, maid outfit, white and black dress, white head dress, standing, music outdoors stage, photorealistic, day, hand on waist, contrapost, close-up
```

 <br />

  <br />
 <div style="display: flex; flex-direction: row; gap: 12px; margin-bottom: 32px;">
  <div style="text-align: center;">
    <a href="https://huggingface.co/deadman44/Z-Image_LoRA/resolve/main/img/20260112160610_z_image_00001_.png" target="_blank">
      <img src="https://huggingface.co/deadman44/Z-Image_LoRA/resolve/main/img/20260112160610_z_image_00001_.jpg" alt="T2I" style="width: 320px; height: auto; object-fit: contain; border: 1px solid #ccc;">
    </a>
  </div>
  <div style="text-align: center;">
    <a href="https://huggingface.co/deadman44/Z-Image_LoRA/resolve/main/img/20260112161105_z_image_00001_.png" target="_blank">
<img src="https://huggingface.co/deadman44/Z-Image_LoRA/resolve/main/img/20260112161105_z_image_00001_.jpg"  alt="T2I"   style="width: 320px; height: auto; object-fit: contain; border: 1px solid #ccc;">
    </a>
  </div>
  <div style="text-align: center;">
    <a href="https://huggingface.co/deadman44/Z-Image_LoRA/resolve/main/img/20260112162036_z_image_00001_.png" target="_blank">
      <img src="https://huggingface.co/deadman44/Z-Image_LoRA/resolve/main/img/20260112162036_z_image_00001_.jpg" alt="T2I" style="width: 320px; height: auto; object-fit: contain; border: 1px solid #ccc;">
    </a>
  </div>
</div>
		
```bash
12yo, myjsh, japanese, 
side bangs, black long hair, low twintails, smile, teeth, 
Close-up portrait of a girl is making a peace sign at crowded street of tokyo.
She is wearing a yellow hoodie and denim shorts.
```
		
```bash
9yo, myjsm, japanese, 
1girl, solo, black hair, looking at viewer, pink shirt, sitting, long hair, hand on own cheek, black skirt, smile, brown eyes, photorealistic, shadow, head rest, frilled skirt, feet out of frame, pink ribbon, stairs, kneehighs
```
		
```bash
6yo, myjsl, japanese, 
black hair, ponytail, blunt bangs, white collared shirt, black suspender pleated skirt, sand, 
A smiling girl squats and plays with dog along the coast during the day.
```


 <br />

 ---

<a id="myjk"></a> 
<h1 class="title">
<span>lora_zimage_turbo_myjk</span>
</h1>
  -It might be a good idea to adjust the strength and use redraw workflow.<br/> 
  -<span class="font_blue">natural Japanese JK face</span><br/>
<br/>
<br/>

# Download
 [Download: myjk_turbo_beta01](https://huggingface.co/deadman44/Z-Image_LoRA/resolve/main/lora_zimage_turbo_myjk_beta01.safetensors) <br />
<br />

# Trigger
```bash
myjk, japanese/european, 
and 16-18yo
```
 <br />

 
# Sample prompt
 <br />
 beta01
 <div style="display: flex; flex-direction: column; align-items: flex-start; gap: 12px; margin-bottom: 32px;">
<a href="https://huggingface.co/deadman44/Z-Image_LoRA/resolve/main/img/20260523083438_z_image_00001_.png" target="_blank">
      <img src="https://huggingface.co/deadman44/Z-Image_LoRA/resolve/main/img/20260523083438_z_image_00001_.jpg"
           alt="T2I"
           style="width: 360px; height: auto; object-fit: contain; border: 1px solid #ccc;">
    </a>
</div>
		
```bash
18yo, myjk, japanese,
Medium close-up shot of two 18-year-old Japanese girls leaning in closely for a cheerful selfie, both wearing school uniforms with white collars. They are smiling broadly with eyes crinkled in genuine laughter, holding up V-sign peace gestures near their faces; one girl’s hand is visible in the foreground holding a smartphone, framing the shot naturally. Centered composition captures their upper bodies from chest up, with clear visibility of facial features, hair strands, and uniform fabric texture. Lighting is bright and even daylight at approximately 5200K color temperature, creating natural skin tones with subtle subsurface scattering on cheeks and nose highlights. Background shows a blurred but recognizable classroom environment with other students sitting at desks, chalkboard, and windows letting in soft ambient light. Shot on 35mm lens perspective from eye-level camera angle, point-and-shoot aesthetic with sharp focus across entire frame including foreground hands and background details. High-definition texture rendering showing individual eyelashes, slight freckles, realistic cotton weave of uniforms, and glossy finish of hair strands. Brightly lit scene with well-exposed midtones, crisp edges on all subjects, no motion blur, authentic candid moment captured in high resolution.
```

 <br />

  <br />
 <div style="display: flex; flex-direction: row; gap: 12px; margin-bottom: 32px;">
  <div style="text-align: center;">
    <a href="https://huggingface.co/deadman44/Z-Image_LoRA/resolve/main/img/20260523082406_z_image_00001_.png" target="_blank">
      <img src="https://huggingface.co/deadman44/Z-Image_LoRA/resolve/main/img/20260523082406_z_image_00001_.jpg" alt="T2I" style="width: 320px; height: auto; object-fit: contain; border: 1px solid #ccc;">
    </a>
  </div>
  <div style="text-align: center;">
    <a href="https://huggingface.co/deadman44/Z-Image_LoRA/resolve/main/img/20260523082726_z_image_00001_.png" target="_blank">
<img src="https://huggingface.co/deadman44/Z-Image_LoRA/resolve/main/img/20260523082726_z_image_00001_.jpg"  alt="T2I"   style="width: 320px; height: auto; object-fit: contain; border: 1px solid #ccc;">
    </a>
  </div>
  <div style="text-align: center;">
    <a href="https://huggingface.co/deadman44/Z-Image_LoRA/resolve/main/img/20260523083034_z_image_00001_.png" target="_blank">
      <img src="https://huggingface.co/deadman44/Z-Image_LoRA/resolve/main/img/20260523083034_z_image_00001_.jpg" alt="T2I" style="width: 320px; height: auto; object-fit: contain; border: 1px solid #ccc;">
    </a>
  </div>
</div>
		
```bash
18yo, myjk, japanese, 
A photorealistic medium close-up shot of an 18-year-old Japanese girl streaming on her smartphone in a dimly lit, cluttered room. The primary light source is direct frontal hard flash at 5000K cool-white temperature, creating crisp shadows and bright highlights that make the subject stand out against the dark background. The camera is positioned at eye level or slightly above, using a 35mm perspective for a casual point-and-shoot look. The composition is centered, showing her face and upper body clearly, with full visibility of her head and hands holding the phone; no selfie arm obscures the view. She has a genuine smile and natural posture, wearing a cute outfit with visible fabric textures such as lace, ribbons, or frills. Visible skin pores, subtle subsurface scattering on her cheeks, and realistic material details are highlighted. Background details include scattered personal items and furniture, rendered with sharp focus and high-definition texture to maintain depth without bokeh blur. Exposure settings: aperture f/4.5, shutter 1/125s, ISO 400. Neutral white balance applied to counter warm bias. Authentic imperfections such as slight fabric wrinkles and asymmetrical hair strands enhance realism.
```
		
```bash
16yo, myjk, japanese,
scarf, walking, multiple girls, school uniform, hand in pocket, black hair, solo focus, outdoors, photorealistic, plaid scarf, socks, kneehighs, black footwear, necktie, coat, school bag, plaid skirt, loafers, tokyo \(city\), pleated skirt, blurry, ponytail, grey skirt, road, winter clothes, long sleeves, smile
```
		
```bash
17yo, myjk, japanese,
A photorealistic medium full shot of an 17-year-old Japanese female idol singing passionately on stage, her face illuminated by bright directional spotlights (5600K daylight white balance), capturing a vivid smile with sharp focus on her eyes and glossy lips. She wears a detailed, sparkling idol costume with intricate fabric textures and sequins reflecting the harsh frontal light, creating crisp specular highlights and deep shadows that define her facial structure. The camera is positioned at eye level, centered composition ensuring her head and upper torso are fully visible within the frame, avoiding any selfie-arm obstruction. Lighting style: Hard/Flash direct frontal illumination, brightly lit subject, high-contrast lighting with clear shadow definition, neutral white balance to counter warm stage bias. Camera settings: 35mm perspective, aperture f/4.5, shutter speed 1/125s, ISO 400, point-and-shoot aesthetic with minimal noise, sharp background details of the darkened concert hall visible behind her, realistic skin pores and subtle sweat sheen under intense stage lights, authentic candid moment frozen in time.
```


 <br />

 ---

<a id="myjy"></a> 
<h1 class="title">
<span>lora_zimage_turbo_myjy_alpha</span>
</h1>
  -It might be a good idea to adjust the strength and use redraw workflow.<br/> 
  -alpha01 strength (0.1-0.7)<br />
  -<span class="font_blue">natural Japanese JY face</span><br/>
<br/>
<br/>

# Download
 [Download: myjk_alpha01](https://huggingface.co/deadman44/Z-Image_LoRA/resolve/main/lora_zimage_turbo_myjy_alpha01.safetensors?download=true) <br />
<br />

# Trigger
```bash
myjy, japanese/european, 
and 3-5yo
```
 <br />

 
# Sample prompt
 <br />
 alpha01
 <div style="display: flex; flex-direction: column; align-items: flex-start; gap: 12px; margin-bottom: 32px;">
<a href="https://huggingface.co/deadman44/Z-Image_LoRA/resolve/main/img/20260113174951_z_image_00001_.png" target="_blank">
      <img src="https://huggingface.co/deadman44/Z-Image_LoRA/resolve/main/img/20260113174951_z_image_00001_.jpg"
           alt="T2I"
           style="width: 360px; height: auto; object-fit: contain; border: 1px solid #ccc;">
    </a>
</div>
		
```bash
5yo, myjy, japanese, 
bangs, black long hair, twintails, smile, open mouth, 
Some girls and boys are sitting and playing at Sandbox in the park.
She is wearing a blue smock.
```

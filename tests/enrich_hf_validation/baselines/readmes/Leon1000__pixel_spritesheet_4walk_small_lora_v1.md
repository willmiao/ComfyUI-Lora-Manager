---
tags:
- text-to-image
- lora
- diffusers
- template:diffusion-lora
widget:
- output:
    url: images/knight.png
  text: >-
    A pixel art spritesheet of a medieval knight wearing metal armor and a
    helmet with a red plume. The spritesheet is a 4 by 4 grid of four rows of
    frames - first row is 3 walking frames facing down and 1 frame both arms
    raised, second row is 3 walking frames facing left and 1 frame jumping left,
    third row is 3 walking frames facing right and 1 frame jumping right, fourth
    row is 3 walking frames back view facing up and 1 frame lying on floor.
- output:
    url: images/witch.png
  text: >-
    A pixel art spritesheet of a witch with long red hair and blue eyes, wearing
    a purple hat and robes trimmed with white and light purple colors. The
    spritesheet is a 4 by 4 grid of four rows of frames - first row is 3 walking
    frames facing down and 1 frame both arms raised, second row is 3 walking
    frames facing left and 1 frame jumping left, third row is 3 walking frames
    facing right and 1 frame jumping right, fourth row is 3 walking frames back
    view facing up and 1 frame lying on floor.
- output:
    url: images/werewolf.png
  text: >-
    A pixel art spritesheet of a werewolf with light gray fur and yellow eyes,
    wearing a red scarf around his neck, and brown leather pants. The
    spritesheet is a 4 by 4 grid of four rows of frames - first row is 3 walking
    frames facing down and 1 frame both arms raised, second row is 3 walking
    frames facing left and 1 frame jumping left, third row is 3 walking frames
    facing right and 1 frame jumping right, fourth row is 3 walking frames back
    view facing up and 1 frame lying on floor.
base_model: black-forest-labs/FLUX.2-klein-base-4B
instance_prompt: null
license: apache-2.0
---
# pixel_spritesheet_4walk_small_lora_v1

<Gallery />

## Model description 

A pixel art spritesheet LoRA for small 32x32 characters, with animation frames for walking up&#x2F;down&#x2F;left&#x2F;right, standing with both arms raised, jumping left&#x2F;right, and lying on the floor.

## How to use

You can use the default FLUX.2 Klein base 4B workflows from ComfyUI. Both the text-to-image workflow and the edit base workflow work.

Images should be 512x512 because that&#39;s the size of the spritesheets used in training.

Both the 2750-steps LoRA and the 3000-steps LoRA are available. The 3000-steps version seems to be more consistent in making humanoid characters, but the 2750-steps version seems a bit more creative in non-humanoid characters if using edit + an image reference.

## Does this LoRA work with FLUX.2 Klein 4B distilled?

No. It&#39;s technically compatible, but the distilled model ruins the quality of the pixels and the consistency. Use the base model.

## How to get pixel-perfect images

To get pixel-perfect images, downscale by a factor of 4. So 512x512 images should downscale to 128x128. Using k-centroid scaling works well.

See the examples below:

| Raw output      | K-centroid downscaled, then upscaled back to 512x512      |
| ------------- | ------------- |
| ![knight](https:&#x2F;&#x2F;cdn-uploads.huggingface.co&#x2F;production&#x2F;uploads&#x2F;68dcbc0eb3e9381d15e2cbbc&#x2F;Sv2ldfiM4S2-5tlzE0buh.png) | ![knight_clean](https:&#x2F;&#x2F;cdn-uploads.huggingface.co&#x2F;production&#x2F;uploads&#x2F;68dcbc0eb3e9381d15e2cbbc&#x2F;cSDU6bnl85wUNL_yV23XO.png) |
| ![witch](https:&#x2F;&#x2F;cdn-uploads.huggingface.co&#x2F;production&#x2F;uploads&#x2F;68dcbc0eb3e9381d15e2cbbc&#x2F;VJ8wzY3M6r1KM75KxFn8a.png) | ![witch_clean](https:&#x2F;&#x2F;cdn-uploads.huggingface.co&#x2F;production&#x2F;uploads&#x2F;68dcbc0eb3e9381d15e2cbbc&#x2F;Wcx-kKPwRX2sRG2mivTL0.png) |
| ![werewolf](https:&#x2F;&#x2F;cdn-uploads.huggingface.co&#x2F;production&#x2F;uploads&#x2F;68dcbc0eb3e9381d15e2cbbc&#x2F;st8tgSE_Oq0RNedyW9tQS.png) | ![werewolf_clean](https:&#x2F;&#x2F;cdn-uploads.huggingface.co&#x2F;production&#x2F;uploads&#x2F;68dcbc0eb3e9381d15e2cbbc&#x2F;zAZ8nGev13qmhc3xTn-3_.png) |

## Using an image reference

You can use the edit workflow with an image reference of a character for your spritesheet.

Prompt: *Create a pixel art spritesheet of the character in the image. The spritesheet is a 4 by 4 grid of four rows of frames - first row is 3 walking frames facing down and 1 frame both arms raised, second row is 3 walking frames facing left and 1 frame jumping left, third row is 3 walking frames facing right and 1 frame jumping right, fourth row is 3 walking frames back view facing up and 1 frame lying on floor.*

![demon_man_image_ref](https://cdn-uploads.huggingface.co/production/uploads/68dcbc0eb3e9381d15e2cbbc/mq_NRXpKlWOEQMyBAIEhk.png)

![astronaut_image_ref](https://cdn-uploads.huggingface.co/production/uploads/68dcbc0eb3e9381d15e2cbbc/MtCFgXHjqjfSsQI0KzPw3.png)

![bluejay_image_ref](https://cdn-uploads.huggingface.co/production/uploads/68dcbc0eb3e9381d15e2cbbc/HyPn2YZST-C50FOXNTQT7.png)

## Testing the spritesheets in a game

If you want to quickly test your spritesheets in a 2D game, here&#39;s a simple &quot;sandbox&quot; game&#x2F;tool where you can upload the raw spritesheet outputs and spawn in your characters to move around:

Link to tool [here](https://svntax.github.io/pixel-art-spritesheet-sandbox/)

Source code [here](https://github.com/svntax/pixel-art-spritesheet-sandbox)

## Notes

This is a first attempt at making a pixel art spritesheet LoRA using small sprites. There are sometimes bad images generated with issues like hair or headwear being cut off, and non-human characters with bad anatomy. The bottom row of sprites with the back view also has problems with consistency sometimes (for example, the werewolf is missing the red scarf).

## Credits

- The dataset used to train this LoRA consists of spritesheets edited and based on a template spritesheet by [George Bailey](https:&#x2F;&#x2F;opengameart.org&#x2F;content&#x2F;16x16-game-assets), licensed under [CC BY 4.0](https:&#x2F;&#x2F;creativecommons.org&#x2F;licenses&#x2F;by&#x2F;4.0&#x2F;)


## Download model


[Download](/svntax-dev/pixel_spritesheet_4walk_small_lora_v1/tree/main) them in the Files & versions tab.

# Anima LoRA block compatibility

`Lora Loader (LoraManager)` and `LoRA Text Loader (LoraManager)` automatically
remap legacy Anima LoRA block indices when the connected model uses a larger
Anima layout. No extra node is required and the LoRA file is never modified.

## Why this is needed

Anima 2.9B and 3.8B are depth expansions of the original 28-block Anima model.
New transformer blocks were inserted **between** the original blocks, so the old
block indices no longer point at the same layers:

```text
Anima Base (28)   0  1  2  3  4  5  6 ...
Anima 2.9B (40)   0  1  3  4  6  7  9 ...
Anima 3.8B (52)   0  1  4  5  8  9 12 ...
```

Applying a 28-block LoRA directly to 2.9B or 3.8B therefore lands most of its
deltas on the wrong layers. ComfyUI does not warn about this: every old block
index (`0..27`) still exists in the larger model, so no key is reported as
missing. The image usually looks like the LoRA had no effect, or degrades as the
strength is raised.

## Supported layouts

- Anima Base (28) → Anima 2.9B (40)
- Anima 2.9B (40) → Anima 3.8B (52)
- Anima Base (28) → Anima 3.8B (52), composed from the two steps above
- A LoRA whose layout already matches the model is loaded unchanged.
- A LoRA from a newer/larger layout than the connected model raises a clear
  error instead of being applied partially.

Both common key naming schemes are handled:

```text
lora_unet_blocks_2_self_attn_q_proj.lora_down.weight
diffusion_model.blocks.2.self_attn.q_proj.lora_A.weight
```

Text encoder keys, `llm_adapter` keys, and the Anima 3.8B semantic connector
keys are never remapped. Newly inserted blocks have no counterpart in the old
LoRA and are intentionally left untouched.

## Settings

The behavior is on by default. It can be disabled globally under **ComfyUI
Settings → LoRA Manager → LoRA Loader → Legacy Anima LoRA block remap**. The
ComfyUI setting is synced with LoRA Manager's backend setting so the Python
loader sees the change on the next run. Disabling it loads the LoRA file exactly
as-is, which is useful for A/B comparison or for a custom derivative whose
topology you understand.

## User flow

1. Load an Anima 2.9B or 3.8B model as usual.
2. Add `Lora Loader (LoraManager)` and select an old Anima LoRA normally.
3. Queue the workflow. The loader logs a single line when a remap happens:

```text
Anima block remap "styleX": 28 -> 40 blocks; 1040/1040 block keys rewritten;
28 source blocks mapped; inserted blocks 2, 5, 8, ... left untouched
```

Trigger words, recipes, `<lora:...>` syntax, and the LoRA widget are unchanged.

## Requirements

- A ComfyUI build that can load the target model without truncating its blocks
  (Anima 2.9B support arrived around ComfyUI 0.33.1; Anima 3.8B may require its
  own model-support extension).
- If the model is loaded with only 28 blocks, no remap is possible — fix the
  model loading/ComfyUI version first.

## Limitations

- This fixes **layer correspondence**, not numerical equivalence. The inserted
  blocks and retrained adapter change the model's behavior; start around
  **0.5–0.7** strength instead of 1.0.
- New blocks are not covered by the LoRA. An optional "extend to inserted
  blocks" approximation is not part of this feature.
- Generation is inferred from the highest block index referenced by the LoRA.
  A LoRA that only touches early blocks is assigned to the smallest layout that
  can contain it; this is the same trade-off as the community remap packs.
- Replacing a LoRA file in place is safe: remapping is performed at load time
  and nothing is cached on disk.

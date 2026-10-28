# Anima expansion manifests

Each JSON file records one depth-expansion step of the Anima DiT:

- `old_block_count` / `new_block_count`
- `insertion_positions`: target indices occupied by newly inserted blocks
- `inserted_to_source`: which source block each inserted block was initialized
  from (metadata for a future "extend to inserted blocks" feature; not used by
  the current remapper)

The 28 -> 40 insertion positions are the measured layout published by
`sparklingcoffee777/ComfyUI-Anima-2.9B-loraPatch`. The 40 -> 52 positions match
`KitagawaCoding/ComfyUI-Anima-3.8B-loraPatch` and the independently derived
table in `INuBq8/ComfyUI-Anima-LoRA-ControlNet-Patch`. The manifest format
follows `shin131002/ComfyUI-Anima-Remap`. The same data set was used by the
earlier LoRA Manager PR #1104; this implementation reuses the data and tests
but moves the behavior behind the generic loader adapter.

The mapping is applied only to DiT block keys at load time; no LoRA or model
file is modified.

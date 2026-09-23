# Load Image Metadata (LoraManager)

Load a source image and reuse its prompts, local models, LoRAs, and sampling settings.
The node lives under **Lora Manager → loaders**. Restart ComfyUI after installing
this change and refresh the page. This Python node needs no Vue widget build.

## Wiring a checkpoint workflow

1. Upload/select an image in **Load Image Metadata (LoraManager)**.
2. Convert `ckpt_name` on **Checkpoint Loader (LoraManager)** to an input and
   connect `model_name`. Leave its randomization control fixed.
3. Connect the checkpoint's MODEL and CLIP to **Lora Loader (LoraManager)**.
   Connect the metadata node's `lora_stack` to that loader. Leave its LoRA widget
   empty unless you intentionally want additional LoRAs.
4. Connect the LoRA loader's CLIP to two CLIP Text Encode nodes. Connect metadata
   `positive` and `negative` to their text inputs, and their conditioning outputs
   to KSampler. Connect the LoRA loader's MODEL to KSampler.
5. Convert KSampler's seed, steps, cfg, sampler_name, scheduler, and denoise
   widgets to inputs and connect the corresponding metadata outputs.
6. For text-to-image, connect width/height to an appropriate Empty Latent node.
   For img2img, encode the `image` output with the appropriate VAE instead.
7. Connect KSampler's samples and the checkpoint's VAE to VAE Decode, then Save Image.
8. Connect `readable_report` to a text display node for prompts, sampling settings,
   model/LoRA names, local resolution status and warnings. The original `report`
   output remains notes followed by formatted JSON; it is not a pure JSON string.

`model_name`, `sampler_name`, and `scheduler` use COMBO outputs for converted
dropdown inputs in current ComfyUI. `model_name` contains the matching local
checkpoint or diffusion-model filename. The report identifies the resolved type;
connect it to the appropriate loader. Lookup searches both categories regardless
of how the original metadata labels the model.

For a diffusion-model workflow, connect `model_name` to **Unet Loader
(LoraManager)** and select the correct text encoder(s), VAE, latent node and
architecture-specific conditioning separately. These settings do not reconstruct
an entire workflow or guarantee pixel-identical reproduction.

## Selection and overrides

`prefer_saved_image_metadata` is enabled by default. It prefers the saved
A1111-style generation parameters (including ComfyUI exports in that format)
over the workflow. The report identifies this source; `sampler_node_id` is
ignored in this mode when valid saved parameters are available. If saved
parameters are absent or malformed, the node tries workflow metadata and
reports any parsing failure.

Disable the flag to prefer workflow extraction. Only active samplers are
eligible: muted/bypassed sampler nodes and samplers inside muted/bypassed
subgraph instances are excluded. This uses the saved UI workflow's mode flags
when available, including nested subgraphs, and any modes in the API graph.
Explicitly selecting an inactive sampler produces an error report and the
usual saved-parameter/default recovery; it never extracts that inactive stage.

With one supported active sampler, leave `sampler_node_id` blank. With several, enter
its original node ID. Reports list candidate IDs when selection is ambiguous.
Native subgraphs in API prompt metadata use colon-qualified paths: `1481:1783`
means node 1783 inside subgraph instance 1481. Nested paths such as `10:20:30`
are supported; slash notation (`1481/1783`) is also accepted. A container ID
(`1481`) or leaf ID (`1783`) is accepted only if it identifies one sampler.
An exact sampler ID takes precedence over abbreviated matching.

Selection follows that sampler's graph, rather than mixing branches. Supported
sampling nodes include KSampler, KSamplerAdvanced and SamplerCustomAdvanced with
standard RandomNoise, CFGGuider/BasicGuider, BasicScheduler and KSamplerSelect
components. BasicGuider's CFG is 1; its architecture-specific lack of negative
conditioning is reported. Known Image Saver parameter/selector outputs and
rgthree seed values can be read without executing those nodes.

Detail Daemon's underlying sampler name is recovered, but its sampling effects
are explicitly unsupported. Other custom model/conditioning nodes can still
require defaults or overrides. If a requested stage cannot be read and global
image parameters are used instead, the report explicitly says those parameters
cannot verify the selected stage. Subgraph traversal requires the expanded API
prompt; UI-workflow-only subgraph definitions are not expanded or executed.

Extraction errors do not stop this node. If an API prompt uses unsupported
samplers, the node first tries the image's saved generation parameters. Any
remaining unavailable or invalid extracted fields use the SDXL starter defaults
(width/height fall back to the source image dimensions instead);
valid extracted fields are preserved. `readable_report` starts with **❌ ERROR**
and explains each recovery or substitution. This also applies to existing nodes
saved with `missing_settings=strict`; that legacy option no longer blocks
extraction recovery. New nodes default to `use_defaults`.

The report uses emoji section markers (🖼️ image, 📦 model, ⚙️ sampling, 🧩 LoRAs,
➕/➖ prompts) and ❌/⚠️/ℹ️ status markers. It is plain text, so colors depend on the
connected display node. Missing/ambiguous local files still appear in
`missing_files`. An empty model output requires selecting a local model manually.
Invalid explicit overrides and unreadable image files remain execution errors.

`overrides_json` replaces extracted values, for example:

```json
{
  "scheduler": "normal",
  "model_name": "portraits/model.safetensors",
  "seed": 12345,
  "loras": [["styles/ink.safetensors", 0.7, 0.3]]
}
```

Supported keys: `positive`, `negative`, `model_name`, `seed`,
`steps`, `cfg`, `sampler_name`, `scheduler`, `width`, `height`, `denoise`, `loras`.
LoRA entries are `[name, model_strength, clip_strength]`; `"loras": []` explicitly
clears the extracted stack. Legacy `checkpoint_name` and `unet_name` override
keys remain accepted as aliases for `model_name`; supply only one model key.
Exact relative or absolute local
business paths disambiguate duplicate basenames. Matching falls back to a unique
filename or extensionless filename, then an exact unique catalog `file_name` or
`model_name` alias. Version dots are preserved when stripping known file
extensions. It never downloads or fuzzy-matches models, and stale entries whose
files no longer exist are excluded.

Images with no metadata automatically use a bottle-inspired SDXL starter preset,
even with an existing saved `strict` setting: a glass-bottle/galaxy landscape
prompt, negative `text, watermark`, seed 0, 20 steps, CFG 7, Euler/normal,
1024×1024 and denoise 1, with no LoRAs. These settings are clearly identified as
synthetic defaults in both reports. Source image pixels and mask are unchanged.
Overrides take precedence. The node selects `sd_xl_base_1.0.safetensors` only
when uniquely indexed; otherwise choose an SDXL checkpoint manually or supply
`model_name`. Malformed or unsupported metadata also recovers with an explicit ERROR report.

## Supported metadata and limits

- PNG API prompt metadata; JPEG/WebP EXIF parameter comments; ComfyUI WebP
  `prompt:`/`workflow:` EXIF fields.
- Standard KSampler, core checkpoint/UNet/LoRA loaders, LoRA Manager checkpoint,
  UNet, LoRA/text loaders and LoRA stacks. LoRA application order and separate
  model/CLIP strengths are preserved, including intentional repeated entries.
  Different LoRA chains on model and prompt CLIP branches require an explicit
  stack override rather than being silently merged.
- Literal CLIPTextEncode text and supported primitive value connections. Prompt
  polarity comes from sampler wiring, never from words such as “ugly”.
- A1111/Forge generation text with explicit sampler alias mappings. Recognized
  LoRA directives become stack entries and are removed from prompt text. Literal
  tags in ComfyUI encoder text remain literal; graph loaders determine its stack.
- A1111 `Automatic`/absent schedules do not reliably identify a ComfyUI schedule.
  The node substitutes `normal` and reports the missing information as an ERROR;
  an explicit override can select a different schedule.
- UI-workflow-only fallback supports known core widget layouts, with a report
  warning. Saved widgets can differ from executed values (for example a seed
  randomized after generation). Custom widget layouts are not guessed.
- KSamplerAdvanced partial/noise settings require an explicit denoise override;
  this is an intentional approximation, not a reconstruction of those controls.
- Distinct SDXL/Flux encoder prompts, combined/regional/zeroed conditioning,
  arbitrary custom nodes, dynamic wildcards and unsupported custom sampling components are
  not automatically reconstructed. Supply explicit overrides or retain the
  original workflow for those cases.
- Width/height come from a recognized latent source or fall back to source-image
  dimensions; resized/upscaled images can therefore need dimension overrides.
  Only the synthetic starter preset for metadata-free images uses a fixed
  1024×1024 regardless of the source image size.
- VAE, text encoder choice, CLIP skip, ControlNet and architecture-specific
  conditioning still need the appropriate nodes. No embedded code is executed
  and no external metadata service is contacted.

LoRA Manager must have indexed the required models. Library resolution includes
its configured extra folders and preserves business paths through symlinks.

## Extraction without a local catalog

The parser extracts names before attempting local resolution. In recovery mode,
`report` includes `source_resources` with original model names, LoRA names and
strengths, and embedded resource hashes even when none are installed. The model
output sockets remain empty and the resolved stack excludes missing files.

Combined sampler labels such as `Euler a SGM Uniform`, `Euler Normal` and
`er_sde simple` are split into sampler and scheduler. Multiline parameter blocks
and their nested JSON resource lists are supported. If prompt LoRA tags are
absent, one hash-name entry and one weighted resource can be matched offline;
multiple entries require an explicit mapping rather than guessing from order.
A single resource also disambiguates duplicated identical prompt tags.

The `Model` field in A1111-style metadata does not distinguish checkpoints from
standalone diffusion models. The node searches both indexed categories by name,
then reports the matched type. Local model type and filename cannot be verified
without an indexed library. Multiple equally good matches are reported as
ambiguous; specify a relative path through `model_name` to disambiguate.

## “Image contains no supported generation metadata”

For older versions, this means extraction failed before any library lookup.
The current node uses the starter preset when metadata is entirely absent. The error identifies the
actual server file, its format, byte size and metadata keys. PNG text chunks are
read both before and after pixel data. If no generation metadata remains, upload
the original saved file: clipboard copies and re-encoded/exported images may
lose it. `use_defaults` supplies replacement settings; it does not recover the
original prompts or seed.

## Missing local resources

`missing_files` is a text output listing unresolved checkpoints/UNets and LoRAs.
LoRA entries include both model and CLIP weights and the resolution failure.
It is empty when all requested resources resolve. Missing and ambiguous LoRAs
are excluded from `lora_stack`, including in strict mode, so downstream loaders
receive only resolved files. Valid entries keep their original order and weights.
Unresolved model-name sockets are empty: select a model manually or override its
name before connecting that socket to a loader.

## Output layout and upgrade

The outputs start with `image`, `mask`, `positive`, `negative`, **`model_name`**,
**`lora_stack`**, **`lora_stack_text`**, followed by the sampling settings and reports.
`lora_stack_text` lists each resolved stack path with model and CLIP weights in
application order. It is empty for an empty stack; unresolved files appear only
in `missing_files`, with their requested weights.

This replaces the former separate checkpoint/UNet sockets and renames `lost_list`
to `missing_files`. Restart ComfyUI, refresh, and recreate existing instances of
this node; reconnect the model and stack outputs to avoid stale saved slot indices.
Sampling and report output indices remain unchanged. No Vue build is required.

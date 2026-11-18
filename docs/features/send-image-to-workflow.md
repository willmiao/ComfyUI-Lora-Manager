# Send Image to Workflow

Send a LoRA Manager example image or recipe preview directly to a ComfyUI image
input node (built-in `Load Image`, `Load Image (Mask)`, and compatible custom
nodes).

## User flow

1. Open a model's example gallery or a recipe preview.
2. Click the paper-plane **Send image to workflow** control (showcase hover
   controls, full-size media viewer, or the recipe card context menu).
3. If any image node is marked **Mark as → Send Image Target**, the image goes
   to the marked node directly. Otherwise LoRA Manager auto-detects image
   nodes and asks which one to use when there are several.
4. The image appears in the target node's image widget and is ready to run.

Remote images can take a few seconds to download. During that time the clicked
control shows a spinner and a persistent **Downloading image and sending to
workflow...** toast stays visible; duplicate sends are ignored until the first
one finishes.

Marking is stored on the node as `properties.lm_marker_role =
"send_image_target"` and survives workflow saves.

## How it works

```text
browser ──POST /api/lm/send-image-to-workflow──► LoRA Manager backend
                                                    │ resolve source
                                                    │ validate image
                                                    │ copy/download to ComfyUI input/
                                                    ▼
                                            lm_widget_update (WebSocket)
                                                    │ action: "set_image"
                                                    ▼
                                            target node image widget
```

The backend resolves three source forms:

- `/example_images_static/...` — a downloaded model example image
- `/api/lm/previews?path=...` — a recipe or model preview image
- `https://image.civitai.com/...` / other allow-listed CivitAI hosts — downloaded
  on demand

Local files are limited to LoRA Manager library roots, the example-images root,
the recipes root, and ComfyUI's input directory. Remote URLs are limited to
CivitAI media hosts.

## Image materialization

`LoadImage` only lists files under ComfyUI's `input/` directory and its
`VALIDATE_INPUTS` checks that the file exists. The backend therefore writes
images to `folder_paths.get_input_directory()` with a content-addressed name:

```text
lm_<sha256-prefix>_<sanitized-original-name>.<canonical-extension>
```

The prefix makes these files easy to identify, and the content hash deduplicates
repeated sends. Files already in the input root are reused under their original
name.

## Widget update

The backend broadcasts the existing `lm_widget_update` event with
`action: "set_image"`. The ComfyUI-side registry:

1. resolves the node's image widget from the synthetic `upload` input added by
   ComfyUI's core `uploadImage` extension (`imageInputName`);
2. appends the new filename to the widget's combo values;
3. sets `widget.value` and `widgets_values`;
4. invokes the widget callback so `LoadImage` refreshes its preview.

## API

`POST /api/lm/send-image-to-workflow`

```json
{
  "source": { "url": "/example_images_static/<model>/image_0.webp" },
  "node_ids": [{ "node_id": 3, "graph_id": "root" }]
}
```

`source` accepts `url` or `path`. Response:

```json
{
  "success": true,
  "value": "lm_ab12..._image_0.webp",
  "name": "image_0.webp",
  "results": [{ "node_id": 3, "graph_id": "root", "success": true }]
}
```

The endpoint returns `503` in standalone mode and `400` for unsupported sources
or invalid images.

## Scope and limitations

- v1 targets image inputs in ComfyUI's **input** folder only. Output/temp nodes
  such as `Load Image (Output)` are not offered.
- Video examples and video recipe previews are skipped.
- Node capability detection relies on the image input's `image_upload` /
  `animated_image_upload` metadata, with a widget-name fallback for older
  frontends and custom nodes.
- A connected image input is excluded from targets because the linked value
  overrides the widget during execution.
- If the marked target is unusable (connected input or non-input folder), the
  send is refused rather than silently falling back to another image node.
- Standalone mode has no ComfyUI connection, so the controls are hidden and the
  endpoint is disabled.

## Tests

- `tests/routes/test_send_image_workflow.py` — source resolution, materialization,
  dedup, path traversal, non-image rejection, standalone mode.
- `tests/frontend/utils/uiHelpers.imageSend.test.js` — marked-target precedence,
  auto-detection, no-target behavior.

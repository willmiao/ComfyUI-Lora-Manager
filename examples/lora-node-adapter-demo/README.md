# LoRA node adapter demo

This is a minimal third-party ComfyUI node pack demonstrating LoRA Manager adapter API version 1. It is intentionally independent of LoRA Manager's Python internals.

The demo provides `LoRA Adapter Demo Loader` with a plain multiline `text` widget. It supports:

- Send to Workflow target discovery;
- append and replace updates;
- immediate TriggerWord Toggle synchronization after sends and manual edits;
- standard `loaded_loras` output for `LoRA Trigger Words (LoraManager)`;
- graceful frontend degradation when LoRA Manager or adapter API version 1 is unavailable.

It deliberately omits autocomplete, a structured LoRA list, and other production loader features.

## Install for local testing

Copy this directory into ComfyUI's `custom_nodes` directory, alongside `ComfyUI-Lora-Manager`, then restart ComfyUI and reload the browser page:

```bash
cp -R examples/lora-node-adapter-demo /path/to/ComfyUI/custom_nodes/
```

When copied by that command, the frontend is served from `/extensions/lora-node-adapter-demo/lora_node_adapter_demo.js`.

## Manual verification

Open `example_workflow.json` in ComfyUI, or create these connections manually:

```text
CheckpointLoaderSimple.MODEL -> LoRA Adapter Demo Loader.model
CheckpointLoaderSimple.CLIP  -> LoRA Adapter Demo Loader.clip
LoRA Adapter Demo Loader.loaded_loras
  -> LoRA Trigger Words (LoraManager).lora_syntax
LoRA Trigger Words (LoraManager).trigger_words
  -> TriggerWord Toggle (LoraManager).trigger_words
```

Select a valid checkpoint before executing the workflow. The demo starts with empty LoRA text, so no LoRA is loaded until you send or enter one.

Verify that:

1. `LoRA Adapter Demo Loader` appears in LoRA Manager's Send to Workflow target selector.
2. Clicking Send appends LoRA syntax; Shift+click replaces it.
3. Sending a LoRA updates the connected TriggerWord Toggle after the short debounce.
4. Editing the demo node's text manually also updates the Toggle.
5. Bypassing the demo node clears its Toggle entries; restoring it repopulates them.
6. Saving and reloading the workflow preserves the demo text and restores Toggle entries.
7. Executing with a valid LoRA loads it and resolves its trigger words through the resolver node.

## Source map

- `__init__.py`: minimal Python loader and standard `loaded_loras` output.
- `web/lora_node_adapter_demo.js`: dynamic API import, adapter registration, append/replace handling, active-name extraction, and manual-change notification.
- `example_workflow.json`: loader, resolver, and Toggle connections.

See [Third-party LoRA node integration](../../docs/third-party-lora-node-integration.md) for the complete API contract. The repository's integration tests import these source files directly, so this example is also an executable specification of the adapter API.

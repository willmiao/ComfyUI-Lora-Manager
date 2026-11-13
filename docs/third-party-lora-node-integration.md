# Third-party LoRA node integration

LoRA Manager exposes a browser-side adapter API for third-party LoRA nodes. An adapter can:

- make its node classes available as **Send to ComfyUI / Send to Workflow** targets;
- receive LoRA or Recipe syntax in `append` or `replace` mode;
- optionally synchronize `TriggerWord Toggle (LoraManager)` nodes when the active LoRA set changes.

A separate `LoRA Trigger Words (LoraManager)` execution node resolves standard LoRA syntax into trigger words. This lets third-party loaders support trigger-word workflows without importing LoRA Manager's internal Python modules.

## Executable demo

The independent [LoRA node adapter demo](../examples/lora-node-adapter-demo/README.md) is a minimal third-party node pack using this API. Its frontend and Python sources are loaded directly by the integration tests, and its example workflow demonstrates the resolver and TriggerWord Toggle connections.

## Requirements and compatibility

Use a LoRA Manager build that exports LoRA node adapter API version 1 from:

```text
/extensions/ComfyUI-Lora-Manager/lora_node_adapters.js
```

Use dynamic `import()` if your extension also supports older LoRA Manager versions or must work when LoRA Manager is not installed. A static import of a missing module can prevent the rest of your frontend extension from loading.

The integration is optional: your node must retain its normal behavior when registration fails or the API is unavailable.

## Minimal Send to Workflow adapter

Register during your ComfyUI frontend extension's `setup()`:

```js
import { app } from "../../scripts/app.js";

let loraManagerApi = null;

app.registerExtension({
  name: "ExamplePack.LoraManagerIntegration",

  async setup() {
    try {
      loraManagerApi = await import(
        "/extensions/ComfyUI-Lora-Manager/lora_node_adapters.js"
      );

      if (loraManagerApi.LORA_NODE_ADAPTER_API_VERSION !== 1) {
        return;
      }

      loraManagerApi.registerLoraNodeAdapter({
        id: "example-pack",
        apiVersion: 1,
        nodeClasses: ["Example LoRA Loader"],

        applyLoraCode({ node, loraCode, mode }) {
          const widget = node.widgets?.find((item) => item.name === "text");
          if (!widget) {
            throw new Error("Example LoRA Loader text widget is unavailable");
          }

          const currentValue = String(widget.value ?? "").trim();
          widget.value =
            mode === "replace" || !currentValue
              ? loraCode
              : `${currentValue} ${loraCode}`;

          widget.callback?.(widget.value);
          node.setDirtyCanvas?.(true, true);
        },
      });
    } catch (error) {
      console.warn("LoRA Manager integration is unavailable", error);
      loraManagerApi = null;
    }
  },
});
```

`nodeClasses` contains exact ComfyUI `node.comfyClass` values, not node display titles. Do not use the user's renamed node title as an identifier.

The adapter owns the update. LoRA Manager does not guess which widget or internal fields a third-party node uses. In particular, `applyLoraCode` must:

1. apply `append` or `replace` semantics;
2. update the state used for workflow serialization and Python execution;
3. invoke the node's normal widget callback or equivalent state-sync logic;
4. request a canvas refresh when necessary.

Registration is safe after the graph and LoRA Manager registry have already initialized. LoRA Manager refreshes target discovery when adapters are registered or unregistered. Existing target exclusions, enabled-node filtering, subgraph references, and the target selector continue to apply.

`applyLoraCode` is synchronous in API version 1. Start no asynchronous state update that `getActiveLoraNames` would need to await.

## TriggerWord Toggle frontend synchronization

Add `getActiveLoraNames` if the adapted node can be connected to a TriggerWord Toggle:

```js
loraManagerApi.registerLoraNodeAdapter({
  id: "example-pack",
  apiVersion: 1,
  nodeClasses: ["Example LoRA Loader"],

  applyLoraCode({ node, loraCode, mode }) {
    // Update the node's real state and widgets.
  },

  getActiveLoraNames(node) {
    return node.exampleLoras
      .filter((lora) => lora.active)
      .map((lora) => lora.name);
  },
});
```

The function must return an iterable of LoRA names or relative paths understood by LoRA Manager's model cache. Return the node's own active LoRAs, not `<lora:...>` tags. `null` and `undefined` are treated as an empty set; a bare string is invalid because it would otherwise be iterated character by character.

LoRA Manager automatically synchronizes connected toggles:

- after `applyLoraCode` returns;
- after the adapted node changes between active and bypassed/muted modes;
- after a workflow is configured;
- after adapter registration.

When your own UI changes the active LoRA set, call the public notification function after updating your state:

```js
function onExampleLorasChanged(node) {
  // Update node.exampleLoras and the node's widgets first.
  loraManagerApi?.notifyLoraNodeChanged(node);
}
```

Typical notification points include text edits, adding or removing a LoRA, and enabling or disabling an entry. Do not call this inside `applyLoraCode`; LoRA Manager already does so.

Updates are debounced. Bypassed and muted nodes contribute no LoRAs. If the node has connected `LORA_STACK` inputs, LoRA Manager also aggregates active names from supported built-in and adapted upstream nodes.

`notifyLoraNodeChanged(node)` returns `false` when the node has no adapter or the adapter has no `getActiveLoraNames`; otherwise it returns `true` after scheduling synchronization. It is not a delivery acknowledgement.

## Execution-time trigger words

The browser adapter cannot add or change Python outputs. For graph-level integration, expose the active LoRAs from your Python node as a `STRING` containing standard syntax:

```text
<lora:name_or_relative_path:model_strength>
<lora:name_or_relative_path:model_strength:clip_strength>
```

Multiple entries can be separated by spaces, as with LoRA Manager's `loaded_loras` output. Then connect:

```text
Third-party loader.loaded_loras (STRING)
  -> LoRA Trigger Words (LoraManager).lora_syntax
  -> TriggerWord Toggle (LoraManager).trigger_words
```

The resolver's `trigger_words` output preserves LoRA and trigger-group order. It uses `",, "` between groups, matching LoRA Manager's built-in loaders. Unknown LoRAs and LoRAs without metadata contribute no trigger words.

Frontend synchronization follows connections directly from an adapted node to a TriggerWord Toggle and connections passing through `LoRA Trigger Words (LoraManager)`, so the same graph supports both immediate canvas updates and execution-time values.

API version 1 does not expose a public Python metadata resolver. Third-party nodes that must return trigger words directly from their own Python execution method remain responsible for that implementation; the resolver node is the supported low-coupling alternative.

## API reference

### `LORA_NODE_ADAPTER_API_VERSION`

The current adapter API version. Version 1 is the contract described by this document.

### `registerLoraNodeAdapter(adapter)`

Registers one adapter for one or more exact node classes and returns an idempotent unregister function.

Adapter fields:

| Field | Required | Description |
| --- | --- | --- |
| `id` | yes | Stable, non-empty identifier used in diagnostics; use your node-pack name. |
| `apiVersion` | no | Defaults to `1`. Explicitly pass `1` when checking the exported constant. |
| `nodeClasses` | yes | Non-empty array of exact `comfyClass` strings. |
| `applyLoraCode` | yes | Synchronous callback receiving `{ node, loraCode, mode }`. |
| `getActiveLoraNames` | no | Returns an iterable of active LoRA names for trigger-word synchronization. |

Each node class can have only one adapter. Registration rejects duplicate classes atomically, unsupported API versions, missing callbacks, and invalid names. The unregister function removes only the registration that returned it.

### `notifyLoraNodeChanged(node)`

Recomputes the active LoRA set through the node's adapter and schedules updates for connected TriggerWord Toggle nodes. Call it after third-party UI state changes.

## Error handling and delivery semantics

LoRA Manager catches and logs adapter exceptions without falling back to built-in widget assumptions. A failing adapter therefore does not cause LoRA Manager to write an arbitrary `inputWidget` on the third-party node.

The existing `/api/lm/update-lora-code` response confirms that the WebSocket update was sent. It does **not** confirm that a browser adapter found the node or applied the value successfully. Adapter callbacks cannot currently change the management page's success toast. End-to-end acknowledgements are outside adapter API version 1.

## Integration checklist

Test at least the following:

- append and replace with empty and non-empty node state;
- individual LoRAs and Recipes containing multiple LoRA tags;
- multiple targets and nodes inside subgraphs;
- widget display, serialized workflow state, and Python execution state after sending;
- manual LoRA edits and active/inactive changes;
- bypass/mute and restoration to an active mode;
- workflow save and reload;
- direct Toggle connections and connections through the trigger-word resolver;
- behavior with LoRA Manager absent or older than adapter API version 1.

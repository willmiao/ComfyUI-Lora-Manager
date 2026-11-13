import { app } from "../../scripts/app.js";

const DEMO_NODE_CLASS = "LoRA Adapter Demo Loader";
const LORA_PATTERN =
  /<lora:([^>]+?):([-+]?(?:\d+(?:\.\d*)?|\.\d+))(?::([-+]?(?:\d+(?:\.\d*)?|\.\d+)))?>/gi;
const LORA_MANAGER_ADAPTER_MODULE =
  "/extensions/ComfyUI-Lora-Manager/lora_node_adapters.js";

let loraManagerApi = null;

function getTextWidget(node) {
  const widget = node.widgets?.find((item) => item.name === "text");
  if (!widget) {
    throw new Error("LoRA Adapter Demo Loader text widget is unavailable");
  }
  return widget;
}

app.registerExtension({
  name: "ThirdPartyExample.LoraNodeAdapterDemo",

  async setup() {
    try {
      loraManagerApi = await import(LORA_MANAGER_ADAPTER_MODULE);
      if (loraManagerApi.LORA_NODE_ADAPTER_API_VERSION !== 1) {
        return;
      }

      loraManagerApi.registerLoraNodeAdapter({
        id: "lora-node-adapter-demo",
        apiVersion: 1,
        nodeClasses: [DEMO_NODE_CLASS],

        applyLoraCode({ node, loraCode, mode }) {
          const widget = getTextWidget(node);
          const currentValue = String(widget.value ?? "").trim();
          widget.value =
            mode === "replace" || !currentValue
              ? loraCode
              : `${currentValue} ${loraCode}`;
          widget.callback?.(widget.value);
          node.setDirtyCanvas?.(true, true);
        },

        getActiveLoraNames(node) {
          const widget = getTextWidget(node);
          return Array.from(
            String(widget.value ?? "").matchAll(LORA_PATTERN),
            (match) => match[1]
          );
        },
      });
    } catch (error) {
      loraManagerApi = null;
      console.warn("LoRA Manager adapter integration is unavailable", error);
    }
  },

  nodeCreated(node) {
    if (node.comfyClass !== DEMO_NODE_CLASS) {
      return;
    }

    node.serialize_widgets = true;
    const widget = getTextWidget(node);
    const originalCallback = widget.callback;
    widget.callback = function (...args) {
      originalCallback?.apply(this, args);
      loraManagerApi?.notifyLoraNodeChanged(node);
    };
  },
});

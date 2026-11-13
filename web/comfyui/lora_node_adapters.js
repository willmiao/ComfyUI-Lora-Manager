import {
  collectActiveLorasFromChain,
  updateConnectedTriggerWords,
} from "./utils.js";
import {
  getLoraNodeAdapter,
  hasLoraNodeAdapter,
  onLoraNodeAdaptersChanged,
  registerLoraNodeAdapter,
  LORA_NODE_ADAPTER_API_VERSION,
} from "./lora_node_adapter_registry.js";

export {
  getLoraNodeAdapter,
  hasLoraNodeAdapter,
  onLoraNodeAdaptersChanged,
  registerLoraNodeAdapter,
  LORA_NODE_ADAPTER_API_VERSION,
};

export function notifyLoraNodeChanged(node) {
  const adapter = getLoraNodeAdapter(node);
  if (!adapter?.getActiveLoraNames) {
    return false;
  }

  try {
    const activeLoraNames = collectActiveLorasFromChain(node);
    updateConnectedTriggerWords(node, activeLoraNames);
    return true;
  } catch (error) {
    console.error(
      `LoRA Manager: failed to synchronize trigger words for adapter ${adapter.id}`,
      error
    );
    return false;
  }
}

export function applyLoraCodeToNode(node, loraCode, mode) {
  const adapter = getLoraNodeAdapter(node);
  if (!adapter) {
    return false;
  }

  try {
    adapter.applyLoraCode({ node, loraCode, mode });
    notifyLoraNodeChanged(node);
    return true;
  } catch (error) {
    console.error(
      `LoRA Manager: adapter ${adapter.id} failed to apply LoRA code`,
      error
    );
    return true;
  }
}

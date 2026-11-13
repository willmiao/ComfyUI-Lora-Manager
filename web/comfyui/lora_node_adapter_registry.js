export const LORA_NODE_ADAPTER_API_VERSION = 1;

const registryState = globalThis.__lmLoraNodeAdapterRegistry ?? {
  adaptersByClass: new Map(),
  changeListeners: new Set(),
};
globalThis.__lmLoraNodeAdapterRegistry = registryState;

const { adaptersByClass, changeListeners } = registryState;

function notifyChangeListeners() {
  for (const listener of changeListeners) {
    try {
      listener();
    } catch (error) {
      console.error("LoRA Manager: adapter change listener failed", error);
    }
  }
}

function getNodeClass(nodeOrClass) {
  return typeof nodeOrClass === "string"
    ? nodeOrClass
    : nodeOrClass?.comfyClass;
}

export function getLoraNodeAdapter(nodeOrClass) {
  const nodeClass = getNodeClass(nodeOrClass);
  return nodeClass ? adaptersByClass.get(nodeClass) ?? null : null;
}

export function hasLoraNodeAdapter(nodeOrClass) {
  return getLoraNodeAdapter(nodeOrClass) !== null;
}

export function onLoraNodeAdaptersChanged(listener) {
  if (typeof listener !== "function") {
    throw new TypeError("LoRA Manager: adapter change listener must be a function");
  }

  changeListeners.add(listener);
  return () => changeListeners.delete(listener);
}

export function registerLoraNodeAdapter(adapter) {
  if (!adapter || typeof adapter !== "object") {
    throw new TypeError("LoRA Manager: a LoRA node adapter object is required");
  }
  if (typeof adapter.id !== "string" || !adapter.id.trim()) {
    throw new TypeError("LoRA Manager: adapter.id must be a non-empty string");
  }
  if (!Array.isArray(adapter.nodeClasses) || adapter.nodeClasses.length === 0) {
    throw new TypeError("LoRA Manager: adapter.nodeClasses must be a non-empty array");
  }
  if (adapter.nodeClasses.some((name) => typeof name !== "string" || !name.trim())) {
    throw new TypeError("LoRA Manager: adapter.nodeClasses must contain non-empty strings");
  }
  if (typeof adapter.applyLoraCode !== "function") {
    throw new TypeError("LoRA Manager: adapter.applyLoraCode must be a function");
  }
  if (
    adapter.getActiveLoraNames !== undefined &&
    typeof adapter.getActiveLoraNames !== "function"
  ) {
    throw new TypeError("LoRA Manager: adapter.getActiveLoraNames must be a function");
  }

  const apiVersion = adapter.apiVersion ?? LORA_NODE_ADAPTER_API_VERSION;
  if (apiVersion !== LORA_NODE_ADAPTER_API_VERSION) {
    throw new RangeError(
      `LoRA Manager: unsupported LoRA node adapter API version ${apiVersion}`
    );
  }

  const nodeClasses = [...new Set(adapter.nodeClasses)];
  for (const nodeClass of nodeClasses) {
    const existing = adaptersByClass.get(nodeClass);
    if (existing) {
      throw new Error(
        `LoRA Manager: ${nodeClass} is already registered by adapter ${existing.id}`
      );
    }
  }

  const registration = Object.freeze({
    ...adapter,
    apiVersion,
    nodeClasses: Object.freeze(nodeClasses),
  });
  for (const nodeClass of nodeClasses) {
    adaptersByClass.set(nodeClass, registration);
  }
  notifyChangeListeners();

  let active = true;
  return () => {
    if (!active) {
      return;
    }
    active = false;

    for (const nodeClass of nodeClasses) {
      if (adaptersByClass.get(nodeClass) === registration) {
        adaptersByClass.delete(nodeClass);
      }
    }
    notifyChangeListeners();
  };
}

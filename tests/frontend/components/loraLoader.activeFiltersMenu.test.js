import { describe, it, expect, beforeEach, vi } from "vitest";

const {
  APP_MODULE,
  API_MODULE,
  UTILS_MODULE,
  SETTINGS_MODULE,
  LORA_LOADER_MODULE,
} = vi.hoisted(() => ({
  APP_MODULE: new URL("../../../scripts/app.js", import.meta.url).pathname,
  API_MODULE: new URL("../../../scripts/api.js", import.meta.url).pathname,
  UTILS_MODULE: new URL("../../../web/comfyui/utils.js", import.meta.url).pathname,
  SETTINGS_MODULE: new URL("../../../web/comfyui/settings.js", import.meta.url).pathname,
  LORA_LOADER_MODULE: new URL("../../../web/comfyui/lora_loader.js", import.meta.url).pathname,
}));

const extensionState = { current: null };
const registerExtensionMock = vi.fn((extension) => {
  extensionState.current = extension;
});

vi.mock(APP_MODULE, () => ({
  app: {
    registerExtension: registerExtensionMock,
    graph: {},
  },
}));

vi.mock(API_MODULE, () => ({
  api: {
    addEventListener: vi.fn(),
  },
}));

const showToastMock = vi.fn();

vi.mock(UTILS_MODULE, () => ({
  collectActiveLorasFromChain: vi.fn(),
  updateConnectedTriggerWords: vi.fn(),
  mergeLoras: vi.fn(),
  chainCallback: (proto, property, callback) => {
    proto[property] = callback;
  },
  getAllGraphNodes: vi.fn(),
  getNodeFromGraph: vi.fn(),
  getWidgetByName: vi.fn(),
  getWidgetSerializedValue: vi.fn(),
  showToast: showToastMock,
}));

const getActiveFiltersPreferenceMock = vi.fn();
const setSettingValueMock = vi.fn();

vi.mock(SETTINGS_MODULE, () => ({
  LORA_ACTIVE_FILTERS_AUTOCOMPLETE_SETTING_ID:
    "loramanager.lora_active_filters_autocomplete",
  SETTING_TOGGLED_EVENT_NAME: "lora-manager:setting-toggled",
  getLoraActiveFiltersAutocompletePreference: getActiveFiltersPreferenceMock,
  setLoraManagerSettingValue: setSettingValueMock,
}));

async function registerNodeType(comfyClass) {
  await import(LORA_LOADER_MODULE);
  const extension = extensionState.current;
  expect(extension).toBeDefined();
  const nodeType = { comfyClass, prototype: {} };
  await extension.beforeRegisterNodeDef(nodeType, {}, {});
  return nodeType;
}

function getMenuOption(nodeType, enabled) {
  getActiveFiltersPreferenceMock.mockReturnValue(enabled);
  const options = [];
  nodeType.prototype.getExtraMenuOptions(null, options);
  return options.find(
    (option) =>
      option &&
      typeof option.content === "string" &&
      option.content.startsWith("Active Filters Search:")
  );
}

describe("Lora Loader active-filters context menu", () => {
  beforeEach(() => {
    vi.resetModules();
    extensionState.current = null;
    registerExtensionMock.mockClear();
    showToastMock.mockClear();
    getActiveFiltersPreferenceMock.mockReset();
    setSettingValueMock.mockReset();
    setSettingValueMock.mockResolvedValue(true);
  });

  it.each([
    "Lora Loader (LoraManager)",
    "Lora Stacker (LoraManager)",
    "WanVideo Lora Select (LoraManager)",
    "Create Hook LoRA (LoraManager)",
  ])("adds the toggle entry to the %s context menu", async (comfyClass) => {
    const nodeType = await registerNodeType(comfyClass);

    const option = getMenuOption(nodeType, false);
    expect(option).toBeDefined();
    expect(option.content).toContain("Active Filters Search: OFF");
    expect(option.content).toContain("/activefilters to enable");
  });

  it("shows the disable hint when active-filters search is on", async () => {
    const nodeType = await registerNodeType("Lora Loader (LoraManager)");

    const option = getMenuOption(nodeType, true);
    expect(option.content).toContain("Active Filters Search: ON");
    expect(option.content).toContain("/noactivefilters to disable");
  });

  it("toggles the setting and toasts feedback", async () => {
    const nodeType = await registerNodeType("Lora Loader (LoraManager)");

    const enableOption = getMenuOption(nodeType, false);
    await enableOption.callback();

    expect(setSettingValueMock).toHaveBeenCalledWith(
      "loramanager.lora_active_filters_autocomplete",
      true
    );
    expect(showToastMock).toHaveBeenCalledWith(
      expect.objectContaining({ summary: "Active Filters Search Enabled" })
    );

    const disableOption = getMenuOption(nodeType, true);
    await disableOption.callback();

    expect(setSettingValueMock).toHaveBeenCalledWith(
      "loramanager.lora_active_filters_autocomplete",
      false
    );
    expect(showToastMock).toHaveBeenCalledWith(
      expect.objectContaining({ summary: "Active Filters Search Disabled" })
    );
  });
});

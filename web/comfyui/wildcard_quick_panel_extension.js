import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";
import { COMMAND_IDS, DEFAULT_KEYBINDINGS } from "./shortcuts.js";
import { reloadWildcardQuickPanel, toggleWildcardQuickPanel } from "./wildcard_quick_panel.js";

app.registerExtension({
  name: "LoraManager.WildcardQuickPanel",
  commands: [{
    id: COMMAND_IDS.quickWildcardPicker,
    label: "Global Wildcards",
    icon: "pi pi-bolt",
    function: toggleWildcardQuickPanel,
  }],
  keybindings: [{
    combo: DEFAULT_KEYBINDINGS[COMMAND_IDS.quickWildcardPicker],
    commandId: COMMAND_IDS.quickWildcardPicker,
  }],
  setup() {
    api.addEventListener("lm_wildcards_changed", () => reloadWildcardQuickPanel());
  },
});

export { openWildcardQuickPanel, toggleWildcardQuickPanel } from "./wildcard_quick_panel.js";

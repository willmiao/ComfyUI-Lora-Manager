import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";
import { COMMAND_IDS } from "./shortcuts.js";
import { reloadWildcardQuickPanel, toggleWildcardQuickPanel } from "./wildcard_quick_panel.js";

app.registerExtension({
  name: "LoraManager.WildcardQuickPanel",
  commands: [{
    id: COMMAND_IDS.quickWildcardPicker,
    label: "Global Wildcards",
    icon: "pi pi-bolt",
    function: toggleWildcardQuickPanel,
  }],
  setup() {
    api.addEventListener("lm_wildcards_changed", () => reloadWildcardQuickPanel());
  },
});

export { openWildcardQuickPanel, toggleWildcardQuickPanel } from "./wildcard_quick_panel.js";

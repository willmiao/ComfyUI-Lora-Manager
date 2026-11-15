import { app } from "../../scripts/app.js";
import { COMMAND_IDS, DEFAULT_KEYBINDINGS } from "./shortcuts.js";
import { openRecipeQuickPanel, toggleRecipeQuickPanel } from "./lora_quick_panel.js";

const COMMAND_ID = COMMAND_IDS.quickRecipePicker;

app.registerExtension({
  name: "LoraManager.RecipeQuickPanel",
  commands: [{
    id: COMMAND_ID,
    label: "Quick Recipe Picker",
    icon: "pi pi-search",
    function: toggleRecipeQuickPanel,
  }],
  keybindings: [{ combo: DEFAULT_KEYBINDINGS[COMMAND_ID], commandId: COMMAND_ID }],
});

export { openRecipeQuickPanel, toggleRecipeQuickPanel };

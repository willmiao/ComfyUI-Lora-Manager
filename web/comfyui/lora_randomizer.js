import { app } from "../../scripts/app.js";
import {
  getActiveLorasFromNode,
  updateDownstreamLoaders,
  chainCallback,
} from "./utils.js";

app.registerExtension({
  name: "LoraManager.LoraRandomizer",

  async beforeRegisterNodeDef(nodeType, nodeData, app) {
    if (nodeType.comfyClass === "Lora Randomizer (LoraManager)") {
      chainCallback(nodeType.prototype, "onNodeCreated", async function () {
        this.serialize_widgets = true;

        let _mode = this.mode;
        const self = this;
        Object.defineProperty(this, 'mode', {
          get() {
            return _mode;
          },
          set(value) {
            const oldValue = _mode;
            _mode = value;

            if (self.onModeChange) {
              self.onModeChange(value, oldValue);
            }
          }
        });

        this.onModeChange = function(newMode, oldMode) {
          const isNodeActive = newMode === 0 || newMode === 3;
          const activeLoraNames = isNodeActive ? getActiveLorasFromNode(self) : new Set();
          updateDownstreamLoaders(self);
        };
      });
    }
  },
});

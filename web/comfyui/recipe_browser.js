import { app } from "../../scripts/app.js";
import { addRecipeBrowserWidget } from "./recipes_widget.js";

const NODE_NAME = "Recipe Browser (LoraManager)";

app.registerExtension({
  name: "LoraManager.RecipeBrowser",

  async beforeRegisterNodeDef(nodeType, nodeData) {
    if (nodeData.name !== NODE_NAME) return;

    const origOnNodeCreated = nodeType.prototype.onNodeCreated;

    nodeType.prototype.onNodeCreated = function () {
      const r = origOnNodeCreated?.apply(this, arguments);

      if (!this.__lmRecipeBrowserAttached) {
        this.__lmRecipeBrowserAttached = true;

        addRecipeBrowserWidget(this, "recipe_id", {}, () => {
          this.setDirtyCanvas(true, true);
          this.graph?.setDirtyCanvas(true, true);
        });
      }

      return r;
    };
  },
});
import { app } from "../../scripts/app.js";
import { chainCallback, getWidgetByName } from "./utils.js";

app.registerExtension({
  name: "LoraManager.SaveImageExtraOutput",

  async beforeRegisterNodeDef(nodeType, nodeData) {
    if (nodeData.name !== "Save Image (LoraManager)") {
      return;
    }

    chainCallback(nodeType.prototype, "onNodeCreated", function () {
      // Conditional widget visibility for webp_method / jpeg_subsampling
      const formatWidget = getWidgetByName(this, "file_format");
      const webpMethodWidget = getWidgetByName(this, "webp_method");
      const jpegSubWidget = getWidgetByName(this, "jpeg_subsampling");

      function updateFormatConditional() {
        const fmt = formatWidget?.value;
        if (webpMethodWidget) {
          webpMethodWidget.disabled = fmt !== "webp";
          webpMethodWidget.hidden = fmt !== "webp";
        }
        if (jpegSubWidget) {
          jpegSubWidget.disabled = fmt !== "jpeg";
          jpegSubWidget.hidden = fmt !== "jpeg";
        }
      }

      // Set initial state
      updateFormatConditional();

      // Watch for format changes
      if (formatWidget) {
        const origCallback = formatWidget.callback;
        formatWidget.callback = function (value) {
          origCallback?.call(this, value);
          updateFormatConditional();
        };
      }
    });
  },
});

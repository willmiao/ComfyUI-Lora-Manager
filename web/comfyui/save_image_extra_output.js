import { app } from "../../scripts/app.js";
import { chainCallback, getAllGraphNodes, getWidgetByName } from "./utils.js";

/**
 * Resolve %NodeTitle.WidgetName% placeholders in a string using the current graph.
 *
 * Patterns supported:
 *   %NodeTitle.WidgetName%  – widget value from a node (by title or "Node name for S&R")
 *
 * All other %text% patterns are passed through unchanged so the backend's
 * format_filename can handle them (e.g. %seed%, %model%, %pprompt%, %width%,
 * %height%). In particular %date:format% must NOT be resolved here: doing so
 * would bake the queue time into the serialized prompt instead of the save
 * time, and prompts queued within the same second (or re-run from history)
 * would share one timestamp and overwrite each other's files.
 */
function applyTextReplacements(value) {
  if (!value || typeof value !== "string" || !value.includes("%")) {
    return value;
  }

  // Collect all nodes from the entire graph hierarchy (including subgraphs)
  const allNodes = getAllGraphNodes(app.graph);

  return value.replace(/%([^%]+)%/g, function (match, text) {
    // Backend-handled patterns (checked before splitting on "." so date
    // formats containing dots, e.g. %date:yyyy.M.d%, are not mistaken for
    // %NodeTitle.WidgetName% placeholders).
    if (text.startsWith("date:")) {
      return match;
    }

    const split = text.split(".");
    if (split.length !== 2) {
      // %width% and %height% are left for the backend to handle
      if (text !== "width" && text !== "height") {
        console.warn(
          "[Save Image (LoraManager)] Unknown placeholder: %" + text + "%"
        );
      }
      return match;
    }

    // Try finding the node by its "Node name for S&R" property first
    let nodes = allNodes
      .filter((n) => n.node.properties?.["Node name for S&R"] === split[0])
      .map((n) => n.node);

    // Fall back to matching by node title
    if (!nodes.length) {
      nodes = allNodes
        .filter((n) => n.node.title === split[0])
        .map((n) => n.node);
    }

    if (!nodes.length) {
      console.warn(
        "[Save Image (LoraManager)] Node not found: " + split[0]
      );
      return match;
    }

    if (nodes.length > 1) {
      console.warn(
        "[Save Image (LoraManager)] Multiple nodes matched '" +
          split[0] +
          "', using first match"
      );
    }

    const node = nodes[0];
    const widget = node.widgets?.find((w) => w.name === split[1]);
    if (!widget) {
      console.warn(
        "[Save Image (LoraManager)] Widget '" +
          split[1] +
          "' not found on node " +
          split[0]
      );
      return match;
    }

    // Sanitize the value: replace characters invalid for filenames
    // eslint-disable-next-line no-control-regex
    return ((widget.value ?? "") + "").replaceAll(
      /[/?<>\\:*|"\x00-\x1F\x7F]/g,
      "_"
    );
  });
}

app.registerExtension({
  name: "LoraManager.SaveImageExtraOutput",

  async beforeRegisterNodeDef(nodeType, nodeData) {
    if (nodeData.name !== "Save Image (LoraManager)") {
      return;
    }

    chainCallback(nodeType.prototype, "onNodeCreated", function () {
      // Find the filename_prefix widget
      const widget = getWidgetByName(this, "filename_prefix");
      if (!widget) {
        console.warn(
          "[Save Image (LoraManager)] filename_prefix widget not found"
        );
        return;
      }

      // Override serialization to resolve %NodeTitle.WidgetName% placeholders
      widget.serializeValue = () => {
        return applyTextReplacements(widget.value);
      };

      // --- Conditional widget visibility for webp_method / jpeg_subsampling ---
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

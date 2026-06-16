import { app } from "../../scripts/app.js";
import { chainCallback, getAllGraphNodes, getWidgetByName } from "./utils.js";

/**
 * Format a date string using the given pattern (e.g. "yyyy-MM-dd").
 * Supports: yyyy, yy, MM, M, dd, d, hh, h, mm, m, ss, s
 */
function formatDate(text, date) {
  const pad = (n, len) => n.toString().padStart(len, "0");
  // Order matters: longer patterns first to avoid partial substring matches.
  // The original ComfyUI frontend uses the same ordered-alternation approach.
  return text
    .replace(/yyyy/g, () => date.getFullYear().toString())
    .replace(/yy/g, () => pad(date.getFullYear() % 100, 2))
    .replace(/MM/g, () => pad(date.getMonth() + 1, 2))
    .replace(/M/g, () => (date.getMonth() + 1).toString())
    .replace(/dd/g, () => pad(date.getDate(), 2))
    .replace(/d/g, () => date.getDate().toString())
    .replace(/hh/g, () => pad(date.getHours(), 2))
    .replace(/h/g, () => date.getHours().toString())
    .replace(/mm/g, () => pad(date.getMinutes(), 2))
    .replace(/m/g, () => date.getMinutes().toString())
    .replace(/ss/g, () => pad(date.getSeconds(), 2))
    .replace(/s/g, () => date.getSeconds().toString());
}

/**
 * Resolve %NodeTitle.WidgetName% placeholders in a string using the current graph.
 *
 * Patterns supported:
 *   %NodeTitle.WidgetName%  – widget value from a node (by title or "Node name for S&R")
 *   %date:format%           – current date/time formatted (e.g. %date:yyyy-MM-dd%)
 *   %width%, %height%       – left as-is, handled by the backend
 *
 * All other %text% patterns are passed through unchanged (they may be handled by
 * the backend's format_filename, e.g. %seed%, %model%, %pprompt%).
 */
function applyTextReplacements(value) {
  if (!value || typeof value !== "string" || !value.includes("%")) {
    return value;
  }

  // Collect all nodes from the entire graph hierarchy (including subgraphs)
  const allNodes = getAllGraphNodes(app.graph);

  return value.replace(/%([^%]+)%/g, function (match, text) {
    const split = text.split(".");
    if (split.length !== 2) {
      // Handle %date:format% patterns
      if (split[0].startsWith("date:")) {
        return formatDate(split[0].substring(5), new Date());
      }

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
    });
  },
});

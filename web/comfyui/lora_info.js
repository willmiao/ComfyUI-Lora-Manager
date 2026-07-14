import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";
import {
  getLinkFromGraph,
  chainCallback,
} from "./utils.js";

const LORA_INFO_CLASS = "Lora Info (LoraManager)";

/**
 * Find Lora Info nodes directly connected to the given node's outputs.
 * Mirrors the getConnectedTriggerToggleNodes pattern from utils.js.
 * @param {object} node - The source node to check outputs from
 * @returns {object[]} Array of connected Lora Info node instances
 */
export function getConnectedLoraInfoNodes(node) {
  const connectedNodes = [];

  if (!node?.outputs) {
    return connectedNodes;
  }

  for (const output of node.outputs) {
    if (!output?.links?.length) {
      continue;
    }

    for (const linkId of output.links) {
      const link = getLinkFromGraph(node.graph, linkId);
      if (!link) {
        continue;
      }

      const targetNode = node.graph?.getNodeById?.(link.target_id);
      if (targetNode && targetNode.comfyClass === LORA_INFO_CLASS) {
        connectedNodes.push(targetNode);
      }
    }
  }

  return connectedNodes;
}

/**
 * Fetch notes for the selected lora and push them to all directly connected
 * Lora Info nodes (no recursive chain traversal — only direct connections).
 * @param {object} node - The source LoRA Loader/Stacker node
 * @param {object|null} selection - The current lora selection {name, active, entry}
 */
export async function updateConnectedLoraInfoNodes(node, selection) {
  if (!node) {
    return;
  }

  const infoNodes = getConnectedLoraInfoNodes(node);

  if (infoNodes.length === 0) {
    return;
  }

  // No selection or inactive — clear the display on all connected info nodes
  if (!selection?.name || !selection?.active) {
    for (const infoNode of infoNodes) {
      infoNode.__loraInfoReqId = (infoNode.__loraInfoReqId || 0) + 1;
      if (typeof infoNode._setLoraInfo === "function") {
        infoNode._setLoraInfo(null);
      } else {
        infoNode.__pendingLoraInfo = null;
      }
    }
    return;
  }

  // Bump request token on each info node to guard against stale async responses
  for (const infoNode of infoNodes) {
    infoNode.__loraInfoReqId = (infoNode.__loraInfoReqId || 0) + 1;
  }
  const reqIdSnapshot = new Map();
  for (const infoNode of infoNodes) {
    reqIdSnapshot.set(infoNode, infoNode.__loraInfoReqId);
  }

  // Fetch notes for the selected lora
  try {
    const response = await api.fetchApi(
      `/lm/loras/get-notes?name=${encodeURIComponent(selection.name)}`,
      { method: "GET" }
    );

    if (!response?.ok) {
      throw new Error(`Failed to fetch notes for ${selection.name}`);
    }

    const data = await response.json();
    const infoData = {
      name: selection.name,
      notes: data?.notes || "",
      filePath: data?.file_path || "",
    };

    for (const infoNode of infoNodes) {
      // Discard if a newer request has been issued for this node
      if (infoNode.__loraInfoReqId !== reqIdSnapshot.get(infoNode)) {
        continue;
      }
      if (typeof infoNode._setLoraInfo === "function") {
        infoNode._setLoraInfo(infoData);
      } else {
        infoNode.__pendingLoraInfo = infoData;
      }
    }
  } catch (error) {
    console.error("Error fetching notes for lora info:", error);

    const errorData = {
      name: selection.name,
      notes: "[Error loading notes]",
      filePath: "",
    };

    for (const infoNode of infoNodes) {
      if (infoNode.__loraInfoReqId !== reqIdSnapshot.get(infoNode)) {
        continue;
      }
      if (typeof infoNode._setLoraInfo === "function") {
        infoNode._setLoraInfo(errorData);
      } else {
        infoNode.__pendingLoraInfo = errorData;
      }
    }
  }
}

app.registerExtension({
  name: "LoraManager.LoraInfo",

  beforeRegisterNodeDef(nodeType, nodeData) {
    if (nodeData.name !== LORA_INFO_CLASS) {
      return;
    }

    chainCallback(nodeType.prototype, "onNodeCreated", function () {
      // Add wire-only input for receiving connections from LoRA nodes
      this.addInput("lora_source", "*", { shape: 7 });

      // Forward lora info data to the Vue widget when available.
      this._setLoraInfo = function (data) {
        const widget = this.widgets?.find(
          (w) => w.type === "LORA_INFO_DISPLAY"
        );
        if (widget) {
          if (typeof widget._setLoraInfo === "function") {
            widget._setLoraInfo(data);
          } else {
            widget.__pendingLoraInfo = data;
          }
        }
      };
    });

    // When the lora_source wire is disconnected, clear the display.
    const origOnConnectionsChange = nodeType.prototype.onConnectionsChange;
    nodeType.prototype.onConnectionsChange = function (type, index, connected, link_info) {
      if (origOnConnectionsChange) {
        origOnConnectionsChange.apply(this, arguments);
      }
      // type 1 = input connection change; disconnected = !connected
      if (type === 1 && !connected) {
        const input = this.inputs?.[index];
        if (input?.name === "lora_source") {
          // Check if any lora_source input still has a connection
          const hasLoraSourceConnection = this.inputs?.some(
            (inp) => inp.name === "lora_source" && inp.link != null
          );
          if (!hasLoraSourceConnection) {
            this._setLoraInfo?.(null);
          }
        }
      }
    };
  },
});

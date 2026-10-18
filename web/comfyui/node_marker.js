import { app } from "../../scripts/app.js";

// =============================================================================
// Node Marker – right-click node marking (no dedicated node required)
//
// Adds a "🎯 Mark as →" submenu with role options to any node's context menu.
// Roles are stored in ``node.properties.lm_marker_role`` and automatically
// persist with the workflow JSON.
//
// A separate "Exclude from Send Targets" toggle stores
// ``node.properties.lm_exclude_send``: such nodes never appear as send
// targets, regardless of capabilities or markers.
//
// Two categories:
//   send_* – consumed by the standalone UI's "Send to Workflow" feature
//   meta_* – consumed by the metadata processor to override heuristic inference
//
// The workflow registry reads these markers and makes them available to the
// standalone UI (e.g. ``sendEmbeddingToWorkflow`` also considers nodes marked
// as ``send_prompt_target``).
// =============================================================================

const SEND_ROLES = {
  send_prompt_target: {
    label: "Send Prompt Target",
    emoji: "\uD83D\uDCDD",
  },
  send_gen_params: {
    label: "Send Gen Params Target",
    emoji: "\uD83D\uDD27",
  },
};

const META_ROLES = {
  meta_primary_model: {
    label: "Meta hints: Primary Model",
    emoji: "\uD83D\uDCA1",
  },
  meta_primary_sampler: {
    label: "Meta hints: Primary Sampler",
    emoji: "\uD83D\uDCA1",
  },
  meta_positive_prompt: {
    label: "Meta hints: Positive Prompt",
    emoji: "\uD83D\uDCA1",
  },
  meta_negative_prompt: {
    label: "Meta hints: Negative Prompt",
    emoji: "\uD83D\uDCA1",
  },
};

// Flat lookup for setMarker / getMarker / clearMarker
const ROLES = { ...SEND_ROLES, ...META_ROLES };

// ---- Helpers ----------------------------------------------------------------

function getMarker(node) {
  return node?.properties?.lm_marker_role ?? null;
}

function setMarker(node, roleKey) {
  if (!node || !ROLES[roleKey]) return;
  node.properties = node.properties || {};
  node.properties.lm_marker_role = roleKey;

  // Save original title if not already saved, then prefix with emoji
  if (!node.properties.lm_marker_original_title) {
    node.properties.lm_marker_original_title = node.title || "";
  }
  const def = ROLES[roleKey];
  node.title = `${def.emoji} ${node.properties.lm_marker_original_title}`;

  if (typeof node.setDirtyCanvas === "function") {
    node.setDirtyCanvas(true, true);
  }
  triggerRegistryRefresh();
}

function clearMarker(node) {
  if (!node) return;
  delete node.properties.lm_marker_role;

  // Restore original title: prefer stripping emoji from current title
  // (captures user renames after marking), fall back to saved original.
  const cleaned = node.title?.replace(
    /^(\u2709\uFE0F?|\u2699\uFE0F?|\uD83D\uDCDD|\uD83C\uDF9B\uFE0F?|\uD83D\uDD27|\uD83D\uDCA1)\s*/,
    ''
  );
  if (cleaned && cleaned !== node.title) {
    node.title = cleaned;
  } else {
    const orig = node.properties.lm_marker_original_title;
    if (orig !== undefined) {
      node.title = orig;
    }
  }
  delete node.properties.lm_marker_original_title;

  if (typeof node.setDirtyCanvas === "function") {
    node.setDirtyCanvas(true, true);
  }
  triggerRegistryRefresh();
}

function triggerRegistryRefresh() {
  // workflow_registry.js listens for this event to re-scan the graph.
  window.dispatchEvent(new CustomEvent("lm_marker_changed"));
}

// ---- Send-target exclusion toggle -------------------------------------------

function isExcludedFromSend(node) {
  return node?.properties?.lm_exclude_send === true;
}

function toggleExcludeFromSend(node) {
  if (!node) return;
  node.properties = node.properties || {};
  if (node.properties.lm_exclude_send) {
    delete node.properties.lm_exclude_send;
  } else {
    node.properties.lm_exclude_send = true;
  }

  if (typeof node.setDirtyCanvas === "function") {
    node.setDirtyCanvas(true, true);
  }
  triggerRegistryRefresh();
}

// ---- Submenu builder --------------------------------------------------------

function buildSubmenuOptions(node) {
  const currentRole = getMarker(node);
  const options = [];

  const buildGroup = (roles) => {
    for (const [key, def] of Object.entries(roles)) {
      const isActive = currentRole === key;
      options.push({
        content: `${isActive ? "\u2713 " : ""}${def.label}`,
        disabled: isActive,
        callback: () => setMarker(node, key),
      });
    }
  };

  buildGroup(SEND_ROLES);
  options.push(null);  // separator
  buildGroup(META_ROLES);

  if (currentRole) {
    options.push(null);  // separator
    options.push({
      content: "Clear marker",
      callback: () => clearMarker(node),
    });
  }

  return options;
}

function buildMenuItems(node) {
  const excluded = isExcludedFromSend(node);
  return [
    null,
    {
      content: "\uD83C\uDFAF Mark as",
      has_submenu: true,
      submenu: {
        options: buildSubmenuOptions(node),
      },
    },
    {
      content: `${excluded ? "\u2713 " : ""}\uD83D\uDEAB Exclude from Send Targets`,
      callback: () => toggleExcludeFromSend(node),
    },
  ];
}

// ---- Extension --------------------------------------------------------------

app.registerExtension({
  name: "LoraManager.NodeMarker",
  getNodeMenuItems(node) {
    return buildMenuItems(node);
  },
});

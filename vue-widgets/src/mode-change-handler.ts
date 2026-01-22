/**
 * Mode change handler for LoRA provider nodes.
 *
 * Provides common mode change logic for nodes that provide LoRA configurations:
 * - Lora Stacker (LoraManager)
 * - Lora Randomizer (LoraManager)
 * - Lora Cycler (LoraManager)
 */

/**
 * List of node types that act as LoRA providers in the workflow chain.
 * These nodes can be traversed when collecting active LoRAs and can trigger
 * downstream loader updates when their mode or active LoRAs change.
 */
export const LORA_PROVIDER_NODE_TYPES = [
  "Lora Stacker (LoraManager)",
  "Lora Randomizer (LoraManager)",
  "Lora Cycler (LoraManager)",
] as const;

export type LoraProviderNodeType = typeof LORA_PROVIDER_NODE_TYPES[number];

/**
 * Check if a node class is a LoRA provider node.
 */
export function isLoraProviderNode(comfyClass: string): comfyClass is LoraProviderNodeType {
  return LORA_PROVIDER_NODE_TYPES.includes(comfyClass as LoraProviderNodeType);
}

/**
 * Extract active LoRA filenames from a node based on its type.
 *
 * For Lora Stacker and Lora Randomizer: extracts from lorasWidget (array of loras, filtered by active)
 * For Lora Cycler: extracts from cycler_config widget (single current_lora_filename)
 */
export function getActiveLorasFromNodeByType(node: any): Set<string> {
  const comfyClass = node?.comfyClass;

  if (comfyClass === "Lora Cycler (LoraManager)") {
    return extractFromCyclerConfig(node);
  }

  // Default: use lorasWidget (works for Stacker and Randomizer)
  return extractFromLorasWidget(node);
}

/**
 * Extract active LoRAs from a node's lorasWidget.
 * Used by Lora Stacker and Lora Randomizer.
 */
function extractFromLorasWidget(node: any): Set<string> {
  const activeLoraNames = new Set<string>();
  const lorasWidget = node.lorasWidget || node.widgets?.find((w: any) => w.name === 'loras');

  if (lorasWidget?.value) {
    lorasWidget.value.forEach((lora: any) => {
      if (lora.active) {
        activeLoraNames.add(lora.name);
      }
    });
  }

  return activeLoraNames;
}

/**
 * Extract the active LoRA from a Lora Cycler node.
 * The Cycler has only one active LoRA at a time, stored in cycler_config.current_lora_filename.
 */
function extractFromCyclerConfig(node: any): Set<string> {
  const activeLoraNames = new Set<string>();
  const cyclerWidget = node.widgets?.find((w: any) => w.name === 'cycler_config');

  if (cyclerWidget?.value?.current_lora_filename) {
    activeLoraNames.add(cyclerWidget.value.current_lora_filename);
  }

  return activeLoraNames;
}

/**
 * Check if a mode value represents an active node.
 * Active modes: 0 (Always), 3 (On Trigger)
 * Inactive modes: 2 (Never), 4 (Bypass)
 */
export function isNodeActive(mode: number | undefined): boolean {
  return mode === undefined || mode === 0 || mode === 3;
}

/**
 * Setup a mode change handler for a node.
 *
 * Intercepts the mode property setter to trigger a callback when the mode changes.
 * This is needed because ComfyUI sets the mode property directly without using a setter.
 *
 * @param node - The node to set up the handler for
 * @param onModeChange - Callback function called when mode changes (receives newMode and oldMode)
 */
export function setupModeChangeHandler(
  node: any,
  onModeChange: (newMode: number, oldMode: number) => void
): void {
  let _mode = node.mode;

  Object.defineProperty(node, 'mode', {
    get() {
      return _mode;
    },
    set(value: number) {
      const oldValue = _mode;
      _mode = value;

      if (oldValue !== value) {
        onModeChange(value, oldValue);
      }
    }
  });
}

/**
 * Create a mode change callback that updates downstream loaders.
 *
 * This is the standard callback used by all LoRA provider nodes.
 * When mode changes:
 * 1. Determine if the node is active (mode 0 or 3)
 * 2. Get active LoRAs (empty set if inactive)
 * 3. Call the optional node-specific callback (e.g., updateConnectedTriggerWords for Stacker)
 * 4. Update downstream loaders
 *
 * @param node - The node instance
 * @param updateDownstreamLoaders - Function to update downstream loaders (from utils.js)
 * @param nodeSpecificCallback - Optional callback for node-specific behavior
 */
export function createModeChangeCallback(
  node: any,
  updateDownstreamLoaders: (node: any) => void,
  nodeSpecificCallback?: (activeLoraNames: Set<string>) => void
): (newMode: number, oldMode: number) => void {
  return (newMode: number, _oldMode: number) => {
    const isNodeCurrentlyActive = isNodeActive(newMode);
    const activeLoraNames = isNodeCurrentlyActive
      ? getActiveLorasFromNodeByType(node)
      : new Set<string>();

    // Node-specific handling (e.g., Lora Stacker's direct trigger toggle updates)
    if (nodeSpecificCallback) {
      nodeSpecificCallback(activeLoraNames);
    }

    // Always update downstream loaders
    updateDownstreamLoaders(node);
  };
}

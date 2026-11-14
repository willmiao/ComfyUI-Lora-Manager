/**
 * Shared "already on the node" state and cue for LoRA result lists.
 *
 * The autocomplete dropdown and the canvas quick picker both mark LoRAs that
 * are already present on the target node, so the lookup (including the legacy
 * bare-name fallback) and the badge markup live here to keep the two surfaces
 * identical.
 */

import { normalizeLoraNameKey } from "./loras_widget_utils.js";

/**
 * Map normalized LoRA names to their enabled state.
 *
 * @param {Array<{name?: string, active?: boolean}>|null|undefined} loras
 * @returns {Map<string, boolean>} normalized name -> enabled
 */
export function buildAddedLoraStateMap(loras) {
  const states = new Map();
  if (!Array.isArray(loras)) return states;
  for (const lora of loras) {
    const key = normalizeLoraNameKey(lora?.name);
    if (key) states.set(key, lora?.active !== false);
  }
  return states;
}

/**
 * Whether a result path is already on the node.
 *
 * Returns "active" when the node has it enabled, "inactive" when it is listed
 * but turned off, and null when it is not on the node. Legacy workflows store
 * entries without their folder, so the bare file name is accepted as a
 * fallback.
 *
 * @param {Map<string, boolean>|null|undefined} states
 * @param {string} relativePath
 * @returns {"active"|"inactive"|null}
 */
export function resolveAddedLoraState(states, relativePath) {
  if (!states || states.size === 0) return null;
  const key = normalizeLoraNameKey(relativePath);
  if (!key) return null;
  const stateFor = (name) => {
    if (!states.has(name)) return null;
    return states.get(name) ? "active" : "inactive";
  };
  const direct = stateFor(key);
  if (direct) return direct;
  const bareName = key.slice(key.lastIndexOf("/") + 1);
  return bareName !== key ? stateFor(bareName) : null;
}

/**
 * Badge markup shared by the autocomplete dropdown and the quick picker.
 *
 * @param {"active"|"inactive"} state
 * @returns {HTMLElement}
 */
export function createAddedLoraCue(state) {
  const isActive = state === "active";
  const cue = document.createElement("span");
  cue.className = `lm-lora-added ${isActive ? "is-active" : "is-inactive"}`;
  cue.title = isActive ? "Added to this node" : "Added but turned off — select to enable";
  cue.setAttribute("aria-label", cue.title);

  const icon = document.createElement("span");
  icon.className = "lm-lora-added-icon";
  icon.textContent = isActive ? "✓" : "○";
  icon.setAttribute("aria-hidden", "true");
  cue.appendChild(icon);

  const label = document.createElement("span");
  label.textContent = isActive ? "Added" : "Off";
  cue.appendChild(label);

  return cue;
}

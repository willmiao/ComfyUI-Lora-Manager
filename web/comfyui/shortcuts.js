import { app } from "../../scripts/app.js";

// Quick pickers are registered as ComfyUI commands with a default keybinding,
// so users can remap them in Settings > Keybindings. User overrides are stored
// by command id: keep these ids stable once released, or saved customizations
// are orphaned.
export const COMMAND_IDS = {
  quickLoraPicker: "LoraManager.ToggleQuickPanel",
};

// Default combos live beside the command ids so the registered default and the
// displayed fallback (used when the effective binding cannot be read) cannot
// drift apart. Each picker added later gets its own entry here.
export const DEFAULT_KEYBINDINGS = {
  [COMMAND_IDS.quickLoraPicker]: { key: "l", alt: true },
};

function formatKeyCombo(combo) {
  const sequences = combo?.getKeySequences?.();
  if (Array.isArray(sequences) && sequences.length > 0) {
    return sequences.join("+");
  }
  if (!combo?.key) return "";

  const parts = [];
  if (combo.ctrl) parts.push("Ctrl");
  if (combo.alt) parts.push("Alt");
  if (combo.shift) parts.push("Shift");
  if (combo.meta) parts.push("Meta");
  const key = String(combo.key);
  parts.push(key.length === 1 ? key.toUpperCase() : key);
  return parts.join("+");
}

// Returns the effective combo for a command, `null` when the command exists but
// has no binding left, and `undefined` when the binding cannot be read (older
// frontend without the command keybinding getter, or the command is not
// registered yet). Querying lazily keeps remaps applied later in the session
// visible without a page reload.
function readKeyCombo(commandId) {
  try {
    const commands = app?.extensionManager?.command?.commands;
    if (!Array.isArray(commands)) return undefined;
    const command = commands.find((entry) => entry?.id === commandId);
    if (!command) return undefined;
    // `undefined` means this frontend has no command keybinding getter, which is
    // different from a command whose binding was removed (getter returns null).
    if (command.keybinding === undefined) return undefined;
    return command.keybinding?.combo ?? null;
  } catch {
    return undefined;
  }
}

export function getCommandShortcutLabel(commandId) {
  const combo = readKeyCombo(commandId);
  if (combo === undefined) {
    return formatKeyCombo(DEFAULT_KEYBINDINGS[commandId]);
  }
  if (!combo) return "";
  return formatKeyCombo(combo);
}

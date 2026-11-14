import { ensureLmStyles } from "./lm_styles_loader.js";
import { openLoraManagerHome } from "./lora_canvas_api.js";
import { toggleLoraQuickPanel } from "./lora_quick_panel.js";
import { COMMAND_IDS, getCommandShortcutLabel } from "./shortcuts.js";

let activeMenu = null;

function closeQuickActionsMenu() {
  if (!activeMenu) return;
  const { element, anchor, onPointerDown, onKeyDown, onResize } = activeMenu;
  document.removeEventListener("pointerdown", onPointerDown, true);
  document.removeEventListener("keydown", onKeyDown, true);
  window.removeEventListener("resize", onResize);
  element.remove();
  anchor?.setAttribute("aria-expanded", "false");
  activeMenu = null;
}

function createMenuItem(label, shortcut, action) {
  const button = document.createElement("button");
  button.type = "button";
  button.className = "lm-quick-actions-menu__item";
  button.setAttribute("role", "menuitem");

  const text = document.createElement("span");
  text.textContent = label;
  button.appendChild(text);
  if (shortcut) {
    const keybinding = document.createElement("kbd");
    keybinding.className = "lm-quick-actions-menu__shortcut";
    keybinding.textContent = shortcut;
    button.appendChild(keybinding);
  }
  button.addEventListener("click", () => {
    closeQuickActionsMenu();
    action();
  });
  return button;
}

export function toggleQuickActionsMenu(anchor) {
  if (activeMenu) {
    closeQuickActionsMenu();
    return;
  }
  if (!anchor) return;

  ensureLmStyles();
  const element = document.createElement("div");
  element.className = "lm-popover lm-quick-actions-menu";
  element.setAttribute("role", "menu");
  element.setAttribute("aria-label", "LoRA Manager quick actions");
  // The badge follows the user's keybinding override, and is omitted when the
  // shortcut has been unbound. Rebuilt on every open, so remaps apply at once.
  element.appendChild(createMenuItem(
    "Quick LoRA Picker",
    getCommandShortcutLabel(COMMAND_IDS.quickLoraPicker),
    toggleLoraQuickPanel,
  ));
  const divider = document.createElement("div");
  divider.className = "lm-quick-actions-menu__divider";
  element.appendChild(divider);
  element.appendChild(createMenuItem("Open LoRA Manager", "", () => openLoraManagerHome()));
  document.body.appendChild(element);

  const anchorRect = anchor.getBoundingClientRect();
  const menuRect = element.getBoundingClientRect();
  const margin = 8;
  const gap = 6;
  const left = Math.max(margin, Math.min(anchorRect.right - menuRect.width, window.innerWidth - menuRect.width - margin));
  const below = anchorRect.bottom + gap;
  const top = below + menuRect.height <= window.innerHeight - margin
    ? below
    : Math.max(margin, anchorRect.top - menuRect.height - gap);
  element.style.left = `${Math.round(left)}px`;
  element.style.top = `${Math.round(top)}px`;

  const onPointerDown = (event) => {
    if (!element.contains(event.target) && !anchor.contains(event.target)) closeQuickActionsMenu();
  };
  const onKeyDown = (event) => {
    if (event.key !== "Escape") return;
    event.preventDefault();
    event.stopPropagation();
    closeQuickActionsMenu();
    anchor.focus();
  };
  const onResize = () => closeQuickActionsMenu();
  document.addEventListener("pointerdown", onPointerDown, true);
  document.addEventListener("keydown", onKeyDown, true);
  window.addEventListener("resize", onResize);
  anchor.setAttribute("aria-expanded", "true");
  activeMenu = { element, anchor, onPointerDown, onKeyDown, onResize };
  element.querySelector("button")?.focus();
}

import { ensureLmStyles } from "./lm_styles_loader.js";
import { openComfyUISettingsDialog } from "./comfy_settings_dialog.js";
import { openLoraManagerHome } from "./lora_canvas_api.js";
import { toggleLoraQuickPanel, toggleRecipeQuickPanel } from "./lora_quick_panel.js";
import { toggleWildcardQuickPanel } from "./wildcard_quick_panel.js";
import { COMMAND_IDS, getCommandShortcutLabel } from "./shortcuts.js";

const NATIVE_MENU_CONTAINER_CLASS =
  "lm-popover lm-quick-actions-menu z-3000 min-w-52 overflow-y-auto rounded-lg border border-solid border-border bg-background p-1 text-foreground shadow-lg outline-none";
const NATIVE_MENU_ITEM_CLASS =
  "lm-quick-actions-menu__item group flex min-h-8 w-full cursor-pointer appearance-none items-center justify-between gap-4 rounded-sm border-0 bg-transparent px-2 py-1 text-left font-inter text-xs text-foreground outline-none transition-colors hover:bg-accent focus-visible:bg-accent disabled:pointer-events-none disabled:opacity-50";
const NATIVE_MENU_DIVIDER_CLASS = "lm-quick-actions-menu__divider my-1 h-px bg-border/50";
const NATIVE_MENU_SHORTCUT_CLASS =
  "lm-quick-actions-menu__shortcut inline-flex items-center justify-center rounded bg-secondary px-1.5 py-0.5 text-[11px] leading-none text-muted-foreground";

let activeMenu = null;

function closeQuickActionsMenu() {
  if (!activeMenu) return;
  const { element, anchor, onPointerDown, onKeyDown, onResize } = activeMenu;
  document.removeEventListener("pointerdown", onPointerDown, true);
  document.removeEventListener("keydown", onKeyDown, true);
  window.removeEventListener("resize", onResize);
  element.remove();
  anchor?.setAttribute("aria-expanded", "false");
  anchor?.setAttribute("data-state", "closed");
  activeMenu = null;
}

function createMenuItem(label, shortcut, action, iconClass = "") {
  const button = document.createElement("button");
  button.type = "button";
  button.className = NATIVE_MENU_ITEM_CLASS;
  button.setAttribute("role", "menuitem");

  const left = document.createElement("span");
  left.className = "flex min-w-0 flex-1 items-center gap-2";

  if (iconClass) {
    const icon = document.createElement("i");
    icon.className = `${iconClass} size-3.5 shrink-0 text-muted-foreground`;
    icon.setAttribute("aria-hidden", "true");
    left.appendChild(icon);
  }

  const text = document.createElement("span");
  text.className = "min-w-0 truncate";
  text.textContent = label;
  left.appendChild(text);
  button.appendChild(left);

  if (shortcut) {
    const keybinding = document.createElement("kbd");
    keybinding.className = NATIVE_MENU_SHORTCUT_CLASS;
    keybinding.textContent = shortcut;
    button.appendChild(keybinding);
  }
  button.addEventListener("click", () => {
    closeQuickActionsMenu();
    action();
  });
  return button;
}

function createDivider() {
  const divider = document.createElement("div");
  divider.setAttribute("role", "separator");
  divider.className = NATIVE_MENU_DIVIDER_CLASS;
  return divider;
}

export function toggleQuickActionsMenu(anchor) {
  if (activeMenu) {
    closeQuickActionsMenu();
    return;
  }
  if (!anchor) return;

  ensureLmStyles();
  const element = document.createElement("div");
  element.className = NATIVE_MENU_CONTAINER_CLASS;
  element.setAttribute("role", "menu");
  element.setAttribute("data-state", "open");
  element.setAttribute("aria-label", "LoRA Manager quick actions");
  // The badge follows the user's keybinding override, and is omitted when the
  // shortcut has been unbound. Rebuilt on every open, so remaps apply at once.
  element.appendChild(createMenuItem(
    "Quick LoRA Picker",
    getCommandShortcutLabel(COMMAND_IDS.quickLoraPicker),
    toggleLoraQuickPanel,
    "icon-[lucide--layers]",
  ));
  element.appendChild(createMenuItem(
    "Quick Recipe Picker",
    getCommandShortcutLabel(COMMAND_IDS.quickRecipePicker),
    toggleRecipeQuickPanel,
    "icon-[lucide--book-open]",
  ));
  element.appendChild(createMenuItem(
    "Global Wildcards",
    getCommandShortcutLabel(COMMAND_IDS.quickWildcardPicker),
    toggleWildcardQuickPanel,
    "icon-[lucide--sparkles]",
  ));
  element.appendChild(createDivider());
  element.appendChild(createMenuItem(
    "Open LoRA Manager",
    "",
    () => openLoraManagerHome(),
    "icon-[lucide--external-link]",
  ));
  // These settings are ComfyUI's: the LoRA Manager ones that live in ComfyUI's
  // settings dialog (widget accent, autocomplete, node labels, ...), not the
  // manager page's own settings. The chevron is attached to the LoRA Manager
  // button, so the short label is unambiguous here.
  element.appendChild(createDivider());
  element.appendChild(createMenuItem(
    "Settings",
    "",
    () => void openComfyUISettingsDialog(),
    "icon-[lucide--settings]",
  ));
  document.body.appendChild(element);

  const anchorRect = anchor.getBoundingClientRect();
  const menuRect = element.getBoundingClientRect();
  const margin = 8;
  const gap = 8;
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
  anchor.setAttribute("data-state", "open");
  activeMenu = { element, anchor, onPointerDown, onKeyDown, onResize };
  element.querySelector("button")?.focus();
}

import { COMMAND_IDS, getCommandShortcutLabel } from "./shortcuts.js";

// Function to create toggle element
export function createToggle(active, onChange, {
  mixed = false,
  disabled = false,
  label = "Toggle LoRA",
  focusable = false,
} = {}) {
  const toggle = document.createElement("div");
  toggle.className = "lm-lora-toggle";
  toggle.setAttribute("role", "checkbox");
  toggle.setAttribute("aria-label", label);
  toggle.setAttribute("aria-disabled", String(disabled));
  toggle.tabIndex = focusable && !disabled ? 0 : -1;

  updateToggleStyle(toggle, active, mixed);
  toggle.classList.toggle("lm-lora-toggle--disabled", disabled);

  const activate = (e) => {
    e.stopPropagation();
    if (!disabled) {
      onChange(!active);
    }
  };

  toggle.addEventListener("click", activate);
  if (focusable) {
    toggle.addEventListener("keydown", (e) => {
      if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        activate(e);
      }
    });
  }

  return toggle;
}

// Helper function to update toggle style
export function updateToggleStyle(toggleEl, active, mixed = false) {
  toggleEl.classList.toggle("lm-lora-toggle--active", active);
  toggleEl.classList.toggle("lm-lora-toggle--mixed", mixed);
  toggleEl.setAttribute("aria-checked", mixed ? "mixed" : String(active));
}

export function createStrengthDragHandle() {
  const handle = document.createElement("button");
  handle.className = "lm-lora-strength-drag-handle";
  handle.type = "button";
  handle.innerHTML = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m18 8 4 4-4 4"/><path d="m6 8-4 4 4 4"/><path d="M2 12h20"/></svg>`;
  handle.title = "Drag to scale all strengths";
  handle.setAttribute("aria-label", "Drag to scale all strengths");
  return handle;
}

export function createAddLoraButton(onClick) {
  const button = document.createElement("button");
  button.className = "lm-lora-add-button";
  button.type = "button";
  button.innerHTML = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 5v14M5 12h14"/></svg>`;
  // Resolve the hint lazily: the binding can be remapped while the graph stays
  // open, so refresh it when the pointer reaches the button.
  const updateShortcutHint = () => {
    const shortcut = getCommandShortcutLabel(COMMAND_IDS.quickLoraPicker);
    const suffix = shortcut ? ` (${shortcut})` : "";
    button.title = `Add LoRA · Quick Picker${suffix}`;
    button.setAttribute("aria-label", `Add LoRA with Quick Picker${suffix}`);
  };
  updateShortcutHint();
  button.addEventListener("pointerenter", updateShortcutHint);
  button.addEventListener("click", (e) => {
    e.preventDefault();
    e.stopPropagation();
    onClick();
  });
  return button;
}

// Create arrow button for strength adjustment
export function createArrowButton(direction, onClick) {
  const button = document.createElement("div");
  button.className = `lm-lora-arrow lm-lora-arrow-${direction}`;
  button.innerHTML = direction === "left"
    ? `<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m15 18-6-6 6-6"/></svg>`
    : `<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m9 18 6-6-6-6"/></svg>`;

  button.addEventListener("click", (e) => {
    e.stopPropagation();
    onClick();
  });

  return button;
}

// Function to create drag handle
export function createDragHandle() {
  const handle = document.createElement("div");
  handle.className = "lm-lora-drag-handle";
  handle.innerHTML = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="9" cy="12" r="1"/><circle cx="9" cy="5" r="1"/><circle cx="9" cy="19" r="1"/><circle cx="15" cy="12" r="1"/><circle cx="15" cy="5" r="1"/><circle cx="15" cy="19" r="1"/></svg>`;
  handle.title = "Drag to reorder LoRA";
  return handle;
}

// Function to create drop indicator
export function createDropIndicator() {
  const indicator = document.createElement("div");
  indicator.className = "lm-lora-drop-indicator";
  return indicator;
}

// Function to update entry selection state
export function updateEntrySelection(entryEl, isSelected) {
  entryEl.dataset.selected = isSelected ? "true" : "false";
  if (!isSelected) {
    entryEl.style.removeProperty("background-color");
    entryEl.style.removeProperty("border");
    entryEl.style.removeProperty("box-shadow");
  }
}

// Function to create menu item
export function createMenuItem(text, icon, onClick) {
  const menuItem = document.createElement("div");
  menuItem.className = "lm-lora-menu-item";

  const iconEl = document.createElement("div");
  iconEl.className = "lm-lora-menu-item-icon";
  iconEl.innerHTML = icon;

  const textEl = document.createElement("span");
  textEl.textContent = text;

  menuItem.appendChild(iconEl);
  menuItem.appendChild(textEl);

  if (onClick) {
    menuItem.addEventListener("click", onClick);
  }

  return menuItem;
}

// Function to create expand/collapse button
export function createExpandButton(isExpanded, onClick) {
  const button = document.createElement("button");
  button.className = "lm-lora-expand-button";
  button.type = "button";
  button.tabIndex = -1;

  // Set icon based on expanded state
  updateExpandButtonState(button, isExpanded);

  button.addEventListener("click", (e) => {
    e.preventDefault();
    e.stopPropagation();
    onClick(!isExpanded);
  });

  return button;
}

// Helper function to update expand button state
export function updateExpandButtonState(button, isExpanded) {
  if (isExpanded) {
    button.innerHTML = `<svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m6 9 6 6 6-6"/></svg>`;
    button.title = "Collapse clip controls";
  } else {
    button.innerHTML = `<svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m9 18 6-6-6-6"/></svg>`;
    button.title = "Expand clip controls";
  }
}

// Function to create lock button
export function createLockButton(isLocked, onChange) {
  const button = document.createElement("button");
  button.className = "lm-lora-lock-button";
  button.type = "button";
  button.tabIndex = -1;

  // Set icon based on locked state
  updateLockButtonState(button, isLocked);

  button.addEventListener("click", (e) => {
    e.preventDefault();
    e.stopPropagation();
    onChange(!isLocked);
  });

  return button;
}

// Helper function to update lock button state
export function updateLockButtonState(button, isLocked) {
  if (isLocked) {
    button.innerHTML = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect width="18" height="11" x="3" y="11" rx="2" ry="2"></rect><path d="M7 11V7a5 5 0 0 1 10 0v4"></path></svg>`;
    button.title = "Unlock this LoRA (allow re-rolling)";
    button.classList.add("lm-lora-lock-button--locked");
  } else {
    button.innerHTML = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect width="18" height="11" x="3" y="11" rx="2" ry="2"></rect><path d="M7 11V7a5 5 0 0 1 9.9-1"></path></svg>`;
    button.title = "Lock this LoRA (prevent re-rolling)";
    button.classList.remove("lm-lora-lock-button--locked");
  }
}

// Function to create toggle element
export function createToggle(active, onChange) {
  const toggle = document.createElement("div");
  toggle.className = "lm-lora-toggle";

  updateToggleStyle(toggle, active);

  toggle.addEventListener("click", (e) => {
    e.stopPropagation();
    onChange(!active);
  });

  return toggle;
}

// Helper function to update toggle style
export function updateToggleStyle(toggleEl, active) {
  toggleEl.classList.toggle("lm-lora-toggle--active", active);
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

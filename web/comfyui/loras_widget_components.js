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
  button.textContent = direction === "left" ? "◀" : "▶";

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
  handle.innerHTML = "≡";
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
    button.innerHTML = "▼"; // Down arrow for expanded
    button.title = "Collapse clip controls";
  } else {
    button.innerHTML = "▶"; // Right arrow for collapsed
    button.title = "Expand clip controls";
  }
}

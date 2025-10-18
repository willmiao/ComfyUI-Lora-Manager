// Function to create toggle element
export function createToggle(active, onChange) {
  const toggle = document.createElement("div");
  toggle.className = "comfy-lora-toggle";
  
  updateToggleStyle(toggle, active);
  
  toggle.addEventListener("click", (e) => {
    e.stopPropagation();
    onChange(!active);
  });
  
  return toggle;
}

// Helper function to update toggle style
export function updateToggleStyle(toggleEl, active) {
  Object.assign(toggleEl.style, {
    width: "18px",
    height: "18px",
    borderRadius: "4px",
    cursor: "pointer",
    transition: "all 0.2s ease",
    backgroundColor: active ? "rgba(66, 153, 225, 0.9)" : "rgba(45, 55, 72, 0.7)",
    border: `1px solid ${active ? "rgba(66, 153, 225, 0.9)" : "rgba(226, 232, 240, 0.2)"}`,
  });

  // Add hover effect
  toggleEl.onmouseenter = () => {
    toggleEl.style.transform = "scale(1.05)";
    toggleEl.style.boxShadow = "0 2px 4px rgba(0,0,0,0.15)";
  };

  toggleEl.onmouseleave = () => {
    toggleEl.style.transform = "scale(1)";
    toggleEl.style.boxShadow = "none";
  };
}

// Create arrow button for strength adjustment
export function createArrowButton(direction, onClick) {
  const button = document.createElement("div");
  button.className = `comfy-lora-arrow comfy-lora-arrow-${direction}`;
  
  Object.assign(button.style, {
    width: "16px",
    height: "16px",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    cursor: "pointer",
    userSelect: "none",
    fontSize: "12px",
    color: "rgba(226, 232, 240, 0.8)",
    transition: "all 0.2s ease",
  });
  
  button.textContent = direction === "left" ? "◀" : "▶";
  
  button.addEventListener("click", (e) => {
    e.stopPropagation();
    onClick();
  });
  
  // Add hover effect
  button.onmouseenter = () => {
    button.style.color = "white";
    button.style.transform = "scale(1.2)";
  };
  
  button.onmouseleave = () => {
    button.style.color = "rgba(226, 232, 240, 0.8)";
    button.style.transform = "scale(1)";
  };
  
  return button;
}

// Function to create drag handle
export function createDragHandle() {
  const handle = document.createElement("div");
  handle.className = "comfy-lora-drag-handle";
  handle.innerHTML = "≡";
  handle.title = "Drag to reorder LoRA";
  
  Object.assign(handle.style, {
    width: "16px",
    height: "16px",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    cursor: "grab",
    userSelect: "none",
    fontSize: "14px",
    color: "rgba(226, 232, 240, 0.6)",
    transition: "all 0.2s ease",
    marginRight: "8px",
    flexShrink: "0"
  });
  
  // Add hover effect
  handle.onmouseenter = () => {
    handle.style.color = "rgba(226, 232, 240, 0.9)";
    handle.style.transform = "scale(1.1)";
  };
  
  handle.onmouseleave = () => {
    handle.style.color = "rgba(226, 232, 240, 0.6)";
    handle.style.transform = "scale(1)";
  };
  
  // Change cursor when dragging
  handle.onmousedown = () => {
    handle.style.cursor = "grabbing";
  };

  handle.onmouseup = () => {
    handle.style.cursor = "grab";
  };
  
  return handle;
}

// Function to create drop indicator
export function createDropIndicator() {
  const indicator = document.createElement("div");
  indicator.className = "comfy-lora-drop-indicator";
  
  Object.assign(indicator.style, {
    position: "absolute",
    left: "0",
    right: "0",
    height: "3px",
    backgroundColor: "rgba(66, 153, 225, 0.9)",
    borderRadius: "2px",
    opacity: "0",
    transition: "opacity 0.2s ease",
    boxShadow: "0 0 6px rgba(66, 153, 225, 0.8)",
    zIndex: "10",
    pointerEvents: "none"
  });
  
  return indicator;
}

// Function to update entry selection state
export function updateEntrySelection(entryEl, isSelected) {
  // Remove any conflicting styles first
  entryEl.style.removeProperty('border');
  entryEl.style.removeProperty('box-shadow');

  const baseColor = entryEl.dataset.active === 'true' ?
    "rgba(45, 55, 72, 0.7)" : "rgba(35, 40, 50, 0.5)";
  const selectedColor = entryEl.dataset.active === 'true' ?
    "rgba(66, 153, 225, 0.3)" : "rgba(66, 153, 225, 0.2)";

  // Update data attribute to track selection state
  entryEl.dataset.selected = isSelected ? 'true' : 'false';
  
  if (isSelected) {
    entryEl.style.setProperty('backgroundColor', selectedColor, 'important');
    entryEl.style.setProperty('border', "1px solid rgba(66, 153, 225, 0.6)", 'important');
    entryEl.style.setProperty('box-shadow', "0 0 0 1px rgba(66, 153, 225, 0.3)", 'important');
  } else {
    entryEl.style.backgroundColor = baseColor;
    entryEl.style.border = "1px solid transparent";
    entryEl.style.boxShadow = "none";
  }
}

// Function to create menu item
export function createMenuItem(text, icon, onClick) {
  const menuItem = document.createElement('div');
  Object.assign(menuItem.style, {
    padding: '6px 20px',
    cursor: 'pointer',
    color: 'rgba(226, 232, 240, 0.9)',
    fontSize: '13px',
    userSelect: 'none',
    display: 'flex',
    alignItems: 'center',
    gap: '8px',
  });

  // Create icon element
  const iconEl = document.createElement('div');
  iconEl.innerHTML = icon;
  Object.assign(iconEl.style, {
    width: '14px',
    height: '14px',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
  });

  // Create text element
  const textEl = document.createElement('span');
  textEl.textContent = text;

  menuItem.appendChild(iconEl);
  menuItem.appendChild(textEl);

  menuItem.addEventListener('mouseenter', () => {
    menuItem.style.backgroundColor = 'rgba(66, 153, 225, 0.2)';
  });

  menuItem.addEventListener('mouseleave', () => {
    menuItem.style.backgroundColor = 'transparent';
  });

  if (onClick) {
    menuItem.addEventListener('click', onClick);
  }

  return menuItem;
}

// Function to create expand/collapse button
export function createExpandButton(isExpanded, onClick) {
  const button = document.createElement("button");
  button.className = "comfy-lora-expand-button";
  button.type = "button";
  button.tabIndex = -1;
  
  Object.assign(button.style, {
    width: "20px",
    height: "20px",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    cursor: "pointer",
    userSelect: "none",
    fontSize: "10px",
    color: "rgba(226, 232, 240, 0.7)",
    backgroundColor: "rgba(45, 55, 72, 0.3)",
    border: "1px solid rgba(226, 232, 240, 0.2)",
    borderRadius: "3px",
    transition: "all 0.2s ease",
    marginLeft: "6px",
    marginRight: "4px",
    flexShrink: "0",
    outline: "none"
  });
  
  // Set icon based on expanded state
  updateExpandButtonState(button, isExpanded);
  
  button.addEventListener("click", (e) => {
    e.preventDefault();
    e.stopPropagation();
    onClick(!isExpanded);
  });
  
  // Add hover effects
  button.addEventListener("mouseenter", () => {
    button.style.backgroundColor = "rgba(66, 153, 225, 0.2)";
    button.style.borderColor = "rgba(66, 153, 225, 0.4)";
    button.style.color = "rgba(226, 232, 240, 0.9)";
    button.style.transform = "scale(1.05)";
  });
  
  button.addEventListener("mouseleave", () => {
    button.style.backgroundColor = "rgba(45, 55, 72, 0.3)";
    button.style.borderColor = "rgba(226, 232, 240, 0.2)";
    button.style.color = "rgba(226, 232, 240, 0.7)";
    button.style.transform = "scale(1)";
  });
  
  // Add active (pressed) state
  button.addEventListener("mousedown", () => {
    button.style.transform = "scale(0.95)";
    button.style.backgroundColor = "rgba(66, 153, 225, 0.3)";
  });
  
  button.addEventListener("mouseup", () => {
    button.style.transform = "scale(1.05)"; // Return to hover state
  });
  
  // Add focus state for keyboard accessibility
  button.addEventListener("focus", () => {
    button.style.boxShadow = "0 0 0 2px rgba(66, 153, 225, 0.5)";
  });
  
  button.addEventListener("blur", () => {
    button.style.boxShadow = "none";
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

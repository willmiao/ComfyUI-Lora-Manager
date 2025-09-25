import { api } from "../../scripts/api.js";

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

// Preview tooltip class
export class PreviewTooltip {
  constructor() {
    this.element = document.createElement('div');
    Object.assign(this.element.style, {
      position: 'fixed',
      zIndex: 9999,
      background: 'rgba(0, 0, 0, 0.85)',
      borderRadius: '6px',
      boxShadow: '0 4px 12px rgba(0, 0, 0, 0.3)',
      display: 'none',
      overflow: 'hidden',
      maxWidth: '300px',
      pointerEvents: 'none', // Prevent interference with autocomplete
    });
    document.body.appendChild(this.element);
    this.hideTimeout = null;
    this.isFromAutocomplete = false;
    
    // Modified event listeners for autocomplete compatibility
    this.globalClickHandler = (e) => {
      // Don't hide if click is on autocomplete dropdown
      if (!e.target.closest('.comfy-autocomplete-dropdown')) {
        this.hide();
      }
    };
    document.addEventListener('click', this.globalClickHandler);
    
    this.globalScrollHandler = () => this.hide();
    document.addEventListener('scroll', this.globalScrollHandler, true);
  }

  async show(loraName, x, y, fromAutocomplete = false) {
    try {
      // Clear previous hide timer
      if (this.hideTimeout) {
        clearTimeout(this.hideTimeout);
        this.hideTimeout = null;
      }

      // Track if this is from autocomplete
      this.isFromAutocomplete = fromAutocomplete;

      // Don't redisplay the same lora preview
      if (this.element.style.display === 'block' && this.currentLora === loraName) {
        this.position(x, y);
        return;
      }

      this.currentLora = loraName;
      
      // Get preview URL
      const response = await api.fetchApi(`/lm/loras/preview-url?name=${encodeURIComponent(loraName)}`, {
        method: 'GET'
      });

      if (!response.ok) {
        throw new Error('Failed to fetch preview URL');
      }

      const data = await response.json();
      if (!data.success || !data.preview_url) {
        throw new Error('No preview available');
      }

      // Clear existing content
      while (this.element.firstChild) {
        this.element.removeChild(this.element.firstChild);
      }

      // Create media container with relative positioning
      const mediaContainer = document.createElement('div');
      Object.assign(mediaContainer.style, {
        position: 'relative',
        maxWidth: '300px',
        maxHeight: '300px',
      });

      const isVideo = data.preview_url.endsWith('.mp4');
      const mediaElement = isVideo ? document.createElement('video') : document.createElement('img');

      Object.assign(mediaElement.style, {
        maxWidth: '300px',
        maxHeight: '300px',
        objectFit: 'contain',
        display: 'block',
      });

      if (isVideo) {
        mediaElement.autoplay = true;
        mediaElement.loop = true;
        mediaElement.muted = true;
        mediaElement.controls = false;
      }

      // Create name label with absolute positioning
      const nameLabel = document.createElement('div');
      nameLabel.textContent = loraName;
      Object.assign(nameLabel.style, {
        position: 'absolute',
        bottom: '0',
        left: '0',
        right: '0',
        padding: '8px',
        color: 'white',
        fontSize: '13px',
        fontFamily: "'Inter', 'Segoe UI', system-ui, -apple-system, sans-serif",
        background: 'linear-gradient(transparent, rgba(0, 0, 0, 0.8))',
        whiteSpace: 'nowrap',
        overflow: 'hidden',
        textOverflow: 'ellipsis',
        textAlign: 'center',
        backdropFilter: 'blur(4px)',
        WebkitBackdropFilter: 'blur(4px)',
      });

      mediaContainer.appendChild(mediaElement);
      mediaContainer.appendChild(nameLabel);
      this.element.appendChild(mediaContainer);
      
      // Show element with opacity 0 first to get dimensions
      this.element.style.opacity = '0';
      this.element.style.display = 'block';
      
      // Wait for media to load before positioning
      const waitForLoad = () => {
        return new Promise((resolve) => {
          if (isVideo) {
            if (mediaElement.readyState >= 2) { // HAVE_CURRENT_DATA
              resolve();
            } else {
              mediaElement.addEventListener('loadeddata', resolve, { once: true });
              mediaElement.addEventListener('error', resolve, { once: true });
            }
          } else {
            if (mediaElement.complete) {
              resolve();
            } else {
              mediaElement.addEventListener('load', resolve, { once: true });
              mediaElement.addEventListener('error', resolve, { once: true });
            }
          }
          
          // Set a timeout to prevent hanging
          setTimeout(resolve, 1000);
        });
      };

      // Set source after setting up load listeners
      mediaElement.src = data.preview_url;
      
      // Wait for content to load, then position and show
      await waitForLoad();
      
      // Small delay to ensure layout is complete
      requestAnimationFrame(() => {
        this.position(x, y);
        this.element.style.transition = 'opacity 0.15s ease';
        this.element.style.opacity = '1';
      });
    } catch (error) {
      console.warn('Failed to load preview:', error);
    }
  }

  position(x, y) {
    // Ensure preview box doesn't exceed viewport boundaries
    const rect = this.element.getBoundingClientRect();
    const viewportWidth = window.innerWidth;
    const viewportHeight = window.innerHeight;

    let left = x + 10; // Default 10px offset to the right of mouse
    let top = y + 10;  // Default 10px offset below mouse

    // Check right boundary
    if (left + rect.width > viewportWidth) {
      left = x - rect.width - 10;
    }

    // Check bottom boundary
    if (top + rect.height > viewportHeight) {
      top = y - rect.height - 10;
    }

    // Ensure minimum distance from edges
    left = Math.max(10, Math.min(left, viewportWidth - rect.width - 10));
    top = Math.max(10, Math.min(top, viewportHeight - rect.height - 10));

    Object.assign(this.element.style, {
      left: `${left}px`,
      top: `${top}px`
    });
  }

  hide() {
    // Use fade-out effect
    if (this.element.style.display === 'block') {
      this.element.style.opacity = '0';
      this.hideTimeout = setTimeout(() => {
        this.element.style.display = 'none';
        this.currentLora = null;
        this.isFromAutocomplete = false;
        // Stop video playback
        const video = this.element.querySelector('video');
        if (video) {
          video.pause();
        }
        this.hideTimeout = null;
      }, 150);
    }
  }

  cleanup() {
    if (this.hideTimeout) {
      clearTimeout(this.hideTimeout);
    }
    // Remove event listeners properly
    document.removeEventListener('click', this.globalClickHandler);
    document.removeEventListener('scroll', this.globalScrollHandler, true);
    this.element.remove();
  }
}

// Function to create expand/collapse button
export function createExpandButton(isExpanded, onClick) {
  const button = document.createElement("button");
  button.className = "comfy-lora-expand-button";
  button.type = "button";
  
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

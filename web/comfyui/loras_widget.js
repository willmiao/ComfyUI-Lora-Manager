import { createToggle, createArrowButton, createDragHandle, updateEntrySelection, createExpandButton, updateExpandButtonState } from "./loras_widget_components.js";
import { 
  parseLoraValue, 
  formatLoraValue, 
  updateWidgetHeight, 
  shouldShowClipEntry, 
  syncClipStrengthIfCollapsed,
  LORA_ENTRY_HEIGHT, 
  HEADER_HEIGHT, 
  CONTAINER_PADDING, 
  EMPTY_CONTAINER_HEIGHT 
} from "./loras_widget_utils.js";
import { initDrag, createContextMenu, initHeaderDrag, initReorderDrag, handleKeyboardNavigation } from "./loras_widget_events.js";
import { forwardMiddleMouseToCanvas } from "./utils.js";
import { PreviewTooltip } from "./preview_tooltip.js";

export function addLorasWidget(node, name, opts, callback) {
  // Create container for loras
  const container = document.createElement("div");
  container.className = "comfy-loras-container";

  forwardMiddleMouseToCanvas(container);

  // Set initial height using CSS variables approach
  const defaultHeight = 200;
  
  Object.assign(container.style, {
    display: "flex",
    flexDirection: "column",
    gap: "5px",
    padding: "6px",
    backgroundColor: "rgba(40, 44, 52, 0.6)",
    borderRadius: "6px",
    width: "100%",
    boxSizing: "border-box",
    overflow: "auto"
  });

  // Initialize default value
  const defaultValue = opts?.defaultVal || [];

  // Create preview tooltip instance
  const previewTooltip = new PreviewTooltip({ modelType: "loras" });
  
  // Selection state - only one LoRA can be selected at a time
  let selectedLora = null;
  let pendingFocusTarget = null;
  
  // Function to select a LoRA
  const selectLora = (loraName) => {
    selectedLora = loraName;
    // Update visual feedback for all entries
    container.querySelectorAll('.comfy-lora-entry').forEach(entry => {
      const entryLoraName = entry.dataset.loraName;
      updateEntrySelection(entry, entryLoraName === selectedLora);
    });
  };
  
  // Add keyboard event listener to container
  container.addEventListener('keydown', (e) => {
    if (handleKeyboardNavigation(e, selectedLora, widget, renderLoras, selectLora)) {
      e.stopPropagation();
    }
  });
  
  // Make container focusable for keyboard events
  container.tabIndex = 0;
  container.style.outline = 'none';
  
  // Function to render loras from data
  const renderLoras = (value, widget) => {
    // Clear existing content
    while (container.firstChild) {
      container.removeChild(container.firstChild);
    }

    // Parse the loras data
    const lorasData = parseLoraValue(value);
    const focusSequence = [];

    const createFocusEntry = (loraName, type) => {
      const entry = { name: loraName, type };
      focusSequence.push(entry);
      return entry;
    };

    const findFocusEntryIndex = (entry) =>
      focusSequence.findIndex(
        (sequenceEntry) =>
          sequenceEntry?.name === entry?.name && sequenceEntry?.type === entry?.type
      );

    const getAdjacentFocusEntry = (currentEntry, direction) => {
      const currentIndex = findFocusEntryIndex(currentEntry);
      if (currentIndex === -1) {
        return null;
      }
      return focusSequence[currentIndex + direction] || null;
    };

    const queueFocusEntry = (entry) => {
      if (!entry) {
        return false;
      }
      pendingFocusTarget = { ...entry };
      return true;
    };

    const queueFocusAdjacentFrom = (currentEntry, direction) => {
      const targetEntry = getAdjacentFocusEntry(currentEntry, direction);
      return queueFocusEntry(targetEntry);
    };

    const escapeLoraName = (loraName) => {
      const css =
        (typeof window !== "undefined" && window.CSS) ||
        (typeof globalThis !== "undefined" && globalThis.CSS);
      if (css && typeof css.escape === "function") {
        return css.escape(loraName);
      }
      return loraName.replace(/"|\\/g, "\\$&");
    };

    if (lorasData.length === 0) {
      // Show message when no loras are added
      const emptyMessage = document.createElement("div");
      emptyMessage.textContent = "No LoRAs added";
      Object.assign(emptyMessage.style, {
        textAlign: "center",
        padding: "20px 0",
        color: "rgba(226, 232, 240, 0.8)",
        fontStyle: "italic",
        userSelect: "none",
        WebkitUserSelect: "none",
        MozUserSelect: "none",
        msUserSelect: "none",
        width: "100%"
      });
      container.appendChild(emptyMessage);
      
      // Set fixed height for empty state
      updateWidgetHeight(container, EMPTY_CONTAINER_HEIGHT, defaultHeight, node);
      return;
    }

    // Create header
    const header = document.createElement("div");
    header.className = "comfy-loras-header";
    Object.assign(header.style, {
      display: "flex",
      justifyContent: "space-between",
      alignItems: "center",
      padding: "4px 8px",
      borderBottom: "1px solid rgba(226, 232, 240, 0.2)",
      marginBottom: "5px",
      position: "relative" // Added for positioning the drag hint
    });

    // Add toggle all control
    const allActive = lorasData.every(lora => lora.active);
    const toggleAll = createToggle(allActive, (active) => {
      // Update all loras active state
      const lorasData = parseLoraValue(widget.value);
      lorasData.forEach(lora => lora.active = active);
      
      const newValue = formatLoraValue(lorasData);
      widget.value = newValue;
    });

    // Add label to toggle all
    const toggleLabel = document.createElement("div");
    toggleLabel.textContent = "Toggle All";
    Object.assign(toggleLabel.style, {
      color: "rgba(226, 232, 240, 0.8)",
      fontSize: "13px",
      marginLeft: "8px",
      userSelect: "none",
      WebkitUserSelect: "none",
      MozUserSelect: "none",
      msUserSelect: "none",
    });

    const toggleContainer = document.createElement("div");
    Object.assign(toggleContainer.style, {
      display: "flex",
      alignItems: "center",
    });
    toggleContainer.appendChild(toggleAll);
    toggleContainer.appendChild(toggleLabel);

    // Strength label with drag hint
    const strengthLabel = document.createElement("div");
    strengthLabel.textContent = "Strength";
    Object.assign(strengthLabel.style, {
      color: "rgba(226, 232, 240, 0.8)",
      fontSize: "13px",
      marginRight: "8px",
      userSelect: "none",
      WebkitUserSelect: "none",
      MozUserSelect: "none",
      msUserSelect: "none",
      display: "flex",
      alignItems: "center"
    });
    
    // Add drag hint icon next to strength label
    const dragHint = document.createElement("span");
    dragHint.innerHTML = "↔"; // Simple left-right arrow as drag indicator
    Object.assign(dragHint.style, {
      marginLeft: "5px",
      fontSize: "11px",
      opacity: "0.6",
      transition: "opacity 0.2s ease"
    });
    strengthLabel.appendChild(dragHint);
    
    // Add hover effect to improve discoverability
    header.addEventListener("mouseenter", () => {
      dragHint.style.opacity = "1";
    });
    
    header.addEventListener("mouseleave", () => {
      dragHint.style.opacity = "0.6";
    });

    header.appendChild(toggleContainer);
    header.appendChild(strengthLabel);
    container.appendChild(header);
    
    // Initialize the header drag functionality
    initHeaderDrag(header, widget, renderLoras);

    // Track the total visible entries for height calculation
    let totalVisibleEntries = lorasData.length;

    // Render each lora entry
    lorasData.forEach((loraData) => {
      const { name, strength, clipStrength, active } = loraData;
      
      // Determine expansion state using our helper function
      const isExpanded = shouldShowClipEntry(loraData);
      const strengthFocusEntry = createFocusEntry(name, "strength");
      
      // Create the main LoRA entry
      const loraEl = document.createElement("div");
      loraEl.className = "comfy-lora-entry";
      Object.assign(loraEl.style, {
        display: "flex",
        justifyContent: "space-between",
        alignItems: "center",
        padding: "6px",
        borderRadius: "6px",
        backgroundColor: active ? "rgba(45, 55, 72, 0.7)" : "rgba(35, 40, 50, 0.5)",
        transition: "all 0.2s ease",
        marginBottom: "4px",
      });

      // Store lora name and active state in dataset for selection
      loraEl.dataset.loraName = name;
      loraEl.dataset.active = active;

      // Add click handler for selection
      loraEl.addEventListener('click', (e) => {
        // Skip if clicking on interactive elements
        if (e.target.closest('.comfy-lora-toggle') || 
            e.target.closest('input') || 
            e.target.closest('.comfy-lora-arrow') ||
            e.target.closest('.comfy-lora-drag-handle') ||
            e.target.closest('.comfy-lora-expand-button')) {
          return;
        }
        
        e.preventDefault();
        e.stopPropagation();
        selectLora(name);
        container.focus(); // Focus container for keyboard events
      });

      // Create drag handle for reordering
      const dragHandle = createDragHandle();
      
      // Initialize reorder drag functionality
      initReorderDrag(dragHandle, name, widget, renderLoras);

      // Create toggle for this lora
      const toggle = createToggle(active, (newActive) => {
        // Update this lora's active state
        const lorasData = parseLoraValue(widget.value);
        const loraIndex = lorasData.findIndex(l => l.name === name);
        
        if (loraIndex >= 0) {
          lorasData[loraIndex].active = newActive;
          
          const newValue = formatLoraValue(lorasData);
          widget.value = newValue;
        }
      });

      // Create expand button
      const expandButton = createExpandButton(isExpanded, (shouldExpand) => {
        // Toggle the clip entry expanded state
        const lorasData = parseLoraValue(widget.value);
        const loraIndex = lorasData.findIndex(l => l.name === name);
        
        if (loraIndex >= 0) {
          // Set the expansion state
          lorasData[loraIndex].expanded = shouldExpand;
          
          // If collapsing, set clipStrength = strength
          if (!shouldExpand) {
            lorasData[loraIndex].clipStrength = lorasData[loraIndex].strength;
          } 
          
          // Update the widget value
          widget.value = formatLoraValue(lorasData);
          
          // Re-render to show/hide clip entry
          renderLoras(widget.value, widget);
        }
      });

      // Create name display
      const nameEl = document.createElement("div");
      nameEl.textContent = name;
      Object.assign(nameEl.style, {
        marginLeft: "4px",
        flex: "1",
        overflow: "hidden",
        textOverflow: "ellipsis",
        whiteSpace: "nowrap",
        color: active ? "rgba(226, 232, 240, 0.9)" : "rgba(226, 232, 240, 0.6)",
        fontSize: "13px",
        userSelect: "none",
        WebkitUserSelect: "none",
        MozUserSelect: "none",
        msUserSelect: "none",
      });

      // Move preview tooltip events to nameEl instead of loraEl
      let previewTimer; // Timer for delayed preview
      nameEl.addEventListener('mouseenter', async (e) => {
        e.stopPropagation();
        const rect = nameEl.getBoundingClientRect();
        previewTimer = setTimeout(async () => {
          await previewTooltip.show(name, rect.right, rect.top);
        }, 400); // 400ms delay
      });

      nameEl.addEventListener('mouseleave', (e) => {
        e.stopPropagation();
        clearTimeout(previewTimer); // Cancel if not triggered
        previewTooltip.hide();
      });
      
      // Initialize drag functionality for strength adjustment
      initDrag(loraEl, name, widget, false, previewTooltip, renderLoras);

      // Remove the preview tooltip events from loraEl
      loraEl.onmouseenter = () => {
        loraEl.style.backgroundColor = active ? "rgba(50, 60, 80, 0.8)" : "rgba(40, 45, 55, 0.6)";
      };
      
      loraEl.onmouseleave = () => {
        loraEl.style.backgroundColor = active ? "rgba(45, 55, 72, 0.7)" : "rgba(35, 40, 50, 0.5)";
      };

      // Add context menu event
      loraEl.addEventListener('contextmenu', (e) => {
        e.preventDefault();
        e.stopPropagation();
        createContextMenu(e.clientX, e.clientY, name, widget, previewTooltip, renderLoras);
      });

      // Create strength control
      const strengthControl = document.createElement("div");
      Object.assign(strengthControl.style, {
        display: "flex",
        alignItems: "center",
        gap: "8px",
      });

      // Left arrow
      const leftArrow = createArrowButton("left", () => {
        // Decrease strength
        const lorasData = parseLoraValue(widget.value);
        const loraIndex = lorasData.findIndex(l => l.name === name);
        
        if (loraIndex >= 0) {
          lorasData[loraIndex].strength = (parseFloat(lorasData[loraIndex].strength) - 0.05).toFixed(2);
          // Sync clipStrength if collapsed
          syncClipStrengthIfCollapsed(lorasData[loraIndex]);
          
          const newValue = formatLoraValue(lorasData);
          widget.value = newValue;
        }
      });

      // Strength display
      const strengthEl = document.createElement("input");
      strengthEl.classList.add("comfy-lora-strength-input");
      strengthEl.type = "text";
      strengthEl.value = typeof strength === 'number' ? strength.toFixed(2) : Number(strength).toFixed(2);
      strengthEl.addEventListener('pointerdown', () => {
        pendingFocusTarget = { name, type: "strength" };
      });
      Object.assign(strengthEl.style, {
        minWidth: "50px",
        width: "50px",
        textAlign: "center",
        color: active ? "rgba(226, 232, 240, 0.9)" : "rgba(226, 232, 240, 0.6)",
        fontSize: "13px",
        background: "none",
        border: "1px solid transparent",
        padding: "2px 4px",
        borderRadius: "3px",
        outline: "none",
      });

      // Add hover effect
      strengthEl.addEventListener('mouseenter', () => {
        strengthEl.style.border = "1px solid rgba(226, 232, 240, 0.2)";
      });

      strengthEl.addEventListener('mouseleave', () => {
        if (document.activeElement !== strengthEl) {
          strengthEl.style.border = "1px solid transparent";
        }
      });

      // Handle focus
      strengthEl.addEventListener('focus', () => {
        pendingFocusTarget = null;
        strengthEl.style.border = "1px solid rgba(66, 153, 225, 0.6)";
        strengthEl.style.background = "rgba(0, 0, 0, 0.2)";
        // Auto-select all content
        strengthEl.select();
        selectLora(name);
      });

      strengthEl.addEventListener('blur', () => {
        strengthEl.style.border = "1px solid transparent";
        strengthEl.style.background = "none";
      });

      // Handle input changes
      const commitStrengthValue = () => {
        let parsedValue = parseFloat(strengthEl.value);
        if (isNaN(parsedValue)) {
          parsedValue = 1.0;
        }
        const normalizedValue = parsedValue.toFixed(2);

        const currentLoras = parseLoraValue(widget.value);
        const loraIndex = currentLoras.findIndex(l => l.name === name);

        if (loraIndex >= 0) {
          currentLoras[loraIndex].strength = normalizedValue;
          // Sync clipStrength if collapsed
          syncClipStrengthIfCollapsed(currentLoras[loraIndex]);

          strengthEl.value = normalizedValue;
          const newLorasValue = formatLoraValue(currentLoras);
          widget.value = newLorasValue;
        } else {
          strengthEl.value = normalizedValue;
        }
      };

      strengthEl.addEventListener('change', commitStrengthValue);

      // Handle key events
      strengthEl.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
          strengthEl.blur();
        } else if (e.key === 'Tab') {
          const moved = queueFocusAdjacentFrom(strengthFocusEntry, e.shiftKey ? -1 : 1);
          commitStrengthValue();
          if (moved) {
            e.preventDefault();
          }
        }
      });

      // Right arrow
      const rightArrow = createArrowButton("right", () => {
        // Increase strength
        const lorasData = parseLoraValue(widget.value);
        const loraIndex = lorasData.findIndex(l => l.name === name);
        
        if (loraIndex >= 0) {
          lorasData[loraIndex].strength = (parseFloat(lorasData[loraIndex].strength) + 0.05).toFixed(2);
          // Sync clipStrength if collapsed
          syncClipStrengthIfCollapsed(lorasData[loraIndex]);
          
          const newValue = formatLoraValue(lorasData);
          widget.value = newValue;
        }
      });

      strengthControl.appendChild(leftArrow);
      strengthControl.appendChild(strengthEl);
      strengthControl.appendChild(rightArrow);

      // Assemble entry
      const leftSection = document.createElement("div");
      Object.assign(leftSection.style, {
        display: "flex",
        alignItems: "center",
        flex: "1",
        minWidth: "0", // Allow shrinking
      });
      
      leftSection.appendChild(dragHandle); // Add drag handle first
      leftSection.appendChild(toggle);
      leftSection.appendChild(expandButton); // Add expand button
      leftSection.appendChild(nameEl);
      
      loraEl.appendChild(leftSection);
      loraEl.appendChild(strengthControl);

      container.appendChild(loraEl);

      // If expanded, show the clip entry
      if (isExpanded) {
        totalVisibleEntries++;
        const clipEl = document.createElement("div");
        clipEl.className = "comfy-lora-clip-entry";
        Object.assign(clipEl.style, {
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          padding: "6px",
          paddingLeft: "20px", // Indent to align with parent name
          borderRadius: "6px",
          backgroundColor: active ? "rgba(65, 70, 90, 0.6)" : "rgba(50, 55, 65, 0.5)",
          borderLeft: "2px solid rgba(72, 118, 255, 0.6)",
          transition: "all 0.2s ease",
          marginBottom: "4px",
          marginLeft: "10px",
          marginTop: "-2px"
        });

        // Store the same lora name in clip entry dataset
        clipEl.dataset.loraName = name;
        clipEl.dataset.active = active;

        // Create clip name display
        const clipNameEl = document.createElement("div");
        clipNameEl.textContent = "[clip] " + name;
        Object.assign(clipNameEl.style, {
          flex: "1",
          overflow: "hidden",
          textOverflow: "ellipsis",
          whiteSpace: "nowrap",
          color: active ? "rgba(200, 215, 240, 0.9)" : "rgba(200, 215, 240, 0.6)",
          fontSize: "13px",
          userSelect: "none",
          WebkitUserSelect: "none",
          MozUserSelect: "none",
          msUserSelect: "none",
        });

        // Create clip strength control
        const clipStrengthControl = document.createElement("div");
        Object.assign(clipStrengthControl.style, {
          display: "flex",
          alignItems: "center",
          gap: "8px",
        });

        // Left arrow for clip
        const clipLeftArrow = createArrowButton("left", () => {
          // Decrease clip strength
          const lorasData = parseLoraValue(widget.value);
          const loraIndex = lorasData.findIndex(l => l.name === name);
          
          if (loraIndex >= 0) {
            lorasData[loraIndex].clipStrength = (parseFloat(lorasData[loraIndex].clipStrength) - 0.05).toFixed(2);
            
            const newValue = formatLoraValue(lorasData);
            widget.value = newValue;
          }
        });

        // Clip strength display
        const clipStrengthEl = document.createElement("input");
        clipStrengthEl.classList.add("comfy-lora-strength-input", "comfy-lora-clip-strength-input");
        clipStrengthEl.type = "text";
        clipStrengthEl.value = typeof clipStrength === 'number' ? clipStrength.toFixed(2) : Number(clipStrength).toFixed(2);
        clipStrengthEl.addEventListener('pointerdown', () => {
          pendingFocusTarget = { name, type: "clip" };
        });
        Object.assign(clipStrengthEl.style, {
          minWidth: "50px",
          width: "50px",
          textAlign: "center",
          color: active ? "rgba(200, 215, 240, 0.9)" : "rgba(200, 215, 240, 0.6)",
          fontSize: "13px",
          background: "none",
          border: "1px solid transparent",
          padding: "2px 4px",
          borderRadius: "3px",
          outline: "none",
        });

        // Add hover effect
        clipStrengthEl.addEventListener('mouseenter', () => {
          clipStrengthEl.style.border = "1px solid rgba(226, 232, 240, 0.2)";
        });

        clipStrengthEl.addEventListener('mouseleave', () => {
          if (document.activeElement !== clipStrengthEl) {
            clipStrengthEl.style.border = "1px solid transparent";
          }
        });

        // Handle focus
        clipStrengthEl.addEventListener('focus', () => {
          pendingFocusTarget = null;
          clipStrengthEl.style.border = "1px solid rgba(72, 118, 255, 0.6)";
          clipStrengthEl.style.background = "rgba(0, 0, 0, 0.2)";
          // Auto-select all content
          clipStrengthEl.select();
          selectLora(name);
        });

        clipStrengthEl.addEventListener('blur', () => {
          clipStrengthEl.style.border = "1px solid transparent";
          clipStrengthEl.style.background = "none";
        });

        // Handle input changes
        const clipFocusEntry = createFocusEntry(name, "clip");

        const commitClipStrengthValue = () => {
          let parsedValue = parseFloat(clipStrengthEl.value);
          if (isNaN(parsedValue)) {
            parsedValue = 1.0;
          }
          const normalizedValue = parsedValue.toFixed(2);

          const currentLoras = parseLoraValue(widget.value);
          const loraIndex = currentLoras.findIndex(l => l.name === name);

          if (loraIndex >= 0) {
            currentLoras[loraIndex].clipStrength = normalizedValue;
            clipStrengthEl.value = normalizedValue;

            const newLorasValue = formatLoraValue(currentLoras);
            widget.value = newLorasValue;
          } else {
            clipStrengthEl.value = normalizedValue;
          }
        };

        clipStrengthEl.addEventListener('change', commitClipStrengthValue);

        // Handle key events
        clipStrengthEl.addEventListener('keydown', (e) => {
          if (e.key === 'Enter') {
            clipStrengthEl.blur();
          } else if (e.key === 'Tab') {
            const moved = queueFocusAdjacentFrom(clipFocusEntry, e.shiftKey ? -1 : 1);
            commitClipStrengthValue();
            if (moved) {
              e.preventDefault();
            }
          }
        });

        // Right arrow for clip
        const clipRightArrow = createArrowButton("right", () => {
          // Increase clip strength
          const lorasData = parseLoraValue(widget.value);
          const loraIndex = lorasData.findIndex(l => l.name === name);
          
          if (loraIndex >= 0) {
            lorasData[loraIndex].clipStrength = (parseFloat(lorasData[loraIndex].clipStrength) + 0.05).toFixed(2);
            
            const newValue = formatLoraValue(lorasData);
            widget.value = newValue;
          }
        });

        clipStrengthControl.appendChild(clipLeftArrow);
        clipStrengthControl.appendChild(clipStrengthEl);
        clipStrengthControl.appendChild(clipRightArrow);

        // Assemble clip entry
        const clipLeftSection = document.createElement("div");
        Object.assign(clipLeftSection.style, {
          display: "flex",
          alignItems: "center",
          flex: "1",
          minWidth: "0", // Allow shrinking
        });
        
        clipLeftSection.appendChild(clipNameEl);
        
        clipEl.appendChild(clipLeftSection);
        clipEl.appendChild(clipStrengthControl);

        // Hover effects for clip entry
        clipEl.onmouseenter = () => {
          clipEl.style.backgroundColor = active ? "rgba(70, 75, 95, 0.7)" : "rgba(55, 60, 70, 0.6)";
        };
        
        clipEl.onmouseleave = () => {
          clipEl.style.backgroundColor = active ? "rgba(65, 70, 90, 0.6)" : "rgba(50, 55, 65, 0.5)";
        };

        // Add drag functionality to clip entry
        initDrag(clipEl, name, widget, true, previewTooltip, renderLoras);

        container.appendChild(clipEl);
      }
    });
    
    // Calculate height based on number of loras and fixed sizes
    const calculatedHeight = CONTAINER_PADDING + HEADER_HEIGHT + (Math.min(totalVisibleEntries, 12) * LORA_ENTRY_HEIGHT);
    updateWidgetHeight(container, calculatedHeight, defaultHeight, node);

    // After all LoRA elements are created, apply selection state as the last step
    // This ensures the selection state is not overwritten
    container.querySelectorAll('.comfy-lora-entry').forEach(entry => {
      const entryLoraName = entry.dataset.loraName;
      updateEntrySelection(entry, entryLoraName === selectedLora);
    });

    if (pendingFocusTarget) {
      const focusTarget = pendingFocusTarget;
      const safeName = escapeLoraName(focusTarget.name);
      let selector = "";

      if (focusTarget.type === "strength") {
        selector = `.comfy-lora-entry[data-lora-name="${safeName}"] .comfy-lora-strength-input`;
      } else if (focusTarget.type === "clip") {
        selector = `.comfy-lora-clip-entry[data-lora-name="${safeName}"] .comfy-lora-clip-strength-input`;
      }

      if (selector) {
        const targetInput = container.querySelector(selector);
        if (targetInput) {
          requestAnimationFrame(() => {
            targetInput.focus();
            if (typeof targetInput.select === "function") {
              targetInput.select();
            }
            selectLora(focusTarget.name);
          });
        }
      }

      pendingFocusTarget = null;
    }
  };

  // Store the value in a variable to avoid recursion
  let widgetValue = defaultValue;

  // Create widget with new DOM Widget API
  const widget = node.addDOMWidget(name, "custom", container, {
    getValue: function() {
      return widgetValue;
    },
    setValue: function(v) {
      // Remove duplicates by keeping the last occurrence of each lora name
      const uniqueValue = (v || []).reduce((acc, lora) => {
        // Remove any existing lora with the same name
        const filtered = acc.filter(l => l.name !== lora.name);
        // Add the current lora
        return [...filtered, lora];
      }, []);
      
      // Apply existing clip strength values and transfer them to the new value
      const updatedValue = uniqueValue.map(lora => {       
        // For new loras, default clip strength to model strength and expanded to false
        // unless clipStrength is already different from strength
        const clipStrength = lora.clipStrength || lora.strength;
        return {
          ...lora,
          clipStrength: clipStrength,
          expanded: lora.hasOwnProperty('expanded') ? 
                    lora.expanded : 
                    Number(clipStrength) !== Number(lora.strength)
        };
      });

      widgetValue = updatedValue;
      renderLoras(widgetValue, widget);
    },
    hideOnZoom: true,
    selectOn: ['click', 'focus']
  });

  widget.value = defaultValue;
  
  widget.callback = callback;

  widget.serializeValue = () => {
    return widgetValue;
  }

  widget.onRemove = () => {
    container.remove(); 
    previewTooltip.cleanup();
    // Remove keyboard event listener
    container.removeEventListener('keydown', handleKeyboardNavigation);
  };

  return { minWidth: 400, minHeight: defaultHeight, widget };
}

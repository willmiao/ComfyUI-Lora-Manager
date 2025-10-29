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
import { ensureLmStyles } from "./lm_styles_loader.js";

export function addLorasWidget(node, name, opts, callback) {
  ensureLmStyles();

  // Create container for loras
  const container = document.createElement("div");
  container.className = "lm-loras-container";

  forwardMiddleMouseToCanvas(container);

  // Set initial height using CSS variables approach
  const defaultHeight = 200;

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
    container.querySelectorAll('.lm-lora-entry').forEach(entry => {
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
  
  // Function to render loras from data
  const renderLoras = (value, widget) => {
    // Clear existing content
    while (container.firstChild) {
      container.removeChild(container.firstChild);
    }

    // Parse the loras data
    const lorasData = parseLoraValue(value);
    const focusSequence = [];

    const updateWidgetValue = (newValue) => {
      widget.value = newValue;

      if (typeof widget.callback === "function") {
        widget.callback(widget.value);
      }
    };

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
      emptyMessage.className = "lm-lora-empty-state";
      container.appendChild(emptyMessage);
      
      // Set fixed height for empty state
      updateWidgetHeight(container, EMPTY_CONTAINER_HEIGHT, defaultHeight, node);
      return;
    }

    // Create header
    const header = document.createElement("div");
    header.className = "lm-loras-header";

    // Add toggle all control
    const allActive = lorasData.every(lora => lora.active);
    const toggleAll = createToggle(allActive, (active) => {
      // Update all loras active state
      const lorasData = parseLoraValue(widget.value);
      lorasData.forEach(lora => lora.active = active);
      
      const newValue = formatLoraValue(lorasData);
      updateWidgetValue(newValue);
    });

    // Add label to toggle all
    const toggleLabel = document.createElement("div");
    toggleLabel.textContent = "Toggle All";
    toggleLabel.className = "lm-toggle-label";

    const toggleContainer = document.createElement("div");
    toggleContainer.className = "lm-toggle-container";
    toggleContainer.appendChild(toggleAll);
    toggleContainer.appendChild(toggleLabel);

    // Strength label with drag hint
    const strengthLabel = document.createElement("div");
    strengthLabel.textContent = "Strength";
    strengthLabel.className = "lm-strength-label";

    // Add drag hint icon next to strength label
    const dragHint = document.createElement("span");
    dragHint.innerHTML = "↔"; // Simple left-right arrow as drag indicator
    dragHint.className = "lm-drag-hint";
    strengthLabel.appendChild(dragHint);

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
      loraEl.className = "lm-lora-entry";

      // Store lora name and active state in dataset for selection
      loraEl.dataset.loraName = name;
      loraEl.dataset.active = active ? "true" : "false";

      // Add click handler for selection
      loraEl.addEventListener('click', (e) => {
        // Skip if clicking on interactive elements
        if (e.target.closest('.lm-lora-toggle') || 
            e.target.closest('input') || 
            e.target.closest('.lm-lora-arrow') ||
            e.target.closest('.lm-lora-drag-handle') ||
            e.target.closest('.lm-lora-expand-button')) {
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
          updateWidgetValue(newValue);
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
          updateWidgetValue(formatLoraValue(lorasData));

          // Re-render to show/hide clip entry
          renderLoras(widget.value, widget);
        }
      });

      // Create name display
      const nameEl = document.createElement("div");
      nameEl.textContent = name;
      nameEl.className = "lm-lora-name";

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

      // Add context menu event
      loraEl.addEventListener('contextmenu', (e) => {
        e.preventDefault();
        e.stopPropagation();
        createContextMenu(e.clientX, e.clientY, name, widget, previewTooltip, renderLoras);
      });

      // Create strength control
      const strengthControl = document.createElement("div");
      strengthControl.className = "lm-lora-strength-control";

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
          updateWidgetValue(newValue);
        }
      });

      // Strength display
      const strengthEl = document.createElement("input");
      strengthEl.classList.add("lm-lora-strength-input");
      strengthEl.type = "text";
      strengthEl.value = typeof strength === 'number' ? strength.toFixed(2) : Number(strength).toFixed(2);
      strengthEl.addEventListener('pointerdown', () => {
        pendingFocusTarget = { name, type: "strength" };
      });

      // Handle focus
      strengthEl.addEventListener('focus', () => {
        pendingFocusTarget = null;
        // Auto-select all content
        strengthEl.select();
        selectLora(name);
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
          updateWidgetValue(newLorasValue);
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
          updateWidgetValue(newValue);
        }
      });

      strengthControl.appendChild(leftArrow);
      strengthControl.appendChild(strengthEl);
      strengthControl.appendChild(rightArrow);

      // Assemble entry
      const leftSection = document.createElement("div");
      leftSection.className = "lm-lora-entry-left";
      
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
        clipEl.className = "lm-lora-clip-entry";

        // Store the same lora name in clip entry dataset
        clipEl.dataset.loraName = name;
        clipEl.dataset.active = active ? "true" : "false";

        // Create clip name display
        const clipNameEl = document.createElement("div");
        clipNameEl.textContent = "[clip] " + name;
        clipNameEl.className = "lm-lora-name";

        // Create clip strength control
        const clipStrengthControl = document.createElement("div");
        clipStrengthControl.className = "lm-lora-strength-control";

        // Left arrow for clip
        const clipLeftArrow = createArrowButton("left", () => {
          // Decrease clip strength
          const lorasData = parseLoraValue(widget.value);
          const loraIndex = lorasData.findIndex(l => l.name === name);
          
          if (loraIndex >= 0) {
            lorasData[loraIndex].clipStrength = (parseFloat(lorasData[loraIndex].clipStrength) - 0.05).toFixed(2);
            
            const newValue = formatLoraValue(lorasData);
            updateWidgetValue(newValue);
          }
        });

        // Clip strength display
        const clipStrengthEl = document.createElement("input");
        clipStrengthEl.classList.add("lm-lora-strength-input", "lm-lora-clip-strength-input");
        clipStrengthEl.type = "text";
        clipStrengthEl.value = typeof clipStrength === 'number' ? clipStrength.toFixed(2) : Number(clipStrength).toFixed(2);
        clipStrengthEl.addEventListener('pointerdown', () => {
          pendingFocusTarget = { name, type: "clip" };
        });

        // Handle focus
        clipStrengthEl.addEventListener('focus', () => {
          pendingFocusTarget = null;
          // Auto-select all content
          clipStrengthEl.select();
          selectLora(name);
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
            updateWidgetValue(newLorasValue);
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
            updateWidgetValue(newValue);
          }
        });

        clipStrengthControl.appendChild(clipLeftArrow);
        clipStrengthControl.appendChild(clipStrengthEl);
        clipStrengthControl.appendChild(clipRightArrow);

        // Assemble clip entry
        const clipLeftSection = document.createElement("div");
        clipLeftSection.className = "lm-lora-entry-left";

        clipLeftSection.appendChild(clipNameEl);

        clipEl.appendChild(clipLeftSection);
        clipEl.appendChild(clipStrengthControl);

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
    container.querySelectorAll('.lm-lora-entry').forEach(entry => {
      const entryLoraName = entry.dataset.loraName;
      updateEntrySelection(entry, entryLoraName === selectedLora);
    });

    if (pendingFocusTarget) {
      const focusTarget = pendingFocusTarget;
      const safeName = escapeLoraName(focusTarget.name);
      let selector = "";

      if (focusTarget.type === "strength") {
        selector = `.lm-lora-entry[data-lora-name="${safeName}"] .lm-lora-strength-input`;
      } else if (focusTarget.type === "clip") {
        selector = `.lm-lora-clip-entry[data-lora-name="${safeName}"] .lm-lora-clip-strength-input`;
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

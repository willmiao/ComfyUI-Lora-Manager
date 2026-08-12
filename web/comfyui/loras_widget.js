import { createToggle, createArrowButton, createDragHandle, updateEntrySelection, createExpandButton, updateExpandButtonState, createLockButton, updateLockButtonState } from "./loras_widget_components.js";
import { 
  parseLoraValue, 
  formatLoraValue, 
  shouldShowClipEntry, 
  syncClipStrengthIfCollapsed,
  getAvailableLoras,
  getAvailableLorasSync,
  isLoraNameAvailable,
  onLibraryChanged
} from "./loras_widget_utils.js";
import { initDrag, createContextMenu, initHeaderDrag, initReorderDrag, handleKeyboardNavigation } from "./loras_widget_events.js";
import { forwardMiddleMouseToCanvas, forwardWheelToCanvas, enableListWheelScroll } from "./utils.js";
import { PreviewTooltip } from "./preview_tooltip.js";
import { ensureLmStyles } from "./lm_styles_loader.js";
import { getStrengthStepPreference } from "./settings.js";

export function addLorasWidget(node, name, opts, callback) {
  ensureLmStyles();

  // Create container for loras — search for an empty container already
  // in the DOM first. During undo/redo in ComfyUI Vue render mode,
  // WidgetDOM.vue reuses its component without re-calling
  // mountWidgetElement(), so we must reuse the existing DOM element
  // instead of creating an orphaned replacement.
  let container = null;
  let reuseExisting = false;
  const existingContainers = document.querySelectorAll('.lm-loras-container');
  for (const el of existingContainers) {
    if (el.children.length === 0) {
      container = el;
      reuseExisting = true;
      break;
    }
  }

  if (!container) {
    container = document.createElement("div");
    container.className = "lm-loras-container";
  }

  if (!reuseExisting) {
    forwardMiddleMouseToCanvas(container);
    forwardWheelToCanvas(container);
  }

  // Set initial height using CSS variables approach
  const defaultHeight = 200;

  // Set a fixed minimum height so the node has a reasonable starting size.
  // Adding or removing LoRAs does NOT change the node size — the container
  // scrolls when content exceeds the allocated space.
  container.style.setProperty('--comfy-widget-min-height', `${defaultHeight}px`);

  if (!reuseExisting && typeof LiteGraph !== 'undefined' && LiteGraph.vueNodesMode) {
    container.classList.add('lm-vue-node');
    enableListWheelScroll(container);
  }

  // Check if this is a randomizer node (lock button instead of drag handle)
  const isRandomizerNode = opts?.isRandomizerNode === true;

  // Initialize default value
  const defaultValue = opts?.defaultVal || [];
  const onSelectionChange = typeof opts?.onSelectionChange === "function"
    ? opts.onSelectionChange
    : null;

  // Create preview tooltip instance
  const previewTooltip = new PreviewTooltip({ modelType: "loras" });
  
  // Selection state - only one LoRA can be selected at a time
  let selectedLora = null;
  let currentLorasData = parseLoraValue(defaultValue);
  let lastSelectionKey = "__none__";
  let pendingFocusTarget = null;

  const PREVIEW_SUPPRESSION_AFTER_DRAG_MS = 500;
  let strengthDragActive = false;
  let lastStrengthDragEndAt = 0;

  const shouldSuppressPreview = () => {
    if (strengthDragActive) {
      return true;
    }
    return Date.now() - lastStrengthDragEndAt < PREVIEW_SUPPRESSION_AFTER_DRAG_MS;
  };


  // Grouped LoRA panels. The widget value remains a single flat list, so this
  // only changes presentation and category-level controls.
  const GROUPED_PANELS = ["Characters", "Concepts", "Enhancements", "Other"];

  const ensureGroupedPanelStyles = () => {
    if (document.getElementById("lm-lora-grouped-panels-style")) {
      return;
    }

    const style = document.createElement("style");
    style.id = "lm-lora-grouped-panels-style";
    style.textContent = `
      .lm-lora-groups {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
        gap: 8px;
        width: 100%;
        align-items: start;
      }

      .lm-lora-category-section {
        min-width: 0;
        border: 1px solid rgba(255, 255, 255, 0.08);
        border-radius: 8px;
        background: rgba(0, 0, 0, 0.14);
        padding: 8px;
        box-sizing: border-box;
      }

      .lm-lora-category-title {
        margin: 0 0 8px;
        padding: 0 2px;
        overflow: hidden;
        color: rgba(255, 255, 255, 0.92);
        font-size: 16px;
        font-weight: 600;
        text-overflow: ellipsis;
        white-space: nowrap;
      }

      .lm-lora-category-section .lm-loras-header {
        margin-bottom: 6px;
      }

      .lm-lora-category-body {
        display: flex;
        flex-direction: column;
        gap: 5px;
      }
    `;
    document.head.appendChild(style);
  };

  const inferLoraCategory = (lora) => {
    if (lora?.category) {
      return GROUPED_PANELS.includes(lora.category) ? lora.category : "Other";
    }

    const normalized = String(lora?.name || "")
      .toLowerCase()
      .trim()
      .replace(/[_./\\]+/g, " ")
      .replace(/\s*-\s*/g, " ")
      .replace(/\s+/g, " ")
      .trim();

    if (
      normalized === "enhance" ||
      normalized.startsWith("enhance ") ||
      normalized === "enhancement" ||
      normalized.startsWith("enhancement ") ||
      normalized === "quality" ||
      normalized.startsWith("quality ") ||
      normalized.includes("add detail") ||
      normalized.includes("detail") ||
      normalized.includes("upscale") ||
      normalized.includes("hands") ||
      normalized.includes("eyes") ||
      normalized.includes("face") ||
      normalized.includes("skin") ||
      normalized.includes("aesthetic") ||
      normalized.includes("artfull") ||
      normalized.includes("masterpiece") ||
      normalized.includes("stabilizer")
    ) {
      return "Enhancements";
    }

    if (
      normalized === "concept" ||
      normalized.startsWith("concept ") ||
      normalized === "style" ||
      normalized.startsWith("style ") ||
      normalized === "pose" ||
      normalized.startsWith("pose ") ||
      normalized === "outfit" ||
      normalized.startsWith("outfit ") ||
      normalized === "clothing" ||
      normalized.startsWith("clothing ") ||
      normalized === "background" ||
      normalized.startsWith("background ") ||
      normalized.includes("slider") ||
      normalized.includes("lighting")
    ) {
      return "Concepts";
    }

    return "Characters";
  };

  const createCategoryHeader = (
    categoryName,
    groupItems,
    widget,
    updateWidgetValue,
    renderLoras
  ) => {
    const header = document.createElement("div");
    header.className = "lm-loras-header";

    const allActive = groupItems.length > 0 && groupItems.every((lora) => lora.active);
    const toggleAll = createToggle(allActive, (active) => {
      const currentLoras = parseLoraValue(widget.value);
      currentLoras.forEach((lora) => {
        if (inferLoraCategory(lora) === categoryName) {
          lora.active = active;
        }
      });
      updateWidgetValue(formatLoraValue(currentLoras));
    });

    const toggleLabel = document.createElement("div");
    toggleLabel.textContent = "Toggle All";
    toggleLabel.className = "lm-toggle-label";

    const toggleContainer = document.createElement("div");
    toggleContainer.className = "lm-toggle-container";
    toggleContainer.appendChild(toggleAll);
    toggleContainer.appendChild(toggleLabel);

    const strengthLabel = document.createElement("div");
    strengthLabel.textContent = "Strength";
    strengthLabel.className = "lm-strength-label";

    const dragHint = document.createElement("span");
    dragHint.textContent = "<->";
    dragHint.className = "lm-drag-hint";
    strengthLabel.appendChild(dragHint);

    header.appendChild(toggleContainer);
    header.appendChild(strengthLabel);

    // Preserve upstream's header strength-drag behaviour.
    initHeaderDrag(header, widget, renderLoras);
    return header;
  };

  const applyGroupedLayout = (
    lorasData,
    widget,
    updateWidgetValue,
    renderLoras
  ) => {
    ensureGroupedPanelStyles();

    const originalHeader = Array.from(container.children).find(
      (child) => child.classList?.contains("lm-loras-header")
    );
    originalHeader?.remove();

    const grouped = new Map(GROUPED_PANELS.map((category) => [category, []]));
    lorasData.forEach((lora) => {
      grouped.get(inferLoraCategory(lora)).push(lora);
    });

    const mainEntries = new Map();
    const clipEntries = new Map();

    container.querySelectorAll(":scope > .lm-lora-entry").forEach((entry) => {
      mainEntries.set(entry.dataset.loraName, entry);
    });
    container.querySelectorAll(":scope > .lm-lora-clip-entry").forEach((entry) => {
      clipEntries.set(entry.dataset.loraName, entry);
    });

    const groupsContainer = document.createElement("div");
    groupsContainer.className = "lm-lora-groups";

    GROUPED_PANELS.forEach((categoryName) => {
      const groupItems = grouped.get(categoryName) || [];
      if (groupItems.length === 0) {
        return;
      }

      const section = document.createElement("section");
      section.className = "lm-lora-category-section";
      section.dataset.loraCategory = categoryName;

      const title = document.createElement("div");
      title.className = "lm-lora-category-title";
      title.textContent = categoryName;

      const header = createCategoryHeader(
        categoryName,
        groupItems,
        widget,
        updateWidgetValue,
        renderLoras
      );

      const body = document.createElement("div");
      body.className = "lm-lora-category-body";

      groupItems.forEach((lora) => {
        const mainEntry = mainEntries.get(lora.name);
        const clipEntry = clipEntries.get(lora.name);
        if (mainEntry) {
          body.appendChild(mainEntry);
        }
        if (clipEntry) {
          body.appendChild(clipEntry);
        }
      });

      section.appendChild(title);
      section.appendChild(header);
      section.appendChild(body);
      groupsContainer.appendChild(section);
    });

    container.prepend(groupsContainer);
  };

  const markStrengthDragStart = () => {
    strengthDragActive = true;
    previewTooltip.hide();
  };

  const markStrengthDragEnd = () => {
    strengthDragActive = false;
    lastStrengthDragEndAt = Date.now();
    previewTooltip.hide();
  };
  
  // Function to select a LoRA
  const buildSelectionPayload = (loraName) => {
    if (!loraName) {
      return null;
    }

    const entry = currentLorasData.find((lora) => lora.name === loraName);
    if (!entry) {
      return null;
    }

    return {
      name: entry.name,
      active: !!entry.active,
      entry: { ...entry },
    };
  };

  const emitSelectionChange = (payload, options = {}) => {
    if (!onSelectionChange) {
      return;
    }

    const key = payload
      ? `${payload.name || ""}|${payload.active ? "1" : "0"}`
      : "__null__";

    if (!options.force && key === lastSelectionKey) {
      return;
    }

    lastSelectionKey = key;
    onSelectionChange(payload);
  };

  const selectLora = (loraName, options = {}) => {
    selectedLora = loraName;
    // Update visual feedback for all entries
    container.querySelectorAll('.lm-lora-entry').forEach(entry => {
      const entryLoraName = entry.dataset.loraName;
      updateEntrySelection(entry, entryLoraName === selectedLora);
    });

    if (!options.silent) {
      emitSelectionChange(buildSelectionPayload(loraName));
    }
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
    currentLorasData = lorasData;
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

    // Render each lora entry
    lorasData.forEach((loraData) => {
      const { name, strength, clipStrength, active } = loraData;
      
      // Determine expansion state using our helper function
      const isExpanded = shouldShowClipEntry(loraData);
      const strengthFocusEntry = createFocusEntry(name, "strength");
      
      // Create the main LoRA entry
      const loraEl = document.createElement("div");
      loraEl.className = "lm-lora-entry";

      // Store lora name, active state, and locked state in dataset
      loraEl.dataset.loraName = name;
      loraEl.dataset.active = active ? "true" : "false";
      loraEl.dataset.locked = (loraData.locked || false) ? "true" : "false";

      // Add click handler for selection
      loraEl.addEventListener('click', (e) => {
        // Skip if clicking on interactive elements
        if (e.target.closest('.lm-lora-toggle') ||
            e.target.closest('input') ||
            e.target.closest('.lm-lora-arrow') ||
            e.target.closest('.lm-lora-drag-handle') ||
            e.target.closest('.lm-lora-lock-button') ||
            e.target.closest('.lm-lora-expand-button')) {
          return;
        }

        e.preventDefault();
        e.stopPropagation();
        selectLora(name === selectedLora ? null : name);
        container.focus();
      });

      // Conditionally create drag handle OR lock button
      let dragHandleOrLockButton;

      if (isRandomizerNode) {
        // For randomizer node, show lock button instead of drag handle
        const isLocked = loraData.locked || false;
        dragHandleOrLockButton = createLockButton(isLocked, (newLocked) => {
          // Update this lora's locked state
          const lorasData = parseLoraValue(widget.value);
          const loraIndex = lorasData.findIndex(l => l.name === name);

          if (loraIndex >= 0) {
            lorasData[loraIndex].locked = newLocked;
            const newValue = formatLoraValue(lorasData);
            updateWidgetValue(newValue);
          }
        });
      } else {
        // For other nodes, show drag handle
        dragHandleOrLockButton = createDragHandle();
        // Initialize reorder drag functionality
        initReorderDrag(dragHandleOrLockButton, name, widget, renderLoras);
      }

      // Create toggle for this lora
      const toggle = createToggle(active, (newActive) => {
        // Update this lora's active state
        const lorasData = parseLoraValue(widget.value);
        const loraIndex = lorasData.findIndex(l => l.name === name);
        
        if (loraIndex >= 0) {
          lorasData[loraIndex].active = newActive;
          
          if (selectedLora === name) {
            emitSelectionChange({
              name,
              active: newActive,
              entry: { ...lorasData[loraIndex] },
            });
          }

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
      let previewTimer = null; // Timer for delayed preview

      const clearPreviewTimer = () => {
        if (previewTimer) {
          clearTimeout(previewTimer);
          previewTimer = null;
        }
      };

      nameEl.addEventListener('mouseenter', (e) => {
        e.stopPropagation();
        if (shouldSuppressPreview()) {
          return;
        }
        previewTimer = setTimeout(async () => {
          previewTimer = null;
          if (shouldSuppressPreview()) {
            return;
          }
          const rect = nameEl.getBoundingClientRect();
          await previewTooltip.show(name, rect.right, rect.top);
        }, 400); // 400ms delay
      });

      nameEl.addEventListener('mouseleave', (e) => {
        e.stopPropagation();
        clearPreviewTimer(); // Cancel if not triggered
        previewTooltip.hide();
      });
      
      // Initialize drag functionality for strength adjustment
      initDrag(loraEl, name, widget, false, previewTooltip, renderLoras, {
        onDragStart: () => {
          clearPreviewTimer();
          markStrengthDragStart();
        },
        onDragEnd: () => {
          clearPreviewTimer();
          markStrengthDragEnd();
        }
      });

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
          lorasData[loraIndex].strength = (parseFloat(lorasData[loraIndex].strength) - getStrengthStepPreference()).toFixed(2);
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
          lorasData[loraIndex].strength = (parseFloat(lorasData[loraIndex].strength) + getStrengthStepPreference()).toFixed(2);
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

      leftSection.appendChild(dragHandleOrLockButton); // Add drag handle or lock button first
      leftSection.appendChild(toggle);
      leftSection.appendChild(expandButton); // Add expand button
      leftSection.appendChild(nameEl);
      
      loraEl.appendChild(leftSection);
      loraEl.appendChild(strengthControl);

      container.appendChild(loraEl);

      // If expanded, show the clip entry
      if (isExpanded) {
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
            lorasData[loraIndex].clipStrength = (parseFloat(lorasData[loraIndex].clipStrength) - getStrengthStepPreference()).toFixed(2);
            
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
            lorasData[loraIndex].clipStrength = (parseFloat(lorasData[loraIndex].clipStrength) + getStrengthStepPreference()).toFixed(2);
            
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
        initDrag(clipEl, name, widget, true, previewTooltip, renderLoras, {
          onDragStart: markStrengthDragStart,
          onDragEnd: markStrengthDragEnd
        });

        container.appendChild(clipEl);
      }
    });
    

    // Reorganize the fully-rendered upstream entries into inferred category panels.
    applyGroupedLayout(lorasData, widget, updateWidgetValue, renderLoras);

    // After all LoRA elements are created, apply selection state as the last step
    // This ensures the selection state is not overwritten
    container.querySelectorAll('.lm-lora-entry').forEach(entry => {
      const entryLoraName = entry.dataset.loraName;
      updateEntrySelection(entry, entryLoraName === selectedLora);
    });

    const selectionExists = selectedLora
      ? currentLorasData.some((lora) => lora.name === selectedLora)
      : false;

    if (selectedLora && !selectionExists) {
      selectLora(null);
    } else if (selectedLora) {
      emitSelectionChange(buildSelectionPayload(selectedLora));
    }

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
            selectLora(focusTarget.name, { silent: true });
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
      return widgetValue.map(lora => {
        const entry = { ...lora };
        entry.selected = lora.name === selectedLora;
        return entry;
      });
    },
    setValue: function(v) {
      // Ensure v is an array; handle falsy, string, or object values safely
      v = Array.isArray(v) ? v : [];
      // Remove duplicates by keeping the last occurrence of each lora name
      const uniqueValue = v.reduce((acc, lora) => {
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
                    Number(clipStrength) !== Number(lora.strength),
          locked: lora.hasOwnProperty('locked') ? lora.locked : false  // Initialize locked to false if not present
        };
      });

      widgetValue = updatedValue;

      // Restore selection state when loading a saved workflow
      if (!selectedLora) {
        const selectedEntry = updatedValue.find(lora => lora.selected);
        if (selectedEntry) {
          selectedLora = selectedEntry.name;
        }
      }

      // Skip DOM re-render during drag to preserve pointer capture and event listeners.
      // The strength inputs are updated directly via the pointermove handler instead.
      if (!widget.__dragActive) {
        renderLoras(widgetValue, widget);
      }
    },
    hideOnZoom: true,
    selectOn: ['click', 'focus']
  });

  widget.value = defaultValue;
  
  widget.callback = callback;

  widget.onRemove = () => {
    while (container.firstChild) {
      container.removeChild(container.firstChild);
    }
    previewTooltip.cleanup();
    container.removeEventListener('keydown', handleKeyboardNavigation);
  };

  return { minWidth: 900, minHeight: defaultHeight, widget };
}
import { createToggle, createArrowButton, createDragHandle, updateEntrySelection, createExpandButton, updateExpandButtonState, createLockButton, updateLockButtonState } from "./loras_widget_components.js";
import { 
  parseLoraValue, 
  formatLoraValue, 
  shouldShowClipEntry, 
  syncClipStrengthIfCollapsed
} from "./loras_widget_utils.js";
import { initDrag, createContextMenu, initHeaderDrag, initReorderDrag, handleKeyboardNavigation } from "./loras_widget_events.js";
import { forwardMiddleMouseToCanvas, forwardWheelToCanvas, enableListWheelScroll } from "./utils.js";
import { PreviewTooltip } from "./preview_tooltip.js";
import { ensureLmStyles } from "./lm_styles_loader.js";
import { getStrengthStepPreference } from "./settings.js";

export function addLorasWidget(node, name, opts, callback) {
  ensureLmStyles();

  // Create container for loras — search for an empty container already
  // in the DOM first. During undo/redo in ComfyUI Vue render mode,
  // WidgetDOM.vue reuses its component without re-calling
  // mountWidgetElement(), so we must reuse the existing DOM element
  // instead of creating an orphaned replacement.
  let container = null;
  let reuseExisting = false;
  const existingContainers = document.querySelectorAll('.lm-loras-container');
  for (const el of existingContainers) {
    if (el.children.length === 0) {
      container = el;
      reuseExisting = true;
      break;
    }
  }

  if (!container) {
    container = document.createElement("div");
    container.className = "lm-loras-container";
  }

  if (!reuseExisting) {
    forwardMiddleMouseToCanvas(container);
    forwardWheelToCanvas(container);
  }

  // Set initial height using CSS variables approach
  const defaultHeight = 200;

  // Set a fixed minimum height so the node has a reasonable starting size.
  // Adding or removing LoRAs does NOT change the node size — the container
  // scrolls when content exceeds the allocated space.
  container.style.setProperty('--comfy-widget-min-height', `${defaultHeight}px`);

  if (!reuseExisting && typeof LiteGraph !== 'undefined' && LiteGraph.vueNodesMode) {
    container.classList.add('lm-vue-node');
    enableListWheelScroll(container);
  }

  // Check if this is a randomizer node (lock button instead of drag handle)
  const isRandomizerNode = opts?.isRandomizerNode === true;

  // Initialize default value
  const defaultValue = opts?.defaultVal || [];
  const onSelectionChange = typeof opts?.onSelectionChange === "function"
    ? opts.onSelectionChange
    : null;

  // Create preview tooltip instance
  const previewTooltip = new PreviewTooltip({ modelType: "loras" });
  
  // Selection state - only one LoRA can be selected at a time
  let selectedLora = null;
  let currentLorasData = parseLoraValue(defaultValue);
  let lastSelectionKey = "__none__";
  let pendingFocusTarget = null;

  const PREVIEW_SUPPRESSION_AFTER_DRAG_MS = 500;
  let strengthDragActive = false;
  let lastStrengthDragEndAt = 0;

  const shouldSuppressPreview = () => {
    if (strengthDragActive) {
      return true;
    }
    return Date.now() - lastStrengthDragEndAt < PREVIEW_SUPPRESSION_AFTER_DRAG_MS;
  };

  const markStrengthDragStart = () => {
    strengthDragActive = true;
    previewTooltip.hide();
  };

  const markStrengthDragEnd = () => {
    strengthDragActive = false;
    lastStrengthDragEndAt = Date.now();
    previewTooltip.hide();
  };
  
  // Function to select a LoRA
  const buildSelectionPayload = (loraName) => {
    if (!loraName) {
      return null;
    }

    const entry = currentLorasData.find((lora) => lora.name === loraName);
    if (!entry) {
      return null;
    }

    return {
      name: entry.name,
      active: !!entry.active,
      entry: { ...entry },
    };
  };

  const emitSelectionChange = (payload, options = {}) => {
    if (!onSelectionChange) {
      return;
    }

    const key = payload
      ? `${payload.name || ""}|${payload.active ? "1" : "0"}`
      : "__null__";

    if (!options.force && key === lastSelectionKey) {
      return;
    }

    lastSelectionKey = key;
    onSelectionChange(payload);
  };

  const selectLora = (loraName, options = {}) => {
    selectedLora = loraName;
    // Update visual feedback for all entries
    container.querySelectorAll('.lm-lora-entry').forEach(entry => {
      const entryLoraName = entry.dataset.loraName;
      updateEntrySelection(entry, entryLoraName === selectedLora);
    });

    if (!options.silent) {
      emitSelectionChange(buildSelectionPayload(loraName));
    }
  };

  // Mirror ComfyUI's setNodeHasErrors: has_errors is not an auto-tracked
  // litegraph property, so the node:property:changed event must be fired
  // manually for the Vue renderer to pick up the error state.
  //
  // The flag is applied asynchronously (setTimeout 0): applying it during
  // LGraphNode.configure makes ComfyUI's errorNodeWidgets.onConfigure create
  // a fallback UNKNOWN widget for every widgets_values entry, because it
  // treats has_errors as "node definition missing".
  let pendingErrorFlag = null;
  let errorFlagTimer = null;

  const flushErrorFlag = () => {
    errorFlagTimer = null;
    const hasMissing = pendingErrorFlag;
    pendingErrorFlag = null;
    if (typeof hasMissing !== 'boolean') {
      return;
    }
    const oldValue = node.has_errors === true;
    if (oldValue === hasMissing) {
      return;
    }
    node.has_errors = hasMissing;
    if (node.graph) {
      node.graph.trigger('node:property:changed', {
        type: 'node:property:changed',
        nodeId: node.id,
        property: 'has_errors',
        oldValue,
        newValue: hasMissing
      });
      node.graph.setDirtyCanvas(true, true);
    }
  };

  const updateNodeErrorFlag = (hasMissing) => {
    pendingErrorFlag = hasMissing;
    if (errorFlagTimer === null) {
      errorFlagTimer = setTimeout(flushErrorFlag, 0);
    }
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
    currentLorasData = lorasData;
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
      updateNodeErrorFlag(false);
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

    // Render each lora entry
    const availableSet = getAvailableLorasSync();
    if (!availableSet) {
      // Availability data missing (workflow switch without node recreation,
      // cache expiry): fetch it and re-render once it lands so missing cues
      // and the node flag always resolve. Only re-render on success to avoid
      // retry loops on failure.
      getAvailableLoras().then((set) => {
        if (set && !widget.__dragActive && container.isConnected) {
          renderLoras(widget.value, widget);
        }
      });
    }
    lorasData.forEach((loraData) => {
      const { name, strength, clipStrength, active } = loraData;
      const missing = !isLoraNameAvailable(name, availableSet);
      
      // Determine expansion state using our helper function
      const isExpanded = shouldShowClipEntry(loraData);
      const strengthFocusEntry = createFocusEntry(name, "strength");
      
      // Create the main LoRA entry
      const loraEl = document.createElement("div");
      loraEl.className = "lm-lora-entry";

      // Store lora name, active state, and locked state in dataset
      loraEl.dataset.loraName = name;
      loraEl.dataset.active = active ? "true" : "false";
      loraEl.dataset.locked = (loraData.locked || false) ? "true" : "false";

      if (missing) {
        loraEl.setAttribute("data-missing", "true");
      }

      // Add click handler for selection
      loraEl.addEventListener('click', (e) => {
        // Skip if clicking on interactive elements
        if (e.target.closest('.lm-lora-toggle') ||
            e.target.closest('input') ||
            e.target.closest('.lm-lora-arrow') ||
            e.target.closest('.lm-lora-drag-handle') ||
            e.target.closest('.lm-lora-lock-button') ||
            e.target.closest('.lm-lora-expand-button')) {
          return;
        }

        e.preventDefault();
        e.stopPropagation();
        selectLora(name === selectedLora ? null : name);
        container.focus();
      });

      // Conditionally create drag handle OR lock button
      let dragHandleOrLockButton;

      if (isRandomizerNode) {
        // For randomizer node, show lock button instead of drag handle
        const isLocked = loraData.locked || false;
        dragHandleOrLockButton = createLockButton(isLocked, (newLocked) => {
          // Update this lora's locked state
          const lorasData = parseLoraValue(widget.value);
          const loraIndex = lorasData.findIndex(l => l.name === name);

          if (loraIndex >= 0) {
            lorasData[loraIndex].locked = newLocked;
            const newValue = formatLoraValue(lorasData);
            updateWidgetValue(newValue);
          }
        });
      } else {
        // For other nodes, show drag handle
        dragHandleOrLockButton = createDragHandle();
        // Initialize reorder drag functionality
        initReorderDrag(dragHandleOrLockButton, name, widget, renderLoras);
      }

      // Create toggle for this lora
      const toggle = createToggle(active, (newActive) => {
        // Update this lora's active state
        const lorasData = parseLoraValue(widget.value);
        const loraIndex = lorasData.findIndex(l => l.name === name);
        
        if (loraIndex >= 0) {
          lorasData[loraIndex].active = newActive;
          
          if (selectedLora === name) {
            emitSelectionChange({
              name,
              active: newActive,
              entry: { ...lorasData[loraIndex] },
            });
          }

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
      if (missing) {
        nameEl.title = "LoRA not found in local library";
      }

      // Move preview tooltip events to nameEl instead of loraEl
      let previewTimer = null; // Timer for delayed preview

      const clearPreviewTimer = () => {
        if (previewTimer) {
          clearTimeout(previewTimer);
          previewTimer = null;
        }
      };

      nameEl.addEventListener('mouseenter', (e) => {
        e.stopPropagation();
        // Missing LoRAs have no preview data — skip the placeholder tooltip.
        if (missing || shouldSuppressPreview()) {
          return;
        }
        previewTimer = setTimeout(async () => {
          previewTimer = null;
          if (shouldSuppressPreview()) {
            return;
          }
          const rect = nameEl.getBoundingClientRect();
          await previewTooltip.show(name, rect.right, rect.top);
        }, 400); // 400ms delay
      });

      nameEl.addEventListener('mouseleave', (e) => {
        e.stopPropagation();
        clearPreviewTimer(); // Cancel if not triggered
        previewTooltip.hide();
      });
      
      // Initialize drag functionality for strength adjustment
      initDrag(loraEl, name, widget, false, previewTooltip, renderLoras, {
        onDragStart: () => {
          clearPreviewTimer();
          markStrengthDragStart();
        },
        onDragEnd: () => {
          clearPreviewTimer();
          markStrengthDragEnd();
        }
      });

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
          lorasData[loraIndex].strength = (parseFloat(lorasData[loraIndex].strength) - getStrengthStepPreference()).toFixed(2);
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
          lorasData[loraIndex].strength = (parseFloat(lorasData[loraIndex].strength) + getStrengthStepPreference()).toFixed(2);
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

      leftSection.appendChild(dragHandleOrLockButton); // Add drag handle or lock button first
      leftSection.appendChild(toggle);
      leftSection.appendChild(expandButton); // Add expand button
      leftSection.appendChild(nameEl);
      
      loraEl.appendChild(leftSection);
      loraEl.appendChild(strengthControl);

      container.appendChild(loraEl);

      // If expanded, show the clip entry
      if (isExpanded) {
        const clipEl = document.createElement("div");
        clipEl.className = "lm-lora-clip-entry";

        // Store the same lora name in clip entry dataset
        clipEl.dataset.loraName = name;
        clipEl.dataset.active = active ? "true" : "false";

        if (missing) {
          clipEl.setAttribute("data-missing", "true");
        }

        // Create clip name display
        const clipNameEl = document.createElement("div");
        clipNameEl.textContent = "[clip] " + name;
        clipNameEl.className = "lm-lora-name";
        if (missing) {
          clipNameEl.title = "LoRA not found in local library";
        }

        // Create clip strength control
        const clipStrengthControl = document.createElement("div");
        clipStrengthControl.className = "lm-lora-strength-control";

        // Left arrow for clip
        const clipLeftArrow = createArrowButton("left", () => {
          // Decrease clip strength
          const lorasData = parseLoraValue(widget.value);
          const loraIndex = lorasData.findIndex(l => l.name === name);
          
          if (loraIndex >= 0) {
            lorasData[loraIndex].clipStrength = (parseFloat(lorasData[loraIndex].clipStrength) - getStrengthStepPreference()).toFixed(2);
            
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
            lorasData[loraIndex].clipStrength = (parseFloat(lorasData[loraIndex].clipStrength) + getStrengthStepPreference()).toFixed(2);
            
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
        initDrag(clipEl, name, widget, true, previewTooltip, renderLoras, {
          onDragStart: markStrengthDragStart,
          onDragEnd: markStrengthDragEnd
        });

        container.appendChild(clipEl);
      }
    });
    
    // After all LoRA elements are created, apply selection state as the last step
    // This ensures the selection state is not overwritten
    container.querySelectorAll('.lm-lora-entry').forEach(entry => {
      const entryLoraName = entry.dataset.loraName;
      updateEntrySelection(entry, entryLoraName === selectedLora);
    });

    // Flag the node when any active entry references a LoRA missing locally.
    // Skipped while the availability set is not loaded (null) to avoid
    // clearing or setting the flag based on incomplete information.
    const hasMissingActive = availableSet
      ? lorasData.some(
          (lora) => lora.active && !isLoraNameAvailable(lora.name, availableSet)
        )
      : null;
    updateNodeErrorFlag(hasMissingActive);

    const selectionExists = selectedLora
      ? currentLorasData.some((lora) => lora.name === selectedLora)
      : false;

    if (selectedLora && !selectionExists) {
      selectLora(null);
    } else if (selectedLora) {
      emitSelectionChange(buildSelectionPayload(selectedLora));
    }

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
            selectLora(focusTarget.name, { silent: true });
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
      return widgetValue.map(lora => {
        const entry = { ...lora };
        entry.selected = lora.name === selectedLora;
        return entry;
      });
    },
    setValue: function(v) {
      // Ensure v is an array; handle falsy, string, or object values safely
      v = Array.isArray(v) ? v : [];
      // Remove duplicates by keeping the last occurrence of each lora name
      const uniqueValue = v.reduce((acc, lora) => {
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
                    Number(clipStrength) !== Number(lora.strength),
          locked: lora.hasOwnProperty('locked') ? lora.locked : false  // Initialize locked to false if not present
        };
      });

      widgetValue = updatedValue;

      // Restore selection state when loading a saved workflow
      if (!selectedLora) {
        const selectedEntry = updatedValue.find(lora => lora.selected);
        if (selectedEntry) {
          selectedLora = selectedEntry.name;
        }
      }

      // Skip DOM re-render during drag to preserve pointer capture and event listeners.
      // The strength inputs are updated directly via the pointermove handler instead.
      if (!widget.__dragActive) {
        renderLoras(widgetValue, widget);
      }
    },
    hideOnZoom: true,
    selectOn: ['click', 'focus']
  });

  widget.value = defaultValue;
  
  widget.callback = callback;

  // Invalidate the availability cache and re-render when the local library
  // changes (e.g. a LoRA is deleted from the Lora Manager UI) so missing
  // cues and the node error flag update without waiting for the TTL.
  const unsubscribeLibraryChange = onLibraryChanged(() => {
    if (!widget.__dragActive && container.isConnected) {
      renderLoras(widget.value, widget);
    }
  });

  // Fetch the local library and re-render once available so missing entries
  // get their visual cue and the node error flag as soon as the data lands.
  getAvailableLoras().then(() => {
    if (!widget.__dragActive && container.isConnected) {
      renderLoras(widget.value, widget);
    }
  });

  widget.onRemove = () => {
    unsubscribeLibraryChange();
    if (errorFlagTimer !== null) {
      clearTimeout(errorFlagTimer);
      errorFlagTimer = null;
      pendingErrorFlag = null;
    }
    while (container.firstChild) {
      container.removeChild(container.firstChild);
    }
    previewTooltip.cleanup();
    container.removeEventListener('keydown', handleKeyboardNavigation);
  };

  return { minWidth: 400, minHeight: defaultHeight, widget };
}

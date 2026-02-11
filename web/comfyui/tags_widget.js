import { forwardMiddleMouseToCanvas } from "./utils.js";
import { getTriggerWordMaxHeight } from "./settings.js";

export function addTagsWidget(node, name, opts, callback, wheelSensitivity = 0.02, options = {}) {
  // Create container for tags
  const container = document.createElement("div");
  container.className = "comfy-tags-container";

  const { allowStrengthAdjustment = true } = options;

  forwardMiddleMouseToCanvas(container);
  
  // Set initial height
  const defaultHeight = 150;
  
  // Get max height from settings
  const maxHeight = getTriggerWordMaxHeight();

  Object.assign(container.style, {
    display: "flex",
    flexWrap: "wrap",
    gap: "4px",
    padding: "6px",
    backgroundColor: "rgba(40, 44, 52, 0.6)",
    borderRadius: "6px",
    width: "100%",
    boxSizing: "border-box",
    overflow: "auto",
    alignItems: "flex-start", // Ensure tags align at the top of each row
    maxHeight: `${maxHeight}px` // Set max height for scrollable container
  });

  // Initialize default value as array
  const initialTagsData = opts?.defaultVal || [];

  // Fixed sizes for tag elements to avoid zoom-related calculation issues
  const TAG_HEIGHT = 26; // Adjusted height of a single tag including margins
  const TAGS_PER_ROW = 3; // Approximate number of tags per row
  const ROW_GAP = 2; // Reduced gap between rows
  const CONTAINER_PADDING = 12; // Top and bottom padding
  const EMPTY_CONTAINER_HEIGHT = 60; // Height when no tags are present

  // Function to render tags from array data
  const renderTags = (tagsData, widget) => {
    // Clear existing tags
    while (container.firstChild) {
      container.removeChild(container.firstChild);
    }

    const normalizedTags = tagsData;
    const showStrengthInfo = widget.allowStrengthAdjustment ?? allowStrengthAdjustment;

    if (normalizedTags.length === 0) {
      // Show message when no tags are present
      const emptyMessage = document.createElement("div");
      emptyMessage.textContent = "No trigger words detected";
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
      updateWidgetHeight(EMPTY_CONTAINER_HEIGHT);
      return;
    }

    // Create a row container approach for better layout control
    let rowContainer = document.createElement("div");
    rowContainer.className = "comfy-tags-row";
    Object.assign(rowContainer.style, {
      display: "flex",
      flexWrap: "wrap",
      gap: "4px",
      width: "100%",
      marginBottom: "2px" // Small gap between rows
    });
    container.appendChild(rowContainer);

    let tagCount = 0;
    normalizedTags.forEach((tagData, index) => {
      const { text, active, highlighted, strength } = tagData;
      const tagEl = document.createElement("div");
      tagEl.className = "comfy-tag";
      tagEl.dataset.captureWheel = "true";

      const textSpan = document.createElement("span");
      textSpan.className = "comfy-tag-text";
      textSpan.textContent = text;
      Object.assign(textSpan.style, {
        display: "inline-block",
        overflow: "hidden",
        textOverflow: "ellipsis",
        whiteSpace: "nowrap",
        minWidth: "0",
        flexGrow: "1",
      });
      tagEl.appendChild(textSpan);

      const strengthBadge = showStrengthInfo ? document.createElement("span") : null;
      if (strengthBadge) {
        strengthBadge.className = "comfy-tag-strength";
        Object.assign(strengthBadge.style, {
          fontSize: "11px",
          fontWeight: "600",
          padding: "1px 6px",
          borderRadius: "999px",
          letterSpacing: "0.2px",
          backgroundColor: "rgba(255,255,255,0.08)",
          color: "rgba(255,255,255,0.95)",
          border: "1px solid rgba(255,255,255,0.25)",
          lineHeight: "normal",
          minWidth: "34px",
          textAlign: "center",
          pointerEvents: "none",
          opacity: "0",
          visibility: "hidden",
          transition: "opacity 0.2s ease",
        });
        tagEl.appendChild(strengthBadge);
      }

      updateTagStyle(tagEl, active, highlighted, strength);
      updateStrengthDisplay(tagEl, strength, text, showStrengthInfo);

      // Add click handler to toggle state
      tagEl.addEventListener("click", (e) => {
        e.stopPropagation();

        // Toggle active state for this specific tag using its index
        const updatedTags = [...widget.value];
        updatedTags[index].active = !updatedTags[index].active;
        textSpan.textContent = updatedTags[index].text;
        updateTagStyle(
          tagEl,
          updatedTags[index].active,
          updatedTags[index].highlighted,
          updatedTags[index].strength
        );
        updateStrengthDisplay(tagEl, updatedTags[index].strength, updatedTags[index].text);

        tagEl.dataset.active = updatedTags[index].active ? "true" : "false";
        tagEl.dataset.highlighted = updatedTags[index].highlighted ? "true" : "false";

        widget.value = updatedTags;
      });

      // Add mouse wheel handler to adjust strength
      if (showStrengthInfo) {
        tagEl.addEventListener("wheel", (e) => {
          e.preventDefault();
          e.stopPropagation();

          // Only adjust strength if the mouse is over the tag
          const updatedTags = [...widget.value];
          let currentStrength = updatedTags[index].strength;
          
          // If no strength is set, default to 1.0
          if (currentStrength === undefined || currentStrength === null) {
            currentStrength = 1.0;
          }

          // Adjust strength based on scroll direction
          // DeltaY < 0 is scroll up, deltaY > 0 is scroll down
          if (e.deltaY < 0) {
            // Scroll up: increase strength by wheelSensitivity
            currentStrength += wheelSensitivity;
          } else {
            // Scroll down: decrease strength by wheelSensitivity
            currentStrength -= wheelSensitivity;
          }

          // Ensure strength doesn't go below 0
          currentStrength = Math.max(0, currentStrength);

          // Update the strength value
          updatedTags[index].strength = currentStrength;
          textSpan.textContent = updatedTags[index].text;

          updateStrengthDisplay(tagEl, currentStrength, updatedTags[index].text, showStrengthInfo);

          widget.value = updatedTags;
        });
      }

      rowContainer.appendChild(tagEl);
      tagCount++;
    });
    
    // Calculate height based on number of tags and fixed sizes
    const tagsCount = normalizedTags.length;
    const rows = Math.ceil(tagsCount / TAGS_PER_ROW);
    const calculatedHeight = CONTAINER_PADDING + (rows * TAG_HEIGHT) + ((rows - 1) * ROW_GAP);
    
    // Update widget height with calculated value
    updateWidgetHeight(calculatedHeight);
  };

  // Function to update widget height consistently
  const updateWidgetHeight = (height) => {
    const maxHeight = getTriggerWordMaxHeight();
    // Ensure height is within bounds [defaultHeight, maxHeight]
    const finalHeight = Math.min(Math.max(defaultHeight, height), maxHeight);

    // Update CSS variables
    container.style.setProperty('--comfy-widget-min-height', `${finalHeight}px`);
    container.style.setProperty('--comfy-widget-height', `${finalHeight}px`);

    // Force node to update size after a short delay to ensure DOM is updated
    if (node) {
      setTimeout(() => {
        node.setDirtyCanvas(true, true);
      }, 10);
    }
  };

  // Helper function to update tag style based on active state
  function updateTagStyle(tagEl, active, highlighted = false, strength = null) {
    const baseStyles = {
      padding: "3px 10px",
      borderRadius: "6px",
      maxWidth: "200px",
      overflow: "hidden",
      textOverflow: "ellipsis",
      whiteSpace: "nowrap",
      fontSize: "13px",
      cursor: "pointer",
      transition: "all 0.2s ease",
      border: "1px solid transparent",
      display: "inline-flex",
      alignItems: "center",
      gap: "6px",
      boxShadow: "0 1px 2px rgba(0,0,0,0.1)",
      margin: "1px", 
      userSelect: "none",
      WebkitUserSelect: "none",
      MozUserSelect: "none",
      msUserSelect: "none",
      height: "22px", // Increased height to better fit text with descenders
      minHeight: "22px", // Matching minHeight
      boxSizing: "border-box",
      width: "fit-content",
      maxWidth: "200px",
      lineHeight: "16px", // Added explicit line-height
      verticalAlign: "middle", // Added vertical alignment
      textAlign: "center", // Center text horizontally
    };

    const highlightStyles = highlighted
      ? {
          boxShadow: "0 0 0 2px rgba(255, 255, 255, 0.35), 0 1px 2px rgba(0,0,0,0.15)",
          borderColor: "rgba(246, 224, 94, 0.8)",
          backgroundImage: "linear-gradient(120deg, rgba(255,255,255,0.08), rgba(255,255,255,0))",
        }
      : {
          boxShadow: "0 1px 2px rgba(0,0,0,0.1)",
          backgroundImage: "none",
        };

    if (active) {
      Object.assign(tagEl.style, {
        ...baseStyles,
        backgroundColor: "rgba(66, 153, 225, 0.9)",
        color: "white",
        borderColor: "rgba(66, 153, 225, 0.9)",
        ...highlightStyles,
      });
    } else {
      Object.assign(tagEl.style, {
        ...baseStyles,
        backgroundColor: "rgba(45, 55, 72, 0.7)",
        color: "rgba(226, 232, 240, 0.8)",
        borderColor: "rgba(226, 232, 240, 0.2)",
        ...highlightStyles,
      });
    }

    // Add hover effect
    tagEl.onmouseenter = () => {
      tagEl.style.transform = "translateY(-1px)";
      tagEl.dataset.prevBoxShadow = tagEl.style.boxShadow || "";
      tagEl.style.boxShadow = "0 2px 4px rgba(0,0,0,0.2)";
    };

    tagEl.onmouseleave = () => {
      tagEl.style.transform = "translateY(0)";
      tagEl.style.boxShadow = tagEl.dataset.prevBoxShadow || "0 1px 2px rgba(0,0,0,0.1)";
    };

    tagEl.dataset.active = active ? "true" : "false";
    tagEl.dataset.highlighted = highlighted ? "true" : "false";
  }

  function formatStrengthValue(value) {
    if (value === undefined || value === null) {
      return null;
    }
    const num = Number(value);
    if (!Number.isFinite(num)) {
      return null;
    }
    return num.toFixed(2);
  }

  function updateStrengthDisplay(tagEl, strength, baseText, showStrengthInfo) {
    if (!showStrengthInfo) {
      tagEl.title = baseText;
      return;
    }
    const badge = tagEl.querySelector(".comfy-tag-strength");
    if (!badge) {
      tagEl.title = baseText;
      return;
    }
    const displayValue = strength === undefined || strength === null ? 1 : strength;
    const formatted = formatStrengthValue(displayValue);
    if (formatted !== null) {
      badge.textContent = formatted;
      badge.style.opacity = "1";
      badge.style.visibility = "visible";
      tagEl.title = `${baseText} (${formatted})`;
    } else {
      badge.textContent = "";
      badge.style.opacity = "0";
      badge.style.visibility = "hidden";
      tagEl.title = baseText;
    }
  }

  // Store the value as array
  let widgetValue = initialTagsData;

  // Create widget with new DOM Widget API
  const widget = node.addDOMWidget(name, "custom", container, {
    getValue: function() {
      return widgetValue;
    },
    setValue: function(v) {
      widgetValue = v;
      renderTags(widgetValue, widget);
    },
    getMaxHeight: function() {
      return getTriggerWordMaxHeight();
    },
    hideOnZoom: true,
    selectOn: ['click', 'focus']
  });

  // Set initial value
  widget.value = initialTagsData;

  // Set callback
  widget.callback = callback;

  widget.serializeValue = () => {
    return widgetValue
  };

  return { minWidth: 300, minHeight: defaultHeight, maxHeight: getTriggerWordMaxHeight(), widget };
}

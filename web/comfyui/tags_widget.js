import { app } from "../../scripts/app.js";
import { forwardMiddleMouseToCanvas, forwardWheelToCanvas } from "./utils.js";

const MIN_HEIGHT = 150;
const GROUP_EDITOR_ID = "lm-trigger-group-editor";

function isGroupTag(tagData) {
  return Array.isArray(tagData?.items);
}

function cloneTagData(tagData) {
  if (!isGroupTag(tagData)) {
    return { ...tagData };
  }

  return {
    ...tagData,
    items: tagData.items.map((item) => ({ ...item })),
  };
}

function getGroupState(tagData) {
  const items = Array.isArray(tagData?.items) ? tagData.items : [];
  const hasChildren = items.length > 0;
  const activeChildren = items.filter((item) => item.active).length;
  const highlightedChildren = items.some((item) => item.highlighted);

  return {
    hasChildren,
    activeChildren,
    totalChildren: items.length,
    hasInactiveChildren: hasChildren && activeChildren < items.length,
    highlighted: Boolean(tagData?.highlighted) || highlightedChildren,
  };
}

function splitTopLevelCommas(text) {
  if (typeof text !== "string" || !text.trim()) {
    return [];
  }

  const parts = [];
  let current = "";
  let depth = 0;

  for (const char of text) {
    if (char === "(") {
      depth += 1;
      current += char;
      continue;
    }
    if (char === ")") {
      depth = Math.max(0, depth - 1);
      current += char;
      continue;
    }
    if (char === "," && depth === 0) {
      const trimmed = current.trim();
      if (trimmed) {
        parts.push(trimmed);
      }
      current = "";
      continue;
    }
    current += char;
  }

  const trimmed = current.trim();
  if (trimmed) {
    parts.push(trimmed);
  }

  return parts;
}

function createStrengthBadge() {
  const badge = document.createElement("span");
  badge.className = "comfy-tag-strength";
  Object.assign(badge.style, {
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
  return badge;
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

function ensureGroupEditorState(widget) {
  if (!widget._groupEditorState) {
    widget._groupEditorState = {
      openIndex: null,
      anchorEl: null,
      panelEl: null,
      closeHandlersAttached: false,
      outsideClickHandler: null,
      keydownHandler: null,
      trackingFrame: null,
      lastUiScale: null,
      lastAnchorRect: null,
    };
  }
  return widget._groupEditorState;
}

function getCanvasUiScale() {
  const rawScale = Number(app?.canvas?.ds?.scale);
  if (!Number.isFinite(rawScale) || rawScale <= 0) {
    return 1;
  }
  return Math.min(1.35, Math.max(0.85, rawScale));
}

function roundScaled(value, scale) {
  return Math.round(value * scale * 100) / 100;
}

function getEditorMetrics(scale) {
  return {
    panelMinWidth: roundScaled(220, scale),
    panelMaxWidth: roundScaled(360, scale),
    panelMaxHeight: roundScaled(240, scale),
    panelPadding: roundScaled(10, scale),
    panelRadius: roundScaled(10, scale),
    panelGap: roundScaled(8, scale),
    headerGap: roundScaled(2, scale),
    titleFontSize: roundScaled(12, scale),
    subtitleFontSize: roundScaled(11, scale),
    itemsGap: roundScaled(6, scale),
    childTagFontSize: roundScaled(13, scale),
    childTagPaddingY: roundScaled(3, scale),
    childTagPaddingX: roundScaled(10, scale),
    childTagMinHeight: roundScaled(22, scale),
    childTagMaxWidth: roundScaled(200, scale),
    childTagRadius: roundScaled(6, scale),
  };
}

function getRectSnapshot(element) {
  if (!element || !document.body.contains(element)) {
    return null;
  }

  const rect = element.getBoundingClientRect();
  return {
    left: Math.round(rect.left * 100) / 100,
    top: Math.round(rect.top * 100) / 100,
    width: Math.round(rect.width * 100) / 100,
    height: Math.round(rect.height * 100) / 100,
  };
}

function closeGroupEditor(widget) {
  const state = ensureGroupEditorState(widget);
  state.openIndex = null;
  state.anchorEl = null;
  state.lastUiScale = null;
  state.lastAnchorRect = null;
  if (state.panelEl) {
    state.panelEl.remove();
    state.panelEl = null;
  }
  if (state.trackingFrame) {
    cancelAnimationFrame(state.trackingFrame);
    state.trackingFrame = null;
  }
  if (state.closeHandlersAttached) {
    document.removeEventListener("mousedown", state.outsideClickHandler, true);
    document.removeEventListener("keydown", state.keydownHandler, true);
    state.closeHandlersAttached = false;
  }
}

function attachGroupEditorCloseHandlers(widget) {
  const state = ensureGroupEditorState(widget);
  if (state.closeHandlersAttached) {
    return;
  }

  state.outsideClickHandler = (event) => {
    const panel = state.panelEl;
    const anchor = state.anchorEl;
    if (panel?.contains(event.target) || anchor?.contains(event.target)) {
      return;
    }
    closeGroupEditor(widget);
  };

  state.keydownHandler = (event) => {
    if (event.key === "Escape") {
      closeGroupEditor(widget);
    }
  };

  document.addEventListener("mousedown", state.outsideClickHandler, true);
  document.addEventListener("keydown", state.keydownHandler, true);
  state.closeHandlersAttached = true;
}

function updateWidgetValue(widget, updater) {
  const nextValue = updater((widget.value || []).map(cloneTagData));
  widget.value = nextValue;
}

function createTagElement({
  text,
  active,
  highlighted,
  group = false,
  mixed = false,
  styleScale = 1,
  textMaxWidth = null,
}) {
  const tagEl = document.createElement("div");
  tagEl.className = "comfy-tag";
  tagEl.dataset.captureWheel = "true";

  const baseStyles = {
    padding: `${roundScaled(group ? 5 : 3, styleScale)}px ${roundScaled(group ? 8 : 10, styleScale)}px`,
    borderRadius: `${roundScaled(6, styleScale)}px`,
    overflow: "hidden",
    textOverflow: "ellipsis",
    whiteSpace: "nowrap",
    fontSize: `${roundScaled(group ? 12 : 13, styleScale)}px`,
    cursor: "pointer",
    transition: "all 0.2s ease",
    border: "1px solid transparent",
    display: "inline-flex",
    alignItems: "center",
    gap: `${roundScaled(6, styleScale)}px`,
    boxShadow: "0 1px 2px rgba(0,0,0,0.1)",
    margin: "1px",
    userSelect: "none",
    WebkitUserSelect: "none",
    MozUserSelect: "none",
    msUserSelect: "none",
    minHeight: `${roundScaled(group ? 26 : 22, styleScale)}px`,
    boxSizing: "border-box",
    width: "fit-content",
    maxWidth: `${roundScaled(group ? 260 : 200, styleScale)}px`,
    lineHeight: `${roundScaled(16, styleScale)}px`,
    verticalAlign: "middle",
    textAlign: "center",
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

  Object.assign(tagEl.style, {
    ...baseStyles,
    ...(active
      ? {
          backgroundColor: "rgba(66, 153, 225, 0.9)",
          color: "white",
          borderColor: "rgba(66, 153, 225, 0.9)",
        }
      : {
          backgroundColor: "rgba(45, 55, 72, 0.7)",
          color: "rgba(226, 232, 240, 0.8)",
          borderColor: "rgba(226, 232, 240, 0.2)",
        }),
    ...highlightStyles,
  });

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
  tagEl.dataset.mixed = mixed ? "true" : "false";
  tagEl.dataset.group = group ? "true" : "false";

  if (text) {
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
      maxWidth: textMaxWidth !== null
        ? `${roundScaled(textMaxWidth, styleScale)}px`
        : group
          ? `${roundScaled(170, styleScale)}px`
          : "inherit",
    });
    tagEl.appendChild(textSpan);
  }

  return tagEl;
}

function positionGroupEditor(widget) {
  const state = ensureGroupEditorState(widget);
  if (!state.panelEl || !state.anchorEl || !document.body.contains(state.anchorEl)) {
    closeGroupEditor(widget);
    return;
  }

  const anchorRect = state.anchorEl.getBoundingClientRect();
  const panel = state.panelEl;
  const viewportWidth = window.innerWidth;
  const viewportHeight = window.innerHeight;
  const panelRect = panel.getBoundingClientRect();

  let left = anchorRect.left;
  let top = anchorRect.bottom + roundScaled(8, getCanvasUiScale());

  if (left + panelRect.width > viewportWidth - 8) {
    left = Math.max(8, viewportWidth - panelRect.width - 8);
  }

  if (top + panelRect.height > viewportHeight - 8) {
    top = Math.max(8, anchorRect.top - panelRect.height - 8);
  }

  panel.style.left = `${left}px`;
  panel.style.top = `${top}px`;
  state.lastAnchorRect = getRectSnapshot(state.anchorEl);
}

function startGroupEditorTracking(widget) {
  const state = ensureGroupEditorState(widget);
  if (state.trackingFrame) {
    return;
  }

  const tick = () => {
    state.trackingFrame = null;

    if (state.openIndex === null || !state.anchorEl || !state.panelEl) {
      return;
    }

    const nextScale = getCanvasUiScale();
    const nextRect = getRectSnapshot(state.anchorEl);
    if (!nextRect) {
      closeGroupEditor(widget);
      return;
    }

    const scaleChanged = state.lastUiScale === null || Math.abs(nextScale - state.lastUiScale) > 0.001;
    const rectChanged =
      !state.lastAnchorRect ||
      nextRect.left !== state.lastAnchorRect.left ||
      nextRect.top !== state.lastAnchorRect.top ||
      nextRect.width !== state.lastAnchorRect.width ||
      nextRect.height !== state.lastAnchorRect.height;

    if (scaleChanged) {
      const currentTag = (widget.value || [])[state.openIndex];
      if (!currentTag || !isGroupTag(currentTag)) {
        closeGroupEditor(widget);
        return;
      }
      renderGroupEditor(widget, currentTag, state.openIndex);
    } else if (rectChanged) {
      positionGroupEditor(widget);
    }

    if (state.openIndex !== null && state.anchorEl && state.panelEl) {
      state.trackingFrame = requestAnimationFrame(tick);
    }
  };

  state.trackingFrame = requestAnimationFrame(tick);
}

function renderGroupEditor(widget, tagData, index) {
  const state = ensureGroupEditorState(widget);
  if (state.openIndex !== index || !state.anchorEl) {
    closeGroupEditor(widget);
    return;
  }

  if (state.panelEl) {
    state.panelEl.remove();
  }

  const uiScale = getCanvasUiScale();
  const metrics = getEditorMetrics(uiScale);

  const panel = document.createElement("div");
  panel.id = GROUP_EDITOR_ID;
  panel.className = "lm-trigger-group-editor";
  Object.assign(panel.style, {
    position: "fixed",
    zIndex: "10001",
    minWidth: `${metrics.panelMinWidth}px`,
    maxWidth: `${metrics.panelMaxWidth}px`,
    maxHeight: `${metrics.panelMaxHeight}px`,
    overflowY: "auto",
    padding: `${metrics.panelPadding}px`,
    borderRadius: `${metrics.panelRadius}px`,
    border: "1px solid rgba(255,255,255,0.15)",
    background: "rgba(22, 26, 32, 0.96)",
    boxShadow: "0 10px 30px rgba(0,0,0,0.35)",
    backdropFilter: "blur(8px)",
    display: "flex",
    flexDirection: "column",
    gap: `${metrics.panelGap}px`,
  });

  const header = document.createElement("div");
  header.className = "lm-trigger-group-editor__header";
  Object.assign(header.style, {
    display: "flex",
    flexDirection: "column",
    gap: `${metrics.headerGap}px`,
    minWidth: "0",
  });

  const title = document.createElement("div");
  title.className = "lm-trigger-group-editor__title";
  title.textContent = tagData.text;
  Object.assign(title.style, {
    color: "rgba(255,255,255,0.96)",
    fontSize: `${metrics.titleFontSize}px`,
    fontWeight: "600",
    whiteSpace: "nowrap",
    overflow: "hidden",
    textOverflow: "ellipsis",
  });

  const groupState = getGroupState(tagData);
  const subtitle = document.createElement("div");
  subtitle.className = "lm-trigger-group-editor__subtitle";
  subtitle.textContent = `${groupState.activeChildren}/${groupState.totalChildren} active`;
  Object.assign(subtitle.style, {
    color: "rgba(226,232,240,0.72)",
    fontSize: `${metrics.subtitleFontSize}px`,
  });
  header.appendChild(title);
  header.appendChild(subtitle);
  panel.appendChild(header);

  const itemsWrap = document.createElement("div");
  itemsWrap.className = "lm-trigger-group-editor__items";
  Object.assign(itemsWrap.style, {
    display: "flex",
    flexWrap: "wrap",
    gap: `${metrics.itemsGap}px`,
  });

  tagData.items.forEach((item, itemIndex) => {
    const childEl = createTagElement({
      text: item.text,
      active: item.active,
      highlighted: item.highlighted,
      group: false,
      mixed: false,
      styleScale: uiScale,
      textMaxWidth: metrics.childTagMaxWidth,
    });
    childEl.title = item.text;
    childEl.addEventListener("click", (event) => {
      event.preventDefault();
      event.stopPropagation();
      updateWidgetValue(widget, (updatedTags) => {
        updatedTags[index].items[itemIndex].active = !updatedTags[index].items[itemIndex].active;
        return updatedTags;
      });
    });
    itemsWrap.appendChild(childEl);
  });

  if (!tagData.items.length) {
    const emptyHint = document.createElement("div");
    emptyHint.className = "lm-trigger-group-editor__empty";
    emptyHint.textContent = "No tags in this group";
    Object.assign(emptyHint.style, {
      fontSize: `${metrics.titleFontSize}px`,
      opacity: "0.7",
      fontStyle: "italic",
      color: "rgba(226,232,240,0.75)",
    });
    itemsWrap.appendChild(emptyHint);
  }

  panel.appendChild(itemsWrap);
  document.body.appendChild(panel);

  state.panelEl = panel;
  state.lastUiScale = uiScale;
  state.lastAnchorRect = getRectSnapshot(state.anchorEl);
  attachGroupEditorCloseHandlers(widget);
  positionGroupEditor(widget);
  startGroupEditorTracking(widget);
}

function openGroupEditor(widget, index, anchorEl) {
  const state = ensureGroupEditorState(widget);
  state.openIndex = index;
  state.anchorEl = anchorEl;
}

function toggleGroupEditor(widget, index, anchorEl) {
  const state = ensureGroupEditorState(widget);
  if (state.openIndex === index && state.panelEl) {
    closeGroupEditor(widget);
    return;
  }
  openGroupEditor(widget, index, anchorEl);
}

export function addTagsWidget(node, name, opts, callback, wheelSensitivity = 0.02, options = {}) {
  const container = document.createElement("div");
  container.className = "comfy-tags-container";

  const { allowStrengthAdjustment = true } = options;

  forwardMiddleMouseToCanvas(container);
  forwardWheelToCanvas(container);

  Object.assign(container.style, {
    display: "flex",
    flexWrap: "wrap",
    gap: "6px",
    padding: "6px",
    backgroundColor: "rgba(40, 44, 52, 0.6)",
    borderRadius: "6px",
    width: "100%",
    height: "100%",
    boxSizing: "border-box",
    overflow: "auto",
    alignItems: "flex-start",
    alignContent: "flex-start",
  });

  const initialTagsData = opts?.defaultVal || [];

  function renderSimpleTag(tagData, index, widget, showStrengthInfo) {
    const { text, active, highlighted, strength } = tagData;
    const tagEl = createTagElement({
      text,
      active,
      highlighted,
      group: false,
      mixed: false,
    });

    const strengthBadge = showStrengthInfo ? createStrengthBadge() : null;
    if (strengthBadge) {
      tagEl.appendChild(strengthBadge);
    }
    updateStrengthDisplay(tagEl, strength, text, showStrengthInfo);

    tagEl.addEventListener("click", (e) => {
      e.stopPropagation();
      updateWidgetValue(widget, (updatedTags) => {
        updatedTags[index].active = !updatedTags[index].active;
        return updatedTags;
      });
    });

    if (showStrengthInfo) {
      tagEl.addEventListener("wheel", (e) => {
        e.preventDefault();
        e.stopPropagation();

        updateWidgetValue(widget, (updatedTags) => {
          let currentStrength = updatedTags[index].strength;
          if (currentStrength === undefined || currentStrength === null) {
            currentStrength = 1.0;
          }

          currentStrength += e.deltaY < 0 ? wheelSensitivity : -wheelSensitivity;
          updatedTags[index].strength = Math.max(0, currentStrength);
          return updatedTags;
        });
      });
    }

    return tagEl;
  }

  function renderGroupTag(tagData, index, widget, showStrengthInfo) {
    const groupState = getGroupState(tagData);
    const groupChip = createTagElement({
      text: tagData.text,
      active: tagData.active,
      highlighted: groupState.highlighted,
      group: true,
      mixed: groupState.hasInactiveChildren,
    });
    Object.assign(groupChip.style, {
      maxWidth: "280px",
      paddingRight: "6px",
    });

    const textEl = groupChip.querySelector(".comfy-tag-text");
    if (textEl) {
      textEl.style.maxWidth = "140px";
    }

    if (tagData.items.length > 1) {
      const countBadge = document.createElement("span");
      countBadge.className = "lm-trigger-count-badge";
      countBadge.textContent = `${groupState.activeChildren}/${groupState.totalChildren}`;
      Object.assign(countBadge.style, {
        fontSize: "11px",
        padding: "1px 6px",
        borderRadius: "999px",
        backgroundColor: "rgba(255,255,255,0.12)",
        color: "inherit",
        flexShrink: "0",
        boxSizing: "border-box",
        minWidth: "42px",
        display: "inline-flex",
        alignItems: "center",
        justifyContent: "center",
        lineHeight: "1",
        fontVariantNumeric: "tabular-nums",
      });
      if (groupState.hasInactiveChildren) {
        countBadge.classList.add("lm-trigger-count-badge--edited");
        Object.assign(countBadge.style, {
          backgroundColor: "rgba(255,255,255,0.08)",
          boxShadow: "inset 0 0 0 1px rgba(255,255,255,0.28)",
        });
      }
      groupChip.appendChild(countBadge);
    }

    if (showStrengthInfo) {
      const strengthBadge = createStrengthBadge();
      groupChip.appendChild(strengthBadge);
      updateStrengthDisplay(groupChip, tagData.strength, tagData.text, showStrengthInfo);
    } else {
      const activePreview = tagData.items
        .filter((item) => item.active)
        .map((item) => item.text)
        .join(", ");
      groupChip.title = activePreview ? `${tagData.text}\nActive: ${activePreview}` : tagData.text;
    }

    let editButton = null;

    if (tagData.items.length > 1) {
      editButton = document.createElement("button");
      editButton.type = "button";
      editButton.className = "lm-trigger-group-edit-button";
      editButton.textContent = "⋯";
      Object.assign(editButton.style, {
        border: "none",
        background: "transparent",
        color: "inherit",
        cursor: "pointer",
        fontSize: "14px",
        lineHeight: "1",
        padding: "0 2px",
        marginLeft: "2px",
        opacity: groupState.hasInactiveChildren ? "0.9" : "0.72",
        flexShrink: "0",
      });
      editButton.title = "Edit group tags";

      const openEditor = (event) => {
        event.preventDefault();
        event.stopPropagation();
        toggleGroupEditor(widget, index, groupChip);
        renderGroupEditor(widget, tagData, index);
      };

      editButton.addEventListener("click", openEditor);
      groupChip.addEventListener("contextmenu", openEditor);

      groupChip.appendChild(editButton);
    }

    groupChip.addEventListener("click", (e) => {
      e.stopPropagation();
      if (editButton && e.target === editButton) {
        return;
      }
      updateWidgetValue(widget, (updatedTags) => {
        updatedTags[index].active = !updatedTags[index].active;
        return updatedTags;
      });
    });

    if (showStrengthInfo) {
      groupChip.addEventListener("wheel", (e) => {
        if (editButton && e.target === editButton) {
          return;
        }
        e.preventDefault();
        e.stopPropagation();

        updateWidgetValue(widget, (updatedTags) => {
          let currentStrength = updatedTags[index].strength;
          if (currentStrength === undefined || currentStrength === null) {
            currentStrength = 1.0;
          }

          currentStrength += e.deltaY < 0 ? wheelSensitivity : -wheelSensitivity;
          updatedTags[index].strength = Math.max(0, currentStrength);
          return updatedTags;
        });
      });
    }

    return groupChip;
  }

  const renderTags = (tagsData, widget) => {
    while (container.firstChild) {
      container.removeChild(container.firstChild);
    }

    const normalizedTags = Array.isArray(tagsData) ? tagsData : [];
    const showStrengthInfo = widget.allowStrengthAdjustment ?? allowStrengthAdjustment;
    const groupAnchors = new Map();

    if (normalizedTags.length === 0) {
      closeGroupEditor(widget);
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
        width: "100%",
      });
      container.appendChild(emptyMessage);
      return;
    }

    normalizedTags.forEach((tagData, index) => {
      const tagEl = isGroupTag(tagData)
        ? renderGroupTag(tagData, index, widget, showStrengthInfo)
        : renderSimpleTag(tagData, index, widget, showStrengthInfo);
      container.appendChild(tagEl);
      if (isGroupTag(tagData)) {
        groupAnchors.set(index, tagEl);
      }
    });

    const state = ensureGroupEditorState(widget);
    if (state.openIndex !== null) {
      const activeGroup = normalizedTags[state.openIndex];
      const anchorEl = groupAnchors.get(state.openIndex);
      if (!activeGroup || !anchorEl || !isGroupTag(activeGroup)) {
        closeGroupEditor(widget);
      } else {
        state.anchorEl = anchorEl;
        renderGroupEditor(widget, activeGroup, state.openIndex);
      }
    } else if (state.panelEl) {
      closeGroupEditor(widget);
    }
  };

  let widgetValue = initialTagsData;

  const widget = node.addDOMWidget(name, "custom", container, {
    getValue: function() {
      return widgetValue;
    },
    setValue: function(v) {
      widgetValue = Array.isArray(v) ? v : [];
      renderTags(widgetValue, widget);
    },
    getMinHeight: () => MIN_HEIGHT,
    hideOnZoom: true,
    selectOn: ["click", "focus"],
  });

  widget.value = initialTagsData;
  widget.callback = callback;
  widget.serializeValue = () => widgetValue;
  widget.splitTopLevelCommas = splitTopLevelCommas;
  widget.closeGroupEditor = () => closeGroupEditor(widget);

  return { minWidth: 300, minHeight: MIN_HEIGHT, widget };
}

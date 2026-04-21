import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";
import { CONVERTED_TYPE, getNodeFromGraph } from "./utils.js";
import { addTagsWidget } from "./tags_widget.js";
import { getWheelSensitivity } from "./settings.js";

function normalizeTagText(text) {
  return typeof text === "string" ? text.trim().toLowerCase() : "";
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

function isGroupTag(tag) {
  return Array.isArray(tag?.items);
}

function parseSerializedText(text) {
  const normalizedText = typeof text === "string" ? text.trim() : "";
  const strengthMatch = normalizedText.match(/^\((.+):([\d.]+)\)$/);
  if (!strengthMatch) {
    return {
      text: normalizedText,
      strength: null,
    };
  }

  const parsedStrength = Number(strengthMatch[2]);
  return {
    text: strengthMatch[1].trim(),
    strength: Number.isFinite(parsedStrength) ? parsedStrength : null,
  };
}

function cloneTag(tag) {
  if (!isGroupTag(tag)) {
    return { ...tag };
  }
  return {
    ...tag,
    items: tag.items.map((item) => ({ ...item })),
  };
}

function collectHighlightTokens(wordsArray) {
  const tokens = new Set();

  const addToken = (text) => {
    const normalized = normalizeTagText(text);
    if (normalized) {
      tokens.add(normalized);
    }
  };

  wordsArray.forEach((rawWord) => {
    if (typeof rawWord !== "string") {
      return;
    }

    addToken(rawWord);

    const groupParts = rawWord.split(/,{2,}/);
    groupParts.forEach((groupPart) => {
      addToken(groupPart);
      splitTopLevelCommas(groupPart).forEach(addToken);
    });

    splitTopLevelCommas(rawWord).forEach(addToken);
  });

  return tokens;
}

function buildLegacyTagState(existingTags, allowStrengthAdjustment) {
  return existingTags.reduce((acc, tag) => {
    const parsed = parseSerializedText(tag.text);
    const key = parsed.text;
    if (!acc[key]) {
      acc[key] = [];
    }
    acc[key].push({
      active: tag.active,
      strength:
        allowStrengthAdjustment
          ? (tag.strength !== undefined && tag.strength !== null ? tag.strength : parsed.strength)
          : null,
    });
    return acc;
  }, {});
}

function buildGroupState(existingTags, allowStrengthAdjustment) {
  return existingTags.reduce((acc, tag) => {
    const parsed = parseSerializedText(tag.text);
    const key = parsed.text;
    if (!acc[key]) {
      acc[key] = [];
    }

    const itemState = {};
    if (Array.isArray(tag.items)) {
      tag.items.forEach((item) => {
        const itemKey = item.text;
        if (!itemState[itemKey]) {
          itemState[itemKey] = [];
        }
        itemState[itemKey].push({
          active: item.active,
        });
      });
    } else {
      splitTopLevelCommas(tag.text).forEach((itemText) => {
        if (!itemState[itemText]) {
          itemState[itemText] = [];
        }
        itemState[itemText].push({
          active: tag.active,
        });
      });
    }

    acc[key].push({
      active: tag.active,
      strength:
        allowStrengthAdjustment
          ? (tag.strength !== undefined && tag.strength !== null ? tag.strength : parsed.strength)
          : null,
      itemState,
    });
    return acc;
  }, {});
}

function consumeQueuedState(stateMap, key) {
  const queue = stateMap[key];
  if (queue && queue.length > 0) {
    return queue.shift();
  }
  return null;
}

app.registerExtension({
  name: "LoraManager.TriggerWordToggle",

  setup() {
    api.addEventListener("trigger_word_update", (event) => {
      const { id, graph_id: graphId, message } = event.detail;
      this.handleTriggerWordUpdate(id, graphId, message);
    });
  },

  async nodeCreated(node) {
    if (node.comfyClass !== "TriggerWord Toggle (LoraManager)") {
      return;
    }

    node.serialize_widgets = true;
    node.addInput("trigger_words", "string", {
      shape: 7,
    });

    requestAnimationFrame(async () => {
      const wheelSensitivity = getWheelSensitivity();
      const groupModeWidget = node.widgets[0];
      const defaultActiveWidget = node.widgets[1];
      const strengthAdjustmentWidget = node.widgets[2];
      const initialStrengthAdjustment = Boolean(strengthAdjustmentWidget?.value);

      const result = addTagsWidget(node, "toggle_trigger_words", {
        defaultVal: [],
      }, null, wheelSensitivity, {
        allowStrengthAdjustment: initialStrengthAdjustment,
      });

      node.tagWidget = result.widget;
      node.tagWidget.allowStrengthAdjustment = initialStrengthAdjustment;

      const applyHighlightState = () => {
        if (!node.tagWidget) {
          return;
        }

        const highlightSet = node._highlightedTriggerWords || new Set();
        const updatedTags = (node.tagWidget.value || []).map((tag) => {
          if (Array.isArray(tag.items)) {
            const items = tag.items.map((item) => ({
              ...item,
              highlighted: highlightSet.size > 0 && highlightSet.has(normalizeTagText(item.text)),
            }));

            return {
              ...tag,
              items,
              highlighted:
                highlightSet.size > 0 &&
                (highlightSet.has(normalizeTagText(tag.text)) ||
                  items.some((item) => item.highlighted)),
            };
          }

          return {
            ...tag,
            highlighted: highlightSet.size > 0 && highlightSet.has(normalizeTagText(tag.text)),
          };
        });

        node.tagWidget.value = updatedTags;
      };

      node.highlightTriggerWords = (triggerWords) => {
        const wordsArray = Array.isArray(triggerWords)
          ? triggerWords
          : triggerWords
            ? [triggerWords]
            : [];
        node._highlightedTriggerWords = collectHighlightTokens(wordsArray);
        applyHighlightState();
      };

      if (node.__pendingHighlightWords !== undefined) {
        const pending = node.__pendingHighlightWords;
        delete node.__pendingHighlightWords;
        node.highlightTriggerWords(pending);
      }

      node.applyTriggerHighlightState = applyHighlightState;

      const hiddenWidget = node.addWidget("text", "orinalMessage", "");
      hiddenWidget.type = CONVERTED_TYPE;
      hiddenWidget.hidden = true;
      hiddenWidget.computeSize = () => [0, -4];
      node.originalMessageWidget = hiddenWidget;

      const tagWidgetIndex = node.widgets.indexOf(result.widget);
      const originalMessageWidgetIndex = node.widgets.indexOf(hiddenWidget);
      if (node.widgets_values && node.widgets_values.length > 0) {
        if (tagWidgetIndex >= 0) {
          const savedValue = node.widgets_values[tagWidgetIndex];
          if (savedValue) {
            result.widget.value = Array.isArray(savedValue) ? savedValue : [];
          }
        }
        if (originalMessageWidgetIndex >= 0) {
          const originalMessage = node.widgets_values[originalMessageWidgetIndex];
          if (originalMessage) {
            hiddenWidget.value = originalMessage;
          }
        }
      }

      requestAnimationFrame(() => node.applyTriggerHighlightState?.());

      groupModeWidget.callback = (value) => {
        node.tagWidget?.closeGroupEditor?.();
        if (node.originalMessageWidget?.value) {
          this.updateTagsBasedOnMode(
            node,
            node.originalMessageWidget.value,
            value,
            Boolean(strengthAdjustmentWidget?.value)
          );
        }
      };

      defaultActiveWidget.callback = (value) => {
        if (!node.tagWidget || !node.tagWidget.value) {
          return;
        }

        const updatedTags = node.tagWidget.value.map((tag) => {
          if (!Array.isArray(tag.items)) {
            return {
              ...tag,
              active: value,
            };
          }

          return {
            ...tag,
            active: value,
            items: tag.items.map((item) => ({
              ...item,
              active: value,
            })),
          };
        });

        node.tagWidget.value = updatedTags;
        node.applyTriggerHighlightState?.();
      };

      if (strengthAdjustmentWidget) {
        strengthAdjustmentWidget.callback = (value) => {
          const allowStrengthAdjustment = Boolean(value);
          if (node.tagWidget) {
            node.tagWidget.allowStrengthAdjustment = allowStrengthAdjustment;
            node.tagWidget.closeGroupEditor?.();
          }
          this.updateTagsBasedOnMode(
            node,
            node.originalMessageWidget?.value || "",
            groupModeWidget?.value ?? false,
            allowStrengthAdjustment
          );
        };
      }

      result.widget.serializeValue = function() {
        const value = this.value || [];
        return value.map((tag) => {
          if (Array.isArray(tag.items)) {
            return {
              ...tag,
              text:
                tag.strength !== undefined && tag.strength !== null
                  ? `(${tag.text}:${tag.strength.toFixed(2)})`
                  : tag.text,
              items: tag.items.map((item) => ({ ...item })),
            };
          }

          if (tag.strength !== undefined && tag.strength !== null) {
            return {
              ...tag,
              text: `(${tag.text}:${tag.strength.toFixed(2)})`,
            };
          }

          return tag;
        });
      };
    });
  },

  handleTriggerWordUpdate(id, graphId, message) {
    const node = getNodeFromGraph(graphId, id);
    if (!node || node.comfyClass !== "TriggerWord Toggle (LoraManager)") {
      console.warn("Node not found or not a TriggerWordToggle:", id);
      return;
    }

    if (node.originalMessageWidget) {
      node.originalMessageWidget.value = message;
    }

    if (node.tagWidget) {
      const groupMode = node.widgets[0] ? node.widgets[0].value : false;
      const allowStrengthAdjustment = Boolean(node.widgets[2]?.value);
      node.tagWidget.allowStrengthAdjustment = allowStrengthAdjustment;
      this.updateTagsBasedOnMode(node, message, groupMode, allowStrengthAdjustment);
    }
  },

  updateTagsBasedOnMode(node, message, groupMode, allowStrengthAdjustment = false) {
    if (!node.tagWidget) {
      return;
    }
    node.tagWidget.closeGroupEditor?.();
    node.tagWidget.allowStrengthAdjustment = allowStrengthAdjustment;

    const existingTags = (node.tagWidget.value || []).map(cloneTag);
    const defaultActive = node.widgets[1] ? node.widgets[1].value : true;
    let tagArray = [];

    if (groupMode) {
      const existingGroupState = buildGroupState(existingTags, allowStrengthAdjustment);
      const groups = message.trim()
        ? (message.includes(",,") ? message.split(/,{2,}/) : [message])
            .map((group) => group.trim())
            .filter(Boolean)
        : [];

      tagArray = groups.map((group) => {
        const existing = consumeQueuedState(existingGroupState, group);
        const itemState = existing?.itemState || {};
        const items = splitTopLevelCommas(group).map((itemText) => {
          const savedItem = consumeQueuedState(itemState, itemText);
          return {
            text: itemText,
            active: savedItem ? savedItem.active : defaultActive,
            highlighted: false,
            strength: null,
          };
        });

        return {
          text: group,
          active: existing ? existing.active : defaultActive,
          highlighted: false,
          strength: existing ? existing.strength : null,
          items,
        };
      });
    } else {
      const existingTagState = buildLegacyTagState(existingTags, allowStrengthAdjustment);
      tagArray = splitTopLevelCommas(message).map((word) => {
        const existing = consumeQueuedState(existingTagState, word);
        return {
          text: word,
          active: existing ? existing.active : defaultActive,
          highlighted: false,
          strength: existing ? existing.strength : null,
        };
      });
    }

    node.tagWidget.value = tagArray;
    node.applyTriggerHighlightState?.();
  },
});

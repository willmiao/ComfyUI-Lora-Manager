import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";
import { CONVERTED_TYPE, getNodeFromGraph } from "./utils.js";
import { addTagsWidget } from "./tags_widget.js";

// Setting ID for wheel sensitivity
const TRIGGER_WORD_WHEEL_SENSITIVITY_ID = "loramanager.trigger_word_wheel_sensitivity";
const TRIGGER_WORD_WHEEL_SENSITIVITY_DEFAULT = 0.02;

// Get the wheel sensitivity setting value
const getWheelSensitivity = (() => {
    let settingsUnavailableLogged = false;

    return () => {
        const settingManager = app?.extensionManager?.setting;
        if (!settingManager || typeof settingManager.get !== "function") {
            if (!settingsUnavailableLogged) {
                console.warn("LoRA Manager: settings API unavailable, using default wheel sensitivity.");
                settingsUnavailableLogged = true;
            }
            return TRIGGER_WORD_WHEEL_SENSITIVITY_DEFAULT;
        }

        try {
            const value = settingManager.get(TRIGGER_WORD_WHEEL_SENSITIVITY_ID);
            return value ?? TRIGGER_WORD_WHEEL_SENSITIVITY_DEFAULT;
        } catch (error) {
            if (!settingsUnavailableLogged) {
                console.warn("LoRA Manager: unable to read wheel sensitivity setting, using default.", error);
                settingsUnavailableLogged = true;
            }
            return TRIGGER_WORD_WHEEL_SENSITIVITY_DEFAULT;
        }
    };
})();

// TriggerWordToggle extension for ComfyUI
app.registerExtension({
    name: "LoraManager.TriggerWordToggle",
    
    settings: [
        {
            id: TRIGGER_WORD_WHEEL_SENSITIVITY_ID,
            name: "Trigger Word Wheel Sensitivity",
            type: "slider",
            attrs: {
                min: 0.01,
                max: 0.1,
                step: 0.01,
            },
            defaultValue: TRIGGER_WORD_WHEEL_SENSITIVITY_DEFAULT,
            tooltip: "Mouse wheel sensitivity for adjusting trigger word strength (default: 0.02)",
            category: ["LoRA Manager", "Trigger Word Toggle", "Wheel Sensitivity"],
        },
    ],
    
    setup() {
        // Add message handler to listen for messages from Python
        api.addEventListener("trigger_word_update", (event) => {
            const { id, graph_id: graphId, message } = event.detail;
            this.handleTriggerWordUpdate(id, graphId, message);
        });
    },
    
    async nodeCreated(node) {
        if (node.comfyClass === "TriggerWord Toggle (LoraManager)") {
            // Enable widget serialization
            node.serialize_widgets = true;
            
            node.addInput("trigger_words", 'string', {
                "shape": 7  // 7 is the shape of the optional input
            });

            // Wait for node to be properly initialized
            requestAnimationFrame(async () => {
                // Get the wheel sensitivity setting
                const wheelSensitivity = getWheelSensitivity();
                const groupModeWidget = node.widgets[0];
                const defaultActiveWidget = node.widgets[1];
                const strengthAdjustmentWidget = node.widgets[2];
                const initialStrengthAdjustment = Boolean(strengthAdjustmentWidget?.value);
                
                // Get the widget object directly from the returned object
                const result = addTagsWidget(node, "toggle_trigger_words", {
                    defaultVal: []
                }, null, wheelSensitivity, {
                    allowStrengthAdjustment: initialStrengthAdjustment
                });
                
                node.tagWidget = result.widget;
                node.tagWidget.allowStrengthAdjustment = initialStrengthAdjustment;

                const normalizeTagText = (text) =>
                    (typeof text === 'string' ? text.trim().toLowerCase() : '');

                const collectHighlightTokens = (wordsArray) => {
                    const tokens = new Set();

                    const addToken = (text) => {
                        const normalized = normalizeTagText(text);
                        if (normalized) {
                            tokens.add(normalized);
                        }
                    };

                    wordsArray.forEach((rawWord) => {
                        if (typeof rawWord !== 'string') {
                            return;
                        }

                        addToken(rawWord);

                        const groupParts = rawWord.split(/,{2,}/);
                        groupParts.forEach((groupPart) => {
                            addToken(groupPart);
                            groupPart.split(',').forEach(addToken);
                        });

                        rawWord.split(',').forEach(addToken);
                    });

                    return tokens;
                };

                const applyHighlightState = () => {
                    if (!node.tagWidget) return;
                    const highlightSet = node._highlightedTriggerWords || new Set();
                    const updatedTags = (node.tagWidget.value || []).map(tag => ({
                        ...tag,
                        highlighted: highlightSet.size > 0 && highlightSet.has(normalizeTagText(tag.text))
                    }));
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

                // Add hidden widget to store original message
                const hiddenWidget = node.addWidget('text', 'orinalMessage', '');
                hiddenWidget.type = CONVERTED_TYPE;
                hiddenWidget.hidden = true;
                hiddenWidget.computeSize = () => [0, -4];
                node.originalMessageWidget = hiddenWidget;

                // Restore saved value if exists
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
                    if (node.originalMessageWidget?.value) {
                        this.updateTagsBasedOnMode(
                            node,
                            node.originalMessageWidget.value,
                            value,
                            Boolean(strengthAdjustmentWidget?.value)
                        );
                    }
                }

                // Add callback for default_active widget
                defaultActiveWidget.callback = (value) => {
                    // Set all existing tags' active state to the new value
                    if (node.tagWidget && node.tagWidget.value) {
                        const updatedTags = node.tagWidget.value.map(tag => ({
                            ...tag,
                            active: value
                        }));
                        node.tagWidget.value = updatedTags;
                        node.applyTriggerHighlightState?.();
                    }
                }
                
                if (strengthAdjustmentWidget) {
                    strengthAdjustmentWidget.callback = (value) => {
                        const allowStrengthAdjustment = Boolean(value);
                        if (node.tagWidget) {
                            node.tagWidget.allowStrengthAdjustment = allowStrengthAdjustment;
                        }
                        this.updateTagsBasedOnMode(
                            node,
                            node.originalMessageWidget?.value || "",
                            groupModeWidget?.value ?? false,
                            allowStrengthAdjustment
                        );
                    };
                }
                
                // Override the serializeValue method to properly format trigger words with strength
                const originalSerializeValue = result.widget.serializeValue;
                result.widget.serializeValue = function() {
                    const value = this.value || [];
                    // Transform the values to include strength in the proper format
                    const transformedValue = value.map(tag => {
                        // If strength is defined (even if it's 1.0), format as {text: "(original_text:strength)", ...}
                        if (tag.strength !== undefined && tag.strength !== null) {
                            return {
                                ...tag,
                                text: `(${tag.text}:${tag.strength.toFixed(2)})`
                            };
                        }
                        return tag;
                    });
                    return transformedValue;
                };
            });
        }
    },

    // Handle trigger word updates from Python
    handleTriggerWordUpdate(id, graphId, message) {
        const node = getNodeFromGraph(graphId, id);
        if (!node || node.comfyClass !== "TriggerWord Toggle (LoraManager)") {
            console.warn("Node not found or not a TriggerWordToggle:", id);
            return;
        }
        
        // Store the original message for mode switching
        if (node.originalMessageWidget) {
            node.originalMessageWidget.value = message;
        }

        if (node.tagWidget) {
            // Parse tags based on current group mode
            const groupMode = node.widgets[0] ? node.widgets[0].value : false;
            const allowStrengthAdjustment = Boolean(node.widgets[2]?.value);
            node.tagWidget.allowStrengthAdjustment = allowStrengthAdjustment;
            this.updateTagsBasedOnMode(node, message, groupMode, allowStrengthAdjustment);
        }
    },
    
    // Update tags display based on group mode
  updateTagsBasedOnMode(node, message, groupMode, allowStrengthAdjustment = false) {
    if (!node.tagWidget) return;
    node.tagWidget.allowStrengthAdjustment = allowStrengthAdjustment;
    
    const existingTags = node.tagWidget.value || [];
    const existingTagState = existingTags.reduce((acc, tag) => {
      const key = tag.text;
      if (!acc[key]) {
        acc[key] = [];
      }
      acc[key].push({
        active: tag.active,
        strength: allowStrengthAdjustment ? tag.strength : null,
      });
      return acc;
    }, {});
    const consumeExistingState = (text) => {
      const states = existingTagState[text];
      if (states && states.length > 0) {
        return states.shift();
      }
      return null;
    };
    
    // Get default active state from the widget
    const defaultActive = node.widgets[1] ? node.widgets[1].value : true;
    
    let tagArray = [];
    
    if (groupMode) {
      if (message.trim() === '') {
        tagArray = [];
      }
      // Group mode: split by ',,' and treat each group as a single tag
      else if (message.includes(',,')) {
        const groups = message.split(/,{2,}/); // Match 2 or more consecutive commas
        tagArray = groups
          .map(group => group.trim())
          .filter(group => group)
          .map(group => {
            // Check if this group already exists with strength info
            const existing = consumeExistingState(group);
            return {
              text: group,
              // Use existing values if available, otherwise use defaults
              active: existing ? existing.active : defaultActive,
              strength: existing ? existing.strength : null
            };
          });
      } else {
        // If no ',,' delimiter, treat the entire message as one group
        const existing = consumeExistingState(message.trim());
        tagArray = [{
          text: message.trim(),
          // Use existing values if available, otherwise use defaults
          active: existing ? existing.active : defaultActive,
          strength: existing ? existing.strength : null
        }];
      }
    } else {
      // Normal mode: split by commas and treat each word as a separate tag
      tagArray = message
        .split(',')
        .map(word => word.trim())
          .filter(word => word)
          .map(word => {
            // Check if this word already exists with strength info
            const existing = consumeExistingState(word);
            return {
              text: word,
              // Use existing values if available, otherwise use defaults
              active: existing ? existing.active : defaultActive,
              strength: existing ? existing.strength : null
            };
        });
    }
    
    node.tagWidget.value = tagArray;
    node.applyTriggerHighlightState?.();
  }
});

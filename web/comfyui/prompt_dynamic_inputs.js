import { app } from "../../scripts/app.js";
import {
    PROMPT_TAG_AUTOCOMPLETE_SETTING_ID,
    getPromptTagAutocompletePreference,
    setLoraManagerSettingValue,
} from "./settings.js";
import { showToast } from "./utils.js";

/**
 * Extension for PromptLM node to support dynamic trigger_words inputs.
 * Based on the dynamic input pattern from Impact Pack's Switch (Any) node.
 *
 * Slot names are `trigger_words1..n` and the node always keeps exactly one
 * empty slot after the connected ones, so there is somewhere to drop the next
 * link. Two rules keep that layout from breaking on load:
 *
 * 1. Never rename, add or remove a slot while the graph is configuring.
 *    Since frontend 1.16 the loader rebuilds `node.inputs` from the node
 *    definition (so `seed` can be inserted in the middle) and then repairs
 *    every link target *by slot name* (`realignInputLinkSlots`). Renaming a
 *    slot during that pass makes the repair miss, and the link keeps the
 *    `target_slot` it was saved with - which by then addresses another slot
 *    (e.g. the `text` widget input).
 * 2. Legacy workflows (saved with a bare `trigger_words` slot, before the
 *    definition had `seed` / `trigger_words1`) are normalized once the graph
 *    has finished loading, when link targets are consistent again.
 */

const PROMPT_NODE_TYPE = "Prompt (LoraManager)";
// Legacy files use the bare `trigger_words` name for the first slot.
const TRIGGER_INPUT_PATTERN = /^trigger_words\d*$/;
const TRIGGER_INPUT_TOOLTIP =
    "Trigger words to prepend. Connect to add more inputs.";

function isTriggerInput(input) {
    return Boolean(input) && TRIGGER_INPUT_PATTERN.test(input.name ?? "");
}

function listTriggerInputs(node) {
    return (node.inputs ?? []).filter(isTriggerInput);
}

/**
 * Renumber trigger slots 1..n in layout order.
 *
 * Renaming never moves a slot, so link target slots stay valid. The stale
 * `localized_name` written by older workflows has to follow the name, though:
 * the label renderer prefers it over `name`.
 */
function renumberTriggerInputs(node) {
    let ordinal = 1;
    for (const input of node.inputs ?? []) {
        if (!isTriggerInput(input)) {
            continue;
        }
        const name = `trigger_words${ordinal}`;
        ordinal += 1;
        if (input.name === name) {
            continue;
        }
        input.name = name;
        if (input.localized_name) {
            input.localized_name = name;
        }
    }
    return ordinal - 1;
}

function addTriggerInput(node, ordinal) {
    return node.addInput(`trigger_words${ordinal}`, "STRING", {
        forceInput: true,
        tooltip: TRIGGER_INPUT_TOOLTIP,
    });
}

function removeTriggerInput(node, input) {
    const index = (node.inputs ?? []).indexOf(input);
    if (index === -1) {
        return false;
    }
    node.removeInput(index);
    return true;
}

/**
 * Whether removing an input also shifts the `target_slot` of the links behind
 * it. Frontends with the shared link store (ComfyUI >= 1.5) do; the oldest
 * ones restore the saved input order verbatim and do not, so they must not be
 * rebuilt.
 */
function supportsInputRebuild(node) {
    return typeof node.graph?.links?.get === "function";
}

/**
 * Bring a loaded node back to the canonical layout: connected trigger slots
 * first, exactly one empty slot after them.
 */
function normalizeTriggerInputs(node) {
    const triggers = listTriggerInputs(node);
    if (!triggers.length) {
        addTriggerInput(node, 1);
        return;
    }

    const connectedCount = triggers.filter(
        (input) => input.link != null,
    ).length;
    const emptyCount = triggers.length - connectedCount;
    const trailingIsEmpty = triggers[triggers.length - 1].link == null;

    const canonical =
        connectedCount === 0
            ? triggers.length === 1
            : emptyCount === 1 && trailingIsEmpty;

    if (!canonical && supportsInputRebuild(node)) {
        // Empty slots carry no links, so dropping them is safe: the loader
        // moves every remaining link to its new slot index.
        for (const input of triggers) {
            if (input.link == null) {
                removeTriggerInput(node, input);
            }
        }
        if (!listTriggerInputs(node).length) {
            addTriggerInput(node, 1);
            return;
        }
    }

    const count = renumberTriggerInputs(node);
    if (listTriggerInputs(node).every((input) => input.link != null)) {
        // Every slot is connected - keep a free slot for the next link.
        addTriggerInput(node, count + 1);
    }
}

app.registerExtension({
    name: "Comfy.LoraManager.PromptLM",

    async beforeRegisterNodeDef(nodeType, nodeData, app) {
        if (nodeData.name !== PROMPT_NODE_TYPE) {
            return;
        }

        const onConnectionsChange = nodeType.prototype.onConnectionsChange;

        nodeType.prototype.onConnectionsChange = function(type, index, connected, link_info) {
            // The loader is rebuilding the graph: renaming or inserting slots
            // here would invalidate the name based link realignment that runs
            // right after `configure()`.
            if (app.configuringGraph) {
                return onConnectionsChange?.apply?.(this, arguments);
            }

            // Fallback for frontends without `app.configuringGraph`.
            const stackTrace = new Error().stack ?? "";

            // Skip during graph loading/pasting to avoid interference
            if (stackTrace.includes('loadGraphData') || stackTrace.includes('pasteFromClipboard')) {
                return onConnectionsChange?.apply?.(this, arguments);
            }

            // Skip subgraph operations
            if (stackTrace.includes('convertToSubgraph') || stackTrace.includes('Subgraph.configure')) {
                return onConnectionsChange?.apply?.(this, arguments);
            }

            if (!link_info) {
                return onConnectionsChange?.apply?.(this, arguments);
            }

            // Handle input connections (type === 1)
            if (type === 1) {
                const input = this.inputs?.[index];

                // Only process trigger_words inputs
                if (!isTriggerInput(input)) {
                    return onConnectionsChange?.apply?.(this, arguments);
                }

                try {
                    if (connected) {
                        // Connecting the last slot (or the only one) grows the list.
                        const triggers = listTriggerInputs(this);
                        if (triggers[triggers.length - 1] === input) {
                            const count = renumberTriggerInputs(this);
                            addTriggerInput(this, count + 1);
                        }
                    } else if (supportsInputRebuild(this)) {
                        // Drop the slot that was just disconnected unless it is
                        // the trailing empty slot.
                        const triggers = listTriggerInputs(this);
                        if (triggers.length > 1 && triggers[triggers.length - 1] !== input) {
                            removeTriggerInput(this, input);
                            renumberTriggerInputs(this);
                        }
                    }
                } catch (error) {
                    console.warn('[Lora Manager] Failed to update trigger word inputs:', error);
                }
            }

            return onConnectionsChange?.apply?.(this, arguments);
        };

        // Expose the tag autocomplete toggle in the node's right-click menu so
        // users can discover the switch where the behavior actually happens,
        // instead of only via slash commands or the global settings dialog.
        const getExtraMenuOptions = nodeType.prototype.getExtraMenuOptions;
        nodeType.prototype.getExtraMenuOptions = function(_, options) {
            getExtraMenuOptions?.apply?.(this, arguments);

            options.push(null);

            const autocompleteEnabled = getPromptTagAutocompletePreference();
            options.push({
                content: autocompleteEnabled
                    ? "Tag Autocomplete: ON (/noautocomplete to disable)"
                    : "Tag Autocomplete: OFF (/autocomplete to enable)",
                callback: async () => {
                    const newValue = !autocompleteEnabled;
                    try {
                        const success = await setLoraManagerSettingValue(PROMPT_TAG_AUTOCOMPLETE_SETTING_ID, newValue);
                        if (!success) {
                            throw new Error("settings API unavailable");
                        }
                        showToast({
                            severity: newValue ? 'success' : 'secondary',
                            summary: newValue ? 'Autocomplete Enabled' : 'Autocomplete Disabled',
                            detail: newValue
                                ? 'Tag autocomplete is now ON. Type to see suggestions.'
                                : 'Tag autocomplete is now OFF. Type /autocomplete in the prompt field to re-enable.',
                            life: 3000
                        });
                    } catch (error) {
                        console.error('[Lora Manager] Failed to toggle setting:', error);
                        showToast({
                            severity: 'error',
                            summary: 'Error',
                            detail: 'Failed to toggle autocomplete setting',
                            life: 3000
                        });
                    }
                }
            });
        };
    },

    nodeCreated(node, app) {
        if (node.comfyClass !== PROMPT_NODE_TYPE) {
            return;
        }

        // Ensure at least one trigger_words input exists on creation
        const hasTriggerWords = (node.inputs ?? []).some(inp => isTriggerInput(inp));
        if (!hasTriggerWords) {
            addTriggerInput(node, 1);
        }
    },

    loadedGraphNode(node) {
        if (node.comfyClass !== PROMPT_NODE_TYPE) {
            return;
        }

        // Runs after the graph has been configured, so links already point at
        // the right slots and migrating the layout cannot desync them.
        try {
            normalizeTriggerInputs(node);
        } catch (error) {
            console.warn('[Lora Manager] Failed to normalize trigger word inputs:', error);
        }
    }
});

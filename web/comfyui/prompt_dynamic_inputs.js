import { app } from "../../scripts/app.js";

/**
 * Extension for PromptLM node to support dynamic trigger_words inputs.
 * Based on the dynamic input pattern from Impact Pack's Switch (Any) node.
 */
app.registerExtension({
    name: "Comfy.LoraManager.PromptLM",

    async beforeRegisterNodeDef(nodeType, nodeData, app) {
        if (nodeData.name !== "Prompt (LoraManager)") {
            return;
        }

        const onConnectionsChange = nodeType.prototype.onConnectionsChange;
        
        nodeType.prototype.onConnectionsChange = function(type, index, connected, link_info) {
            const stackTrace = new Error().stack;
            
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
                const input = this.inputs[index];
                
                // Only process trigger_words inputs
                if (!input || !input.name.startsWith('trigger_words')) {
                    return onConnectionsChange?.apply?.(this, arguments);
                }

                // Count existing trigger_words inputs
                let triggerWordCount = 0;
                for (const inp of this.inputs) {
                    if (inp.name.startsWith('trigger_words')) {
                        triggerWordCount++;
                    }
                }

                // Renumber all trigger_words inputs sequentially
                let slotIndex = 1;
                for (const inp of this.inputs) {
                    if (inp.name.startsWith('trigger_words')) {
                        inp.name = `trigger_words${slotIndex}`;
                        slotIndex++;
                    }
                }

                // Add new input slot if connected and this was the last one
                if (connected) {
                    const lastTriggerIndex = triggerWordCount;
                    if (index === lastTriggerIndex || index === this.inputs.findIndex(i => i.name === `trigger_words${lastTriggerIndex}`)) {
                        this.addInput(`trigger_words${slotIndex}`, "STRING", { 
                            forceInput: true,
                            tooltip: "Trigger words to prepend. Connect to add more inputs."
                        });
                    }
                }

                // Remove disconnected empty input slots (but keep at least one)
                if (!connected && triggerWordCount > 1) {
                    // Check if this input is now empty and can be removed
                    const disconnectedInput = this.inputs[index];
                    if (disconnectedInput && disconnectedInput.name.startsWith('trigger_words')) {
                        // Only remove if it has no link and is not the last trigger_words input
                        const isLastTriggerSlot = index === this.inputs.findLastIndex(i => i.name.startsWith('trigger_words'));
                        if (!isLastTriggerSlot && !disconnectedInput.link) {
                            this.removeInput(index);
                            
                            // Renumber again after removal
                            let newSlotIndex = 1;
                            for (const inp of this.inputs) {
                                if (inp.name.startsWith('trigger_words')) {
                                    inp.name = `trigger_words${newSlotIndex}`;
                                    newSlotIndex++;
                                }
                            }
                        }
                    }
                }
            }

            return onConnectionsChange?.apply?.(this, arguments);
        };
    },

    nodeCreated(node, app) {
        if (node.comfyClass !== "Prompt (LoraManager)") {
            return;
        }

        // Ensure at least one trigger_words input exists on creation
        const hasTriggerWords = node.inputs.some(inp => inp.name.startsWith('trigger_words'));
        if (!hasTriggerWords) {
            node.addInput("trigger_words1", "STRING", { 
                forceInput: true,
                tooltip: "Trigger words to prepend. Connect to add more inputs."
            });
        }
    }
});

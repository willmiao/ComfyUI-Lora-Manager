import { app } from "../../scripts/app.js";

/**
 * Extension for LoraStackCombinerLM node to support dynamic lora_stack inputs.
 * Defaults to two inputs; connecting the last slot adds a new empty one, and
 * disconnecting a non-last slot removes it (at least two are always kept).
 * Based on the dynamic input pattern from Impact Pack's Switch (Any) node.
 */
const STACK_INPUT_PATTERN = /^lora_stack\d+$/;

app.registerExtension({
    name: "Comfy.LoraManager.LoraStackCombiner",

    async beforeRegisterNodeDef(nodeType, nodeData, app) {
        if (nodeData.name !== "Lora Stack Combiner (LoraManager)") {
            return;
        }

        const onConnectionsChange = nodeType.prototype.onConnectionsChange;
        
        nodeType.prototype.onConnectionsChange = function(type, index, connected, link_info) {
            // Skip while the graph is being (re)configured (load, paste, subgraph ops)
            if (app.configuringGraph) {
                return onConnectionsChange?.apply?.(this, arguments);
            }

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
                
                // Only process numbered lora_stack inputs (legacy a/b slots are left untouched)
                if (!input || !STACK_INPUT_PATTERN.test(input.name)) {
                    return onConnectionsChange?.apply?.(this, arguments);
                }

                // Count existing numbered lora_stack inputs
                let stackInputCount = 0;
                for (const inp of this.inputs) {
                    if (STACK_INPUT_PATTERN.test(inp.name)) {
                        stackInputCount++;
                    }
                }

                // Renumber all numbered lora_stack inputs sequentially
                let slotIndex = 1;
                for (const inp of this.inputs) {
                    if (STACK_INPUT_PATTERN.test(inp.name)) {
                        inp.name = `lora_stack${slotIndex}`;
                        slotIndex++;
                    }
                }

                // Add new input slot if connected and this was the last one
                if (connected) {
                    const lastStackIndex = stackInputCount;
                    if (index === lastStackIndex || index === this.inputs.findIndex(i => i.name === `lora_stack${lastStackIndex}`)) {
                        this.addInput(`lora_stack${slotIndex}`, "LORA_STACK", { 
                            tooltip: "A LoRA stack to combine. Connect to add more inputs."
                        });
                    }
                }

                // Remove disconnected input slots (but keep at least two).
                // LiteGraph fires this event only for slots that had a link, and
                // it has already cleared input.link by the time the event fires,
                // so the disconnected slot is always empty at this point.
                if (!connected && stackInputCount > 2) {
                    const disconnectedInput = this.inputs[index];
                    if (disconnectedInput && STACK_INPUT_PATTERN.test(disconnectedInput.name)) {
                        // Keep the last slot so there is always an empty slot to reconnect into
                        const isLastStackSlot = index === this.inputs.findLastIndex(i => STACK_INPUT_PATTERN.test(i.name));
                        if (!isLastStackSlot) {
                            this.removeInput(index);
                            
                            // Renumber again after removal
                            let newSlotIndex = 1;
                            for (const inp of this.inputs) {
                                if (STACK_INPUT_PATTERN.test(inp.name)) {
                                    inp.name = `lora_stack${newSlotIndex}`;
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
        if (node.comfyClass !== "Lora Stack Combiner (LoraManager)") {
            return;
        }

        // Leave legacy (a/b) workflows untouched
        const hasLegacyInputs = node.inputs.some(inp => inp.name === "lora_stack_a" || inp.name === "lora_stack_b");
        if (hasLegacyInputs) {
            return;
        }

        // Ensure at least two numbered lora_stack inputs exist on creation
        const stackInputCount = node.inputs.filter(inp => STACK_INPUT_PATTERN.test(inp.name)).length;
        for (let i = stackInputCount + 1; i <= 2; i++) {
            node.addInput(`lora_stack${i}`, "LORA_STACK", { 
                tooltip: "A LoRA stack to combine. Connect to add more inputs."
            });
        }
    }
});

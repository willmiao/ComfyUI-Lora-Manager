// ComfyUI extension to track model usage statistics
import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";
import { showToast } from "./utils.js";

// Define target nodes and their widget configurations
const PATH_CORRECTION_TARGETS = [
    { comfyClass: "CheckpointLoaderSimple", widgetName: "ckpt_name", modelType: "checkpoints" },
    { comfyClass: "Checkpoint Loader with Name (Image Saver)", widgetName: "ckpt_name", modelType: "checkpoints" },
    { comfyClass: "UNETLoader", widgetName: "unet_name", modelType: "checkpoints" },
    { comfyClass: "easy comfyLoader", widgetName: "ckpt_name", modelType: "checkpoints" },
    { comfyClass: "CheckpointLoader|pysssss", widgetName: "ckpt_name", modelType: "checkpoints" },
    { comfyClass: "Efficient Loader", widgetName: "ckpt_name", modelType: "checkpoints" },
    { comfyClass: "UnetLoaderGGUF", widgetName: "unet_name", modelType: "checkpoints" },
    { comfyClass: "UnetLoaderGGUFAdvanced", widgetName: "unet_name", modelType: "checkpoints" },
    { comfyClass: "LoraLoader", widgetName: "lora_name", modelType: "loras" },
    { comfyClass: "easy loraStack", widgetNamePattern: "lora_\\d+_name", modelType: "loras" }
];

// Register the extension
app.registerExtension({
    name: "LoraManager.UsageStats",
    
    setup() {
        // Listen for successful executions
        api.addEventListener("execution_success", ({ detail }) => {
            if (detail && detail.prompt_id) {
                this.updateUsageStats(detail.prompt_id);
            }
        });

        // Listen for registry refresh requests
        api.addEventListener("lora_registry_refresh", () => {
            this.refreshRegistry();
        });
    },
    
    async updateUsageStats(promptId) {
        try {
            // Call backend endpoint with the prompt_id
            const response = await fetch(`/api/lm/update-usage-stats`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ prompt_id: promptId }),
            });
            
            if (!response.ok) {
                console.warn("Failed to update usage statistics:", response.statusText);
            }
        } catch (error) {
            console.error("Error updating usage statistics:", error);
        }
    },

    async refreshRegistry() {
        try {
            // Get current workflow nodes
            const prompt = await app.graphToPrompt();
            const workflow = prompt.workflow;
            if (!workflow || !workflow.nodes) {
                console.warn("No workflow nodes found for registry refresh");
                return;
            }

            // Find all Lora nodes
            const loraNodes = [];
            for (const node of workflow.nodes.values()) {
                if (node.type === "Lora Loader (LoraManager)" || 
                    node.type === "Lora Stacker (LoraManager)" || 
                    node.type === "WanVideo Lora Select (LoraManager)") {
                    loraNodes.push({
                        node_id: node.id,
                        bgcolor: node.bgcolor || null,
                        title: node.title || node.type,
                        type: node.type
                    });
                }
            }

            const response = await fetch('/api/lm/register-nodes', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ nodes: loraNodes }),
            });

            if (!response.ok) {
                console.warn("Failed to register Lora nodes:", response.statusText);
            } else {
                console.log(`Successfully registered ${loraNodes.length} Lora nodes`);
            }
        } catch (error) {
            console.error("Error refreshing registry:", error);
        }
    },

    async loadedGraphNode(node) {
        // Check if this node type needs path correction
        const target = PATH_CORRECTION_TARGETS.find(t => t.comfyClass === node.comfyClass);
        if (!target) {
            return;
        }
        
        await this.correctNodePaths(node, target);
    },
    
    async correctNodePaths(node, target) {
        try {
            if (target.widgetNamePattern) {
                // Handle pattern-based widget names (like lora_1_name, lora_2_name, etc.)
                const pattern = new RegExp(target.widgetNamePattern);
                const widgetIndexes = [];
                
                if (node.widgets) {
                    node.widgets.forEach((widget, index) => {
                        if (pattern.test(widget.name)) {
                            widgetIndexes.push(index);
                        }
                    });
                }
                
                // Process each matching widget
                for (const widgetIndex of widgetIndexes) {
                    await this.correctWidgetPath(node, widgetIndex, target.modelType);
                }
            } else {
                // Handle single widget name
                if (node.widgets) {
                    const widgetIndex = node.widgets.findIndex(w => w.name === target.widgetName);
                    if (widgetIndex !== -1) {
                        await this.correctWidgetPath(node, widgetIndex, target.modelType);
                    }
                }
            }
        } catch (error) {
            console.error("Error correcting node paths:", error);
        }
    },
    
    async correctWidgetPath(node, widgetIndex, modelType) {
        if (!node.widgets_values || !node.widgets_values[widgetIndex]) {
            return;
        }
        
        const currentPath = node.widgets_values[widgetIndex];
        if (!currentPath || typeof currentPath !== 'string') {
            return;
        }
        
        // Extract filename from path (after last separator)
        const fileName = currentPath.split(/[/\\]/).pop();
        if (!fileName) {
            return;
        }
        
        try {
            // Search for current relative path
            const response = await api.fetchApi(`/lm/${modelType}/relative-paths?search=${encodeURIComponent(fileName)}&limit=2`);
            const data = await response.json();
            
            if (!data.success || !data.relative_paths || data.relative_paths.length === 0) {
                return;
            }
            
            const foundPaths = data.relative_paths;
            const firstPath = foundPaths[0];
            
            // Check if we need to update the path
            if (firstPath !== currentPath) {
                // Update the widget value
                // node.widgets_values[widgetIndex] = firstPath;
                node.widgets[widgetIndex].value = firstPath;
                
                if (foundPaths.length === 1) {
                    // Single match found - success
                    showToast({
                        severity: 'info',
                        summary: 'LoRA Manager Path Correction',
                        detail: `Updated path for ${fileName}: ${firstPath}`,
                        life: 5000
                    });
                } else {
                    // Multiple matches found - warning
                    showToast({
                        severity: 'warn',
                        summary: 'LoRA Manager Path Correction',
                        detail: `Multiple paths found for ${fileName}, using: ${firstPath}`,
                        life: 5000
                    });
                }
                
                // Mark node as modified
                if (node.setDirtyCanvas) {
                    node.setDirtyCanvas(true);
                }
            }
        } catch (error) {
            console.error(`Error correcting path for ${fileName}:`, error);
        }
    }
});

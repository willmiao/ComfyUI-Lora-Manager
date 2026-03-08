import { app } from "../../scripts/app.js";

// ============================================================================
// Setting IDs and Defaults
// ============================================================================

const TRIGGER_WORD_WHEEL_SENSITIVITY_ID = "loramanager.trigger_word_wheel_sensitivity";
const TRIGGER_WORD_WHEEL_SENSITIVITY_DEFAULT = 0.02;

const AUTO_PATH_CORRECTION_SETTING_ID = "loramanager.auto_path_correction";
const AUTO_PATH_CORRECTION_DEFAULT = true;

const PROMPT_TAG_AUTOCOMPLETE_SETTING_ID = "loramanager.prompt_tag_autocomplete";
const PROMPT_TAG_AUTOCOMPLETE_DEFAULT = true;

const TAG_SPACE_REPLACEMENT_SETTING_ID = "loramanager.tag_space_replacement";
const TAG_SPACE_REPLACEMENT_DEFAULT = false;

const USAGE_STATISTICS_SETTING_ID = "loramanager.usage_statistics";
const USAGE_STATISTICS_DEFAULT = true;

const NEW_TAB_TEMPLATE_ID = "loramanager.new_tab_template";
const NEW_TAB_TEMPLATE_DEFAULT = "Default";

const NEW_TAB_ZOOM_LEVEL = 0.8;

// ============================================================================
// Helper Functions
// ============================================================================

let workflowOptions = [NEW_TAB_TEMPLATE_DEFAULT];
let workflowOptionsFull = [{ value: "Default", label: "Default (Blank)", path: null }];
let workflowOptionsLoaded = false;

const loadWorkflowOptions = async () => {
    if (workflowOptionsLoaded) {
        return;
    }
    try {
        const response = await fetch("/api/lm/example-workflows");
        const data = await response.json();
        if (data.success && data.workflows) {
            workflowOptionsFull = data.workflows;
            workflowOptions = data.workflows.map((w) => w.label);
            workflowOptionsLoaded = true;
        }
    } catch (error) {
        console.warn("LoRA Manager: Failed to fetch workflow options", error);
    }
};

const getWorkflowOptions = () => {
    // Function may be called with or without parameters
    // Return the current workflow options array
    return workflowOptions;
};

const loadTemplateWorkflow = async (templateName) => {
    if (!templateName || templateName === NEW_TAB_TEMPLATE_DEFAULT) {
        return null;
    }
    try {
        const workflow = workflowOptionsFull.find((w) => w.label === templateName);
        if (workflow && workflow.value) {
            const workflowResponse = await fetch(
                `/api/lm/example-workflows/${encodeURIComponent(workflow.value)}`
            );
            const workflowData = await workflowResponse.json();
            if (workflowData.success && workflowData.workflow) {
                return workflowData.workflow;
            }
        }
    } catch (error) {
        console.error("LoRA Manager: Failed to load template workflow", error);
    }
    return null;
};

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

const getAutoPathCorrectionPreference = (() => {
    let settingsUnavailableLogged = false;

    return () => {
        const settingManager = app?.extensionManager?.setting;
        if (!settingManager || typeof settingManager.get !== "function") {
            if (!settingsUnavailableLogged) {
                console.warn("LoRA Manager: settings API unavailable, defaulting auto path correction to enabled.");
                settingsUnavailableLogged = true;
            }
            return AUTO_PATH_CORRECTION_DEFAULT;
        }

        try {
            const value = settingManager.get(AUTO_PATH_CORRECTION_SETTING_ID);
            return value ?? AUTO_PATH_CORRECTION_DEFAULT;
        } catch (error) {
            if (!settingsUnavailableLogged) {
                console.warn("LoRA Manager: unable to read auto path correction setting, defaulting to enabled.", error);
                settingsUnavailableLogged = true;
            }
            return AUTO_PATH_CORRECTION_DEFAULT;
        }
    };
})();

const getPromptTagAutocompletePreference = (() => {
    let settingsUnavailableLogged = false;

    return () => {
        const settingManager = app?.extensionManager?.setting;
        if (!settingManager || typeof settingManager.get !== "function") {
            if (!settingsUnavailableLogged) {
                console.warn("LoRA Manager: settings API unavailable, using default tag autocomplete setting.");
                settingsUnavailableLogged = true;
            }
            return PROMPT_TAG_AUTOCOMPLETE_DEFAULT;
        }

        try {
            const value = settingManager.get(PROMPT_TAG_AUTOCOMPLETE_SETTING_ID);
            return value ?? PROMPT_TAG_AUTOCOMPLETE_DEFAULT;
        } catch (error) {
            if (!settingsUnavailableLogged) {
                console.warn("LoRA Manager: unable to read tag autocomplete setting, using default.", error);
                settingsUnavailableLogged = true;
            }
            return PROMPT_TAG_AUTOCOMPLETE_DEFAULT;
        }
    };
})();

const getTagSpaceReplacementPreference = (() => {
    let settingsUnavailableLogged = false;

    return () => {
        const settingManager = app?.extensionManager?.setting;
        if (!settingManager || typeof settingManager.get !== "function") {
            if (!settingsUnavailableLogged) {
                console.warn("LoRA Manager: settings API unavailable, using default tag space replacement setting.");
                settingsUnavailableLogged = true;
            }
            return TAG_SPACE_REPLACEMENT_DEFAULT;
        }

        try {
            const value = settingManager.get(TAG_SPACE_REPLACEMENT_SETTING_ID);
            return value ?? TAG_SPACE_REPLACEMENT_DEFAULT;
        } catch (error) {
            if (!settingsUnavailableLogged) {
                console.warn("LoRA Manager: unable to read tag space replacement setting, using default.", error);
                settingsUnavailableLogged = true;
            }
            return TAG_SPACE_REPLACEMENT_DEFAULT;
        }
    };
})();

const getUsageStatisticsPreference = (() => {
    let settingsUnavailableLogged = false;

    return () => {
        const settingManager = app?.extensionManager?.setting;
        if (!settingManager || typeof settingManager.get !== "function") {
            if (!settingsUnavailableLogged) {
                console.warn("LoRA Manager: settings API unavailable, using default usage statistics setting.");
                settingsUnavailableLogged = true;
            }
            return USAGE_STATISTICS_DEFAULT;
        }

        try {
            const value = settingManager.get(USAGE_STATISTICS_SETTING_ID);
            return value ?? USAGE_STATISTICS_DEFAULT;
        } catch (error) {
            if (!settingsUnavailableLogged) {
                console.warn("LoRA Manager: unable to read usage statistics setting, using default.", error);
                settingsUnavailableLogged = true;
            }
            return USAGE_STATISTICS_DEFAULT;
        }
    };
})();

const getNewTabTemplatePreference = (() => {
    let settingsUnavailableLogged = false;

    return () => {
        const settingManager = app?.extensionManager?.setting;
        if (!settingManager || typeof settingManager.get !== "function") {
            if (!settingsUnavailableLogged) {
                console.warn("LoRA Manager: settings API unavailable, using default new tab template.");
                settingsUnavailableLogged = true;
            }
            return NEW_TAB_TEMPLATE_DEFAULT;
        }

        try {
            const value = settingManager.get(NEW_TAB_TEMPLATE_ID);
            return value ?? NEW_TAB_TEMPLATE_DEFAULT;
        } catch (error) {
            if (!settingsUnavailableLogged) {
                console.warn("LoRA Manager: unable to read new tab template setting, using default.", error);
                settingsUnavailableLogged = true;
            }
            return NEW_TAB_TEMPLATE_DEFAULT;
        }
    };
})();

// ============================================================================
// Register Extension with All Settings
// ============================================================================

app.registerExtension({
    name: "LoraManager.Settings",
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
        {
            id: AUTO_PATH_CORRECTION_SETTING_ID,
            name: "Auto path correction",
            type: "boolean",
            defaultValue: AUTO_PATH_CORRECTION_DEFAULT,
            tooltip: "Automatically update model paths to their current file locations.",
            category: ["LoRA Manager", "Automation", "Auto path correction"],
        },
        {
            id: PROMPT_TAG_AUTOCOMPLETE_SETTING_ID,
            name: "Enable Tag Autocomplete in Prompt Nodes",
            type: "boolean",
            defaultValue: PROMPT_TAG_AUTOCOMPLETE_DEFAULT,
            tooltip: "When enabled, typing will trigger tag autocomplete suggestions. Commands (e.g., /character, /artist) always work regardless of this setting.",
            category: ["LoRA Manager", "Autocomplete", "Prompt"],
        },
        {
            id: TAG_SPACE_REPLACEMENT_SETTING_ID,
            name: "Replace underscores with spaces in tags",
            type: "boolean",
            defaultValue: TAG_SPACE_REPLACEMENT_DEFAULT,
            tooltip: "When enabled, tag names with underscores will have them replaced with spaces when inserted (e.g., 'blonde_hair' becomes 'blonde hair').",
            category: ["LoRA Manager", "Autocomplete", "Tag Formatting"],
        },
        {
            id: USAGE_STATISTICS_SETTING_ID,
            name: "Enable usage statistics tracking",
            type: "boolean",
            defaultValue: USAGE_STATISTICS_DEFAULT,
            tooltip: "When enabled, LoRA Manager will track model usage statistics during workflow execution. Disabling this will prevent unnecessary disk writes.",
            category: ["LoRA Manager", "Statistics", "Usage Tracking"],
        },
        {
            id: NEW_TAB_TEMPLATE_ID,
            name: "New Tab Template Workflow",
            type: "combo",
            options: getWorkflowOptions,
            defaultValue: NEW_TAB_TEMPLATE_DEFAULT,
            tooltip: "Choose a template workflow to load when creating a new workflow tab. 'Default (Blank)' keeps ComfyUI's original blank workflow behavior.",
            category: ["LoRA Manager", "Workflow", "New Tab Template"],
        },
    ],
    async setup() {
        await loadWorkflowOptions();

        const originalNewBlankWorkflow = async () => {
            const blankGraph = {
                last_node_id: 0,
                last_link_id: 0,
                nodes: [],
                links: [],
                groups: [],
                config: {},
                extra: {},
                version: 0.4,
            };
            await app.loadGraphData(blankGraph);
        };

        const waitForCommandStore = async (maxWaitMs = 5000) => {
            const startTime = Date.now();
            while (Date.now() - startTime < maxWaitMs) {
                if (app.extensionManager?.command?.commands) {
                    return true;
                }
                await new Promise((resolve) => setTimeout(resolve, 100));
            }
            return false;
        };

        const patchCommand = async () => {
            const storeReady = await waitForCommandStore();
            if (!storeReady) {
                console.warn("LoRA Manager: Could not access command store to patch NewBlankWorkflow");
                return;
            }

            const commands = app.extensionManager.command.commands;
            for (const cmd of commands) {
                if (cmd.id === "Comfy.NewBlankWorkflow") {
                    const originalFunc = cmd.function;
                    cmd.function = async (metadata) => {
                        const templateName = getNewTabTemplatePreference();
                        
                        if (templateName && templateName !== NEW_TAB_TEMPLATE_DEFAULT) {
                            const workflowData = await loadTemplateWorkflow(templateName);
                            if (workflowData) {
                                // Override the workflow's saved view settings with our custom zoom
                                if (!workflowData.extra) {
                                    workflowData.extra = {};
                                }
                                if (!workflowData.extra.ds) {
                                    workflowData.extra.ds = { offset: [0, 0], scale: 1 };
                                }
                                workflowData.extra.ds.scale = NEW_TAB_ZOOM_LEVEL;
                                
                                await app.loadGraphData(workflowData);
                                return;
                            }
                        }
                        
                        await originalNewBlankWorkflow();
                    };
                    break;
                }
            }
        };

        patchCommand();
    },
});

// ============================================================================
// Exports
// ============================================================================

export {
    getWheelSensitivity,
    getAutoPathCorrectionPreference,
    getPromptTagAutocompletePreference,
    getTagSpaceReplacementPreference,
    getUsageStatisticsPreference,
    getNewTabTemplatePreference,
};

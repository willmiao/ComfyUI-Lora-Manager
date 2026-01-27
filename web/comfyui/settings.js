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

// ============================================================================
// Helper Functions
// ============================================================================

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
    ],
});

// ============================================================================
// Exports
// ============================================================================

export { getWheelSensitivity, getAutoPathCorrectionPreference, getPromptTagAutocompletePreference, getTagSpaceReplacementPreference };

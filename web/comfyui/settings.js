import { app } from "../../scripts/app.js";

// ============================================================================
// Setting IDs and Defaults
// ============================================================================

const TRIGGER_WORD_WHEEL_SENSITIVITY_ID = "loramanager.trigger_word_wheel_sensitivity";
const TRIGGER_WORD_WHEEL_SENSITIVITY_DEFAULT = 0.02;

const AUTO_PATH_CORRECTION_SETTING_ID = "loramanager.auto_path_correction";
const AUTO_PATH_CORRECTION_DEFAULT = true;

const PROMPT_CUSTOM_WORDS_AUTOCOMPLETE_SETTING_ID = "loramanager.prompt_custom_words_autocomplete";
const PROMPT_CUSTOM_WORDS_AUTOCOMPLETE_DEFAULT = true;

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

const getPromptCustomWordsAutocompletePreference = (() => {
    let settingsUnavailableLogged = false;

    return () => {
        const settingManager = app?.extensionManager?.setting;
        if (!settingManager || typeof settingManager.get !== "function") {
            if (!settingsUnavailableLogged) {
                console.warn("LoRA Manager: settings API unavailable, using default custom words autocomplete setting.");
                settingsUnavailableLogged = true;
            }
            return PROMPT_CUSTOM_WORDS_AUTOCOMPLETE_DEFAULT;
        }

        try {
            const value = settingManager.get(PROMPT_CUSTOM_WORDS_AUTOCOMPLETE_SETTING_ID);
            return value ?? PROMPT_CUSTOM_WORDS_AUTOCOMPLETE_DEFAULT;
        } catch (error) {
            if (!settingsUnavailableLogged) {
                console.warn("LoRA Manager: unable to read custom words autocomplete setting, using default.", error);
                settingsUnavailableLogged = true;
            }
            return PROMPT_CUSTOM_WORDS_AUTOCOMPLETE_DEFAULT;
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
            id: PROMPT_CUSTOM_WORDS_AUTOCOMPLETE_SETTING_ID,
            name: "Enable Custom Words Autocomplete in Prompt Nodes",
            type: "boolean",
            defaultValue: PROMPT_CUSTOM_WORDS_AUTOCOMPLETE_DEFAULT,
            tooltip: "When enabled, prompt nodes will autocomplete custom words. When disabled, only 'emb:' prefix will trigger embeddings autocomplete.",
            category: ["LoRA Manager", "Autocomplete", "Prompt"],
        },
    ],
});

// ============================================================================
// Exports
// ============================================================================

export { getWheelSensitivity, getAutoPathCorrectionPreference, getPromptCustomWordsAutocompletePreference };

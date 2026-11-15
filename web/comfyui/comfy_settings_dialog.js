import { app } from "../../scripts/app.js";

/**
 * Opens ComfyUI's settings dialog on the LoRA Manager category.
 *
 * The LoRA Manager preferences that change the canvas (widget accent,
 * autocomplete, strength step, node labels, new tab template, usage statistics)
 * are registered as ComfyUI settings, so they live in ComfyUI's settings dialog
 * rather than in the manager's own settings modal. The manager page reaches
 * this dialog through a postMessage bridge (see settings.js); the canvas can
 * call this module directly.
 *
 * Kept separate from settings.js so callers that only need to open the dialog
 * do not import a module that registers an extension at import time.
 */

const SETTINGS_DIALOG_COMMAND = "Comfy.ShowSettingsDialog";

// The nav id is the setting category's key, not its translated label, so this
// matches in every locale. Custom categories may be nested under a group.
const CATEGORY_SELECTOR =
  '[data-testid="settings-dialog"] [data-nav-id="LoRA Manager"], ' +
  '[data-testid="settings-dialog"] [data-nav-id$="/LoRA Manager"]';

const COMMAND_STORE_WAIT_MS = 5000;
const CATEGORY_SELECT_WAIT_MS = 2000;

const waitForCommandStore = async (maxWaitMs = COMMAND_STORE_WAIT_MS) => {
  const startTime = Date.now();
  while (Date.now() - startTime < maxWaitMs) {
    if (app.extensionManager?.command?.commands) {
      return true;
    }
    await new Promise((resolve) => setTimeout(resolve, 100));
  }
  return false;
};

/**
 * Clicks the LoRA Manager entry in the settings dialog navigation.
 * Returns false when the entry does not appear (older or redesigned frontend);
 * the dialog is then left on its default category.
 */
const selectLoraManagerSettings = async (maxWaitMs = CATEGORY_SELECT_WAIT_MS) => {
  const startTime = Date.now();
  while (Date.now() - startTime < maxWaitMs) {
    const navItem = document.querySelector(CATEGORY_SELECTOR);
    if (navItem) {
      navItem.click();
      return true;
    }
    await new Promise((resolve) => setTimeout(resolve, 50));
  }
  return false;
};

const warnCategoryMissing = () => {
  console.warn(
    "LoRA Manager: ComfyUI settings opened, but the LoRA Manager category was not found."
  );
};

export async function openComfyUISettingsDialog() {
  try {
    if (await waitForCommandStore()) {
      await app.extensionManager.command.execute(SETTINGS_DIALOG_COMMAND);
      if (!(await selectLoraManagerSettings())) {
        warnCategoryMissing();
      }
      return;
    }

    // Older frontends expose the dialog through app.ui.settings instead of
    // the command store.
    if (typeof app?.ui?.settings?.show === "function") {
      app.ui.settings.show();
      if (!(await selectLoraManagerSettings())) {
        warnCategoryMissing();
      }
      return;
    }

    console.warn("LoRA Manager: Could not access the ComfyUI settings dialog.");
  } catch (error) {
    console.warn("LoRA Manager: Failed to open the ComfyUI settings dialog.", error);
  }
}

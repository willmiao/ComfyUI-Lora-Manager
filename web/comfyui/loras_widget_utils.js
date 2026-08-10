import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";

// Mirrors the backend resolver (get_lora_info_absolute): a ".ckpt"/".pt"
// reference resolves to the same-named .safetensors file. The scanner only
// indexes .safetensors, but keeping these here lets legacy references match.
const LORA_FILE_EXTENSIONS = [".safetensors", ".ckpt", ".pt", ".bin"];

/**
 * Strip a known LoRA model extension from a name (case-insensitive).
 *
 * The two sides of the availability check differ:
 * - The collection side (cycler-list `file_name`) is stored extension-free
 *   (scanner convention), so stripping is a no-op there.
 * - The widget entry side comes from the autocomplete path, which returns
 *   on-disk relative paths WITH the extension (e.g.
 *   "Illustrious/lazyhand.safetensors"), so stripping is required to match.
 */
export function stripLoraExtension(name) {
  const lowered = String(name || "").toLowerCase();
  for (const ext of LORA_FILE_EXTENSIONS) {
    if (lowered.endsWith(ext)) {
      return name.slice(0, -ext.length);
    }
  }
  return name;
}

/**
 * Normalize a LoRA name for availability lookup: forward slashes and no
 * extension, mirroring the backend matching in get_lora_info_absolute.
 */
export function normalizeLoraNameKey(name) {
  return stripLoraExtension(String(name || "").replace(/\\/g, "/"));
}

/**
 * Build the lookup set of available LoRA names from relative paths like
 * "folder/lora.safetensors". Both the full path and the bare basename are
 * registered (extension stripped), matching how users can reference LoRAs.
 */
export function buildAvailableLoraSet(relativePaths) {
  const set = new Set();
  for (const p of relativePaths || []) {
    const normalized = normalizeLoraNameKey(p);
    if (!normalized) continue;
    set.add(normalized);
    const slash = normalized.lastIndexOf("/");
    if (slash >= 0) {
      set.add(normalized.slice(slash + 1));
    }
  }
  return set;
}

/**
 * Check whether a widget entry name is available locally.
 *
 * When the availability set is not loaded yet (null), every name is treated
 * as available so entries are never falsely flagged while the fetch is
 * pending. Absolute paths outside the library cannot be verified
 * client-side and are treated as available. A folder-qualified name that
 * does not match a stored path falls back to its basename, mirroring the
 * backend resolver (get_lora_info_absolute's basename fallback and the
 * legacy syntax format).
 */
export function isLoraNameAvailable(name, availableSet) {
  if (!availableSet) {
    return true;
  }
  const normalized = String(name || "").replace(/\\/g, "/");
  if (normalized.startsWith("/") || /^[A-Za-z]:\//.test(normalized)) {
    return true;
  }
  const key = normalizeLoraNameKey(name);
  if (availableSet.has(key)) {
    return true;
  }
  const slash = key.lastIndexOf("/");
  if (slash >= 0) {
    return availableSet.has(key.slice(slash + 1));
  }
  return false;
}

const AVAILABLE_LORAS_TTL_MS = 60000;
let availableLorasCache = null;
let availableLorasPromise = null;
let availabilityGeneration = 0;

async function refreshAvailableLoras() {
  const generation = availabilityGeneration;
  try {
    const response = await api.fetchApi("/lm/loras/cycler-list", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: "{}",
    });
    if (!response || !response.ok) {
      return null;
    }
    const data = await response.json();
    const paths = (data?.loras || [])
      .map((lora) => lora?.file_name)
      .filter(Boolean);
    const set = buildAvailableLoraSet(paths);
    if (generation !== availabilityGeneration) {
      // Stale response: the cache was invalidated while this fetch was in
      // flight, do not repopulate it with pre-change data.
      return null;
    }
    availableLorasCache = { set, at: Date.now() };
    return set;
  } catch (error) {
    console.warn("Failed to fetch available LoRAs:", error);
    return null;
  }
}

/**
 * Fetch the set of available LoRA names, cached with a TTL. Concurrent
 * callers share a single in-flight request. Resolves to null on failure.
 */
export function getAvailableLoras() {
  connectLibraryChangeSocket();
  if (
    availableLorasCache &&
    Date.now() - availableLorasCache.at < AVAILABLE_LORAS_TTL_MS
  ) {
    return Promise.resolve(availableLorasCache.set);
  }
  if (!availableLorasPromise) {
    availableLorasPromise = refreshAvailableLoras().finally(() => {
      availableLorasPromise = null;
    });
  }
  return availableLorasPromise;
}

/**
 * Synchronous snapshot of the cached availability set, or null when the
 * cache is not loaded (or expired).
 */
export function getAvailableLorasSync() {
  if (
    availableLorasCache &&
    Date.now() - availableLorasCache.at < AVAILABLE_LORAS_TTL_MS
  ) {
    return availableLorasCache.set;
  }
  return null;
}

/**
 * Drop the cached availability data (used by tests and by callers that need
 * a forced refresh of the local library state). In-flight fetches started
 * before the reset are invalidated via the generation counter.
 */
export function resetAvailableLorasCache() {
  availabilityGeneration += 1;
  availableLorasCache = null;
  availableLorasPromise = null;
}

// The Lora Manager UI and the ComfyUI graph page are separate pages; the
// backend broadcasts "models_changed" over its WebSocket when the local
// library changes (delete/rename/move/scan), so the graph page can
// invalidate its availability cache immediately instead of waiting for the
// TTL to expire.
const libraryChangeListeners = new Set();

/**
 * Register a callback fired whenever the local model library changes.
 * Returns an unsubscribe function.
 */
export function onLibraryChanged(callback) {
  libraryChangeListeners.add(callback);
  return () => {
    libraryChangeListeners.delete(callback);
  };
}

/**
 * Process a library-change WebSocket message. Exported for testability.
 */
export function handleLibraryChangeMessage(data) {
  if (!data || data.type !== "models_changed") {
    return;
  }
  resetAvailableLorasCache();
  for (const listener of libraryChangeListeners) {
    try {
      listener();
    } catch (error) {
      console.warn("Library change listener failed:", error);
    }
  }
}

const LIBRARY_WS_RECONNECT_MS = 30000;
let libraryWs = null;
let libraryWsRetryTimer = null;

function connectLibraryChangeSocket() {
  if (libraryWs || typeof WebSocket === "undefined") {
    return;
  }
  const protocol = window.location.protocol === "https:" ? "wss://" : "ws://";
  let ws;
  try {
    ws = new WebSocket(`${protocol}${window.location.host}/ws/fetch-progress`);
  } catch (error) {
    return;
  }
  libraryWs = ws;
  ws.onmessage = (event) => {
    try {
      handleLibraryChangeMessage(JSON.parse(event.data));
    } catch (error) {
      // Non-JSON messages from other broadcasters are ignored.
    }
  };
  ws.onclose = () => {
    libraryWs = null;
    if (libraryWsRetryTimer === null) {
      libraryWsRetryTimer = setTimeout(() => {
        libraryWsRetryTimer = null;
        connectLibraryChangeSocket();
      }, LIBRARY_WS_RECONNECT_MS);
    }
  };
  ws.onerror = () => {
    ws.close();
  };
}

/**
 * Ensure the library-change WebSocket is connected (idempotent). Called on
 * the first availability fetch; safe in environments without WebSocket.
 */
export function ensureLibraryChangeSocket() {
  connectLibraryChangeSocket();
}

// Parse LoRA entries from value
export function parseLoraValue(value) {
  if (!value) return [];
  return Array.isArray(value) ? value : [];
}

// Format LoRA data
export function formatLoraValue(loras) {
  return loras;
}

// Determine if clip entry should be shown - now based on expanded property or initial diff values
export function shouldShowClipEntry(loraData) {
  // If expanded property exists, use that
  if (loraData.hasOwnProperty('expanded')) {
    return loraData.expanded;
  }
  // Otherwise use the legacy logic - if values differ, it should be expanded
  return Number(loraData.strength) !== Number(loraData.clipStrength);
}

// Helper function to sync clipStrength with strength when collapsed
export function syncClipStrengthIfCollapsed(loraData) {
  // If not expanded (collapsed), sync clipStrength with strength
  if (loraData.hasOwnProperty('expanded') && !loraData.expanded) {
    loraData.clipStrength = loraData.strength;
  }
  return loraData;
}

// Function to directly save the recipe without dialog
export async function saveRecipeDirectly() {
  try {
    const prompt = await app.graphToPrompt();
    console.log('Prompt:', prompt); // for debugging purposes
    // Show loading toast
    if (app && app.extensionManager && app.extensionManager.toast) {
      app.extensionManager.toast.add({
        severity: 'info',
        summary: 'Saving Recipe',
        detail: 'Please wait...',
        life: 2000
      });
    }
    
    // Send the request to the backend API
    const response = await fetch('/api/lm/recipes/save-from-widget', {
      method: 'POST'
    });
    
    const result = await response.json();
    
    // Show result toast
    if (app && app.extensionManager && app.extensionManager.toast) {
      if (result.success) {
        app.extensionManager.toast.add({
          severity: 'success',
          summary: 'Recipe Saved',
          detail: 'Recipe has been saved successfully',
          life: 3000
        });
      } else {
        app.extensionManager.toast.add({
          severity: 'error',
          summary: 'Error',
          detail: result.error || 'Failed to save recipe',
          life: 5000
        });
      }
    }
  } catch (error) {
    console.error('Error saving recipe:', error);
    
    // Show error toast
    if (app && app.extensionManager && app.extensionManager.toast) {
      app.extensionManager.toast.add({
        severity: 'error',
        summary: 'Error',
        detail: 'Failed to save recipe: ' + (error.message || 'Unknown error'),
        life: 5000
      });
    }
  }
}

/**
 * Utility function to copy text to clipboard with fallback for older browsers
 * @param {string} text - The text to copy to clipboard
 * @param {string} successMessage - Optional success message to show in toast
 * @returns {Promise<boolean>} - Promise that resolves to true if copy was successful
 */
export async function copyToClipboard(text, successMessage = 'Copied to clipboard') {
    try {
        // Modern clipboard API
        if (navigator.clipboard && window.isSecureContext) {
            await navigator.clipboard.writeText(text);
        } else {
            // Fallback for older browsers
            const textarea = document.createElement('textarea');
            textarea.value = text;
            textarea.style.position = 'absolute';
            textarea.style.left = '-99999px';
            document.body.appendChild(textarea);
            textarea.select();
            document.execCommand('copy');
            document.body.removeChild(textarea);
        }
        
        if (successMessage) {
            showToast(successMessage, 'success');
        }
        return true;
    } catch (err) {
        console.error('Copy failed:', err);
        showToast('Copy failed', 'error');
        return false;
    }
}

/**
 * Show a toast notification
 * @param {string} message - The message to display
 * @param {string} type - The type of toast (success, error, info, warning)
 */
export function showToast(message, type = 'info') {
    if (app && app.extensionManager && app.extensionManager.toast) {
        app.extensionManager.toast.add({
            severity: type,
            summary: type.charAt(0).toUpperCase() + type.slice(1),
            detail: message,
            life: 3000
        });
    } else {
        console.log(`${type.toUpperCase()}: ${message}`);
        // Fallback alert for critical errors only
        if (type === 'error') {
            alert(message);
        }
    }
}

/**
 * Move a LoRA to a new position in the array
 * @param {Array} loras - Array of LoRA objects
 * @param {number} fromIndex - Current index of the LoRA
 * @param {number} toIndex - Target index for the LoRA
 * @returns {Array} - New array with LoRA moved
 */
export function moveLoraInArray(loras, fromIndex, toIndex) {
  const newLoras = [...loras];
  const [removed] = newLoras.splice(fromIndex, 1);
  newLoras.splice(toIndex, 0, removed);
  return newLoras;
}

/**
 * Move a LoRA by name to a specific position
 * @param {Array} loras - Array of LoRA objects
 * @param {string} loraName - Name of the LoRA to move
 * @param {string} direction - 'up', 'down', 'top', 'bottom'
 * @returns {Array} - New array with LoRA moved
 */
export function moveLoraByDirection(loras, loraName, direction) {
  const currentIndex = loras.findIndex(l => l.name === loraName);
  if (currentIndex === -1) return loras;
  
  let newIndex;
  switch (direction) {
    case 'up':
      newIndex = Math.max(0, currentIndex - 1);
      break;
    case 'down':
      newIndex = Math.min(loras.length - 1, currentIndex + 1);
      break;
    case 'top':
      newIndex = 0;
      break;
    case 'bottom':
      newIndex = loras.length - 1;
      break;
    default:
      return loras;
  }
  
  if (newIndex === currentIndex) return loras;
  return moveLoraInArray(loras, currentIndex, newIndex);
}

/**
 * Get the drop target index based on mouse position
 * @param {HTMLElement} container - The container element
 * @param {number} clientY - Mouse Y position
 * @returns {number} - Target index for dropping
 */
export function getDropTargetIndex(container, clientY) {
  const entries = container.querySelectorAll('.lm-lora-entry');
  let targetIndex = entries.length;
  
  for (let i = 0; i < entries.length; i++) {
    const rect = entries[i].getBoundingClientRect();
    if (clientY < rect.top + rect.height / 2) {
      targetIndex = i;
      break;
    }
  }
  
  return targetIndex;
}

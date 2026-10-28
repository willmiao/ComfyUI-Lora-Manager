/**
 * Write-back of the current ComfyUI graph into a LoRA Manager managed
 * workflow ("Update LM-managed workflow").
 *
 * Correspondence: when LoRA Manager pushes a library workflow into ComfyUI
 * ("Open in ComfyUI"), workflow_registry.js stamps the provenance marker
 * `extra.lm_source = { file_path, sha256 }` onto the loaded graph. The marker
 * rides the graph serialization, so it survives tab switches and browser
 * reloads together with the workflow draft. Entry points below are only
 * usable while the active graph carries that marker.
 *
 * Entry points:
 *  - A command (`LoraManager.UpdateManagedWorkflow`), reachable from the
 *    command palette and the top menu bar (File group).
 *  - An item injected into the workflow actions dropdown (the "Graph ▾"
 *    toggle menu). The frontend offers no extension API for that menu, so
 *    the item is appended via DOM observation of the menu's trigger; if the
 *    markup changes upstream the injection silently stops and the command
 *    remains as the fallback.
 */
import { app } from "../../scripts/app.js";
import { lmUrl } from "./base_path.js";
import { showToast } from "./utils.js";

const MARKER_KEY = "lm_source";
const COMMAND_ID = "LoraManager.UpdateManagedWorkflow";
const MENU_LABEL = "Update LM-managed workflow";
const MENU_ICON = "pi pi-upload";
// data-testid of the workflow actions dropdown trigger in ComfyUI_frontend
// (WorkflowActionsDropdown.vue).
const DROPDOWN_TRIGGER_TESTID = "view-mode-toggle";

function getRootGraph() {
    return app.rootGraph ?? app.graph ?? null;
}

/**
 * The provenance marker of the active graph, or null when the open workflow
 * was not loaded from the LoRA Manager library.
 */
export function getActiveLmSource() {
    const marker = getRootGraph()?.extra?.[MARKER_KEY];
    if (!marker || typeof marker.file_path !== "string" || !marker.file_path) {
        return null;
    }
    return marker;
}

/**
 * Serialize the current graph without the LM provenance marker: the marker
 * is client-side bookkeeping and must not be persisted into the library
 * document (the backend strips it too, defense in depth).
 */
function serializeWorkflowForWriteback() {
    const graph = getRootGraph();
    const data = JSON.parse(JSON.stringify(graph.serialize()));
    if (data.extra && typeof data.extra === "object") {
        delete data.extra[MARKER_KEY];
    }
    return data;
}

async function requestWriteback(marker, { force = false } = {}) {
    const response = await fetch(lmUrl("/api/lm/workflows/content"), {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
            file_path: marker.file_path,
            workflow: serializeWorkflowForWriteback(),
            base_sha256: marker.sha256 || "",
            force,
        }),
    });
    let payload = null;
    try {
        payload = await response.json();
    } catch (_error) {
        payload = null;
    }
    return { status: response.status, payload };
}

/**
 * Write the active graph back into its LoRA Manager managed workflow
 * document. No-op (with a warning toast) when the graph carries no marker.
 */
export async function updateManagedWorkflow() {
    const marker = getActiveLmSource();
    if (!marker) {
        showToast({
            severity: "warn",
            summary: "LoRA Manager",
            detail: "This workflow is not linked to the LoRA Manager library. Open it via LoRA Manager first.",
            life: 5000,
        });
        return;
    }

    try {
        let result = await requestWriteback(marker);
        if (result.status === 409) {
            const overwrite = window.confirm(
                "The library copy of this workflow has changed since it was opened.\n" +
                "Overwrite the LoRA Manager copy with the current graph?"
            );
            if (!overwrite) {
                return;
            }
            result = await requestWriteback(marker, { force: true });
        }

        if (result.payload?.success) {
            if (result.payload.sha256) {
                marker.sha256 = result.payload.sha256;
            }
            showToast({
                severity: "success",
                summary: "LoRA Manager",
                detail: "Workflow updated in the LoRA Manager library.",
                life: 3000,
            });
        } else {
            showToast({
                severity: "error",
                summary: "LoRA Manager",
                detail: result.payload?.error || "Failed to update the managed workflow.",
                life: 5000,
            });
        }
    } catch (error) {
        console.error("LoRA Manager: workflow write-back failed", error);
        showToast({
            severity: "error",
            summary: "LoRA Manager",
            detail: `Failed to update the managed workflow: ${error.message}`,
            life: 5000,
        });
    }
}

// ---------------------------------------------------------------------------
// Workflow actions dropdown injection
// ---------------------------------------------------------------------------

const ITEM_CLASSES =
    "flex min-h-6 items-center gap-2 self-stretch rounded-sm p-2 outline-none";
const ITEM_ACTIVE_CLASSES = "cursor-pointer hover:bg-secondary-background-hover";
const ITEM_DISABLED_CLASSES = "cursor-default opacity-50";
const SEPARATOR_CLASSES = "my-1 w-full border-b border-border-subtle";

function buildMenuItem() {
    const linked = getActiveLmSource() !== null;

    const separator = document.createElement("div");
    separator.className = SEPARATOR_CLASSES;
    separator.setAttribute("role", "separator");

    const item = document.createElement("div");
    item.setAttribute("role", "menuitem");
    item.className = `${ITEM_CLASSES} ${linked ? ITEM_ACTIVE_CLASSES : ITEM_DISABLED_CLASSES}`;
    if (!linked) {
        item.setAttribute("aria-disabled", "true");
        item.title = "Only available for workflows opened from LoRA Manager";
    }

    const icon = document.createElement("i");
    icon.className = MENU_ICON;
    const label = document.createElement("span");
    label.className = "flex-1";
    label.textContent = MENU_LABEL;
    item.append(icon, label);

    if (linked) {
        item.addEventListener("click", () => {
            // Our node is not a reka-ui DropdownMenuItem, so the menu does not
            // close on its own — close it the way Escape would.
            const menu = item.closest('[role="menu"]');
            (menu ?? document).dispatchEvent(
                new KeyboardEvent("keydown", { key: "Escape", bubbles: true })
            );
            updateManagedWorkflow();
        });
    }

    return [separator, item];
}

/**
 * Append the write-back item to an open workflow actions menu, once per
 * menu instance (the portal remounts on every open).
 */
function injectIntoMenu(menuElement) {
    if (menuElement.dataset.lmWritebackInjected) {
        return;
    }
    menuElement.dataset.lmWritebackInjected = "1";
    for (const node of buildMenuItem()) {
        menuElement.appendChild(node);
    }
}

function findOpenWorkflowMenu() {
    // The workflow actions menu is the reka-ui dropdown containing the
    // core items (pencil = Rename, save = Save, download = Export); icon
    // classes are locale-independent.
    for (const menu of document.querySelectorAll('[role="menu"]')) {
        if (
            menu.querySelector(".pi-pencil") &&
            menu.querySelector(".pi-save") &&
            menu.querySelector(".pi-download")
        ) {
            return menu;
        }
    }
    return null;
}

function installDropdownInjection() {
    let pollTimer = null;
    const scheduleInjection = () => {
        if (pollTimer != null) {
            clearTimeout(pollTimer);
        }
        // The portal mounts asynchronously after the trigger click; poll
        // briefly instead of assuming a fixed delay.
        let attempts = 0;
        const poll = () => {
            pollTimer = null;
            const menu = findOpenWorkflowMenu();
            if (menu) {
                injectIntoMenu(menu);
                return;
            }
            attempts += 1;
            if (attempts < 10) {
                pollTimer = setTimeout(poll, 50);
            }
        };
        pollTimer = setTimeout(poll, 0);
    };

    // The trigger itself mounts late (frontend boot) and can remount on mode
    // switches, so observe its appearance and hook clicks on it.
    const hookTrigger = () => {
        const trigger = document.querySelector(`[data-testid="${DROPDOWN_TRIGGER_TESTID}"]`);
        if (trigger && !trigger.dataset.lmWritebackHooked) {
            trigger.dataset.lmWritebackHooked = "1";
            trigger.addEventListener("click", scheduleInjection);
        }
    };

    const observer = new MutationObserver(() => hookTrigger());
    observer.observe(document.body, { childList: true, subtree: true });
    hookTrigger();
}

app.registerExtension({
    name: "LoraManager.WorkflowWriteback",

    commands: [
        {
            id: COMMAND_ID,
            label: MENU_LABEL,
            menubarLabel: MENU_LABEL,
            icon: MENU_ICON,
            function: () => updateManagedWorkflow(),
        },
    ],

    menuCommands: [{ path: ["File"], commands: [COMMAND_ID] }],

    setup() {
        try {
            installDropdownInjection();
        } catch (error) {
            console.warn("LoRA Manager: workflow dropdown injection unavailable", error);
        }
    },
});

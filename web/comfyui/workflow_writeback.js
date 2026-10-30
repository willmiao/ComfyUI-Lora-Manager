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
 * Dirty tracking: the first `graphChanged` event after a load/write-back
 * flips `marker.dirty` (persisted inside the marker, so reloads keep it).
 * `graphChanged` is dispatched by ComfyUI's ChangeTracker only when the
 * serialized state actually changed, so selection/panning never dirties.
 *
 * Entry points:
 *  - A command (`LoraManager.UpdateManagedWorkflow`), reachable from the
 *    command palette and the top menu bar (File group).
 *  - An item injected into the workflow actions dropdown (the "Graph ▾"
 *    toggle menu). The frontend offers no extension API for that menu, so
 *    the item is appended via DOM observation of the menu's trigger; if the
 *    markup changes upstream the injection silently stops and the command
 *    remains as the fallback.
 *  - The LM web UI card context menu ("Update from ComfyUI"): the backend
 *    routes its request here over the `lm_collect_workflow` WS channel and
 *    awaits the outcome via `/api/lm/workflows/collect-result`.
 *
 * The active graph's link state is reported to the backend
 * (`/api/lm/workflows/comfyui-state`) on load/tab-switch/dirty-flip/
 * write-back so the LM web UI can enable the menu entry only when the
 * workflow is open in ComfyUI and has edits.
 */
import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";
import { lmUrl } from "./base_path.js";
import { showToast } from "./utils.js";

const MARKER_KEY = "lm_source";
const COMMAND_ID = "LoraManager.UpdateManagedWorkflow";
const MENU_LABEL = "Update LM-managed workflow";
const MENU_ICON = "pi pi-upload";
const CREATE_COMMAND_ID = "LoraManager.CreateManagedWorkflow";
const CREATE_MENU_LABEL = "Create LM-managed workflow";
const CREATE_MENU_ICON = "pi pi-plus";
// data-testid of the workflow actions dropdown trigger in ComfyUI_frontend
// (WorkflowActionsDropdown.vue).
const DROPDOWN_TRIGGER_TESTID = "view-mode-toggle";

// { enabled: boolean, path: string } once fetched; null while unknown (the
// menu entry stays optimistically enabled and the backend reports the error).
let workflowLibraryState = null;
let workflowLibraryFetch = null;

// Prompt ids this tab queued and that finished executing. The backend only
// attaches a preview image when the id is still the metadata registry's
// current prompt, so another tab's run can never be borrowed.
let lastExecutedPromptId = null;
const queuedPromptIds = new Set();

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
 * Fetch (once, then cached) whether the workflow library can accept a new
 * entry: the opt-in feature must be on and a library folder configured.
 * Never throws: an unreachable/older backend leaves the state unknown and the
 * create entry optimistically enabled (the POST reports the real error).
 */
function refreshWorkflowLibraryState() {
    if (workflowLibraryFetch) {
        return workflowLibraryFetch;
    }
    workflowLibraryFetch = fetch(lmUrl("/api/lm/settings"))
        .then((response) => (response.ok ? response.json() : null))
        .then((payload) => {
            const settings = payload?.settings;
            if (!settings || typeof settings !== "object") {
                return null;
            }
            workflowLibraryState = {
                enabled: settings.enable_workflows !== false,
                path:
                    typeof settings.workflow_path === "string"
                        ? settings.workflow_path.trim()
                        : "",
            };
            return workflowLibraryState;
        })
        .catch(() => null)
        .finally(() => {
            workflowLibraryFetch = null;
        });
    return workflowLibraryFetch;
}

function canCreateWorkflow() {
    if (workflowLibraryState == null) {
        return true;
    }
    return workflowLibraryState.enabled && !!workflowLibraryState.path;
}

function createUnavailableTitle() {
    if (workflowLibraryState?.enabled === false) {
        return "Workflow management is disabled in LoRA Manager";
    }
    return "Configure the workflow library folder in LoRA Manager first";
}

/**
 * Derive a library file name from the active ComfyUI workflow. Falls back to
 * "Untitled" for temporary/unsaved workflows (the backend sanitizes it).
 */
function getActiveWorkflowName() {
    const workflow = app.extensionManager?.workflow?.activeWorkflow;
    const name = workflow?.filename || workflow?.name || "";
    return typeof name === "string" && name.trim() ? name.trim() : "Untitled";
}

/**
 * Stamp the provenance marker of a freshly created library workflow onto the
 * live graph so "Update LM-managed workflow" becomes available immediately.
 */
function stampLmSource(filePath, sha256) {
    const graph = getRootGraph();
    if (!graph || typeof filePath !== "string" || !filePath) {
        return;
    }
    graph.extra = {
        ...(graph.extra || {}),
        [MARKER_KEY]: { file_path: filePath, sha256: sha256 || null },
    };
}

function clearLmSource() {
    const graph = getRootGraph();
    if (graph && graph.extra && typeof graph.extra === "object") {
        delete graph.extra[MARKER_KEY];
    }
}

/**
 * True when the linked library document still exists; true on any failure so
 * a transient backend error never unlinks a perfectly valid workflow.
 */
async function isLinkedDocumentAlive(marker) {
    if (!marker || typeof marker.file_path !== "string") {
        return false;
    }
    try {
        const response = await fetch(
            lmUrl(
                `/api/lm/workflows/link-status?file_path=${encodeURIComponent(
                    marker.file_path
                )}`
            )
        );
        if (!response.ok) {
            return true;
        }
        const payload = await response.json();
        if (payload?.success && payload.exists === false) {
            return false;
        }
        return true;
    } catch (_error) {
        return true;
    }
}

/**
 * Drop a provenance marker whose library entry was deleted/renamed from the
 * LM page, and report the resulting unlinked state.
 */
async function validateActiveLink() {
    const marker = getActiveLmSource();
    if (!marker) {
        return false;
    }
    if (await isLinkedDocumentAlive(marker)) {
        return true;
    }
    clearLmSource();
    reportLinkState();
    return false;
}

/**
 * Track which prompt ids this tab queued and which of them finished. Used to
 * ask the backend for a preview image without borrowing another tab's run.
 */
function installPromptTracking() {
    if (typeof api.queuePrompt === "function" && !api.__lmQueuePromptHooked) {
        api.__lmQueuePromptHooked = true;
        const originalQueuePrompt = api.queuePrompt.bind(api);
        api.queuePrompt = async function (...args) {
            const response = await originalQueuePrompt(...args);
            const promptId = response?.prompt_id;
            if (typeof promptId === "string" && promptId) {
                queuedPromptIds.add(promptId);
                if (queuedPromptIds.size > 32) {
                    queuedPromptIds.delete(queuedPromptIds.values().next().value);
                }
            }
            return response;
        };
    }

    api.addEventListener("execution_success", (event) => {
        const promptId = event?.detail?.prompt_id;
        if (typeof promptId !== "string" || !promptId) {
            return;
        }
        if (queuedPromptIds.has(promptId)) {
            queuedPromptIds.delete(promptId);
            lastExecutedPromptId = promptId;
        }
    });
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
 * Report the active graph's link state to the LM backend (null state when
 * the active graph is not LM-linked). Best-effort: failures are silent so a
 * missing/older backend never spams the console.
 */
export async function reportLinkState() {
    const marker = getActiveLmSource();
    try {
        await fetch(lmUrl("/api/lm/workflows/comfyui-state"), {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                client_id: api.clientId ?? api.initialClientId ?? "",
                state: marker
                    ? {
                          file_path: marker.file_path,
                          sha256: marker.sha256 || null,
                          dirty: marker.dirty === true,
                      }
                    : null,
            }),
        });
    } catch (_error) {
        // Backend unreachable or older version without the endpoint.
    }
}

/**
 * Core write-back: PUT the current graph into the managed document.
 * Returns { success, sha256? , error? }. On success the marker is refreshed
 * (new hash, dirty cleared) and the new state is reported. On 409 the user
 * is asked to confirm the overwrite when `askOnConflict` is set.
 */
async function performWriteback(marker, { askOnConflict = true } = {}) {
    let result;
    try {
        result = await requestWriteback(marker);
    } catch (error) {
        return { success: false, error: error.message };
    }

    if (result.status === 409) {
        if (!askOnConflict) {
            return { success: false, error: "conflict" };
        }
        const overwrite = window.confirm(
            "The library copy of this workflow has changed since it was opened.\n" +
            "Overwrite the LoRA Manager copy with the current graph?"
        );
        if (!overwrite) {
            return { success: false, error: "cancelled" };
        }
        try {
            result = await requestWriteback(marker, { force: true });
        } catch (error) {
            return { success: false, error: error.message };
        }
    }

    if (result.status === 404) {
        // The library entry was deleted/renamed while this tab held the
        // marker; unlink so "Update" reverts to "Create".
        clearLmSource();
        reportLinkState();
        return { success: false, error: "not_found" };
    }

    if (result.payload?.success) {
        if (result.payload.sha256) {
            marker.sha256 = result.payload.sha256;
        }
        marker.dirty = false;
        reportLinkState();
        return { success: true, sha256: result.payload.sha256 ?? null };
    }
    return {
        success: false,
        error: result.payload?.error || `HTTP ${result.status}`,
    };
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

    if (!(await isLinkedDocumentAlive(marker))) {
        clearLmSource();
        reportLinkState();
        showToast({
            severity: "warn",
            summary: "LoRA Manager",
            detail: "The library copy was deleted or moved. Create it again to keep editing.",
            life: 5000,
        });
        return;
    }

    const result = await performWriteback(marker);
    if (result.success) {
        showToast({
            severity: "success",
            summary: "LoRA Manager",
            detail: "Workflow updated in the LoRA Manager library.",
            life: 3000,
        });
    } else if (result.error === "not_found") {
        showToast({
            severity: "warn",
            summary: "LoRA Manager",
            detail: "The library copy was deleted or moved. Create it again to keep editing.",
            life: 5000,
        });
    } else if (result.error !== "cancelled") {
        showToast({
            severity: "error",
            summary: "LoRA Manager",
            detail: `Failed to update the managed workflow: ${result.error}`,
            life: 5000,
        });
    }
}

/**
 * Create a new LoRA Manager library workflow from the active graph.
 *
 * The backend writes the document into the single configured
 * ``workflow_path`` folder and returns its path/hash; the marker is then
 * stamped onto the live graph so updates work without reopening it. When the
 * graph is already linked, confirm first: the new entry is a separate copy
 * and the existing library document is left untouched.
 */
export async function createManagedWorkflow() {
    const graph = getRootGraph();
    if (!graph || typeof graph.serialize !== "function") {
        showToast({
            severity: "warn",
            summary: "LoRA Manager",
            detail: "No workflow is open to create.",
            life: 5000,
        });
        return;
    }

    const existingMarker = getActiveLmSource();
    if (existingMarker) {
        // The LM entry may have been deleted/renamed since this tab loaded;
        // only ask about a copy when the link is still real.
        if (await isLinkedDocumentAlive(existingMarker)) {
            const createCopy = window.confirm(
                "This graph is already linked to a LoRA Manager workflow.\n" +
                "Create a new library workflow from the current graph?"
            );
            if (!createCopy) {
                return;
            }
        } else {
            clearLmSource();
            reportLinkState();
        }
    }

    let response;
    try {
        response = await fetch(lmUrl("/api/lm/workflows/create"), {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                name: getActiveWorkflowName(),
                workflow: serializeWorkflowForWriteback(),
                preview_prompt_id: lastExecutedPromptId || undefined,
            }),
        });
    } catch (error) {
        showToast({
            severity: "error",
            summary: "LoRA Manager",
            detail: `Failed to create the library workflow: ${error.message}`,
            life: 5000,
        });
        return;
    }

    let payload = null;
    try {
        payload = await response.json();
    } catch (_error) {
        payload = null;
    }

    if (response.ok && payload?.success) {
        stampLmSource(payload.file_path, payload.sha256);
        reportLinkState();
        const displayName = payload.name || getActiveWorkflowName();
        showToast({
            severity: "success",
            summary: "LoRA Manager",
            detail: `Created "${displayName}" in the LoRA Manager library.`,
            life: 3000,
        });
        return;
    }

    showToast({
        severity: "error",
        summary: "LoRA Manager",
        detail: `Failed to create the library workflow: ${payload?.error || `HTTP ${response.status}`}`,
        life: 5000,
    });
}

/**
 * Answer an LM-web-UI "Update from ComfyUI" request. Only the tab whose
 * active graph marker matches the requested file_path responds; the outcome
 * is posted back to the backend, which resolves the pending LM-page request.
 */
async function handleCollectRequest(detail) {
    const requestId = detail?.request_id;
    const filePath = detail?.file_path;
    if (!requestId || !filePath) {
        return;
    }
    const marker = getActiveLmSource();
    if (!marker || marker.file_path !== filePath) {
        return;
    }

    const result = marker.dirty
        ? await performWriteback(marker)
        : { success: false, error: "no_changes" };

    try {
        await fetch(lmUrl("/api/lm/workflows/collect-result"), {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ request_id: requestId, ...result }),
        });
    } catch (error) {
        console.error("LoRA Manager: failed to post collect result", error);
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

// classList.add/remove accept multiple tokens, while classList.toggle expects
// a single token — keep the class strings and split them at the call site.
const ITEM_ACTIVE_TOKENS = ITEM_ACTIVE_CLASSES.split(/\s+/);
const ITEM_DISABLED_TOKENS = ITEM_DISABLED_CLASSES.split(/\s+/);

function applyItemState(item, active) {
    const add = active ? ITEM_ACTIVE_TOKENS : ITEM_DISABLED_TOKENS;
    const remove = active ? ITEM_DISABLED_TOKENS : ITEM_ACTIVE_TOKENS;
    item.classList.remove(...remove);
    item.classList.add(...add);
}

function closeMenu(item) {
    // Our node is not a reka-ui DropdownMenuItem, so the menu does not close
    // on its own — close it the way Escape would.
    const menu = item.closest('[role="menu"]');
    (menu ?? document).dispatchEvent(
        new KeyboardEvent("keydown", { key: "Escape", bubbles: true })
    );
}

function buildCreateItem() {
    const canCreate = canCreateWorkflow();
    const item = document.createElement("div");
    item.setAttribute("role", "menuitem");
    item.dataset.lmAction = "create-workflow";
    item.className = `${ITEM_CLASSES} ${canCreate ? ITEM_ACTIVE_CLASSES : ITEM_DISABLED_CLASSES}`;
    if (!canCreate) {
        item.setAttribute("aria-disabled", "true");
        item.title = createUnavailableTitle();
    }

    const icon = document.createElement("i");
    icon.className = CREATE_MENU_ICON;
    const label = document.createElement("span");
    label.className = "flex-1";
    label.textContent = CREATE_MENU_LABEL;
    item.append(icon, label);

    item.addEventListener("click", () => {
        if (!canCreateWorkflow()) {
            return;
        }
        closeMenu(item);
        createManagedWorkflow();
    });

    return item;
}

/**
 * Re-evaluate the create entry after the library state fetch resolves while
 * the menu is still open (the item is built before the fetch completes).
 */
function applyCreateAvailability(item) {
    if (!item) {
        return;
    }
    const canCreate = canCreateWorkflow();
    applyItemState(item, canCreate);
    if (canCreate) {
        item.removeAttribute("aria-disabled");
        item.removeAttribute("title");
    } else {
        item.setAttribute("aria-disabled", "true");
        item.title = createUnavailableTitle();
    }
}

function applyUpdateLinkState(item) {
    if (!item) {
        return;
    }
    const linked = getActiveLmSource() !== null;
    applyItemState(item, linked);
    if (linked) {
        item.removeAttribute("aria-disabled");
        item.removeAttribute("title");
    } else {
        item.setAttribute("aria-disabled", "true");
        item.title = "Open a workflow from LoRA Manager, or create one first";
    }
}

function buildUpdateItem() {
    const item = document.createElement("div");
    item.setAttribute("role", "menuitem");
    item.dataset.lmAction = "update-workflow";
    item.className = ITEM_CLASSES;

    const icon = document.createElement("i");
    icon.className = MENU_ICON;
    const label = document.createElement("span");
    label.className = "flex-1";
    label.textContent = MENU_LABEL;
    item.append(icon, label);

    item.addEventListener("click", () => {
        if (getActiveLmSource() === null) {
            return;
        }
        closeMenu(item);
        updateManagedWorkflow();
    });

    applyUpdateLinkState(item);
    return item;
}

function buildMenuItems() {
    const separator = document.createElement("div");
    separator.className = SEPARATOR_CLASSES;
    separator.setAttribute("role", "separator");

    return [separator, buildCreateItem(), buildUpdateItem()];
}

/**
 * Append the LM entries to an open workflow actions menu, once per menu
 * instance (the portal remounts on every open).
 */
function injectIntoMenu(menuElement) {
    if (menuElement.dataset.lmWritebackInjected) {
        return;
    }
    menuElement.dataset.lmWritebackInjected = "1";
    for (const node of buildMenuItems()) {
        menuElement.appendChild(node);
    }

    if (workflowLibraryState === null || !canCreateWorkflow()) {
        const createItem = menuElement.querySelector(
            '[data-lm-action="create-workflow"]'
        );
        refreshWorkflowLibraryState().then(() =>
            applyCreateAvailability(createItem)
        );
    }

    if (getActiveLmSource()) {
        const updateItem = menuElement.querySelector(
            '[data-lm-action="update-workflow"]'
        );
        validateActiveLink().then(() => applyUpdateLinkState(updateItem));
    }
}

function findOpenWorkflowMenu() {
    // The workflow actions menu is the reka-ui dropdown containing the
    // core items (pencil = Rename, save = Save, download = Export); icon
    // classes are locale-independent.
    for (const menu of document.querySelectorAll('[role="menu"]')) {
        // The workflow tab context menu has the same core icons; skip it so
        // the two injection paths never write into each other's menu.
        if (menu.querySelector(".pi-arrows-h")) {
            continue;
        }
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

// ---------------------------------------------------------------------------
// Workflow tab context menu injection
// ---------------------------------------------------------------------------
//
// ComfyUI exposes commands and the File menu to extensions, but the workflow
// tab context menu is built inside WorkflowTab.vue with no extension hook.
// Fall back to the same portal injection used for the Graph menu: the items
// still call the registered create/update actions, and they first activate the
// right-clicked tab so Save-style actions always target that workflow.

const TAB_UPDATE_UNAVAILABLE_TITLE =
    "This workflow is not linked to the LoRA Manager library";

function getTabWorkflow(tab) {
    // Scope to the tab strip so a hidden second view (graph vs linear) can
    // never shift the index that maps a tab to openWorkflows.
    const container = tab.closest(".workflow-tabs-container") ?? document;
    const index = Array.from(container.querySelectorAll(".workflow-tab")).indexOf(
        tab
    );
    if (index < 0) {
        return null;
    }
    const workflow = app.extensionManager?.workflow?.openWorkflows?.[index];
    return workflow && typeof workflow === "object" ? workflow : null;
}

function getTabLmSource(tab) {
    const workflow = getTabWorkflow(tab);
    const store = app.extensionManager?.workflow;
    if (!workflow || !store) {
        return null;
    }
    if (store.activeWorkflow === workflow) {
        return getActiveLmSource();
    }
    const marker = workflow.activeState?.extra?.[MARKER_KEY];
    return marker &&
        typeof marker === "object" &&
        typeof marker.file_path === "string"
        ? marker
        : null;
}

/**
 * Make the right-clicked tab active, the way the native Save/Export entries
 * do, so the LM action operates on that tab instead of whichever graph was
 * previously active.
 */
async function activateTabWorkflow(tab) {
    const workflow = getTabWorkflow(tab);
    const store = app.extensionManager?.workflow;
    if (!workflow || !store) {
        return false;
    }
    if (store.activeWorkflow !== workflow) {
        if (typeof store.openWorkflow !== "function") {
            return false;
        }
        await store.openWorkflow(workflow);
    }
    return true;
}

function applyTabUpdateState(item, tab) {
    if (!item) {
        return;
    }
    const linked = getTabLmSource(tab) !== null;
    applyItemState(item, linked);
    if (linked) {
        item.removeAttribute("aria-disabled");
        item.removeAttribute("title");
    } else {
        item.setAttribute("aria-disabled", "true");
        item.title = TAB_UPDATE_UNAVAILABLE_TITLE;
    }
}

function buildTabActionItem(action, label, icon, tab) {
    const item = document.createElement("div");
    item.setAttribute("role", "menuitem");
    item.dataset.lmTabAction =
        action === "create" ? "create-workflow" : "update-workflow";
    item.className = ITEM_CLASSES;

    const iconElement = document.createElement("i");
    iconElement.className = icon;
    const labelElement = document.createElement("span");
    labelElement.className = "flex-1";
    labelElement.textContent = label;
    item.append(iconElement, labelElement);

    item.addEventListener("click", async (event) => {
        event.preventDefault();
        event.stopPropagation();
        if (item.getAttribute("aria-disabled") === "true") {
            return;
        }
        closeMenu(item);
        try {
            if (!(await activateTabWorkflow(tab))) {
                return;
            }
        } catch (error) {
            console.warn("LoRA Manager: could not activate workflow tab", error);
            showToast({
                severity: "warn",
                summary: "LoRA Manager",
                detail: "Could not switch to that workflow tab.",
                life: 5000,
            });
            return;
        }
        if (action === "create") {
            await createManagedWorkflow();
        } else {
            await updateManagedWorkflow();
        }
    });

    return item;
}

function findTabMenuCloseSeparator(menu) {
    // The last separator divides the workflow actions from the tab-close
    // group; put the LM group just above it.
    let separators = Array.from(menu.querySelectorAll('[role="separator"]'));
    if (separators.length === 0) {
        separators = Array.from(
            menu.querySelectorAll(".my-1.w-full.border-b")
        );
    }
    return separators.at(-1) ?? null;
}

function findTabContextMenu(tab) {
    // reka-ui links the open trigger to its portalled content. Use that when
    // available; otherwise pick the visible menu that carries the distinctive
    // tab-close overlay icon (pi-arrows-h).
    const contentId = tab.getAttribute("aria-controls");
    if (contentId) {
        const menu = document.getElementById(contentId);
        if (
            menu &&
            menu.getAttribute("role") === "menu" &&
            menu.dataset.state !== "closed"
        ) {
            return menu;
        }
    }
    const menus = Array.from(document.querySelectorAll('[role="menu"]')).filter(
        (menu) => menu.getClientRects().length > 0 && menu.querySelector(".pi-arrows-h")
    );
    return menus.at(-1) ?? null;
}

/**
 * Append the LM entries to the workflow tab context menu, once per menu
 * instance. Unlike the Graph menu, Update reflects the marker of the
 * right-clicked tab, not only the active graph.
 */
function injectIntoTabMenu(tab) {
    const menu = findTabContextMenu(tab);
    if (!menu || menu.dataset.lmTabMenuInjected) {
        return;
    }
    // Wait until the tab-close group has rendered (pi-arrows-h belongs to
    // Close Other Tabs) so the LM group is inserted above it, not after a
    // half-built menu.
    if (!menu.querySelector(".pi-arrows-h")) {
        return;
    }
    menu.dataset.lmTabMenuInjected = "1";

    const createItem = buildTabActionItem(
        "create",
        CREATE_MENU_LABEL,
        CREATE_MENU_ICON,
        tab
    );
    const updateItem = buildTabActionItem(
        "update",
        MENU_LABEL,
        MENU_ICON,
        tab
    );
    applyCreateAvailability(createItem);
    applyTabUpdateState(updateItem, tab);

    const separator = document.createElement("div");
    separator.setAttribute("role", "separator");
    separator.className = SEPARATOR_CLASSES;

    const anchor = findTabMenuCloseSeparator(menu);
    if (anchor) {
        anchor.before(separator, createItem, updateItem);
    } else {
        menu.append(separator, createItem, updateItem);
    }

    const marker = getTabLmSource(tab);
    if (marker) {
        // An inactive tab can carry a marker whose library entry was already
        // deleted. Keep Update disabled for that case; opening the tab later
        // clears the marker through afterConfigureGraph.
        isLinkedDocumentAlive(marker).then((alive) => {
            if (!alive && updateItem.isConnected) {
                applyItemState(updateItem, false);
                updateItem.setAttribute("aria-disabled", "true");
                updateItem.title = "The library copy was deleted or moved";
            }
        });
    }

    if (workflowLibraryState === null) {
        refreshWorkflowLibraryState().then(() => {
            if (createItem.isConnected) {
                applyCreateAvailability(createItem);
            }
        });
    }
}

function safeInjectIntoTabMenu(tab) {
    try {
        injectIntoTabMenu(tab);
    } catch (error) {
        console.warn("LoRA Manager: workflow tab menu injection failed", error);
    }
}

function installTabContextMenuInjection() {
    let lastContextTab = null;
    const scheduleInjection = (tab) => {
        // The portal mounts after the contextmenu event; poll briefly.
        for (const delay of [0, 40, 120]) {
            setTimeout(() => {
                if (tab.isConnected) {
                    safeInjectIntoTabMenu(tab);
                }
            }, delay);
        }
    };

    document.addEventListener(
        "contextmenu",
        (event) => {
            const target = event.target;
            if (!(target instanceof Element)) {
                return;
            }
            const tab = target.closest(".workflow-tab");
            if (!tab) {
                return;
            }
            lastContextTab = tab;
            scheduleInjection(tab);
        },
        true
    );

    // Keyboard/long-press openings do not fire a contextmenu event on the
    // tab; catch the menu as it mounts while a tab is in the open state.
    // Ignore unrelated DOM churn so graph edits do not trigger menu scans.
    const observer = new MutationObserver((mutations) => {
        let menuAdded = false;
        for (const mutation of mutations) {
            for (const node of mutation.addedNodes) {
                if (
                    node instanceof Element &&
                    (node.matches('[role="menu"]') ||
                        node.querySelector('[role="menu"]'))
                ) {
                    menuAdded = true;
                    break;
                }
            }
            if (menuAdded) {
                break;
            }
        }
        if (!menuAdded) {
            return;
        }
        const tab =
            document.querySelector('.workflow-tab[data-state="open"]') ??
            lastContextTab;
        if (!tab || !tab.isConnected) {
            return;
        }
        const menu = findTabContextMenu(tab);
        if (menu && !menu.dataset.lmTabMenuInjected) {
            safeInjectIntoTabMenu(tab);
        }
    });
    observer.observe(document.body, { childList: true, subtree: true });
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
            id: CREATE_COMMAND_ID,
            label: CREATE_MENU_LABEL,
            menubarLabel: CREATE_MENU_LABEL,
            icon: CREATE_MENU_ICON,
            function: () => createManagedWorkflow(),
        },
        {
            id: COMMAND_ID,
            label: MENU_LABEL,
            menubarLabel: MENU_LABEL,
            icon: MENU_ICON,
            function: () => updateManagedWorkflow(),
        },
    ],

    menuCommands: [
        { path: ["File"], commands: [CREATE_COMMAND_ID, COMMAND_ID] },
    ],

    setup() {
        try {
            installDropdownInjection();
        } catch (error) {
            console.warn("LoRA Manager: workflow dropdown injection unavailable", error);
        }

        try {
            installTabContextMenuInjection();
        } catch (error) {
            console.warn("LoRA Manager: workflow tab menu injection unavailable", error);
        }

        // Resolve whether the library can accept a new entry before the user
        // opens the menu; failures leave the entry optimistically enabled and
        // the create request itself reports the real error.
        refreshWorkflowLibraryState();

        // Track this tab's executed prompt so Create can attach its decode
        // image as the workflow preview.
        installPromptTracking();

        // graphChanged is dispatched by ComfyUI's ChangeTracker only when the
        // serialized state actually changed: the first one after a load or
        // write-back is a genuine user edit.
        api.addEventListener("graphChanged", () => {
            const marker = getActiveLmSource();
            if (marker && marker.dirty !== true) {
                marker.dirty = true;
                reportLinkState();
            }
        });

        api.addEventListener("lm_collect_workflow", (event) =>
            handleCollectRequest(event?.detail ?? {})
        );
    },

    // Fires on initial load, workflow open, and tab switch: drop a stale
    // marker (library entry deleted/renamed) before reporting which managed
    // workflow is active now.
    async afterConfigureGraph() {
        // A different workflow is active now: never borrow its predecessor's
        // executed prompt for the next Create preview.
        lastExecutedPromptId = null;
        await validateActiveLink();
        await reportLinkState();
    },
});

import { app } from "../../scripts/app.js";
import { createFloatingPanel } from "./floating_panel.js";
import { ensureLmStyles } from "./lm_styles_loader.js";
import { getAllGraphNodes, getWidgetByName } from "./utils.js";
import { applyLoraSelection, findLoraIndex } from "./lora_selection.js";
import { normalizeLoraNameKey } from "./loras_widget_utils.js";
import { isVideoPreviewUrl } from "./mediaTypes.js";
import {
  buildAddedLoraStateMap,
  createAddedLoraCue,
  resolveAddedLoraState,
} from "./lora_added_state.js";
import {
  countActiveFilters,
  fetchActiveFilters,
  fetchLoraDetails,
  fetchLoraFolderIndex,
  openLoraManager,
  recommendedStrength,
  searchLoraLibrary,
} from "./lora_canvas_api.js";

const COMMAND_ID = "LoraManager.ToggleQuickPanel";
const RECENT_KEY = "lm:quick-panel:recent-loras";
const VIEW_KEY = "lm:quick-panel:view-mode";
const ACTIVE_FILTERS_KEY = "lm:quick-panel:active-filters";
let activeQuickPanel = null;

function el(tag, className, text) {
  const element = document.createElement(tag);
  if (className) element.className = className;
  if (text !== undefined) element.textContent = text;
  return element;
}

function loraWidget(node) {
  return node?.lorasWidget || getWidgetByName(node, "loras");
}

function compatibleNodes() {
  return getAllGraphNodes(app.graph)
    .map(({ node }) => node)
    .filter((node) => !!loraWidget(node));
}

function nodeLabel(node) {
  return `${node?.title || node?.comfyClass || "LoRA node"} (#${node?.id ?? "?"})`;
}

function recentNames() {
  try { return JSON.parse(localStorage.getItem(RECENT_KEY) || "[]"); } catch { return []; }
}

function rememberName(name) {
  const next = [name, ...recentNames().filter((item) => item !== name)].slice(0, 20);
  try { localStorage.setItem(RECENT_KEY, JSON.stringify(next)); } catch { /* cosmetic only */ }
}

export function applyQuickLoraSelection(node, selection, replaceName = "") {
  const widget = loraWidget(node);
  if (!widget) throw new Error("The target node no longer accepts LoRAs");
  const current = Array.isArray(widget.value) ? widget.value : [];
  let next;
  let changed = true;

  if (replaceName) {
    const index = findLoraIndex(current, normalizeLoraNameKey(replaceName));
    if (index < 0) throw new Error("The LoRA being replaced is no longer on this node");
    const replacement = applyLoraSelection([], selection).loras[0];
    next = current.slice();
    next[index] = replacement;
  } else {
    const result = applyLoraSelection(current, selection);
    next = result.loras;
    changed = result.changed;
  }

  if (changed) {
    widget.value = next;
    widget.callback?.(next);
    node.setDirtyCanvas?.(true, true);
    app.graph?.setDirtyCanvas?.(true, true);
  }
  return { changed, loras: next };
}

export class LoraQuickPanel {
  constructor({ node = null, replaceName = "" } = {}) {
    this.targetNode = node;
    this.replaceName = replaceName;
    this.items = [];
    this.selectedIndex = -1;
    this.details = null;
    this.searchSequence = 0;
    this.detailSequence = 0;
    this.recentOnly = false;
    this.debounceTimer = null;
    this.panel = null;
    this.viewMode = "folders";
    try { this.viewMode = localStorage.getItem(VIEW_KEY) === "flat" ? "flat" : "folders"; } catch { /* default */ }
    this.activeFilters = false;
    try { this.activeFilters = localStorage.getItem(ACTIVE_FILTERS_KEY) === "1"; } catch { /* default */ }
    this.activeFilterSnapshot = null;
    this.activeFilterCount = 0;
    this.filterSequence = 0;
    this.folderIndex = null;
    this.folderError = "";
    this.currentFolder = "";
    this.folderSequence = 0;
  }

  open() {
    ensureLmStyles();
    this.panel = createFloatingPanel({
      title: "Quick Pick · LoRA",
      context: this.replaceName ? "Replace a LoRA" : "Add to the current workflow",
      className: "lm-quick-panel",
      storageKey: "lm:quick-panel:rect",
      width: 880,
      height: 570,
      minWidth: 600,
      minHeight: 380,
      onClose: () => {
        clearTimeout(this.debounceTimer);
        if (activeQuickPanel === this) activeQuickPanel = null;
      },
    });
    this.build();
    this.loadActiveFilters();
    this.loadFolderIndex();
    this.loadSearch();
    setTimeout(() => this.searchInput?.focus(), 20);
    return this;
  }

  close() {
    this.panel?.close();
  }

  build() {
    const { body, footer } = this.panel;
    body.replaceChildren();
    footer.replaceChildren();
    this.panel.element.addEventListener("keydown", (event) => {
      if (event.target !== this.searchInput) this.onSearchKey(event);
    }, true);

    const toolbar = el("div", "lm-quick__toolbar");
    this.searchInput = el("input", "lm-quick__search");
    this.searchInput.type = "search";
    this.searchInput.placeholder = "Search file or model name…";
    this.searchInput.setAttribute("aria-label", "Search LoRA library");
    this.searchInput.addEventListener("input", () => {
      clearTimeout(this.debounceTimer);
      this.debounceTimer = setTimeout(() => this.loadSearch(), 180);
    });
    this.searchInput.addEventListener("keydown", (event) => this.onSearchKey(event));

    this.viewButtons = {};
    const viewSwitch = el("div", "lm-quick__view-switch");
    viewSwitch.setAttribute("role", "group");
    viewSwitch.setAttribute("aria-label", "Library layout");
    for (const [mode, label] of [["folders", "Folder"], ["flat", "Flat"]]) {
      const button = el("button", "lm-quick__view-button", label);
      button.type = "button";
      button.classList.toggle("is-active", this.viewMode === mode);
      button.setAttribute("aria-pressed", String(this.viewMode === mode));
      button.addEventListener("click", () => this.setViewMode(mode));
      this.viewButtons[mode] = button;
      viewSwitch.appendChild(button);
    }

    this.filterButton = el("button", "lm-quick__filter", "Filters");
    this.filterButton.type = "button";
    this.filterButton.addEventListener("click", () => this.toggleActiveFilters());

    this.recentButton = el("button", "lm-quick__filter", "Recent");
    this.recentButton.type = "button";
    this.recentButton.title = "Show recently applied LoRAs";
    this.recentButton.addEventListener("click", () => {
      this.recentOnly = !this.recentOnly;
      this.selectedIndex = this.visibleItems().length ? 0 : -1;
      this.recentButton.classList.toggle("is-active", this.recentOnly);
      this.renderResults();
    });

    this.targetSelect = el("select", "lm-quick__target");
    this.targetSelect.setAttribute("aria-label", "Target LoRA node");
    this.targetSelect.addEventListener("change", () => {
      const candidates = compatibleNodes();
      this.targetNode = candidates[Number(this.targetSelect.value)] || null;
      this.replaceName = "";
      this.panel.setContext(this.targetNode ? `Add to ${nodeLabel(this.targetNode)}` : "No compatible node");
      this.refreshAddedMarkers();
      this.renderDetail();
    });
    toolbar.append(this.searchInput, viewSwitch, this.filterButton, this.recentButton, this.targetSelect);

    const content = el("div", "lm-quick__content");
    this.resultsElement = el("div", "lm-quick__results");
    this.resultsElement.setAttribute("role", "listbox", "LoRA results");
    this.detailElement = el("aside", "lm-quick__detail");
    content.append(this.resultsElement, this.detailElement);
    body.append(toolbar, content);

    this.statusElement = el("span", "lm-quick__status");
    const hints = el("span", "lm-quick__hints", "↑↓ Navigate · ←→ Folder · Enter Open/Apply · Shift+Enter Keep open · Esc Close");
    footer.append(this.statusElement, hints);
    this.renderTargets();
    this.renderFilterButton();
    this.renderDetail();
  }

  renderTargets() {
    const candidates = compatibleNodes();
    if (!this.targetNode || !candidates.includes(this.targetNode)) {
      const selected = Object.values(app.canvas?.selected_nodes || {})
        .find((node) => candidates.includes(node));
      this.targetNode = selected || candidates[0] || null;
    }
    this.targetSelect.replaceChildren();
    candidates.forEach((node, index) => {
      const option = el("option", "", nodeLabel(node));
      option.value = String(index);
      this.targetSelect.appendChild(option);
    });
    this.targetSelect.hidden = candidates.length < 2;
    this.targetSelect.disabled = !candidates.length;
    if (this.targetNode) this.targetSelect.value = String(candidates.indexOf(this.targetNode));
    this.panel.setContext(this.targetNode
      ? `${this.replaceName ? "Replace in" : "Add to"} ${nodeLabel(this.targetNode)}`
      : "No compatible LoRA Manager node on this workflow");
  }

  async loadSearch() {
    const sequence = ++this.searchSequence;
    const query = this.searchInput.value.trim();
    this.setStatus(query ? `Searching “${query}”…` : "Loading library…");
    try {
      const items = await searchLoraLibrary(query, 60, { useActiveFilters: this.activeFilters });
      if (sequence !== this.searchSequence || !this.panel?.isOpen()) return;
      this.items = items;
      this.selectedIndex = items.length ? 0 : -1;
      this.renderResults();
      const scope = this.activeFilters ? " within active filters" : "";
      this.setStatus(items.length
        ? `${items.length} result${items.length === 1 ? "" : "s"}${scope}`
        : `No matching LoRAs${scope}`);
    } catch (error) {
      if (sequence !== this.searchSequence) return;
      this.items = [];
      this.selectedIndex = -1;
      this.renderResults();
      this.setStatus(error.message);
    }
  }

  async loadFolderIndex() {
    const sequence = ++this.folderSequence;
    try {
      const root = await fetchLoraFolderIndex({ useActiveFilters: this.activeFilters });
      if (sequence !== this.folderSequence || !this.panel?.isOpen()) return;
      this.folderIndex = root;
      this.folderError = "";
      this.renderResults();
    } catch (error) {
      if (sequence !== this.folderSequence) return;
      this.folderError = error.message;
      this.renderResults();
    }
  }

  /**
   * Refresh the manager page's active-filter snapshot and reflect it on the
   * Filters toggle. The filters themselves live server-side (the page mirrors
   * them), so this works even when ComfyUI and the page are separate origins.
   */
  async loadActiveFilters() {
    const sequence = ++this.filterSequence;
    try {
      const snapshot = await fetchActiveFilters();
      if (sequence !== this.filterSequence || !this.panel?.isOpen()) return;
      this.activeFilterSnapshot = snapshot;
    } catch {
      if (sequence !== this.filterSequence || !this.panel?.isOpen()) return;
      this.activeFilterSnapshot = null;
    }
    this.activeFilterCount = countActiveFilters(this.activeFilterSnapshot);
    this.renderFilterButton();
  }

  renderFilterButton() {
    if (!this.filterButton) return;
    const count = this.activeFilterCount;
    this.filterButton.textContent = count ? `Filters · ${count}` : "Filters";
    this.filterButton.classList.toggle("is-active", this.activeFilters);
    this.filterButton.setAttribute("aria-pressed", String(this.activeFilters));
    this.filterButton.title = this.activeFilters
      ? `Showing LoRAs inside the LoRA Manager page's active filters${count ? ` (${count})` : ""}. Click to show the whole library.`
      : count
        ? `Filter by the LoRA Manager page's active filters (${count}).`
        : "No active filters are set on the LoRA Manager page.";
  }

  async toggleActiveFilters() {
    this.activeFilters = !this.activeFilters;
    try { localStorage.setItem(ACTIVE_FILTERS_KEY, this.activeFilters ? "1" : "0"); } catch { /* cosmetic only */ }
    this.renderFilterButton();
    this.folderIndex = null;
    this.selectedIndex = 0;
    await this.loadActiveFilters();
    await Promise.all([this.loadFolderIndex(), this.loadSearch()]);
    if (this.activeFilters && !this.activeFilterCount) {
      this.setStatus("No active filters are set on the LoRA Manager page.");
    }
  }

  setViewMode(mode) {
    if (mode !== "folders" && mode !== "flat") return;
    this.viewMode = mode;
    try { localStorage.setItem(VIEW_KEY, mode); } catch { /* cosmetic only */ }
    for (const [name, button] of Object.entries(this.viewButtons)) {
      button.classList.toggle("is-active", name === mode);
      button.setAttribute("aria-pressed", String(name === mode));
    }
    this.selectedIndex = this.navigationItems().length ? 0 : -1;
    this.renderResults();
  }

  isFolderBrowse() {
    return this.viewMode === "folders" && !this.recentOnly && !this.searchInput.value.trim();
  }

  currentFolderNode() {
    let node = this.folderIndex;
    for (const part of this.currentFolder.split("/").filter(Boolean)) {
      node = node?.folders?.[part];
    }
    return node || null;
  }

  openFolder(path, selectedPath = "") {
    this.currentFolder = path;
    const items = this.navigationItems();
    const selectedFolder = items.findIndex((entry) => entry.type === "folder" && entry.path === selectedPath);
    this.selectedIndex = selectedFolder >= 0 ? selectedFolder : items.length ? 0 : -1;
    this.renderResults();
    this.searchInput.focus();
    const count = this.currentFolderNode()?.count || 0;
    this.setStatus(`${count} LoRA${count === 1 ? "" : "s"} in this folder`);
  }

  closeFolder() {
    if (!this.currentFolder) return;
    const previous = this.currentFolder;
    const parts = previous.split("/");
    parts.pop();
    this.openFolder(parts.join("/"), previous);
  }

  visibleItems() {
    if (this.isFolderBrowse()) return this.currentFolderNode()?.items || [];
    if (!this.recentOnly) return this.items;
    const recent = new Set(recentNames());
    return this.items.filter((item) => recent.has(normalizeLoraNameKey(item.relativePath)));
  }

  navigationItems() {
    if (!this.isFolderBrowse()) {
      return this.visibleItems().map((item) => ({ type: "lora", item }));
    }
    const node = this.currentFolderNode();
    return [
      ...Object.entries(node?.folders || {}).map(([name, child]) => ({
        type: "folder",
        name,
        path: this.currentFolder ? `${this.currentFolder}/${name}` : name,
      })),
      ...(node?.items || []).map((item) => ({ type: "lora", item })),
    ];
  }

  /** Snapshot of the target node's LoRA list, keyed by normalized name. */
  addedLoraStates() {
    if (!this.targetNode) return new Map();
    return buildAddedLoraStateMap(loraWidget(this.targetNode)?.value);
  }

  appendLoraRows(items, offset = 0) {
    const states = this.addedLoraStates();
    items.forEach((item, index) => {
      const navigationIndex = offset + index;
      const row = el("button", "lm-quick__row");
      row.type = "button";
      row.setAttribute("role", "option");
      row.setAttribute("aria-selected", String(navigationIndex === this.selectedIndex));
      row.classList.toggle("is-selected", navigationIndex === this.selectedIndex);
      row.dataset.loraPath = item.relativePath || "";
      const head = el("span", "lm-quick__row-head");
      head.appendChild(el("span", "lm-quick__row-name", item.modelName));
      const addedState = resolveAddedLoraState(states, item.relativePath);
      if (addedState) head.appendChild(createAddedLoraCue(addedState));
      row.append(head, el("span", "lm-quick__row-path", item.relativePath));
      row.addEventListener("click", () => this.select(navigationIndex));
      row.addEventListener("dblclick", () => this.apply(false));
      this.resultsElement.appendChild(row);
    });
  }

  /**
   * Re-read the target node's LoRA list and update the "Added"/"Off" cues in
   * place, so applying a LoRA or switching targets does not rebuild (and
   * scroll-reset) the result list.
   */
  refreshAddedMarkers() {
    const states = this.addedLoraStates();
    this.resultsElement.querySelectorAll(".lm-quick__row").forEach((row) => {
      const head = row.querySelector(".lm-quick__row-head");
      if (!head) return;
      const state = resolveAddedLoraState(states, row.dataset.loraPath || "");
      head.querySelector(".lm-lora-added")?.remove();
      if (state) head.appendChild(createAddedLoraCue(state));
    });
  }

  renderFolderResults() {
    this.resultsElement.replaceChildren();
    if (this.folderError) {
      const message = el("div", "lm-quick__empty", `Folder view unavailable: ${this.folderError}`);
      const flat = el("button", "lm-quick__secondary", "Use Flat view");
      flat.type = "button";
      flat.addEventListener("click", () => this.setViewMode("flat"));
      message.appendChild(document.createElement("br"));
      message.appendChild(flat);
      this.resultsElement.appendChild(message);
      this.renderDetail();
      return;
    }
    if (!this.folderIndex) {
      this.resultsElement.appendChild(el("div", "lm-quick__loading", "Loading folders…"));
      this.renderDetail();
      return;
    }

    const node = this.currentFolderNode();
    if (!node) {
      this.currentFolder = "";
      return this.renderFolderResults();
    }
    const navigationItems = this.navigationItems();
    if (this.selectedIndex < 0 || this.selectedIndex >= navigationItems.length) {
      this.selectedIndex = navigationItems.length ? 0 : -1;
    }
    const navigation = el("div", "lm-quick__folder-nav");
    if (this.currentFolder) {
      const back = el("button", "lm-quick__folder-back", "‹ Back");
      back.type = "button";
      back.addEventListener("click", () => this.closeFolder());
      navigation.appendChild(back);
    }
    navigation.appendChild(el("span", "lm-quick__folder-current", this.currentFolder || "All"));
    this.resultsElement.appendChild(navigation);

    const folders = Object.entries(node.folders || {});
    folders.forEach(([name, child], index) => {
      const path = this.currentFolder ? `${this.currentFolder}/${name}` : name;
      const row = el("button", "lm-quick__folder-row");
      row.type = "button";
      row.setAttribute("role", "option");
      row.setAttribute("aria-label", `Open folder ${name}, ${child.count} LoRAs`);
      row.setAttribute("aria-selected", String(index === this.selectedIndex));
      row.classList.toggle("is-selected", index === this.selectedIndex);
      row.append(
        el("span", "lm-quick__folder-icon"),
        el("span", "lm-quick__folder-name", name),
        el("span", "lm-quick__folder-count", String(child.count)),
        el("span", "lm-quick__folder-chevron", "›"),
      );
      row.addEventListener("click", () => this.openFolder(path));
      this.resultsElement.appendChild(row);
    });

    const visible = this.visibleItems();
    this.appendLoraRows(visible, folders.length);
    if (!folders.length && !visible.length) {
      this.resultsElement.appendChild(el("div", "lm-quick__empty", "This folder is empty."));
    }
    this.renderDetail();
  }

  renderResults() {
    if (this.isFolderBrowse()) {
      this.renderFolderResults();
      return;
    }
    const visible = this.visibleItems();
    this.resultsElement.replaceChildren();
    if (!visible.length) {
      this.resultsElement.appendChild(el("div", "lm-quick__empty", this.recentOnly
        ? "No recently applied LoRAs in this result set."
        : "No LoRAs to show. Try another search or clear Recent."));
      this.renderDetail();
      return;
    }
    if (this.selectedIndex >= visible.length) this.selectedIndex = 0;
    this.appendLoraRows(visible);
    this.renderDetail();
  }

  select(index) {
    this.selectedIndex = index;
    const rows = this.resultsElement.querySelectorAll(".lm-quick__folder-row, .lm-quick__row");
    rows.forEach((row, rowIndex) => {
      row.classList.toggle("is-selected", rowIndex === index);
      row.setAttribute("aria-selected", String(rowIndex === index));
    });
    rows[index]?.scrollIntoView({ block: "nearest" });
    this.renderDetail();
  }

  selectedItem() {
    const selected = this.navigationItems()[this.selectedIndex];
    return selected?.type === "lora" ? selected.item : null;
  }

  async renderDetail() {
    const sequence = ++this.detailSequence;
    const item = this.selectedItem();
    this.details = null;
    this.detailElement.replaceChildren();
    if (!item) {
      this.detailElement.appendChild(el("div", "lm-quick__empty", "Select a LoRA to see its details."));
      return;
    }

    this.detailElement.appendChild(el("div", "lm-quick__loading", "Loading local details…"));
    try {
      const details = await fetchLoraDetails(item.relativePath);
      if (sequence !== this.detailSequence || !this.panel?.isOpen()) return;
      this.details = details;
      this.detailElement.replaceChildren();

      if (details.preview_url) {
        // Video LoRAs store an .mp4/.webm preview; an <img> would render a
        // broken thumbnail for them, so pick the element from the media type.
        const isVideo = isVideoPreviewUrl(details.preview_url);
        const preview = el(isVideo ? "video" : "img", "lm-quick__preview");
        preview.src = details.preview_url;
        if (isVideo) {
          preview.autoplay = true;
          preview.loop = true;
          preview.muted = true;
          preview.playsInline = true;
        } else {
          preview.alt = "";
        }
        this.detailElement.appendChild(preview);
      }
      this.detailElement.appendChild(el("h2", "lm-quick__name", details.model_name || item.modelName));
      const meta = [details.base_model, details.folder].filter(Boolean).join(" · ");
      this.detailElement.appendChild(el("div", "lm-quick__meta", meta || item.relativePath));
      const triggers = details.civitai?.trainedWords || [];
      if (triggers.length) {
        const words = el("div", "lm-quick__triggers");
        triggers.slice(0, 6).forEach((word) => words.appendChild(el("span", "lm-quick__chip", word)));
        this.detailElement.appendChild(words);
      }

      const actions = el("div", "lm-quick__actions");
      const applyButton = el("button", "lm-quick__primary", this.replaceName ? "Replace LoRA" : "Add LoRA");
      applyButton.type = "button";
      applyButton.disabled = !this.targetNode;
      applyButton.addEventListener("click", () => this.apply(false));
      const keepButton = el("button", "lm-quick__secondary", "Apply & keep open");
      keepButton.type = "button";
      keepButton.disabled = !this.targetNode;
      keepButton.addEventListener("click", () => this.apply(true));
      const fullButton = el("button", "lm-quick__secondary", "Full details");
      fullButton.type = "button";
      fullButton.addEventListener("click", () => openLoraManager(details.file_path || ""));
      actions.append(applyButton, keepButton, fullButton);
      this.detailElement.appendChild(actions);
    } catch (error) {
      if (sequence !== this.detailSequence) return;
      this.detailElement.replaceChildren();
      this.detailElement.appendChild(el("div", "lm-quick__empty", `${item.modelName}\n${error.message}`));
    }
  }

  apply(keepOpen) {
    const item = this.selectedItem();
    if (!item) return;
    try {
      if (this.targetNode && app.graph && !compatibleNodes().includes(this.targetNode)) {
        throw new Error("The target node is no longer on this workflow. Reopen Quick Pick from the node.");
      }
      const name = normalizeLoraNameKey(item.relativePath);
      const result = applyQuickLoraSelection(this.targetNode, {
        name,
        strength: recommendedStrength(this.details),
      }, this.replaceName);
      rememberName(name);
      this.refreshAddedMarkers();
      this.setStatus(result.changed ? `Applied ${item.modelName}` : `${item.modelName} is already active`);
      if (this.replaceName || !keepOpen) this.close();
    } catch (error) {
      this.setStatus(error.message);
    }
  }

  onSearchKey(event) {
    if (event.key === "Escape") {
      if (this.searchInput.value) {
        event.preventDefault();
        event.stopPropagation();
        this.searchInput.value = "";
        this.loadSearch();
      }
      return;
    }
    if (event.target === this.targetSelect) return;

    const items = this.navigationItems();
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      if (!items.length) return;
      const direction = event.key === "ArrowDown" ? 1 : -1;
      const next = Math.max(0, Math.min(items.length - 1, this.selectedIndex + direction));
      this.select(next);
      return;
    }
    if (this.isFolderBrowse() && (event.key === "ArrowLeft" || event.key === "ArrowRight")) {
      event.preventDefault();
      if (event.key === "ArrowLeft") {
        this.closeFolder();
      } else {
        const selected = items[this.selectedIndex];
        if (selected?.type === "folder") this.openFolder(selected.path);
      }
      return;
    }
    if (event.key !== "Enter") return;
    if (event.target !== this.searchInput && !this.resultsElement.contains(event.target)) return;
    if (event.target.closest(".lm-quick__folder-back")) return;
    event.preventDefault();
    const selected = items[this.selectedIndex];
    if (selected?.type === "folder") this.openFolder(selected.path);
    else if (selected?.type === "lora") this.apply(event.shiftKey);
  }

  setStatus(message) {
    this.statusElement.textContent = message || "";
  }
}

export function openLoraQuickPanel(options = {}) {
  activeQuickPanel?.close();
  activeQuickPanel = new LoraQuickPanel(options).open();
  return activeQuickPanel;
}

export function closeLoraQuickPanel() {
  activeQuickPanel?.close();
}

export function toggleLoraQuickPanel() {
  if (activeQuickPanel?.panel?.isOpen()) closeLoraQuickPanel();
  else openLoraQuickPanel();
}

app.registerExtension({
  name: "LoraManager.QuickPanel",
  commands: [{
    id: COMMAND_ID,
    label: "Quick LoRA Picker",
    icon: "pi pi-search",
    function: toggleLoraQuickPanel,
  }],
  keybindings: [{ combo: { key: "l", alt: true }, commandId: COMMAND_ID }],
  getNodeMenuItems(node) {
    if (!loraWidget(node)) return [];
    return [null, {
      content: "Quick LoRA Picker",
      callback: () => openLoraQuickPanel({ node }),
    }];
  },
  afterConfigureGraph() {
    closeLoraQuickPanel();
  },
});

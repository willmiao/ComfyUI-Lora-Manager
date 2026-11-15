import { app } from "../../scripts/app.js";
import { createFloatingPanel } from "./floating_panel.js";
import { ensureLmStyles } from "./lm_styles_loader.js";
import { getAllGraphNodes, getWidgetByName } from "./utils.js";
import { applyLoraSelection, applyLoraSet, findLoraIndex } from "./lora_selection.js";
import { normalizeLoraNameKey } from "./loras_widget_utils.js";
import { hasRealPreview, isVideoPreviewUrl } from "./mediaTypes.js";
import { COMMAND_IDS, DEFAULT_KEYBINDINGS } from "./shortcuts.js";
import {
  fetchRecipeDetails,
  openRecipeManager,
  searchRecipes,
} from "./recipe_canvas_api.js";
import {
  appendRecipeRows,
  renderRecipeDetail,
} from "./recipe_quick_view.js";
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

const COMMAND_ID = COMMAND_IDS.quickLoraPicker;
const RECENT_KEY = "lm:quick-panel:recent-loras";
const VIEW_KEY = "lm:quick-panel:view-mode";
const ACTIVE_FILTERS_KEY = "lm:quick-panel:active-filters";
const ASSET_VIEW_KEY = "lm:quick-panel:asset-view";
const RECIPE_PAGE_SIZE = 30;
// Hovering a row this long opens its preview; shorter passes over the list
// should not flash previews for every row the pointer crosses.
const ROW_PREVIEW_DELAY_MS = 400;
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

function itemsByName(items) {
  return new Map(
    (items || []).map((item) => [normalizeLoraNameKey(item.relativePath), item]),
  );
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

/**
 * Write a recipe's LoRA set to a node's widget.
 *
 * `mode` is `append` (keep the node's list, enable/append each recipe entry) or
 * `replace` (rewrite the list to the recipe's available entries).
 */
export function applyQuickLoraSet(node, entries, mode = "append") {
  const widget = loraWidget(node);
  if (!widget) throw new Error("The target node no longer accepts LoRAs");
  const current = Array.isArray(widget.value) ? widget.value : [];
  const result = applyLoraSet(current, entries, { mode });
  if (result.changed) {
    widget.value = result.loras;
    widget.callback?.(result.loras);
    node.setDirtyCanvas?.(true, true);
    app.graph?.setDirtyCanvas?.(true, true);
  }
  return result;
}

export class LoraQuickPanel {
  constructor({ node = null, replaceName = "", initialView = "" } = {}) {
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
    this.assetView = "lora";
    try {
      const requested = initialView || localStorage.getItem(ASSET_VIEW_KEY);
      if (requested === "recipe") this.assetView = "recipe";
    } catch { /* default */ }
    this.recipeItems = [];
    this.recipeDetails = null;
    this.recipeSequence = 0;
    this.recipeDetailSequence = 0;
    this.keyboardWired = false;
    this.previewTooltip = null;
    this.previewTooltipPromise = null;
    this.previewTimer = null;
    this.previewRow = null;
    this.viewMode = "folders";
    try { this.viewMode = localStorage.getItem(VIEW_KEY) === "flat" ? "flat" : "folders"; } catch { /* default */ }
    this.activeFilters = false;
    try { this.activeFilters = localStorage.getItem(ACTIVE_FILTERS_KEY) === "1"; } catch { /* default */ }
    this.activeFilterSnapshot = null;
    this.activeFilterCount = 0;
    this.filterSequence = 0;
    this.folderIndex = null;
    this.libraryCache = null;
    this.folderError = "";
    this.currentFolder = "";
    this.folderSequence = 0;
  }

  open() {
    ensureLmStyles();
    this.panel = createFloatingPanel({
      title: this.panelTitle(),
      context: "",
      className: "lm-quick-panel",
      storageKey: "lm:quick-panel:rect",
      width: 880,
      height: 570,
      minWidth: 600,
      minHeight: 380,
      onClose: () => {
        clearTimeout(this.debounceTimer);
        this.teardownPreview();
        if (activeQuickPanel === this) activeQuickPanel = null;
      },
    });
    this.wirePanelKeyboard();
    this.build();
    this.loadInitialForView();
    setTimeout(() => this.searchInput?.focus(), 20);
    return this;
  }

  close() {
    this.panel?.close();
  }

  panelTitle() {
    return this.assetView === "recipe" ? "Quick Pick · Recipe" : "Quick Pick · LoRA";
  }

  wirePanelKeyboard() {
    if (this.keyboardWired) return;
    this.keyboardWired = true;
    this.panel.element.addEventListener("keydown", (event) => {
      if (event.target !== this.searchInput) this.onSearchKey(event);
    }, true);
  }

  searchPlaceholder() {
    return this.assetView === "recipe"
      ? "Search recipes, tags, LoRA names…"
      : "Search file or model name…";
  }

  footerHints() {
    return this.assetView === "recipe"
      ? "↑↓ Navigate · Enter Append · Shift+Enter Keep open · Esc Close"
      : "↑↓ Navigate · ←→ Folder · Enter Open/Apply · Shift+Enter Keep open · Esc Close";
  }

  loadInitialForView() {
    if (this.assetView === "recipe") {
      this.loadRecipeSearch();
      return;
    }
    this.loadActiveFilters();
    this.loadFolderIndex();
    this.loadSearch();
  }

  loadCurrentSearch() {
    if (this.assetView === "recipe") this.loadRecipeSearch();
    else this.loadSearch();
  }

  setAssetView(view) {
    if (view !== "lora" && view !== "recipe") return;
    if (view === this.assetView) {
      this.searchInput?.focus();
      return;
    }
    this.assetView = view;
    try { localStorage.setItem(ASSET_VIEW_KEY, view); } catch { /* cosmetic only */ }
    clearTimeout(this.debounceTimer);
    this.searchSequence += 1;
    this.detailSequence += 1;
    this.folderSequence += 1;
    this.filterSequence += 1;
    this.recipeSequence += 1;
    this.recipeDetailSequence += 1;
    this.selectedIndex = -1;
    this.recipeItems = [];
    this.recipeDetails = null;
    this.panel.titleElement.textContent = this.panelTitle();
    this.panel.element.setAttribute("aria-label", this.panelTitle());
    this.build();
    this.loadInitialForView();
    setTimeout(() => this.searchInput?.focus(), 20);
  }

  onTargetChanged() {
    const candidates = compatibleNodes();
    this.targetNode = candidates[Number(this.targetSelect.value)] || null;
    this.replaceName = "";
    this.updateContext();
    if (this.assetView === "recipe") {
      this.renderRecipeDetailContent();
    } else {
      this.refreshAddedMarkers();
      this.renderDetail();
    }
  }

  updateContext() {
    const label = this.targetNode
      ? this.assetView === "recipe"
        ? `Apply recipe to ${nodeLabel(this.targetNode)}`
        : `${this.replaceName ? "Replace in" : "Add to"} ${nodeLabel(this.targetNode)}`
      : "No compatible LoRA Manager node on this workflow";
    this.panel?.setContext(label);
  }

  setTargetNode(node) {
    if (!node) return;
    this.targetNode = node;
    this.replaceName = "";
    this.renderTargets();
    this.onTargetChanged();
  }

  build() {
    const { body, footer } = this.panel;
    this.clearRowPreview();
    body.replaceChildren();
    footer.replaceChildren();

    const tabs = el("div", "lm-quick__tabs");
    tabs.setAttribute("role", "tablist");
    tabs.setAttribute("aria-label", "Picker asset type");
    this.assetTabs = {};
    for (const [view, label] of [["lora", "LoRAs"], ["recipe", "Recipes"]]) {
      const button = el("button", "lm-quick__tab", label);
      button.type = "button";
      button.setAttribute("role", "tab");
      button.setAttribute("aria-selected", String(this.assetView === view));
      button.classList.toggle("is-active", this.assetView === view);
      button.addEventListener("click", () => this.setAssetView(view));
      this.assetTabs[view] = button;
      tabs.append(button);
    }

    const toolbar = el("div", "lm-quick__toolbar");
    this.searchInput = el("input", "lm-quick__search");
    this.searchInput.type = "search";
    this.searchInput.placeholder = this.searchPlaceholder();
    this.searchInput.setAttribute(
      "aria-label",
      this.assetView === "recipe" ? "Search recipes" : "Search LoRA library",
    );
    this.searchInput.addEventListener("input", () => {
      clearTimeout(this.debounceTimer);
      this.debounceTimer = setTimeout(() => this.loadCurrentSearch(), 180);
    });
    this.searchInput.addEventListener("keydown", (event) => this.onSearchKey(event));

    this.viewButtons = {};
    this.filterButton = null;
    this.recentButton = null;
    let viewSwitch = null;
    if (this.assetView === "lora") {
      viewSwitch = el("div", "lm-quick__view-switch");
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
      this.recentButton.setAttribute("aria-pressed", String(this.recentOnly));
      this.recentButton.addEventListener("click", () => {
        this.recentOnly = !this.recentOnly;
        this.selectedIndex = this.visibleItems().length ? 0 : -1;
        this.recentButton.classList.toggle("is-active", this.recentOnly);
        this.recentButton.setAttribute("aria-pressed", String(this.recentOnly));
        this.renderResults();
      });
    }

    this.targetSelect = el("select", "lm-quick__target");
    this.targetSelect.setAttribute("aria-label", "Target LoRA node");
    this.targetSelect.addEventListener("change", () => this.onTargetChanged());

    toolbar.append(this.searchInput);
    if (this.assetView === "lora") {
      toolbar.append(viewSwitch, this.filterButton, this.recentButton);
    }
    toolbar.append(this.targetSelect);

    const content = el("div", "lm-quick__content");
    this.resultsElement = el("div", "lm-quick__results");
    this.resultsElement.setAttribute(
      "role",
      "listbox",
      this.assetView === "recipe" ? "Recipe results" : "LoRA results",
    );
    this.resultsElement.addEventListener("mouseover", (event) => this.onRowPointerOver(event));
    this.resultsElement.addEventListener("mouseout", (event) => this.onRowPointerOut(event));
    this.detailElement = el("aside", "lm-quick__detail");
    content.append(this.resultsElement, this.detailElement);
    body.append(tabs, toolbar, content);

    this.statusElement = el("span", "lm-quick__status");
    const hints = el("span", "lm-quick__hints", this.footerHints());
    footer.append(this.statusElement, hints);
    this.renderTargets();
    if (this.assetView === "lora") {
      this.renderFilterButton();
      this.renderDetail();
    } else {
      this.renderRecipeDetailContent();
    }
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
    this.updateContext();
  }

  async loadSearch() {
    const sequence = ++this.searchSequence;
    const query = this.searchInput.value.trim();
    this.setStatus(query ? `Searching “${query}”…` : "Loading library…");
    try {
      const items = await searchLoraLibrary(query, 60, { useActiveFilters: this.activeFilters });
      if (
        sequence !== this.searchSequence
        || !this.panel?.isOpen()
        || this.assetView !== "lora"
      ) return;
      this.items = items;
      this.selectedIndex = items.length ? 0 : -1;
      this.renderResults();
      const scope = this.activeFilters ? " within active filters" : "";
      this.setStatus(items.length
        ? `${items.length} result${items.length === 1 ? "" : "s"}${scope}`
        : `No matching LoRAs${scope}`);
    } catch (error) {
      if (sequence !== this.searchSequence) return;
      if (this.assetView !== "lora") return;
      this.items = [];
      this.selectedIndex = -1;
      this.renderResults();
      this.setStatus(error.message);
    }
  }

  async loadRecipeSearch() {
    const sequence = ++this.recipeSequence;
    const query = this.searchInput.value.trim();
    this.setStatus(query ? `Searching “${query}”…` : "Loading recipes…");
    try {
      const items = await searchRecipes(query, RECIPE_PAGE_SIZE);
      if (
        sequence !== this.recipeSequence
        || !this.panel?.isOpen()
        || this.assetView !== "recipe"
      ) return;
      this.recipeItems = items;
      this.selectedIndex = items.length ? 0 : -1;
      this.recipeDetails = null;
      this.renderRecipeResults();
      const suffix = query ? ` for “${query}”` : "";
      this.setStatus(items.length
        ? `${items.length} recipe${items.length === 1 ? "" : "s"}${suffix}`
        : `No recipes match${suffix}`);
    } catch (error) {
      if (sequence !== this.recipeSequence) return;
      if (this.assetView !== "recipe") return;
      this.recipeItems = [];
      this.selectedIndex = -1;
      this.renderRecipeResults();
      this.setStatus(error.message);
    }
  }

  selectedRecipe() {
    if (this.assetView !== "recipe") return null;
    return this.recipeItems[this.selectedIndex] || null;
  }

  renderRecipeResults() {
    this.clearRowPreview();
    this.resultsElement.replaceChildren();
    if (!this.recipeItems.length) {
      const query = this.searchInput?.value.trim() || "";
      const message = el("div", "lm-quick__empty");
      message.textContent = query
        ? `No recipes match “${query}”.`
        : "No recipes yet. Save one from the LoRA widget or the manager.";
      if (!query) {
        const open = el("button", "lm-quick__secondary", "Open LoRA Manager");
        open.type = "button";
        open.addEventListener("click", () => openRecipeManager(""));
        message.appendChild(document.createElement("br"));
        message.appendChild(open);
      }
      this.resultsElement.appendChild(message);
      this.renderRecipeDetailContent();
      return;
    }
    if (this.selectedIndex < 0 || this.selectedIndex >= this.recipeItems.length) {
      this.selectedIndex = 0;
    }
    appendRecipeRows({
      container: this.resultsElement,
      recipes: this.recipeItems,
      selectedIndex: this.selectedIndex,
      onSelect: (index) => this.select(index),
      onActivate: (index) => {
        this.select(index);
        this.applyRecipe("append", false);
      },
    });
    this.renderRecipeDetail();
  }

  async renderRecipeDetail() {
    const sequence = ++this.recipeDetailSequence;
    const recipe = this.selectedRecipe();
    this.recipeDetails = null;
    if (!recipe) {
      this.renderRecipeDetailContent();
      return;
    }
    renderRecipeDetail({
      container: this.detailElement,
      recipe,
      targetNode: this.targetNode,
      loading: true,
      onApply: (mode) => this.applyRecipe(mode, false),
      onOpen: (recipeId) => openRecipeManager(recipeId),
    });
    try {
      const details = await fetchRecipeDetails(recipe.id);
      if (
        sequence !== this.recipeDetailSequence
        || !this.panel?.isOpen()
        || this.assetView !== "recipe"
      ) return;
      this.recipeDetails = details;
      this.renderRecipeDetailContent();
    } catch (error) {
      if (sequence !== this.recipeDetailSequence) return;
      this.renderRecipeDetailContent(error.message);
    }
  }

  renderRecipeDetailContent(error = "") {
    const recipe = this.recipeDetails || this.selectedRecipe();
    renderRecipeDetail({
      container: this.detailElement,
      recipe,
      targetNode: this.targetNode,
      error,
      onApply: (mode) => this.applyRecipe(mode, false),
      onOpen: (recipeId) => openRecipeManager(recipeId),
    });
  }

  applyRecipe(mode = "append", keepOpen = false) {
    const recipe = this.recipeDetails || this.selectedRecipe();
    if (!recipe) return;
    if (!this.targetNode) {
      this.setStatus("Select a LoRA node to apply this recipe.");
      return;
    }
    try {
      if (app.graph && !compatibleNodes().includes(this.targetNode)) {
        throw new Error("The target node is no longer on this workflow. Reopen Quick Pick from the node.");
      }
      const result = applyQuickLoraSet(this.targetNode, recipe.loras, mode);
      const skipped = result.skipped ? ` · ${result.skipped} skipped` : "";
      if (!result.applied) {
        this.setStatus(`No available LoRAs in this recipe${skipped}`);
        return;
      }
      if (!result.changed) {
        this.setStatus(`Recipe is already applied${skipped}`);
        return;
      }
      const verb = mode === "replace" ? "Replaced with" : "Applied";
      this.setStatus(`${verb} ${result.applied} LoRA${result.applied === 1 ? "" : "s"}${skipped}`);
      if (!keepOpen) this.close();
    } catch (error) {
      this.setStatus(error.message);
    }
  }

  async loadFolderIndex() {
    const sequence = ++this.folderSequence;
    try {
      const root = await fetchLoraFolderIndex({ useActiveFilters: this.activeFilters });
      if (
        sequence !== this.folderSequence
        || !this.panel?.isOpen()
        || this.assetView !== "lora"
      ) return;
      this.folderIndex = root;
      this.folderError = "";
      this.renderResults();
    } catch (error) {
      if (sequence !== this.folderSequence) return;
      if (this.assetView !== "lora") return;
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
    if (this.assetView !== "lora") return;
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

  /**
   * Flat name → item map over the whole folder index, cached per index
   * snapshot so navigation is not penalized.
   */
  libraryByName() {
    if (!this.folderIndex) return null;
    if (this.libraryCache?.source === this.folderIndex) return this.libraryCache.byName;
    const byName = new Map();
    const walk = (node) => {
      for (const item of node?.items || []) {
        byName.set(normalizeLoraNameKey(item.relativePath), item);
      }
      for (const child of Object.values(node?.folders || {})) walk(child);
    };
    walk(this.folderIndex);
    this.libraryCache = { source: this.folderIndex, byName };
    return byName;
  }

  /**
   * Recently applied LoRAs, newest first, resolved against the whole library
   * (via the folder index) instead of the loaded search page: that page is
   * capped at 60 rows, so a recent LoRA often lives outside it. A search
   * query narrows the history to the matching loaded results. While the
   * folder index is still loading, fall back to the loaded page; the index
   * load re-renders the list once it arrives.
   */
  recentItems() {
    const names = recentNames();
    if (!names.length) return [];
    const query = this.searchInput?.value.trim() || "";
    const byName = query
      ? itemsByName(this.items)
      : this.libraryByName() || itemsByName(this.items);
    return names.map((name) => byName.get(normalizeLoraNameKey(name))).filter(Boolean);
  }

  visibleItems() {
    if (this.isFolderBrowse()) return this.currentFolderNode()?.items || [];
    if (!this.recentOnly) return this.items;
    return this.recentItems();
  }

  navigationItems() {
    if (this.assetView === "recipe") {
      return this.recipeItems.map((item) => ({ type: "recipe", item }));
    }
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

  /** The `lora:`/`recipe:` key identifying the row's preview, if it has one. */
  previewKeyForRow(row) {
    if (row.dataset.recipeId) return `recipe:${row.dataset.recipeId}`;
    if (row.dataset.loraPath) return `lora:${row.dataset.loraPath}`;
    return "";
  }

  onRowPointerOver(event) {
    const row = event.target?.closest?.(".lm-quick__row");
    if (!row || row === this.previewRow) return;
    this.startRowPreview(row);
  }

  onRowPointerOut(event) {
    const row = event.target?.closest?.(".lm-quick__row");
    if (!row || row !== this.previewRow) return;
    const next = event.relatedTarget;
    if (next && row.contains(next)) return;
    this.clearRowPreview();
  }

  /**
   * Wait out a short hover before showing the preview, so moving the pointer
   * across the list does not open a tooltip for every row it crosses.
   */
  startRowPreview(row) {
    const key = this.previewKeyForRow(row);
    if (!key) {
      this.clearRowPreview();
      return;
    }
    this.previewRow = row;
    clearTimeout(this.previewTimer);
    this.previewTimer = setTimeout(() => {
      this.previewTimer = null;
      void this.showRowPreview(row, key);
    }, ROW_PREVIEW_DELAY_MS);
  }

  clearRowPreview() {
    clearTimeout(this.previewTimer);
    this.previewTimer = null;
    this.previewRow = null;
    this.previewTooltip?.hide();
  }

  async showRowPreview(row, key) {
    if (this.previewRow !== row) return;
    const tooltip = await this.ensurePreviewTooltip();
    // The pointer may have left while the tooltip module was loading.
    if (!tooltip || this.previewRow !== row) return;
    const rect = row.getBoundingClientRect();
    await tooltip.show(key, rect.right, rect.top);
  }

  /**
   * Create the shared preview tooltip on first hover. Loading it lazily keeps
   * the picker's startup free of the tooltip and license-icon modules.
   */
  ensurePreviewTooltip() {
    if (this.previewTooltip) return Promise.resolve(this.previewTooltip);
    if (!this.previewTooltipPromise) {
      this.previewTooltipPromise = import("./preview_tooltip.js")
        .then(({ PreviewTooltip, fetchModelPreviewData }) => {
          this.previewTooltipPromise = null;
          if (!this.panel?.isOpen()) return null;
          this.previewTooltip = new PreviewTooltip({
            modelType: "loras",
            // The tooltip is appended to <body>, so without this modifier the
            // floating panel (z-index 10020) would cover it.
            className: "lm-tooltip--elevated",
            // Keep the preview over the results column: the detail column
            // holds the selected item's overview and its action buttons.
            positionBoundary: () => this.resultsElement?.getBoundingClientRect() || null,
            previewUrlResolver: (key) => this.resolveRowPreview(key, fetchModelPreviewData),
          });
          return this.previewTooltip;
        })
        .catch((error) => {
          this.previewTooltipPromise = null;
          console.warn("Failed to load the preview tooltip:", error);
          return null;
        });
    }
    return this.previewTooltipPromise;
  }

  /**
   * Resolve the hovered row's preview. LoRAs reuse the same preview-url
   * endpoint as the autocomplete; recipes carry their preview in the list
   * payload, so opening a recipe tooltip needs no request.
   */
  async resolveRowPreview(key, fetchPreview) {
    const separator = key.indexOf(":");
    if (separator < 0) return null;
    const kind = key.slice(0, separator);
    const value = key.slice(separator + 1);
    if (kind === "recipe") {
      const recipe = this.recipeItems.find((entry) => String(entry.id) === value);
      if (!hasRealPreview(recipe?.fileUrl)) return null;
      return { previewUrl: recipe.fileUrl, displayName: recipe.title };
    }
    if (kind !== "lora" || !value) return null;
    const data = await fetchPreview("loras", value);
    if (!data || !hasRealPreview(data.previewUrl)) return null;
    return {
      ...data,
      displayName: this.findLoraItem(value)?.modelName || data.displayName || value,
    };
  }

  findLoraItem(relativePath) {
    const loaded = this.items.find((item) => item.relativePath === relativePath);
    if (loaded) return loaded;
    return this.libraryByName()?.get(normalizeLoraNameKey(relativePath)) || null;
  }

  teardownPreview() {
    this.clearRowPreview();
    this.previewTooltip?.cleanup();
    this.previewTooltip = null;
    this.previewTooltipPromise = null;
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
    this.clearRowPreview();
    if (this.assetView === "recipe") {
      this.renderRecipeResults();
      return;
    }
    if (this.isFolderBrowse()) {
      this.renderFolderResults();
      return;
    }
    const visible = this.visibleItems();
    this.resultsElement.replaceChildren();
    if (!visible.length) {
      let message = "No LoRAs to show. Try another search or clear Recent.";
      if (this.recentOnly) {
        message = this.searchInput?.value.trim()
          ? "No recently applied LoRAs match this search."
          : "No recently applied LoRAs yet. Apply one from this picker to build the list.";
      }
      this.resultsElement.appendChild(el("div", "lm-quick__empty", message));
      if (this.recentOnly) this.setStatus("No recently applied LoRAs");
      this.renderDetail();
      return;
    }
    if (this.selectedIndex >= visible.length) this.selectedIndex = 0;
    if (this.recentOnly) {
      this.setStatus(`${visible.length} recently applied LoRA${visible.length === 1 ? "" : "s"}`);
    }
    this.appendLoraRows(visible);
    this.renderDetail();
  }

  select(index) {
    const changed = index !== this.selectedIndex;
    this.selectedIndex = index;
    const rows = this.resultsElement.querySelectorAll(".lm-quick__folder-row, .lm-quick__row");
    rows.forEach((row, rowIndex) => {
      row.classList.toggle("is-selected", rowIndex === index);
      row.setAttribute("aria-selected", String(rowIndex === index));
    });
    rows[index]?.scrollIntoView({ block: "nearest" });
    // Re-selecting the same row (arrow key held at a list edge, clicking the
    // current row) must not replay the detail fetch: the "Loading local
    // details…" placeholder made a clamped key press look like a duplicate row.
    if (changed) this.renderDetail();
  }

  selectedItem() {
    const selected = this.navigationItems()[this.selectedIndex];
    return selected?.type === "lora" ? selected.item : null;
  }

  async renderDetail() {
    if (this.assetView === "recipe") {
      await this.renderRecipeDetail();
      return;
    }
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
    if (this.assetView !== "lora") return;
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
      if (this.recentOnly) {
        // The applied LoRA moved to the top of the history: rebuild so
        // "Apply & keep open" shows the new order and contents.
        this.selectedIndex = 0;
        this.renderResults();
      }
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
        this.loadCurrentSearch();
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
      // Keep the selection pinned at the first/last row instead of re-selecting
      // it. A no-op matches native autocomplete dropdowns, so the edge is
      // signalled by the highlight no longer moving — not by a re-load.
      if (next !== this.selectedIndex) this.select(next);
      return;
    }
    if (
      this.assetView === "lora"
      && this.isFolderBrowse()
      && (event.key === "ArrowLeft" || event.key === "ArrowRight")
    ) {
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
    if (this.assetView === "lora" && event.target.closest(".lm-quick__folder-back")) return;
    event.preventDefault();
    if (this.assetView === "recipe") {
      this.applyRecipe("append", event.shiftKey);
      return;
    }
    const selected = items[this.selectedIndex];
    if (selected?.type === "folder") this.openFolder(selected.path);
    else if (selected?.type === "lora") this.apply(event.shiftKey);
  }

  setStatus(message) {
    this.statusElement.textContent = message || "";
  }
}

function openQuickPanel(options = {}, view) {
  if (activeQuickPanel?.panel?.isOpen()) {
    activeQuickPanel.setAssetView(view);
    if (options?.node) activeQuickPanel.setTargetNode(options.node);
    if (options?.replaceName && view === "lora") {
      activeQuickPanel.replaceName = options.replaceName;
      activeQuickPanel.updateContext();
    }
    activeQuickPanel.searchInput?.focus();
    return activeQuickPanel;
  }
  activeQuickPanel = new LoraQuickPanel({ ...options, initialView: view }).open();
  return activeQuickPanel;
}

export function openLoraQuickPanel(options = {}) {
  return openQuickPanel(options, "lora");
}

export function openRecipeQuickPanel(options = {}) {
  return openQuickPanel(options, "recipe");
}

export function closeLoraQuickPanel() {
  activeQuickPanel?.close();
}

export function closeRecipeQuickPanel() {
  activeQuickPanel?.close();
}

export function closeQuickPanel() {
  activeQuickPanel?.close();
}

export function toggleLoraQuickPanel() {
  if (activeQuickPanel?.panel?.isOpen() && activeQuickPanel.assetView === "lora") {
    closeQuickPanel();
  } else {
    openLoraQuickPanel();
  }
}

export function toggleRecipeQuickPanel() {
  if (activeQuickPanel?.panel?.isOpen() && activeQuickPanel.assetView === "recipe") {
    closeQuickPanel();
  } else {
    openRecipeQuickPanel();
  }
}

app.registerExtension({
  name: "LoraManager.QuickPanel",
  commands: [{
    id: COMMAND_ID,
    label: "Quick LoRA Picker",
    icon: "pi pi-search",
    function: toggleLoraQuickPanel,
  }],
  keybindings: [{ combo: DEFAULT_KEYBINDINGS[COMMAND_ID], commandId: COMMAND_ID }],
  getNodeMenuItems(node) {
    if (!loraWidget(node)) return [];
    return [null, {
      content: "Quick LoRA Picker",
      callback: () => openLoraQuickPanel({ node }),
    }];
  },
  afterConfigureGraph() {
    closeQuickPanel();
  },
});

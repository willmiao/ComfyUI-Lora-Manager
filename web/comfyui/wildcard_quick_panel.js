import { createFloatingPanel } from "./floating_panel.js";
import { ensureLmStyles } from "./lm_styles_loader.js";
import {
  openWildcardManager,
  searchWildcardLibrary,
  setWildcardActive,
} from "./wildcard_canvas_api.js";

function el(tag, className, text) {
  const element = document.createElement(tag);
  if (className) element.className = className;
  if (text !== undefined) element.textContent = text;
  return element;
}

let activePanel = null;

export class WildcardQuickPanel {
  constructor() {
    this.items = [];
    this.manual = [];
    this.selected = null;
    this.activeOnly = true;
    this.searchSequence = 0;
    this.panel = null;
  }

  open() {
    ensureLmStyles();
    this.panel = createFloatingPanel({
      title: "Global Wildcards",
      context: "Activation affects autocomplete and subsequent executions",
      className: "lm-quick-panel lm-wildcard-quick-panel",
      storageKey: "lm:quick-panel:wildcards-rect",
      width: 850,
      height: 560,
      minWidth: 580,
      minHeight: 360,
      onClose: () => {
        if (activePanel === this) activePanel = null;
      },
    });
    this.build();
    this.load();
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
    const toolbar = el("div", "lm-quick__toolbar");
    this.searchInput = el("input", "lm-quick__search");
    this.searchInput.type = "search";
    this.searchInput.placeholder = "Search resources or wildcard keys…";
    this.searchInput.addEventListener("input", () => {
      clearTimeout(this.debounceTimer);
      this.debounceTimer = setTimeout(() => this.load(), 180);
    });
    this.scopeButton = el("button", "lm-quick__filter is-active", "Active");
    this.scopeButton.type = "button";
    this.scopeButton.title = "Toggle between active resources and the full local library";
    this.scopeButton.addEventListener("click", () => {
      this.activeOnly = !this.activeOnly;
      this.scopeButton.classList.toggle("is-active", this.activeOnly);
      this.scopeButton.textContent = this.activeOnly ? "Active" : "Library";
      this.render();
    });
    const managerButton = el("button", "lm-quick__filter", "Open Manager");
    managerButton.type = "button";
    managerButton.addEventListener("click", () => openWildcardManager(this.selected?.file_path || ""));
    toolbar.append(this.searchInput, this.scopeButton, managerButton);
    const content = el("div", "lm-quick__content");
    this.resultsElement = el("div", "lm-quick__results");
    this.detailElement = el("aside", "lm-quick__detail");
    content.append(this.resultsElement, this.detailElement);
    body.append(toolbar, content);
    this.statusElement = el("span", "lm-quick__status", "Loading…");
    footer.append(this.statusElement, el("span", "lm-quick__hints", "Global activation · Esc Close"));
  }

  async load() {
    const sequence = ++this.searchSequence;
    try {
      const data = await searchWildcardLibrary(this.searchInput?.value || "");
      if (sequence !== this.searchSequence) return;
      this.items = data.resources || [];
      this.manual = data.manual?.entries || [];
      this.conflicts = data.runtime_conflicts || [];
      if (this.selected) {
        this.selected = this.items.find((item) => item.file_path === this.selected.file_path) || null;
      }
      if (!this.selected) this.selected = this.visibleItems()[0] || null;
      this.render();
    } catch (error) {
        this.statusElement.textContent = error.message;
    }
  }

  visibleItems() {
    return this.activeOnly ? this.items.filter((item) => item.active) : this.items;
  }

  render() {
    if (!this.panel) return;
    const items = this.visibleItems();
    this.resultsElement.replaceChildren();
    for (const resource of items) {
      const row = el("div", "lm-quick__row");
      row.classList.toggle("is-selected", this.selected?.file_path === resource.file_path);
      const select = el("button", "lm-quick__row-main");
      select.type = "button";
      select.append(
        el("span", "lm-quick__row-title", resource.model_name || resource.file_name),
        el("span", "lm-quick__row-subtitle", `${resource.entry_count || 0} keys · ${resource.file_name}`),
      );
      select.addEventListener("click", () => {
        this.selected = resource;
        this.render();
      });
      const toggle = el("button", "lm-quick__filter", resource.active ? "On" : "Add");
      toggle.type = "button";
      toggle.title = resource.active ? "Deactivate globally" : "Activate from the local library";
      toggle.addEventListener("click", () => this.toggle(resource));
      row.append(select, toggle);
      this.resultsElement.append(row);
    }
    if (!items.length) {
      this.resultsElement.append(el("p", "lm-quick__empty", this.activeOnly ? "No managed wildcards are active" : "No wildcard resources found"));
    }
    if (this.activeOnly && this.manual.length) {
      const manual = el("div", "lm-quick__row lm-wildcard-quick-panel__manual");
      manual.append(el("span", "lm-quick__row-title", `Manual files · ${this.manual.length} keys`));
      manual.title = this.manual.map((entry) => entry.key).join("\n");
      this.resultsElement.append(manual);
    }
    const activeCount = this.items.filter((item) => item.active).length;
    this.statusElement.textContent = `${activeCount} active resources · ${this.manual.length} manual keys${this.conflicts?.length ? ` · ${this.conflicts.length} conflicts` : ""}`;
    this.renderDetail();
  }

  renderDetail() {
    this.detailElement.replaceChildren();
    const resource = this.selected;
    if (!resource) {
      this.detailElement.append(el("p", "lm-quick__empty", "Select a resource to inspect its wildcard keys"));
      return;
    }
    this.detailElement.append(
      el("h3", "lm-quick__detail-title", resource.model_name),
      el("p", "lm-quick__detail-subtitle", `${resource.active ? "Active" : "Inactive"} · ${resource.value_count || 0} values`),
    );
    const keys = el("div", "lm-wildcard-quick-panel__keys");
    for (const entry of (resource.entries || []).slice(0, 250)) {
      const key = el("button", "lm-wildcard-quick-panel__key", entry.effective_key || entry.key);
      key.type = "button";
      key.title = "Copy wildcard syntax";
      key.addEventListener("click", async () => {
        await navigator.clipboard?.writeText(`__${entry.effective_key || entry.key}__`);
        this.statusElement.textContent = `Copied __${entry.effective_key || entry.key}__`;
      });
      keys.append(key);
    }
    this.detailElement.append(keys);
  }

  async toggle(resource) {
    try {
      await setWildcardActive(resource.file_path, !resource.active);
      await this.load();
    } catch (error) {
      const conflicts = error.payload?.conflicts || [];
      this.statusElement.textContent = conflicts.length
        ? `Key conflict: ${conflicts.map((item) => item.key).join(", ")}. Open Manager to rename.`
        : error.message;
    }
  }
}

export function openWildcardQuickPanel() {
  if (!activePanel) activePanel = new WildcardQuickPanel().open();
  return activePanel;
}

export function reloadWildcardQuickPanel() {
  return activePanel?.load();
}

export function toggleWildcardQuickPanel() {
  if (activePanel) activePanel.close();
  else openWildcardQuickPanel();
}

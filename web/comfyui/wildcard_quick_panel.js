import { createFloatingPanel } from "./floating_panel.js";
import { ensureLmStyles } from "./lm_styles_loader.js";
import { hasRealPreview, isVideoPreviewUrl } from "./mediaTypes.js";
import {
  openWildcardManager,
  openWildcardsFolder,
  searchWildcardLibrary,
  setWildcardActive,
} from "./wildcard_canvas_api.js";

const SCOPE_KEY = "lm:quick-panel:wildcards-scope";
const MANUAL_COLLAPSED_KEY = "lm:quick-panel:wildcards-manual-collapsed";
// Hovering a row this long opens its preview; shorter passes over the list
// should not flash previews for every row the pointer crosses.
const ROW_PREVIEW_DELAY_MS = 400;
const MAX_RENDERED_KEYS = 300;
const COPY_ICON =
  '<svg viewBox="0 0 16 16" width="11" height="11" fill="none" stroke="currentColor" stroke-width="1.4" aria-hidden="true">' +
  '<rect x="5.5" y="5.5" width="8" height="8" rx="1.2"></rect>' +
  '<path d="M10.5 3.5V2.7A1.2 1.2 0 0 0 9.3 1.5H2.7A1.2 1.2 0 0 0 1.5 2.7v6.6a1.2 1.2 0 0 0 1.2 1.2h.8"></path>' +
  "</svg>";

let activePanel = null;

function el(tag, className, text) {
  const element = document.createElement(tag);
  if (className) element.className = className;
  if (text !== undefined) element.textContent = text;
  return element;
}

function readStorage(key, fallback) {
  try {
    return localStorage.getItem(key) ?? fallback;
  } catch {
    return fallback;
  }
}

function writeStorage(key, value) {
  try {
    localStorage.setItem(key, value);
  } catch {
    /* cosmetic only */
  }
}

function plural(count, singular, pluralForm = `${singular}s`) {
  return `${count} ${count === 1 ? singular : pluralForm}`;
}

function formatCount(value) {
  return Number(value || 0).toLocaleString();
}

function copyIcon() {
  const span = el("span", "lm-wildcard-key-copy");
  span.setAttribute("aria-hidden", "true");
  span.innerHTML = COPY_ICON;
  return span;
}

export class WildcardQuickPanel {
  constructor() {
    this.items = [];
    this.manual = [];
    this.conflicts = [];
    this.selected = null;
    this.scope = readStorage(SCOPE_KEY, "all") === "active" ? "active" : "all";
    this.manualCollapsed = readStorage(MANUAL_COLLAPSED_KEY, "0") === "1";
    this.searchQuery = "";
    this.searchSequence = 0;
    this.keyFilter = "";
    this.loadError = "";
    this.activationError = null;
    this.activationInFlight = null;
    this.panel = null;
    this.searchInput = null;
    this.resultsElement = null;
    this.detailElement = null;
    this.statusElement = null;
    this.hintsElement = null;
    this.scopeButtons = {};
    this.previewTooltip = null;
    this.previewTooltipPromise = null;
    this.previewTimer = null;
    this.previewRow = null;
    this.debounceTimer = null;
    this.keyboardWired = false;
  }

  open() {
    ensureLmStyles();
    this.panel = createFloatingPanel({
      title: "Global Wildcards",
      context: "Activation affects autocomplete and subsequent executions",
      className: "lm-quick-panel lm-wildcard-quick-panel",
      storageKey: "lm:quick-panel:wildcards-rect",
      width: 880,
      height: 570,
      minWidth: 600,
      minHeight: 380,
      onClose: () => {
        clearTimeout(this.debounceTimer);
        this.teardownPreview();
        if (activePanel === this) activePanel = null;
      },
    });
    this.wirePanelKeyboard();
    this.build();
    this.load();
    setTimeout(() => this.searchInput?.focus(), 20);
    return this;
  }

  close() {
    this.panel?.close();
  }

  wirePanelKeyboard() {
    if (this.keyboardWired) return;
    this.keyboardWired = true;
    this.panel.element.addEventListener(
      "keydown",
      (event) => this.onKeyDown(event),
      true,
    );
  }

  build() {
    const { body, footer } = this.panel;
    body.replaceChildren();
    footer.replaceChildren();

    const toolbar = el("div", "lm-quick__toolbar");
    this.searchInput = el("input", "lm-quick__search");
    this.searchInput.type = "search";
    this.searchInput.placeholder = "Search resources or wildcard keys…";
    this.searchInput.setAttribute("aria-label", "Search wildcards");
    this.searchInput.addEventListener("input", () => {
      clearTimeout(this.debounceTimer);
      this.debounceTimer = setTimeout(() => {
        this.searchQuery = this.searchInput.value.trim();
        if (this.searchQuery && this.manualCollapsed) {
          // A search must reveal matching manual keys; the user can collapse
          // the group again once the query is cleared.
          this.manualCollapsed = false;
          writeStorage(MANUAL_COLLAPSED_KEY, "0");
        }
        this.load();
      }, 180);
    });

    const scopeSwitch = el("div", "lm-quick__view-switch");
    scopeSwitch.setAttribute("role", "group");
    scopeSwitch.setAttribute("aria-label", "Wildcard scope");
    this.scopeButtons = {};
    for (const [scope, label] of [["all", "All"], ["active", "Active"]]) {
      const button = el("button", "lm-quick__view-button", label);
      button.type = "button";
      button.dataset.scope = scope;
      button.addEventListener("click", () => this.setScope(scope));
      this.scopeButtons[scope] = button;
      scopeSwitch.appendChild(button);
    }
    toolbar.append(this.searchInput, scopeSwitch);

    const content = el("div", "lm-quick__content");
    this.resultsElement = el("div", "lm-quick__results");
    this.resultsElement.setAttribute("role", "listbox");
    this.resultsElement.setAttribute(
      "aria-label",
      "Wildcard resources and manual keys",
    );
    this.resultsElement.addEventListener("mouseover", (event) =>
      this.onRowPointerOver(event),
    );
    this.resultsElement.addEventListener("mouseout", (event) =>
      this.onRowPointerOut(event),
    );
    this.resultsElement.addEventListener("scroll", () => this.clearRowPreview(), true);
    this.detailElement = el("aside", "lm-quick__detail");
    this.detailElement.setAttribute("aria-live", "polite");
    content.append(this.resultsElement, this.detailElement);
    body.append(toolbar, content);

    this.statusElement = el("span", "lm-quick__status", "Loading wildcards…");
    this.statusElement.setAttribute("aria-live", "polite");
    this.hintsElement = el("span", "lm-quick__hints", this.defaultHints());
    footer.append(this.statusElement, this.hintsElement);
    this.renderScopeButtons();
  }

  defaultHints() {
    return "↑↓ Navigate · Enter Activate · Esc Close";
  }

  manualHints() {
    return "↑↓ Navigate · Enter Copy · Esc Close";
  }

  updateHints() {
    if (!this.hintsElement) return;
    this.hintsElement.textContent =
      this.selected?.kind === "manual" ? this.manualHints() : this.defaultHints();
  }

  setStatus(message) {
    if (this.statusElement) this.statusElement.textContent = message || "";
  }

  renderScopeButtons() {
    for (const [scope, button] of Object.entries(this.scopeButtons)) {
      const active = scope === this.scope;
      button.classList.toggle("is-active", active);
      button.setAttribute("aria-pressed", String(active));
    }
  }

  setScope(scope) {
    const next = scope === "active" ? "active" : "all";
    if (next === this.scope) return;
    this.scope = next;
    writeStorage(SCOPE_KEY, next);
    this.renderScopeButtons();
    this.render();
  }

  visibleResources() {
    const query = this.searchQuery.toLowerCase();
    return this.items.filter((item) => {
      if (this.scope === "active" && !item.active) return false;
      if (!query) return true;
      const keys = (item.entries || [])
        .map((entry) => `${entry.key || ""} ${entry.effective_key || ""}`)
        .join(" ");
      return `${item.model_name || ""} ${item.file_name || ""} ${keys}`
        .toLowerCase()
        .includes(query);
    });
  }

  visibleManual() {
    const query = this.searchQuery.toLowerCase();
    if (!query) return this.manual;
    return this.manual.filter((entry) =>
      `${entry.key || ""} ${(entry.sample_values || []).join(" ")}`
        .toLowerCase()
        .includes(query),
    );
  }

  reconcileSelection() {
    const resources = this.visibleResources();
    const manual = this.visibleManual();
    if (this.selected?.kind === "resource") {
      const item = resources.find(
        (entry) => entry.file_path === this.selected.filePath,
      );
      if (item) return;
    } else if (this.selected?.kind === "manual") {
      const entry = manual.find((item) => item.key === this.selected.key);
      if (entry) return;
    }
    const firstResource = resources[0];
    const firstManual = manual[0];
    const next = firstResource
      ? { kind: "resource", filePath: firstResource.file_path }
      : firstManual
        ? { kind: "manual", key: firstManual.key }
        : null;
    if (next) this.keyFilter = "";
    this.selected = next;
  }

  selectedItem() {
    if (!this.selected) return null;
    if (this.selected.kind === "manual") {
      return this.manual.find((entry) => entry.key === this.selected.key) || null;
    }
    return (
      this.items.find((item) => item.file_path === this.selected.filePath) || null
    );
  }

  async load({ preserveSelection = true } = {}) {
    const sequence = ++this.searchSequence;
    if (!preserveSelection) this.selected = null;
    this.loadError = "";
    this.setStatus(
      this.searchQuery ? `Searching “${this.searchQuery}”…` : "Loading wildcards…",
    );
    try {
      const data = await searchWildcardLibrary(this.searchQuery);
      if (sequence !== this.searchSequence || !this.panel?.isOpen()) return;
      this.items = Array.isArray(data.resources) ? data.resources : [];
      this.manual = Array.isArray(data.manual?.entries)
        ? data.manual.entries
        : [];
      this.conflicts = Array.isArray(data.runtime_conflicts)
        ? data.runtime_conflicts
        : [];
      this.activationError = null;
      this.reconcileSelection();
      this.render();
    } catch (error) {
      if (sequence !== this.searchSequence || !this.panel?.isOpen()) return;
      this.loadError = error.message || "Unable to load wildcards";
      this.items = [];
      this.manual = [];
      this.conflicts = [];
      this.selected = null;
      this.render();
    }
  }

  render() {
    if (!this.panel) return;
    this.clearRowPreview();
    const resultsScroll = this.resultsElement.scrollTop;
    const focusInResults = this.resultsElement.contains(document.activeElement);
    const focusInDetail = this.detailElement.contains(document.activeElement);
    this.reconcileSelection();
    this.renderResults();
    this.resultsElement.scrollTop = resultsScroll;
    this.renderDetail();
    if (focusInResults) {
      const selectedRow = this.resultsElement.querySelector(
        ".lm-quick__row.is-selected",
      );
      (selectedRow || this.searchInput)?.focus({ preventScroll: true });
    } else if (focusInDetail) {
      this.searchInput?.focus({ preventScroll: true });
    }
    this.renderStatus();
    this.updateHints();
  }

  renderResults() {
    this.resultsElement.replaceChildren();
    if (this.loadError) {
      const empty = el("div", "lm-quick__empty");
      empty.append(el("div", "", this.loadError));
      const retry = el("button", "lm-quick__secondary", "Retry");
      retry.type = "button";
      retry.addEventListener("click", () => this.load());
      empty.append(retry);
      this.resultsElement.appendChild(empty);
      return;
    }

    const resources = this.visibleResources();
    const active = resources.filter((item) => item.active);
    const library =
      this.scope === "all" ? resources.filter((item) => !item.active) : [];
    const manual = this.visibleManual();

    if (!active.length && !library.length && !manual.length) {
      this.appendEmptyState();
      return;
    }

    if (!active.length && !library.length && manual.length) {
      const note = el("div", "lm-quick__empty lm-quick__empty--inline");
      const noteText = this.searchQuery
        ? "No managed resources match this search."
        : this.scope === "active"
          ? "No managed wildcards are active."
          : "No managed wildcard resources.";
      note.appendChild(el("span", "", noteText));
      if (this.scope === "active" && this.items.some((item) => !item.active)) {
        const showAll = el("button", "lm-quick__secondary", "Show all");
        showAll.type = "button";
        showAll.addEventListener("click", () => this.setScope("all"));
        note.appendChild(showAll);
      }
      this.resultsElement.appendChild(note);
    }

    if (active.length) {
      this.appendSection("Active", active.length, active.map((item) => this.createResourceRow(item)));
    }
    if (library.length) {
      this.appendSection("Library", library.length, library.map((item) => this.createResourceRow(item)));
    }
    if (manual.length) {
      this.appendManualSection(manual);
    }
  }

  appendSection(title, count, rows) {
    const section = el("section", "lm-quick__section");
    const head = el("div", "lm-quick__section-head");
    head.append(
      el("span", "", title),
      el("span", "lm-quick__section-count", String(count)),
    );
    const body = el("div", "lm-quick__section-body");
    rows.forEach((row) => body.appendChild(row));
    section.append(head, body);
    this.resultsElement.appendChild(section);
  }

  appendManualSection(entries) {
    const section = el("section", "lm-quick__section lm-quick__section--manual");
    if (this.manualCollapsed) section.classList.add("is-collapsed");
    const head = el("div", "lm-quick__section-head");
    const toggle = el("button", "lm-quick__section-toggle", "▾");
    toggle.type = "button";
    toggle.setAttribute("aria-expanded", String(!this.manualCollapsed));
    toggle.setAttribute("aria-label", "Toggle manual wildcards");
    toggle.addEventListener("click", () => this.toggleManual());
    head.append(
      toggle,
      el("span", "", "Manual"),
      el(
        "span",
        "lm-quick__section-count",
        plural(entries.length, "key"),
      ),
    );
    const body = el("div", "lm-quick__section-body");
    entries.forEach((entry) => body.appendChild(this.createManualRow(entry)));
    section.append(head, body);
    this.resultsElement.appendChild(section);
  }

  toggleManual() {
    this.manualCollapsed = !this.manualCollapsed;
    writeStorage(MANUAL_COLLAPSED_KEY, this.manualCollapsed ? "1" : "0");
    this.render();
  }

  createResourceRow(item) {
    const row = el("button", "lm-quick__row");
    row.type = "button";
    row.setAttribute("role", "option");
    row.dataset.kind = "resource";
    row.dataset.filePath = item.file_path || "";
    row.dataset.preview = hasRealPreview(item.preview_url) ? "true" : "false";
    const selected =
      this.selected?.kind === "resource" &&
      this.selected.filePath === item.file_path;
    row.classList.toggle("is-selected", selected);
    row.setAttribute("aria-selected", String(selected));

    const head = el("span", "lm-quick__row-head");
    head.appendChild(
      el("span", "lm-quick__row-name", item.model_name || item.file_name || "Untitled"),
    );
    if (item.active) head.appendChild(this.createBadge("active"));
    row.append(head, el("span", "lm-quick__row-path", this.resourceSubtitle(item)));
    row.addEventListener("click", () => {
      // Keep focus inside the panel even on browsers that do not focus a
      // button on click; Escape must reach the floating panel.
      row.focus({ preventScroll: true });
      this.selectResource(item);
    });
    return row;
  }

  createManualRow(entry) {
    const row = el("button", "lm-quick__row lm-quick__row--manual");
    row.type = "button";
    row.setAttribute("role", "option");
    row.dataset.kind = "manual";
    row.dataset.key = entry.key || "";
    const selected =
      this.selected?.kind === "manual" && this.selected.key === entry.key;
    row.classList.toggle("is-selected", selected);
    row.setAttribute("aria-selected", String(selected));

    const head = el("span", "lm-quick__row-head");
    head.append(el("span", "lm-quick__row-name", entry.key));
    head.appendChild(this.createBadge("manual"));
    row.append(
      head,
      el(
        "span",
        "lm-quick__row-path",
        `${plural(Number(entry.values_count || 0), "value")} · manual wildcard`,
      ),
    );
    row.addEventListener("click", () => {
      row.focus({ preventScroll: true });
      this.selectManual(entry);
    });
    return row;
  }

  createBadge(kind) {
    const badge = el(
      "span",
      `lm-wildcard-state is-${kind}`,
      kind === "active" ? "Active" : kind === "manual" ? "Manual" : "Inactive",
    );
    if (kind === "active") {
      const icon = el("span", "", "⚡");
      icon.setAttribute("aria-hidden", "true");
      badge.prepend(icon);
      badge.title = "Active globally";
    } else if (kind === "manual") {
      badge.title = "Manual wildcard (always active)";
    }
    return badge;
  }

  resourceSubtitle(item) {
    const parts = [];
    if (item.file_name) parts.push(item.file_name);
    if (item.wildcard_format) parts.push(String(item.wildcard_format).toUpperCase());
    parts.push(plural(Number(item.entry_count || 0), "key"));
    parts.push(`${formatCount(item.value_count)} values`);
    return parts.join(" · ");
  }

  appendEmptyState() {
    const empty = el("div", "lm-quick__empty");
    let message;
    if (this.searchQuery) {
      message = `No resources or keys match “${this.searchQuery}”.`;
    } else if (this.scope === "active") {
      message = "No managed wildcards are active.";
    } else {
      message = "No wildcard resources or manual keys found.";
    }
    empty.appendChild(el("div", "", message));
    if (this.scope === "active" && this.items.some((item) => !item.active)) {
      const showAll = el("button", "lm-quick__secondary", "Show all");
      showAll.type = "button";
      showAll.addEventListener("click", () => this.setScope("all"));
      empty.appendChild(showAll);
    }
    this.resultsElement.appendChild(empty);
  }

  renderStatus() {
    if (!this.statusElement) return;
    if (this.loadError) {
      this.statusElement.textContent = this.loadError;
      return;
    }
    const resources = this.visibleResources();
    const active = resources.filter((item) => item.active).length;
    const library =
      this.scope === "all"
        ? resources.filter((item) => !item.active).length
        : 0;
    const manual = this.visibleManual().length;
    let status;
    if (this.searchQuery) {
      status = `${plural(active + library + manual, "result")} for “${this.searchQuery}”`;
    } else if (this.scope === "active") {
      status = `${active} active · ${plural(manual, "manual key")}`;
    } else {
      status = `${active} active · ${library} library · ${plural(manual, "manual key")}`;
    }
    if (this.conflicts.length) {
      status += ` · ${plural(this.conflicts.length, "runtime conflict")}`;
    }
    this.statusElement.textContent = status;
  }

  selectResource(item) {
    this.selected = { kind: "resource", filePath: item.file_path };
    this.keyFilter = "";
    // Update the existing rows instead of rebuilding the list: the clicked
    // row keeps focus, so Escape still reaches the floating panel's close
    // handler.
    this.updateRowSelection();
    this.renderDetail();
    this.updateHints();
  }

  selectManual(entry) {
    this.selected = { kind: "manual", key: entry.key };
    this.updateRowSelection();
    this.renderDetail();
    this.updateHints();
  }

  updateRowSelection() {
    this.resultsElement.querySelectorAll(".lm-quick__row").forEach((row) => {
      const selected =
        row.dataset.kind === "manual"
          ? this.selected?.kind === "manual" &&
            this.selected.key === row.dataset.key
          : this.selected?.kind === "resource" &&
            this.selected.filePath === row.dataset.filePath;
      row.classList.toggle("is-selected", selected);
      row.setAttribute("aria-selected", String(selected));
    });
  }

  renderDetail() {
    this.detailElement.replaceChildren();
    const selection = this.selectedItem();
    if (!selection) {
      this.detailElement.appendChild(
        el("p", "lm-quick__empty", "Select a resource to inspect its wildcard keys."),
      );
      return;
    }
    if (this.selected.kind === "manual") {
      this.renderManualDetail(selection);
    } else {
      this.renderResourceDetail(selection);
    }
  }

  renderResourceDetail(item) {
    const entries = item.entries || [];
    const entryCount =
      item.entry_count != null ? Number(item.entry_count) : entries.length;
    const valueCount = formatCount(item.value_count);
    const previewUrl = item.preview_url;
    if (hasRealPreview(previewUrl)) {
      const isVideo = isVideoPreviewUrl(previewUrl);
      const preview = el(isVideo ? "video" : "img", "lm-quick__preview");
      preview.src = previewUrl;
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

    this.detailElement.appendChild(
      el("h2", "lm-quick__name", item.model_name || item.file_name || "Wildcard resource"),
    );
    const meta = [
      item.file_name,
      item.wildcard_format ? String(item.wildcard_format).toUpperCase() : "",
      item.base_model,
    ]
      .filter(Boolean)
      .join(" · ");
    if (meta) this.detailElement.appendChild(el("div", "lm-quick__meta", meta));

    const status = el("div", "lm-wildcard-status");
    status.appendChild(this.createBadge(item.active ? "active" : "inactive"));
    const aliases = item.activation_aliases || {};
    let statusText;
    if (item.active) {
      statusText = `Namespace: ${item.activation_namespace || "(none)"}`;
      if (entries.length === 1) {
        const source = entries[0].key;
        const alias = source ? aliases[source] : "";
        if (alias && alias !== source) statusText += ` · Alias: ${source} → ${alias}`;
      }
    } else {
      statusText = "Not active";
    }
    status.appendChild(el("span", "lm-wildcard-status-text", statusText));
    this.detailElement.appendChild(status);
    this.detailElement.appendChild(
      el("div", "lm-wildcard-counts", `${plural(entryCount, "key")} · ${valueCount} values`),
    );

    if (Array.isArray(item.errors) && item.errors.length) {
      this.detailElement.appendChild(
        el("p", "lm-wildcard-note lm-wildcard-note--error", item.errors.join(" · ")),
      );
    }
    if (
      !item.active &&
      (item.activation_namespace || Object.keys(aliases).length)
    ) {
      this.detailElement.appendChild(
        el(
          "p",
          "lm-wildcard-note",
          "Previous activation settings will be reused when you activate.",
        ),
      );
    }

    const keysHead = el("div", "lm-wildcard-keys-head");
    keysHead.appendChild(el("span", "", `Keys (${entryCount})`));
    const keyFilter = el("input", "");
    keyFilter.type = "search";
    keyFilter.placeholder = "Filter keys…";
    keyFilter.setAttribute("aria-label", "Filter wildcard keys");
    keyFilter.value = this.keyFilter;
    keysHead.appendChild(keyFilter);
    this.detailElement.appendChild(keysHead);

    const keyList = el("div", "lm-wildcard-keys");
    this.detailElement.appendChild(keyList);
    keyFilter.addEventListener("input", () => {
      this.keyFilter = keyFilter.value;
      this.renderKeyRows(keyList, item);
    });
    this.renderKeyRows(keyList, item);

    if (this.activationError?.filePath === item.file_path) {
      this.detailElement.appendChild(this.createActivationError(item));
    }

    const actions = el("div", "lm-quick__actions");
    const primary = el(
      "button",
      "lm-quick__primary",
      item.active ? "Deactivate" : "Activate",
    );
    primary.type = "button";
    primary.disabled = this.activationInFlight === item.file_path;
    if (primary.disabled) primary.setAttribute("aria-busy", "true");
    primary.addEventListener("click", () => this.toggleActivation(item));
    const manager = el("button", "lm-quick__secondary", "Open in manager");
    manager.type = "button";
    manager.addEventListener("click", () => openWildcardManager(item.file_path || ""));
    actions.append(primary, manager);
    this.detailElement.appendChild(actions);

    if (item.active) {
      this.detailElement.appendChild(
        el(
          "p",
          "lm-wildcard-note",
          "Global activation affects autocomplete and every subsequent execution.",
        ),
      );
    }
  }

  renderKeyRows(container, item) {
    container.replaceChildren();
    const entries = item.entries || [];
    const query = this.keyFilter.trim().toLowerCase();
    const visible = entries.filter((entry) => {
      if (!query) return true;
      const key = item.active
        ? entry.effective_key || entry.key || ""
        : entry.key || "";
      return `${key} ${entry.source_path || ""}`.toLowerCase().includes(query);
    });
    if (!visible.length) {
      container.appendChild(
        el(
          "div",
          "lm-wildcard-empty",
          entries.length ? "No keys match this filter." : "No parsed keys. Refresh metadata in the manager.",
        ),
      );
      return;
    }
    visible.slice(0, MAX_RENDERED_KEYS).forEach((entry) => {
      const keyText = item.active
        ? entry.effective_key || entry.key || ""
        : entry.key || "";
      if (!keyText) return;
      const problem = entry.reference_problem;
      const row = el("button", "lm-wildcard-key");
      row.type = "button";
      if (problem) {
        row.classList.add("is-unreferenceable");
        row.disabled = true;
        row.title = `Cannot be referenced: ${problem}`;
        row.setAttribute("aria-label", `Cannot be referenced: ${problem}`);
      } else {
        row.title = `Copy __${keyText}__`;
        row.setAttribute("aria-label", `Copy __${keyText}__`);
        row.addEventListener("click", () => this.copyKey(keyText, row));
      }
      row.appendChild(el("span", "lm-wildcard-key-name", keyText));
      row.appendChild(
        el(
          "span",
          "lm-wildcard-key-count",
          formatCount(entry.values_count),
        ),
      );
      row.appendChild(
        problem
          ? el("span", "lm-wildcard-key-copy", "⚠")
          : copyIcon(),
      );
      container.appendChild(row);
    });
    if (visible.length > MAX_RENDERED_KEYS) {
      container.appendChild(
        el(
          "div",
          "lm-wildcard-empty",
          `Showing ${MAX_RENDERED_KEYS} of ${visible.length} keys. Open the manager to browse all.`,
        ),
      );
    }
  }

  createActivationError(item) {
    const box = el("div", "lm-wildcard-error");
    box.appendChild(el("strong", "", "Activation blocked"));
    box.appendChild(el("p", "", this.activationError.message));
    for (const conflict of (this.activationError.conflicts || []).slice(0, 6)) {
      const owners = (conflict.owners || [])
        .map((owner) =>
          owner.resource_id === item.file_path ? "this resource" : owner.resource_id,
        )
        .join(", ");
      box.appendChild(
        el(
          "div",
          "lm-wildcard-error__conflict",
          `${conflict.key}: ${owners || "another resource"}`,
        ),
      );
    }
    const resolve = el("button", "lm-quick__secondary", "Resolve in manager");
    resolve.type = "button";
    resolve.addEventListener("click", () => openWildcardManager(item.file_path || ""));
    box.appendChild(resolve);
    return box;
  }

  renderManualDetail(entry) {
    this.detailElement.appendChild(
      el("h2", "lm-quick__name", entry.key),
    );
    this.detailElement.appendChild(
      el(
        "div",
        "lm-quick__meta",
        `Manual wildcard · ${plural(Number(entry.values_count || 0), "value")}`,
      ),
    );
    const status = el("div", "lm-wildcard-status");
    status.appendChild(this.createBadge("manual"));
    status.appendChild(
      el("span", "lm-wildcard-status-text", "Always active · not toggleable"),
    );
    this.detailElement.appendChild(status);
    this.detailElement.appendChild(
      el(
        "p",
        "lm-wildcard-note",
        "Loaded from the settings wildcards folder. Edit the source file to change the values.",
      ),
    );
    if (entry.source_path) {
      this.detailElement.appendChild(
        el("p", "lm-wildcard-note", `Source: ${entry.source_path}`),
      );
    }

    const valuesHead = el("div", "lm-wildcard-keys-head");
    valuesHead.appendChild(
      el("span", "", `Value preview (${Number(entry.values_count || 0)})`),
    );
    this.detailElement.appendChild(valuesHead);
    const values = el("div", "lm-wildcard-keys lm-wildcard-values");
    const samples = Array.isArray(entry.sample_values) ? entry.sample_values : [];
    if (!samples.length) {
      values.appendChild(el("div", "lm-wildcard-empty", "No value preview available."));
    } else {
      samples.forEach((value) => {
        const row = el("div", "lm-wildcard-key");
        row.appendChild(el("span", "lm-wildcard-key-name", String(value)));
        values.appendChild(row);
      });
    }
    this.detailElement.appendChild(values);
    if (samples.length && Number(entry.values_count || 0) > samples.length) {
      this.detailElement.appendChild(
        el(
          "p",
          "lm-wildcard-note",
          `Showing ${samples.length} of ${Number(entry.values_count || 0)} values. Open the wildcards folder to see all.`,
        ),
      );
    }

    const actions = el("div", "lm-quick__actions");
    const problem = entry.reference_problem;
    const copy = el("button", "lm-quick__primary", `Copy __${entry.key}__`);
    copy.type = "button";
    if (problem) {
      copy.disabled = true;
      copy.title = `Cannot be referenced: ${problem}`;
    } else {
      copy.addEventListener("click", () => this.copyKey(entry.key, copy));
    }
    const folder = el("button", "lm-quick__secondary", "Open folder");
    folder.type = "button";
    folder.title = "Open wildcards folder";
    folder.addEventListener("click", () => this.openFolder());
    actions.append(copy, folder);
    this.detailElement.appendChild(actions);
    if (problem) {
      this.detailElement.appendChild(
        el("p", "lm-wildcard-note", `Cannot be referenced: ${problem}`),
      );
    }
  }

  async copyKey(key, button) {
    const syntax = `__${key}__`;
    try {
      if (!navigator.clipboard) throw new Error("Clipboard unavailable");
      await navigator.clipboard.writeText(syntax);
      button?.classList.add("is-copied");
      setTimeout(() => button?.classList.remove("is-copied"), 900);
      this.setStatus(`Copied ${syntax}`);
    } catch (error) {
      this.setStatus(error.message || `Unable to copy ${syntax}`);
    }
  }

  async toggleActivation(item) {
    if (!item || this.activationInFlight) return;
    const wasActive = item.active === true;
    this.activationInFlight = item.file_path;
    this.activationError = null;
    this.renderDetail();
    try {
      await setWildcardActive(item.file_path, !wasActive);
      const name = item.model_name || item.file_name || "wildcard";
      await this.load();
      this.setStatus(`${wasActive ? "Deactivated" : "Activated"} ${name}`);
    } catch (error) {
      this.activationError = {
        filePath: item.file_path,
        message: error.message || "Activation failed",
        conflicts: error.payload?.conflicts || [],
      };
      this.setStatus(
        this.activationError.conflicts.length
          ? "Activation blocked by a key conflict"
          : this.activationError.message,
      );
    } finally {
      this.activationInFlight = null;
      if (this.panel?.isOpen()) this.renderDetail();
    }
  }

  async openFolder() {
    try {
      await openWildcardsFolder();
      this.setStatus("Opened wildcards folder");
    } catch (error) {
      this.setStatus(error.message || "Unable to open the wildcards folder");
    }
  }

  visibleRows() {
    const rows = this.visibleResources().map((item) => ({
      kind: "resource",
      item,
    }));
    if (!this.manualCollapsed) {
      rows.push(
        ...this.visibleManual().map((entry) => ({ kind: "manual", entry })),
      );
    }
    return rows;
  }

  selectionMatchesRow(row) {
    if (row.kind === "resource") {
      return (
        this.selected?.kind === "resource" &&
        this.selected.filePath === row.item.file_path
      );
    }
    return (
      this.selected?.kind === "manual" &&
      this.selected.key === row.entry.key
    );
  }

  moveSelection(direction) {
    const rows = this.visibleRows();
    if (!rows.length) return;
    const focusInResults = this.resultsElement.contains(document.activeElement);
    const current = rows.findIndex((row) => this.selectionMatchesRow(row));
    const fallback = direction > 0 ? 0 : rows.length - 1;
    const next = Math.max(
      0,
      Math.min(rows.length - 1, current < 0 ? fallback : current + direction),
    );
    const row = rows[next];
    this.keyFilter = "";
    if (row.kind === "resource") {
      this.selected = { kind: "resource", filePath: row.item.file_path };
    } else {
      this.selected = { kind: "manual", key: row.entry.key };
    }
    this.updateRowSelection();
    this.renderDetail();
    this.updateHints();
    const domRows = this.resultsElement.querySelectorAll(".lm-quick__row");
    domRows[next]?.scrollIntoView({ block: "nearest" });
    if (focusInResults) domRows[next]?.focus({ preventScroll: true });
  }

  activateSelected() {
    const selection = this.selectedItem();
    if (!selection) return;
    if (this.selected.kind === "manual") this.copyKey(selection.key);
    else this.toggleActivation(selection);
  }

  onKeyDown(event) {
    if (event.key === "Escape") {
      if (this.searchInput?.value) {
        event.preventDefault();
        event.stopPropagation();
        this.searchInput.value = "";
        this.searchQuery = "";
        clearTimeout(this.debounceTimer);
        this.load();
      }
      return;
    }
    if (event.target.closest?.(".lm-wildcard-keys-head input")) return;
    const inSearch = event.target === this.searchInput;
    const inResults = this.resultsElement?.contains(event.target);
    if (event.target.closest?.(".lm-quick__detail button")) return;
    if (!inSearch && !inResults) return;

    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      this.moveSelection(event.key === "ArrowDown" ? 1 : -1);
      return;
    }
    if (event.key !== "Enter") return;
    event.preventDefault();
    const focusedRow = event.target.closest?.(".lm-quick__row");
    if (focusedRow) {
      if (focusedRow.dataset.kind === "manual") {
        this.copyKey(focusedRow.dataset.key || "");
      } else {
        const item = this.items.find(
          (entry) => entry.file_path === focusedRow.dataset.filePath,
        );
        if (item) this.toggleActivation(item);
      }
      return;
    }
    this.activateSelected();
  }

  previewKeyForRow(row) {
    if (row?.dataset?.kind !== "resource" || row.dataset.preview !== "true") {
      return "";
    }
    return row.dataset.filePath || "";
  }

  onRowPointerOver(event) {
    const row = event.target?.closest?.(".lm-quick__row[data-kind='resource']");
    if (!row || row === this.previewRow) return;
    const key = this.previewKeyForRow(row);
    if (!key) {
      this.clearRowPreview();
      return;
    }
    this.clearRowPreview();
    this.previewRow = row;
    clearTimeout(this.previewTimer);
    this.previewTimer = setTimeout(() => {
      this.previewTimer = null;
      void this.showRowPreview(row, key);
    }, ROW_PREVIEW_DELAY_MS);
  }

  onRowPointerOut(event) {
    const row = event.target?.closest?.(".lm-quick__row[data-kind='resource']");
    if (!row || row !== this.previewRow) return;
    const next = event.relatedTarget;
    if (next && row.contains(next)) return;
    this.clearRowPreview();
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
    if (!tooltip || this.previewRow !== row) return;
    const rect = row.getBoundingClientRect();
    await tooltip.show(key, rect.right, rect.top);
  }

  ensurePreviewTooltip() {
    if (this.previewTooltip) return Promise.resolve(this.previewTooltip);
    if (!this.previewTooltipPromise) {
      this.previewTooltipPromise = import("./preview_tooltip.js")
        .then(({ PreviewTooltip }) => {
          this.previewTooltipPromise = null;
          if (!this.panel?.isOpen()) return null;
          this.previewTooltip = new PreviewTooltip({
            modelType: "wildcards",
            className: "lm-tooltip--elevated",
            positionBoundary: () =>
              this.resultsElement?.getBoundingClientRect() || null,
            previewUrlResolver: (filePath) => this.resolveRowPreview(filePath),
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

  resolveRowPreview(filePath) {
    const item = this.items.find((entry) => entry.file_path === filePath);
    if (!item || !hasRealPreview(item.preview_url)) return null;
    return {
      previewUrl: item.preview_url,
      displayName: item.model_name || item.file_name || filePath,
    };
  }

  teardownPreview() {
    this.clearRowPreview();
    this.previewTooltip?.cleanup();
    this.previewTooltip = null;
    this.previewTooltipPromise = null;
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

import { ensureLmStyles } from "./lm_styles_loader.js";
import {
  getAvailableLoraEntries,
  getAvailableLoras,
  normalizeLoraNameKey,
} from "./loras_widget_utils.js";

/**
 * Type-to-add search field for the Lora Stacker node.
 *
 * The field is a plain, always-empty text input above the LoRA list: one click
 * puts the caret in it, and every accepted candidate is appended to (or enabled
 * in) the node's LoRA list by the caller. Matching follows the node's label
 * mode, so a node showing titles searches titles and a node showing file names
 * searches file names.
 *
 * The candidate list comes from the library catalogue the LoRA widgets already
 * cache (`getAvailableLoraEntries`), so titles need no extra request and no
 * backend change.
 */

export const LORA_SEARCH_WIDGET_HEIGHT = 30;

// ComfyUI positions DOM widgets at node-margin inset and gives them a box that
// is 2 × margin shorter than the height litegraph allocated, which itself is
// the computeSize height plus 4. Return the allocation that leaves
// LORA_SEARCH_WIDGET_HEIGHT px of usable content box.
const DOM_WIDGET_MARGIN = 10;
const WIDGET_LAYOUT_PADDING = 4;
const LORA_SEARCH_WIDGET_ALLOCATION =
  LORA_SEARCH_WIDGET_HEIGHT + DOM_WIDGET_MARGIN * 2 - WIDGET_LAYOUT_PADDING;

const MAX_RESULTS = 50;
const POPOVER_MIN_WIDTH = 240;
const POPOVER_MAX_HEIGHT = 260;
const POPOVER_MIN_HEIGHT = 80;
const POPOVER_OFFSET = 4;
const POPOVER_FLIP_MIN_BELOW = 140;
const DISPLAY_MODE_MODEL_NAME = "model_name";
const DEFAULT_DISPLAY_MODE = "file_name";
const DEFAULT_STRENGTH = 1;
const STRENGTH_DECIMALS = 2;

/**
 * The text a candidate is matched, ranked and displayed by in the given label
 * mode: the library title in model-name mode, the stored file name otherwise.
 */
export function getLoraSearchField(entry, displayMode = DEFAULT_DISPLAY_MODE) {
  const title = entry?.label || entry?.name || "";
  return displayMode === DISPLAY_MODE_MODEL_NAME ? title : entry?.name || "";
}

/**
 * Filter the catalogue by a search query.
 *
 * Matching is case-insensitive and substring-based, and every whitespace
 * separated token must match (the same AND semantics as the LoRA Manager
 * backend). Prefix matches are ranked first, then the earliest match, then the
 * shorter label, so typing "port" surfaces "Port..." above "...port...".
 */
export function filterLoraCandidates(entries, query, displayMode = DEFAULT_DISPLAY_MODE) {
  const normalizedQuery = String(query ?? "").trim().toLowerCase();
  if (!normalizedQuery) {
    return [];
  }
  const tokens = normalizedQuery.split(/\s+/).filter(Boolean);
  const ranked = [];
  for (const entry of entries || []) {
    if (!entry || !entry.name) {
      continue;
    }
    const field = getLoraSearchField(entry, displayMode).toLowerCase();
    if (!tokens.every((token) => field.includes(token))) {
      continue;
    }
    ranked.push({
      entry,
      field,
      prefix: field.startsWith(normalizedQuery),
      index: field.indexOf(tokens[0]),
    });
  }
  ranked.sort((a, b) => {
    if (a.prefix !== b.prefix) {
      return a.prefix ? -1 : 1;
    }
    if (a.index !== b.index) {
      return a.index - b.index;
    }
    if (a.field.length !== b.field.length) {
      return a.field.length - b.field.length;
    }
    return a.field.localeCompare(b.field);
  });
  return ranked.map((candidate) => candidate.entry);
}

/**
 * Find the list entry that refers to the same file as `targetName`.
 *
 * Entries are compared the way the backend resolves names: exact match on the
 * extension-free, forward-slash name, falling back to the bare file name for
 * legacy entries stored without their folder. Two folder-qualified names in
 * different folders are different files and never match.
 */
function findLoraIndex(loras, targetName) {
  const targetBase = targetName.slice(targetName.lastIndexOf("/") + 1);
  let bareIndex = -1;
  for (let index = 0; index < loras.length; index += 1) {
    const key = normalizeLoraNameKey(loras[index]?.name);
    if (!key) {
      continue;
    }
    if (key === targetName) {
      return index;
    }
    if (bareIndex === -1 && key === targetBase) {
      bareIndex = index;
    }
  }
  return bareIndex;
}

function formatStrength(value) {
  if (value === null || value === undefined || value === "") {
    return DEFAULT_STRENGTH.toFixed(STRENGTH_DECIMALS);
  }
  const numeric = Number(value);
  return (Number.isFinite(numeric) ? numeric : DEFAULT_STRENGTH).toFixed(
    STRENGTH_DECIMALS
  );
}

/**
 * Apply a search selection to the node's LoRA list.
 *
 * A LoRA that is already in the list is enabled in place (its strengths are
 * kept) instead of being added twice; a new one is appended active, using the
 * library's recommended strength when one is configured. Returns the list to
 * write back and whether it actually changed.
 */
export function applyLoraSelection(currentLoras, selection) {
  const loras = Array.isArray(currentLoras) ? currentLoras : [];
  const name = normalizeLoraNameKey(selection?.name);
  if (!name) {
    return { loras, changed: false };
  }

  const existingIndex = findLoraIndex(loras, name);
  if (existingIndex >= 0) {
    const existing = loras[existingIndex];
    if (existing?.active) {
      return { loras, changed: false };
    }
    const next = loras.slice();
    next[existingIndex] = { ...existing, active: true };
    return { loras: next, changed: true };
  }

  const strength = formatStrength(selection?.strength);
  return {
    loras: [
      ...loras,
      {
        name,
        strength,
        clipStrength: strength,
        active: true,
        expanded: false,
        selected: false,
        locked: false,
      },
    ],
    changed: true,
  };
}

function defaultGetEntries() {
  return getAvailableLoraEntries();
}

/**
 * Create the search field as a DOM widget on `node`.
 *
 * Options:
 *   onSelect(entry)  called with the chosen catalogue entry; required.
 *   getDisplayMode() returns "model_name" or "file_name" at search time; read
 *                    it from the node label setting on every call.
 *   getEntries()     returns the current catalogue snapshot (tests).
 *
 * Returns the created widget. It is never serialized (`serialize = false`), so
 * `widgets_values` keeps its existing slots and old workflows keep loading.
 */
export function addLoraSearchWidget(node, options = {}) {
  ensureLmStyles();

  const { onSelect, getDisplayMode, getEntries = defaultGetEntries } = options;
  const readDisplayMode = () =>
    typeof getDisplayMode === "function"
      ? getDisplayMode()
      : DEFAULT_DISPLAY_MODE;

  let entries = null;
  let entriesPromise = null;
  let results = [];
  let activeIndex = -1;

  const container = document.createElement("div");
  container.className = "lm-widget-root lm-lora-search";
  if (typeof LiteGraph !== "undefined" && LiteGraph.vueNodesMode) {
    container.classList.add("lm-vue-node");
  }

  const input = document.createElement("input");
  input.type = "text";
  input.className = "lm-lora-search-input";
  input.placeholder = "Search LoRAs to add…";
  input.autocomplete = "off";
  input.spellcheck = false;
  input.setAttribute("aria-label", "Search LoRAs to add");
  container.appendChild(input);

  const popover = document.createElement("div");
  popover.className = "lm-popover lm-lora-search-results";
  popover.setAttribute("role", "listbox");
  popover.setAttribute("data-capture-wheel", "true");

  const isOpen = () => popover.classList.contains("is-open");

  const positionPopover = () => {
    const rect = input.getBoundingClientRect();
    const width = Math.max(rect.width, POPOVER_MIN_WIDTH);
    const spaceBelow = window.innerHeight - rect.bottom - POPOVER_OFFSET;
    const spaceAbove = rect.top - POPOVER_OFFSET;
    const placeAbove =
      spaceBelow < POPOVER_FLIP_MIN_BELOW && spaceAbove > spaceBelow;
    const available = Math.max(placeAbove ? spaceAbove : spaceBelow, POPOVER_MIN_HEIGHT);

    popover.style.width = `${width}px`;
    popover.style.left = `${Math.max(rect.left, 0)}px`;
    popover.style.maxHeight = `${Math.min(POPOVER_MAX_HEIGHT, available)}px`;
    if (placeAbove) {
      popover.style.top = "";
      popover.style.bottom = `${window.innerHeight - rect.top + POPOVER_OFFSET}px`;
    } else {
      popover.style.bottom = "";
      popover.style.top = `${rect.bottom + POPOVER_OFFSET}px`;
    }
  };

  const close = () => {
    popover.classList.remove("is-open");
    popover.remove();
    activeIndex = -1;
    window.removeEventListener("resize", positionPopover);
    document.removeEventListener("pointerdown", handleOutsidePointerDown, true);
  };

  const open = () => {
    if (isOpen()) {
      positionPopover();
      return;
    }
    document.body.appendChild(popover);
    popover.classList.add("is-open");
    positionPopover();
    window.addEventListener("resize", positionPopover);
    document.addEventListener("pointerdown", handleOutsidePointerDown, true);
  };

  const setActiveIndex = (index) => {
    activeIndex = index;
    const rows = popover.querySelectorAll(".lm-lora-search-result");
    rows.forEach((row, rowIndex) => {
      const isActive = rowIndex === index;
      row.dataset.active = isActive ? "true" : "false";
      if (isActive && typeof row.scrollIntoView === "function") {
        row.scrollIntoView({ block: "nearest" });
      }
    });
    if (activeIndex >= 0) {
      input.setAttribute(
        "aria-activedescendant",
        `lm-lora-search-result-${node.id ?? 0}-${activeIndex}`
      );
    } else {
      input.removeAttribute("aria-activedescendant");
    }
  };

  const selectResult = (index) => {
    const entry = results[index];
    if (!entry) {
      return;
    }
    if (typeof onSelect === "function") {
      onSelect(entry);
    }
    // The field is session-only: clear it so the next LoRA can be typed
    // straight away, and keep the caret in the input.
    input.value = "";
    render();
    input.focus();
  };

  const buildRow = (entry, index) => {
    const mode = readDisplayMode();
    const primary = getLoraSearchField(entry, mode);
    const secondary =
      mode === DISPLAY_MODE_MODEL_NAME ? entry.name : entry.label;

    const row = document.createElement("div");
    row.className = "lm-lora-search-result";
    row.id = `lm-lora-search-result-${node.id ?? 0}-${index}`;
    row.setAttribute("role", "option");
    row.dataset.active = "false";
    row.dataset.name = entry.name;

    const label = document.createElement("span");
    label.className = "lm-lora-search-result-label";
    label.textContent = primary;
    row.appendChild(label);

    if (secondary && secondary !== primary) {
      const meta = document.createElement("span");
      meta.className = "lm-lora-search-result-meta";
      meta.textContent = secondary;
      row.appendChild(meta);
    }

    // Keep the caret in the input: a pointerdown on the row would otherwise
    // blur it and close the list before the click lands.
    row.addEventListener("pointerdown", (event) => {
      event.preventDefault();
      event.stopPropagation();
      selectResult(index);
    });

    return row;
  };

  const renderResults = () => {
    results = filterLoraCandidates(entries || [], input.value, readDisplayMode())
      .slice(0, MAX_RESULTS);
    popover.replaceChildren();
    activeIndex = -1;

    results.forEach((entry, index) => {
      popover.appendChild(buildRow(entry, index));
    });

    if (results.length === 0) {
      const empty = document.createElement("div");
      empty.className = "lm-lora-search-empty";
      empty.textContent = entries === null ? "Loading LoRAs…" : "No matches";
      popover.appendChild(empty);
    }
  };

  function render() {
    renderResults();
    if (results.length > 0 && document.activeElement === input) {
      open();
    } else {
      close();
    }
  }

  function handleOutsidePointerDown(event) {
    const target = event.target;
    if (target === input || container.contains(target) || popover.contains(target)) {
      return;
    }
    close();
  }

  const ensureEntries = () => {
    const cached = getEntries();
    if (cached) {
      entries = cached;
    }
    if (entriesPromise) {
      return entriesPromise;
    }
    entriesPromise = Promise.resolve(getAvailableLoras())
      .then(() => {
        entries = getEntries() || entries || [];
        return entries;
      })
      .finally(() => {
        entriesPromise = null;
      });
    return entriesPromise;
  };

  const onInput = () => {
    if (entries !== null) {
      render();
    }
    ensureEntries().then(() => {
      if (document.activeElement === input) {
        render();
      }
    });
  };

  const moveActive = (delta) => {
    if (results.length === 0) {
      return;
    }
    const next = (activeIndex + delta + results.length) % results.length;
    setActiveIndex(next);
  };

  const onKeyDown = (event) => {
    // Typing in the field must not reach ComfyUI's canvas shortcuts.
    event.stopPropagation();
    switch (event.key) {
      case "ArrowDown":
        event.preventDefault();
        moveActive(1);
        break;
      case "ArrowUp":
        event.preventDefault();
        moveActive(-1);
        break;
      case "Enter":
        if (results.length > 0) {
          event.preventDefault();
          selectResult(activeIndex >= 0 ? activeIndex : 0);
        }
        break;
      case "Escape":
        event.preventDefault();
        input.value = "";
        render();
        input.blur();
        break;
      default:
        break;
    }
  };

  const onFocus = () => {
    ensureEntries().then(() => {
      if (document.activeElement === input && input.value.trim()) {
        render();
      }
    });
  };

  const onBlur = () => {
    // Session-only field: dropping focus drops the query, so the next click
    // always starts empty.
    input.value = "";
    results = [];
    close();
  };

  input.addEventListener("input", onInput);
  input.addEventListener("keydown", onKeyDown);
  input.addEventListener("focus", onFocus);
  input.addEventListener("blur", onBlur);

  // Clicking the field's padding should land the caret in the input, so the
  // control is typable with one click anywhere on the row.
  container.addEventListener("pointerdown", (event) => {
    if (event.target !== input) {
      event.preventDefault();
      input.focus();
    }
  });

  const widget = node.addDOMWidget("lora_search", "custom", container, {
    getValue: () => "",
    setValue: () => {},
    getMinHeight: () => LORA_SEARCH_WIDGET_HEIGHT,
    hideInPanel: true,
    selectOn: ["click", "focus"],
  });
  // Keep the node's serialized widget slots untouched.
  widget.serialize = false;
  widget.computeSize = () => [0, LORA_SEARCH_WIDGET_ALLOCATION];
  widget.inputEl = input;

  widget.onRemove = () => {
    input.removeEventListener("input", onInput);
    input.removeEventListener("keydown", onKeyDown);
    input.removeEventListener("focus", onFocus);
    input.removeEventListener("blur", onBlur);
    close();
  };

  return widget;
}

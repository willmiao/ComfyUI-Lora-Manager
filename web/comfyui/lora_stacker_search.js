import { ensureLmStyles } from "./lm_styles_loader.js";
import {
  getActiveFilteredLoraEntries,
  getAvailableLoraEntries,
  getAvailableLoras,
} from "./loras_widget_utils.js";
import { getLoraActiveFiltersAutocompletePreference } from "./settings.js";

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
 * cache (`getAvailableLoraEntries`), so titles need no extra request. When the
 * "active filters" setting is on — the same one the textarea autocomplete
 * honours — the catalogue is first narrowed to the LoRA Manager page's browse
 * filters, so the field cannot offer a LoRA the filtered page is hiding.
 */

export { applyLoraSelection } from "./lora_selection.js";

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
 * The primary text for a candidate in the given label mode: the library title in
 * model-name mode, the stored file name otherwise. This is what the row shows.
 */
export function getLoraSearchField(entry, displayMode = DEFAULT_DISPLAY_MODE) {
  const title = entry?.label || entry?.name || "";
  return displayMode === DISPLAY_MODE_MODEL_NAME ? title : entry?.name || "";
}

/**
 * Every text a candidate can be matched by, lowercased and de-duplicated, with
 * the mode's primary field first.
 *
 * Search deliberately looks at both the title and the file name: a library title
 * frequently shares no substring with its file name, and the user may type
 * either one, so a hit on either must surface the entry.
 */
function getLoraMatchFields(entry, displayMode) {
  const fields = [];
  for (const value of [
    getLoraSearchField(entry, displayMode),
    entry?.label || entry?.name || "",
    entry?.name || "",
  ]) {
    const field = String(value || "").toLowerCase();
    if (field && !fields.includes(field)) {
      fields.push(field);
    }
  }
  return fields;
}

/** Earliest position of `token` across `fields`, or -1 when it matches none. */
function indexOfFirstMatch(fields, token) {
  let best = -1;
  for (const field of fields) {
    const index = field.indexOf(token);
    if (index >= 0 && (best < 0 || index < best)) {
      best = index;
    }
  }
  return best;
}

/**
 * Filter the catalogue by a search query.
 *
 * Candidates match on **either** their library title or their file name,
 * whichever the node rows are currently showing, so typing a title fragment
 * finds the LoRA in "File Name" mode and vice versa. Matching is
 * case-insensitive and substring-based, and every whitespace separated token
 * must match somewhere (tokens may hit different fields). Ranking follows the
 * field the row displays: prefix matches first, then the earliest match, then
 * the shorter label, so typing "port" surfaces "Port..." above "...port...".
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
    const fields = getLoraMatchFields(entry, displayMode);
    if (!tokens.every((token) => fields.some((field) => field.includes(token)))) {
      continue;
    }
    const primary = fields[0];
    const primaryIndex = primary.includes(tokens[0])
      ? primary.indexOf(tokens[0])
      : -1;
    ranked.push({
      entry,
      field: primary,
      // Rank on the displayed field so a file name's folder prefix does not
      // outrank a real title match; the other field only decides inclusion.
      prefix: primary.startsWith(normalizedQuery),
      index:
        primaryIndex >= 0
          ? primaryIndex
          : indexOfFirstMatch(fields, tokens[0]),
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
 *   useActiveFilters() returns true when candidates must be restricted to the
 *                    LoRA Manager page's active filters; read per search, the
 *                    same way the display mode is.
 *   getFilteredEntries() returns that restricted catalogue (tests).
 *
 * Returns the created widget. It is never serialized (`serialize = false`), so
 * `widgets_values` keeps its existing slots and old workflows keep loading.
 */
export function addLoraSearchWidget(node, options = {}) {
  ensureLmStyles();

  const {
    onSelect,
    getDisplayMode,
    getEntries = defaultGetEntries,
    useActiveFilters = getLoraActiveFiltersAutocompletePreference,
    getFilteredEntries = getActiveFilteredLoraEntries,
  } = options;
  const readDisplayMode = () =>
    typeof getDisplayMode === "function"
      ? getDisplayMode()
      : DEFAULT_DISPLAY_MODE;
  const wantsActiveFilters = () =>
    typeof useActiveFilters === "function" ? Boolean(useActiveFilters()) : false;

  let entries = null;
  let entriesPromise = null;
  // Which catalogue `entries` was built from, so flipping the setting throws
  // away a list built under the other one instead of searching stale scope.
  let entriesFiltered = null;
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
    // Keep the popover up while the field is focused and holds a query, even
    // with no rows: that is the only way "Loading LoRAs…" and "No matches"
    // reach the user instead of the list silently closing.
    const focused = document.activeElement === input;
    const typed = input.value.trim().length > 0;
    if (focused && (results.length > 0 || typed)) {
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
    const filtered = wantsActiveFilters();
    if (entriesFiltered !== null && entriesFiltered !== filtered) {
      // The setting flipped since this list was built: drop it and re-resolve.
      entries = null;
    }
    entriesFiltered = filtered;

    if (entriesPromise) {
      return entriesPromise;
    }
    if (!filtered) {
      const cached = getEntries();
      if (cached) {
        entries = cached;
        return Promise.resolve(entries);
      }
    }
    entriesPromise = Promise.resolve(getAvailableLoras())
      .then(async () => {
        if (filtered) {
          // Null means the filtered lookup failed: fall back to the whole
          // catalogue rather than pretending the library is empty.
          entries = (await getFilteredEntries()) || getEntries() || entries || [];
        } else {
          entries = getEntries() || entries || [];
        }
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

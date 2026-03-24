import { ensureLmStyles } from "./lm_styles_loader.js";
import { forwardMiddleMouseToCanvas } from "./utils.js";

// --------------------------------------------------
// Helpers
// --------------------------------------------------

function extractRecipeId(item) {
  if (item?.id) return item.id;

  const rawPath =
    item?.recipe_path ||
    item?.json_path ||
    item?.file_path ||
    item?.file_url ||
    "";

  if (!rawPath) return "";

  const normalized = String(rawPath).replace(/\\/g, "/");
  const fileName = normalized.split("/").pop() || "";

  if (fileName.endsWith(".recipe.json")) {
    return fileName.replace(/\.recipe\.json$/i, "");
  }

  if (fileName.endsWith(".json")) {
    return fileName.replace(/\.json$/i, "");
  }

  return "";
}

function hideDefaultRecipeIdWidget(node, widgetName) {
  const existing = node.widgets?.find((w) => w.name === widgetName);
  if (!existing) return;

  existing.hidden = true;
  existing.computeSize = () => [0, -4];
  existing.type = "hidden";
}

function safeText(value, fallback = "") {
  if (value === undefined || value === null) return fallback;
  return String(value);
}

function truncate(text, max = 100) {
  const s = safeText(text, "");
  if (s.length <= max) return s;
  return `${s.slice(0, max - 3)}...`;
}

function normalizeText(value) {
  return safeText(value, "").trim().toLowerCase();
}

function getRecipePrompt(item) {
  return (
    item?.prompt ||
    item?.gen_params?.prompt ||
    item?.metadata?.prompt ||
    ""
  );
}

function getRecipeNegativePrompt(item) {
  return (
    item?.negative_prompt ||
    item?.gen_params?.negative_prompt ||
    item?.metadata?.negative_prompt ||
    ""
  );
}

function getRecipeSampler(item) {
  return item?.sampler || item?.gen_params?.sampler || "";
}

function getRecipeSteps(item) {
  return item?.steps || item?.gen_params?.steps || "";
}

function getRecipeCfg(item) {
  return item?.cfg_scale || item?.gen_params?.cfg_scale || "";
}

function getRecipeSeed(item) {
  return item?.seed || item?.gen_params?.seed || "";
}

function getRecipeTags(item) {
  const raw =
    item?.tags ||
    item?.metadata?.tags ||
    item?.recipe_tags ||
    [];

  if (Array.isArray(raw)) {
    return raw.map((t) => safeText(t)).filter(Boolean);
  }

  if (typeof raw === "string") {
    return raw
      .split(",")
      .map((t) => t.trim())
      .filter(Boolean);
  }

  return [];
}

function getLoraCount(item) {
  if (Array.isArray(item?.loras)) return item.loras.length;
  if (typeof item?.lora_count === "number") return item.lora_count;
  return 0;
}

function matchesSearch(item, searchText) {
  if (!searchText) return true;

  const haystack = [
    item?.title,
    getRecipePrompt(item),
    ...getRecipeTags(item),
  ]
    .map((x) => normalizeText(x))
    .join(" ");

  return haystack.includes(searchText);
}

function matchesTagFilter(item, tagText) {
  if (!tagText) return true;

  const tags = getRecipeTags(item).map((t) => normalizeText(t));
  return tags.some((tag) => tag.includes(tagText));
}

function isFavoriteRecipe(item) {
  return !!(item?.favorite || item?.is_favorite);
}

async function tryToggleFavorite(item, nextValue) {
  const recipeId = extractRecipeId(item);
  if (!recipeId) return false;

  const attempts = [
    {
      url: `/api/lm/recipe/${encodeURIComponent(recipeId)}/favorite`,
      options: {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ favorite: nextValue }),
      },
    },
    {
      url: `/api/lm/recipes/${encodeURIComponent(recipeId)}/favorite`,
      options: {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ favorite: nextValue }),
      },
    },
    {
      url: `/api/lm/recipe/${encodeURIComponent(recipeId)}`,
      options: {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ favorite: nextValue }),
      },
    },
  ];

  for (const attempt of attempts) {
    try {
      const res = await fetch(attempt.url, attempt.options);
      if (res.ok) return true;
    } catch (_err) {
      // ignore
    }
  }

  return false;
}

// --------------------------------------------------
// Class-based UI helpers
// --------------------------------------------------

function createIconButton(symbol, title) {
  const btn = document.createElement("button");
  btn.type = "button";
  btn.textContent = symbol;
  btn.title = title;
  btn.className = "lm-recipe-card__icon-btn";
  return btn;
}

function createSmallButton(label, active = false) {
  const btn = document.createElement("button");
  btn.type = "button";
  btn.textContent = label;
  btn.className = `lm-recipes-button${active ? " lm-recipes-button--active" : ""}`;
  return btn;
}

function createInput(placeholder, value = "") {
  const input = document.createElement("input");
  input.type = "text";
  input.placeholder = placeholder;
  input.value = value;
  input.className = "lm-recipes-input";
  return input;
}

// --------------------------------------------------
// Info Overlay
// --------------------------------------------------

function buildInfoOverlay(item, onClose) {
  const recipeId = extractRecipeId(item);

  const panel = document.createElement("div");
  panel.className = "lm-recipe-info";

  const closeBtn = document.createElement("button");
  closeBtn.type = "button";
  closeBtn.textContent = "×";
  closeBtn.title = "Close";
  closeBtn.className = "lm-recipe-info__close";
  closeBtn.addEventListener("click", (e) => {
    e.preventDefault();
    e.stopPropagation();
    onClose();
  });

  const title = document.createElement("div");
  title.className = "lm-recipe-info__title";
  title.textContent = safeText(item?.title || recipeId || "Recipe");

  const prompt = document.createElement("div");
  prompt.innerHTML = `<strong>Prompt:</strong> ${truncate(getRecipePrompt(item), 120)}`;

  const sampler = document.createElement("div");
  sampler.innerHTML = `<strong>Sampler:</strong> ${safeText(getRecipeSampler(item), "-")}`;

  const steps = document.createElement("div");
  steps.innerHTML = `<strong>Steps:</strong> ${safeText(getRecipeSteps(item), "-")}`;

  const cfg = document.createElement("div");
  cfg.innerHTML = `<strong>CFG:</strong> ${safeText(getRecipeCfg(item), "-")}`;

  const seed = document.createElement("div");
  seed.innerHTML = `<strong>Seed:</strong> ${safeText(getRecipeSeed(item), "-")}`;

  const negative = document.createElement("div");
  negative.innerHTML = `<strong>Neg:</strong> ${truncate(getRecipeNegativePrompt(item), 90) || "-"}`;

  const loras = document.createElement("div");
  loras.innerHTML = `<strong>LoRAs:</strong> ${getLoraCount(item)}`;

  const tags = getRecipeTags(item);
  const tagsLine = document.createElement("div");
  tagsLine.innerHTML = `<strong>Tags:</strong> ${tags.length ? truncate(tags.join(", "), 100) : "-"}`;

  panel.appendChild(closeBtn);
  panel.appendChild(title);
  panel.appendChild(prompt);
  panel.appendChild(negative);
  panel.appendChild(sampler);
  panel.appendChild(steps);
  panel.appendChild(cfg);
  panel.appendChild(seed);
  panel.appendChild(loras);
  panel.appendChild(tagsLine);

  return panel;
}

// --------------------------------------------------
// Selected Preview
// --------------------------------------------------

function createSelectedPreview(item, onClear) {
  const wrap = document.createElement("div");
  wrap.className = "lm-recipes-selected-preview";

  const img = document.createElement("img");
  img.className = "lm-recipes-selected-preview__image";
  img.src = item?.file_url || "/loras_static/images/no-preview.png";
  img.alt = safeText(item?.title || "Selected recipe");

  img.onerror = () => {
    img.src = "/loras_static/images/no-preview.png";
    img.style.opacity = "0.5";
  };

  const content = document.createElement("div");
  content.className = "lm-recipes-selected-preview__content";

  const topRow = document.createElement("div");
  topRow.className = "lm-recipes-selected-preview__top";

  const title = document.createElement("div");
  title.className = "lm-recipes-selected-preview__title";
  title.textContent = safeText(item?.title || extractRecipeId(item) || "Selected recipe");

  const clearBtn = createIconButton("×", "Clear selection");
  clearBtn.addEventListener("click", (e) => {
    e.preventDefault();
    e.stopPropagation();
    onClear();
  });

  const prompt = document.createElement("div");
  prompt.className = "lm-recipes-selected-preview__prompt";
  prompt.textContent = truncate(getRecipePrompt(item), 100) || "No prompt";

  const meta = document.createElement("div");
  meta.className = "lm-recipes-selected-preview__meta";
  meta.textContent =
    `steps ${safeText(getRecipeSteps(item), "-")} • ` +
    `sampler ${safeText(getRecipeSampler(item), "-")} • ` +
    `cfg ${safeText(getRecipeCfg(item), "-")} • ` +
    `${getLoraCount(item)} LoRAs`;

  topRow.appendChild(title);
  topRow.appendChild(clearBtn);

  content.appendChild(topRow);
  content.appendChild(prompt);
  content.appendChild(meta);

  wrap.appendChild(img);
  wrap.appendChild(content);

  return wrap;
}

// --------------------------------------------------
// Recipe Card
// --------------------------------------------------

function createCard(item, isSelected, onApply, onFavoriteChange) {
  const recipeId = extractRecipeId(item);
  let showInfo = false;
  let isFavorite = isFavoriteRecipe(item);

  const card = document.createElement("div");
  card.className = "lm-recipe-card";
  card.dataset.selected = isSelected ? "true" : "false";

  const mediaWrap = document.createElement("div");
  mediaWrap.className = "lm-recipe-card__media";

  const img = document.createElement("img");
  img.className = "lm-recipe-card__image";
  img.src = item?.file_url || "/loras_static/images/no-preview.png";
  img.loading = "lazy";
  img.draggable = false;
  img.alt = safeText(item?.title || recipeId || "recipe");

  img.onerror = () => {
    img.src = "/loras_static/images/no-preview.png";
    img.style.opacity = "0.5";
  };

  const overlay = document.createElement("div");
  overlay.className = "lm-recipe-card__overlay";

  const leftControls = document.createElement("div");
  leftControls.className = "lm-recipe-card__overlay-group";

  const rightControls = document.createElement("div");
  rightControls.className = "lm-recipe-card__overlay-group";

  const favoriteBtn = createIconButton(isFavorite ? "★" : "☆", "Favorite");
  const applyBtn = createIconButton("➜", "Apply");
  const infoBtn = createIconButton("ⓘ", "Info");

  function syncFavoriteVisual() {
    favoriteBtn.textContent = isFavorite ? "★" : "☆";
    favoriteBtn.classList.toggle("lm-recipe-card__icon-btn--favorite-active", isFavorite);
  }

  syncFavoriteVisual();

  favoriteBtn.addEventListener("click", async (e) => {
    e.preventDefault();
    e.stopPropagation();

    isFavorite = !isFavorite;
    syncFavoriteVisual();

    item.favorite = isFavorite;
    item.is_favorite = isFavorite;

    if (typeof onFavoriteChange === "function") {
      onFavoriteChange(recipeId, isFavorite);
    }

    const saved = await tryToggleFavorite(item, isFavorite);
    if (!saved) {
      console.warn(
        `[RecipeBrowserWidget] Favorite endpoint not confirmed for recipe ${recipeId}`
      );
    }
  });

  applyBtn.addEventListener("click", (e) => {
    e.preventDefault();
    e.stopPropagation();
    if (!recipeId) return;
    onApply(recipeId);
  });

  let infoPanel = null;

  function closeInfo() {
    showInfo = false;
    if (infoPanel) {
      infoPanel.remove();
      infoPanel = null;
    }
  }

  function openInfo() {
    closeInfo();
    showInfo = true;
    infoPanel = buildInfoOverlay(item, closeInfo);
    mediaWrap.appendChild(infoPanel);
  }

  infoBtn.addEventListener("click", (e) => {
    e.preventDefault();
    e.stopPropagation();
    if (showInfo) closeInfo();
    else openInfo();
  });

  leftControls.appendChild(favoriteBtn);
  rightControls.appendChild(infoBtn);
  rightControls.appendChild(applyBtn);

  overlay.appendChild(leftControls);
  overlay.appendChild(rightControls);

  const labelWrap = document.createElement("div");
  labelWrap.className = "lm-recipe-card__label-wrap";

  const label = document.createElement("div");
  label.className = "lm-recipe-card__title";
  label.textContent = (item?.title || recipeId || "recipe").slice(0, 28);

  const meta = document.createElement("div");
  meta.className = "lm-recipe-card__meta";
  meta.textContent = `${getLoraCount(item)} LoRAs`;

  labelWrap.appendChild(label);
  labelWrap.appendChild(meta);

  mediaWrap.appendChild(img);
  mediaWrap.appendChild(overlay);

  card.appendChild(mediaWrap);
  card.appendChild(labelWrap);

  card.addEventListener("click", (e) => {
    e.preventDefault();
    e.stopPropagation();
    if (!recipeId) return;
    onApply(recipeId);
  });

  card.addEventListener("pointerdown", (e) => e.stopPropagation());
  card.addEventListener("mousedown", (e) => e.stopPropagation());

  return card;
}

// --------------------------------------------------
// Main Widget
// --------------------------------------------------

export function addRecipeBrowserWidget(node, name, opts, callback) {
  ensureLmStyles();

  hideDefaultRecipeIdWidget(node, name);

  const container = document.createElement("div");
  container.className = "lm-recipes-container";

  forwardMiddleMouseToCanvas(container);

  const defaultHeight = 420;
  const pageSize = Number(opts?.pageSize || 60);

  let widgetValue = opts?.defaultVal || "";

  const state = {
    items: [],
    page: 1,
    loading: false,
    hasMore: true,
    selected: widgetValue || null,
    initialLoadComplete: false,
    searchText: "",
    tagText: "",
    favoritesOnly: false,
  };

  async function loadRecipes() {
    if (state.loading || !state.hasMore) return;

    state.loading = true;
    render();

    try {
      const res = await fetch(
        `/api/lm/recipes?page=${state.page}&page_size=${pageSize}`
      );

      if (!res.ok) throw new Error(`HTTP ${res.status}`);

      const data = await res.json();
      const newItems = Array.isArray(data?.items) ? data.items : [];

      state.items.push(...newItems);

      const totalPages = Number(data?.total_pages || 1);
      state.hasMore = state.page < totalPages && newItems.length > 0;

      state.page += 1;
      state.initialLoadComplete = true;
    } catch (e) {
      console.error("[RecipeBrowserWidget] fetch failed", e);
      state.initialLoadComplete = true;
      state.hasMore = false;
    } finally {
      state.loading = false;
      render();
    }
  }

  function onApply(recipeId) {
    widgetValue = recipeId;
    state.selected = recipeId;

    if (typeof widget.callback === "function") {
      widget.callback(recipeId);
    }

    node.setDirtyCanvas(true, true);
    node.graph?.setDirtyCanvas(true, true);

    render();
  }

  function onFavoriteChange(recipeId, value) {
    const item = state.items.find((x) => extractRecipeId(x) === recipeId);
    if (!item) return;
    item.favorite = value;
    item.is_favorite = value;
    render();
  }

  function clearSelection() {
    widgetValue = "";
    state.selected = null;

    if (typeof widget.callback === "function") {
      widget.callback("");
    }

    node.setDirtyCanvas(true, true);
    node.graph?.setDirtyCanvas(true, true);

    render();
  }

  function getSelectedItem() {
    return state.items.find((x) => extractRecipeId(x) === state.selected) || null;
  }

  function getFilteredItems() {
    const searchText = normalizeText(state.searchText);
    const tagText = normalizeText(state.tagText);

    return state.items.filter((item) => {
      if (state.favoritesOnly && !isFavoriteRecipe(item)) return false;
      if (!matchesSearch(item, searchText)) return false;
      if (!matchesTagFilter(item, tagText)) return false;
      return true;
    });
  }

  function renderToolbar() {
    const wrap = document.createElement("div");
    wrap.className = "lm-recipes-toolbar";

    const searchInput = createInput("Search recipes...", state.searchText);
    searchInput.addEventListener("input", (e) => {
      state.searchText = e.target.value || "";
      render();
    });

    const tagInput = createInput("Filter by tag...", state.tagText);
    tagInput.addEventListener("input", (e) => {
      state.tagText = e.target.value || "";
      render();
    });

    const row = document.createElement("div");
    row.className = "lm-recipes-toolbar__row";

    const favoritesBtn = createSmallButton("★ Favorites only", state.favoritesOnly);
    favoritesBtn.addEventListener("click", (e) => {
      e.preventDefault();
      e.stopPropagation();
      state.favoritesOnly = !state.favoritesOnly;
      render();
    });

    const clearBtn = createSmallButton("Clear filters", false);
    clearBtn.addEventListener("click", (e) => {
      e.preventDefault();
      e.stopPropagation();
      state.searchText = "";
      state.tagText = "";
      state.favoritesOnly = false;
      render();
    });

    row.appendChild(favoritesBtn);
    row.appendChild(clearBtn);

    wrap.appendChild(searchInput);
    wrap.appendChild(tagInput);
    wrap.appendChild(row);

    return wrap;
  }

  function renderStatus(text) {
    const el = document.createElement("div");
    el.className = "lm-recipes-status";
    el.textContent = text;
    return el;
  }

  function render() {
    container.innerHTML = "";

    const selectedItem = getSelectedItem();
    if (selectedItem) {
      container.appendChild(createSelectedPreview(selectedItem, clearSelection));
    }

    container.appendChild(renderToolbar());

    const filteredItems = getFilteredItems();

    const grid = document.createElement("div");
    grid.className = "lm-recipes-grid";

    filteredItems.forEach((item) => {
      const recipeId = extractRecipeId(item);
      const isSelected = recipeId === state.selected;
      const card = createCard(item, isSelected, onApply, onFavoriteChange);
      grid.appendChild(card);
    });

    container.appendChild(grid);

    if (!state.initialLoadComplete && state.loading) {
      container.appendChild(renderStatus("Loading recipes..."));
      return;
    }

    if (state.initialLoadComplete && filteredItems.length === 0) {
      container.appendChild(renderStatus("No recipes match your filters"));
      return;
    }

    if (state.loading) {
      container.appendChild(renderStatus("Loading more..."));
    }
  }

  function maybeLoadMore() {
    const nearBottom =
      container.scrollTop + container.clientHeight >=
      container.scrollHeight - 200;

    if (nearBottom) {
      loadRecipes();
    }
  }

  container.addEventListener("scroll", maybeLoadMore);
  container.addEventListener("pointerdown", (e) => e.stopPropagation());
  container.addEventListener("mousedown", (e) => e.stopPropagation());
  container.addEventListener("click", (e) => e.stopPropagation());

  const widget = node.addDOMWidget(name, "custom", container, {
    getValue() {
      return widgetValue;
    },
    setValue(v) {
      widgetValue = v || "";
      state.selected = widgetValue || null;
      render();
    },
    hideOnZoom: true,
  });

  widget.callback = callback;
  widget.onRemove = () => {
    container.removeEventListener("scroll", maybeLoadMore);
    container.remove();
  };

  if (widgetValue) {
    state.selected = widgetValue;
  }

  loadRecipes();

  return {
    minWidth: 420,
    minHeight: defaultHeight,
    widget,
  };
}
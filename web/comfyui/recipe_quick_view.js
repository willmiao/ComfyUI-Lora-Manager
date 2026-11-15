import { hasRealPreview } from "./mediaTypes.js";

function el(tag, className, text) {
  const element = document.createElement(tag);
  if (className) element.className = className;
  if (text !== undefined) element.textContent = text;
  return element;
}

export function formatStrength(value) {
  const numeric = Number(value);
  return (Number.isFinite(numeric) ? numeric : 1).toFixed(2);
}

export function recipeMeta(recipe) {
  const parts = [`${recipe.loraCount} LoRA${recipe.loraCount === 1 ? "" : "s"}`];
  if (recipe.baseModel) parts.push(recipe.baseModel);
  return parts.join(" · ");
}

function issueText(recipe) {
  const issues = [];
  if (recipe.missing) issues.push(`${recipe.missing} missing`);
  if (recipe.deleted) issues.push(`${recipe.deleted} deleted`);
  return issues.join(" · ");
}

/**
 * Append recipe result rows to the picker's results column.
 *
 * Rows are buttons so the panel's existing `.lm-quick__row` selection styling
 * and keyboard navigation keep working; the thumbnail is the recipe preview.
 */
export function appendRecipeRows({
  container,
  recipes,
  selectedIndex,
  onSelect,
  onActivate,
}) {
  recipes.forEach((recipe, index) => {
    const row = el("button", "lm-quick__row lm-quick__recipe-row");
    row.type = "button";
    row.setAttribute("role", "option");
    row.setAttribute("aria-selected", String(index === selectedIndex));
    row.classList.toggle("is-selected", index === selectedIndex);
    row.dataset.recipeId = recipe.id;
    // With a preview the tooltip already labels the recipe; the native title
    // would pop over it. Keep the title only for preview-less rows, where it
    // is the only way to read a truncated title.
    if (!hasRealPreview(recipe.fileUrl)) row.title = recipe.title;

    const thumb = recipe.fileUrl
      ? el("img", "lm-quick__recipe-thumb")
      : el("span", "lm-quick__recipe-thumb lm-quick__recipe-thumb--empty", "?");
    if (recipe.fileUrl) {
      thumb.src = recipe.fileUrl;
      thumb.alt = "";
      thumb.loading = "lazy";
    }

    const body = el("span", "lm-quick__recipe-body");
    const head = el("span", "lm-quick__row-head");
    head.appendChild(el("span", "lm-quick__row-name", recipe.title));
    if (recipe.favorite) {
      const star = el("span", "lm-quick__recipe-favorite", "★");
      star.title = "Favorite";
      head.appendChild(star);
    }
    body.appendChild(head);
    body.appendChild(el("span", "lm-quick__row-path", recipeMeta(recipe)));
    const issues = issueText(recipe);
    if (issues) {
      body.appendChild(el("span", "lm-quick__recipe-warning", issues));
    }

    row.append(thumb, body);
    row.addEventListener("click", () => onSelect(index));
    row.addEventListener("dblclick", () => onActivate(index));
    container.appendChild(row);
  });
}

function appendLoraList(container, recipe) {
  const section = el("section", "lm-quick__recipe-loras");
  section.appendChild(el(
    "h3",
    "lm-quick__recipe-heading",
    `LoRAs (${recipe.loraCount})`,
  ));
  if (!recipe.loras.length) {
    section.appendChild(el("div", "lm-quick__recipe-note", "This recipe has no LoRAs."));
    container.appendChild(section);
    return;
  }
  for (const lora of recipe.loras) {
    const row = el("div", `lm-quick__recipe-lora is-${lora.status}`);
    const name = el("span", "lm-quick__recipe-lora-name", lora.label || lora.name);
    name.title = lora.name;
    row.appendChild(name);
    row.appendChild(el("span", "lm-quick__recipe-lora-strength", formatStrength(lora.strength)));
    if (lora.status !== "ready") {
      row.appendChild(el("span", "lm-quick__recipe-lora-status", lora.status));
    }
    section.appendChild(row);
  }
  container.appendChild(section);
}

/**
 * Render the recipe detail column from the list row and/or the fetched detail.
 *
 * Both payloads carry the enriched LoRA list, so the actions stay usable while
 * the detail request is in flight; the detail pass only replaces the content
 * with the fuller payload (and any error message).
 */
export function renderRecipeDetail({
  container,
  recipe,
  targetNode,
  loading = false,
  error = "",
  onApply,
  onOpen,
}) {
  container.replaceChildren();
  if (!recipe) {
    container.appendChild(el("div", "lm-quick__empty", "Select a recipe to see its LoRAs."));
    return;
  }

  if (recipe.fileUrl) {
    const preview = el("img", "lm-quick__preview");
    preview.src = recipe.fileUrl;
    preview.alt = "";
    container.appendChild(preview);
  }
  container.appendChild(el("h2", "lm-quick__name", recipe.title));
  container.appendChild(el("div", "lm-quick__meta", recipeMeta(recipe)));

  if (loading) {
    container.appendChild(el("div", "lm-quick__recipe-note", "Loading recipe details…"));
  }
  if (error) {
    container.appendChild(el("div", "lm-quick__empty", error));
  }

  appendLoraList(container, recipe);

  const issues = issueText(recipe);
  if (issues) {
    container.appendChild(el(
      "div",
      "lm-quick__recipe-note",
      `${issues} will be skipped when applying.`,
    ));
  }
  if (!targetNode) {
    container.appendChild(el(
      "div",
      "lm-quick__recipe-note",
      "No compatible LoRA node in this workflow.",
    ));
  }

  const available = recipe.loras.filter((lora) => lora.status === "ready").length;
  const actions = el("div", "lm-quick__actions");
  const append = el("button", "lm-quick__primary", "Append");
  append.type = "button";
  append.disabled = !targetNode || available === 0;
  append.title = "Add the recipe's available LoRAs to the target node";
  append.addEventListener("click", () => onApply("append"));
  const replace = el("button", "lm-quick__secondary", "Replace");
  replace.type = "button";
  replace.disabled = !targetNode || available === 0;
  replace.title = "Replace the target node's LoRAs with the recipe's available LoRAs";
  replace.addEventListener("click", () => onApply("replace"));
  const open = el("button", "lm-quick__secondary", "Open in manager");
  open.type = "button";
  open.addEventListener("click", () => onOpen(recipe.id));
  actions.append(append, replace, open);
  container.appendChild(actions);

  container.appendChild(el(
    "div",
    "lm-quick__recipe-note",
    "Checkpoint and prompt are not applied.",
  ));
}

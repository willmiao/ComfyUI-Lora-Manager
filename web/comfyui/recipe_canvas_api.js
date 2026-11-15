import { api } from "../../scripts/api.js";
import { lmUrl } from "./base_path.js";
import { normalizeLoraNameKey } from "./loras_widget_utils.js";

const DEFAULT_PAGE_SIZE = 30;

async function readJson(response, fallbackMessage) {
  const data = await response.json().catch(() => ({}));
  if (!response.ok || data.success === false) {
    throw new Error(data.error || fallbackMessage);
  }
  return data;
}

function normalizeStrength(entry) {
  const raw = entry?.strength ?? entry?.weight;
  const numeric = Number(raw);
  return Number.isFinite(numeric) ? numeric : undefined;
}

function normalizeRecipeLora(entry) {
  if (!entry || typeof entry !== "object" || entry.exclude) return null;
  const name = normalizeLoraNameKey(
    entry.file_name ?? entry.name ?? entry.fileName ?? "",
  );
  if (!name) return null;
  const isDeleted = entry.isDeleted === true;
  const inLibrary = entry.inLibrary !== false && !isDeleted;
  return {
    name,
    label: entry.modelName || entry.model_name || entry.name || name,
    strength: normalizeStrength(entry),
    inLibrary,
    isDeleted,
    exclude: false,
    status: isDeleted ? "deleted" : inLibrary ? "ready" : "missing",
  };
}

/**
 * Normalize a recipe list/detail payload into the shape the canvas view uses.
 *
 * The backend enriches every recipe LoRA with `inLibrary`/`isDeleted` in both
 * the paginated list and the detail response, so the view can count missing
 * entries without fetching details for every row.
 */
export function normalizeRecipe(recipe) {
  const raw = recipe && typeof recipe === "object" ? recipe : {};
  const loras = (Array.isArray(raw.loras) ? raw.loras : [])
    .map(normalizeRecipeLora)
    .filter(Boolean);
  const counts = { ready: 0, missing: 0, deleted: 0 };
  for (const lora of loras) {
    counts[lora.status] = (counts[lora.status] || 0) + 1;
  }
  const fallbackTitle = raw.file_name || raw.fileName || raw.name || "Untitled recipe";
  return {
    id: String(raw.id ?? ""),
    title: raw.title || raw.name || fallbackTitle,
    fileUrl: raw.file_url || raw.preview_url || "",
    baseModel: raw.base_model || "",
    favorite: raw.favorite === true,
    hasWorkflow: raw.has_workflow === true,
    loras,
    loraCount: loras.length,
    ready: counts.ready,
    missing: counts.missing,
    deleted: counts.deleted,
    raw,
  };
}

export async function searchRecipes(query = "", limit = DEFAULT_PAGE_SIZE) {
  const params = new URLSearchParams({
    page: "1",
    page_size: String(limit),
    sort_by: "date",
    search: query,
    search_title: "true",
    search_tags: "true",
    search_lora_name: "true",
    search_lora_model: "true",
    search_prompt: "true",
    recursive: "true",
  });
  const data = await readJson(
    await api.fetchApi(`/lm/recipes?${params}`),
    "Failed to search recipes",
  );
  const items = Array.isArray(data.items) ? data.items : [];
  return items.map(normalizeRecipe).filter((recipe) => recipe.id);
}

export async function fetchRecipeDetails(recipeId) {
  if (!recipeId) throw new Error("Unable to determine recipe ID");
  const data = await readJson(
    await api.fetchApi(`/lm/recipe/${encodeURIComponent(recipeId)}`),
    "Failed to load recipe details",
  );
  return normalizeRecipe(data);
}

export function openRecipeManager(recipeId = "") {
  const hash = recipeId ? `#recipe=${encodeURIComponent(recipeId)}` : "";
  const url = `${window.location.origin}${lmUrl("/loras/recipes")}${hash}`;
  window.open(url, "lm-lora-manager");
}

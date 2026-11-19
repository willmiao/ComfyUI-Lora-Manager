import { api } from "../../scripts/api.js";
import { lmUrl } from "./base_path.js";

async function request(path, options = {}) {
  const response = await api.fetchApi(path, options);
  const data = await response.json().catch(() => ({}));
  if (!response.ok || data.success === false) {
    const error = new Error(data.error || `HTTP ${response.status}`);
    error.payload = data;
    throw error;
  }
  return data;
}

export function searchWildcardLibrary(search = "") {
  const query = new URLSearchParams({ search });
  return request(`/lm/wildcards/active?${query}`);
}

export function setWildcardActive(filePath, active) {
  return request(`/lm/wildcards/${active ? "activate" : "deactivate"}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ file_path: filePath }),
  });
}

export function openWildcardManager(filePath = "") {
  const hash = filePath ? `#model=${encodeURIComponent(filePath)}` : "";
  window.location.href = `${window.location.origin}${lmUrl("/wildcards")}${hash}`;
}

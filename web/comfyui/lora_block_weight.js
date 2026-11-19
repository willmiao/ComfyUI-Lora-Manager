export function normalizeLbwConfig(config) {
  const rawWeights = config && typeof config === "object" && config.weights && typeof config.weights === "object"
    ? config.weights
    : {};
  const weights = {};
  for (const [blockId, rawValue] of Object.entries(rawWeights)) {
    const value = Number(rawValue);
    if (Number.isFinite(value)) weights[blockId] = value;
  }
  return {
    enabled: config?.enabled === true,
    weights,
  };
}

export function hasActiveLbw(config) {
  const normalized = normalizeLbwConfig(config);
  return normalized.enabled && Object.values(normalized.weights).some((value) => value !== 1);
}

export function formatLbwSyntax(config) {
  if (!hasActiveLbw(config)) return "";
  const { weights } = normalizeLbwConfig(config);
  const parts = Object.entries(weights).map(([blockId, value]) => {
    const formatted = Number(value.toFixed(4)).toString();
    return `${blockId}=${formatted}`;
  });
  return `LBW=${parts.join(";")}`;
}

export function parseLbwSyntax(value) {
  const text = String(value || "");
  if (!text.toUpperCase().startsWith("LBW=")) return null;
  const weights = {};
  for (const item of text.slice(4).split(";")) {
    const [blockId, rawValue] = item.split("=");
    const weight = Number(rawValue);
    if (/^(BASE|IN|MID|OUT|DOUBLE|SINGLE|IN\d+|MID\d+|OUT\d+|D\d+|S\d+)$/.test(blockId) && Number.isFinite(weight)) {
      weights[blockId] = weight;
    }
  }
  return { enabled: true, weights };
}

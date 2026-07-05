export const BAND_COLORS = {
  high: "#ef4444",
  moderate: "#f59e0b",
  low: "#22c55e",
  unknown: "#475569",
};

export const BAND_LABEL = {
  high: "High", moderate: "Moderate", low: "Low", unknown: "No score",
};

// Human labels for model feature names (explainability panel).
export const FEATURE_LABEL = {
  ward_flood_baseline: "Ward complaint baseline",
  rain_fcst_1d: "Forecast rain (24h)",
  rain_prev_1d: "Rain (prev 24h)",
  rain_prev_3d: "Rain (prev 3 days)",
  rain_prev_7d: "Antecedent rain (7 days)",
  velocity_prev_1d: "Complaint velocity (1d)",
  velocity_prev_3d: "Complaint velocity (3d)",
  is_low_lying: "Low-lying area",
  historical_flood_count: "Flood-prone spots",
  month: "Season (month)",
  is_monsoon: "Monsoon flag",
};

export const featureLabel = (f) => FEATURE_LABEL[f] || f;

export const pct = (x) => (x == null ? "—" : `${Math.round(x * 100)}%`);

export const num = (x) =>
  x == null ? "—" : x.toLocaleString(undefined, { maximumFractionDigits: 2 });

export function timeAgo(iso) {
  if (!iso) return "";
  try {
    return new Date(iso).toLocaleString(undefined, {
      dateStyle: "medium", timeStyle: "short",
    });
  } catch {
    return iso;
  }
}

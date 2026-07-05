// API client. Dev hits the deployed Cloud Run API (CORS open); prod is same-origin.
const BASE = import.meta.env.DEV
  ? "https://varuna-229692962627.asia-south1.run.app"
  : "";

async function getJSON(path) {
  const r = await fetch(BASE + path);
  if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
  return r.json();
}

async function postJSON(path, body) {
  const r = await fetch(BASE + path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
  return r.json();
}

export const api = {
  cities: () => getJSON("/api/cities"),
  summary: (city, horizon = 24) =>
    getJSON(`/api/risk/summary?city=${city}&horizon=${horizon}`),
  wardsGeojson: (city, horizon = 24) =>
    getJSON(`/api/risk/wards.geojson?city=${city}&horizon=${horizon}`),
  wardsRanked: (city, horizon = 24) =>
    getJSON(`/api/risk/wards?city=${city}&horizon=${horizon}`),
  wardDetail: (wardId, city, horizon = 24) =>
    getJSON(`/api/risk/ward/${wardId}?city=${city}&horizon=${horizon}`),
  cityPulse: (question) => postJSON("/api/citypulse/chat", { question }),
  reports: (city) => getJSON(`/api/reports?city=${city}`),
  agentStatus: () => getJSON("/api/agents/status"),
  responsePlan: (focus) => postJSON("/api/agents/response-plan", { focus: focus || null }),
};

export default api;

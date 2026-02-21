// frontend/js/api.js
const API_BASE = "http://localhost:8000/api";

export async function getTopHashtags(n = 10) {
  const res = await fetch(`${API_BASE}/trends/hashtags?n=${n}`);
  if (!res.ok) throw new Error(`GET /trends/hashtags ${res.status}`);
  return res.json();
}

export async function getStats() {
  const res = await fetch(`${API_BASE}/stats/interactions`);
  if (!res.ok) throw new Error(`GET /stats/interactions ${res.status}`);
  return res.json();
}

export async function postEvent(payload) {
  const res = await fetch(`${API_BASE}/events`, {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify(payload)
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`POST /events ${res.status} ${text}`);
  }
  return res.json();
}

export async function loadRAML() {
  const res = await fetch("api.raml");
  if (!res.ok) throw new Error(`GET api.raml ${res.status}`);
  return res.text();
}
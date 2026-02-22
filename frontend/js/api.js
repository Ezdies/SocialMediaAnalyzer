// frontend/api.js
const BASE = (window.location.hostname === "localhost") ? "http://localhost:8000/api" : "/api";

async function request(path, opts = {}) {
  const url = `${BASE}${path}`;
  opts.headers = Object.assign({ 'Content-Type': 'application/json' }, opts.headers || {});
  const res = await fetch(url, opts);
  if (!res.ok) {
    const txt = await res.text().catch(()=>null);
    let msg = `HTTP ${res.status}`;
    try {
      const j = JSON.parse(txt);
      msg = j.error || j.detail || j.message || msg;
    } catch(e){}
    throw new Error(msg);
  }
  const contentType = res.headers.get('content-type') || '';
  if (contentType.includes('application/json')) return await res.json();
  return await res.text();
}

export async function postEvent(payload) {
  // payload: { type, hashtags: [], user_id }
  const safe = {
    type: payload.type,
    hashtags: Array.isArray(payload.hashtags) ? payload.hashtags : (payload.hashtags ? [payload.hashtags] : []),
    user_id: payload.user_id || payload.user || "",
    metadata: payload.metadata || {}
  };
  return await request('/events', { method: 'POST', body: JSON.stringify(safe) });
}

export async function getTopHashtags(n = 10) {
  const q = `?n=${encodeURIComponent(n)}`;
  const data = await request(`/trends/hashtags${q}`, { method: 'GET' });
  // API returns array [{hashtag, count}]
  return Array.isArray(data) ? data : [];
}

export async function getStats() {
  return await request('/stats/interactions', { method: 'GET' });
}

export async function health() {
  return await request('/health', { method: 'GET' });
}
// frontend/js/ui.js
export function renderTags(container, tags) {
  container.innerHTML = "";
  tags.forEach(t => {
    const li = document.createElement("li");
    li.textContent = `#${t.hashtag} (${t.count})`;
    container.appendChild(li);
  });
}

export function renderStats(container, stats) {
  container.textContent = JSON.stringify(stats, null, 2);
}

export function appendLog(logEl, msg) {
  const now = new Date().toISOString();
  if (logEl.textContent === "Brak akcji.") logEl.textContent = "";
  logEl.textContent = `${now}  ${msg}\n` + logEl.textContent;
}

export function setProgress(barEl, ratio) {
  const pct = Math.round(Math.max(0, Math.min(1, ratio)) * 100);
  barEl.style.width = pct + "%";
}
// frontend/ui.js
export function renderTags(container, tags) {
  container.innerHTML = '';
  if (!Array.isArray(tags) || tags.length === 0) {
    container.innerHTML = '<li>Brak danych</li>';
    return;
  }
  tags.forEach(it => {
    const tag = it.hashtag || it.tag || it[0] || '';
    const count = it.count || it[1] || 0;
    const li = document.createElement('li');
    li.textContent = `${tag.startsWith('#') ? tag : '#' + tag} — ${count}`;
    container.appendChild(li);
  });
}

export function renderStats(container, stats) {
  container.textContent = `Likes: ${stats.likes || 0}  Comments: ${stats.comments || 0}  Shares: ${stats.shares || 0}`;
}

export function appendLog(s) {
  const el = document.getElementById('logBox');
  const time = new Date().toLocaleTimeString();
  const line = `[${time}] ${s}\n`;
  if (el) {
    el.textContent = line + el.textContent;
  } else {
    console.log(line);
  }
}

export function showLastEventId(id) {
  const el = document.getElementById('lastEventId');
  if (el) el.textContent = id || '';
}
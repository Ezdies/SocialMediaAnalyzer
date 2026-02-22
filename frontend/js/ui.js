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

export function renderTrends(container, trends) {
  container.innerHTML = '';
  if (!Array.isArray(trends) || trends.length === 0) {
    container.innerHTML = '<li>No data</li>';
    return;
  }
  trends.forEach((it, idx) => {
    const tag = it.hashtag || '';
    const count = it.count || 0;
    const li = document.createElement('li');
    li.textContent = `${idx + 1}. ${tag.startsWith('#') ? tag : '#' + tag} (${count})`;
    container.appendChild(li);
  });
}

export function renderUsers(container, users) {
  container.innerHTML = '';
  if (!Array.isArray(users) || users.length === 0) {
    container.innerHTML = '<li>No data</li>';
    return;
  }
  users.forEach((it, idx) => {
    const user = it.user || 'Unknown';
    const count = it.activity_count || 0;
    const li = document.createElement('li');
    li.textContent = `${idx + 1}. ${user} (${count} events)`;
    container.appendChild(li);
  });
}

export function renderComments(container, comments) {
  container.innerHTML = '';
  if (!Array.isArray(comments) || comments.length === 0) {
    container.innerHTML = '<li>No comments</li>';
    return;
  }
  comments.forEach((it, idx) => {
    const user = it.user || '';
    const comment = it.comment || '';
    const ts = it.ts ? new Date(Number(it.ts)).toLocaleString() : '';
    const li = document.createElement('li');
    li.textContent = `${ts} ${user ? user + ': ' : ''}${comment}`;
    container.appendChild(li);
  });
}
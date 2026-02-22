// frontend/app.js
import * as API from "./api.js";
import { runBurst } from "./sim.js";
import { renderTags, renderStats, appendLog, showLastEventId, renderTrends, renderUsers } from "./ui.js";

const topList = document.getElementById('topList');
const statsBox = document.getElementById('statsBox');
const logBox = document.getElementById('logBox');
const lastId = document.getElementById('lastEventId');
const trendsList = document.getElementById('trendsList');
const usersList = document.getElementById('usersList');

let currentHashtagPeriod = '1h';
let currentUserPeriod = 'all';

async function loadTrends(period = '1h') {
  try {
    const trends = await API.getHashtagsByPeriod(period, 10);
    renderTrends(trendsList, trends);
    currentHashtagPeriod = period;
  } catch (e) {
    appendLog(`Trends load error: ${e.message}`);
  }
}

async function loadUsers(period = 'all') {
  try {
    const users = await API.getTopUsers(period, 10);
    renderUsers(usersList, users);
    currentUserPeriod = period;
  } catch (e) {
    appendLog(`Users load error: ${e.message}`);
  }
}

async function loadAll() {
  try {
    const tags = await API.getTopHashtags(10);
    renderTags(topList, tags);
    const stats = await API.getStats();
    renderStats(statsBox, stats);
    await loadTrends(currentHashtagPeriod);
    await loadUsers(currentUserPeriod);
  } catch (e) {
    appendLog(`Load error: ${e.message}`);
  }
}

window.loadAll = loadAll; // expose for manual calls

// wire up single-event form
const form = document.getElementById('sendForm');
if (form) {
  form.addEventListener('submit', async (ev) => {
    ev.preventDefault();
    const type = document.getElementById('evtType').value;
    const tags = document.getElementById('evtTags').value.split(',').map(s=>s.trim()).filter(Boolean);
    const user = document.getElementById('evtUser').value || ('u' + Math.floor(Math.random()*10000));
    try {
      const res = await API.postEvent({ type, hashtags: tags, user_id: user });
      appendLog(`Event posted id=${res.event_id} type=${type}`);
      showLastEventId(res.event_id);
      // quick refresh
      await loadAll();
    } catch (e) {
      appendLog(`Post error: ${e.message}`);
    }
  });
}

// wire sim button
const simBtn = document.getElementById('simBtn');
if (simBtn) {
  simBtn.addEventListener('click', async () => {
    appendLog('Starting simulator (50 events)...');
    const onProgress = (done, total) => {
      appendLog(`Simulated ${done}/${total}`);
    };
    const result = await runBurst({ count: 50, concurrency: 10, tags: ['#AI','#Redis','#Node'], onProgress });
    appendLog(`Simulator finished. Sent ${result.finished} events`);
    if (result.eventIds && result.eventIds.length) {
      showLastEventId(result.eventIds[result.eventIds.length - 1]);
    }
    await loadAll();
  });
}

// wire trend period tabs
document.querySelectorAll('.tab-hashtag').forEach(btn => {
  btn.addEventListener('click', async () => {
    document.querySelectorAll('.tab-hashtag').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    await loadTrends(btn.dataset.period);
  });
});

// wire user period tabs
document.querySelectorAll('.tab-users').forEach(btn => {
  btn.addEventListener('click', async () => {
    document.querySelectorAll('.tab-users').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    await loadUsers(btn.dataset.period);
  });
});

// initial load + polling
window.addEventListener('load', () => {
  loadAll();
  setInterval(loadAll, 5000);
});
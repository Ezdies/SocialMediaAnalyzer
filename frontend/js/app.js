// frontend/app.js
import * as API from "./api.js";
import { runBurst } from "./sim.js";
import { renderTags, renderStats, appendLog, showLastEventId } from "./ui.js";

const topList = document.getElementById('topList');
const statsBox = document.getElementById('statsBox');
const logBox = document.getElementById('logBox');
const lastId = document.getElementById('lastEventId');

async function loadAll() {
  try {
    const tags = await API.getTopHashtags(10);
    renderTags(topList, tags);
    const stats = await API.getStats();
    renderStats(statsBox, stats);
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

// initial load + polling
window.addEventListener('load', () => {
  loadAll();
  setInterval(loadAll, 5000);
});
// frontend/sim.js
import * as API from "./api.js";
import { appendLog } from "./ui.js";

/**
 * runBurst({count, concurrency, tags, onProgress})
 * sends events and collects returned event_ids
 */
export async function runBurst({ count = 100, concurrency = 20, tags = ['#AI','#Redis','#Node'], onProgress = ()=>{} } = {}) {
  const norm = tags.map(t => (t||'').trim()).filter(Boolean).map(t => t.startsWith('#') ? t : '#'+t);
  let finished = 0;
  const eventIds = [];
  const makeEvent = () => {
    const type = ['like','comment','share'][Math.floor(Math.random()*3)];
    const tag = norm[Math.floor(Math.random()*norm.length)];
    const base = { type, hashtags: [tag], user_id: 'sim-' + Math.floor(Math.random()*10000) };
    if (type === 'comment') {
      const sample = [
        'Nice post!',
        'Great insight, thanks for sharing.',
        'I totally agree with this.',
        'Could you provide more details?',
        'Interesting perspective.'
      ];
      base.comment = sample[Math.floor(Math.random()*sample.length)];
    }
    return base;
  };

  const tasks = new Array(count).fill(0).map(() => async () => {
    try {
      const ev = makeEvent();
      const res = await API.postEvent(ev);
      if (res && res.event_id) {
        eventIds.push(res.event_id);
        appendLog(`Sim event sent, id=${res.event_id}`);
      } else {
        appendLog(`Sim event sent (no id returned)`);
      }
    } catch (e) {
      appendLog(`Sim event error: ${e.message}`);
    } finally {
      finished++;
      onProgress(finished, count);
    }
  });

  // run tasks in batches of size `concurrency`
  for (let i = 0; i < tasks.length; i += concurrency) {
    const batch = tasks.slice(i, i + concurrency).map(fn => fn());
    await Promise.allSettled(batch);
    // small pause to avoid tight loop / too large burst
    await new Promise(r => setTimeout(r, 10));
  }

  return { finished, eventIds };
}
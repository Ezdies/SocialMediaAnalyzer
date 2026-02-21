// frontend/js/sim.js
import { postEvent } from "./api.js";
import { appendLog, setProgress } from "./ui.js";

export async function runBurst({ total = 100, concurrency = 20, tagPool = ["#AI","#Python"] , logEl, progressEl }) {
  const queue = Array.from({length: total}, (_, i) => i);
  let sent = 0;

  function genEvent() {
    const types = ["like","comment","share"];
    const type = types[Math.floor(Math.random() * types.length)];
    const count = Math.floor(Math.random() * 3) + 1;
    const hs = [];
    for (let i = 0; i < count; i++) hs.push(tagPool[Math.floor(Math.random() * tagPool.length)]);
    return { type, hashtags: hs, user_id: "sim_" + Math.floor(Math.random() * 100000) };
  }

  async function worker() {
    while (true) {
      const i = queue.shift();
      if (i === undefined) return;
      const ev = genEvent();
      try {
        await postEvent(ev);
        appendLog(logEl, `OK: ${JSON.stringify(ev)}`);
      } catch (err) {
        appendLog(logEl, `ERR: ${err.message}`);
      }
      sent++;
      setProgress(progressEl, sent / total);
    }
  }

  const workers = [];
  for (let w = 0; w < Math.min(concurrency, total); w++) {
    workers.push(worker());
  }
  await Promise.all(workers);
  appendLog(logEl, `Symulacja zakończona — wysłano ${sent} eventów.`);
  setProgress(progressEl, 1);
  return sent;
}
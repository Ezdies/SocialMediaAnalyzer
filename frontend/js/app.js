// frontend/js/app.js
import * as API from "./api.js";
import * as UI from "./ui.js";
import { runBurst } from "./sim.js";

const els = {
  tags: document.getElementById("tags"),
  stats: document.getElementById("stats"),
  log: document.getElementById("log"),
  topN: document.getElementById("topN"),
  btnRefresh: document.getElementById("btnRefresh"),
  eventForm: document.getElementById("eventForm"),
  evType: document.getElementById("evType"),
  evHashtags: document.getElementById("evHashtags"),
  evUser: document.getElementById("evUser"),
  quickLike: document.getElementById("quickLike"),
  quickComment: document.getElementById("quickComment"),
  quickShare: document.getElementById("quickShare"),
  btnRunBurst: document.getElementById("btnRunBurst"),
  burstCount: document.getElementById("burstCount"),
  concurrency: document.getElementById("concurrency"),
  burstTags: document.getElementById("burstTags"),
  progressBar: document.getElementById("progressBar"),
  ramlView: document.getElementById("ramlView"),
  tabDashboard: document.getElementById("tabDashboard"),
  tabRAML: document.getElementById("tabRAML"),
  tabSim: document.getElementById("tabSim"),
  dashboard: document.getElementById("dashboard"),
  ramlPanel: document.getElementById("ramlPanel"),
  simPanel: document.getElementById("simPanel"),
  btnRefreshHeader: document.getElementById("btnRefresh")
};

async function loadAll() {
  try {
    const n = Number(els.topN.value) || 10;
    const tags = await API.getTopHashtags(n);
    UI.renderTags(els.tags, tags);
  } catch (err) {
    UI.appendLog(els.log, `Błąd pobierania hashtagów: ${err.message}`);
    els.tags.innerHTML = "<li>Nie można pobrać</li>";
  }

  try {
    const stats = await API.getStats();
    UI.renderStats(els.stats, stats);
  } catch (err) {
    UI.appendLog(els.log, `Błąd pobierania statystyk: ${err.message}`);
    els.stats.textContent = `Błąd: ${err.message}`;
  }
}

// form
els.eventForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  const type = els.evType.value;
  const hashtags = els.evHashtags.value.split(",").map(s => s.trim()).filter(Boolean);
  const user_id = els.evUser.value || "";
  const payload = { type, hashtags, user_id };
  try {
    const res = await API.postEvent(payload);
    UI.appendLog(els.log, `OK: ${JSON.stringify(payload)} -> ${JSON.stringify(res)}`);
  } catch (err) {
    UI.appendLog(els.log, `ERROR: ${err.message}`);
  }
  loadAll();
});

// quick
els.quickLike.addEventListener("click", async () => {
  const payload = { type: "like", hashtags: ["#AI", "#ML"], user_id: "demo" };
  try { await API.postEvent(payload); UI.appendLog(els.log, `OK quick: like`); } catch (e) { UI.appendLog(els.log, `ERR quick: ${e.message}`); }
  loadAll();
});
els.quickComment.addEventListener("click", async () => {
  const payload = { type: "comment", hashtags: ["#Python"], user_id: "demo" };
  try { await API.postEvent(payload); UI.appendLog(els.log, `OK quick: comment`); } catch (e) { UI.appendLog(els.log, `ERR quick: ${e.message}`); }
  loadAll();
});
els.quickShare.addEventListener("click", async () => {
  const payload = { type: "share", hashtags: ["#Redis"], user_id: "demo" };
  try { await API.postEvent(payload); UI.appendLog(els.log, `OK quick: share`); } catch (e) { UI.appendLog(els.log, `ERR quick: ${e.message}`); }
  loadAll();
});

// burst
els.btnRunBurst.addEventListener("click", async () => {
  const total = Number(els.burstCount.value) || 100;
  const concurrency = Number(els.concurrency.value) || 20;
  const tagPool = els.burstTags.value.split(",").map(s => s.trim()).filter(Boolean);
  UI.appendLog(els.log, `Start symulacji: total=${total} concurrency=${concurrency}`);
  els.progressBar.style.width = "0%";
  await runBurst({ total, concurrency, tagPool, logEl: els.log, progressEl: els.progressBar });
  loadAll();
});

// refresh button
els.btnRefreshHeader.addEventListener("click", loadAll);

// tabs
els.tabDashboard.addEventListener("click", () => {
  els.dashboard.classList.remove("hidden"); els.ramlPanel.classList.add("hidden"); els.simPanel.classList.add("hidden");
  els.tabDashboard.classList.add("active"); els.tabRAML.classList.remove("active"); els.tabSim.classList.remove("active");
});
els.tabRAML.addEventListener("click", async () => {
  els.dashboard.classList.add("hidden"); els.ramlPanel.classList.remove("hidden"); els.simPanel.classList.add("hidden");
  els.tabRAML.classList.add("active"); els.tabDashboard.classList.remove("active"); els.tabSim.classList.remove("active");
  try {
    const raml = await API.loadRAML();
    els.ramlView.textContent = raml;
  } catch (err) {
    UI.appendLog(els.log, `Błąd ładowania RAML: ${err.message}`);
    els.ramlView.textContent = `Błąd: ${err.message}`;
  }
});
els.tabSim.addEventListener("click", () => {
  els.dashboard.classList.add("hidden"); els.ramlPanel.classList.add("hidden"); els.simPanel.classList.remove("hidden");
  els.tabSim.classList.add("active"); els.tabDashboard.classList.remove("active"); els.tabRAML.classList.remove("active");
});

// auto reload
loadAll();
setInterval(loadAll, 5000);
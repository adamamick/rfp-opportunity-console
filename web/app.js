const generateBtn = document.getElementById("generateBtn");
const minLevel = document.getElementById("minLevel");
const days = document.getElementById("days");
const maxItems = document.getElementById("maxItems");
const useCached = document.getElementById("useCached");
const statusEl = document.getElementById("status");
const summaryEl = document.getElementById("summary");
const resultsEl = document.getElementById("results");
const resultsMetaEl = document.getElementById("resultsMeta");
const cardTemplate = document.getElementById("cardTemplate");

function setStatus(text) {
  statusEl.textContent = text;
}

async function pingServer() {
  try {
    const res = await fetch("/api/ping");
    if (!res.ok) {
      throw new Error(`HTTP ${res.status}`);
    }
    return true;
  } catch {
    return false;
  }
}

function metricCard(label, value) {
  const wrap = document.createElement("article");
  wrap.className = "metric";
  wrap.innerHTML = `<p class="label">${label}</p><p class="value">${value}</p>`;
  return wrap;
}

function renderSummary(data) {
  summaryEl.innerHTML = "";
  summaryEl.appendChild(metricCard("Generated At (UTC)", data.generated_at || "-"));
  summaryEl.appendChild(metricCard("Total", data.total_items ?? 0));
  summaryEl.appendChild(metricCard("New", data.new_items ?? 0));
  summaryEl.appendChild(metricCard("High", data.high_priority ?? 0));
  summaryEl.appendChild(metricCard("Medium", data.medium_priority ?? 0));
}

function renderResults(items) {
  resultsEl.innerHTML = "";
  if (!items || !items.length) {
    const empty = document.createElement("div");
    empty.className = "empty";
    empty.textContent = "No opportunities met this filter in the latest run.";
    resultsEl.appendChild(empty);
    return;
  }

  for (const item of items) {
    const node = cardTemplate.content.firstElementChild.cloneNode(true);
    const badge = node.querySelector(".badge");
    const score = node.querySelector(".score");
    const title = node.querySelector(".title");
    const meta = node.querySelector(".meta");
    const terms = node.querySelector(".terms");
    const link = node.querySelector(".link");

    const level = (item.level || "LOW").toLowerCase();
    badge.classList.add(level);
    badge.textContent = item.level || "LOW";
    score.textContent = `score:${item.score}`;
    title.textContent = item.title || "(untitled)";
    meta.textContent = `Published: ${item.published} | Age: ${item.age_days} day(s)`;
    terms.textContent = `Matches: ${(item.reason_terms || []).join(", ") || "none"}`;
    link.href = item.link || "#";

    resultsEl.appendChild(node);
  }
}

async function loadLatest() {
  const alive = await pingServer();
  if (!alive) {
    setStatus("Server connection failed. Start server with: python3 src/dashboard_server.py --open");
    return;
  }

  try {
    const res = await fetch("/api/latest");
    if (!res.ok) {
      throw new Error(`HTTP ${res.status}`);
    }
    const data = await res.json();
    renderSummary(data);
    renderResults(data.items || []);
    resultsMetaEl.textContent = "Showing latest saved report.";
    setStatus("UI connected. Click Generate Opportunities.");
  } catch {
    renderSummary({ generated_at: "-", total_items: 0, new_items: 0, high_priority: 0, medium_priority: 0 });
    renderResults([]);
    resultsMetaEl.textContent = "No report yet. Click Generate Opportunities.";
    setStatus("Connected. No report found yet.");
  }
}

async function generate() {
  generateBtn.disabled = true;
  setStatus("Running scan... this can take 10-25 seconds.");

  const payload = {
    min_level: minLevel.value,
    days: Number(days.value || 90),
    max_items: Number(maxItems.value || 300),
    use_cached: useCached.checked
  };

  try {
    const res = await fetch("/api/generate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });

    const data = await res.json();
    if (!res.ok) {
      throw new Error(data.error || `HTTP ${res.status}`);
    }

    renderSummary(data.report);
    renderResults(data.report.items || []);
    resultsMetaEl.textContent = `Scan complete. ${data.stdout_summary}`;
    setStatus("Done. Results refreshed.");
  } catch (err) {
    setStatus(`Scan failed: ${err.message}`);
  } finally {
    generateBtn.disabled = false;
  }
}

generateBtn.addEventListener("click", generate);
window.addEventListener("error", (event) => {
  setStatus(`UI error: ${event.message}`);
});
loadLatest();

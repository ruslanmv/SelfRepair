async function loadJson(path) {
  const r = await fetch(path);
  if (!r.ok) return null;
  return await r.json();
}
function badge(status) {
  return `<span class="badge ${status}">${status}</span>`;
}
async function init() {
  const summary = await loadJson("data/summary.json");
  const repos = await loadJson("data/repos.json");
  const infra = await loadJson("data/infra.json");
  const incidents = await loadJson("data/incidents.json");

  const summaryEl = document.getElementById("summary");
  if (summaryEl && summary) {
    summaryEl.innerHTML = `
      <div class="card">
        <h2>${summary.title}</h2>
        <p>Checked: ${summary.generated_at}</p>
        <p>Healthy: ${summary.healthy} / Degraded: ${summary.degraded} / Down: ${summary.down}</p>
      </div>
    `;
  }
  const reposEl = document.getElementById("repos");
  if (reposEl && repos) {
    reposEl.innerHTML = `
      <table>
        <thead><tr><th>Repository</th><th>Status</th><th>Install</th><th>Test</th><th>Start</th></tr></thead>
        <tbody>
          ${repos.items.map(x => `<tr><td>${x.name}</td><td>${badge(x.status)}</td><td>${x.install_ok}</td><td>${x.test_ok}</td><td>${x.start_ok}</td></tr>`).join("")}
        </tbody>
      </table>
    `;
  }
  const infraEl = document.getElementById("infra");
  if (infraEl && infra) {
    infraEl.innerHTML = infra.items.map(x => `<div class="card"><h3>${x.name}</h3><p>${badge(x.status)}</p><p>${x.details || ""}</p></div>`).join("");
  }
  const histEl = document.getElementById("history");
  if (histEl && incidents) {
    histEl.innerHTML = incidents.items.map(x => `<div class="card"><h3>${x.title}</h3><p>${badge(x.status)}</p><p>${x.timestamp}</p><p>${x.details}</p></div>`).join("");
  }
}
init();

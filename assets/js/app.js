async function loadJSON(path) {
  const response = await fetch(path);
  if (!response.ok) throw new Error(`Cannot load ${path}`);
  return response.json();
}

function statusClass(status) {
  const s = status.toLowerCase();
  if (s.includes("hoàn thành")) return "done";
  if (s.includes("rủi ro") || s.includes("cần đẩy")) return "risk";
  return "doing";
}

function renderKPI(data) {
  document.getElementById("execution-score").textContent = data.executionScore;
  document.getElementById("execution-bar").style.width = `${data.executionScore}%`;
  document.getElementById("execution-note").textContent = data.note;

  const container = document.getElementById("kpi-cards");
  container.innerHTML = data.metrics.map(item => `
    <div class="metric-card">
      <div class="value">${item.value}</div>
      <div class="label">${item.label}</div>
    </div>
  `).join("");
}

function renderProjects(data) {
  const tbody = document.getElementById("project-table");
  tbody.innerHTML = data.map(p => `
    <tr>
      <td><strong>${p.name}</strong></td>
      <td>${p.goal}</td>
      <td>${p.kpi}</td>
      <td>
        <div class="progress"><div class="bar" style="width:${p.progress}%"></div></div>
        <span class="muted">${p.progress}%</span>
      </td>
      <td><span class="status ${statusClass(p.status)}">${p.status}</span></td>
    </tr>
  `).join("");
}

function renderLearning(data) {
  document.getElementById("learning-list").innerHTML = data.roadmap.map(item => `
    <div class="stack-item">
      <strong>${item.name}</strong>
      <span>${item.priority} · ${item.target}</span>
      <div class="progress"><div class="bar" style="width:${item.progress}%"></div></div>
      <span class="muted">${item.progress}%</span>
    </div>
  `).join("");

  document.getElementById("skill-list").innerHTML =
    data.skills.map(skill => `<span class="tag">${skill}</span>`).join("");
}

function renderContent(data) {
  document.getElementById("content-grid").innerHTML = data.map(item => `
    <div class="content-card">
      <h4>${item.pillar}</h4>
      <p>${item.angle}</p>
      <span class="tag">${item.output}</span>
    </div>
  `).join("");
}

function renderPortfolio(data) {
  document.getElementById("portfolio-grid").innerHTML = data.map(item => `
    <div class="content-card">
      <h4>${item.name}</h4>
      <p>${item.description}</p>
      <span class="tag">${item.status}</span>
    </div>
  `).join("");
}

function renderCareer(data) {
  document.getElementById("career-roadmap").innerHTML = data.map(item => `
    <div class="timeline-item">
      <strong>${item.period}</strong>
      <span>${item.focus}</span>
    </div>
  `).join("");
}

async function initPBOS() {
  const [kpi, projects, learning, content, portfolio, career] = await Promise.all([
    loadJSON("data/kpi.json"),
    loadJSON("data/projects.json"),
    loadJSON("data/learning.json"),
    loadJSON("data/content.json"),
    loadJSON("data/portfolio.json"),
    loadJSON("data/career.json")
  ]);

  renderKPI(kpi);
  renderProjects(projects);
  renderLearning(learning);
  renderContent(content);
  renderPortfolio(portfolio);
  renderCareer(career);
}

initPBOS().catch(error => {
  console.error(error);
  document.body.insertAdjacentHTML("afterbegin", `<div style="padding:12px;background:#7f1d1d;color:white">PBOS data loading error. Open via GitHub Pages or a local server, not by double-clicking index.html.</div>`);
});

async function loadJSON(path) {
  const res = await fetch(path);
  if (!res.ok) throw new Error(path);
  return res.json();
}

function setDate() {
  const now = new Date();
  const hour = now.getHours();
  document.getElementById("greeting").textContent =
    hour < 11 ? "Good Morning, Ngoc" : hour < 17 ? "Good Afternoon, Ngoc" : "Good Evening, Ngoc";
  document.getElementById("today-date").textContent = now.toLocaleDateString("vi-VN", {
    weekday: "long", year: "numeric", month: "long", day: "numeric"
  });
}

function renderToday(data) {
  document.getElementById("today-focus").innerHTML = data.focus.map(x => `
    <div class="focus">
      <span>${x.type}</span>
      <strong>${x.title}</strong>
      <p>${x.note}</p>
    </div>
  `).join("");

  document.getElementById("current-focus").textContent = data.currentFocus.title;
  document.getElementById("current-focus-note").textContent = data.currentFocus.note;
  document.getElementById("main-risk").textContent = data.mainRisk.title;
  document.getElementById("main-risk-note").textContent = data.mainRisk.note;
  document.getElementById("next-output").textContent = data.nextOutput.title;
  document.getElementById("next-output-note").textContent = data.nextOutput.note;
}

function renderKPI(data) {
  document.getElementById("execution-score").textContent = data.executionScore;
  document.getElementById("execution-bar").style.width = data.executionScore + "%";
  document.getElementById("execution-note").textContent = data.note;

  document.getElementById("score").innerHTML = data.metrics.map(x => `
    <div class="metric">
      <div class="value">${x.value}</div>
      <div class="name">${x.label}</div>
    </div>
  `).join("");
}

function renderCareer(data) {
  document.getElementById("career-capital").innerHTML = data.capital.map(x => `
    <div class="metric">
      <div class="value">${x.value}</div>
      <div class="name">${x.label}</div>
    </div>
  `).join("");

  document.getElementById("achievement-table").innerHTML = data.achievements.map(x => `
    <tr>
      <td>${x.year}</td>
      <td><strong>${x.title}</strong><br><span class="muted">${x.note}</span></td>
      <td>${x.source}</td>
      <td>${x.evidence}</td>
    </tr>
  `).join("");
}

function renderProjects(data) {
  document.getElementById("projects-grid").innerHTML = data.map(x => `
    <div class="project">
      <strong>${x.name}</strong>
      <p>${x.goal}</p>
      <div class="bar-wrap"><div class="bar" style="width:${x.progress}%"></div></div>
      <span class="status">${x.progress}% · ${x.status}</span>
    </div>
  `).join("");
}

function renderLearning(data) {
  document.getElementById("learning-list").innerHTML = data.roadmap.map(x => `
    <div class="learn">
      <strong>${x.name}</strong>
      <p>${x.target}</p>
      <div class="bar-wrap"><div class="bar" style="width:${x.progress}%"></div></div>
      <span class="status">${x.progress}% · ${x.priority}</span>
    </div>
  `).join("");

  document.getElementById("skill-list").innerHTML = data.skills.map(x => `<span class="tag">${x}</span>`).join("");
}

function renderCards(id, data) {
  document.getElementById(id).innerHTML = data.map(x => `
    <div class="asset">
      <strong>${x.name || x.pillar}</strong>
      <p>${x.description || x.angle}</p>
      <span class="tag">${x.status || x.output}</span>
    </div>
  `).join("");
}

async function init() {
  setDate();
  const [today, kpi, career, projects, learning, content, portfolio] = await Promise.all([
    loadJSON("data/today.json"),
    loadJSON("data/kpi.json"),
    loadJSON("data/achievements.json"),
    loadJSON("data/projects.json"),
    loadJSON("data/learning.json"),
    loadJSON("data/content.json"),
    loadJSON("data/portfolio.json")
  ]);

  renderToday(today);
  renderKPI(kpi);
  renderCareer(career);
  renderProjects(projects);
  renderLearning(learning);
  renderCards("content-grid", content);
  renderCards("portfolio-grid", portfolio);
}

init().catch(err => {
  console.error(err);
  document.body.insertAdjacentHTML("afterbegin", "<div style='padding:12px;background:#7f1d1d;color:white'>PBOS data loading error. Check data/*.json paths.</div>");
});

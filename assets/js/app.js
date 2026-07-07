async function loadData() {
  const res = await fetch("data/pbos-data.json", { cache: "no-store" });
  if (!res.ok) throw new Error("Cannot load data/pbos-data.json");
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

function renderMeta(data) {
  document.getElementById("app-title").textContent = data.meta.title;
  document.getElementById("app-subtitle").textContent = data.meta.subtitle;
  document.getElementById("north-star").textContent = data.meta.northStar;
}

function renderToday(data) {
  document.getElementById("today-focus").innerHTML = data.today.focus.map(x => `
    <div class="focus">
      <span>${x.type}</span>
      <strong>${x.title}</strong>
      <p>${x.note}</p>
    </div>
  `).join("");

  document.getElementById("current-focus").textContent = data.today.currentFocus.title;
  document.getElementById("current-focus-note").textContent = data.today.currentFocus.note;
  document.getElementById("main-risk").textContent = data.today.mainRisk.title;
  document.getElementById("main-risk-note").textContent = data.today.mainRisk.note;
  document.getElementById("next-output").textContent = data.today.nextOutput.title;
  document.getElementById("next-output-note").textContent = data.today.nextOutput.note;
}

function renderKPI(data) {
  document.getElementById("execution-score").textContent = data.kpi.executionScore;
  document.getElementById("execution-bar").style.width = data.kpi.executionScore + "%";
  document.getElementById("execution-note").textContent = data.kpi.note;

  document.getElementById("score").innerHTML = data.kpi.metrics.map(x => `
    <div class="metric">
      <div class="value">${x.value}</div>
      <div class="name">${x.label}</div>
    </div>
  `).join("");
}

function renderCareer(data) {
  document.getElementById("career-capital").innerHTML = data.career.capital.map(x => `
    <div class="metric">
      <div class="value">${x.value}</div>
      <div class="name">${x.label}</div>
    </div>
  `).join("");

  document.getElementById("achievement-table").innerHTML = data.career.achievements.map(x => `
    <tr>
      <td>${x.year}</td>
      <td><strong>${x.title}</strong><br><span class="muted">${x.note}</span></td>
      <td>${x.source}</td>
      <td>${x.evidence}</td>
    </tr>
  `).join("");
}

function renderProjects(data) {
  document.getElementById("projects-grid").innerHTML = data.projects.map(x => `
    <div class="project">
      <strong>${x.name}</strong>
      <p>${x.goal}</p>
      <div class="bar-wrap"><div class="bar" style="width:${x.progress}%"></div></div>
      <span class="status">${x.progress}% · ${x.status}</span>
    </div>
  `).join("");
}

function renderLearning(data) {
  document.getElementById("learning-list").innerHTML = data.learning.roadmap.map(x => `
    <div class="learn">
      <strong>${x.name}</strong>
      <p>${x.target}</p>
      <div class="bar-wrap"><div class="bar" style="width:${x.progress}%"></div></div>
      <span class="status">${x.progress}% · ${x.priority}</span>
    </div>
  `).join("");

  document.getElementById("skill-list").innerHTML = data.learning.skills.map(x => `<span class="tag">${x}</span>`).join("");
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
  const data = await loadData();
  renderMeta(data);
  renderToday(data);
  renderKPI(data);
  renderCareer(data);
  renderProjects(data);
  renderLearning(data);
  renderCards("content-grid", data.content);
  renderCards("portfolio-grid", data.portfolio);
}

init().catch(err => {
  console.error(err);
  document.body.insertAdjacentHTML("afterbegin", "<div style='padding:12px;background:#7f1d1d;color:white'>PBOS data loading error. Check data/pbos-data.json.</div>");
});

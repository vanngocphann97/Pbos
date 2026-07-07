async function loadData(){
  const res=await fetch("data/pbos-data.json",{cache:"no-store"});
  if(!res.ok) throw new Error("Cannot load data");
  return res.json();
}
function nowText(){
  const n=new Date(),h=n.getHours();
  document.getElementById("greeting").textContent=h<11?"Good Morning, Ngoc":h<17?"Good Afternoon, Ngoc":"Good Evening, Ngoc";
  document.getElementById("dateNow").textContent=n.toLocaleDateString("vi-VN",{weekday:"long",year:"numeric",month:"long",day:"numeric"});
}
function card(title,body,badge=""){
  return `<div class="card"><strong>${title}</strong><p>${body||""}</p>${badge?`<span class="badge">${badge}</span>`:""}</div>`;
}
function progress(v){return `<div class="progress"><div class="bar" style="width:${v}%"></div></div>`}
function render(d){
  document.getElementById("versionText").textContent=`v${d.meta.version} · ${d.meta.mode}`;
  document.getElementById("northStar").textContent=d.meta.northStar;
  document.getElementById("principle").textContent=d.meta.principle;
  document.getElementById("operatingScore").textContent=d.daily.operatingScore;
  document.getElementById("weekOutput").textContent=`${d.daily.weekOutput.done}/${d.daily.weekOutput.target}`;
  document.getElementById("todayOutput").textContent=d.daily.todayOutput;
  document.getElementById("deadline").textContent=`Deadline: ${d.daily.deadline}`;
  document.getElementById("focusGrid").innerHTML=d.daily.focus.map(x=>card(x.title,x.why,x.status)).join("");
  document.getElementById("nextList").innerHTML=d.daily.nextActions.map(x=>`<div>${x}</div>`).join("");
  document.getElementById("projectGrid").innerHTML=d.projects.map(p=>`<div class="card"><strong>${p.name}</strong><p>${p.next}</p>${progress(p.progress)}<span class="badge">${p.progress}% · ${p.risk} · ${p.status}</span></div>`).join("");
  document.getElementById("careerRole").textContent=`${d.career.currentRole} → ${d.career.targetRole}`;
  document.getElementById("careerGrid").innerHTML=d.career.capital.map(x=>`<div class="metric"><strong>${x.value}</strong><span>${x.name}</span></div>`).join("");
  document.getElementById("achievementRows").innerHTML=d.career.achievements.map(a=>`<tr><td>${a.year}</td><td>${a.title}</td><td>${a.source}</td></tr>`).join("");
  document.getElementById("knowledgeGrid").innerHTML=d.knowledge.map(k=>`<div class="card"><strong>${k.name}</strong><p>${k.type}</p>${progress(k.progress)}<span class="badge">${k.progress}% · ${k.priority}</span></div>`).join("");
  document.getElementById("portfolioGrid").innerHTML=d.portfolio.map(p=>card(p.name,p.type,p.status)).join("");
  document.getElementById("questionList").innerHTML=d.review.weeklyQuestions.map(x=>`<div>${x}</div>`).join("");
  document.getElementById("ruleList").innerHTML=d.review.rules.map(x=>`<div>${x}</div>`).join("");
}
nowText();
loadData().then(render).catch(e=>{
  console.error(e);
  document.body.insertAdjacentHTML("afterbegin","<div style='background:#b91c1c;color:white;padding:12px'>Cannot load data/pbos-data.json</div>");
});
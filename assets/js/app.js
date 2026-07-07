async function loadData(){
  const res=await fetch("data/pbos-data.json",{cache:"no-store"});
  if(!res.ok) throw new Error("Cannot load data");
  return res.json();
}
function dateNow(){
  const n=new Date(),h=n.getHours();
  document.getElementById("greeting").textContent=h<11?"Good Morning, Ngoc":h<17?"Good Afternoon, Ngoc":"Good Evening, Ngoc";
  document.getElementById("dateNow").textContent=n.toLocaleDateString("vi-VN",{weekday:"long",year:"numeric",month:"long",day:"numeric"});
}
function card(title,body,badge=""){
  return `<div class="card"><strong>${title}</strong><p>${body||""}</p>${badge?`<span class="badge">${badge}</span>`:""}</div>`;
}
function progress(x){
  return `<div class="progress"><div class="bar" style="width:${x}%"></div></div>`;
}
function render(d){
  document.getElementById("versionText").textContent=`v${d.meta.version} · ${d.meta.mode}`;
  document.getElementById("northStar").textContent=d.meta.northStar;
  document.getElementById("principle").textContent=d.meta.principle;
  document.getElementById("todayFocus").innerHTML=d.today.focus.map(x=>card(x.title,x.type,x.status)).join("");
  document.getElementById("nextActions").innerHTML=d.today.nextActions.map(x=>`<div class="action">${x}</div>`).join("");
  document.getElementById("scoreStrip").innerHTML=d.scores.map(s=>`<div class="score"><strong>${s.value}</strong><span>${s.name}</span><em>${s.note||""}</em></div>`).join("");
  document.getElementById("projectGrid").innerHTML=d.projects.map(p=>`<div class="card"><strong>${p.name}</strong><p>${p.next}</p>${progress(p.progress)}<span class="badge">${p.progress}% · ${p.priority} · ${p.status}</span></div>`).join("");
  document.getElementById("careerRole").textContent=`${d.career.currentRole} → ${d.career.targetRole}`;
  document.getElementById("careerCapital").innerHTML=d.career.capital.map(x=>`<div class="score"><strong>${x.value}</strong><span>${x.name}</span></div>`).join("");
  document.getElementById("achievementRows").innerHTML=d.career.achievements.map(a=>`<tr><td>${a.year}</td><td>${a.title}</td><td>${a.source}</td></tr>`).join("");
  document.getElementById("learningGrid").innerHTML=d.learning.map(l=>`<div class="card"><strong>${l.name}</strong><p>${l.why||""}</p>${progress(l.progress)}<span class="badge">${l.progress}% · ${l.priority}</span></div>`).join("");
  document.getElementById("portfolioGrid").innerHTML=d.portfolio.map(p=>card(p.name,p.type,p.status)).join("");
  document.getElementById("rules").innerHTML=d.operatingRules.map(x=>`<div class="action">${x}</div>`).join("");
}
dateNow();
loadData().then(render).catch(e=>{
  console.error(e);
  document.body.insertAdjacentHTML("afterbegin","<div style='background:#b91c1c;color:white;padding:12px'>Cannot load data/pbos-data.json</div>");
});
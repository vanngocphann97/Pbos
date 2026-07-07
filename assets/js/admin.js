const editor = document.getElementById("json-editor");
const statusEl = document.getElementById("status");

function setStatus(text) {
  statusEl.textContent = text;
}

async function loadCurrentData() {
  try {
    const res = await fetch("data/pbos-data.json", { cache: "no-store" });
    if (!res.ok) throw new Error("Cannot load data/pbos-data.json");
    const data = await res.json();
    editor.value = JSON.stringify(data, null, 2);
    setStatus("Loaded data/pbos-data.json.");
  } catch (error) {
    setStatus("Load failed. You can still paste JSON manually.");
    console.error(error);
  }
}

function parseEditor() {
  return JSON.parse(editor.value);
}

function formatJSON() {
  try {
    const data = parseEditor();
    editor.value = JSON.stringify(data, null, 2);
    setStatus("JSON formatted.");
  } catch (error) {
    setStatus("Invalid JSON. Check commas, brackets and quotes.");
  }
}

function validateJSON() {
  try {
    parseEditor();
    setStatus("Valid JSON.");
  } catch (error) {
    setStatus("Invalid JSON: " + error.message);
  }
}

function downloadJSON() {
  try {
    const data = parseEditor();
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "pbos-data.json";
    a.click();
    URL.revokeObjectURL(url);
    setStatus("Exported pbos-data.json.");
  } catch (error) {
    setStatus("Export failed. JSON is invalid.");
  }
}

document.getElementById("load-current").addEventListener("click", loadCurrentData);
document.getElementById("format-json").addEventListener("click", formatJSON);
document.getElementById("validate-json").addEventListener("click", validateJSON);
document.getElementById("download-json").addEventListener("click", downloadJSON);

loadCurrentData();

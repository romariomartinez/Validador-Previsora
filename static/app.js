const form = document.getElementById("radicacionForm");
const statusBadge = document.getElementById("statusBadge");
const requirementsEl = document.getElementById("requirements");
const resultSummary = document.getElementById("resultSummary");
const issuesEl = document.getElementById("issues");
const downloadsEl = document.getElementById("downloads");
const filesEl = document.getElementById("files");
const clearBtn = document.getElementById("clearBtn");
const modeTabs = Array.from(document.querySelectorAll(".mode-tab"));
const autoUpload = document.getElementById("autoUpload");
const manualUpload = document.getElementById("manualUpload");

const boxes = ["CUV", "RIPS", "FURIPS", "FURTRAN", "SOPORTES"];
let currentMode = "auto";

function setStatus(text, kind = "idle") {
  statusBadge.textContent = text;
  statusBadge.className = `status-badge ${kind}`;
}

function currentRequirementParams() {
  const data = new FormData(form);
  return new URLSearchParams({
    ramo: data.get("ramo"),
    amparo: data.get("amparo"),
    tipo_cuenta: data.get("tipo_cuenta"),
    pdf_furips_furtran: data.get("pdf_furips_furtran") ? "true" : "false",
  });
}

async function loadRequirements() {
  const response = await fetch(`/api/requirements?${currentRequirementParams()}`);
  const payload = await response.json();
  if (!response.ok) {
    requirementsEl.innerHTML = `<div class="issue error">${payload.error || "No se pudieron cargar reglas."}</div>`;
    return;
  }

  requirementsEl.innerHTML = payload.requirements
    .map((item) => {
      const kind = item.required ? "required" : "optional";
      const requiredText = item.required ? "Obligatorio" : "Opcional";
      return `
        <div class="req-item ${kind}">
          <strong>${item.label}</strong>
          <small>${item.box_label} · ${requiredText}</small>
        </div>
      `;
    })
    .join("");
}

function updateFileCounts() {
  const autoInput = document.getElementById("files_AUTO");
  const folderInput = document.getElementById("folder_AUTO");
  document.getElementById("count_AUTO").textContent =
    autoInput.files.length === 0 ? "Sin archivos" : `${autoInput.files.length} archivo${autoInput.files.length === 1 ? "" : "s"} seleccionado${autoInput.files.length === 1 ? "" : "s"}`;
  document.getElementById("count_FOLDER_AUTO").textContent =
    folderInput.files.length === 0 ? "Sin carpeta" : `${folderInput.files.length} archivo${folderInput.files.length === 1 ? "" : "s"} en carpeta`;

  for (const box of boxes) {
    const input = document.getElementById(`files_${box}`);
    const count = document.getElementById(`count_${box}`);
    const total = input.files.length;
    count.textContent = total === 0 ? "Sin archivos" : `${total} archivo${total === 1 ? "" : "s"} seleccionado${total === 1 ? "" : "s"}`;
  }
}

function setMode(mode) {
  currentMode = mode;
  autoUpload.classList.toggle("hidden", mode !== "auto");
  manualUpload.classList.toggle("hidden", mode !== "manual");
  for (const tab of modeTabs) {
    tab.classList.toggle("active", tab.dataset.mode === mode);
  }
}

function appendFiles(data, box) {
  const input = document.getElementById(`files_${box}`);
  for (const file of input.files) {
    const name = file.webkitRelativePath || file.name;
    data.append(`files_${box}`, file, name);
  }
}

function appendAutoFiles(data) {
  for (const id of ["files_AUTO", "folder_AUTO"]) {
    const input = document.getElementById(id);
    for (const file of input.files) {
      const name = file.webkitRelativePath || file.name;
      data.append("files_AUTO", file, name);
    }
  }
}

function renderSummary(payload) {
  const statusLabel = payload.status === "ok" ? "Aprobado" : payload.status === "warning" ? "Con advertencias" : "Con errores";
  resultSummary.className = "summary";
  resultSummary.innerHTML = `
    <div class="metric"><strong>${statusLabel}</strong><span>Estado</span></div>
    <div class="metric"><strong>${payload.summary.files}</strong><span>Archivos</span></div>
    <div class="metric"><strong>${payload.summary.errors}</strong><span>Errores</span></div>
    <div class="metric"><strong>${payload.summary.ready_zips}</strong><span>ZIPs</span></div>
  `;
}

function renderIssues(issues) {
  if (!issues.length) {
    issuesEl.innerHTML = `<div class="issue info"><strong>OK</strong> Sin errores ni advertencias.</div>`;
    return;
  }
  issuesEl.innerHTML = `
    <div class="issue-list">
      <div class="section-title">Hallazgos</div>
      ${issues
        .map((item) => {
          const box = item.box ? ` · ${item.box}` : "";
          const file = item.file ? `<br><small>${item.file}</small>` : "";
          return `<div class="issue ${item.level}"><strong>${item.level}${box}</strong>${item.message}${file}</div>`;
        })
        .join("")}
    </div>
  `;
}

function renderDownloads(payload) {
  const reportLinks = [
    { label: "Reporte JSON", filename: "report.json", size_mb: "" },
    { label: "Reporte de validacion", filename: "reporte_validacion.md", size_mb: "" },
  ];
  const links = [...payload.ready_zips, ...reportLinks];
  const blocked = payload.summary.errors > 0;
  downloadsEl.innerHTML = `
    <div class="download-list">
      <div class="section-title">Descargas</div>
      ${blocked ? `<div class="issue blocked"><strong>Bloqueado</strong>No se generan ZIPs hasta corregir los errores.</div>` : ""}
      ${links
        .map((item) => {
          const filename = item.filename || item.filename === "" ? item.filename : "";
          const href = `/download/${payload.run_id}/${filename}`;
          const size = item.size_mb ? `${item.size_mb} MB` : "Archivo";
          const label = item.label || item.filename;
          return `<a class="download-link" href="${href}"><span>${label}</span><small>${size}</small></a>`;
        })
        .join("")}
    </div>
  `;
}

function renderFiles(payload) {
  const files = payload.files || [];
  const classification = payload.classification || [];
  if (!files.length && !classification.length) {
    filesEl.innerHTML = "";
    return;
  }
  filesEl.innerHTML = `
    ${
      classification.length
        ? `<div class="file-list">
            <div class="section-title">Clasificacion</div>
            <table>
              <thead>
                <tr><th>Archivo</th><th>Caja</th><th>Criterio</th></tr>
              </thead>
              <tbody>
                ${classification
                  .map((item) => `<tr><td>${item.file}</td><td>${item.box_label || "Sin clasificar"}</td><td>${item.reason}</td></tr>`)
                  .join("")}
              </tbody>
            </table>
          </div>`
        : ""
    }
    <div class="file-list">
      <div class="section-title">Inventario</div>
      <table>
        <thead>
          <tr><th>Caja</th><th>Archivo</th><th>MB</th><th>ZIP</th></tr>
        </thead>
        <tbody>
          ${files
            .map((item) => `<tr><td>${item.box_label}</td><td>${item.name}</td><td>${item.size_mb}</td><td>${item.from_zip ? "Si" : "No"}</td></tr>`)
            .join("")}
        </tbody>
      </table>
    </div>
  `;
}

async function submitForm(event) {
  event.preventDefault();
  setStatus("Procesando", "idle");
  const button = form.querySelector("button.primary");
  button.disabled = true;

  const data = new FormData(form);
  data.set("pdf_furips_furtran", data.get("pdf_furips_furtran") ? "true" : "false");
  if (currentMode === "auto") {
    appendAutoFiles(data);
  } else {
    for (const box of boxes) {
      appendFiles(data, box);
    }
  }

  try {
    const endpoint = currentMode === "auto" ? "/api/process-auto" : "/api/process";
    const response = await fetch(endpoint, {
      method: "POST",
      body: data,
    });
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload.error || "No se pudo procesar el lote.");
    }
    setStatus(payload.status === "ok" ? "Aprobado" : payload.status === "warning" ? "Advertencias" : "Errores", payload.status);
    renderSummary(payload);
    renderIssues(payload.issues);
    renderDownloads(payload);
    renderFiles(payload);
  } catch (error) {
    setStatus("Error", "error");
    resultSummary.className = "empty-state";
    resultSummary.textContent = error.message;
    issuesEl.innerHTML = "";
    downloadsEl.innerHTML = "";
    filesEl.innerHTML = "";
  } finally {
    button.disabled = false;
  }
}

function clearForm() {
  form.reset();
  setMode("auto");
  resultSummary.className = "empty-state";
  resultSummary.textContent = "Aun no hay validacion.";
  issuesEl.innerHTML = "";
  downloadsEl.innerHTML = "";
  filesEl.innerHTML = "";
  setStatus("Listo", "idle");
  updateFileCounts();
  loadRequirements();
}

form.addEventListener("submit", submitForm);
clearBtn.addEventListener("click", clearForm);
for (const tab of modeTabs) {
  tab.addEventListener("click", () => {
    setMode(tab.dataset.mode);
  });
}
form.addEventListener("change", (event) => {
  if (event.target.type === "file") {
    updateFileCounts();
  }
  if (["ramo", "amparo", "tipo_cuenta", "pdf_furips_furtran"].includes(event.target.name)) {
    loadRequirements();
  }
});

loadRequirements();
updateFileCounts();
setMode("auto");

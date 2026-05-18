/* ── Drop zone drag & drop ──────────────────────────────────── */
const dropZone = document.getElementById("dropZone");
const fileInput = document.getElementById("fileInput");
const fileInfo  = document.getElementById("fileInfo");
const outputDirInput = document.getElementById("outputDirInput");
const submitBtn = document.getElementById("submitBtn");
const previewBtn = document.getElementById("previewBtn");
const statusMsg = document.getElementById("statusMsg");
const form      = document.getElementById("uploadForm");
const previewCard = document.getElementById("previewCard");
const previewMeta = document.getElementById("previewMeta");
const previewNav = document.getElementById("previewNav");
const previewFrame = document.getElementById("previewFrame");
const openDirModalBtn = document.getElementById("openDirModalBtn");
const directoryModal = document.getElementById("directoryModal");
const closeDirModalBtn = document.getElementById("closeDirModalBtn");
const dirHomeBtn = document.getElementById("dirHomeBtn");
const dirProjectBtn = document.getElementById("dirProjectBtn");
const dirUpBtn = document.getElementById("dirUpBtn");
const cancelDirSelectionBtn = document.getElementById("cancelDirSelectionBtn");
const selectCurrentDirBtn = document.getElementById("selectCurrentDirBtn");
const dirCurrentPath = document.getElementById("dirCurrentPath");
const dirList = document.getElementById("dirList");

const ALLOWED = [".docx", ".pdf"];
const MAX_MB  = 50;
let previewState = null;
let selectedDirectoryHandle = null;
let dirBrowserState = {
  currentPath: "",
  parentPath: "",
  homePath: "",
  projectPath: "",
};

function selectedFiles() {
  return Array.from(fileInput.files || []);
}

function validateFile(file) {
  if (!file) return null;
  const ext = file.name.slice(file.name.lastIndexOf(".")).toLowerCase();
  if (!ALLOWED.includes(ext)) {
    return `Tipo de archivo no permitido: ${ext}. Solo DOCX o PDF.`;
  }
  if (file.size > MAX_MB * 1024 * 1024) {
    return `El archivo supera los ${MAX_MB} MB.`;
  }
  return null;
}

function validateFiles(files) {
  if (!files.length) {
    return "Selecciona al menos un archivo DOCX o PDF.";
  }
  for (const file of files) {
    const err = validateFile(file);
    if (err) {
      return `${file.name}: ${err}`;
    }
  }
  return null;
}

function updateActionButtons(isBusy = false) {
  if (isBusy) {
    submitBtn.disabled = true;
    previewBtn.disabled = true;
    return;
  }

  const files = selectedFiles();
  const hasFiles = files.length > 0;
  const hasOutputDir = Boolean(outputDirInput.value.trim()) || Boolean(selectedDirectoryHandle);
  const requiresOutputDir = files.length > 1;

  previewBtn.disabled = files.length !== 1;
  submitBtn.disabled = !(hasFiles && (!requiresOutputDir || hasOutputDir));
}

function showFileInfo(files) {
  const totalBytes = files.reduce((sum, file) => sum + file.size, 0);
  const sizeMB = (totalBytes / (1024 * 1024)).toFixed(2);
  const lines = files.slice(0, 5).map(file => `• ${file.name}`);
  if (files.length > 5) {
    lines.push(`• ... y ${files.length - 5} más`);
  }

  fileInfo.textContent = `${files.length} archivo(s) seleccionado(s) — ${sizeMB} MB\n${lines.join("\n")}`;
  fileInfo.style.whiteSpace = "pre-line";
  fileInfo.classList.remove("hidden");
  updateActionButtons();
}

function clearFileInfo() {
  fileInfo.textContent = "";
  fileInfo.classList.add("hidden");
  updateActionButtons();
}

function clearPreview() {
  previewState = null;
  previewNav.innerHTML = "";
  previewMeta.textContent = "";
  previewFrame.srcdoc = "";
  previewCard.classList.add("hidden");
}

function showStatus(msg, type) {
  statusMsg.textContent = msg;
  statusMsg.className = `status-msg ${type}`;
  statusMsg.classList.remove("hidden");
}

function clearStatus() {
  statusMsg.className = "status-msg hidden";
  statusMsg.textContent = "";
}

function setBusy(isBusy) {
  updateActionButtons(isBusy);
}

function openDirectoryModal() {
  directoryModal.classList.remove("hidden");
}

function closeDirectoryModal() {
  directoryModal.classList.add("hidden");
}

function renderDirectoryList(directories) {
  dirList.innerHTML = "";
  if (!directories.length) {
    const emptyItem = document.createElement("li");
    emptyItem.textContent = "(No hay subcarpetas en esta ubicación)";
    emptyItem.className = "dir-empty";
    dirList.appendChild(emptyItem);
    return;
  }

  directories.forEach(dir => {
    const li = document.createElement("li");
    const button = document.createElement("button");
    button.type = "button";
    button.className = "dir-item";
    button.textContent = dir.name;
    button.title = dir.path;
    button.addEventListener("click", () => {
      loadDirectories(dir.path);
    });
    li.appendChild(button);
    dirList.appendChild(li);
  });
}

async function loadDirectories(path = "") {
  const query = path ? `?path=${encodeURIComponent(path)}` : "";

  try {
    const response = await fetch(`/directories${query}`);
    const payload = await response.json().catch(() => ({}));

    if (!response.ok) {
      showStatus(`Error al listar carpetas: ${payload.detail || response.statusText}`, "error");
      return;
    }

    dirBrowserState.currentPath = payload.current_path || "";
    dirBrowserState.parentPath = payload.parent_path || "";

    if (Array.isArray(payload.shortcuts)) {
      const home = payload.shortcuts.find(s => s.name === "Inicio");
      const project = payload.shortcuts.find(s => s.name === "Proyecto");
      dirBrowserState.homePath = home ? home.path : "";
      dirBrowserState.projectPath = project ? project.path : "";
    }

    dirCurrentPath.textContent = dirBrowserState.currentPath || "";
    dirUpBtn.disabled = !dirBrowserState.parentPath;
    dirHomeBtn.disabled = !dirBrowserState.homePath;
    dirProjectBtn.disabled = !dirBrowserState.projectPath;
    renderDirectoryList(Array.isArray(payload.directories) ? payload.directories : []);
  } catch (err) {
    showStatus(`Error de red al listar carpetas: ${err.message}`, "error");
  }
}

function filenameFromResponse(response) {
  const disposition = response.headers.get("Content-Disposition") || "";
  const match = disposition.match(/filename="([^"]+)"/);
  return match ? match[1] : "paquete_exe.zip";
}

async function saveZipToLocalDirectory(file, directoryHandle) {
  const data = new FormData();
  data.append("files", file);

  const response = await fetch("/convert", {
    method: "POST",
    body: data,
  });

  if (!response.ok) {
    const errPayload = await response.json().catch(() => ({ detail: "Error desconocido" }));
    const detail = errPayload.detail;
    let msg = response.statusText;
    if (typeof detail === "string") {
      msg = detail;
    } else if (detail && typeof detail === "object" && detail.message) {
      msg = detail.message;
    }
    throw new Error(`${file.name}: ${msg}`);
  }

  const contentType = response.headers.get("Content-Type") || "";
  if (!contentType.includes("application/zip")) {
    throw new Error(`${file.name}: Respuesta inesperada del servidor.`);
  }

  const filename = filenameFromResponse(response);
  const blob = await response.blob();
  const fileHandle = await directoryHandle.getFileHandle(filename, { create: true });
  const writable = await fileHandle.createWritable();
  await writable.write(blob);
  await writable.close();

  return filename;
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function renderPreviewPage(index) {
  if (!previewState || !previewState.pages[index]) return;

  const page = previewState.pages[index];

  const navItems = previewState.pages.map((p, idx) => {
    const isActive = idx === index ? " class=\"active\"" : "";
    return `<li${isActive}><a href=\"#\">${escapeHtml(p.title)}</a></li>`;
  }).join("");

  const html = `<!DOCTYPE html>
<html lang=\"es\" class=\"js\">
<head>
  <meta charset=\"utf-8\">
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">
  <title>${escapeHtml(page.title)}</title>
  <link rel=\"stylesheet\" href=\"/exe_preview/libs/bootstrap/bootstrap.min.css\">
  <link rel=\"stylesheet\" href=\"/exe_preview/content/css/base.css\">
  <link rel=\"stylesheet\" href=\"/exe_preview/theme/style.css\">
</head>
<body class=\"exe-export exe-web-site js\">
  <div class=\"exe-content exe-export pre-js siteNav-hidden\">
    <a href=\"#${escapeHtml(page.id)}\" id=\"skipNav\">Skip to content</a>
    <nav id=\"siteNav\"><ul>${navItems}</ul></nav>
    <main id=\"${escapeHtml(page.id)}\" class=\"page\">
      <header class=\"main-header\">
        <div class=\"package-header\"><p class=\"package-title\">${escapeHtml(previewState.title)}</p></div>
        <div class=\"page-header\"><h1 class=\"page-title\">${escapeHtml(page.title)}</h1></div>
      </header>
      <div id=\"page-content-${escapeHtml(page.id)}\" class=\"page-content\">${page.content}</div>
    </main>
  </div>
</body>
</html>`;

  previewFrame.srcdoc = html;

  Array.from(previewNav.querySelectorAll("button")).forEach((button, idx) => {
    button.classList.toggle("active", idx === index);
  });
}

function renderPreview(result) {
  previewState = {
    title: result.title,
    pages: result.pages,
  };

  previewMeta.textContent = `Proyecto: ${result.title} · Páginas detectadas: ${result.page_count}`;

  previewNav.innerHTML = "";
  result.pages.forEach((page, idx) => {
    const item = document.createElement("li");
    const btn = document.createElement("button");
    btn.type = "button";
    btn.textContent = page.title || `Página ${idx + 1}`;
    btn.addEventListener("click", () => renderPreviewPage(idx));
    item.appendChild(btn);
    previewNav.appendChild(item);
  });

  previewCard.classList.remove("hidden");
  renderPreviewPage(0);
}

/* ── File input change ─────────────────────────────────────── */
fileInput.addEventListener("change", () => {
  const files = selectedFiles();
  clearStatus();
  clearPreview();
  const err = validateFiles(files);
  if (err) {
    showStatus(err, "error");
    clearFileInfo();
    return;
  }
  showFileInfo(files);
});

outputDirInput.addEventListener("input", () => {
  selectedDirectoryHandle = null;
  updateActionButtons();
});

openDirModalBtn.addEventListener("click", async () => {
  if (window.showDirectoryPicker) {
    try {
      const handle = await window.showDirectoryPicker({ mode: "readwrite" });
      selectedDirectoryHandle = handle;
      outputDirInput.value = `[Carpeta local] ${handle.name}`;
      updateActionButtons();
      showStatus("Carpeta local seleccionada con el selector del sistema.", "success");
      return;
    } catch (err) {
      if (err && err.name === "AbortError") {
        return;
      }
      showStatus(`No se pudo abrir el selector nativo: ${err.message}`, "error");
    }
  }

  openDirectoryModal();
  await loadDirectories(outputDirInput.value.trim());
});

closeDirModalBtn.addEventListener("click", closeDirectoryModal);
cancelDirSelectionBtn.addEventListener("click", closeDirectoryModal);

directoryModal.addEventListener("click", event => {
  if (event.target === directoryModal) {
    closeDirectoryModal();
  }
});

dirUpBtn.addEventListener("click", async () => {
  if (!dirBrowserState.parentPath) return;
  await loadDirectories(dirBrowserState.parentPath);
});

dirHomeBtn.addEventListener("click", async () => {
  if (!dirBrowserState.homePath) return;
  await loadDirectories(dirBrowserState.homePath);
});

dirProjectBtn.addEventListener("click", async () => {
  if (!dirBrowserState.projectPath) return;
  await loadDirectories(dirBrowserState.projectPath);
});

selectCurrentDirBtn.addEventListener("click", () => {
  if (!dirBrowserState.currentPath) return;
  selectedDirectoryHandle = null;
  outputDirInput.value = dirBrowserState.currentPath;
  updateActionButtons();
  closeDirectoryModal();
});

/* ── Drag & drop ───────────────────────────────────────────── */
["dragenter", "dragover"].forEach(ev =>
  dropZone.addEventListener(ev, e => {
    e.preventDefault();
    dropZone.classList.add("drag-over");
  })
);
["dragleave", "drop"].forEach(ev =>
  dropZone.addEventListener(ev, e => {
    e.preventDefault();
    dropZone.classList.remove("drag-over");
  })
);
dropZone.addEventListener("drop", e => {
  const files = Array.from(e.dataTransfer.files || []);
  if (!files.length) return;
  clearStatus();
  clearPreview();
  const err = validateFiles(files);
  if (err) {
    showStatus(err, "error");
    clearFileInfo();
    return;
  }
  // Assign to file input via DataTransfer
  const dt = new DataTransfer();
  files.forEach(file => dt.items.add(file));
  fileInput.files = dt.files;
  showFileInfo(files);
});

/* ── Preview submit ────────────────────────────────────────── */
previewBtn.addEventListener("click", async () => {
  const files = selectedFiles();
  const file = files[0];
  if (files.length !== 1 || !file) {
    showStatus("La vista previa solo esta disponible cuando seleccionas un unico archivo.", "error");
    return;
  }
  if (!file) return;

  setBusy(true);
  showStatus("Generando vista previa…", "loading");

  const data = new FormData();
  data.append("file", file);

  try {
    const response = await fetch("/preview", {
      method: "POST",
      body: data,
    });

    if (!response.ok) {
      const err = await response.json().catch(() => ({ detail: "Error desconocido" }));
      showStatus(`Error: ${err.detail || response.statusText}`, "error");
      return;
    }

    const result = await response.json();
    renderPreview(result);
    showStatus("✅ Vista previa generada correctamente.", "success");
  } catch (err) {
    showStatus(`Error de red: ${err.message}`, "error");
  } finally {
    setBusy(false);
  }
});

/* ── Form submit ───────────────────────────────────────────── */
form.addEventListener("submit", async e => {
  e.preventDefault();

  const files = selectedFiles();
  const outputDir = outputDirInput.value.trim();
  const err = validateFiles(files);
  if (err) {
    showStatus(err, "error");
    return;
  }
  if (files.length > 1 && !outputDir) {
    if (!selectedDirectoryHandle) {
      showStatus("Para convertir varios archivos debes indicar un directorio de salida o seleccionar carpeta local.", "error");
      return;
    }
  }

  if (selectedDirectoryHandle) {
    setBusy(true);
    showStatus("Convirtiendo y guardando en carpeta local...", "loading");

    const saved = [];
    const failed = [];

    try {
      for (const file of files) {
        try {
          const outName = await saveZipToLocalDirectory(file, selectedDirectoryHandle);
          saved.push(outName);
        } catch (err) {
          failed.push(err.message);
        }
      }

      const parts = [`${saved.length} archivo(s) guardado(s) en la carpeta local.`];
      if (failed.length) {
        parts.push(`${failed.length} con error: ${failed.join(" | ")}`);
      }
      showStatus(`✅ ${parts.join(" ")}`, failed.length ? "loading" : "success");
    } catch (err) {
      showStatus(`Error al guardar en carpeta local: ${err.message}`, "error");
    } finally {
      updateActionButtons();
    }
    return;
  }

  setBusy(true);
  showStatus("Convirtiendo… por favor espera.", "loading");

  const data = new FormData();
  files.forEach(file => data.append("files", file));
  if (outputDir) {
    data.append("output_dir", outputDir);
  }

  try {
    const response = await fetch("/convert", {
      method: "POST",
      body: data,
    });

    if (!response.ok) {
      const errPayload = await response.json().catch(() => ({ detail: "Error desconocido" }));
      const detail = errPayload.detail;
      let msg = response.statusText;

      if (typeof detail === "string") {
        msg = detail;
      } else if (detail && typeof detail === "object") {
        const parts = [];
        if (detail.message) parts.push(detail.message);
        if (Array.isArray(detail.errors) && detail.errors.length) {
          parts.push(detail.errors.map(item => `${item.source}: ${item.error}`).join(" | "));
        }
        msg = parts.join(" · ") || msg;
      }

      showStatus(`Error: ${msg}`, "error");
      return;
    }

    const contentType = response.headers.get("Content-Type") || "";
    if (contentType.includes("application/zip")) {
      const blob = await response.blob();
      const disposition = response.headers.get("Content-Disposition") || "";
      const match = disposition.match(/filename="([^"]+)"/);
      const filename = match ? match[1] : "paquete_exe.zip";

      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);

      showStatus(`✅ Paquete generado: ${filename}`, "success");
      return;
    }

    const result = await response.json();
    const savedCount = Array.isArray(result.saved_files) ? result.saved_files.length : 0;
    const errorCount = Array.isArray(result.errors) ? result.errors.length : 0;
    const statusParts = [result.message || `${savedCount} archivo(s) convertido(s).`];
    if (errorCount > 0) {
      statusParts.push(`${errorCount} archivo(s) con error.`);
    }
    showStatus(`✅ ${statusParts.join(" ")}`, "success");
  } catch (err) {
    showStatus(`Error de red: ${err.message}`, "error");
  } finally {
    updateActionButtons();
  }
});

updateActionButtons();

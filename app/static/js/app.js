/* ── Drop zone drag & drop ──────────────────────────────────── */
const dropZone = document.getElementById("dropZone");
const fileInput = document.getElementById("fileInput");
const fileInfo  = document.getElementById("fileInfo");
const submitBtn = document.getElementById("submitBtn");
const statusMsg = document.getElementById("statusMsg");
const form      = document.getElementById("uploadForm");

const ALLOWED = [".docx", ".pdf"];
const MAX_MB  = 50;

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

function showFileInfo(file) {
  const sizeMB = (file.size / (1024 * 1024)).toFixed(2);
  fileInfo.textContent = `📄 ${file.name} — ${sizeMB} MB`;
  fileInfo.classList.remove("hidden");
  submitBtn.disabled = false;
}

function clearFileInfo() {
  fileInfo.classList.add("hidden");
  submitBtn.disabled = true;
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

/* ── File input change ─────────────────────────────────────── */
fileInput.addEventListener("change", () => {
  const file = fileInput.files[0];
  clearStatus();
  const err = validateFile(file);
  if (err) {
    showStatus(err, "error");
    clearFileInfo();
    return;
  }
  showFileInfo(file);
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
  const file = e.dataTransfer.files[0];
  if (!file) return;
  clearStatus();
  const err = validateFile(file);
  if (err) {
    showStatus(err, "error");
    clearFileInfo();
    return;
  }
  // Assign to file input via DataTransfer
  const dt = new DataTransfer();
  dt.items.add(file);
  fileInput.files = dt.files;
  showFileInfo(file);
});

/* ── Form submit ───────────────────────────────────────────── */
form.addEventListener("submit", async e => {
  e.preventDefault();

  const file = fileInput.files[0];
  if (!file) return;

  submitBtn.disabled = true;
  showStatus("Convirtiendo… por favor espera.", "loading");

  const data = new FormData();
  data.append("file", file);

  try {
    const response = await fetch("/convert", {
      method: "POST",
      body: data,
    });

    if (!response.ok) {
      const err = await response.json().catch(() => ({ detail: "Error desconocido" }));
      showStatus(`Error: ${err.detail || response.statusText}`, "error");
      submitBtn.disabled = false;
      return;
    }

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
  } catch (err) {
    showStatus(`Error de red: ${err.message}`, "error");
  } finally {
    submitBtn.disabled = false;
  }
});

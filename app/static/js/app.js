/* ── Drop zone drag & drop ──────────────────────────────────── */
const dropZone = document.getElementById("dropZone");
const fileInput = document.getElementById("fileInput");
const fileInfo  = document.getElementById("fileInfo");
const submitBtn = document.getElementById("submitBtn");
const previewBtn = document.getElementById("previewBtn");
const statusMsg = document.getElementById("statusMsg");
const form      = document.getElementById("uploadForm");
const previewCard = document.getElementById("previewCard");
const previewMeta = document.getElementById("previewMeta");
const previewNav = document.getElementById("previewNav");
const previewFrame = document.getElementById("previewFrame");

const ALLOWED = [".docx", ".pdf"];
const MAX_MB  = 50;
let previewState = null;

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
  previewBtn.disabled = false;
}

function clearFileInfo() {
  fileInfo.classList.add("hidden");
  submitBtn.disabled = true;
  previewBtn.disabled = true;
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
  submitBtn.disabled = isBusy;
  previewBtn.disabled = isBusy;
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
  const file = fileInput.files[0];
  clearStatus();
  clearPreview();
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
  clearPreview();
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

/* ── Preview submit ────────────────────────────────────────── */
previewBtn.addEventListener("click", async () => {
  const file = fileInput.files[0];
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

  const file = fileInput.files[0];
  if (!file) return;

  setBusy(true);
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
    setBusy(false);
  }
});

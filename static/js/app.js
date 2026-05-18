const state = {
  username: null,
  highlightedRecoveredFileId: null,
  filesCache: null,
  deletedFilesCache: null,
};

const fileList = document.getElementById("file-list");
const deletedFileList = document.getElementById("deleted-file-list");
const recoveryLogList = document.getElementById("recovery-log-list");
const dashboardUsername = document.getElementById("dashboard-username");
const notificationArea = document.getElementById("notification-area");
const alertsPanel = document.getElementById("alerts-panel");
const uploadForm = document.getElementById("upload-form");
const fileInput = document.getElementById("file-input");
const uploadButton = document.getElementById("upload-btn");
const uploadButtonText = document.getElementById("upload-btn-text");
const uploadSpinner = document.getElementById("upload-spinner");

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function statusBadge(status) {
  const normalized = (status || "UNKNOWN").toUpperCase();
  const badgeClass =
    normalized === "SAFE"
      ? "text-bg-success"
      : normalized === "RECOVERED"
        ? "text-bg-info"
        : normalized === "TAMPERED"
          ? "text-bg-danger"
          : "text-bg-secondary";
  return `<span class="badge ${badgeClass}">${normalized}</span>`;
}

function pushAlert(message, tone = "secondary") {
  const alertMarkup = `
    <div class="alert alert-${tone} alert-dismissible fade show mb-3" role="alert">
      ${escapeHtml(message)}
      <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
    </div>
  `;
  notificationArea.innerHTML = alertMarkup;
  alertsPanel.innerHTML = `
    <div class="alert alert-${tone} mb-0" role="alert">${escapeHtml(message)}</div>
  `;
}

function setUploadLoading(isLoading) {
  uploadButton.disabled = isLoading;
  fileInput.disabled = isLoading;
  uploadButtonText.textContent = isLoading ? "Uploading..." : "Upload";
  uploadSpinner.classList.toggle("d-none", !isLoading);
}

function setActionLoading(button, isLoading, loadingLabel) {
  if (!button) {
    return;
  }
  if (!button.dataset.originalLabel) {
    button.dataset.originalLabel = button.textContent.trim();
  }
  button.disabled = isLoading;
  button.textContent = isLoading ? loadingLabel : button.dataset.originalLabel;
}

function renderFiles(files) {
  if (!files.length) {
    fileList.innerHTML = `<tr><td colspan="5" class="text-center text-secondary py-4">No active files available.</td></tr>`;
    return;
  }

  fileList.innerHTML = files
    .map(
      (file) => `
        <tr class="${file.id === state.highlightedRecoveredFileId || file.status === "RECOVERED" ? "recovered-row" : ""}">
          <td>
            <div class="fw-semibold">${escapeHtml(file.filename)}</div>
            <div class="small text-secondary">${escapeHtml(file.sha256_hash)}</div>
          </td>
          <td>${statusBadge(file.status)}</td>
          <td>${escapeHtml(file.uploaded_by || "Unknown")}</td>
          <td>${escapeHtml(file.last_verified_at || "Never")}</td>
          <td>
            <div class="d-flex flex-wrap gap-2">
              <button class="btn btn-outline-primary btn-sm" data-action="verify" data-id="${file.id}">Verify</button>
              <button class="btn btn-outline-danger btn-sm" data-action="delete" data-id="${file.id}">Delete</button>
              <button class="btn btn-outline-secondary btn-sm" data-action="view-primary" data-id="${file.id}">View Primary</button>
              <button class="btn btn-outline-secondary btn-sm" data-action="view-backup" data-id="${file.id}">View Backup</button>
              <button class="btn btn-dark btn-sm" data-action="download" data-id="${file.id}">Download</button>
            </div>
          </td>
        </tr>
      `,
    )
    .join("");
}

function renderDeletedFiles(files) {
  if (!files.length) {
    deletedFileList.innerHTML = `<tr><td colspan="4" class="text-center text-secondary py-4">No deleted files.</td></tr>`;
    return;
  }

  deletedFileList.innerHTML = files
    .map(
      (file) => `
        <tr>
          <td>
            <div class="fw-semibold">${escapeHtml(file.filename)}</div>
            <div class="small text-secondary">${escapeHtml(file.sha256_hash)}</div>
          </td>
          <td><span class="badge text-bg-secondary">DELETED</span></td>
          <td>${escapeHtml(file.last_verified_at || file.uploaded_at || "N/A")}</td>
          <td>
            <div class="d-flex flex-wrap gap-2">
              <button class="btn btn-warning btn-sm" data-action="recover" data-id="${file.id}">Recover</button>
              <button class="btn btn-outline-secondary btn-sm" data-action="view-backup" data-id="${file.id}">View Backup</button>
            </div>
          </td>
        </tr>
      `,
    )
    .join("");
}

function renderLogs(logs) {
  if (!logs.length) {
    recoveryLogList.innerHTML = `<tr><td colspan="3" class="text-center text-secondary py-4">No recovery logs available.</td></tr>`;
    return;
  }

  recoveryLogList.innerHTML = logs
    .map(
      (log) => `
        <tr class="${state.highlightedRecoveredFileId && log.file_id === state.highlightedRecoveredFileId ? "recovered-log-row" : ""}">
          <td>${escapeHtml(log.filename)}</td>
          <td>${escapeHtml(log.action)}</td>
          <td>${escapeHtml(log.timestamp)}</td>
        </tr>
      `,
    )
    .join("");
}

async function api(url, options = {}) {
  const response = await fetch(url, {
    credentials: "same-origin",
    ...options,
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(data.error || data.message || "Request failed");
  }
  return data;
}

async function refreshSession() {
  const data = await api("/api/me");
  state.username = data.username;

  if (!data.authenticated) {
    window.location.href = "/login";
    return;
  }

  if (dashboardUsername) {
    dashboardUsername.textContent = state.username;
  }
  await loadFiles();
}

async function loadFiles() {
  if (!state.username) {
    return;
  }

  const data = await api("/api/files");
  state.filesCache = data.files || [];
  state.deletedFilesCache = data.deleted_files || [];
  if (state.highlightedRecoveredFileId) {
    const stillRecovered = (state.filesCache || []).some(
      (file) => file.id === state.highlightedRecoveredFileId && file.status === "RECOVERED",
    );
    if (!stillRecovered) {
      state.highlightedRecoveredFileId = null;
    }
  }
  renderFiles(state.filesCache || []);
  renderDeletedFiles(state.deletedFilesCache || []);
  const logs = await api("/api/recovery-logs");
  renderLogs(logs.logs || []);
}

uploadForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!fileInput.files.length) {
    pushAlert("Choose a file before uploading.", "warning");
    return;
  }

  try {
    setUploadLoading(true);
    const formData = new FormData();
    formData.append("file", fileInput.files[0]);
    const data = await api("/api/upload", {
      method: "POST",
      body: formData,
    });
    fileInput.value = "";
    pushAlert(data.message || "File uploaded successfully.", "success");
    await loadFiles();
  } catch (error) {
    pushAlert(error.message || "Upload failed.", "danger");
  } finally {
    setUploadLoading(false);
  }
});

document.getElementById("refresh-btn").addEventListener("click", async () => {
  try {
    await loadFiles();
    pushAlert("Dashboard data refreshed.", "info");
  } catch (error) {
    pushAlert(error.message, "danger");
  }
});

document.addEventListener("click", async (event) => {
  const button = event.target.closest("[data-action]");
  if (!button) {
    return;
  }

  const { action, id } = button.dataset;
  try {
    if (action === "verify") {
      setActionLoading(button, true, "Verifying...");
      const data = await api(`/api/verify/${id}`);
      state.highlightedRecoveredFileId = data.verification.status === "RECOVERED" ? id : null;
      pushAlert(`Verification completed: ${data.verification.status}`, "primary");
    }

    if (action === "delete") {
      setActionLoading(button, true, "Deleting...");
      const data = await api(`/api/delete/${id}`, { method: "POST" });
      pushAlert(data.message || "File deleted.", "warning");
    }

    if (action === "recover") {
      setActionLoading(button, true, "Recovering...");
      const data = await api(`/api/recover/${id}`, { method: "POST" });
      state.highlightedRecoveredFileId = null;
      pushAlert(data.message || "File restored.", "success");
    }

    if (action === "download") {
      setActionLoading(button, true, "Preparing...");
      const data = await api(`/api/download/${id}`);
      const link = document.createElement("a");
      link.href = data.url;
      link.download = data.filename || "";
      document.body.appendChild(link);
      link.click();
      link.remove();
      pushAlert(`Download started for ${data.filename}`, "info");
    }

    if (action === "view-primary" || action === "view-backup") {
      setActionLoading(button, true, "Opening...");
      const location = action === "view-primary" ? "primary" : "backup";
      const data = await api(`/api/view/${id}/${location}`);
      window.open(data.url, "_blank", "noopener,noreferrer");
    }

    await loadFiles();
  } catch (error) {
    pushAlert(error.message, "danger");
  } finally {
    setActionLoading(button, false);
  }
});

refreshSession();

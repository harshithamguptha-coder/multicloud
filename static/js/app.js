const state = {
  username: null,
  highlightedRecoveredFileId: null,
  filesCache: null,
  deletedFilesCache: null,
};

const fileList = document.getElementById("file-list");
const deletedFileList = document.getElementById("deleted-file-list");
const recoveryLogList = document.getElementById("recovery-log-list");
const recentActivityList = document.getElementById("recent-activity-list");
const storageFileList = document.getElementById("storage-file-list");
const dashboardUsername = document.getElementById("dashboard-username");
const notificationArea = document.getElementById("notification-area");
const alertsPanel = document.getElementById("alerts-panel");
const uploadForm = document.getElementById("upload-form");
const fileInput = document.getElementById("file-input");
const uploadButton = document.getElementById("upload-btn");
const uploadButtonText = document.getElementById("upload-btn-text");
const uploadSpinner = document.getElementById("upload-spinner");
const refreshButton = document.getElementById("refresh-btn");
const statActiveFiles = document.getElementById("stat-active-files");
const statTamperedFiles = document.getElementById("stat-tampered-files");
const statDeletedFiles = document.getElementById("stat-deleted-files");
const statRecoveryLogs = document.getElementById("stat-recovery-logs");

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
  if (!notificationArea && !alertsPanel) {
    return;
  }
  const alertMarkup = `
    <div class="alert alert-${tone} alert-dismissible fade show mb-3" role="alert">
      ${escapeHtml(message)}
      <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
    </div>
  `;
  if (notificationArea) {
    notificationArea.innerHTML = alertMarkup;
  }
  if (alertsPanel) {
    alertsPanel.innerHTML = `
      <div class="alert alert-${tone} mb-0" role="alert">${escapeHtml(message)}</div>
    `;
  }
}

function setUploadLoading(isLoading) {
  if (!uploadButton || !fileInput || !uploadButtonText || !uploadSpinner) {
    return;
  }
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
  if (!fileList) {
    return;
  }
  if (!files.length) {
    fileList.innerHTML = `<tr><td colspan="5" class="text-center text-secondary py-4">No active files available.</td></tr>`;
    return;
  }

  fileList.innerHTML = files
    .map(
      (file) => {
        const rowClass =
          file.status === "TAMPERED"
            ? "tampered-row"
            : file.id === state.highlightedRecoveredFileId || file.status === "RECOVERED"
              ? "recovered-row"
              : "";
        const normalizedLabel =
          file.normalized_filename && file.normalized_filename !== file.filename
            ? `<div class="small text-danger">Normalized: ${escapeHtml(file.normalized_filename)}</div>`
            : "";
        const uploadAliasLabel =
          file.latest_uploaded_filename && file.latest_uploaded_filename !== file.filename
            ? `<div class="small text-danger">Uploaded as: ${escapeHtml(file.latest_uploaded_filename)}</div>`
            : "";
        return `
        <tr class="${rowClass}">
          <td>
            <div class="fw-semibold">${escapeHtml(file.filename)}</div>
            ${uploadAliasLabel}
            ${normalizedLabel}
            <div class="small text-secondary">${escapeHtml(file.sha256_hash)}</div>
          </td>
          <td>${statusBadge(file.status)}</td>
          <td>${escapeHtml(file.uploaded_by || "Unknown")}</td>
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
      `;
      },
    )
    .join("");
}

function renderDeletedFiles(files) {
  if (!deletedFileList) {
    return;
  }
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
  if (!recoveryLogList) {
    return;
  }
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
        </tr>
      `,
    )
    .join("");
}

function renderStorageFiles(files) {
  if (!storageFileList) {
    return;
  }
  if (!files.length) {
    storageFileList.innerHTML = `<tr><td colspan="4" class="text-center text-secondary py-4">No active cloud objects available.</td></tr>`;
    return;
  }

  storageFileList.innerHTML = files
    .map(
      (file) => `
        <tr class="${file.status === "TAMPERED" ? "tampered-row" : ""}">
          <td>
            <div class="fw-semibold">${escapeHtml(file.filename)}</div>
            <div class="small text-secondary">${escapeHtml(file.content_type || "application/octet-stream")}</div>
          </td>
          <td>${statusBadge(file.status)}</td>
          <td><div class="small text-secondary hash-text">${escapeHtml(file.sha256_hash)}</div></td>
          <td>
            <div class="d-flex flex-wrap gap-2">
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

function renderRecentActivity(files, logs) {
  if (!recentActivityList) {
    return;
  }

  const fileEvents = files.slice(0, 5).map((file) => ({
    name: file.filename,
    status: file.status,
  }));
  const logEvents = logs.slice(0, 5).map((log) => ({
    name: log.filename,
    status: log.action,
  }));
  const events = [...fileEvents, ...logEvents].slice(0, 8);

  if (!events.length) {
    recentActivityList.innerHTML = `<tr><td colspan="2" class="text-center text-secondary py-4">No activity yet.</td></tr>`;
    return;
  }

  recentActivityList.innerHTML = events
    .map(
      (event) => `
        <tr>
          <td>${escapeHtml(event.name)}</td>
          <td>${statusBadge(event.status)}</td>
        </tr>
      `,
    )
    .join("");
}

function updateStats(files, deletedFiles, logs) {
  if (statActiveFiles) {
    statActiveFiles.textContent = files.length;
  }
  if (statTamperedFiles) {
    statTamperedFiles.textContent = files.filter((file) => file.status === "TAMPERED").length;
  }
  if (statDeletedFiles) {
    statDeletedFiles.textContent = deletedFiles.length;
  }
  if (statRecoveryLogs) {
    statRecoveryLogs.textContent = logs.length;
  }
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
  const recoveryLogs = logs.logs || [];
  renderLogs(recoveryLogs);
  renderStorageFiles(state.filesCache || []);
  renderRecentActivity(state.filesCache || [], recoveryLogs);
  updateStats(state.filesCache || [], state.deletedFilesCache || [], recoveryLogs);
}

if (uploadForm) {
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
      pushAlert(data.message || "File uploaded successfully.", data.file?.status === "TAMPERED" ? "danger" : "success");
      await loadFiles();
    } catch (error) {
      pushAlert(error.message || "Upload failed.", "danger");
    } finally {
      setUploadLoading(false);
    }
  });
}

if (refreshButton) {
  refreshButton.addEventListener("click", async () => {
    try {
      await loadFiles();
      pushAlert("Dashboard data refreshed.", "info");
    } catch (error) {
      pushAlert(error.message, "danger");
    }
  });
}

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

/**
 * KaizenReader Google Drive Cartridge Locker (`src/ui/gdrive.js`).
 *
 * Connects directly to Google Drive API v3 from both MacBook Pro M1 and iPhone 16e
 * using Google Identity Services (OAuth 2.0) — zero backend secrets required.
 * - Browses `.kzn` Sovereign Cartridges and `.epub`/`.pdf`/`.md`/`.docx`/`.txt` books.
 * - Downloads `.kzn` cartridges straight into IndexedDB `kaizen_sovereign_vault_v1`
 *   on any coffee-shop Wi-Fi, even when the MacBook Pro M1 is powered off.
 * - Pushes newly compiled `.kzn` cartridges from the Mac Foundry into a `KaizenReader`
 *   folder in Google Drive for anywhere-access on iPhone 16e.
 */
(function (global) {
  "use strict";

  const DRIVE_API = "https://www.googleapis.com/drive/v3";
  const DRIVE_UPLOAD_API = "https://www.googleapis.com/upload/drive/v3";
  const SCOPES = "https://www.googleapis.com/auth/drive.readonly https://www.googleapis.com/auth/drive.file";
  const SUPPORTED_EXT_RE = /\.(kzn|epub|pdf|md|markdown|docx|txt|html|htm)$/i;

  let _accessToken = null;
  let _tokenExpiresAt = 0;
  let _tokenClient = null;
  let _gisLoaded = false;

  function getSavedClientId() {
    return localStorage.getItem("kaizen_gdrive_client_id") || "";
  }

  function setSavedClientId(clientId) {
    const clean = (clientId || "").trim();
    localStorage.setItem("kaizen_gdrive_client_id", clean);
    fetch("/api/gdrive/config", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ client_id: clean }),
    }).catch(() => {});
    return clean;
  }

  async function syncConfigFromServer() {
    try {
      const res = await fetch("/api/gdrive/config");
      if (res.ok) {
        const cfg = await res.json();
        if (cfg.client_id && !getSavedClientId()) {
          localStorage.setItem("kaizen_gdrive_client_id", cfg.client_id);
        }
        return cfg;
      }
    } catch (e) {}
    return { client_id: getSavedClientId(), folder_name: "KaizenReader" };
  }

  function loadGisScript() {
    if (_gisLoaded || (global.google && global.google.accounts && global.google.accounts.oauth2)) {
      _gisLoaded = true;
      return Promise.resolve();
    }
    return new Promise((resolve, reject) => {
      const s = document.createElement("script");
      s.src = "https://accounts.google.com/gsi/client";
      s.async = true;
      s.defer = true;
      s.onload = () => {
        _gisLoaded = true;
        resolve();
      };
      s.onerror = () => reject(new Error("Could not load Google Identity Services (check Wi-Fi)."));
      document.head.appendChild(s);
    });
  }

  function isConnected() {
    return Boolean(_accessToken && Date.now() < _tokenExpiresAt - 15000);
  }

  async function connect(clientIdOverride = null) {
    const clientId = (clientIdOverride || getSavedClientId()).trim();
    if (!clientId) {
      throw new Error("Enter your Google OAuth Client ID first.");
    }
    setSavedClientId(clientId);
    await loadGisScript();

    return new Promise((resolve, reject) => {
      _tokenClient = global.google.accounts.oauth2.initTokenClient({
        client_id: clientId,
        scope: SCOPES,
        callback: (resp) => {
          if (resp.error) {
            reject(new Error(resp.error_description || resp.error));
            return;
          }
          _accessToken = resp.access_token;
          _tokenExpiresAt = Date.now() + Number(resp.expires_in || 3600) * 1000;
          resolve(_accessToken);
        },
      });
      _tokenClient.requestAccessToken({ prompt: _accessToken ? "" : "consent" });
    });
  }

  function disconnect() {
    if (_accessToken && global.google?.accounts?.oauth2) {
      try {
        global.google.accounts.oauth2.revoke(_accessToken);
      } catch (e) {}
    }
    _accessToken = null;
    _tokenExpiresAt = 0;
  }

  async function driveFetch(url, options = {}) {
    if (!isConnected()) {
      throw new Error("Not connected to Google Drive");
    }
    const headers = new Headers(options.headers || {});
    headers.set("Authorization", `Bearer ${_accessToken}`);
    const res = await fetch(url, { ...options, headers });
    if (res.status === 401) {
      _accessToken = null;
      throw new Error("Google Drive session expired. Tap Connect to refresh.");
    }
    if (!res.ok) {
      const errText = await res.text();
      throw new Error(`Drive API ${res.status}: ${errText.slice(0, 140)}`);
    }
    return res;
  }

  async function findOrCreateKaizenFolder(folderName = "KaizenReader") {
    const q = `name='${folderName}' and mimeType='application/vnd.google-apps.folder' and trashed=false`;
    const listUrl = `${DRIVE_API}/files?q=${encodeURIComponent(q)}&fields=files(id,name)&pageSize=5`;
    const res = await driveFetch(listUrl);
    const data = await res.json();
    if (data.files && data.files.length > 0) {
      return data.files[0].id;
    }

    const createRes = await driveFetch(`${DRIVE_API}/files`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        name: folderName,
        mimeType: "application/vnd.google-apps.folder",
      }),
    });
    const created = await createRes.json();
    return created.id;
  }

  async function listDriveLibraryFiles(onlyKaizenFolder = false) {
    let q = "trashed=false and mimeType!='application/vnd.google-apps.folder'";
    if (onlyKaizenFolder) {
      const folderId = await findOrCreateKaizenFolder("KaizenReader");
      q += ` and '${folderId}' in parents`;
    } else {
      const extFilters = [
        "name contains '.kzn'",
        "name contains '.epub'",
        "name contains '.pdf'",
        "name contains '.md'",
        "name contains '.docx'",
        "name contains '.txt'",
      ].join(" or ");
      q += ` and (${extFilters})`;
    }

    const url = `${DRIVE_API}/files?q=${encodeURIComponent(q)}&orderBy=modifiedTime desc&pageSize=40&fields=files(id,name,size,mimeType,modifiedTime)`;
    const res = await driveFetch(url);
    const data = await res.json();
    return (data.files || []).filter((f) => SUPPORTED_EXT_RE.test(f.name || ""));
  }

  async function downloadFileAsBlob(fileId) {
    const url = `${DRIVE_API}/files/${encodeURIComponent(fileId)}?alt=media`;
    const res = await driveFetch(url);
    return res.blob();
  }

  async function uploadCartridgeToDrive(filename, blobOrBytes, folderName = "KaizenReader") {
    const folderId = await findOrCreateKaizenFolder(folderName);
    const metadata = {
      name: filename,
      parents: [folderId],
      mimeType: "application/zip",
    };

    const boundary = `kaizen_boundary_${Date.now()}`;
    const metaPart = `--${boundary}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n${JSON.stringify(metadata)}\r\n`;
    const fileHeader = `--${boundary}\r\nContent-Type: application/zip\r\n\r\n`;
    const footer = `\r\n--${boundary}--`;

    const bodyBlob = new Blob([metaPart, fileHeader, blobOrBytes, footer], {
      type: `multipart/related; boundary=${boundary}`,
    });

    const res = await driveFetch(
      `${DRIVE_UPLOAD_API}/files?uploadType=multipart&fields=id,name,size`,
      {
        method: "POST",
        body: bodyBlob,
      }
    );
    return res.json();
  }

  global.KaizenGDrive = {
    getSavedClientId,
    setSavedClientId,
    syncConfigFromServer,
    loadGisScript,
    isConnected,
    connect,
    disconnect,
    findOrCreateKaizenFolder,
    listDriveLibraryFiles,
    downloadFileAsBlob,
    uploadCartridgeToDrive,
  };
})(window);

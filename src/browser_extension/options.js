const intercept = document.getElementById("intercept");
const status = document.getElementById("status");
const logs = document.getElementById("logs");
const refreshButton = document.getElementById("refresh");
const copyButton = document.getElementById("copy");
const clearButton = document.getElementById("clear");
const testButton = document.getElementById("test");
const extensionVersion = document.getElementById("extension-version");
const TEST_URL = "https://www.youtube.com/watch?v=dQw4w9WgXcQ";

const manifest = chrome.runtime.getManifest();
extensionVersion.textContent = `Version ${manifest.version}`;

chrome.storage.sync.get({interceptYoutubeClicks: false}, (items) => {
  intercept.checked = Boolean(items.interceptYoutubeClicks);
});

function requestAllSitesPermission() {
  return new Promise((resolve) => {
    chrome.permissions.request({origins: ["<all_urls>"]}, resolve);
  });
}

function sendMessage(message) {
  return new Promise((resolve) => {
    chrome.runtime.sendMessage(message, resolve);
  });
}

async function refreshLogs() {
  const response = await sendMessage({type: "get-diagnostic-log"});
  const lines = (response?.log || []).map((entry) => {
    const details = JSON.stringify(entry.details || {});
    return `${entry.time} ${entry.message} ${details}`;
  });
  logs.value = lines.join("\n");
}

function setStatus(message) {
  status.textContent = message;
  window.setTimeout(() => {
    status.textContent = "";
  }, 2500);
}

intercept.addEventListener("change", () => {
  const enabled = intercept.checked;
  const save = (value, message) => {
    chrome.storage.sync.set({interceptYoutubeClicks: value}, () => {
      intercept.checked = value;
      setStatus(message);
    });
  };

  if (!enabled) {
    save(false, "Saved.");
    return;
  }

  requestAllSitesPermission().then((granted) => {
    if (!granted) {
      save(false, "Permission was not granted.");
      return;
    }
    save(true, "Saved.");
  });
});

refreshButton.addEventListener("click", () => {
  refreshLogs();
});

copyButton.addEventListener("click", async () => {
  await refreshLogs();
  await navigator.clipboard.writeText(logs.value);
  setStatus("Logs copied.");
});

clearButton.addEventListener("click", async () => {
  await sendMessage({type: "clear-diagnostic-log"});
  await refreshLogs();
  setStatus("Logs cleared.");
});

const exportCookiesButton = document.getElementById("export-cookies");

exportCookiesButton?.addEventListener("click", async () => {
  setStatus("Exporting cookies to HexPlayer...");
  try {
    const response = await sendMessage({type: "export-cookies-to-hexplayer"});
    if (response?.ok) {
      setStatus(
        `Successfully exported ${response.count || 0} YouTube cookies to HexPlayer.`,
      );
    } else {
      setStatus(`Failed to export cookies: ${response?.error || "Unknown error"}`);
    }
  } catch (err) {
    setStatus(`Error: ${err.message || String(err)}`);
  }
});

refreshLogs();

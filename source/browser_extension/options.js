const intercept = document.getElementById("intercept");
const status = document.getElementById("status");
const logs = document.getElementById("logs");
const refreshButton = document.getElementById("refresh");
const copyButton = document.getElementById("copy");
const clearButton = document.getElementById("clear");
const testButton = document.getElementById("test");
const TEST_URL = "https://www.youtube.com/watch?v=dQw4w9WgXcQ";

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

testButton.addEventListener("click", () => {
  chrome.runtime.sendMessage({
    type: "open-url-in-hexplayer",
    url: TEST_URL,
  });
});

refreshLogs();

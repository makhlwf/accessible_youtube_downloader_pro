importScripts("youtube-links.js");

const SETTINGS_DEFAULTS = {
  interceptYoutubeClicks: false,
};
const CLICK_SCRIPT_ID = "hexplayer-youtube-clicks";
const MAX_LOG_ENTRIES = 80;
const NATIVE_HOST_NAME = "com.hexplayer.link_helper";

function logEvent(message, details = {}) {
  const entry = {
    time: new Date().toISOString(),
    message,
    details,
  };
  console.log("[HexPlayer Link Helper]", message, details);
  chrome.storage.local.get({diagnosticLog: []}, (items) => {
    const diagnosticLog = [...items.diagnosticLog, entry].slice(-MAX_LOG_ENTRIES);
    chrome.storage.local.set({diagnosticLog});
  });
}

function getStorage(defaults) {
  return new Promise((resolve) => {
    chrome.storage.sync.get(defaults, resolve);
  });
}

function permissionsContains(permissions) {
  return new Promise((resolve) => {
    chrome.permissions.contains(permissions, resolve);
  });
}

function unregisterClickInterceptionScript() {
  return new Promise((resolve) => {
    chrome.scripting.unregisterContentScripts({ids: [CLICK_SCRIPT_ID]}, () => {
      chrome.runtime.lastError;
      resolve();
    });
  });
}

function registerClickInterceptionScript() {
  return new Promise((resolve) => {
    chrome.scripting.registerContentScripts(
      [
        {
          id: CLICK_SCRIPT_ID,
          matches: ["<all_urls>"],
          js: ["youtube-links.js", "content.js"],
          runAt: "document_start",
        },
      ],
      () => {
        resolve(!chrome.runtime.lastError);
      },
    );
  });
}

async function syncClickInterceptionRegistration(enabled) {
  await unregisterClickInterceptionScript();
  if (!enabled) {
    logEvent("Click interception disabled");
    return false;
  }

  const hasPermission = await permissionsContains({origins: ["<all_urls>"]});
  if (!hasPermission) {
    logEvent("Click interception permission missing");
    chrome.storage.sync.set({interceptYoutubeClicks: false});
    return false;
  }

  const registered = await registerClickInterceptionScript();
  logEvent("Click interception registration updated", {registered});
  return registered;
}

function sendNativeOpenMessage(youtubeUrl) {
  return new Promise((resolve) => {
    chrome.runtime.sendNativeMessage(
      NATIVE_HOST_NAME,
      {type: "open", url: youtubeUrl},
      (response) => {
        if (chrome.runtime.lastError) {
          resolve({
            ok: false,
            error: chrome.runtime.lastError.message,
          });
          return;
        }
        resolve(response || {ok: false, error: "Empty native host response"});
      },
    );
  });
}

function openFallbackLaunchPage(youtubeUrl) {
  const launchUrl = chrome.runtime.getURL(
    `launch.html?url=${encodeURIComponent(youtubeUrl)}`,
  );
  logEvent("Opening HexPlayer launch page fallback", {youtubeUrl});
  chrome.tabs.create({url: launchUrl, active: true}, () => {
    if (chrome.runtime.lastError) {
      logEvent("Failed to open launch page", {
        error: chrome.runtime.lastError.message,
      });
    }
  });
}

async function launchHexPlayer(url) {
  const youtubeUrl = extractSupportedYouTubeUrl(url);
  if (!youtubeUrl) {
    logEvent("Ignored unsupported URL", {url});
    return;
  }

  logEvent("Sending URL to Native Messaging host", {youtubeUrl});
  const response = await sendNativeOpenMessage(youtubeUrl);
  if (response?.ok) {
    logEvent("Native Messaging host opened HexPlayer", {youtubeUrl});
    return;
  }

  logEvent("Native Messaging host failed; using fallback", {
    youtubeUrl,
    error: response?.error || "Unknown native host error",
  });
  openFallbackLaunchPage(youtubeUrl);
}

chrome.runtime.onInstalled.addListener(() => {
  logEvent("Extension installed or updated");
  chrome.storage.sync.get(SETTINGS_DEFAULTS, (items) => {
    const enabled = Boolean(items.interceptYoutubeClicks);
    chrome.storage.sync.set({interceptYoutubeClicks: enabled});
    syncClickInterceptionRegistration(enabled);
  });

  chrome.contextMenus.removeAll(() => {
    chrome.contextMenus.create({
      id: "open-link-in-hexplayer",
      title: "Open YouTube link in HexPlayer",
      contexts: ["link"],
      targetUrlPatterns: [
        "*://*.youtube.com/*",
        "*://youtube.com/*",
        "*://youtu.be/*",
      ],
    });

    chrome.contextMenus.create({
      id: "open-page-in-hexplayer",
      title: "Open this YouTube page in HexPlayer",
      contexts: ["page"],
      documentUrlPatterns: [
        "*://*.youtube.com/*",
        "*://youtube.com/*",
        "*://youtu.be/*",
      ],
    });
    logEvent("Context menus registered");
  });
});

chrome.storage.sync.get(SETTINGS_DEFAULTS, (items) => {
  syncClickInterceptionRegistration(Boolean(items.interceptYoutubeClicks));
});

chrome.storage.onChanged.addListener((changes, areaName) => {
  if (areaName !== "sync" || !changes.interceptYoutubeClicks) {
    return;
  }
  syncClickInterceptionRegistration(Boolean(changes.interceptYoutubeClicks.newValue));
});

chrome.contextMenus.onClicked.addListener((info, tab) => {
  logEvent("Context menu clicked", {
    menuItemId: info.menuItemId,
    linkUrl: info.linkUrl || "",
    pageUrl: info.pageUrl || tab?.url || "",
  });
  if (info.menuItemId === "open-link-in-hexplayer") {
    launchHexPlayer(info.linkUrl);
  } else if (info.menuItemId === "open-page-in-hexplayer") {
    launchHexPlayer(info.pageUrl || tab?.url);
  }
});

chrome.action.onClicked.addListener((tab) => {
  logEvent("Toolbar button clicked", {url: tab?.url || ""});
  launchHexPlayer(tab?.url);
});

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (message?.type === "get-diagnostic-log") {
    chrome.storage.local.get({diagnosticLog: []}, (items) => {
      sendResponse({log: items.diagnosticLog});
    });
    return true;
  }

  if (message?.type === "clear-diagnostic-log") {
    chrome.storage.local.set({diagnosticLog: []}, () => {
      sendResponse({ok: true});
    });
    return true;
  }

  if (message?.type === "diagnostic-event") {
    logEvent(message.message || "Diagnostic event", message.details || {});
    sendResponse({ok: true});
    return true;
  }

  if (message?.type === "open-url-in-hexplayer") {
    launchHexPlayer(message.url);
    sendResponse({ok: true});
    return true;
  }

  if (message?.type !== "open-in-hexplayer") {
    return false;
  }

  getStorage(SETTINGS_DEFAULTS).then((settings) => {
    if (settings.interceptYoutubeClicks) {
      logEvent("Intercepted click message received", {url: message.url});
      launchHexPlayer(message.url);
      sendResponse({ok: true});
    } else {
      logEvent("Ignored intercepted click because setting is disabled", {
        url: message.url,
      });
      sendResponse({ok: false});
    }
  });
  return true;
});

let interceptYoutubeClicks = false;

chrome.storage.sync.get({interceptYoutubeClicks: false}, (items) => {
  interceptYoutubeClicks = Boolean(items.interceptYoutubeClicks);
});

chrome.storage.onChanged.addListener((changes, areaName) => {
  if (areaName !== "sync" || !changes.interceptYoutubeClicks) {
    return;
  }
  interceptYoutubeClicks = Boolean(changes.interceptYoutubeClicks.newValue);
});

function getAnchorFromEvent(event) {
  const path = event.composedPath ? event.composedPath() : [];
  for (const item of path) {
    if (item?.tagName === "A" && item.href) {
      return item;
    }
  }

  if (event.target?.closest) {
    return event.target.closest("a[href]");
  }
  return null;
}

document.addEventListener(
  "click",
  (event) => {
    if (
      !interceptYoutubeClicks ||
      event.defaultPrevented ||
      event.button !== 0 ||
      event.altKey ||
      event.ctrlKey ||
      event.metaKey ||
      event.shiftKey
    ) {
      return;
    }

    const anchor = getAnchorFromEvent(event);
    const youtubeUrl = extractSupportedYouTubeUrl(anchor?.href);
    if (!youtubeUrl) {
      return;
    }

    event.preventDefault();
    event.stopPropagation();
    chrome.runtime.sendMessage({
      type: "open-in-hexplayer",
      url: youtubeUrl,
    }, (response) => {
      if (!response?.ok) {
        chrome.runtime.sendMessage({
          type: "diagnostic-event",
          message: "Content script click message was not accepted",
          details: {url: youtubeUrl},
        });
      }
    });
  },
  true,
);

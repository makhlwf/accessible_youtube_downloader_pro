const statusElement = document.getElementById("status");
const urlElement = document.getElementById("url");
const openButton = document.getElementById("open");

function log(message, details = {}) {
  chrome.runtime.sendMessage({
    type: "diagnostic-event",
    message,
    details,
  });
}

function getLaunchUrl() {
  const params = new URLSearchParams(window.location.search);
  return extractSupportedYouTubeUrl(params.get("url") || "");
}

function openHexPlayer(youtubeUrl, source) {
  const hexPlayerUrl = buildHexPlayerUrl(youtubeUrl);
  statusElement.textContent = "Asking Brave to open HexPlayer...";
  log("Launch page opening custom protocol", {youtubeUrl, source});
  window.location.href = hexPlayerUrl;
  window.setTimeout(() => {
    statusElement.textContent =
      "If HexPlayer did not open, make sure browser integration is enabled in HexPlayer settings.";
  }, 2500);
}

const youtubeUrl = getLaunchUrl();
if (!youtubeUrl) {
  statusElement.textContent = "This is not a supported YouTube link.";
  openButton.disabled = true;
  log("Launch page received unsupported URL", {
    search: window.location.search,
  });
} else {
  urlElement.textContent = youtubeUrl;
  openButton.addEventListener("click", () => openHexPlayer(youtubeUrl, "button"));
  window.setTimeout(() => openHexPlayer(youtubeUrl, "automatic"), 200);
}

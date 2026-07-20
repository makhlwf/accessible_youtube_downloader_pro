function normaliseUrlCandidate(value) {
  if (typeof value !== "string") {
    return "";
  }

  value = value.trim().replace(/^["']|["']$/g, "");
  if (value.startsWith("//")) {
    return `https:${value}`;
  }
  if (/^(?:[\w-]+\.)?(?:youtube\.com|youtu\.be)(?:[/:?#]|$)/i.test(value)) {
    return `https://${value}`;
  }
  return value;
}

function isYouTubeHost(hostname) {
  hostname = hostname.toLowerCase();
  return (
    hostname === "youtu.be" ||
    hostname === "youtube.com" ||
    hostname.endsWith(".youtube.com")
  );
}

function isSupportedYouTubeUrl(value) {
  value = normaliseUrlCandidate(value);
  let url;
  try {
    url = new URL(value);
  } catch (_error) {
    return false;
  }

  if (!["http:", "https:"].includes(url.protocol) || !isYouTubeHost(url.hostname)) {
    return false;
  }

  const segments = url.pathname.split("/").filter(Boolean);
  if (url.hostname.toLowerCase() === "youtu.be") {
    return segments.length > 0;
  }

  if (url.pathname === "/watch") {
    return url.searchParams.has("v") || url.searchParams.has("list");
  }
  if (url.pathname === "/playlist") {
    return url.searchParams.has("list");
  }
  if (segments.length === 0) {
    return false;
  }

  const firstSegment = segments[0];
  if (firstSegment.startsWith("@")) {
    return firstSegment.length > 1;
  }
  return ["shorts", "embed", "v", "live", "clip", "channel", "c", "user"].includes(
    firstSegment,
  ) && segments.length > 1;
}

function extractSupportedYouTubeUrl(value) {
  value = normaliseUrlCandidate(value);
  if (isSupportedYouTubeUrl(value)) {
    return value;
  }
  return "";
}

function buildHexPlayerUrl(youtubeUrl) {
  return `hexplayer://open?url=${encodeURIComponent(youtubeUrl)}`;
}

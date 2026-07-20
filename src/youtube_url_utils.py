import re
from urllib.parse import parse_qs, unquote, urlparse


def youtube_regexp(string):
    pattern = re.compile(
        r"^((?:https?:)?\/\/)?((?:www|m)\.)?((?:youtube\.com|youtu.be))(\/(?:[\w\-]+.*[?&]v=|embed\/|v\/|shorts\/|watch\?.*list=|))([\w\-]{11,34})(.*)?$"
    )
    return pattern.search(string)


def _normalise_url_candidate(value):
    if not isinstance(value, str):
        return ""
    value = value.strip().strip("\"'")
    if value.startswith("//"):
        return f"https:{value}"
    if re.match(r"^(?:[\w-]+\.)?(?:youtube\.com|youtu\.be)(?:[/:?#]|$)", value, re.I):
        return f"https://{value}"
    return value


def _youtube_host(host):
    host = host.lower().split("@")[-1].split(":")[0]
    return host == "youtu.be" or host == "youtube.com" or host.endswith(".youtube.com")


def is_supported_youtube_url(value):
    value = _normalise_url_candidate(value)
    parsed = urlparse(value)
    if parsed.scheme not in ("http", "https") or not _youtube_host(parsed.netloc):
        return False

    host = parsed.netloc.lower().split("@")[-1].split(":")[0]
    path = parsed.path or ""
    segments = [segment for segment in path.split("/") if segment]
    query = parse_qs(parsed.query)

    if host == "youtu.be":
        return bool(segments)

    if path == "/watch":
        return bool(query.get("v") or query.get("list"))
    if path == "/playlist":
        return bool(query.get("list"))
    if not segments:
        return False

    first_segment = segments[0]
    if first_segment.startswith("@"):
        return len(first_segment) > 1
    if first_segment in {
        "shorts",
        "embed",
        "v",
        "live",
        "clip",
        "channel",
        "c",
        "user",
    }:
        return len(segments) > 1

    return youtube_regexp(value) is not None


def extract_supported_youtube_url(value):
    value = _normalise_url_candidate(value)
    if is_supported_youtube_url(value):
        return value

    if not isinstance(value, str):
        return ""
    pattern = re.compile(
        r"(?i)(https?:\/\/(?:[\w-]+\.)?(?:youtube\.com|youtu\.be)\/[^\s<>\"']+)"
    )
    for match in pattern.finditer(value):
        candidate = match.group(1).rstrip(".,;)]}")
        if is_supported_youtube_url(candidate):
            return candidate
    return ""


def extract_launch_youtube_url(value):
    if not isinstance(value, str):
        return ""

    value = value.strip().strip("\"'")
    parsed = urlparse(value)
    if parsed.scheme.lower() == "hexplayer":
        candidates = []
        query = parse_qs(parsed.query)
        candidates.extend(query.get("url", []))
        if parsed.path:
            candidates.append(parsed.path.lstrip("/"))
        if parsed.netloc and parsed.netloc not in {"open", "url"}:
            candidates.append(parsed.netloc)

        for candidate in candidates:
            url = extract_supported_youtube_url(unquote(candidate))
            if url:
                return url
        return ""

    return extract_supported_youtube_url(value)

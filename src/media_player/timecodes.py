import re

TIMECODE_PATTERN = re.compile(r"(?<![\d:])(?:\d+:)?\d{1,2}:\d{2}(?![\d:])")


def parse_timecode(value):
    text = str(value or "").strip()
    if not TIMECODE_PATTERN.fullmatch(text):
        return None

    parts = [int(part) for part in text.split(":")]
    if len(parts) == 2:
        minutes, seconds = parts
        hours = 0
    elif len(parts) == 3:
        hours, minutes, seconds = parts
        if minutes > 59:
            return None
    else:
        return None

    if seconds > 59:
        return None

    return hours * 3600 + minutes * 60 + seconds


def format_timecode(total_seconds):
    try:
        total_seconds = max(0, int(total_seconds))
    except TypeError, ValueError:
        total_seconds = 0

    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{seconds:02d}"
    return f"{minutes}:{seconds:02d}"


def extract_timecodes(text):
    timestamps = []
    seen = set()
    for match in TIMECODE_PATTERN.finditer(str(text or "")):
        label = match.group(0)
        seconds = parse_timecode(label)
        if seconds is None:
            continue
        key = (seconds, label)
        if key in seen:
            continue
        seen.add(key)
        timestamps.append({"label": label, "seconds": seconds})
    return timestamps

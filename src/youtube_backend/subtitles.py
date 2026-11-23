"""Subtitle track normalization and cue parsing."""

import html as html_parser
import json
import re
import xml.etree.ElementTree as ET

from language_handler import _

SUBTITLE_EXT_PRIORITY = {
    "json3": 0,
    "vtt": 1,
    "webvtt": 1,
    "ttml": 2,
    "dfxp": 2,
    "srv3": 3,
    "srv2": 4,
    "srv1": 5,
}


def _clean_subtitle_text(value):
    if value is None:
        return ""
    text = str(value)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html_parser.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def _subtitle_track_priority(entry):
    ext = str(entry.get("ext") or "").lower()
    return SUBTITLE_EXT_PRIORITY.get(ext, 99)


def _subtitle_language_label(code, entries, source):
    names = []
    for entry in entries:
        name = str(
            entry.get("name")
            or entry.get("language")
            or entry.get("language_name")
            or ""
        ).strip()
        if name and name not in names:
            names.append(name)

    label = names[0] if names else code
    if code and code not in label:
        label = f"{label} ({code})"
    if source == "automatic":
        label = _("{} - تلقائي").format(label)
    return label


def _normalize_subtitle_tracks(info):
    if not isinstance(info, dict):
        return []

    tracks = []
    seen_codes = set()
    sources = (
        ("manual", info.get("subtitles") or {}),
        ("automatic", info.get("automatic_captions") or {}),
    )

    for source, subtitles in sources:
        if not isinstance(subtitles, dict):
            continue
        for code, entries in subtitles.items():
            code = str(code or "").strip()
            if not code or code in seen_codes:
                continue
            if isinstance(entries, dict):
                entries = [entries]
            if not isinstance(entries, list):
                continue
            entries = [
                entry
                for entry in entries
                if isinstance(entry, dict) and entry.get("url")
            ]
            if not entries:
                continue

            selected = min(entries, key=_subtitle_track_priority)
            tracks.append(
                {
                    "code": code,
                    "label": _subtitle_language_label(code, entries, source),
                    "url": selected.get("url"),
                    "ext": str(selected.get("ext") or "").lower(),
                    "source": source,
                }
            )
            seen_codes.add(code)

    return sorted(tracks, key=lambda track: track["label"].casefold())


def _parse_subtitle_timestamp(value, numeric_unit="seconds"):
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None

    try:
        if text.endswith("ms"):
            return max(0, int(float(text[:-2]) or 0))
        if text.endswith("s") and not text.endswith("ms"):
            return max(0, int((float(text[:-1]) or 0) * 1000))
        if ":" in text:
            match = re.match(
                r"^(?:(\d+):)?(\d{1,2}):(\d{1,2})(?:[.,](\d{1,3}))?",
                text,
            )
            if not match:
                return None
            hours = int(match.group(1) or 0)
            minutes = int(match.group(2) or 0)
            seconds = int(match.group(3) or 0)
            milliseconds = int((match.group(4) or "0").ljust(3, "0")[:3])
            return ((hours * 3600 + minutes * 60 + seconds) * 1000) + milliseconds

        number = float(text)
        if numeric_unit == "milliseconds":
            return max(0, int(number))
        return max(0, int(number * 1000))
    except TypeError, ValueError:
        return None


def _normalize_subtitle_cues(cues):
    normalized = []
    for cue in cues:
        text = _clean_subtitle_text(cue.get("text"))
        if not text:
            continue
        try:
            start_ms = int(cue.get("start_ms"))
            end_ms = int(cue.get("end_ms"))
        except TypeError, ValueError:
            continue
        if end_ms <= start_ms:
            end_ms = start_ms + 1500
        normalized.append(
            {"start_ms": max(0, start_ms), "end_ms": max(0, end_ms), "text": text}
        )

    normalized.sort(key=lambda cue: (cue["start_ms"], cue["end_ms"]))
    deduped = []
    seen = set()
    for cue in normalized:
        key = (cue["start_ms"], cue["end_ms"], cue["text"])
        if key in seen:
            continue
        seen.add(key)
        deduped.append(cue)
    return deduped


def _parse_json3_subtitles(text):
    try:
        data = json.loads(text)
    except TypeError, json.JSONDecodeError:
        return []

    events = data.get("events") if isinstance(data, dict) else None
    if not isinstance(events, list):
        return []

    cues = []
    for index, event in enumerate(events):
        if not isinstance(event, dict):
            continue
        segments = event.get("segs") or []
        if not segments:
            continue
        text = "".join(str(segment.get("utf8") or "") for segment in segments)
        start_ms = event.get("tStartMs")
        duration_ms = event.get("dDurationMs")
        try:
            start_ms = int(start_ms)
        except TypeError, ValueError:
            continue
        try:
            end_ms = start_ms + int(duration_ms)
        except TypeError, ValueError:
            next_start = None
            for next_event in events[index + 1 :]:
                if isinstance(next_event, dict) and next_event.get("tStartMs"):
                    try:
                        next_start = int(next_event["tStartMs"])
                    except TypeError, ValueError:
                        next_start = None
                    break
            end_ms = next_start if next_start is not None else start_ms + 1500
        cues.append({"start_ms": start_ms, "end_ms": end_ms, "text": text})
    return _normalize_subtitle_cues(cues)


def _parse_vtt_subtitles(text):
    text = str(text or "").replace("\r\n", "\n").replace("\r", "\n")
    cues = []
    for block in re.split(r"\n\s*\n", text):
        lines = [line.strip() for line in block.split("\n") if line.strip()]
        if not lines:
            continue
        if lines[0].upper().startswith(("WEBVTT", "NOTE", "STYLE", "REGION")):
            continue

        timing_index = next(
            (index for index, line in enumerate(lines) if "-->" in line),
            None,
        )
        if timing_index is None:
            continue

        timing = lines[timing_index]
        start_text, end_text = [part.strip() for part in timing.split("-->", 1)]
        end_text = end_text.split()[0] if end_text else ""
        start_ms = _parse_subtitle_timestamp(start_text)
        end_ms = _parse_subtitle_timestamp(end_text)
        if start_ms is None or end_ms is None:
            continue
        cues.append(
            {
                "start_ms": start_ms,
                "end_ms": end_ms,
                "text": " ".join(lines[timing_index + 1 :]),
            }
        )
    return _normalize_subtitle_cues(cues)


def _parse_xml_subtitles(text):
    try:
        root = ET.fromstring(str(text or ""))
    except ET.ParseError:
        return []

    cues = []
    for element in root.iter():
        tag = element.tag.rsplit("}", 1)[-1].lower()
        if tag not in {"p", "text"}:
            continue
        content = "".join(element.itertext())
        if tag == "text":
            start_ms = _parse_subtitle_timestamp(
                element.get("start"), numeric_unit="seconds"
            )
            duration_ms = _parse_subtitle_timestamp(
                element.get("dur"), numeric_unit="seconds"
            )
            end_ms = (
                start_ms + duration_ms if None not in (start_ms, duration_ms) else None
            )
        else:
            start_ms = _parse_subtitle_timestamp(
                element.get("begin") or element.get("t"),
                numeric_unit="milliseconds" if element.get("t") else "seconds",
            )
            end_ms = _parse_subtitle_timestamp(element.get("end"))
            duration_ms = _parse_subtitle_timestamp(
                element.get("dur") or element.get("d"),
                numeric_unit="milliseconds" if element.get("d") else "seconds",
            )
            if end_ms is None and None not in (start_ms, duration_ms):
                end_ms = start_ms + duration_ms
        if start_ms is None or end_ms is None:
            continue
        cues.append({"start_ms": start_ms, "end_ms": end_ms, "text": content})
    return _normalize_subtitle_cues(cues)


def _parse_subtitle_cues(text, ext):
    ext = str(ext or "").lower()
    if ext == "json3":
        return _parse_json3_subtitles(text)
    if ext in {"vtt", "webvtt"}:
        return _parse_vtt_subtitles(text)
    if ext in {"ttml", "dfxp", "srv1", "srv2", "srv3"}:
        return _parse_xml_subtitles(text)
    return (
        _parse_vtt_subtitles(text)
        or _parse_json3_subtitles(text)
        or _parse_xml_subtitles(text)
    )

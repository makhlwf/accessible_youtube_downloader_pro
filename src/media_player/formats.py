"""Audio and video format selection and display labels."""

from collections import OrderedDict

from app_state.settings_handler import config_get
from language_handler import _

VIDEO_QUALITIES = [144, 240, 360, 480, 720, 1080, 1440, 2160]
AUDIO_QUALITIES = [64, 128, 256]


def _clamp_index(value, length, default=0):
    try:
        index = int(float(value)) if isinstance(value, str) else int(value)
    except TypeError, ValueError, OverflowError:
        index = default
    return max(0, min(index, length - 1))


VIDEO_QUALITY_DESCRIPTIONS = {
    144: _("144ب (جودة منخفضة جدًا)"),
    240: _("240ب (جودة منخفضة)"),
    360: _("360ب (جودة متوسطة)"),
    480: _("480ب (جودة متوسطة)"),
    720: _("720ب (جودة عالية عالية الدقة)"),
    1080: _("1080ب (جودة عالية جدًا عالية الدقة الكاملة)"),
    1440: _("1440ب (جودة فائقة 2 كي)"),
    2160: _("2160ب (جودة فائقة 4 كي)"),
}


def get_quality_description(height):
    return VIDEO_QUALITY_DESCRIPTIONS.get(
        height, _("{}ب (جودة غير معروفة)").format(height)
    )


def get_audio_track_languages():
    return [
        ("ar", _("العربية")),
        ("en", _("الإنجليزية")),
        ("es", _("الإسبانية")),
        ("fr", _("الفرنسية")),
        ("de", _("الألمانية")),
        ("it", _("الإيطالية")),
        ("pt", _("البرتغالية")),
        ("ru", _("الروسية")),
        ("ja", _("اليابانية")),
        ("ko", _("الكورية")),
        ("hi", _("الهندية")),
        ("tr", _("التركية")),
        ("id", _("الإندونيسية")),
        ("zh", _("الصينية")),
        ("vi", _("الفيتنامية")),
        ("bn", _("البنغالية")),
        ("pl", _("البولندية")),
        ("th", _("التايلاندية")),
        ("nl", _("الهولندية")),
        ("sv", _("السويدية")),
        ("fa", _("الفارسية")),
        ("ur", _("الأردية")),
    ]


AUDIO_TRACK_LANGUAGES = [
    ("ar", "العربية"),
    ("en", "الإنجليزية"),
    ("es", "الإسبانية"),
    ("fr", "الفرنسية"),
    ("de", "الألمانية"),
    ("it", "الإيطالية"),
    ("pt", "البرتغالية"),
    ("ru", "الروسية"),
    ("ja", "اليابانية"),
    ("ko", "الكورية"),
    ("hi", "الهندية"),
    ("tr", "التركية"),
    ("id", "الإندونيسية"),
    ("zh", "الصينية"),
    ("vi", "الفيتنامية"),
    ("bn", "البنغالية"),
    ("pl", "البولندية"),
    ("th", "التايلاندية"),
    ("nl", "الهولندية"),
    ("sv", "السويدية"),
    ("fa", "الفارسية"),
    ("ur", "الأردية"),
]


def is_language_match(track_lang, target_lang):
    if not track_lang or not target_lang:
        return False
    tl = str(track_lang).strip().lower()
    tgt = str(target_lang).strip().lower()
    if tl == tgt:
        return True
    tl_base = tl.split("-")[0].split("_")[0]
    tgt_base = tgt.split("-")[0].split("_")[0]
    if tl_base == tgt_base:
        return True
    iso_map = {
        "eng": "en",
        "ara": "ar",
        "spa": "es",
        "fra": "fr",
        "fre": "fr",
        "deu": "de",
        "ger": "de",
        "ita": "it",
        "por": "pt",
        "rus": "ru",
        "jpn": "ja",
        "kor": "ko",
        "hin": "hi",
        "tur": "tr",
        "ind": "id",
        "zho": "zh",
        "chi": "zh",
        "vie": "vi",
        "ben": "bn",
        "pol": "pl",
        "tha": "th",
        "nld": "nl",
        "dut": "nl",
        "swe": "sv",
        "fas": "fa",
        "per": "fa",
        "urd": "ur",
    }
    tl_mapped = iso_map.get(tl_base, tl_base)
    tgt_mapped = iso_map.get(tgt_base, tgt_base)
    return tl_mapped == tgt_mapped


def get_language_display_name(lang_code, note=""):
    code_base = (lang_code or "").split("-")[0].split("_")[0].lower()
    for code, label in get_audio_track_languages():
        if code.lower() == code_base:
            return label
    if note:
        cleaned_note = str(note).split("-")[0].split("(")[0].split(",")[0].strip()
        if cleaned_note and not cleaned_note.isdigit() and len(cleaned_note) > 1:
            return cleaned_note
    if lang_code and lang_code != "und":
        return str(lang_code).upper()
    return _("الصوت الأصلي")


def get_audio_tracks_from_formats(formats, entry=None):
    if not formats:
        return []
    audio_formats = [f for f in formats if f.get("acodec") not in (None, "none")]
    if not audio_formats:
        return []

    def marked_original(fmt):
        return (
            fmt.get("language_preference") == 10
            or "original" in str(fmt.get("format_note", "")).lower()
            or fmt.get("is_original") is True
        )

    tracks_by_key = OrderedDict()
    entry_lang = (entry.get("language") if isinstance(entry, dict) else "") or ""
    explicit_original = any(marked_original(fmt) for fmt in audio_formats)

    for f in audio_formats:
        lang = f.get("language") or ""
        note = str(f.get("format_note", ""))
        is_orig = marked_original(f) or (
            not explicit_original
            and f.get("language_preference") != 5
            and bool(entry_lang)
            and is_language_match(lang, entry_lang)
        )
        key = lang if lang else "default"
        if key not in tracks_by_key:
            tracks_by_key[key] = {
                "id": key,
                "lang": lang or "und",
                "is_original": is_orig,
                "formats": [f],
                "note": note,
            }
        else:
            tracks_by_key[key]["formats"].append(f)
            if is_orig:
                tracks_by_key[key]["is_original"] = True

    has_orig = any(tr["is_original"] for tr in tracks_by_key.values())
    if not has_orig and len(tracks_by_key) == 1:
        first_key = next(iter(tracks_by_key))
        tracks_by_key[first_key]["is_original"] = True

    tracks = []
    for key, tr in tracks_by_key.items():
        if tr["is_original"]:
            tr["formats"] = [
                fmt
                for fmt in tr["formats"]
                if fmt.get("language_preference") != 5 or marked_original(fmt)
            ] or tr["formats"]
        name = get_language_display_name(tr["lang"], tr["note"])
        if tr["is_original"]:
            if len(tracks_by_key) > 1 and name != _("الصوت الأصلي"):
                label = _("{language} (أصلي)").format(language=name)
            else:
                label = _("الصوت الأصلي")
        else:
            label = name
        tr["name"] = name
        tr["label"] = label
        tracks.append(tr)

    return tracks


def select_audio_format(
    formats,
    entry=None,
    preferred_lang=None,
    force_original=None,
    preferred_quality_index=None,
    audio_track_id=None,
):
    if not formats:
        return None, None

    tracks = get_audio_tracks_from_formats(formats, entry=entry)
    if not tracks:
        return None, None

    if preferred_quality_index is None:
        try:
            preferred_quality_index = int(config_get("defaultaudioquality"))
        except Exception:
            preferred_quality_index = 1

    target_abr = AUDIO_QUALITIES[
        _clamp_index(preferred_quality_index, len(AUDIO_QUALITIES), 1)
    ]

    def pick_track_format(track):
        fmts = track["formats"]
        fmts = [fmt for fmt in fmts if fmt.get("vcodec") == "none"] or fmts
        with_bitrate = [fmt for fmt in fmts if fmt.get("abr") is not None]
        return (
            min(with_bitrate, key=lambda fmt: abs(fmt["abr"] - target_abr))
            if with_bitrate
            else fmts[-1]
        )

    if audio_track_id:
        chosen_track = next((t for t in tracks if t["id"] == audio_track_id), None)
        if chosen_track:
            return pick_track_format(chosen_track), chosen_track

    if force_original is None:
        force_original = bool(config_get("force_original_audio"))
    if preferred_lang is None:
        preferred_lang = config_get("preferred_audio_language")

    orig_track = next((t for t in tracks if t["is_original"]), tracks[0])

    if force_original:
        chosen_track = orig_track
    elif preferred_lang:
        matched_track = next(
            (t for t in tracks if is_language_match(t["lang"], preferred_lang)),
            None,
        )
        if matched_track:
            chosen_track = matched_track
        else:
            chosen_track = orig_track
    else:
        chosen_track = orig_track

    return pick_track_format(chosen_track), chosen_track


def pick_best_format(
    formats,
    preferred_index,
    is_video=True,
    target_height=None,
    preferred_audio_lang=None,
    force_original=None,
    audio_track_id=None,
):
    if is_video:
        target_list = VIDEO_QUALITIES
        if target_height is not None:
            preferred_val = target_height
        else:
            preferred_val = target_list[
                _clamp_index(preferred_index, len(target_list), 0)
            ]

        available = [
            f
            for f in formats
            if f.get("vcodec") != "none" and f.get("height") is not None
        ]

        enforce_original = (
            config_get("force_original_audio")
            if force_original is None
            else force_original
        )
        if enforce_original or audio_track_id:
            track_formats = get_audio_tracks_from_formats(formats)
            requested = next(
                (track for track in track_formats if track["id"] == audio_track_id),
                None,
            )
            if requested is None and enforce_original:
                requested = next(
                    (track for track in track_formats if track["is_original"]), None
                )
            if requested is not None:
                compatible = [
                    f
                    for f in available
                    if f.get("acodec") == "none" or f in requested["formats"]
                ]
                if compatible:
                    available = compatible

        if not available:
            return None, None, None

        available.sort(key=lambda x: x.get("height", 0))

        fmt = None
        if target_height is not None:
            match = [f for f in available if f.get("height") == target_height]
            if match:
                fmt = match[0]

        if not fmt:
            try:
                pref_idx = (
                    target_list.index(preferred_val)
                    if target_height is None
                    else next(
                        i
                        for i, v in enumerate(target_list)
                        if v >= preferred_val or i == len(target_list) - 1
                    )
                )
            except ValueError, StopIteration:
                pref_idx = _clamp_index(preferred_index, len(target_list), 0)

            for i in range(pref_idx, -1, -1):
                target = target_list[i]
                match = [f for f in available if f.get("height") == target]
                if match:
                    fmt = match[0]
                    break

        if not fmt:
            for i in range(pref_idx + 1, len(target_list)):
                target = target_list[i]
                match = [f for f in available if f.get("height") == target]
                if match:
                    fmt = match[0]
                    break

        if not fmt:
            fmt = available[-1]

        audio_fmt = None
        if fmt.get("acodec") == "none":
            audio_fmt, chosen_track = select_audio_format(
                formats,
                preferred_lang=preferred_audio_lang,
                force_original=force_original,
                audio_track_id=audio_track_id,
            )
            if audio_fmt is None:
                audio_formats = [
                    f
                    for f in formats
                    if f.get("acodec") != "none" and f.get("vcodec") == "none"
                ]
                if audio_formats:
                    audio_formats.sort(key=lambda x: x.get("abr") or 0)
                    audio_fmt = audio_formats[-1]
            elif chosen_track is not None:
                audio_fmt = {**audio_fmt, "_chosen_track": chosen_track}

        return fmt, audio_fmt, fmt.get("height")
    else:
        fmt, chosen_track = select_audio_format(
            formats,
            preferred_lang=preferred_audio_lang,
            force_original=force_original,
            preferred_quality_index=preferred_index,
            audio_track_id=audio_track_id,
        )
        if fmt is not None:
            if chosen_track is not None:
                fmt = {**fmt, "_chosen_track": chosen_track}
            return fmt, None, fmt.get("abr")

        available = [
            f
            for f in formats
            if f.get("acodec") != "none"
            and f.get("vcodec") == "none"
            and f.get("abr") is not None
        ]
        if not available:
            available = [f for f in formats if f.get("acodec") != "none"]
        if not available:
            return None, None, None

        available.sort(key=lambda x: x.get("abr") or 0)
        target_abr = AUDIO_QUALITIES[
            _clamp_index(preferred_index, len(AUDIO_QUALITIES), 1)
        ]

        # Find the format with abr closest to target_abr
        fmt = min(available, key=lambda x: abs((x.get("abr") or 0) - target_abr))

        return fmt, None, fmt.get("abr")

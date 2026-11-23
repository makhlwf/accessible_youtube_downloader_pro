"""Duration and filename formatting."""

import re

from language_handler import _


def time_formatting(total_seconds):
    if total_seconds is None:
        return ""
    try:
        total_seconds = int(total_seconds)
    except ValueError, TypeError:
        return ""

    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)

    parts = []
    if hours > 0:
        if hours == 1:
            parts.append(_("ساعة واحدة"))
        elif hours == 2:
            parts.append(_("ساعتان"))
        elif 3 <= hours <= 10:
            parts.append(_("{} ساعات").format(hours))
        else:
            parts.append(_("{} ساعة").format(hours))

    if minutes > 0:
        if minutes == 1:
            parts.append(_("دقيقة واحدة"))
        elif minutes == 2:
            parts.append(_("دقيقتان"))
        elif 3 <= minutes <= 10:
            parts.append(_("{} دقائق").format(minutes))
        else:
            parts.append(_("{} دقيقة").format(minutes))

    if seconds > 0 or (not parts and total_seconds == 0):
        if seconds == 1:
            parts.append(_("ثانية واحدة"))
        elif seconds == 2:
            parts.append(_("ثانيتين"))
        elif 3 <= seconds <= 10:
            parts.append(_("{} ثواني").format(seconds))
        else:
            parts.append(_("{} ثانية").format(seconds))

    if not parts:
        return _("0 ثانية")

    return _(" و").join(parts)


def format_duration(duration):
    if duration is None:
        return _("مباشر")
    if isinstance(duration, str):
        seconds = time_to_seconds(duration)
    else:
        seconds = duration
    if seconds is None:
        return _("غير معروف")
    return _("المدة: {}").format(time_formatting(seconds))


def time_to_seconds(time_str):
    if not isinstance(time_str, str):
        return None
    parts = time_str.split(":")
    total_seconds = 0
    try:
        if len(parts) == 3:  # HH:MM:SS
            total_seconds = int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
        elif len(parts) == 2:  # MM:SS
            total_seconds = int(parts[0]) * 60 + int(parts[1])
        elif len(parts) == 1:  # SS
            total_seconds = int(parts[0])
        else:
            return None
    except ValueError:
        return None
    return total_seconds


def sanitize_filename(filename):
    if not filename:
        return "unnamed"
    return re.sub(r'[<>:"/\\|?*]', "_", filename).strip()

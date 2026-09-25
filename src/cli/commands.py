"""CLI command handlers.

Every handler has the signature ``cmd_x(args, emitter)`` and returns a process
exit code (0 = success). Handlers reuse the desktop app's backend modules and
never construct a wx application; features that would otherwise pop a wx dialog
when a dependency is missing are guarded up front with ``require_deno`` /
``require_cookies`` so the CLI stays fully headless.
"""

import os
import sys

import utils
from cli import deps
from cli.runtime import require_cookies, require_deno, run_async
from database import Favorite, SearchHistory, WatchHistory
from language_handler import _
from settings_handler import config_get, config_set, defaults, save_settings
from youtube_browser.search_handler import (
    ChannelTabResult,
    PlaylistResult,
    Search,
    fetch_search_suggestions,
)


def _serialize_results(result):
    """Turn a Search/Playlist/Channel result object into a list of dicts."""
    items = []
    count = getattr(result, "count", 0) or 0
    for index in range(count):
        item = {
            "index": index + 1,
            "type": result.get_type(index),
            "title": result.get_title(index),
            "url": result.get_url(index),
        }
        try:
            channel = result.get_channel(index)
            if isinstance(channel, dict):
                item["channel"] = channel.get("name")
                item["channel_url"] = channel.get("url")
        except Exception:
            pass
        try:
            views = result.get_views(index)
            if views is not None:
                item["views"] = views
        except Exception:
            pass
        items.append(item)
    return items


def _display_lines(result):
    """Numbered, screen-reader-friendly text lines for a result object."""
    if hasattr(result, "get_titles"):
        titles = result.get_titles()
    elif hasattr(result, "get_display_titles"):
        titles = result.get_display_titles()
    else:
        titles = []
    return [f"{index + 1}. {title}" for index, title in enumerate(titles)]


def cmd_search(args, emitter):
    filter_map = {"video": 0, "playlist": 4, "channel": 5}
    search = Search(args.query, filter=filter_map.get(args.type, 0))
    run_async(search.init_async())
    for _page in range(max(0, args.pages - 1)):
        if not run_async(search.load_more()):
            break
    if not getattr(search, "count", 0):
        emitter.result([], _("لا توجد نتائج."))
        return 0
    emitter.result(_serialize_results(search), _display_lines(search))
    return 0


def cmd_suggest(args, emitter):
    suggestions = fetch_search_suggestions(args.query)
    emitter.result(suggestions, suggestions)
    return 0


def cmd_info(args, emitter):
    info = utils.get_media_info(args.url)
    if not info:
        emitter.error(_("تعذر جلب معلومات المرئي."), code="info_failed")
        return 1
    data = {
        "id": info.get("id"),
        "title": info.get("title"),
        "channel": info.get("channel") or info.get("uploader"),
        "channel_url": info.get("channel_url") or info.get("uploader_url"),
        "duration": info.get("duration"),
        "view_count": info.get("view_count"),
        "like_count": info.get("like_count"),
        "upload_date": info.get("upload_date"),
        "webpage_url": info.get("webpage_url") or info.get("original_url"),
        "is_live": bool(info.get("is_live")),
        "description": info.get("description"),
    }
    lines = [
        _("العنوان: {value}").format(value=data["title"] or "-"),
        _("القناة: {value}").format(value=data["channel"] or "-"),
        _("المدة (ثانية): {value}").format(value=data["duration"] or "-"),
        _("عدد المشاهدات: {value}").format(value=data["view_count"] or "-"),
        _("عدد الإعجابات: {value}").format(value=data["like_count"] or "-"),
        _("تاريخ الرفع: {value}").format(value=data["upload_date"] or "-"),
        _("الرابط: {value}").format(value=data["webpage_url"] or "-"),
    ]
    emitter.result(data, lines)
    return 0


def cmd_formats(args, emitter):
    info = utils.get_media_info(args.url)
    if not info:
        emitter.error(_("تعذر جلب معلومات المرئي."), code="info_failed")
        return 1
    formats = []
    lines = []
    for fmt in info.get("formats", []) or []:
        entry = {
            "format_id": fmt.get("format_id"),
            "ext": fmt.get("ext"),
            "height": fmt.get("height"),
            "abr": fmt.get("abr"),
            "vcodec": fmt.get("vcodec"),
            "acodec": fmt.get("acodec"),
            "filesize": fmt.get("filesize") or fmt.get("filesize_approx"),
        }
        formats.append(entry)
        resolution = f"{entry['height']}p" if entry["height"] else _("صوت فقط")
        lines.append(
            _("{fid}: {res}, صيغة {ext}").format(
                fid=entry["format_id"], res=resolution, ext=entry["ext"] or "-"
            )
        )
    emitter.result(formats, lines)
    return 0


def cmd_qualities(args, emitter):
    qualities = utils.get_available_qualities(args.url, audio_mode=args.audio)
    lines = [str(quality) for quality in qualities]
    emitter.result(qualities, lines)
    return 0


def cmd_stream_url(args, emitter):
    if args.quality:
        stream = utils.get_specific_quality_stream(
            args.url, args.quality, audio_mode=args.audio
        )
    else:
        stream = utils.get_playable_stream(args.url, audio_mode=args.audio)
    if not stream:
        emitter.error(_("تعذر الحصول على رابط البث."), code="stream_failed")
        return 1
    data = {
        "title": stream.title,
        "url": stream.url,
        "audio_url": stream.audio_url,
        "quality": stream.quality,
        "headers": stream.headers,
        "webpage_url": stream.webpage_url,
        "channel_name": stream.channel_name,
    }
    lines = [
        _("العنوان: {value}").format(value=stream.title or "-"),
        _("رابط الفيديو: {value}").format(value=stream.url or "-"),
    ]
    if stream.audio_url:
        lines.append(_("رابط الصوت: {value}").format(value=stream.audio_url))
    emitter.result(data, lines)
    return 0


def _make_progress_printer():
    def _progress(update):
        if update.get("status") == "downloading":
            line = _("التنزيل: {percent}٪ — السرعة {speed} — المتبقي {eta}").format(
                percent=update.get("value", 0),
                speed=update.get("speed") or "?",
                eta=update.get("eta") or "?",
            )
            print("\r" + line, end="", file=sys.stderr, flush=True)
        elif update.get("status") == "finished":
            print(file=sys.stderr)

    return _progress


def cmd_download(args, emitter):
    from download_handler.downloader import (
        Downloader,
        diagnose_download_error,
        get_video_download_format,
    )

    fmt = (args.format or "mp4").lower()
    audio_format = video_format = None
    convert = False
    if fmt == "mkv":
        video_format = "mkv"
    elif fmt == "m4a":
        audio_format = "m4a"
    elif fmt == "mp3":
        audio_format, convert = "mp3", True
    elif fmt == "wav":
        audio_format = "wav"
    elif fmt == "flac":
        audio_format = "flac"
    else:
        video_format = "mp4"

    path = args.output or config_get("path") or "."
    if video_format and args.quality:
        downloading_format = get_video_download_format(
            args.quality, container=video_format
        )
    else:
        downloading_format = "best"

    downloader = Downloader(
        args.url,
        path,
        downloading_format,
        monitor=None,
        status_label=None,
        convert=convert,
        folder=args.folder,
        audio_format=audio_format,
        video_format=video_format,
        progress_callback=None if emitter.json_mode else _make_progress_printer(),
    )
    result = downloader.download_with_cookie_fallback()
    if result == 0:
        emitter.message(
            _("اكتمل التنزيل: {file}").format(file=downloader.last_file or path),
            data={"file": downloader.last_file, "path": path},
        )
        return 0
    emitter.error(diagnose_download_error(result), code="download_failed")
    return 1


def cmd_subtitles_list(args, emitter):
    tracks = utils.get_available_subtitles(args.url)
    lines = [
        _("{code}: {label} ({source})").format(
            code=track.get("code"),
            label=track.get("label"),
            source=track.get("source"),
        )
        for track in tracks
    ]
    emitter.result(tracks, lines or [_("لا توجد ترجمات متاحة.")])
    return 0


def _format_srt_timestamp(milliseconds):
    milliseconds = max(0, int(milliseconds))
    hours, milliseconds = divmod(milliseconds, 3600000)
    minutes, milliseconds = divmod(milliseconds, 60000)
    seconds, milliseconds = divmod(milliseconds, 1000)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{milliseconds:03d}"


def _cues_to_srt(cues):
    blocks = []
    for number, cue in enumerate(cues, start=1):
        blocks.append(
            "{number}\n{start} --> {end}\n{text}\n".format(
                number=number,
                start=_format_srt_timestamp(cue["start_ms"]),
                end=_format_srt_timestamp(cue["end_ms"]),
                text=cue["text"],
            )
        )
    return "\n".join(blocks)


def cmd_subtitles_get(args, emitter):
    cues = utils.get_subtitle_cues(args.url, args.lang)
    if not cues:
        emitter.error(_("لا توجد ترجمة باللغة المطلوبة."), code="subtitle_missing")
        return 1
    srt = _cues_to_srt(cues)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as handle:
            handle.write(srt)
        emitter.message(
            _("تم حفظ الترجمة في: {path}").format(path=args.output),
            data={"path": args.output, "cues": len(cues)},
        )
        return 0
    emitter.result(cues, [srt])
    return 0


def cmd_comments(args, emitter):
    sort_map = {"top": "TOP_COMMENTS", "new": "NEWEST_FIRST"}
    data = utils.get_video_comments(
        args.url,
        continuation=args.continuation,
        sort_by=sort_map.get(args.sort, "TOP_COMMENTS"),
    )
    comments = data.get("comments", [])
    lines = [
        _("{author}: {content}").format(
            author=comment.get("author"), content=comment.get("content")
        )
        for comment in comments
    ]
    if data.get("continuation"):
        lines.append(_("رمز المتابعة: {token}").format(token=data["continuation"]))
    emitter.result(data, lines or [_("لا توجد تعليقات.")])
    return 0


def cmd_replies(args, emitter):
    data = utils.get_comment_replies(
        args.token,
        continuation=args.continuation,
        video_url=args.url,
        parent_id=args.parent,
    )
    comments = data.get("comments", [])
    lines = [
        _("{author}: {content}").format(
            author=comment.get("author"), content=comment.get("content")
        )
        for comment in comments
    ]
    emitter.result(data, lines or [_("لا توجد ردود.")])
    return 0


def _emit_action_result(emitter, result, success_message):
    """Emit the outcome of a mutating deno action returning ``{success,error}``."""
    if isinstance(result, dict) and result.get("success"):
        emitter.message(success_message)
        return 0
    error = result.get("error") if isinstance(result, dict) else _("فشلت العملية.")
    emitter.error(error or _("فشلت العملية."), code="action_failed")
    return 1


def cmd_post_comment(args, emitter):
    if not require_deno(emitter) or not require_cookies(emitter):
        return 1
    result = utils.post_video_comment(args.url, args.text)
    return _emit_action_result(emitter, result, _("تم نشر التعليق."))


def cmd_like_comment(args, emitter):
    if not require_deno(emitter) or not require_cookies(emitter):
        return 1
    result = utils.like_comment(args.url, args.comment_id, action=args.action)
    return _emit_action_result(emitter, result, _("تم تحديث تقييم التعليق."))


def cmd_reply_comment(args, emitter):
    if not require_deno(emitter) or not require_cookies(emitter):
        return 1
    result = utils.reply_to_comment(args.url, args.comment_id, args.text)
    return _emit_action_result(emitter, result, _("تم نشر الرد."))


def cmd_chapters(args, emitter):
    chapters = utils.get_video_chapters(args.url)
    lines = [
        _("{time}ms: {title}").format(
            time=chapter.get("time_ms"), title=chapter.get("title")
        )
        for chapter in chapters
    ]
    emitter.result(chapters, lines or [_("لا توجد فصول.")])
    return 0


def cmd_likes(args, emitter):
    info = utils.get_video_like_info(args.url)
    lines = [
        _("عدد الإعجابات: {value}").format(value=info.get("likes")),
        _("أعجبني: {value}").format(
            value=_("نعم") if info.get("is_liked") else _("لا")
        ),
    ]
    emitter.result(info, lines)
    return 0


def cmd_like(args, emitter):
    if not require_deno(emitter) or not require_cookies(emitter):
        return 1
    result = utils.like_video(args.url, action=args.action)
    return _emit_action_result(emitter, result, _("تم تحديث تقييم المرئي."))


def cmd_channel(args, emitter):
    result = ChannelTabResult(args.url, tab=args.tab)
    for _page in range(max(0, args.pages - 1)):
        if not result.load_more():
            break
    emitter.result(
        _serialize_results(result),
        _display_lines(result) or [_("لا توجد عناصر.")],
    )
    return 0


def cmd_playlist(args, emitter):
    playlist = PlaylistResult(args.url)
    run_async(playlist.init_async())
    emitter.result(
        _serialize_results(playlist),
        _display_lines(playlist) or [_("قائمة التشغيل فارغة.")],
    )
    return 0


def _serialize_feed(videos):
    items = []
    lines = []
    for video in videos or []:
        if not isinstance(video, dict):
            continue
        channel = video.get("channel")
        channel_name = (
            channel.get("name") if isinstance(channel, dict) else video.get("author")
        )
        item = {
            "title": video.get("title"),
            "url": video.get("url") or video.get("link"),
            "channel": channel_name,
            "duration": video.get("duration"),
            "views": video.get("views") or video.get("view_count"),
        }
        items.append(item)
        lines.append(
            _("{title} — {channel}").format(
                title=item["title"] or "-", channel=channel_name or "-"
            )
        )
    return items, lines


def cmd_home(args, emitter):
    if not require_deno(emitter) or not require_cookies(emitter):
        return 1
    result = utils.get_home_feed(continuation=args.continuation)
    if result.get("error"):
        emitter.error(result["error"], code="home_failed")
        return 1
    items, lines = _serialize_feed(result.get("videos"))
    data = {"videos": items, "continuation": result.get("continuation")}
    if result.get("continuation"):
        lines.append(_("رمز المتابعة: {token}").format(token=result["continuation"]))
    emitter.result(data, lines or [_("الخلاصة فارغة.")])
    return 0


def cmd_shorts(args, emitter):
    if not require_deno(emitter) or not require_cookies(emitter):
        return 1
    shorts = utils.get_shorts_feed(seed_video_id=args.seed)
    items, lines = _serialize_feed(shorts)
    emitter.result(items, lines or [_("لا توجد مقاطع قصيرة.")])
    return 0


def cmd_watch_history(args, emitter):
    if args.online:
        if not require_deno(emitter) or not require_cookies(emitter):
            return 1
        result = utils.get_watch_history(continuation=args.continuation)
        items, lines = _serialize_feed(result.get("videos"))
        data = {"videos": items, "continuation": result.get("continuation")}
        emitter.result(data, lines or [_("السجل فارغ.")])
        return 0
    rows = WatchHistory.get_page(limit=args.limit, offset=args.offset) or []
    lines = [
        _("{title} — {channel}").format(
            title=row.get("title") or "-", channel=row.get("channel_name") or "-"
        )
        for row in rows
    ]
    emitter.result(rows, lines or [_("السجل فارغ.")])
    return 0


def cmd_favorites_list(args, emitter):
    rows = Favorite().get_all() or []
    lines = [
        _("{title} — {url}").format(title=row.get("title") or "-", url=row.get("url"))
        for row in rows
    ]
    emitter.result(rows, lines or [_("لا توجد مفضلات.")])
    return 0


def cmd_favorites_add(args, emitter):
    data = {
        "title": args.title or args.url,
        "display_title": args.title or args.url,
        "url": args.url,
        "live": 1 if args.live else 0,
        "channel_name": args.channel or "",
        "channel_url": args.channel_url or "",
    }
    Favorite().add_favorite(data)
    emitter.message(_("تمت الإضافة إلى المفضلة."), data={"url": args.url})
    return 0


def cmd_favorites_remove(args, emitter):
    Favorite().remove_favorite(args.url)
    emitter.message(_("تمت الإزالة من المفضلة."), data={"url": args.url})
    return 0


def cmd_search_history_list(args, emitter):
    queries = SearchHistory.get_recent() or []
    emitter.result(queries, queries or [_("لا يوجد سجل بحث.")])
    return 0


def cmd_search_history_clear(args, emitter):
    SearchHistory.clear()
    emitter.message(_("تم مسح سجل البحث."))
    return 0


def cmd_config_get(args, emitter):
    value = config_get(args.key)
    emitter.result(
        {"key": args.key, "value": value},
        _("{key} = {value}").format(key=args.key, value=value),
    )
    return 0


def cmd_config_set(args, emitter):
    if args.key not in defaults:
        emitter.error(
            _("مفتاح إعداد غير معروف: {key}").format(key=args.key),
            code="unknown_key",
        )
        return 1
    config_set(args.key, args.value)
    save_settings()
    emitter.message(
        _("تم ضبط {key} = {value}").format(key=args.key, value=args.value),
        data={"key": args.key, "value": args.value},
    )
    return 0


def cmd_config_list(args, emitter):
    data = {key: config_get(key) for key in defaults}
    lines = [
        _("{key} = {value}").format(key=key, value=value) for key, value in data.items()
    ]
    emitter.result(data, lines)
    return 0


def cmd_config_path(args, emitter):
    from paths import settings_path

    settings_file = os.path.join(settings_path, "settings.ini")
    emitter.result({"path": settings_file}, settings_file)
    return 0


def cmd_cookies_status(args, emitter):
    cookies_path = config_get("cookiespath")
    exists = bool(cookies_path and os.path.exists(cookies_path))
    data = {
        "path": cookies_path or None,
        "configured": bool(cookies_path),
        "exists": exists,
    }
    if not cookies_path:
        line = _("لم يتم ضبط ملف كوكيز.")
    elif exists:
        line = _("ملف الكوكيز مضبوط: {path}").format(path=cookies_path)
    else:
        line = _("ملف الكوكيز مضبوط لكنه غير موجود: {path}").format(path=cookies_path)
    emitter.result(data, line)
    return 0


def cmd_cookies_set(args, emitter):
    path = os.path.abspath(args.path)
    if not os.path.exists(path):
        emitter.error(
            _("ملف الكوكيز غير موجود: {path}").format(path=path),
            code="file_missing",
        )
        return 1
    config_set("cookiespath", path)
    save_settings()
    emitter.message(_("تم ضبط ملف الكوكيز."), data={"path": path})
    return 0


def cmd_cookies_clear(args, emitter):
    config_set("cookiespath", "")
    save_settings()
    emitter.message(_("تم مسح ملف الكوكيز."))
    return 0


def cmd_deps_versions(args, emitter):
    data = deps.versions()
    labels = {
        "yt_dlp": _("واي تي دي إل بي"),
        "deno": _("دينو"),
        "youtubei": _("مكتبة YouTube.js"),
        "pot_provider": _("مولد رموز POT"),
    }
    lines = [
        _("{name}: {version}").format(
            name=labels.get(key, key), version=value or _("غير مثبت")
        )
        for key, value in data.items()
    ]
    emitter.result(data, lines)
    return 0


def cmd_deps_update(args, emitter):
    targets = []
    if args.all:
        targets = ["ytdlp", "deno", "youtubei", "pot"]
    else:
        if args.ytdlp:
            targets.append("ytdlp")
        if args.deno:
            targets.append("deno")
        if args.youtubei:
            targets.append("youtubei")
        if args.pot:
            targets.append("pot")
    if not targets:
        emitter.error(
            _("حدد مكوناً للتحديث: --ytdlp أو --deno أو --youtubei أو --pot أو --all"),
            code="no_target",
        )
        return 1

    runners = {
        "ytdlp": deps.update_ytdlp,
        "deno": deps.update_deno,
        "youtubei": deps.update_youtubei,
        "pot": deps.update_pot,
    }
    results = {}
    lines = []
    exit_code = 0
    for target in targets:
        ok, message = runners[target]()
        results[target] = {"ok": ok, "message": message}
        lines.append(message)
        if not ok:
            exit_code = 1
    emitter.result(results, lines)
    return exit_code

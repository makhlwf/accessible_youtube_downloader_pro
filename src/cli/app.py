"""Argument parsing and command dispatch for the HexPlayer CLI.

Builds an argparse tree covering every exposed feature, then routes the parsed
namespace to the matching handler in :mod:`cli.commands`. Two global options
apply to all commands: ``--json`` (machine-readable output) and ``--lang``
(per-invocation interface language override).
"""

import argparse

from cli import commands
from cli.runtime import Emitter, bootstrap


def _prescan_lang(argv):
    """Find ``--lang`` before argparse runs so help text is translated."""
    for index, token in enumerate(argv):
        if token == "--lang" and index + 1 < len(argv):
            return argv[index + 1]
        if token.startswith("--lang="):
            return token.split("=", 1)[1]
    return None


def main(argv=None):
    import sys

    if argv is None:
        argv = sys.argv[1:]

    bootstrap(_prescan_lang(argv))
    parser = build_parser()
    args = parser.parse_args(argv)

    from language_handler import _

    emitter = Emitter(json_mode=getattr(args, "json", False))
    handler = getattr(args, "func", None)
    if handler is None:
        parser.print_help()
        return 1
    try:
        return handler(args, emitter) or 0
    except KeyboardInterrupt:
        emitter.error(_("تم الإلغاء."), code="cancelled")
        return 130
    except Exception as error:
        emitter.error(str(error), code="unexpected")
        return 1


def build_parser():
    from language_handler import _

    parser = argparse.ArgumentParser(
        prog="hexplayer",
        description=_("واجهة سطر الأوامر لتطبيق HexPlayer لتنزيل وتصفح يوتيوب."),
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help=_("إخراج النتائج بصيغة JSON."),
    )
    parser.add_argument(
        "--lang",
        help=_("لغة الواجهة لهذا الأمر (مثل ar أو en)."),
    )
    sub = parser.add_subparsers(dest="command")

    search = sub.add_parser("search", help=_("البحث في يوتيوب."))
    search.add_argument("query", help=_("عبارة البحث."))
    search.add_argument(
        "--type",
        choices=["video", "playlist", "channel"],
        default="video",
        help=_("نوع النتائج."),
    )
    search.add_argument("--pages", type=int, default=1, help=_("عدد صفحات النتائج."))
    search.set_defaults(func=commands.cmd_search)

    suggest = sub.add_parser("suggest", help=_("اقتراحات البحث."))
    suggest.add_argument("query", help=_("عبارة البحث."))
    suggest.set_defaults(func=commands.cmd_suggest)

    info = sub.add_parser("info", help=_("عرض معلومات المرئي."))
    info.add_argument("url", help=_("رابط المرئي."))
    info.set_defaults(func=commands.cmd_info)

    formats = sub.add_parser("formats", help=_("عرض الصيغ المتاحة."))
    formats.add_argument("url", help=_("رابط المرئي."))
    formats.set_defaults(func=commands.cmd_formats)

    qualities = sub.add_parser("qualities", help=_("عرض الجودات المتاحة."))
    qualities.add_argument("url", help=_("رابط المرئي."))
    qualities.add_argument(
        "--audio", action="store_true", help=_("جودات الصوت بدل الفيديو.")
    )
    qualities.set_defaults(func=commands.cmd_qualities)

    stream = sub.add_parser("stream-url", help=_("الحصول على رابط البث المباشر."))
    stream.add_argument("url", help=_("رابط المرئي."))
    stream.add_argument("--audio", action="store_true", help=_("بث صوتي فقط."))
    stream.add_argument(
        "--quality", type=int, help=_("ارتفاع الفيديو المطلوب (مثل 720).")
    )
    stream.set_defaults(func=commands.cmd_stream_url)

    download = sub.add_parser("download", help=_("تنزيل مرئي أو صوت."))
    download.add_argument("url", help=_("رابط المرئي أو قائمة التشغيل."))
    download.add_argument(
        "--format",
        choices=["mp4", "mkv", "m4a", "mp3", "wav", "flac"],
        default="mp4",
        help=_("صيغة الملف الناتج."),
    )
    download.add_argument(
        "--quality", type=int, help=_("أقصى ارتفاع للفيديو (مثل 1080).")
    )
    download.add_argument("--output", help=_("مجلد الحفظ."))
    download.add_argument(
        "--folder",
        action="store_true",
        help=_("تنزيل قائمة تشغيل كاملة داخل مجلد."),
    )
    download.set_defaults(func=commands.cmd_download)

    subtitles = sub.add_parser("subtitles", help=_("إدارة الترجمات."))
    subtitles_sub = subtitles.add_subparsers(dest="subtitles_command")
    subtitles_list = subtitles_sub.add_parser("list", help=_("عرض الترجمات المتاحة."))
    subtitles_list.add_argument("url", help=_("رابط المرئي."))
    subtitles_list.set_defaults(func=commands.cmd_subtitles_list)
    subtitles_get = subtitles_sub.add_parser("get", help=_("تنزيل ترجمة."))
    subtitles_get.add_argument("url", help=_("رابط المرئي."))
    subtitles_get.add_argument("--lang", required=True, help=_("رمز لغة الترجمة."))
    subtitles_get.add_argument("--output", help=_("مسار حفظ ملف srt."))
    subtitles_get.set_defaults(func=commands.cmd_subtitles_get)

    comments = sub.add_parser("comments", help=_("عرض تعليقات المرئي."))
    comments.add_argument("url", help=_("رابط المرئي."))
    comments.add_argument("--continuation", help=_("رمز المتابعة للصفحة التالية."))
    comments.add_argument(
        "--sort", choices=["top", "new"], default="top", help=_("ترتيب التعليقات.")
    )
    comments.set_defaults(func=commands.cmd_comments)

    replies = sub.add_parser("replies", help=_("عرض ردود تعليق."))
    replies.add_argument("--token", required=True, help=_("رمز الردود."))
    replies.add_argument("--continuation", help=_("رمز المتابعة."))
    replies.add_argument("--url", help=_("رابط المرئي (للاحتياط)."))
    replies.add_argument("--parent", help=_("معرف التعليق الأصلي (للاحتياط)."))
    replies.set_defaults(func=commands.cmd_replies)

    post_comment = sub.add_parser("post-comment", help=_("نشر تعليق."))
    post_comment.add_argument("url", help=_("رابط المرئي."))
    post_comment.add_argument("text", help=_("نص التعليق."))
    post_comment.set_defaults(func=commands.cmd_post_comment)

    like_comment = sub.add_parser("like-comment", help=_("التفاعل مع تعليق."))
    like_comment.add_argument("url", help=_("رابط المرئي."))
    like_comment.add_argument("comment_id", help=_("معرف التعليق."))
    like_comment.add_argument(
        "--action",
        choices=["like", "dislike", "remove_like"],
        default="like",
        help=_("نوع التفاعل."),
    )
    like_comment.set_defaults(func=commands.cmd_like_comment)

    reply_comment = sub.add_parser("reply-comment", help=_("الرد على تعليق."))
    reply_comment.add_argument("url", help=_("رابط المرئي."))
    reply_comment.add_argument("comment_id", help=_("معرف التعليق."))
    reply_comment.add_argument("text", help=_("نص الرد."))
    reply_comment.set_defaults(func=commands.cmd_reply_comment)

    chapters = sub.add_parser("chapters", help=_("عرض فصول المرئي."))
    chapters.add_argument("url", help=_("رابط المرئي."))
    chapters.set_defaults(func=commands.cmd_chapters)

    likes = sub.add_parser("likes", help=_("عرض عدد الإعجابات وحالة التقييم."))
    likes.add_argument("url", help=_("رابط المرئي."))
    likes.set_defaults(func=commands.cmd_likes)

    like = sub.add_parser("like", help=_("الإعجاب بمرئي أو إلغاؤه."))
    like.add_argument("url", help=_("رابط المرئي."))
    like.add_argument(
        "--action",
        choices=["like", "dislike", "remove_like"],
        default="like",
        help=_("نوع التفاعل."),
    )
    like.set_defaults(func=commands.cmd_like)

    channel = sub.add_parser("channel", help=_("تصفح قناة."))
    channel.add_argument("url", help=_("رابط القناة."))
    channel.add_argument(
        "--tab",
        choices=[
            "home",
            "videos",
            "shorts",
            "live",
            "playlists",
            "community",
            "channels",
            "about",
        ],
        default="videos",
        help=_("تبويب القناة."),
    )
    channel.add_argument("--pages", type=int, default=1, help=_("عدد الصفحات."))
    channel.set_defaults(func=commands.cmd_channel)

    playlist = sub.add_parser("playlist", help=_("عرض قائمة تشغيل."))
    playlist.add_argument("url", help=_("رابط قائمة التشغيل."))
    playlist.set_defaults(func=commands.cmd_playlist)

    home = sub.add_parser("home", help=_("عرض الخلاصة الرئيسية."))
    home.add_argument("--continuation", help=_("رمز المتابعة."))
    home.set_defaults(func=commands.cmd_home)

    shorts = sub.add_parser("shorts", help=_("عرض المقاطع القصيرة."))
    shorts.add_argument("--seed", help=_("معرف مرئي للاقتراح منه."))
    shorts.set_defaults(func=commands.cmd_shorts)

    history = sub.add_parser("watch-history", help=_("سجل المشاهدة."))
    history.add_argument(
        "--online", action="store_true", help=_("سجل يوتيوب أونلاين بدل المحلي.")
    )
    history.add_argument("--limit", type=int, default=50, help=_("عدد العناصر."))
    history.add_argument("--offset", type=int, default=0, help=_("الإزاحة."))
    history.add_argument("--continuation", help=_("رمز المتابعة (أونلاين)."))
    history.set_defaults(func=commands.cmd_watch_history)

    favorites = sub.add_parser("favorites", help=_("إدارة المفضلة."))
    favorites_sub = favorites.add_subparsers(dest="favorites_command")
    favorites_list = favorites_sub.add_parser("list", help=_("عرض المفضلة."))
    favorites_list.set_defaults(func=commands.cmd_favorites_list)
    favorites_add = favorites_sub.add_parser("add", help=_("إضافة إلى المفضلة."))
    favorites_add.add_argument("url", help=_("رابط المرئي."))
    favorites_add.add_argument("--title", help=_("عنوان المرئي."))
    favorites_add.add_argument("--channel", help=_("اسم القناة."))
    favorites_add.add_argument(
        "--channel-url", dest="channel_url", help=_("رابط القناة.")
    )
    favorites_add.add_argument("--live", action="store_true", help=_("بث مباشر."))
    favorites_add.set_defaults(func=commands.cmd_favorites_add)
    favorites_remove = favorites_sub.add_parser("remove", help=_("إزالة من المفضلة."))
    favorites_remove.add_argument("url", help=_("رابط المرئي."))
    favorites_remove.set_defaults(func=commands.cmd_favorites_remove)

    search_history = sub.add_parser("search-history", help=_("سجل البحث."))
    search_history_sub = search_history.add_subparsers(dest="search_history_command")
    search_history_list = search_history_sub.add_parser(
        "list", help=_("عرض سجل البحث.")
    )
    search_history_list.set_defaults(func=commands.cmd_search_history_list)
    search_history_clear = search_history_sub.add_parser(
        "clear", help=_("مسح سجل البحث.")
    )
    search_history_clear.set_defaults(func=commands.cmd_search_history_clear)

    config = sub.add_parser("config", help=_("إدارة الإعدادات."))
    config_sub = config.add_subparsers(dest="config_command")
    config_get_parser = config_sub.add_parser("get", help=_("قراءة إعداد."))
    config_get_parser.add_argument("key", help=_("اسم الإعداد."))
    config_get_parser.set_defaults(func=commands.cmd_config_get)
    config_set_parser = config_sub.add_parser("set", help=_("ضبط إعداد."))
    config_set_parser.add_argument("key", help=_("اسم الإعداد."))
    config_set_parser.add_argument("value", help=_("القيمة الجديدة."))
    config_set_parser.set_defaults(func=commands.cmd_config_set)
    config_list_parser = config_sub.add_parser("list", help=_("عرض كل الإعدادات."))
    config_list_parser.set_defaults(func=commands.cmd_config_list)
    config_path_parser = config_sub.add_parser("path", help=_("مسار ملف الإعدادات."))
    config_path_parser.set_defaults(func=commands.cmd_config_path)

    cookies = sub.add_parser("cookies", help=_("إدارة ملف الكوكيز."))
    cookies_sub = cookies.add_subparsers(dest="cookies_command")
    cookies_status = cookies_sub.add_parser("status", help=_("حالة ملف الكوكيز."))
    cookies_status.set_defaults(func=commands.cmd_cookies_status)
    cookies_set = cookies_sub.add_parser("set", help=_("ضبط ملف الكوكيز."))
    cookies_set.add_argument("path", help=_("مسار ملف الكوكيز."))
    cookies_set.set_defaults(func=commands.cmd_cookies_set)
    cookies_clear = cookies_sub.add_parser("clear", help=_("مسح ملف الكوكيز."))
    cookies_clear.set_defaults(func=commands.cmd_cookies_clear)

    deps = sub.add_parser("deps", help=_("إدارة المكونات (تحديث وإصدارات)."))
    deps_sub = deps.add_subparsers(dest="deps_command")
    deps_versions = deps_sub.add_parser("versions", help=_("عرض إصدارات المكونات."))
    deps_versions.set_defaults(func=commands.cmd_deps_versions)
    deps_update = deps_sub.add_parser("update", help=_("تحديث المكونات."))
    deps_update.add_argument(
        "--ytdlp", action="store_true", help=_("تحديث واي تي دي إل بي.")
    )
    deps_update.add_argument("--deno", action="store_true", help=_("تحديث دينو."))
    deps_update.add_argument(
        "--youtubei", action="store_true", help=_("تحديث مكتبة YouTube.js.")
    )
    deps_update.add_argument(
        "--pot", action="store_true", help=_("تحديث مولد رموز POT.")
    )
    deps_update.add_argument("--all", action="store_true", help=_("تحديث كل المكونات."))
    deps_update.set_defaults(func=commands.cmd_deps_update)

    return parser

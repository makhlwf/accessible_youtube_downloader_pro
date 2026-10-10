"""View controllers for the YouTube Music panel.

A *view* knows how to fetch a list of normalized rows and how to react to Enter
and the context menu on a row. The panel owns one shared ``wx.ListBox`` and asks
the active view to render into it, so views are plain controllers (no widgets of
their own) — this is what lets navigation push/pop cheaply.

``CollectionView`` is the reusable workhorse: give it a title and a
zero-argument fetch function returning rows, and it handles loading status,
rendering, playback, radio, download, and drill-down for albums/artists/
playlists uniformly.
"""

import logging

from language_handler import _

from . import adapters

logger = logging.getLogger(__name__)

STATUS_OK = "ok"
STATUS_EMPTY = "empty"
STATUS_AUTH = "auth"
STATUS_ERROR = "error"


class BaseView:
    def __init__(self, panel, title=""):
        self.panel = panel
        self.title = title
        self.rows = []
        self.result = None
        self.status = STATUS_OK
        # Write-context: set by views that support in-place removal.
        self.owner_playlist_id = (
            None  # playlist_id if this view is an editable playlist
        )
        self.section = None  # e.g. "history" to enable "remove from history"

    def fetch(self):
        """Return a list of normalized rows. Runs on a worker thread. Override."""
        return []

    def build_result(self):
        self.result = adapters.YTMusicResult(self.rows)
        scraper = getattr(self.panel, "scraper", None)
        if scraper is not None:
            self.result.scraper = scraper
        return self.result

    def display_lines(self):
        if self.status == STATUS_AUTH:
            return [_("يلزم تسجيل الدخول. افتح الإعدادات لاستيراد كوكيز المتصفح.")]
        if self.status == STATUS_ERROR:
            return [_("حدث خطأ. اضغط إدخال لإعادة المحاولة.")]
        if self.status == STATUS_EMPTY or not self.rows:
            return [_("لا توجد عناصر.")]
        return [adapters.display_title(row) for row in self.rows]

    def is_actionable(self):
        return self.status == STATUS_OK and bool(self.rows)

    def on_activate(self, index, audio_mode=True):
        if not self.is_actionable():
            if self.status == STATUS_ERROR:
                self.panel.reload_current()
            elif self.status == STATUS_AUTH:
                self.panel.prompt_sign_in()
            return
        if not (0 <= index < len(self.rows)):
            return
        row = self.rows[index]
        if row.get("videoId"):
            self.build_result()
            self.panel.play(self.result, index, audio_mode=audio_mode)
            return
        row_type = row.get("type")
        if row_type == "album":
            self.panel.open_album(row)
        elif row_type == "artist":
            self.panel.open_artist(row)
        elif row_type == "playlist":
            self.panel.open_playlist(row)
        elif row_type == "mood":
            self.panel.open_mood(row)

    def context_actions(self, index):
        if not self.is_actionable() or not (0 <= index < len(self.rows)):
            return []
        row = self.rows[index]
        actions = []
        if row.get("videoId"):
            self.build_result()
            actions.append(
                (
                    _("تشغيل"),
                    lambda: self.panel.play(self.result, index, audio_mode=True),
                )
            )
            actions.append(
                (
                    _("تشغيل مع الفيديو"),
                    lambda: self.panel.play(self.result, index, audio_mode=False),
                )
            )
            actions.append(
                (_("بدء الراديو"), lambda: self.panel.start_radio(self.result, index))
            )
            actions.append((_("إعجاب"), lambda: self.panel.like_row(row)))
            if row.get("feedbackTokens"):
                actions.append(
                    (_("إضافة إلى المكتبة"), lambda: self.panel.add_to_library(row))
                )
            actions.append(
                (_("إضافة إلى قائمة تشغيل"), lambda: self.panel.add_to_playlist(row))
            )
            actions.append((_("تنزيل"), lambda: self.panel.download_row(row)))
            if self.section == "history":
                actions.append(
                    (_("إزالة من السجل"), lambda: self.panel.remove_from_history(row))
                )
            if self.owner_playlist_id:
                actions.append(
                    (
                        _("إزالة من قائمة التشغيل"),
                        lambda: self.panel.remove_from_playlist(
                            self.owner_playlist_id, row
                        ),
                    )
                )
        if row.get("type") == "album":
            actions.append((_("فتح الألبوم"), lambda: self.panel.open_album(row)))
        if row.get("type") == "artist":
            actions.append((_("فتح الفنان"), lambda: self.panel.open_artist(row)))
            actions.append((_("اشتراك"), lambda: self.panel.subscribe(row)))
            actions.append((_("إلغاء الاشتراك"), lambda: self.panel.unsubscribe(row)))
        if row.get("type") == "playlist":
            actions.append(
                (_("فتح قائمة التشغيل"), lambda: self.panel.open_playlist(row))
            )
            actions.append(
                (_("حذف قائمة التشغيل"), lambda: self.panel.delete_playlist(row))
            )
            actions.append(
                (
                    _("إعادة تسمية قائمة التشغيل"),
                    lambda: self.panel.rename_playlist(row),
                )
            )
        return actions


class CollectionView(BaseView):
    """A view backed by an arbitrary ``fetch_fn() -> list[row]`` closure."""

    def __init__(self, panel, title, fetch_fn, header_actions=None):
        super().__init__(panel, title)
        self._fetch_fn = fetch_fn
        # header_actions: list of (label, callback) shown via the view menu,
        # e.g. "Play all" / "Start radio" / "Add to library" for an album.
        self.header_actions = header_actions or []

    def fetch(self):
        return self._fetch_fn()

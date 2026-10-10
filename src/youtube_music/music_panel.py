"""The in-place YouTube Music panel for HexPlayer.

A sibling ``wx.Panel`` of the home screen's main panel: opening YouTube Music
hides the main panel and shows this one in the same window (the "flip"); the
"back to YouTube" button reverses it. The panel owns a single ``wx.ListBox`` and
a navigation back-stack of view controllers, reusing the accessible
list + context-menu + Enter/Ctrl+Enter recipe from the YouTube browser.
"""

import logging
import threading

import wx

from gui.custom_controls import CustomLabel
from language_handler import _
from speech_client import speak
from theme_handler import apply_theme

from . import actions, adapters, playback, views
from .base_view import STATUS_AUTH, STATUS_EMPTY, STATUS_ERROR
from .errors import AuthRequiredError
from .navigation import ViewStack
from .service import get_service

logger = logging.getLogger(__name__)

_LIBRARY_SECTIONS = (
    ("playlists", lambda: _("قوائم التشغيل")),
    ("songs", lambda: _("الأغاني")),
    ("albums", lambda: _("الألبومات")),
    ("artists", lambda: _("الفنانون")),
    ("subscriptions", lambda: _("الاشتراكات")),
    ("liked", lambda: _("الأغاني المفضلة")),
    ("history", lambda: _("سجل الاستماع")),
)


class YouTubeMusicPanel(wx.Panel):
    def __init__(self, parent, home_screen):
        super().__init__(parent, name="youtube_music_panel")
        self.home_screen = home_screen
        self.stack = ViewStack()
        self._load_token = 0
        try:
            from youtube_browser.scraper import Scraper

            self.scraper = Scraper()
        except Exception:
            self.scraper = None
        self._build_ui()
        self._bind_events()
        apply_theme(self)

    # PLACEHOLDER_PANEL_BODY

    def _build_ui(self):
        self.title_label = CustomLabel(self, -1, _("يوتيوب ميوزك"))
        self.back_button = wx.Button(self, -1, _("رجوع"), name="controls")
        self.youtube_button = wx.Button(
            self, -1, _("العودة إلى يوتيوب"), name="controls"
        )
        self.search_button = wx.Button(self, -1, _("بحث"), name="controls")
        self.library_button = wx.Button(self, -1, _("المكتبة"), name="controls")
        self.moods_button = wx.Button(self, -1, _("الأجواء والأنواع"), name="controls")
        self.content_list = wx.ListBox(self, -1, name="ytmusic_list")

        header = wx.BoxSizer(wx.HORIZONTAL)
        for button in (
            self.back_button,
            self.youtube_button,
            self.search_button,
            self.library_button,
            self.moods_button,
        ):
            header.Add(button, 0, wx.ALL, 5)

        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(self.title_label, 0, wx.ALL, 10)
        sizer.Add(header, 0, wx.EXPAND | wx.ALL, 5)
        sizer.Add(self.content_list, 1, wx.EXPAND | wx.ALL, 5)
        self.SetSizer(sizer)

    def _bind_events(self):
        self.back_button.Bind(wx.EVT_BUTTON, lambda e: self.go_back())
        self.youtube_button.Bind(
            wx.EVT_BUTTON, lambda e: self.home_screen.close_music()
        )
        self.search_button.Bind(wx.EVT_BUTTON, lambda e: self.open_search_dialog())
        self.library_button.Bind(wx.EVT_BUTTON, lambda e: self.open_library_menu())
        self.moods_button.Bind(wx.EVT_BUTTON, lambda e: self.open_moods())
        self.content_list.Bind(wx.EVT_LISTBOX_DCLICK, self._on_dclick)
        self.content_list.Bind(wx.EVT_CONTEXT_MENU, self._on_context_menu)
        self.content_list.Bind(wx.EVT_CHAR_HOOK, self._on_char_hook)

    # -- navigation ----------------------------------------------------------

    def activate(self):
        """Called by HomeScreen each time the panel is flipped into view."""
        if self.stack.current is None:
            self.show_view(views.HomeView(self), reset=True)
        else:
            self._render_current()
            self.focus_list()

    def show_view(self, view, reset=False):
        if reset:
            self.stack.reset(view)
        else:
            self.stack.push(view)
        self._start_load(view)
        return view

    def go_back(self):
        if not self.stack.can_go_back():
            speak(_("أنت في الصفحة الرئيسية ليوتيوب ميوزك"))
            return
        self.stack.pop()
        self._render_current()
        self.focus_list()
        speak(self.stack.current.title)

    def reload_current(self):
        if self.stack.current is not None:
            self._start_load(self.stack.current)

    # PLACEHOLDER_PANEL_LOAD

    # -- loading & rendering -------------------------------------------------

    def _start_load(self, view):
        self._load_token += 1
        token = self._load_token
        self.title_label.SetLabel(view.title)
        self.content_list.Set([_("جاري التحميل...")])
        speak(_("جاري تحميل {title}").format(title=view.title))
        threading.Thread(
            target=self._load_worker, args=(view, token), daemon=True
        ).start()

    def _load_worker(self, view, token):
        try:
            rows = view.fetch()
            error = None
        except Exception as exc:
            rows, error = None, exc
        wx.CallAfter(self._on_loaded, view, token, rows, error)

    def _on_loaded(self, view, token, rows, error):
        # Ignore results from a superseded load or a view we navigated away from.
        if token != self._load_token or self.stack.current is not view:
            return
        if error is not None:
            view.status = (
                STATUS_AUTH if isinstance(error, AuthRequiredError) else STATUS_ERROR
            )
            view.rows = []
            if not isinstance(error, AuthRequiredError):
                logger.warning("YouTube Music view failed to load", exc_info=error)
        elif not rows:
            view.status = STATUS_EMPTY
            view.rows = []
        else:
            view.status = "ok"
            view.rows = rows
        self._render_current()
        self.focus_list()
        self._announce(view)

    def _render_current(self):
        view = self.stack.current
        if view is None:
            return
        self.content_list.Set(view.display_lines())
        if self.content_list.GetCount():
            self.content_list.SetSelection(0)

    def _announce(self, view):
        if view.status == STATUS_AUTH:
            speak(_("يلزم تسجيل الدخول لعرض هذا المحتوى"))
        elif view.status == STATUS_ERROR:
            speak(_("حدث خطأ أثناء التحميل"))
        elif view.status == STATUS_EMPTY:
            speak(_("لا توجد عناصر"))
        else:
            speak(
                _("{title}، {count} عنصر").format(
                    title=view.title, count=len(view.rows)
                )
            )

    def focus_list(self):
        try:
            if self.IsShown():
                self.content_list.SetFocus()
        except Exception:
            logger.debug("Could not focus the music list", exc_info=True)

    # PLACEHOLDER_PANEL_EVENTS

    # -- list interaction ----------------------------------------------------

    def _selected_index(self):
        index = self.content_list.GetSelection()
        if index == wx.NOT_FOUND:
            return 0
        return index

    def _activate_selected(self, audio_mode=True):
        view = self.stack.current
        if view is None:
            return
        view.on_activate(self._selected_index(), audio_mode=audio_mode)

    def _on_dclick(self, event):
        self._activate_selected(audio_mode=True)

    def _on_char_hook(self, event):
        key = event.GetKeyCode()
        if key in (wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER):
            # Enter = play as audio (music default); Ctrl+Enter = play with video.
            self._activate_selected(audio_mode=not event.ControlDown())
            return
        if key == wx.WXK_BACK or (key == wx.WXK_LEFT and event.AltDown()):
            self.go_back()
            return
        event.Skip()

    def _on_context_menu(self, event):
        view = self.stack.current
        if view is None:
            return
        index = self.content_list.GetSelection()
        actions = view.context_actions(index) if index != wx.NOT_FOUND else []
        if not actions:
            return
        menu = wx.Menu()
        for label, callback in actions:
            item = menu.Append(-1, label)
            self.Bind(wx.EVT_MENU, lambda e, cb=callback: cb(), item)
        self.content_list.PopupMenu(menu)
        menu.Destroy()

    # PLACEHOLDER_PANEL_ACTIONS

    # -- actions invoked by views -------------------------------------------

    def play(self, result, index, audio_mode=True):
        playback.play_result(self.home_screen, result, index, audio_mode=audio_mode)

    def start_radio(self, result, index, audio_mode=True):
        playback.start_radio(self.home_screen, result, index, audio_mode=audio_mode)

    def download_row(self, row):
        video_id = row.get("videoId")
        if not video_id:
            return
        url = adapters.WATCH_URL.format(video_id=video_id)
        try:
            from download_handler.downloader import start_media_download
            from settings_handler import config_get

            start_media_download(
                url,
                "m4a",
                self.home_screen,
                config_get("path"),
                row.get("title", ""),
            )
        except Exception:
            logger.exception("YouTube Music download failed to start")
            speak(_("تعذر بدء التنزيل"))

    def open_album(self, row):
        self.show_view(views.album_view(self, row))

    def open_artist(self, row):
        self.show_view(views.artist_view(self, row))

    def open_playlist(self, row):
        self.show_view(views.playlist_view(self, row))

    def open_mood(self, row):
        self.show_view(
            views.mood_playlists_view(self, row.get("params"), row.get("title"))
        )

    def open_moods(self):
        self.show_view(views.moods_view(self))

    def open_search_dialog(self):
        dialog = wx.TextEntryDialog(self, _("ابحث في يوتيوب ميوزك:"), _("بحث"))
        try:
            if dialog.ShowModal() == wx.ID_OK:
                query = dialog.GetValue().strip()
                if query:
                    self.show_view(views.search_view(self, query))
        finally:
            dialog.Destroy()

    def open_library_menu(self):
        menu = wx.Menu()
        for kind, label_fn in _LIBRARY_SECTIONS:
            item = menu.Append(-1, label_fn())
            self.Bind(wx.EVT_MENU, lambda e, k=kind: self.open_library(k), item)
        menu.AppendSeparator()
        create_item = menu.Append(-1, _("إنشاء قائمة تشغيل جديدة"))
        self.Bind(wx.EVT_MENU, lambda e: self.create_playlist(), create_item)
        self.library_button.PopupMenu(menu)
        menu.Destroy()

    def open_library(self, kind):
        self.show_view(views.library_view(self, kind))

    def prompt_sign_in(self):
        speak(_("افتح الإعدادات ثم بطاقة يوتيوب ميوزك لاستيراد كوكيز المتصفح"))
        opener = getattr(self.home_screen, "open_music_settings", None)
        if callable(opener):
            opener()

    # -- write actions (auth; destructive ones confirm first) ----------------

    @staticmethod
    def _channel_id(row):
        cid = row.get("browseId")
        if not cid:
            url = (row.get("channel") or {}).get("url", "")
            cid = url.rsplit("/", 1)[-1] if url else None
        return cid

    def like_row(self, row):
        video_id = row.get("videoId")
        if not video_id:
            return
        actions.run_write(
            self.home_screen,
            self,
            lambda: get_service().rate_song(video_id, "LIKE"),
            success_msg=_("تم تسجيل الإعجاب"),
            refresh=False,
        )

    def add_to_library(self, row):
        tokens = row.get("feedbackTokens") or {}
        add_token = tokens.get("add")
        if not add_token:
            speak(_("هذا العنصر غير متاح للإضافة إلى المكتبة"))
            return
        actions.run_write(
            self.home_screen,
            self,
            lambda: get_service().edit_song_library_status([add_token]),
            success_msg=_("تمت الإضافة إلى المكتبة"),
            refresh=False,
        )

    def add_to_playlist(self, row):
        video_id = row.get("videoId")
        if not video_id:
            return
        try:
            from gui.activity_dialog import LoadingDialog

            playlists = LoadingDialog(
                self.home_screen,
                _("جاري تحميل قوائم التشغيل"),
                lambda: get_service().get_library_playlists(),
            ).res
        except AuthRequiredError:
            self.prompt_sign_in()
            return
        except Exception:
            logger.exception("Could not load playlists")
            speak(_("تعذر تحميل قوائم التشغيل"))
            return
        playlists = playlists or []
        if not playlists:
            speak(_("لا توجد قوائم تشغيل. أنشئ واحدة أولاً"))
            return
        names = [p.get("title", "") for p in playlists]
        dialog = wx.SingleChoiceDialog(
            self.home_screen, _("اختر قائمة تشغيل:"), _("إضافة إلى قائمة تشغيل"), names
        )
        try:
            if dialog.ShowModal() != wx.ID_OK:
                return
            chosen = playlists[dialog.GetSelection()]
        finally:
            dialog.Destroy()
        playlist_id = chosen.get("playlistId")
        actions.run_write(
            self.home_screen,
            self,
            lambda: get_service().add_playlist_items(playlist_id, video_ids=[video_id]),
            success_msg=_("تمت الإضافة إلى قائمة التشغيل"),
            refresh=False,
        )

    def create_playlist(self):
        dialog = wx.TextEntryDialog(
            self.home_screen, _("اسم قائمة التشغيل الجديدة:"), _("إنشاء قائمة تشغيل")
        )
        try:
            if dialog.ShowModal() != wx.ID_OK:
                return
            title = dialog.GetValue().strip()
        finally:
            dialog.Destroy()
        if not title:
            return
        actions.run_write(
            self.home_screen,
            self,
            lambda: get_service().create_playlist(title, ""),
            success_msg=_("تم إنشاء قائمة التشغيل"),
            refresh=True,
        )

    def subscribe(self, row):
        channel_id = self._channel_id(row)
        if not channel_id:
            return
        actions.run_write(
            self.home_screen,
            self,
            lambda: get_service().subscribe_artists([channel_id]),
            success_msg=_("تم الاشتراك"),
            refresh=False,
        )

    def unsubscribe(self, row):
        channel_id = self._channel_id(row)
        if not channel_id:
            return
        name = row.get("title") or (row.get("channel") or {}).get("name", "")
        actions.run_write(
            self.home_screen,
            self,
            lambda: get_service().unsubscribe_artists([channel_id]),
            success_msg=_("تم إلغاء الاشتراك"),
            destructive=True,
            confirm_text=_("إلغاء الاشتراك من {name}؟").format(name=name),
            refresh=True,
        )

    def delete_playlist(self, row):
        playlist_id = row.get("playlistId") or row.get("browseId")
        if not playlist_id:
            return
        name = row.get("title", "")
        actions.run_write(
            self.home_screen,
            self,
            lambda: get_service().delete_playlist(playlist_id),
            success_msg=_("تم حذف قائمة التشغيل"),
            destructive=True,
            confirm_text=_("حذف قائمة التشغيل {name}؟").format(name=name),
            refresh=True,
        )

    def rename_playlist(self, row):
        playlist_id = row.get("playlistId") or row.get("browseId")
        if not playlist_id:
            return
        dialog = wx.TextEntryDialog(
            self.home_screen,
            _("الاسم الجديد:"),
            _("إعادة تسمية قائمة التشغيل"),
            row.get("title", ""),
        )
        try:
            if dialog.ShowModal() != wx.ID_OK:
                return
            new_title = dialog.GetValue().strip()
        finally:
            dialog.Destroy()
        if not new_title:
            return
        actions.run_write(
            self.home_screen,
            self,
            lambda: get_service().edit_playlist(playlist_id, title=new_title),
            success_msg=_("تمت إعادة التسمية"),
            refresh=True,
        )

    def remove_from_history(self, row):
        token = row.get("feedbackToken")
        if not token:
            speak(_("لا يمكن إزالة هذا العنصر من السجل"))
            return
        actions.run_write(
            self.home_screen,
            self,
            lambda: get_service().remove_history_items([token]),
            success_msg=_("تمت الإزالة من السجل"),
            destructive=True,
            confirm_text=_("إزالة {title} من السجل؟").format(
                title=row.get("title", "")
            ),
            refresh=True,
        )

    def remove_from_playlist(self, playlist_id, row):
        set_video_id = row.get("setVideoId")
        video_id = row.get("videoId")
        if not (playlist_id and video_id):
            return
        video_entry = {"videoId": video_id}
        if set_video_id:
            video_entry["setVideoId"] = set_video_id
        actions.run_write(
            self.home_screen,
            self,
            lambda: get_service().remove_playlist_items(playlist_id, [video_entry]),
            success_msg=_("تمت الإزالة من قائمة التشغيل"),
            destructive=True,
            confirm_text=_("إزالة {title} من قائمة التشغيل؟").format(
                title=row.get("title", "")
            ),
            refresh=True,
        )

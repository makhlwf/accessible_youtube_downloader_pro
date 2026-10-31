"""Accessible, paginated view of YouTube's chronological subscriptions feed."""

from threading import Thread

import wx

import utils
from gui.activity_dialog import LoadingDialog
from language_handler import _
from speech_client import speak
from theme_handler import apply_theme
from youtube_browser.scraper import Scraper
from youtube_browser.search_handler import SimpleResult


class SubscriptionsFeed(wx.Frame):
    def __init__(self, parent, return_focus=None):
        super().__init__(parent=parent, title=_("Subscriptions feed"))
        self._return_focus = return_focus or wx.Window.FindFocus()
        self._closed = False
        self._loading = False
        self._request_id = 0
        self.videos = []
        self.continuation = None
        self.results = SimpleResult([])
        self.scraper = Scraper(owner=self)

        panel = self.panel = wx.Panel(self, style=wx.TAB_TRAVERSAL)
        heading = wx.StaticText(
            panel, label=_("Videos from subscribed channels, newest first")
        )
        self.videosList = wx.ListBox(panel, name=_("Subscription videos, newest first"))
        self.status = wx.StaticText(panel, label="")
        self.refreshButton = wx.Button(panel, label=_("Refresh subscriptions feed"))
        self.loadMoreButton = wx.Button(panel, label=_("Load more videos"))
        self.playButton = wx.Button(panel, label=_("Play audio (Enter)"))
        self.videoButton = wx.Button(panel, label=_("Play video (Ctrl+Enter)"))
        self.backButton = wx.Button(panel, label=_("Back to home"))
        for button in (
            self.refreshButton,
            self.loadMoreButton,
            self.playButton,
            self.videoButton,
            self.backButton,
        ):
            button.SetName(button.GetLabel())

        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(heading, 0, wx.ALL, 5)
        sizer.Add(self.videosList, 1, wx.EXPAND | wx.ALL, 5)
        sizer.Add(self.status, 0, wx.EXPAND | wx.ALL, 5)
        for button in (
            self.refreshButton,
            self.loadMoreButton,
            self.playButton,
            self.videoButton,
            self.backButton,
        ):
            sizer.Add(button, 0, wx.EXPAND | wx.ALL, 5)
        panel.SetSizer(sizer)
        frame_sizer = wx.BoxSizer(wx.VERTICAL)
        frame_sizer.Add(panel, 1, wx.EXPAND)
        self.SetSizerAndFit(frame_sizer)
        self.Centre()
        self.Maximize(True)
        apply_theme(self)

        self.refreshButton.Bind(wx.EVT_BUTTON, lambda event: self.load_feed())
        self.loadMoreButton.Bind(wx.EVT_BUTTON, lambda event: self.load_feed(True))
        self.playButton.Bind(wx.EVT_BUTTON, lambda event: self.play(True))
        self.videoButton.Bind(wx.EVT_BUTTON, lambda event: self.play(False))
        self.backButton.Bind(wx.EVT_BUTTON, lambda event: self.back())
        self.videosList.Bind(wx.EVT_LISTBOX, self.on_selection)
        self.videosList.Bind(wx.EVT_LISTBOX_DCLICK, lambda event: self.play(True))
        self.Bind(wx.EVT_CHAR_HOOK, self.on_key)
        self.Bind(wx.EVT_CLOSE, lambda event: self.back())
        self.Bind(wx.EVT_WINDOW_DESTROY, self.on_destroy)
        self.Show()
        parent.Hide()
        self.videosList.SetFocus()
        self.load_feed()

    def _set_status(self, message):
        self.status.SetLabel(message)
        if self.IsShown():
            speak(message, interrupt=True)
        self.panel.Layout()

    def _update_controls(self):
        selected = self.videosList.GetSelection()
        playable = not self._loading and 0 <= selected < len(self.videos)
        self.playButton.Enable(playable)
        self.videoButton.Enable(playable)
        self.refreshButton.Enable(not self._loading)
        self.loadMoreButton.Enable(not self._loading and bool(self.continuation))

    def load_feed(self, load_more=False):
        if self._closed or self._loading or (load_more and not self.continuation):
            return
        # Move focus before disabling a focused action, not after its response.
        if wx.Window.FindFocus() in (
            self.refreshButton,
            self.loadMoreButton,
            self.playButton,
            self.videoButton,
        ):
            self.videosList.SetFocus()
        self._loading = True
        self._request_id += 1
        request_id = self._request_id
        continuation = self.continuation if load_more else None
        self._update_controls()
        self._set_status(
            _("Loading more subscription videos...")
            if load_more
            else _("Loading subscriptions feed...")
        )

        def fetch():
            try:
                data = utils.get_subscriptions_feed(continuation)
            except Exception:
                # Neither exception details nor cookie contents belong in speech.
                data = {
                    "error": _("Could not load subscriptions feed. Please try again.")
                }
            wx.CallAfter(self._apply_feed, request_id, data, load_more)

        Thread(target=fetch, daemon=True).start()

    def _apply_feed(self, request_id, data, load_more=False):
        if self._closed or request_id != self._request_id:
            return
        self._loading = False
        if (
            not isinstance(data, dict)
            or data.get("error")
            or not isinstance(data.get("videos"), list)
        ):
            # Retain existing items and the continuation so a failed page is retryable.
            message = data.get("error") if isinstance(data, dict) else None
            self._update_controls()
            self._set_status(
                message or _("Could not load subscriptions feed. Please try again.")
            )
            return

        selection = self.videosList.GetSelection()
        selected_id = (
            self.videos[selection]["id"] if 0 <= selection < len(self.videos) else None
        )
        old_count = len(self.videos) if load_more else 0
        videos = list(self.videos) if load_more else []
        seen = {video["id"] for video in videos}
        for video in data.get("videos", []):
            if (
                isinstance(video, dict)
                and video.get("id")
                and video.get("url")
                and video["id"] not in seen
            ):
                videos.append(video)
                seen.add(video["id"])
        # The server's subscriptions timeline is chronological. Do not sort its
        # localized relative publication labels lexically or by popularity.
        self.videos = videos
        next_token = data.get("continuation")
        self.continuation = (
            None if load_more and next_token == self.continuation else next_token
        )
        self.results = SimpleResult(self.videos)
        self.results.scraper = self.scraper
        self.scraper.set_results(self.results)
        self.videosList.Set([self._video_label(video) for video in self.videos])
        if self.videos:
            index = next(
                (
                    i
                    for i, video in enumerate(self.videos)
                    if video["id"] == selected_id
                ),
                0,
            )
            self.videosList.SetSelection(index)
        self._update_controls()
        if not self.videos:
            message = (
                _("No videos on this page. Load more to continue.")
                if self.continuation
                else _("No videos from subscribed channels are available.")
            )
        elif load_more:
            message = _("Loaded {count} more subscription videos.").format(
                count=len(self.videos) - old_count
            )
        else:
            message = _("Loaded {count} subscription videos, newest first.").format(
                count=len(self.videos)
            )
        if not self.continuation and self.videos:
            message = _("{message} End of subscriptions feed.").format(message=message)
        self._set_status(message)
        for index in range(old_count, min(old_count + 5, len(self.videos))):
            self.scraper.add_item(index, priority=10)

    @staticmethod
    def _video_label(video):
        return _("{title}, channel: {channel}, published: {published}").format(
            title=video.get("title") or _("Untitled video"),
            channel=video.get("author") or _("Unknown channel"),
            published=video.get("published_time") or _("Publication time unavailable"),
        )

    def on_selection(self, event):
        self._update_controls()
        index = self.videosList.GetSelection()
        if 0 <= index < len(self.videos):
            self.scraper.add_item(index, priority=0)

    def play(self, audio_mode=True):
        index = self.videosList.GetSelection()
        if self._closed or self._loading or not 0 <= index < len(self.videos):
            return
        video = self.videos[index]
        self._set_status(_("Starting playback..."))
        stream = self.results.get_stream(index, audio_mode=audio_mode)
        if stream is None:
            if not utils.check_yt_dlp(self):
                self._set_status(_("Playback was not started."))
                self.videosList.SetFocus()
                return
            stream = LoadingDialog(
                self,
                _("Starting playback..."),
                utils.get_playable_stream,
                video["url"],
                audio_mode,
            ).res
        if self._closed:
            return
        if stream is None:
            self._set_status(_("Could not play this video. Please try again."))
            self.videosList.SetFocus()
            return
        from media_player.media_gui import MediaGui

        self.videosList.SetFocus()
        MediaGui(
            self,
            video["title"],
            stream,
            video["url"],
            audio_mode=audio_mode,
            results=self.results,
        )
        self.Hide()

    def on_key(self, event):
        if event.KeyCode == wx.WXK_ESCAPE:
            self.back()
        elif event.KeyCode in (wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER) and (
            wx.Window.FindFocus() == self.videosList
        ):
            self.play(audio_mode=not event.ControlDown())
        else:
            # Native buttons handle Space/Enter and containers handle Tab/Shift+Tab.
            event.Skip()

    def _dispose(self):
        self._closed = True
        self._request_id += 1
        self.scraper.close()

    def on_destroy(self, event):
        if event.GetEventObject() is self:
            self._dispose()
        event.Skip()

    def back(self):
        if self._closed:
            return
        self._dispose()
        parent = self.Parent
        self.Destroy()
        if parent:
            parent.Show()
            focus = self._return_focus
            if focus and focus.IsShown() and focus.IsEnabled():
                focus.SetFocus()
            else:
                parent.SetFocus()

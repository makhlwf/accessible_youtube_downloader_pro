import logging

import wx

import doc_handler
import settings_handler
import speech_client
import utils
from gui.custom_controls import CustomLabel
from gui.text_viewer import Viewer
from language_handler import _, supported_languages

logger = logging.getLogger(__name__)


def _accessible_name(label):
    return str(label).replace("&", "").strip().rstrip(":：").strip()


def _set_accessible_name(control, label):
    name = _accessible_name(label)
    if name:
        set_name = getattr(control, "SetName", None)
        if callable(set_name):
            set_name(name)


def _set_bold_title(ctrl, size_delta=2):
    if hasattr(ctrl, "GetFont") and callable(ctrl.GetFont):
        try:
            font = ctrl.GetFont()
            if font and hasattr(font, "SetPointSize"):
                font.SetPointSize(font.GetPointSize() + size_delta)
                font.SetWeight(getattr(wx, "FONTWEIGHT_BOLD", 700))
                ctrl.SetFont(font)
        except Exception:
            pass


def _safe_wrap(ctrl, width=540):
    if hasattr(ctrl, "Wrap") and callable(ctrl.Wrap):
        try:
            ctrl.Wrap(width)
        except Exception:
            pass


class Step1ConfigPanel(wx.Panel):
    """Step 1: Core Configuration (Language, Playback Mode, Clipboard Detection)."""

    def __init__(self, parent, dialog):
        super().__init__(parent, style=wx.TAB_TRAVERSAL)
        self.dialog = dialog
        self._init_ui()

    def _init_ui(self):
        sizer = wx.BoxSizer(wx.VERTICAL)

        self.heading = CustomLabel(self, -1, _("Step 1 of 4: Initial Configuration"))
        _set_bold_title(self.heading, 3)
        _set_accessible_name(self.heading, _("Step 1 of 4: Initial Configuration"))
        sizer.Add(self.heading, 0, wx.ALL, 8)

        desc_text = _(
            "Configure essential preferences for your listening and browsing experience. "
            "You can always change these settings later in the Settings menu."
        )
        self.desc_label = wx.StaticText(self, -1, desc_text)
        _safe_wrap(self.desc_label, 560)
        _set_accessible_name(self.desc_label, desc_text)
        sizer.Add(self.desc_label, 0, wx.ALL, 8)

        # Language selection
        lang_box = wx.BoxSizer(wx.HORIZONTAL)
        self.lang_label = wx.StaticText(self, -1, _("Interface Language:"))
        _set_accessible_name(self.lang_label, _("Interface Language"))
        lang_box.Add(self.lang_label, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 8)

        self.lang_codes = list(supported_languages.keys())
        self.lang_names = list(supported_languages.values())
        self.choice_lang = wx.Choice(self, -1, choices=self.lang_names)
        _set_accessible_name(self.choice_lang, _("Interface Language"))

        current_lang = settings_handler.config_get("lang") or "en"
        if current_lang in self.lang_codes:
            self.choice_lang.SetSelection(self.lang_codes.index(current_lang))
        elif len(self.lang_names) > 0:
            self.choice_lang.SetSelection(0)
        lang_box.Add(self.choice_lang, 1, wx.EXPAND)
        sizer.Add(lang_box, 0, wx.ALL | wx.EXPAND, 8)

        # Playback Mode
        mode_choices = [
            _("Audio Mode (Fast, screen reader optimized, background listening)"),
            _("Video Mode (Displays video player window)"),
        ]
        self.radio_mode = wx.RadioBox(
            self,
            -1,
            label=_("Preferred Playback Mode"),
            choices=mode_choices,
            majorDimension=1,
            style=wx.RA_SPECIFY_COLS,
        )
        _set_accessible_name(self.radio_mode, _("Preferred Playback Mode"))
        current_audio = settings_handler.config_get("defaultaudio")
        # 0 = audio, 1 = video
        mode_idx = 0 if current_audio == 0 else 1
        self.radio_mode.SetSelection(mode_idx)
        sizer.Add(self.radio_mode, 0, wx.ALL | wx.EXPAND, 8)

        # Clipboard Detection Checkbox
        self.chk_clipboard = wx.CheckBox(
            self,
            -1,
            _("Automatically detect YouTube links copied to clipboard"),
        )
        _set_accessible_name(
            self.chk_clipboard,
            _("Automatically detect YouTube links copied to clipboard"),
        )
        self.chk_clipboard.SetValue(bool(settings_handler.config_get("autodetect")))
        sizer.Add(self.chk_clipboard, 0, wx.ALL, 8)

        self.SetSizer(sizer)


class Step2ComponentsPanel(wx.Panel):
    """Step 2: Component Readiness (yt-dlp check and update)."""

    def __init__(self, parent, dialog):
        super().__init__(parent, style=wx.TAB_TRAVERSAL)
        self.dialog = dialog
        self._init_ui()

    def _init_ui(self):
        sizer = wx.BoxSizer(wx.VERTICAL)

        self.heading = CustomLabel(self, -1, _("Step 2 of 4: Component Readiness"))
        _set_bold_title(self.heading, 3)
        _set_accessible_name(self.heading, _("Step 2 of 4: Component Readiness"))
        sizer.Add(self.heading, 0, wx.ALL, 8)

        intro_text = _(
            "HexPlayer includes bundled media codecs (libmpv) for instant playback. "
            "To download videos and extract high quality audio, the yt-dlp download engine is used."
        )
        self.intro_label = wx.StaticText(self, -1, intro_text)
        _safe_wrap(self.intro_label, 560)
        _set_accessible_name(self.intro_label, intro_text)
        sizer.Add(self.intro_label, 0, wx.ALL, 8)

        # Downloader Status Box
        status_box = wx.StaticBox(self, -1, _("Download Engine Status"))
        box_sizer = wx.StaticBoxSizer(status_box, wx.VERTICAL)

        self.lbl_ytdlp_status = wx.StaticText(
            self, -1, _("Checking download engine...")
        )
        _set_bold_title(self.lbl_ytdlp_status, 1)
        box_sizer.Add(self.lbl_ytdlp_status, 0, wx.ALL, 8)

        self.btn_download_ytdlp = wx.Button(
            self, -1, _("Download or Update Download Engine")
        )
        _set_accessible_name(
            self.btn_download_ytdlp, _("Download or Update Download Engine")
        )
        self.btn_download_ytdlp.Bind(wx.EVT_BUTTON, self._on_download_ytdlp)
        box_sizer.Add(self.btn_download_ytdlp, 0, wx.ALL, 8)

        sizer.Add(box_sizer, 0, wx.ALL | wx.EXPAND, 8)
        self.SetSizer(sizer)
        self.refresh_status(announce=False)

    def refresh_status(self, announce=False):
        ver = utils.get_yt_dlp_version()
        if ver:
            status_str = _(
                "Download Engine (yt-dlp): Ready (Version: {version})"
            ).format(version=ver)
            self.lbl_ytdlp_status.SetLabel(status_str)
            _set_accessible_name(self.lbl_ytdlp_status, status_str)
        else:
            status_str = _(
                "Download Engine (yt-dlp): Not installed or update recommended"
            )
            self.lbl_ytdlp_status.SetLabel(status_str)
            _set_accessible_name(self.lbl_ytdlp_status, status_str)

        if announce:
            speech_client.speak(status_str, interrupt=True)

    def _on_download_ytdlp(self, event):
        speech_client.speak(
            _("Starting download of the download engine in the background..."),
            interrupt=True,
        )
        self.btn_download_ytdlp.Disable()
        try:
            utils.download_yt_dlp(parent=self.dialog)
        finally:
            self.btn_download_ytdlp.Enable()
            self.refresh_status(announce=True)


class Step3ShortcutsPanel(wx.Panel):
    """Step 3: Keyboard Shortcuts & Workflow Cheat Sheet."""

    def __init__(self, parent, dialog):
        super().__init__(parent, style=wx.TAB_TRAVERSAL)
        self.dialog = dialog
        self._init_ui()

    def _init_ui(self):
        sizer = wx.BoxSizer(wx.VERTICAL)

        self.heading = CustomLabel(
            self, -1, _("Step 3 of 4: Keyboard Shortcuts & Quick Workflows")
        )
        _set_bold_title(self.heading, 3)
        _set_accessible_name(
            self.heading, _("Step 3 of 4: Keyboard Shortcuts & Quick Workflows")
        )
        sizer.Add(self.heading, 0, wx.ALL, 8)

        desc_text = _(
            "Use Arrow keys to explore essential shortcuts. You can use these keys anywhere in the main window."
        )
        self.desc_label = wx.StaticText(self, -1, desc_text)
        _safe_wrap(self.desc_label, 560)
        _set_accessible_name(self.desc_label, desc_text)
        sizer.Add(self.desc_label, 0, wx.ALL, 8)

        # Shortcuts list control
        self.list_shortcuts = wx.ListCtrl(
            self,
            -1,
            style=wx.LC_REPORT | wx.LC_SINGLE_SEL | wx.BORDER_SUNKEN,
            size=(-1, 220),
        )
        _set_accessible_name(self.list_shortcuts, _("Keyboard Shortcuts Cheat Sheet"))

        self.list_shortcuts.InsertColumn(0, _("Shortcut"), width=150)
        self.list_shortcuts.InsertColumn(1, _("Action"), width=380)

        self.shortcuts = [
            ("Alt+S / Ctrl+F", _("Focus Search Box")),
            ("Tab / Shift+Tab", _("Move between Search, Results list, and Controls")),
            ("Enter", _("Play selected video or playlist")),
            ("Space", _("Play / Pause media")),
            ("Left / Right Arrows", _("Seek 5 seconds backward / forward")),
            ("Up / Down Arrows", _("Volume increase / decrease")),
            ("[ / ]", _("Decrease / Increase playback speed")),
            ("M", _("Mute / Unmute audio")),
            ("D / Alt+D", _("Download selected media")),
            ("Ctrl+H", _("Open History")),
            ("Ctrl+B", _("Open Bookmarks / Favorites")),
        ]

        for i, (key, action) in enumerate(self.shortcuts):
            self.list_shortcuts.InsertItem(i, key)
            self.list_shortcuts.SetItem(i, 1, action)

        sizer.Add(self.list_shortcuts, 1, wx.ALL | wx.EXPAND, 8)

        self.btn_full_shortcuts = wx.Button(self, -1, _("Open Full Shortcuts Guide"))
        _set_accessible_name(self.btn_full_shortcuts, _("Open Full Shortcuts Guide"))
        self.btn_full_shortcuts.Bind(wx.EVT_BUTTON, self._on_full_shortcuts)
        sizer.Add(self.btn_full_shortcuts, 0, wx.ALL, 8)

        self.SetSizer(sizer)

    def _on_full_shortcuts(self, event):
        content = doc_handler.documentation_get()
        if content:
            viewer = Viewer(self.dialog, _("HexPlayer Documentation"), content)
            viewer.ShowModal()
        else:
            speech_client.speak(_("Full documentation opened."), interrupt=True)


class Step4ReadyPanel(wx.Panel):
    """Step 4: Ready to Go & Launch."""

    def __init__(self, parent, dialog):
        super().__init__(parent, style=wx.TAB_TRAVERSAL)
        self.dialog = dialog
        self._init_ui()

    def _init_ui(self):
        sizer = wx.BoxSizer(wx.VERTICAL)

        self.heading = CustomLabel(self, -1, _("Step 4 of 4: You are Ready to Go!"))
        _set_bold_title(self.heading, 3)
        _set_accessible_name(self.heading, _("Step 4 of 4: You are Ready to Go!"))
        sizer.Add(self.heading, 0, wx.ALL, 8)

        summary_text = _(
            "Setup is complete! You can access all settings and features at any time "
            "from the main window menu bar. Press F1 anytime for the complete User Guide."
        )
        self.summary_label = wx.StaticText(self, -1, summary_text)
        _safe_wrap(self.summary_label, 560)
        _set_accessible_name(self.summary_label, summary_text)
        sizer.Add(self.summary_label, 0, wx.ALL, 8)

        self.chk_show_on_startup = wx.CheckBox(
            self, -1, _("Show this welcome screen on startup")
        )
        _set_accessible_name(
            self.chk_show_on_startup, _("Show this welcome screen on startup")
        )
        self.chk_show_on_startup.SetValue(False)
        sizer.Add(self.chk_show_on_startup, 0, wx.ALL, 8)

        self.btn_open_docs = wx.Button(self, -1, _("Open User Documentation (F1)"))
        _set_accessible_name(self.btn_open_docs, _("Open User Documentation (F1)"))
        self.btn_open_docs.Bind(wx.EVT_BUTTON, self._on_open_docs)
        sizer.Add(self.btn_open_docs, 0, wx.ALL, 8)

        sizer.AddStretchSpacer(1)

        self.btn_finish = wx.Button(self, wx.ID_OK, _("Finish and Launch HexPlayer"))
        _set_bold_title(self.btn_finish, 1)
        _set_accessible_name(self.btn_finish, _("Finish and Launch HexPlayer"))
        self.btn_finish.Bind(wx.EVT_BUTTON, self.dialog._on_finish)
        sizer.Add(self.btn_finish, 0, wx.ALL | wx.ALIGN_CENTER_HORIZONTAL, 12)

        self.SetSizer(sizer)

    def _on_open_docs(self, event):
        content = doc_handler.documentation_get()
        if content:
            viewer = Viewer(self.dialog, _("HexPlayer Documentation"), content)
            viewer.ShowModal()
        else:
            speech_client.speak(_("User Guide not found."), interrupt=True)


class WelcomeDialog(wx.Dialog):
    """Accessible 4-step first-run onboarding wizard for HexPlayer."""

    def __init__(self, parent=None):
        super().__init__(
            parent,
            id=wx.ID_ANY,
            title=_("HexPlayer Welcome & Setup Guide"),
            size=(640, 520),
            style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER,
        )

        self.current_step = 0

        self.step_titles = [
            _("Initial Configuration"),
            _("Component Readiness"),
            _("Keyboard Shortcuts & Quick Workflows"),
            _("You are Ready to Go!"),
        ]

        self._init_ui()
        if hasattr(self, "CenterOnScreen") and callable(self.CenterOnScreen):
            self.CenterOnScreen()

    def _init_ui(self):
        main_sizer = wx.BoxSizer(wx.VERTICAL)

        # Panel container
        self.container = wx.Panel(self, -1)
        self.container_sizer = wx.BoxSizer(wx.VERTICAL)

        self.step1_panel = Step1ConfigPanel(self.container, self)
        self.step2_panel = Step2ComponentsPanel(self.container, self)
        self.step3_panel = Step3ShortcutsPanel(self.container, self)
        self.step4_panel = Step4ReadyPanel(self.container, self)

        self.steps = [
            self.step1_panel,
            self.step2_panel,
            self.step3_panel,
            self.step4_panel,
        ]

        for p in self.steps:
            self.container_sizer.Add(p, 1, wx.EXPAND)
            p.Hide()

        self.container.SetSizer(self.container_sizer)
        main_sizer.Add(self.container, 1, wx.EXPAND | wx.ALL, 8)

        # Bottom navigation bar
        nav_sizer = wx.BoxSizer(wx.HORIZONTAL)

        self.btn_back = wx.Button(self, wx.ID_BACKWARD, _("< Back"))
        _set_accessible_name(self.btn_back, _("Back to previous step"))
        self.btn_back.Bind(wx.EVT_BUTTON, self._on_back)
        nav_sizer.Add(self.btn_back, 0, wx.RIGHT, 8)

        self.btn_next = wx.Button(self, wx.ID_FORWARD, _("Next >"))
        _set_accessible_name(self.btn_next, _("Next step"))
        self.btn_next.Bind(wx.EVT_BUTTON, self._on_next)
        nav_sizer.Add(self.btn_next, 0, wx.RIGHT, 8)

        nav_sizer.AddStretchSpacer(1)

        self.btn_skip = wx.Button(self, wx.ID_CANCEL, _("Skip / Close"))
        _set_accessible_name(self.btn_skip, _("Skip and close guide"))
        self.btn_skip.Bind(wx.EVT_BUTTON, self._on_skip)
        nav_sizer.Add(self.btn_skip, 0, wx.LEFT, 8)

        main_sizer.Add(nav_sizer, 0, wx.EXPAND | wx.ALL, 12)
        self.SetSizer(main_sizer)

        self.Bind(wx.EVT_CHAR_HOOK, self._on_char_hook)

        # Show initial step
        self._show_step(0, announce=False)

    @property
    def choice_lang(self):
        return self.step1_panel.choice_lang

    @property
    def radio_mode(self):
        return self.step1_panel.radio_mode

    @property
    def chk_clipboard(self):
        return self.step1_panel.chk_clipboard

    @property
    def btn_download_ytdlp(self):
        return self.step2_panel.btn_download_ytdlp

    @property
    def lbl_ytdlp_status(self):
        return self.step2_panel.lbl_ytdlp_status

    @property
    def list_shortcuts(self):
        return self.step3_panel.list_shortcuts

    @property
    def btn_full_shortcuts(self):
        return self.step3_panel.btn_full_shortcuts

    @property
    def shortcuts(self):
        return self.step3_panel.shortcuts

    @property
    def chk_show_on_startup(self):
        return self.step4_panel.chk_show_on_startup

    @property
    def btn_finish(self):
        return self.step4_panel.btn_finish

    def _show_step(self, step_idx, announce=True):
        if not (0 <= step_idx < len(self.steps)):
            return

        for i, p in enumerate(self.steps):
            if i == step_idx:
                p.Show()
            else:
                p.Hide()

        self.current_step = step_idx
        self.container.Layout()

        # Update navigation buttons
        self.btn_back.Enable(self.current_step > 0)
        if self.current_step == len(self.steps) - 1:
            self.btn_next.SetLabel(_("Finish"))
            _set_accessible_name(self.btn_next, _("Finish and save"))
        else:
            self.btn_next.SetLabel(_("Next >"))
            _set_accessible_name(self.btn_next, _("Next step"))

        # Screen reader announcement
        title = self.step_titles[self.current_step]
        if announce:
            msg = _("Step {current} of {total}: {title}").format(
                current=self.current_step + 1,
                total=len(self.steps),
                title=title,
            )
            speech_client.speak(msg, interrupt=True)

        # Shift focus to active panel heading or first element
        active_panel = self.steps[self.current_step]
        if hasattr(active_panel, "heading"):
            active_panel.heading.SetFocus()

    def _on_next(self, event):
        if self.current_step < len(self.steps) - 1:
            self._show_step(self.current_step + 1, announce=True)
        else:
            self._on_finish(event)

    def _on_back(self, event):
        if self.current_step > 0:
            self._show_step(self.current_step - 1, announce=True)

    def _save_settings(self):
        # 1. Language
        sel = self.choice_lang.GetSelection()
        if 0 <= sel < len(self.step1_panel.lang_codes):
            lang_code = self.step1_panel.lang_codes[sel]
            settings_handler.config_set("lang", lang_code)

        # 2. Playback mode (0 = Audio, 1 = Video)
        mode_sel = self.radio_mode.GetSelection()
        settings_handler.config_set("defaultaudio", 0 if mode_sel == 0 else 1)

        # 3. Clipboard auto-detection
        settings_handler.config_set("autodetect", self.chk_clipboard.GetValue())

        # 4. Welcome completion
        show_on_startup = self.chk_show_on_startup.GetValue()
        settings_handler.config_set("welcome_completed", not show_on_startup)

        settings_handler.save_settings()

    def _on_finish(self, event):
        self._save_settings()
        speech_client.speak(_("Welcome tour completed."), interrupt=True)
        if hasattr(self, "EndModal"):
            self.EndModal(wx.ID_OK)
        else:
            self.Close()

    def _on_skip(self, event):
        self._save_settings()
        if hasattr(self, "EndModal"):
            self.EndModal(wx.ID_CANCEL)
        else:
            self.Close()

    def _on_char_hook(self, event):
        key = event.GetKeyCode()
        if key == wx.WXK_ESCAPE:
            self._on_skip(event)
        else:
            event.Skip()

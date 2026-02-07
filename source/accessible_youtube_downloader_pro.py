# the main module
import os

os.chdir(os.path.abspath(os.path.dirname(__file__)))
os.add_dll_directory(os.getcwd())
import settings_handler  # noqa: E402
from language_handler import init_translation, codes, _  # noqa: E402

settings_handler.config_initialization()  # calling the config_initialization function which sets up the accessible_youtube_downloader_pro.ini file in the user appdata folder
init_translation("HexPlayer")  # program localization
import database  # noqa: E402
import application  # noqa: E402
import pyperclip  # noqa: E402
import wx  # noqa: E402
import webbrowser  # noqa: E402
import subprocess  # noqa: E402
import utiles  # noqa: E402
import threading  # noqa: E402
from async_utils import (  # noqa: E402
    start_async_loop,
    stop_async_loop,
)
from gui.activity_dialog import LoadingDialog  # noqa: E402
from gui.auto_detect_dialog import AutoDetectDialog  # noqa: E402
from gui.download_dialog import DownloadDialog  # noqa: E402
from gui.link_dlg import LinkDlg  # noqa: E402
from gui.settings_dialog import SettingsDialog  # noqa: E402
from gui.text_viewer import Viewer  # noqa: E402
from gui.custom_controls import CustomLabel  # noqa: E402
from gui.favorites import Favorites  # noqa: E402
from gui.history import HistoryDialog  # noqa: E402
from doc_handler import documentation_get  # noqa: E402
from media_player.media_gui import MediaGui  # noqa: E402
from youtube_browser.browser import YoutubeBrowser  # noqa: E402
from threading import Thread  # noqa: E402


class HomeScreen(wx.Frame):
    # the main class
    def __init__(self):
        wx.Frame.__init__(self, parent=None, title=application.name)
        self.Centre()
        self.SetSize(wx.DisplaySize())
        self.Maximize(True)
        panel = wx.Panel(self)
        self.instruction = CustomLabel(
            panel,
            -1,
            _(
                "اضغط على مفتاح القوائم alt للوصول إلى خيارات البرنامج, أو تنقل بزر التاب للوصول سريعًا إلى أهم الخيارات المتاحة."
            ),
        )  # a breafe instruction message witch is shown by the custome StaticText to automaticly be focused when launching the app
        youtubeBrowseButton = wx.Button(
            panel, -1, _("البحث في youtube\tctrl+f"), name="tab"
        )
        downloadFromLinkButton = wx.Button(
            panel, -1, _("التنزيل من خلال رابط\tctrl+d"), name="tab"
        )
        playYoutubeLinkButton = wx.Button(
            panel, -1, _("تشغيل فيديو youtube من خلال الرابط\tctrl+y"), name="tab"
        )
        favButton = wx.Button(
            panel, -1, _("الفيديوهات المفضلة	ctrl+shift+f"), name="tab"
        )
        self.historyButton = wx.Button(panel, -1, _("سجل المشاهدة\tctrl+h"), name="tab")
        self.historyButton.Hide()
        # quick access buttons
        sizer = wx.BoxSizer(wx.VERTICAL)  # the main sizer
        sizer1 = wx.BoxSizer(wx.HORIZONTAL)  # quick access buttons sizer
        for control in panel.GetChildren():
            if control.Name == "tab":
                sizer1.Add(
                    control, 1
                )  # adding quick access buttons using for loop sins that eatch button named by the "tab" word
        sizer.Add(self.instruction, 0, wx.ALL, 10)
        self.home_feed_list = wx.ListBox(panel, -1, name="home_feed")
        self.home_feed_list.Hide()
        self.home_feed_data = []
        self.home_feed_continuation = None
        self.load_more_home_button = wx.Button(
            panel, -1, _("تحميل المزيد من الفيديوهات المقترحة")
        )
        self.load_more_home_button.Hide()
        sizer.Add(self.home_feed_list, 1, wx.EXPAND | wx.ALL, 5)
        sizer.Add(self.load_more_home_button, 0, wx.ALIGN_CENTER | wx.ALL, 5)
        sizer.AddStretchSpacer()
        sizer.Add(sizer1, 1, wx.EXPAND)
        panel.SetSizer(sizer)  # adding the sizer to the main panel
        menuBar = wx.MenuBar()  # seting up the menu bar
        mainMenu = wx.Menu()
        searchItem = mainMenu.Append(
            -1, _("البحث في youtube\tctrl+f")
        )  # search in youtube item
        downloadItem = mainMenu.Append(
            -1, _("التنزيل من خلال رابط\tctrl+d")
        )  # download link item
        playItem = mainMenu.Append(
            -1, _("تشغيل فيديو youtube من خلال الرابط\tctrl+y")
        )  # play youtube link item
        favoriteItem = mainMenu.Append(-1, _("الفيديوهات المفضلة	ctrl+shift+f"))
        self.historyItem = mainMenu.Append(-1, _("سجل المشاهدة\tctrl+h"))
        self.historyItem.Enable(False)
        openDownloadingPathItem = mainMenu.Append(
            -1, _("فتح مجلد التنزيل\tctrl+p")
        )  # open downloading folder item
        settingsItem = mainMenu.Append(-1, _("الإعدادات...\talt+s"))  # settings item
        exitItem = mainMenu.Append(-1, _("خروج\tctrl+w"))  # quit item
        hotKeys = wx.AcceleratorTable(
            [
                (wx.ACCEL_CTRL, ord("F"), searchItem.GetId()),
                (wx.ACCEL_CTRL, ord("D"), downloadItem.GetId()),
                (wx.ACCEL_CTRL, ord("Y"), playItem.GetId()),
                (wx.ACCEL_CTRL + wx.ACCEL_SHIFT, ord("F"), favoriteItem.GetId()),
                (wx.ACCEL_CTRL, ord("H"), self.historyItem.GetId()),
                (wx.ACCEL_CTRL, ord("P"), openDownloadingPathItem.GetId()),
                (wx.ACCEL_ALT, ord("S"), settingsItem.GetId()),
                (wx.ACCEL_CTRL, ord("W"), exitItem.GetId()),
            ]
        )
        # the accelerator table asociated with the menu items
        self.SetAcceleratorTable(hotKeys)  # adding the accelerator table to the frame
        menuBar.Append(
            mainMenu, _("القائمة الرئيسية")
        )  # append the main menu to the menu bar
        toolsMenu = wx.Menu()
        showYtdlpVersionItem = toolsMenu.Append(-1, _("عرض إصدار yt-dlp"))
        updateYtdlpItem = toolsMenu.Append(-1, _("التحقق من وجود تحديث لـ yt-dlp"))
        showDenoVersionItem = toolsMenu.Append(-1, _("عرض إصدار Deno.js"))
        updateDenoItem = toolsMenu.Append(-1, _("التحقق من وجود تحديث لـ Deno.js"))
        menuBar.Append(toolsMenu, _("قائمة الأدوات الخارجية"))
        aboutMenu = wx.Menu()
        userGuideItem = aboutMenu.Append(-1, _("دليل المستخدم...\tf1"))  # userguide
        checkForUpdatesItem = aboutMenu.Append(-1, _("البحث عن التحديثات"))
        aboutItem = aboutMenu.Append(-1, _("عن البرنامج..."))  # about item
        contactMenu = wx.Menu()
        emailItem = contactMenu.Append(-1, _("البريد الالكتروني..."))
        telegramItem = contactMenu.Append(-1, _("تلجرام..."))
        aboutMenu.AppendSubMenu(contactMenu, _("تواصل معي"))
        menuBar.Append(aboutMenu, _("حول"))  # append the about menu to the menu bar
        self.SetMenuBar(menuBar)  # add the menu bar to the window
        # event bindings
        self.Bind(wx.EVT_MENU, self.onSearch, searchItem)
        youtubeBrowseButton.Bind(wx.EVT_BUTTON, self.onSearch)
        self.Bind(wx.EVT_MENU, self.onDownload, downloadItem)
        downloadFromLinkButton.Bind(wx.EVT_BUTTON, self.onDownload)
        self.Bind(wx.EVT_MENU, self.onPlay, playItem)
        playYoutubeLinkButton.Bind(wx.EVT_BUTTON, self.onPlay)
        self.Bind(wx.EVT_MENU, self.onFavorite, favoriteItem)
        favButton.Bind(wx.EVT_BUTTON, self.onFavorite)
        self.Bind(wx.EVT_MENU, self.onHistory, self.historyItem)
        self.historyButton.Bind(wx.EVT_BUTTON, self.onHistory)
        self.Bind(wx.EVT_MENU, self.onOpen, openDownloadingPathItem)
        self.Bind(wx.EVT_MENU, self.onSettings, settingsItem)
        self.Bind(wx.EVT_MENU, lambda event: wx.Exit(), exitItem)
        self.Bind(wx.EVT_MENU, self.onGuide, userGuideItem)
        self.Bind(wx.EVT_MENU, self.onCheckForUpdates, checkForUpdatesItem)
        self.Bind(wx.EVT_MENU, self.onAbout, aboutItem)
        self.Bind(wx.EVT_MENU, self.on_show_yt_dlp_version, showYtdlpVersionItem)
        self.Bind(wx.EVT_MENU, self.on_update_yt_dlp, updateYtdlpItem)
        self.Bind(wx.EVT_MENU, self.on_show_deno_version, showDenoVersionItem)
        self.Bind(wx.EVT_MENU, self.on_update_deno, updateDenoItem)
        self.Bind(
            wx.EVT_MENU,
            lambda event: webbrowser.open("mailto:altrhwnyashrf1@gmail.com"),
            emailItem,
        )
        self.Bind(
            wx.EVT_MENU,
            lambda event: webbrowser.open("https://t.me/makhlwf"),
            telegramItem,
        )
        self.Bind(wx.EVT_LISTBOX_DCLICK, self.on_home_feed_play, self.home_feed_list)
        self.home_feed_list.Bind(wx.EVT_CHAR_HOOK, self.on_home_feed_hook)
        self.load_more_home_button.Bind(
            wx.EVT_BUTTON, lambda event: self.load_home_feed(True)
        )
        self.Bind(wx.EVT_CHAR_HOOK, self.onHook)
        self.Bind(wx.EVT_SHOW, self.onShow)
        self.Bind(wx.EVT_CLOSE, self.onClose)
        self.Show()
        self.checked = False
        cookies_path = settings_handler.config_get("cookiespath")
        if cookies_path and os.path.exists(cookies_path):
            self.historyButton.Show()
            self.historyItem.Enable(True)
            self.load_home_feed()
        self.detectFromClipboard(settings_handler.config_get("autodetect"))
        if settings_handler.config_get("checkupdates"):
            Thread(target=utiles.check_for_updates, args=[True]).start()

    def on_show_yt_dlp_version(self, event):
        version = utiles.get_yt_dlp_version()
        if not version:
            wx.MessageBox(
                _("لم يتم العثور على أداة yt-dlp.exe أو تعذر الحصول على إصدارها"),
                _("خطأ"),
                style=wx.ICON_ERROR,
                parent=self,
            )
            return
        wx.MessageBox(version, _("إصدار yt-dlp"), parent=self)

    def load_home_feed(self, load_more=False):
        if not load_more:
            self.home_feed_list.Set([_("جاري تحميل الاقتراحات... يرجى الانتظار")])
            self.home_feed_list.Show()
            self.Layout()

        continuation = self.home_feed_continuation if load_more else None

        def _load():
            data = utiles.get_home_feed(continuation)
            wx.CallAfter(self._update_home_feed, data, load_more)

        Thread(target=_load, daemon=True).start()

    def _update_home_feed(self, data, load_more=False):
        new_videos = data.get("videos", [])
        self.home_feed_continuation = data.get("continuation")

        if load_more:
            self.home_feed_data.extend(new_videos)
        else:
            self.home_feed_data = new_videos
            self.home_feed_list.Clear()

        titles = [f"{item['title']} - {item['author']}" for item in self.home_feed_data]
        self.home_feed_list.Set(titles)

        if self.home_feed_data:
            self.home_feed_list.Show()
            if self.home_feed_continuation:
                self.load_more_home_button.Show()
            else:
                self.load_more_home_button.Hide()
            self.Layout()
        else:
            self.home_feed_list.Hide()
            self.load_more_home_button.Hide()
            self.Layout()

    def on_home_feed_play(self, event, audio_mode=False):
        selection = self.home_feed_list.GetSelection()
        if selection == wx.NOT_FOUND:
            return
        video_data = self.home_feed_data[selection]
        url = video_data["url"]
        stream = LoadingDialog(
            self,
            _("جاري التشغيل"),
            utiles.get_playable_stream,
            url,
            audio_mode,
        ).res
        if stream is None:
            wx.MessageBox(
                _("لا يمكن تشغيل الرابط"), _("خطأ"), style=wx.ICON_ERROR, parent=self
            )
            return
        MediaGui(
            self,
            stream.title,
            stream,
            url,
            audio_mode=audio_mode,
            results=self.home_feed_data,
        )
        self.Hide()

    def on_home_feed_hook(self, event):
        if event.KeyCode == wx.WXK_RETURN:
            if event.ControlDown():
                self.on_home_feed_play(None, audio_mode=False)
            else:
                self.on_home_feed_play(None, audio_mode=True)
        else:
            event.Skip()

    def on_show_deno_version(self, event):
        version = utiles.get_deno_version()
        if not version:
            wx.MessageBox(
                _("لم يتم العثور على أداة deno.exe أو تعذر الحصول على إصدارها"),
                _("خطأ"),
                style=wx.ICON_ERROR,
                parent=self,
            )
            return
        wx.MessageBox(version, _("إصدار Deno.js"), parent=self)

    def on_update_deno(self, event):
        utiles.update_deno()

    def on_update_yt_dlp(self, event):
        utiles.update_yt_dlp()

    def onPlay(
        self, event
    ):  # the event function called when the play youtube link is clicked
        linkDlg = LinkDlg(self)
        data = linkDlg.data  # get the link and playing format from the dialog
        if data["link"] == "":
            return
        url = data["link"]
        audio_mode = data["audio"]
        stream = LoadingDialog(
            self,
            _("جاري التشغيل"),
            utiles.get_playable_stream,
            url,
            audio_mode,
        ).res
        if stream is None:
            wx.MessageBox(
                _("لا يمكن تشغيل الرابط"), _("خطأ"), style=wx.ICON_ERROR, parent=self
            )
            return
        MediaGui(
            self, stream.title, stream, data["link"], audio_mode=audio_mode
        )  # initiating the media gui
        self.Hide()

    def onDownload(
        self, event
    ):  # the event function for the link downloading item to show the appropriate dialog
        dlg = DownloadDialog(self)
        dlg.Show()

    def onSearch(self, event):  # showing the youtube browser window event function
        YoutubeBrowser(self)

    def onHistory(self, event):
        HistoryDialog(self)

    def detectFromClipboard(self, config):
        if not config:
            return
        clip_content = pyperclip.paste()  # get the clipboard content
        match = utiles.youtube_regexp(clip_content)
        if match is not None:
            AutoDetectDialog(self, clip_content)

    def onSettings(self, event):
        SettingsDialog(self)
        cookies_path = settings_handler.config_get("cookiespath")
        if cookies_path and os.path.exists(cookies_path):
            if not self.home_feed_list.IsShown() or not self.home_feed_data:
                self.load_home_feed()
        else:
            self.home_feed_list.Hide()
            self.load_more_home_button.Hide()
            self.Layout()

    def onFavorite(self, event):
        Favorites(self)
        self.Hide()

    def onOpen(self, event):
        path = settings_handler.config_get("path")
        if not os.path.exists(path):
            os.mkdir(path)
        explorer = os.path.join(os.getenv("SYSTEMDRIVE"), "\\windows\\explorer")
        subprocess.call(f"{explorer} {path}")

    def onHook(self, event):
        if event.KeyCode == wx.WXK_F1:
            content = documentation_get()
            if content is None:
                event.Skip()
                return
            Viewer(
                self,
                _("دليل استخدام برنامج HexPlayer"),
                content,
            )
        event.Skip()

    def onShow(self, event):
        self.instruction.SetFocus()
        if not self.checked:
            wx.CallAfter(self.startup_checks)
            self.checked = True
        event.Skip()

    def startup_checks(self):
        if utiles.check_yt_dlp(self):
            if utiles.check_deno(self):
                utiles.ensure_js_dependencies()

    def onGuide(self, event):
        content = documentation_get()
        if content is None:
            return
        Viewer(self, _("دليل استخدام برنامج HexPlayer"), content).ShowModal()

    def onCheckForUpdates(self, event):
        from gui.activity_dialog import LoadingDialog

        # speak(_("جاري البحث عن التحديثات. يرجى الانتظار"))
        LoadingDialog(
            self, _("جاري البحث عن التحديثات. يرجى الانتظار"), utiles.check_for_updates
        )
        self.instruction.SetFocus()

    def onAbout(self, event):
        about = f"""{_("اسم البرنامج")}: {application.name}.
{_("الإصدار")}: {application.version}.
{_("طُوِر بواسطة")}: {application.author}.
{_("الوصف: ")}{_(application.describtion)}."""
        wx.MessageBox(about, _("حول"), parent=self)

    def onClose(self, event):
        database.disconnect()
        stop_async_loop()
        wx.Exit()


_async_thread = threading.Thread(target=start_async_loop, daemon=True)
_async_thread.start()

app = wx.App()
lang_id = codes.get(settings_handler.config_get("lang"), wx.LANGUAGE_ARABIC)
locale = wx.Locale(lang_id)
HomeScreen()
app.MainLoop()

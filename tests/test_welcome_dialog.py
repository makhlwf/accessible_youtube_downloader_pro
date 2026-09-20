import unittest
from unittest.mock import MagicMock, patch

import wx

from gui.welcome_dialog import (
    Step1ConfigPanel,
    Step2ComponentsPanel,
    Step3ShortcutsPanel,
    Step4ReadyPanel,
    WelcomeDialog,
    _accessible_name,
    _set_accessible_name,
)


class TestWelcomeDialog(unittest.TestCase):
    def setUp(self):
        self.app = wx.App.GetInstance() or wx.App()

        self.speak_patcher = patch("gui.welcome_dialog.speech_client")
        self.mock_speech = self.speak_patcher.start()

        self.dialog = WelcomeDialog(None)

    def tearDown(self):
        if self.dialog:
            self.dialog.Destroy()
        self.speak_patcher.stop()
        wx.Yield()

    def test_init_properties(self):
        self.assertEqual(len(self.dialog.steps), 4)
        self.assertEqual(self.dialog.current_step, 0)

        self.assertFalse(self.dialog.btn_back.IsEnabled())
        self.assertTrue(self.dialog.btn_next.IsEnabled())
        self.assertTrue(self.dialog.btn_skip.IsEnabled())
        self.assertEqual(self.dialog.btn_next.GetLabel(), "Next >")

        # Verify page classes
        self.assertIsInstance(self.dialog.steps[0], Step1ConfigPanel)
        self.assertIsInstance(self.dialog.steps[1], Step2ComponentsPanel)
        self.assertIsInstance(self.dialog.steps[2], Step3ShortcutsPanel)
        self.assertIsInstance(self.dialog.steps[3], Step4ReadyPanel)

    def test_accessible_name_helpers(self):
        self.assertEqual(_accessible_name("&Next >"), "Next >")
        self.assertEqual(_accessible_name("Interface Language: "), "Interface Language")

        btn = wx.Button(self.dialog, -1, "Test")
        _set_accessible_name(btn, "&Test Action: ")
        self.assertEqual(btn.GetName(), "Test Action")
        btn.Destroy()

    def test_welcome_dialog_step_navigation(self):
        # Step 0 -> Step 1
        self.dialog._on_next(None)
        self.assertEqual(self.dialog.current_step, 1)
        self.assertTrue(self.dialog.btn_back.IsEnabled())
        self.assertEqual(self.dialog.btn_next.GetLabel(), "Next >")
        self.assertTrue(self.mock_speech.speak.called)

        # Step 1 -> Step 2
        self.dialog._on_next(None)
        self.assertEqual(self.dialog.current_step, 2)
        self.assertTrue(self.dialog.btn_back.IsEnabled())
        self.assertEqual(self.dialog.btn_next.GetLabel(), "Next >")

        # Step 2 -> Step 3 (Final step)
        self.dialog._on_next(None)
        self.assertEqual(self.dialog.current_step, 3)
        self.assertTrue(self.dialog.btn_back.IsEnabled())
        self.assertEqual(self.dialog.btn_next.GetLabel(), "Finish")

        # Move back: Step 3 -> Step 2
        self.dialog._on_back(None)
        self.assertEqual(self.dialog.current_step, 2)
        self.assertEqual(self.dialog.btn_next.GetLabel(), "Next >")

    def test_step1_settings_persistence(self):
        self.dialog.EndModal = MagicMock()

        with (
            patch("gui.welcome_dialog.settings_handler.config_set") as mock_set,
            patch("gui.welcome_dialog.settings_handler.save_settings") as mock_save,
        ):
            self.dialog.choice_lang.SetSelection(0)
            self.dialog.radio_mode.SetSelection(1)  # Video
            self.dialog.chk_clipboard.SetValue(False)
            self.dialog.chk_show_on_startup.SetValue(False)

            self.dialog._on_finish(None)

            mock_set.assert_any_call("lang", "ar")
            mock_set.assert_any_call("defaultaudio", 1)
            mock_set.assert_any_call("autodetect", False)
            mock_set.assert_any_call("welcome_completed", True)
            self.assertTrue(mock_save.called)
            self.dialog.EndModal.assert_called_with(wx.ID_OK)

    def test_step1_language_selection_english(self):
        self.dialog.EndModal = MagicMock()
        with (
            patch("gui.welcome_dialog.settings_handler.config_set") as mock_set,
            patch("gui.welcome_dialog.settings_handler.save_settings"),
        ):
            self.dialog.choice_lang.SetSelection(1)
            self.dialog._on_finish(None)
            mock_set.assert_any_call("lang", "en")

    def test_step1_language_choices(self):
        self.assertEqual(
            list(self.dialog.choice_lang.GetStrings()), ["العربية", "English"]
        )
        self.assertEqual(self.dialog.step1_panel.lang_codes, ["ar", "en"])

    def test_step2_component_readiness_and_download(self):
        self.assertIsInstance(self.dialog.lbl_ytdlp_status.GetParent(), wx.StaticBox)
        self.assertIsInstance(self.dialog.btn_download_ytdlp.GetParent(), wx.StaticBox)

        with patch(
            "gui.welcome_dialog.utils.get_yt_dlp_version", return_value="2026.01.01"
        ):
            self.dialog.step2_panel.refresh_status(announce=True)
            self.assertIn("2026.01.01", self.dialog.lbl_ytdlp_status.GetLabel())
            self.assertTrue(self.mock_speech.speak.called)

        with patch("gui.welcome_dialog.utils.get_yt_dlp_version", return_value=None):
            self.dialog.step2_panel.refresh_status(announce=False)
            self.assertIn("Not installed", self.dialog.lbl_ytdlp_status.GetLabel())

        with patch("gui.welcome_dialog.utils.download_yt_dlp") as mock_dl:
            self.dialog.step2_panel._on_download_ytdlp(None)
            mock_dl.assert_called_once_with(parent=self.dialog)

    def test_step3_shortcuts_cheat_sheet_populated(self):
        self.assertGreater(len(self.dialog.shortcuts), 5)

        with (
            patch(
                "gui.welcome_dialog.doc_handler.documentation_get",
                return_value="Doc Content",
            ),
            patch("gui.welcome_dialog.Viewer") as mock_viewer,
        ):
            mock_inst = MagicMock()
            mock_viewer.return_value = mock_inst
            self.dialog.step3_panel._on_full_shortcuts(None)
            mock_viewer.assert_called_once()
            mock_inst.ShowModal.assert_called_once()

    def test_step4_startup_toggle_controls_welcome_completed(self):
        self.dialog.EndModal = MagicMock()

        # If user leaves "Show this welcome screen on startup" checked (True),
        # welcome_completed becomes False (so it shows again).
        with (
            patch("gui.welcome_dialog.settings_handler.config_set") as mock_set,
            patch("gui.welcome_dialog.settings_handler.save_settings") as mock_save,
        ):
            self.dialog.chk_show_on_startup.SetValue(True)
            self.dialog._on_finish(None)
            mock_set.assert_any_call("welcome_completed", False)
            self.assertTrue(mock_save.called)

        # If user unchecks "Show this welcome screen on startup" (False),
        # welcome_completed becomes True (does not show again).
        with (
            patch("gui.welcome_dialog.settings_handler.config_set") as mock_set,
            patch("gui.welcome_dialog.settings_handler.save_settings") as mock_save,
        ):
            self.dialog.chk_show_on_startup.SetValue(False)
            self.dialog._on_finish(None)
            mock_set.assert_any_call("welcome_completed", True)
            self.assertTrue(mock_save.called)

    def test_skip_and_close(self):
        self.dialog.EndModal = MagicMock()

        with (
            patch("gui.welcome_dialog.settings_handler.config_set") as mock_set,
            patch("gui.welcome_dialog.settings_handler.save_settings") as mock_save,
        ):
            self.dialog.chk_show_on_startup.SetValue(False)
            self.dialog._on_skip(None)
            mock_set.assert_any_call("welcome_completed", True)
            self.assertTrue(mock_save.called)
            self.dialog.EndModal.assert_called_with(wx.ID_CANCEL)

    def test_main_app_startup_welcome_integration(self):
        from accessible_youtube_downloader_pro import HomeScreen

        home = MagicMock(spec=HomeScreen)
        home.onShow = HomeScreen.onShow.__get__(home, HomeScreen)
        home.show_welcome_screen = MagicMock()
        home.startup_dependency_checks = MagicMock()
        home.instruction = MagicMock()
        home.checked = False

        # 1. When welcome_completed is False:
        with (
            patch("settings_handler.config_get", return_value=False),
            patch("wx.CallAfter") as mock_call_after,
        ):
            mock_event = MagicMock()
            home.onShow(mock_event)
            self.assertTrue(home.checked)
            mock_call_after.assert_called_once_with(home.show_welcome_screen)
            home.startup_dependency_checks.assert_not_called()

        # 2. When welcome_completed is True:
        home.checked = False
        with (
            patch("settings_handler.config_get", return_value=True),
            patch("wx.CallAfter") as mock_call_after,
        ):
            mock_event = MagicMock()
            home.onShow(mock_event)
            self.assertTrue(home.checked)
            home.startup_dependency_checks.assert_called_once()
            mock_call_after.assert_not_called()

        # 3. onWelcomeTour calls show_welcome_screen
        home.onWelcomeTour = HomeScreen.onWelcomeTour.__get__(home, HomeScreen)
        home.onWelcomeTour(None)
        home.show_welcome_screen.assert_called_once()


if __name__ == "__main__":
    unittest.main()

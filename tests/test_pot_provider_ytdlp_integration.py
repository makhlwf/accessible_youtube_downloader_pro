from unittest.mock import patch

import wx

import paths
import utils
from download_handler.downloader import Downloader


def test_get_ydl_instance_injects_pot_args_when_enabled(monkeypatch):
    monkeypatch.setattr(
        "utils.config_get",
        lambda k, default=None: (
            True
            if k == "pot_provider_enabled"
            else (4416 if k == "pot_provider_port" else default)
        ),
    )

    with (
        patch("pot_provider_service.pot_service.is_available", return_value=True),
        patch("pot_provider_service.pot_service.has_binary", return_value=True),
        patch(
            "pot_provider_service.pot_service.get_base_url",
            return_value="http://127.0.0.1:4416",
        ),
        patch("pot_provider_service.pot_service.ensure_started", return_value=True),
    ):
        ydl = utils.get_ydl_instance()
        assert ydl is not None
        extractor_args = ydl.params.get("extractor_args", {})
        assert "youtubepot-bgutilhttp" in extractor_args
        assert extractor_args["youtubepot-bgutilhttp"]["base_url"] == [
            "http://127.0.0.1:4416"
        ]
        assert "youtubepot-bgutilcli" in extractor_args
        assert extractor_args["youtubepot-bgutilcli"]["cli_path"] == [
            paths.pot_provider_exe
        ]


def test_get_ydl_instance_omits_pot_args_when_disabled(monkeypatch):
    monkeypatch.setattr(
        "utils.config_get",
        lambda k, default=None: False if k == "pot_provider_enabled" else default,
    )

    ydl = utils.get_ydl_instance()
    assert ydl is not None
    extractor_args = ydl.params.get("extractor_args", {})
    assert "youtubepot-bgutilhttp" not in extractor_args
    assert "youtubepot-bgutilcli" not in extractor_args


def test_downloader_base_options_injects_pot_args(monkeypatch):
    monkeypatch.setattr(
        "download_handler.downloader.config_get",
        lambda k, default=None: (
            True
            if k == "pot_provider_enabled"
            else (4416 if k == "pot_provider_port" else default)
        ),
    )

    with (
        patch("pot_provider_service.pot_service.is_available", return_value=True),
        patch("pot_provider_service.pot_service.has_binary", return_value=True),
        patch(
            "pot_provider_service.pot_service.get_base_url",
            return_value="http://127.0.0.1:4416",
        ),
        patch("pot_provider_service.pot_service.ensure_started", return_value=True),
    ):
        dl = Downloader(
            "https://www.youtube.com/watch?v=dummy", "C:/tmp", "video", None, None
        )
        opts = dl._base_options()
        extractor_args = opts.get("extractor_args", {})
        assert "youtubepot-bgutilhttp" in extractor_args
        assert extractor_args["youtubepot-bgutilhttp"]["base_url"] == [
            "http://127.0.0.1:4416"
        ]
        assert "youtubepot-bgutilcli" in extractor_args
        assert extractor_args["youtubepot-bgutilcli"]["cli_path"] == [
            paths.pot_provider_exe
        ]


def test_downloader_base_options_omits_pot_args_when_disabled(monkeypatch):
    monkeypatch.setattr(
        "download_handler.downloader.config_get",
        lambda k, default=None: False if k == "pot_provider_enabled" else default,
    )

    dl = Downloader(
        "https://www.youtube.com/watch?v=dummy", "C:/tmp", "video", None, None
    )
    opts = dl._base_options()
    extractor_args = opts.get("extractor_args", {})
    assert "youtubepot-bgutilhttp" not in extractor_args
    assert "youtubepot-bgutilcli" not in extractor_args


def test_check_pot_provider_when_installed():
    with (
        patch("utils.config_get", return_value=True),
        patch("pot_provider_service.pot_service.is_installed", return_value=True),
        patch("pot_provider_service.pot_service.ensure_started", return_value=True),
    ):
        assert utils.check_pot_provider() is True


def test_check_pot_provider_when_disabled():
    with patch("utils.config_get", return_value=False):
        assert utils.check_pot_provider() is False


def test_check_pot_provider_when_missing_prompts_and_installs():
    with (
        patch("utils.config_get", return_value=True),
        patch("pot_provider_service.pot_service.is_installed", return_value=False),
        patch("wx.MessageBox", return_value=wx.YES),
        patch(
            "pot_provider_service.pot_service.download_and_install", return_value=True
        ) as mock_install,
    ):
        assert utils.check_pot_provider() is True
        mock_install.assert_called_once()


def test_check_pot_provider_when_missing_declined():
    with (
        patch("utils.config_get", return_value=True),
        patch("pot_provider_service.pot_service.is_installed", return_value=False),
        patch("wx.MessageBox", return_value=wx.NO),
        patch("pot_provider_service.pot_service.download_and_install") as mock_install,
    ):
        assert utils.check_pot_provider() is False
        mock_install.assert_not_called()

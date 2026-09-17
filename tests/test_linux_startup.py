import os
import subprocess
import sys
from pathlib import Path
from textwrap import dedent

import pytest


@pytest.mark.skipif(sys.platform != "linux", reason="Requires a real Linux interpreter")
@pytest.mark.parametrize(
    ("locale_name", "expected_language", "xdg_downloads"),
    [
        ("C.UTF-8", "en", False),
        ("en_US.UTF-8", "en", True),
        ("ar_EG.UTF-8", "ar", True),
    ],
)
def test_linux_startup_real_ctypes(
    tmp_path, locale_name, expected_language, xdg_downloads
):
    source = Path(__file__).resolve().parents[1] / "src"
    home = tmp_path / "home"
    config = tmp_path / "config"
    data = tmp_path / "data"
    for directory in (home, config, data):
        directory.mkdir()
    if xdg_downloads:
        (config / "user-dirs.dirs").write_text(
            'XDG_DOWNLOAD_DIR="$HOME/Custom Downloads"\n', encoding="utf-8"
        )
    env = os.environ.copy()
    env.update(
        HOME=str(home),
        XDG_CONFIG_HOME=str(config),
        XDG_DATA_HOME=str(data),
        LC_ALL=locale_name,
        LC_MESSAGES=locale_name,
        LANG=locale_name,
    )
    script = dedent(
        """
        import _ctypes
        import ctypes
        import ctypes.util
        import os
        import sys
        import types
        from pathlib import Path

        assert sys.platform == "linux"
        assert isinstance(ctypes, types.ModuleType)
        assert ctypes.Structure is _ctypes.Structure
        assert not hasattr(ctypes, "windll")
        assert not hasattr(ctypes, "WinDLL")
        native_cdll = ctypes.CDLL
        source = Path(sys.argv[1])
        sys.path.insert(0, str(source))
        wx = types.ModuleType("wx")
        wx.LANGUAGE_ARABIC = 1
        wx.LANGUAGE_ENGLISH = 2
        sys.modules["wx"] = wx

        import language_handler
        import paths
        import settings_handler
        from media_player import mpv_backend

        assert language_handler.ctypes is ctypes
        assert mpv_backend.ctypes is ctypes
        assert ctypes.CDLL is native_cdll
        assert not hasattr(ctypes, "windll")
        assert issubclass(mpv_backend.MpvNode, ctypes.Structure)
        assert issubclass(mpv_backend.MpvNodeUnion, ctypes.Union)
        node = mpv_backend.MpvNode()
        node.format = mpv_backend.MPV_FORMAT_INT64
        node.u.int64 = 2**40
        pointer = ctypes.pointer(node)
        assert pointer.contents.u.int64 == 2**40
        assert ctypes.sizeof(node) > ctypes.sizeof(ctypes.c_int64)
        assert mpv_backend._mpv_lib is None
        assert language_handler.get_default_language() == sys.argv[2]
        assert language_handler._("startup") == "startup"
        assert Path(paths.get_app_path()) == source
        assert Path(paths.get_config_root()) == Path(os.environ["XDG_CONFIG_HOME"])
        assert Path(paths.get_data_root()) == Path(os.environ["XDG_DATA_HOME"])
        expected_settings = source / "data" if paths.portable else Path(os.environ["XDG_DATA_HOME"]) / "HexPlayer"
        assert Path(paths.settings_path) == expected_settings
        assert Path(paths.pot_provider_exe).name == "bgutil-pot"
        assert Path(paths.deno_install_path).name == "deno"
        expected_download = Path(os.environ["HOME"]) / sys.argv[3] / "HexPlayer"
        assert Path(paths.get_default_download_dir()) == expected_download
        assert Path(settings_handler.defaults["path"]) == expected_download
        assert settings_handler.defaults["lang"] == sys.argv[2]
        assert settings_handler.defaults["audiooutputdevice"] == ""
        assert settings_handler.defaults["volume"] == 100
        print("linux-startup-ok")
        """
    )
    result = subprocess.run(
        [
            sys.executable,
            "-I",
            "-c",
            script,
            str(source),
            expected_language,
            "Custom Downloads" if xdg_downloads else "Downloads",
        ],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.strip() == "linux-startup-ok"

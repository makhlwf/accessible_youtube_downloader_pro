"""Installation and updates for external runtime dependencies."""

import json
import logging
import os
import platform
import re
import subprocess
import sys
import zipfile

import requests
import wx

import paths
from app_runtime.desktop import show_error
from app_state.settings_handler import config_get
from language_handler import _
from youtube_backend import ytdlp_runtime
from youtube_backend.deno_service import deno_service
from youtube_backend.pot_provider_service import pot_service
from youtube_backend.ytdlp_runtime import load_yt_dlp

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


YOUTUBEI_PACKAGE = "youtubei.js"
YOUTUBEI_IMPORT_SPECIFIER = "youtubei.js"


def download_yt_dlp(parent=None):
    from gui.update_dialog import UpdateDialog

    url = "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp"
    os.makedirs(paths.settings_path, exist_ok=True)
    target_path = os.path.join(paths.settings_path, "yt_dlp.zip")
    download_path = f"{target_path}.download"
    try:
        if os.path.exists(download_path):
            os.remove(download_path)
    except OSError:
        pass

    UpdateDialog(
        parent or (wx.GetApp().GetTopWindow() if wx.GetApp() else None),
        url,
        download_path,
        _("جاري تنزيل واي تي دي إل بي"),
    )

    if os.path.exists(download_path):
        if zipfile.is_zipfile(download_path):
            os.replace(download_path, target_path)
        else:
            try:
                os.remove(download_path)
            except OSError:
                pass
            show_error(_("ملف واي تي دي إل بي الذي تم تنزيله غير صالح"))

    paths.yt_dlp_path = (
        target_path if os.path.exists(target_path) else paths._get_yt_dlp_path()
    )
    load_yt_dlp(force=True)


def get_latest_github_release(repo):
    url = f"https://api.github.com/repos/{repo}/releases/latest"
    try:
        r = requests.get(url, timeout=10)
        if r.status_code == 200:
            return r.json().get("tag_name")
    except Exception as e:
        logger.error(f"Failed to get latest release for {repo}: {e}")
    return None


def get_latest_npm_package_version(package):
    url = f"https://registry.npmjs.org/{package}/latest"
    try:
        r = requests.get(url, timeout=10)
        if r.status_code == 200:
            return r.json().get("version")
    except Exception as e:
        logger.error(f"Failed to get latest npm version for {package}: {e}")
    return None


def _read_json_file(path):
    try:
        with open(path, "r", encoding="utf-8") as file:
            return json.load(file)
    except Exception:
        return None


def _version_from_youtubei_specifier(specifier):
    if not specifier:
        return None
    match = re.search(r"(?:npm:)?youtubei\.js@([^\s\"',}]+)", str(specifier))
    if not match:
        return None
    version = match.group(1).strip()
    return version.lstrip("^~<>= ")


def _read_youtubei_lock_version(lock_path):
    data = _read_json_file(lock_path)
    if not isinstance(data, dict):
        return None

    npm_entries = data.get("npm", {})
    if isinstance(npm_entries, dict):
        for name in npm_entries:
            match = re.fullmatch(r"youtubei\.js@(.+)", name)
            if match:
                return match.group(1)

    specifiers = data.get("specifiers", {})
    if isinstance(specifiers, dict):
        for key, value in specifiers.items():
            if str(key).startswith("npm:youtubei.js@"):
                version = str(value).strip()
                if version:
                    return version

    return None


def _read_youtubei_config_version(config_path):
    data = _read_json_file(config_path)
    if not isinstance(data, dict):
        return None

    imports = data.get("imports", {})
    if not isinstance(imports, dict):
        return None
    return _version_from_youtubei_specifier(imports.get(YOUTUBEI_IMPORT_SPECIFIER))


def get_youtubei_version():
    version = _read_youtubei_lock_version(paths.get_js_runtime_lock_path())
    if version:
        return version
    return _read_youtubei_config_version(paths.get_js_runtime_config_path())


def _semver_key(version):
    match = re.match(r"^v?(\d+)(?:\.(\d+))?(?:\.(\d+))?", str(version or ""))
    if not match:
        return None
    return tuple(int(part or 0) for part in match.groups())


def _is_newer_version(latest, current):
    if not latest:
        return False
    if not current:
        return True
    latest_key = _semver_key(latest)
    current_key = _semver_key(current)
    if latest_key and current_key:
        return latest_key > current_key
    return latest != current


def _write_youtubei_runtime_config(version):
    config_path = paths.get_writable_js_runtime_file("deno.json")
    config = {
        "imports": {YOUTUBEI_IMPORT_SPECIFIER: f"npm:{YOUTUBEI_PACKAGE}@{version}"}
    }
    temp_path = f"{config_path}.tmp"
    with open(temp_path, "w", encoding="utf-8") as file:
        json.dump(config, file, ensure_ascii=False, indent=2)
        file.write("\n")
    os.replace(temp_path, config_path)
    return config_path


def _deno_cache_command(config_path, lock_path, reload_package=False):
    command = [
        paths.get_deno_path(),
        "cache",
        "--config",
        config_path,
        "--lock",
        lock_path,
    ]
    if reload_package:
        command.append(f"--reload=npm:{YOUTUBEI_PACKAGE}")
    command.append(paths.get_js_runtime_service_script())
    return command


def _run_deno_cache(config_path, lock_path, reload_package=False):
    env = os.environ.copy()
    env["PATH"] = paths.main_path + os.pathsep + env.get("PATH", "")
    return subprocess.run(
        _deno_cache_command(config_path, lock_path, reload_package=reload_package),
        creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        env=env,
        cwd=paths.main_path,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=180,
        check=False,
    )


def install_youtubei_version(version, parent=None, success_message=None):
    if not os.path.exists(paths.get_deno_path()):
        if paths.get_youtube_service_path():
            return update_youtube_service(parent=parent)
        show_error(
            _(
                "لم يتم العثور على أداة deno.exe, وهي مطلوبة لتحديث مكتبة YouTube.js (Innertube)."
            ),
            parent=parent,
        )
        return False

    try:
        config_path = _write_youtubei_runtime_config(version)
        lock_path = paths.get_writable_js_runtime_file("deno.lock")
        result = _run_deno_cache(config_path, lock_path, reload_package=True)
        if result.returncode != 0:
            detail = result.stderr.strip() or result.stdout.strip()
            show_error(
                _("تعذر تحديث مكتبة YouTube.js (Innertube)"),
                Exception(detail),
                parent=parent,
            )
            return False

        deno_service.stop()
        wx.MessageBox(
            success_message
            or _("تم تحديث مكتبة YouTube.js (Innertube) إلى الإصدار {}").format(
                version
            ),
            _("اكتمل التحديث"),
            parent=parent or wx.GetApp().GetTopWindow(),
        )
        return True
    except Exception as e:
        show_error(_("تعذر تحديث مكتبة YouTube.js (Innertube)"), e, parent=parent)
        return False


def update_youtubei(parent=None):
    current = get_youtubei_version()
    latest = get_latest_npm_package_version(YOUTUBEI_PACKAGE)
    if not latest:
        show_error(
            _("تعذر الحصول على معلومات تحديث مكتبة YouTube.js (Innertube) من npm"),
            parent=parent,
        )
        return False

    if not _is_newer_version(latest, current):
        wx.MessageBox(
            _(
                "أنت تستخدم بالفعل أحدث إصدار من مكتبة YouTube.js (Innertube) ({})"
            ).format(current or latest),
            _("لا يوجد تحديث"),
            parent=parent or wx.GetApp().GetTopWindow(),
        )
        return True

    msg = wx.MessageBox(
        _(
            "هناك إصدار جديد متوفر من مكتبة YouTube.js (Innertube)\nالإصدار الحالي: {}\nالإصدار الأحدث: {}\nهل تريد التحديث الآن؟"
        ).format(current or _("غير معروف"), latest),
        _("تحديث متوفر"),
        style=wx.YES_NO | wx.ICON_INFORMATION,
        parent=parent or wx.GetApp().GetTopWindow(),
    )
    if msg == wx.YES:
        return install_youtubei_version(latest, parent=parent)
    return False


def refresh_youtubei_cache(parent=None):
    version = get_youtubei_version()
    if not version:
        show_error(
            _("تعذر تحديد إصدار مكتبة YouTube.js (Innertube) الحالي"),
            parent=parent,
        )
        return False
    return install_youtubei_version(
        version,
        parent=parent,
        success_message=_("تم تحديث ذاكرة مكتبة YouTube.js (Innertube) المؤقتة"),
    )


def get_yt_dlp_version():
    if ytdlp_runtime.yt_dlp_module:
        try:
            if hasattr(ytdlp_runtime.yt_dlp_module, "version"):
                return getattr(ytdlp_runtime.yt_dlp_module.version, "__version__", None)
            return getattr(ytdlp_runtime.yt_dlp_module, "__version__", None)
        except Exception:
            pass
    return None


def update_yt_dlp():
    current = get_yt_dlp_version()
    latest = get_latest_github_release("yt-dlp/yt-dlp")
    if not latest:
        show_error(
            _("تعذر الحصول على معلومات التحديث من غيت هاب"),
        )
        return

    if current == latest:
        wx.MessageBox(
            _("أنت تستخدم بالفعل أحدث إصدار من واي تي دي إل بي ({})").format(current),
            _("لا يوجد تحديث"),
            parent=wx.GetApp().GetTopWindow(),
        )
    else:
        msg = wx.MessageBox(
            _(
                "هناك إصدار جديد متوفر من واي تي دي إل بي\nالإصدار الحالي: {}\nالإصدار الأحدث: {}\nهل تريد التحديث الآن؟"
            ).format(current or _("غير معروف"), latest),
            _("تحديث متوفر"),
            style=wx.YES_NO | wx.ICON_INFORMATION,
            parent=wx.GetApp().GetTopWindow(),
        )
        if msg == wx.YES:
            download_yt_dlp()


def _deno_release_asset():
    machine = platform.machine().lower()
    arch = {
        "amd64": "x86_64",
        "x86_64": "x86_64",
        "arm64": "aarch64",
        "aarch64": "aarch64",
    }.get(machine)
    target = {"win32": "pc-windows-msvc", "linux": "unknown-linux-gnu"}.get(
        sys.platform
    )
    if not arch or not target:
        raise RuntimeError(f"Unsupported Deno platform: {sys.platform}/{machine}")
    return f"deno-{arch}-{target}.zip"


def download_deno(parent=None):
    from gui.update_dialog import UpdateDialog

    url = f"https://github.com/denoland/deno/releases/latest/download/{_deno_release_asset()}"
    install_dir = os.path.dirname(paths.deno_install_path)
    os.makedirs(install_dir, exist_ok=True)
    UpdateDialog(
        parent or (wx.GetApp().GetTopWindow() if wx.GetApp() else None),
        url,
        os.path.join(install_dir, "deno.zip"),
        _("جاري تنزيل دينو"),
        is_zip=True,
    )


def get_deno_version():
    if not os.path.exists(paths.get_deno_path()):
        return None
    try:
        result = subprocess.run(
            [paths.get_deno_path(), "--version"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
            check=False,
        )
        if result.returncode == 0:
            line = result.stdout.splitlines()[0]
            version = line.split(" ")[1]
            if not version.startswith("v"):
                version = "v" + version
            return version
    except Exception:
        pass
    return None


def update_deno():
    current = get_deno_version()
    latest = get_latest_github_release("denoland/deno")
    if not latest:
        show_error(
            _("تعذر الحصول على معلومات التحديث من غيت هاب"),
        )
        return

    if current == latest:
        wx.MessageBox(
            _("أنت تستخدم بالفعل أحدث إصدار من دينو ({})").format(current),
            _("لا يوجد تحديث"),
            parent=wx.GetApp().GetTopWindow(),
        )
    else:
        msg = wx.MessageBox(
            _(
                "هناك إصدار جديد متوفر من دينو\nالإصدار الحالي: {}\nالإصدار الأحدث: {}\nهل تريد التحديث الآن؟"
            ).format(current or _("غير معروف"), latest),
            _("تحديث متوفر"),
            style=wx.YES_NO | wx.ICON_INFORMATION,
            parent=wx.GetApp().GetTopWindow(),
        )
        if msg == wx.YES:
            download_deno()


def download_youtube_service(parent=None):
    from gui.update_dialog import UpdateDialog

    binary_name = (
        "youtube_service.exe" if sys.platform == "win32" else "youtube_service"
    )
    url = f"https://github.com/makhlwf/accessible_youtube_downloader_pro/releases/latest/download/{binary_name}"
    install_target = paths.youtube_service_install_path
    os.makedirs(os.path.dirname(install_target), exist_ok=True)
    UpdateDialog(
        parent or (wx.GetApp().GetTopWindow() if wx.GetApp() else None),
        url,
        install_target,
        _("جاري تنزيل خدمة يوتيوب المدمجة"),
        is_zip=False,
    )
    return os.path.exists(install_target)


def get_youtube_service_version():
    exe_path = paths.get_youtube_service_path()
    if not exe_path or not os.path.exists(exe_path):
        return None
    try:
        result = subprocess.run(
            [exe_path, "--version"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
            timeout=5,
            check=False,
        )
        if result.returncode == 0:
            line = result.stdout.strip().splitlines()[0]
            parts = line.split(" ")
            version = parts[1] if len(parts) >= 2 else line
            if not version.startswith("v"):
                version = "v" + version
            return version
    except Exception:
        pass
    return None


def update_youtube_service(parent=None):
    current = get_youtube_service_version()
    latest = get_latest_github_release("makhlwf/accessible_youtube_downloader_pro")
    if not latest:
        show_error(
            _("تعذر الحصول على معلومات التحديث من غيت هاب"),
            parent=parent,
        )
        return False

    if (current or "").lstrip("v") == (latest or "").lstrip("v"):
        wx.MessageBox(
            _("أنت تستخدم بالفعل أحدث إصدار من خدمة يوتيوب المدمجة ({})").format(
                current or latest
            ),
            _("لا يوجد تحديث"),
            parent=parent or (wx.GetApp().GetTopWindow() if wx.GetApp() else None),
        )
        return True
    else:
        msg = wx.MessageBox(
            _(
                "هناك إصدار جديد متوفر من خدمة يوتيوب المدمجة\nالإصدار الحالي: {}\nالإصدار الأحدث: {}\nهل تريد التحديث الآن؟"
            ).format(current or _("غير معروف"), latest),
            _("تحديث متوفر"),
            style=wx.YES_NO | wx.ICON_INFORMATION,
            parent=parent or (wx.GetApp().GetTopWindow() if wx.GetApp() else None),
        )
        if msg == wx.YES:
            return download_youtube_service(parent=parent)
        return False


def check_yt_dlp(parent=None):
    if not ytdlp_runtime.YoutubeDL:
        # yt-dlp is loaded lazily now; try to bring it in before concluding it
        # is missing, so we only prompt to download when it is genuinely absent.
        load_yt_dlp()
    if not ytdlp_runtime.YoutubeDL:
        msg = wx.MessageBox(
            _("لم يتم العثور على مكتبة واي تي دي إل بي, هل تريد تنزيلها الآن؟"),
            _("تنبيه"),
            style=wx.YES_NO | wx.ICON_INFORMATION,
            parent=parent or wx.GetApp().GetTopWindow(),
        )
        if msg == wx.YES:
            download_yt_dlp()
            return ytdlp_runtime.YoutubeDL is not None
        return False
    return True


def check_deno(parent=None):
    yt_service = paths.get_youtube_service_path()
    if yt_service and os.path.exists(yt_service):
        return True
    if not os.path.exists(paths.get_deno_path()):
        msg = wx.MessageBox(
            _(
                "لم يتم العثور على أداة deno.exe, وهي مطلوبة لبعض وظائف اليوتيوب. هل تريد تنزيلها الآن؟"
            ),
            _("تنبيه"),
            style=wx.YES_NO | wx.ICON_INFORMATION,
            parent=parent or wx.GetApp().GetTopWindow(),
        )
        if msg == wx.YES:
            download_deno()
            return os.path.exists(paths.get_deno_path())
        return False
    return True


def get_pot_provider_version():
    """Returns the installed version string of bgutil-pot, or None if not installed."""
    return pot_service.get_installed_version()


def update_pot_provider(parent=None):
    """Checks for bgutil-pot updates on GitHub and prompts the user to download if newer."""
    current = get_pot_provider_version()
    latest = get_latest_github_release("jim60105/bgutil-ytdlp-pot-provider-rs")
    if not latest:
        show_error(
            _("تعذر الحصول على معلومات التحديث من غيت هاب"),
            parent=parent or (wx.GetApp().GetTopWindow() if wx.GetApp() else None),
        )
        return False

    if (current or "").lstrip("v") == (latest or "").lstrip("v"):
        wx.MessageBox(
            _("أنت تستخدم بالفعل أحدث إصدار من مولد رموز POT ({})").format(current),
            _("لا يوجد تحديث"),
            parent=parent or (wx.GetApp().GetTopWindow() if wx.GetApp() else None),
        )
        return False
    else:
        msg = wx.MessageBox(
            _(
                "هناك إصدار جديد متوفر من مولد رموز POT\nالإصدار الحالي: {}\nالإصدار الأحدث: {}\nهل تريد التحديث الآن؟"
            ).format(current or _("غير معروف"), latest),
            _("تحديث متوفر"),
            style=wx.YES_NO | wx.ICON_INFORMATION,
            parent=parent or (wx.GetApp().GetTopWindow() if wx.GetApp() else None),
        )
        if msg == wx.YES:
            return pot_service.download_and_install(parent=parent)
        return False


def check_pot_provider(parent=None):
    """Ensures bgutil-pot is installed and running if enabled, prompting download if missing."""
    if not config_get("pot_provider_enabled"):
        return False
    if not pot_service.is_installed():
        msg = wx.MessageBox(
            _(
                "لم يتم العثور على أداة مولد رموز POT (bgutil-pot)، وهي تساعد في حل قيود يوتيوب وتحسين التنزيل. هل تريد تنزيلها الآن؟"
            ),
            _("تنبيه"),
            style=wx.YES_NO | wx.ICON_INFORMATION,
            parent=parent or (wx.GetApp().GetTopWindow() if wx.GetApp() else None),
        )
        if msg == wx.YES:
            return pot_service.download_and_install(parent=parent)
        return False
    pot_service.ensure_started()
    return True


def ensure_deno_installed(parent=None, feature_name=None, **kwargs):
    """
    Checks if the JS runtime (youtube_service.exe or deno.exe) is installed.
    Returns True if available or installed, False otherwise.
    """
    yt_service = paths.get_youtube_service_path()
    if yt_service and os.path.exists(yt_service):
        return True
    if not os.path.exists(paths.get_deno_path()):
        feature = feature_name or kwargs.get("feature_name_ar") or _("هذه الميزة")
        msg_text = _(
            "تنبيه: لم يتم تثبيت أداة Deno وهي مطلوبة لـ {}. هل تريد تنزيل وتثبيت Deno الآن؟"
        ).format(feature)
        title = _("تنبيه")
        dialog_parent = parent or (wx.GetApp().GetTopWindow() if wx.GetApp() else None)
        res = wx.MessageBox(
            msg_text,
            title,
            style=wx.YES_NO | wx.ICON_WARNING,
            parent=dialog_parent,
        )
        if res == wx.YES:
            download_deno(dialog_parent)
            return os.path.exists(paths.get_deno_path())
        return False
    return True


def ensure_js_dependencies():
    """Silently ensure JavaScript dependencies are cached by Deno."""
    if not os.path.exists(paths.get_deno_path()):
        return

    service_script = paths.get_js_runtime_service_script()
    config_path = paths.get_js_runtime_config_path()
    lock_path = paths.get_js_runtime_lock_path()

    if not os.path.exists(service_script) or not os.path.exists(config_path):
        return

    def _cache_task():
        try:
            if os.path.exists(lock_path):
                _run_deno_cache(config_path, lock_path)
            else:
                env = os.environ.copy()
                env["PATH"] = paths.main_path + os.pathsep + env.get("PATH", "")
                subprocess.run(
                    [
                        paths.get_deno_path(),
                        "cache",
                        "--config",
                        config_path,
                        service_script,
                    ],
                    creationflags=subprocess.CREATE_NO_WINDOW
                    if sys.platform == "win32"
                    else 0,
                    env=env,
                    cwd=paths.main_path,
                    check=False,
                )
        except Exception:
            pass

    import threading

    threading.Thread(target=_cache_task, daemon=True).start()

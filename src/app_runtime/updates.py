"""HexPlayer release selection and update checks."""

import logging
import os
import platform
import sys

import requests
import wx

import application
from app_runtime.desktop import show_error
from language_handler import _

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


def _app_update_platform_target():
    if sys.platform == "win32":
        return "windows", "x86_64"
    if sys.platform.startswith("linux"):
        machine = platform.machine().lower()
        arch = {
            "amd64": "x86_64",
            "x86_64": "x86_64",
            "arm64": "aarch64",
            "aarch64": "aarch64",
        }.get(machine)
        if arch:
            return "linux", arch
    return None, None


RELEASES_PAGE_URL = (
    "https://github.com/makhlwf/accessible_youtube_downloader_pro/releases"
)


def _detect_linux_distro_family(os_release_data=None):
    override = os.environ.get("HEXPLAYER_DISTRO_OVERRIDE", "").strip().lower()
    if override:
        if override in ("fedora", "rhel", "centos", "rocky", "almalinux", "rpm"):
            return "fedora"
        if override in ("debian", "ubuntu", "linuxmint", "pop", "deb"):
            return "debian"
        return override

    data = os_release_data
    if data is None:
        os_file = os.environ.get("OS_RELEASE_FILE")
        if os_file:
            if os.path.isfile(os_file):
                data = _parse_os_release_file(os_file)
            else:
                data = {}
        else:
            try:
                if hasattr(platform, "freedesktop_os_release"):
                    data = platform.freedesktop_os_release()
            except OSError:
                data = {}
            if not data:
                for candidate in ("/etc/os-release", "/usr/lib/os-release"):
                    if os.path.isfile(candidate):
                        data = _parse_os_release_file(candidate)
                        break

    if not data or not isinstance(data, dict):
        return "unknown"

    distro_id = str(data.get("ID", "")).lower().strip("\"' ")
    distro_like = str(data.get("ID_LIKE", "")).lower().strip("\"' ")
    tokens = {distro_id} | set(distro_like.split())

    fedora_tokens = {
        "fedora",
        "rhel",
        "centos",
        "rocky",
        "almalinux",
        "ol",
        "scientific",
    }
    debian_tokens = {
        "debian",
        "ubuntu",
        "linuxmint",
        "pop",
        "elementary",
        "zorin",
        "kali",
        "raspbian",
    }

    if distro_id in fedora_tokens:
        return "fedora"
    if distro_id in debian_tokens:
        return "debian"
    if tokens & fedora_tokens:
        return "fedora"
    if tokens & debian_tokens:
        return "debian"
    return "unknown"


def _parse_os_release_file(path):
    data = {}
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, val = line.split("=", 1)
                key = key.strip()
                val = val.strip().strip("\"'")
                data[key] = val
    except OSError:
        pass
    return data


def _extract_candidate_urls(entry):
    urls = []
    if isinstance(entry, str):
        urls.append(entry)
    elif isinstance(entry, dict):
        for k in ("url", "browser_download_url"):
            v = entry.get(k)
            if isinstance(v, str):
                urls.append(v)
        for k, v in entry.items():
            if k not in ("url", "browser_download_url"):
                urls.extend(_extract_candidate_urls(v))
    elif isinstance(entry, (list, tuple)):
        for item in entry:
            urls.extend(_extract_candidate_urls(item))
    return urls


def _linux_release_asset_url(url, arch, distro=None):
    if not isinstance(url, str):
        return ""
    if not url.startswith("https://github.com/"):
        return ""

    rpm_suffixes = [
        f"-1.{arch}.rpm",
        f"-linux-{arch}.rpm",
        f"-{arch}.rpm",
        f".{arch}.rpm",
    ]
    deb_suffixes = [
        f"-linux-{arch}.deb",
        f"-{arch}.deb",
        f"_{arch}.deb",
        f".{arch}.deb",
    ]
    if arch in ("x86_64", "amd64"):
        deb_suffixes.extend(
            ["-linux-amd64.deb", "-amd64.deb", "_amd64.deb", ".amd64.deb"]
        )
    elif arch == "aarch64":
        deb_suffixes.extend(
            ["-linux-arm64.deb", "-arm64.deb", "_arm64.deb", ".arm64.deb"]
        )

    tar_suffixes = [
        f"-linux-{arch}.tar.xz",
        f"-{arch}.tar.xz",
        f"-linux-{arch}.tar.gz",
        f"-{arch}.tar.gz",
    ]

    if distro == "fedora":
        suffixes = rpm_suffixes + tar_suffixes
    elif distro == "debian":
        suffixes = deb_suffixes + tar_suffixes
    else:
        suffixes = rpm_suffixes + deb_suffixes + tar_suffixes

    for suffix in suffixes:
        if url.endswith(suffix):
            return url
    return ""


def _select_app_update(info):
    platform_key, arch = _app_update_platform_target()
    if not platform_key:
        return RELEASES_PAGE_URL, False
    if platform_key == "windows":
        url = info.get("url") if isinstance(info, dict) else None
        return (url if isinstance(url, str) else ""), bool(url)

    distro = _detect_linux_distro_family()
    platforms = info.get("platforms") if isinstance(info, dict) else None

    candidates = []
    if isinstance(platforms, dict):
        if distro and distro in platforms:
            candidates.extend(_extract_candidate_urls(platforms[distro]))
        if distro == "fedora" and "rpm" in platforms:
            candidates.extend(_extract_candidate_urls(platforms["rpm"]))
        elif distro == "debian":
            for deb_key in ("ubuntu", "deb"):
                if deb_key in platforms:
                    candidates.extend(_extract_candidate_urls(platforms[deb_key]))

        if platform_key in platforms:
            candidates.extend(_extract_candidate_urls(platforms[platform_key]))

        for k, v in platforms.items():
            if k not in (distro, platform_key, "rpm", "deb", "ubuntu"):
                candidates.extend(_extract_candidate_urls(v))

    if isinstance(info, dict) and "assets" in info:
        candidates.extend(_extract_candidate_urls(info["assets"]))

    valid_urls = []
    seen = set()
    for cand in candidates:
        matched = _linux_release_asset_url(cand, arch, distro=distro)
        if matched and matched not in seen:
            seen.add(matched)
            valid_urls.append(matched)

    if not valid_urls:
        return RELEASES_PAGE_URL, False

    def _rank_url(u):
        if distro == "fedora":
            if u.endswith(".rpm"):
                return 0
            if u.endswith((".tar.gz", ".tar.xz")):
                return 1
            return 2
        elif distro == "debian":
            if u.endswith(".deb"):
                return 0
            if u.endswith((".tar.gz", ".tar.xz")):
                return 1
            return 2
        else:
            if u.endswith((".rpm", ".deb")):
                return 0
            return 1

    valid_urls.sort(key=_rank_url)
    return valid_urls[0], True


def check_for_updates(quiet=False):
    new_url = "https://raw.githubusercontent.com/makhlwf/accessible_youtube_downloader_pro/refs/heads/master/update.json"
    old_url = "https://raw.githubusercontent.com/makhlwf/accessible_youtube_downloader_pro/refs/heads/master/update_info.json"
    try:
        r = requests.get(new_url, timeout=10)
        if r.status_code == 200:
            info = r.json()
        else:
            r = requests.get(old_url, timeout=10)
            if r.status_code == 200:
                info = r.json()
            else:
                if not quiet:
                    show_error(
                        _(
                            "حدث خطأ ما أثناء الاتصال بخدمة العثور على التحديثات. تأكد من وجود اتصال مستقر بالإنترنت ثم عاود المحاولة"
                        ),
                    )
                return
        if application.version != info["version"]:
            url, in_app_download = _select_app_update(info)

            def show_update_dialog():
                from gui.update_check_dialog import UpdateCheckDialog

                new_version = info["version"]
                whats_new = info.get("whats_new", _("لا توجد معلومات حول هذا التحديث"))
                dlg = UpdateCheckDialog(
                    wx.GetApp().GetTopWindow(),
                    new_version,
                    whats_new,
                    url=url,
                    can_download=in_app_download,
                )
                if dlg.ShowModal() == wx.ID_OK and in_app_download:
                    from gui.update_dialog import UpdateDialog

                    UpdateDialog(
                        wx.GetApp().GetTopWindow(),
                        url,
                        title=_("جاري تنزيل التحديث"),
                    )
                dlg.Destroy()

            wx.CallAfter(show_update_dialog)
            return
        if not quiet:
            wx.CallAfter(
                wx.MessageBox,
                _("أنت تعمل الآن على آخر تحديث متوفر من التطبيق"),
                _("لا يوجد تحديث"),
                parent=wx.GetApp().GetTopWindow(),
            )
    except Exception as e:
        logger.error(f"Update check failed: {e}")
        if not quiet:
            show_error(
                _(
                    "حدث خطأ ما أثناء الاتصال بخدمة العثور على التحديثات. تأكد من وجود اتصال مستقر بالإنترنت ثم عاود المحاولة"
                ),
                e,
            )

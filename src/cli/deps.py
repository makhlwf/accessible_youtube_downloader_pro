"""Headless dependency management for the CLI: version reporting and updates.

Reuses the same download URLs, version helpers and (for the POT provider) the
same security-validated install routine as the GUI, but never opens a wx
dialog. Each update function returns ``(ok, message)`` with a localized
message.
"""

import os
import sys
import zipfile

import paths
import utils
from language_handler import _
from pot_provider_service import pot_service


def _http_download(url, dest, timeout=60):
    """Stream ``url`` to ``dest`` using requests (no GUI)."""
    import requests

    tmp = f"{dest}.part"
    os.makedirs(os.path.dirname(dest) or ".", exist_ok=True)
    with requests.get(
        url, stream=True, timeout=timeout, headers={"User-Agent": "HexPlayer"}
    ) as response:
        response.raise_for_status()
        with open(tmp, "wb") as handle:
            for chunk in response.iter_content(chunk_size=262144):
                if chunk:
                    handle.write(chunk)
    os.replace(tmp, dest)


def versions():
    """Return a dict of installed component versions (None when absent)."""
    return {
        "yt_dlp": utils.get_yt_dlp_version(),
        "deno": utils.get_deno_version(),
        "youtubei": utils.get_youtubei_version(),
        "pot_provider": utils.get_pot_provider_version(),
    }


def update_ytdlp():
    """Download the latest yt-dlp release headlessly. Returns ``(ok, message)``."""
    current = utils.get_yt_dlp_version()
    latest = utils.get_latest_github_release("yt-dlp/yt-dlp")
    if not latest:
        return False, _("تعذر الحصول على معلومات التحديث من غيت هاب")
    if current and current == latest:
        return True, _(
            "أنت تستخدم بالفعل أحدث إصدار من واي تي دي إل بي ({version})"
        ).format(version=current)

    url = "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp"
    os.makedirs(paths.settings_path, exist_ok=True)
    target = os.path.join(paths.settings_path, "yt_dlp.zip")
    download = f"{target}.download"
    try:
        _http_download(url, download)
    except Exception as error:
        return False, _("فشل تنزيل واي تي دي إل بي: {error}").format(error=error)

    if not zipfile.is_zipfile(download):
        try:
            os.remove(download)
        except OSError:
            pass
        return False, _("ملف واي تي دي إل بي الذي تم تنزيله غير صالح")

    os.replace(download, target)
    paths.yt_dlp_path = target
    utils.load_yt_dlp()
    new = utils.get_yt_dlp_version()
    return True, _("تم تحديث واي تي دي إل بي إلى الإصدار {version}").format(
        version=new or latest
    )


def update_deno():
    """Download and extract the latest Deno runtime. Returns ``(ok, message)``."""
    current = utils.get_deno_version()
    latest = utils.get_latest_github_release("denoland/deno")
    if not latest:
        return False, _("تعذر الحصول على معلومات التحديث من غيت هاب")
    if current and current == latest:
        return True, _("أنت تستخدم بالفعل أحدث إصدار من دينو ({version})").format(
            version=current
        )

    try:
        asset = utils._deno_release_asset()
    except Exception as error:
        return False, _("منصة غير مدعومة لأداة دينو: {error}").format(error=error)

    url = f"https://github.com/denoland/deno/releases/latest/download/{asset}"
    install_dir = os.path.dirname(paths.deno_install_path)
    os.makedirs(install_dir, exist_ok=True)
    zip_path = os.path.join(install_dir, "deno.zip")
    try:
        _http_download(url, zip_path)
    except Exception as error:
        return False, _("فشل تنزيل دينو: {error}").format(error=error)

    try:
        with zipfile.ZipFile(zip_path, "r") as archive:
            archive.extractall(install_dir)
    except Exception as error:
        return False, _("تعذر فك ضغط أداة دينو: {error}").format(error=error)
    finally:
        try:
            os.remove(zip_path)
        except OSError:
            pass

    deno_bin = paths.get_deno_path()
    if not os.path.exists(deno_bin):
        return False, _("تعذر العثور على أداة دينو بعد التثبيت")
    if sys.platform != "win32":
        try:
            os.chmod(deno_bin, 0o755)
        except OSError:
            pass
    new = utils.get_deno_version()
    return True, _("تم تحديث دينو إلى الإصدار {version}").format(version=new or latest)


def _install_youtubei(version):
    """Write the YouTube.js runtime config and warm the Deno cache (headless)."""
    from deno_service import deno_service

    try:
        config_path = utils._write_youtubei_runtime_config(version)
        lock_path = paths.get_writable_js_runtime_file("deno.lock")
        result = utils._run_deno_cache(config_path, lock_path, reload_package=True)
        if result.returncode != 0:
            detail = (result.stderr or result.stdout or "").strip()
            return False, detail
        deno_service.stop()
        return True, ""
    except Exception as error:
        return False, str(error)


def update_youtubei():
    """Update the youtubei.js (InnerTube) library via Deno. Returns ``(ok, message)``."""
    if not os.path.exists(paths.get_deno_path()):
        return False, _("تحديث مكتبة YouTube.js (Innertube) يتطلب تثبيت دينو أولاً")

    current = utils.get_youtubei_version()
    latest = utils.get_latest_npm_package_version(utils.YOUTUBEI_PACKAGE)
    if not latest:
        return False, _(
            "تعذر الحصول على معلومات تحديث مكتبة YouTube.js (Innertube) من npm"
        )
    if not utils._is_newer_version(latest, current):
        return True, _(
            "أنت تستخدم بالفعل أحدث إصدار من مكتبة YouTube.js (Innertube) ({version})"
        ).format(version=current or latest)

    ok, detail = _install_youtubei(latest)
    if ok:
        return True, _(
            "تم تحديث مكتبة YouTube.js (Innertube) إلى الإصدار {version}"
        ).format(version=latest)
    return False, _("تعذر تحديث مكتبة YouTube.js (Innertube): {error}").format(
        error=detail or _("خطأ غير معروف")
    )


def refresh_youtubei():
    """Re-warm the youtubei.js Deno cache for the current version."""
    if not os.path.exists(paths.get_deno_path()):
        return False, _("تحديث مكتبة YouTube.js (Innertube) يتطلب تثبيت دينو أولاً")
    version = utils.get_youtubei_version()
    if not version:
        return False, _("تعذر تحديد إصدار مكتبة YouTube.js (Innertube) الحالي")
    ok, detail = _install_youtubei(version)
    if ok:
        return True, _("تم تحديث ذاكرة مكتبة YouTube.js (Innertube) المؤقتة")
    return False, _(
        "تعذر تحديث ذاكرة مكتبة YouTube.js (Innertube) المؤقتة: {error}"
    ).format(error=detail or _("خطأ غير معروف"))


def update_pot():
    """Update the bgutil POT provider, reusing its validated installer headlessly."""
    current = utils.get_pot_provider_version()
    latest = utils.get_latest_github_release("jim60105/bgutil-ytdlp-pot-provider-rs")
    if not latest:
        return False, _("تعذر الحصول على معلومات التحديث من غيت هاب")
    if (current or "").lstrip("v") == (latest or "").lstrip("v"):
        return True, _(
            "أنت تستخدم بالفعل أحدث إصدار من مولد رموز POT ({version})"
        ).format(version=current)

    try:
        ok = pot_service.download_and_install(downloader=_http_download)
    except Exception as error:
        return False, _("تعذر تحديث مولد رموز POT: {error}").format(error=error)
    if ok:
        return True, _("تم تحديث مولد رموز POT إلى الإصدار {version}").format(
            version=latest
        )
    return False, _("تعذر تحديث مولد رموز POT")

import atexit
import json
import logging
import os
import subprocess
import sys
import threading
import time
import urllib.request
import zipfile

import requests

import paths
from settings_handler import config_get

logger = logging.getLogger(__name__)

GITHUB_REPO = "jim60105/bgutil-ytdlp-pot-provider-rs"
DOWNLOAD_EXE_NAME = "bgutil-pot-windows-x86_64.exe"
DOWNLOAD_ZIP_NAME = "bgutil-ytdlp-pot-provider-rs.zip"


class PotProviderService:
    def __init__(self):
        self.process = None
        self.lock = threading.Lock()
        self._initialized = False

    def get_port(self):
        return int(config_get("pot_provider_port") or 4416)

    def get_base_url(self):
        return f"http://127.0.0.1:{self.get_port()}"

    def initialize(self):
        plugins_dir = os.path.abspath(paths.pot_provider_plugins_dir)
        if self._initialized and plugins_dir in sys.path:
            return
        if os.path.exists(plugins_dir) and plugins_dir not in sys.path:
            sys.path.insert(0, plugins_dir)
            logger.debug(f"Added POT provider plugins to sys.path: {plugins_dir}")
        self._initialized = True

    def is_installed(self):
        return os.path.isfile(paths.pot_provider_exe) and os.path.isdir(
            paths.pot_provider_plugins_dir
        )

    def has_binary(self):
        return os.path.isfile(paths.pot_provider_exe)

    def is_running(self):
        with self.lock:
            return self.process is not None and self.process.poll() is None

    def is_healthy(self):
        try:
            url = f"{self.get_base_url()}/ping"
            req = urllib.request.Request(url, headers={"User-Agent": "HexPlayer"})
            with urllib.request.urlopen(req, timeout=1.5) as resp:
                return resp.status == 200
        except Exception:
            return False

    def is_available(self):
        return self.is_installed() and (self.is_running() or self.is_healthy())

    def start(self):
        with self.lock:
            if self.process and self.process.poll() is None and self.is_healthy():
                return True

            if not os.path.isfile(paths.pot_provider_exe):
                logger.warning("POT provider binary does not exist.")
                return False

            self.initialize()
            port = self.get_port()
            cmd = [
                paths.pot_provider_exe,
                "server",
                "--host",
                "127.0.0.1",
                "--port",
                str(port),
            ]

            try:
                creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
                self.process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    creationflags=creationflags,
                    text=True,
                    encoding="utf-8",
                )
                logger.info(f"Started POT provider background server on port {port}.")
            except Exception as e:
                logger.error(f"Failed to start POT provider process: {e}")
                self.process = None
                return False

        # Wait for health check up to 3 seconds outside the lock
        start_time = time.time()
        while time.time() - start_time < 3.0:
            if self.is_healthy():
                logger.info("POT provider server ping check succeeded.")
                return True
            if not self.is_running():
                logger.warning("POT provider server process terminated unexpectedly.")
                return False
            time.sleep(0.15)

        logger.warning("POT provider server started but ping check timed out.")
        return False

    def stop(self):
        with self.lock:
            if not self.process:
                return
            try:
                self.process.kill()
                self.process.wait(timeout=2.0)
            except Exception:
                pass
            self.process = None
            logger.info("POT provider server stopped.")

    def ensure_started(self):
        if not config_get("pot_provider_enabled"):
            return False
        if not self.is_installed():
            return False
        if self.is_running() and self.is_healthy():
            return True
        return self.start()

    def get_installed_version(self):
        if os.path.exists(paths.pot_provider_version_file):
            try:
                with open(paths.pot_provider_version_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    return data.get("version")
            except Exception:
                pass

        if os.path.isfile(paths.pot_provider_exe):
            try:
                res = subprocess.run(
                    [paths.pot_provider_exe, "--version"],
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                    timeout=5,
                    check=False,
                )
                if res.returncode == 0:
                    line = res.stdout.strip()
                    parts = line.split(" ")
                    if len(parts) >= 2:
                        return f"v{parts[1]}"
                    return line
            except Exception:
                pass
        return None

    def download_and_install(self, parent=None):
        from gui.update_dialog import UpdateDialog

        try:
            from language_handler import _
        except Exception:

            def _(s):
                return s

        os.makedirs(paths.pot_provider_dir, exist_ok=True)

        api_url = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
        try:
            r = requests.get(api_url, timeout=10)
            if r.status_code != 200:
                return False
            release_data = r.json()
            tag_name = release_data.get("tag_name")
            assets = release_data.get("assets", [])
        except Exception as e:
            logger.error(f"Failed to fetch POT release info: {e}")
            return False

        exe_url = None
        zip_url = None
        for asset in assets:
            if asset.get("name") == DOWNLOAD_EXE_NAME:
                exe_url = asset.get("browser_download_url")
            elif asset.get("name") == DOWNLOAD_ZIP_NAME:
                zip_url = asset.get("browser_download_url")

        if not exe_url or not zip_url:
            logger.error("Required release assets not found.")
            return False

        self.stop()

        # Download exe
        tmp_exe = os.path.join(paths.pot_provider_dir, "bgutil-pot.exe.download")
        UpdateDialog(
            parent,
            exe_url,
            tmp_exe,
            _("جاري تنزيل أداة مولد رموز POT"),
            is_zip=False,
        )
        if not os.path.exists(tmp_exe):
            return False

        # Download zip
        tmp_zip = os.path.join(paths.pot_provider_dir, "plugins.zip.download")
        UpdateDialog(
            parent,
            zip_url,
            tmp_zip,
            _("جاري تنزيل ملحق واي تي دي إل بي لـ POT"),
            is_zip=False,
        )
        if not os.path.exists(tmp_zip):
            try:
                os.remove(tmp_exe)
            except OSError:
                pass
            return False

        # Replace exe
        if os.path.exists(paths.pot_provider_exe):
            try:
                os.remove(paths.pot_provider_exe)
            except OSError:
                pass
        os.replace(tmp_exe, paths.pot_provider_exe)

        # Extract zip into plugins directory
        os.makedirs(paths.pot_provider_plugins_dir, exist_ok=True)
        try:
            with zipfile.ZipFile(tmp_zip, "r") as z:
                z.extractall(paths.pot_provider_plugins_dir)
            os.remove(tmp_zip)
        except Exception as e:
            logger.error(f"Failed to extract POT plugins: {e}")
            return False

        # Write version file
        try:
            with open(paths.pot_provider_version_file, "w", encoding="utf-8") as f:
                json.dump({"version": tag_name}, f)
        except Exception:
            pass

        self._initialized = False
        self.initialize()

        if config_get("pot_provider_enabled"):
            self.start()

        return True


pot_service = PotProviderService()
atexit.register(pot_service.stop)

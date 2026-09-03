import atexit
import json
import logging
import os
import shutil
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
        val = config_get("pot_provider_port")
        try:
            port = int(val)
            if 1 <= port <= 65535:
                return port
        except ValueError:
            pass
        except TypeError:
            pass
        return 4416

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

    def _drain_output(self, proc):
        def _reader(stream, name):
            if not stream:
                return
            try:
                for line in stream:
                    if line:
                        logger.debug(f"POT provider {name}: {line.strip()}")
            except Exception:
                pass

        if proc.stdout:
            threading.Thread(
                target=_reader, args=(proc.stdout, "stdout"), daemon=True
            ).start()
        if proc.stderr:
            threading.Thread(
                target=_reader, args=(proc.stderr, "stderr"), daemon=True
            ).start()

    def start(self):
        with self.lock:
            if self.process and self.process.poll() is None:
                if self.is_healthy():
                    return True
                # Process is already running/starting up: do not spawn a second instance.
                # Fall through to the polling loop outside the lock.
            else:
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
                    self._drain_output(self.process)
                    logger.info(
                        f"Started POT provider background server on port {port}."
                    )
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

        logger.warning(
            "POT provider server started but ping check timed out. Stopping process."
        )
        self.stop()
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
            try:
                can_log = not (
                    sys.is_finalizing() if hasattr(sys, "is_finalizing") else False
                )
                if can_log:
                    curr = logger
                    while curr:
                        for h in getattr(curr, "handlers", []):
                            stream = getattr(h, "stream", None)
                            if stream and getattr(stream, "closed", False):
                                can_log = False
                                break
                        if not can_log or not getattr(curr, "propagate", True):
                            break
                        curr = getattr(curr, "parent", None)
                if can_log:
                    logger.info("POT provider server stopped.")
            except Exception:
                pass

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
                    version = parts[1] if len(parts) >= 2 else line
                    if not version.startswith("v"):
                        version = f"v{version}"
                    return version
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
            r = requests.get(
                api_url,
                headers={"User-Agent": "HexPlayer"},
                timeout=10,
            )
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
        exe_size = None
        zip_size = None
        for asset in assets:
            if asset.get("name") == DOWNLOAD_EXE_NAME:
                exe_url = asset.get("browser_download_url")
                exe_size = asset.get("size")
            elif asset.get("name") == DOWNLOAD_ZIP_NAME:
                zip_url = asset.get("browser_download_url")
                zip_size = asset.get("size")

        if not exe_url or not zip_url:
            logger.error("Required release assets not found.")
            return False

        was_running = self.is_running()

        tmp_exe = os.path.join(paths.pot_provider_dir, "bgutil-pot.exe.download")
        tmp_zip = os.path.join(paths.pot_provider_dir, "plugins.zip.download")
        staging_plugins_dir = os.path.join(paths.pot_provider_dir, "plugins.staging")
        for stale in (tmp_exe, tmp_zip):
            if os.path.exists(stale):
                try:
                    os.remove(stale)
                except OSError:
                    pass
        if os.path.exists(staging_plugins_dir):
            shutil.rmtree(staging_plugins_dir, ignore_errors=True)

        # Download exe first while service is still running
        UpdateDialog(
            parent,
            exe_url,
            tmp_exe,
            _("جاري تنزيل أداة مولد رموز POT"),
            is_zip=False,
        )
        if not os.path.exists(tmp_exe):
            return False

        # Validate executable size and binary header
        if exe_size is not None and os.path.getsize(tmp_exe) != exe_size:
            logger.error(
                f"Binary size mismatch for {tmp_exe}: expected {exe_size}, got {os.path.getsize(tmp_exe)}"
            )
            try:
                os.remove(tmp_exe)
            except OSError:
                pass
            return False

        try:
            with open(tmp_exe, "rb") as f:
                header = f.read(2)
            if header != b"MZ":
                logger.error(
                    f"Invalid executable format for {tmp_exe}: missing PE header"
                )
                try:
                    os.remove(tmp_exe)
                except OSError:
                    pass
                return False
        except Exception as e:
            logger.error(f"Failed to inspect binary header: {e}")
            try:
                os.remove(tmp_exe)
            except OSError:
                pass
            return False

        # Download zip while service is still running
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

        # Validate zip size
        if zip_size is not None and os.path.getsize(tmp_zip) != zip_size:
            logger.error(
                f"Zip size mismatch for {tmp_zip}: expected {zip_size}, got {os.path.getsize(tmp_zip)}"
            )
            for cleanup_path in (tmp_exe, tmp_zip):
                if os.path.exists(cleanup_path):
                    try:
                        os.remove(cleanup_path)
                    except OSError:
                        pass
            return False

        # Validate and extract zip into staging directory
        os.makedirs(staging_plugins_dir, exist_ok=True)
        try:
            if not zipfile.is_zipfile(tmp_zip):
                raise zipfile.BadZipFile("Not a valid zip file")
            with zipfile.ZipFile(tmp_zip, "r") as z:
                if z.testzip() is not None:
                    raise zipfile.BadZipFile("Zip file checksum mismatch")
                z.extractall(staging_plugins_dir)

            # Locate yt_dlp_plugins directory in extracted content
            direct_plugins = os.path.join(staging_plugins_dir, "yt_dlp_plugins")
            if not os.path.isdir(direct_plugins):
                # Look for nested yt_dlp_plugins (e.g. inside bgutil-ytdlp-pot-provider/)
                found_dir = None
                for root, dirs, _ in os.walk(staging_plugins_dir):
                    if "yt_dlp_plugins" in dirs:
                        found_dir = os.path.join(root, "yt_dlp_plugins")
                        break
                if found_dir:
                    temp_promote = os.path.join(
                        paths.pot_provider_dir, "yt_dlp_plugins.staging_promote"
                    )
                    if os.path.exists(temp_promote):
                        shutil.rmtree(temp_promote, ignore_errors=True)
                    shutil.move(found_dir, temp_promote)
                    shutil.rmtree(staging_plugins_dir, ignore_errors=True)
                    os.makedirs(staging_plugins_dir, exist_ok=True)
                    shutil.move(temp_promote, direct_plugins)
                else:
                    raise ValueError(
                        "Archive layout invalid: missing yt_dlp_plugins directory"
                    )
        except Exception as e:
            logger.error(f"Failed to validate and extract POT plugins staging: {e}")
            for cleanup_path in (tmp_exe, tmp_zip):
                if os.path.exists(cleanup_path):
                    try:
                        os.remove(cleanup_path)
                    except OSError:
                        pass
            shutil.rmtree(staging_plugins_dir, ignore_errors=True)
            return False

        # Both assets are validated in staging. Stop service now to perform swap.
        self.stop()

        backup_exe = os.path.join(paths.pot_provider_dir, "bgutil-pot.exe.backup")
        backup_plugins = os.path.join(paths.pot_provider_dir, "plugins.backup")
        for b in (backup_exe, backup_plugins):
            if os.path.exists(b):
                if os.path.isdir(b):
                    shutil.rmtree(b, ignore_errors=True)
                else:
                    try:
                        os.remove(b)
                    except OSError:
                        pass

        swap_success = False
        try:
            if os.path.exists(paths.pot_provider_exe):
                os.replace(paths.pot_provider_exe, backup_exe)
            os.replace(tmp_exe, paths.pot_provider_exe)

            if os.path.exists(paths.pot_provider_plugins_dir):
                os.replace(paths.pot_provider_plugins_dir, backup_plugins)
            os.replace(staging_plugins_dir, paths.pot_provider_plugins_dir)
            swap_success = True
        except Exception as e:
            logger.error(f"Failed to swap POT provider assets, rolling back: {e}")
            if os.path.exists(backup_exe):
                try:
                    if os.path.exists(paths.pot_provider_exe):
                        os.remove(paths.pot_provider_exe)
                    os.replace(backup_exe, paths.pot_provider_exe)
                except Exception:
                    pass
            if os.path.exists(backup_plugins):
                try:
                    if os.path.exists(paths.pot_provider_plugins_dir):
                        shutil.rmtree(
                            paths.pot_provider_plugins_dir, ignore_errors=True
                        )
                    os.replace(backup_plugins, paths.pot_provider_plugins_dir)
                except Exception:
                    pass
        finally:
            for stale in (tmp_exe, tmp_zip):
                if os.path.exists(stale):
                    try:
                        os.remove(stale)
                    except OSError:
                        pass
            if os.path.exists(staging_plugins_dir):
                shutil.rmtree(staging_plugins_dir, ignore_errors=True)

        if not swap_success:
            if was_running:
                self.start()
            return False

        # Swap completed cleanly; clean up backups
        if os.path.exists(backup_exe):
            try:
                os.remove(backup_exe)
            except OSError:
                pass
        if os.path.exists(backup_plugins):
            shutil.rmtree(backup_plugins, ignore_errors=True)

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

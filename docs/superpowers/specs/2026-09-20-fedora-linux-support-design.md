# Design Specification: First-Class Fedora Linux Support & Unified Installation

## 1. Objective and Scope

HexPlayer (Accessible YouTube Downloader Pro) recently introduced Linux desktop support targeting Ubuntu 24.04 via Debian packaging (`.deb`) and standalone tarballs (`.tar.gz`).
The objective of this design is to elevate **Fedora Linux** to full first-class tier support with equal functionality, full screen reader accessibility, seamless installation via native RPM packages (`.rpm`), and comprehensive automated verification in GitHub Actions.

Key deliverables:
1. Native RPM packaging in `scripts/build.py` driven by a compliant RPM spec template `packaging/linux/hexplayer.spec.in`.
2. Universal dependency installer `packaging/linux/install-deps.sh` auto-detecting Fedora (`dnf`) vs Debian/Ubuntu (`apt-get`).
3. Single-command installation helper `install.sh` for streamlined user onboarding.
4. Distro-aware in-app update checking and accessible installation guidance in `src/utils.py` and `src/gui/update_dialog.py`.
5. Automated CI/CD validation in `.github/workflows/build-artifacts.yml` running real RPM installation and accessibility smoke tests in a Fedora 43 container.
6. GitHub Releases integration in `.github/workflows/release.yml` publishing `.rpm`, `.deb`, `.tar.gz`, and checksums.
7. Unit and integration tests covering Linux package formats and distribution detection.
8. Updated multilingual documentation (English and Arabic guides, README, DEVELOPMENT.md, CONTRIBUTING.md).

---

## 2. Architecture & Components

### 2.1 RPM Packaging Pipeline (`packaging/linux/hexplayer.spec.in` & `scripts/build.py`)

- **RPM Spec Template (`packaging/linux/hexplayer.spec.in`)**:
  - `Name`: `hexplayer`
  - `Version`: `@VERSION@`
  - `Release`: `1%{?dist}`
  - `Summary`: Accessible YouTube browser, player, and downloader
  - `License`: MIT
  - `Group`: Applications/Multimedia
  - `URL`: https://github.com/makhlwf/accessible_youtube_downloader_pro
  - `Requires`:
    - Core GUI & Graphics: `gtk3`, `webkit2gtk4.1`, `libglvnd-glx`, `mesa-libGLU`, `libSM`, `libXtst`
    - Media Engine: `mpv-libs`, `ffmpeg-free` (or `ffmpeg`)
    - Notification & Secrets: `libnotify`, `libsecret`
    - Accessibility & TTS: `speech-dispatcher`, `speech-dispatcher-libs`, `speech-dispatcher-espeak-ng`, `at-spi2-core`
    - Desktop Integration: `xdg-utils`, `xclip`, `wl-clipboard`
  - `%post` / `%postun`: runs `update-desktop-database &> /dev/null || :` to maintain desktop file caches.

- **Build Script (`scripts/build.py`)**:
  - Requires `rpmbuild` on Linux (provided by `rpm` package on Debian/Ubuntu and `rpm-build` on Fedora).
  - Creates an isolated RPM directory hierarchy in `build/rpm/{BUILD,RPMS,SOURCES,SPECS,SRPMS,BUILDROOT}`.
  - Copies the standardized frozen application directory to `BUILDROOT/hexplayer-@VERSION@-1.x86_64/opt/hexplayer`.
  - Sets up `/usr/bin/hexplayer` and `/usr/bin/hexplayer-native-host` symlinks and installs `/usr/share/applications/hexplayer.desktop`.
  - Executes `rpmbuild -bb --define "_topdir <rpm_topdir>" <specs_file>`.
  - Places `HexPlayer-<version>-1.x86_64.rpm` in `dist/` and creates matching `.sha256` checksum.

### 2.2 Universal Dependency & Easy Installation (`packaging/linux/install-deps.sh` & `install.sh`)

- **`packaging/linux/install-deps.sh`**:
  - Reads `/etc/os-release` to determine the distribution ID (`ID`, `ID_LIKE`).
  - Supports `--runtime-only` flag for minimal environments vs full development setups.
  - **Debian / Ubuntu**: Uses `apt-get` to install build tools, GTK3 development headers, media libraries, Speech Dispatcher, and `rpm` (enabling `rpmbuild` on the Ubuntu GitHub Actions runner).
  - **Fedora / RHEL**: Uses `dnf` with `--setopt=install_weak_deps=False` to install `gcc`, `gcc-c++`, `python3-devel`, `pkgconf-pkg-config`, `rpm-build`, `gtk3-devel`, `webkit2gtk4.1-devel`, `mpv-libs`, `ffmpeg-free`, `speech-dispatcher`, `speech-dispatcher-libs`, `speech-dispatcher-devel`, `speech-dispatcher-espeak-ng`, `at-spi2-core`, and related dependencies.

- **`install.sh` (Repository Root / Easy Installer)**:
  - Detects Linux distribution family (Fedora vs Ubuntu/Debian).
  - Detects if local `.rpm` or `.deb` packages exist in current directory or `dist/`.
  - Executes the native package manager command (`sudo dnf install <rpm>` or `sudo apt install <deb>`).
  - If running from source, calls `install-deps.sh`, runs `uv sync`, and registers protocol/native messaging handlers.
  - Checks Speech Dispatcher and AT-SPI status to ensure screen readers (such as Orca) have immediate voice and focus support.

### 2.3 Distro-Aware App Updates & In-App Parity (`src/utils.py` & `src/gui/update_dialog.py`)

- **Distribution Family Detection (`src/utils.py`)**:
  - `_detect_linux_distro_family()` checks `platform.freedesktop_os_release()` (or parses `/etc/os-release`).
  - Distinguishes:
    - `"rpm"`: Fedora, RHEL, CentOS, Rocky Linux, AlmaLinux.
    - `"deb"`: Ubuntu, Debian, Linux Mint, Pop!_OS.
    - `"tarball"`: Other generic distributions or unrecognized platforms.
- **Update Asset Selection (`src/utils.py`)**:
  - `_linux_release_asset_url(url, arch)` is updated to match `.rpm` suffixes (`-1.x86_64.rpm` or `-linux-x86_64.rpm`) as well as `.deb` and `.tar.gz`.
  - Distro-aware matching serves `.rpm` to Fedora users and `.deb` to Ubuntu users.
- **Update Completion Dialog (`src/gui/update_dialog.py`)**:
  - Upon download completion on Linux, provides the exact terminal command formatted with localized gettext strings:
    - Fedora: `sudo dnf install {path}`
    - Ubuntu: `sudo apt install {path}`
  - Both visually displayed in read-only status and announced via `speech_client.speak(..., interrupt=True)`.

### 2.4 CI/CD Verification & Accessibility Testing

- **`build-artifacts.yml`**:
  - Installs `rpm` on `ubuntu-24.04` builder.
  - Validates all generated packages: `desktop-file-validate`, `dpkg-deb --info`, `rpm -qip`.
  - Tests Ubuntu `.deb` installation with `sudo apt-get install -y ./dist/*.deb` and runs `validate_package.py --installed`.
  - Uploads `dist/*.rpm` along with `.deb`, `.tar.gz`, and checksums.
- **`fedora-smoke` Job**:
  - Uses `registry.fedoraproject.org/fedora:43`.
  - Runs `packaging/linux/validate_fedora.sh`:
    - Installs dependencies with DNF.
    - Installs the generated RPM: `dnf install -y /artifacts/*.rpm`.
    - Confirms package query: `rpm -q hexplayer`.
    - Validates `/usr/share/applications/hexplayer.desktop`.
    - Executes `validate_package.py --installed` under unprivileged user `smoke` with Xvfb, D-Bus session, Speech Dispatcher, and AT-SPI accessibility bus.
    - Validates tarball execution from path containing spaces.
- **`release.yml`**:
  - Verifies RPM asset exists: `test -s artifacts/linux/HexPlayer-$VERSION-1.x86_64.rpm` (or matching glob).
  - Publishes `.rpm` assets to GitHub Releases.

---

## 3. Localization & Internationalization (i18n)

- All user-facing strings in `update_dialog.py` and new scripts use `_()` wrapper.
- Extract strings using `uv run pybabel extract -F babel.cfg -k _ -o messages.pot .`.
- Update Arabic translation catalog `src/languages/ar/LC_MESSAGES/messages.po` and recompile `.mo` files.

---

## 4. Verification and Preflight Checkpoints

1. `uv run ruff check .`
2. `uv run python scripts/check_translations.py`
3. `uv run pytest tests/`
4. `uv run python scripts/agent_preflight.py`
5. Push commits and verify GitHub Actions workflows pass across Windows, Ubuntu, and Fedora.

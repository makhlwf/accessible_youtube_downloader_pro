# Fedora Linux Full Support & Unified Packaging Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Provide first-class Fedora Linux support alongside Ubuntu with native RPM packaging, universal dependency and installer scripts, distro-aware in-app updates, full accessibility and functionality parity, and automated CI/CD verification.

**Architecture:** Extend Linux packaging in `scripts/build.py` to generate `.rpm` via `rpmbuild` and `packaging/linux/hexplayer.spec.in`, make `packaging/linux/install-deps.sh` multi-distribution aware (APT and DNF), provide a root `install.sh` convenience script, update `src/utils.py` and `src/gui/update_dialog.py` for Fedora/RPM update matching, test native `.rpm` installation and speech/accessibility in the Fedora 43 container in `.github/workflows/build-artifacts.yml`, and publish `.rpm` assets in `.github/workflows/release.yml`.

**Tech Stack:** Python 3.12+, RPM (`rpmbuild`), DNF, APT, GTK 3, libmpv, Speech Dispatcher (`speechd` / `libspeechd`), AT-SPI2, PyInstaller, Pytest, GitHub Actions.

## Global Constraints

- wxPython GUI thread safety: `wx.CallAfter` for all background/callback operations.
- Accessibility first: all controls labelled, keyboard navigability, Speech Dispatcher announcements.
- i18n freshness: all user strings in `_()`, update `messages.pot` and compiled catalogs.
- Path safety: resolve all directories via `paths.py`.
- Mandatory preflight: `uv run python scripts/agent_preflight.py` must pass before completion.

---

### Task 1: Universal Dependency Management (`packaging/linux/install-deps.sh`)

**Files:**
- Modify: `packaging/linux/install-deps.sh`
- Test: `tests/test_linux_gui_integration.py`

**Interfaces:**
- Consumes: `/etc/os-release` (`ID`, `ID_LIKE`)
- Produces: CLI script accepting optional `--runtime-only` flag, supporting Ubuntu/Debian (`apt-get`) and Fedora/RHEL (`dnf`).

- [ ] **Step 1: Write test for distro detection logic**

Add tests to `tests/test_linux_gui_integration.py` verifying `/etc/os-release` parsing helper.

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_linux_gui_integration.py -k "test_detect_distro" -v`
Expected: FAIL

- [ ] **Step 3: Update `packaging/linux/install-deps.sh`**

Support `apt-get` on Ubuntu/Debian (installing `rpm` build utility) and `dnf` on Fedora/RHEL (installing development tools, GTK3, WebKitGTK 4.1, libmpv, speech-dispatcher, at-spi2-core, and rpm-build).

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_linux_gui_integration.py -k "test_detect_distro" -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add packaging/linux/install-deps.sh tests/test_linux_gui_integration.py
git commit -m "feat(linux): make install-deps.sh support Fedora and Ubuntu"
```

---

### Task 2: RPM Spec Template and Build Pipeline (`packaging/linux/hexplayer.spec.in` & `scripts/build.py`)

**Files:**
- Create: `packaging/linux/hexplayer.spec.in`
- Modify: `scripts/build.py`
- Test: `tests/test_linux_startup.py`

**Interfaces:**
- Consumes: Standard PyInstaller output in `PACKAGE_DIR`, `pyproject.toml` version
- Produces: `HexPlayer-<version>-1.x86_64.rpm` in `dist/` with `.sha256` digest

- [ ] **Step 1: Write test for RPM spec templating and packaging helper**

Add test in `tests/test_linux_startup.py` (mocked for cross-platform execution) that verifies spec file substitution and layout.

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_linux_startup.py -k "test_rpm_spec" -v`
Expected: FAIL

- [ ] **Step 3: Create `packaging/linux/hexplayer.spec.in`**

Add complete RPM spec template declaring `Name: hexplayer`, version, release, license, runtime dependencies (`gtk3`, `mpv-libs`, `ffmpeg-free`, `speech-dispatcher`, `speech-dispatcher-libs`, `speech-dispatcher-espeak-ng`, `at-spi2-core`, `libnotify`, `libsecret`, `webkit2gtk4.1`, `mesa-libGLU`, `libSM`, `libXtst`, `xdg-utils`, `xclip`, `wl-clipboard`), file lists, and desktop database update scriptlets.

- [ ] **Step 4: Implement RPM generation in `scripts/build.py`**

In `scripts/build.py`:
- Check for `rpmbuild` in `ensure_mpv_runtime()`.
- Add `package_rpm(version, architecture, staging, assets)` inside `package_linux()` to invoke `rpmbuild -bb`.
- Compute SHA-256 for the generated `.rpm`.

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_linux_startup.py -k "test_rpm_spec" -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add packaging/linux/hexplayer.spec.in scripts/build.py tests/test_linux_startup.py
git commit -m "feat(linux): add RPM spec and build support for Fedora"
```

---

### Task 3: Universal Single-Command User Installer (`install.sh`)

**Files:**
- Create: `packaging/linux/install.sh`
- Create: `install.sh` (symlink or runner script at repository root)
- Test: `tests/test_linux_gui_integration.py`

**Interfaces:**
- Consumes: Local `.rpm` or `.deb` packages if available, or system package manager
- Produces: Executable installer shell script with speech/accessibility checks.

- [ ] **Step 1: Write unit test validating installer script syntax and flags**

Run: `uv run pytest tests/test_linux_gui_integration.py -k "test_installer" -v`
Expected: FAIL

- [ ] **Step 2: Create `packaging/linux/install.sh` and root `install.sh`**

Implement automated distro detection, local package installation (`dnf install` on Fedora, `apt install` on Ubuntu), or source setup, checking AT-SPI and Speech Dispatcher accessibility services.

- [ ] **Step 3: Run test to verify it passes**

Run: `uv run pytest tests/test_linux_gui_integration.py -k "test_installer" -v`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add packaging/linux/install.sh install.sh tests/test_linux_gui_integration.py
git commit -m "feat(linux): add unified single-command installer script"
```

---

### Task 4: Distro-Aware App Updates & In-App Parity (`src/utils.py` & `src/gui/update_dialog.py`)

**Files:**
- Modify: `src/utils.py`
- Modify: `src/gui/update_dialog.py`
- Test: `tests/test_utils.py`
- Test: `tests/test_update_dialog.py`

**Interfaces:**
- Consumes: Release assets list from update JSON
- Produces: Proper package URL (`.rpm` on Fedora, `.deb` on Ubuntu) and localized instructions.

- [ ] **Step 1: Write failing tests for RPM update URL selection and dialog messages**

Add tests in `tests/test_utils.py` and `tests/test_update_dialog.py` for Fedora distro detection, `.rpm` asset suffix parsing, and localized install commands (`sudo dnf install` vs `sudo apt install`).

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_utils.py tests/test_update_dialog.py -k "rpm" -v`
Expected: FAIL

- [ ] **Step 3: Implement distro detection and RPM URL resolution in `src/utils.py`**

Add `_detect_linux_distro_family()` and update `_linux_release_asset_url(url, arch)` to support `.rpm`.

- [ ] **Step 4: Update `src/gui/update_dialog.py`**

Show and speak the exact command (`sudo dnf install` or `sudo apt install`) when an update finishes downloading.

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_utils.py tests/test_update_dialog.py -k "rpm" -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/utils.py src/gui/update_dialog.py tests/test_utils.py tests/test_update_dialog.py
git commit -m "feat(linux): add distro-aware update selection for Fedora and Ubuntu"
```

---

### Task 5: CI/CD Workflows & Native Fedora Verification

**Files:**
- Modify: `packaging/linux/validate_fedora.sh`
- Modify: `packaging/linux/validate_package.py`
- Modify: `.github/workflows/build-artifacts.yml`
- Modify: `.github/workflows/release.yml`

**Interfaces:**
- Consumes: Built artifacts in `dist/` or `artifacts/linux/`
- Produces: Automated verification of `.rpm` installation in Fedora container, desktop file validation, and RPM release uploads.

- [ ] **Step 1: Update `packaging/linux/validate_fedora.sh`**

Test installing the generated `.rpm` via `dnf install -y /artifacts/*.rpm`, verify `rpm -q hexplayer`, run `desktop-file-validate`, and execute `validate_package.py --installed` with accessibility tools enabled.

- [ ] **Step 2: Update `packaging/linux/validate_package.py`**

Support testing installed RPM paths and verifying Speech Dispatcher / AT-SPI connectivity.

- [ ] **Step 3: Update `.github/workflows/build-artifacts.yml`**

Add `rpm -qip dist/*.rpm` inspection, upload `dist/*.rpm`, and configure `fedora-smoke` container mount to test the `.rpm` package.

- [ ] **Step 4: Update `.github/workflows/release.yml`**

Include RPM assets in release checks: `test -s artifacts/linux/HexPlayer-$VERSION-1.x86_64.rpm` and publish `.rpm` with release assets.

- [ ] **Step 5: Commit**

```bash
git add packaging/linux/validate_fedora.sh packaging/linux/validate_package.py .github/workflows/build-artifacts.yml .github/workflows/release.yml
git commit -m "ci(linux): test native RPM installation in Fedora 43 container"
```

---

### Task 6: Documentation, Localization & Preflight Verification

**Files:**
- Modify: `readme.md`
- Modify: `DEVELOPMENT.md`
- Modify: `CONTRIBUTING.md`
- Modify: `src/docs/en/guide.txt`
- Modify: `src/docs/ar/guide.txt`
- Modify: `messages.pot`
- Modify: `src/languages/ar/LC_MESSAGES/messages.po`
- Modify: `src/languages/ar/LC_MESSAGES/messages.mo`

- [ ] **Step 1: Update user and developer documentation**

Document Fedora installation via DNF (`sudo dnf install ./HexPlayer-*.rpm`) and the unified installer `install.sh`, alongside Ubuntu instructions.

- [ ] **Step 2: Update gettext catalogs**

Extract strings: `uv run pybabel extract -F babel.cfg -k _ -o messages.pot .`
Update Arabic translations in `src/languages/ar/LC_MESSAGES/messages.po`.
Compile catalogs: `uv run pybabel compile -d src/languages`.

- [ ] **Step 3: Run complete preflight verification**

Run: `uv run python scripts/agent_preflight.py`
Expected: ALL CHECKS PASSED

- [ ] **Step 4: Commit and push**

```bash
git add readme.md DEVELOPMENT.md CONTRIBUTING.md src/docs/ messages.pot src/languages/
git commit -m "docs: document Fedora RPM installation and update translations"
git push origin master
```

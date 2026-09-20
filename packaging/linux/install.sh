#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"

SOURCE_MODE=0
CHECK_A11Y=0
DRY_RUN=0
NON_INTERACTIVE=0
PACKAGE_PATH=""

show_help() {
    cat << 'EOF'
HexPlayer (Accessible YouTube Downloader Pro) - Linux Installer

Usage:
  ./install.sh [OPTIONS]

Options:
  -h, --help               Show this help message and exit
  --check-accessibility   Verify screen reader (Orca), AT-SPI2, and Speech Dispatcher
  --package <file>         Install specific .rpm or .deb package file
  --source                 Install from source repository using install-deps.sh and uv/python
  --dry-run                Print installation commands without executing them
  -y, --yes, --non-interactive
                           Run in non-interactive mode (use defaults)

Distro Support:
  - Fedora / RHEL / CentOS / Rocky / AlmaLinux (dnf)
  - Ubuntu / Debian / Linux Mint / Pop!_OS (apt-get)
EOF
}

check_accessibility() {
    printf '%s\n' "=================================================="
    printf '%s\n' "HexPlayer Linux Accessibility & Screen Reader Check"
    printf '%s\n' "=================================================="

    local issues=0

    # 1. Speech Dispatcher & Synthesizer
    printf '%s\n' "1. Speech Dispatcher & TTS Synthesizer:"
    local spd_bin=""
    if command -v spd-say >/dev/null 2>&1; then
        spd_bin=$(command -v spd-say)
        printf '%s\n' "   [OK] 'spd-say' command found: $spd_bin"
    else
        printf '%s\n' "   [MISSING] 'spd-say' command not found."
        issues=$((issues + 1))
    fi

    local espeak_bin=""
    if command -v espeak-ng >/dev/null 2>&1; then
        espeak_bin=$(command -v espeak-ng)
        printf '%s\n' "   [OK] 'espeak-ng' speech synthesizer found: $espeak_bin"
    elif command -v espeak >/dev/null 2>&1; then
        espeak_bin=$(command -v espeak)
        printf '%s\n' "   [OK] 'espeak' speech synthesizer found: $espeak_bin"
    else
        printf '%s\n' "   [MISSING] Speech synthesizer (espeak-ng / espeak) not found."
        issues=$((issues + 1))
    fi

    if [ -n "$spd_bin" ]; then
        if pgrep -f speech-dispatcher >/dev/null 2>&1; then
            printf '%s\n' "   [OK] Speech Dispatcher daemon process is running."
        else
            printf '%s\n' "   [INFO] Speech Dispatcher daemon will auto-start on first audio request."
        fi
    fi

    # 2. AT-SPI2 Accessibility Bus
    printf '%s\n' "2. AT-SPI2 Accessibility Bus:"
    local atspi_found=0
    for atspi_candidate in at-spi-bus-launcher /usr/libexec/at-spi-bus-launcher /usr/lib/at-spi2-core/at-spi-bus-launcher /usr/lib/at-spi2/at-spi-bus-launcher; do
        if command -v "$atspi_candidate" >/dev/null 2>&1 || [ -f "$atspi_candidate" ]; then
            atspi_found=1
            printf '%s\n' "   [OK] AT-SPI2 bus launcher found: $atspi_candidate"
            break
        fi
    done
    if [ "$atspi_found" -eq 0 ]; then
        printf '%s\n' "   [MISSING] AT-SPI2 bus launcher not found in standard paths."
        issues=$((issues + 1))
    fi

    if command -v gsettings >/dev/null 2>&1; then
        local a11y_status
        a11y_status=$(gsettings get org.gnome.desktop.interface toolkit-accessibility 2>/dev/null || echo "unknown")
        if [ "$a11y_status" = "true" ]; then
            printf '%s\n' "   [OK] Desktop toolkit accessibility: Enabled (true)"
        elif [ "$a11y_status" = "false" ]; then
            printf '%s\n' "   [WARNING] Desktop toolkit accessibility: Disabled (false)"
            printf '%s\n' "             Enable with: gsettings set org.gnome.desktop.interface toolkit-accessibility true"
        fi
    fi

    if pgrep -f "at-spi" >/dev/null 2>&1; then
        printf '%s\n' "   [OK] AT-SPI2 bus process is active."
    else
        printf '%s\n' "   [INFO] AT-SPI2 bus will launch on session login or screen reader startup."
    fi

    # 3. Screen Reader (Orca)
    printf '%s\n' "3. Screen Reader (Orca):"
    if command -v orca >/dev/null 2>&1; then
        local orca_bin
        orca_bin=$(command -v orca)
        if pgrep -f "orca" >/dev/null 2>&1; then
            printf '%s\n' "   [OK] Orca screen reader is running ($orca_bin)."
        else
            printf '%s\n' "   [OK] Orca screen reader is installed ($orca_bin)."
        fi
    else
        printf '%s\n' "   [INFO] Orca screen reader is not currently installed."
    fi

    printf '%s\n' "--------------------------------------------------"
    if [ "$issues" -eq 0 ]; then
        printf '%s\n' "Accessibility status: Ready. Screen reader and speech services are available."
    else
        printf '%s\n' "Accessibility notice: $issues potential service(s) may need attention."
        printf '%s\n' "To install accessibility packages:"
        printf '%s\n' "  Fedora: sudo dnf install speech-dispatcher speech-dispatcher-espeak-ng at-spi2-core orca"
        printf '%s\n' "  Ubuntu: sudo apt-get install speech-dispatcher espeak-ng at-spi2-core orca"
    fi
    printf '%s\n' "=================================================="
}

detect_distro() {
    local os_file="${OS_RELEASE_FILE:-/etc/os-release}"
    if [ ! -f "$os_file" ] && [ -f /usr/lib/os-release ]; then
        os_file=/usr/lib/os-release
    fi

    if [ -f "$os_file" ]; then
        # shellcheck source=/dev/null
        . "$os_file"
        local target_id="${ID:-}"
        local target_like="${ID_LIKE:-}"
        case " $target_id $target_like " in
            *" fedora "*|*" rhel "*|*" centos "*|*" rocky "*|*" almalinux "*)
                echo "fedora"
                return 0
                ;;
            *" ubuntu "*|*" debian "*|*" linuxmint "*|*" pop "*)
                echo "debian"
                return 0
                ;;
        esac
    fi

    if [ -f "$SCRIPT_DIR/install-deps.sh" ]; then
        local from_deps
        from_deps=$("$SCRIPT_DIR/install-deps.sh" --detect-distro 2>/dev/null || echo "unknown")
        if [ "$from_deps" = "fedora" ] || [ "$from_deps" = "debian" ]; then
            echo "$from_deps"
            return 0
        fi
    fi

    echo "unknown"
}

find_package() {
    local family="$1"
    local ext=""
    case "$family" in
        fedora) ext="rpm" ;;
        debian) ext="deb" ;;
        *) return 1 ;;
    esac

    local search_dirs=("$PWD" "$PWD/dist" "$REPO_DIR/dist")
    for dir in "${search_dirs[@]}"; do
        if [ -d "$dir" ]; then
            local found
            found=$(ls -t "$dir"/*."$ext" 2>/dev/null | head -n 1 || true)
            if [ -n "$found" ] && [ -f "$found" ]; then
                echo "$found"
                return 0
            fi
        fi
    done
    return 1
}

while [ $# -gt 0 ]; do
    case "$1" in
        -h|--help)
            show_help
            exit 0
            ;;
        --check-accessibility)
            CHECK_A11Y=1
            shift
            ;;
        --source)
            SOURCE_MODE=1
            shift
            ;;
        --package)
            if [ $# -lt 2 ]; then
                printf '%s\n' "Error: --package requires a file argument" >&2
                exit 1
            fi
            PACKAGE_PATH="$2"
            shift 2
            ;;
        --package=*)
            PACKAGE_PATH="${1#*=}"
            shift
            ;;
        --dry-run)
            DRY_RUN=1
            shift
            ;;
        -y|--yes|--non-interactive)
            NON_INTERACTIVE=1
            shift
            ;;
        *)
            printf '%s\n' "Unknown argument: $1" >&2
            printf '%s\n' "Run '$0 --help' for usage information." >&2
            exit 1
            ;;
    esac
done

if [ "$CHECK_A11Y" -eq 1 ]; then
    check_accessibility
    exit 0
fi

FAMILY=$(detect_distro)
if [ "$FAMILY" = "unknown" ]; then
    printf '%s\n' "Unsupported Linux distribution. install.sh supports Fedora/RHEL and Ubuntu/Debian." >&2
    exit 1
fi

if [ -n "$PACKAGE_PATH" ]; then
    if [ ! -f "$PACKAGE_PATH" ]; then
        printf '%s\n' "Error: Package file '$PACKAGE_PATH' not found." >&2
        exit 1
    fi
elif [ "$SOURCE_MODE" -eq 0 ]; then
    if found_pkg=$(find_package "$FAMILY"); then
        PACKAGE_PATH="$found_pkg"
    else
        if [ -f "$SCRIPT_DIR/install-deps.sh" ] || [ -f "$REPO_DIR/src/accessible_youtube_downloader_pro.py" ]; then
            printf '%s\n' "No prebuilt package (.rpm/.deb) found. Falling back to source installation..."
            SOURCE_MODE=1
        else
            printf '%s\n' "Error: No prebuilt package found and not in a source repository." >&2
            printf '%s\n' "Use --package <file> to install a package directly." >&2
            exit 1
        fi
    fi
fi

# Defer OS check until actual execution (allows cross-platform --help and --dry-run)
if [ "$DRY_RUN" -eq 0 ]; then
    if [ "$(uname -s)" != "Linux" ]; then
        printf '%s\n' "Error: HexPlayer Linux installer requires a Linux operating system." >&2
        exit 1
    fi
fi

SUDO="sudo"
if [ "$(id -u 2>/dev/null || echo 1000)" -eq 0 ]; then
    SUDO=""
fi

if [ "$SOURCE_MODE" -eq 0 ]; then
    printf '%s\n' "Installing HexPlayer package: $PACKAGE_PATH"
    if [ "$FAMILY" = "fedora" ]; then
        if [ "$DRY_RUN" -eq 1 ]; then
            printf '%s\n' "[DRY-RUN] ${SUDO:+$SUDO }dnf install -y $PACKAGE_PATH"
        else
            ${SUDO:+$SUDO }dnf install -y "$PACKAGE_PATH"
        fi
    elif [ "$FAMILY" = "debian" ]; then
        case "$PACKAGE_PATH" in
            /*|./*|../*) ;;
            *) PACKAGE_PATH="./$PACKAGE_PATH" ;;
        esac
        if [ "$DRY_RUN" -eq 1 ]; then
            printf '%s\n' "[DRY-RUN] ${SUDO:+$SUDO }apt-get install -y --no-install-recommends $PACKAGE_PATH"
        else
            ${SUDO:+$SUDO }apt-get install -y --no-install-recommends "$PACKAGE_PATH"
        fi
    fi
else
    printf '%s\n' "Setting up HexPlayer from source..."
    DEPS_SCRIPT="$SCRIPT_DIR/install-deps.sh"
    if [ -f "$DEPS_SCRIPT" ]; then
        if [ "$DRY_RUN" -eq 1 ]; then
            printf '%s\n' "[DRY-RUN] ${SUDO:+$SUDO }bash $DEPS_SCRIPT"
        else
            ${SUDO:+$SUDO }bash "$DEPS_SCRIPT"
        fi
    fi

    if [ "$DRY_RUN" -eq 1 ]; then
        printf '%s\n' "[DRY-RUN] Checking python3 and uv"
        printf '%s\n' "[DRY-RUN] uv sync"
    else
        if ! command -v python3 >/dev/null 2>&1; then
            printf '%s\n' "Error: python3 is required for source installation." >&2
            exit 1
        fi
        if command -v uv >/dev/null 2>&1; then
            (cd "$REPO_DIR" && uv sync)
        elif command -v pip3 >/dev/null 2>&1; then
            pip3 install -e "$REPO_DIR" || true
        fi
    fi

    if [ "$DRY_RUN" -eq 1 ]; then
        printf '%s\n' "[DRY-RUN] Registering HexPlayer URL protocol and browser native messaging host"
    else
        do_register=1
        if [ "$NON_INTERACTIVE" -eq 0 ] && [ -t 0 ]; then
            read -r -p "Register HexPlayer URL protocol and browser extension integration? [Y/n] " response || response="y"
            case "$response" in
                [nN][oO]|[nN]) do_register=0 ;;
                *) do_register=1 ;;
            esac
        fi
        if [ "$do_register" -eq 1 ]; then
            if command -v uv >/dev/null 2>&1; then
                (cd "$REPO_DIR" && uv run python -c "import sys; sys.path.insert(0, 'src'); from windows_url_association import register_browser_integration; register_browser_integration()") 2>/dev/null || true
            elif command -v python3 >/dev/null 2>&1; then
                (cd "$REPO_DIR" && python3 -c "import sys; sys.path.insert(0, 'src'); from windows_url_association import register_browser_integration; register_browser_integration()") 2>/dev/null || true
            fi
        fi
    fi
fi

if [ "$DRY_RUN" -eq 0 ]; then
    check_accessibility
fi
printf '%s\n' "HexPlayer installation complete!"

#!/usr/bin/env bash
set -euo pipefail

if [ "$(uname -s)" != Linux ]; then
    printf '%s\n' 'This dependency installer requires Linux.' >&2
    exit 1
fi

RUNTIME_ONLY=0
DETECT_DISTRO=0

for arg in "$@"; do
    case "$arg" in
        --runtime-only)
            RUNTIME_ONLY=1
            ;;
        --detect-distro)
            DETECT_DISTRO=1
            ;;
        -h|--help)
            printf '%s\n' "Usage: $0 [--runtime-only] [--detect-distro]"
            exit 0
            ;;
        *)
            printf '%s\n' "Unknown argument: $arg" >&2
            printf '%s\n' "Usage: $0 [--runtime-only] [--detect-distro]" >&2
            exit 1
            ;;
    esac
done

OS_RELEASE_FILE="${OS_RELEASE_FILE:-/etc/os-release}"

if [ ! -f "$OS_RELEASE_FILE" ] && [ -f /usr/lib/os-release ]; then
    OS_RELEASE_FILE=/usr/lib/os-release
fi

if [ ! -f "$OS_RELEASE_FILE" ]; then
    printf '%s\n' "Cannot detect Linux distribution: $OS_RELEASE_FILE not found." >&2
    exit 1
fi

# Source os-release
# shellcheck source=/dev/null
. "$OS_RELEASE_FILE"

DISTRO_ID="${ID:-}"
DISTRO_ID_LIKE="${ID_LIKE:-}"

detect_distro() {
    local target_id="${1:-$DISTRO_ID}"
    local target_like="${2:-$DISTRO_ID_LIKE}"
    case " $target_id $target_like " in
        *" fedora "*|*" rhel "*|*" centos "*|*" rocky "*|*" almalinux "*)
            echo "fedora"
            ;;
        *" ubuntu "*|*" debian "*|*" linuxmint "*|*" pop "*)
            echo "debian"
            ;;
        *)
            echo "unknown"
            ;;
    esac
}

FAMILY=$(detect_distro)

if [ "$DETECT_DISTRO" -eq 1 ]; then
    echo "$FAMILY"
    exit 0
fi

if [ "$FAMILY" = "unknown" ]; then
    printf '%s\n' "Unsupported distribution '${DISTRO_ID}'. install-deps.sh supports Fedora/RHEL (dnf) and Debian/Ubuntu (apt-get)." >&2
    exit 1
fi

if [ "$FAMILY" = "fedora" ]; then
    if [ "$RUNTIME_ONLY" -eq 1 ]; then
        dnf install -y --setopt=install_weak_deps=False \
            gtk3 webkit2gtk4.1 libnotify libsecret mesa-libGL mesa-libGLU libSM libXtst \
            mpv-libs ffmpeg-free \
            speech-dispatcher speech-dispatcher-libs speech-dispatcher-espeak-ng at-spi2-core \
            xdg-utils xclip wl-clipboard
    else
        dnf install -y --setopt=install_weak_deps=False \
            gcc gcc-c++ make python3-devel pkgconf-pkg-config rpm-build \
            gtk3-devel webkit2gtk4.1-devel mesa-libGL-devel mesa-libGLU-devel \
            libjpeg-turbo-devel libpng-devel libtiff-devel expat-devel libnotify-devel \
            SDL2-devel libSM-devel libXtst-devel gstreamer1-devel gstreamer1-plugins-base-devel \
            libsecret-devel libffi-devel \
            gtk3 webkit2gtk4.1 libnotify libsecret mesa-libGL mesa-libGLU libSM libXtst \
            mpv-libs ffmpeg-free \
            speech-dispatcher speech-dispatcher-libs speech-dispatcher-devel speech-dispatcher-espeak-ng at-spi2-core \
            xclip wl-clipboard xdg-utils desktop-file-utils \
            xorg-x11-server-Xvfb xorg-x11-xauth dbus-daemon
    fi
elif [ "$FAMILY" = "debian" ]; then
    apt-get update
    if [ "$RUNTIME_ONLY" -eq 1 ]; then
        apt-get install -y --no-install-recommends \
            libc6 libstdc++6 libgtk-3-0t64 libmpv2 ffmpeg libnotify4 libsecret-1-0 \
            libwebkit2gtk-4.1-0 libgl1 libglu1-mesa libsm6 libxtst6 libspeechd2 \
            speech-dispatcher at-spi2-core xdg-utils espeak-ng xclip wl-clipboard
    else
        apt-get install -y --no-install-recommends \
            build-essential pkg-config python3-dev binutils dpkg-dev rpm \
            libgtk-3-dev libwebkit2gtk-4.1-dev libgl1-mesa-dev libglu1-mesa-dev \
            libjpeg-dev libpng-dev libtiff-dev libexpat1-dev libnotify-dev \
            libsdl2-dev libsm-dev libxtst-dev libgstreamer1.0-dev \
            libgstreamer-plugins-base1.0-dev libsecret-1-dev libffi-dev \
            libmpv2 ffmpeg speech-dispatcher libspeechd2 espeak-ng at-spi2-core \
            xclip xsel wl-clipboard xdg-utils desktop-file-utils xvfb xauth dbus-x11
    fi
fi

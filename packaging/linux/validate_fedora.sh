set -euo pipefail

packages=(
    gtk3 mpv-libs ffmpeg-free libnotify libsecret webkit2gtk4.1
    libglvnd-glx mesa-libGLU libSM libXtst
    speech-dispatcher speech-dispatcher-libs speech-dispatcher-espeak-ng
    at-spi2-core desktop-file-utils xdg-utils
    python3 tar gzip coreutils shadow-utils util-linux
    xorg-x11-server-Xvfb xorg-x11-xauth dbus-daemon
)
timeout --kill-after=15s 600s dnf install -y --setopt=install_weak_deps=False \
    --setopt=timeout=30 --setopt=retries=2 "${packages[@]}"
rpm -q "${packages[@]}"
for command in python3 Xvfb xvfb-run xauth dbus-run-session timeout runuser ffmpeg ffprobe desktop-file-validate; do
    command -v "$command"
done
id -u smoke >/dev/null 2>&1 || useradd --create-home --uid 10001 smoke

# Verify RPM package installation
rpms=(/artifacts/*.rpm)
if [ "${#rpms[@]}" -ne 1 ] || [ ! -f "${rpms[0]}" ]; then
    printf '%s\n' 'Expected exactly one Linux RPM in /artifacts.' >&2
    exit 1
fi
dnf install -y "${rpms[0]}"
rpm -q hexplayer
test -x /usr/bin/hexplayer
test -x /usr/bin/hexplayer-native-host
test -f /usr/share/applications/hexplayer.desktop
test -d /opt/hexplayer
desktop-file-validate /usr/share/applications/hexplayer.desktop

# Smoke installed RPM package as normal user with xvfb and dbus
timeout --kill-after=10s 150s runuser -u smoke -- \
    python3 /validation/validate_package.py --installed

# Smoke tarball as normal user with xvfb and dbus
archives=(/artifacts/*.tar.gz)
if [ "${#archives[@]}" -ne 1 ] || [ ! -f "${archives[0]}" ]; then
    printf '%s\n' 'Expected exactly one Linux tarball in /artifacts.' >&2
    exit 1
fi
timeout --kill-after=10s 150s runuser -u smoke -- \
    python3 /validation/validate_package.py --tarball "${archives[0]}"

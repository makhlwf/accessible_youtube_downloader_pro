set -euo pipefail

packages=(
    gtk3 mpv-libs ffmpeg-free libnotify libsecret webkit2gtk4.1
    libglvnd-glx mesa-libGLU libSM libXtst speech-dispatcher-libs xdg-utils
    python3 tar gzip coreutils shadow-utils util-linux
    xorg-x11-server-Xvfb xorg-x11-xauth dbus-daemon
)
timeout --kill-after=15s 600s dnf install -y --setopt=install_weak_deps=False \
    --setopt=timeout=30 --setopt=retries=2 "${packages[@]}"
rpm -q "${packages[@]}"
for command in python3 Xvfb xvfb-run xauth dbus-run-session timeout runuser ffmpeg ffprobe; do
    command -v "$command"
done
useradd --create-home --uid 10001 smoke
archives=(/artifacts/*.tar.gz)
if [ "${#archives[@]}" -ne 1 ] || [ ! -f "${archives[0]}" ]; then
    printf '%s\n' 'Expected exactly one Linux tarball in /artifacts.' >&2
    exit 1
fi
timeout --kill-after=10s 150s runuser -u smoke -- \
    python3 /validation/validate_package.py --tarball "${archives[0]}"

set -euo pipefail

if [ "$(uname -s)" != Linux ]; then
    printf '%s\n' 'This dependency installer requires Linux.' >&2
    exit 1
fi

apt-get update
apt-get install -y --no-install-recommends \
    build-essential pkg-config python3-dev binutils dpkg-dev \
    libgtk-3-dev libwebkit2gtk-4.1-dev libgl1-mesa-dev libglu1-mesa-dev \
    libjpeg-dev libpng-dev libtiff-dev libexpat1-dev libnotify-dev \
    libsdl2-dev libsm-dev libxtst-dev libgstreamer1.0-dev \
    libgstreamer-plugins-base1.0-dev libsecret-1-dev libffi-dev \
    libmpv2 ffmpeg speech-dispatcher libspeechd2 espeak-ng \
    xclip xsel wl-clipboard xdg-utils desktop-file-utils xvfb xauth dbus-x11

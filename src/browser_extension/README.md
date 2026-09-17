# HexPlayer Link Helper

This extension sends supported YouTube links to HexPlayer through Chrome/Brave
Native Messaging. If the native host is not registered, it falls back to the
`hexplayer://` custom protocol. It does not register HexPlayer as the handler
for normal `http://` or `https://` links.

Developer: makhlwf

Source code: https://github.com/makhlwf/accessible_youtube_downloader_pro

## Supported environments

HexPlayer targets modern 64-bit Windows, especially Windows 10 and Windows 11; older Windows releases and 32-bit systems may not work reliably with current runtime components. Linux uses Ubuntu 24.04 x86_64 (amd64), glibc 2.39 or newer, as its reference desktop environment, not a guarantee for every distribution. No macOS packages or ARM releases are promised.

Linux assets may not yet be available on the [Releases page](https://github.com/makhlwf/accessible_youtube_downloader_pro/releases). Until a new release publishes them, use the [source installation instructions](../../readme.md#running-from-source). Those instructions also cover runtime dependencies, first-launch downloads, and Speech Dispatcher/Orca limitations. Run HexPlayer as your normal desktop user, never with `sudo`.

## Install the extension

1. In HexPlayer, enable the safe browser integration setting. This registers
   the Native Messaging host and the fallback `hexplayer://` protocol.
2. Open the browser extension folder from HexPlayer's Tools menu. HexPlayer
   keeps this user extension folder refreshed from the installed copy.
3. In Chrome or Edge, open `chrome://extensions` or `edge://extensions`.
4. Enable Developer mode.
5. Choose Load unpacked and select this folder.

## Linux desktop registration

Enable safe browser integration in the same user account that runs your browser. HexPlayer registers `hexplayer://` through a per-user desktop entry at `$XDG_DATA_HOME/applications/hexplayer.desktop` (default `~/.local/share/applications/hexplayer.desktop`) and `xdg-mime`. It does not take over ordinary web links.

Native Messaging manifests are named `com.hexplayer.link_helper.json` and are placed under `$XDG_CONFIG_HOME` (default `~/.config`) in these standard browser directories:

- `google-chrome/NativeMessagingHosts`
- `chromium/NativeMessagingHosts`
- `microsoft-edge/NativeMessagingHosts`
- `BraveSoftware/Brave-Browser/NativeMessagingHosts`

Automatic registration covers these standard paths, not every Chromium derivative or custom profile location. Snap/Flatpak browser sandboxes may block host access or use different paths; their integration is not guaranteed. Re-enable integration after moving a tarball or source checkout so launch paths are updated.

App data and the refreshed extension normally live in `$XDG_DATA_HOME/HexPlayer` (default `~/.local/share/HexPlayer`); the extension subfolder is `browser_extension`. Portable mode uses the application's `data` directory instead. Use **External Tools > Open Browser Extension Folder** rather than guessing the path.

## Use

- Right-click a supported YouTube link and choose Open YouTube link in
  HexPlayer.
- On a supported YouTube page, click the HexPlayer toolbar button.
- Optional: open the extension options and enable click interception. When that
  option is off, ordinary clicks continue to open in the browser. Enabling it
  asks the browser for permission to watch link clicks on websites.
- Brave should not ask before opening HexPlayer when Native Messaging is
  registered correctly.
- If the extension falls back to the external `hexplayer://` link, Brave may
  show a confirmation prompt.

## Diagnostics

Open the extension options page to see diagnostic logs. From `brave://extensions`,
find HexPlayer Link Helper and choose Details, then Extension options.

The options page includes:

- Open test video in HexPlayer
- Refresh logs
- Copy logs
- Clear logs

If nothing happens, copy the logs and check for `Native Messaging host opened
HexPlayer`. If you see `Native Messaging host failed; using fallback`, re-enable
safe browser integration in HexPlayer settings and reload the extension from
the folder opened by **External Tools > Open Browser Extension Folder**. Its
normal location is `%APPDATA%\HexPlayer\browser_extension` on Windows or
`~/.local/share/HexPlayer/browser_extension` on Linux (unless XDG data or
portable settings change it). On Linux, confirm `xdg-utils` is installed and
that the browser uses one of the standard configuration paths listed above.

## Supported links

The helper accepts YouTube watch, Shorts, playlist, live, clip, channel,
handle, and `youtu.be` links.

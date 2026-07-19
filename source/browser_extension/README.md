# HexPlayer Link Helper

This extension sends supported YouTube links to HexPlayer through Chrome/Brave
Native Messaging. If the native host is not registered, it falls back to the
`hexplayer://` custom protocol. It does not register HexPlayer as the handler
for normal `http://` or `https://` links.

Developer: makhlwf

Source code: https://github.com/makhlwf/accessible_youtube_downloader_pro

## Install for development

1. In HexPlayer, enable the safe browser integration setting. This registers
   the Native Messaging host and the fallback `hexplayer://` protocol.
2. Open the browser extension folder from HexPlayer's Tools menu. HexPlayer
   keeps this user extension folder refreshed from the installed copy.
3. In Chrome or Edge, open `chrome://extensions` or `edge://extensions`.
4. Enable Developer mode.
5. Choose Load unpacked and select this folder.

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
`%APPDATA%\HexPlayer\browser_extension`.

## Supported links

The helper accepts YouTube watch, Shorts, playlist, live, clip, channel,
handle, and `youtu.be` links.

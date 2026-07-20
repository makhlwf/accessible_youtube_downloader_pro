# Privacy Policy for HexPlayer

**Last Updated: July 17, 2026**

HexPlayer is an open-source, accessible YouTube downloader and player for Windows. This Privacy Policy explains what information the app uses, where it is stored, and when it is sent to third-party services.

HexPlayer is designed as a local-first application. The project maintainer does not operate a server for collecting user data, analytics, telemetry, or usage tracking.

## 1. Information HexPlayer Uses

HexPlayer may use the following information while you use the app:

- **YouTube links, searches, channels, playlists, and video metadata:** Used to search, browse, play, and download YouTube content.
- **Download settings:** Such as output folder, selected format, quality, and conversion preferences.
- **Playback settings:** Such as volume, speed, equalizer settings, audio output device, and resume positions.
- **Favorites:** Videos you manually save to favorites.
- **Clipboard content:** If clipboard link detection is enabled or used, HexPlayer may read the clipboard locally to detect YouTube links. It does not upload your clipboard contents to the project maintainer.
- **Cookies file path:** If you configure a YouTube cookies file, HexPlayer stores the local path to that file in settings.

## 2. YouTube Cookies and Authentication

Using a cookies file is optional. If you configure the "Cookies File Path" setting:

- HexPlayer uses that cookies file locally to authenticate requests to YouTube.
- Cookies may allow features such as recommendations, YouTube watch history, age-restricted content, home feed access, and other account-based YouTube features.
- Your cookies are not uploaded to HexPlayer servers or shared with the developer.
- Your cookies may be sent to Google/YouTube because they are used to authenticate YouTube requests.
- The path to the cookies file is stored locally in `settings.ini`.

Treat your cookies file like a password. Anyone with access to it may be able to access parts of your YouTube account session.

## 3. Local Data Storage

HexPlayer stores app data locally on your device. This may include:

- **Settings:** Stored in a local configuration file, including language, download path, theme, playback options, cookies file path, and tool paths.
- **Favorites:** Stored in a local SQLite database.
- **Resume positions:** Stored locally so playback can continue from the previous position.
- **Downloaded files:** Stored in the folder you choose.
- **External tool files:** `yt-dlp`, Deno, cache files, or related support files may be stored locally so the app can play, browse, and download media.

HexPlayer does not sell, rent, or share this local data with the project maintainer.

## 4. YouTube Watch History and Account Features

If you use cookies and account-based features, HexPlayer may request or update data associated with your YouTube account, including:

- YouTube home feed and recommendations.
- YouTube watch history.
- Video comments you choose to post.
- Video chapters and metadata.
- Like and dislike actions.
- Watch-history updates when media is played.

These requests are sent to Google/YouTube and are subject to Google's privacy policy and YouTube's terms.

## 5. Third-Party Services

HexPlayer may connect to the following third-party services:

- **Google/YouTube:** For search, browsing, playback metadata, streams, channels, playlists, recommendations, watch history, video comments, likes, dislikes, and downloads.
- **GitHub:** For checking app updates and downloading or updating external components such as `yt-dlp`.
- **Deno release sources:** For downloading or updating Deno when needed.
- **Deno module and package hosts:** Deno or YouTube-related helper code may download modules from sources such as `deno.land`, `jsr.io`, or the npm registry.
- **yt-dlp extractors:** `yt-dlp` may contact YouTube or related media endpoints to extract playable or downloadable media information.

HexPlayer does not control the privacy practices of these third-party services.

## 6. No Analytics or Tracking

HexPlayer does not include analytics, telemetry, advertising trackers, or tracking scripts. The project maintainer does not receive reports about what you search for, watch, download, or save.

## 7. User Controls

You can control or remove locally stored data by:

- Clearing the cookies file path in settings.
- Deleting favorites from the Favorites window.
- Changing or deleting the download folder contents yourself.
- Removing HexPlayer settings and databases from the local app data folder.
- Uninstalling HexPlayer.

If you want to revoke YouTube account access represented by a cookies file, delete or replace that cookies file and sign out or manage sessions from your Google account settings.

## 8. Security

HexPlayer stores settings and databases locally using normal user-level files. It does not encrypt the cookies file or local database. You are responsible for protecting access to your Windows account and local files.

## 9. Children's Privacy

HexPlayer is not designed to collect information from children. The app does not knowingly collect personal information from children or send such information to the project maintainer.

## 10. Changes to This Policy

This policy may be updated when HexPlayer's features or data handling change. The "Last Updated" date at the top of this file will be changed when the policy is revised.

## 11. Transparency and Open Source

HexPlayer is open source. You can review the source code to verify how the app handles data:

https://github.com/makhlwf/accessible_youtube_downloader_pro

## 12. Contact

If you have questions about this Privacy Policy, you can contact the project maintainer via:

- **Email:** altrhwnyashrf1@gmail.com
- **Telegram:** [@makhlwf](https://t.me/makhlwf)
- **GitHub Issues:** [Open an issue here](https://github.com/makhlwf/accessible_youtube_downloader_pro/issues)

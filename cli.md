# HexPlayer Command Line Interface

HexPlayer ships a dedicated command line tool, `hexplayer`, that exposes the
application's YouTube features without opening the graphical interface. It is
designed to be scriptable and screen-reader friendly in a terminal: every
command supports plain human-readable text output and a machine-readable
`--json` mode.

> Playback is intentionally **not** available from the CLI. Everything else —
> search, browsing, information, downloads, subtitles, comments, favorites,
> history, settings, cookies, and dependency management — is exposed.

---

## Installation and PATH

On Windows, the installer includes an optional task **"Add HexPlayer to the
system PATH (enables the hexplayer command line tool)"**. When selected, the
installation directory is appended to your per-user `PATH` (HKCU), so you can
run `hexplayer` from any Command Prompt, PowerShell, or terminal window.

- The task is **off by default**; enable it on the "Select Additional Tasks"
  page of the installer.
- The change applies to the current user only and does not require
  administrator rights.
- Open a **new** terminal after installation for the updated `PATH` to take
  effect.
- Uninstalling HexPlayer removes the directory from your `PATH`.

If you did not enable the task, you can still run the tool with its full path:

```powershell
"%LOCALAPPDATA%\HexPlayer\hexplayer.exe" --help
```

On Linux, the native packages install a `hexplayer` launcher on `PATH`
already.

When running from source, invoke the CLI module directly:

```bash
uv run python src/hexplayer_cli.py --help
```

---

## Global options

These options apply to every command and must appear **before** the command
name:

| Option | Description |
| :--- | :--- |
| `--json` | Emit results as JSON instead of human-readable text. |
| `--lang CODE` | Override the interface language for this invocation only (for example `ar` or `en`). Not saved to settings. |

Examples:

```bash
hexplayer --json search "lofi hip hop"
hexplayer --lang en info https://youtu.be/dQw4w9WgXcQ
```

### JSON output shape

- Success: `{ "ok": true, "data": ... }` or `{ "ok": true, "message": "..." }`.
- Failure: `{ "ok": false, "error": "...", "code": "..." }` printed to stderr.

Common error codes include `deno_missing`, `cookies_missing`, `cancelled`
(exit 130), and `unexpected`.

### Exit codes

| Code | Meaning |
| :--- | :--- |
| `0` | Success. |
| `1` | An error occurred (message printed to stderr). |
| `130` | Interrupted with Ctrl+C. |

---

## Features that require Deno or cookies

Some commands need external resources to be configured first. The CLI never
opens a dialog; instead it prints a localized error explaining how to fix it.

- **Deno runtime** (InnerTube features): install with
  `hexplayer deps update --deno`.
- **Cookies file** (signed-in features such as posting comments, likes, home
  feed, shorts, and online watch history): set one with
  `hexplayer cookies set <path>`.

Commands that require both are noted below.

---

## Command reference

### search

Search YouTube.

```bash
hexplayer search "QUERY" [--type video|playlist|channel] [--pages N]
```

- `--type` — result type (default `video`).
- `--pages` — number of result pages to load (default `1`).

### suggest

Show search suggestions for a query.

```bash
hexplayer suggest "QUERY"
```

### info

Show information about a video.

```bash
hexplayer info URL
```

### formats

List the available formats for a video.

```bash
hexplayer formats URL
```

### qualities

List the available qualities for a video.

```bash
hexplayer qualities URL [--audio]
```

- `--audio` — list audio qualities instead of video.

### stream-url

Get a direct playable stream URL.

```bash
hexplayer stream-url URL [--audio] [--quality HEIGHT]
```

- `--audio` — audio-only stream.
- `--quality` — requested video height (for example `720`).

### download

Download a video, audio track, or a whole playlist.

```bash
hexplayer download URL [--format mp4|mkv|m4a|mp3|wav|flac] [--quality HEIGHT] [--output DIR] [--folder]
```

- `--format` — output file format (default `mp4`). `mp4`/`mkv` produce video;
  `m4a`/`mp3`/`wav`/`flac` produce audio.
- `--quality` — maximum video height (for example `1080`).
- `--output` — destination folder (defaults to the configured download path,
  then the current directory).
- `--folder` — download an entire playlist into its own folder.

In text mode a progress line is written to stderr; in `--json` mode progress
is suppressed and only the final result is emitted.

### subtitles

Manage subtitles.

```bash
hexplayer subtitles list URL
hexplayer subtitles get URL --lang CODE [--output FILE.srt]
```

- `list` — show available subtitle tracks.
- `get` — download a subtitle track as SRT. `--lang` is required; `--output`
  writes to a file, otherwise the SRT is printed.

### comments

Show a video's comments.

```bash
hexplayer comments URL [--sort top|new] [--continuation TOKEN]
```

- `--sort` — comment ordering (default `top`).
- `--continuation` — token for the next page (from a previous result).

### replies

Show replies to a comment.

```bash
hexplayer replies --token TOKEN [--continuation TOKEN] [--url URL] [--parent COMMENT_ID]
```

- `--token` — replies token (required).
- `--continuation`, `--url`, `--parent` — optional fallbacks for pagination.

### post-comment

Post a comment. **Requires Deno and cookies.**

```bash
hexplayer post-comment URL "TEXT"
```

### like-comment

React to a comment. **Requires Deno and cookies.**

```bash
hexplayer like-comment URL COMMENT_ID [--action like|dislike|remove_like]
```

### reply-comment

Reply to a comment. **Requires Deno and cookies.**

```bash
hexplayer reply-comment URL COMMENT_ID "TEXT"
```

### chapters

Show a video's chapters.

```bash
hexplayer chapters URL
```

### likes

Show a video's like count and your rating state.

```bash
hexplayer likes URL
```

### like

Like or dislike a video, or remove your rating. **Requires Deno and cookies.**

```bash
hexplayer like URL [--action like|dislike|remove_like]
```

### channel

Browse a channel.

```bash
hexplayer channel URL [--tab home|videos|shorts|live|playlists|community|channels|about] [--pages N]
```

- `--tab` — channel tab to open (default `videos`).
- `--pages` — number of pages to load (default `1`).

### playlist

Show a playlist's contents.

```bash
hexplayer playlist URL
```

### home

Show the home feed. **Requires Deno and cookies.**

```bash
hexplayer home [--continuation TOKEN]
```

### shorts

Show Shorts recommendations. **Requires Deno and cookies.**

```bash
hexplayer shorts [--seed VIDEO_ID]
```

### watch-history

Show watch history.

```bash
hexplayer watch-history [--online] [--limit N] [--offset N] [--continuation TOKEN]
```

- `--online` — use your online YouTube history (**requires Deno and cookies**)
  instead of the local history.
- `--limit` / `--offset` — paginate the local history (defaults `50` / `0`).
- `--continuation` — token for the next online page.

### favorites

Manage local favorites.

```bash
hexplayer favorites list
hexplayer favorites add URL [--title TITLE] [--channel NAME] [--channel-url URL] [--live]
hexplayer favorites remove URL
```

### search-history

Manage your local search history.

```bash
hexplayer search-history list
hexplayer search-history clear
```

### config

Read and change application settings.

```bash
hexplayer config get KEY
hexplayer config set KEY VALUE
hexplayer config list
hexplayer config path
```

- `set` accepts only known setting keys.
- `path` prints the location of the settings file.

### cookies

Manage the cookies file used for signed-in features.

```bash
hexplayer cookies status
hexplayer cookies set PATH
hexplayer cookies clear
```

- `status` reports only whether a cookies file is configured and present. It
  never prints the file's contents.
- `set` validates that the given path exists and stores its absolute path.
- `clear` removes the configured cookies path.

### deps

Manage external components.

```bash
hexplayer deps versions
hexplayer deps update [--ytdlp] [--deno] [--youtubei] [--pot] [--all]
```

- `versions` — show installed versions of yt-dlp, Deno, YouTube.js, and the POT
  provider.
- `update` — update one or more components. Pass `--all` to update everything.
  Exits non-zero if any requested update fails.

---

## Tips

- Use `hexplayer COMMAND --help` (and `hexplayer COMMAND SUBCOMMAND --help`)
  to see the help for any command directly in your terminal.
- Combine `--json` with tools like `jq` to build scripts around HexPlayer.
- Interface text follows your configured language; override per invocation with
  `--lang`.
- Integrating HexPlayer into your own application? See the
  [Developer API guide](api.md) for the `--json` contract, per-command output,
  integration examples, and the attribution HexPlayer requires under GPL-3.0.


# HexPlayer Developer API Guide

This guide is for developers who want to use HexPlayer's YouTube capabilities
**from their own applications**.

HexPlayer's programmatic surface is its command line tool, `hexplayer`, running
in **`--json` mode**. You invoke it as a subprocess, pass a command, and read a
single JSON document from standard output. There is no separate network service
and no public importable Python library; the CLI *is* the API, and `--json` is
its stable contract.

> **Licensing notice (read first):** HexPlayer is licensed under **GPL-3.0**.
> Integrating it into your application carries obligations, and this project
> additionally **requires explicit, visible attribution to HexPlayer**. See
> [Attribution and Licensing](#attribution-and-licensing) at the end of this
> document before you ship.

---

## Contents

- [Invocation model](#invocation-model)
- [Response envelope](#response-envelope)
- [Exit codes and error codes](#exit-codes-and-error-codes)
- [Prerequisites: Deno and cookies](#prerequisites-deno-and-cookies)
- [Command reference with expected output](#command-reference-with-expected-output)
- [Integration examples](#integration-examples)
- [Attribution and Licensing](#attribution-and-licensing)

---

## Invocation model

Call the executable with the global `--json` flag **before** the command name:

```
hexplayer --json <command> [subcommand] [arguments] [options]
```

- On Windows, if the installer's "Add HexPlayer to the system PATH" task was
  selected, `hexplayer` is on `PATH`. Otherwise call the full path, e.g.
  `%LOCALAPPDATA%\HexPlayer\hexplayer.exe`.
- On Linux, the native packages install `hexplayer` on `PATH`.
- From source: `python src/hexplayer_cli.py --json <command> ...`.

Each invocation is stateless, does one thing, and exits. Successful results and
success messages are written to **stdout**; errors are written to **stderr**.

---

## Response envelope

Every `--json` invocation prints exactly one JSON object. There are three
shapes.

**1. A result carrying data** (queries such as `search`, `info`, `formats`):

```json
{
  "ok": true,
  "data": { }
}
```

`data` is either an object or an array depending on the command (documented per
command below).

**2. A success message** (mutating commands such as `favorites add`,
`cookies set`, `download`):

```json
{
  "ok": true,
  "message": "Added to favorites.",
  "data": { "url": "https://youtu.be/VIDEO_ID" }
}
```

`message` is localized (see `--lang`). `data` may be present or absent.

**3. An error** (printed to **stderr**):

```json
{
  "ok": false,
  "error": "This feature requires a valid cookies file. Set it with: hexplayer cookies set <path>",
  "code": "cookies_missing"
}
```

Always branch on the boolean `ok` field first. Do not parse the human-readable
`error`/`message` text — it changes with the interface language. Branch on
`code` (for errors) and read structured values from `data`.

### A note on language

Human-readable strings (`message`, `error`, and text output) follow the
configured interface language, which defaults to the user's setting. Pass
`--lang en` (or `--lang ar`) to pin the language for one invocation. The
**structure** of `data`, the field names, and `code` values are stable and
language-independent — build your integration on those.

---

## Exit codes and error codes

| Exit code | Meaning |
| :--- | :--- |
| `0` | Success (`"ok": true`). |
| `1` | Handled error (`"ok": false`, JSON on stderr). |
| `130` | Interrupted (Ctrl+C); `code` is `cancelled`. |

Common `code` values:

| `code` | Cause |
| :--- | :--- |
| `cookies_missing` | The command needs a configured cookies file. |
| `deno_missing` | The command needs the Deno runtime installed. |
| `stream_failed` | No playable stream could be resolved. |
| `download_failed` | The download did not complete. |
| `unknown_config_key` | `config set` was given a key that does not exist. |
| `unexpected` | An unhandled exception; `error` carries the detail. |
| `cancelled` | The process was interrupted. |

---

## Prerequisites: Deno and cookies

Some commands need resources the CLI will not install on the fly. Instead of
prompting, it returns a structured error so your app can react.

- **Deno runtime** — required by InnerTube-backed features. Install with
  `hexplayer deps update --deno`. Missing → `code: "deno_missing"`.
- **Cookies file** — required for signed-in read-only features (home feed,
  Shorts, online watch history). Configure with
  `hexplayer cookies set <path>`. Missing → `code: "cookies_missing"`.

Commands that require **both** are marked below. Your app should check
`deps versions` and `cookies status` up front if it depends on these.

---

## Command reference with expected output

Every example below shows a real `--json` response. Long arrays and text are
truncated with `…` for readability.

### search

```
hexplayer --json search "QUERY" [--type video|playlist|channel] [--pages N]
```

`data` is an array of result objects. `views` is present only when known.

```json
{
  "ok": true,
  "data": [
    {
      "index": 1,
      "type": "video",
      "title": "lofi hip hop radio 📚 beats to relax/study to",
      "url": "https://www.youtube.com/watch?v=rFZHOHl-L8A",
      "channel": "Lofi Girl",
      "channel_url": "https://www.youtube.com/channel/UCSJ4gkVC6NrvII8umztf0Ow"
    }
  ]
}
```

### suggest

```
hexplayer --json suggest "QUERY"
```

`data` is an array of suggestion strings.

```json
{ "ok": true, "data": ["lofi", "lofi songs", "lofi music", "lofi girl"] }
```

### info

```
hexplayer --json info URL
```

`data` is a single video object. Fields YouTube does not return are `null`.

```json
{
  "ok": true,
  "data": {
    "id": "rFZHOHl-L8A",
    "title": "lofi hip hop radio 📚 beats to relax/study to",
    "channel": "Lofi Girl",
    "channel_url": "https://www.youtube.com/channel/UCSJ4gkVC6NrvII8umztf0Ow",
    "duration": null,
    "view_count": 10083610,
    "like_count": 30921,
    "upload_date": "20260819",
    "webpage_url": "https://www.youtube.com/watch?v=rFZHOHl-L8A",
    "is_live": true,
    "description": "…"
  }
}
```

### formats

```
hexplayer --json formats URL
```

`data` is an array of format objects.

```json
{
  "ok": true,
  "data": [
    {
      "format_id": "251",
      "ext": "webm",
      "height": 0,
      "abr": 160,
      "vcodec": "none",
      "acodec": "opus",
      "filesize": null
    }
  ]
}
```

### qualities

```
hexplayer --json qualities URL [--audio]
```

`data` is an array of available heights (video) or bitrates (`--audio`).

```json
{ "ok": true, "data": [144, 240, 360, 480, 720, 1080] }
```

### stream-url

```
hexplayer --json stream-url URL [--audio] [--quality HEIGHT]
```

`data` carries the resolved playable stream. `audio_url` is set when video and
audio tracks are separate. `headers` are the HTTP headers needed to fetch it.

```json
{
  "ok": true,
  "data": {
    "title": "…",
    "url": "https://…",
    "audio_url": "https://…",
    "quality": 720,
    "headers": { "User-Agent": "…" },
    "webpage_url": "https://www.youtube.com/watch?v=…",
    "channel_name": "…"
  }
}
```

Failure → `code: "stream_failed"`.

### download

```
hexplayer --json download URL [--format mp4|mkv|m4a|mp3|wav|flac] [--quality HEIGHT] [--output DIR] [--folder]
```

In `--json` mode, per-chunk progress is suppressed and only the final result is
printed.

```json
{
  "ok": true,
  "message": "Download complete: …/video.mp4",
  "data": { "file": "…/video.mp4", "path": "…/HexPlayer" }
}
```

Failure → `code: "download_failed"`.

### subtitles

```
hexplayer --json subtitles list URL
hexplayer --json subtitles get URL --lang CODE [--output FILE.srt]
```

`list` → `data` is an array of `{ "code", "label", "source" }`. `get` with
`--output` returns a success message; without it, `data` is the array of cue
objects and the SRT text is the message.

### comments / replies

```
hexplayer --json comments URL [--sort top|new] [--continuation TOKEN]
hexplayer --json replies --token TOKEN [--continuation TOKEN]
```

`data` includes the comment/reply items and a `continuation` token (when more
pages exist) that you pass back via `--continuation`.

### chapters

```
hexplayer --json chapters URL
```

`data` is an array of `{ "time", "title" }` objects (time in milliseconds).

### likes

```
hexplayer --json likes URL
```

`likes` returns the like count and your rating state. It is read-only.

### channel / playlist

```
hexplayer --json channel URL [--tab videos|shorts|live|playlists|community|channels|about|home] [--pages N]
hexplayer --json playlist URL
```

`data` is an array of entry objects, same item shape as `search`.

### home / shorts  *(requires Deno and cookies)*

```
hexplayer --json home [--continuation TOKEN]
hexplayer --json shorts [--seed VIDEO_ID]
```

Without a cookies file these return `code: "cookies_missing"`.

### watch-history

```
hexplayer --json watch-history [--online] [--limit N] [--offset N] [--continuation TOKEN]
```

Local history (default) → an array of watched items:

```json
{
  "ok": true,
  "data": [
    {
      "title": "Test Title",
      "url": "https://www.youtube.com/watch?v=kJQP7kiw5Fk",
      "channel_name": "…",
      "watched_seconds": 12.0,
      "last_played": 1790360818.39,
      "type": "video"
    }
  ]
}
```

`--online` uses your YouTube account history and **requires Deno and cookies**.

### favorites

```
hexplayer --json favorites list
hexplayer --json favorites add URL [--title T] [--channel C] [--channel-url U] [--live]
hexplayer --json favorites remove URL
```

`list` → an array of favorite objects:

```json
{
  "ok": true,
  "data": [
    {
      "title": "Title 0",
      "display_title": "Title 0. Author",
      "url": "https://youtube.com/watch?v=bench_0",
      "live": 0,
      "channel_name": "Author 0",
      "channel_url": "https://youtube.com/channel/c_0"
    }
  ]
}
```

`add` / `remove` → a success message with `data: { "url": "…" }`.

### search-history

```
hexplayer --json search-history list
hexplayer --json search-history clear
```

`list` → an array of query strings. `clear` → a success message.

### config

```
hexplayer --json config get KEY
hexplayer --json config set KEY VALUE
hexplayer --json config list
hexplayer --json config path
```

```json
{ "ok": true, "data": { "key": "path", "value": "…/Downloads/HexPlayer" } }
```

`config list` → an object of every setting. `config set` with an unknown key →
`code: "unknown_config_key"`.

### cookies

```
hexplayer --json cookies status
hexplayer --json cookies set PATH
hexplayer --json cookies clear
```

`status` reports **only** whether a cookies file is configured and present. It
never returns the file's contents.

```json
{ "ok": true, "data": { "path": null, "configured": false, "exists": false } }
```

### deps

```
hexplayer --json deps versions
hexplayer --json deps update [--ytdlp] [--deno] [--youtubei] [--pot] [--all]
```

```json
{
  "ok": true,
  "data": {
    "yt_dlp": "2026.08.19",
    "deno": "v2.9.3",
    "youtubei": "18.0.0",
    "pot_provider": "v0.8.1"
  }
}
```

A component that is not installed reports `null`. `deps update` exits non-zero
if any requested update fails.

---

## Integration examples

### Python

```python
import json
import subprocess


def hexplayer(*args, lang="en"):
    """Call the hexplayer CLI in JSON mode and return the parsed envelope."""
    result = subprocess.run(
        ["hexplayer", "--json", "--lang", lang, *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    # Success goes to stdout; handled errors go to stderr. Both are JSON.
    payload = result.stdout.strip() or result.stderr.strip()
    envelope = json.loads(payload)
    if not envelope.get("ok"):
        raise RuntimeError(f"{envelope.get('code')}: {envelope.get('error')}")
    return envelope


results = hexplayer("search", "lofi hip hop")
for item in results["data"]:
    print(item["title"], "->", item["url"])
```

### Node.js

```js
const { execFile } = require("node:child_process");

function hexplayer(args, lang = "en") {
  return new Promise((resolve, reject) => {
    execFile(
      "hexplayer",
      ["--json", "--lang", lang, ...args],
      { encoding: "utf8" },
      (_err, stdout, stderr) => {
        const envelope = JSON.parse((stdout || stderr).trim());
        envelope.ok ? resolve(envelope) : reject(envelope);
      }
    );
  });
}

hexplayer(["info", "https://youtu.be/rFZHOHl-L8A"])
  .then((env) => console.log(env.data.title, env.data.view_count))
  .catch((env) => console.error(env.code, env.error));
```

### Shell + jq

```bash
# Print the URL of the first search result.
hexplayer --json search "lofi" | jq -r '.data[0].url'

# Fail the script if a download did not complete.
hexplayer --json download "https://youtu.be/VIDEO_ID" --format mp3 \
  | jq -e '.ok' >/dev/null || { echo "download failed"; exit 1; }
```

---

## Attribution and Licensing

HexPlayer is free software released under the **GNU General Public License,
version 3.0 (GPL-3.0)**. When you build on top of it — including calling the
`hexplayer` CLI as described in this guide — you take on the obligations of that
license. This section states what this project requires of integrators. It is a
summary for convenience, **not legal advice**; the authoritative terms are in
the `LICENSE` file shipped with HexPlayer, and you should read it in full.

### Required attribution

If your application uses HexPlayer's CLI/API, you **must give explicit, visible
credit to HexPlayer by name**. This is a condition of using the API:

- Name **HexPlayer** explicitly in a place your users can actually see — an
  "About", "Credits", "Acknowledgements", or "Third-party software" screen, your
  documentation, or your project's README.
- Include a link back to the project:
  <https://github.com/makhlwf/accessible_youtube_downloader_pro>.
- Do **not** imply that HexPlayer endorses, sponsors, or is affiliated with your
  application. Attribution credits the software; it does not grant you the
  HexPlayer name as a badge of endorsement.

A minimal, acceptable attribution reads:

```
Powered by HexPlayer — https://github.com/makhlwf/accessible_youtube_downloader_pro
Licensed under GPL-3.0.
```

or, in HTML:

```html
<p>
  Powered by
  <a href="https://github.com/makhlwf/accessible_youtube_downloader_pro">HexPlayer</a>,
  licensed under GPL-3.0.
</p>
```

### GPL-3.0 obligations you should be aware of

Beyond visible attribution, GPL-3.0 carries obligations of its own. In
particular:

- **Preserve the license and copyright notices.** Do not strip HexPlayer's
  `LICENSE`, copyright headers, or notices from the copies you distribute.
- **Distribute the license text.** Anyone who receives HexPlayer (or a build
  that bundles it) must receive a copy of the GPL-3.0 as well.
- **Copyleft on derivative works.** If you modify HexPlayer's own source, or
  combine it with your code such that the result is a derivative work under the
  license, the combined work must itself be offered under GPL-3.0, with
  corresponding source made available.
- **Invoking the CLI as a separate process** (the integration model this guide
  describes) is generally treated differently from linking HexPlayer's code
  directly into your program. The boundary between "separate program" and
  "derivative work" is a legal question that depends on your specifics — if you
  are unsure how the GPL applies to your product, consult a lawyer.

### Summary

1. Use the `hexplayer` CLI as a subprocess, per this guide.
2. Credit **HexPlayer** by name, visibly, with a link — always.
3. Keep the license and notices intact, and comply with GPL-3.0.
4. When in doubt about your obligations, read `LICENSE` and seek legal advice.


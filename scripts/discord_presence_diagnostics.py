#!/usr/bin/env python3
"""HexPlayer Discord Rich Presence diagnostics.

Connects to the local Discord IPC pipe/socket, pushes a sample activity that
includes BOTH presence buttons ("Watch on YouTube" and "Download HexPlayer"),
and prints Discord's raw response so you can confirm the payload — buttons
included — was accepted.

Run with Discord open and logged in:

    uv run python scripts/discord_presence_diagnostics.py

IMPORTANT — where buttons appear (this trips everyone up):
  * You CANNOT see your own Rich Presence buttons. It is a Discord quirk, not a
    bug in HexPlayer. Verify from a second account, a phone, or the web client.
  * Buttons render in the full PROFILE POPOUT / expanded activity card — click
    the user to open it. The compact "Active Now" sidebar never shows buttons.
"""

import sys
import time
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from discord_presence import (
    DEFAULT_CLIENT_ID,
    DiscordRPCClient,
    is_valid_button_url,
)

VIDEO_ID = "dQw4w9WgXcQ"
WATCH_URL = f"https://www.youtube.com/watch?v={VIDEO_ID}"
DOWNLOAD_URL = "https://github.com/makhlwf/accessible_youtube_downloader_pro/releases"
HOLD_SECONDS = 40


def main() -> int:
    buttons = [
        {"label": "Watch on YouTube", "url": WATCH_URL},
        {"label": "Download HexPlayer", "url": DOWNLOAD_URL},
    ]

    print("Validating button URLs before sending...")
    for btn in buttons:
        ok = is_valid_button_url(btn["url"])
        print(f"  [{'OK ' if ok else 'BAD'}] {btn['label']}: {btn['url']}")
        if not ok:
            print("  -> Invalid URL would make Discord reject the whole activity.")
            return 2

    client = DiscordRPCClient(DEFAULT_CLIENT_ID)
    print(f"\nConnecting to Discord IPC (client_id={DEFAULT_CLIENT_ID})...")
    if not client.connect():
        print("FAILED to connect. Is the Discord desktop app running and logged in?")
        return 1
    print("Connected and handshaked.")

    now = int(time.time())
    activity = {
        "details": "HexPlayer button diagnostics",
        "state": "If a friend sees two buttons, it works",
        "timestamps": {"start": now},
        "assets": {
            "large_image": f"https://i.ytimg.com/vi/{VIDEO_ID}/hqdefault.jpg",
            "large_text": "HexPlayer",
        },
        "buttons": buttons,
    }

    print("\nSending SET_ACTIVITY with 2 buttons...")
    sent = client.send_activity(activity)
    resp = client.last_response or {}
    print(f"  send_activity() returned: {sent}")
    print(f"  Discord raw response: {resp}")

    if resp.get("evt") == "ERROR":
        err = resp.get("data") or {}
        print(
            f"\nDiscord REJECTED the payload (code {err.get('code')}): "
            f"{err.get('message')}"
        )
        print("The buttons or another field are malformed. See message above.")
        client.send_activity(None)
        client.close()
        return 3

    print("\nDiscord ACCEPTED the activity (buttons included).")
    print(
        f"Holding presence for {HOLD_SECONDS}s. Now open YOUR profile from a "
        "SECOND account / phone / web client and open the profile popout — the "
        "two buttons appear there (never on your own client, never in the "
        "'Active Now' sidebar)."
    )
    try:
        time.sleep(HOLD_SECONDS)
    except KeyboardInterrupt:
        pass
    finally:
        client.send_activity(None)
        client.close()
    print("Done. Presence cleared.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""YouTube Music subsystem for HexPlayer.

A self-contained, accessible YouTube Music experience built on ytmusicapi. It
reuses the existing stream resolver (``utils.get_playable_stream``), player
(``MediaGui``), downloader, threading model, result-object protocol, scraper,
theming, speech, config, database, and i18n so it integrates natively rather
than feeling like a separate application.

Submodules are imported lazily by callers to avoid pulling heavy dependencies at
package import time.
"""

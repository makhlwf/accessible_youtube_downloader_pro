# Performance and Reliability Enhancement Design - HexPlayer

**Date:** 2026-04-24  
**Status:** Draft  
**Topic:** Application-wide performance optimization, async refactoring, and extraction reliability.

## 1. Executive Summary
HexPlayer currently suffers from performance bottlenecks due to frequent subprocess spawning (Deno), inefficient stream extraction (multiple yt-dlp client retries), and a mixed threading/async model that causes UI lag. This design proposes a transition to a persistent background service architecture and a unified async core to achieve near-instant responsiveness.

## 2. Goals & Success Criteria
- **Goal 1:** Eliminate the 1.5s - 2s lag when loading Home Feed and History.
- **Goal 2:** Reduce stream extraction time by targeting the most reliable client (`android_vr`) immediately.
- **Goal 3:** Ensure zero UI lag during background metadata scraping.
- **Goal 4:** Improve startup speed by deferring non-critical checks.

## 3. Architecture & Components

### 3.1 Persistent Deno Service (JSON-RPC)
Instead of spawning a new Deno process for every metadata request, we will implement a persistent "Service" model.

- **Component:** `DenoService` (Python) and `service.js` (Deno).
- **Communication:** Standard Input (stdin) for commands, Standard Output (stdout) for JSON responses.
- **Commands:** `get_home_feed`, `get_watch_history`, `update_watch_history`.
- **Reliability:** The Python wrapper will monitor the process and automatically restart it if it exits.

### 3.2 Optimized Stream Extraction
We will simplify `utils.get_playable_stream` to prioritize the most successful client.

- **Strategy:** Configure `yt-dlp` to use the `android` client specifically targeting the `vr` player API.
- **Configuration:** `extractor_args = {"youtube": {"player_client": ["android"], "player_skip": ["web", "ios", "mweb"]}}` (or equivalent to force `android_vr`).
- **Parallelism:** If a fallback is needed, we will use `asyncio.gather` to try alternatives concurrently rather than sequentially.

### 3.3 Unified Async Core
Refactor the application's background operations to use a single `asyncio` event loop.

- **Async Scraper:** Replace the threaded `Scraper` with an `asyncio.Queue` based system.
- **Non-blocking Startup:** Move `wx.SingleInstanceChecker`, version checks, and JS dependency verification into the async loop so the main window appears instantly.
- **Throttling:** Implement a "navigation-aware" scraper that pauses or slows down when the user is actively scrolling to prevent screen reader stutter.

## 4. Data Flow

1. **Metadata Request:** UI -> `DenoService.send_command()` -> `stdin` -> `service.js` -> YouTube API -> `stdout` -> UI.
2. **Stream Request:** UI -> `AsyncScraper` -> `yt-dlp` (Android VR) -> `Stream` object -> UI.

## 5. Error Handling
- **Deno Crash:** Python detects `broken pipe` or process exit and respawns the service transparently.
- **Extraction Failure:** If `android_vr` fails, a single fallback to `web_embedded` or `ios` is attempted before reporting an error.
- **Network Issues:** Centralized async exception handling with user-friendly notifications via `wx.CallAfter`.

## 6. Testing Strategy
- **Benchmark:** Measure "Time to First Byte" for Home Feed before and after (target: <200ms).
- **Stress Test:** Rapidly scroll through 100 search results to verify UI responsiveness.
- **Integration:** Mock the Deno service to test Python-side state management without hitting YouTube APIs.

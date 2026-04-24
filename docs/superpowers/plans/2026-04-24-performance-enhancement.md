# Performance Enhancement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Transform HexPlayer into a high-performance, responsive application by implementing a persistent Deno worker, optimized stream extraction (Android VR), and a unified async architecture.

**Architecture:** 
- A persistent `DenoService` replaces transient subprocess calls for metadata.
- `yt-dlp` is hard-coded to prioritize `android_vr` to eliminate extraction retries.
- The UI thread is decoupled from heavy operations using a single `asyncio` event loop.

**Tech Stack:** Python (asyncio), Deno (youtubei.js), yt-dlp, wxPython.

---

### Task 1: Persistent Deno Service (JavaScript side)
**Files:**
- Create: `source/service.js`
- Modify: `source/deno.json` (ensure all imports are present)

- [ ] **Step 1: Implement `service.js`**
Write a Deno script that listens on `stdin` for JSON commands and writes JSON results to `stdout`. Include optimized extraction logic from `get_recommendations.js`.

- [ ] **Step 2: Update `deno.json`**
Ensure `youtubei.js` is correctly mapped.

- [ ] **Step 3: Manual Verification**
Run `deno run --allow-all source/service.js` and pipe in a test JSON command.

- [ ] **Step 4: Commit**
`git add source/service.js source/deno.json && git commit -m "feat: add persistent deno service script"`

---

### Task 2: Python DenoService Wrapper
**Files:**
- Create: `source/deno_service.py`
- Modify: `source/utils.py` (redirect feed calls to `deno_service`)

- [ ] **Step 1: Create `source/deno_service.py`**
Implement a thread-safe `DenoService` class using `subprocess.Popen`.

- [ ] **Step 2: Refactor `source/utils.py`**
Replace `get_home_feed` and `get_watch_history` implementations with calls to `deno_service.send_command`.

- [ ] **Step 3: Commit**
`git add source/deno_service.py source/utils.py && git commit -m "feat: implement persistent deno service wrapper"`

---

### Task 3: Optimized Stream Extraction (Android VR)
**Files:**
- Modify: `source/utils.py`

- [ ] **Step 1: Simplify `get_playable_stream`**
Change `PLAYER_OPTS` and `clients_to_try` to prioritize `android` and specifically the `vr` player API. Remove expensive sequential retries.

- [ ] **Step 2: Parallel Fallback**
Use `asyncio.gather` if multiple clients must be tried, ensuring the fastest one wins.

- [ ] **Step 3: Commit**
`git add source/utils.py && git commit -m "feat: optimize stream extraction targeting android_vr"`

---

### Task 4: Unified Async Core & Scraper Refactor
**Files:**
- Modify: `source/youtube_browser/scraper.py`
- Modify: `source/accessible_youtube_downloader_pro.py`

- [ ] **Step 1: Refactor `Scraper` to Async**
Replace `queue.PriorityQueue` and threads with `asyncio.Queue` and async tasks.

- [ ] **Step 2: Implement Scraper Throttling**
Add logic to slow down or pause background scraping when the user is actively navigating.

- [ ] **Step 3: Async Startup**
Move `SingleInstanceChecker` and version checks into the existing async loop in `accessible_youtube_downloader_pro.py`.

- [ ] **Step 4: Commit**
`git add source/youtube_browser/scraper.py source/accessible_youtube_downloader_pro.py && git commit -m "feat: unify async core and refactor scraper"`

---

### Task 5: Final Validation & Cleanup
- [ ] **Step 1: Full Application Test**
Verify Home Feed loads instantly, History works, and Search/Playback is lag-free.
- [ ] **Step 2: Resource Usage Check**
Confirm Deno and yt-dlp don't leak processes or consume excessive CPU.
- [ ] **Step 3: Final Commit**
`git commit -m "chore: final performance enhancement cleanup"`

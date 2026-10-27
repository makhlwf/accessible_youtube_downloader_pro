"""Deterministic worker/UI queue tests; no real wx loop, network, or sleeps."""

from collections import deque
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from types import SimpleNamespace

import pytest

import download_handler.downloader as downloader_module
from download_handler.downloader import DownloadCancelled, Downloader


class ManualGuiLoop:
    def __init__(self):
        self.now = 0.0
        self.wall_time = 1000.0
        self.on_ui_thread = False
        self.callbacks = deque()
        self.timers = []
        self.call_after_count = 0
        self.trace = []

    def require_ui(self):
        assert self.on_ui_thread, "wx window/timer accessed from a worker"

    def ui(self, callback, *args, **kwargs):
        previous = self.on_ui_thread
        self.on_ui_thread = True
        try:
            return callback(*args, **kwargs)
        finally:
            self.on_ui_thread = previous

    def call_after(self, callback, *args, **kwargs):
        self.call_after_count += 1
        self.callbacks.append((callback, args, kwargs))

    def call_later(self, milliseconds, callback, *args):
        self.require_ui()
        assert milliseconds > 0
        timer = SimpleNamespace(
            deadline=self.now + milliseconds / 1000,
            callback=callback,
            args=args,
            running=True,
        )

        def stop():
            self.require_ui()
            timer.running = False

        timer.Stop = stop
        self.timers.append(timer)
        return timer

    @property
    def pending_count(self):
        return len(self.callbacks) + sum(timer.running for timer in self.timers)

    def pump(self):
        for _ in range(10000):
            if self.callbacks:
                callback, args, kwargs = self.callbacks.popleft()
                self.ui(callback, *args, **kwargs)
                continue
            timer = next(
                (t for t in self.timers if t.running and t.deadline <= self.now),
                None,
            )
            if timer is None:
                return
            timer.running = False
            self.ui(timer.callback, *timer.args)
        pytest.fail("GUI callbacks did not quiesce")

    def advance(self, seconds):
        self.now += seconds
        self.pump()


class GuardedWindow:
    """Reject both worker access and access to deleted native windows."""

    def __init__(self, loop):
        self.loop = loop
        self.state = "alive"
        self.bindings = {}
        self.events = []
        self.event_times = []
        self.values = []
        self.strings = {}

    def __bool__(self):
        self.loop.require_ui()
        if self.state == "dead-wrapper":
            raise RuntimeError("wrapped C/C++ object has been deleted")
        return self.state != "destroyed"

    def IsBeingDeleted(self):
        self.loop.require_ui()
        return self.state == "deleting"

    def require_live(self):
        self.loop.require_ui()
        assert self.state == "alive", "accessed a destroyed wx window"

    def Bind(self, event_type, callback):
        self.require_live()
        self.bindings[event_type] = callback

    def GetEventHandler(self):
        self.require_live()
        return self

    def ProcessEvent(self, event):
        self.require_live()
        self.events.append(event)
        self.event_times.append(self.loop.now)
        self.loop.trace.append(("progress", event.value))
        handler = self.bindings.get(downloader_module.EVT_PROGRESS_CHANGED)
        if handler is not None:
            handler(event)
        return True

    def SetValue(self, value):
        self.require_live()
        self.values.append(value)

    def SetString(self, index, value):
        self.require_live()
        self.strings[index] = value


class GuardedDialog(GuardedWindow):
    def __init__(self, loop, parent):
        super().__init__(loop)
        self.parent = parent
        self.cancel_callback = None
        self.cancel_queries = 0
        self.finished = False
        self.destroy_count = 0

    def set_cancel_callback(self, callback):
        self.require_live()
        self.cancel_callback = callback

    def is_cancelled(self):
        self.require_live()
        self.cancel_queries += 1
        return False

    def GetParent(self):
        self.require_live()
        return self.parent

    def Show(self):
        self.require_live()

    def mark_finished(self):
        self.require_live()
        self.finished = True
        self.loop.trace.append(("finished",))

    def Destroy(self):
        self.require_live()
        self.state = "destroyed"
        self.destroy_count += 1
        self.loop.trace.append(("destroyed",))
        handler = self.bindings.get(downloader_module.wx.EVT_WINDOW_DESTROY)
        if handler is not None:
            handler(SimpleNamespace(GetEventObject=lambda: self, Skip=lambda: None))


@pytest.fixture
def loop(monkeypatch):
    loop = ManualGuiLoop()
    # Patch the module reference, not the process-wide time module used by pytest.
    monkeypatch.setattr(
        downloader_module,
        "time",
        SimpleNamespace(
            monotonic=lambda: loop.now,
            time=lambda: loop.wall_time,
        ),
    )
    monkeypatch.setattr(downloader_module.wx, "CallAfter", loop.call_after)
    monkeypatch.setattr(downloader_module.wx, "CallLater", loop.call_later)
    monkeypatch.setattr(
        downloader_module.wx,
        "PostEvent",
        lambda window, event: loop.call_after(window.ProcessEvent, event),
    )
    monkeypatch.setattr(downloader_module, "ProgressChangedEvent", SimpleNamespace)
    return loop


@pytest.fixture
def progress(loop):
    monitor = GuardedWindow(loop)
    downloader = Downloader("url", ".", "best", monitor, None)
    return downloader, monitor


def downloading(percent, **fields):
    return {"status": "downloading", "_percent_str": f"{percent}%", **fields}


def test_burst_keeps_one_queued_callback_and_the_latest_snapshot(loop, progress):
    downloader, monitor = progress
    data = downloading(0)
    for index in range(2000):
        loop.now = index / 1000
        data.update(
            _percent_str=f"{index % 101}%",
            _downloaded_bytes_str=f"{index}KiB",
        )
        downloader._progress_hook(data)
        assert loop.pending_count == 1

    data.update(
        _percent_str="100%",
        _total_bytes_str="[0;94m2000KiB[0m",
        _speed_str="[0;33m20MiB/s[0m",
        _eta_str="00:00",
    )
    downloader._progress_hook(data)
    # yt-dlp can reuse/mutate its hook dictionary after returning from the hook.
    data["_percent_str"] = "1%"
    data["_downloaded_bytes_str"] = "stale"
    assert loop.call_after_count == 1
    assert monitor.events == []

    loop.pump()

    assert len(monitor.events) == 1
    assert vars(monitor.events[0]) == {
        "value": 100,
        "total": "2000KiB",
        "downloaded": "1999KiB",
        "speed": "20MiB/s",
        "eta": "00:00",
    }
    assert loop.pending_count == 0


def test_parallel_hooks_share_one_pending_gui_wakeup(loop, progress):
    downloader, monitor = progress
    ready = Barrier(4)

    def burst(worker):
        ready.wait(timeout=5)
        for index in range(100):
            downloader._progress_hook(downloading(index, _speed_str=str(worker)))

    with ThreadPoolExecutor(max_workers=4) as workers:
        futures = [workers.submit(burst, worker) for worker in range(4)]
        for future in futures:
            future.result(timeout=5)
    downloader._progress_hook(downloading(100, _speed_str="latest"))

    assert loop.call_after_count == 1
    assert loop.pending_count == 1
    loop.pump()
    assert len(monitor.events) == 1
    assert monitor.events[0].value == 100
    assert monitor.events[0].speed == "latest"


def test_progress_is_rate_limited_by_monotonic_time_even_at_100_percent(loop, progress):
    downloader, monitor = progress
    for tick in range(1001):
        loop.now = tick / 1000
        loop.wall_time = 1000000.0 if tick % 2 else -1000000.0
        downloader._progress_hook(downloading(100 if tick % 2 else 0))
        loop.pump()
        assert loop.pending_count <= 1

    assert 9 <= len(monitor.events) <= 11
    assert all(
        later - earlier >= downloader_module._PROGRESS_INTERVAL
        for earlier, later in zip(monitor.event_times, monitor.event_times[1:])
    )
    assert loop.call_after_count <= 12
    loop.advance(0.2)
    assert monitor.events[-1].value == 0
    assert loop.pending_count == 0


def test_throttled_trailing_update_arrives_without_another_hook(loop, progress):
    downloader, monitor = progress
    downloader._progress_hook(downloading(10))
    loop.pump()
    loop.now = 0.01
    downloader._progress_hook(downloading(55, _downloaded_bytes_str="55MiB"))
    loop.pump()

    assert [event.value for event in monitor.events] == [10]
    assert loop.pending_count == 1
    loop.advance(0.2)
    assert [event.value for event in monitor.events] == [10, 55]
    assert monitor.events[-1].downloaded == "55MiB"
    assert loop.pending_count == 0


def test_finished_payload_survives_throttling_and_preserves_latest_details(
    loop, progress
):
    downloader, monitor = progress
    downloader._progress_hook(downloading(1, _total_bytes_str="100MiB"))
    loop.pump()
    loop.now = 0.01
    downloader._progress_hook(
        downloading(95, _downloaded_bytes_str="95MiB", _speed_str="5MiB/s")
    )
    loop.pump()
    callbacks_before_finish = loop.call_after_count
    for _ in range(100):
        downloader._progress_hook({"status": "finished", "_total_bytes_str": "100MiB"})

    assert loop.call_after_count == callbacks_before_finish
    assert loop.pending_count == 1
    loop.advance(0.2)
    assert [event.value for event in monitor.events] == [1, 100]
    assert monitor.events[-1].total == "100MiB"
    assert monitor.events[-1].downloaded == "95MiB"
    assert monitor.events[-1].speed == "5MiB/s"


@pytest.mark.parametrize("status", ["downloading", "finished", "error", None])
@pytest.mark.parametrize("with_monitor", [True, False])
def test_every_hook_checks_cancellation_before_throttling_or_status(
    loop, progress, status, with_monitor
):
    downloader, monitor = progress
    if not with_monitor:
        downloader.monitor = None
    checks = []
    requested = False

    def cancelled():
        checks.append(True)
        return requested

    downloader.cancel_checker = cancelled
    downloader._progress_hook(downloading(10))
    requested = True
    with pytest.raises(DownloadCancelled):
        downloader._progress_hook({"status": status})

    assert len(checks) == 2
    loop.pump()
    assert monitor.events == []
    assert loop.pending_count == 0


def test_cancellation_discards_an_already_scheduled_timer(loop, progress):
    downloader, monitor = progress
    downloader._progress_hook(downloading(10))
    loop.pump()
    loop.now = 0.01
    downloader._progress_hook(downloading(20))
    loop.pump()
    downloader.cancel()
    loop.advance(0.2)

    assert [event.value for event in monitor.events] == [10]
    assert loop.pending_count == 0
    with pytest.raises(DownloadCancelled):
        downloader._progress_hook({"status": "finished"})


@pytest.mark.parametrize("state", ["destroyed", "deleting", "dead-wrapper"])
def test_queued_progress_safely_discards_a_destroyed_monitor(loop, progress, state):
    downloader, monitor = progress
    downloader._progress_hook(downloading(10))
    monitor.state = state
    loop.pump()

    assert monitor.events == []
    assert loop.pending_count == 0
    assert downloader.cancelled


@pytest.mark.parametrize("state", ["destroyed", "deleting", "dead-wrapper"])
def test_destroyed_monitor_discards_the_scheduled_trailing_timer(loop, progress, state):
    downloader, monitor = progress
    downloader._progress_hook(downloading(10))
    loop.pump()
    loop.now = 0.01
    downloader._progress_hook(downloading(20))
    loop.pump()
    monitor.state = state
    loop.advance(0.2)

    assert [event.value for event in monitor.events] == [10]
    assert loop.pending_count == 0
    assert downloader.cancelled


@pytest.mark.parametrize(
    ("value", "expected"),
    [("n/a", 0), ("nan", 0), ("inf", 0), ("-25", 0), ("150", 100)],
)
def test_invalid_percentages_do_not_break_gui_dispatch(loop, progress, value, expected):
    downloader, monitor = progress
    downloader._progress_hook(downloading(value))
    loop.pump()
    assert monitor.events[-1].value == expected


@pytest.fixture
def action(loop, monkeypatch, tmp_path):
    parent = GuardedWindow(loop)
    dialog = GuardedDialog(loop, parent)
    monitor = GuardedWindow(loop)
    label = GuardedWindow(loop)
    context = SimpleNamespace(
        dialog=dialog,
        monitor=monitor,
        label=label,
        result=0,
        calls=0,
        download_hook=None,
        workers=[],
        notices=[],
    )

    class DeferredThread:
        def __init__(self, target):
            self.target = target

        def start(self):
            context.workers.append(self.target)

    def run_download(downloader):
        context.calls += 1
        if context.download_hook is not None:
            context.download_hook(downloader)
        return context.result

    def notice(kind, *args, **kwargs):
        loop.require_ui()
        context.notices.append((kind, args, kwargs))
        loop.trace.append((kind,))

    def get_app():
        loop.require_ui()
        return SimpleNamespace(GetTopWindow=lambda: parent)

    monkeypatch.setattr(downloader_module, "Thread", DeferredThread)
    monkeypatch.setattr(Downloader, "download_with_cookie_fallback", run_download)
    monkeypatch.setattr(downloader_module.utils, "check_yt_dlp", lambda parent: True)
    monkeypatch.setattr(downloader_module.wx, "GetApp", get_app)
    monkeypatch.setattr(
        downloader_module.wx, "MessageBox", lambda *a, **kw: notice("cancel", *a, **kw)
    )
    monkeypatch.setattr(
        downloader_module.utils,
        "show_error",
        lambda *a, **kw: notice("error", *a, **kw),
    )
    monkeypatch.setattr(
        "gui.download_complete_dialog.show_download_complete",
        lambda *a, **kw: notice("complete", *a, **kw),
    )
    assert loop.ui(
        downloader_module.downloadAction,
        "url",
        str(tmp_path),
        dialog,
        "best",
        monitor,
        label,
    )
    context.downloader = dialog.cancel_callback.__self__
    return context


def test_completion_flushes_final_progress_before_destroying_dialog(loop, action):
    downloader = action.downloader
    downloader._progress_hook(downloading(10))
    loop.pump()
    loop.now = 0.01
    downloader._progress_hook(downloading(20))
    loop.pump()
    assert loop.pending_count == 1
    action.download_hook = lambda dl: dl._progress_hook({"status": "finished"})

    action.workers[0]()
    # Completion is queued while the progress timer is not yet due.
    loop.pump()

    assert action.monitor.values == [10, 100]
    assert loop.trace.index(("progress", 100)) < loop.trace.index(("destroyed",))
    assert action.dialog.finished
    assert action.dialog.destroy_count == 1
    assert [kind for kind, _, _ in action.notices] == ["complete"]
    assert loop.pending_count == 0
    loop.advance(1)
    assert action.monitor.values == [10, 100]


def test_completion_can_overtake_the_queued_progress_callback(loop, action):
    action.download_hook = lambda dl: dl._progress_hook({"status": "finished"})
    action.workers[0]()
    assert loop.pending_count == 2  # One progress wakeup plus completion.
    loop.callbacks.reverse()
    loop.pump()

    assert action.monitor.values == [100]
    assert action.dialog.destroy_count == 1
    assert [kind for kind, _, _ in action.notices] == ["complete"]
    assert loop.pending_count == 0


@pytest.mark.parametrize("result", [0, DownloadCancelled(), RuntimeError("failed")])
@pytest.mark.parametrize("state", ["destroyed", "deleting", "dead-wrapper"])
def test_queued_completion_is_safe_after_dialog_destruction(
    loop, action, result, state
):
    action.result = result
    action.workers[0]()
    action.dialog.state = state
    loop.pump()

    assert not action.dialog.finished
    assert action.dialog.destroy_count == 0
    assert action.notices == []
    assert loop.pending_count == 0


@pytest.mark.parametrize("window", ["dialog", "label"])
def test_progress_handler_checks_all_window_lifetimes(loop, action, window):
    action.downloader._progress_hook(downloading(50))
    getattr(action, window).state = "destroyed"
    loop.pump()

    assert action.monitor.values == []
    assert action.label.strings == {}
    assert action.downloader.cancelled


def test_worker_uses_cancel_token_without_querying_dialog(loop, action):
    queries_before_work = action.dialog.cancel_queries
    action.download_hook = lambda dl: dl._progress_hook(downloading(50))
    action.workers[0]()
    assert action.dialog.cancel_queries == queries_before_work
    assert action.monitor.values == []
    loop.pump()
    assert action.monitor.values == [50]


def test_destroy_event_cancels_worker_but_child_destroy_does_not(loop, action):
    on_destroy = action.dialog.bindings[downloader_module.wx.EVT_WINDOW_DESTROY]
    event = SimpleNamespace(GetEventObject=lambda: action.monitor, Skip=lambda: None)
    loop.ui(on_destroy, event)
    assert not action.downloader.cancelled

    loop.ui(action.dialog.Destroy)
    assert action.downloader.cancelled
    with pytest.raises(DownloadCancelled):
        action.downloader._progress_hook({"status": "finished"})


def test_late_cancellation_does_not_show_queued_success(loop, action):
    action.workers[0]()
    loop.ui(action.dialog.cancel_callback)
    loop.pump()
    assert [kind for kind, _, _ in action.notices] == ["cancel"]
    assert action.dialog.destroy_count == 1


def test_cancelled_worker_is_not_retried(loop, action):
    action.result = RuntimeError("cookie error")
    action.download_hook = lambda downloader: downloader.cancel()
    action.workers[0]()
    loop.pump()
    assert action.calls == 1
    assert [kind for kind, _, _ in action.notices] == ["cancel"]


@pytest.mark.parametrize("wrapped_error", [False, True])
def test_late_or_wrapped_cancellation_is_not_success_or_cookie_retry(
    monkeypatch, tmp_path, wrapped_error
):
    downloader = Downloader("url", str(tmp_path), "best", None, None)
    calls = []

    class FakeYoutubeDL:
        def __init__(self, options):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def download(self, urls):
            calls.append(urls)
            downloader.cancel()
            if wrapped_error:
                raise RuntimeError("cookie download interrupted")

    monkeypatch.setattr(downloader_module.utils, "YoutubeDL", FakeYoutubeDL)
    monkeypatch.setattr(downloader, "_base_options", lambda **kwargs: {})
    result = downloader.download_with_cookie_fallback()
    assert isinstance(result, DownloadCancelled)
    assert calls == [["url"]]


@pytest.mark.parametrize(
    ("hook", "payload"),
    [
        ("_after_move_hook", "download.mp4"),
        ("_postprocessor_hook", {"status": "started"}),
        ("_postprocessor_hook", {"status": "finished"}),
    ],
)
def test_postprocessing_hooks_also_observe_cancellation(hook, payload):
    downloader = Downloader("url", ".", "best", None, None)
    downloader.cancel()
    with pytest.raises(DownloadCancelled):
        getattr(downloader, hook)(payload)

"""Deterministic RPC tests with local output pipes, never a JS runtime/network."""

import json
import os
import queue
import threading
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

import deno_service


class _InputPipe:
    def __init__(self, process):
        self.process = process
        self.closed = False
        self.pending = ""

    def write(self, payload):
        self.process.write_started.set()
        if self.process.block_writes:
            self.process.release_write.wait()
        if self.closed or self.process.poll() is not None:
            raise BrokenPipeError("closed input pipe")
        self.pending += payload
        return len(payload)

    def flush(self):
        assert self.pending.endswith("\n")
        self.process.payloads.append(self.pending)
        self.process.requests.put(json.loads(self.pending))
        self.pending = ""

    def close(self):
        self.closed = True


class _PipeProcess:
    """A controllable child with actual blocking TextIOWrapper output pipes."""

    def __init__(self, *, keep_outputs_open=False, block_writes=False):
        self.returncode = None
        self.requests = queue.Queue()
        self.payloads = []
        self.exited = threading.Event()
        self.reaped = threading.Event()
        self.write_started = threading.Event()
        self.release_write = threading.Event()
        self.kill_count = 0
        self.keep_outputs_open = keep_outputs_open
        self.block_writes = block_writes
        self._output_lock = threading.Lock()
        self.stdin = _InputPipe(self)
        self.stdout, self._stdout_writer = self._pipe()
        self.stderr, self._stderr_writer = self._pipe()

    @staticmethod
    def _pipe():
        reader, writer = os.pipe()
        return (
            os.fdopen(reader, "r", encoding="utf-8"),
            os.fdopen(writer, "w", encoding="utf-8"),
        )

    def poll(self):
        return self.returncode

    def kill(self):
        self.kill_count += 1
        self.returncode = -9
        self.exited.set()
        self.release_write.set()
        if not self.keep_outputs_open:
            self.close_outputs()

    def wait(self, timeout):
        if not self.exited.wait(timeout):
            raise deno_service.subprocess.TimeoutExpired("local pipe child", timeout)
        self.reaped.set()
        return self.returncode

    def emit(self, line, *, stderr=False):
        with self._output_lock:
            writer = self._stderr_writer if stderr else self._stdout_writer
            writer.write(line)
            writer.flush()

    def respond(self, request, result):
        self.emit(json.dumps({"id": request["id"], "result": result}) + "\n")

    def close_outputs(self):
        with self._output_lock:
            self._stdout_writer.close()
            self._stderr_writer.close()

    def finish(self):
        self.returncode = self.returncode if self.returncode is not None else 0
        self.exited.set()
        self.release_write.set()
        self.close_outputs()


class _Call:
    def __init__(self, function, *args):
        self.results = queue.Queue()
        self.thread = threading.Thread(
            target=lambda: self.results.put(function(*args)), daemon=True
        )
        self.thread.start()

    def result(self, timeout=2):
        self.thread.join(timeout)
        assert not self.thread.is_alive(), "RPC operation did not finish promptly"
        return self.results.get_nowait()


class _ObservedLock:
    """Signal when a caller reaches the occupied request gate; no timing sleeps."""

    def __init__(self):
        self.lock = threading.Lock()
        self.contended = threading.Event()

    def acquire(self, **kwargs):
        if self.lock.locked():
            self.contended.set()
        return self.lock.acquire(**kwargs)

    def release(self):
        self.lock.release()


@pytest.fixture
def make_bridge(monkeypatch, tmp_path):
    services = []
    children = []
    states = []
    original_start = deno_service._ProcessIO.start

    def record_start(io):
        states.append(io)
        original_start(io)

    monkeypatch.setattr(deno_service._ProcessIO, "start", record_start)
    monkeypatch.setattr("settings_handler.config_get", lambda key: False)
    monkeypatch.setattr(
        deno_service.paths,
        "get_youtube_service_path",
        lambda: str(tmp_path / "youtube_service"),
    )

    def make(*processes, timeout=2):
        children.extend(processes)
        popen = Mock(side_effect=processes)
        monkeypatch.setattr(deno_service.subprocess, "Popen", popen)
        service = deno_service.DenoService(request_timeout=timeout)
        services.append(service)
        return service, popen

    yield make

    # Release even deliberately stalled pipes before joining, including on a
    # failing assertion, so regression tests cannot hang the test runner.
    for process in children:
        process.finish()
    for service in services:
        _Call(service.stop).result()
    for io in states:
        for thread in (io.worker, io.stderr_reader):
            if thread is not None and thread.ident is not None:
                thread.join(2)
                assert not thread.is_alive(), "process I/O thread leaked"
    for process in children:
        process.stdin.close()
        process.stdout.close()
        process.stderr.close()


def _assert_cleaned(io):
    for thread in (io.worker, io.stderr_reader):
        thread.join(2)
        assert not thread.is_alive()
    assert io.process.reaped.is_set()
    assert io.process.stdin.closed
    assert io.process.stdout.closed
    assert io.process.stderr.closed


@pytest.mark.parametrize("partial_line", ["", '{"id": 1, "result":'])
def test_stalled_response_is_bounded_and_next_command_recovers(
    make_bridge, partial_line
):
    stalled, healthy = _PipeProcess(), _PipeProcess()
    service, popen = make_bridge(stalled, healthy, timeout=0.2)

    call = _Call(service.send_command, "post_video_comment", {"text": "only once"})
    request = stalled.requests.get(timeout=2)
    old_io = service._io
    assert request["command"] == "post_video_comment"
    if partial_line:
        stalled.emit(partial_line)

    assert call.result() == {"error": "Deno service not available"}
    assert service.process is None
    assert popen.call_count == 1  # A timed-out write must never be replayed.
    assert len(stalled.payloads) == 1
    _assert_cleaned(old_io)

    recovered = _Call(service.send_command, "get_home_feed")
    next_request = healthy.requests.get(timeout=2)
    assert next_request["id"] > request["id"]
    healthy.respond(next_request, {"videos": []})
    assert recovered.result() == {"videos": []}
    assert popen.call_count == 2


def test_stop_interrupts_active_and_queued_calls_without_restarting(make_bridge):
    stalled, healthy = _PipeProcess(), _PipeProcess()
    service, popen = make_bridge(stalled, healthy, timeout=30)
    service.lock = _ObservedLock()
    active = _Call(service.send_command, "post_video_comment")
    stalled.requests.get(timeout=2)
    old_io = service._io
    queued = _Call(service.send_command, "get_home_feed")
    assert service.lock.contended.wait(2)

    assert _Call(service.stop).result() is None
    assert active.result() == {"error": "Deno service not available"}
    assert queued.result() == {"error": "Deno service not available"}
    assert service.process is None
    assert popen.call_count == 1
    assert len(stalled.payloads) == 1
    _assert_cleaned(old_io)
    service.stop()  # Repeated shutdown is harmless.
    assert stalled.kill_count == 1

    recovered = _Call(service.send_command, "get_home_feed")
    healthy.respond(healthy.requests.get(timeout=2), "fresh")
    assert recovered.result() == "fresh"


def test_queue_timeout_does_not_kill_or_extend_the_active_request(make_bridge):
    process = _PipeProcess()
    service, popen = make_bridge(process, timeout=30)
    service.lock = _ObservedLock()
    active = _Call(service.send_command, "get_home_feed")
    request = process.requests.get(timeout=2)
    # The active call already captured its long deadline. Give the queued call
    # a short budget so this test needs no sleeps or runtime/network scheduling.
    service._request_timeout = 0.1
    queued = _Call(service.send_command, "get_video_comments")
    assert service.lock.contended.wait(2)

    assert queued.result() == {"error": "Deno service not available"}
    assert active.thread.is_alive()
    assert process.kill_count == 0
    assert service.process is process
    assert process.requests.empty()
    assert popen.call_count == 1
    process.respond(request, "active response")
    assert active.result() == "active response"


def test_queue_and_response_wait_use_one_deadline(make_bridge, monkeypatch):
    process = _PipeProcess()
    service, _ = make_bridge(process, timeout=10)
    io = service._ensure_process()
    clock = SimpleNamespace(now=0.0)
    monkeypatch.setattr(
        deno_service, "time", SimpleNamespace(monotonic=lambda: clock.now)
    )

    def acquire(*, timeout):
        assert timeout == 10
        clock.now = 8.0  # Eight seconds of the budget were spent queueing.
        return True

    service.lock = Mock(acquire=Mock(side_effect=acquire))
    response_get = Mock(side_effect=queue.Empty)
    monkeypatch.setattr(io.responses, "get", response_get)

    assert service.send_command("get_home_feed") == {
        "error": "Deno service not available"
    }
    response_get.assert_called_once_with(timeout=2.0)
    service.lock.release.assert_called_once()
    _assert_cleaned(io)


def test_concurrent_requests_remain_serialized_with_distinct_ids(make_bridge):
    process = _PipeProcess()
    service, popen = make_bridge(process)
    service.lock = _ObservedLock()
    first = _Call(service.send_command, "get_home_feed", {"language": "ar"})
    first_request = process.requests.get(timeout=2)
    second = _Call(service.send_command, "get_video_comments", {"videoId": "video"})
    assert service.lock.contended.wait(2)
    assert process.requests.empty()
    assert len(process.payloads) == 1

    process.respond(first_request, ["first"])
    assert first.result() == ["first"]
    second_request = process.requests.get(timeout=2)
    assert first_request["id"] != second_request["id"]
    assert second_request["command"] == "get_video_comments"
    assert second_request["params"] == {"videoId": "video"}
    process.respond(second_request, ["second"])
    assert second.result() == ["second"]
    assert popen.call_count == 1
    assert process.kill_count == 0


@pytest.mark.parametrize(
    "response",
    [
        "not JSON\n",
        "[]\n",
        "null\n",
        '"not an object"\n',
        '{"id": 999, "result": "wrong request"}\n',
        '{"result": "missing ID"}\n',
        '{"id": "1", "result": "string ID"}\n',
        '{"id": true, "result": "boolean ID"}\n',
        '{"id": 1.0, "result": "float ID"}\n',
    ],
)
def test_bad_response_discards_only_that_process_and_recovers(make_bridge, response):
    broken, healthy = _PipeProcess(), _PipeProcess()
    service, popen = make_bridge(broken, healthy)
    first = _Call(service.send_command, "get_home_feed")
    broken.requests.get(timeout=2)
    old_io = service._io
    broken.emit(response)
    assert "error" in first.result()
    assert service.process is None
    assert popen.call_count == 1
    _assert_cleaned(old_io)

    second = _Call(service.send_command, "get_home_feed")
    healthy.respond(healthy.requests.get(timeout=2), {"ok": True})
    assert second.result() == {"ok": True}
    assert popen.call_count == 2


def test_remote_errors_and_result_values_keep_the_public_api(make_bridge):
    process = _PipeProcess()
    service, popen = make_bridge(process)
    call = _Call(service.send_command, "get_home_feed")
    request = process.requests.get(timeout=2)
    process.emit(json.dumps({"id": request["id"], "error": "upstream error"}) + "\n")
    assert call.result() == {"error": "upstream error"}

    for result in (None, [], {}, 0, False, "text", {"videos": ["video"]}):
        call = _Call(service.send_command, "get_home_feed")
        process.respond(process.requests.get(timeout=2), result)
        assert call.result() == result
    assert popen.call_count == 1
    assert process.kill_count == 0


@pytest.mark.parametrize("failure", ["eof", "write", "read"])
def test_transport_failure_does_not_retry_non_idempotent_commands(
    make_bridge, monkeypatch, failure
):
    broken, healthy = _PipeProcess(), _PipeProcess()
    service, popen = make_bridge(broken, healthy)
    if failure == "write":
        monkeypatch.setattr(
            broken.stdin, "write", Mock(side_effect=BrokenPipeError("broken stdin"))
        )
    elif failure == "read":
        monkeypatch.setattr(
            broken.stdout, "readline", Mock(side_effect=OSError("broken stdout"))
        )

    call = _Call(service.send_command, "reply_to_comment", {"text": "only once"})
    if failure == "eof":
        broken.requests.get(timeout=2)
        broken.finish()
    assert "error" in call.result()
    assert popen.call_count == 1
    assert service.process is None

    recovered = _Call(service.send_command, "get_home_feed")
    healthy.respond(healthy.requests.get(timeout=2), "recovered")
    assert recovered.result() == "recovered"
    assert popen.call_count == 2


@pytest.mark.parametrize("interrupt", ["timeout", "stop"])
def test_stalled_stdin_write_is_also_interruptible(make_bridge, interrupt):
    process = _PipeProcess(block_writes=True)
    service, popen = make_bridge(process, timeout=0.1 if interrupt == "timeout" else 30)
    call = _Call(service.send_command, "post_video_comment")
    assert process.write_started.wait(2)
    io = service._io
    if interrupt == "stop":
        assert _Call(service.stop).result() is None
    assert call.result() == {"error": "Deno service not available"}
    assert popen.call_count == 1
    assert process.requests.empty()
    _assert_cleaned(io)


def test_late_old_response_cannot_satisfy_a_new_process_request(make_bridge):
    old, new = _PipeProcess(keep_outputs_open=True), _PipeProcess()
    service, _ = make_bridge(old, new, timeout=0.1)
    first = _Call(service.send_command, "get_home_feed")
    old.requests.get(timeout=2)
    old_io = service._io
    assert first.result() == {"error": "Deno service not available"}
    assert old_io.worker.is_alive()  # Simulate an old pipe taking time to unblock.

    service._request_timeout = 2
    second = _Call(service.send_command, "get_home_feed")
    new_request = new.requests.get(timeout=2)
    new_io = service._io
    # Even an old response with the new ID must stay in the old process queue.
    old.respond(new_request, "stale")
    old.close_outputs()
    _assert_cleaned(old_io)
    assert second.thread.is_alive()
    assert service.process is new
    assert service._io is new_io
    assert new.kill_count == 0

    new.respond(new_request, "fresh")
    assert second.result() == "fresh"


def test_stderr_reader_binds_its_process_before_a_restart(
    make_bridge, monkeypatch, caplog
):
    old, new = _PipeProcess(), _PipeProcess()
    service, _ = make_bridge(old, new)
    reader_entered = threading.Event()
    release_reader = threading.Event()
    original_reader = deno_service._ProcessIO._log_stderr

    def delayed_reader(io):
        if io.process is old:
            reader_entered.set()
            release_reader.wait(2)
        original_reader(io)

    monkeypatch.setattr(deno_service._ProcessIO, "_log_stderr", delayed_reader)
    try:
        old_io = service._ensure_process()
        assert reader_entered.wait(2)
        old.emit("old process stderr\n", stderr=True)
        service.stop()
        new_io = service._ensure_process()
        new.emit("new process stderr\n", stderr=True)
        release_reader.set()
        _assert_cleaned(old_io)
        assert service.process is new
        service.stop()
        _assert_cleaned(new_io)
    finally:
        release_reader.set()
    assert "Deno service stderr: old process stderr" in caplog.text
    assert "Deno service stderr: new process stderr" in caplog.text


def test_dead_process_is_reaped_and_its_pipes_closed_before_reuse(make_bridge):
    old, new = _PipeProcess(), _PipeProcess()
    service, popen = make_bridge(old, new)
    old_io = service._ensure_process()
    old.finish()
    call = _Call(service.send_command, "get_home_feed")
    new.respond(new.requests.get(timeout=2), "new process")
    assert call.result() == "new process"
    assert popen.call_count == 2
    _assert_cleaned(old_io)


def test_stop_during_startup_does_not_publish_the_old_process(make_bridge):
    old, new = _PipeProcess(), _PipeProcess()
    service, popen = make_bridge(old, new, timeout=30)
    launch_entered = threading.Event()
    release_launch = threading.Event()

    def launch(*args, **kwargs):
        if popen.call_count == 1:
            launch_entered.set()
            release_launch.wait(2)
            return old
        return new

    popen.side_effect = launch
    try:
        call = _Call(service.send_command, "post_video_comment")
        assert launch_entered.wait(2)
        assert _Call(service.stop).result() is None
        assert service.process is None
        release_launch.set()
        assert call.result() == {"error": "Deno service not available"}
        assert old.exited.wait(2)
        assert old.requests.empty()
        assert service.process is None
    finally:
        release_launch.set()

    recovered = _Call(service.send_command, "get_home_feed")
    new.respond(new.requests.get(timeout=2), "recovered")
    assert recovered.result() == "recovered"


def test_worker_start_failure_closes_unused_pipes(make_bridge, monkeypatch):
    process = _PipeProcess()
    service, _ = make_bridge(process)
    with monkeypatch.context() as patch:
        patch.setattr(
            deno_service.threading.Thread,
            "start",
            Mock(side_effect=RuntimeError("thread start failed")),
        )
        assert service._ensure_process() is None
    assert service.process is None
    assert process.reaped.is_set()
    assert process.stdin.closed
    assert process.stdout.closed
    assert process.stderr.closed


@pytest.mark.parametrize("timeout", [0, -1, float("inf"), float("nan")])
def test_timeout_must_be_positive_and_finite(timeout):
    with pytest.raises(ValueError):
        deno_service.DenoService(request_timeout=timeout)

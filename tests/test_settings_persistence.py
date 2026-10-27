"""Deterministic settings scheduling, concurrency and crash-safety regressions."""

import configparser
import importlib.util
import os
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace

import pytest

import settings_handler


def read_settings(path):
    config = configparser.ConfigParser()
    config.optionxform = str
    config.read(path / "settings.ini", encoding="utf-8")
    return config["settings"]


@pytest.fixture
def settings(tmp_path):
    # A separate module instance prevents other tests' settings workers/cache
    # from leaking into these tests, or these tests from changing user settings.
    spec = importlib.util.spec_from_file_location(
        "_settings_persistence_test", settings_handler.__file__
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.settings_path = str(tmp_path)
    module.legacy_settings_paths = []
    yield module
    with module._save_condition:
        module._save_deadline = None
        worker = module._save_thread
        module._save_condition.notify_all()
    if worker is not None:
        worker.join(timeout=5)
        assert not worker.is_alive(), "settings worker did not stop"


@pytest.fixture
def scheduler(settings, monkeypatch):
    clock = SimpleNamespace(now=100.0)
    workers = []

    class DeferredThread:
        def __init__(self, *, target, name, daemon):
            self.target = target
            self.name = name
            self.daemon = daemon
            self.started = False
            workers.append(self)

        def start(self):
            assert not self.started
            self.started = True

        def join(self, timeout=None):
            self.target()

        def is_alive(self):
            return False

    # Replace module references rather than patching process-wide threading/time.
    monkeypatch.setattr(settings, "threading", SimpleNamespace(Thread=DeferredThread))
    monkeypatch.setattr(settings, "monotonic", lambda: clock.now)
    return SimpleNamespace(clock=clock, workers=workers)


def test_burst_edits_use_one_worker_and_a_bounded_flush(settings, scheduler, tmp_path):
    settings.config_initialization()
    for value in range(500):
        scheduler.clock.now = 100.0 + value / 500
        settings.config_set("volume", value)
        settings.config_set("eq_preamp", value / 10)

    assert len(scheduler.workers) == 1
    worker = scheduler.workers[0]
    assert worker.started and worker.daemon
    assert settings._save_deadline == 102.0
    assert read_settings(tmp_path)["volume"] == "100"

    # No sleeps: inspect the boundary with a fake monotonic clock.
    scheduler.clock.now = 101.999
    settings._flush_settings(pending_only=True)
    assert read_settings(tmp_path)["volume"] == "100"
    scheduler.clock.now = 102.0
    worker.target()
    saved = read_settings(tmp_path)
    assert saved["volume"] == "499"
    assert saved["eq_preamp"] == "49.9"
    assert settings._save_thread is None
    assert not settings._dirty


def test_noop_edits_do_not_schedule_or_extend_flush(settings, scheduler):
    settings.config_initialization()
    settings.config_set("VOLUME", 100)
    settings.config_set("repeattracks", False)
    settings.config_set("lang", settings.defaults["lang"] + "_XX")
    assert not scheduler.workers
    assert settings._save_deadline is None

    settings.config_set("volume", 75)
    deadline = settings._save_deadline
    scheduler.clock.now += 1
    for _ in range(100):
        settings.config_set("volume", 75)
    assert settings._save_deadline == deadline
    assert len(scheduler.workers) == 1


@pytest.mark.parametrize(
    ("key", "value"), [("defaultaudio", False), ("volume", 100.0), ("volume", "100")]
)
def test_equal_values_of_different_types_are_not_skipped(
    settings, scheduler, tmp_path, key, value
):
    settings.config_initialization()
    settings.config_set(key, value)
    result = settings.config_get(key)
    assert result == value
    assert type(result) is type(value)
    assert len(scheduler.workers) == 1
    settings.save_settings()
    assert read_settings(tmp_path)[key] == str(value)


def test_explicit_save_consumes_pending_work_and_can_be_repeated(
    settings, scheduler, monkeypatch, tmp_path
):
    settings.config_initialization()
    write = settings._write_settings_now
    writes = []

    def record_write(contents):
        writes.append(contents)
        write(contents)

    monkeypatch.setattr(settings, "_write_settings_now", record_write)
    settings.config_set("volume", 25)
    worker = scheduler.workers[0]
    settings.save_settings()
    assert read_settings(tmp_path)["volume"] == "25"
    assert settings._save_deadline is None
    scheduler.clock.now += 10
    worker.target()
    assert len(writes) == 1

    settings.config_set("volume", 30)
    assert len(scheduler.workers) == 2
    settings.save_settings()
    scheduler.workers[-1].target()
    assert read_settings(tmp_path)["volume"] == "30"
    assert len(writes) == 2


@pytest.mark.parametrize("explicit_final_save", [False, True])
def test_slow_save_keeps_edits_responsive_and_persists_latest_value(
    settings, monkeypatch, tmp_path, explicit_final_save
):
    settings.config_initialization()
    monkeypatch.setattr(settings, "_SAVE_DELAY", 0)
    write_started = threading.Event()
    release_write = threading.Event()
    latest_written = threading.Event()
    final_started = threading.Event()
    write = settings._write_settings_now
    writes = []

    def slow_write(contents):
        writes.append(contents)
        if len(writes) == 1:
            write_started.set()
            assert release_write.wait(5), "test did not release blocked write"
        write(contents)
        if "volume = 90\n" in contents:
            latest_written.set()

    def edit_settings():
        for value in range(40, 91):
            settings.config_set("volume", value)
            settings.config_set("eq_preamp", float(value))
        return settings.config_get("volume"), settings.config_get("eq_preamp")

    def final_save():
        final_started.set()
        settings.save_settings()

    monkeypatch.setattr(settings, "_write_settings_now", slow_write)
    with ThreadPoolExecutor(max_workers=2) as executor:
        final = None
        try:
            settings.config_set("volume", 20)
            assert write_started.wait(5)
            worker = settings._save_thread
            update = executor.submit(edit_settings)
            # Completing while disk I/O is blocked proves get/set don't take
            # the writer lock. No timing sleeps or throughput assumptions.
            assert update.result(timeout=5) == (90, 90.0)
            assert settings._save_thread is worker
            assert read_settings(tmp_path)["volume"] == "100"
            if explicit_final_save:
                final = executor.submit(final_save)
                assert final_started.wait(5)
                assert not final.done()
        finally:
            release_write.set()
        if final is not None:
            final.result(timeout=5)
        assert latest_written.wait(5)
        worker.join(timeout=5)
        assert not worker.is_alive()

    saved = read_settings(tmp_path)
    assert saved["volume"] == "90"
    assert saved["eq_preamp"] == "90.0"
    assert "volume = 20\n" in writes[0]
    assert all("volume = 90\n" in contents for contents in writes[1:])
    assert settings._save_deadline is None
    assert not settings._dirty


def test_concurrent_first_edits_and_saves_keep_cache_and_config_consistent(
    settings, scheduler, tmp_path
):
    (tmp_path / "settings.ini").write_text(
        "[settings]\ncustom_existing = retained\n", encoding="utf-8"
    )
    ready = threading.Barrier(4)

    def edit(index):
        ready.wait(timeout=5)
        key = f"worker_{index}"
        for value in range(40):
            settings.config_set(key, value)
            assert settings.config_get(key) == value
            with settings._lock:
                assert all(
                    settings._config["settings"][name] == str(cached)
                    for name, cached in settings._cache.items()
                )
            if value % 20 == 0:
                settings.save_settings()

    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = [executor.submit(edit, index) for index in range(4)]
        for future in futures:
            future.result(timeout=10)
    settings.save_settings()
    saved = read_settings(tmp_path)
    assert saved["custom_existing"] == "retained"
    for index in range(4):
        assert saved[f"worker_{index}"] == "39"
    assert set(settings.defaults).issubset(saved)


@pytest.mark.parametrize("failure_stage", ["write", "fsync", "replace"])
def test_failed_atomic_save_preserves_file_and_allows_retry(
    settings, scheduler, monkeypatch, tmp_path, failure_stage
):
    settings.config_initialization()
    old_contents = (tmp_path / "settings.ini").read_bytes()
    settings.config_set("volume", 37)

    def fail(*args, **kwargs):
        raise OSError("simulated settings storage failure")

    with monkeypatch.context() as patch:
        if failure_stage == "write":
            make_file = settings.tempfile.NamedTemporaryFile

            class PartialWriter:
                def __init__(self, *args, **kwargs):
                    self.file = make_file(*args, **kwargs)
                    self.name = self.file.name

                def __enter__(self):
                    return self

                def __exit__(self, *args):
                    self.file.close()

                def write(self, contents):
                    self.file.write(contents[:15])
                    fail()

            patch.setattr(
                settings, "tempfile", SimpleNamespace(NamedTemporaryFile=PartialWriter)
            )
        else:
            patched_os = SimpleNamespace(**vars(os))
            setattr(patched_os, failure_stage, fail)
            patch.setattr(settings, "os", patched_os)
        settings.save_settings()

    assert (tmp_path / "settings.ini").read_bytes() == old_contents
    assert list(tmp_path.iterdir()) == [tmp_path / "settings.ini"]
    assert settings.config_get("volume") == 37
    assert settings._dirty

    # Even an unchanged value can re-arm persistence after failure. An explicit
    # final save must still be synchronous and must not lose the dirty snapshot.
    settings.config_set("volume", 37)
    assert settings._save_deadline is not None
    settings.save_settings()
    assert read_settings(tmp_path)["volume"] == "37"
    assert not settings._dirty
    assert list(tmp_path.iterdir()) == [tmp_path / "settings.ini"]


def test_replacement_uses_flushed_complete_file_in_same_directory(
    settings, scheduler, monkeypatch, tmp_path
):
    settings.config_initialization()
    original = (tmp_path / "settings.ini").read_bytes()
    settings.config_set("path", str(tmp_path / "موسيقى"))
    events = []
    patched_os = SimpleNamespace(**vars(os))

    def fsync(fd):
        os.fsync(fd)
        events.append("fsync")

    def replace(source, destination):
        assert Path(source).parent == Path(destination).parent == tmp_path
        assert Path(destination).read_bytes() == original
        assert "موسيقى" in Path(source).read_text(encoding="utf-8")
        events.append("replace")
        os.replace(source, destination)

    patched_os.fsync = fsync
    patched_os.replace = replace
    monkeypatch.setattr(settings, "os", patched_os)
    settings.save_settings()
    assert events == ["fsync", "replace"]
    assert read_settings(tmp_path)["path"] == str(tmp_path / "موسيقى")
    assert list(tmp_path.iterdir()) == [tmp_path / "settings.ini"]


def test_set_before_first_read_keeps_existing_values_and_defaults(
    settings, scheduler, tmp_path
):
    (tmp_path / "settings.ini").write_text(
        "[settings]\nvolume = 10\nrepeattracks = True\nlang = English\n"
        "custom_existing = retained\n",
        encoding="utf-8",
    )
    settings.config_set("volume", 45)
    settings.save_settings()
    saved = read_settings(tmp_path)
    assert saved["volume"] == "45"
    assert saved["repeatTracks"] == "True"
    assert saved["custom_existing"] == "retained"
    assert saved["lang"] == "en"
    assert set(settings.defaults).issubset(saved)


def test_reload_does_not_block_or_discard_concurrent_edits(
    settings, scheduler, monkeypatch, tmp_path
):
    settings.config_initialization()
    read_started = threading.Event()
    release_read = threading.Event()
    candidates = settings._candidate_settings_files

    def slow_candidates():
        read_started.set()
        assert release_read.wait(5), "test did not release blocked read"
        return candidates()

    monkeypatch.setattr(settings, "_candidate_settings_files", slow_candidates)
    with ThreadPoolExecutor(max_workers=2) as executor:
        reload = executor.submit(settings.config_initialization)
        try:
            assert read_started.wait(5)
            edit = executor.submit(settings.config_set, "volume", 62)
            edit.result(timeout=5)
            assert settings.config_get("volume") == 62
        finally:
            release_read.set()
        reload.result(timeout=5)
    assert settings.config_get("volume") == 62
    assert read_settings(tmp_path)["volume"] == "62"


@pytest.mark.parametrize("failed_save", [False, True])
def test_repeated_initialization_preserves_unsaved_cache(
    settings, scheduler, monkeypatch, tmp_path, failed_save
):
    settings.config_initialization()

    def fail_write(contents):
        raise OSError("simulated settings storage failure")

    for value in (25, 50, 75):
        settings.config_set("volume", value)
        settings.config_set("eq_preamp", value / 10)
        if failed_save:
            with monkeypatch.context() as patch:
                patch.setattr(settings, "_write_settings_now", fail_write)
                settings.save_settings()
        assert read_settings(tmp_path)["volume"] != str(value)

        settings.config_initialization()

        assert settings.config_get("volume") == value
        assert settings.config_get("eq_preamp") == value / 10
        saved = read_settings(tmp_path)
        assert saved["volume"] == str(value)
        assert saved["eq_preamp"] == str(value / 10)
        assert settings._save_deadline is None
        assert not settings._dirty

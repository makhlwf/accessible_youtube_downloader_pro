import ctypes
import locale
import shutil
import sys
import threading
import zipfile
from enum import IntEnum
from pathlib import Path
from typing import Any, ClassVar

from runtime_dlls import configure_dll_search_path, runtime_roots

MPV_FORMAT_STRING = 1
MPV_FORMAT_FLAG = 3
MPV_FORMAT_INT64 = 4
MPV_FORMAT_DOUBLE = 5
MPV_FORMAT_NODE = 6
MPV_FORMAT_NODE_ARRAY = 7
MPV_FORMAT_NODE_MAP = 8

MPV_EVENT_NONE = 0
MPV_EVENT_SHUTDOWN = 1
MPV_EVENT_START_FILE = 6
MPV_EVENT_END_FILE = 7
MPV_EVENT_FILE_LOADED = 8

MPV_END_FILE_REASON_EOF = 0
MPV_END_FILE_REASON_STOP = 2
MPV_END_FILE_REASON_QUIT = 3
MPV_END_FILE_REASON_ERROR = 4


class State(IntEnum):
    NothingSpecial = 0
    Opening = 1
    Buffering = 2
    Playing = 3
    Paused = 4
    Stopped = 5
    Ended = 6
    Error = 7


class MPVError(RuntimeError):
    pass


def _ensure_numeric_locale() -> None:
    try:
        locale.setlocale(locale.LC_NUMERIC, "C")
    except locale.Error:
        pass


class MpvNode(ctypes.Structure):
    pass


class MpvNodeList(ctypes.Structure):
    pass


class MpvNodeUnion(ctypes.Union):
    _fields_: ClassVar[list] = [
        ("string", ctypes.c_char_p),
        ("flag", ctypes.c_int),
        ("int64", ctypes.c_int64),
        ("double_", ctypes.c_double),
        ("list", ctypes.POINTER(MpvNodeList)),
        ("ba", ctypes.c_void_p),
    ]


MpvNode._fields_ = [
    ("u", MpvNodeUnion),
    ("format", ctypes.c_int),
]

MpvNodeList._fields_ = [
    ("num", ctypes.c_int),
    ("values", ctypes.POINTER(MpvNode)),
    ("keys", ctypes.POINTER(ctypes.c_char_p)),
]


class MpvEventEndFile(ctypes.Structure):
    _fields_ = [
        ("reason", ctypes.c_int),
        ("error", ctypes.c_int),
        ("playlist_entry_id", ctypes.c_int64),
        ("playlist_insert_id", ctypes.c_int64),
        ("playlist_insert_num_entries", ctypes.c_int),
    ]


class MpvEvent(ctypes.Structure):
    _fields_ = [
        ("event_id", ctypes.c_int),
        ("error", ctypes.c_int),
        ("reply_userdata", ctypes.c_uint64),
        ("data", ctypes.c_void_p),
    ]


class MpvEndEvent:
    def __init__(self, reason: int) -> None:
        self.reason = reason
        self.type = MPV_EVENT_END_FILE


class MpvMedia:
    def __init__(self, url: str, options: list[str] | None = None) -> None:
        self.url = url
        self.options = list(options or [])

    def add_option(self, option: str) -> None:
        self.options.append(option)


_mpv_lib: ctypes.CDLL | None = None


def _bundle_root() -> Path:
    if hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)  # type: ignore[attr-defined]
    return Path(__file__).resolve().parent.parent


def _extract_mpv_dll(root: Path) -> Path | None:
    dll_path = root / "libmpv-2.dll"
    if dll_path.exists():
        return dll_path

    archive_path = root / "libmpv-2.dll.zip"
    if not archive_path.exists():
        return None

    try:
        with zipfile.ZipFile(archive_path) as archive:
            member = next(
                (
                    name
                    for name in archive.namelist()
                    if Path(name).name.lower() == "libmpv-2.dll"
                ),
                None,
            )
            if member is None:
                raise MPVError("libmpv-2.dll.zip does not contain libmpv-2.dll.")
            with archive.open(member) as source, dll_path.open("wb") as target:
                shutil.copyfileobj(source, target)
    except (OSError, zipfile.BadZipFile) as exc:
        raise MPVError("Unable to extract libmpv-2.dll from bundled archive.") from exc

    return dll_path if dll_path.exists() else None


def _mpv_candidates() -> list[Path]:
    roots = runtime_roots([_bundle_root()])

    candidates = []
    for root in roots:
        candidates.append(_extract_mpv_dll(root) or root / "libmpv-2.dll")
    return candidates


def _load_mpv() -> ctypes.CDLL:
    global _mpv_lib
    if _mpv_lib is not None:
        return _mpv_lib

    dll_path = next((path for path in _mpv_candidates() if path.exists()), None)
    if dll_path is None:
        dll_name = "libmpv-2.dll" if sys.platform == "win32" else "libmpv.so.2"
        try:
            lib = ctypes.CDLL(dll_name)
        except OSError as exc:
            raise MPVError("libmpv-2.dll was not found.") from exc
    else:
        configure_dll_search_path([dll_path.parent])
        try:
            lib = ctypes.CDLL(str(dll_path))
        except OSError as exc:
            raise MPVError(
                f"Failed to load {dll_path}. The file exists, but Windows could "
                f"not load one of its runtime dependencies. Original error: {exc}"
            ) from exc

    lib.mpv_create.restype = ctypes.c_void_p

    lib.mpv_initialize.argtypes = [ctypes.c_void_p]
    lib.mpv_initialize.restype = ctypes.c_int

    lib.mpv_set_option_string.argtypes = [
        ctypes.c_void_p,
        ctypes.c_char_p,
        ctypes.c_char_p,
    ]
    lib.mpv_set_option_string.restype = ctypes.c_int

    lib.mpv_command.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_char_p)]
    lib.mpv_command.restype = ctypes.c_int

    lib.mpv_command_node.argtypes = [
        ctypes.c_void_p,
        ctypes.POINTER(MpvNode),
        ctypes.POINTER(MpvNode),
    ]
    lib.mpv_command_node.restype = ctypes.c_int

    lib.mpv_set_property.argtypes = [
        ctypes.c_void_p,
        ctypes.c_char_p,
        ctypes.c_int,
        ctypes.c_void_p,
    ]
    lib.mpv_set_property.restype = ctypes.c_int

    lib.mpv_set_property_string.argtypes = [
        ctypes.c_void_p,
        ctypes.c_char_p,
        ctypes.c_char_p,
    ]
    lib.mpv_set_property_string.restype = ctypes.c_int

    lib.mpv_get_property.argtypes = [
        ctypes.c_void_p,
        ctypes.c_char_p,
        ctypes.c_int,
        ctypes.c_void_p,
    ]
    lib.mpv_get_property.restype = ctypes.c_int

    lib.mpv_get_property_string.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
    lib.mpv_get_property_string.restype = ctypes.c_void_p

    lib.mpv_free_node_contents.argtypes = [ctypes.POINTER(MpvNode)]
    lib.mpv_free_node_contents.restype = None

    lib.mpv_wait_event.argtypes = [ctypes.c_void_p, ctypes.c_double]
    lib.mpv_wait_event.restype = ctypes.POINTER(MpvEvent)

    lib.mpv_wakeup.argtypes = [ctypes.c_void_p]
    lib.mpv_wakeup.restype = None

    lib.mpv_terminate_destroy.argtypes = [ctypes.c_void_p]
    lib.mpv_terminate_destroy.restype = None

    lib.mpv_error_string.argtypes = [ctypes.c_int]
    lib.mpv_error_string.restype = ctypes.c_char_p

    lib.mpv_free.argtypes = [ctypes.c_void_p]
    lib.mpv_free.restype = None

    _mpv_lib = lib
    return lib


def _encode(value: Any) -> bytes:
    return str(value).encode("utf-8")


def _decode_mpv_string(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)


def _parse_node(node: MpvNode) -> Any:
    if node.format == MPV_FORMAT_STRING:
        return _decode_mpv_string(node.u.string)
    if node.format == MPV_FORMAT_FLAG:
        return bool(node.u.flag)
    if node.format == MPV_FORMAT_INT64:
        return int(node.u.int64)
    if node.format == MPV_FORMAT_DOUBLE:
        return float(node.u.double_)
    if node.format not in (MPV_FORMAT_NODE_ARRAY, MPV_FORMAT_NODE_MAP):
        return None

    node_list_ptr = node.u.list
    if not node_list_ptr:
        return {} if node.format == MPV_FORMAT_NODE_MAP else []

    node_list = node_list_ptr.contents
    if node.format == MPV_FORMAT_NODE_ARRAY:
        return [_parse_node(node_list.values[index]) for index in range(node_list.num)]

    values: dict[str, Any] = {}
    for index in range(node_list.num):
        if node_list.keys:
            key = _decode_mpv_string(node_list.keys[index])
        else:
            key = str(index)
        values[key] = _parse_node(node_list.values[index])
    return values


def _clean_option(option: str) -> tuple[str, str]:
    option = option.strip()
    while option.startswith((":", "-")):
        option = option[1:]
    if "=" in option:
        key, value = option.split("=", 1)
    else:
        key, value = option, "yes"
    return key, value


def parse_player_options(options: list[str] | None) -> dict[str, str]:
    mpv_options: dict[str, str] = {}
    for option in options or []:
        key, value = _clean_option(option)
        if key == "http-user-agent":
            mpv_options["user-agent"] = value
        elif key == "input-slave":
            mpv_options["audio-file"] = value
        elif key == "no-video":
            mpv_options["vid"] = "no"
        else:
            mpv_options[key] = value
    return mpv_options


class MpvMediaPlayer:
    def __init__(self, hwnd: int | None = None, end_callback=None) -> None:
        _ensure_numeric_locale()
        self._lib = _load_mpv()
        self._handle = self._lib.mpv_create()
        if not self._handle:
            raise MPVError("Unable to create an MPV handle.")

        self._lock = threading.RLock()
        self._closed = False
        self._loaded = False
        self._state = State.NothingSpecial
        self._current_media: MpvMedia | None = None
        self._pending_position: float | None = None
        self._pending_time: float | None = None
        self._end_callback = end_callback

        self._set_option("config", "no")
        self._set_option("terminal", "no")
        self._set_option("osc", "no")
        self._set_option("osd-level", "0")
        self._set_option("osd-on-seek", "no")
        self._set_option("input-default-bindings", "no")
        self._set_option("volume-max", "350")
        self._set_option("keep-open", "no")
        self._set_option("cache", "yes")
        if hwnd:
            self._set_option("wid", int(hwnd))

        self._check(self._lib.mpv_initialize(self._handle))
        self._event_thread = threading.Thread(target=self._event_loop, daemon=True)
        self._event_thread.start()

    def _check(self, result: int) -> None:
        if result < 0:
            error = self._lib.mpv_error_string(result)
            message = error.decode("utf-8", errors="replace") if error else result
            raise MPVError(f"MPV error: {message}")

    def _set_option(self, name: str, value: Any) -> None:
        self._check(
            self._lib.mpv_set_option_string(
                self._handle,
                _encode(name),
                _encode(value),
            )
        )

    def _command(self, *args: Any, check: bool = True) -> int:
        if self._closed:
            return -1
        encoded = [_encode(arg) for arg in args]
        c_args = (ctypes.c_char_p * (len(encoded) + 1))()
        for index, arg in enumerate(encoded):
            c_args[index] = arg
        c_args[len(encoded)] = None
        result = self._lib.mpv_command(self._handle, c_args)
        if check:
            self._check(result)
        return result

    def _string_node(self, value: Any, keepalive: list[bytes]) -> MpvNode:
        data = _encode(value)
        keepalive.append(data)
        node = MpvNode()
        node.format = MPV_FORMAT_STRING
        node.u.string = ctypes.c_char_p(data)
        return node

    def _load_current(self) -> None:
        if self._current_media is None:
            return

        options = parse_player_options(self._current_media.options)
        keepalive: list[bytes] = []
        command_values = (MpvNode * 5)()
        command_values[0] = self._string_node("loadfile", keepalive)
        command_values[1] = self._string_node(self._current_media.url, keepalive)
        command_values[2] = self._string_node("replace", keepalive)
        command_values[3] = self._string_node("-1", keepalive)

        option_values = (MpvNode * len(options))()
        option_keys = (ctypes.c_char_p * len(options))()
        for index, (key, value) in enumerate(options.items()):
            key_bytes = _encode(key)
            keepalive.append(key_bytes)
            option_keys[index] = ctypes.c_char_p(key_bytes)
            option_values[index] = self._string_node(value, keepalive)

        option_list = MpvNodeList()
        option_list.num = len(options)
        option_list.values = option_values
        option_list.keys = option_keys

        option_node = MpvNode()
        option_node.format = MPV_FORMAT_NODE_MAP
        option_node.u.list = ctypes.pointer(option_list)
        command_values[4] = option_node

        command_list = MpvNodeList()
        command_list.num = len(command_values)
        command_list.values = command_values
        command_list.keys = None

        root = MpvNode()
        root.format = MPV_FORMAT_NODE_ARRAY
        root.u.list = ctypes.pointer(command_list)

        self._check(self._lib.mpv_command_node(self._handle, ctypes.byref(root), None))
        self._loaded = False
        self._state = State.Opening

    def _set_property_string(self, name: str, value: str, check: bool = False) -> int:
        result = self._lib.mpv_set_property_string(
            self._handle,
            _encode(name),
            _encode(value),
        )
        if check:
            self._check(result)
        return result

    def _set_property_flag(self, name: str, value: bool) -> None:
        flag = ctypes.c_int(1 if value else 0)
        self._check(
            self._lib.mpv_set_property(
                self._handle,
                _encode(name),
                MPV_FORMAT_FLAG,
                ctypes.byref(flag),
            )
        )

    def _set_property_double(self, name: str, value: float) -> None:
        number = ctypes.c_double(float(value))
        self._check(
            self._lib.mpv_set_property(
                self._handle,
                _encode(name),
                MPV_FORMAT_DOUBLE,
                ctypes.byref(number),
            )
        )

    def _get_property_double(self, name: str) -> float | None:
        number = ctypes.c_double()
        result = self._lib.mpv_get_property(
            self._handle,
            _encode(name),
            MPV_FORMAT_DOUBLE,
            ctypes.byref(number),
        )
        if result < 0:
            return None
        return float(number.value)

    def _get_property_flag(self, name: str) -> bool | None:
        flag = ctypes.c_int()
        result = self._lib.mpv_get_property(
            self._handle,
            _encode(name),
            MPV_FORMAT_FLAG,
            ctypes.byref(flag),
        )
        if result < 0:
            return None
        return bool(flag.value)

    def _get_property_string(self, name: str) -> str | None:
        value = self._lib.mpv_get_property_string(self._handle, _encode(name))
        if not value:
            return None
        try:
            return ctypes.cast(value, ctypes.c_char_p).value.decode(
                "utf-8", errors="replace"
            )
        finally:
            self._lib.mpv_free(value)

    def _get_property_node(self, name: str) -> Any:
        node = MpvNode()
        result = self._lib.mpv_get_property(
            self._handle,
            _encode(name),
            MPV_FORMAT_NODE,
            ctypes.byref(node),
        )
        if result < 0:
            return None
        try:
            return _parse_node(node)
        finally:
            self._lib.mpv_free_node_contents(ctypes.byref(node))

    def _event_loop(self) -> None:
        while not self._closed:
            event_ptr = self._lib.mpv_wait_event(self._handle, 0.1)
            if not event_ptr:
                continue
            event = event_ptr.contents
            if event.event_id == MPV_EVENT_NONE:
                continue
            if event.event_id == MPV_EVENT_SHUTDOWN:
                break
            if event.event_id == MPV_EVENT_START_FILE:
                self._state = State.Opening
            elif event.event_id == MPV_EVENT_FILE_LOADED:
                self._loaded = True
                self._state = State.Playing
                self._apply_pending_seek()
            elif event.event_id == MPV_EVENT_END_FILE:
                self._handle_end_file(event)

    def _handle_end_file(self, event: MpvEvent) -> None:
        reason = MPV_END_FILE_REASON_ERROR
        if event.data:
            end_file = ctypes.cast(
                event.data,
                ctypes.POINTER(MpvEventEndFile),
            ).contents
            reason = end_file.reason

        self._loaded = False
        if reason == MPV_END_FILE_REASON_EOF:
            self._state = State.Ended
            if self._end_callback:
                self._end_callback(MpvEndEvent(reason))
        elif reason == MPV_END_FILE_REASON_STOP:
            self._state = State.Stopped
        elif reason == MPV_END_FILE_REASON_QUIT:
            self._closed = True
        else:
            self._state = State.Error

    def _apply_pending_seek(self) -> None:
        if self._pending_time is not None:
            seconds = self._pending_time
            self._pending_time = None
            self._command("seek", seconds, "absolute", "exact", check=False)
        elif self._pending_position is not None:
            position = self._pending_position
            self._pending_position = None
            self.set_position(position)

    def set_media(self, media: MpvMedia) -> None:
        with self._lock:
            self._current_media = media
            self._loaded = False
            self._pending_position = None
            self._pending_time = None
            self._state = State.NothingSpecial

    def get_media(self) -> MpvMedia | None:
        return self._current_media

    def set_hwnd(self, hwnd: int) -> None:
        if hwnd:
            self._set_property_string("wid", str(int(hwnd)))

    def play(self) -> None:
        with self._lock:
            if self._closed:
                return
            if self._current_media is None:
                return
            if self._loaded and self._get_property_flag("pause"):
                self._set_property_flag("pause", False)
                self._state = State.Playing
                return
            if not self._loaded or self._state in (
                State.NothingSpecial,
                State.Stopped,
                State.Ended,
                State.Error,
            ):
                self._load_current()
            self._set_property_flag("pause", False)
            if self._state != State.Opening:
                self._state = State.Playing

    def pause(self) -> None:
        with self._lock:
            paused = self._get_property_flag("pause")
            if paused is None:
                return
            self._set_property_flag("pause", not paused)
            self._state = State.Playing if paused else State.Paused

    def stop(self) -> None:
        with self._lock:
            self._command("stop", check=False)
            self._loaded = False
            self._pending_position = None
            self._pending_time = None
            self._state = State.Stopped

    def get_length(self) -> int:
        duration = self._get_property_double("duration")
        if duration is None or duration <= 0:
            return -1
        return int(duration * 1000)

    def get_time(self) -> int:
        elapsed = self._get_property_double("time-pos")
        if elapsed is None:
            elapsed = self._get_property_double("playback-time")
        if elapsed is None or elapsed < 0:
            return -1
        return int(elapsed * 1000)

    def set_time(self, milliseconds: int) -> None:
        seconds = max(0.0, float(milliseconds) / 1000)
        if not self._loaded:
            self._pending_time = seconds
        self._command("seek", seconds, "absolute", "exact", check=False)

    def get_position(self) -> float:
        percent = self._get_property_double("percent-pos")
        if percent is not None and percent >= 0:
            return max(0.0, min(1.0, percent / 100))

        length = self.get_length()
        elapsed = self.get_time()
        if length <= 0 or elapsed < 0:
            return -1
        return max(0.0, min(1.0, elapsed / length))

    def set_position(self, position: float) -> None:
        position = max(0.0, min(1.0, float(position)))
        if not self._loaded:
            self._pending_position = position
        self._command("seek", position * 100, "absolute-percent", "exact", check=False)

    def get_state(self) -> State:
        if self._state in (State.Error, State.Ended, State.Stopped):
            return self._state
        idle = self._get_property_flag("idle-active")
        if idle:
            return State.Stopped if self._state != State.NothingSpecial else self._state
        paused = self._get_property_flag("pause")
        if paused is True:
            return State.Paused
        if paused is False:
            return State.Playing
        return self._state

    def get_rate(self) -> float:
        return self._get_property_double("speed") or 1.0

    def set_rate(self, rate: float) -> None:
        self._set_property_double("speed", max(0.1, float(rate)))

    def audio_set_volume(self, volume: float) -> None:
        self._set_property_double("volume", max(0.0, min(350.0, float(volume))))

    def get_audio_output_devices(self) -> list[dict[str, str]]:
        with self._lock:
            if self._closed:
                return []
            raw_devices = self._get_property_node("audio-device-list")

        devices: list[dict[str, str]] = []
        seen = set()
        if not isinstance(raw_devices, list):
            return devices

        for device in raw_devices:
            if not isinstance(device, dict):
                continue
            device_id = str(device.get("name") or device.get("id") or "")
            description = str(device.get("description") or device_id)
            if not device_id or device_id == "auto" or device_id in seen:
                continue
            devices.append({"id": device_id, "description": description})
            seen.add(device_id)
        return devices

    def get_audio_output_device(self) -> str:
        with self._lock:
            if self._closed:
                return ""
            device_id = self._get_property_string("audio-device")
        if not device_id or device_id == "auto":
            return ""
        return device_id

    def set_audio_output_device(self, device_id: str | None) -> bool:
        with self._lock:
            if self._closed:
                return False
            result = self._set_property_string("audio-device", device_id or "auto")
        return result >= 0

    def set_equalizer(self, equalizer: Any) -> None:
        if hasattr(equalizer, "apply_to_mpv"):
            equalizer.apply_to_mpv(self)
        elif hasattr(equalizer, "preamp") and hasattr(equalizer, "bands"):
            self.apply_equalizer(equalizer.preamp, equalizer.bands)

    def apply_equalizer(self, preamp: float, bands: list[float]) -> None:
        frequencies = [60, 170, 310, 600, 1000, 3000, 6000, 12000, 14000, 16000]
        filters = []
        if abs(preamp) > 0.001:
            filters.append(f"volume={preamp:g}dB")
        for frequency, gain in zip(frequencies, bands):
            if abs(gain) > 0.001:
                filters.append(f"equalizer=f={frequency}:t=q:w=1:g={gain:g}")

        value = f"lavfi=[{','.join(filters)}]" if filters else ""
        self._set_property_string("af", value)

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
            self._lib.mpv_wakeup(self._handle)
            self._lib.mpv_terminate_destroy(self._handle)

        if threading.current_thread() is not self._event_thread:
            self._event_thread.join(timeout=1)

    def __del__(self) -> None:
        try:
            self.close()
        except Exception:
            pass


def get_available_audio_output_devices() -> list[dict[str, str]]:
    player = MpvMediaPlayer()
    try:
        return player.get_audio_output_devices()
    finally:
        player.close()

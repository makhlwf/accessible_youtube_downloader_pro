"""Desktop startup logging and optional Windows console output."""

import ctypes
import logging
import os
import sys

import paths
from app_state import settings_handler


def is_debug_invocation(argv=None):
    if argv is None:
        argv = sys.argv
    return any(arg in ("-d", "--debug") for arg in argv[1:])


def enable_console_output():
    if sys.platform != "win32":
        return True

    try:
        kernel32 = ctypes.windll.kernel32
        ATTACH_PARENT_PROCESS = -1
        if not kernel32.AttachConsole(ATTACH_PARENT_PROCESS):
            kernel32.AllocConsole()

        try:
            sys.stdout = open(  # noqa: SIM115
                "CONOUT$", "w", encoding="utf-8", errors="replace", buffering=1
            )
        except Exception:
            pass
        try:
            sys.stderr = open(  # noqa: SIM115
                "CONOUT$", "w", encoding="utf-8", errors="replace", buffering=1
            )
        except Exception:
            pass
        try:
            sys.stdin = open("CONIN$", "r", encoding="utf-8", errors="replace")  # noqa: SIM115
        except Exception:
            pass
        return True
    except Exception:
        return False


def setup_logging(argv=None):
    os.makedirs(paths.settings_path, exist_ok=True)
    root_logger = logging.getLogger()
    for h in list(root_logger.handlers):
        root_logger.removeHandler(h)

    is_debug_cli = is_debug_invocation(argv)
    is_debug_config = False
    try:
        settings_handler.config_initialization()
        is_debug_config = bool(settings_handler.config_get("debug"))
    except Exception:
        pass

    is_debug = is_debug_cli or is_debug_config

    if is_debug_cli:
        enable_console_output()

    root_logger.setLevel(logging.DEBUG if is_debug else logging.INFO)
    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    console_h = logging.StreamHandler(sys.stderr)
    console_h.setFormatter(formatter)
    root_logger.addHandler(console_h)

    try:
        file_h = logging.FileHandler(paths.log_path, encoding="utf-8", mode="a")
        file_h.setFormatter(formatter)
        root_logger.addHandler(file_h)
    except Exception:
        pass

    try:
        from logging_config import apply_logging_settings

        apply_logging_settings()
    except Exception:
        pass

    if is_debug:
        if is_debug_cli:
            root_logger.debug("Debug logging initialized (terminal output enabled)")
        else:
            root_logger.debug("Debug logging initialized")

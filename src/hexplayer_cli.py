"""Frozen console entry point for the HexPlayer command line interface.

This module is the target of the dedicated ``hexplayer.exe`` PyInstaller EXE
(console subsystem). It performs the same early DLL search-path setup as the
GUI entry point so bundled native libraries resolve correctly, ensures the
source directory is importable when running from source, then hands control to
:func:`cli.app.main`.
"""

import os
import sys

# Early setup for bundled native DLLs, matching the GUI entry point. This must
# run before any import that may pull in a native extension.
from runtime_dlls import configure_dll_search_path

configure_dll_search_path()


def _ensure_src_on_path():
    """Make the ``src`` directory importable when running from source."""
    here = os.path.dirname(os.path.abspath(__file__))
    if here not in sys.path:
        sys.path.insert(0, here)


def main():
    _ensure_src_on_path()

    # Ensure the console can carry Arabic and other non-ASCII output.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass

    from cli.app import main as cli_main

    return cli_main(sys.argv[1:])


if __name__ == "__main__":
    sys.exit(main())

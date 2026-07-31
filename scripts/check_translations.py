import difflib
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MESSAGES_POT = ROOT / "messages.pot"


def comparable_lines(path):
    return [
        line
        for line in path.read_text(encoding="utf-8").splitlines()
        if "POT-Creation-Date" not in line and line.strip()
    ]


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    with tempfile.TemporaryDirectory() as temp_dir:
        generated = Path(temp_dir) / "messages.pot.tmp"
        command = [
            sys.executable,
            "-m",
            "babel.messages.frontend",
            "extract",
            "-F",
            "babel.cfg",
            "-k",
            "_",
            "-o",
            str(generated),
            ".",
        ]
        subprocess.run(command, cwd=ROOT, check=True)

        expected = comparable_lines(MESSAGES_POT)
        actual = comparable_lines(generated)

    if expected == actual:
        return 0

    diff = difflib.unified_diff(
        expected,
        actual,
        fromfile="messages.pot",
        tofile="generated messages.pot",
        lineterm="",
    )
    print("\n".join(diff))
    print(
        "\nmessages.pot is out of date. Run "
        "`uv run pybabel extract -F babel.cfg -k _ -o messages.pot .` "
        "and commit the changes."
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

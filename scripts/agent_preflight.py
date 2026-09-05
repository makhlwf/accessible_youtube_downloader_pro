#!/usr/bin/env python3
"""
HexPlayer Agent & Developer Preflight Harness
Runs all quality, syntax, translation, test, and skill validation checks
required before claiming completion or opening pull requests.
"""

import subprocess
import sys
import time
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parents[1]


def run_step(name: str, cmd: list[str]) -> bool:
    print("\n========================================================")
    print(f"▶ Running {name}: {' '.join(cmd)}")
    print("========================================================")
    start = time.time()
    try:
        res = subprocess.run(cmd, cwd=ROOT, check=False)
        duration = time.time() - start
        if res.returncode == 0:
            print(f"✅ {name} PASSED ({duration:.2f}s)")
            return True
        else:
            print(f"❌ {name} FAILED with code {res.returncode} ({duration:.2f}s)")
            return False
    except Exception as e:
        print(f"❌ {name} encountered execution exception: {e}")
        return False


def main() -> int:
    steps = [
        (
            "Skills Specification Validator",
            [sys.executable, "scripts/verify_skills.py"],
        ),
        ("Ruff Linter", ["uv", "run", "ruff", "check", "."]),
        (
            "Translation Catalog Freshness",
            ["uv", "run", "python", "scripts/check_translations.py"],
        ),
        ("Pytest Test Suite", ["uv", "run", "pytest", "tests/"]),
    ]

    failed = []
    for name, cmd in steps:
        success = run_step(name, cmd)
        if not success:
            failed.append(name)

    print("\n========================================================")
    print("PREFLIGHT SUMMARY")
    print("========================================================")
    if failed:
        print("❌ The following checks failed:")
        for f in failed:
            print(f"   - {f}")
        return 1

    print("🎉 ALL PREFLIGHT CHECKS PASSED! Ready for deployment/merge.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

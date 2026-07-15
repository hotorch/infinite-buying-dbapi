from __future__ import annotations

import subprocess
import sys


def main() -> int:
    if len(sys.argv) != 2 or sys.argv[1] not in {"live", "capital"}:
        print("usage: infinite_buying_runner.py live|capital", file=sys.stderr)
        return 2
    command = (
        ["uv", "run", "app", "automation", "tick", "--all", "--quiet-when-idle"]
        if sys.argv[1] == "live"
        else ["uv", "run", "app", "capital", "scan"]
    )
    completed = subprocess.run(command, check=False, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if completed.stdout.strip():
        print(completed.stdout.strip())
    if completed.returncode and completed.stderr.strip():
        print(completed.stderr.strip(), file=sys.stderr)
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Recreate the constructed C00 fixture: a two-commit repository with an injected interface drift.

    python retry_fixture.py TARGET_DIR

Deterministic: fixed author, dates and bytes give the same two commit SHAs on
every machine. This is a controlled fixture, never an observed incident.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

CLIENT = 'from httpkit.retry import Retry\n\n\ndef make_default_retry():\n    """Retry policy used by every client."""\n    return Retry(total=3)\n'
RETRY_S = 'class Retry:\n    """Retry policy."""\n\n    def __init__(self, total=3, method_whitelist=None):\n        self.total = total\n        self.methods = method_whitelist\n'
RETRY_T = 'class Retry:\n    """Retry policy."""\n\n    def __init__(self, total=3, allowed_methods=None):\n        self.total = total\n        self.methods = allowed_methods\n'
STATES = [("s", "2024-01-01T00:00:00+00:00", {"httpkit/__init__.py": "", "httpkit/client.py": CLIENT, "httpkit/retry.py": RETRY_S}), ("t", "2024-03-01T00:00:00+00:00", {"httpkit/retry.py": RETRY_T})]


def main() -> int:
    target = Path(sys.argv[1])
    target.mkdir(parents=True, exist_ok=True)

    def git(*args: str, date: str | None = None) -> str:
        env = dict(os.environ, GIT_AUTHOR_NAME="Fixture", GIT_AUTHOR_EMAIL="fixture@docagent.local", GIT_COMMITTER_NAME="Fixture", GIT_COMMITTER_EMAIL="fixture@docagent.local")
        if date:
            env.update(GIT_AUTHOR_DATE=date, GIT_COMMITTER_DATE=date)
        return subprocess.run(["git", "-c", "core.autocrlf=false", *args], cwd=target, env=env, check=True, text=True, stdout=subprocess.PIPE).stdout.strip()

    git("init", "-q", "-b", "main")
    for label, date, files in STATES:
        for name, text in files.items():
            (target / name).parent.mkdir(parents=True, exist_ok=True)
            with open(target / name, "w", encoding="utf-8", newline="\n") as handle:
                handle.write(text)
        git("add", "-A")
        git("commit", "-q", "-m", f"fixture state {label}", date=date)
        print(label, git("rev-parse", "HEAD"))
    return 0


if __name__ == "__main__":
    sys.exit(main())

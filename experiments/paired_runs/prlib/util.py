"""Shared helpers for the paired-run benchmark: hashing, atomic writes, Git, ledgers, host facts."""

from __future__ import annotations

import ctypes
import hashlib
import json
import os
import platform
import shutil
import signal
import stat
import subprocess
import sys
import tarfile
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

EXCERPT_BYTES = 512
LEDGER_BYTES = 64 * 1024
SUMMARY_RESERVE = 3072

PACKAGE_DIR = Path(__file__).resolve().parents[1]
EXPERIMENTS_DIR = PACKAGE_DIR.parent
REPO_ROOT = EXPERIMENTS_DIR.parent
HELPER = REPO_ROOT / "skills" / "docagent" / "scripts" / "docagent.py"


class BenchError(RuntimeError):
    pass


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def hash_obj(value: Any) -> str:
    return sha256_bytes(canonical(value).encode("utf-8"))


def write_atomic(path: Path, data: bytes | str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + f".tmp{os.getpid()}")
    with open(temp, "wb") as handle:
        handle.write(data.encode("utf-8", errors="surrogateescape") if isinstance(data, str) else data)
    os.replace(temp, path)


def write_json(path: Path, value: Any) -> None:
    write_atomic(path, json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n")


def read_json(path: Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def read_jsonl(path: Path) -> list[dict]:
    if not Path(path).is_file():
        return []
    rows = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def excerpt(value: Any, limit: int = EXCERPT_BYTES) -> str:
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
    raw = text.encode("utf-8")
    if len(raw) <= limit:
        return text
    return raw[: limit - 3].decode("utf-8", errors="ignore") + "…"


def run(argv: list[str], cwd: Path | None = None, timeout: float | None = None, env: dict | None = None, check: bool = False, input_text: str | None = None) -> subprocess.CompletedProcess:
    """Run a command given as an argument array. Never goes through a shell."""
    result = subprocess.run(argv, cwd=cwd, timeout=timeout, env=env, input=input_text, text=True, encoding="utf-8", errors="replace", stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if check and result.returncode != 0:
        raise BenchError(f"command failed ({result.returncode}): {' '.join(argv[:6])}\n{result.stderr.strip()[-800:]}")
    return result


def git(root: Path, *args: str, check: bool = True) -> str:
    return run(["git", "-c", "core.autocrlf=false", "-c", "core.safecrlf=false", *args], cwd=root, check=check).stdout.strip()


def kill_tree(process: subprocess.Popen) -> None:
    try:
        if os.name == "nt":
            subprocess.run(["taskkill", "/T", "/F", "/PID", str(process.pid)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            os.killpg(os.getpgid(process.pid), signal.SIGKILL)
    except (OSError, ProcessLookupError):
        pass


def remove_tree(path: Path) -> None:
    """Delete a directory even when Git left read-only files in it (Windows)."""

    def force(function, target, _error):
        os.chmod(target, stat.S_IWRITE)
        function(target)

    if Path(path).exists():
        try:
            shutil.rmtree(path, **({"onexc": force} if sys.version_info >= (3, 12) else {"onerror": force}))
        except OSError:
            pass


def extract_tar(tar_path: Path, target: Path) -> None:
    target.mkdir(parents=True, exist_ok=True)
    with tarfile.open(tar_path) as archive:
        members = [m for m in archive.getmembers() if m.isfile() or m.isdir()]
        if sys.version_info >= (3, 12):
            archive.extractall(target, members=members, filter="data")
        else:
            archive.extractall(target, members=members)


def init_snapshot_repo(root: Path, message: str) -> str:
    """Turn an exported tree into a one-commit repository with no history or remotes."""
    git(root, "init", "-q", "-b", "main")
    git(root, "config", "user.email", "bench@docagent.local")
    git(root, "config", "user.name", "DocAgent Bench")
    git(root, "config", "core.autocrlf", "false")
    git(root, "add", "-A")
    env = dict(os.environ, GIT_AUTHOR_DATE="2000-01-01T00:00:00Z", GIT_COMMITTER_DATE="2000-01-01T00:00:00Z")
    run(["git", "commit", "-q", "--allow-empty", "-m", message], cwd=root, env=env, check=True)
    return git(root, "rev-parse", "HEAD")


def workspace_diff(root: Path) -> str:
    """The actual unified diff of everything the agent changed, new files included."""
    git(root, "add", "-A")
    result = subprocess.run(["git", "-c", "core.autocrlf=false", "diff", "--cached", "--no-color", "--binary", "HEAD"], cwd=root, stdout=subprocess.PIPE, check=True)
    return result.stdout.decode("utf-8", errors="surrogateescape")  # bytes kept as they are: no newline translation


def _memory_mb() -> tuple[float | None, float | None]:
    try:
        if os.name == "nt":
            class Status(ctypes.Structure):
                _fields_ = [("length", ctypes.c_ulong), ("load", ctypes.c_ulong), ("total", ctypes.c_ulonglong), ("avail", ctypes.c_ulonglong), ("a", ctypes.c_ulonglong), ("b", ctypes.c_ulonglong), ("c", ctypes.c_ulonglong), ("d", ctypes.c_ulonglong), ("e", ctypes.c_ulonglong)]
            status = Status()
            status.length = ctypes.sizeof(Status)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status))
            return status.total / 2**20, status.avail / 2**20
        info = {}
        for line in Path("/proc/meminfo").read_text().splitlines():
            key, _, rest = line.partition(":")
            info[key] = float(rest.split()[0]) / 1024
        return info.get("MemTotal"), info.get("MemAvailable")
    except (OSError, AttributeError, ValueError, IndexError):
        return None, None


def _gpu() -> list[dict]:
    if not shutil.which("nvidia-smi"):
        return []
    try:
        out = run(["nvidia-smi", "--query-gpu=name,memory.total,memory.used", "--format=csv,noheader,nounits"], timeout=10).stdout
    except (OSError, subprocess.TimeoutExpired):
        return []
    rows = []
    for line in out.splitlines():
        parts = [p.strip() for p in line.split(",")]
        if len(parts) == 3:
            rows.append({"name": parts[0], "vram_total_mb": float(parts[1]), "vram_used_mb": float(parts[2])})
    return rows


def host_info(disk_path: Path | None = None) -> dict:
    total, available = _memory_mb()
    disk = shutil.disk_usage(str(disk_path or Path.cwd()))
    return {
        "host": platform.node(),
        "os": platform.platform(),
        "python": platform.python_version(),
        "cpu": platform.processor() or platform.machine(),
        "cpu_logical": os.cpu_count(),
        "ram_total_mb": round(total) if total else None,
        "ram_available_mb": round(available) if available else None,
        "gpu": _gpu(),
        "disk_free_gb": round(disk.free / 2**30, 1),
        "docker": shutil.which("docker"),
    }


class ResourceSampler:
    """Samples host-wide used memory and VRAM while a stage runs. Process RSS is not exposed without extra packages."""

    def __init__(self, interval: float = 2.0):
        self.interval = interval
        self.peak_used_mb: float | None = None
        self.min_available_mb: float | None = None
        self.peak_vram_mb: float | None = None
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._loop, daemon=True)

    def _sample(self) -> None:
        total, available = _memory_mb()
        if total and available:
            used = total - available
            self.peak_used_mb = max(self.peak_used_mb or 0, used)
            self.min_available_mb = min(self.min_available_mb or available, available)
        for gpu in _gpu():
            self.peak_vram_mb = max(self.peak_vram_mb or 0, gpu["vram_used_mb"])

    def _loop(self) -> None:
        while not self._stop.is_set():
            self._sample()
            self._stop.wait(self.interval)

    def __enter__(self) -> "ResourceSampler":
        self._sample()
        self._thread.start()
        return self

    def __exit__(self, *_: Any) -> None:
        self._stop.set()
        self._thread.join(timeout=5)
        self._sample()

    def summary(self) -> dict:
        def rounded(value: float | None) -> int | None:
            return round(value) if value is not None else None

        return {
            "host_peak_used_mb": rounded(self.peak_used_mb),
            "host_min_available_mb": rounded(self.min_available_mb),
            "vram_peak_used_mb": rounded(self.peak_vram_mb),
            "process_peak_mb": None,
            "process_peak_note": "unavailable: no per-process sampler in the standard library",
            "remote_memory": None,
        }


class Ledger:
    """Append-only JSONL trace with a byte cap. Counters keep running after the cap is hit."""

    def __init__(self, path: Path, base: dict, cap: int = LEDGER_BYTES):
        self.path = path
        self.base = base
        self.cap = cap
        self.seq = 0
        self.written = 0
        self.truncated = 0
        self.bytes = 0
        self.counts: dict[str, int] = {}
        path.parent.mkdir(parents=True, exist_ok=True)
        self._handle = open(path, "w", encoding="utf-8", newline="\n")
        self._started = time.monotonic()

    def event(self, event_type: str, **fields: Any) -> int:
        self.seq += 1
        self.counts[event_type] = self.counts.get(event_type, 0) + 1
        row = {**self.base, "seq": self.seq, "event_type": event_type}
        row.setdefault("elapsed_ms", int((time.monotonic() - self._started) * 1000))
        for key, value in fields.items():
            row[key] = excerpt(value) if isinstance(value, str) else value
        line = json.dumps(row, ensure_ascii=False) + "\n"
        size = len(line.encode("utf-8"))
        if self.bytes + size > self.cap - SUMMARY_RESERVE:
            self.truncated += 1
            return self.seq
        self._handle.write(line)
        self._handle.flush()
        self.bytes += size
        self.written += 1
        return self.seq

    def close(self, **summary: Any) -> dict:
        totals = {"events_total": self.seq, "events_written": self.written, "events_truncated": self.truncated, "truncated": self.truncated > 0, "counts": dict(self.counts), "cap_bytes": self.cap}
        row = {**self.base, "seq": self.seq + 1, "event_type": "terminal_summary", **totals, **summary}
        self._handle.write(json.dumps(row, ensure_ascii=False) + "\n")
        self._handle.close()
        return totals


def expand_command(command: list[str]) -> list[str]:
    return [part.replace("{python}", sys.executable).replace("{experiments}", str(EXPERIMENTS_DIR)) for part in command]

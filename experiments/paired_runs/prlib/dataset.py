"""Pinned SWE-bench Lite access, candidate ordering, and revision snapshots.

Leak control starts here. The reference patch, the evaluator test patch, the
eval script and the hints are dropped at fetch time; only their hashes are
kept. The test-name lists go to a separate evaluator-only store. Nothing in
the public cache can reveal the fix.
"""

from __future__ import annotations

import io
import json
import random
import subprocess
import tarfile
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .util import BenchError, git, hash_obj, now_iso, read_json, read_jsonl, run, sha256_bytes, write_atomic, write_json

PUBLIC_FIELDS = ("instance_id", "repo", "base_commit", "problem_statement", "version", "created_at", "environment_setup_commit", "image")
EVALUATOR_FIELDS = ("FAIL_TO_PASS", "PASS_TO_PASS")
HASH_ONLY_FIELDS = ("patch", "test_patch", "eval_script", "hints_text")
PAGE = 100


def _get_json(url: str, timeout: float = 60) -> dict:
    request = urllib.request.Request(url, headers={"User-Agent": "docagent-experiments"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def served_revision(name: str) -> str:
    return _get_json(f"https://huggingface.co/api/datasets/{name}")["sha"]


def load_split(name: str, split: str, revision: str | None, cache_dir: Path, grader_store: Path) -> dict:
    """Return {"meta", "public": {id: row}}. Fetches once per pinned revision, then works offline."""
    if not revision:
        raise BenchError(f"dataset revision is not pinned; the revision served now is {served_revision(name)}. Put it in the study config.")
    slug = name.replace("/", "__") + f"__{split}__{revision[:12]}"
    public_path = cache_dir / "datasets" / slug / "public.jsonl"
    meta_path = cache_dir / "datasets" / slug / "meta.json"
    if not meta_path.is_file():
        served = served_revision(name)
        if served != revision:
            raise BenchError(f"pinned dataset revision {revision} is not the revision served now ({served}); the row API only serves the current one. Re-pin deliberately or restore the cache.")
        rows, offset, total = [], 0, None
        while total is None or offset < total:
            query = urllib.parse.urlencode({"dataset": name, "config": "default", "split": split, "offset": offset, "length": PAGE})
            page = _get_json("https://datasets-server.huggingface.co/rows?" + query)
            total = page["num_rows_total"]
            rows.extend(item["row"] for item in page["rows"])
            offset += PAGE
        if served_revision(name) != revision:
            raise BenchError("dataset revision changed while fetching; retry")
        public_lines, evaluator_lines = [], []
        for row in sorted(rows, key=lambda r: r["instance_id"]):
            public = {key: row.get(key) for key in PUBLIC_FIELDS}
            public["row_sha256"] = hash_obj(row)
            public["hidden_sha256"] = {key: sha256_bytes(str(row.get(key) or "").encode("utf-8")) for key in HASH_ONLY_FIELDS}
            public_lines.append(json.dumps(public, sort_keys=True, ensure_ascii=False))
            evaluator_lines.append(json.dumps({"instance_id": row["instance_id"], **{key: row.get(key) for key in EVALUATOR_FIELDS}}, sort_keys=True))
        write_atomic(public_path, "\n".join(public_lines) + "\n")
        write_atomic(grader_store / "datasets" / slug / "evaluator_only.jsonl", "\n".join(evaluator_lines) + "\n")
        write_json(meta_path, {"dataset": name, "split": split, "revision": revision, "rows": len(rows), "fetched_at": now_iso(), "public_sha256": sha256_bytes(public_path.read_bytes()), "dropped_fields": list(HASH_ONLY_FIELDS), "evaluator_only_fields": list(EVALUATOR_FIELDS)})
    meta = read_json(meta_path)
    if sha256_bytes(public_path.read_bytes()) != meta["public_sha256"]:
        raise BenchError(f"cached dataset file changed on disk: {public_path}")
    return {"meta": meta, "public": {row["instance_id"]: row for row in read_jsonl(public_path)}}


def evaluator_tests(name: str, split: str, revision: str, grader_store: Path, instance_id: str) -> dict:
    slug = name.replace("/", "__") + f"__{split}__{revision[:12]}"
    for row in read_jsonl(grader_store / "datasets" / slug / "evaluator_only.jsonl"):
        if row["instance_id"] == instance_id:
            out = {}
            for key in EVALUATOR_FIELDS:
                value = row.get(key)
                out[key] = json.loads(value) if isinstance(value, str) else (value or [])
            return out
    raise BenchError(f"no evaluator record for {instance_id}")


def candidate_order(public: dict, repos: list[str], seed: int) -> dict:
    """Sorted, then shuffled per repository with the published seed, then dealt round-robin."""
    per_repo = {}
    for repo in repos:
        ids = sorted(i for i, row in public.items() if row["repo"] == repo)
        random.Random(f"{seed}:{repo}").shuffle(ids)
        per_repo[repo] = ids
    order, depth = [], 0
    while any(depth < len(ids) for ids in per_repo.values()):
        for repo in repos:
            if depth < len(per_repo[repo]):
                order.append(per_repo[repo][depth])
        depth += 1
    return {"seed": seed, "repos": repos, "per_repo": per_repo, "round_robin": order}


def ensure_clone(repo: str, cache_dir: Path) -> Path:
    """Evaluator-side bare clone with full history. Solvers never see this directory."""
    target = cache_dir / "repos" / (repo.replace("/", "__") + ".git")
    if not (target / "HEAD").is_file():
        target.parent.mkdir(parents=True, exist_ok=True)
        run(["git", "clone", "--bare", "--quiet", f"https://github.com/{repo}.git", str(target)], check=True, timeout=3600)
    return target


def commit_date(clone: Path, revision: str) -> datetime:
    return datetime.fromtimestamp(int(git(clone, "show", "-s", "--format=%ct", revision)), tz=timezone.utc)


def resolve_revisions(clone: Path, base_commit: str, min_age_days: int) -> dict:
    """t is the benchmark's pre-fix commit; s is the nearest first-parent ancestor at least min_age_days older."""
    t_date = commit_date(clone, base_commit)
    cutoff = t_date - timedelta(days=min_age_days)
    s = git(clone, "rev-list", "--first-parent", "-1", f"--before={int(cutoff.timestamp())}", base_commit)
    if not s:
        raise BenchError(f"no first-parent ancestor at least {min_age_days} days before {base_commit}")
    s_date = commit_date(clone, s)
    return {"t": base_commit, "t_date": t_date.strftime("%Y-%m-%dT%H:%M:%SZ"), "s": s, "s_date": s_date.strftime("%Y-%m-%dT%H:%M:%SZ"), "age_days": round((t_date - s_date).total_seconds() / 86400, 1), "rule": f"nearest first-parent ancestor >= {min_age_days} days before t"}


def export_snapshot(clone: Path, revision: str, tar_path: Path) -> str:
    """Exactly one tree as committed: raw blobs, no history, no refs, no later objects.

    `git archive` is avoided on purpose: it applies end-of-line conversion and
    export attributes, so its output can differ from the tree the grader checks out.
    Symbolic links and submodules are skipped and listed next to the tar file.
    """
    if not tar_path.is_file():
        tar_path.parent.mkdir(parents=True, exist_ok=True)
        listing = subprocess.run(["git", "ls-tree", "-r", "-z", revision], cwd=clone, stdout=subprocess.PIPE, check=True).stdout
        entries, skipped = [], []
        for item in listing.split(b"\0"):
            if not item:
                continue
            meta, _, name = item.partition(b"\t")
            mode, kind, oid = meta.split()
            if kind != b"blob" or mode == b"120000":
                skipped.append(name.decode("utf-8", "replace"))
                continue
            entries.append((mode, oid, name.decode("utf-8")))
        temp = tar_path.with_suffix(".part")
        reader = subprocess.Popen(["git", "cat-file", "--batch"], cwd=clone, stdin=subprocess.PIPE, stdout=subprocess.PIPE)
        try:
            with tarfile.open(temp, "w") as archive:
                for mode, oid, name in sorted(entries, key=lambda e: e[2]):
                    reader.stdin.write(oid + b"\n")
                    reader.stdin.flush()
                    size = int(reader.stdout.readline().split()[2])
                    data = reader.stdout.read(size)
                    reader.stdout.read(1)
                    info = tarfile.TarInfo(name)
                    info.size, info.mtime, info.mode = size, 0, (0o755 if mode == b"100755" else 0o644)
                    archive.addfile(info, io.BytesIO(data))
        finally:
            reader.stdin.close()
            reader.wait()
        temp.replace(tar_path)
        write_json(tar_path.with_suffix(".skipped.json"), {"revision": revision, "skipped_non_regular_entries": skipped})
    return sha256_bytes(tar_path.read_bytes())

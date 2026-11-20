"""Official grading: request bundles for the SWE-bench harness and import of its reports.

This module never grades anything itself. It writes a request (controls and/or
predictions in the official JSONL format), hands it to a grader that runs the
official harness (`experiments/grader/remote_grade.py`, locally with Docker or
on a GitHub-hosted runner), and reads the harness reports back. Reports live
in the grader store, which no solver workspace can reach.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

from .util import EXPERIMENTS_DIR, REPO_ROOT, BenchError, git, now_iso, read_json, run, write_atomic, write_json

BASE_CONTROL = "base_control"
GOLD_CONTROL = "gold_control"


def safe_id(text: str) -> str:
    return "".join(ch if ch.isalnum() or ch in "._-" else "-" for ch in text)


def build_request(manifest: dict, manifest_hash: str, instance_id: str, request_id: str, attempts: list[dict], controls: bool, out_dir: Path) -> Path:
    """Write request.json plus one official predictions file per attempt."""
    request_dir = out_dir / request_id
    if request_dir.exists():
        raise BenchError(f"grading request already exists: {request_dir}")
    predictions = []
    for attempt in attempts:
        patch = Path(attempt["patch_path"]).read_bytes().decode("utf-8", errors="replace")
        record = {"instance_id": instance_id, "model_name_or_path": safe_id(f"{attempt['backend_name']}__{attempt['arm']}"), "model_patch": patch}
        name = f"predictions/{attempt['attempt_id']}.jsonl"
        write_atomic(request_dir / name, json.dumps(record, ensure_ascii=False) + "\n")
        predictions.append({"attempt_id": attempt["attempt_id"], "arm": attempt["arm"], "run_id": safe_id(attempt["attempt_id"]).lower(), "file": name, "model_name_or_path": record["model_name_or_path"], "empty": not patch.strip(), "patch_sha256": attempt["patch_sha256"]})
    request = {
        "schema_version": 1, "request_id": request_id, "created_at": now_iso(), "manifest_hash": manifest_hash,
        "dataset_name": manifest["dataset"]["name"], "split": manifest["dataset"]["split"], "dataset_revision": manifest["dataset"]["revision"],
        "swebench_revision": manifest["evaluator"]["swebench_revision"], "instance_id": instance_id, "max_workers": 1,
        "timeout_s": manifest["evaluator"].get("timeout_s", 1800), "controls": [BASE_CONTROL, GOLD_CONTROL] if controls else [], "predictions": predictions,
    }
    write_json(request_dir / "request.json", request)
    return request_dir


def run_local(request_dir: Path, results_dir: Path) -> None:
    """Run the official harness on this host. Needs Docker and the pinned swebench package."""
    import sys

    if not shutil.which("docker"):
        raise BenchError("local grading needs Docker, which is not on this host; use the remote route")
    run([sys.executable, str(EXPERIMENTS_DIR / "grader" / "remote_grade.py"), "--request", str(request_dir / "request.json"), "--out", str(results_dir)], check=True)


def push_request(request_dir: Path, remote: str = "origin") -> str:
    """Publish the request on its own branch so the grading workflow picks it up. Explicit opt-in only."""
    request_id = request_dir.name
    branch = f"grading/{request_id}"
    if git(REPO_ROOT, "status", "--porcelain", "--", "experiments", ".github"):
        raise BenchError("commit the pipeline before pushing a grading request: the runner executes the committed grader")
    with tempfile.TemporaryDirectory(prefix="grading-wt-") as temp:
        tree = Path(temp) / "wt"
        git(REPO_ROOT, "worktree", "add", "-q", "-b", branch, str(tree), "HEAD")
        try:
            shutil.copytree(request_dir, tree / "grading" / "requests" / request_id)
            git(tree, "add", "-A", "grading")
            git(tree, "commit", "-q", "-m", f"Grading request {request_id}")
            run(["git", "push", "-q", remote, branch], cwd=tree, check=True, timeout=300)
        finally:
            git(REPO_ROOT, "worktree", "remove", "--force", str(tree), check=False)
    return branch


def fetch_results(request_id: str, results_root: Path, remote: str = "origin", wait_s: float = 0, poll_s: float = 30) -> Path | None:
    """Copy the official reports from the grading branch into the grader store. Returns None while pending."""
    branch = f"grading/{request_id}"
    prefix = f"grading/results/{request_id}/"
    deadline = time.monotonic() + wait_s
    while True:
        run(["git", "fetch", "-q", remote, f"+refs/heads/{branch}:refs/remotes/{remote}/{branch}"], cwd=REPO_ROOT, timeout=300)
        ref = f"refs/remotes/{remote}/{branch}"
        listing = run(["git", "ls-tree", "-r", "--name-only", ref, prefix], cwd=REPO_ROOT).stdout.splitlines()
        if prefix + "done.json" in listing:
            target = results_root / request_id
            # cat-file, not show: `git show ref:path` first stats that string as a file name and fails on long paths.
            # Everything is read before anything is written, and done.json is written last, so a partial copy is never mistaken for a finished one.
            files = {name: subprocess.run(["git", "cat-file", "blob", f"{ref}:{name}"], cwd=REPO_ROOT, stdout=subprocess.PIPE, check=True).stdout for name in listing}
            for name in sorted(files, key=lambda item: item.endswith("/done.json")):
                write_atomic(target / name[len(prefix):], files[name])
            return target
        if time.monotonic() >= deadline:
            return None
        time.sleep(poll_s)


def read_outcome(results_dir: Path, name: str) -> dict:
    """Normalise one harness result (a control or an attempt) into separate apply and grade statuses."""
    path = results_dir / name / "outcome.json"
    if not path.is_file():
        return {"grading_status": "pending", "resolved": None, "apply_status": "not_run", "report": None}
    outcome = read_json(path)
    report = outcome.get("report") or {}
    if outcome.get("skipped_empty"):
        return {**outcome, "grading_status": "not_graded_empty_patch", "resolved": False, "apply_status": "not_run"}
    if outcome.get("error") or not report:
        return {**outcome, "grading_status": "infra_error", "resolved": None, "apply_status": "unknown"}
    # The harness sets patch_successfully_applied only when it could parse test results, so a patch that
    # applies but breaks the test run shows False there. The apply step itself is read from the run log.
    log = " ".join(outcome.get("apply_lines") or [])
    applied = bool(report.get("patch_successfully_applied")) or bool(outcome.get("skip_patch")) or (">>>>> Applied Patch" in log and "Patch Apply Failed" not in log)
    note = None
    if report.get("infra_failure"):
        status = "infra_error"
    elif not applied:
        status = "patch_apply_failed"
    elif report.get("resolved"):
        status = "resolved"
    else:
        status = "unresolved"
        if not report.get("tests_status"):
            note = "patch applied, but the test run produced no parseable results (the patched code could not be imported or collected); the harness reports resolved=false"
    resolved = report.get("resolved") if status in {"resolved", "unresolved"} else (False if status == "patch_apply_failed" else None)
    return {**outcome, "grading_status": status, "resolved": resolved, "apply_status": "applied" if applied else "failed", "grade_note": note}


def control_verdict(results_dir: Path) -> dict:
    """Environment controls: the unmodified base must fail a FAIL_TO_PASS test; the reference patch must resolve."""
    base = read_outcome(results_dir, BASE_CONTROL)
    gold = read_outcome(results_dir, GOLD_CONTROL)
    tests = ((base.get("report") or {}).get("tests_status") or {}).get("FAIL_TO_PASS") or {}
    base_failed = sorted(tests.get("failure") or [])
    base_ok = base["grading_status"] == "unresolved" and len(base_failed) > 0
    gold_ok = gold["grading_status"] == "resolved"
    return {
        "base_control": {"expected": "at least one FAIL_TO_PASS test runs and fails on the unmodified base", "grading_status": base["grading_status"], "fail_to_pass_failed": base_failed, "fail_to_pass_passed": sorted(tests.get("success") or []), "ok": base_ok},
        "gold_control": {"expected": "official grader marks the reference patch resolved", "grading_status": gold["grading_status"], "ok": gold_ok},
        "ok": base_ok and gold_ok, "environment": (read_json(results_dir / "done.json") if (results_dir / "done.json").is_file() else {}),
    }

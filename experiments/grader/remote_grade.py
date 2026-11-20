#!/usr/bin/env python3
"""Grader side: run the official SWE-bench harness on one grading request.

Runs on any Linux host with Docker and the pinned `swebench` package: a
teammate's machine, or the GitHub-hosted runner started by
`.github/workflows/swebench-grade.yml`. It needs nothing else from this
repository and makes no model call.

    python remote_grade.py --request grading/requests/<id>/request.json --out grading/results/<id>

For every item it calls the harness's own code and keeps the harness's own
`report.json` and per-test output:

* base_control   harness negative-test mode (`skip_patch=True`): the evaluator
                 test script on the unmodified base. This exists because the
                 harness skips empty predictions before running any test.
* gold_control   `--predictions_path gold`: the reference patch.
* predictions    one official predictions JSONL per solver attempt.

The dataset is loaded from the parquet file of the pinned revision, so the
grader sees exactly the rows the preparer saw. The reference patch, the eval
script and the gold run log never leave the grader: only reports and test
output are written to the results directory.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
import time
import traceback
import urllib.request
from pathlib import Path

TEST_OUTPUT_CAP = 200 * 1024
LOG_CAP = 64 * 1024


def tail(path: Path, cap: int) -> str:
    data = path.read_bytes()
    text = data[-cap:].decode("utf-8", errors="replace")
    return (f"[truncated to the last {cap} bytes of {len(data)}]\n" if len(data) > cap else "") + text


def shell(argv: list[str]) -> str:
    try:
        return subprocess.run(argv, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=900).stdout.strip()
    except (OSError, subprocess.TimeoutExpired) as exc:
        return f"unavailable: {exc}"


def memory_mb() -> dict:
    info = {}
    try:
        for line in Path("/proc/meminfo").read_text().splitlines():
            key, _, rest = line.partition(":")
            if key in {"MemTotal", "MemAvailable"}:
                info[key] = round(float(rest.split()[0]) / 1024)
    except OSError:
        pass
    return info


def collect(log_dir: Path, target: Path, instance_id: str, keep_run_log: bool) -> dict:
    """Copy the harness's own report and per-test output for one run."""
    target.mkdir(parents=True, exist_ok=True)
    outcome: dict = {"report": None, "has_test_output": False, "apply_lines": []}
    report = log_dir / "report.json"
    if report.is_file():
        outcome["report"] = json.loads(report.read_text()).get(instance_id)
        shutil.copyfile(report, target / "report.json")
    output = log_dir / "test_output.txt"
    if output.is_file():
        (target / "test_output.txt").write_text(tail(output, TEST_OUTPUT_CAP), encoding="utf-8")
        outcome["has_test_output"] = True
    run_log = log_dir / "run_instance.log"
    if run_log.is_file():
        text = run_log.read_text(errors="replace")
        outcome["apply_lines"] = [line[:200] for line in text.splitlines() if ">>>>>" in line or "Skipping model patch" in line or "Test runtime" in line][:20]
        if keep_run_log:
            (target / "run_instance.log").write_text(tail(run_log, LOG_CAP), encoding="utf-8")
    return outcome


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the official SWE-bench harness on one grading request")
    parser.add_argument("--request", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    request_path = Path(args.request).resolve()
    request = json.loads(request_path.read_text(encoding="utf-8"))
    out = Path(args.out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    instance_id = request["instance_id"]
    started = time.time()
    environment: dict = {
        "request_id": request["request_id"], "instance_id": instance_id, "host": platform.node(), "os": platform.platform(), "python": platform.python_version(),
        "cpu_logical": os.cpu_count(), "memory_mb_start": memory_mb(), "disk_free_gb_start": round(shutil.disk_usage(".").free / 2**30, 1),
        "docker": shell(["docker", "version", "--format", "{{.Server.Version}}"]), "runner": os.environ.get("RUNNER_NAME"), "github_run": os.environ.get("GITHUB_RUN_ID"),
        "dataset_name": request["dataset_name"], "split": request["split"], "dataset_revision": request["dataset_revision"], "swebench_revision_requested": request["swebench_revision"],
    }
    items: dict = {}
    try:
        import swebench
        from swebench.harness import run_evaluation as harness
        from swebench.harness.constants import RUN_EVALUATION_LOG_DIR

        environment["swebench_version"] = swebench.__version__
        environment["swebench_install"] = shell([sys.executable, "-m", "pip", "freeze", "--all"]).split("\n")
        environment["swebench_install"] = [line for line in environment["swebench_install"] if line.lower().startswith("swebench")]

        work = Path(os.environ.get("RUNNER_TEMP") or "/tmp") / f"grade-{request['request_id']}"
        work.mkdir(parents=True, exist_ok=True)
        parquet = work / f"{request['split']}-{request['dataset_revision'][:12]}.parquet"
        url = f"https://huggingface.co/datasets/{request['dataset_name']}/resolve/{request['dataset_revision']}/data/{request['split']}-00000-of-00001.parquet"
        urllib.request.urlretrieve(url, parquet)
        environment["dataset_file"] = url
        dataset_name = str(parquet)
        instances = harness.load_instances(dataset_name, request["split"], [instance_id], None)
        image = instances[0].get("image")
        environment["image"] = image
        cold = time.time()
        environment["image_pull"] = shell(["docker", "pull", "-q", image])
        environment["image_pull_s"] = round(time.time() - cold, 1)
        environment["image_digest"] = shell(["docker", "image", "inspect", image, "--format", "{{json .RepoDigests}} {{.Id}}"])
        timeout = int(request.get("timeout_s", 1800))

        def run_item(name: str, run_id: str, model: str, action, keep_run_log: bool, extra: dict) -> None:
            begun = time.time()
            outcome: dict = {"name": name, "run_id": run_id, "model_name_or_path": model, **extra}
            try:
                action()
                outcome.update(collect(RUN_EVALUATION_LOG_DIR / run_id / model / instance_id, out / name, instance_id, keep_run_log))
                if outcome["report"] is None:
                    outcome["error"] = "harness produced no report.json for this run"
            except Exception as exc:  # the harness can raise anything; record it and continue
                outcome["error"] = f"{type(exc).__name__}: {exc}"[:500]
                outcome["traceback"] = traceback.format_exc()[-1500:]
            outcome["elapsed_s"] = round(time.time() - begun, 1)
            (out / name).mkdir(parents=True, exist_ok=True)
            (out / name / "outcome.json").write_text(json.dumps(outcome, indent=2) + "\n", encoding="utf-8")
            items[name] = {k: outcome.get(k) for k in ("run_id", "elapsed_s", "error")}
            items[name]["resolved"] = (outcome.get("report") or {}).get("resolved")

        def harness_main(predictions_path: str, run_id: str) -> None:
            harness.main(dataset_name=dataset_name, split=request["split"], instance_ids=[instance_id], predictions_path=predictions_path, max_workers=1, open_file_limit=4096, run_id=run_id, timeout=timeout, rewrite_reports=False, modal=False, report_dir=str(work / "reports"))

        suffix = request["request_id"].lower()
        if "base_control" in request.get("controls", []):
            model = "base-control-no-patch"
            placeholder = {instance_id: {"instance_id": instance_id, "model_name_or_path": model, "model_patch": "<none: harness negative-test mode, no patch applied>"}}
            run_id = f"base-{suffix}"
            run_item("base_control", run_id, model, lambda: harness.run_instances(placeholder, instances, 1, run_id, timeout, skip_patch=True), True, {"skip_patch": True, "mode": "harness run_instances(skip_patch=True)"})
        if "gold_control" in request.get("controls", []):
            run_id = f"gold-{suffix}"
            run_item("gold_control", run_id, "gold", lambda: harness_main("gold", run_id), False, {"mode": "harness main(predictions_path='gold')"})
        for prediction in request.get("predictions", []):
            name = prediction["attempt_id"]
            if prediction.get("empty"):
                (out / name).mkdir(parents=True, exist_ok=True)
                outcome = {"name": name, "run_id": prediction["run_id"], "skipped_empty": True, "report": None, "note": "the official harness does not run tests for an empty prediction; recorded as an observed solver failure"}
                (out / name / "outcome.json").write_text(json.dumps(outcome, indent=2) + "\n", encoding="utf-8")
                items[name] = {"run_id": prediction["run_id"], "skipped_empty": True, "resolved": False}
                continue
            predictions_file = str(request_path.parent / prediction["file"])
            run_item(name, prediction["run_id"], prediction["model_name_or_path"], lambda p=predictions_file, r=prediction["run_id"]: harness_main(p, r), True, {"arm": prediction.get("arm"), "mode": "harness main(predictions_path=<attempt>.jsonl)"})
    except Exception as exc:  # setup failure: report it as an infrastructure blocker
        environment["setup_error"] = f"{type(exc).__name__}: {exc}"[:800]
        environment["setup_traceback"] = traceback.format_exc()[-2000:]
    environment.update(items=items, elapsed_s=round(time.time() - started, 1), memory_mb_end=memory_mb(), disk_free_gb_end=round(shutil.disk_usage(".").free / 2**30, 1), finished_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
    (out / "done.json").write_text(json.dumps(environment, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"request_id": request["request_id"], "items": items, "setup_error": environment.get("setup_error")}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())

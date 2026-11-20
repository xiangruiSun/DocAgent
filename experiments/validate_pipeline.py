#!/usr/bin/env python3
"""One-issue validation of the whole pipeline on a real SWE-bench Lite instance.

    python -m experiments.validate_pipeline --instance-id <real-lite-id> \
        --backend-config <backend.json> --out <dir> [--study study.json] [--push-grading]

Exactly one explicit instance id. Wildcards, empty values, lists and manifest
files are refused: this entry point can never start a batch. It previews the
one id, the two evaluator controls, the three live solver attempts and the
limits, then runs restartable stages:

    preflight -> prepare -> controls -> solve -> grade -> report

Each stage only calls the public command lines of the two packages
(`paired_runs/bench.py`, `case_studies/cases.py`) and the integration adapter.
Rerunning continues from saved state: finished attempts are not paid for
again and earlier attempts are never overwritten. The solve stage refuses to
start until both evaluator controls behave as expected.
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
import urllib.request
from pathlib import Path

EXPERIMENTS = Path(__file__).resolve().parent
BENCH = EXPERIMENTS / "paired_runs" / "bench.py"
CASES = EXPERIMENTS / "case_studies" / "cases.py"
ADAPTER = EXPERIMENTS / "integration" / "trace_to_case.py"
STAGES = ("preflight", "prepare", "controls", "solve", "grade", "report")
FORBIDDEN = set("*?[]{},; \t\n")
ARMS = ("source_only", "static_stale", "selective_stale")


class Blocker(RuntimeError):
    pass


def single_id(value: str) -> str:
    if not value or not value.strip():
        raise Blocker("an explicit instance id is required; an empty id never starts a batch")
    if FORBIDDEN & set(value) or value.lower() in {"all", "lite", "test"} or value.endswith((".json", ".jsonl", ".txt")):
        raise Blocker(f"'{value}' is not one instance id; wildcards, lists and manifests are refused at this entry point (use bench.py run --batch for batches)")
    return value


def read_json(path: Path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp")
    temp.write_text(json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    os.replace(temp, path)


class Run:
    def __init__(self, out: Path):
        self.out = out
        self.state_path = out / "validation" / "state.json"
        self.state = read_json(self.state_path) if self.state_path.is_file() else {"commands": [], "stages": {}}

    def call(self, stage: str, argv: list[str], ok_codes: tuple[int, ...] = (0,)) -> subprocess.CompletedProcess:
        started = time.time()
        result = subprocess.run(argv, text=True, encoding="utf-8", errors="replace", stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        shown = " ".join(a if " " not in a else f'"{a}"' for a in argv)
        self.state["commands"].append({"stage": stage, "command": shown, "exit_status": result.returncode, "seconds": round(time.time() - started, 1)})
        write_json(self.state_path, self.state)
        print(f"[{stage}] exit {result.returncode} in {time.time() - started:.1f}s: {shown}", flush=True)
        if result.stdout.strip():
            print(result.stdout.strip()[-3000:], flush=True)
        if result.returncode not in ok_codes:
            raise Blocker(f"{stage} failed with exit {result.returncode}: {result.stderr.strip()[-600:] or result.stdout.strip()[-600:]}")
        return result

    def mark(self, stage: str, **facts) -> None:
        self.state["stages"][stage] = {"finished_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), **facts}
        write_json(self.state_path, self.state)


def preflight(run: Run, args, study: dict, backend: dict) -> None:
    command = [part.replace("{python}", sys.executable).replace("{experiments}", str(EXPERIMENTS)) for part in backend["command"]]
    capabilities = json.loads(run.call("preflight", command + ["--capabilities"]).stdout)
    facts = {"capabilities": capabilities, "host": platform.node(), "os": platform.platform(), "cpu_logical": os.cpu_count(), "disk_free_gb": round(shutil.disk_usage(str(args.out)).free / 2**30, 1), "docker": shutil.which("docker"), "git": shutil.which("git")}
    settings = backend.get("settings", {})
    if settings.get("api_style") == "ollama":
        try:
            with urllib.request.urlopen(settings.get("base_url", "http://127.0.0.1:11434").rstrip("/") + "/api/version", timeout=10) as response:
                facts["backend_endpoint"] = json.loads(response.read().decode("utf-8"))
        except OSError as exc:
            raise Blocker(f"backend endpoint {settings.get('base_url')} is not reachable: {exc}")
    if settings.get("api_key_env") and not os.environ.get(settings["api_key_env"]):
        raise Blocker(f"backend credentials missing: environment variable {settings['api_key_env']} is not set")
    if not capabilities.get("is_live"):
        if not args.allow_fake:
            raise Blocker("the configured backend is a fake; a dry run cannot be the acceptance run")
        facts["warning"] = "fake backend: this run can test the plumbing only and can never be accepted"
    for capability in ("can_reset_session", "can_limit_time", "can_count_actions", "can_capture_diff"):
        if not capabilities.get(capability):
            raise Blocker(f"backend cannot {capability}; it is not eligible for the comparison")
    route = study.get("evaluator", {}).get("grader", "github_actions")
    facts["grader_route"] = route
    if route == "local" and not facts["docker"]:
        raise Blocker("no working grader: Docker is not installed on this host and the study selects local grading. Use the remote route (evaluator.grader = github_actions) or grade the exported request on a Linux host.")
    if route != "local" and not args.push_grading:
        facts["note"] = "remote grading selected: grading requests are written locally and only published with --push-grading"
    if facts["disk_free_gb"] < 5:
        raise Blocker(f"only {facts['disk_free_gb']} GB free at {args.out}")
    run.mark("preflight", **facts)


def verdicts(report: dict, instance_id: str, replay: dict) -> dict:
    issue = next(i for i in report["issues"] if i["instance_id"] == instance_id)
    controls = issue.get("controls") or {}
    control_ok = bool(controls.get("ok"))
    arms = issue["arms"]
    terminal = all(arms[a]["status"] not in {"missing"} for a in ARMS)
    live = all(arms[a].get("is_live") for a in ARMS) if terminal else False
    graded = [a for a in ARMS if arms[a].get("generation_status") == "patch" and arms[a].get("apply_status") == "applied" and arms[a].get("grading_status") in {"resolved", "unresolved"}]
    accepted = control_ok and terminal and live and bool(graded) and replay.get("ok", False)
    reasons = []
    if not control_ok:
        reasons.append("environment controls are not both as expected")
    if not terminal:
        reasons.append("not every arm has a recorded terminal state")
    if terminal and not live:
        reasons.append("at least one attempt did not come from a live agent")
    if not graded:
        reasons.append("no unedited model-generated patch applied and received a conclusive official grade")
    if not replay.get("ok"):
        reasons.append("the case report did not replay offline")
    return {
        "environment_controls": {"status": "established" if control_ok else "not established", "base_control": controls.get("base_control"), "gold_control": controls.get("gold_control")},
        "pipeline_acceptance": {"status": "accepted" if accepted else "incomplete", "all_arms_terminal": terminal, "all_arms_live": live, "arms_with_conclusive_official_grade": graded, "offline_case_replay": replay, "open_gates": reasons},
        "agent_resolution": {a: {"outcome": arms[a].get("outcome"), "reason": arms[a].get("reason"), "terminal_state": arms[a].get("status"), "attempt_id": arms[a].get("attempt_id")} for a in ARMS},
        "performance_conclusions": "pending the held-out study; this is one development pilot",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0], formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__)
    parser.add_argument("--instance-id", required=True)
    parser.add_argument("--backend-config", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--study", default=str(EXPERIMENTS / "paired_runs" / "study.example.json"))
    parser.add_argument("--stage", choices=STAGES + ("all",), default="all", help="run one stage, or all remaining stages in order")
    parser.add_argument("--push-grading", action="store_true", help="publish grading requests on grading/<id> branches for the remote official grader")
    parser.add_argument("--wait-s", type=float, default=2400, help="how long to wait for remote official reports")
    parser.add_argument("--outer-timeout-s", type=float, default=3600)
    parser.add_argument("--preview-only", action="store_true")
    parser.add_argument("--allow-fake", action="store_true", help="plumbing test only; the result can never be accepted")
    parser.add_argument("--case-id")
    args = parser.parse_args(argv)
    started = time.monotonic()
    try:
        instance_id = single_id(args.instance_id)
        args.out = Path(args.out).resolve()
        args.out.mkdir(parents=True, exist_ok=True)
        study = read_json(Path(args.study))
        backend_path = EXPERIMENTS / "backends" / "backend.fake.json" if args.backend_config == "fake" else Path(args.backend_config)
        backend = read_json(backend_path)
        limits = {"time_s": 360, "max_actions": 12, **study.get("limits", {})}
        print("Validation preview")
        print(f"  instance id         : {instance_id}  (exactly one; development pilot, reserved from held-out evaluation)")
        print(f"  dataset             : {study['dataset']['name']} {study['dataset']['split']} @ {study['dataset'].get('revision')}")
        print("  evaluator controls  : 2  (unmodified base must fail a FAIL_TO_PASS test; reference patch must resolve)")
        print("  live solver attempts: 3  (source_only, static_stale, selective_stale; one attempt each, one worker)")
        print(f"  limits per attempt  : {limits['time_s']} s and {limits['max_actions']} visible actions shared by checker, planner and implementer")
        print(f"  backend             : {backend.get('name')} / {backend.get('settings', {}).get('model')}")
        print(f"  grader              : {study.get('evaluator', {}).get('grader', 'github_actions')}; outer timeout {args.outer_timeout_s:.0f} s")
        print(f"  output              : {args.out}", flush=True)
        if args.preview_only:
            return 0
        run = Run(args.out)
        manifest = args.out / "prepared" / "frozen.json"
        case_id = args.case_id or "PILOT-" + instance_id.replace("__", "-")
        stages = STAGES if args.stage == "all" else (args.stage,)
        python = sys.executable
        push = ["--push"] if args.push_grading else []
        for stage in stages:
            if time.monotonic() - started > args.outer_timeout_s:
                raise Blocker(f"outer timeout of {args.outer_timeout_s:.0f} s reached before stage {stage}; rerun to resume")
            if stage == "preflight":
                preflight(run, args, study, backend)
            elif stage == "prepare":
                if manifest.is_file() and any(i["instance_id"] == instance_id for i in read_json(manifest)["issues"]):
                    print("[prepare] frozen manifest already holds this instance; inputs are reused from cache", flush=True)
                else:
                    run.call("prepare", [python, str(BENCH), "prepare", "--config", args.study, "--out", str(args.out / "prepared"), "--instance-id", instance_id, "--status", "pilot"])
                run.mark("prepare", manifest=str(manifest))
            elif stage == "controls":
                result = run.call("controls", [python, str(BENCH), "grade", "--manifest", str(manifest), "--workers", "1", "--instance-id", instance_id, "--controls", "--wait-s", str(args.wait_s), *push], ok_codes=(0, 3))
                if result.returncode == 3:
                    raise Blocker("official control reports are not available yet (grading request pending or not published); rerun this stage to resume")
                verdict = json.loads(result.stdout[result.stdout.index("{"):]).get("verdict") or {}
                run.mark("controls", ok=bool(verdict.get("ok")), verdict=verdict)
                if not verdict.get("ok"):
                    raise Blocker("environment controls did not behave as expected; no solver call was made. See the control reports in the grader store.")
            elif stage == "solve":
                if not run.state["stages"].get("controls", {}).get("ok"):
                    raise Blocker("refusing to spend solver calls: the evaluator controls are not established for this instance")
                run.call("solve", [python, str(BENCH), "pilot", "--backend", str(backend_path), "--out", str(args.out / "prepared")])
                run.mark("solve")
            elif stage == "grade":
                result = run.call("grade", [python, str(BENCH), "grade", "--manifest", str(manifest), "--workers", "1", "--instance-id", instance_id, "--wait-s", str(args.wait_s), *push], ok_codes=(0, 3))
                run.mark("grade", pending=result.returncode == 3)
            elif stage == "report":
                run.call("report", [python, str(BENCH), "report", "--manifest", str(manifest), "--out", str(args.out / "report")])
                local = read_json(args.out / "prepared" / "local_paths.json")
                replay = {"ok": False}
                case_runs = args.out / "case_runs"
                if not (case_runs / case_id).exists():
                    run.call("report", [python, str(ADAPTER), "--manifest", str(manifest), "--instance-id", instance_id, "--case-id", case_id, "--out", str(case_runs), "--results", str(Path(local["grader_store"]) / "results")])
                clean_env = {k: v for k, v in os.environ.items() if k.upper() in {"PATH", "SYSTEMROOT", "TEMP", "TMP", "HOME", "USERPROFILE", "PATHEXT", "COMSPEC"}}
                digests = []
                for _ in range(2):  # a clean process, twice: same bytes, no backend, no benchmark package on the path
                    result = subprocess.run([python, "-I", str(CASES), "replay", "--case", case_id, "--runs", str(case_runs), "--offline", "--out", str(args.out / "case_report")], cwd=str(CASES.parent), env=clean_env, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                    run.state["commands"].append({"stage": "report", "command": f"python -I cases.py replay --case {case_id} --runs {case_runs} --offline", "exit_status": result.returncode})
                    print(f"[report] exit {result.returncode}: python -I cases.py replay --case {case_id} --offline", flush=True)
                    if result.returncode == 0:
                        digests.append(json.loads(result.stdout)["sha256"])
                replay = {"ok": len(digests) == 2 and digests[0] == digests[1], "report": str(args.out / "case_report" / f"{case_id}.md"), "sha256": digests[0] if digests else None, "model_calls": 0}
                summary = verdicts(read_json(args.out / "report" / "report.json"), instance_id, replay)
                summary.update(instance_id=instance_id, elapsed_s=round(time.monotonic() - started, 1), commands=run.state["commands"])
                write_json(args.out / "validation" / "summary.json", summary)
                run.mark("report", acceptance=summary["pipeline_acceptance"]["status"])
                print(json.dumps({k: summary[k] for k in ("environment_controls", "pipeline_acceptance", "agent_resolution")}, indent=2, default=str)[:6000])
        return 0
    except Blocker as exc:
        print(f"BLOCKED: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())

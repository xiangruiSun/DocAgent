#!/usr/bin/env python3
"""Paired DocAgent issue-resolution benchmark (Task 2).

    python bench.py smoke   --backend fake
    python bench.py prepare --config study.json --out OUT/prepared [--instance-id ID --status pilot]
    python bench.py pilot   --config study.json --backend backend.json --out OUT/prepared
    python bench.py run     --manifest OUT/prepared/frozen.json --backend backend.json --resume [--instance-id ID | --batch]
    python bench.py grade   --manifest OUT/prepared/frozen.json --workers 1 --instance-id ID [--controls] [--push] [--wait-s N]
    python bench.py report  --manifest OUT/prepared/frozen.json --out OUT/report

Standard library only. This package does not import the case-study package and
needs none of its outputs. Batch execution is opt-in: `run` without an explicit
instance refuses to start unless `--batch` is given.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from prlib import dataset, grading, prepare as prep, report as reporting, runner  # noqa: E402
from prlib.util import EXPERIMENTS_DIR, BenchError, expand_command, git, host_info, now_iso, read_json, run as run_command, write_json  # noqa: E402

WILDCARD = set("*?[]{},; \t\n")


def one_instance_id(value: str | None) -> str:
    """An explicit single id. Never a pattern, a list or a manifest path."""
    if not value or not value.strip():
        raise BenchError("an explicit instance id is required; an empty id never starts a batch")
    if WILDCARD & set(value) or value.endswith((".json", ".jsonl", ".txt")):
        raise BenchError(f"'{value}' is not a single instance id; wildcards, lists and manifests are refused here")
    return value


def load_backend(path: str) -> dict:
    if path == "fake":
        path = str(EXPERIMENTS_DIR / "backends" / "backend.fake.json")
    backend = read_json(Path(path))
    if not isinstance(backend.get("command"), list):
        raise BenchError("backend config needs 'command' as an argument array")
    return {k: v for k, v in backend.items() if not k.startswith("_")}


def layout(manifest_path: Path) -> dict:
    prepared = manifest_path.resolve().parent
    local = read_json(prepared / "local_paths.json")
    return {"prepared": prepared, "root": prepared.parent, "runs": prepared.parent / "runs", "requests": prepared.parent / "grading_requests", "results": Path(local["grader_store"]) / "results", "grader_store": Path(local["grader_store"]), "work": Path(tempfile.gettempdir()) / "docagent-bench-work"}


def load_manifest(path: str) -> tuple[dict, str, dict]:
    manifest = read_json(Path(path))
    return manifest, prep.manifest_hash(manifest), layout(Path(path))


def cmd_prepare(args: argparse.Namespace) -> int:
    study = prep.load_study(Path(args.config))
    prepared = Path(args.out).resolve()
    prepared.mkdir(parents=True, exist_ok=True)
    cache, store = Path(study["cache_dir"]), Path(study["grader_store"])
    write_json(prepared / "local_paths.json", {"cache_dir": str(cache), "grader_store": str(store)})
    if study.get("relevance"):
        write_json(store / "relevance.json", study["relevance"])
    data = dataset.load_split(study["dataset"]["name"], study["dataset"]["split"], study["dataset"].get("revision"), cache, store)
    order = dataset.candidate_order(data["public"], study["repos"], study["seed"])
    write_json(prepared / "candidates.json", {**order, "dataset": data["meta"], "rule": "sorted ids, shuffled per repository with the seed, dealt round-robin; pilot reserved first"})
    issues, statuses, log = [], {}, []
    if args.instance_id:
        instance_id = one_instance_id(args.instance_id)
        if instance_id not in data["public"]:
            raise BenchError(f"{instance_id} is not in {study['dataset']['name']} {study['dataset']['split']} at revision {study['dataset']['revision']}")
        result = prep.prepare_issue(prep.spec_from_dataset(data["public"][instance_id], study), study, prepared)
        issues.append(result["issue"])
        statuses[instance_id] = args.status
        log.append({**result["screening"], "decision": f"prepared by explicit id as {args.status}"})
    else:
        wanted = 1 + int(study["tier"]["held_out"])
        deadline = time.monotonic() + 60 * float(study["screen"]["timebox_minutes"])
        for position, instance_id in enumerate(order["round_robin"][: int(study["screen"]["max_candidates"])]):
            if len(issues) >= wanted:
                break
            if time.monotonic() > deadline:
                log.append({"instance_id": instance_id, "decision": "not screened: timebox reached"})
                continue
            try:
                result = prep.prepare_issue(prep.spec_from_dataset(data["public"][instance_id], study), study, prepared)
            except (BenchError, OSError) as exc:
                log.append({"instance_id": instance_id, "order": position, "decision": f"excluded: {str(exc)[:200]}"})
                continue
            screening = result["screening"]
            if screening["contradicted_mentioned_exposed"]:
                status = "pilot" if not issues else "held_out"
                issues.append(result["issue"])
                statuses[instance_id] = status
                decision = f"selected as {status}: an issue-named claim changed between s and t and was routed"
            elif screening["contradicted_mentioned"]:
                decision = "excluded from selection: issue-named claim changed but the router missed it (kept in this log as a router miss)"
            else:
                decision = "excluded: no issue-named claim changed between s and t"
            log.append({**screening, "order": position, "decision": decision})
    write_json(prepared / "screening_log.json", {"generated_at": now_iso(), "selection_rule": "first candidates in round-robin order with a contradicted claim that the issue names and the released router exposed; outcomes of solvers are never consulted", "entries": log})
    if not issues:
        raise BenchError("no eligible issue was prepared; see screening_log.json")
    manifest = prep.freeze(study, issues, statuses, prepared)
    print(json.dumps({"frozen": str(prepared / "frozen.json"), "manifest_hash": prep.manifest_hash(manifest), "issues": [{"instance_id": i["instance_id"], "status": statuses[i["instance_id"]], "s": i["s"][:12], "t": i["t"][:12], "packet_sha256": i["packet_sha256"][:12]} for i in issues], "screened": len(log)}, indent=2))
    return 0


def select_issues(manifest: dict, args: argparse.Namespace, statuses: tuple[str, ...] | None = None) -> list[dict]:
    if getattr(args, "instance_id", None):
        instance_id = one_instance_id(args.instance_id)
        chosen = [i for i in manifest["issues"] if i["instance_id"] == instance_id]
        if not chosen:
            raise BenchError(f"{instance_id} is not in the frozen manifest")
        return chosen
    chosen = [i for i in manifest["issues"] if statuses is None or i["status"] in statuses]
    if len(chosen) > 1 and not getattr(args, "batch", False):
        raise BenchError(f"{len(chosen)} issues selected; batch execution is opt-in, pass --batch or name one --instance-id")
    return chosen


def run_issues(manifest: dict, manifest_hash: str, paths: dict, issues: list[dict], backend: dict, new_block: bool) -> list[dict]:
    summaries = []
    for issue in issues:
        for arm in issue["arm_order"]:
            started = time.monotonic()
            summary = runner.run_attempt(manifest, manifest_hash, issue, arm, backend, paths["prepared"], paths["runs"], paths["work"], new_block)
            line = {"instance_id": issue["instance_id"], "arm": arm, "attempt_id": summary["attempt_id"], "wall_s": round(time.monotonic() - started, 1)}
            line.update({"skipped": True, "reason": summary["reason"]} if summary.get("skipped") else {"status": summary["status"], "live": summary["is_live"], "patch_bytes": summary["patch"]["bytes"], "actions": summary["actions_used"]})
            print(json.dumps(line), flush=True)
            summaries.append(line)
    return summaries


def cmd_run(args: argparse.Namespace) -> int:
    manifest, manifest_hash, paths = load_manifest(args.manifest)
    issues = select_issues(manifest, args, statuses=("held_out",))
    run_issues(manifest, manifest_hash, paths, issues, load_backend(args.backend), args.new_block)
    return 0


def cmd_pilot(args: argparse.Namespace) -> int:
    manifest, manifest_hash, paths = load_manifest(str(Path(args.out) / "frozen.json"))
    pilots = [i for i in manifest["issues"] if i["status"] == "pilot"]
    if len(pilots) != 1:
        raise BenchError(f"expected exactly one pilot issue in the manifest, found {len(pilots)}")
    lines = run_issues(manifest, manifest_hash, paths, pilots, load_backend(args.backend), False)
    slowest = max((line.get("wall_s", 0) for line in lines), default=0)
    write_json(paths["root"] / "pilot_timing.json", {"cells": lines, "slowest_cell_s": slowest, "note": "budget held-out tiers with the slowest cell plus per-issue preparation and grading; reserve 20 minutes"})
    return 0


def cmd_grade(args: argparse.Namespace) -> int:
    manifest, manifest_hash, paths = load_manifest(args.manifest)
    if args.workers != 1:
        raise BenchError("one grader worker per host: use --workers 1")
    instance_id = one_instance_id(args.instance_id)
    route = args.route or manifest["evaluator"].get("grader", "github_actions")
    attempts = []
    if not args.controls:
        for arm in runner.ARMS:
            summary = reporting.primary_attempt(paths["runs"], instance_id, arm, manifest_hash)
            if summary and not reporting.find_results(paths["results"], summary["attempt_id"]):
                attempts.append({"attempt_id": summary["attempt_id"], "arm": arm, "backend_name": summary["backend"].get("name") or "backend", "patch_path": str(Path(summary["_dir"]) / "patch.diff"), "patch_sha256": summary["patch"]["sha256"]})
    kind = "controls" if args.controls else "attempts"
    marker = paths["requests"] / f"{instance_id}.{kind}.json"
    if marker.is_file():
        request_id = read_json(marker)["request_id"]
    else:
        if not args.controls and not attempts:
            print(json.dumps({"status": "nothing to grade: every recorded attempt already has an official outcome or none exists"}))
            return 0
        request_id = grading.safe_id(f"{instance_id}-{kind}-{manifest_hash[:8]}-{time.strftime('%Y%m%dT%H%M%S', time.gmtime())}").lower()
        grading.build_request(manifest, manifest_hash, instance_id, request_id, attempts, args.controls, paths["requests"])
        write_json(marker, {"request_id": request_id, "created_at": now_iso(), "attempts": [a["attempt_id"] for a in attempts], "pushed": False})
    request_dir = paths["requests"] / request_id
    state = read_json(marker)
    result_dir = paths["results"] / request_id
    if (result_dir / "done.json").is_file():
        status = "graded"
    elif route == "local":
        grading.run_local(request_dir, result_dir)
        status = "graded"
    else:
        if not state.get("pushed"):
            if not args.push:
                print(json.dumps({"status": "request written, not sent", "request": str(request_dir), "next": "rerun with --push to publish it on a grading branch, or copy it to a Linux host with Docker and run experiments/grader/remote_grade.py"}, indent=2))
                return 0
            state["branch"] = grading.push_request(request_dir, manifest["evaluator"].get("remote", "origin"))
            state["pushed"] = True
            write_json(marker, state)
        fetched = grading.fetch_results(request_id, paths["results"], manifest["evaluator"].get("remote", "origin"), wait_s=args.wait_s)
        status = "graded" if fetched else "pending"
    out = {"request_id": request_id, "status": status, "results": str(result_dir)}
    if status == "graded":
        done = read_json(result_dir / "done.json")
        out["setup_error"] = done.get("setup_error")
        out["verdict"] = grading.control_verdict(result_dir) if args.controls else {a: grading.read_outcome(result_dir, a)["grading_status"] for a in read_json(marker)["attempts"]}
        if args.controls:
            out["verdict"].pop("environment", None)
    print(json.dumps(out, indent=2))
    return 0 if status == "graded" else 3


def cmd_report(args: argparse.Namespace) -> int:
    manifest, manifest_hash, paths = load_manifest(args.manifest)
    relevance_path = paths["grader_store"] / "relevance.json"
    relevance = read_json(relevance_path) if relevance_path.is_file() else {}
    report = reporting.build(manifest, manifest_hash, paths["prepared"], paths["runs"], paths["results"], relevance)
    reporting.write(report, Path(args.out))
    print(json.dumps({"report": str(Path(args.out) / "summary.md"), "model_calls": 0}, indent=2))
    return 0


SMOKE_ISSUE = "Retry ignores the method_whitelist argument in `pkg/retry.py`: passing Retry(method_whitelist=['GET']) raises TypeError. The retry backoff and pick helpers should keep working."
SMOKE_S = {
    "pkg/__init__.py": "",
    "pkg/retry.py": "DEFAULT_TOTAL = 3\n\n\ndef pick(candidates):\n    return candidates[0]\n\n\nclass Retry:\n    def __init__(self, total=3, method_whitelist=None):\n        self.total = total\n        self.methods = method_whitelist\n\n\ndef backoff(attempt, factor=0.5):\n    return factor * (2 ** attempt)\n",
    "pkg/stable.py": "def untouched(value):\n    return value\n",
}
SMOKE_T = {
    "pkg/retry.py": "DEFAULT_TOTAL = 3\n\n\ndef pick(candidates):\n    return candidates[0]\n\n\ndef pick(candidates, default=None):  # redefinition: the call shape is ambiguous\n    return candidates[0] if candidates else default\n\n\nclass Retry:\n    def __init__(self, total=3, allowed_methods=None):\n        self.total = total\n        self.methods = allowed_methods\n\n\ndef backoff(attempt, factor=0.5):\n    # comment-only change: the recorded signature still holds\n    return factor * (2 ** attempt)\n",
}


def make_fixture(root: Path) -> dict:
    """A two-commit repository: one repairable drift, one harmless edit, one ambiguous definition."""
    root.mkdir(parents=True)
    git(root, "init", "-q", "-b", "main")
    git(root, "config", "user.email", "bench@docagent.local")
    git(root, "config", "user.name", "DocAgent Bench")
    revisions = {}
    for label, files in (("s", SMOKE_S), ("t", SMOKE_T)):
        for name, text in files.items():
            (root / name).parent.mkdir(parents=True, exist_ok=True)
            (root / name).write_text(text, encoding="utf-8", newline="\n")
        git(root, "add", "-A")
        git(root, "commit", "-q", "-m", f"fixture {label}")
        revisions[label] = git(root, "rev-parse", "HEAD")
    return {"instance_id": "fixture__retry-1", "repo": "fixture/retry", "clone": str(root), "problem_statement": SMOKE_ISSUE, **revisions, "rule": "controlled fixture, never a SWE-bench resolution"}


def cmd_smoke(args: argparse.Namespace) -> int:
    backend = load_backend(args.backend)
    capabilities = json.loads(run_command(expand_command(backend["command"]) + ["--capabilities"], check=True).stdout)
    base = Path(args.keep).resolve() if args.keep else Path(tempfile.mkdtemp(prefix="bench-smoke-"))
    if base.exists() and any(base.iterdir()):
        raise BenchError(f"smoke directory is not empty: {base}")
    try:
        study = {**prep.DEFAULTS, "cache_dir": str(base / "cache"), "grader_store": str(base / "grader_store"), "dataset": {"name": "fixture", "split": "none", "revision": "fixture"}}
        prepared = base / "prepared"
        result = prep.prepare_issue(make_fixture(base / "fixture_repo"), study, prepared)
        write_json(prepared / "local_paths.json", {"cache_dir": study["cache_dir"], "grader_store": study["grader_store"]})
        manifest = prep.freeze(study, [result["issue"]], {"fixture__retry-1": "pilot"}, prepared)
        manifest_hash = prep.manifest_hash(manifest)
        paths = layout(prepared / "frozen.json")
        paths["work"] = base / "work"
        issue = manifest["issues"][0]
        summaries = {arm: runner.run_attempt(manifest, manifest_hash, issue, arm, backend, prepared, paths["runs"], paths["work"]) for arm in issue["arm_order"]}
        again = runner.run_attempt(manifest, manifest_hash, issue, "static_stale", backend, prepared, paths["runs"], paths["work"])
        report = reporting.build(manifest, manifest_hash, prepared, paths["runs"], paths["results"], {})
        reporting.write(report, base / "report")
        source, static, selective = summaries["source_only"], summaries["static_stale"], summaries["selective_stale"]
        decisions = {d["old_text"].split("`")[1].split("(")[0].split(" ")[0]: d for d in selective["checks"]["decisions"]}
        checks = {
            "source_only receives no generated memory": source["packet"]["initial_sha256"] is None and source["generated_documents_in_workspace"] == 0 and not (paths["runs"] / issue["instance_id"] / "source_only" / source["attempt_id"] / "packet_final.md").exists(),
            "all arms start from the same clean snapshot": len({s["workspace_tree_sha256"] for s in summaries.values()}) == 1,
            "static and selective start from byte-identical stale packets": static["packet"]["initial_sha256"] == selective["packet"]["initial_sha256"] == issue["packet_sha256"],
            "static packet is passed through unchanged": static["packet"]["final_sha256"] == static["packet"]["initial_sha256"],
            "selective packet is rewritten by checks": selective["packet"]["final_sha256"] != selective["packet"]["initial_sha256"] and selective["counters"]["checks"] == 3,
            "only the selective arm runs the checker": source["counters"]["checks"] == 0 and static["counters"]["checks"] == 0,
            "ambiguous definition is unresolved and omitted": decisions["pkg.retry.pick"]["status"] == "unresolved" and decisions["pkg.retry.pick"]["policy_action"] == "omit",
            "changed signature is contradicted and repaired": decisions["pkg.retry.Retry.__init__"]["status"] == "contradicted" and "allowed_methods" in decisions["pkg.retry.Retry.__init__"]["repair_text"],
            "harmless source edit keeps a supported claim": decisions["pkg.retry.DEFAULT_TOTAL"]["status"] == "supported",
            "released file-change signal fires on the committed s..t change": result["screening"]["stale_documents_routed"] >= 1,
            "every attempt reached a recorded terminal state": all(s["status"] in runner.TERMINAL for s in summaries.values()),
            "resume makes no second call": again.get("skipped") is True,
            "report rebuilt offline with no model call": report["model_calls_made_by_this_report"] == 0 and (base / "report" / "summary.md").is_file(),
            "fake output is never counted as live": capabilities["is_live"] is not False or all(s["is_live"] is False for s in summaries.values()),
        }
        for name, ok in checks.items():
            print(f"{'PASS' if ok else 'FAIL'}  {name}")
        failed = [name for name, ok in checks.items() if not ok]
        print(f"smoke: {len(checks) - len(failed)}/{len(checks)} checks passed with backend '{backend.get('name')}' (live={capabilities['is_live']}); artifacts in {base if args.keep else 'a temporary directory (removed)'}")
        return 1 if failed else 0
    finally:
        if not args.keep:
            shutil.rmtree(base, ignore_errors=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0], formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    item = sub.add_parser("smoke", help="no-key end-to-end check on a controlled fixture")
    item.add_argument("--backend", default="fake")
    item.add_argument("--keep", help="keep artifacts in this empty directory")
    item = sub.add_parser("prepare", help="pin data, screen candidates, build memory and the stale packet, freeze the manifest")
    item.add_argument("--config", required=True)
    item.add_argument("--out", required=True)
    item.add_argument("--instance-id")
    item.add_argument("--status", choices=("pilot", "held_out"), default="pilot")
    item = sub.add_parser("pilot", help="run the three arms on the single pilot issue")
    item.add_argument("--config")
    item.add_argument("--backend", required=True)
    item.add_argument("--out", required=True)
    item = sub.add_parser("run", help="run held-out issues; more than one needs --batch")
    item.add_argument("--manifest", required=True)
    item.add_argument("--backend", required=True)
    item.add_argument("--resume", action="store_true", help="default behaviour; kept for explicitness")
    item.add_argument("--instance-id")
    item.add_argument("--batch", action="store_true")
    item.add_argument("--new-block", action="store_true", help="start a separate setup block after a solver configuration change")
    item = sub.add_parser("grade", help="send controls or recorded patches to the official harness and read its reports")
    item.add_argument("--manifest", required=True)
    item.add_argument("--workers", type=int, default=1)
    item.add_argument("--instance-id", required=True)
    item.add_argument("--controls", action="store_true")
    item.add_argument("--route", choices=("local", "github_actions"))
    item.add_argument("--push", action="store_true", help="publish the request on a grading/<id> branch")
    item.add_argument("--wait-s", type=float, default=0)
    item = sub.add_parser("report", help="rebuild tables from saved artifacts; no model call")
    item.add_argument("--manifest", required=True)
    item.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    try:
        return {"smoke": cmd_smoke, "prepare": cmd_prepare, "pilot": cmd_pilot, "run": cmd_run, "grade": cmd_grade, "report": cmd_report}[args.command](args)
    except BenchError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())

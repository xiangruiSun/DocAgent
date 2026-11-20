#!/usr/bin/env python3
"""Thin integration adapter: one paired-run pilot trace -> one case-study bundle.

    python trace_to_case.py --manifest OUT/prepared/frozen.json --instance-id ID \
        --case-id PILOT-01 --out OUT/case_runs [--results GRADER_STORE/results]

It reads the benchmark package's public output files and writes the case
tool's public input files. It imports neither package and starts no model or
grader. The bundle it writes is self-contained: after this step
`cases.py replay --offline` needs nothing from the benchmark run.

Arm names map as: static_stale -> blind, selective_stale -> checked,
source_only -> source_only (shown as an extra column).
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
from pathlib import Path

ARM_MAP = {"static_stale": "blind", "selective_stale": "checked", "source_only": "source_only"}
TERMINAL = {"completed_patch", "completed_empty", "budget_exhausted", "action_limit", "infra_error"}


def read_json(path: Path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()] if Path(path).is_file() else []


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")


def first_attempt(runs: Path, instance_id: str, arm: str) -> tuple[dict, Path] | None:
    base = runs / instance_id / arm
    for path in sorted(base.glob("*/summary.json")) if base.is_dir() else []:
        summary = read_json(path)
        if summary["status"] in TERMINAL:
            return summary, path.parent
    return None


def official_outcome(results: Path | None, attempt_id: str) -> dict:
    if results and results.is_dir():
        for done in sorted(results.glob("*/done.json"), reverse=True):
            path = done.parent / attempt_id / "outcome.json"
            if path.is_file():
                outcome = read_json(path)
                report = outcome.get("report") or {}
                if outcome.get("skipped_empty"):
                    return {"kind": "patch", "verdict": "fail", "detail": "empty prediction; the official harness does not run tests for it", "official": True}
                applied = bool(report.get("patch_successfully_applied")) or ">>>>> Applied Patch" in " ".join(outcome.get("apply_lines") or [])
                if applied and report:
                    detail = f"official SWE-bench harness report, request {done.parent.name}: resolved={report.get('resolved')}"
                    if not report.get("tests_status"):
                        detail += "; the patch applied but the test run produced no parseable results"
                    return {"kind": "patch", "verdict": "pass" if report.get("resolved") else "fail", "detail": detail, "official": True}
                return {"kind": "patch", "verdict": "fail" if report else "ungraded", "detail": f"official harness: {outcome.get('error') or 'patch did not apply'}", "official": True}
    return {"kind": "patch", "verdict": "ungraded", "detail": "no official grade imported", "official": False}


def convert_events(ledger: list[dict], run_id: str, oracle: dict) -> list[dict]:
    rows = []

    def add(event_type: str, source: dict, **fields) -> None:
        rows.append({"run_id": run_id, "seq": len(rows) + 1, "role": source.get("role"), "stage": source.get("stage"), "event_type": event_type, "claim_id": source.get("claim_id"), "path": source.get("path"), "symbol": source.get("symbol"), "action": None, "evidence": source.get("observation"), "check_status": source.get("check_status"), "policy_action": source.get("policy_action"), "elapsed_ms": source.get("elapsed_ms"), "source_seq": source.get("seq"), **fields})

    for event in ledger:
        kind = event.get("event_type")
        if kind == "claim_exposure":
            add("claim_exposure", event, action="inject routed stale packet")
        elif kind == "check":
            add("check", event, action="check predicate against current source", old_text=event.get("old_text"), new_text=event.get("new_text"))
        elif kind == "tool_call":
            add("source_edit" if event.get("tool") == "replace_in_file" else "source_read", event, action=f"{event.get('tool')} {event.get('args') or ''}".strip())
        elif kind == "handoff":
            add("handoff", event, action="planner handoff")
        elif kind == "role_terminal" and event.get("stage") == "implementer":
            add("terminal_answer", event, action=event.get("exit_reason"))
    rows.append({"run_id": run_id, "seq": len(rows) + 1, "role": "oracle", "stage": "grade", "event_type": "oracle_outcome", "claim_id": None, "path": None, "symbol": None, "action": oracle["kind"], "evidence": oracle["detail"], "check_status": oracle["verdict"], "policy_action": None, "elapsed_ms": None})
    return rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Convert one paired-run pilot trace into a case-study bundle")
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--instance-id", required=True)
    parser.add_argument("--case-id", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--results", help="grader store results directory holding official reports")
    parser.add_argument("--claim-id", help="claim to feature; default: first checked claim, else first drifted exposed claim")
    args = parser.parse_args(argv)

    manifest_path = Path(args.manifest).resolve()
    manifest = read_json(manifest_path)
    prepared, runs = manifest_path.parent, manifest_path.parent.parent / "runs"
    issue = next((i for i in manifest["issues"] if i["instance_id"] == args.instance_id), None)
    if issue is None:
        print(f"error: {args.instance_id} is not in the manifest", file=sys.stderr)
        return 2
    issue_dir = prepared / args.instance_id
    packet = read_json(issue_dir / "packet.json")
    exposed = {c["claim_id"]: c for c in read_json(issue_dir / "claims_exposed.json")}
    drift = {r["claim_id"]: r for r in read_json(issue_dir / "drift.json")}
    attempts = {arm: first_attempt(runs, args.instance_id, arm) for arm in ARM_MAP}
    selective = attempts.get("selective_stale")
    decisions = ((selective[0].get("checks") or {}).get("decisions") or []) if selective else []
    claim_id = args.claim_id or (decisions[0]["claim_id"] if decisions else next((c for c in exposed if c in drift), None) or next(iter(exposed), None))
    if claim_id is None or claim_id not in exposed:
        print("error: no exposed claim to feature; the router returned an empty packet", file=sys.stderr)
        return 2
    claim = exposed[claim_id]
    decision = next((d for d in decisions if d["claim_id"] == claim_id), None)
    entry = next((e for e in packet["documents"] if claim_id in e["claim_ids"]), {})
    if decision:
        at_t = {"status": decision["status"], "evidence": decision["evidence"], "repair": decision.get("repair_text"), "source": "experimental checker during the selective attempt"}
    elif claim_id in drift:
        at_t = {"status": drift[claim_id]["status"], "evidence": drift[claim_id]["evidence"], "repair": None, "source": "experimental checker at prepare time (evaluator side)"}
    else:
        at_t = {"status": "supported" if claim["path"] in set(entry.get("changed_files") or []) else "unchecked", "evidence": "not among the claims that fail at t", "repair": None, "source": "prepare-time drift scan"}

    case_dir = Path(args.out).resolve() / args.case_id
    if case_dir.exists():
        print(f"error: {case_dir} already exists; choose a new case id rather than overwriting", file=sys.stderr)
        return 2
    issue_text = (issue_dir / "issue.md").read_text(encoding="utf-8")
    bundle = {
        "schema_version": 1, "case_id": args.case_id, "category": "benchmark_pilot", "project_url": f"https://github.com/{issue['repo']}", "s": issue["s"], "t": issue["t"],
        "claim": {"claim_id": claim_id, "statement": claim["text"], "covered_path": claim["path"], "predicate": claim["predicate"]},
        "change_origin": "natural_commit", "note_origin": "snapshot_generated",
        "task": {"kind": "patch", "prompt": issue_text[:1200], "prompt_truncated": len(issue_text) > 1200, "issue_sha256": issue["issue_sha256"], "instance_id": args.instance_id},
        "evidence": {
            "s": {"revision": issue["s"], "path": claim["path"], "status": "supported", "evidence": f"recorded by the issue-blind builder from the source at s: {claim['text']}", "verifier": manifest["driver"]["builder"]},
            "t": {"revision": issue["t"], "path": claim["path"], **at_t, "verifier": manifest["driver"]["checker"]},
        },
        "released_gate": {"source": "released docagent.py context_bundle freshness findings", "helper_sha256": issue["router"]["helper_sha256"], "covered_file_changed": bool(entry.get("stale")), "changed_covered_files": entry.get("changed_files") or [], "routed_document": entry.get("doc_path"), "router_rank": entry.get("rank")},
        "experimental_verifier": manifest["driver"]["checker"],
        "human_review": {"status": "pending", "note": "development pilot; reused only to test integration, reserved from held-out evaluation"},
        "source": "integration adapter from paired_runs", "manifest_hash_inputs": {"packet_sha256": issue["packet_sha256"], "snapshot_t_sha256": issue["snapshot_t_sha256"]}, "written_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    write_json(case_dir / "case.json", bundle)
    results = Path(args.results).resolve() if args.results else None
    converted = []
    for order, (arm, found) in enumerate(attempts.items(), 1):
        if not found:
            continue
        summary, attempt_dir = found
        target = case_dir / "attempts" / summary["attempt_id"]
        target.mkdir(parents=True)
        oracle = official_outcome(results, summary["attempt_id"])
        events = convert_events(read_jsonl(attempt_dir / "ledger.jsonl"), summary["attempt_id"], oracle)
        with open(target / "ledger.jsonl", "w", encoding="utf-8", newline="\n") as handle:
            for row in events:
                handle.write(json.dumps(row, ensure_ascii=False) + "\n")
        for name in ("packet_initial.md", "packet_final.md", "patch.diff", "handoff.md"):
            if (attempt_dir / name).is_file():
                shutil.copyfile(attempt_dir / name, target / name)
        reads = [e for e in events if e["event_type"] in {"source_read", "source_edit"} and e.get("path")]
        terminal = next((e for e in events if e["event_type"] == "terminal_answer"), {})
        write_json(target / "summary.json", {
            "attempt_id": summary["attempt_id"], "case_id": args.case_id, "arm": ARM_MAP[arm], "benchmark_arm": arm, "order": order, "status": summary["status"], "exit_reason": summary["roles"]["implementer"].get("exit_reason"),
            "is_live": summary["is_live"], "backend": summary["backend"], "capabilities": summary.get("capabilities") or {}, "packet_initial_sha256": summary["packet"]["initial_sha256"], "packet_final_sha256": summary["packet"]["final_sha256"],
            "check": {"status": decision["status"], "policy_action": decision["policy_action"], "evidence": decision["evidence"], "verifier": manifest["driver"]["checker"]} if arm == "selective_stale" and decision else None,
            "final_answer": terminal.get("evidence") or "", "first_inspected_path": reads[0]["path"] if reads else None, "actions": summary["actions_used"], "limits": summary["limits"], "patch_bytes": summary["patch"]["bytes"], "oracle": oracle,
            "timing": {"wall_ms": summary["timing"]["solve_ms"]}, "usage": summary["usage"], "resources": summary["resources"], "ledger": {"events_total": len(events), "events_truncated": summary["trace"]["events_truncated"], "truncated": summary["trace"]["truncated"]},
        })
        converted.append({"attempt_id": summary["attempt_id"], "arm": ARM_MAP[arm], "oracle": oracle["verdict"], "official": oracle["official"]})
    print(json.dumps({"case_id": args.case_id, "bundle": str(case_dir), "claim_id": claim_id, "attempts": converted}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())

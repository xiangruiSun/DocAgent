"""Offline report: reads saved manifests, traces, patches and official reports. Makes no model call."""

from __future__ import annotations

import csv
import io
from pathlib import Path

from . import grading
from .runner import ARMS, TERMINAL
from .util import now_iso, read_json, read_jsonl, write_atomic, write_json

READ_TOOLS = {"read_file", "search", "list_dir"}


def find_results(results_root: Path, name: str) -> Path | None:
    """Newest grader result directory that holds this control or attempt."""
    found = [p for p in sorted(results_root.glob("*/done.json")) if (p.parent / name / "outcome.json").is_file()]
    return found[-1].parent if found else None


def primary_attempt(runs_dir: Path, instance_id: str, arm: str, manifest_hash: str) -> dict | None:
    """The first terminal attempt under this manifest. Later attempts are listed but never replace it."""
    base = runs_dir / instance_id / arm
    for path in sorted(base.glob("*/summary.json")) if base.is_dir() else []:
        summary = read_json(path)
        if summary["key"]["manifest_hash"] == manifest_hash and summary["status"] in TERMINAL:
            summary["_dir"] = str(path.parent)
            return summary
    return None


def exploration(ledger: list[dict], relevant_paths: list[str]) -> dict:
    calls = [e for e in ledger if e.get("event_type") == "tool_call"]
    reads = [e for e in calls if e.get("tool") in READ_TOOLS]
    first = None
    for index, event in enumerate(reads, 1):
        text = f"{event.get('path') or ''} {event.get('observation') or ''}"
        if relevant_paths and any(path in text for path in relevant_paths):
            first = index
            break
    planner = [e for e in reads if e.get("stage") == "planner" and e.get("tool") == "read_file" and e.get("path")]
    implementer = [e for e in reads if e.get("stage") == "implementer" and e.get("tool") == "read_file" and e.get("path")]

    def overlaps(event: dict) -> bool:
        a = event.get("range") or [0, 0]
        return any(p["path"] == event["path"] and (p.get("range") or [0, 0])[0] <= a[1] and a[0] <= (p.get("range") or [0, 0])[1] for p in planner)

    return {
        "read_actions": len(reads), "reads_until_first_relevant_source": first, "reached_relevant_source": (first is not None) if relevant_paths else None,
        "relevance_annotation": "present" if relevant_paths else "missing", "distinct_paths": len({e["path"] for e in calls if e.get("path")}),
        "implementer_reads": len(implementer), "implementer_reads_overlapping_planner": sum(1 for e in implementer if overlaps(e)),
        "handoff_overlap_ratio": round(sum(1 for e in implementer if overlaps(e)) / len(implementer), 3) if implementer else None,
        "edited_paths": sorted({e["path"] for e in calls if e.get("tool") == "replace_in_file" and e.get("ok") and e.get("path")}),
    }


def build(manifest: dict, manifest_hash: str, prepared: Path, runs_dir: Path, results_root: Path, relevance: dict) -> dict:
    issues = []
    for issue in manifest["issues"]:
        instance_id = issue["instance_id"]
        drift = read_json(prepared / instance_id / "drift.json")
        note = relevance.get(instance_id, {})
        relevant_claims = set(note.get("claim_ids") or [])
        eligible = [r for r in drift if r["status"] == "contradicted" and (r["claim_id"] in relevant_claims if relevant_claims else False)]
        control_dirs = [p.parent for p in sorted(results_root.glob("*/done.json")) if (p.parent / grading.BASE_CONTROL).is_dir() and read_json(p).get("instance_id") == instance_id]
        controls = grading.control_verdict(control_dirs[-1]) if control_dirs else None
        arms = {}
        for arm in ARMS:
            summary = primary_attempt(runs_dir, instance_id, arm, manifest_hash)
            if summary is None:
                arms[arm] = {"status": "missing", "outcome": "missing", "reason": "no terminal attempt recorded"}
                continue
            ledger = read_jsonl(Path(summary["_dir"]) / "ledger.jsonl")
            result_dir = find_results(results_root, summary["attempt_id"])
            official = grading.read_outcome(result_dir, summary["attempt_id"]) if result_dir else {"grading_status": "pending", "resolved": None, "apply_status": "not_run"}
            if summary["patch"]["generation_status"] == "empty":
                outcome, reason = "unresolved", "empty prediction: observed solver failure, not gradeable"
            elif official["grading_status"] in {"resolved", "unresolved"}:
                outcome, reason = official["grading_status"], "official harness report"
            elif official["grading_status"] == "patch_apply_failed":
                outcome, reason = "unresolved", "official harness could not apply the patch"
            else:
                outcome, reason = "ungraded", official["grading_status"]
            decisions = (summary.get("checks") or {}).get("decisions") or []
            exposed = set(summary["packet"]["exposed_claim_ids"])
            supported_exposed = exposed - {r["claim_id"] for r in drift}
            arms[arm] = {
                "attempt_id": summary["attempt_id"], "status": summary["status"], "is_live": summary["is_live"], "backend": summary["backend"], "outcome": outcome, "reason": reason,
                "generation_status": summary["patch"]["generation_status"], "apply_status": official["apply_status"], "grading_status": official["grading_status"], "local_apply_check": summary["patch"]["local_apply_check"],
                "patch_bytes": summary["patch"]["bytes"], "patch_sha256": summary["patch"]["sha256"], "packet": {k: summary["packet"][k] for k in ("initial_sha256", "final_sha256", "initial_bytes", "final_bytes")},
                "actions_used": summary["actions_used"], "counters": summary["counters"], "solve_ms": summary["timing"]["solve_ms"], "usage": summary["usage"], "resources": summary["resources"],
                "trace": summary["trace"], "grading_s": official.get("elapsed_s"), "exploration": exploration(ledger, note.get("paths") or []),
                "outdated_claims": {"eligible_contradicted": len(eligible), "routed": sum(1 for r in eligible if r["routed"]), "exposed": sum(1 for r in eligible if r["claim_id"] in exposed), "corrected": sum(1 for d in decisions if d["policy_action"] == "repair" and d["claim_id"] in {r["claim_id"] for r in eligible}), "omitted_or_unresolved": sum(1 for d in decisions if d["policy_action"] == "omit" and d["claim_id"] in {r["claim_id"] for r in eligible}), "acted_upon": "needs human review of the trace", "relevance_annotation": "present" if relevant_claims else "missing"},
                "checking": {"checks": len(decisions), "check_ms": (summary.get("checks") or {}).get("check_ms"), "suspect_claims": (summary.get("checks") or {}).get("suspect_claims"), "supported_exposed": len(supported_exposed) if exposed else None, "supported_rejected": sum(1 for d in decisions if d["claim_id"] in supported_exposed and d["policy_action"] != "reuse") if exposed else None, "repairs": [{"claim_id": d["claim_id"], "old": d["old_text"], "new": d["repair_text"]} for d in decisions if d["policy_action"] == "repair"]},
            }
        issues.append({"instance_id": instance_id, "status": issue["status"], "repo": issue["repo"], "s": issue["s"], "t": issue["t"], "controls": controls, "arms": arms, "timing_ms": issue["timing_ms"], "packet_sha256": issue["packet_sha256"], "claims_not_supported_at_t": len(drift)})

    held_out = [i for i in issues if i["status"] == "held_out"]
    pairs = {"both_resolved": 0, "neither_resolved": 0, "selective_only": 0, "static_only": 0, "missing": 0}
    for item in held_out:
        static, selective = item["arms"]["static_stale"]["outcome"], item["arms"]["selective_stale"]["outcome"]
        if "ungraded" in (static, selective) or "missing" in (static, selective):
            pairs["missing"] += 1
        elif static == selective:
            pairs["both_resolved" if static == "resolved" else "neither_resolved"] += 1
        else:
            pairs["selective_only" if selective == "resolved" else "static_only"] += 1
    complete = len(held_out) - pairs["missing"]
    primary = {**pairs, "held_out_issues": len(held_out), "complete_pairs": complete, "paired_difference": round((pairs["selective_only"] - pairs["static_only"]) / complete, 3) if complete else None, "sensitivity_if_missing_all_favour_static": round((pairs["selective_only"] - pairs["static_only"] - pairs["missing"]) / len(held_out), 3) if held_out else None, "sensitivity_if_missing_all_favour_selective": round((pairs["selective_only"] - pairs["static_only"] + pairs["missing"]) / len(held_out), 3) if held_out else None}
    return {
        "generated_at": now_iso(), "manifest_hash": manifest_hash, "model_calls_made_by_this_report": 0, "issues": issues, "primary_paired_success": primary,
        "unmeasured": ["full current-source rebuild", "released DocAgent review-and-sync workflow", "fresh-memory arms", "rebuild amortisation for H=1,5,20"],
        "interpretation": "Counts, paired differences and traces only. With two to six issues one result moves the estimate a lot; no population-wide speed-up or significance claim. Pilot issues are development runs and are excluded from the paired table. Performance conclusions are pending the held-out study.",
    }


def write(report: dict, out: Path) -> None:
    write_json(out / "report.json", report)
    table = io.StringIO()
    writer = csv.writer(table, lineterminator="\n")
    writer.writerow(["instance_id", "issue_status", "arm", "attempt_id", "live", "terminal_state", "generation", "apply", "grading", "outcome", "actions", "checks", "solve_s", "input_tokens", "output_tokens", "host_peak_used_mb", "vram_peak_mb", "reads_to_relevant", "handoff_overlap"])
    lines = ["# Paired-run report", "", f"Generated {report['generated_at']} from saved artifacts. Model calls made by this report: 0.", "", report["interpretation"], ""]
    for issue in report["issues"]:
        lines += [f"## {issue['instance_id']} ({issue['status']})", "", f"Repository {issue['repo']}; s `{issue['s'][:12]}`, t `{issue['t'][:12]}`; stale packet `{issue['packet_sha256'][:12]}`.", ""]
        controls = issue["controls"]
        if controls:
            lines += [f"Environment controls: base **{'ok' if controls['base_control']['ok'] else 'NOT ok'}** ({controls['base_control']['grading_status']}, {len(controls['base_control']['fail_to_pass_failed'])} FAIL_TO_PASS failing), reference patch **{'ok' if controls['gold_control']['ok'] else 'NOT ok'}** ({controls['gold_control']['grading_status']}).", ""]
        else:
            lines += ["Environment controls: no official control report found.", ""]
        lines += ["| Arm | Live | Terminal state | Patch | Official grade | Outcome | Actions | Checks | Solve s |", "|---|---|---|---|---|---|---:|---:|---:|"]
        for arm, data in issue["arms"].items():
            if data["status"] == "missing":
                lines.append(f"| {arm} | | missing | | | missing | | | |")
                writer.writerow([issue["instance_id"], issue["status"], arm, "", "", "missing"] + [""] * 13)
                continue
            usage, resources, explore = data["usage"], data["resources"], data["exploration"]
            lines.append(f"| {arm} | {'yes' if data['is_live'] else 'NO (fake)'} | {data['status']} | {data['generation_status']}, {data['patch_bytes']} B | {data['grading_status']} | **{data['outcome']}** | {data['actions_used']} | {data['counters']['checks']} | {data['solve_ms'] / 1000:.1f} |")
            writer.writerow([issue["instance_id"], issue["status"], arm, data["attempt_id"], data["is_live"], data["status"], data["generation_status"], data["apply_status"], data["grading_status"], data["outcome"], data["actions_used"], data["counters"]["checks"], round(data["solve_ms"] / 1000, 1), usage.get("input_tokens"), usage.get("output_tokens"), resources.get("host_peak_used_mb"), resources.get("vram_peak_used_mb"), explore["reads_until_first_relevant_source"], explore["handoff_overlap_ratio"]])
        lines.append("")
    primary = report["primary_paired_success"]
    lines += ["## Primary paired success (held-out issues only)", "", f"Held-out issues: {primary['held_out_issues']}; complete static/selective pairs: {primary['complete_pairs']}; both {primary['both_resolved']}, neither {primary['neither_resolved']}, selective only {primary['selective_only']}, static only {primary['static_only']}, missing {primary['missing']}; paired difference {primary['paired_difference']}.", "", "Not measured in this run: " + "; ".join(report["unmeasured"]) + ".", ""]
    write_atomic(out / "summary.md", "\n".join(lines))
    write_atomic(out / "per_issue.csv", table.getvalue())

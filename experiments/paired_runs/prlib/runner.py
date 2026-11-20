"""One solver attempt: clean workspace, arm context, planner, implementer, diff, terminal state."""

from __future__ import annotations

import os
import shutil
import subprocess
import time
from pathlib import Path

from . import checker
from .util import BenchError, Ledger, ResourceSampler, excerpt, expand_command, extract_tar, hash_obj, init_snapshot_repo, kill_tree, now_iso, read_json, read_jsonl, run, sha256_bytes, sha256_file, workspace_diff, write_atomic, write_json

ARMS = ("source_only", "static_stale", "selective_stale")
TERMINAL = {"completed_patch", "completed_empty", "budget_exhausted", "action_limit", "infra_error"}

PLANNER_PROMPT = (
    "You are the planner in a two-step fix of a software issue. You can only read the repository. "
    "Use your few tool actions to find where the issue comes from, then call finish with a handoff note of at most 600 bytes: "
    "name the file and symbol to change and what to change. Any repository memory packet may be outdated; check it against the source when it matters.\n"
)
IMPLEMENTER_PROMPT = (
    "You are the implementer in a two-step fix of a software issue. Read the code you need, then make the smallest source change that fixes the issue using replace_in_file. "
    "Do not edit or add tests. Any repository memory packet or planner handoff may be outdated or wrong; the source is the authority. "
    "When the change is made, call finish with a one-line summary.\n"
)
PROMPTS = {"planner": PLANNER_PROMPT, "implementer": IMPLEMENTER_PROMPT}


def solver_config_hash(backend: dict, limits: dict) -> str:
    return hash_obj({"backend": backend, "limits": limits, "prompts": {k: sha256_bytes(v.encode("utf-8")) for k, v in PROMPTS.items()}})


def tree_hash(root: Path) -> str:
    rows = []
    for directory, folders, files in os.walk(root):
        folders[:] = sorted(f for f in folders if f != ".git")
        for name in sorted(files):
            path = Path(directory) / name
            rows.append(path.relative_to(root).as_posix() + ":" + sha256_file(path))
    return sha256_bytes("\n".join(sorted(rows)).encode("utf-8"))


def launch_backend(backend: dict, request: dict, attempt_dir: Path, deadline_s: float) -> dict:
    """Start the adapter as an argument array and enforce the deadline on its whole process tree."""
    role = request["role"]
    request_path = attempt_dir / f"{role}.request.json"
    write_json(request_path, request)
    argv = expand_command(backend["command"]) + ["--request", str(request_path)]
    options = {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP} if os.name == "nt" else {"start_new_session": True}
    started = time.monotonic()
    with open(attempt_dir / f"{role}.stderr.txt", "w", encoding="utf-8") as stderr:
        process = subprocess.Popen(argv, stdout=subprocess.DEVNULL, stderr=stderr, **options)
        try:
            process.wait(timeout=deadline_s + 20)
            killed = False
        except subprocess.TimeoutExpired:
            kill_tree(process)
            process.wait(timeout=30)
            killed = True
    result_path = Path(request["out"]["result"])
    if killed or not result_path.is_file():
        result = {"status": "budget_exhausted" if killed else "error", "exit_reason": "killed_at_deadline" if killed else "no_result_file", "is_live": None, "backend": {}, "actions": None, "usage": {}, "final_answer": None, "elapsed_ms": int((time.monotonic() - started) * 1000), "capabilities": {}}
    else:
        result = read_json(result_path)
    result["wall_ms"] = int((time.monotonic() - started) * 1000)
    result["exit_code"] = process.returncode
    return result


def existing_attempts(runs_dir: Path, instance_id: str, arm: str) -> list[dict]:
    base = runs_dir / instance_id / arm
    return [read_json(p) for p in sorted(base.glob("*/state.json"))] if base.is_dir() else []


def plan_attempt(runs_dir: Path, key: dict, new_block: bool = False) -> tuple[str | None, int]:
    """Resume rule. Returns (attempt_id to skip, next attempt number)."""
    states = existing_attempts(runs_dir, key["instance_id"], key["arm"])
    number = 1
    for state in states:
        number = max(number, state["key"]["attempt"] + 1)
        same_manifest = state["key"]["manifest_hash"] == key["manifest_hash"]
        if not same_manifest:
            continue
        if state["key"]["solver_config_hash"] != key["solver_config_hash"] and not new_block:
            raise BenchError(f"{key['instance_id']}/{key['arm']} already has an attempt under a different solver configuration; rerun every arm of this issue with --new-block instead of mixing configurations")
        if state["status"] in TERMINAL and state["key"]["solver_config_hash"] == key["solver_config_hash"] and state["key"]["seed"] == key["seed"]:
            return state["attempt_id"], number
    return None, number


def run_attempt(manifest: dict, manifest_hash: str, issue: dict, arm: str, backend: dict, prepared: Path, runs_dir: Path, work_root: Path, new_block: bool = False) -> dict:
    limits = manifest["limits"]
    seed = manifest["seed"]
    key = {"manifest_hash": manifest_hash, "instance_id": issue["instance_id"], "arm": arm, "solver_config_hash": solver_config_hash(backend, limits), "seed": seed}
    done, number = plan_attempt(runs_dir, key, new_block)
    if done:
        return {"attempt_id": done, "skipped": True, "reason": "terminal state already recorded; no new paid call"}
    key["attempt"] = number
    attempt_id = f"{issue['instance_id']}__{arm}__seed{seed}__a{number:02d}"
    attempt_dir = runs_dir / issue["instance_id"] / arm / attempt_id
    attempt_dir.mkdir(parents=True, exist_ok=False)
    state = {"attempt_id": attempt_id, "key": key, "status": "running", "started_at": now_iso()}
    write_json(attempt_dir / "state.json", state)

    issue_dir = prepared / issue["instance_id"]
    workspace = work_root / attempt_id / "ws"
    if workspace.parent.exists():
        shutil.rmtree(workspace.parent)
    extract_tar(Path(issue["snapshot_t"]), workspace)
    base_tree = tree_hash(workspace)
    init_snapshot_repo(workspace, "pre-fix snapshot")
    if base_tree != issue["tree_t_sha256"]:
        raise BenchError("workspace does not match the prepared pre-fix snapshot")

    ledger = Ledger(attempt_dir / "ledger.jsonl", {"run_id": attempt_id, "arm": arm})
    issue_text = (issue_dir / "issue.md").read_text(encoding="utf-8")
    budget_started = time.monotonic()
    actions_left = int(limits["max_actions"])
    counters = {"checks": 0, "planner_actions": 0, "implementer_actions": 0}
    context_paths: list[str] = []
    packet_info = {"initial_sha256": None, "final_sha256": None, "initial_bytes": 0, "final_bytes": 0, "exposed_claim_ids": []}
    check_report = None

    def remaining() -> float:
        return float(limits["time_s"]) - (time.monotonic() - budget_started)

    with ResourceSampler() as sampler:
        if arm != "source_only":
            initial = (issue_dir / "packet.md").read_bytes()
            if sha256_bytes(initial) != issue["packet_sha256"]:
                raise BenchError("cached stale packet does not match the frozen manifest hash")
            write_atomic(attempt_dir / "packet_initial.md", initial)
            final = initial
            packet = {**read_json(issue_dir / "packet.json"), "text": initial.decode("utf-8")}
            packet_info.update(initial_sha256=sha256_bytes(initial), initial_bytes=len(initial), exposed_claim_ids=[c for e in packet["documents"] for c in e["claim_ids"]])
            ledger.event("claim_exposure", stage="context", role="harness", observation=f"{len(packet_info['exposed_claim_ids'])} claims in {len(packet['documents'])} routed documents", packet_sha256=packet_info["initial_sha256"])
            if arm == "selective_stale":
                claims = {c["claim_id"]: c for c in read_json(issue_dir / "claims_exposed.json")}
                check_limits = manifest["checker"]
                check_report = checker.selective_packet(packet, claims, workspace, min(int(check_limits["max_checks"]), actions_left), min(float(check_limits["time_s"]), max(remaining(), 0)))
                for decision in check_report["decisions"]:
                    ledger.event("check", stage="verify", role="checker", claim_id=decision["claim_id"], path=decision["path"], symbol=decision["symbol"], check_status=decision["status"], policy_action=decision["policy_action"], observation=decision["evidence"], old_text=decision["old_text"], new_text=decision.get("repair_text"), check_ms=decision["check_ms"], counters={"actions": 1, "checks": 1})
                for item in check_report["skipped"]:
                    ledger.event("check", stage="verify", role="checker", claim_id=item["claim_id"], check_status="skipped", policy_action="unchecked", observation=item["reason"])
                counters["checks"] = check_report["checks"]
                actions_left -= check_report["checks"]
                final = check_report["text"].encode("utf-8")
                write_json(attempt_dir / "checks.json", {k: v for k, v in check_report.items() if k != "text"})
            write_atomic(attempt_dir / "packet_final.md", final)
            packet_info.update(final_sha256=sha256_bytes(final), final_bytes=len(final))
            context_paths = [str(attempt_dir / "packet_final.md")]
        for role, text in PROMPTS.items():
            write_atomic(attempt_dir / f"{role}.prompt.txt", text)

        roles: dict[str, dict] = {}
        handoff_path = attempt_dir / "handoff.md"
        handoff_truncated = False
        for role in ("planner", "implementer"):
            cap = min(int(manifest["planner"]["max_actions"]), actions_left) if role == "planner" else actions_left
            time_cap = min(float(manifest["planner"]["time_s"]), remaining()) if role == "planner" else remaining()
            if time_cap <= 1 or cap <= 0:
                roles[role] = {"status": "budget_exhausted", "exit_reason": "no_budget_left", "actions": 0, "usage": {}, "backend": {}, "is_live": None, "wall_ms": 0}
                ledger.event("role_skipped", stage=role, role=role, observation="no time or actions left in the shared allowance")
                continue
            request = {
                "schema_version": 1, "run_id": f"{attempt_id}:{role}", "workspace": str(workspace), "issue_text": issue_text, "role": role,
                "prompt_path": str(attempt_dir / f"{role}.prompt.txt"), "context_paths": context_paths,
                "handoff_path": str(handoff_path) if role == "implementer" else None,
                "limits": {"time_s": round(time_cap, 1), "max_actions": cap}, "read_only": role == "planner", "seed": seed,
                "out": {"events": str(attempt_dir / f"{role}.events.jsonl"), "result": str(attempt_dir / f"{role}.result.json")},
                "backend": backend.get("settings", {}),
            }
            result = launch_backend(backend, request, attempt_dir, time_cap)
            roles[role] = result
            for event in read_jsonl(attempt_dir / f"{role}.events.jsonl"):
                if event.get("type") == "tool_call":
                    ledger.event("tool_call", stage=role, role=role, tool=event.get("tool"), path=event.get("path"), range=event.get("range"), ok=event.get("ok"), args=event.get("args"), observation=event.get("result"), agent_t_ms=event.get("t_ms"), counters={"actions": 1})
                elif event.get("type") == "refused":
                    ledger.event("refused", stage=role, role=role, tool=event.get("tool"), observation=event.get("reason"))
                elif event.get("type") == "terminal":
                    ledger.event("role_terminal", stage=role, role=role, observation=event.get("answer"), status=event.get("status"), exit_reason=event.get("exit_reason"))
            used = int(result.get("actions") or 0)
            counters[f"{role}_actions"] = used
            actions_left -= used
            if role == "planner":
                note = (result.get("final_answer") or "").encode("utf-8")
                cap_bytes = int(manifest["planner"]["handoff_bytes"])
                handoff_truncated = len(note) > cap_bytes
                write_atomic(handoff_path, note[:cap_bytes].decode("utf-8", errors="ignore"))
                ledger.event("handoff", stage="planner", role="planner", observation=excerpt(note.decode("utf-8", errors="ignore")), handoff_bytes=min(len(note), cap_bytes), truncated=handoff_truncated)

        solve_ms = int((time.monotonic() - budget_started) * 1000)
        patch = workspace_diff(workspace)
        patch_raw = patch.encode("utf-8", errors="surrogateescape")
        write_atomic(attempt_dir / "patch.diff", patch_raw)
        apply_check = {"ok": None, "detail": "no patch"}
        if patch.strip():
            clean = work_root / attempt_id / "apply_check"
            extract_tar(Path(issue["snapshot_t"]), clean)
            init_snapshot_repo(clean, "pre-fix snapshot")
            applied = run(["git", "-c", "core.autocrlf=false", "apply", "--check", str(attempt_dir / "patch.diff")], cwd=clean)
            apply_check = {"ok": applied.returncode == 0, "detail": applied.stderr.strip()[:300] or "applies cleanly to a fresh pre-fix snapshot"}
            shutil.rmtree(clean, ignore_errors=True)

    implementer = roles["implementer"]
    planner = roles["planner"]
    if "error" in (planner.get("status"), implementer.get("status")):
        status = "infra_error"
    elif implementer.get("status") == "budget_exhausted" or planner.get("status") == "budget_exhausted" and not patch.strip():
        status = "budget_exhausted"
    elif implementer.get("status") == "action_limit":
        status = "action_limit"
    else:
        status = "completed_patch" if patch.strip() else "completed_empty"
    ledger.event("patch", stage="collect", role="harness", observation=f"{len(patch_raw)} bytes; local apply check: {apply_check['detail']}", patch_sha256=sha256_bytes(patch_raw))
    totals = ledger.close(status=status, counters=counters, solve_ms=solve_ms)

    live = [r.get("is_live") for r in (planner, implementer)]
    usage = {}
    for field in ("input_tokens", "output_tokens", "cache_read_tokens"):
        values = [r.get("usage", {}).get(field) for r in (planner, implementer)]
        usage[field] = sum(v for v in values if isinstance(v, int)) if any(isinstance(v, int) for v in values) else None
    usage["source"] = implementer.get("usage", {}).get("source") or planner.get("usage", {}).get("source")
    summary = {
        "attempt_id": attempt_id, "key": key, "instance_id": issue["instance_id"], "arm": arm, "status": status, "finished_at": now_iso(),
        "is_live": bool(live) and all(v is True for v in live),
        "backend": {"name": backend.get("name"), **(implementer.get("backend") or planner.get("backend") or {})},
        "capabilities": implementer.get("capabilities") or planner.get("capabilities") or {},
        "workspace_tree_sha256": base_tree, "generated_documents_in_workspace": 0,
        "packet": packet_info, "checks": {k: v for k, v in (check_report or {}).items() if k != "text"} or None,
        "handoff": {"bytes": handoff_path.stat().st_size if handoff_path.is_file() else 0, "truncated": handoff_truncated, "byte_cap": manifest["planner"]["handoff_bytes"]},
        "roles": {name: {k: r.get(k) for k in ("status", "exit_reason", "error", "actions", "refused_after_limit", "elapsed_ms", "wall_ms", "exit_code", "usage")} for name, r in roles.items()},
        "counters": counters, "actions_used": int(limits["max_actions"]) - actions_left, "limits": limits,
        "timing": {"solve_ms": solve_ms, "over_deadline": solve_ms > float(limits["time_s"]) * 1000 + 20000},
        "usage": usage, "resources": sampler.summary(),
        "patch": {"file": "patch.diff", "bytes": len(patch_raw), "sha256": sha256_bytes(patch_raw), "generation_status": "patch" if patch.strip() else "empty", "local_apply_check": apply_check, "human_edited": False},
        "trace": {"ledger": "ledger.jsonl", **totals},
    }
    write_json(attempt_dir / "summary.json", summary)
    state.update(status=status, finished_at=summary["finished_at"])
    write_json(attempt_dir / "state.json", state)
    shutil.rmtree(work_root / attempt_id, ignore_errors=True)
    return summary

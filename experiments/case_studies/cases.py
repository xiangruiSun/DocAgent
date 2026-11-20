#!/usr/bin/env python3
"""Collect and replay DocAgent staleness cases (Task 1).

    python cases.py validate --manifest cases.json
    python cases.py smoke    --backend fake
    python cases.py run      --case C02 --arm both --backend-config backend.json --out runs
    python cases.py replay   --case C02 --runs runs --offline
    python cases.py report   --runs runs --out reports

Standard library and Git only. No SWE-bench, no import of the benchmark
package. Reports are rebuilt from saved observations; `replay` and `report`
never call a model. The claim verifier in this file is EXPERIMENTAL and
case-only: the released DocAgent helper contributes just its file-level
change signal, which is recorded separately.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
EXPERIMENTS = HERE.parent
HELPER = EXPERIMENTS.parent / "skills" / "docagent" / "scripts" / "docagent.py"
VERIFIER = "experimental-case-verifier-1"
EXCERPT = 512
LEDGER_CAP = 64 * 1024
RESERVE = 3072
CATEGORIES = {"moved_owner", "interface_drift", "obsolete_test", "harmless_change", "benchmark_pilot"}
CHANGE_ORIGINS = {"natural_commit", "injected_fixture"}
NOTE_ORIGINS = {"historical_document", "snapshot_generated", "researcher_authored"}
TASK_KINDS = {"localize", "patch"}
ARMS = ("blind", "checked")
PROMPT = (
    "You are working on a task in a code repository. Use the tools to inspect the source. "
    "A stored repository note may be included; it can be outdated, and the source is the authority. "
    "If the task asks for a change, make the smallest edit with replace_in_file. "
    "Finish by calling finish with your answer: name the file and symbol that owns the behaviour, or summarise your change.\n"
)


class CaseError(RuntimeError):
    pass


def now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def sha(data: bytes | str) -> str:
    return hashlib.sha256(data.encode("utf-8") if isinstance(data, str) else data).hexdigest()


def cut(value, limit: int = EXCERPT) -> str:
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
    raw = text.encode("utf-8")
    return text if len(raw) <= limit else raw[: limit - 3].decode("utf-8", errors="ignore") + "…"


def write(path: Path, data: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp")
    with open(temp, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(data)
    os.replace(temp, path)


def write_json(path: Path, value) -> None:
    write(path, json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n")


def read_json(path: Path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()] if Path(path).is_file() else []


def sh(argv: list[str], cwd: Path | None = None, timeout: float | None = None, check: bool = False, env: dict | None = None) -> subprocess.CompletedProcess:
    result = subprocess.run(argv, cwd=cwd, timeout=timeout, env=env, text=True, encoding="utf-8", errors="replace", stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if check and result.returncode != 0:
        raise CaseError(f"command failed ({result.returncode}): {' '.join(argv[:5])}: {result.stderr.strip()[-400:]}")
    return result


def git(root: Path, *args: str, check: bool = True) -> str:
    return sh(["git", "-c", "core.autocrlf=false", *args], cwd=root, check=check).stdout.strip()


def expand(argv: list[str]) -> list[str]:
    return [part.replace("{python}", sys.executable).replace("{experiments}", str(EXPERIMENTS)) for part in argv]


# ---------------------------------------------------------------- manifest

def validate_manifest(manifest: dict) -> list[str]:
    problems = []
    if manifest.get("schema_version") != 1:
        problems.append("schema_version must be 1")
    seen = set()
    for index, case in enumerate(manifest.get("cases", [])):
        label = case.get("case_id", f"#{index}")
        if label in seen:
            problems.append(f"{label}: duplicate case_id")
        seen.add(label)
        for field in ("case_id", "category", "project_url", "repo", "s", "t", "claim", "change_origin", "note_origin", "task", "oracle"):
            if field not in case:
                problems.append(f"{label}: missing {field}")
        if case.get("category") not in CATEGORIES:
            problems.append(f"{label}: category must be one of {sorted(CATEGORIES)}")
        if case.get("change_origin") not in CHANGE_ORIGINS:
            problems.append(f"{label}: change_origin must be one of {sorted(CHANGE_ORIGINS)}")
        if case.get("note_origin") not in NOTE_ORIGINS:
            problems.append(f"{label}: note_origin must be one of {sorted(NOTE_ORIGINS)}")
        claim = case.get("claim", {})
        for field in ("claim_id", "statement", "covered_path", "predicate"):
            if field not in claim:
                problems.append(f"{label}: claim missing {field}")
        if case.get("task", {}).get("kind") not in TASK_KINDS:
            problems.append(f"{label}: task.kind must be one of {sorted(TASK_KINDS)}")
        if "expected" in json.dumps(case.get("task", {})) or "evaluator_only" in case:
            problems.append(f"{label}: evaluator-only answers belong in the separate evaluator file, not in the manifest")
        if case.get("task", {}).get("kind") == "patch" and not isinstance(case.get("oracle", {}).get("command"), list):
            problems.append(f"{label}: oracle.command must be an argument array")
    return problems


def load_manifest(path: Path) -> tuple[dict, dict]:
    manifest = read_json(path)
    problems = validate_manifest(manifest)
    if problems:
        raise CaseError("manifest invalid:\n  " + "\n  ".join(problems))
    evaluator_path = path.with_name(path.stem + ".evaluator.json")
    return manifest, (read_json(evaluator_path) if evaluator_path.is_file() else {})


def find_case(manifest: dict, case_id: str) -> dict:
    for case in manifest["cases"]:
        if case["case_id"] == case_id:
            return case
    raise CaseError(f"unknown case {case_id}")


def source_repo(case: dict, cache: Path) -> Path:
    """Evaluator-side repository with both revisions. Agents never see it."""
    repo = case["repo"]
    target = cache / case["case_id"]
    if repo["kind"] == "fixture":
        if not (target / ".git").is_dir():
            sh([sys.executable, str(HERE / repo["script"]), str(target)], check=True)
    elif repo["kind"] == "git":
        if not (target / "HEAD").is_file() and not (target / ".git").is_dir():
            sh(["git", "clone", "--quiet", "--filter=blob:none", repo["url"], str(target)], check=True, timeout=1800)
    elif repo["kind"] == "bundle":
        return target
    else:
        raise CaseError(f"{case['case_id']}: unknown repo kind {repo['kind']}")
    for label in ("s", "t"):
        if sh(["git", "cat-file", "-e", case[label] + "^{commit}"], cwd=target).returncode != 0:
            raise CaseError(f"{case['case_id']}: revision {label}={case[label]} not found; the manifest must record the exact SHA")
    if sh(["git", "merge-base", "--is-ancestor", case["s"], case["t"]], cwd=target).returncode != 0:
        raise CaseError(f"{case['case_id']}: s is not an ancestor of t")
    return target


def show(repo: Path, revision: str, path: str) -> str | None:
    result = sh(["git", "show", f"{revision}:{path}"], cwd=repo)
    return result.stdout if result.returncode == 0 else None


# ---------------------------------------------------------------- experimental verifier

def _functions(tree: ast.AST) -> dict:
    found: dict[str, list] = {}
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            found.setdefault(node.name, []).append(node)
        if isinstance(node, ast.ClassDef):
            for child in node.body:
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    found.setdefault(f"{node.name}.{child.name}", []).append(child)
    return found


def verify(predicate: dict, source: str | None) -> dict:
    """Check one predicate against one file's text. Returns status, evidence, locator, repair."""
    out = {"status": "unresolved", "evidence": "", "line": None, "repair": None, "verifier": VERIFIER}
    if source is None:
        return {**out, "evidence": "file absent at this revision; absence does not show where the behaviour went"}
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        return {**out, "evidence": f"file does not parse: {exc.msg}"}
    kind = predicate["type"]
    if kind == "signature_has_param":
        nodes = _functions(tree).get(predicate["qualname"], [])
        if len(nodes) != 1 or isinstance(nodes[0], ast.ClassDef):
            return {**out, "evidence": f"{len(nodes)} definitions of {predicate['qualname']}; an AST signature proves only one call shape"}
        node = nodes[0]
        names = [a.arg for a in node.args.posonlyargs + node.args.args + node.args.kwonlyargs]
        signature = f"{predicate['qualname']}({ast.unparse(node.args)})"
        if predicate["param"] in names:
            return {**out, "status": "supported", "line": node.lineno, "evidence": f"line {node.lineno}: def {signature}"}
        if node.args.kwarg:
            return {**out, "line": node.lineno, "evidence": f"line {node.lineno}: def {signature}; **{node.args.kwarg.arg} may still accept a deprecated alias"}
        return {**out, "status": "contradicted", "line": node.lineno, "evidence": f"line {node.lineno}: def {signature}", "repair": f"`{predicate['qualname']}` no longer takes `{predicate['param']}`; its current signature is `{signature}`."}
    if kind == "symbol_owner":
        name = predicate["qualname"]
        for node in tree.body:
            if isinstance(node, ast.ImportFrom) and any((alias.asname or alias.name) == name for alias in node.names):
                origin = "." * node.level + (node.module or "")
                return {**out, "status": "contradicted", "line": node.lineno, "evidence": f"line {node.lineno}: from {origin} import {name} (re-export)", "repair": f"`{name}` is now imported from `{origin}`; this file only re-exports it."}
        nodes = _functions(tree).get(name, [])
        if len(nodes) != 1:
            return {**out, "evidence": f"{len(nodes)} definitions of {name} in this file"}
        node = nodes[0]
        body = [n for n in getattr(node, "body", []) if not (isinstance(n, ast.Expr) and isinstance(n.value, ast.Constant))]
        if len(body) == 1 and isinstance(body[0], ast.Return) and isinstance(body[0].value, ast.Call):
            return {**out, "status": "contradicted", "line": node.lineno, "evidence": f"line {node.lineno}: {name} only delegates to {ast.unparse(body[0].value.func)}", "repair": f"`{name}` here is a wrapper that delegates to `{ast.unparse(body[0].value.func)}`."}
        return {**out, "status": "supported", "line": node.lineno, "evidence": f"line {node.lineno}: {name} is implemented here ({len(body)} statements)"}
    if kind == "literal_equals":
        nodes = [n for n in tree.body if isinstance(n, ast.Assign) and len(n.targets) == 1 and isinstance(n.targets[0], ast.Name) and n.targets[0].id == predicate["name"]]
        if len(nodes) != 1 or not isinstance(nodes[0].value, ast.Constant):
            return {**out, "evidence": f"{predicate['name']} has {len(nodes)} module-level assignment(s) or a computed value"}
        value = ast.unparse(nodes[0].value)
        if value == predicate["value"]:
            return {**out, "status": "supported", "line": nodes[0].lineno, "evidence": f"line {nodes[0].lineno}: {predicate['name']} = {value}"}
        return {**out, "status": "contradicted", "line": nodes[0].lineno, "evidence": f"line {nodes[0].lineno}: {predicate['name']} = {value}", "repair": f"`{predicate['name']}` is now `{value}`."}
    return {**out, "evidence": f"unsupported predicate type {kind}"}


def released_gate(repo: Path, case: dict) -> dict:
    """The released helper's file-level signal for s..t, recorded apart from the experimental verifier."""
    try:
        spec = importlib.util.spec_from_file_location("docagent_released_helper_cases", HELPER)
        helper = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = helper
        spec.loader.exec_module(helper)
        with tempfile.TemporaryDirectory(prefix="gate-") as temp:
            sh(["git", "clone", "--quiet", str(repo), temp], check=True)
            git(Path(temp), "checkout", "--quiet", case["t"])
            changed = sorted(helper.diff_since(Path(temp).resolve(), case["s"]))
        covered = [f for f in changed if helper.match_any(f, [case["claim"]["covered_path"]])]
        return {"source": "released docagent.py diff_since + match_any", "helper_sha256": sha(HELPER.read_bytes()), "covered_file_changed": bool(covered), "changed_covered_files": covered, "files_changed_s_to_t": len(changed)}
    except Exception as exc:  # the gate is informative; a failure here must not hide the case
        return {"source": "released docagent.py", "covered_file_changed": None, "error": str(exc)[:200]}


def evidence_for(case: dict, repo: Path) -> dict:
    claim = case["claim"]
    out = {}
    for label in ("s", "t"):
        result = verify(claim["predicate"], show(repo, case[label], claim["covered_path"]))
        out[label] = {"revision": case[label], "path": claim["covered_path"], **result}
    return out


def render_packets(case: dict, evidence: dict) -> dict:
    """Blind reuse is the old note as written. Checked reuse starts from those bytes and applies the policy."""
    claim = case["claim"]
    blind = f"# Stored repository note\n\nRecorded at revision {case['s'][:12]}. The repository may have changed since.\n\n- [{claim['claim_id']}] {claim['statement']}\n  source: `{claim['covered_path']}`\n"
    check = evidence["t"]
    if check["status"] == "supported":
        action, line = "reuse", f"- [{claim['claim_id']}] {claim['statement']}  [checked against the current source: supported]"
    elif check["status"] == "contradicted" and check.get("repair"):
        action, line = "repair", f"- [{claim['claim_id']}] {check['repair']}  [repaired from the current source]"
    else:
        action, line = "omit", f"- [{claim['claim_id']}] [omitted: the stored claim could not be confirmed against the current source]"
    checked = blind.replace(f"- [{claim['claim_id']}] {claim['statement']}", line)
    return {"blind": blind, "checked": checked, "policy_action": action, "initial_sha256": sha(blind), "final_sha256": {"blind": sha(blind), "checked": sha(checked)}}


# ---------------------------------------------------------------- ledger

class Ledger:
    FIELDS = ("role", "stage", "event_type", "claim_id", "path", "symbol", "action", "evidence", "check_status", "policy_action", "elapsed_ms")

    def __init__(self, path: Path, run_id: str):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.handle = open(path, "w", encoding="utf-8", newline="\n")
        self.run_id, self.seq, self.bytes, self.dropped, self.started = run_id, 0, 0, 0, time.monotonic()
        self.counts: dict[str, int] = {}

    def event(self, event_type: str, **fields) -> int:
        self.seq += 1
        self.counts[event_type] = self.counts.get(event_type, 0) + 1
        row = {"run_id": self.run_id, "seq": self.seq, **{k: None for k in self.FIELDS}, "event_type": event_type, "elapsed_ms": int((time.monotonic() - self.started) * 1000)}
        row.update({k: cut(v) if isinstance(v, str) else v for k, v in fields.items()})
        line = json.dumps(row, ensure_ascii=False) + "\n"
        if self.bytes + len(line.encode("utf-8")) > LEDGER_CAP - RESERVE:
            self.dropped += 1
            return self.seq
        self.handle.write(line)
        self.bytes += len(line.encode("utf-8"))
        return self.seq

    def close(self, **summary) -> dict:
        totals = {"events_total": self.seq, "events_truncated": self.dropped, "truncated": self.dropped > 0, "counts": self.counts}
        self.handle.write(json.dumps({"run_id": self.run_id, "seq": self.seq + 1, "event_type": "terminal_summary", **totals, **summary}, ensure_ascii=False) + "\n")
        self.handle.close()
        return totals


# ---------------------------------------------------------------- running

def export_tree(repo: Path, revision: str, target: Path) -> None:
    """A clean snapshot with one commit: no later history, no notes, no oracle."""
    target.mkdir(parents=True)
    listing = git(repo, "ls-tree", "-r", "--name-only", revision).splitlines()
    for name in listing:
        data = subprocess.run(["git", "show", f"{revision}:{name}"], cwd=repo, stdout=subprocess.PIPE, check=True).stdout
        (target / name).parent.mkdir(parents=True, exist_ok=True)
        (target / name).write_bytes(data)
    git(target, "init", "-q", "-b", "main")
    git(target, "config", "user.email", "cases@docagent.local")
    git(target, "config", "user.name", "DocAgent Cases")
    git(target, "add", "-A")
    git(target, "commit", "-q", "--allow-empty", "-m", "snapshot")


def run_oracle(case: dict, expected: dict, repo: Path, patch: str, answer: str, first_path: str | None) -> dict:
    """Local targeted oracle, run after the agent has exited, in a tree the agent never saw."""
    kind = case["task"]["kind"]
    if kind == "localize":
        wanted = expected.get("answer_any_of") or []
        if not wanted:
            return {"kind": "localize", "verdict": "ungraded", "detail": "no evaluator-only expected answer recorded", "official": False}
        hit = [w for w in wanted if w in (answer or "")]
        return {"kind": "localize", "verdict": "pass" if hit else "fail", "detail": f"answer names {hit}" if hit else "answer names none of the expected owners", "first_inspected_path": first_path, "first_inspected_is_owner": first_path in wanted if first_path else None, "official": False}
    if not patch.strip():
        return {"kind": "patch", "verdict": "fail", "detail": "empty patch graded as a failure", "exit_code": None, "official": False}
    with tempfile.TemporaryDirectory(prefix="oracle-") as temp:
        tree = Path(temp) / "tree"
        export_tree(repo, case["t"], tree)
        patch_file = Path(temp) / "patch.diff"
        patch_file.write_bytes(patch if isinstance(patch, bytes) else patch.encode("utf-8"))
        applied = sh(["git", "-c", "core.autocrlf=false", "apply", str(patch_file)], cwd=tree)
        if applied.returncode != 0:
            return {"kind": "patch", "verdict": "fail", "detail": "patch does not apply: " + cut(applied.stderr, 200), "exit_code": None, "official": False}
        try:
            result = sh(expand(case["oracle"]["command"]), cwd=tree, timeout=float(case["oracle"].get("timeout_s", 60)))
        except subprocess.TimeoutExpired:
            return {"kind": "patch", "verdict": "budget_exhausted", "detail": "oracle timed out", "exit_code": None, "official": False}
        except OSError as exc:
            return {"kind": "patch", "verdict": "infrastructure_missing", "detail": str(exc)[:200], "exit_code": None, "official": False}
    ok = result.returncode == case["oracle"].get("expect_exit_code", 0)
    return {"kind": "patch", "verdict": "pass" if ok else "fail", "exit_code": result.returncode, "stdout": cut(result.stdout, 300), "stderr": cut(result.stderr, 300), "detail": "oracle command exit code", "official": False}


def run_arm(case: dict, expected: dict, arm: str, order: int, backend: dict, repo: Path, evidence: dict, packets: dict, gate: dict, runs: Path, limits: dict) -> dict:
    stamp = time.strftime("%Y%m%dT%H%M%S", time.gmtime())
    attempts = runs / case["case_id"] / "attempts"
    number = len(list(attempts.glob(f"{case['case_id']}-{arm}-*"))) + 1 if attempts.is_dir() else 1
    attempt_id = f"{case['case_id']}-{arm}-{stamp}-{number:02d}"
    attempt = attempts / attempt_id
    attempt.mkdir(parents=True, exist_ok=False)
    ledger = Ledger(attempt / "ledger.jsonl", attempt_id)
    claim = case["claim"]
    write(attempt / "packet_initial.md", packets["blind"])
    write(attempt / "packet_final.md", packets[arm])
    write(attempt / "prompt.txt", PROMPT)
    ledger.event("claim_exposure", role="harness", stage="context", claim_id=claim["claim_id"], path=claim["covered_path"], action="inject stored note", evidence=claim["statement"])
    actions_left = int(limits["max_actions"])
    if arm == "checked":
        ledger.event("gate", role="released_helper", stage="verify", claim_id=claim["claim_id"], path=claim["covered_path"], action="file-level change signal s..t", evidence=json.dumps({k: gate.get(k) for k in ("covered_file_changed", "changed_covered_files")}))
        ledger.event("check", role="experimental_verifier", stage="verify", claim_id=claim["claim_id"], path=claim["covered_path"], action="check predicate against current source", evidence=evidence["t"]["evidence"], check_status=evidence["t"]["status"], policy_action=packets["policy_action"], old_text=claim["statement"], new_text=evidence["t"].get("repair"))
        actions_left -= 1
    work = Path(tempfile.mkdtemp(prefix="case-ws-"))
    started = time.monotonic()
    try:
        export_tree(repo, case["t"], work / "ws")
        request = {
            "schema_version": 1, "run_id": attempt_id, "workspace": str(work / "ws"), "issue_text": case["task"]["prompt"], "role": "solver", "prompt_path": str(attempt / "prompt.txt"),
            "context_paths": [str(attempt / "packet_final.md")], "handoff_path": None, "limits": {"time_s": limits["time_s"], "max_actions": actions_left}, "read_only": case["task"]["kind"] == "localize",
            "out": {"events": str(attempt / "agent.events.jsonl"), "result": str(attempt / "agent.result.json")}, "backend": backend.get("settings", {}),
        }
        write_json(attempt / "request.json", request)
        infrastructure = None
        try:
            process = subprocess.run(expand(backend["command"]) + ["--request", str(attempt / "request.json")], timeout=float(limits["time_s"]) + 30, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
            result = read_json(attempt / "agent.result.json") if (attempt / "agent.result.json").is_file() else {"status": "error", "exit_reason": "no_result_file", "error": cut(process.stderr.decode("utf-8", "replace"), 200)}
        except subprocess.TimeoutExpired:
            result = {"status": "budget_exhausted", "exit_reason": "killed_at_deadline"}
        except OSError as exc:
            result, infrastructure = {"status": "error", "exit_reason": "backend_not_startable"}, str(exc)[:200]
        first_path = None
        for event in read_jsonl(attempt / "agent.events.jsonl"):
            if event.get("type") == "tool_call":
                first_path = first_path or event.get("path")
                kind = "source_edit" if event.get("tool") == "replace_in_file" else "source_read"
                ledger.event(kind, role="agent", stage="solve", path=event.get("path"), action=f"{event.get('tool')} {event.get('args') or ''}", evidence=event.get("result"), ok=event.get("ok"))
        answer = result.get("final_answer") or ""
        ledger.event("terminal_answer", role="agent", stage="solve", action=result.get("exit_reason"), evidence=answer)
        git(work / "ws", "add", "-A")
        raw = subprocess.run(["git", "-c", "core.autocrlf=false", "diff", "--cached", "--no-color", "--binary", "HEAD"], cwd=work / "ws", stdout=subprocess.PIPE, check=True).stdout
        (attempt / "patch.diff").write_bytes(raw)
        patch = raw.decode("utf-8", errors="replace")
        elapsed = int((time.monotonic() - started) * 1000)
        if result.get("status") == "error":
            oracle = {"kind": case["task"]["kind"], "verdict": "infrastructure_missing", "detail": infrastructure or result.get("error") or result.get("exit_reason"), "official": False}
        else:
            oracle = run_oracle(case, expected, repo, patch, answer, first_path)
            if result.get("status") == "budget_exhausted" and oracle["verdict"] != "pass":
                oracle["verdict"] = "budget_exhausted"
        ledger.event("oracle_outcome", role="oracle", stage="grade", action=oracle["kind"], evidence=oracle.get("detail"), check_status=oracle["verdict"])
    finally:
        shutil.rmtree(work, ignore_errors=True)
    totals = ledger.close(status=result.get("status"))
    summary = {
        "attempt_id": attempt_id, "case_id": case["case_id"], "arm": arm, "order": order, "finished_at": now(), "status": result.get("status"), "exit_reason": result.get("exit_reason"),
        "is_live": result.get("is_live") is True, "backend": {"name": backend.get("name"), **(result.get("backend") or {})}, "capabilities": result.get("capabilities") or {},
        "packet_initial_sha256": packets["initial_sha256"], "packet_final_sha256": packets["final_sha256"][arm],
        "check": {"status": evidence["t"]["status"], "policy_action": packets["policy_action"], "evidence": evidence["t"]["evidence"], "verifier": VERIFIER} if arm == "checked" else None,
        "final_answer": cut(answer), "first_inspected_path": first_path, "actions": result.get("actions"), "limits": limits, "patch_bytes": len(patch.encode("utf-8")), "oracle": oracle,
        "timing": {"wall_ms": elapsed, "agent_ms": result.get("elapsed_ms")}, "usage": result.get("usage") or {}, "resources": {"peak_memory_mb": None, "note": "unavailable: no per-process sampler in the standard library"},
        "artifact_bytes": sum(p.stat().st_size for p in attempt.iterdir() if p.is_file()), "ledger": totals,
    }
    write_json(attempt / "summary.json", summary)
    return summary


def write_case_bundle(case: dict, repo: Path, runs: Path) -> tuple[dict, dict, dict]:
    evidence = evidence_for(case, repo)
    gate = released_gate(repo, case)
    packets = render_packets(case, evidence)
    bundle = {
        "schema_version": 1, "case_id": case["case_id"], "category": case["category"], "project_url": case["project_url"], "s": case["s"], "t": case["t"], "claim": case["claim"],
        "change_origin": case["change_origin"], "note_origin": case["note_origin"], "task": case["task"], "evidence": evidence, "released_gate": gate,
        "experimental_verifier": VERIFIER, "human_review": case.get("human_review", {"status": "pending", "note": "a second member must label t without seeing the first verdict"}),
        "source": "cases.py run", "written_at": now(),
    }
    write_json(runs / case["case_id"] / "case.json", bundle)
    return evidence, gate, packets


def cmd_run(args) -> int:
    manifest, evaluator = load_manifest(Path(args.manifest))
    backend = read_json(Path(args.backend_config)) if args.backend_config != "fake" else read_json(EXPERIMENTS / "backends" / "backend.fake.json")
    case = find_case(manifest, args.case)
    runs = Path(args.out).resolve()
    repo = source_repo(case, Path(args.cache).resolve())
    evidence, gate, packets = write_case_bundle(case, repo, runs)
    if evidence["s"]["status"] != "supported":
        raise CaseError(f"{case['case_id']}: the stored claim is not supported at s ({evidence['s']['evidence']}); it cannot be a staleness case")
    limits = {"time_s": args.time_s, "max_actions": args.max_actions}
    index = [c["case_id"] for c in manifest["cases"]].index(case["case_id"])
    arms = list(ARMS) if args.arm == "both" else [args.arm]
    if args.arm == "both" and index % 2:
        arms.reverse()
    for order, arm in enumerate(arms, 1):
        summary = run_arm(case, evaluator.get(case["case_id"], {}), arm, order, backend, repo, evidence, packets, gate, runs, limits)
        print(json.dumps({"attempt_id": summary["attempt_id"], "arm": arm, "status": summary["status"], "live": summary["is_live"], "oracle": summary["oracle"]["verdict"]}))
    return 0


# ---------------------------------------------------------------- replay and report

def latest_attempts(case_dir: Path) -> dict:
    """Newest attempt per arm; older attempts are kept on disk and listed in the report."""
    chosen, every = {}, []
    for path in sorted((case_dir / "attempts").glob("*/summary.json")) if (case_dir / "attempts").is_dir() else []:
        summary = read_json(path)
        summary["_dir"] = path.parent
        every.append(summary["attempt_id"])
        chosen[summary["arm"]] = summary
    return {"chosen": chosen, "all": every}


def render_case(case_dir: Path) -> str:
    bundle = read_json(case_dir / "case.json")
    found = latest_attempts(case_dir)
    attempts = found["chosen"]
    claim, evidence, gate = bundle["claim"], bundle["evidence"], bundle.get("released_gate", {})
    lines = [f"# Case {bundle['case_id']}: {bundle['category']}", "", f"Project: {bundle['project_url']}  ", f"Old revision s: `{bundle['s']}`  ", f"Current revision t: `{bundle['t']}`  ",
             f"Provenance: change_origin = **{bundle['change_origin']}**, note_origin = **{bundle['note_origin']}**", ""]
    if bundle["change_origin"] == "injected_fixture" or bundle["note_origin"] != "historical_document":
        lines += ["> This is not an observed incident of stale documentation: the change, the note, or both were constructed.", ""]
    lines += ["## The stored claim", "", f"`{claim['claim_id']}`: {claim['statement']} (source `{claim['covered_path']}`)", "", "## What changed", "",
              "| Revision | Verdict | Evidence |", "|---|---|---|"]
    for label in ("s", "t"):
        item = evidence.get(label) or {}
        lines.append(f"| {label} `{str(item.get('revision', ''))[:12]}` | {item.get('status')} | `{item.get('path')}` {item.get('evidence', '')} |")
    lines += ["", "Who established what:", "",
              f"- Released DocAgent helper (file-level only): covered file changed between s and t = **{gate.get('covered_file_changed')}** {gate.get('changed_covered_files') or ''}. This is a reason to inspect the claim, not a verdict on it.",
              f"- Experimental verifier (`{bundle.get('experimental_verifier')}`): the verdicts in the table above.",
              f"- Human review: {json.dumps(bundle.get('human_review'))}", ""]
    if not attempts:
        lines += ["## Sessions", "", "No session is recorded for this case. A scripted replay cannot fill a missing session.", ""]
        return "\n".join(lines)
    lines += ["## Sessions", "", "| Arm | Attempt | Live agent | Backend / model | Initial packet | Final packet | Terminal state | Oracle |", "|---|---|---|---|---|---|---|---|"]
    for arm, summary in attempts.items():
        backend = summary.get("backend", {})
        lines.append(f"| {arm} | `{summary['attempt_id']}` | {'yes' if summary['is_live'] else '**no**'} | {backend.get('name')} / {backend.get('model')} | `{str(summary.get('packet_initial_sha256'))[:12]}` | `{str(summary.get('packet_final_sha256'))[:12]}` | {summary['status']} | {summary['oracle']['verdict']}{' (official SWE-bench harness)' if summary['oracle'].get('official') else ''} |")
    not_live = [a for a, s in attempts.items() if not s["is_live"]]
    if not_live:
        lines += ["", f"> Sessions {', '.join(not_live)} came from a fake or replayed backend. They test the recorder and contribute **zero agent observations**."]
    missing = [a for a in ARMS if a not in attempts]
    if missing:
        lines += ["", f"> Missing sessions: {', '.join(missing)}."]
    hashes = {s.get("packet_initial_sha256") for a, s in attempts.items() if a in ARMS}
    if len(hashes) > 1:
        lines += ["", "> WARNING: the blind and checked arms did not start from the same packet bytes."]
    ledgers = {arm: read_jsonl(summary["_dir"] / "ledger.jsonl") for arm, summary in attempts.items()}
    lines += ["", "## Side by side", ""]
    order = [a for a in ("source_only", "blind", "checked") if a in ledgers]
    acts = {arm: [e for e in ledgers[arm] if e.get("event_type") in {"source_read", "source_edit", "check", "gate", "terminal_answer", "oracle_outcome", "handoff"}] for arm in order}
    lines += ["| Step | " + " | ".join(order) + " |", "|---|" + "---|" * len(order)]
    for step in range(max((len(v) for v in acts.values()), default=0)):
        cells = []
        for arm in order:
            if step < len(acts[arm]):
                e = acts[arm][step]
                detail = e.get("path") or e.get("check_status") or ""
                cells.append(f"#{e['seq']} {e['event_type']} {detail}".strip())
            else:
                cells.append("")
        lines.append(f"| {step + 1} | " + " | ".join(cells) + " |")
    if "blind" in acts and "checked" in acts:
        blind = [(e["event_type"], e.get("path")) for e in acts["blind"] if e["event_type"] in {"source_read", "source_edit"}]
        checked = [(e["event_type"], e.get("path")) for e in acts["checked"] if e["event_type"] in {"source_read", "source_edit"}]
        split = next((i for i, (a, b) in enumerate(zip(blind, checked)) if a != b), None)
        if split is None and len(blind) == len(checked):
            lines += ["", "The agent's source actions were the same in both arms (converged)."]
        else:
            where = split if split is not None else min(len(blind), len(checked))
            lines += ["", f"The arms diverged at agent source action {where + 1}: blind did `{blind[where] if where < len(blind) else 'nothing further'}`, checked did `{checked[where] if where < len(checked) else 'nothing further'}`."]
    lines += ["", "## What each session did and what the oracle found", ""]
    for arm, summary in attempts.items():
        events = ledgers[arm]
        touched = [e["seq"] for e in events if e.get("event_type") in {"source_read", "source_edit"} and e.get("path") == claim["covered_path"]]
        reliance = f"the agent accessed the claimed path `{claim['covered_path']}` at event(s) {touched}; whether it relied on the note is **unknown**" if touched else "no recorded access to the claimed path; reliance is **unknown**"
        terminal = next((e for e in events if e.get("event_type") == "terminal_answer"), {})
        graded = next((e for e in events if e.get("event_type") == "oracle_outcome"), {})
        lines += [f"- **{arm}** (`{summary['attempt_id']}`, ledger `attempts/{summary['attempt_id']}/ledger.jsonl`): {reliance}. Terminal answer at event {terminal.get('seq')}: \"{summary.get('final_answer')}\". Patch: {summary.get('patch_bytes')} bytes. Oracle at event {graded.get('seq')}: **{summary['oracle']['verdict']}** ({summary['oracle'].get('detail')}). Trace truncated: {summary['ledger'].get('truncated')}."]
    lines += ["", f"All attempts on disk for this case: {', '.join(found['all'])}.", "", "A failed patch is not evidence of what the model believed; this report states only recorded actions.", ""]
    return "\n".join(lines)


def cmd_replay(args) -> int:
    if not args.offline:
        raise CaseError("replay rebuilds from saved observations only; pass --offline (live oracle re-execution is the separate --rerun-oracle flag of `run`)")
    case_dir = Path(args.runs).resolve() / args.case
    if not (case_dir / "case.json").is_file():
        raise CaseError(f"no saved case bundle at {case_dir}")
    text = render_case(case_dir)
    target = Path(args.out).resolve() / f"{args.case}.md" if args.out else case_dir / "report.md"
    write(target, text)
    print(json.dumps({"case": args.case, "report": str(target), "sha256": sha(text), "model_calls": 0, "backend_processes_started": 0}))
    return 0


def cmd_report(args) -> int:
    runs, out = Path(args.runs).resolve(), Path(args.out).resolve()
    rows = ["# Case index", "", "Rebuilt from saved observations; no model call.", "", "| Case | Category | change_origin | note_origin | Released helper: covered file changed | Experimental verifier at t | Human review | Live sessions | Missing sessions |", "|---|---|---|---|---|---|---|---|---|"]
    for case_dir in sorted(p.parent for p in runs.glob("*/case.json")):
        bundle = read_json(case_dir / "case.json")
        write(out / f"{bundle['case_id']}.md", render_case(case_dir))
        attempts = latest_attempts(case_dir)["chosen"]
        live = [a for a, s in attempts.items() if s["is_live"]]
        missing = [a for a in ARMS if a not in attempts]
        rows.append(f"| [{bundle['case_id']}]({bundle['case_id']}.md) | {bundle['category']} | {bundle['change_origin']} | {bundle['note_origin']} | {bundle.get('released_gate', {}).get('covered_file_changed')} | {bundle['evidence']['t']['status']} | {bundle.get('human_review', {}).get('status')} | {', '.join(live) or 'none'} | {', '.join(missing) or 'none'} |")
    write(out / "index.md", "\n".join(rows) + "\n")
    print(json.dumps({"index": str(out / "index.md"), "cases": len(rows) - 6, "model_calls": 0}))
    return 0


def cmd_validate(args) -> int:
    manifest, evaluator = load_manifest(Path(args.manifest))
    failures = 0
    for case in manifest["cases"]:
        try:
            repo = source_repo(case, Path(args.cache).resolve())
            evidence = evidence_for(case, repo)
            ok = evidence["s"]["status"] == "supported"
            failures += 0 if ok else 1
            print(f"{'OK  ' if ok else 'FAIL'} {case['case_id']} {case['category']}: s={evidence['s']['status']} t={evidence['t']['status']} change={case['change_origin']} note={case['note_origin']} expected_answer={'recorded' if case['case_id'] in evaluator else 'missing'}")
        except CaseError as exc:
            failures += 1
            print(f"FAIL {case['case_id']}: {exc}")
    print(f"manifest schema valid; {len(manifest['cases']) - failures}/{len(manifest['cases'])} cases have a claim supported at s")
    return 1 if failures else 0


def cmd_smoke(args) -> int:
    base = Path(tempfile.mkdtemp(prefix="cases-smoke-"))
    try:
        manifest_path = HERE / "cases.example.json"
        common = ["--manifest", str(manifest_path), "--cache", str(base / "cache")]
        steps = [
            ("validate", lambda: cmd_validate(argparse.Namespace(manifest=str(manifest_path), cache=str(base / "cache")))),
            ("run both arms", lambda: main(["run", "--case", "C00", "--arm", "both", "--backend-config", args.backend, "--out", str(base / "runs"), *common])),
            ("replay offline", lambda: main(["replay", "--case", "C00", "--runs", str(base / "runs"), "--offline"])),
            ("report", lambda: main(["report", "--runs", str(base / "runs"), "--out", str(base / "reports")])),
        ]
        failed = [name for name, step in steps if step() != 0]
        attempts = latest_attempts(base / "runs" / "C00")["chosen"]
        report = (base / "runs" / "C00" / "report.md").read_text(encoding="utf-8") if (base / "runs" / "C00" / "report.md").is_file() else ""
        checks = {
            "all steps exited 0": not failed,
            "blind and checked start from the same packet bytes": len({s["packet_initial_sha256"] for s in attempts.values()}) == 1 and len(attempts) == 2,
            "checked arm repaired the drifted claim": attempts.get("checked", {}).get("check", {}).get("policy_action") == "repair",
            "fake sessions are not counted as observations": all(not s["is_live"] for s in attempts.values()) and "zero agent observations" in report,
            "report cites the constructed provenance": "not an observed incident" in report,
        }
        for name, ok in checks.items():
            print(f"{'PASS' if ok else 'FAIL'}  {name}")
        bad = [n for n, ok in checks.items() if not ok]
        print(f"smoke: {len(checks) - len(bad)}/{len(checks)} checks passed")
        return 1 if bad else 0
    finally:
        shutil.rmtree(base, ignore_errors=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0], formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    default_cache = str(HERE / ".cache")
    item = sub.add_parser("validate")
    item.add_argument("--manifest", required=True)
    item.add_argument("--cache", default=default_cache)
    item = sub.add_parser("smoke")
    item.add_argument("--backend", default="fake")
    item = sub.add_parser("run")
    item.add_argument("--case", required=True)
    item.add_argument("--arm", choices=("blind", "checked", "both"), default="both")
    item.add_argument("--backend-config", required=True)
    item.add_argument("--out", required=True)
    item.add_argument("--manifest", default=str(HERE / "cases.json"))
    item.add_argument("--cache", default=default_cache)
    item.add_argument("--time-s", type=float, default=180)
    item.add_argument("--max-actions", type=int, default=8)
    item = sub.add_parser("replay")
    item.add_argument("--case", required=True)
    item.add_argument("--runs", required=True)
    item.add_argument("--offline", action="store_true")
    item.add_argument("--out")
    item = sub.add_parser("report")
    item.add_argument("--runs", required=True)
    item.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    try:
        return {"validate": cmd_validate, "smoke": cmd_smoke, "run": cmd_run, "replay": cmd_replay, "report": cmd_report}[args.command](args)
    except CaseError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())

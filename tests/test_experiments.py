"""Regression tests for the evaluation pipeline under experiments/.

No network, no model, no Docker. The tool-loop adapter is driven by a local
stub endpoint, and harness reports are synthetic files in the harness's
format. Nothing here is, or may be reported as, a live result.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXPERIMENTS = ROOT / "experiments"
BENCH = EXPERIMENTS / "paired_runs" / "bench.py"
CASES = EXPERIMENTS / "case_studies" / "cases.py"
sys.path.insert(0, str(EXPERIMENTS / "paired_runs"))
sys.path.insert(0, str(EXPERIMENTS / "backends"))

from prlib import checker, grading, memory, runner, util  # noqa: E402
import toolloop_agent  # noqa: E402


def call(*argv: str, cwd: Path | None = None) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, *argv], cwd=cwd, text=True, encoding="utf-8", errors="replace", stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def tool_call(name: str, **arguments) -> dict:
    return {"choices": [{"message": {"role": "assistant", "content": "", "tool_calls": [{"id": "c1", "type": "function", "function": {"name": name, "arguments": json.dumps(arguments)}}]}}], "usage": {"prompt_tokens": 10, "completion_tokens": 2}}


class StubEndpoint:
    """A scripted /chat/completions endpoint. Not a model."""

    def __init__(self, script: list[dict], delay: float = 0.0):
        outer = self
        self.script, self.delay, self.requests = list(script), delay, []

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):  # noqa: N802
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                outer.requests.append(body)
                time.sleep(outer.delay)
                reply = outer.script.pop(0) if outer.script else tool_call("finish", answer="script exhausted")
                data = json.dumps(reply).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def log_message(self, *_):
                return

        self.server = HTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.url = f"http://127.0.0.1:{self.server.server_port}"

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()


class ToolLoopTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.workspace = self.base / "ws"
        (self.workspace / "pkg").mkdir(parents=True)
        (self.workspace / ".git").mkdir()
        (self.workspace / ".git" / "config").write_text("hidden", encoding="utf-8")
        (self.workspace / "pkg" / "a.py").write_text("x = 1\n", encoding="utf-8")
        (self.base / "secret.txt").write_text("REFERENCE-PATCH", encoding="utf-8")
        (self.base / "prompt.txt").write_text("Fix it.", encoding="utf-8")

    def tearDown(self) -> None:
        self.temp.cleanup()

    def run_script(self, script: list[dict], max_actions: int = 8, time_s: float = 30, delay: float = 0.0, read_only: bool = False) -> tuple[dict, list[dict], StubEndpoint]:
        stub = StubEndpoint(script, delay)
        try:
            request = {"run_id": "t", "workspace": str(self.workspace), "issue_text": "issue", "role": "implementer", "prompt_path": str(self.base / "prompt.txt"), "context_paths": [], "limits": {"time_s": time_s, "max_actions": max_actions}, "read_only": read_only, "out": {"events": str(self.base / "events.jsonl"), "result": str(self.base / "result.json")}, "backend": {"api_style": "openai", "base_url": stub.url, "model": "stub"}}
            result = toolloop_agent.run(request)
        finally:
            stub.close()
        return result, util.read_jsonl(self.base / "events.jsonl"), stub

    def test_hidden_files_cannot_be_read(self) -> None:
        result, events, _ = self.run_script([tool_call("read_file", path="../secret.txt"), tool_call("read_file", path=str(self.base / "secret.txt")), tool_call("read_file", path=".git/config"), tool_call("search", pattern="REFERENCE"), tool_call("finish", answer="done")])
        calls = [e for e in events if e["type"] == "tool_call"]
        self.assertEqual([c["ok"] for c in calls[:3]], [False, False, False])
        self.assertTrue(all("REFERENCE-PATCH" not in json.dumps(e) and "hidden" not in e.get("result", "") for e in events))
        self.assertEqual(calls[3]["result"], "no matches")
        self.assertEqual(result["status"], "completed")

    def test_edit_is_real_and_usage_is_provider_reported(self) -> None:
        result, events, _ = self.run_script([tool_call("replace_in_file", path="pkg/a.py", old_text="x = 1", new_text="x = 2"), tool_call("finish", answer="changed")])
        self.assertEqual((self.workspace / "pkg" / "a.py").read_text(encoding="utf-8"), "x = 2\n")
        self.assertEqual(result["usage"]["input_tokens"], 20)
        self.assertEqual(result["usage"]["source"], "provider_reported")
        self.assertTrue(result["is_live"])  # the adapter is a live adapter; the stub is what makes this a test

    def test_action_limit_is_enforced(self) -> None:
        script = [tool_call("read_file", path="pkg/a.py")] * 6
        result, events, stub = self.run_script(script, max_actions=2)
        self.assertEqual(result["actions"], 2)
        self.assertEqual(result["status"], "action_limit")
        self.assertEqual(len([e for e in events if e["type"] == "tool_call"]), 2)
        offered = [[t["function"]["name"] for t in r["tools"]] for r in stub.requests]
        self.assertEqual(offered[2], ["finish"])  # after the cap only finish is offered

    def test_read_only_role_cannot_edit(self) -> None:
        result, events, _ = self.run_script([tool_call("replace_in_file", path="pkg/a.py", old_text="x = 1", new_text="x = 9"), tool_call("finish", answer="x")], read_only=True)
        self.assertEqual((self.workspace / "pkg" / "a.py").read_text(encoding="utf-8"), "x = 1\n")
        self.assertFalse([e for e in events if e["type"] == "tool_call"][0]["ok"])

    def test_deadline_is_a_recorded_terminal_state(self) -> None:
        result, events, _ = self.run_script([tool_call("read_file", path="pkg/a.py")] * 5, time_s=1.5, delay=1.0)
        self.assertEqual(result["status"], "budget_exhausted")
        self.assertEqual(events[-1]["type"], "terminal")


class CheckerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.tree = Path(self.temp.name)
        (self.tree / "m.py").write_text("LIMIT = 5\n\n\ndef f(a, b=1):\n    return a\n\n\ndef g(x):\n    return x\n", encoding="utf-8")
        self.claims = {c["symbol"]: c for c in memory.build_claims(self.tree, "s" * 40)["claims"]}

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_harmless_edit_preserves_a_supported_claim(self) -> None:
        (self.tree / "m.py").write_text("LIMIT = 5\n\n\ndef f(a, b=1):\n    # only a comment changed\n    return a\n\n\ndef g(x):\n    return x\n", encoding="utf-8")
        result = checker.check_claim(self.claims["m.f"], self.tree)
        self.assertEqual((result["status"], checker.policy_action(result)), ("supported", "reuse"))
        self.assertEqual(checker.check_claim(self.claims["m.LIMIT"], self.tree)["status"], "supported")

    def test_changed_signature_is_repaired_from_current_source(self) -> None:
        (self.tree / "m.py").write_text("LIMIT = 7\n\n\ndef f(a, c=1):\n    return a\n", encoding="utf-8")
        result = checker.check_claim(self.claims["m.f"], self.tree)
        self.assertEqual((result["status"], checker.policy_action(result)), ("contradicted", "repair"))
        self.assertIn("m.f(a, c=1)", result["repair_text"])
        self.assertEqual(checker.policy_action(checker.check_claim(self.claims["m.LIMIT"], self.tree)), "repair")
        gone = checker.check_claim(self.claims["m.g"], self.tree)
        self.assertEqual((gone["status"], checker.policy_action(gone)), ("contradicted", "omit"))

    def test_ambiguous_or_missing_evidence_is_unresolved(self) -> None:
        (self.tree / "m.py").write_text("def f(a):\n    return a\n\n\ndef f(a, b):\n    return b\n\n\nLIMIT = compute()\n", encoding="utf-8")
        self.assertEqual(checker.check_claim(self.claims["m.f"], self.tree)["status"], "unresolved")
        self.assertEqual(checker.check_claim(self.claims["m.LIMIT"], self.tree)["status"], "unresolved")
        (self.tree / "m.py").unlink()
        missing = checker.check_claim(self.claims["m.f"], self.tree)
        self.assertEqual((missing["status"], checker.policy_action(missing)), ("unresolved", "omit"))
        (self.tree / "m.py").write_text("def broken(:\n", encoding="utf-8")
        self.assertEqual(checker.check_claim(self.claims["m.f"], self.tree)["status"], "unresolved")


class RoutingRepoTest(unittest.TestCase):
    def test_routing_works_through_an_aliased_temp_path(self) -> None:
        """macOS temp directories are symlinks; the released helper needs a resolved project root."""
        with tempfile.TemporaryDirectory() as temp:
            real = Path(temp) / "real"
            alias = Path(temp) / "alias"
            real.mkdir()
            try:
                if sys.platform == "win32":
                    made = subprocess.run(["cmd", "/c", "mklink", "/J", str(alias), str(real)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0
                else:
                    alias.symlink_to(real, target_is_directory=True)
                    made = True
            except OSError:
                made = False
            if not made:
                self.skipTest("cannot create a directory alias on this host")
            for label, body in (("s", "def f(a):\n    return a\n"), ("t", "def f(a, b=2):\n    return a\n")):
                (alias / label / "pkg").mkdir(parents=True)
                (alias / label / "pkg" / "mod.py").write_text(body, encoding="utf-8")
            inventory = memory.build_claims(alias / "s", "s" * 40)
            documents = memory.build_documents(inventory, 1500)
            routing = memory.build_routing_repo(alias / "routing", alias / "s", alias / "t", documents)
            routed = memory.route(alias / "routing", "f in pkg mod fails", 5)
            self.assertEqual(routing["changed_scope_files"], ["pkg/mod.py"])
            self.assertEqual(len(routed["documents"]), 1)
            self.assertEqual(list(routed["stale_documents"].values()), [["pkg/mod.py"]])


class LedgerAndGradingTest(unittest.TestCase):
    def test_trace_truncation_keeps_terminal_counters(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            ledger = util.Ledger(Path(temp) / "ledger.jsonl", {"run_id": "r"})
            for index in range(2000):
                ledger.event("tool_call", observation="x" * 2000, counters={"actions": 1}, index=index)
            totals = ledger.close(status="completed_patch")
            data = (Path(temp) / "ledger.jsonl").read_bytes()
            rows = util.read_jsonl(Path(temp) / "ledger.jsonl")
            self.assertLessEqual(len(data), util.LEDGER_BYTES)
            self.assertTrue(all(len(r.get("observation", "").encode("utf-8")) <= util.EXCERPT_BYTES for r in rows))
            self.assertEqual(rows[-1]["event_type"], "terminal_summary")
            self.assertEqual(rows[-1]["events_total"], 2000)
            self.assertEqual(rows[-1]["counts"]["tool_call"], 2000)
            self.assertTrue(totals["truncated"] and totals["events_truncated"] > 0)

    def test_requests_use_unique_run_ids_and_flag_empty_patches(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            attempts = []
            for arm, patch in (("source_only", ""), ("static_stale", "diff --git a/x b/x\n"), ("selective_stale", "diff --git a/y b/y\n")):
                path = base / f"{arm}.diff"
                path.write_text(patch, encoding="utf-8")
                attempts.append({"attempt_id": f"inst__{arm}__seed1__a01", "arm": arm, "backend_name": "b", "patch_path": str(path), "patch_sha256": util.sha256_bytes(patch.encode())})
            manifest = {"dataset": {"name": "SWE-bench/SWE-bench_Lite", "split": "test", "revision": "r"}, "evaluator": {"swebench_revision": "v"}}
            request_dir = grading.build_request(manifest, "h" * 64, "inst", "req-1", attempts, True, base / "requests")
            request = util.read_json(request_dir / "request.json")
            self.assertEqual(len({p["run_id"] for p in request["predictions"]}), 3)
            self.assertEqual([p["empty"] for p in request["predictions"]], [True, False, False])
            record = json.loads((request_dir / request["predictions"][1]["file"]).read_text(encoding="utf-8"))
            self.assertEqual(set(record), {"instance_id", "model_name_or_path", "model_patch"})
            with self.assertRaises(util.BenchError):
                grading.build_request(manifest, "h" * 64, "inst", "req-1", attempts, True, base / "requests")

    def test_control_verdict_needs_a_real_failing_test_and_a_resolved_reference(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            results = Path(temp)

            def put(name: str, report: dict | None, **extra) -> None:
                util.write_json(results / name / "outcome.json", {"report": report, **extra})

            put("gold_control", {"patch_successfully_applied": True, "resolved": True})
            put("base_control", {"patch_successfully_applied": True, "resolved": False, "tests_status": {"FAIL_TO_PASS": {"success": [], "failure": ["t::a"]}}}, skip_patch=True)
            self.assertTrue(grading.control_verdict(results)["ok"])
            put("base_control", None, skipped_empty=True)  # a skipped empty prediction proves nothing
            self.assertFalse(grading.control_verdict(results)["ok"])
            put("base_control", {"patch_successfully_applied": True, "resolved": False, "tests_status": {"FAIL_TO_PASS": {"success": ["t::a"], "failure": []}}}, skip_patch=True)
            self.assertFalse(grading.control_verdict(results)["ok"])
            put("attempt", {"patch_successfully_applied": False, "resolved": False})
            self.assertEqual(grading.read_outcome(results, "attempt")["grading_status"], "patch_apply_failed")
            self.assertEqual(grading.read_outcome(results, "never_sent")["grading_status"], "pending")


class EndToEndSmokeTest(unittest.TestCase):
    def test_benchmark_smoke_then_offline_case_replay(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            keep = Path(temp) / "smoke"
            result = call(str(BENCH), "smoke", "--backend", "fake", "--keep", str(keep))
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertNotIn("FAIL", result.stdout)
            summaries = [util.read_json(p) for p in sorted((keep / "runs").glob("*/*/*/summary.json"))]
            self.assertEqual(len(summaries), 3)
            self.assertEqual(len({s["attempt_id"] for s in summaries}), 3)
            self.assertTrue(all(s["is_live"] is False and s["status"] in runner.TERMINAL for s in summaries))
            self.assertTrue(all(s["patch"]["local_apply_check"]["ok"] for s in summaries))
            source = next(s for s in summaries if s["arm"] == "source_only")
            self.assertIsNone(source["packet"]["initial_sha256"])
            self.assertFalse(list((keep / "runs").glob("*/source_only/*/packet*.md")))
            self.assertEqual(json.loads((keep / "runs" / "fixture__retry-1" / "source_only" / source["attempt_id"] / "implementer.request.json").read_text(encoding="utf-8"))["context_paths"], [])
            # the adapter reuses the pilot trace as a case report, then the case tool replays it offline, twice
            adapter = call(str(EXPERIMENTS / "integration" / "trace_to_case.py"), "--manifest", str(keep / "prepared" / "frozen.json"), "--instance-id", "fixture__retry-1", "--case-id", "PILOT-T", "--out", str(keep / "case_runs"))
            self.assertEqual(adapter.returncode, 0, adapter.stderr)
            digests = []
            for _ in range(2):
                replay = call("-I", str(CASES), "replay", "--case", "PILOT-T", "--runs", str(keep / "case_runs"), "--offline", cwd=CASES.parent)
                self.assertEqual(replay.returncode, 0, replay.stderr)
                digests.append(json.loads(replay.stdout)["sha256"])
            self.assertEqual(digests[0], digests[1])
            report = (keep / "case_runs" / "PILOT-T" / "report.md").read_text(encoding="utf-8")
            self.assertIn("zero agent observations", report)
            self.assertIn("ungraded", report)

    def test_case_study_smoke(self) -> None:
        result = call(str(CASES), "smoke", "--backend", "fake", cwd=CASES.parent)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertNotIn("FAIL ", result.stdout)

    def test_one_issue_entry_point_never_starts_a_batch(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            for bad in ("", "*", "pytest-dev__pytest-*", "a,b", "a b", "frozen.json", "all"):
                result = call("-m", "experiments.validate_pipeline", "--instance-id", bad, "--backend-config", "fake", "--out", temp, cwd=ROOT)
                self.assertEqual(result.returncode, 2, bad)
                self.assertIn("BLOCKED", result.stderr)
            preview = call("-m", "experiments.validate_pipeline", "--instance-id", "pytest-dev__pytest-0000", "--backend-config", "fake", "--out", temp, "--preview-only", cwd=ROOT)
            self.assertEqual(preview.returncode, 0, preview.stderr)
            self.assertIn("exactly one", preview.stdout)
            self.assertIn("evaluator controls  : 2", preview.stdout)
            self.assertIn("live solver attempts: 3", preview.stdout)
            fake = call("-m", "experiments.validate_pipeline", "--instance-id", "pytest-dev__pytest-0000", "--backend-config", "fake", "--out", temp, "--stage", "preflight", cwd=ROOT)
            self.assertEqual(fake.returncode, 2)
            self.assertIn("dry run cannot be the acceptance run", fake.stderr)

    def test_batch_runs_are_opt_in(self) -> None:
        import bench

        manifest = {"issues": [{"instance_id": "a", "status": "held_out"}, {"instance_id": "b", "status": "held_out"}]}
        with self.assertRaises(util.BenchError):
            bench.select_issues(manifest, type("Args", (), {"instance_id": None, "batch": False})(), ("held_out",))
        self.assertEqual(len(bench.select_issues(manifest, type("Args", (), {"instance_id": None, "batch": True})(), ("held_out",))), 2)
        with self.assertRaises(util.BenchError):
            bench.one_instance_id("a*")


if __name__ == "__main__":
    unittest.main()

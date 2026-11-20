"""Prepare one issue: snapshots at s and t, issue-blind memory at s, one routed stale packet, screening facts."""

from __future__ import annotations

import re
import shutil
import tempfile
import time
from pathlib import Path

from . import checker, dataset, memory
from .runner import tree_hash
from .util import REPO_ROOT, BenchError, extract_tar, git, hash_obj, now_iso, read_json, sha256_bytes, sha256_file, write_atomic, write_json

DEFAULTS = {
    "seed": 20261119,
    "repos": ["pytest-dev/pytest", "sphinx-doc/sphinx", "sympy/sympy"],
    "min_age_days": 30,
    "limits": {"time_s": 360, "max_actions": 12},
    "planner": {"max_actions": 2, "handoff_bytes": 600, "time_s": 120},
    "checker": {"max_checks": 3, "time_s": 45},
    "packet": {"max_docs": 5, "max_bytes": 8000, "doc_body_cap": 1500},
    "screen": {"max_candidates": 9, "timebox_minutes": 15},
    "tier": {"held_out": 0},
    "evaluator": {"swebench_revision": "87ab1f6ced28f75ba73ca899dc759b019310944a", "swebench_version": "5.0.1", "timeout_s": 1800, "grader": "github_actions", "remote": "origin"},
    "cache_dir": "experiments/.cache",
    "grader_store": "experiments/.grader_store",
}


def load_study(path: Path) -> dict:
    study = read_json(path)
    for key, value in DEFAULTS.items():
        if isinstance(value, dict):
            study[key] = {**value, **study.get(key, {})}
        else:
            study.setdefault(key, value)
    for key in ("cache_dir", "grader_store"):
        location = Path(study[key])
        study[key] = str(location if location.is_absolute() else REPO_ROOT / location)
    return study


def mentioned(claim: dict, issue_text: str) -> bool:
    """Screening signal only: the issue names the claim's symbol or module. Relevance itself is a human annotation."""
    words = set(re.findall(r"[A-Za-z_][A-Za-z0-9_]{3,}", issue_text))
    leaf = claim["symbol"].rsplit(".", 1)[-1]
    stem = claim["path"].rsplit("/", 1)[-1][:-3]
    return leaf in words or (stem in words and stem not in {"__init__", "main", "base", "utils", "util", "core"})


def prepare_issue(spec: dict, study: dict, prepared: Path) -> dict:
    """spec: instance_id, repo, clone (evaluator-side Git dir), s, t, problem_statement, plus pass-through facts."""
    started = time.monotonic()
    cache = Path(study["cache_dir"])
    issue_dir = prepared / spec["instance_id"]
    issue_dir.mkdir(parents=True, exist_ok=True)
    snapshots = {}
    for label in ("s", "t"):
        tar_path = cache / "snapshots" / spec["instance_id"] / f"{label}-{spec[label][:12]}.tar"
        snapshots[label] = {"tar": str(tar_path), "sha256": dataset.export_snapshot(Path(spec["clone"]), spec[label], tar_path)}
    with tempfile.TemporaryDirectory(prefix="prep-") as temp:
        tree_s, tree_t = Path(temp) / "s", Path(temp) / "t"
        extract_tar(Path(snapshots["s"]["tar"]), tree_s)
        extract_tar(Path(snapshots["t"]["tar"]), tree_t)
        build_started = time.monotonic()
        inventory = memory.build_claims(tree_s, spec["s"])
        documents = memory.build_documents(inventory, study["packet"]["doc_body_cap"])
        build_ms = int((time.monotonic() - build_started) * 1000)
        route_started = time.monotonic()
        routing = memory.build_routing_repo(Path(temp) / "routing", tree_s, tree_t, documents)
        intent = spec["problem_statement"][:20000]
        routed = memory.route(Path(temp) / "routing", intent, study["packet"]["max_docs"])
        route_ms = int((time.monotonic() - route_started) * 1000)
        packet = memory.render_packet(routed, documents, spec["s"], study["packet"]["max_docs"], study["packet"]["max_bytes"])
        claims_by_id = {c["claim_id"]: c for c in inventory["claims"]}
        changed = set(routing["changed_scope_files"])
        # Evaluator-side labels for claims whose file changed between s and t, from the same experimental checker.
        drift = []
        for claim in inventory["claims"]:
            if claim["path"] in changed:
                result = checker.check_claim(claim, tree_t)
                if result["status"] != "supported":
                    drift.append({"claim_id": claim["claim_id"], "path": claim["path"], "symbol": claim["symbol"], "status": result["status"], "old_text": claim["text"], "evidence": result["evidence"], "repairable": bool(result.get("repair_text")), "mentioned_in_issue": mentioned(claim, spec["problem_statement"])})
        tree_t_hash = tree_hash(tree_t)
    exposed = [cid for entry in packet["documents"] for cid in entry["claim_ids"]]
    routed_docs = {entry["doc_path"] for entry in packet["documents"]}
    doc_of = {cid: d["doc_path"] for d in documents for cid in d["claim_ids"]}
    for row in drift:
        row["routed"] = doc_of.get(row["claim_id"]) in routed_docs
        row["exposed"] = row["claim_id"] in exposed
    contradicted = [r for r in drift if r["status"] == "contradicted"]
    screening = {
        "instance_id": spec["instance_id"], "claims_at_s": len(inventory["claims"]), "documents_at_s": len(documents), "scope_files_changed_s_to_t": len(changed),
        "claims_not_supported_at_t": len(drift), "contradicted": len(contradicted), "contradicted_mentioned": [r["claim_id"] for r in contradicted if r["mentioned_in_issue"]],
        "contradicted_exposed": [r["claim_id"] for r in contradicted if r["exposed"]], "contradicted_mentioned_exposed": [r["claim_id"] for r in contradicted if r["exposed"] and r["mentioned_in_issue"]],
        "router_miss": bool([r for r in contradicted if r["mentioned_in_issue"]]) and not [r for r in contradicted if r["mentioned_in_issue"] and r["exposed"]],
        "stale_documents_routed": sum(1 for e in packet["documents"] if e["stale"]), "skipped_files": inventory["skipped_files"][:20], "skipped_ambiguous": inventory["skipped_ambiguous"],
    }
    write_atomic(issue_dir / "issue.md", spec["problem_statement"])
    write_atomic(issue_dir / "packet.md", packet["text"])
    write_json(issue_dir / "packet.json", {k: v for k, v in packet.items() if k != "text"})
    write_json(issue_dir / "claims_exposed.json", [claims_by_id[cid] for cid in exposed])
    write_json(issue_dir / "claim_index.json", {"inventory_sha256": inventory["inventory_sha256"], "builder": inventory["builder"], "revision": spec["s"], "scope_rule": inventory["scope_rule"], "skipped_predicate_types": inventory["skipped_predicate_types"], "claims": [{k: c[k] for k in ("claim_id", "text", "path", "symbol", "predicate", "evidence_revision")} for c in inventory["claims"]]})
    write_json(issue_dir / "drift.json", drift)
    write_json(issue_dir / "screening.json", screening)
    issue = {
        "instance_id": spec["instance_id"], "repo": spec["repo"], "s": spec["s"], "t": spec["t"], "s_date": spec.get("s_date"), "t_date": spec.get("t_date"), "age_days": spec.get("age_days"), "revision_rule": spec.get("rule"),
        "image": spec.get("image"), "environment_setup_commit": spec.get("environment_setup_commit"), "row_sha256": spec.get("row_sha256"), "issue_sha256": sha256_bytes(spec["problem_statement"].encode("utf-8")),
        "snapshot_s": snapshots["s"]["tar"], "snapshot_s_sha256": snapshots["s"]["sha256"], "snapshot_t": snapshots["t"]["tar"], "snapshot_t_sha256": snapshots["t"]["sha256"], "tree_t_sha256": tree_t_hash,
        "inventory_sha256": inventory["inventory_sha256"], "packet_sha256": packet["sha256"], "packet_bytes": packet["bytes"], "routed_documents": [e["doc_path"] for e in packet["documents"]],
        "exposed_claims": len(exposed), "truncated_claims": packet["truncated_claims"], "router": {"status": routed["status"], "helper_sha256": routing["helper_sha256"], "helper_version": routing["helper_version"], "stale_documents_total": routed["stale_document_count"]},
        "timing_ms": {"build_memory": build_ms, "route_and_check_freshness": route_ms, "prepare_total": int((time.monotonic() - started) * 1000)}, "prepared_at": now_iso(),
    }
    write_json(issue_dir / "issue.json", issue)
    return {"issue": issue, "screening": screening}


def spec_from_dataset(row: dict, study: dict) -> dict:
    clone = dataset.ensure_clone(row["repo"], Path(study["cache_dir"]))
    revisions = dataset.resolve_revisions(clone, row["base_commit"], int(study["min_age_days"]))
    return {**{k: row.get(k) for k in ("instance_id", "repo", "problem_statement", "image", "environment_setup_commit", "row_sha256")}, "clone": str(clone), **revisions}


def driver_facts() -> dict:
    head = git(REPO_ROOT, "rev-parse", "HEAD", check=False)
    return {"docagent_checkout_sha": head, "docagent_reference_sha": "cfd5224729c8b2eb7502e51934aa2a2a38501357", "worktree_dirty": bool(git(REPO_ROOT, "status", "--porcelain", "--", "experiments", "skills", check=False)), "helper_sha256": sha256_file(memory.HELPER), "builder": memory.BUILDER_VERSION, "checker": checker.CHECKER_VERSION}


def freeze(study: dict, issues: list[dict], statuses: dict, prepared: Path) -> dict:
    """Frozen manifest: everything a run or a grade needs, hashed as a whole."""
    import random

    entries = []
    for issue in issues:
        order = ["source_only", "static_stale", "selective_stale"]
        random.Random(f"{study['seed']}:{issue['instance_id']}").shuffle(order)
        entries.append({**issue, "status": statuses[issue["instance_id"]], "arm_order": order})
    manifest = {
        "schema_version": 1, "frozen_at": now_iso(), "seed": study["seed"], "dataset": study["dataset"], "evaluator": study["evaluator"], "limits": study["limits"], "planner": study["planner"], "checker": study["checker"], "packet": study["packet"],
        "min_age_days": study["min_age_days"], "driver": driver_facts(), "token_accounting": "provider-reported tokens when the backend exposes them; context bound is a UTF-8 byte ceiling", "cached_work": "routing and the stale packet are built once per issue and charged equally to static and selective", "issues": entries,
    }
    write_json(prepared / "frozen.json", manifest)
    return manifest


def manifest_hash(manifest: dict) -> str:
    return hash_obj(manifest)

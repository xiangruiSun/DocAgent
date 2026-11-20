"""EXPERIMENTAL claim-level checker. Not part of released DocAgent.

The released helper only says that a covered file changed. This module asks
the narrower question for one recorded claim: does the current source still
support it? It reads the solver-visible tree at t and nothing else. It never
sees evaluator answers, relevance labels or another team's annotations.

Verdicts: supported, contradicted, unresolved. A repair is offered only when
exactly one current definition gives the new fact directly. Anything dynamic,
duplicated, unparsable or missing is unresolved or omitted, never guessed.
"""

from __future__ import annotations

import time
from pathlib import Path

from .memory import CLAIM_LINE, file_facts

CHECKER_VERSION = "experimental-claim-checker-1"
LEGEND = "\nCheck legend: [checked: supported] was confirmed in the current source; [repaired] was rewritten from the current source; [omitted] could not be confirmed; [unchecked] and unmarked claims were not checked.\n"


def check_claim(claim: dict, tree: Path) -> dict:
    predicate = claim["predicate"]
    path = tree / predicate["path"]
    base = {"claim_id": claim["claim_id"], "path": predicate["path"], "symbol": claim["symbol"], "old_text": claim["text"], "repair_text": None, "line": None}
    if not path.is_file():
        return {**base, "status": "unresolved", "evidence": "recorded file is absent at the current revision; a missing file does not show where the symbol went"}
    try:
        facts = file_facts(path.read_text(encoding="utf-8"))
    except (SyntaxError, UnicodeDecodeError, ValueError) as exc:
        return {**base, "status": "unresolved", "evidence": f"current file could not be parsed ({type(exc).__name__})"}
    if predicate["type"] == "signature":
        entries = facts["signature"].get(predicate["qualname"], [])
        if not entries:
            return {**base, "status": "contradicted", "evidence": f"no definition of {predicate['qualname']} in the current file; new location unknown"}
        if len(entries) > 1 or "overload" in " ".join(entries[0]["decorators"]):
            return {**base, "status": "unresolved", "evidence": f"{len(entries)} definitions of {predicate['qualname']}; call shape is ambiguous"}
        entry = entries[0]
        current = f"{predicate['qualname']}({entry['args']})"
        if entry["args"] == predicate["args"]:
            return {**base, "status": "supported", "line": entry["line"], "evidence": f"line {entry['line']}: def {current}"}
        repaired = claim["text"].replace(f"({predicate['args']})`", f"({entry['args']})`")
        return {**base, "status": "contradicted", "line": entry["line"], "evidence": f"line {entry['line']}: def {current}", "repair_text": repaired if repaired != claim["text"] else None}
    if predicate["type"] == "literal":
        entries = facts["literal"].get(predicate["name"], [])
        if not entries:
            return {**base, "status": "contradicted", "evidence": f"no module-level assignment of {predicate['name']} in the current file"}
        if len(entries) > 1 or not entries[0]["literal"]:
            return {**base, "status": "unresolved", "evidence": f"{predicate['name']} is assigned {len(entries)} time(s) or to a computed value"}
        entry = entries[0]
        if entry["value"] == predicate["value"]:
            return {**base, "status": "supported", "line": entry["line"], "evidence": f"line {entry['line']}: {predicate['name']} = {entry['value']}"}
        repaired = claim["text"].replace(f"= {predicate['value']}`", f"= {entry['value']}`")
        return {**base, "status": "contradicted", "line": entry["line"], "evidence": f"line {entry['line']}: {predicate['name']} = {entry['value']}", "repair_text": repaired if repaired != claim["text"] else None}
    return {**base, "status": "unresolved", "evidence": f"unsupported predicate type {predicate['type']}"}


def policy_action(result: dict) -> str:
    if result["status"] == "supported":
        return "reuse"
    if result["status"] == "contradicted" and result.get("repair_text"):
        return "repair"
    return "omit"


def selective_packet(packet: dict, claims_by_id: dict, tree: Path, max_checks: int, time_limit_s: float) -> dict:
    """Start from the exact stale packet bytes; check up to max_checks suspect claims in retrieval order."""
    started = time.monotonic()
    suspects = [cid for entry in packet["documents"] if entry["stale"] for cid in entry["claim_ids"]]
    decisions: dict[str, dict] = {}
    skipped = []
    for claim_id in suspects:
        if len(decisions) >= max_checks:
            skipped.append({"claim_id": claim_id, "status": "skipped", "reason": "check budget exhausted"})
            continue
        if time.monotonic() - started > time_limit_s:
            skipped.append({"claim_id": claim_id, "status": "skipped", "reason": "check time limit reached"})
            continue
        check_started = time.monotonic()
        result = check_claim(claims_by_id[claim_id], tree)
        result["policy_action"] = policy_action(result)
        result["check_ms"] = int((time.monotonic() - check_started) * 1000)
        decisions[claim_id] = result
    skipped_ids = {item["claim_id"] for item in skipped}
    lines = []
    for line in packet["text"].split("\n"):
        match = CLAIM_LINE.match(line)
        claim_id = match.group(1) if match else None
        if claim_id in decisions:
            result = decisions[claim_id]
            if result["policy_action"] == "reuse":
                line += "  [checked: supported]"
            elif result["policy_action"] == "repair":
                line = f"- [{claim_id}] {result['repair_text']}  [repaired from the current source]"
            else:
                line = f"- [{claim_id}] [omitted: the recorded claim could not be confirmed; read `{result['path']}`]"
        elif claim_id in skipped_ids:
            line += "  [unchecked]"
        lines.append(line)
    text = "\n".join(lines)
    if decisions or skipped:
        text += LEGEND
    return {"text": text, "decisions": list(decisions.values()), "skipped": skipped, "suspect_claims": len(suspects), "checks": len(decisions), "check_ms": int((time.monotonic() - started) * 1000), "checker": CHECKER_VERSION}

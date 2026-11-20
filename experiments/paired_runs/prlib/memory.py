"""Issue-blind memory builder, released-router call, and packet rendering.

The builder sees one source tree and nothing else: no issue, no later history.
It records two predicate types, Python signatures and literal module defaults.
Routing and the file-level freshness signal come from the released DocAgent
helper (`context_bundle`), called unmodified on a small routing repository
whose history is: source at s, memory documents anchored there, source at t.
"""

from __future__ import annotations

import ast
import importlib.util
import os
import re
import shutil
import sys
from pathlib import Path

from .util import HELPER, BenchError, git, sha256_bytes, sha256_file

BUILDER_VERSION = "memory-builder-1"
EXCLUDED_PARTS = {"tests", "test", "testing", "doc", "docs", "examples", "example", "bench", "benchmarks", "scripts", "extra", "changelog", ".github", "build", "dist", "release", "bin"}
EXCLUDED_NAMES = {"setup.py", "conftest.py"}
SKIPPED_PREDICATES = ["symbol location", "existing-test selector", "class attribute default", "non-literal default", "nested function", "dunder method other than __init__"]
DOC_ROOT = "docs/memory"
CLAIM_LINE = re.compile(r"^- \[(K\d+)\] ")


def in_scope(relative: str) -> bool:
    parts = relative.split("/")
    name = parts[-1]
    return name.endswith(".py") and name not in EXCLUDED_NAMES and not name.startswith("test_") and not any(part in EXCLUDED_PARTS for part in parts[:-1])


def scope_files(tree: Path) -> list[str]:
    found = []
    for directory, folders, files in os.walk(tree):
        folders[:] = sorted(f for f in folders if f != ".git")
        for name in sorted(files):
            relative = (Path(directory) / name).relative_to(tree).as_posix()
            if in_scope(relative):
                found.append(relative)
    return sorted(found)


def module_name(relative: str) -> str:
    parts = relative[:-3].split("/")
    if parts and parts[0] in {"src", "lib"}:
        parts = parts[1:]
    if parts and parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def _literal(node: ast.AST) -> bool:
    if isinstance(node, ast.Constant):
        return isinstance(node.value, (str, int, float, bool, type(None)))
    if isinstance(node, ast.Tuple):
        return all(_literal(item) for item in node.elts)
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        return _literal(node.operand)
    return False


def _decorators(node: ast.AST) -> list[str]:
    names = []
    for item in getattr(node, "decorator_list", []):
        target = item.func if isinstance(item, ast.Call) else item
        names.append(ast.unparse(target))
    return names


def file_facts(source: str) -> dict:
    """All recordable facts of one file: {"signature": {qualname: [entries]}, "literal": {name: [entries]}}."""
    tree = ast.parse(source)
    signatures: dict[str, list[dict]] = {}
    literals: dict[str, list[dict]] = {}

    def add_function(node: ast.AST, prefix: str) -> None:
        if node.name.startswith("__") and node.name != "__init__":
            return
        signatures.setdefault(prefix + node.name, []).append({"args": ast.unparse(node.args), "line": node.lineno, "decorators": _decorators(node)})

    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            add_function(node, "")
        elif isinstance(node, ast.ClassDef):
            for child in node.body:
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    add_function(child, node.name + ".")
        elif isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            name = node.targets[0].id
            if name.isupper():
                entry = {"line": node.lineno, "literal": _literal(node.value), "value": ast.unparse(node.value)}
                literals.setdefault(name, []).append(entry)
    return {"signature": signatures, "literal": literals}


def build_claims(tree: Path, revision: str) -> dict:
    """Deterministic inventory of claims for every in-scope file of one tree."""
    claims, skipped_files, ambiguous = [], [], 0
    for relative in scope_files(tree):
        try:
            facts = file_facts((tree / relative).read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError, ValueError) as exc:
            skipped_files.append({"path": relative, "reason": type(exc).__name__})
            continue
        module = module_name(relative)
        rows = []
        for qualname, entries in facts["signature"].items():
            if len(entries) != 1 or {"overload", "typing.overload"} & set(entries[0]["decorators"]) or any(d.endswith((".setter", ".getter", ".deleter")) for d in entries[0]["decorators"]):
                ambiguous += 1
                continue
            entry = entries[0]
            rows.append({"kind": "signature", "path": relative, "symbol": f"{module}.{qualname}", "line": entry["line"], "text": f"signature `{module}.{qualname}({entry['args']})`", "predicate": {"type": "signature", "path": relative, "qualname": qualname, "args": entry["args"]}})
        for name, entries in facts["literal"].items():
            if len(entries) != 1 or not entries[0]["literal"] or len(entries[0]["value"]) > 100:
                ambiguous += 1
                continue
            entry = entries[0]
            rows.append({"kind": "literal", "path": relative, "symbol": f"{module}.{name}", "line": entry["line"], "text": f"default `{module}.{name} = {entry['value']}`", "predicate": {"type": "literal", "path": relative, "name": name, "value": entry["value"]}})
        claims.extend(sorted(rows, key=lambda row: (row["line"], row["symbol"])))
    for index, claim in enumerate(claims, 1):
        claim["claim_id"] = f"K{index:05d}"
        claim["evidence_revision"] = revision
    inventory = {"builder": BUILDER_VERSION, "revision": revision, "claims": claims, "skipped_files": skipped_files, "skipped_ambiguous": ambiguous, "skipped_predicate_types": SKIPPED_PREDICATES, "scope_rule": {"excluded_parts": sorted(EXCLUDED_PARTS), "excluded_names": sorted(EXCLUDED_NAMES), "pattern": "*.py not starting with test_"}}
    inventory["inventory_sha256"] = sha256_bytes("\n".join(f"{c['claim_id']}|{c['path']}|{c['text']}" for c in claims).encode("utf-8"))
    return inventory


def build_documents(inventory: dict, body_cap: int) -> list[dict]:
    """One or more bounded Markdown documents per module. Fixed rule: claims in definition order, cut at the byte cap."""
    by_path: dict[str, list[dict]] = {}
    for claim in inventory["claims"]:
        by_path.setdefault(claim["path"], []).append(claim)
    documents = []
    for path in sorted(by_path):
        parts: list[list[dict]] = [[]]
        used = 0
        for claim in by_path[path]:
            size = len(f"- [{claim['claim_id']}] {claim['text']}\n".encode("utf-8"))
            if parts[-1] and used + size > body_cap:
                parts.append([])
                used = 0
            parts[-1].append(claim)
            used += size
        for index, part in enumerate(parts, 1):
            lines = "\n".join(f"- [{c['claim_id']}] {c['text']}" for c in part)
            doc_path = f"{DOC_ROOT}/{path[:-3]}.part{index:02d}.md"
            body = (
                f"# Memory: {path} (part {index} of {len(parts)})\n\n## Current behavior\n\n"
                f"Recorded from `{path}` at revision {inventory['revision'][:12]}. Each line is a claim id followed by a fact that held at that revision.\n\n"
                f"{lines}\n\n## Verification\n\nRun `python -c \"import ast; ast.parse(open('{path}').read())\"` and compare each listed fact with the file.\n"
            )
            documents.append({"doc_path": doc_path, "covers": path, "part": index, "parts": len(parts), "claim_ids": [c["claim_id"] for c in part], "claim_lines": lines, "body": body})
    return documents


def load_helper():
    """Import the released helper from this checkout, unmodified, once."""
    if "docagent_released_helper" not in sys.modules:
        spec = importlib.util.spec_from_file_location("docagent_released_helper", HELPER)
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
    return sys.modules["docagent_released_helper"]


def _copy_scope(tree: Path, target: Path, files: list[str]) -> None:
    for relative in files:
        destination = target / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(tree / relative, destination)


def build_routing_repo(root: Path, tree_s: Path, tree_t: Path, documents: list[dict]) -> dict:
    """Routing repository for the released helper: commit 1 source at s, commit 2 memory, commit 3 source at t."""
    helper = load_helper()
    if root.exists():
        shutil.rmtree(root, ignore_errors=True)
    root.mkdir(parents=True)
    git(root, "init", "-q", "-b", "main")
    git(root, "config", "user.email", "bench@docagent.local")
    git(root, "config", "user.name", "DocAgent Bench")
    git(root, "config", "core.autocrlf", "false")
    files_s, files_t = scope_files(tree_s), scope_files(tree_t)
    _copy_scope(tree_s, root, files_s)
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "source at s")
    anchor = git(root, "rev-parse", "HEAD")
    helper.enable(root)
    for document in documents:
        front = f'---\ndocagent_authority: current-state\ndocagent_verified_at: {anchor}\ndocagent_covers:\n  - "{document["covers"]}"\ndocagent_domains:\n  - "memory"\n---\n'
        target = root / document["doc_path"]
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(front + document["body"], encoding="utf-8", newline="\n")
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "memory at s")
    for relative in files_s:
        (root / relative).unlink()
    _copy_scope(tree_t, root, files_t)
    git(root, "add", "-A")
    git(root, "commit", "-q", "--allow-empty", "-m", "source at t")
    changed = sorted(line for line in git(root, "diff", "--name-only", f"{anchor}..HEAD").splitlines() if in_scope(line))
    return {"anchor": anchor, "head": git(root, "rev-parse", "HEAD"), "files_s": len(files_s), "files_t": len(files_t), "changed_scope_files": changed, "helper_sha256": sha256_file(HELPER), "helper_version": helper.skill_version()}


def route(root: Path, intent: str, limit: int) -> dict:
    """Unmodified released router. Returns ranked documents and its freshness findings."""
    bundle = load_helper().context_bundle(root, intent, limit)
    if bundle.get("status") in {"unconfigured", "disabled"}:
        raise BenchError(f"released helper reports {bundle.get('status')}")
    stale = {f["document"]: f.get("files") or [] for f in bundle.get("freshness_findings", []) if f.get("code") == "stale-document"}
    ranked = [d for d in bundle["documents"] if d["path"].startswith(DOC_ROOT + "/")]
    return {"status": bundle["status"], "query_terms": len(bundle.get("query_terms", [])), "documents": ranked, "stale_documents": stale, "stale_document_count": len(stale)}


def render_packet(routed: dict, documents: list[dict], revision_s: str, max_docs: int, max_bytes: int) -> dict:
    """Assemble the packet from the selected bodies, in router order, under the document and byte caps."""
    by_path = {d["doc_path"]: d for d in documents}
    header = f"# Repository memory packet\n\nRecorded at revision {revision_s[:12]}. The repository may have changed since.\n"
    text, used, entries, truncated_claims = header, len(header.encode("utf-8")), [], 0
    for rank, item in enumerate(routed["documents"][:max_docs], 1):
        document = by_path[item["path"]]
        changed = routed["stale_documents"].get(item["path"])
        freshness = f"stale-document (covered file changed: {', '.join(changed)})" if changed else "no finding"
        block = f"\n## {rank}. {item['path']}\n\nrouter: score={item['score']}, authority={item['authority']}, freshness={freshness}\nsource: `{document['covers']}`\n\n"
        if used + len(block.encode("utf-8")) > max_bytes:
            truncated_claims += len(document["claim_ids"])
            entries.append({"rank": rank, "doc_path": item["path"], "covers": document["covers"], "score": item["score"], "stale": bool(changed), "changed_files": changed or [], "claim_ids": [], "dropped_claim_ids": document["claim_ids"]})
            continue
        text += block
        used += len(block.encode("utf-8"))
        kept, dropped = [], []
        for claim_id, line in zip(document["claim_ids"], document["claim_lines"].split("\n")):
            size = len((line + "\n").encode("utf-8"))
            if used + size > max_bytes:
                dropped.append(claim_id)
                continue
            text += line + "\n"
            used += size
            kept.append(claim_id)
        truncated_claims += len(dropped)
        entries.append({"rank": rank, "doc_path": item["path"], "covers": document["covers"], "score": item["score"], "stale": bool(changed), "changed_files": changed or [], "claim_ids": kept, "dropped_claim_ids": dropped})
    data = text.encode("utf-8")
    return {"text": text, "sha256": sha256_bytes(data), "bytes": len(data), "byte_cap": max_bytes, "doc_cap": max_docs, "documents": entries, "truncated_claims": truncated_claims, "token_accounting": "UTF-8 bytes; no tokenizer for this backend", "router_status": routed["status"]}


def packet_claim_ids(text: str) -> list[str]:
    return [m.group(1) for m in (CLAIM_LINE.match(line) for line in text.splitlines()) if m]

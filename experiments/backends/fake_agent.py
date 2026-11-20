#!/usr/bin/env python3
"""Deterministic fake agent for smoke tests.

Same file contract as ``toolloop_agent.py``. It makes no model call. Every
result carries ``is_live: false`` so that no report can count it as an agent
observation.

Behaviour: it "inspects" the first existing workspace path named in backticks
in, in order, the planner handoff, the memory packet, the issue text; failing
that, the first Python file. A planner writes a one-line handoff. A writing
role appends one comment line to the inspected file, which gives the caller a
real diff to capture.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ADAPTER_VERSION = "fake-1"
CAPABILITIES = {
    "can_reset_session": True,
    "can_limit_time": True,
    "can_count_actions": True,
    "can_capture_diff": True,
    "observable_reads": True,
    "usage_source": None,
}
MARK = "# fake-agent edit (not a model output)\n"


def pick_target(workspace: Path, texts: list[str]) -> str | None:
    for text in texts:
        for candidate in re.findall(r"`([^`\n]+)`", text):
            cleaned = candidate.strip().split("::")[0]
            if cleaned and (workspace / cleaned).is_file():
                return cleaned.replace("\\", "/")
    for path in sorted(workspace.rglob("*.py")):
        if ".git" not in path.parts:
            return path.relative_to(workspace).as_posix()
    return None


def run(request: dict) -> dict:
    workspace = Path(request["workspace"])
    texts = []
    if request.get("handoff_path") and Path(request["handoff_path"]).is_file():
        texts.append(Path(request["handoff_path"]).read_text(encoding="utf-8"))
    texts.extend(Path(p).read_text(encoding="utf-8") for p in request.get("context_paths") or [])
    texts.append(request.get("issue_text", ""))
    target = pick_target(workspace, texts)
    events = []
    role = request.get("role")
    max_actions = int((request.get("limits") or {}).get("max_actions", 8))

    def emit(**fields):
        events.append({"seq": len(events) + 1, "t_ms": len(events), "role": role, **fields})

    actions = 0
    if target and actions < max_actions:
        actions += 1
        emit(type="tool_call", tool="read_file", path=target, range=[1, 1], args=json.dumps({"path": target}), result="(fake read)", ok=True, action_index=actions)
    if target and not request.get("read_only") and actions < max_actions:
        actions += 1
        with open(workspace / target, "a", encoding="utf-8", newline="") as handle:
            handle.write(MARK)
        emit(type="tool_call", tool="replace_in_file", path=target, range=None, args=json.dumps({"path": target}), result=f"edited {target}", ok=True, action_index=actions)
    answer = f"Inspect `{target}`." if target else "No file found."
    emit(type="terminal", status="completed", exit_reason="finished", actions=actions, answer=answer)
    events_path = Path(request["out"]["events"])
    events_path.parent.mkdir(parents=True, exist_ok=True)
    with open(events_path, "w", encoding="utf-8", newline="\n") as handle:
        for event in events:
            handle.write(json.dumps(event) + "\n")
    return {
        "schema_version": 1,
        "run_id": request.get("run_id"),
        "role": role,
        "status": "completed",
        "exit_reason": "finished",
        "error": None,
        "is_live": False,
        "backend": {"agent": ADAPTER_VERSION, "model": "none", "version": ADAPTER_VERSION, "quantization": None, "location": "local"},
        "capabilities": CAPABILITIES,
        "elapsed_ms": 0,
        "actions": actions,
        "refused_after_limit": 0,
        "usage": {"input_tokens": None, "output_tokens": None, "cache_read_tokens": None, "source": None},
        "final_answer": answer,
        "no_patch": None,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Deterministic fake agent")
    parser.add_argument("--request")
    parser.add_argument("--capabilities", action="store_true")
    args = parser.parse_args()
    if args.capabilities:
        print(json.dumps({"adapter": ADAPTER_VERSION, "is_live": False, **CAPABILITIES}))
        return 0
    request = json.loads(Path(args.request).read_text(encoding="utf-8"))
    result = run(request)
    Path(request["out"]["result"]).write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())

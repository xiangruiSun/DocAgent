#!/usr/bin/env python3
"""Neutral agent adapter: a small tool loop over a chat endpoint.

Contract (shared by the case-study and paired-run packages, by file, not import):

    python toolloop_agent.py --request request.json
    python toolloop_agent.py --capabilities

The request names a workspace, an issue, a role prompt, optional context files
and limits. The adapter writes an event JSONL, a result JSON and nothing else:
the caller captures the diff from the workspace. Every file tool is confined to
the workspace, there is no shell tool and no network tool, so the model cannot
read anything the caller did not place in the workspace or the prompt.

Two request shapes are supported so that one adapter covers a local model and a
hosted one: ``api_style: "ollama"`` (native /api/chat, lets us pin num_ctx and
seed) and ``api_style: "openai"`` (any /chat/completions compatible endpoint).
Credentials are read from the environment variable named by ``api_key_env``.
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

ADAPTER_VERSION = "toolloop-1"
EXCERPT_BYTES = 512
READ_MAX_LINES = 160
READ_MAX_CHARS = 9000
SEARCH_MAX_HITS = 30
LIST_MAX = 200

CAPABILITIES = {
    "can_reset_session": True,  # every invocation starts from an empty message list
    "can_limit_time": True,
    "can_count_actions": True,
    "can_capture_diff": True,  # the caller diffs the workspace; this adapter never fabricates one
    "observable_reads": True,
    "usage_source": "provider_reported",
}

TOOL_DEFS = {
    "list_dir": {
        "description": "List files and folders in a workspace directory.",
        "parameters": {"type": "object", "properties": {"path": {"type": "string", "description": "Directory relative to the workspace root; use '.' for the root."}}, "required": ["path"]},
    },
    "read_file": {
        "description": f"Read a text file with line numbers. Returns at most {READ_MAX_LINES} lines per call; pass start_line to continue.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "start_line": {"type": "integer", "description": "1-based first line, default 1"},
                "end_line": {"type": "integer", "description": "1-based last line, optional"},
            },
            "required": ["path"],
        },
    },
    "search": {
        "description": f"Search file contents with a regular expression. Returns up to {SEARCH_MAX_HITS} matches as path:line: text.",
        "parameters": {
            "type": "object",
            "properties": {
                "pattern": {"type": "string"},
                "glob": {"type": "string", "description": "Optional file name pattern such as *.py"},
            },
            "required": ["pattern"],
        },
    },
    "replace_in_file": {
        "description": "Edit a file by replacing one exact, unique occurrence of old_text with new_text. Include enough surrounding lines to make old_text unique.",
        "parameters": {
            "type": "object",
            "properties": {"path": {"type": "string"}, "old_text": {"type": "string"}, "new_text": {"type": "string"}},
            "required": ["path", "old_text", "new_text"],
        },
    },
    "finish": {
        "description": "End the session. Put your final answer or handoff note in 'answer'.",
        "parameters": {"type": "object", "properties": {"answer": {"type": "string"}}, "required": ["answer"]},
    },
}
READ_ONLY_TOOLS = ("list_dir", "read_file", "search", "finish")
ALL_TOOLS = ("list_dir", "read_file", "search", "replace_in_file", "finish")


class ToolError(Exception):
    pass


def excerpt(value: Any, limit: int = EXCERPT_BYTES) -> str:
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
    raw = text.encode("utf-8")
    if len(raw) <= limit:
        return text
    return raw[:limit].decode("utf-8", errors="ignore") + "…"


class Workspace:
    """File access confined to one directory tree."""

    def __init__(self, root: Path):
        self.root = root.resolve()

    def resolve(self, relative: Any) -> Path:
        text = str(relative or ".").replace("\\", "/").strip()
        candidate = (self.root / text).resolve()
        try:
            rel = candidate.relative_to(self.root)
        except ValueError:
            raise ToolError("refused: path is outside the workspace")
        if ".git" in rel.parts:
            raise ToolError("refused: the .git directory is not readable")
        return candidate

    def rel(self, path: Path) -> str:
        return path.relative_to(self.root).as_posix()

    def list_dir(self, path: Any = ".") -> str:
        target = self.resolve(path)
        if not target.is_dir():
            raise ToolError(f"not a directory: {path}")
        rows = []
        for item in sorted(target.iterdir(), key=lambda p: (p.is_file(), p.name)):
            if item.name == ".git":
                continue
            rows.append(item.name + ("/" if item.is_dir() else ""))
        more = "" if len(rows) <= LIST_MAX else f"\n… {len(rows) - LIST_MAX} more entries"
        return "\n".join(rows[:LIST_MAX]) + more

    def read_file(self, path: Any, start_line: Any = 1, end_line: Any = None) -> tuple[str, list[int]]:
        target = self.resolve(path)
        if not target.is_file():
            raise ToolError(f"file not found: {path}")
        lines = target.read_text(encoding="utf-8", errors="replace").splitlines()
        try:
            start = max(int(start_line or 1), 1)
        except (TypeError, ValueError):
            start = 1
        try:
            end = int(end_line) if end_line not in (None, "") else start + READ_MAX_LINES - 1
        except (TypeError, ValueError):
            end = start + READ_MAX_LINES - 1
        end = min(end, start + READ_MAX_LINES - 1, len(lines))
        body, used = [], 0
        last = start - 1
        for number in range(start, end + 1):
            row = f"{number}: {lines[number - 1]}"
            used += len(row) + 1
            if used > READ_MAX_CHARS:
                break
            body.append(row)
            last = number
        header = f"{self.rel(target)} lines {start}-{last} of {len(lines)}"
        return header + "\n" + "\n".join(body), [start, last]

    def search(self, pattern: Any, glob: Any = None) -> str:
        try:
            regex = re.compile(str(pattern))
        except re.error:
            regex = re.compile(re.escape(str(pattern)))
        hits: list[str] = []
        for directory, folders, files in os.walk(self.root):
            folders[:] = sorted(f for f in folders if f != ".git")
            for name in sorted(files):
                if glob and not fnmatch.fnmatch(name, str(glob).split("/")[-1]):
                    continue
                path = Path(directory) / name
                try:
                    if path.stat().st_size > 1_000_000:
                        continue
                    text = path.read_text(encoding="utf-8")
                except (OSError, UnicodeDecodeError):
                    continue
                for number, line in enumerate(text.splitlines(), 1):
                    if regex.search(line):
                        hits.append(f"{self.rel(path)}:{number}: {line.strip()[:160]}")
                        if len(hits) >= SEARCH_MAX_HITS:
                            return "\n".join(hits) + f"\n… stopped at {SEARCH_MAX_HITS} matches"
        return "\n".join(hits) if hits else "no matches"

    def replace_in_file(self, path: Any, old_text: Any, new_text: Any) -> str:
        target = self.resolve(path)
        if not target.is_file():
            raise ToolError(f"file not found: {path}")
        with open(target, "r", encoding="utf-8", newline="") as handle:
            text = handle.read()
        old, new = str(old_text), str(new_text)
        if "\r\n" in text and "\r\n" not in old:
            old, new = old.replace("\n", "\r\n"), new.replace("\n", "\r\n")
        count = text.count(old)
        if not old or count == 0:
            raise ToolError("old_text was not found; read the file and copy the exact text")
        if count > 1:
            raise ToolError(f"old_text occurs {count} times; include more surrounding lines")
        with open(target, "w", encoding="utf-8", newline="") as handle:
            handle.write(text.replace(old, new, 1))
        return f"edited {self.rel(target)}"


def http_json(url: str, payload: dict, headers: dict, timeout: float) -> dict:
    request = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers={"Content-Type": "application/json", **headers})
    with urllib.request.urlopen(request, timeout=max(timeout, 1.0)) as response:
        return json.loads(response.read().decode("utf-8"))


class Chat:
    """One chat endpoint, two wire shapes."""

    def __init__(self, settings: dict):
        self.settings = settings
        self.style = settings.get("api_style", "ollama")
        self.base = str(settings.get("base_url", "http://127.0.0.1:11434")).rstrip("/")
        self.model = settings["model"]
        self.headers: dict[str, str] = {}
        key_env = settings.get("api_key_env")
        if key_env and os.environ.get(key_env):
            self.headers["Authorization"] = "Bearer " + os.environ[key_env]
        self.usage = {"input_tokens": None, "output_tokens": None, "cache_read_tokens": None}

    def _add(self, key: str, value: Any) -> None:
        if isinstance(value, int):
            self.usage[key] = (self.usage[key] or 0) + value

    def tools(self, names: tuple[str, ...]) -> list[dict]:
        return [{"type": "function", "function": {"name": name, **TOOL_DEFS[name]}} for name in names]

    def complete(self, messages: list[dict], tool_names: tuple[str, ...], timeout: float) -> tuple[dict, list[dict]]:
        """Return (assistant message to append, [{id, name, arguments}])."""
        if self.style == "ollama":
            options = {"temperature": self.settings.get("temperature", 0)}
            for key in ("seed", "num_ctx", "num_predict"):
                if self.settings.get(key) is not None:
                    options[key] = self.settings[key]
            payload: dict[str, Any] = {"model": self.model, "messages": messages, "tools": self.tools(tool_names), "stream": False, "options": options}
            if self.settings.get("think") is not None:
                payload["think"] = self.settings["think"]
            data = http_json(self.base + "/api/chat", payload, self.headers, timeout)
            message = data.get("message", {})
            self._add("input_tokens", data.get("prompt_eval_count"))
            self._add("output_tokens", data.get("eval_count"))
            calls = [{"id": None, "name": c.get("function", {}).get("name"), "arguments": c.get("function", {}).get("arguments") or {}} for c in message.get("tool_calls") or []]
            keep = {"role": "assistant", "content": message.get("content", "")}
            if message.get("tool_calls"):
                keep["tool_calls"] = message["tool_calls"]
            return keep, calls
        payload = {"model": self.model, "messages": messages, "tools": self.tools(tool_names), "temperature": self.settings.get("temperature", 0)}
        if self.settings.get("seed") is not None:
            payload["seed"] = self.settings["seed"]
        payload.update(self.settings.get("extra_body") or {})
        data = http_json(self.base + "/chat/completions", payload, self.headers, timeout)
        message = data["choices"][0]["message"]
        usage = data.get("usage") or {}
        self._add("input_tokens", usage.get("prompt_tokens"))
        self._add("output_tokens", usage.get("completion_tokens"))
        self._add("cache_read_tokens", (usage.get("prompt_tokens_details") or {}).get("cached_tokens"))
        calls = []
        for call in message.get("tool_calls") or []:
            raw = call.get("function", {}).get("arguments") or "{}"
            try:
                arguments = json.loads(raw) if isinstance(raw, str) else raw
            except json.JSONDecodeError:
                arguments = {"_unparsed": raw}
            calls.append({"id": call.get("id"), "name": call.get("function", {}).get("name"), "arguments": arguments})
        keep = {"role": "assistant", "content": message.get("content") or ""}
        if message.get("tool_calls"):
            keep["tool_calls"] = message["tool_calls"]
        return keep, calls

    def tool_message(self, call: dict, content: str) -> dict:
        if self.style == "ollama":
            return {"role": "tool", "tool_name": call["name"], "content": content}
        return {"role": "tool", "tool_call_id": call["id"], "content": content}

    def identity(self) -> dict:
        info = {"agent": ADAPTER_VERSION, "model": self.model, "version": None, "quantization": self.settings.get("quantization"), "location": self.settings.get("location"), "api_style": self.style, "base_url": self.base}
        if self.style == "ollama":
            try:
                with urllib.request.urlopen(self.base + "/api/version", timeout=5) as response:
                    info["version"] = "ollama " + json.loads(response.read().decode("utf-8")).get("version", "")
                shown = http_json(self.base + "/api/show", {"model": self.model}, {}, 10)
                details = shown.get("details") or {}
                info["quantization"] = details.get("quantization_level") or info["quantization"]
                info["parameter_size"] = details.get("parameter_size")
            except (OSError, ValueError, urllib.error.URLError):
                pass
        return info


def build_user_message(request: dict) -> str:
    parts = ["## Issue\n\n" + request.get("issue_text", "").strip()]
    for path in request.get("context_paths") or []:
        parts.append("## Repository memory packet\n\n" + Path(path).read_text(encoding="utf-8").strip())
    if request.get("handoff_path") and Path(request["handoff_path"]).is_file():
        parts.append("## Planner handoff\n\n" + Path(request["handoff_path"]).read_text(encoding="utf-8").strip())
    limits = request.get("limits", {})
    parts.append(f"You have at most {limits.get('max_actions')} tool actions and {limits.get('time_s')} seconds. Work inside the repository workspace only.")
    return "\n\n".join(parts)


def run(request: dict) -> dict:
    started = time.monotonic()
    settings = request.get("backend") or {}
    limits = request.get("limits") or {}
    deadline = started + float(limits.get("time_s", 180))
    max_actions = int(limits.get("max_actions", 8))
    workspace = Workspace(Path(request["workspace"]))
    tool_names = READ_ONLY_TOOLS if request.get("read_only") else ALL_TOOLS
    chat = Chat(settings)
    events_path = Path(request["out"]["events"])
    events_path.parent.mkdir(parents=True, exist_ok=True)
    seq = 0
    actions = 0
    final_answer: str | None = None
    exit_reason = "finished"
    status = "completed"
    error: str | None = None
    refused_after_limit = 0
    messages = [
        {"role": "system", "content": Path(request["prompt_path"]).read_text(encoding="utf-8")},
        {"role": "user", "content": build_user_message(request)},
    ]

    with open(events_path, "w", encoding="utf-8", newline="\n") as log:

        def emit(**fields: Any) -> None:
            nonlocal seq
            seq += 1
            row = {"seq": seq, "t_ms": int((time.monotonic() - started) * 1000), "role": request.get("role"), **fields}
            log.write(json.dumps(row, ensure_ascii=False) + "\n")
            log.flush()

        try:
            while final_answer is None:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    status, exit_reason = "budget_exhausted", "time_limit"
                    break
                offered = tool_names if actions < max_actions else ("finish",)
                message, calls = chat.complete(messages, offered, remaining)
                messages.append(message)
                if message.get("content"):
                    emit(type="message", text=excerpt(message["content"]))
                if not calls:
                    final_answer = message.get("content") or ""
                    break
                for call in calls:
                    name, args = call["name"], call["arguments"] if isinstance(call["arguments"], dict) else {}
                    if name == "finish":
                        final_answer = str(args.get("answer", ""))
                        messages.append(chat.tool_message(call, "ok"))
                        break
                    if actions >= max_actions:
                        refused_after_limit += 1
                        emit(type="refused", tool=name, reason="action_limit")
                        messages.append(chat.tool_message(call, "ACTION LIMIT REACHED. No further tool actions are possible. Call finish now."))
                        continue
                    actions += 1
                    path, line_range, ok = args.get("path"), None, True
                    try:
                        if name not in tool_names:
                            raise ToolError(f"tool not available in this session: {name}")
                        if name == "list_dir":
                            result = workspace.list_dir(args.get("path", "."))
                        elif name == "read_file":
                            result, line_range = workspace.read_file(args.get("path"), args.get("start_line", 1), args.get("end_line"))
                        elif name == "search":
                            result = workspace.search(args.get("pattern", ""), args.get("glob"))
                        else:
                            result = workspace.replace_in_file(args.get("path"), args.get("old_text", ""), args.get("new_text", ""))
                    except ToolError as exc:
                        result, ok = f"error: {exc}", False
                    shown = {k: v for k, v in args.items() if k not in ("old_text", "new_text")}
                    emit(type="tool_call", tool=name, path=str(path).replace("\\", "/") if path else None, range=line_range, args=excerpt(shown, 256), result=excerpt(result), ok=ok, action_index=actions)
                    messages.append(chat.tool_message(call, result))
                if refused_after_limit >= 2 and final_answer is None:
                    status, exit_reason = "action_limit", "action_limit"
                    break
            if final_answer is not None and refused_after_limit:
                exit_reason = "finished_after_action_limit"
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            if time.monotonic() >= deadline - 1:
                status, exit_reason = "budget_exhausted", "time_limit"
            else:
                status, exit_reason, error = "error", "backend_unreachable", str(exc)[:300]
        except (KeyError, ValueError) as exc:
            status, exit_reason, error = "error", "bad_backend_response", str(exc)[:300]
        emit(type="terminal", status=status, exit_reason=exit_reason, actions=actions, answer=excerpt(final_answer or ""))

    usage = dict(chat.usage)
    usage["source"] = "provider_reported" if usage["input_tokens"] is not None else None
    return {
        "schema_version": 1,
        "run_id": request.get("run_id"),
        "role": request.get("role"),
        "status": status,
        "exit_reason": exit_reason,
        "error": error,
        "is_live": True,
        "backend": chat.identity(),
        "capabilities": CAPABILITIES,
        "elapsed_ms": int((time.monotonic() - started) * 1000),
        "actions": actions,
        "refused_after_limit": refused_after_limit,
        "usage": usage,
        "final_answer": final_answer,
        "no_patch": None,  # the caller diffs the workspace
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--request")
    parser.add_argument("--capabilities", action="store_true")
    args = parser.parse_args()
    if args.capabilities:
        print(json.dumps({"adapter": ADAPTER_VERSION, "is_live": True, **CAPABILITIES}))
        return 0
    if not args.request:
        parser.error("--request is required")
    request = json.loads(Path(args.request).read_text(encoding="utf-8"))
    result = run(request)
    target = Path(request["out"]["result"])
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return 0 if result["status"] != "error" else 2


if __name__ == "__main__":
    sys.exit(main())

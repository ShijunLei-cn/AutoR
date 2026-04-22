"""Per-stage session log management.

Each stage execution writes a JSONL trace of the full "Claude Code"-style
conversation it ran to produce its artifacts: system prompt, tool calls,
tool results, assistant turns, approvals, etc. The Studio frontend reads this
trace so the operator can see *how* a stage arrived at its output, not just
the final markdown.

Layout on disk:
    runs/{run_id}/sessions/{stage_slug}.jsonl

Each line is one event:

    {
      "ts": "2026-04-09T17:12:03",
      "kind": "system" | "user" | "assistant" | "tool_use" | "tool_result" |
              "stage_start" | "stage_end" | "approval" | "feedback",
      "content": "...",          # free-form text for assistant / system / user
      "tool": { "name": "...", "input": {...} },    # for tool_use
      "output": "...",           # for tool_result
      "attempt": 1,
      "stage_slug": "01_literature_survey"
    }

The log is append-only and survives server restarts. The frontend polls the
latest N events and renders them in a chat-style timeline.
"""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


_write_locks: dict[Path, threading.Lock] = {}
_write_locks_lock = threading.Lock()


def _lock_for(path: Path) -> threading.Lock:
    with _write_locks_lock:
        lock = _write_locks.get(path)
        if lock is None:
            lock = threading.Lock()
            _write_locks[path] = lock
        return lock


def _sessions_dir(run_root: Path) -> Path:
    return run_root / "sessions"


def session_path(run_root: Path, stage_slug: str) -> Path:
    return _sessions_dir(run_root) / f"{stage_slug}.jsonl"


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def append_event(
    run_root: Path,
    stage_slug: str,
    kind: str,
    *,
    content: str | None = None,
    tool: dict[str, Any] | None = None,
    output: str | None = None,
    attempt: int | None = None,
    extra: dict[str, Any] | None = None,
) -> None:
    """Append one event to the stage session log. Thread-safe."""
    path = session_path(run_root, stage_slug)
    path.parent.mkdir(parents=True, exist_ok=True)

    event: dict[str, Any] = {
        "ts": _now_iso(),
        "kind": kind,
        "stage_slug": stage_slug,
    }
    if content is not None:
        event["content"] = content
    if tool is not None:
        event["tool"] = tool
    if output is not None:
        event["output"] = output
    if attempt is not None:
        event["attempt"] = attempt
    if extra:
        event.update(extra)

    line = json.dumps(event, ensure_ascii=True) + "\n"
    lock = _lock_for(path)
    with lock:
        with path.open("a", encoding="utf-8") as f:
            f.write(line)


def read_events(run_root: Path, stage_slug: str) -> list[dict[str, Any]]:
    """Read all events for a given stage. Returns [] if the file is missing."""
    path = session_path(run_root, stage_slug)
    if not path.exists():
        return []
    events: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return events


def summarize_sessions(run_root: Path) -> dict[str, int]:
    """Return a {stage_slug: event_count} map for all stages that have logs."""
    d = _sessions_dir(run_root)
    if not d.exists():
        return {}
    out: dict[str, int] = {}
    for path in sorted(d.glob("*.jsonl")):
        slug = path.stem
        count = 0
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    count += 1
        out[slug] = count
    return out


# ---------- Real-runner bridge: parse logs_raw.jsonl ----------
#
# When the real ResearchManager (Claude CLI) drives a run, it writes Claude's
# stream-json output to ``runs/{id}/logs_raw.jsonl``. The Studio's session
# viewer expects events in our own simplified shape. The functions below
# parse the raw log and convert it to that shape on demand so the right-side
# Progress Monitor in the Review page shows the live Claude trace without
# touching the runner code.


def parse_real_session(run_root: Path, stage_slug: str) -> list[dict[str, Any]]:
    """Parse runs/{id}/logs_raw.jsonl and return events for one stage.

    Streams the file line-by-line to avoid loading the entire (potentially
    100+ MB) log into memory on every poll tick.
    """
    raw_path = run_root / "logs_raw.jsonl"
    if not raw_path.exists():
        return []

    events: list[dict[str, Any]] = []
    in_stage = False
    attempt = 1
    try:
        with raw_path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue

                if "_meta" in rec:
                    meta = rec["_meta"]
                    meta_stage = meta.get("stage", "")
                    if meta_stage == stage_slug:
                        in_stage = True
                        attempt = int(meta.get("attempt", 1) or 1)
                        events.append({
                            "ts": _now_iso(),
                            "kind": "stage_start",
                            "stage_slug": stage_slug,
                            "attempt": attempt,
                            "content": (
                                f"Starting {stage_slug} (attempt {attempt}). "
                                f"Command: {' '.join(meta.get('command', [])[:3])}…"
                            ),
                        })
                    else:
                        in_stage = False
                    continue

                if not in_stage:
                    continue

                kind = rec.get("type", "")
                sub = rec.get("subtype", "")

                if kind == "system" and sub == "init":
                    model = rec.get("model", "")
                    tools = rec.get("tools", [])
                    events.append({
                        "ts": _now_iso(),
                        "kind": "system",
                        "stage_slug": stage_slug,
                        "attempt": attempt,
                        "content": (
                            f"Session initialized. Model: {model}. "
                            f"Tools: {', '.join(tools[:6])}{'…' if len(tools) > 6 else ''}"
                        ),
                    })
                    continue

                if kind == "assistant" and "message" in rec:
                    for block in rec["message"].get("content", []):
                        if not isinstance(block, dict):
                            continue
                        btype = block.get("type")
                        if btype == "text" and block.get("text", "").strip():
                            events.append({
                                "ts": _now_iso(),
                                "kind": "assistant",
                                "stage_slug": stage_slug,
                                "attempt": attempt,
                                "content": block["text"].strip()[:600],
                            })
                        elif btype == "thinking" and block.get("thinking", "").strip():
                            events.append({
                                "ts": _now_iso(),
                                "kind": "assistant",
                                "stage_slug": stage_slug,
                                "attempt": attempt,
                                "content": "💭 " + block["thinking"].strip()[:500],
                            })
                        elif btype == "tool_use":
                            events.append({
                                "ts": _now_iso(),
                                "kind": "tool_use",
                                "stage_slug": stage_slug,
                                "attempt": attempt,
                                "tool": {
                                    "name": block.get("name", ""),
                                    "input": _shrink_tool_input(block.get("input", {})),
                                },
                            })
                    continue

                if kind == "user" and "message" in rec:
                    for block in rec["message"].get("content", []):
                        if not isinstance(block, dict):
                            continue
                        if block.get("type") == "tool_result":
                            result = block.get("content", "")
                            if isinstance(result, list):
                                parts = []
                                for r in result:
                                    if isinstance(r, dict) and r.get("type") == "text":
                                        parts.append(r.get("text", ""))
                                    elif isinstance(r, str):
                                        parts.append(r)
                                result = "\n".join(parts)
                            events.append({
                                "ts": _now_iso(),
                                "kind": "tool_result",
                                "stage_slug": stage_slug,
                                "attempt": attempt,
                                "output": str(result)[:800],
                            })
                    continue

                if kind == "result":
                    events.append({
                        "ts": _now_iso(),
                        "kind": "stage_end",
                        "stage_slug": stage_slug,
                        "attempt": attempt,
                        "content": f"Stage attempt {attempt} complete. Outcome: {sub or 'success'}.",
                    })
    except Exception:
        pass

    return events


def _shrink_tool_input(value: Any, depth: int = 0) -> Any:
    """Truncate long strings in tool inputs so the UI stays compact."""
    if depth > 4:
        return "…"
    if isinstance(value, str):
        return value[:200] + ("…" if len(value) > 200 else "")
    if isinstance(value, list):
        return [_shrink_tool_input(v, depth + 1) for v in value[:8]]
    if isinstance(value, dict):
        return {k: _shrink_tool_input(v, depth + 1) for k, v in list(value.items())[:12]}
    return value

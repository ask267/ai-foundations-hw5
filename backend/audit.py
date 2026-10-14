"""Append-only audit trail of agent-loop activity: output/audit_trail.json.

The file is one JSON array, oldest event first. Events are appended as they
happen (so a crash still leaves a trail) and earlier events are never
rewritten or removed. To append, the writer seeks back to the closing `]`,
truncates just that bracket, and writes `,<event>]`, so the file is valid JSON
after every write. A lock keeps concurrent agents from interleaving.

Every event has: time, run_id, event, agent, depth, chain. Event types:

    run_start         team run begins: entry agent, task, approvals, read_only, limits
    agent_start       an agent's loop begins (entry or delegated): task
    model_step        one model response: step, finish_reason, tool calls asked for, tokens, text
    tool_call         MCP tool requested: tool, args
    tool_result       MCP tool returned: tool, ok, result summary, ms
    guard_block       the harness refused a tool call: tool, reason
    delegate_call     agent asked a teammate: teammate, task
    delegate_result   teammate answered: teammate, summary
    delegate_refused  delegation refused (loop / depth / budget): teammate, reason
    agent_end         an agent's loop ended: stop_reason, steps, summary
    run_end           team run ended: stop_reason, usage totals, delegations, duration

Long values are cut to MAX_TEXT characters.
"""

from __future__ import annotations

import json
import os
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic_core import to_jsonable_python

HERE = Path(__file__).resolve().parent
DEFAULT_AUDIT_PATH = HERE.parent / "output" / "audit_trail.json"
MAX_TEXT = 300

_lock = threading.Lock()


def audit_path() -> Path:
    return Path(os.getenv("AUDIT_PATH", DEFAULT_AUDIT_PATH))


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def new_run_id() -> str:
    return uuid.uuid4().hex[:12]


def short(value: Any, limit: int = MAX_TEXT) -> str:
    text = value if isinstance(value, str) else json.dumps(
        to_jsonable_python(value), separators=(",", ":"), ensure_ascii=False
    )
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def record(event: str, deps: Any = None, **fields: Any) -> None:
    """Append one event. `deps` (TeamDeps) supplies run_id/agent/depth/chain."""
    entry: dict[str, Any] = {"time": now(), "event": event}
    if deps is not None:
        entry.update(
            run_id=deps.run_id, agent=deps.agent, depth=deps.depth, chain=list(deps.chain)
        )
    entry.update(fields)
    _append(entry)


def _append(entry: dict) -> None:
    body = json.dumps(to_jsonable_python(entry), ensure_ascii=False)
    path = audit_path()
    with _lock:
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists() or path.stat().st_size == 0:
            path.write_text(f"[\n{body}\n]\n", encoding="utf-8")
            return
        with path.open("r+b") as f:
            end = f.seek(0, os.SEEK_END)
            f.seek(max(0, end - 4096))
            tail = f.read()
            close = tail.rfind(b"]")
            if close == -1:
                # Not an array we wrote: keep it under a new name, start fresh.
                f.close()
                path.rename(path.with_suffix(f".unreadable-{new_run_id()}.json"))
                path.write_text(f"[\n{body}\n]\n", encoding="utf-8")
                return
            empty = tail[:close].rstrip().endswith(b"[")
            f.seek(end - len(tail) + close)
            f.truncate()
            f.write((("\n" if empty else ",\n") + body + "\n]\n").encode("utf-8"))

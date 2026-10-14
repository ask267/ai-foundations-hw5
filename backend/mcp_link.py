"""The one connection between the agents and the campus-customs MCP server.

There is no other shop-tools layer: every shop fact and every write goes
through the MCP server defined in homework/hw5/.mcp.json. This module:

1. Builds a single MCPToolset (one stdio server process per team run) from the
   same .mcp.json entry Claude Code uses.
2. Gives each agent a filtered view that only lists its role's tools.
3. Wraps every MCP call (process_tool_call) to enforce guardrails and write
   tool_call / tool_result / guard_block events to the audit trail.
4. Gives the FastAPI backend (main.py) a plain client for its own routes, so
   the dashboard reads tickets/cash and approves payments through MCP too.

Guardrails enforced here (in code, not just in prompts):
- An agent can only call tools in its role's list.
- Agents can't move money at all: they only *prepare* payment/purchase
  requests. approve/reject are human-only tools no role can see or call.
- read_only runs block every write tool.
- Every write must trace back to the Boss (Boss is in the delegation chain).
- update_ticket's author and prepare_*'s prepared_by are stamped by the
  harness, so a model can't pretend to be another agent.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any

from fastmcp import Client
from pydantic_ai import RunContext
from pydantic_ai.mcp import CallToolFunc, MCPToolset
from pydantic_ai.toolsets import AbstractToolset

from agents import HUMAN_ONLY_TOOLS, SPECS, WRITE_TOOLS
from audit import record, short
from models import TeamDeps

HERE = Path(__file__).resolve().parent
MCP_CONFIG_PATH = HERE.parent / ".mcp.json"
SERVER_NAME = "campus-customs"


def _server_config(db_path: str | None) -> dict:
    """The campus-customs entry from .mcp.json, optionally pointed at another DB copy.

    Paths in .mcp.json are relative to the hw5 folder (so the repo works on any
    machine). If the configured interpreter doesn't exist, fall back to the
    Python running this backend, which has fastmcp installed too.
    """
    entry = dict(json.loads(MCP_CONFIG_PATH.read_text())["mcpServers"][SERVER_NAME])
    entry.pop("type", None)
    root = MCP_CONFIG_PATH.parent
    command = Path(entry["command"])
    if not command.is_absolute() and (root / command).exists():
        entry["command"] = str(root / command)
    elif not command.is_absolute() or not command.exists():
        entry["command"] = sys.executable
    entry["args"] = [str(root / a) if not Path(a).is_absolute() and (root / a).exists() else a
                     for a in entry.get("args", [])]
    entry["cwd"] = str(root)
    if db_path:
        entry["env"] = {**entry.get("env", {}), "CAMPUS_CUSTOMS_DB": str(Path(db_path).resolve())}
    return {"mcpServers": {SERVER_NAME: entry}}


def _blocked(deps: TeamDeps, tool: str, reason: str) -> dict:
    record("guard_block", deps, tool=tool, reason=reason)
    return {"ok": False, "blocked_by_harness": True, "error": reason}


def _guard(deps: TeamDeps, name: str, args: dict[str, Any]) -> tuple[dict[str, Any], str | None]:
    """Return (possibly stamped args, block reason or None)."""
    spec = SPECS[deps.agent]
    if name in HUMAN_ONLY_TOOLS:
        return args, f"{name} is human-only; agents can only prepare payments"
    if name not in spec.mcp_tools:
        return args, f"{deps.agent} is not allowed to use {name}"
    if name not in WRITE_TOOLS:
        return args, None
    if deps.read_only:
        return args, f"Read-only run: {name} is disabled"
    if "Boss" not in deps.chain:
        return args, f"{name} needs a Boss-led run (chain {list(deps.chain)})"

    args = dict(args)
    if name == "update_ticket":
        args["author"] = deps.agent
    elif name in ("prepare_payment", "prepare_purchase"):
        args["prepared_by"] = deps.agent
    return args, None


def _summarize(result: Any) -> tuple[bool, str]:
    data = result
    if isinstance(result, str):
        try:
            data = json.loads(result)
        except ValueError:
            return True, short(result)
    ok = not (isinstance(data, dict) and (data.get("ok") is False or data.get("found") is False))
    return ok, short(data)


async def _process_tool_call(
    ctx: RunContext[TeamDeps], call_tool: CallToolFunc, name: str, args: dict[str, Any]
) -> Any:
    deps = ctx.deps
    args, reason = _guard(deps, name, args)
    if reason:
        return _blocked(deps, name, reason)
    record("tool_call", deps, tool=name, args=short(args))
    started = time.perf_counter()
    try:
        result = await call_tool(name, args)
    except Exception as exc:  # tool errors are logged, then handled by the toolset
        record("tool_result", deps, tool=name, ok=False, result=short(str(exc)),
               ms=round((time.perf_counter() - started) * 1000))
        raise
    ok, summary = _summarize(result)
    record("tool_result", deps, tool=name, ok=ok, result=summary,
           ms=round((time.perf_counter() - started) * 1000))
    return result


def build_toolset(db_path: str | None = None) -> MCPToolset[TeamDeps]:
    """One MCP connection for the whole team. Enter it with `async with` once per run."""
    return MCPToolset(
        Client(_server_config(db_path)),
        id=SERVER_NAME,
        process_tool_call=_process_tool_call,
        tool_error_behavior="retry",
        max_retries=1,
    )


def admin_client(db_path: str | None = None) -> Client:
    """MCP client for the backend's own routes (tickets, cash, approve, reject)."""
    return Client(_server_config(db_path))


def role_view(toolset: MCPToolset[TeamDeps], agent: str) -> AbstractToolset[TeamDeps]:
    """The subset of MCP tools one role can see."""
    allowed = SPECS[agent].mcp_tools
    return toolset.filtered(lambda ctx, tool_def: tool_def.name in allowed)

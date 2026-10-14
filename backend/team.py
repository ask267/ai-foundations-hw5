"""Campus Customs agent team: Boss, Inventory, Accounting, Facilities, CustomerService.

    run_team(task, entry="Boss", read_only=False, run_id=None) -> TeamRunResult

Model:   gpt-6-luna for every agent, through Portkey's OpenAI-compatible
         gateway (PORTKEY_API_KEY from the project root .env).
Prompts: prompts/shop_rules.md (shared) + prompts/<role>.md, plus a dynamic
         block with the agent's place in the delegation chain, teammates
         and mode.
Money:   agents only PREPARE payments/purchases (pending requests). Cash
         moves when a human approves in the dashboard (main.py route).
Tools:   the campus-customs MCP server (mcp_link.py), filtered per role, plus
         `ask_teammate`, which every agent has. Any agent can delegate to any
         other agent (full mesh); loops are prevented by refusing teammates
         already in the chain.
Loop:    each agent runs its own PydanticAI loop (agent.iter). A delegation
         runs the teammate's loop inside the caller's tool call and returns
         its structured report. All agents in a run share one usage counter,
         so the team-wide limits below cap total tokens/requests.
Audit:   every loop step, tool call and delegation is appended to
         output/audit_trail.json (audit.py).

CLI:  python team.py "Work ticket 102" [--entry Boss] [--read-only] [--db PATH]
"""

from __future__ import annotations

import argparse
import asyncio
import contextvars
import json
import os
import sys
import time
from pathlib import Path

os.environ.setdefault("PYDANTIC_AI_NO_BANNER", "1")

from dotenv import load_dotenv
from openai import AsyncOpenAI
from pydantic_ai import Agent, RunContext, UsageLimits
from pydantic_ai.exceptions import UsageLimitExceeded
from pydantic_ai.mcp import MCPToolset
from pydantic_ai.models.openai import OpenAIResponsesModel
from pydantic_ai.providers.openai import OpenAIProvider
from pydantic_ai.settings import ModelSettings
from pydantic_ai.usage import RunUsage

from agents import SPECS
from audit import new_run_id, record, short
from mcp_link import build_toolset, role_view
from models import AGENT_NAMES, AgentName, AgentReport, BossReport, TeamBudget, TeamDeps, TeamRunResult, UsageTotals

HERE = Path(__file__).resolve().parent
PROMPTS = HERE / "prompts"
for _env in (HERE / ".env", HERE.parent / ".env", HERE.parents[2] / ".env"):
    load_dotenv(_env, override=False)

MODEL_NAME = "gpt-6-luna"  # the only model this team uses
PORTKEY_BASE_URL = os.getenv("PORTKEY_BASE_URL", "https://api.portkey.ai/v1")

# ---- limits that keep loops and token use in check -------------------------
MAX_DEPTH = 2            # Boss -> specialist -> specialist, no deeper
MAX_DELEGATIONS = 10     # ask_teammate calls per team run
MAX_AGENT_STEPS = 10     # model responses per single agent loop
TEAM_LIMITS = UsageLimits(  # shared by every agent in one run
    request_limit=40,
    tool_calls_limit=60,
    total_tokens_limit=300_000,
)
MODEL_SETTINGS = ModelSettings(max_tokens=4000)

_toolset: contextvars.ContextVar[MCPToolset[TeamDeps]] = contextvars.ContextVar("campus_toolset")
_agents: dict[AgentName, Agent[TeamDeps, BossReport | AgentReport]] = {}


# ---------------------------------------------------------------- building


def _model() -> OpenAIResponsesModel:
    api_key = os.getenv("PORTKEY_API_KEY")
    if not api_key:
        raise RuntimeError("PORTKEY_API_KEY not found. Put it in the project root .env.")
    # Portkey may serve cached responses for identical requests, which would
    # replay an old run instead of letting the agents think. Force a fresh
    # model call every time (set PORTKEY_CACHE_REFRESH=false to allow cache).
    headers = {}
    if os.getenv("PORTKEY_CACHE_REFRESH", "true").lower() != "false":
        headers["x-portkey-cache-force-refresh"] = "true"
    client = AsyncOpenAI(base_url=PORTKEY_BASE_URL, api_key=api_key, default_headers=headers)
    return OpenAIResponsesModel(MODEL_NAME, provider=OpenAIProvider(openai_client=client))


def _run_context(ctx: RunContext[TeamDeps]) -> str:
    """Dynamic instructions: where this agent sits in the current run."""
    d = ctx.deps
    can_ask = [
        f"- {n}: {SPECS[n].description}" for n in AGENT_NAMES if n not in d.chain
    ]
    lines = [
        "## This run",
        f"- You are **{d.agent}**. Delegation chain: {' -> '.join(d.chain)} (depth {d.depth} of max {MAX_DEPTH}).",
        f"- Mode: {'READ-ONLY - check and report; every write tool is disabled.' if d.read_only else 'You may act within your role.'}",
        "- Money: agents never pay. Accounting prepares requests; a human approves them on the dashboard.",
        f"- Delegations used: {d.budget.delegations} of {MAX_DELEGATIONS}.",
    ]
    if d.depth >= MAX_DEPTH:
        lines.append("- You are at max depth: you can't delegate further. Report back.")
    elif can_ask:
        lines.append("- Teammates you can ask with ask_teammate:")
        lines.extend(can_ask)
    return "\n".join(lines)


async def ask_teammate(ctx: RunContext[TeamDeps], teammate: AgentName, task: str) -> dict:
    """Hand a task to another agent and get its structured report back.

    teammate: Boss, Inventory, Accounting, Facilities or CustomerService.
    task: self-contained instructions - ticket id, exact SKU/size/qty or
          invoice/lease id, what you need back, and whether they may act or
          should only check. Include any Boss authorization verbatim.
    """
    d = ctx.deps
    reason = None
    if teammate == d.agent:
        reason = "You can't delegate to yourself."
    elif teammate in d.chain:
        reason = f"{teammate} is already in this chain ({' -> '.join(d.chain)}); report back instead."
    elif d.depth + 1 > MAX_DEPTH:
        reason = f"Max delegation depth {MAX_DEPTH} reached; report back with what you have."
    elif d.budget.delegations >= MAX_DELEGATIONS:
        reason = f"Team delegation budget ({MAX_DELEGATIONS}) used up; report back."
    if reason:
        record("delegate_refused", d, teammate=teammate, reason=reason)
        return {"refused": True, "reason": reason}

    d.budget.delegations += 1
    record("delegate_call", d, teammate=teammate, task=short(task))
    report = await _run_agent(teammate, task, d.for_teammate(teammate), ctx.usage)
    record("delegate_result", d, teammate=teammate, summary=short(report.summary))
    return report.model_dump(exclude_none=True)


def _build_agents() -> None:
    if _agents:
        return
    model = _model()
    shared = (PROMPTS / "shop_rules.md").read_text(encoding="utf-8")
    for name, spec in SPECS.items():
        role = (PROMPTS / spec.prompt_file).read_text(encoding="utf-8")
        agent: Agent[TeamDeps, BossReport | AgentReport] = Agent(
            model,
            name=name,
            deps_type=TeamDeps,
            output_type=spec.output_type,
            instructions=[shared, role, _run_context],
            tools=[ask_teammate],
            model_settings=MODEL_SETTINGS,
            retries=2,
        )
        _agents[name] = agent


# ------------------------------------------------------------------ the loop


async def _run_agent(
    name: AgentName, task: str, deps: TeamDeps, usage: RunUsage
) -> BossReport | AgentReport:
    """Run one agent's loop, logging every model step to the audit trail."""
    agent = _agents[name]
    record("agent_start", deps, task=short(task))
    step = 0
    try:
        async with agent.iter(
            task,
            deps=deps,
            usage=usage,
            usage_limits=TEAM_LIMITS,
            toolsets=[role_view(_toolset.get(), name)],
        ) as run:
            async for node in run:
                if not Agent.is_call_tools_node(node):
                    continue
                resp = node.model_response
                step += 1
                deps.budget.steps += 1
                calls = [p for p in resp.parts if p.part_kind == "tool-call"]
                text = " ".join(p.content for p in resp.parts if p.part_kind == "text")
                record(
                    "model_step", deps,
                    step=step,
                    model=resp.model_name,
                    finish_reason=resp.finish_reason,
                    tool_calls=[{"tool": c.tool_name, "args": short(c.args or {}, 200)} for c in calls],
                    input_tokens=resp.usage.input_tokens,
                    output_tokens=resp.usage.output_tokens,
                    text=short(text, 200) if text else None,
                )
                if step >= MAX_AGENT_STEPS and calls:
                    raise UsageLimitExceeded(f"{name} hit the {MAX_AGENT_STEPS}-step limit")
            output = run.result.output
    except UsageLimitExceeded as exc:
        record("agent_end", deps, stop_reason="usage_limit", steps=step, error=short(str(exc)))
        raise
    except Exception as exc:
        record("agent_end", deps, stop_reason="error", steps=step, error=short(f"{type(exc).__name__}: {exc}"))
        raise
    record("agent_end", deps, stop_reason="completed", steps=step, summary=short(output.summary))
    return output


async def run_team(
    task: str,
    entry: AgentName = "Boss",
    read_only: bool = False,
    db_path: str | None = None,
    run_id: str | None = None,
) -> TeamRunResult:
    """Run the team on one task, starting at `entry` (usually the Boss)."""
    if entry not in SPECS:
        raise ValueError(f"entry must be one of {AGENT_NAMES}")
    _build_agents()
    deps = TeamDeps(
        run_id=run_id or new_run_id(),
        agent=entry,
        depth=0,
        chain=(entry,),
        read_only=read_only,
        budget=TeamBudget(),
    )
    record(
        "run_start", deps,
        model=MODEL_NAME, task=short(task), read_only=read_only,
        limits={
            "max_depth": MAX_DEPTH, "max_delegations": MAX_DELEGATIONS,
            "max_agent_steps": MAX_AGENT_STEPS, "request_limit": TEAM_LIMITS.request_limit,
            "tool_calls_limit": TEAM_LIMITS.tool_calls_limit,
            "total_tokens_limit": TEAM_LIMITS.total_tokens_limit,
        },
    )
    started = time.perf_counter()
    usage = RunUsage()
    output = None
    stop_reason, error = "completed", None
    toolset = build_toolset(db_path)
    token = _toolset.set(toolset)
    try:
        async with toolset:
            output = await _run_agent(entry, task, deps, usage)
    except UsageLimitExceeded as exc:
        stop_reason, error = "usage_limit", str(exc)
    except Exception as exc:
        stop_reason, error = "error", f"{type(exc).__name__}: {exc}"
    finally:
        _toolset.reset(token)

    totals = UsageTotals(
        requests=usage.requests,
        tool_calls=usage.tool_calls,
        input_tokens=usage.input_tokens,
        output_tokens=usage.output_tokens,
        total_tokens=usage.total_tokens,
    )
    result = TeamRunResult(
        run_id=deps.run_id, entry_agent=entry, task=task, stop_reason=stop_reason, error=error,
        output=output, usage=totals, delegations=deps.budget.delegations,
        duration_s=round(time.perf_counter() - started, 2),
    )
    record(
        "run_end", deps, stop_reason=stop_reason, error=short(error) if error else None,
        usage=totals.model_dump(), delegations=result.delegations, steps=deps.budget.steps,
        duration_s=result.duration_s,
    )
    return result


# ---------------------------------------------------------------------- CLI


def main() -> None:
    p = argparse.ArgumentParser(description="Run the Campus Customs agent team.")
    p.add_argument("task", help="What the team should do, e.g. 'Work ticket 102'.")
    p.add_argument("--entry", default="Boss", choices=AGENT_NAMES, help="Agent that receives the task.")
    p.add_argument("--read-only", action="store_true", help="Block every write tool.")
    p.add_argument("--db", help="Database copy to use (default: data/campus_customs_new.db).")
    args = p.parse_args()
    result = asyncio.run(
        run_team(args.task, args.entry, args.read_only, args.db)
    )
    print(json.dumps(result.model_dump(exclude_none=True), indent=2))
    sys.exit(0 if result.stop_reason == "completed" else 1)


if __name__ == "__main__":
    main()

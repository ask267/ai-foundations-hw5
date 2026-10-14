"""Campus Customs Desk API — the backend the React dashboard calls.

Run from this folder:  uvicorn main:app --reload --port 8000

Every shop read and write goes through the campus-customs MCP server (one
long-lived client opened at startup); the agent team (team.py) opens its own
MCP connection per run. The only thing this file touches directly is the
database *file* for /api/reset and the audit-trail *file* for /api/events.

Money rule: agents only prepare payment/purchase requests. Cash changes only
in POST /api/payments/{id}/approve, after a human clicks Approve.
"""

from __future__ import annotations

import asyncio
import json
import shutil
from collections import Counter
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from agents import SPECS
from audit import audit_path, new_run_id, record, short
from mcp_link import admin_client
from models import AGENT_NAMES, TeamRunResult
from team import MODEL_NAME, run_team

HERE = Path(__file__).resolve().parent
DATA = HERE.parent / "data"
ORIGINAL_DB = DATA / "campus_customs.db"
WORKING_DB = DATA / "campus_customs_new.db"


# ------------------------------------------------------------------ state


class RunState(BaseModel):
    run_id: str
    ticket_id: int
    task: str
    status: Literal["running", "completed", "usage_limit", "error"] = "running"
    started_at: str
    finished_at: str | None = None
    result: TeamRunResult | None = None


_runs: dict[str, RunState] = {}
_tasks: set[asyncio.Task] = set()
_team_lock = asyncio.Lock()  # one team run at a time (one shared working DB)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@asynccontextmanager
async def lifespan(app: FastAPI):
    client = admin_client()
    async with client:
        app.state.mcp = client
        yield


app = FastAPI(title="Campus Customs Desk API", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    # The Vite dev page (http or https, localhost or 127.0.0.1, port 5173/5174).
    allow_origins=[f"{scheme}://{host}:{port}"
                   for scheme in ("http", "https")
                   for host in ("localhost", "127.0.0.1")
                   for port in (5173, 5174)],
    allow_methods=["*"],
    allow_headers=["*"],
)


async def mcp(tool: str, args: dict[str, Any] | None = None) -> dict:
    """Call one MCP tool through the backend's client and return its JSON."""
    try:
        result = await app.state.mcp.call_tool(tool, args or {})
    except Exception as exc:
        raise HTTPException(502, f"MCP tool {tool} failed: {exc}") from exc
    return result.structured_content or {}


# ---------------------------------------------------------------- tickets


def _state(status: str) -> str:
    return "resolved" if status == "resolved" else "open"


@app.get("/api/health")
async def health() -> dict:
    desk = await mcp("get_shop_date")
    return {
        "ok": True,
        "model": MODEL_NAME,
        "database": WORKING_DB.name,
        "shop_date": desk.get("date_today"),
        "team_busy": _team_lock.locked(),
    }


@app.get("/api/agents")
async def agents() -> list[dict]:
    return [
        {"name": s.name, "description": s.description, "mcp_tools": sorted(s.mcp_tools)}
        for s in SPECS.values()
    ]


@app.get("/api/tickets")
async def tickets() -> list[dict]:
    data = await mcp("list_tickets", {"status": "all"})
    pending = (await mcp("list_payment_requests", {"status": "pending"}))["requests"]
    out = []
    for t in data["tickets"]:
        out.append({
            **t,
            "state": _state(t["status"]),
            "pending_requests": [r["id"] for r in pending if r["ticket_id"] == t["id"]],
            "last_run_id": next(
                (r.run_id for r in reversed(_runs.values()) if r.ticket_id == t["id"]), None
            ),
        })
    return out


@app.get("/api/tickets/{ticket_id}")
async def ticket(ticket_id: int) -> dict:
    data = await mcp("get_ticket", {"ticket_id": ticket_id})
    if not data.get("found"):
        raise HTTPException(404, f"Ticket {ticket_id} not found")
    data["state"] = _state(data["ticket"]["status"])
    return data


class RunRequest(BaseModel):
    task: str | None = Field(default=None, description="Override the default 'Work ticket N end to end.'")
    read_only: bool = False


async def _run_in_background(state: RunState, read_only: bool) -> None:
    async with _team_lock:
        try:
            result = await run_team(state.task, "Boss", read_only=read_only, run_id=state.run_id)
            state.result = result
            state.status = result.stop_reason
        except Exception as exc:  # run_team records its own errors; this is a last resort
            state.status = "error"
            record("run_end", None, run_id=state.run_id, agent="Boss",
                   stop_reason="error", error=short(f"{type(exc).__name__}: {exc}"))
        finally:
            state.finished_at = _now()


@app.post("/api/tickets/{ticket_id}/run", status_code=202)
async def run_ticket(ticket_id: int, body: RunRequest | None = None) -> RunState:
    body = body or RunRequest()
    found = await mcp("get_ticket", {"ticket_id": ticket_id})
    if not found.get("found"):
        raise HTTPException(404, f"Ticket {ticket_id} not found")
    if _team_lock.locked():
        raise HTTPException(409, "The team is already working a ticket; try again when it finishes.")
    task = body.task or (
        f"Work ticket {ticket_id} end to end. Handle only ticket {ticket_id}; "
        "leave every other ticket alone."
    )
    state = RunState(run_id=new_run_id(), ticket_id=ticket_id, task=task, started_at=_now())
    _runs[state.run_id] = state
    job = asyncio.create_task(_run_in_background(state, body.read_only))
    _tasks.add(job)
    job.add_done_callback(_tasks.discard)
    return state


# ----------------------------------------------------------------- events


def _read_audit() -> list[dict]:
    path = audit_path()
    if not path.exists():
        return []
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except ValueError:
        return []


def _by_agent(events: list[dict]) -> dict[str, dict]:
    """What each agent said and which tools it used, from a list of events."""
    out: dict[str, dict] = {}
    for e in events:
        agent = e.get("agent")
        if agent not in AGENT_NAMES:
            continue
        a = out.setdefault(agent, {"said": [], "tools": Counter(), "asked": Counter(), "steps": 0})
        kind = e["event"]
        if kind == "model_step":
            a["steps"] += 1
            if e.get("text"):
                a["said"].append(e["text"])
        elif kind == "agent_end" and e.get("summary"):
            a["said"].append(e["summary"])
        elif kind == "tool_call":
            a["tools"][e["tool"]] += 1
        elif kind == "delegate_call":
            a["asked"][e["teammate"]] += 1
    for a in out.values():
        a["tools"] = dict(a["tools"])
        a["asked"] = dict(a["asked"])
    return out


@app.get("/api/events")
async def events(
    since: int = Query(0, ge=0, description="Return events with index >= since (use next_since to poll)."),
    run_id: str | None = None,
    limit: int = Query(200, ge=1, le=1000),
) -> dict:
    all_events = _read_audit()
    picked = [
        {"index": i, **e}
        for i, e in enumerate(all_events)
        if i >= since and (run_id is None or e.get("run_id") == run_id)
    ]
    picked = picked[-limit:]
    return {
        "events": picked,
        "next_since": len(all_events),
        "by_agent": _by_agent(picked),
        "team_busy": _team_lock.locked(),
    }


@app.get("/api/runs")
async def runs() -> list[RunState]:
    return list(reversed(_runs.values()))


@app.get("/api/runs/{run_id}")
async def run(run_id: str) -> dict:
    run_events = [{"index": i, **e} for i, e in enumerate(_read_audit()) if e.get("run_id") == run_id]
    state = _runs.get(run_id)
    if state is None and not run_events:
        raise HTTPException(404, f"Run {run_id} not found")
    return {
        "run": state,
        "by_agent": _by_agent(run_events),
        "events": run_events,
    }


# --------------------------------------------------------------- payments


@app.get("/api/payments")
async def payment_requests(status: str = "pending") -> dict:
    return await mcp("list_payment_requests", {"status": status})


class Decision(BaseModel):
    by: str = Field(default="owner", description="Name of the person approving/rejecting.")
    note: str = ""


@app.post("/api/payments/{request_id}/approve")
async def approve(request_id: int, body: Decision | None = None) -> dict:
    """The human Approve button: this is the only place cash changes."""
    body = body or Decision()
    result = await mcp("approve_payment_request", {"request_id": request_id, "approved_by": body.by})
    record("human_approval", None, run_id=None, agent="human", by=body.by,
           request_id=request_id, ok=result.get("ok", False), result=short(result))
    if not result.get("ok"):
        raise HTTPException(409, result.get("error", "Approval failed"))
    return result


@app.post("/api/payments/{request_id}/reject")
async def reject(request_id: int, body: Decision | None = None) -> dict:
    body = body or Decision()
    result = await mcp("reject_payment_request",
                       {"request_id": request_id, "rejected_by": body.by, "note": body.note})
    record("human_rejection", None, run_id=None, agent="human", by=body.by,
           request_id=request_id, ok=result.get("ok", False), result=short(result))
    if not result.get("ok"):
        raise HTTPException(409, result.get("error", "Rejection failed"))
    return result


# ------------------------------------------------------------------- cash


@app.get("/api/cash")
async def cash() -> dict:
    data = await mcp("get_cash_balance")
    checking = next((a for a in data.get("accounts", []) if a["name"] == "checking"), None)
    if checking is None:
        raise HTTPException(404, "No checking account in cash_accounts")
    pending = (await mcp("list_payment_requests", {"status": "pending"}))["requests"]
    pending_total = round(sum(r["amount"] for r in pending if r["account"] == "checking"), 2)
    return {
        "account": "checking",
        "balance": checking["balance"],
        "as_of": checking["date"],
        "pending_requests_total": pending_total,
        "balance_if_all_approved": round(checking["balance"] - pending_total, 2),
    }


# ------------------------------------------------------------------ reset


@app.post("/api/reset")
async def reset() -> dict:
    """Copy the original database over the working copy for a fresh run."""
    if _team_lock.locked():
        raise HTTPException(409, "Can't reset while the team is working a ticket.")
    shutil.copyfile(ORIGINAL_DB, WORKING_DB)
    _runs.clear()
    record("db_reset", None, run_id=None, agent="human",
           source=ORIGINAL_DB.name, target=WORKING_DB.name)
    return {"ok": True, "tickets": await tickets(), "cash": await cash()}

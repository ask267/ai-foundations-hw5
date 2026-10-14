"""Data types shared by the Campus Customs agent team.

TeamDeps     - per-agent-run context the harness passes to every agent
               (who is running, delegation chain, read-only flag).
AgentReport  - structured output of every specialist agent.
BossReport   - structured output of the Boss (one TicketOutcome per ticket).
TeamRunResult - what run_team() returns to callers (CLI now, API later).
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Literal

from pydantic import BaseModel, Field

AgentName = Literal["Boss", "Inventory", "Accounting", "Facilities", "CustomerService"]
AGENT_NAMES: tuple[AgentName, ...] = ("Boss", "Inventory", "Accounting", "Facilities", "CustomerService")

TicketStatus = Literal["open", "in_progress", "waiting", "resolved", "escalated"]


# ------------------------------------------------------------------ run deps


@dataclass
class TeamBudget:
    """Mutable counters shared by every agent in one team run."""

    delegations: int = 0
    steps: int = 0


@dataclass(frozen=True)
class TeamDeps:
    run_id: str
    agent: AgentName
    depth: int = 0
    chain: tuple[AgentName, ...] = ()
    # When True the harness blocks every MCP write tool (planning / status runs).
    read_only: bool = False
    budget: TeamBudget = field(default_factory=TeamBudget)

    def for_teammate(self, teammate: AgentName) -> "TeamDeps":
        return replace(self, agent=teammate, depth=self.depth + 1, chain=self.chain + (teammate,))


# ------------------------------------------------------------ agent outputs


class Finding(BaseModel):
    fact: str = Field(description="One concrete fact, with the exact numbers/ids from the tool.")
    source_tool: str = Field(description="The MCP tool (or teammate) the fact came from.")


class ActionTaken(BaseModel):
    tool: str = Field(description="A write tool (prepare_payment, prepare_purchase, adjust_inventory, update_ticket) or a delegation. Reads go in facts, not here.")
    summary: str = Field(description="What changed, with ids and amounts.")


class AgentReport(BaseModel):
    """What a specialist (Inventory, Accounting, Facilities, CustomerService) returns."""

    agent: AgentName
    ticket_id: int | None = Field(default=None, description="Ticket this work was for, if any.")
    summary: str = Field(description="2-4 sentences: the answer to the task.")
    facts: list[Finding] = Field(default_factory=list)
    actions: list[ActionTaken] = Field(default_factory=list, description="Writes made; empty if none.")
    needs_human: list[str] = Field(default_factory=list, description="Decisions only the owner can make.")
    customer_message: str | None = Field(default=None, description="Draft reply to the customer, if any.")
    payment_requests: list[int] = Field(default_factory=list, description="ids of payment/purchase requests prepared for human approval.")


class TicketOutcome(BaseModel):
    ticket_id: int
    status: TicketStatus = Field(description="Status the ticket is in after this run.")
    summary: str
    handled_by: list[AgentName] = Field(default_factory=list)
    actions: list[ActionTaken] = Field(default_factory=list)
    needs_human: list[str] = Field(default_factory=list)
    customer_message: str | None = None
    payment_requests: list[int] = Field(default_factory=list, description="Pending request ids awaiting human approval.")


class BossReport(BaseModel):
    """What the Boss returns for a team run."""

    summary: str = Field(description="Overall result in 2-5 sentences.")
    tickets: list[TicketOutcome] = Field(default_factory=list)
    needs_human: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------- run result


class UsageTotals(BaseModel):
    requests: int = 0
    tool_calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0


class TeamRunResult(BaseModel):
    run_id: str
    entry_agent: AgentName
    task: str
    stop_reason: Literal["completed", "usage_limit", "error"]
    error: str | None = None
    output: BossReport | AgentReport | None = None
    usage: UsageTotals = Field(default_factory=UsageTotals)
    delegations: int = 0
    duration_s: float = 0.0

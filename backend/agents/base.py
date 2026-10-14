"""AgentSpec: what makes each of the five agents different.

Every agent shares the same loop (team.py), model, MCP server, and the
`ask_teammate` delegation tool. A spec only sets the role's name, prompt file,
the MCP tools the role may see, and its output type.
"""

from __future__ import annotations

from dataclasses import dataclass

from models import AgentName

WRITE_TOOLS = frozenset({"update_ticket", "adjust_inventory", "prepare_payment", "prepare_purchase"})
# Only the backend's approve/reject routes call these; no agent role lists them.
HUMAN_ONLY_TOOLS = frozenset({"approve_payment_request", "reject_payment_request"})


@dataclass(frozen=True)
class AgentSpec:
    name: AgentName
    prompt_file: str            # file in backend/prompts/
    description: str            # one line shown to teammates in their context
    mcp_tools: frozenset[str]   # MCP tools this role can see and call
    output_type: type

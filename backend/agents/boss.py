from models import BossReport

from .base import AgentSpec

SPEC = AgentSpec(
    name="Boss",
    prompt_file="boss.md",
    description="Manager: routes tickets, decides which payments to prepare, sets ticket status.",
    mcp_tools=frozenset({
        "get_shop_date", "list_tickets", "get_ticket", "get_cash_balance", "list_payment_requests",
        "update_ticket",
    }),
    output_type=BossReport,
)

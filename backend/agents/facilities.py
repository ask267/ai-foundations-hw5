from models import AgentReport

from .base import AgentSpec

SPEC = AgentSpec(
    name="Facilities",
    prompt_file="facilities.md",
    description="Lease and landlord: verifies rent notices; vendor/courier logistics.",
    mcp_tools=frozenset({
        "get_shop_date", "get_ticket", "get_rent_due", "list_vendors", "get_cash_balance",
    }),
    output_type=AgentReport,
)

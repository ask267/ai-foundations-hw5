from models import AgentReport

from .base import AgentSpec

SPEC = AgentSpec(
    name="CustomerService",
    prompt_file="customer_service.md",
    description="Drafts honest customer replies (a human sends them).",
    mcp_tools=frozenset({
        "get_shop_date", "get_ticket", "check_stock", "get_invoice",
    }),
    output_type=AgentReport,
)

from models import AgentReport

from .base import AgentSpec

SPEC = AgentSpec(
    name="Accounting",
    prompt_file="accounting.md",
    description="Cash, invoices, rent, purchases, discount math. Only role that prepares payments for human approval.",
    mcp_tools=frozenset({
        "get_shop_date", "get_ticket", "get_cash_balance", "get_invoice", "get_rent_due",
        "list_payments", "list_payment_requests", "get_pricing", "quote_discount", "list_vendors",
        "prepare_payment", "prepare_purchase",
    }),
    output_type=AgentReport,
)

from models import AgentReport

from .base import AgentSpec

SPEC = AgentSpec(
    name="Inventory",
    prompt_file="inventory.md",
    description="Stock by SKU/size, alternatives, restock ETAs, stock adjustments.",
    mcp_tools=frozenset({
        "get_shop_date", "get_ticket", "check_stock", "get_pricing", "quote_discount",
        "get_invoice", "list_vendors",
        "adjust_inventory",
    }),
    output_type=AgentReport,
)

# Campus Customs MCP Server

A [FastMCP](https://gofastmcp.com) server (`campus-customs`) that gives every Homework 5 agent one shared, honest view of the Campus Customs back office. The Boss, Inventory, Accounting, Facilities, and CustomerService agents (and Claude Code) call these tools instead of guessing. Stock, prices, bills, rent, cash, and tickets always come from the database, and every change goes through a checked tool.

## Database

- Uses **`../data/campus_customs_new.db`**, the working copy. The path is resolved relative to `server.py`.
- The original `../data/campus_customs.db` is never opened.
- Set `CAMPUS_CUSTOMS_DB=/path/to/copy.db` to point the server at another copy (used for tests).

## Tools (18)

### Read
| Tool | Reads | Returns |
|---|---|---|
| `get_shop_date()` | `desk` | The shop's "today" and desk notes |
| `list_tickets(status="open")` | `tickets` | Tickets by status (or `all`), oldest first |
| `get_ticket(ticket_id)` | `tickets`, `inventory`, `pricing`, `leases`, `invoices`, `vendors` | The ticket plus its linked stock, list price, lease, and invoice/vendor |
| `check_stock(sku, size, qty_needed=1)` | `inventory` | Qty on hand, location, can_fill, shortfall, other sizes |
| `get_pricing(sku, qty=1)` | `pricing` | Unit cost, list price, margin, totals at list and at cost, max discount before a loss |
| `quote_discount(sku, qty, discount_pct)` | `pricing`, `inventory` | Discounted price and total, margin, below_cost, needs_owner_approval (>15%) |
| `get_rent_due(lease_id)` | `leases`, `desk`, `cash_accounts` | Landlord, rent, next due, days until due, balances |
| `get_invoice(invoice_id)` | `invoices`, `vendors`, `desk` | Amount, status, days overdue, vendor and lead days, ETA if paid today |
| `list_vendors()` | `vendors` | Vendors with specialty and lead days |
| `get_cash_balance()` | `cash_accounts`, `invoices`, `desk` | Balances plus the total owed on open invoices |
| `list_payments(limit=20)` | `payments` | Recent payments (so nothing is paid twice) |
| `list_payment_requests(status="pending")` | `payment_requests` | Payments and purchases prepared by agents, by status |

### Agent writes (each runs in one transaction and validates first; no cash moves)
| Tool | Writes | Checks |
|---|---|---|
| `update_ticket(ticket_id, status, note, author)` | `tickets` | Valid status; the note is appended, signed, and dated (old notes are kept) |
| `adjust_inventory(sku, size, delta, reason)` | `inventory` | Stock can't go negative; a reason is required |
| `prepare_payment(kind, ref_id, amount, ticket_id, reason, resolves_ticket, prepared_by)` | `payment_requests` | Files a **pending** request. Amount equals the invoice or rent exactly; invoice is open; rent no more than 10 days early; no duplicate payment or pending request; cash covers it plus all other pending requests |
| `prepare_purchase(vendor_id, sku, size, qty, ticket_id, reason, resolves_ticket, prepared_by)` | `payment_requests` | Files a **pending** restock purchase. Amount = `pricing.unit_cost` × qty (never typed in); vendor and SKU/size must exist; cash covers it plus pending requests |

### Human-only (called by the backend's approve/reject routes; no agent role has them)
| Tool | Writes | What it does |
|---|---|---|
| `approve_payment_request(request_id, approved_by)` | `payment_requests`, `payments`, `cash_accounts`, `invoices` / `leases`, `tickets` | Re-checks the request, then pays it: inserts the payment, lowers the balance, marks the invoice paid / moves the lease due date a month / records a paid purchase invoice, and notes (or resolves) the linked ticket |
| `reject_payment_request(request_id, rejected_by, note)` | `payment_requests`, `tickets` | Marks the request rejected and adds a ticket note. No money moves |

`payment_requests` isn't in the original database. The server creates it the first time any tool runs, so a freshly reset copy works too.

If a record doesn't exist, read tools return `"found": false` and write tools return `"ok": false` with an error. Neither ever makes up a value.

## Who can call what
The agent backend (`../backend/mcp_link.py`) shows each agent only its role's tools, and adds harness checks on top: writes must come from a Boss-led run, the human-only tools are blocked for every agent, and `author` / `prepared_by` are stamped by the harness. The FastAPI backend (`../backend/main.py`) uses this same server for its routes, including approve and reject. See `../output/harness.md`.

## Run

From the `hw5/` folder, using the single environment from `requirements.txt`:

```bash
source .venv/bin/activate
python mcp_server/server.py
```

The server runs over stdio. Claude Code, the agent team, and the FastAPI backend all start it from the same `hw5/.mcp.json` entry (`.venv/bin/python mcp_server/server.py`, relative to `hw5/`).
